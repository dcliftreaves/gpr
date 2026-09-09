#!/usr/bin/env python3
"""Probe stochastic Lab-L high-frequency synthesis on saved 100% crops.

This is a diagnostic bridge between the exact REF-HF oracle and a shippable
noise/detail addback. It removes selected candidate Lab-L wavelet detail bands,
then adds deterministic synthetic detail generated from white noise and scaled
to either the REF or candidate HF RMS. No REF phase/detail is copied.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color

try:
    import pywt
except Exception as exc:  # pragma: no cover
    pywt = None
    _PYWT_ERROR = exc
else:
    _PYWT_ERROR = None


Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
DASH = RUNS / "dashboard"
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402


DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
PREVIEW = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}


def load_rgb(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def from_lab(lab_img: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab_img.astype(np.float32)) * 255.0, 0, 255).astype(np.uint8)


def parse_candidate(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        return raw, raw
    label, run_hash = raw.split("=", 1)
    return label.strip(), run_hash.strip()


def pass_preview(m: dict) -> bool:
    return (
        m["lpips"] <= PREVIEW["lpips"]
        and m["ms_ssim"] >= PREVIEW["ms_ssim"]
        and m["y_psnr"] >= PREVIEW["y_psnr"]
        and m["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def metric_row(ref: np.ndarray, test: np.ndarray) -> dict:
    h = min(ref.shape[0], test.shape[0])
    w = min(ref.shape[1], test.shape[1])
    m = compute_visual_metrics(ref[:h, :w], test[:h, :w])
    m["preview_pass"] = pass_preview(m)
    return m


def crop_path(run_hash: str, image_id: str, kind: str, crop: str) -> Path:
    return RUNS / run_hash / f"{image_id}_{kind}_{crop}.png"


def split_l(
    l_chan: np.ndarray,
    wavelet: str,
    levels: int,
    hf_levels: int,
) -> tuple[np.ndarray, np.ndarray]:
    if pywt is None:
        raise RuntimeError(f"pywt is required: {_PYWT_ERROR}")
    coeffs = pywt.wavedec2(l_chan.astype(np.float32), wavelet, level=levels)
    low = [coeffs[0]]
    high = [np.zeros_like(coeffs[0])]
    first_hf = max(1, len(coeffs) - hf_levels)
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_hf:
            low.append(tuple(np.zeros_like(c) for c in detail))
            high.append(detail)
        else:
            low.append(detail)
            high.append(tuple(np.zeros_like(c) for c in detail))
    lf = pywt.waverec2(low, wavelet).astype(np.float32)
    hf = pywt.waverec2(high, wavelet).astype(np.float32)
    return lf[: l_chan.shape[0], : l_chan.shape[1]], hf[: l_chan.shape[0], : l_chan.shape[1]]


def synth_hf(
    shape: tuple[int, int],
    rng: np.random.Generator,
    wavelet: str,
    levels: int,
    hf_levels: int,
    target_rms: float,
    mode: str,
) -> np.ndarray:
    if mode == "white":
        base = rng.normal(0.0, 1.0, shape).astype(np.float32)
    elif mode == "laplace":
        base = rng.laplace(0.0, 1.0, shape).astype(np.float32)
    else:
        raise ValueError(f"unknown mode {mode!r}")
    _, hf = split_l(base, wavelet, levels, hf_levels)
    rms = float(np.sqrt(np.mean(hf * hf)))
    if rms <= 1e-9 or target_rms <= 0.0:
        return np.zeros(shape, dtype=np.float32)
    return (hf * (target_rms / rms)).astype(np.float32)


def assemble(base_lab: np.ndarray, l_chan: np.ndarray) -> np.ndarray:
    out = base_lab.copy()
    out[..., 0] = np.clip(l_chan, 0.0, 100.0)
    return from_lab(out)


def collect(args: argparse.Namespace) -> list[dict]:
    candidates = [parse_candidate(c) for c in args.candidate]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    scales = [float(s) for s in args.scales.split(",") if s.strip()]
    rows: list[dict] = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng_root = np.random.default_rng(args.seed)

    for image_id in args.images:
        ref_rgb = load_rgb(crop_path(args.ref_run, image_id, "REF", args.crop))
        ref_lab = to_lab(ref_rgb)
        ref_lf, ref_hf = split_l(ref_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
        ref_hf_rms = float(np.sqrt(np.mean(ref_hf * ref_hf)))
        Image.fromarray(ref_rgb).save(args.output_dir / f"{image_id}_REF.png")

        for candidate, run_hash in candidates:
            pipe_rgb = load_rgb(crop_path(run_hash, image_id, "PIPELINE", args.crop))
            pipe_lab = to_lab(pipe_rgb)
            pipe_lf, pipe_hf = split_l(pipe_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
            pipe_hf_rms = float(np.sqrt(np.mean(pipe_hf * pipe_hf)))
            original_m = metric_row(ref_rgb, pipe_rgb)
            signal_rgb = assemble(pipe_lab, pipe_lf)
            signal_m = metric_row(assemble(ref_lab, ref_lf), signal_rgb)
            rows.append({
                "image_id": image_id,
                "candidate": candidate,
                "run_hash": run_hash,
                "variant": "original",
                "png": f"../{run_hash}/{image_id}_PIPELINE_{args.crop}.png",
                "mode": "original",
                "scale": 1.0,
                "target": "candidate",
                "ref_hf_rms": ref_hf_rms,
                "candidate_hf_rms": pipe_hf_rms,
                "synth_hf_rms": pipe_hf_rms,
                **original_m,
            })
            rows.append({
                "image_id": image_id,
                "candidate": candidate,
                "run_hash": run_hash,
                "variant": "signal_only",
                "png": "",
                "mode": "none",
                "scale": 0.0,
                "target": "none",
                "ref_hf_rms": ref_hf_rms,
                "candidate_hf_rms": pipe_hf_rms,
                "synth_hf_rms": 0.0,
                **signal_m,
            })
            for target_name, target_rms in (("ref", ref_hf_rms), ("candidate", pipe_hf_rms)):
                for mode in modes:
                    for scale in scales:
                        seed = int(rng_root.integers(0, np.iinfo(np.uint32).max))
                        rng = np.random.default_rng(seed)
                        hf = synth_hf(
                            pipe_lf.shape,
                            rng,
                            args.wavelet,
                            args.levels,
                            args.hf_levels,
                            target_rms * scale,
                            mode,
                        )
                        l_chan = pipe_lf + hf
                        rgb = assemble(pipe_lab, l_chan)
                        label = f"{target_name}_{mode}_s{scale:g}"
                        png_name = f"{image_id}_{candidate}_{label}.png"
                        Image.fromarray(rgb).save(args.output_dir / png_name)
                        m = metric_row(ref_rgb, rgb)
                        rows.append({
                            "image_id": image_id,
                            "candidate": candidate,
                            "run_hash": run_hash,
                            "variant": label,
                            "png": str((args.output_dir / png_name).relative_to(DASH)),
                            "mode": mode,
                            "scale": scale,
                            "target": target_name,
                            "seed": seed,
                            "ref_hf_rms": ref_hf_rms,
                            "candidate_hf_rms": pipe_hf_rms,
                            "synth_hf_rms": float(np.sqrt(np.mean(hf * hf))),
                            **m,
                            "delta_lpips_vs_original": m["lpips"] - original_m["lpips"],
                            "delta_ms_ssim_vs_original": m["ms_ssim"] - original_m["ms_ssim"],
                        })
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    for key in sorted({(r["candidate"], r["variant"]) for r in rows}):
        candidate, variant = key
        group = [r for r in rows if (r["candidate"], r["variant"]) == key]
        worst = max(group, key=lambda r: (r["lpips"], -r["ms_ssim"]))
        out.append({
            "candidate": candidate,
            "variant": variant,
            "count": len(group),
            "pass_count": sum(1 for r in group if r["preview_pass"]),
            "worst_image": worst["image_id"],
            "worst_lpips": max(float(r["lpips"]) for r in group),
            "median_lpips": float(np.median([r["lpips"] for r in group])),
            "worst_ms_ssim": min(float(r["ms_ssim"]) for r in group),
            "median_ms_ssim": float(np.median([r["ms_ssim"] for r in group])),
            "worst_y_psnr": min(float(r["y_psnr"]) for r in group),
            "worst_dE2000_mean": max(float(r["dE2000_mean"]) for r in group),
            "mean_delta_lpips": float(np.mean([r.get("delta_lpips_vs_original", 0.0) for r in group])),
        })
    out.sort(key=lambda r: (r["pass_count"] != r["count"], r["worst_lpips"], -r["worst_ms_ssim"]))
    return out


def fmt(v: object, digits: int = 4) -> str:
    if v is None:
        return "-"
    if isinstance(v, str):
        return html.escape(v)
    if isinstance(v, bool):
        return "PASS" if v else "FAIL"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return str(v)
    return f"{float(v):.{digits}f}"


def write_html(rows: list[dict], summary: list[dict], args: argparse.Namespace) -> None:
    output_dir_rel = html.escape(str(args.output_dir.relative_to(DASH)))
    css = """
