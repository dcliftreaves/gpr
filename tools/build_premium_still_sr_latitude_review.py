#!/usr/bin/env python3
"""Build a raw-editor-style latitude review for premium still-SR DNGs.

This differs from the Bayer/OpenCV proxy dashboard: it renders the source DNG
and candidate DNG through rawpy/LibRaw with the camera white balance, color
metadata, exposure shift, and demosaic path. It is still an automated receipt,
not a substitute for manual review in Lightroom/ACR.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


SCHEMA = "gpr.premium_still_sr_latitude_review.v1"
DEFAULT_EXPOSURES = (-2.0, 0.0, 2.0)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "max": float(arr.max()),
    }


def crop_starts(width: int, height: int, crop: int) -> list[tuple[str, int, int]]:
    margin = max(0, crop // 4)
    return [
        ("upper_left", min(margin, max(0, width - crop)), min(margin, max(0, height - crop))),
        ("center", max(0, (width - crop) // 2), max(0, (height - crop) // 2)),
        ("lower_detail", max(0, width - crop - margin), max(0, height - crop - margin)),
    ]


def render_rawpy(path: Path, ev: float, output_bps: int, half_size: bool) -> np.ndarray:
    import rawpy

    raw = rawpy.imread(str(path))
    try:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=output_bps,
            gamma=(2.222, 4.5),
            output_color=rawpy.ColorSpace.sRGB,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            exp_shift=2.0**ev,
            exp_preserve_highlights=0.0,
            user_flip=0,
            half_size=half_size,
        )
        return rgb
    finally:
        raw.close()


def to_float(rgb: np.ndarray) -> np.ndarray:
    denom = 65535.0 if rgb.dtype == np.uint16 else 255.0
    return rgb.astype(np.float32) / denom


def crop_metrics(ref: np.ndarray, cand: np.ndarray) -> dict[str, Any]:
    ref_f = to_float(ref)
    cand_f = to_float(cand)
    diff = cand_f - ref_f
    abs_diff = np.abs(diff)
    rmse = float(np.sqrt(np.mean(diff * diff)))
    mae = float(np.mean(abs_diff))
    psnr = 99.0 if rmse == 0.0 else 20.0 * math.log10(1.0 / rmse)
    ref_y = 0.2126 * ref_f[:, :, 0] + 0.7152 * ref_f[:, :, 1] + 0.0722 * ref_f[:, :, 2]
    cand_y = 0.2126 * cand_f[:, :, 0] + 0.7152 * cand_f[:, :, 1] + 0.0722 * cand_f[:, :, 2]
    y_diff = np.abs(cand_y - ref_y)
    block = 16
    bh = (ref_y.shape[0] // block) * block
    bw = (ref_y.shape[1] // block) * block
    if bh > 0 and bw > 0:
        ref_lf = ref_y[:bh, :bw].reshape(bh // block, block, bw // block, block).mean(axis=(1, 3))
        cand_lf = cand_y[:bh, :bw].reshape(bh // block, block, bw // block, block).mean(axis=(1, 3))
        lf_y_mae: float | None = float(np.mean(np.abs(cand_lf - ref_lf)))
    else:
        lf_y_mae = None
    highlight = ref_y >= 0.85
    shadow = ref_y <= 0.10
    midtone = (ref_y > 0.10) & (ref_y < 0.85)
    return {
        "mae": mae,
        "rmse": rmse,
        "psnr_db": psnr,
        "y_mae": float(np.mean(y_diff)),
        "lf_y_mae": lf_y_mae,
        "highlight_y_mae": float(np.mean(y_diff[highlight])) if np.any(highlight) else None,
        "shadow_y_mae": float(np.mean(y_diff[shadow])) if np.any(shadow) else None,
        "midtone_y_mae": float(np.mean(y_diff[midtone])) if np.any(midtone) else None,
        "channel_mean_delta": [float(v) for v in np.mean(diff, axis=(0, 1))],
        "ref_clip_fraction": float(np.mean(np.any(ref_f >= 0.999, axis=2))),
        "candidate_clip_fraction": float(np.mean(np.any(cand_f >= 0.999, axis=2))),
    }


def image_from_rgb(rgb: np.ndarray) -> Image.Image:
    if rgb.dtype == np.uint16:
        arr = (np.clip(rgb.astype(np.float32) / 257.0, 0.0, 255.0) + 0.5).astype(np.uint8)
    else:
        arr = rgb.astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def error_image(ref: np.ndarray, cand: np.ndarray, scale: float) -> Image.Image:
    err = np.mean(np.abs(to_float(cand) - to_float(ref)), axis=2)
    arr = (np.clip(err / scale, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(arr, "L").convert("RGB")


def write_contact_sheet(path: Path, rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = rows[:max_rows]
    if not selected:
        return
    first = Image.open(selected[0]["panels"][0]["path"])
    panel_w, panel_h = first.size
    first.close()
    pad = 10
    label_h = 42
    cols = 3
    sheet_w = cols * (panel_w + pad) + pad
    sheet_h = len(selected) * (panel_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["source DNG", "candidate DNG", "error"]
    for row_idx, row in enumerate(selected):
        y0 = pad + row_idx * (panel_h + label_h + pad)
        title = (
            f"{row['crop']} EV {row['ev']:+.0f} "
            f"MAE {row['mae']:.4f} Y {row['y_mae']:.4f} LF {row.get('lf_y_mae'):.4f} PSNR {row['psnr_db']:.2f}"
        )
        draw.text((pad, y0), title, fill=(245, 245, 245))
        for col, panel in enumerate(row["panels"]):
            x0 = pad + col * (panel_w + pad)
            draw.text((x0, y0 + 19), headers[col], fill=(190, 190, 190))
            img = Image.open(panel["path"]).convert("RGB")
            sheet.paste(img, (x0, y0 + label_h))
            img.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def render_html(data: dict[str, Any], output_dir: Path) -> str:
    rows = sorted(data["rows"], key=lambda row: row["mae"], reverse=True)
    table_rows = []
    for row in rows:
        err_panel = next(panel for panel in row["panels"] if panel["kind"] == "error")
        rel = Path(err_panel["path"]).resolve().relative_to(output_dir.resolve()).as_posix()
        table_rows.append(
            f"<tr><td>{html.escape(row['crop'])}</td><td>{row['ev']:+.0f}</td>"
            f"<td>{row['mae']:.5f}</td><td>{row['y_mae']:.5f}</td><td>{html.escape(str(row.get('lf_y_mae')))}</td><td>{row['psnr_db']:.2f}</td>"
            f"<td>{html.escape(str(row['highlight_y_mae']))}</td>"
            f"<td>{html.escape(str(row['shadow_y_mae']))}</td>"
            f"<td><img src='{html.escape(rel)}'></td></tr>"
        )
    summary = data["summary"]
    contact = Path(data["contact_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR Latitude Review</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left;vertical-align:top}}
img{{max-width:220px;height:auto}}code{{color:#b7d7ff}}.contact{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR Latitude Review</h1>
<p>Source DNG: <code>{html.escape(data['source_dng'])}</code></p>
<p>Candidate DNG: <code>{html.escape(data['candidate_dng'])}</code></p>
<div class="grid">
<div class="card"><h2>Rows</h2><p>{summary['row_count']}</p></div>
<div class="card"><h2>MAE</h2><p>median {summary['mae']['median']:.5f}</p><p>worst {summary['mae']['max']:.5f}</p></div>
<div class="card"><h2>Y MAE</h2><p>median {summary['y_mae']['median']:.5f}</p><p>worst {summary['y_mae']['max']:.5f}</p></div>
<div class="card"><h2>LF Y MAE</h2><p>median {summary['lf_y_mae']['median']:.5f}</p><p>worst {summary['lf_y_mae']['max']:.5f}</p></div>
<div class="card"><h2>PSNR</h2><p>median {summary['psnr_db']['median']:.2f} dB</p><p>worst {summary['psnr_db']['min']:.2f} dB</p></div>
</div>
<img class="contact" src="{html.escape(contact)}">
<table><tr><th>crop</th><th>EV</th><th>MAE</th><th>Y MAE</th><th>LF Y MAE</th><th>PSNR</th><th>highlight Y MAE</th><th>shadow Y MAE</th><th>error</th></tr>
{''.join(table_rows)}
</table></body></html>
"""


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panels_dir = args.output_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    exposures = [float(v) for v in args.ev]
    rows: list[dict[str, Any]] = []
    render_times: list[dict[str, Any]] = []
    for ev in exposures:
        t0 = time.perf_counter()
        ref = render_rawpy(args.source_dng, ev, args.output_bps, args.half_size)
        t1 = time.perf_counter()
        cand = render_rawpy(args.candidate_dng, ev, args.output_bps, args.half_size)
        t2 = time.perf_counter()
        source_shape_before_common_crop = list(ref.shape)
        candidate_shape_before_common_crop = list(cand.shape)
        if ref.shape != cand.shape:
            common_h = min(ref.shape[0], cand.shape[0])
            common_w = min(ref.shape[1], cand.shape[1])
            if not args.allow_common_crop:
                raise ValueError(
                    f"render shape mismatch: source {ref.shape}, candidate {cand.shape}; "
                    f"rerun with --allow-common-crop to compare {common_w}x{common_h}"
                )
            ref = ref[:common_h, :common_w]
            cand = cand[:common_h, :common_w]
        height, width = ref.shape[:2]
        crop = min(args.crop_size, width, height)
        render_times.append(
            {
                "ev": ev,
                "source_s": t1 - t0,
                "candidate_s": t2 - t1,
                "shape": [height, width, 3],
                "source_shape_before_common_crop": source_shape_before_common_crop,
                "candidate_shape_before_common_crop": candidate_shape_before_common_crop,
            }
        )
        for crop_name, x, y in crop_starts(width, height, crop):
            ref_crop = ref[y : y + crop, x : x + crop]
            cand_crop = cand[y : y + crop, x : x + crop]
            metrics = crop_metrics(ref_crop, cand_crop)
            safe = f"{crop_name}_ev{ev:+.0f}".replace("+", "p").replace("-", "m")
            ref_path = panels_dir / f"{safe}_source.jpg"
            cand_path = panels_dir / f"{safe}_candidate.jpg"
            err_path = panels_dir / f"{safe}_error.jpg"
            image_from_rgb(ref_crop).save(ref_path, quality=92)
            image_from_rgb(cand_crop).save(cand_path, quality=92)
            error_image(ref_crop, cand_crop, args.error_scale).save(err_path, quality=92)
            rows.append(
                {
                    "crop": crop_name,
                    "ev": ev,
                    "crop_xy": [x, y],
                    "crop_size": crop,
                    **metrics,
                    "panels": [
                        {"kind": "source", "path": str(ref_path)},
                        {"kind": "candidate", "path": str(cand_path)},
                        {"kind": "error", "path": str(err_path)},
                    ],
                }
            )
        del ref
        del cand
    rows_sorted = sorted(rows, key=lambda row: row["mae"], reverse=True)
    contact = args.output_dir / "contact_sheet.jpg"
    write_contact_sheet(contact, rows_sorted, args.contact_rows)
    summary = {
        "row_count": len(rows),
        "mae": stats([float(row["mae"]) for row in rows]),
        "y_mae": stats([float(row["y_mae"]) for row in rows]),
        "lf_y_mae": stats([float(row["lf_y_mae"]) for row in rows if row["lf_y_mae"] is not None]),
        "psnr_db": stats([float(row["psnr_db"]) for row in rows]),
        "highlight_y_mae": stats([float(row["highlight_y_mae"]) for row in rows if row["highlight_y_mae"] is not None]),
        "shadow_y_mae": stats([float(row["shadow_y_mae"]) for row in rows if row["shadow_y_mae"] is not None]),
        "render_times": render_times,
    }
    data = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "source_dng": str(args.source_dng),
        "candidate_dng": str(args.candidate_dng),
        "source_dng_sha256": sha256_file(args.source_dng),
        "candidate_dng_sha256": sha256_file(args.candidate_dng),
        "render": {
            "engine": "rawpy/libraw",
            "use_camera_wb": True,
            "no_auto_bright": True,
            "output_bps": args.output_bps,
            "gamma": [2.222, 4.5],
            "demosaic": "AHD",
            "user_flip": 0,
            "half_size": args.half_size,
            "allow_common_crop": args.allow_common_crop,
        },
        "summary": summary,
        "rows": rows,
        "contact_sheet": str(contact),
        "artifacts": {"contact_sheet": artifact_ref(contact)},
    }
    out_json = args.output_dir / "latitude_review.json"
    out_html = args.output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, args.output_dir), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dng", type=Path, required=True)
    ap.add_argument("--candidate-dng", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--ev", action="append", type=float, default=list(DEFAULT_EXPOSURES))
    ap.add_argument("--crop-size", type=int, default=768)
    ap.add_argument("--output-bps", type=int, choices=(8, 16), default=16)
    ap.add_argument("--half-size", action="store_true")
    ap.add_argument("--allow-common-crop", action="store_true")
    ap.add_argument("--error-scale", type=float, default=0.06)
    ap.add_argument("--contact-rows", type=int, default=9)
    args = ap.parse_args()
    data = build_review(args)
    print(
        json.dumps(
            {
                "receipt": str(args.output_dir / "latitude_review.json"),
                "dashboard": str(args.output_dir / "index.html"),
                "rows": data["summary"]["row_count"],
                "median_mae": data["summary"]["mae"]["median"],
                "worst_mae": data["summary"]["mae"]["max"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
