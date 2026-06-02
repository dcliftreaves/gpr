#!/usr/bin/env python3
"""Probe exact REF high-frequency Lab-L transfer on saved gate crops.

This is a diagnostic for the hypothesis that REF contains non-learnable
high-frequency luminance noise/detail that should be removed from the training
target, learned as low-frequency/detail signal, and then reintroduced for
visual equivalence analysis.

For each saved 100% crop pair this script scores:

  - original: candidate crop vs REF crop
  - signal_only: candidate LF Lab-L vs REF LF Lab-L
  - exact_ref_hf_added: candidate LF Lab-L + exact REF HF Lab-L vs original REF

The exact REF HF transfer is an oracle. It must not be used as a ship claim;
it tells us how much LPIPS/MS-SSIM is attributable to missing unlearnable REF
HF versus wrong low-frequency/detail placement.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage import color

try:
    import pywt
except Exception:  # pragma: no cover - optional diagnostic dependency
    pywt = None


Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
DASH = RUNS / "dashboard"
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402


DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
DEFAULT_CANDIDATES = (
    "baseline=5e7b79b5678fdf62",
    "lab_sips=5e7d52579ffb2d3e",
    "lab_l_residual_v1=5d3cf75bf1b1f44b",
    "w48_blocker_select=e5107f994eb2dd0b",
)
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


def lowpass_gaussian(l_chan: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(l_chan.astype(np.float32), (0, 0), sigma).astype(np.float32)


def lowpass_wavelet(
    l_chan: np.ndarray,
    wavelet: str,
    levels: int,
    remove_hf_levels: int,
) -> np.ndarray:
    if pywt is None:
        raise RuntimeError("pywt is required for --method wavelet")
    coeffs = pywt.wavedec2(l_chan.astype(np.float32), wavelet, level=levels)
    out = [coeffs[0]]
    # pywt detail order: index 1 = coarsest, last = finest.
    first_zero = max(1, len(coeffs) - remove_hf_levels)
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_zero:
            out.append(tuple(np.zeros_like(c) for c in detail))
        else:
            out.append(detail)
    rec = pywt.waverec2(out, wavelet).astype(np.float32)
    return rec[: l_chan.shape[0], : l_chan.shape[1]]


def lowpass(l_chan: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    if args.method == "gaussian":
        return lowpass_gaussian(l_chan, args.sigma)
    return lowpass_wavelet(l_chan, args.wavelet, args.levels, args.hf_levels)


def assemble_l(base_lab: np.ndarray, l_chan: np.ndarray) -> np.ndarray:
    out = base_lab.copy()
    out[..., 0] = np.clip(l_chan, 0.0, 100.0)
    return from_lab(out)


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


def parse_candidate(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        return raw, raw
    label, run_hash = raw.split("=", 1)
    return label.strip(), run_hash.strip()


def crop_path(run_hash: str, image_id: str, kind: str, crop: str) -> Path:
    return RUNS / run_hash / f"{image_id}_{kind}_{crop}.png"


def collect(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = [parse_candidate(c) for c in args.candidate]
    for image_id in args.images:
        ref_rgb = load_rgb(crop_path(args.ref_run, image_id, "REF", args.crop))
        ref_lab = to_lab(ref_rgb)
        ref_l = ref_lab[..., 0]
        ref_lf = lowpass(ref_l, args)
        ref_hf = ref_l - ref_lf
        ref_signal_rgb = assemble_l(ref_lab, ref_lf)
        Image.fromarray(ref_rgb).save(out_dir / f"{image_id}_REF_original.png")
        Image.fromarray(ref_signal_rgb).save(out_dir / f"{image_id}_REF_signal_lf.png")

        for label, run_hash in candidates:
            pipe_rgb = load_rgb(crop_path(run_hash, image_id, "PIPELINE", args.crop))
            pipe_lab = to_lab(pipe_rgb)
            pipe_l = pipe_lab[..., 0]
            pipe_lf = lowpass(pipe_l, args)
            pipe_hf = pipe_l - pipe_lf
            signal_rgb = assemble_l(pipe_lab, pipe_lf)
            exact_rgb = assemble_l(pipe_lab, pipe_lf + args.hf_gain * ref_hf)

            variants = {
                "original": pipe_rgb,
                "signal_only": signal_rgb,
                "exact_ref_hf_added": exact_rgb,
            }
            Image.fromarray(signal_rgb).save(out_dir / f"{image_id}_{label}_signal_only.png")
            Image.fromarray(exact_rgb).save(out_dir / f"{image_id}_{label}_exact_ref_hf_added.png")

            ref_variants = {
                "original": ref_rgb,
                "signal_only": ref_signal_rgb,
                "exact_ref_hf_added": ref_rgb,
            }
            original_m = None
            for variant, render in variants.items():
                m = metric_row(ref_variants[variant], render)
                if variant == "original":
                    original_m = m
                row = {
                    "image_id": image_id,
                    "candidate": label,
                    "run_hash": run_hash,
                    "variant": variant,
                    "png": (
                        str((out_dir / f"{image_id}_{label}_{variant}.png").relative_to(DASH))
                        if variant != "original"
                        else f"../{run_hash}/{image_id}_PIPELINE_{args.crop}.png"
                    ),
                    **m,
                    "ref_hf_rms": float(np.sqrt(np.mean(ref_hf * ref_hf))),
                    "candidate_hf_rms": float(np.sqrt(np.mean(pipe_hf * pipe_hf))),
                    "hf_rms_ratio": float(
                        (np.sqrt(np.mean(pipe_hf * pipe_hf)) + 1e-9)
                        / (np.sqrt(np.mean(ref_hf * ref_hf)) + 1e-9)
                    ),
                }
                if original_m and variant != "original":
                    row["delta_lpips_vs_original"] = m["lpips"] - original_m["lpips"]
                    row["delta_ms_ssim_vs_original"] = m["ms_ssim"] - original_m["ms_ssim"]
                rows.append(row)
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    keys = sorted({(r["candidate"], r["variant"]) for r in rows})
    for candidate, variant in keys:
        group = [r for r in rows if r["candidate"] == candidate and r["variant"] == variant]
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
        })
    out.sort(key=lambda r: (r["candidate"], {"original": 0, "signal_only": 1, "exact_ref_hf_added": 2}.get(r["variant"], 9)))
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
    by_image = {}
    for row in rows:
        by_image.setdefault(row["image_id"], []).append(row)
    output_dir_rel = html.escape(str(args.output_dir.relative_to(DASH)))
    css = """