body { margin: 18px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: #f5f6f6; color: #202124; }
h1 { font-size: 22px; margin: 0 0 6px; }
h2 { font-size: 18px; margin: 28px 0 10px; }
p { max-width: 1160px; line-height: 1.45; color: #555; }
table { border-collapse: collapse; background: #fff; font-size: 12px; margin: 12px 0 20px; }
th, td { border: 1px solid #d8dee5; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #e8eef2; }
.pass { color: #0a6f2a; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
.strip { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 14px; }
.card { flex: 0 0 536px; width: 536px; box-sizing: border-box; background: white; border: 1px solid #d6dce1; border-radius: 6px; padding: 10px; }
.title { font-size: 13px; font-weight: 700; line-height: 1.3; min-height: 34px; }
.meta { font-size: 12px; color: #555; line-height: 1.35; margin: 6px 0; min-height: 96px; }
img { display: block; width: 512px; height: 512px; max-width: none; border: 1px solid #cfd6dc; background: #111; object-fit: contain; }
"""
    sum_rows = []
    for row in summary:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        sum_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['candidate'])}</td>"
            f"<td class='left'>{html.escape(row['variant'])}</td>"
            f"<td class='{cls}'>{row['pass_count']}/{row['count']}</td>"
            f"<td class='left'>{html.escape(row['worst_image'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['median_lpips'])}</td>"
            f"<td>{fmt(row['worst_ms_ssim'])}</td><td>{fmt(row['median_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'], 2)}</td><td>{fmt(row['worst_dE2000_mean'], 2)}</td>"
            f"<td>{fmt(row['mean_delta_lpips'])}</td>"
            "</tr>"
        )
    sections = []
    for image_id in args.images:
        cards = [
            f"<article class='card'><div class='title'>REF</div><div class='meta'>Original REF crop.</div>"
            f"<img src='{output_dir_rel}/{html.escape(image_id)}_REF.png'></article>"
        ]
        image_rows = [r for r in rows if r["image_id"] == image_id]
        image_rows.sort(key=lambda r: (r["candidate"], r["lpips"], r["variant"]))
        for row in image_rows[:24]:
            if row["variant"] == "original":
                src = f"../{html.escape(row['run_hash'])}/{html.escape(image_id)}_PIPELINE_{html.escape(args.crop)}.png"
            elif row["variant"] == "signal_only":
                continue
            else:
                src = html.escape(row["png"])
            cls = "pass" if row["preview_pass"] else "fail"
            cards.append(
                "<article class='card'>"
                f"<div class='title'>{html.escape(row['candidate'])}<br>{html.escape(row['variant'])}</div>"
                f"<div class='meta'><span class='{cls}'>LPIPS {row['lpips']:.4f} / MS {row['ms_ssim']:.4f}</span><br>"
                f"Y {row['y_psnr']:.2f} / dE {row['dE2000_mean']:.2f}<br>"
                f"target {html.escape(row['target'])} / mode {html.escape(row['mode'])} / scale {row['scale']:.2f}<br>"
                f"HF rms {row['synth_hf_rms']:.3f} / dLPIPS {fmt(row.get('delta_lpips_vs_original'))}</div>"
                f"<img src='{src}'></article>"
            )
        sections.append(f"<h2>{html.escape(image_id)} 100% crops</h2><div class='strip'>{''.join(cards)}</div>")
    args.output_html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Stochastic HF synthesis probe</title>"
        f"<style>{css}</style></head><body>"
        "<h1>Stochastic HF Synthesis Probe</h1>"
        "<p>Diagnostic only. Candidate Lab-L low-frequency signal is preserved; selected HF bands are replaced with deterministic synthetic noise/detail scaled by candidate or REF HF RMS. REF phase/detail is not copied.</p>"
        "<table><thead><tr><th class='left'>candidate</th><th class='left'>variant</th><th>pass</th>"
        "<th class='left'>worst image</th><th>worst LPIPS</th><th>median LPIPS</th><th>worst MS</th>"
        "<th>median MS</th><th>worst Y</th><th>worst dE</th><th>mean dLPIPS</th></tr></thead><tbody>"
        f"{''.join(sum_rows)}</tbody></table>"
        f"{''.join(sections)}</body></html>"
    )


class _ImageSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.srcs.append(src)


def validate_html_images(html_path: Path) -> None:
    parser = _ImageSrcParser()
    parser.feed(html_path.read_text())
    missing = []
    for src in parser.srcs:
        if not (html_path.parent / src).resolve().exists():
            missing.append(src)
    if missing:
        raise RuntimeError(f"{html_path} references missing images: {missing[:8]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref-run", required=True)
    ap.add_argument("--candidate", action="append", required=True)
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--crop", default="crop_A_detail")
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=3)
    ap.add_argument("--hf-levels", type=int, default=3)
    ap.add_argument("--modes", default="white,laplace")
    ap.add_argument("--scales", default="0.25,0.5,0.75,1.0,1.25")
    ap.add_argument("--seed", type=int, default=20260606)
    ap.add_argument("--output-dir", type=Path, default=DASH / "stochastic_hf_synthesis")
    ap.add_argument("--output-json", type=Path, default=DASH / "stochastic_hf_synthesis.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "stochastic_hf_synthesis.html")
    args = ap.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_json = args.output_json.resolve()
    args.output_html = args.output_html.resolve()

    rows = collect(args)
    summary = summarize(rows)
    args.output_json.write_text(json.dumps({
        "thresholds": PREVIEW,
        "wavelet": args.wavelet,
        "levels": args.levels,
        "hf_levels": args.hf_levels,
        "seed": args.seed,
        "summary": summary,
        "rows": rows,
    }, indent=2))
    write_html(rows, summary, args)
    validate_html_images(args.output_html)
    for row in summary:
        print(
            f"{row['candidate']:<18} {row['variant']:<24} "
            f"pass={row['pass_count']}/{row['count']} "
            f"worst={row['worst_image']} lpips={row['worst_lpips']:.4f} "
            f"ms={row['worst_ms_ssim']:.4f} dLPIPS={row['mean_delta_lpips']:+.4f}"
        )
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
