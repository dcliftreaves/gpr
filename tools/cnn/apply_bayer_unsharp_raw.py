#!/usr/bin/env python3
"""Apply a CFA-preserving unsharp mask to a uint16 Bayer raw frame."""

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


def apply_unsharp(raw: np.ndarray, amount: float) -> np.ndarray:
    out = raw.astype(np.float32).copy()
    for y in (0, 1):
        for x in (0, 1):
            plane = out[y::2, x::2]
            detail = plane - blur3_reflect(plane)
            out[y::2, x::2] = plane + amount * detail
    return np.clip(np.rint(out), 0, 65535).astype(np.uint16)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in-raw", type=Path, required=True)
    ap.add_argument("--out-raw", type=Path, required=True)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--amount", type=float, required=True)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()

    arr = np.fromfile(args.in_raw, dtype=np.uint16)
    expected = args.width * args.height
    if arr.size != expected:
        raise ValueError(f"{args.in_raw} has {arr.size} pixels, expected {expected}")
    raw = arr.reshape(args.height, args.width)
    out = apply_unsharp(raw, args.amount)

    args.out_raw.parent.mkdir(parents=True, exist_ok=True)
    out.tofile(args.out_raw)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(
                {
                    "schema": "gpr.bayer_unsharp_raw.v1",
                    "input": str(args.in_raw),
                    "output": str(args.out_raw),
                    "width": args.width,
                    "height": args.height,
                    "amount": args.amount,
                    "filter": "per-cfa-plane 3x3 binomial unsharp",
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
