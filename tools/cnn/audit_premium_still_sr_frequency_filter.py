#!/usr/bin/env python3
"""Audit frequency-domain recoverability for premium still-SR raw residuals.

This is a bounded diagnostic, not a production model. It fits per-CFA-plane
frequency-domain linear filters from runtime-safe candidate highpass raw planes
to the source-minus-candidate raw residual target. If this stronger linear
baseline fails, another small local CNN over the same candidate features is
unlikely to close the premium still-SR gap.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_frequency_filter_audit.v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "max": float(arr.max()),
    }


def camera_from_row(row: dict[str, Any]) -> str:
    scene = str(row.get("scene_id") or "").lower()
    source = str(row.get("source_dng") or row.get("candidate_raw") or row.get("candidate_dng") or "").lower()
    if "x2d" in scene or "x2d" in source or "austin" in scene:
        return "x2d"
    if "z8" in scene or "z8" in source:
        return "z8"
    if "mission" in scene or "gopro" in source or "gp0" in scene:
        return "mission1"
    return "unknown"


def load_meta(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list):
        raise ValueError("target meta must be a JSON list")
    return [row if isinstance(row, dict) else {} for row in rows]


def split_rows(
    rows: list[dict[str, Any]],
    holdout_scene: str | None,
    holdout_camera: str | None,
    holdout_crop: str | None,
    holdout_ev: float | None,
) -> tuple[list[int], list[int]]:
    if holdout_scene:
        holdout = []
        for idx, row in enumerate(rows):
            if str(row.get("scene_id") or "") != holdout_scene:
                continue
            if holdout_crop is not None and str(row.get("crop") or "") != holdout_crop:
                continue
            if holdout_ev is not None and abs(float(row.get("ev", 0.0) or 0.0) - holdout_ev) > 1.0e-6:
                continue
            holdout.append(idx)
    elif holdout_camera:
        needle = holdout_camera.lower()
        holdout = [idx for idx, row in enumerate(rows) if camera_from_row(row) == needle]
    else:
        raise ValueError("one of --holdout-scene or --holdout-camera is required")
    train = [idx for idx in range(len(rows)) if idx not in holdout]
    if not train or not holdout:
        raise ValueError(f"split produced train={len(train)} holdout={len(holdout)}")
    return train, holdout


def fit_filter(
    inputs: np.ndarray,
    targets: np.ndarray,
    train_indices: list[int],
    *,
    ridge: float,
    max_train_rows: int | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    selected = train_indices[:max_train_rows] if max_train_rows else train_indices
    if not selected:
        raise ValueError("no training rows selected")
    h, w, planes = inputs.shape[1], inputs.shape[2], inputs.shape[3]
    numerator = np.zeros((planes, h, w // 2 + 1), dtype=np.complex128)
    denominator = np.zeros((planes, h, w // 2 + 1), dtype=np.float64)
    for idx in selected:
        for plane in range(planes):
            x_fft = np.fft.rfft2(inputs[idx, :, :, plane].astype(np.float32, copy=False))
            y_fft = np.fft.rfft2(targets[idx, :, :, plane].astype(np.float32, copy=False))
            numerator[plane] += y_fft * np.conj(x_fft)
            denominator[plane] += np.abs(x_fft) ** 2
    scale = float(np.median(denominator[denominator > 0.0])) if np.any(denominator > 0.0) else 1.0
    filt = numerator / (denominator + float(ridge) * max(scale, 1.0e-12))
    return filt.astype(np.complex64), {
        "train_rows_used": len(selected),
        "ridge": float(ridge),
        "regularization_scale": scale,
        "filter_shape": list(filt.shape),
    }


def apply_filter(x: np.ndarray, filt: np.ndarray) -> np.ndarray:
    h, w, planes = x.shape
    out = np.empty((h, w, planes), dtype=np.float32)
    for plane in range(planes):
        x_fft = np.fft.rfft2(x[:, :, plane].astype(np.float32, copy=False))
        pred = np.fft.irfft2(x_fft * filt[plane], s=(h, w))
        out[:, :, plane] = pred.astype(np.float32)
    return out


def eval_rows(
    inputs: np.ndarray,
    targets: np.ndarray,
    rows: list[dict[str, Any]],
    indices: list[int],
    filt: np.ndarray,
    *,
    max_rows: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = indices[:max_rows] if max_rows else indices
    out_rows: list[dict[str, Any]] = []
    for idx in selected:
        target = targets[idx].astype(np.float32, copy=False)
        pred = apply_filter(inputs[idx], filt)
        base_mae = float(np.mean(np.abs(target)))
        pred_mae = float(np.mean(np.abs(pred - target)))
        base_rmse = float(np.sqrt(np.mean(target * target)))
        pred_rmse = float(np.sqrt(np.mean((pred - target) ** 2)))
        out_rows.append(
            {
                "row_index": idx,
                "scene_id": rows[idx].get("scene_id"),
                "crop": rows[idx].get("crop"),
                "ev": rows[idx].get("ev"),
                "camera": camera_from_row(rows[idx]),
                "baseline_raw_residual_mae": base_mae,
                "model_raw_residual_mae": pred_mae,
                "baseline_raw_residual_rmse": base_rmse,
                "model_raw_residual_rmse": pred_rmse,
                "raw_residual_mae_reduction_pct": 100.0 * (base_mae - pred_mae) / max(base_mae, 1.0e-12),
                "raw_residual_rmse_reduction_pct": 100.0 * (base_rmse - pred_rmse) / max(base_rmse, 1.0e-12),
            }
        )
    summary = {
        "row_count": len(out_rows),
        "raw_residual_mae_reduction_pct": stats([float(row["raw_residual_mae_reduction_pct"]) for row in out_rows]),
        "raw_residual_rmse_reduction_pct": stats([float(row["raw_residual_rmse_reduction_pct"]) for row in out_rows]),
        "baseline_raw_residual_mae": stats([float(row["baseline_raw_residual_mae"]) for row in out_rows]),
        "model_raw_residual_mae": stats([float(row["model_raw_residual_mae"]) for row in out_rows]),
    }
    return out_rows, summary


def render_html(receipt: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{int(row['row_index'])}</td>"
        f"<td>{html.escape(str(row.get('camera')))}</td>"
        f"<td>{html.escape(str(row.get('scene_id')))}</td>"
        f"<td>{html.escape(str(row.get('crop')))}</td>"
        f"<td>{html.escape(str(row.get('ev')))}</td>"
        f"<td>{row['raw_residual_mae_reduction_pct']:.3f}%</td>"
        f"<td>{row['raw_residual_rmse_reduction_pct']:.3f}%</td>"
        "</tr>"
        for row in receipt["holdout_rows"][:80]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Frequency Filter Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #131820; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dde3e9; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3e9; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Frequency Filter Audit</h1>
<p class="sub">Per-CFA-plane frequency-domain linear filter from candidate highpass raw planes to source-minus-candidate raw residual targets. Runtime inputs are candidate-only.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value">{str(receipt['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Holdout rows</div><div class="value">{receipt['holdout_summary']['row_count']}</div></section>
  <section class="card"><div class="label">Holdout MAE recovery median</div><div class="value">{receipt['holdout_summary']['raw_residual_mae_reduction_pct']['median']:.3f}%</div></section>
  <section class="card"><div class="label">Holdout RMSE recovery median</div><div class="value">{receipt['holdout_summary']['raw_residual_rmse_reduction_pct']['median']:.3f}%</div></section>
</div>
<h2>Interpretation</h2>
<p>{html.escape(receipt['interpretation'])}</p>
<h2>Holdout Rows</h2>
<table><tr><th>row</th><th>camera</th><th>scene</th><th>crop</th><th>EV</th><th>MAE recovery</th><th>RMSE recovery</th></tr>{rows}</table>
<p>JSON receipt: <code>{html.escape(receipt['artifacts']['receipt'])}</code></p>
</main></body></html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    z = np.load(args.targets, allow_pickle=False)
    rows = load_meta(z)
    train_indices, holdout_indices = split_rows(
        rows,
        args.holdout_scene,
        args.holdout_camera,
        args.holdout_crop,
        args.holdout_ev,
    )
    inputs = z["candidate_raw_hf_cfa4"].astype(np.float32)
    targets = z["raw_hf_residual_cfa4"].astype(np.float32)
    filt, filter_summary = fit_filter(
        inputs,
        targets,
        train_indices,
        ridge=args.ridge,
        max_train_rows=args.max_train_rows,
    )
    train_rows, train_summary = eval_rows(
        inputs,
        targets,
        rows,
        train_indices,
        filt,
        max_rows=args.eval_train_rows,
    )
    holdout_rows, holdout_summary = eval_rows(
        inputs,
        targets,
        rows,
        holdout_indices,
        filt,
        max_rows=args.max_holdout_rows,
    )
    median_mae = float(holdout_summary["raw_residual_mae_reduction_pct"]["median"])
    production_ready = median_mae >= float(args.promotion_recovery_threshold)
    if median_mae < 1.0:
        interpretation = (
            "The frequency-domain candidate-only filter has effectively no useful holdout recovery. "
            "This points away from another small linear/local learner over candidate HF and toward a stronger prior, "
            "new runtime signal, or different target/objective."
        )
    elif median_mae < float(args.promotion_recovery_threshold):
        interpretation = (
            "The frequency-domain filter finds some recoverable structure, but remains below the promotion floor. "
            "A stronger nonlinear model may be justified only if it beats this baseline on the same holdout."
        )
    else:
        interpretation = (
            "The frequency-domain filter clears the recovery floor. This is still diagnostic, but it warrants "
            "a production model pass and full still/editor-latitude review."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output_dir / "frequency_filter_audit.json"
    dashboard_path = args.output_dir / "index.html"
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_npz": str(args.targets),
        "target_npz_sha256": sha256_file(args.targets),
        "production_ready": production_ready,
        "runtime_policy": {
            "uses_candidate_raw_hf_at_runtime": True,
            "uses_source_raw_at_runtime": False,
            "uses_ref_or_jpeg_content_at_runtime": False,
        },
        "split": {
            "holdout_scene": args.holdout_scene,
            "holdout_camera": args.holdout_camera,
            "holdout_crop": args.holdout_crop,
            "holdout_ev": args.holdout_ev,
            "train_row_count": len(train_indices),
            "holdout_row_count": len(holdout_indices),
        },
        "probe": {
            "kind": "per_cfa_plane_frequency_filter",
            "ridge": float(args.ridge),
            "promotion_recovery_threshold": float(args.promotion_recovery_threshold),
            **filter_summary,
        },
        "train_summary": train_summary,
        "holdout_summary": holdout_summary,
        "holdout_rows": holdout_rows,
        "train_rows": train_rows,
        "interpretation": interpretation,
        "artifacts": {
            "receipt": str(receipt_path),
            "dashboard": str(dashboard_path),
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dashboard_path.write_text(render_html(receipt), encoding="utf-8")
    print(dashboard_path)
    return receipt


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--holdout-scene", default=None)
    ap.add_argument("--holdout-camera", default=None)
    ap.add_argument("--holdout-crop", default=None)
    ap.add_argument("--holdout-ev", type=float, default=None)
    ap.add_argument("--ridge", type=float, default=1.0e-3)
    ap.add_argument("--max-train-rows", type=int, default=None)
    ap.add_argument("--max-holdout-rows", type=int, default=None)
    ap.add_argument("--eval-train-rows", type=int, default=48)
    ap.add_argument("--promotion-recovery-threshold", type=float, default=15.0)
    return ap.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
