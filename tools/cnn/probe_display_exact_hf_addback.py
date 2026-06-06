#!/usr/bin/env python3
"""Probe exact REF Lab-L high-frequency addback for display refiner outputs."""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color


Image.MAX_IMAGE_PIXELS = None
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/cnn"))
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402
from train_display_hf_detail import split_luma_hf  # noqa: E402


PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "dE2000_mean": 3.0}


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def pass_preview(m: dict) -> bool:
    return (
        m["lpips"] <= PREVIEW["lpips"]
        and m["ms_ssim"] >= PREVIEW["ms_ssim"]
        and m["y_psnr"] >= PREVIEW["y_psnr"]
        and m["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def parse_stem(path: Path, suffix: str) -> tuple[str, str]:
    stem = path.name[: -len(suffix)]
    parts = stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"cannot parse {path.name}")
    return "_".join(parts[:2]), "_".join(parts[2:])


def exact_ref_hf(ref_rgb: np.ndarray, base_rgb: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    ref_lab = color.rgb2lab(ref_rgb.astype(np.float32) / 255.0).astype(np.float32)
    base_lab = color.rgb2lab(base_rgb.astype(np.float32) / 255.0).astype(np.float32)
    base_lf, _ = split_luma_hf(base_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
    _, ref_hf = split_luma_hf(ref_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
    out_lab = base_lab.copy()
    out_lab[..., 0] = np.clip(base_lf + ref_hf, 0.0, 100.0)
    return np.clip(color.lab2rgb(out_lab) * 255.0, 0, 255).astype(np.uint8)


def metric_row(ref: np.ndarray, test: np.ndarray) -> dict:
    m = compute_visual_metrics(ref, test)
    m["preview_pass"] = pass_preview(m)
    return m


def summarize(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for variant in sorted({r["variant"] for r in rows}):
        group = [r for r in rows if r["variant"] == variant]
        out[variant] = {
            "count": len(group),
            "pass_count": sum(1 for r in group if r["preview_pass"]),
            "pass_rate": sum(1 for r in group if r["preview_pass"]) / max(1, len(group)),
            "worst_lpips": max(float(r["lpips"]) for r in group),
            "median_lpips": float(np.median([r["lpips"] for r in group])),
            "worst_ms_ssim": min(float(r["ms_ssim"]) for r in group),
            "worst_y_psnr": min(float(r["y_psnr"]) for r in group),
            "worst_dE2000_mean": max(float(r["dE2000_mean"]) for r in group),
        }
    return out


def write_html(rows: list[dict], summary: dict, args: argparse.Namespace) -> None:
    css = """
body { margin:18px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif; background:#f5f5f1; color:#202124; }
h1 { font-size:22px; margin:0 0 8px; } h2 { font-size:18px; margin:24px 0 10px; }
table { border-collapse:collapse; background:#fff; font-size:12px; margin:12px 0 20px; }
th,td { border:1px solid #d8d8d1; padding:6px 8px; text-align:right; } th.left,td.left { text-align:left; } th { background:#e8e8e1; }
.pass { color:#0a6f2a; font-weight:650; } .fail { color:#9b1c1c; font-weight:650; }
.grid { display:grid; grid-template-columns:repeat(4,minmax(220px,1fr)); gap:10px; }
.tile { background:#fff; border:1px solid #d8d8d1; padding:8px; } .tile img { width:100%; display:block; }
.cap { font-size:11px; color:#555; margin-top:4px; }
"""
    parts = ["<!doctype html><meta charset='utf-8'><title>Exact HF Addback Probe</title>", f"<style>{css}</style>", "<h1>Exact HF Addback Probe</h1>"]
    parts.append("<p>Oracle diagnostic: exact REF Lab-L high-frequency detail is added to the candidate low-frequency/color result.</p>")
    parts.append("<table><tr><th class='left'>Variant</th><th>Count</th><th>Pass</th><th>Pass rate</th><th>Worst LPIPS</th><th>Median LPIPS</th><th>Worst MS</th><th>Worst dE</th></tr>")
    for variant, s in summary.items():
        parts.append(
            f"<tr><td class='left'>{html.escape(variant)}</td><td>{s['count']}</td><td>{s['pass_count']}</td>"
            f"<td>{100*s['pass_rate']:.1f}%</td><td>{s['worst_lpips']:.4f}</td><td>{s['median_lpips']:.4f}</td>"
            f"<td>{s['worst_ms_ssim']:.4f}</td><td>{s['worst_dE2000_mean']:.3f}</td></tr>"
        )
    parts.append("</table>")
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["image_id"], row["crop"]), []).append(row)
    for (image_id, crop), group in grouped.items():
        parts.append(f"<h2>{html.escape(image_id)} / {html.escape(crop)}</h2><div class='grid'>")
        for row in sorted(group, key=lambda r: r["variant"]):
            klass = "pass" if row["preview_pass"] else "fail"
            parts.append(
                "<div class='tile'>"
                f"<img src='{html.escape(row['png'])}'>"
                f"<div class='cap'>{html.escape(row['variant'])}<br>"
                f"<span class='{klass}'>LPIPS {row['lpips']:.4f}, MS {row['ms_ssim']:.4f}, "
                f"Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span></div></div>"
            )
        parts.append("</div>")
    args.output_html.write_text("\n".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--base-suffix", default="_refined.png")
    ap.add_argument("--ref-suffix", default="_REF.png")
    ap.add_argument("--candidate-suffix", default="_candidate.png")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=3)
    ap.add_argument("--hf-levels", type=int, default=3)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for ref_path in sorted(args.input_dir.glob(f"*{args.ref_suffix}")):
        image_id, crop = parse_stem(ref_path, args.ref_suffix)
        base_path = args.input_dir / f"{image_id}_{crop}{args.base_suffix}"
        cand_path = args.input_dir / f"{image_id}_{crop}{args.candidate_suffix}"
        if not base_path.exists() or not cand_path.exists():
            continue
        ref = load_rgb(ref_path)
        base = load_rgb(base_path)
        cand = load_rgb(cand_path)
        exact = exact_ref_hf(ref, base, args)
        variants = {"candidate": cand, "base": base, "exact_ref_hf": exact}
        for variant, rgb in variants.items():
            png = args.output_dir / f"{image_id}_{crop}_{variant}.png"
            Image.fromarray(rgb).save(png)
            rows.append({
                "image_id": image_id,
                "crop": crop,
                "variant": variant,
                "png": png.name,
                **metric_row(ref, rgb),
            })
    summary = summarize(rows)
    payload = {"rows": rows, "summary": summary, "input_dir": str(args.input_dir)}
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(rows, summary, args)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
