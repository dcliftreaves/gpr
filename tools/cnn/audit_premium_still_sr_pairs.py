#!/usr/bin/env python3
"""Audit premium still-SR clean-source RAW pair targets.

This is a pre-training receipt, not a model evaluator. It verifies that the
pair NPZ has the expected low/high same-color Bayer layout and records the
baseline that the first clean-source RAW SR teacher must beat.
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


SCHEMA = "gpr.premium_still_sr_pair_audit.v1"
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
        "mean": float(arr.mean()),
        "max": float(arr.max()),
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
    if inputs.shape[0] != targets.shape[0] or inputs.shape[1] != targets.shape[1]:
        raise ValueError(f"input/target batch or plane mismatch: {inputs.shape} vs {targets.shape}")
    if targets.shape[2] != inputs.shape[2] * 2 or targets.shape[3] != inputs.shape[3] * 2:
        raise ValueError(f"target spatial shape must be 2x input: {inputs.shape} vs {targets.shape}")
    if meta.get("schema") != "gpr.premium_still_sr_pairs.v1":
        raise ValueError(f"unexpected pair schema: {meta.get('schema')}")
    return inputs, targets, meta


def nearest_same_color_2x(inputs: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(inputs, 2, axis=2), 2, axis=3)


def row_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    diff = pred.astype(np.float32) - target.astype(np.float32)
    abs_diff = np.abs(diff)
    mse = float(np.mean(diff * diff))
    return {
        "mae": float(np.mean(abs_diff)),
        "rmse": float(math.sqrt(mse)),
        "psnr_db": psnr_from_mse(mse),
        "max_abs": float(np.max(abs_diff)),
        "target_abs_mean": float(np.mean(np.abs(target))),
    }


def image_lookup(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in meta.get("images", []):
        if isinstance(row, dict):
            rows[str(row.get("image_id"))] = row
    return rows


def build_audit(pair_path: Path) -> dict[str, Any]:
    inputs, targets, meta = load_pairs(pair_path)
    pred = nearest_same_color_2x(inputs)
    images = image_lookup(meta)
    tiles = meta.get("tiles", [])
    if len(tiles) != inputs.shape[0]:
        raise ValueError(f"tile metadata count {len(tiles)} does not match batch {inputs.shape[0]}")

    rows: list[dict[str, Any]] = []
    by_image: dict[str, list[dict[str, float]]] = {}
    by_camera: dict[str, list[dict[str, float]]] = {}
    for idx, tile in enumerate(tiles):
        if not isinstance(tile, dict):
            raise ValueError(f"tile {idx} metadata is not an object")
        image_id = str(tile.get("image_id"))
        image = images.get(image_id, {})
        camera_key = str(image.get("camera_key") or "unknown")
        metrics = row_metrics(pred[idx], targets[idx])
        row = {
            "tile_index": idx,
            "image_id": image_id,
            "camera_key": camera_key,
            "class": image.get("class"),
            **metrics,
        }
        rows.append(row)
        by_image.setdefault(image_id, []).append(metrics)
        by_camera.setdefault(camera_key, []).append(metrics)

    def summarize_groups(groups: dict[str, list[dict[str, float]]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, metrics_rows in sorted(groups.items()):
            out[key] = {
                "tile_count": len(metrics_rows),
                "mae": stats([row["mae"] for row in metrics_rows]),
                "rmse": stats([row["rmse"] for row in metrics_rows]),
                "psnr_db": stats([row["psnr_db"] for row in metrics_rows]),
                "max_abs": stats([row["max_abs"] for row in metrics_rows]),
            }
        return out

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pair_npz": pair_path.as_posix(),
        "pair_npz_sha256": sha256_file(pair_path),
        "pair_meta": {
            "dataset_label": meta.get("dataset_label"),
            "fixture_manifest": meta.get("fixture_manifest"),
            "fixture_manifest_sha256": meta.get("fixture_manifest_sha256"),
            "low_tile": meta.get("low_tile"),
            "high_tile": meta.get("high_tile"),
            "tiles_per_fixture": meta.get("tiles_per_fixture"),
            "include_gpr": meta.get("include_gpr"),
            "image_count": len(meta.get("images", [])),
            "tile_count": int(inputs.shape[0]),
            "input_shape": list(map(int, inputs.shape)),
            "target_shape": list(map(int, targets.shape)),
        },
        "baseline": {
            "name": "nearest_same_color_2x",
            "description": "repeat each low-resolution same-color Bayer sample into a 2x2 high-resolution Bayer-plane block",
            "mae": stats([row["mae"] for row in rows]),
            "rmse": stats([row["rmse"] for row in rows]),
            "psnr_db": stats([row["psnr_db"] for row in rows]),
            "max_abs": stats([row["max_abs"] for row in rows]),
        },
        "by_image": summarize_groups(by_image),
        "by_camera": summarize_groups(by_camera),
        "rows": rows,
        "promotion_use": (
            "A clean-source RAW SR teacher must beat this baseline on held-out images before "
            "candidate-only distillation or premium still-SR promotion."
        ),
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    camera_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(camera)}</td>"
        f"<td>{row['tile_count']}</td>"
        f"<td>{row['mae']['median']:.4f}</td>"
        f"<td>{row['rmse']['median']:.4f}</td>"
        f"<td>{row['psnr_db']['median']:.2f}</td>"
        f"<td>{row['max_abs']['median']:.1f}</td>"
        "</tr>"
        for camera, row in data["by_camera"].items()
    )
    image_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(image_id)}</td>"
        f"<td>{row['tile_count']}</td>"
        f"<td>{row['mae']['median']:.4f}</td>"
        f"<td>{row['rmse']['median']:.4f}</td>"
        f"<td>{row['psnr_db']['median']:.2f}</td>"
        "</tr>"
        for image_id, row in data["by_image"].items()
    )
    base = data["baseline"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Pair Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f7f8fa; }}
main {{ max-width: 1120px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; }}
.sub {{ color: #5d6a75; max-width: 820px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 25px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin: 12px 0 24px; }}
th, td {{ border-bottom: 1px solid #e9edf1; padding: 8px; text-align: left; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; font-size: 12px; }}
</style></head><body><main>
<h1>Premium Still-SR Pair Audit</h1>
<p class="sub">Clean-source RAW SR pair layout check and nearest same-color 2x baseline. This is the baseline the first teacher must beat before candidate-only distillation.</p>
<div class="grid">
  <section class="card"><div class="label">Tiles</div><div class="value">{data['pair_meta']['tile_count']}</div></section>
  <section class="card"><div class="label">Images</div><div class="value">{data['pair_meta']['image_count']}</div></section>
  <section class="card"><div class="label">Median MAE</div><div class="value">{base['mae']['median']:.3f}</div></section>
  <section class="card"><div class="label">Median PSNR</div><div class="value">{base['psnr_db']['median']:.2f} dB</div></section>
</div>
<p><strong>Pair NPZ:</strong> <code>{html.escape(data['pair_npz'])}</code></p>
<p><strong>SHA256:</strong> <code>{html.escape(data['pair_npz_sha256'])}</code></p>
<h2>By Camera</h2>
<table><tr><th>camera</th><th>tiles</th><th>median MAE</th><th>median RMSE</th><th>median PSNR</th><th>median max abs</th></tr>{camera_rows}</table>
<h2>By Image</h2>
<table><tr><th>image</th><th>tiles</th><th>median MAE</th><th>median RMSE</th><th>median PSNR</th></tr>{image_rows}</table>
<p>JSON: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    data = build_audit(args.pairs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "pair_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
