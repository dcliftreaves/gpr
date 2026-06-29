#!/usr/bin/env python3
"""Build a camera-noise calibration receipt from raw Bayer darkframes.

This produces the `gpr.camera_noise_calibration.v1` sidecar used by the
product-pillar guard. It intentionally works in raw Bayer space and only marks
the receipt usable for training targets when the source is a darkframe-like
stack with enough frames to separate stochastic noise from scene signal.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.camera_noise_calibration.v1"
PLANE_ORDER = ("r", "g1", "b", "g2")
PHASE_TO_GRID = {
    "RGGB": (("r", "g1"), ("g2", "b")),
    "GRBG": (("g1", "r"), ("b", "g2")),
    "GBRG": (("g1", "b"), ("r", "g2")),
    "BGGR": (("b", "g1"), ("g2", "r")),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stack_sha256(paths: list[Path], metadata: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    for path in paths:
        h.update(path.name.encode("utf-8"))
        h.update(bytes.fromhex(sha256_file(path)))
    return h.hexdigest()


class RunningStats:
    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.total_sq = 0.0

    def update(self, values: array.array) -> None:
        for value in values:
            fv = float(value)
            self.count += 1
            self.total += fv
            self.total_sq += fv * fv

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else 0.0

    @property
    def sigma(self) -> float:
        if self.count <= 1:
            return 0.0
        variance = (self.total_sq - (self.total * self.total / self.count)) / (self.count - 1)
        return math.sqrt(max(variance, 0.0))


def read_raw_u16(path: Path, width: int, height: int) -> array.array:
    arr = array.array("H")
    arr.frombytes(path.read_bytes())
    if sys.byteorder != "little":
        arr.byteswap()
    expected = width * height
    if len(arr) != expected:
        raise ValueError(f"{path} has {len(arr)} uint16 samples, expected {expected}")
    return arr


def update_plane_stats(stats: dict[str, RunningStats], frame: array.array, width: int, height: int, cfa_phase: str) -> None:
    grid = PHASE_TO_GRID[cfa_phase]
    for row in range(height):
        row_base = row * width
        row_grid = grid[row & 1]
        stats[row_grid[0]].update(frame[row_base : row_base + width : 2])
        stats[row_grid[1]].update(frame[row_base + 1 : row_base + width : 2])


def summarize_plane(stats: RunningStats, black_level: float, raw_range: float) -> dict[str, float]:
    sigma = stats.sigma
    mean = stats.mean
    offset = (sigma / max(raw_range, 1.0)) ** 2
    return {
        "noise_profile_scale": 0.0,
        "noise_profile_offset": offset,
        "mean_black": mean,
        "sigma_black": sigma,
        "mean_black_delta": mean - black_level,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    paths = [Path(p) for p in args.raw]
    if not paths:
        raise ValueError("at least one --raw file is required")
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)

    raw_range = float(args.white_level - args.black_level)
    if raw_range <= 0:
        raise ValueError("--white-level must be greater than --black-level")

    by_plane: dict[str, RunningStats] = {plane: RunningStats() for plane in PLANE_ORDER}
    for path in paths:
        update_plane_stats(by_plane, read_raw_u16(path, args.width, args.height), args.width, args.height, args.cfa_phase)

    per_plane = {
        plane: summarize_plane(stats, args.black_level, raw_range)
        for plane, stats in by_plane.items()
    }

    source_kind = args.source_kind
    separates_noise = source_kind in {"darkframes", "flat_dark_pair"} and len(paths) >= 4
    usable = separates_noise
    metadata = {
        "width": args.width,
        "height": args.height,
        "bit_depth": args.bit_depth,
        "cfa_phase": args.cfa_phase,
        "iso": args.iso,
        "source_kind": source_kind,
        "sample_count": len(paths),
    }
    source_hash = stack_sha256(paths, metadata)
    source_path = paths[0].as_posix() if len(paths) == 1 else "raw_stack:" + ",".join(p.name for p in paths)

    return {
        "schema": SCHEMA,
        "camera": {
            "make": args.make,
            "model": args.model,
            "width": args.width,
            "height": args.height,
            "bit_depth": args.bit_depth,
            "cfa_phase": args.cfa_phase,
            "black_level": float(args.black_level),
            "white_level": float(args.white_level),
        },
        "calibrations": [
            {
                "iso": args.iso,
                "calibration_method": "darkframe_stack_per_plane_sigma_v1",
                "source_kind": source_kind,
                "sample_count": len(paths),
                "source": {
                    "path": source_path,
                    "sha256": source_hash,
                },
                "per_plane": per_plane,
                "noise_signal_audit": {
                    "separates_noise_from_signal": separates_noise,
                    "method": "darkframe_stack_sigma" if separates_noise else "insufficient_darkframe_stack",
                    "evidence": (
                        "darkframes contain no scene signal and the stack has at least four frames"
                        if separates_noise
                        else "not enough darkframe evidence to separate stochastic noise from scene signal"
                    ),
                },
                "usable_for_training_targets": usable,
            }
        ],
        "production_ready": usable,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", action="append", required=True, help="little-endian uint16 raw Bayer darkframe")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--bit-depth", type=int, required=True)
    ap.add_argument("--cfa-phase", choices=sorted(PHASE_TO_GRID), required=True)
    ap.add_argument("--iso", type=int, required=True)
    ap.add_argument("--make", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--black-level", type=float, required=True)
    ap.add_argument("--white-level", type=float, required=True)
    ap.add_argument("--source-kind", choices=("darkframes", "flat_dark_pair"), default="darkframes")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    try:
        receipt = build_receipt(args)
    except Exception as exc:
        print(f"build_camera_noise_calibration: {exc}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
