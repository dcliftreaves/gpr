#!/usr/bin/env python3
"""Analyze same-color Bayer detail-residual sidecar budget without writing raws."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from apply_bayer_detail_residual_oracle_raw import (
    apply_detail_residual,
    parse_planes,
    read_raw,
    rmse,
    sidecar_specs,
)


SCHEMA = "gpr.bayer_detail_residual_budget.v1"


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def stat(values: list[float]) -> dict[str, float]:
    return {
        "min": float(min(values)) if values else 0.0,
        "median": float(statistics.median(values)) if values else 0.0,
        "mean": float(sum(values) / len(values)) if values else 0.0,
        "p90": pct(values, 0.90),
        "p95": pct(values, 0.95),
        "max": float(max(values)) if values else 0.0,
    }


def analyze_one(spec: dict[str, Any], args: argparse.Namespace, planes: set[int]) -> dict[str, Any]:
    started = time.perf_counter()
    codec = read_raw(Path(spec["codec_raw"]), int(spec["width"]), int(spec["height"]))
    clean = read_raw(Path(spec["clean_raw"]), int(spec["width"]), int(spec["height"]))
    out, residual = apply_detail_residual(
        codec,
        clean,
        significant_detail_threshold=args.significant_detail_threshold,
        residual_threshold=args.residual_threshold,
        quant_step=args.quant_step,
        planes=planes,
        max_value=args.max_value,
    )
    sidecar = residual["sidecar"]
    return {
        "image": spec["image"],
        "width": int(spec["width"]),
        "height": int(spec["height"]),
        "codec_clean_rmse": rmse(codec, clean),
        "output_clean_rmse": rmse(out, clean),
        "rmse_reduction_pct": 100.0 * (rmse(codec, clean) - rmse(out, clean)) / rmse(codec, clean),
        "nonzero_pct": sidecar["nonzero_pct"],
        "nonzero_samples": sidecar["nonzero_samples"],
        "bitmap_values_zlib_bytes": sidecar["bitmap_values_zlib_bytes"],
        "dense_i16_zlib_bytes": sidecar["dense_i16_zlib_bytes"],
        "bitmap_bytes_estimate": sidecar["bitmap_bytes_estimate"],
        "sparse_bytes_estimate": sidecar["sparse_bytes_estimate"],
        "elapsed_s": time.perf_counter() - started,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "codec_clean_rmse",
        "output_clean_rmse",
        "rmse_reduction_pct",
        "nonzero_pct",
        "bitmap_values_zlib_bytes",
        "dense_i16_zlib_bytes",
        "bitmap_bytes_estimate",
        "sparse_bytes_estimate",
        "elapsed_s",
    ]
    summary: dict[str, Any] = {"image_count": len(rows)}
    for key in keys:
        summary[key] = stat([float(row[key]) for row in rows])
    if rows:
        summary["worst_by_sidecar_bytes"] = max(rows, key=lambda r: r["bitmap_values_zlib_bytes"])
        summary["worst_by_output_rmse"] = max(rows, key=lambda r: r["output_clean_rmse"])
        summary["best_by_sidecar_bytes"] = min(rows, key=lambda r: r["bitmap_values_zlib_bytes"])
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair-sidecar", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--stem", action="append")
    ap.add_argument("--planes", default="all")
    ap.add_argument("--significant-detail-threshold", type=float, default=2.0)
    ap.add_argument("--residual-threshold", type=float, default=1.0)
    ap.add_argument("--quant-step", type=float, default=2.0)
    ap.add_argument("--max-value", type=int, default=65535)
    args = ap.parse_args()

    started = time.perf_counter()
    planes = parse_planes(args.planes)
    specs = sidecar_specs(args.pair_sidecar, set(args.stem or []) or None)
    rows = [analyze_one(spec, args, planes) for spec in specs]
    payload = {
        "schema": SCHEMA,
        "pair_sidecar": str(args.pair_sidecar),
        "planes": args.planes,
        "significant_detail_threshold": args.significant_detail_threshold,
        "residual_threshold": args.residual_threshold,
        "quant_step": args.quant_step,
        "max_value": args.max_value,
        "elapsed_s": time.perf_counter() - started,
        "summary": summarize(rows),
        "images": rows,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out_json": str(args.out_json), "summary": payload["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
