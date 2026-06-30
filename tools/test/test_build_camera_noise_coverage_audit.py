#!/usr/bin/env python3
"""Regression test for the camera-noise coverage audit builder."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_camera_noise_coverage_audit.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_noise_coverage_") as td:
        out_dir = Path(td) / "coverage"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--synthetic",
                "--output-dir",
                str(out_dir),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads((out_dir / "noise_coverage.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.camera_noise_coverage_audit.v1"
        assert data["mode"] == "synthetic"
        assert data["summary"]["ready_camera_keys"] == ["x2d", "z8"]
        assert data["summary"]["missing_camera_keys"] == ["mission1", "iphone"]
        assert data["summary"]["production_noise_coverage_ready"] is False
        assert len(data["coverage"]) == 4
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Camera Noise Coverage Audit" in html
        assert "GoPro Mission 1" in html
        assert "no validated production_ready darkframe sidecar" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_camera_noise_coverage_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
