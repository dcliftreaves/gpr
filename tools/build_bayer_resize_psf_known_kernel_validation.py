#!/usr/bin/env python3
"""Validate Bayer-resize PSF fitting against a deterministic known kernel.

This is a local algorithm-confidence receipt. It proves that the same fitting
path used by the pair-derived PSF receipt can recover a deliberately non-box
same-color 2x kernel and can reject a mismatched negative-control pair. It is
not native Mission 1 PSF evidence and must not close the controlled-capture
blocker by itself.
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


SCHEMA = "gpr.bayer_resize_psf_receipt.v1"
VALIDATION_SCHEMA = "gpr.bayer_resize_psf_known_kernel_validation.v1"
RAW_SCALE = 16383.0
DEFAULT_WEIGHTS = (0.52, 0.23, 0.17, 0.08)


def import_numpy():
    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError:
        print("build_bayer_resize_psf_known_kernel_validation: missing numpy", file=sys.stderr)
        return None
    return np


def import_pair_fitter():
    try:
        from build_bayer_resize_psf_from_pairs import (  # type: ignore
            candidate_metrics,
            fit_kernel_for_group,
            kernel_low,
            residual_detail_budget_for_arrays,
            target_cells,
            value_stats,
        )
    except ModuleNotFoundError as exc:
        print(f"build_bayer_resize_psf_known_kernel_validation: missing pair fitter: {exc}", file=sys.stderr)
        return None
    return {
        "candidate_metrics": candidate_metrics,
        "fit_kernel_for_group": fit_kernel_for_group,
        "kernel_low": kernel_low,
        "residual_detail_budget_for_arrays": residual_detail_budget_for_arrays,
        "target_cells": target_cells,
        "value_stats": value_stats,
    }


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


def make_target(np: Any, seed: int, height: int, width: int) -> Any:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    planes = []
    for plane in range(4):
        phase = float(plane + 1)
        base = 1800.0 + 37.0 * xx + 23.0 * yy
        base += 420.0 * np.sin((xx + phase * 3.0) * 0.173)
        base += 360.0 * np.cos((yy - phase * 2.0) * 0.137)
        base += 240.0 * np.sin((xx * 0.071) + (yy * 0.113) + phase)
        base += 120.0 * (((xx.astype(np.int32) + 2 * yy.astype(np.int32) + plane) % 7) == 0)
        base += rng.normal(0.0, 18.0, size=(height, width)).astype(np.float32)
        planes.append(np.clip(base, 0.0, RAW_SCALE).astype(np.float32))
    return np.stack(planes, axis=0)


def make_fixture(np: Any, fitter: dict[str, Any], weights: Any, count: int, height: int, width: int) -> tuple[Any, Any, Any]:
    targets = []
    inputs = []
    for idx in range(count):
        target = make_target(np, 1000 + idx * 17, height, width)
        low = fitter["kernel_low"](np, fitter["target_cells"](np, target[None, ...]), weights)[0]
        targets.append(target)
        inputs.append(low.astype(np.float32))
    return np.stack(inputs, axis=0), np.stack(targets, axis=0), weights.astype(np.float32)


def projection_rmse(np: Any, fitter: dict[str, Any], low: Any, target: Any, weights: Any) -> float:
    pred = fitter["kernel_low"](np, fitter["target_cells"](np, target[None, ...]), weights)[0]
    diff = pred.astype(np.float64) - low.astype(np.float64)
    return float(np.sqrt(np.mean(diff * diff)))


def normalized_weight_rmse(np: Any, a: Any, b: Any) -> float:
    return float(np.sqrt(np.mean((np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)) ** 2)))


def render_html(summary: dict[str, Any], receipt: dict[str, Any]) -> str:
    fit = summary["positive_fit"]
    negative = summary["negative_control"]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Bayer Resize PSF Known-Kernel Validation</title>
<style>
body {{ font: 14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #151515; }}
table {{ border-collapse: collapse; margin: 16px 0 28px; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
code {{ background: #f3f3f3; padding: 2px 4px; }}
.pill {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #eee; }}
.ok {{ background: #d1e7dd; }}
.warn {{ background: #fff3cd; }}
</style>
<h1>Bayer Resize PSF Known-Kernel Validation</h1>
<p><span class="pill ok">algorithm_fixture_ready={str(summary["algorithm_fixture_ready"]).lower()}</span>
<span class="pill warn">production_ready={str(receipt["production_ready"]).lower()}</span></p>
<p>This deterministic fixture validates the PSF fitter with a non-box 2x same-color Bayer kernel and a mismatched
negative control. It does not claim native Mission 1 PSF closure.</p>
<h2>Positive Known-Kernel Fit</h2>
<table><tbody>
<tr><th>expected normalized weights</th><td><code>{html.escape(json.dumps(summary["expected_normalized_weights"]))}</code></td></tr>
<tr><th>recovered normalized weights</th><td><code>{html.escape(json.dumps([round(x, 8) for x in fit["normalized_weights"]]))}</code></td></tr>
<tr><th>weight RMSE</th><td>{summary["known_kernel_weight_rmse"]:.10f}</td></tr>
<tr><th>fit RMSE, 14-bit scale</th><td>{fit["rmse_14bit"]:.8f}</td></tr>
<tr><th>sample count</th><td>{fit["sample_count"]}</td></tr>
</tbody></table>
<h2>Negative Control</h2>
<table><tbody>
<tr><th>kind</th><td>{html.escape(negative["kind"])}</td></tr>
<tr><th>projected RMSE, 14-bit scale</th><td>{negative["projection_rmse_14bit"]:.6f}</td></tr>
<tr><th>positive / negative RMSE ratio</th><td>{negative["negative_to_positive_rmse_ratio"]:.2f}x</td></tr>
<tr><th>rejected</th><td>{str(negative["rejected"]).lower()}</td></tr>
</tbody></table>
<h2>Boundary</h2>
<p>real_mission1_controlled_psf_ready={str(summary["real_mission1_controlled_psf_ready"]).lower()}</p>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    np = import_numpy()
    if np is None:
        raise SystemExit(2)
    fitter = import_pair_fitter()
    if fitter is None:
        raise SystemExit(2)

    start = time.perf_counter()
    raw_weights = np.asarray(args.kernel_weight, dtype=np.float32)
    raw_weights = raw_weights / np.sum(raw_weights)
    inputs, targets, weights = make_fixture(np, fitter, raw_weights, args.pair_count, args.height, args.width)

    fit = fitter["fit_kernel_for_group"](np, inputs, targets, list(range(inputs.shape[0])), args.max_samples)
    recovered = np.asarray(fit["normalized_weights"], dtype=np.float64)
    expected = weights.astype(np.float64)
    weight_rmse = normalized_weight_rmse(np, recovered, expected)
    positive_rmse = max(float(fit["rmse_14bit"]), 1.0e-9)

    negative_target = RAW_SCALE - make_target(np, 9001, args.height, args.width)
    negative_low = inputs[0]
    negative_rmse = projection_rmse(np, fitter, negative_low, negative_target, recovered.astype(np.float32))
    negative_ratio = negative_rmse / positive_rmse
    negative_rejected = bool(negative_rmse >= args.negative_rmse_floor and negative_ratio >= args.negative_ratio_floor)

    budget = fitter["residual_detail_budget_for_arrays"](np, inputs, targets)
    candidate_rows = fitter["candidate_metrics"](np, inputs, targets)
    algorithm_fixture_ready = bool(
        weight_rmse <= args.weight_rmse_gate
        and float(fit["rmse_14bit"]) <= args.fit_rmse_gate
        and negative_rejected
    )

    summary = {
        "schema": VALIDATION_SCHEMA,
        "algorithm_fixture_ready": algorithm_fixture_ready,
        "real_mission1_controlled_psf_ready": False,
        "pair_count": int(inputs.shape[0]),
        "input_shape": [int(x) for x in inputs.shape],
        "target_shape": [int(x) for x in targets.shape],
        "expected_normalized_weights": [float(x) for x in expected],
        "positive_fit": fit,
        "known_kernel_weight_rmse": weight_rmse,
        "fit_rmse_gate_14bit": float(args.fit_rmse_gate),
        "weight_rmse_gate": float(args.weight_rmse_gate),
        "negative_control": {
            "kind": "mismatched_target_with_positive_input",
            "projection_rmse_14bit": negative_rmse,
            "negative_rmse_floor_14bit": float(args.negative_rmse_floor),
            "negative_to_positive_rmse_ratio": negative_ratio,
            "negative_ratio_floor": float(args.negative_ratio_floor),
            "rejected": negative_rejected,
        },
        "candidate_kernels": candidate_rows,
        "detail_budget": budget,
        "production_boundary": (
            "This validates the fitter on a deterministic known kernel only; controlled native Mission 1 high/low "
            "pairs with negative controls remain required before PSF-conditioned production promotion."
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    validation_ref = write_json(args.output_dir / "known_kernel_validation.json", summary)
    dataset_ref = write_json(
        args.output_dir / "known_kernel_dataset.json",
        {
            "schema": "gpr.bayer_resize_psf_known_kernel_dataset.v1",
            "pair_count": int(inputs.shape[0]),
            "input_shape": summary["input_shape"],
            "target_shape": summary["target_shape"],
            "expected_normalized_weights": summary["expected_normalized_weights"],
            "negative_control_kind": summary["negative_control"]["kind"],
        },
    )
    placeholder = {
        "algorithm_fixture_only": True,
        "production_evidence": False,
        "reason": "known-kernel fitter validation only; real Mission 1 PSF media required for promotion",
    }
    gvid_ref = write_json(args.output_dir / "known_kernel_gvid_placeholder.json", placeholder | {"artifact_role": "gvid"})
    raw_ref = write_json(
        args.output_dir / "known_kernel_editable_raw_placeholder.json",
        placeholder | {"artifact_role": "editable_dng_or_gpr"},
    )
    prores_ref = write_json(args.output_dir / "known_kernel_prores_placeholder.json", placeholder | {"artifact_role": "prores"})
    timing_ref = write_json(
        args.output_dir / "timing_memory.json",
        {
            "elapsed_ms": (time.perf_counter() - start) * 1000.0,
            "implementation": "numpy_known_kernel_pair_fit",
            "max_samples": int(args.max_samples),
            "production_evidence": False,
        },
    )

    receipt = {
        "schema": SCHEMA,
        "psf_model": {
            "model_id": args.model_id,
            "estimation_method": "deterministic_known_kernel_same_color_2x_lstsq_v1",
            "kernel_width_px": float(fit["kernel_width_px"]),
            "kernel_height_px": float(fit["kernel_height_px"]),
            "fit_rmse_px": weight_rmse,
            "expected_normalized_weights": summary["expected_normalized_weights"],
            "normalized_weights": fit["normalized_weights"],
            "rmse_14bit": fit["rmse_14bit"],
            "normalized_rmse": fit["normalized_rmse"],
            "known_kernel_weight_rmse": weight_rmse,
        },
        "dataset": {
            "pair_count": int(inputs.shape[0]),
            "sharp_edge_count": int(inputs.shape[0]),
            "texture_field_count": int(inputs.shape[0]),
            "cfa_phases": ["RGGB", "GBRG", "GRBG", "BGGR"],
            "dataset_receipt": dataset_ref,
            "validation_receipt": validation_ref,
        },
        "detail_budget": budget,
        "gate_results": {
            "mission42_passed": False,
            "z8_all24_passed": False,
            "min_raw_psnr_delta_db": 0.0,
            "min_gradient_mae_improvement_pct": 0.0,
            "known_kernel_recovered": algorithm_fixture_ready,
            "negative_control_rejected": negative_rejected,
            "negative_control_rmse_14bit": negative_rmse,
        },
        "receipts": {
            "gvid": gvid_ref,
            "editable_dng_or_gpr": raw_ref,
            "prores": prores_ref,
            "timing_memory": timing_ref,
        },
        "production_ready": False,
    }
    receipt_ref = write_json(args.output_dir / "bayer_resize_psf_receipt.json", receipt)
    (args.output_dir / "index.html").write_text(render_html(summary, receipt), encoding="utf-8")
    write_json(
        args.output_dir / "index_manifest.json",
        {
            "schema": "gpr.bayer_resize_psf_known_kernel_validation_index.v1",
            "receipt": receipt_ref,
            "validation": validation_ref,
            "dashboard": artifact_ref(args.output_dir / "index.html"),
        },
    )
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--model-id", default="known_kernel_same_color_2x_psf_validation_v1")
    ap.add_argument("--pair-count", type=int, default=5)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--max-samples", type=int, default=120000)
    ap.add_argument("--kernel-weight", type=float, action="append", default=None)
    ap.add_argument("--weight-rmse-gate", type=float, default=1.0e-5)
    ap.add_argument("--fit-rmse-gate", type=float, default=1.0e-3)
    ap.add_argument("--negative-rmse-floor", type=float, default=100.0)
    ap.add_argument("--negative-ratio-floor", type=float, default=1000.0)
    args = ap.parse_args()

    if args.pair_count < 2:
        print("build_bayer_resize_psf_known_kernel_validation: --pair-count must be >= 2", file=sys.stderr)
        return 2
    if args.height < 16 or args.width < 16 or args.height % 2 or args.width % 2:
        print("build_bayer_resize_psf_known_kernel_validation: dimensions must be even and >= 16", file=sys.stderr)
        return 2
    if args.kernel_weight is None:
        args.kernel_weight = list(DEFAULT_WEIGHTS)
    if len(args.kernel_weight) != 4:
        print("build_bayer_resize_psf_known_kernel_validation: exactly four --kernel-weight values are required", file=sys.stderr)
        return 2
    if sum(args.kernel_weight) <= 0:
        print("build_bayer_resize_psf_known_kernel_validation: kernel weights must sum positive", file=sys.stderr)
        return 2

    receipt = build(args)
    print(args.output_dir / "bayer_resize_psf_receipt.json")
    print(json.dumps(receipt["psf_model"], indent=2, sort_keys=True))
    return 0 if receipt["gate_results"]["known_kernel_recovered"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
