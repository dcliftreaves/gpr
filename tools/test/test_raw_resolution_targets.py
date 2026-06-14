#!/usr/bin/env python3
"""Regression tests for raw resolution target helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/cnn"))

from bench_raw_resolution_targets import downsample_bayer_0p5x  # noqa: E402


def assemble_rggb(r: np.ndarray, g1: np.ndarray, g2: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros((r.shape[0] * 2, r.shape[1] * 2), dtype=np.uint16)
    out[0::2, 0::2] = r
    out[0::2, 1::2] = g1
    out[1::2, 0::2] = g2
    out[1::2, 1::2] = b
    return out


def area_down2_expected(plane: np.ndarray) -> np.ndarray:
    p = plane.astype(np.uint32)
    return (
        (p[0::2, 0::2] + p[0::2, 1::2] + p[1::2, 0::2] + p[1::2, 1::2] + 2) >> 2
    ).astype(np.uint16)


def test_downsample_bayer_0p5x_preserves_cfa_planes() -> None:
    r = np.array(
        [
            [10, 20, 30, 40],
            [50, 60, 70, 80],
            [90, 100, 110, 120],
            [130, 140, 150, 160],
        ],
        dtype=np.uint16,
    )
    g1 = r + 1000
    g2 = r + 2000
    b = r + 3000

    candidate = downsample_bayer_0p5x(assemble_rggb(r, g1, g2, b))
    expected = assemble_rggb(
        area_down2_expected(r),
        area_down2_expected(g1),
        area_down2_expected(g2),
        area_down2_expected(b),
    )

    assert candidate.dtype == np.uint16
    assert candidate.shape == (4, 4)
    np.testing.assert_array_equal(candidate, expected)


if __name__ == "__main__":
    test_downsample_bayer_0p5x_preserves_cfa_planes()
