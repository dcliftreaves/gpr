#!/usr/bin/env python3
"""Probe shippable wavelet HF synthesis on saved 100% gate crops.

The REF-HF transfer probe measures an oracle: exact REF high-frequency Lab-L
can explain part of the LPIPS gap, but cannot ship. This probe tests the
shippable counterpart: amplify or attenuate the candidate's own Lab-L wavelet
detail bands, then re-score against REF.

Use this as a fast pre-gate screen. A useful result should improve LPIPS or
MS-SSIM on the blocker crop without breaking Y-PSNR or dE2000.
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
except Exception as exc:  # pragma: no cover - dependency check happens in main
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
DEFAULT_CANDIDATES = (
    "lab_sips=5e7d52579ffb2d3e",
    "lab_l_residual_v1=5d3cf75bf1b1f44b",
    "w48_blocker_select=e5107f994eb2dd0b",
)
DEFAULT_RECIPES = (
    "hf1_gain1p05=1:1.05",
    "hf1_gain1p10=1:1.10",
    "hf1_gain1p20=1:1.20",
    "hf2_gain1p05=2:1.05",
    "hf2_gain1p10=2:1.10",
    "hf2_gain1p20=2:1.20",
    "hf1_atten0p95=1:0.95",
    "hf2_atten0p95=2:0.95",
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


def parse_candidate(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        return raw, raw
    label, run_hash = raw.split("=", 1)
    return label.strip(), run_hash.strip()


def parse_recipe(raw: str) -> tuple[str, int, float]:
    """Parse label=hf_levels:gain, e.g. hf2_gain1p10=2:1.10."""
    if "=" not in raw or ":" not in raw:
        raise ValueError(f"recipe must be label=hf_levels:gain, got {raw!r}")
    label, spec = raw.split("=", 1)
    hf_levels_s, gain_s = spec.split(":", 1)
    hf_levels = int(hf_levels_s)
    gain = float(gain_s)
    if hf_levels < 1:
        raise ValueError(f"hf_levels must be >= 1 in {raw!r}")
    if gain <= 0:
        raise ValueError(f"gain must be > 0 in {raw!r}")
    return label.strip(), hf_levels, gain


def crop_path(run_hash: str, image_id: str, kind: str, crop: str) -> Path:
    return RUNS / run_hash / f"{image_id}_{kind}_{crop}.png"


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


def selected_hf(l_chan: np.ndarray, wavelet: str, levels: int, hf_levels: int) -> np.ndarray:
    if pywt is None:
        raise RuntimeError(f"pywt is required: {_PYWT_ERROR}")
    coeffs = pywt.wavedec2(l_chan.astype(np.float32), wavelet, level=levels)
    out = [np.zeros_like(coeffs[0])]
    first_selected = max(1, len(coeffs) - hf_levels)
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_selected:
            out.append(detail)
        else:
            out.append(tuple(np.zeros_like(c) for c in detail))
    rec = pywt.waverec2(out, wavelet).astype(np.float32)
    return rec[: l_chan.shape[0], : l_chan.shape[1]]


def apply_wavelet_hf_gain(
    lab_img: np.ndarray,
    wavelet: str,
    levels: int,
    hf_levels: int,
    gain: float,
    max_delta: float,
) -> tuple[np.ndarray, dict]:
    l_chan = lab_img[..., 0].astype(np.float32)
    hf = selected_hf(l_chan, wavelet, levels, hf_levels)
    delta = (gain - 1.0) * hf
    if max_delta > 0:
        delta = np.clip(delta, -max_delta, max_delta)
    out = lab_img.copy()
    out[..., 0] = np.clip(l_chan + delta, 0.0, 100.0)
    stats = {
        "hf_rms": float(np.sqrt(np.mean(hf * hf))),
        "delta_rms": float(np.sqrt(np.mean(delta * delta))),
        "delta_p95_abs": float(np.percentile(np.abs(delta), 95)),
        "delta_max_abs": float(np.max(np.abs(delta))),
    }
    return from_lab(out), stats


def ref_hf_stats(ref_lab: np.ndarray, wavelet: str, levels: int, hf_levels: int) -> dict:
    hf = selected_hf(ref_lab[..., 0].astype(np.float32), wavelet, levels, hf_levels)
    return {
        "ref_hf_rms": float(np.sqrt(np.mean(hf * hf))),
        "ref_hf_p95_abs": float(np.percentile(np.abs(hf), 95)),
    }


def collect(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = [parse_candidate(c) for c in args.candidate]
    recipes = [parse_recipe(r) for r in args.recipe]

    for image_id in args.images:
        ref_rgb = load_rgb(crop_path(args.ref_run, image_id, "REF", args.crop))
        ref_lab = to_lab(ref_rgb)
        Image.fromarray(ref_rgb).save(out_dir / f"{image_id}_REF.png")
        ref_stats_by_hf = {
            hf_levels: ref_hf_stats(ref_lab, args.wavelet, args.levels, hf_levels)
            for hf_levels in sorted({r[1] for r in recipes})
        }

        for candidate, run_hash in candidates:
            pipe_rgb = load_rgb(crop_path(run_hash, image_id, "PIPELINE", args.crop))
            pipe_lab = to_lab(pipe_rgb)
            original_m = metric_row(ref_rgb, pipe_rgb)
            rows.append({
                "image_id": image_id,
                "candidate": candidate,
                "run_hash": run_hash,
                "variant": "original",
                "png": f"../{run_hash}/{image_id}_PIPELINE_{args.crop}.png",
                "hf_levels": 0,
                "gain": 1.0,
                "hf_rms": None,
                "hf_rms_ratio_to_ref": None,
                "delta_rms": 0.0,
                "delta_p95_abs": 0.0,
                "delta_max_abs": 0.0,
                **original_m,
            })
            for recipe_label, hf_levels, gain in recipes:
                synth_rgb, stats = apply_wavelet_hf_gain(
                    pipe_lab,
                    args.wavelet,
                    args.levels,
                    hf_levels,
                    gain,
                    args.max_delta,
                )
                png_name = f"{image_id}_{candidate}_{recipe_label}.png"
                Image.fromarray(synth_rgb).save(out_dir / png_name)
                m = metric_row(ref_rgb, synth_rgb)
                ref_stats = ref_stats_by_hf[hf_levels]
                rows.append({
                    "image_id": image_id,
                    "candidate": candidate,
                    "run_hash": run_hash,
                    "variant": recipe_label,
                    "png": str((out_dir / png_name).relative_to(DASH)),
                    "hf_levels": hf_levels,
                    "gain": gain,
                    **stats,
                    **ref_stats,
                    "hf_rms_ratio_to_ref": (
                        (stats["hf_rms"] + 1e-9) / (ref_stats["ref_hf_rms"] + 1e-9)
                    ),
                    **m,
                    "delta_lpips_vs_original": m["lpips"] - original_m["lpips"],
                    "delta_ms_ssim_vs_original": m["ms_ssim"] - original_m["ms_ssim"],
                    "delta_y_psnr_vs_original": m["y_psnr"] - original_m["y_psnr"],
                    "delta_dE2000_vs_original": m["dE2000_mean"] - original_m["dE2000_mean"],
                })
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
            "mean_delta_lpips": float(np.mean([r.get("delta_lpips_vs_original", 0.0) for r in group])),
            "mean_delta_ms_ssim": float(np.mean([r.get("delta_ms_ssim_vs_original", 0.0) for r in group])),
        })
    out.sort(key=lambda r: (r["candidate"], r["variant"] != "original", r["worst_lpips"]))
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
body { margin: 18px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: #f6f5f0; color: #202124; }
h1 { font-size: 22px; margin: 0 0 6px; }
h2 { font-size: 18px; margin: 28px 0 10px; }
p { max-width: 1160px; line-height: 1.45; color: #555; }
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
.meta { font-size: 12px; color: #555; line-height: 1.35; margin: 6px 0; min-height: 96px; }
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
            f"<td>{fmt(row['mean_delta_lpips'])}</td><td>{fmt(row['mean_delta_ms_ssim'])}</td>"
            "</tr>"
        )
    sections = []
    for image_id in args.images:
        cards = [
            f"<article class='card'><div class='title'>REF</div><div class='meta'>Original REF 100% crop.</div>"
            f"<img src='{output_dir_rel}/{html.escape(image_id)}_REF.png'></article>"
        ]
        image_rows = [r for r in rows if r["image_id"] == image_id]
        image_rows.sort(key=lambda r: (r["candidate"], r["variant"] != "original", r["lpips"]))
        for row in image_rows:
            src = html.escape(row["png"])
            cls = "pass" if row["preview_pass"] else "fail"
            cards.append(
                "<article class='card'>"
                f"<div class='title'>{html.escape(row['candidate'])}<br>{html.escape(row['variant'])}</div>"
                f"<div class='meta'><code>{html.escape(row['run_hash'])}</code><br>"
                f"<span class='{cls}'>LPIPS {row['lpips']:.4f} / MS {row['ms_ssim']:.4f}</span><br>"
                f"Y {row['y_psnr']:.2f} / dE {row['dE2000_mean']:.2f}<br>"
                f"hf levels {row['hf_levels']} / gain {row['gain']:.2f}<br>"
                f"HF ratio {fmt(row.get('hf_rms_ratio_to_ref'))} / dLPIPS {fmt(row.get('delta_lpips_vs_original'))}"
                "</div>"
                f"<img src='{src}'></article>"
            )
        sections.append(f"<h2>{html.escape(image_id)} 100% crops</h2><div class='strip'>{''.join(cards)}</div>")
    args.output_html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Wavelet HF synthesis probe</title>"
        f"<style>{css}</style></head><body>"
        "<h1>Wavelet HF Synthesis Probe</h1>"
        "<p>Fast screen for shippable Lab-L detail/noise synthesis. Each variant modifies only the candidate's own "
        "selected wavelet high-frequency bands before scoring against REF. "
        f"Method: wavelet=<code>{html.escape(args.wavelet)}</code>, levels=<code>{args.levels}</code>, "
        f"max_delta=<code>{args.max_delta}</code>.</p>"
        "<table><thead><tr><th class='left'>candidate</th><th class='left'>variant</th><th>pass</th>"
        "<th class='left'>worst image</th><th>worst LPIPS</th><th>median LPIPS</th><th>worst MS</th>"
        "<th>median MS</th><th>worst Y</th><th>worst dE</th><th>mean dLPIPS</th><th>mean dMS</th>"
        "</tr></thead><tbody>"
        f"{''.join(sum_rows)}</tbody></table>"
        f"{''.join(sections)}</body></html>"
    )


class _ImageSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attr_map = dict(attrs)
        src = attr_map.get("src")
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
        preview = ", ".join(missing[:8])
        extra = "" if len(missing) <= 8 else f", ... +{len(missing) - 8} more"
        raise RuntimeError(
            f"{html_path} references {len(missing)} missing image(s): "
            f"{preview}{extra}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref-run", default="5e7b79b5678fdf62")
    ap.add_argument("--candidate", action="append", default=None)
    ap.add_argument("--recipe", action="append", default=None)
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--crop", default="crop_A_detail")
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=3)
    ap.add_argument("--max-delta", type=float, default=2.0,
                    help="Clamp Lab-L delta in L* units; <=0 disables clamping.")
    ap.add_argument("--output-dir", type=Path, default=DASH / "wavelet_hf_synthesis")
    ap.add_argument("--output-json", type=Path, default=DASH / "wavelet_hf_synthesis.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "wavelet_hf_synthesis.html")
    args = ap.parse_args()
    if args.candidate is None:
        args.candidate = list(DEFAULT_CANDIDATES)
    if args.recipe is None:
        args.recipe = list(DEFAULT_RECIPES)
    args.output_dir = args.output_dir.resolve()
    args.output_json = args.output_json.resolve()
    args.output_html = args.output_html.resolve()

    rows = collect(args)
    summary = summarize(rows)
    args.output_json.write_text(json.dumps({
        "thresholds": PREVIEW,
        "wavelet": args.wavelet,
        "levels": args.levels,
        "max_delta": args.max_delta,
        "summary": summary,
        "rows": rows,
    }, indent=2))
    write_html(rows, summary, args)
    validate_html_images(args.output_html)
    for row in summary:
        print(
            f"{row['candidate']:<24} {row['variant']:<16} "
            f"pass={row['pass_count']}/{row['count']} "
            f"worst={row['worst_image']} lpips={row['worst_lpips']:.4f} "
            f"ms={row['worst_ms_ssim']:.4f} "
            f"dLPIPS={row['mean_delta_lpips']:+.4f}"
        )
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
