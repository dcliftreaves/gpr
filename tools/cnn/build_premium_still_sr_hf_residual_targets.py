#!/usr/bin/env python3
"""Build structured HF residual targets for premium still-SR.

This is a training-target builder, not a runtime render path. It compares a
source DNG render against a candidate SR DNG render, decomposes both into
low/high-frequency bands, and saves the residual needed to move candidate HF
toward source HF. The source DNG is used only to build supervised targets.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_premium_still_sr_latitude_review import (  # noqa: E402
    artifact_ref,
    block_lowpass_rgb,
    crop_metrics,
    crop_starts,
    image_from_rgb,
    render_rawpy,
    sha256_file,
    to_float,
)


SCHEMA = "gpr.premium_still_sr_hf_residual_targets.v1"
DEFAULT_EXPOSURES = (-2.0, 0.0, 2.0)


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


def hf_correlation(ref_hf: np.ndarray, cand_hf: np.ndarray) -> float | None:
    num = float(np.sum(ref_hf * cand_hf))
    den = float(np.sqrt(np.sum(ref_hf * ref_hf) * np.sum(cand_hf * cand_hf)))
    return num / den if den > 1.0e-12 else None


def residual_preview(residual: np.ndarray, scale: float) -> Image.Image:
    arr = np.clip((residual / float(scale)) * 0.5 + 0.5, 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8), "RGB")


def build_rows_from_arrays(
    *,
    ref: np.ndarray,
    cand: np.ndarray,
    ev: float,
    crop_size: int,
    block: int,
    residual_scale: float,
    panels_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    if ref.shape != cand.shape:
        common_h = min(ref.shape[0], cand.shape[0])
        common_w = min(ref.shape[1], cand.shape[1])
        ref = ref[:common_h, :common_w]
        cand = cand[:common_h, :common_w]
    height, width = ref.shape[:2]
    crop = min(crop_size, width, height)
    rows: list[dict[str, Any]] = []
    inputs: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    if panels_dir is not None:
        panels_dir.mkdir(parents=True, exist_ok=True)
    for crop_name, x, y in crop_starts(width, height, crop):
        ref_crop = ref[y : y + crop, x : x + crop]
        cand_crop = cand[y : y + crop, x : x + crop]
        ref_f = to_float(ref_crop)
        cand_f = to_float(cand_crop)
        ref_hf = ref_f - block_lowpass_rgb(ref_f, block)
        cand_hf = cand_f - block_lowpass_rgb(cand_f, block)
        residual = ref_hf - cand_hf
        metrics = crop_metrics(ref_crop, cand_crop)
        row = {
            "crop": crop_name,
            "ev": ev,
            "crop_xy": [x, y],
            "crop_size": crop,
            "block": block,
            "mae": metrics["mae"],
            "y_mae": metrics["y_mae"],
            "lf_y_mae": metrics["lf_y_mae"],
            "hf_y_mae": metrics["hf_y_mae"],
            "hf_y_energy_ratio": metrics["hf_y_energy_ratio"],
            "hf_y_correlation": metrics["hf_y_correlation"],
            "ref_hf_abs_mean": float(np.mean(np.abs(ref_hf))),
            "candidate_hf_abs_mean": float(np.mean(np.abs(cand_hf))),
            "residual_abs_mean": float(np.mean(np.abs(residual))),
            "residual_rmse": float(np.sqrt(np.mean(residual * residual))),
            "residual_p95_abs": float(np.percentile(np.abs(residual), 95.0)),
            "policy": "training_target_uses_source_hf_not_runtime_render_path",
        }
        if panels_dir is not None:
            safe = f"{crop_name}_ev{ev:+.0f}".replace("+", "p").replace("-", "m")
            src_path = panels_dir / f"{safe}_source.jpg"
            cand_path = panels_dir / f"{safe}_candidate.jpg"
            residual_path = panels_dir / f"{safe}_hf_residual.jpg"
            image_from_rgb(ref_crop).save(src_path, quality=92)
            image_from_rgb(cand_crop).save(cand_path, quality=92)
            residual_preview(residual, residual_scale).save(residual_path, quality=92)
            row["panels"] = [
                {"kind": "source", "path": str(src_path)},
                {"kind": "candidate", "path": str(cand_path)},
                {"kind": "hf_residual", "path": str(residual_path)},
            ]
        inputs.append(cand_f.astype(np.float16))
        residuals.append(residual.astype(np.float16))
        targets.append(ref_hf.astype(np.float16))
        rows.append(row)
    return rows, inputs, residuals, targets


def write_contact_sheet(path: Path, rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = rows[:max_rows]
    if not selected or "panels" not in selected[0]:
        return
    first = Image.open(selected[0]["panels"][0]["path"])
    panel_w, panel_h = first.size
    first.close()
    pad = 10
    label_h = 42
    cols = 3
    sheet = Image.new("RGB", (cols * (panel_w + pad) + pad, len(selected) * (panel_h + label_h + pad) + pad), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["source", "candidate", "HF residual target"]
    for row_idx, row in enumerate(selected):
        y0 = pad + row_idx * (panel_h + label_h + pad)
        title = (
            f"{row['crop']} EV {row['ev']:+.0f} "
            f"HF corr {row['hf_y_correlation']:.3f} residual {row['residual_abs_mean']:.4f}"
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
    rows = sorted(data["rows"], key=lambda row: row["residual_abs_mean"], reverse=True)
    contact = Path(data["contact_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    table = []
    for row in rows:
        table.append(
            f"<tr><td>{html.escape(row['crop'])}</td><td>{row['ev']:+.0f}</td>"
            f"<td>{row['mae']:.5f}</td><td>{row['hf_y_mae']:.5f}</td>"
            f"<td>{html.escape(str(row['hf_y_energy_ratio']))}</td>"
            f"<td>{html.escape(str(row['hf_y_correlation']))}</td>"
            f"<td>{row['residual_abs_mean']:.5f}</td><td>{row['residual_p95_abs']:.5f}</td></tr>"
        )
    summary = data["summary"]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR HF Residual Targets</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left}}
code{{color:#b7d7ff}}.contact{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR HF Residual Targets</h1>
<p>Source DNG: <code>{html.escape(data['source_dng'])}</code></p>
<p>Candidate DNG: <code>{html.escape(data['candidate_dng'])}</code></p>
<p><b>Policy:</b> source DNG high-frequency content is used only to build supervised training targets. This is not a no-REF runtime render path.</p>
<div class="grid">
<div class="card"><h2>Rows</h2><p>{summary['row_count']}</p></div>
<div class="card"><h2>HF Corr</h2><p>median {summary['hf_y_correlation']['median']:.5f}</p><p>min {summary['hf_y_correlation']['min']:.5f}</p></div>
<div class="card"><h2>Residual Mean</h2><p>median {summary['residual_abs_mean']['median']:.5f}</p><p>max {summary['residual_abs_mean']['max']:.5f}</p></div>
<div class="card"><h2>Residual p95</h2><p>median {summary['residual_p95_abs']['median']:.5f}</p><p>max {summary['residual_p95_abs']['max']:.5f}</p></div>
</div>
<img class="contact" src="{html.escape(contact)}">
<table><tr><th>crop</th><th>EV</th><th>MAE</th><th>HF Y MAE</th><th>HF energy ratio</th><th>HF corr</th><th>residual mean</th><th>residual p95</th></tr>
{''.join(table)}
</table></body></html>
"""


