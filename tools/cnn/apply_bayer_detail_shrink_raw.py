#!/usr/bin/env python3
"""Apply CFA-preserving low-amplitude detail shrinkage to a uint16 Bayer raw."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def blur3_reflect(plane: np.ndarray) -> np.ndarray:
    padded = np.pad(plane.astype(np.float32), 1, mode="reflect")
    return (
        padded[:-2, :-2]
        + 2.0 * padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + 2.0 * padded[1:-1, :-2]
        + 4.0 * padded[1:-1, 1:-1]
        + 2.0 * padded[1:-1, 2:]
        + padded[2:, :-2]
        + 2.0 * padded[2:, 1:-1]
        + padded[2:, 2:]
    ) * (1.0 / 16.0)


def soft_threshold(detail: np.ndarray, threshold: float) -> np.ndarray:
    if threshold <= 0.0:
        return detail
    return np.sign(detail) * np.maximum(np.abs(detail) - threshold, 0.0)


def apply_detail_shrink(raw: np.ndarray, threshold: float, gain: float, max_value: int) -> np.ndarray:
    out = raw.astype(np.float32).copy()
    for y in (0, 1):
        for x in (0, 1):
            plane = out[y::2, x::2]
            low = blur3_reflect(plane)
            detail = plane - low
            out[y::2, x::2] = low + gain * soft_threshold(detail, threshold)
    return np.clip(np.rint(out), 0, max_value).astype(np.uint16)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in-raw", type=Path, required=True)
    ap.add_argument("--out-raw", type=Path, required=True)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--threshold", type=float, required=True, help="same-color plane residual soft threshold in raw counts")
    ap.add_argument("--gain", type=float, default=1.0, help="gain applied to thresholded residual; gain=1 preserves large residual amplitude minus threshold")
    ap.add_argument("--max-value", type=int, default=65535)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()

    arr = np.fromfile(args.in_raw, dtype="<u2")
    expected = args.width * args.height
    if arr.size != expected:
        raise ValueError(f"{args.in_raw} has {arr.size} pixels, expected {expected}")
    raw = arr.reshape(args.height, args.width)
    out = apply_detail_shrink(raw, args.threshold, args.gain, args.max_value)

    args.out_raw.parent.mkdir(parents=True, exist_ok=True)
    out.astype("<u2", copy=False).tofile(args.out_raw)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(
                {
                    "schema": "gpr.bayer_detail_shrink_raw.v1",
                    "input": str(args.in_raw),
                    "output": str(args.out_raw),
                    "width": args.width,
                    "height": args.height,
                    "threshold": args.threshold,
                    "gain": args.gain,
                    "max_value": args.max_value,
                    "filter": "per-cfa-plane 3x3 binomial lowpass plus soft-thresholded residual",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
