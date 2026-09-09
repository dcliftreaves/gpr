#!/usr/bin/env python3
"""Audit candidate-side signal for premium still-SR raw-CFA residuals.

This is a bounded diagnostic, not a production model. It samples pixels from the
canonical raw-CFA residual target set, fits a ridge probe using only runtime-safe
candidate features, and reports whether those features predict the withheld
source-minus-candidate raw residual better than the zero-residual baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_candidate_signal_audit.v1"


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
        "mean": float(arr.mean()),
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
    holdout_crop: str | None = None,
    holdout_ev: float | None = None,
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


def sample_pixels(
    *,
    raw: np.ndarray,
    hf: np.ndarray,
    target: np.ndarray,
    rows: list[dict[str, Any]],
    indices: list[int],
    samples_per_row: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = random.Random(seed)
    h, w = raw.shape[1:3]
    features: list[np.ndarray] = []
    values: list[float] = []
    row_ids: list[int] = []
    for idx in indices:
        row = rows[idx]
        ev = float(row.get("ev", 0.0) or 0.0)
        cam = camera_from_row(row)
        cam_onehot = (
            1.0 if cam == "x2d" else 0.0,
            1.0 if cam == "z8" else 0.0,
            1.0 if cam == "mission1" else 0.0,
        )
        for _ in range(samples_per_row):
            y = rng.randrange(0, h)
            x = rng.randrange(0, w)
            plane = rng.randrange(0, 4)
            raw4 = raw[idx, y, x].astype(np.float32)
            hf4 = hf[idx, y, x].astype(np.float32)
            plane_onehot = np.zeros((4,), dtype=np.float32)
            plane_onehot[plane] = 1.0
            coord = np.asarray(
                [
                    2.0 * ((x + 0.5) / max(w, 1)) - 1.0,
                    2.0 * ((y + 0.5) / max(h, 1)) - 1.0,
                    ev / 2.0,
                    *cam_onehot,
                ],
                dtype=np.float32,
            )
            feat = np.concatenate(
                [
                    raw4,
                    hf4,
                    np.abs(hf4),
                    plane_onehot,
                    np.asarray([raw4[plane], hf4[plane], abs(hf4[plane])], dtype=np.float32),
                    coord,
                    np.asarray([1.0], dtype=np.float32),
                ]
            )
            features.append(feat)
            values.append(float(target[idx, y, x, plane]))
            row_ids.append(idx)
    return np.stack(features).astype(np.float32), np.asarray(values, dtype=np.float32), np.asarray(row_ids, dtype=np.int32)


def fit_ridge(x: np.ndarray, y: np.ndarray, ridge: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x.mean(axis=0, keepdims=True)
    std = x.std(axis=0, keepdims=True)
    std = np.where(std < 1.0e-6, 1.0, std)
    xs = ((x - mean) / std).astype(np.float64)
    xtx = xs.T @ xs
    reg = np.eye(xtx.shape[0], dtype=np.float64) * float(ridge)
    lhs = xtx + reg
    rhs = xs.T @ y.astype(np.float64)
    try:
        w = np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:
        w = np.linalg.lstsq(lhs, rhs, rcond=None)[0]
    return w.astype(np.float32), mean.astype(np.float32), std.astype(np.float32)


def predict(x: np.ndarray, w: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return ((x - mean) / std) @ w


def eval_rows(
    *,
    x: np.ndarray,
    y: np.ndarray,
    row_ids: np.ndarray,
    rows: list[dict[str, Any]],
    w: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pred = predict(x, w, mean, std).astype(np.float32)
    out_rows: list[dict[str, Any]] = []
    for idx in sorted(set(int(v) for v in row_ids.tolist())):
        mask = row_ids == idx
        tgt = y[mask]
        pr = pred[mask]
        base_mae = float(np.mean(np.abs(tgt)))
        pred_mae = float(np.mean(np.abs(pr - tgt)))
        base_rmse = float(np.sqrt(np.mean(tgt * tgt)))
        pred_rmse = float(np.sqrt(np.mean((pr - tgt) ** 2)))
        out_rows.append(
            {
                "row_index": idx,
                "scene_id": rows[idx].get("scene_id"),
                "crop": rows[idx].get("crop"),
                "camera": camera_from_row(rows[idx]),
                "sample_count": int(mask.sum()),
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
        "sample_count": int(len(y)),
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
        f"<td>{row['raw_residual_mae_reduction_pct']:.3f}%</td>"
        f"<td>{row['raw_residual_rmse_reduction_pct']:.3f}%</td>"
        "</tr>"
        for row in receipt["holdout_rows"][:80]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Candidate Signal Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #131820; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 860px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dde3e9; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3e9; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Candidate Signal Audit</h1>
<p class="sub">Bounded ridge probe using only candidate raw/CFA, candidate high-frequency features, deterministic coordinates, EV, camera ID, and CFA plane ID. Source raw is used only as the training/evaluation target.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value">{str(receipt['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Holdout rows</div><div class="value">{receipt['holdout_summary']['row_count']}</div></section>
  <section class="card"><div class="label">Holdout MAE recovery median</div><div class="value">{receipt['holdout_summary']['raw_residual_mae_reduction_pct']['median']:.3f}%</div></section>
  <section class="card"><div class="label">Holdout RMSE recovery median</div><div class="value">{receipt['holdout_summary']['raw_residual_rmse_reduction_pct']['median']:.3f}%</div></section>
</div>
<h2>Interpretation</h2>
<p>{html.escape(receipt['interpretation'])}</p>
<h2>Holdout Rows</h2>
<table><tr><th>row</th><th>camera</th><th>scene</th><th>crop</th><th>MAE recovery</th><th>RMSE recovery</th></tr>{rows}</table>
<p>JSON receipt: <code>{html.escape(receipt['artifacts']['receipt'])}</code></p>
</main></body></html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    holdout_crop = getattr(args, "holdout_crop", None)
    holdout_ev = getattr(args, "holdout_ev", None)
    z = np.load(args.targets, allow_pickle=False)
    rows = load_meta(z)
    train_indices, holdout_indices = split_rows(rows, args.holdout_scene, args.holdout_camera, holdout_crop, holdout_ev)
    raw = z["candidate_raw_cfa4"].astype(np.float32)
    hf = z["candidate_raw_hf_cfa4"].astype(np.float32)
    target = z["raw_hf_residual_cfa4"].astype(np.float32)
    if args.max_train_rows:
        train_indices = train_indices[: args.max_train_rows]
    if args.max_holdout_rows:
        holdout_indices = holdout_indices[: args.max_holdout_rows]
    train_x, train_y, train_row_ids = sample_pixels(
        raw=raw,
        hf=hf,
        target=target,
        rows=rows,
        indices=train_indices,
        samples_per_row=args.samples_per_train_row,
        seed=args.seed,
    )
    holdout_x, holdout_y, holdout_row_ids = sample_pixels(
        raw=raw,
        hf=hf,
        target=target,
        rows=rows,
        indices=holdout_indices,
        samples_per_row=args.samples_per_holdout_row,
        seed=args.seed + 1009,
    )
    w, mean, std = fit_ridge(train_x, train_y, args.ridge)
    train_rows, train_summary = eval_rows(
        x=train_x, y=train_y, row_ids=train_row_ids, rows=rows, w=w, mean=mean, std=std
    )
    holdout_rows, holdout_summary = eval_rows(
        x=holdout_x, y=holdout_y, row_ids=holdout_row_ids, rows=rows, w=w, mean=mean, std=std
    )
    median_mae = float(holdout_summary["raw_residual_mae_reduction_pct"]["median"])
    production_ready = median_mae >= float(args.promotion_recovery_threshold)
    if median_mae < 1.0:
        interpretation = (
            "Candidate-only low-order raw/HF/metadata features have effectively no linear predictive power on this holdout. "
            "The next pass should not rely on another small local learner over the same statistics; it needs a stronger learned prior, "
            "a different runtime signal, or a materially different objective."
        )
    elif median_mae < float(args.promotion_recovery_threshold):
        interpretation = (
            "Candidate-only features contain some signal, but this simple probe is still far below the promotion floor. "
            "A stronger model may be justified, but promotion still requires full still/editor-latitude evidence."
        )
    else:
        interpretation = (
            "The linear candidate-only probe clears the promotion recovery floor. This is not production by itself, "
            "but it warrants a stronger model pass and full still/editor-latitude review."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output_dir / "candidate_signal_audit.json"
    dashboard_path = args.output_dir / "index.html"
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_npz": str(args.targets),
        "target_npz_sha256": sha256_file(args.targets),
        "production_ready": production_ready,
        "runtime_policy": {
            "uses_candidate_raw_at_runtime": True,
            "uses_candidate_hf_at_runtime": True,
            "uses_source_raw_at_runtime": False,
            "uses_ref_or_jpeg_content_at_runtime": False,
        },
        "split": {
            "holdout_scene": args.holdout_scene,
            "holdout_camera": args.holdout_camera,
            "holdout_crop": holdout_crop,
            "holdout_ev": holdout_ev,
            "train_row_count": len(train_indices),
            "holdout_row_count": len(holdout_indices),
        },
        "probe": {
            "kind": "ridge_pixel_candidate_signal",
            "feature_channels": int(train_x.shape[1]),
            "ridge": float(args.ridge),
            "samples_per_train_row": int(args.samples_per_train_row),
            "samples_per_holdout_row": int(args.samples_per_holdout_row),
            "promotion_recovery_threshold": float(args.promotion_recovery_threshold),
            "seed": int(args.seed),
        },
        "train_summary": train_summary,
        "holdout_summary": holdout_summary,
        "holdout_rows": holdout_rows,
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
    ap.add_argument("--samples-per-train-row", type=int, default=256)
    ap.add_argument("--samples-per-holdout-row", type=int, default=512)
    ap.add_argument("--max-train-rows", type=int, default=None)
    ap.add_argument("--max-holdout-rows", type=int, default=None)
    ap.add_argument("--ridge", type=float, default=1.0e-2)
    ap.add_argument("--promotion-recovery-threshold", type=float, default=15.0)
    ap.add_argument("--seed", type=int, default=20260630)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