def write_npz(path: Path, inputs: list[np.ndarray], residuals: list[np.ndarray], targets: list[np.ndarray], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        inputs=np.stack(inputs, axis=0).astype(np.float16),
        hf_residuals=np.stack(residuals, axis=0).astype(np.float16),
        source_hf_targets=np.stack(targets, axis=0).astype(np.float16),
        meta=np.asarray(json.dumps(rows, sort_keys=True)),
    )


def build(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panels_dir = args.output_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    inputs: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    render_times: list[dict[str, Any]] = []
    for ev in [float(v) for v in args.ev]:
        t0 = time.perf_counter()
        ref = render_rawpy(args.source_dng, ev, args.output_bps, args.half_size)
        t1 = time.perf_counter()
        cand = render_rawpy(args.candidate_dng, ev, args.output_bps, args.half_size)
        t2 = time.perf_counter()
        part_rows, part_inputs, part_residuals, part_targets = build_rows_from_arrays(
            ref=ref,
            cand=cand,
            ev=ev,
            crop_size=args.crop_size,
            block=args.block,
            residual_scale=args.residual_preview_scale,
            panels_dir=panels_dir,
        )
        rows.extend(part_rows)
        inputs.extend(part_inputs)
        residuals.extend(part_residuals)
        targets.extend(part_targets)
        render_times.append({"ev": ev, "source_s": t1 - t0, "candidate_s": t2 - t1})
        del ref
        del cand
    rows_sorted = sorted(rows, key=lambda row: row["residual_abs_mean"], reverse=True)
    contact = args.output_dir / "contact_sheet.jpg"
    write_contact_sheet(contact, rows_sorted, args.contact_rows)
    npz_path = args.output_dir / "hf_residual_targets.npz"
    write_npz(npz_path, inputs, residuals, targets, rows)
    summary = {
        "row_count": len(rows),
        "hf_y_correlation": stats([float(row["hf_y_correlation"]) for row in rows if row["hf_y_correlation"] is not None]),
        "hf_y_energy_ratio": stats([float(row["hf_y_energy_ratio"]) for row in rows if row["hf_y_energy_ratio"] is not None]),
        "residual_abs_mean": stats([float(row["residual_abs_mean"]) for row in rows]),
        "residual_rmse": stats([float(row["residual_rmse"]) for row in rows]),
        "residual_p95_abs": stats([float(row["residual_p95_abs"]) for row in rows]),
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
            "half_size": args.half_size,
            "ev": [float(v) for v in args.ev],
            "crop_size": args.crop_size,
            "block": args.block,
        },
        "policy": {
            "uses_source_hf": True,
            "runtime_safe": False,
            "purpose": "supervised_structured_hf_residual_training_target",
        },
        "summary": summary,
        "rows": rows,
        "arrays": {
            "npz": str(npz_path),
            "inputs": "candidate_render_rgb_float16_nhwc",
            "hf_residuals": "source_hf_minus_candidate_hf_float16_nhwc",
            "source_hf_targets": "source_hf_float16_nhwc",
        },
        "contact_sheet": str(contact),
        "artifacts": {"npz": artifact_ref(npz_path), "contact_sheet": artifact_ref(contact)},
    }
    receipt = args.output_dir / "hf_residual_targets.json"
    index = args.output_dir / "index.html"
    receipt.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    index.write_text(render_html(data, args.output_dir), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dng", type=Path, required=True)
    ap.add_argument("--candidate-dng", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--ev", action="append", type=float, default=list(DEFAULT_EXPOSURES))
    ap.add_argument("--crop-size", type=int, default=768)
    ap.add_argument("--block", type=int, default=16)
    ap.add_argument("--output-bps", type=int, choices=(8, 16), default=16)
    ap.add_argument("--half-size", action="store_true")
    ap.add_argument("--residual-preview-scale", type=float, default=0.08)
    ap.add_argument("--contact-rows", type=int, default=9)
    args = ap.parse_args()
    data = build(args)
    print(
        json.dumps(
            {
                "receipt": str(args.output_dir / "hf_residual_targets.json"),
                "dashboard": str(args.output_dir / "index.html"),
                "npz": data["arrays"]["npz"],
                "rows": data["summary"]["row_count"],
                "median_hf_correlation": data["summary"]["hf_y_correlation"]["median"],
                "median_residual_abs_mean": data["summary"]["residual_abs_mean"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
