#!/usr/bin/env python3
"""Diff two uint16 RAW buffers and print quick stats."""

import argparse
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Diff two RAW planes (uint16)")
    p.add_argument("ref", type=Path, help="Reference RAW path")
    p.add_argument("test", type=Path, help="Test RAW path")
    p.add_argument("width", type=int, help="Image width")
    p.add_argument("height", type=int, help="Image height")
    p.add_argument("--max-report", type=int, default=10, help="Show top-K delta values")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    count = args.width * args.height
    ref = np.fromfile(args.ref, dtype=np.uint16, count=count)
    test = np.fromfile(args.test, dtype=np.uint16, count=count)
    if ref.size != count or test.size != count:
        raise ValueError("input size mismatch")
    diff = ref.astype(np.int32) - test.astype(np.int32)
    print(f"Diff min={diff.min()} max={diff.max()} mean={diff.mean():.2f} std={diff.std():.2f}")
    nz = np.count_nonzero(diff)
    print(f"Non-zero pixels: {nz} / {count} ({nz/count:.6%})")
    uniq, counts = np.unique(diff, return_counts=True)
    order = np.argsort(-counts)
    top = min(args.max_report, uniq.size)
    print("Top diffs (value,count):")
    for idx in order[:top]:
        print(f"  {uniq[idx]:+6d}: {counts[idx]}")


if __name__ == "__main__":
    main()
