#!/usr/bin/env python3
"""Regression test for the camera-noise calibration sidecar builder."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_camera_noise_calibration.py"
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    width = 16
    height = 12
    black = 64.0
    white = 16383.0
    rng = random.Random(1337)

    with tempfile.TemporaryDirectory(prefix="gpr_noise_cal_", dir=temp_root()) as tmp:
        tmp_path = Path(tmp)
        raw_paths = []
        for idx in range(6):
            values = []
            for row in range(height):
                for col in range(width):
                    value = black + rng.gauss(0.0, 1.5)
                    if row % 2 == 0 and col % 2 == 1:
                        value += rng.gauss(0.0, 0.3)
                    values.append(max(0, min(int(round(white)), int(round(value)))))
            path = tmp_path / f"dark_{idx:02d}.raw"
            path.write_bytes(b"".join(v.to_bytes(2, "little") for v in values))
            raw_paths.append(path)

        receipt = tmp_path / "noise_calibration.json"
        cmd = [
            sys.executable,
            str(BUILDER),
            "--width",
            str(width),
            "--height",
            str(height),
            "--bit-depth",
            "14",
            "--cfa-phase",
            "GRBG",
            "--iso",
            "1600",
            "--make",
            "Fixture",
            "--model",
            "Synthetic Dark",
            "--black-level",
            str(black),
            "--white-level",
            str(white),
            "--out",
            str(receipt),
        ]
        for path in raw_paths:
            cmd.extend(["--raw", str(path)])
        subprocess.run(cmd, check=True)
        subprocess.run([sys.executable, str(CHECKER), str(receipt)], check=True)

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.camera_noise_calibration.v1"
        assert payload["camera"]["cfa_phase"] == "GRBG"
        assert payload["calibrations"][0]["usable_for_training_targets"] is True
        planes = payload["calibrations"][0]["per_plane"]
        assert 0.5 < planes["r"]["sigma_black"] < 3.0
        assert planes["r"]["noise_profile_offset"] > 0.0

    print("test_build_camera_noise_calibration: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
