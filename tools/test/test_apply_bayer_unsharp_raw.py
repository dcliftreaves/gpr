#!/usr/bin/env python3
"""Regression tests for the CFA-preserving raw unsharp diagnostic."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "cnn" / "apply_bayer_unsharp_raw.py"


def run_tool(raw: np.ndarray, amount: float) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "in.raw"
        dst = root / "out.raw"
        raw.astype(np.uint16).tofile(src)
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
                "--amount",
                str(amount),
            ],
            check=True,
        )
        return np.fromfile(dst, dtype=np.uint16).reshape(raw.shape)


def test_constant_frame_is_unchanged() -> None:
    raw = np.full((8, 8), 1234, dtype=np.uint16)
    out = run_tool(raw, 0.25)
    np.testing.assert_array_equal(out, raw)


def test_filter_preserves_cfa_plane_independence() -> None:
    raw = np.zeros((8, 8), dtype=np.uint16)
    raw[2, 2] = 1000
    out = run_tool(raw, 0.25)
    changed = np.argwhere(out != raw)
    assert changed.size
    assert all((int(y) % 2 == 0 and int(x) % 2 == 0) for y, x in changed)


if __name__ == "__main__":
    test_constant_frame_is_unchanged()
    test_filter_preserves_cfa_plane_independence()
