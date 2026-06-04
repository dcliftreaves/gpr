#!/usr/bin/env python3
"""Validate raw clean-target sidecars before they are used for training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from analyze_dng_noise_profile import deinterleave, plane_validation_stats


DEFAULT_JSON = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets.json")


def validate_row(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    z = np.load(row["npz"])
    raw = z["raw"].astype(np.float32)
    clean = z["clean"].astype(np.float32)
    residual = z["exact_residual"].astype(np.float32)
    sigma = np.maximum(z["sigma"].astype(np.float32), 1e-6)
    raw_ch = deinterleave(raw)
    sigma_ch = deinterleave(sigma)
    residual_ch = deinterleave(residual)
    validation = plane_validation_stats(raw_ch, sigma_ch, residual_ch, wavelet=args.wavelet)

    addback_err = float(np.max(np.abs((clean + residual) - raw)))
    max_residual_sigma = float(np.max(np.abs(residual) / sigma))
    residual_rms = float(np.sqrt(np.mean(residual * residual)))
    sigma_rms = float(np.sqrt(np.mean(sigma * sigma)))
    rms_residual_sigma = residual_rms / max(sigma_rms, 1e-9)
    lag_max_abs = max(
        float(validation["removed_lag1_corr_x_max_abs"]),
        float(validation["removed_lag1_corr_y_max_abs"]),
    )
    edge_ratio = float(validation["edge_removed_energy_ratio"])
    checks = {
        "addback": addback_err <= args.max_addback_error,
        "max_residual_sigma": max_residual_sigma <= args.max_residual_sigma + 1e-5,
        "rms_residual_sigma": rms_residual_sigma <= args.max_rms_residual_sigma,
        "lag": lag_max_abs <= args.max_lag_abs,
        "edge_ratio": edge_ratio <= args.max_edge_ratio,
    }
    return {
        "image_id": row["image_id"],
        "crop": row["crop"],
        "iso": row["iso"],
        "npz": row["npz"],
        "pass": all(checks.values()),
        "checks": checks,
        "metrics": {
            "addback_err": addback_err,
            "max_residual_sigma": max_residual_sigma,
            "exact_residual_to_sigma_rms": rms_residual_sigma,
            "flat_removed_to_sigma_rms": float(validation["flat_removed_to_sigma_rms"]),
            "lag_max_abs": lag_max_abs,
            "edge_removed_energy_ratio": edge_ratio,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--max-addback-error", type=float, default=0.001)
    ap.add_argument("--max-residual-sigma", type=float, default=1.0)
    ap.add_argument("--max-rms-residual-sigma", type=float, default=0.35)
    ap.add_argument("--max-lag-abs", type=float, default=0.20)
    ap.add_argument("--max-edge-ratio", type=float, default=1.0)
    ap.add_argument("--wavelet", default="sym4")
    args = ap.parse_args()

    data = json.loads(args.json.read_text())
    rows = [validate_row(row, args) for row in data["rows"]]
    failed = [row for row in rows if not row["pass"]]
    summary = {
        "input": str(args.json),
        "thresholds": {
            "max_addback_error": args.max_addback_error,
            "max_residual_sigma": args.max_residual_sigma,
            "max_rms_residual_sigma": args.max_rms_residual_sigma,
            "max_lag_abs": args.max_lag_abs,
            "max_edge_ratio": args.max_edge_ratio,
        },
        "pass_count": len(rows) - len(failed),
        "fail_count": len(failed),
        "rows": rows,
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2))

    for row in rows:
        status = "PASS" if row["pass"] else "FAIL"
        m = row["metrics"]
        failed_checks = ",".join(k for k, ok in row["checks"].items() if not ok)
        print(
            f"{status} {row['image_id']} {row['crop']} ISO={row['iso']} "
            f"res/sigma={m['exact_residual_to_sigma_rms']:.3f} "
            f"lag={m['lag_max_abs']:.3f} edge={m['edge_removed_energy_ratio']:.3f} "
            f"max_sigma={m['max_residual_sigma']:.3f}"
            + (f" failed={failed_checks}" if failed_checks else "")
        )
    print(f"summary: pass={summary['pass_count']} fail={summary['fail_count']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
