#!/usr/bin/env python3
"""Audit premium still-SR raw-target distribution by scene and holdout split.

This is a target/objective diagnostic. It does not train a model and it does
not add runtime inputs. It answers whether a held-out scene asks the learner to
recover residual energy that is poorly represented by the selected training
split.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_target_distribution_audit.v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p10": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "p90": 0.0, "max": 0.0, "mean": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
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


def sidecar_path(row: dict[str, Any]) -> str:
    sidecars = row.get("noise_sidecars", [])
    if isinstance(sidecars, list) and sidecars:
        return str(sidecars[0])
    if isinstance(sidecars, str):
        return sidecars
    return ""


def iso_from_sidecar(path: str, cache: dict[str, float]) -> float:
    if path in cache:
        return cache[path]
    iso = 0.0
    if path:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            calibrations = payload.get("calibrations", []) if isinstance(payload, dict) else []
            cal = calibrations[0] if calibrations and isinstance(calibrations[0], dict) else {}
            iso = float(cal.get("iso", 0.0) or 0.0)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            iso = 0.0
    cache[path] = iso
    return iso


def load_rows(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list):
        raise ValueError("target meta must be a JSON list")
    return [row if isinstance(row, dict) else {} for row in rows]


def row_metrics(
    rows: list[dict[str, Any]],
    target: np.ndarray,
    candidate_raw: np.ndarray | None,
) -> list[dict[str, Any]]:
    iso_cache: dict[str, float] = {}
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        t = target[idx].astype(np.float32, copy=False)
        abs_t = np.abs(t)
        candidate_std = float(np.std(candidate_raw[idx].astype(np.float32))) if candidate_raw is not None else 0.0
        plane_mae = np.mean(abs_t, axis=(0, 1)).astype(np.float64)
        out.append(
            {
                "row_index": idx,
                "camera": camera_from_row(row),
                "scene_id": str(row.get("scene_id") or "unknown"),
                "crop": str(row.get("crop") or row.get("crop_id") or idx),
                "iso": iso_from_sidecar(sidecar_path(row), iso_cache),
                "target_abs_mean": float(np.mean(abs_t)),
                "target_rmse": float(np.sqrt(np.mean(t * t))),
                "target_p95_abs": float(np.percentile(abs_t, 95.0)),
                "target_p99_abs": float(np.percentile(abs_t, 99.0)),
                "candidate_raw_std": candidate_std,
                "plane_abs_mean": [float(v) for v in plane_mae.tolist()],
                "plane_abs_mean_max_to_min": float(np.max(plane_mae) / max(float(np.min(plane_mae)), 1.0e-12)),
            }
        )
    return out


def group_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[tuple(str(row.get(key)) for key in keys)].append(row)
    grouped: list[dict[str, Any]] = []
    for key, group in sorted(buckets.items()):
        item = {keys[i]: key[i] for i in range(len(keys))}
        item.update(
            {
                "row_count": len(group),
                "iso_values": sorted({float(row.get("iso", 0.0) or 0.0) for row in group}),
                "target_abs_mean": stats([float(row["target_abs_mean"]) for row in group]),
                "target_rmse": stats([float(row["target_rmse"]) for row in group]),
                "target_p95_abs": stats([float(row["target_p95_abs"]) for row in group]),
                "candidate_raw_std": stats([float(row["candidate_raw_std"]) for row in group]),
                "plane_abs_mean_max_to_min": stats([float(row["plane_abs_mean_max_to_min"]) for row in group]),
            }
        )
        grouped.append(item)
    return grouped


def split_comparison(rows: list[dict[str, Any]], holdout_scene: str | None, train_camera: str | None) -> dict[str, Any]:
    if not holdout_scene:
        return {"enabled": False}
    holdout = [row for row in rows if str(row.get("scene_id")) == holdout_scene]
    if not holdout:
        return {"enabled": True, "holdout_scene": holdout_scene, "error": "holdout scene not found"}
    cameras = {str(row.get("camera")) for row in holdout}
    if train_camera:
        train_cameras = {train_camera}
    elif len(cameras) == 1:
        train_cameras = cameras
    else:
        train_cameras = set()
    train = [
        row
        for row in rows
        if str(row.get("scene_id")) != holdout_scene and (not train_cameras or str(row.get("camera")) in train_cameras)
    ]
    train_vals = [float(row["target_abs_mean"]) for row in train]
    hold_vals = [float(row["target_abs_mean"]) for row in holdout]
    train_stats = stats(train_vals)
    hold_stats = stats(hold_vals)
    train_max = float(max(train_vals)) if train_vals else 0.0
    train_median = float(train_stats["median"])
    hold_median = float(hold_stats["median"])
    ratio = hold_median / max(train_median, 1.0e-12)
    return {
        "enabled": True,
        "holdout_scene": holdout_scene,
        "train_camera_filter": sorted(train_cameras),
        "train_row_count": len(train),
        "holdout_row_count": len(holdout),
        "train_target_abs_mean": train_stats,
        "holdout_target_abs_mean": hold_stats,
        "holdout_median_to_train_median": float(ratio),
        "holdout_rows_above_train_max": int(sum(v > train_max for v in hold_vals)),
        "holdout_rows_above_train_p90": int(sum(v > float(train_stats["p90"]) for v in hold_vals)),
        "distribution_mismatch": bool(ratio >= 3.0 or (hold_vals and sum(v > float(train_stats["p90"]) for v in hold_vals) / len(hold_vals) >= 0.5)),
    }


def render_html(receipt: dict[str, Any]) -> str:
    split = receipt["split_comparison"]
    scene_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['camera']))}</td>"
        f"<td>{html.escape(str(row['scene_id']))}</td>"
        f"<td>{html.escape(','.join(str(v) for v in row['iso_values']))}</td>"
        f"<td>{int(row['row_count'])}</td>"
        f"<td>{float(row['target_abs_mean']['median']):.6f}</td>"
        f"<td>{float(row['target_rmse']['median']):.6f}</td>"
        f"<td>{float(row['target_p95_abs']['median']):.6f}</td>"
        f"<td>{float(row['candidate_raw_std']['median']):.6f}</td>"
        "</tr>"
        for row in sorted(receipt["by_scene"], key=lambda r: (str(r["camera"]), -float(r["target_abs_mean"]["median"])))
    )
    split_html = ""
    if split.get("enabled"):
        split_html = f"""
        <section class="card">
          <h2>Holdout Split</h2>
          <p>Scene <code>{html.escape(str(split.get('holdout_scene')))}</code> has
          <b>{float(split.get('holdout_median_to_train_median', 0.0)):.2f}x</b>
          the median target residual energy of its train split.</p>
          <p>Rows above train p90: <b>{int(split.get('holdout_rows_above_train_p90', 0))}</b> /
          {int(split.get('holdout_row_count', 0))}. Distribution mismatch:
          <b>{html.escape(str(split.get('distribution_mismatch')))}</b>.</p>
        </section>
        """
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Target Distribution Audit</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 24px; background: #f7f7f4; color: #1f2328; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
.card {{ background: white; border: 1px solid #d8d8d0; border-radius: 8px; padding: 14px; margin: 14px 0; }}
.label {{ color: #666; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 24px; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; background: white; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 7px 8px; text-align: left; font-size: 13px; }}
th {{ background: #ecece6; }}
code {{ background: #eee; padding: 1px 4px; border-radius: 4px; }}
</style>
<h1>Premium Still-SR Target Distribution Audit</h1>
<p>This audit groups raw-CFA residual targets by camera, scene, and ISO. It is a target/objective diagnostic, not a production model.</p>
<section class="grid">
  <div class="card"><div class="label">Rows</div><div class="value">{int(receipt['summary']['row_count'])}</div></div>
  <div class="card"><div class="label">Scenes</div><div class="value">{int(receipt['summary']['scene_count'])}</div></div>
  <div class="card"><div class="label">Cameras</div><div class="value">{html.escape(', '.join(receipt['summary']['camera_counts'].keys()))}</div></div>
</section>
{split_html}
<h2>Scene Distribution</h2>
<table>
<tr><th>Camera</th><th>Scene</th><th>ISO</th><th>Rows</th><th>Median target MAE</th><th>Median RMSE</th><th>Median p95</th><th>Median candidate std</th></tr>
{scene_rows}
</table>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    with np.load(args.targets, allow_pickle=False) as z:
        rows_meta = load_rows(z)
        target = z["raw_hf_residual_cfa4"].astype(np.float32)
        candidate_raw = z["candidate_raw_cfa4"].astype(np.float32) if "candidate_raw_cfa4" in z.files else None
    if len(rows_meta) != int(target.shape[0]):
        raise ValueError(f"meta row count {len(rows_meta)} does not match target rows {target.shape[0]}")
    rows = row_metrics(rows_meta, target, candidate_raw)
    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "targets": str(args.targets),
        "targets_sha256": sha256_file(args.targets),
        "policy": {
            "uses_source_raw_at_training": True,
            "uses_source_raw_at_runtime": False,
            "purpose": "target_distribution_diagnostic",
        },
        "summary": {
            "row_count": len(rows),
            "scene_count": len({str(row["scene_id"]) for row in rows}),
            "camera_counts": dict(Counter(str(row["camera"]) for row in rows)),
            "target_abs_mean": stats([float(row["target_abs_mean"]) for row in rows]),
            "target_rmse": stats([float(row["target_rmse"]) for row in rows]),
        },
        "split_comparison": split_comparison(rows, args.holdout_scene, args.train_camera),
        "by_camera": group_rows(rows, ("camera",)),
        "by_scene": group_rows(rows, ("camera", "scene_id")),
        "rows": rows,
        "artifacts": {},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output_dir / "target_distribution_audit.json"
    index_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    index_path.write_text(render_html(receipt), encoding="utf-8")
    receipt["artifacts"] = {"receipt": str(receipt_path), "dashboard": str(index_path)}
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--holdout-scene", help="Optional held-out scene to compare against the same-camera train split.")
    ap.add_argument("--train-camera", help="Optional camera filter for the train split comparison.")
    args = ap.parse_args()
    receipt = run(args)
    print(receipt["artifacts"]["dashboard"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
