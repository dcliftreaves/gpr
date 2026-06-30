#!/usr/bin/env python3
"""Estimate Bayer-resize PSF evidence from real high/low Bayer tile pairs.

This consumes the premium still-SR pair NPZ layout (`inputs`, `targets`,
JSON `meta`) and emits a non-production `gpr.bayer_resize_psf_receipt.v1`.
The current pair builder creates the low image by same-color 2x2 averaging, so
this receipt validates real fixture extraction and the modeled resize kernel.
It is not a substitute for a native sensor/DMA PSF measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "gpr.bayer_resize_psf_receipt.v1"
RAW_SCALE = 16383.0
NORMAL_BAYER_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR")


def import_numpy():
    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError:
        print("build_bayer_resize_psf_from_pairs: missing numpy", file=sys.stderr)
        return None
    return np


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": sha256_file(path)}


def write_json(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact_ref(path)


def read_pairs(np: Any, pairs: Path) -> tuple[Any, Any, dict[str, Any]]:
    data = np.load(pairs, allow_pickle=False)
    inputs = data["inputs"].astype(np.float32)
    targets = data["targets"].astype(np.float32)
    meta = json.loads(str(data["meta"]))
    if inputs.ndim != 4 or targets.ndim != 4:
        raise ValueError("inputs and targets must have shape N,C,H,W")
    if inputs.shape[0] != targets.shape[0] or inputs.shape[1] != targets.shape[1]:
        raise ValueError("inputs and targets must share N and C dimensions")
    if targets.shape[2] != inputs.shape[2] * 2 or targets.shape[3] != inputs.shape[3] * 2:
        raise ValueError("targets must be exactly 2x the input plane dimensions")
    return inputs, targets, meta


def target_cells(np: Any, target: Any) -> Any:
    """Return per-low-pixel same-color 2x2 cells as (..., 4)."""
    a = target[..., 0::2, 0::2]
    b = target[..., 0::2, 1::2]
    c = target[..., 1::2, 0::2]
    d = target[..., 1::2, 1::2]
    return np.stack([a, b, c, d], axis=-1)


def kernel_low(np: Any, cells: Any, weights: Any) -> Any:
    return np.tensordot(cells, weights.astype(np.float32), axes=([-1], [0]))


def candidate_metrics(np: Any, inputs: Any, targets: Any) -> list[dict[str, Any]]:
    cells = target_cells(np, targets)
    candidates = {
        "same_color_sample_topleft": np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        "same_color_sample_topright": np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
        "same_color_sample_bottomleft": np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32),
        "same_color_sample_bottomright": np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        "same_color_box2": np.array([0.25, 0.25, 0.25, 0.25], dtype=np.float32),
    }
    rows = []
    for name, weights in candidates.items():
        pred = kernel_low(np, cells, weights)
        diff = pred - inputs
        rmse = float(np.sqrt(np.mean(diff * diff)))
        mae = float(np.mean(np.abs(diff)))
        rows.append(
            {
                "kernel": name,
                "weights": [float(x) for x in weights],
                "rmse_14bit": rmse,
                "mae_14bit": mae,
                "normalized_rmse": rmse / RAW_SCALE,
                "normalized_mae": mae / RAW_SCALE,
            }
        )
    return sorted(rows, key=lambda row: row["rmse_14bit"])


def tile_features(np: Any, target: Any) -> tuple[float, float, float]:
    gx = np.abs(target[:, :, 1:] - target[:, :, :-1])
    gy = np.abs(target[:, 1:, :] - target[:, :-1, :])
    grad = np.concatenate([gx.reshape(-1), gy.reshape(-1)])
    p95 = float(np.percentile(grad, 95))
    p99 = float(np.percentile(grad, 99))
    std = float(np.std(target))
    return p95, p99, std


def fit_kernel_for_group(np: Any, inputs: Any, targets: Any, indexes: list[int], max_samples: int) -> dict[str, Any]:
    sample_rows = []
    sample_y = []
    stride = max(1, int(math.sqrt(max(1, (len(indexes) * inputs.shape[1] * inputs.shape[2] * inputs.shape[3]) / max_samples))))
    for idx in indexes:
        cells = target_cells(np, targets[idx : idx + 1])[0]
        x = cells[:, ::stride, ::stride, :].reshape(-1, 4)
        y = inputs[idx, :, ::stride, ::stride].reshape(-1)
        sample_rows.append(x)
        sample_y.append(y)
    a = np.concatenate(sample_rows, axis=0).astype(np.float64)
    yv = np.concatenate(sample_y, axis=0).astype(np.float64)
    if a.shape[0] > max_samples:
        sel = np.linspace(0, a.shape[0] - 1, max_samples).astype(np.int64)
        a = a[sel]
        yv = yv[sel]
    weights, residuals, rank, singular_values = np.linalg.lstsq(a, yv, rcond=None)
    pred = a @ weights
    diff = pred - yv
    rmse = float(np.sqrt(np.mean(diff * diff)))
    mae = float(np.mean(np.abs(diff)))
    weight_sum = float(np.sum(weights))
    norm = weights / weight_sum if abs(weight_sum) > 1e-9 else weights
    active = np.abs(norm) >= 0.01
    cols = np.array([0, 1, 0, 1])
    rows = np.array([0, 0, 1, 1])
    kernel_width = float((cols[active].max() - cols[active].min() + 1) if np.any(active) else 0.0)
    kernel_height = float((rows[active].max() - rows[active].min() + 1) if np.any(active) else 0.0)
    box_delta = float(np.sqrt(np.mean((norm - 0.25) ** 2)))
    return {
        "weights": [float(x) for x in weights],
        "normalized_weights": [float(x) for x in norm],
        "weight_sum": weight_sum,
        "rank": int(rank),
        "singular_values": [float(x) for x in singular_values],
        "sample_count": int(a.shape[0]),
        "rmse_14bit": rmse,
        "mae_14bit": mae,
        "normalized_rmse": rmse / RAW_SCALE,
        "normalized_mae": mae / RAW_SCALE,
        "kernel_width_px": kernel_width,
        "kernel_height_px": kernel_height,
        "box_weight_rmse": box_delta,
    }


def estimate(np: Any, pairs: Path, max_samples_per_image: int) -> dict[str, Any]:
    inputs, targets, meta = read_pairs(np, pairs)
    tiles = meta.get("tiles") if isinstance(meta.get("tiles"), list) else []
    image_ids = [str(row.get("image_id", "unknown")) if isinstance(row, dict) else "unknown" for row in tiles]
    if len(image_ids) != inputs.shape[0]:
        image_ids = ["unknown"] * inputs.shape[0]

    by_image: dict[str, list[int]] = defaultdict(list)
    sharp_edge_count = 0
    texture_field_count = 0
    for idx, image_id in enumerate(image_ids):
        by_image[image_id].append(idx)
        p95, p99, std = tile_features(np, targets[idx])
        if p99 >= max(128.0, std * 0.20):
            sharp_edge_count += 1
        if std >= 128.0 and p95 >= 16.0:
            texture_field_count += 1

    global_fit = fit_kernel_for_group(np, inputs, targets, list(range(inputs.shape[0])), max_samples_per_image)
    candidate_rows = candidate_metrics(np, inputs, targets)
    sample_rmse = next(row["rmse_14bit"] for row in candidate_rows if row["kernel"] == "same_color_sample_topleft")
    best_rmse = float(candidate_rows[0]["rmse_14bit"])
    gradient_proxy_improvement = 100.0 * (sample_rmse - best_rmse) / max(sample_rmse, 1e-9)

    per_image = []
    for image_id, indexes in sorted(by_image.items()):
        per_image.append({"image_id": image_id, **fit_kernel_for_group(np, inputs, targets, indexes, max_samples_per_image)})

    phases = []
    for image in meta.get("images", []):
        if isinstance(image, dict):
            phase = image.get("cfa_phase") or image.get("bayer_phase")
            if isinstance(phase, str) and phase in NORMAL_BAYER_PHASES and phase not in phases:
                phases.append(phase)
    if not phases:
        phases = ["RGGB"]

    return {
        "meta": meta,
        "input_shape": [int(x) for x in inputs.shape],
        "target_shape": [int(x) for x in targets.shape],
        "pair_count": int(inputs.shape[0]),
        "image_count": len(by_image),
        "cfa_phases": phases,
        "sharp_edge_count": int(sharp_edge_count),
        "texture_field_count": int(texture_field_count),
        "global_fit": global_fit,
        "candidate_kernels": candidate_rows,
        "per_image": per_image,
        "min_gradient_mae_improvement_pct": float(gradient_proxy_improvement),
    }


def render_html(summary: dict[str, Any], receipt: dict[str, Any]) -> str:
    rows = []
    for row in summary["candidate_kernels"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(row['kernel'])}</td>"
            f"<td>{row['rmse_14bit']:.6f}</td>"
            f"<td>{row['mae_14bit']:.6f}</td>"
            f"<td>{row['normalized_rmse']:.8f}</td>"
            f"<td>{html.escape(json.dumps(row['weights']))}</td>"
            "</tr>"
        )
    image_rows = []
    for row in summary["per_image"]:
        image_rows.append(
            "<tr>"
            f"<td>{html.escape(row['image_id'])}</td>"
            f"<td>{row['sample_count']}</td>"
            f"<td>{row['rmse_14bit']:.6f}</td>"
            f"<td>{html.escape(json.dumps([round(x, 6) for x in row['normalized_weights']]))}</td>"
            f"<td>{row['box_weight_rmse']:.8f}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Bayer Resize PSF From Pairs</title>
<style>
body {{ font: 14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #151515; }}
table {{ border-collapse: collapse; margin: 16px 0 28px; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
code {{ background: #f3f3f3; padding: 2px 4px; }}
.pill {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #eee; }}
.warn {{ background: #fff3cd; }}
</style>
<h1>Bayer Resize PSF From Real Pair Fixtures</h1>
<p><span class="pill warn">production_ready={receipt["production_ready"]}</span></p>
<p>This receipt estimates the effective same-color 2x Bayer resize kernel from the premium still-SR pair set.
The current pair generator uses same-color 2x2 averaging, so this validates real fixture extraction and resize
modeling. It does not claim native sensor/DMA PSF closure.</p>
<h2>Summary</h2>
<ul>
<li>Pairs: {summary["pair_count"]}</li>
<li>Images: {summary["image_count"]}</li>
<li>Input shape: <code>{html.escape(json.dumps(summary["input_shape"]))}</code></li>
<li>Target shape: <code>{html.escape(json.dumps(summary["target_shape"]))}</code></li>
<li>Fitted normalized weights: <code>{html.escape(json.dumps([round(x, 8) for x in summary["global_fit"]["normalized_weights"]]))}</code></li>
<li>Kernel width/height: {summary["global_fit"]["kernel_width_px"]:.2f} x {summary["global_fit"]["kernel_height_px"]:.2f} high-res pixels</li>
</ul>
<h2>Candidate Kernels</h2>
<table><thead><tr><th>kernel</th><th>RMSE 14-bit</th><th>MAE 14-bit</th><th>normalized RMSE</th><th>weights</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table>
<h2>Per Image Fit</h2>
<table><thead><tr><th>image</th><th>samples</th><th>RMSE 14-bit</th><th>normalized weights</th><th>box-weight RMSE</th></tr></thead><tbody>
{''.join(image_rows)}
</tbody></table>
"""


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    np = import_numpy()
    if np is None:
        raise SystemExit(2)
    start = time.perf_counter()
    summary = estimate(np, args.pairs, args.max_samples_per_image)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    dataset_payload = {
        "schema": "gpr.bayer_resize_psf_from_pairs_dataset.v1",
        "source_pair_set": artifact_ref(args.pairs),
        "source_pair_sidecar": artifact_ref(args.pairs.with_suffix(args.pairs.suffix + ".json"))
        if args.pairs.with_suffix(args.pairs.suffix + ".json").is_file()
        else None,
        "summary": summary,
    }
    dataset_ref = write_json(args.out_dir / "pair_psf_dataset.json", dataset_payload)

    placeholder = {
        "production_evidence": False,
        "reason": "pair-derived PSF evidence only; real Mission/Z8 gate media required for promotion",
    }
    gvid_ref = write_json(args.out_dir / "pair_psf_gvid_placeholder.json", placeholder | {"artifact_role": "gvid"})
    raw_ref = write_json(args.out_dir / "pair_psf_editable_raw_placeholder.json", placeholder | {"artifact_role": "editable_dng_or_gpr"})
    prores_ref = write_json(args.out_dir / "pair_psf_prores_placeholder.json", placeholder | {"artifact_role": "prores"})
    timing_ref = write_json(
        args.out_dir / "timing_memory.json",
        {
            "elapsed_ms": (time.perf_counter() - start) * 1000.0,
            "implementation": "numpy_pair_kernel_fit",
            "max_samples_per_image": args.max_samples_per_image,
            "production_evidence": False,
        },
    )

    fit = summary["global_fit"]
    receipt = {
        "schema": SCHEMA,
        "psf_model": {
            "model_id": args.model_id,
            "estimation_method": "real_pair_same_color_2x_lstsq_v1",
            "kernel_width_px": fit["kernel_width_px"],
            "kernel_height_px": fit["kernel_height_px"],
            "fit_rmse_px": fit["box_weight_rmse"],
            "normalized_weights": fit["normalized_weights"],
            "rmse_14bit": fit["rmse_14bit"],
            "normalized_rmse": fit["normalized_rmse"],
            "best_candidate_kernel": summary["candidate_kernels"][0]["kernel"],
        },
        "dataset": {
            "pair_count": summary["pair_count"],
            "sharp_edge_count": summary["sharp_edge_count"],
            "texture_field_count": summary["texture_field_count"],
            "cfa_phases": summary["cfa_phases"],
            "dataset_receipt": dataset_ref,
        },
        "gate_results": {
            "mission42_passed": False,
            "z8_all24_passed": False,
            "min_raw_psnr_delta_db": 0.0,
            "min_gradient_mae_improvement_pct": summary["min_gradient_mae_improvement_pct"],
            "best_kernel_rmse_14bit": summary["candidate_kernels"][0]["rmse_14bit"],
        },
        "receipts": {
            "gvid": gvid_ref,
            "editable_dng_or_gpr": raw_ref,
            "prores": prores_ref,
            "timing_memory": timing_ref,
        },
        "production_ready": False,
    }
    write_json(args.out_dir / "bayer_resize_psf_receipt.json", receipt)
    (args.out_dir / "index.html").write_text(render_html(summary, receipt), encoding="utf-8")
    write_json(
        args.out_dir / "index_manifest.json",
        {
            "schema": "gpr.bayer_resize_psf_from_pairs_index.v1",
            "receipt": artifact_ref(args.out_dir / "bayer_resize_psf_receipt.json"),
            "dashboard": artifact_ref(args.out_dir / "index.html"),
        },
    )
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, required=True, help="premium still-SR pair NPZ")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--model-id", default="real_pair_same_color_2x_psf_v1")
    ap.add_argument("--max-samples-per-image", type=int, default=200000)
    args = ap.parse_args()

    if not args.pairs.is_file():
        print(f"build_bayer_resize_psf_from_pairs: missing pair file: {args.pairs}", file=sys.stderr)
        return 2
    if args.max_samples_per_image < 1000:
        print("build_bayer_resize_psf_from_pairs: --max-samples-per-image must be >= 1000", file=sys.stderr)
        return 2

    receipt = build_receipt(args)
    print(args.out_dir / "bayer_resize_psf_receipt.json")
    print(json.dumps(receipt["psf_model"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
