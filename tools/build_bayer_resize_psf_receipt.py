#!/usr/bin/env python3
"""Build a Bayer-resize PSF receipt from a small synthetic fixture.

This is a contract/regression tool, not a replacement for the real Mission/Z8
PSF work. It creates a non-production `gpr.bayer_resize_psf_receipt.v1`
receipt that exercises the receipt schema and records a simple edge-spread
estimate for Bayer-domain resize blur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.bayer_resize_psf_receipt.v1"
NORMAL_BAYER_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR")


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


def make_edge(width: int, height: int, orientation: str) -> list[list[float]]:
    mid_x = width // 2
    mid_y = height // 2
    out: list[list[float]] = []
    for y in range(height):
        row = []
        for x in range(width):
            if orientation == "vertical":
                row.append(1000.0 if x >= mid_x else 0.0)
            else:
                row.append(1000.0 if y >= mid_y else 0.0)
        out.append(row)
    return out


def make_texture(width: int, height: int) -> list[list[float]]:
    out: list[list[float]] = []
    for y in range(height):
        row = []
        for x in range(width):
            value = 512.0
            value += 180.0 * math.sin((x + 0.25 * y) * 0.55)
            value += 110.0 * math.sin((y - 0.5 * x) * 0.37)
            row.append(value)
        out.append(row)
    return out


def downsample_box(img: list[list[float]], factor: int) -> list[list[float]]:
    height = len(img)
    width = len(img[0])
    out: list[list[float]] = []
    for y in range(0, height, factor):
        row = []
        for x in range(0, width, factor):
            total = 0.0
            count = 0
            for yy in range(y, min(y + factor, height)):
                for xx in range(x, min(x + factor, width)):
                    total += img[yy][xx]
                    count += 1
            row.append(total / max(count, 1))
        out.append(row)
    return out


def upsample_nearest(img: list[list[float]], factor: int) -> list[list[float]]:
    out: list[list[float]] = []
    for row in img:
        expanded_row: list[float] = []
        for value in row:
            expanded_row.extend([value] * factor)
        for _ in range(factor):
            out.append(list(expanded_row))
    return out


def transition_width_px(img: list[list[float]], orientation: str) -> float:
    height = len(img)
    width = len(img[0])
    if orientation == "vertical":
        profile = img[height // 2]
    else:
        profile = [img[y][width // 2] for y in range(height)]
    lo = min(profile)
    hi = max(profile)
    span = max(hi - lo, 1e-9)
    p10 = lo + 0.10 * span
    p90 = lo + 0.90 * span
    i10 = next((idx for idx, value in enumerate(profile) if value >= p10), 0)
    i90 = next((idx for idx, value in enumerate(profile) if value >= p90), i10)
    return float(max(1, i90 - i10 + 1))


def gradient_mae(high: list[list[float]], low_up: list[list[float]]) -> float:
    height = min(len(high), len(low_up))
    width = min(len(high[0]), len(low_up[0]))
    total = 0.0
    count = 0
    for y in range(height - 1):
        for x in range(width - 1):
            gh = abs(high[y][x + 1] - high[y][x]) + abs(high[y + 1][x] - high[y][x])
            gl = abs(low_up[y][x + 1] - low_up[y][x]) + abs(low_up[y + 1][x] - low_up[y][x])
            total += abs(gh - gl)
            count += 1
    return total / max(count, 1)


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    start = time.perf_counter()
    width = args.width
    height = args.height
    factor = args.resize_factor

    vertical = make_edge(width, height, "vertical")
    horizontal = make_edge(width, height, "horizontal")
    texture = make_texture(width, height)

    vertical_low = upsample_nearest(downsample_box(vertical, factor), factor)
    horizontal_low = upsample_nearest(downsample_box(horizontal, factor), factor)
    texture_low = upsample_nearest(downsample_box(texture, factor), factor)

    kernel_w = transition_width_px(vertical_low, "vertical")
    kernel_h = transition_width_px(horizontal_low, "horizontal")
    fit_rmse = math.sqrt(((kernel_w - factor) ** 2 + (kernel_h - factor) ** 2) / 2.0)
    grad_mae = gradient_mae(texture, texture_low)

    dataset_ref = write_json(
        args.out_dir / "synthetic_psf_dataset.json",
        {
            "width": width,
            "height": height,
            "resize_factor": factor,
            "cfa_phases": args.cfa_phase,
            "edge_spread": {
                "kernel_width_px": kernel_w,
                "kernel_height_px": kernel_h,
                "fit_rmse_px": fit_rmse,
            },
            "texture_gradient_mae": grad_mae,
        },
    )
    placeholder = {
        "synthetic_only": True,
        "production_evidence": False,
        "reason": "schema regression placeholder; real Mission/Z8 artifacts are required for promotion",
    }
    gvid_ref = write_json(args.out_dir / "synthetic_gvid_placeholder.json", placeholder | {"artifact_role": "gvid"})
    raw_ref = write_json(args.out_dir / "synthetic_editable_raw_placeholder.json", placeholder | {"artifact_role": "editable_dng_or_gpr"})
    prores_ref = write_json(args.out_dir / "synthetic_prores_placeholder.json", placeholder | {"artifact_role": "prores"})
    timing_ref = write_json(
        args.out_dir / "timing_memory.json",
        {
            "elapsed_ms": (time.perf_counter() - start) * 1000.0,
            "implementation": "pure_python_synthetic_psf_receipt_builder",
            "production_evidence": False,
        },
    )

    return {
        "schema": SCHEMA,
        "psf_model": {
            "model_id": args.model_id,
            "estimation_method": "synthetic_box_resize_edge_spread_v1",
            "kernel_width_px": kernel_w,
            "kernel_height_px": kernel_h,
            "fit_rmse_px": fit_rmse,
        },
        "dataset": {
            "pair_count": 3,
            "sharp_edge_count": 2,
            "texture_field_count": 1,
            "cfa_phases": args.cfa_phase,
            "dataset_receipt": dataset_ref,
        },
        "gate_results": {
            "mission42_passed": False,
            "z8_all24_passed": False,
            "min_raw_psnr_delta_db": 0.0,
            "min_gradient_mae_improvement_pct": 0.0,
            "synthetic_texture_gradient_mae": grad_mae,
        },
        "receipts": {
            "gvid": gvid_ref,
            "editable_dng_or_gpr": raw_ref,
            "prores": prores_ref,
            "timing_memory": timing_ref,
        },
        "production_ready": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--model-id", default="synthetic_bayer_resize_psf_v1")
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--resize-factor", type=int, default=2)
    ap.add_argument("--cfa-phase", action="append", choices=NORMAL_BAYER_PHASES, default=None)
    args = ap.parse_args()

    if args.width < 8 or args.height < 8:
        print("build_bayer_resize_psf_receipt: width and height must be >= 8", file=sys.stderr)
        return 2
    if args.resize_factor < 2:
        print("build_bayer_resize_psf_receipt: resize factor must be >= 2", file=sys.stderr)
        return 2
    if args.width % args.resize_factor or args.height % args.resize_factor:
        print("build_bayer_resize_psf_receipt: dimensions must divide by resize factor", file=sys.stderr)
        return 2
    if not args.cfa_phase:
        args.cfa_phase = ["RGGB"]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    receipt_path = args.out_dir / "bayer_resize_psf_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(receipt_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
