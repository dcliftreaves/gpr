#!/usr/bin/env python3
"""Extract a rectangular patch from a single-plane uint16 RAW image."""

import argparse
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract RAW patch for fast vc5 probing")
    p.add_argument("input", type=Path, help="Source RAW file (uint16, row-major)")
    p.add_argument("output", type=Path, help="Destination RAW file")
    p.add_argument("width", type=int, help="Full image width in pixels")
    p.add_argument("height", type=int, help="Full image height in pixels")
    p.add_argument("patch_width", type=int, help="Patch width in pixels")
    p.add_argument("patch_height", type=int, help="Patch height in pixels")
    p.add_argument("x", type=int, help="Patch left coordinate (pixels)")
    p.add_argument("y", type=int, help="Patch top coordinate (pixels)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    total = args.width * args.height
    data = np.fromfile(args.input, dtype=np.uint16)
    if data.size != total:
        raise ValueError(f"Expected {total} samples, found {data.size}")
    img = data.reshape((args.height, args.width))
    x0 = max(0, args.x)
    y0 = max(0, args.y)
    x1 = min(args.width, x0 + args.patch_width)
    y1 = min(args.height, y0 + args.patch_height)
    patch = img[y0:y1, x0:x1]
    if patch.shape[0] != args.patch_height or patch.shape[1] != args.patch_width:
        raise ValueError("Patch exceeds source bounds")
    patch.astype(np.uint16).tofile(args.output)
    print(f"wrote {patch.size} samples to {args.output}")


if __name__ == "__main__":
    main()
