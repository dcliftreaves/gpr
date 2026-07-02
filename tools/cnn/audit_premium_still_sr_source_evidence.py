#!/usr/bin/env python3
"""Audit whether premium still-SR pair targets have learnable source evidence.

The clean-source pair trainer can fail for two very different reasons:

1. the model/objective is weak, or
2. the low-resolution candidate RAW does not contain enough observable signal
   to predict the held-out high-resolution Bayer target.

This audit keeps those cases separate. It trains a small candidate-only local
linear probe from the same low-resolution Bayer inputs used by the CNN and
checks whether that probe beats nearest same-color 2x interpolation on held-out
tiles. It is a preflight diagnostic, not a production SR candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_source_evidence_audit.v1"
RAW_SCALE = 16383.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "max": float(np.max(arr)),
    }


def psnr_from_mse(mse: float) -> float:
    if mse <= 0.0:
        return float("inf")
    return float(20.0 * math.log10(RAW_SCALE) - 10.0 * math.log10(mse))


def load_pairs(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path, allow_pickle=False) as z:
        inputs = z["inputs"].astype(np.float32)
        targets = z["targets"].astype(np.float32)
        meta = json.loads(str(z["meta"]))
    if inputs.ndim != 4 or targets.ndim != 4:
        raise ValueError("inputs and targets must be NCHW arrays")
    if inputs.shape[:2] != targets.shape[:2]:
        raise ValueError(f"input/target batch or plane mismatch: {inputs.shape} vs {targets.shape}")
    if targets.shape[2] != inputs.shape[2] * 2 or targets.shape[3] != inputs.shape[3] * 2:
        raise ValueError(f"target spatial shape must be 2x input: {inputs.shape} vs {targets.shape}")
    if meta.get("schema") != "gpr.premium_still_sr_pairs.v1":
        raise ValueError(f"unexpected pair schema: {meta.get('schema')}")
    return inputs, targets, meta


def image_camera_lookup(meta: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in meta.get("images", []):
        if isinstance(row, dict):
            out[str(row.get("image_id"))] = str(row.get("camera_key") or "unknown")
    return out


def tile_cameras(meta: dict[str, Any], count: int) -> list[str]:
    images = image_camera_lookup(meta)
    rows = meta.get("tiles", [])
    if len(rows) != count:
        raise ValueError(f"tile metadata count {len(rows)} does not match batch {count}")
    cameras: list[str] = []
    for row in rows:
        image_id = str(row.get("image_id")) if isinstance(row, dict) else "unknown"
        cameras.append(images.get(image_id, "unknown"))
    return cameras


def nearest_same_color_2x(inputs: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(inputs, 2, axis=2), 2, axis=3)


def crop_for_local_features(inputs: np.ndarray, radius: int) -> tuple[np.ndarray, tuple[slice, slice]]:
    if radius <= 0:
        return inputs, (slice(None), slice(None))
    h, w = inputs.shape[-2:]
    if h <= radius * 2 or w <= radius * 2:
        raise ValueError(f"input tiles too small for local radius {radius}: {h}x{w}")
    return inputs[:, :, radius : h - radius, radius : w - radius], (
        slice(radius, h - radius),
        slice(radius, w - radius),
    )


def local_feature_cube(inputs: np.ndarray, radius: int) -> np.ndarray:
    """Return N,C,H,W,F local features for same-plane Bayer samples."""

    center, (ys, xs) = crop_for_local_features(inputs, radius)
    features = [np.ones_like(center, dtype=np.float32)]
    if radius == 0:
        features.append(center)
    else:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                features.append(inputs[:, :, ys.start + dy : ys.stop + dy, xs.start + dx : xs.stop + dx])
    return np.stack(features, axis=-1).astype(np.float32)


def target_phase(targets: np.ndarray, phase_y: int, phase_x: int, radius: int) -> np.ndarray:
    phase = targets[:, :, phase_y::2, phase_x::2]
    if radius <= 0:
        return phase
    h, w = phase.shape[-2:]
    return phase[:, :, radius : h - radius, radius : w - radius]


def sample_rows(
    *,
    features: np.ndarray,
    target: np.ndarray,
    tile_indices: np.ndarray,
    max_samples: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    n, c, h, w, f = features.shape
    available = int(tile_indices.size) * c * h * w
    if available <= 0:
        raise ValueError("no samples available")
    sample_count = min(int(max_samples), available)
    flat_tile = rng.integers(0, int(tile_indices.size), size=sample_count)
    flat_plane = rng.integers(0, c, size=sample_count)
    flat_y = rng.integers(0, h, size=sample_count)
    flat_x = rng.integers(0, w, size=sample_count)
    real_tiles = tile_indices[flat_tile]
    x = features[real_tiles, flat_plane, flat_y, flat_x, :].reshape(sample_count, f)
    y = target[real_tiles, flat_plane, flat_y, flat_x].reshape(sample_count)
    return x.astype(np.float64), y.astype(np.float64)


def fit_ridge(x: np.ndarray, y: np.ndarray, ridge_lambda: float) -> np.ndarray:
    xtx = x.T @ x
    reg = np.eye(xtx.shape[0], dtype=np.float64) * float(ridge_lambda)
    reg[0, 0] = 0.0
    return np.linalg.solve(xtx + reg, x.T @ y)


def predict_tiles(features: np.ndarray, weights: np.ndarray, tile_indices: np.ndarray) -> np.ndarray:
    x = features[tile_indices].astype(np.float64)
    pred = np.tensordot(x, weights, axes=([-1], [0]))
    return np.clip(pred, 0.0, RAW_SCALE).astype(np.float32)


def metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    diff = pred.astype(np.float32) - target.astype(np.float32)
    abs_diff = np.abs(diff)
    mse = float(np.mean(diff * diff))
    return {
        "mae": float(np.mean(abs_diff)),
        "rmse": float(math.sqrt(mse)),
        "psnr_db": psnr_from_mse(mse),
    }


def recovery_pct(baseline: float, candidate: float) -> float:
    if baseline <= 0.0:
        return 0.0
    return float((baseline - candidate) * 100.0 / baseline)


def split_indices(cameras: list[str], holdout_camera: str) -> tuple[np.ndarray, np.ndarray]:
    holdout = np.asarray([idx for idx, camera in enumerate(cameras) if camera == holdout_camera], dtype=np.int64)
    train = np.asarray([idx for idx, camera in enumerate(cameras) if camera != holdout_camera], dtype=np.int64)
    if holdout.size == 0:
        raise ValueError(f"no holdout tiles for camera {holdout_camera!r}")
    if train.size == 0:
        raise ValueError(f"no train tiles outside camera {holdout_camera!r}")
    return train, holdout


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "phase_count": len(rows),
        "linear_probe_mae_recovery_pct": stats([float(row["linear_probe_mae_recovery_pct"]) for row in rows]),
        "linear_probe_rmse_recovery_pct": stats([float(row["linear_probe_rmse_recovery_pct"]) for row in rows]),
        "nearest_mae": stats([float(row["nearest_mae"]) for row in rows]),
        "linear_probe_mae": stats([float(row["linear_probe_mae"]) for row in rows]),
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    t0 = time.perf_counter()
    inputs, targets, meta = load_pairs(args.pairs)
    cameras = tile_cameras(meta, inputs.shape[0])
    train_indices, holdout_indices = split_indices(cameras, args.holdout_camera)
    features = local_feature_cube(inputs, args.radius)

    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(args.seed)
    for phase_y in (0, 1):
        for phase_x in (0, 1):
            target = target_phase(targets, phase_y, phase_x, args.radius)
            nearest = target_phase(nearest_same_color_2x(inputs), phase_y, phase_x, args.radius)
            x_train, y_train = sample_rows(
                features=features,
                target=target,
                tile_indices=train_indices,
                max_samples=args.max_train_samples,
                rng=rng,
            )
            weights = fit_ridge(x_train, y_train, args.ridge_lambda)
            pred_train = predict_tiles(features, weights, train_indices)
            pred_holdout = predict_tiles(features, weights, holdout_indices)
            train_target = target[train_indices]
            holdout_target = target[holdout_indices]
            train_nearest = nearest[train_indices]
            holdout_nearest = nearest[holdout_indices]
            train_base = metrics(train_nearest, train_target)
            holdout_base = metrics(holdout_nearest, holdout_target)
            train_probe = metrics(pred_train, train_target)
            holdout_probe = metrics(pred_holdout, holdout_target)
            rows.append(
                {
                    "phase_y": phase_y,
                    "phase_x": phase_x,
                    "feature_count": int(weights.size),
                    "train_sample_count": int(x_train.shape[0]),
                    "train_tile_count": int(train_indices.size),
                    "holdout_tile_count": int(holdout_indices.size),
                    "nearest_mae": holdout_base["mae"],
                    "nearest_rmse": holdout_base["rmse"],
                    "linear_probe_mae": holdout_probe["mae"],
                    "linear_probe_rmse": holdout_probe["rmse"],
                    "linear_probe_mae_recovery_pct": recovery_pct(holdout_base["mae"], holdout_probe["mae"]),
                    "linear_probe_rmse_recovery_pct": recovery_pct(holdout_base["rmse"], holdout_probe["rmse"]),
                    "train_linear_probe_mae_recovery_pct": recovery_pct(train_base["mae"], train_probe["mae"]),
                    "train_linear_probe_rmse_recovery_pct": recovery_pct(train_base["rmse"], train_probe["rmse"]),
                    "weights": [float(v) for v in weights],
                }
            )

    summary = summarize_rows(rows)
    median_mae = float(summary["linear_probe_mae_recovery_pct"]["median"] or 0.0)
    median_rmse = float(summary["linear_probe_rmse_recovery_pct"]["median"] or 0.0)
    source_evidence_present = median_mae > args.min_recovery_pct and median_rmse > args.min_recovery_pct
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pair_npz": args.pairs.as_posix(),
        "pair_npz_sha256": sha256_file(args.pairs),
        "holdout_camera": args.holdout_camera,
        "train_tile_count": int(train_indices.size),
        "holdout_tile_count": int(holdout_indices.size),
        "camera_tile_counts": {camera: cameras.count(camera) for camera in sorted(set(cameras))},
        "probe": {
            "name": "candidate_only_local_ridge",
            "radius": int(args.radius),
            "ridge_lambda": float(args.ridge_lambda),
            "max_train_samples_per_phase": int(args.max_train_samples),
            "seed": int(args.seed),
            "runtime_inputs": ["candidate_raw"],
            "forbidden_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "jpeg", "gate_metrics"],
        },
        "acceptance": {
            "min_median_mae_recovery_pct": float(args.min_recovery_pct),
            "min_median_rmse_recovery_pct": float(args.min_recovery_pct),
            "source_evidence_present": bool(source_evidence_present),
            "verdict": (
                "source_signal_detected"
                if source_evidence_present
                else "source_signal_not_detected_above_nearest_same_color_2x"
            ),
            "next_gate_a_action": (
                "Use candidate-only local evidence in a material teacher/objective preflight."
                if source_evidence_present
                else "Do not launch another same-target CNN; change target/source evidence or degradation synthesis first."
            ),
        },
        "summary": summary,
        "phase_rows": rows,
        "elapsed_seconds": float(time.perf_counter() - t0),
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{row['phase_y']},{row['phase_x']}</td>"
        f"<td>{row['nearest_mae']:.4f}</td>"
        f"<td>{row['linear_probe_mae']:.4f}</td>"
        f"<td>{row['linear_probe_mae_recovery_pct']:.4f}%</td>"
        f"<td>{row['nearest_rmse']:.4f}</td>"
        f"<td>{row['linear_probe_rmse']:.4f}</td>"
        f"<td>{row['linear_probe_rmse_recovery_pct']:.4f}%</td>"
        "</tr>"
        for row in data["phase_rows"]
    )
    summary = data["summary"]
    verdict = data["acceptance"]["verdict"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Source Evidence Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f7f8fa; }}
main {{ max-width: 1120px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; }}
.sub {{ color: #5d6a75; max-width: 880px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 25px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin: 12px 0 24px; }}
th, td {{ border-bottom: 1px solid #e9edf1; padding: 8px; text-align: left; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; font-size: 12px; }}
</style></head><body><main>
<h1>Premium Still-SR Source Evidence Audit</h1>
<p class="sub">Candidate-only local ridge probe versus nearest same-color Bayer 2x. This tests whether the low RAW source contains observable signal before another CNN training run is allowed.</p>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{html.escape(verdict)}</div></section>
  <section class="card"><div class="label">Holdout</div><div class="value">{html.escape(data['holdout_camera'])}</div></section>
  <section class="card"><div class="label">Median MAE Recovery</div><div class="value">{summary['linear_probe_mae_recovery_pct']['median']:.4f}%</div></section>
  <section class="card"><div class="label">Median RMSE Recovery</div><div class="value">{summary['linear_probe_rmse_recovery_pct']['median']:.4f}%</div></section>
</div>
<p><strong>Pair NPZ:</strong> <code>{html.escape(data['pair_npz'])}</code></p>
<p><strong>Next Gate A action:</strong> {html.escape(data['acceptance']['next_gate_a_action'])}</p>
<table><tr><th>phase y,x</th><th>nearest MAE</th><th>probe MAE</th><th>MAE recovery</th><th>nearest RMSE</th><th>probe RMSE</th><th>RMSE recovery</th></tr>{rows}</table>
<p>JSON: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--holdout-camera", required=True)
    ap.add_argument("--radius", type=int, default=1)
    ap.add_argument("--max-train-samples", type=int, default=200000)
    ap.add_argument("--ridge-lambda", type=float, default=1.0)
    ap.add_argument("--min-recovery-pct", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=20260702)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    data = build_audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "source_evidence_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(
        json.dumps(
            {
                "dashboard": html_path.as_posix(),
                "verdict": data["acceptance"]["verdict"],
                "holdout_camera": data["holdout_camera"],
                "median_mae_recovery_pct": data["summary"]["linear_probe_mae_recovery_pct"]["median"],
                "median_rmse_recovery_pct": data["summary"]["linear_probe_rmse_recovery_pct"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