body { margin: 18px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: #f5f5f1; color: #202124; }
h1 { font-size: 22px; margin: 0 0 6px; }
h2 { font-size: 18px; margin: 28px 0 10px; }
p { max-width: 1120px; line-height: 1.45; color: #555; }
table { border-collapse: collapse; background: #fff; font-size: 12px; margin: 12px 0 20px; }
th, td { border: 1px solid #d8d8d1; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #e8e8e1; }
.pass { color: #0a6f2a; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
.strip { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 14px; }
.card { flex: 0 0 536px; width: 536px; box-sizing: border-box; background: white; border: 1px solid #d6d6cf; border-radius: 6px; padding: 10px; }
.title { font-size: 13px; font-weight: 700; line-height: 1.3; min-height: 34px; }
.meta { font-size: 12px; color: #555; line-height: 1.35; margin: 6px 0; min-height: 78px; }
img { display: block; width: 512px; height: 512px; max-width: none; border: 1px solid #cfcfca; background: #111; object-fit: contain; }
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
            "</tr>"
        )
    sections = []
    for image_id in args.images:
        cards = [
            f"<article class='card'><div class='title'>REF original</div><div class='meta'>Original REF crop.</div>"
            f"<img src='{output_dir_rel}/{html.escape(image_id)}_REF_original.png'></article>",
            f"<article class='card'><div class='title'>REF signal LF</div><div class='meta'>REF with selected high-frequency Lab-L removed.</div>"
            f"<img src='{output_dir_rel}/{html.escape(image_id)}_REF_signal_lf.png'></article>",
        ]
        for row in [r for r in rows if r["image_id"] == image_id and r["variant"] in ("original", "signal_only", "exact_ref_hf_added")]:
            if row["variant"] == "original":
                src = f"../{html.escape(row['run_hash'])}/{html.escape(image_id)}_PIPELINE_{html.escape(args.crop)}.png"
            else:
                src = f"{output_dir_rel}/{html.escape(image_id)}_{html.escape(row['candidate'])}_{html.escape(row['variant'])}.png"
            cls = "pass" if row["preview_pass"] else "fail"
            cards.append(
                "<article class='card'>"
                f"<div class='title'>{html.escape(row['candidate'])}<br>{html.escape(row['variant'])}</div>"
                f"<div class='meta'><code>{html.escape(row['run_hash'])}</code><br>"
                f"<span class='{cls}'>LPIPS {row['lpips']:.4f} · MS {row['ms_ssim']:.4f}</span><br>"
                f"Y {row['y_psnr']:.2f} · dE {row['dE2000_mean']:.2f}<br>"
                f"HF RMS ratio {row['hf_rms_ratio']:.3f}"
                f"{'<br>dLPIPS ' + fmt(row.get('delta_lpips_vs_original')) if 'delta_lpips_vs_original' in row else ''}"
                "</div>"
                f"<img src='{src}'></article>"
            )
        sections.append(f"<h2>{html.escape(image_id)} 100% crops</h2><div class='strip'>{''.join(cards)}</div>")
    args.output_html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>REF HF noise transfer probe</title>"
        f"<style>{css}</style></head><body>"
        "<h1>REF HF Noise Transfer Probe</h1>"
        "<p>Diagnostic only. Lab-L is decomposed into low-frequency signal plus high-frequency residual. "
        "The oracle row adds exact REF HF back onto the candidate LF before comparing to original REF. "
        f"Method: <code>{html.escape(args.method)}</code>, wavelet=<code>{html.escape(args.wavelet)}</code>, "
        f"levels=<code>{args.levels}</code>, hf_levels=<code>{args.hf_levels}</code>, sigma=<code>{args.sigma}</code>.</p>"
        "<table><thead><tr><th class='left'>candidate</th><th class='left'>variant</th><th>pass</th>"
        "<th class='left'>worst image</th><th>worst LPIPS</th><th>median LPIPS</th><th>worst MS</th>"
        "<th>median MS</th><th>worst Y</th><th>worst dE</th></tr></thead><tbody>"
        f"{''.join(sum_rows)}</tbody></table>"
        f"{''.join(sections)}</body></html>"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref-run", default="5e7b79b5678fdf62")
    ap.add_argument("--candidate", action="append", default=None)
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--crop", default="crop_A_detail")
    ap.add_argument("--method", choices=("wavelet", "gaussian"), default="wavelet")
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=3)
    ap.add_argument("--hf-levels", type=int, default=1,
                    help="Number of finest wavelet detail levels treated as REF HF/noise.")
    ap.add_argument("--sigma", type=float, default=1.2)
    ap.add_argument("--hf-gain", type=float, default=1.0)
    ap.add_argument("--output-dir", type=Path, default=DASH / "ref_hf_noise_transfer")
    ap.add_argument("--output-json", type=Path, default=DASH / "ref_hf_noise_transfer.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "ref_hf_noise_transfer.html")
    args = ap.parse_args()
    if args.candidate is None:
        args.candidate = list(DEFAULT_CANDIDATES)
    args.output_dir = args.output_dir.resolve()
    args.output_json = args.output_json.resolve()
    args.output_html = args.output_html.resolve()

    rows = collect(args)
    summary = summarize(rows)
    args.output_json.write_text(json.dumps({
        "thresholds": PREVIEW,
        "method": args.method,
        "wavelet": args.wavelet,
        "levels": args.levels,
        "hf_levels": args.hf_levels,
        "sigma": args.sigma,
        "hf_gain": args.hf_gain,
        "summary": summary,
        "rows": rows,
    }, indent=2))
    write_html(rows, summary, args)
    for row in summary:
        print(
            f"{row['candidate']:<24} {row['variant']:<18} "
            f"pass={row['pass_count']}/{row['count']} "
            f"worst={row['worst_image']} lpips={row['worst_lpips']:.4f} "
            f"ms={row['worst_ms_ssim']:.4f}"
        )
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
