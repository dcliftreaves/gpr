#!/usr/bin/env python3
"""Regression test for Mission 1 SR codec-sensitivity analyzer."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/analyze_mission1_sr_codec_sensitivity.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("analyze_mission1_sr_codec_sensitivity", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_codec_sensitivity_", dir=work_parent) as td:
        root = Path(td)
        codec_dir = root / "codec"
        clean_dir = root / "clean"
        out_dir = root / "out"
        codec_dir.mkdir()
        clean_dir.mkdir()

        clean = np.arange(16, dtype=np.uint16).reshape(4, 4) + 100
        codec = clean.copy()
        codec[0::2, 0::2] += 4
        codec[1::2, 1::2] += 2
        clean.tofile(clean_dir / "IMG.raw")
        codec.tofile(codec_dir / "IMG.raw")

        sr_summary = root / "sr_summary.json"
        sr_summary.write_text(
            json.dumps(
                {
                    "schema": "mission1_sr_fullframe_broad_eval.v1",
                    "images": [
                        {
                            "image": "IMG",
                            "rmse_improvement_pct": 29.0,
                            "mae_improvement_pct": 21.0,
                            "gradient_mae_improvement_pct": 7.5,
                            "model_psnr14_db": 55.0,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--codec-low-dir",
                str(codec_dir),
                "--clean-low-dir",
                str(clean_dir),
                "--sr-summary",
                str(sr_summary),
                "--out-dir",
                str(out_dir),
                "--width",
                "4",
                "--height",
                "4",
            ],
            cwd=ROOT,
            check=True,
        )

        payload = json.loads((out_dir / "mission1_sr_codec_sensitivity.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.mission1_sr_codec_sensitivity.v1"
        assert payload["dimensions"] == {"width": 4, "height": 4}
        row = payload["rows"][0]
        assert row["image"] == "IMG"
        assert row["gate_pass"] is False
        assert abs(row["gate_pressure"] - 1.5) < 1e-6
        assert row["cfa_planes"]["r"]["mae_counts"] == 4.0
        assert row["cfa_planes"]["b"]["mae_counts"] == 2.0
        assert row["cfa_planes"]["g1"]["mae_counts"] == 0.0
        assert row["worst_hf_plane"] in {"r", "b"}
        assert (out_dir / "index.html").exists()

        tool = import_tool()
        assert tool.gradient_mae(clean, clean) == 0.0

    print("test_analyze_mission1_sr_codec_sensitivity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
