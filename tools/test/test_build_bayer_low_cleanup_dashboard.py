#!/usr/bin/env python3
"""Smoke-test the 1x Bayer cleanup dashboard builder."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    print("test_build_bayer_low_cleanup_dashboard: SKIP missing numpy")
    raise SystemExit(0)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_bayer_low_cleanup_dashboard.py"


def write_raw(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.astype("<u2").tofile(path)


def test_build_bayer_low_cleanup_dashboard() -> None:
    with tempfile.TemporaryDirectory(prefix="bayer_cleanup_dashboard_") as td:
        root = Path(td)
        low = root / "low"
        clean = root / "clean"
        candidate = root / "candidate"
        out = root / "out"
        height = 16
        width = 16

        yy, xx = np.mgrid[0:height, 0:width]
        target = (1000 + xx * 8 + yy * 11).astype(np.uint16)
        baseline = np.clip(target.astype(np.int32) + 20, 0, 16383).astype(np.uint16)
        improved = np.clip(target.astype(np.int32) + 5, 0, 16383).astype(np.uint16)
        write_raw(clean / "A.raw", target)
        write_raw(low / "A.raw", baseline)
        write_raw(candidate / "A.raw", improved)

        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--dataset",
                f"tiny:{low}:{clean}:{candidate}:{width}:{height}",
                "--output-dir",
                str(out),
                "--crop-size",
                "8",
                "--edge-inset",
                "0",
            ],
            cwd=ROOT,
            check=True,
        )
        payload = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        assert payload["summary"]["count"] == 1
        assert payload["review_render"]["auto_wb"] is True
        assert payload["review_render"]["wb_source"] == "clean target CFA medians"
        row = payload["rows"][0]
        assert row["rmse_improvement_pct"] > 70.0
        assert row["mae_improvement_pct"] > 70.0
        gains = payload["crop_rows"][0]["auto_wb_gains"]
        assert len(gains) == 4
        assert all(gain > 0.0 for gain in gains)
        assert (out / "index.html").exists()
        assert len(list((out / "crops").glob("*.png"))) == 15


if __name__ == "__main__":
    test_build_bayer_low_cleanup_dashboard()
    print("test_build_bayer_low_cleanup_dashboard: PASS")
