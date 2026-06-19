#!/usr/bin/env python3
"""Regression test for Mission 1 SR hard-tile miner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/mine_mission1_sr_hard_tiles.py"


def write_raw(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.astype(np.uint16).tofile(path)


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_sr_hard_tiles_", dir=work_parent) as td:
        root = Path(td)
        high_target = np.arange(16 * 16, dtype=np.uint16).reshape(16, 16) + 100
        high_model = high_target.copy()
        high_model[0:8, 0:8] += 20
        low_clean = np.arange(8 * 8, dtype=np.uint16).reshape(8, 8) + 50
        low_codec = low_clean.copy()
        low_codec[0::2, 0::2] += 6

        target_raw = root / "IMG.raw"
        sr_raw = root / "IMG_sr.raw"
        write_raw(target_raw, high_target)
        write_raw(sr_raw, high_model)
        write_raw(root / "codec/IMG.raw", low_codec)
        write_raw(root / "clean/IMG.raw", low_clean)

        compare = root / "compare.json"
        compare.write_text(
            json.dumps(
                {
                    "target_raw": str(target_raw),
                    "sr_raw": str(sr_raw),
                    "high_width": 16,
                    "high_height": 16,
                    "low_width": 8,
                    "low_height": 8,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        sensitivity = root / "sensitivity.json"
        sensitivity.write_text(
            json.dumps(
                {
                    "schema": "gpr.mission1_sr_codec_sensitivity.v1",
                    "rows": [
                        {
                            "image": "IMG",
                            "gate_pressure": 2.5,
                            "worst_hf_plane": "r",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        out = root / "manifest.json"
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--compare-json",
                str(compare),
                "--out",
                str(out),
                "--low-tile",
                "2",
                "--stride",
                "2",
                "--top-k-per-image",
                "3",
                "--min-spacing",
                "1",
                "--codec-low-dir",
                str(root / "codec"),
                "--clean-low-dir",
                str(root / "clean"),
                "--codec-sensitivity",
                str(sensitivity),
                "--gate-pressure-weight",
                "0.25",
                "--codec-score-weight",
                "0.5",
            ],
            cwd=ROOT,
            check=True,
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema"] == "mission1_sr_hard_tile_manifest.v1"
        assert payload["tile_count"] == 3
        assert payload["codec_score_weight"] == 0.5
        first = payload["tiles"][0]
        assert first["score_mode"] == "gate_pressure_weighted_detail_error_plus_codec_residual"
        assert first["score_components"]["gate_pressure"] == 2.5
        assert first["score_components"]["codec_focus_plane"] == 0.0
        assert first["score_components"]["codec_score"] > 0.0

    print("test_mine_mission1_sr_hard_tiles: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
