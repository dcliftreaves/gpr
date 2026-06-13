#!/usr/bin/env python3
"""Probe crop-alignment sensitivity for full-frame PREVIEW receipts.

This is a REF-assisted diagnostic only. It reads a full-frame PREVIEW receipt,
renders REF DNGs, then rescrores manifest crops after shifting and slightly
scaling the output crop box. If small geometry changes clear failing rows, the
full-frame blocker may be crop/active-area alignment. If they do not, the
blocker is representation/model output rather than scoring geometry.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import scaled_box  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None


def render_dng_to_tiff(dng_path: Path, tiff_path: Path) -> float:
    t0 = time.perf_counter()
    result = subprocess.run(
        ["sips", "-s", "format", "tiff", str(dng_path), "--out", str(tiff_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed for {dng_path}: {result.stderr[-400:]}")
    return (time.perf_counter() - t0) * 1000.0


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def crop_box_scaled(
    crop: dict[str, int],
    sensor_dims: list[int],
    rendered_size: tuple[int, int],
    dx: int = 0,
    dy: int = 0,
    scale: float = 1.0,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = scaled_box(crop, sensor_dims, rendered_size)
    if scale != 1.0:
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        w = (x1 - x0) * scale
        h = (y1 - y0) * scale
        x0 = int(round(cx - w / 2.0))
        x1 = int(round(cx + w / 2.0))
        y0 = int(round(cy - h / 2.0))
        y1 = int(round(cy + h / 2.0))
    x0 += dx
    x1 += dx
    y0 += dy
    y1 += dy
    width, height = rendered_size
    box_w = max(1, x1 - x0)
    box_h = max(1, y1 - y0)
    x0 = min(max(0, x0), max(0, width - box_w))
    y0 = min(max(0, y0), max(0, height - box_h))
    return x0, y0, x0 + box_w, y0 + box_h


def crop_rgb(
    rgb: np.ndarray,
    crop: dict[str, int],
    sensor_dims: list[int],
    dx: int = 0,
    dy: int = 0,
    scale: float = 1.0,
) -> np.ndarray:
    box = crop_box_scaled(crop, sensor_dims, (rgb.shape[1], rgb.shape[0]), dx=dx, dy=dy, scale=scale)
    pil = Image.fromarray(rgb).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def summarize(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    if not rows:
        return {
            f"{prefix}_count": 0,
            f"{prefix}_pass_count": 0,
            f"{prefix}_pass_rate": 0.0,
            f"{prefix}_worst_lpips": 0.0,
            f"{prefix}_worst_ms_ssim": 0.0,
            f"{prefix}_worst_y_psnr": 0.0,
            f"{prefix}_worst_dE2000_mean": 0.0,
        }
    return {
        f"{prefix}_count": len(rows),
        f"{prefix}_pass_count": sum(1 for row in rows if row[f"{prefix}_preview_pass"]),
        f"{prefix}_pass_rate": sum(1 for row in rows if row[f"{prefix}_preview_pass"]) / len(rows),
        f"{prefix}_worst_lpips": max(float(row[f"{prefix}_lpips"]) for row in rows),
        f"{prefix}_worst_ms_ssim": min(float(row[f"{prefix}_ms_ssim"]) for row in rows),
        f"{prefix}_worst_y_psnr": min(float(row[f"{prefix}_y_psnr"]) for row in rows),
        f"{prefix}_worst_dE2000_mean": max(float(row[f"{prefix}_dE2000_mean"]) for row in rows),
    }


def shift_values(radius: int, step: int) -> list[int]:
    step = max(1, int(step))
    values = list(range(-int(radius), int(radius) + 1, step))
    if 0 not in values:
        values.append(0)
    return sorted(set(values))


def scale_values(values: list[float]) -> list[float]:
    out = sorted(set(float(v) for v in values))
    return out or [1.0]


def collect(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.receipt.read_text())
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images_by_id = {str(image["id"]): image for image in manifest["images"]}
    receipt_dir = args.receipt.parent
    selected_ids = set(args.image_id)
    receipt_images = receipt.get("images") or []
    if selected_ids:
        receipt_images = [image for image in receipt_images if str(image["image_id"]) in selected_ids]
    if not receipt_images:
        raise RuntimeError("no receipt images selected")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_align_oracle_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    render_ms: list[float] = []
    dx_values = shift_values(args.shift_radius, args.shift_step)
    dy_values = shift_values(args.shift_radius, args.shift_step)
    scales = scale_values(args.scale)
    try:
        for image_receipt in receipt_images:
            image_id = str(image_receipt["image_id"])
            image_meta = images_by_id[image_id]
            stitched_name = str(image_receipt.get("stitched_output") or image_receipt.get("stitched_png"))
            stitched_path = receipt_dir / stitched_name
            ref_dng = Path(str(image_receipt["ref_dng"]))
            ref_tiff = work / f"{image_id}_REF.tiff"
            print(f"[alignment-oracle] {image_id}", flush=True)
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
            out_rgb = load_rgb(stitched_path)
            ref_rgb = load_rgb(ref_tiff)
            image_row_count = 0
            image_pass_count = 0
            for crop_name, crop in crops.items():
                ref_crop = crop_rgb(ref_rgb, crop, image_meta["sensor_dims"])
                base_out = crop_rgb(out_rgb, crop, image_meta["sensor_dims"])
                base_metrics = {k: float(v) for k, v in compute_visual_metrics(ref_crop, base_out).items()}
                base_metrics["preview_pass"] = pass_preview(base_metrics)
                best = {
                    "dx": 0,
                    "dy": 0,
                    "scale": 1.0,
                    **base_metrics,
                }
                best_key = (
                    0 if base_metrics["preview_pass"] else 1,
                    float(base_metrics["lpips"]),
                    -float(base_metrics["ms_ssim"]),
                    -float(base_metrics["y_psnr"]),
                    float(base_metrics["dE2000_mean"]),
                )
                for scale in scales:
                    for dy in dy_values:
                        for dx in dx_values:
                            if dx == 0 and dy == 0 and scale == 1.0:
                                continue
                            out_crop = crop_rgb(out_rgb, crop, image_meta["sensor_dims"], dx=dx, dy=dy, scale=scale)
                            metrics = {k: float(v) for k, v in compute_visual_metrics(ref_crop, out_crop).items()}
                            metrics["preview_pass"] = pass_preview(metrics)
                            key = (
                                0 if metrics["preview_pass"] else 1,
                                float(metrics["lpips"]),
                                -float(metrics["ms_ssim"]),
                                -float(metrics["y_psnr"]),
                                float(metrics["dE2000_mean"]),
                            )
                            if key < best_key:
                                best_key = key
                                best = {
                                    "dx": dx,
                                    "dy": dy,
                                    "scale": scale,
                                    **metrics,
                                }
                best_crop = crop_rgb(
                    out_rgb,
                    crop,
                    image_meta["sensor_dims"],
                    dx=int(best["dx"]),
                    dy=int(best["dy"]),
                    scale=float(best["scale"]),
                )
                png_name = f"{image_id}_{crop_name}_alignment_oracle.png"
                Image.fromarray(best_crop).save(args.output_dir / png_name)
                row = {
                    "image_id": image_id,
                    "crop": crop_name,
                    "source_render_size": list(out_rgb.shape[1::-1]),
                    "ref_render_size": list(ref_rgb.shape[1::-1]),
                    "base_preview_pass": bool(base_metrics["preview_pass"]),
                    "base_lpips": float(base_metrics["lpips"]),
                    "base_ms_ssim": float(base_metrics["ms_ssim"]),
                    "base_y_psnr": float(base_metrics["y_psnr"]),
                    "base_dE2000_mean": float(base_metrics["dE2000_mean"]),
                    "oracle_preview_pass": bool(best["preview_pass"]),
                    "oracle_lpips": float(best["lpips"]),
                    "oracle_ms_ssim": float(best["ms_ssim"]),
                    "oracle_y_psnr": float(best["y_psnr"]),
                    "oracle_dE2000_mean": float(best["dE2000_mean"]),
                    "oracle_dx": int(best["dx"]),
                    "oracle_dy": int(best["dy"]),
                    "oracle_scale": float(best["scale"]),
                    "oracle_png": png_name,
                }
                rows.append(row)
                image_row_count += 1
                image_pass_count += 1 if row["oracle_preview_pass"] else 0
            image_rows.append(
                {
                    "image_id": image_id,
                    "source_render_size": list(out_rgb.shape[1::-1]),
                    "ref_render_size": list(ref_rgb.shape[1::-1]),
                    "oracle_pass_count": image_pass_count,
                    "count": image_row_count,
                }
            )
            ref_tiff.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "schema": "preview_fullframe_alignment_oracle.v1",
        "receipt": str(args.receipt),
        "manifest": str(args.manifest),
        "thresholds": PREVIEW,
        "search": {
            "shift_radius": args.shift_radius,
            "shift_step": args.shift_step,
            "dx_values": dx_values,
            "dy_values": dy_values,
            "scales": scales,
            "candidate_count_per_crop": len(dx_values) * len(dy_values) * len(scales),
        },
        "render_contract": {
            "diagnostic_only": True,
            "uses_ref_to_select_alignment": True,
            "production_allowed": False,
        },
        "timing": {
            "render_ms_total": float(sum(render_ms)),
            "render_ms_median": float(np.median(render_ms)) if render_ms else 0.0,
        },
        "summary": {
            **summarize(rows, "base"),
            **summarize(rows, "oracle"),
            "rows_improved_pass": sum(
                1 for row in rows if not row["base_preview_pass"] and row["oracle_preview_pass"]
            ),
        },
        "images": image_rows,
        "rows": rows,
    }


def write_html(payload: dict[str, Any], out: Path) -> None:
    def fmt(value: float) -> str:
        return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"

    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f7f8f9; color:#222; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(170px,1fr)); gap:10px; margin:14px 0; }
.card,.tile { background:#fff; border:1px solid #d4d8de; border-radius:6px; padding:10px; }
table { border-collapse:collapse; background:#fff; width:100%; font-size:12px; margin:14px 0; }
td,th { border:1px solid #ccd2d9; padding:5px 7px; text-align:right; }
th.left,td.left { text-align:left; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
.tile img { width:100%; display:block; border:1px solid #ddd; }
"""
    summary = payload["summary"]
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW full-frame alignment oracle</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Frame Alignment Oracle</h1>",
        "<p>REF-assisted diagnostic only. Alignment selected using REF metrics; not a production render path.</p>",
        "<div class=cards>",
        f"<div class=card><b>Base pass</b><br>{summary['base_pass_count']}/{summary['base_count']}</div>",
        f"<div class=card><b>Oracle pass</b><br>{summary['oracle_pass_count']}/{summary['oracle_count']}</div>",
        f"<div class=card><b>Improved fails</b><br>{summary['rows_improved_pass']}</div>",
        f"<div class=card><b>Candidates/crop</b><br>{payload['search']['candidate_count_per_crop']}</div>",
        "</div>",
        "<table><thead><tr><th class=left>image</th><th class=left>crop</th><th>base pass</th><th>oracle pass</th><th>dx</th><th>dy</th><th>scale</th><th>base LPIPS</th><th>oracle LPIPS</th><th>base Y</th><th>oracle Y</th><th>base dE</th><th>oracle dE</th></tr></thead><tbody>",
    ]
    for row in sorted(payload["rows"], key=lambda r: (not r["oracle_preview_pass"], r["oracle_lpips"]), reverse=True):
        base_cls = "pass" if row["base_preview_pass"] else "fail"
        oracle_cls = "pass" if row["oracle_preview_pass"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['image_id'])}</td><td class=left>{html.escape(row['crop'])}</td>"
            f"<td class={base_cls}>{row['base_preview_pass']}</td><td class={oracle_cls}>{row['oracle_preview_pass']}</td>"
            f"<td>{row['oracle_dx']}</td><td>{row['oracle_dy']}</td><td>{row['oracle_scale']:.4f}</td>"
            f"<td>{fmt(row['base_lpips'])}</td><td>{fmt(row['oracle_lpips'])}</td>"
            f"<td>{fmt(row['base_y_psnr'])}</td><td>{fmt(row['oracle_y_psnr'])}</td>"
            f"<td>{fmt(row['base_dE2000_mean'])}</td><td>{fmt(row['oracle_dE2000_mean'])}</td></tr>"
        )
    parts.append("</tbody></table><h2>Oracle Crops</h2><div class=grid>")
    for row in sorted(payload["rows"], key=lambda r: (not r["oracle_preview_pass"], r["oracle_lpips"]), reverse=True)[:72]:
        cls = "pass" if row["oracle_preview_pass"] else "fail"
        parts.append(
            f"<div class=tile><b>{html.escape(row['image_id'])} {html.escape(row['crop'])}</b>"
            f"<br><span class={cls}>LPIPS {row['oracle_lpips']:.4f}, MS {row['oracle_ms_ssim']:.4f}, "
            f"Y {row['oracle_y_psnr']:.2f}, dE {row['oracle_dE2000_mean']:.2f}</span>"
            f"<br>dx {row['oracle_dx']}, dy {row['oracle_dy']}, scale {row['oracle_scale']:.4f}"
            f"<img src='{html.escape(row['oracle_png'])}'></div>"
        )
    parts.append("</div>")
    out.write_text("".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--shift-radius", type=int, default=12)
    ap.add_argument("--shift-step", type=int, default=3)
    ap.add_argument("--scale", type=float, action="append", default=[0.997, 1.0, 1.003])
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.output_html)
    summary = payload["summary"]
    print(
        f"base={summary['base_pass_count']}/{summary['base_count']} "
        f"oracle={summary['oracle_pass_count']}/{summary['oracle_count']} "
        f"improved={summary['rows_improved_pass']} "
        f"oracle_worst_lpips={summary['oracle_worst_lpips']:.4f} "
        f"oracle_worst_dE={summary['oracle_worst_dE2000_mean']:.2f}",
        flush=True,
    )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
