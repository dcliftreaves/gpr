#!/usr/bin/env python3
"""Generate synthetic 16-bit RGGB Bayer raw test images for round-trip testing."""

import argparse
import numpy as np
import sys
from pathlib import Path


def gen_constant(width: int, height: int, value: int = 32768) -> np.ndarray:
    return np.full((height, width), value, dtype=np.uint16)


def gen_gradient_h(width: int, height: int) -> np.ndarray:
    row = np.linspace(0, 65535, width, dtype=np.float64)
    return np.tile(row.astype(np.uint16), (height, 1))


def gen_gradient_v(width: int, height: int) -> np.ndarray:
    col = np.linspace(0, 65535, height, dtype=np.float64)
    return np.tile(col.astype(np.uint16).reshape(-1, 1), (1, width))


def gen_checkerboard(width: int, height: int, block: int = 16) -> np.ndarray:
    img = np.zeros((height, width), dtype=np.uint16)
    for y in range(height):
        for x in range(width):
            if ((x // block) + (y // block)) % 2 == 0:
                img[y, x] = 50000
            else:
                img[y, x] = 15000
    return img


def gen_random(width: int, height: int, seed: int = 42) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return rng.randint(0, 65536, size=(height, width), dtype=np.uint16)


PATTERNS = {
    "constant": gen_constant,
    "gradient_h": gen_gradient_h,
    "gradient_v": gen_gradient_v,
    "checkerboard": gen_checkerboard,
    "random": gen_random,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", "-W", type=int, default=128)
    parser.add_argument("--height", "-H", type=int, default=128)
    parser.add_argument(
        "--pattern",
        "-p",
        choices=list(PATTERNS.keys()) + ["all"],
        default="all",
    )
    parser.add_argument(
        "--outdir", "-o", type=str, default=".",
        help="Output directory for generated .raw files",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    patterns = list(PATTERNS.keys()) if args.pattern == "all" else [args.pattern]

    for name in patterns:
        img = PATTERNS[name](args.width, args.height)
        fname = outdir / f"test_{name}_{args.width}x{args.height}.raw"
        img.tofile(str(fname))
        nbytes = args.width * args.height * 2
        print(f"{fname}  {nbytes} bytes  ({args.width}x{args.height} uint16)")


if __name__ == "__main__":
    main()
