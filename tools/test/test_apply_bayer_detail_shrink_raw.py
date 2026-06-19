#!/usr/bin/env python3
"""Regression tests for the CFA-preserving raw detail-shrink diagnostic."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "cnn" / "apply_bayer_detail_shrink_raw.py"


def run_tool(raw: np.ndarray, threshold: float, gain: float = 1.0) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "in.raw"
        dst = root / "out.raw"
        raw.astype("<u2").tofile(src)
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--in-raw",
                str(src),
                "--out-raw",
                str(dst),
                "--width",
                str(raw.shape[1]),
                "--height",
                str(raw.shape[0]),
                "--threshold",
                str(threshold),
                "--gain",
                str(gain),
            ],
            check=True,
        )
        return np.fromfile(dst, dtype="<u2").reshape(raw.shape)


def test_threshold_zero_is_identity_on_linear_plane() -> None:
    yy, xx = np.indices((8, 8))
    raw = (1000 + 2 * yy + 3 * xx).astype(np.uint16)
    out = run_tool(raw, threshold=0.0)
    np.testing.assert_array_equal(out, raw)


def test_filter_preserves_cfa_plane_independence() -> None:
    raw = np.full((8, 8), 1000, dtype=np.uint16)
    raw[2, 2] = 1010
    out = run_tool(raw, threshold=2.0)
    changed = np.argwhere(out != raw)
    assert changed.size
    assert all((int(y) % 2 == 0 and int(x) % 2 == 0) for y, x in changed)


def test_soft_threshold_reduces_small_same_plane_impulse() -> None:
    raw = np.full((8, 8), 1000, dtype=np.uint16)
    raw[2, 2] = 1004
    out = run_tool(raw, threshold=4.0)
    assert int(out[2, 2]) < int(raw[2, 2])


if __name__ == "__main__":
    test_threshold_zero_is_identity_on_linear_plane()
    test_filter_preserves_cfa_plane_independence()
    test_soft_threshold_reduces_small_same_plane_impulse()
