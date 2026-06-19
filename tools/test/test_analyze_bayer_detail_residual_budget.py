#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools/cnn/analyze_bayer_detail_residual_budget.py"


def test_budget_cli() -> None:
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(dir=tmp_parent) as td:
        root = Path(td)
        low = root / "low"
        clean_dir = root / "clean"
        low.mkdir()
        clean_dir.mkdir()
        codec = np.full((8, 8), 1000, dtype=np.uint16)
        clean = codec.copy()
        clean[0::4, 0::4] += 12
        codec.tofile(low / "A.raw")
        clean.tofile(clean_dir / "A.raw")
        sidecar = root / "pairs.json"
        sidecar.write_text(
            json.dumps(
                {
                    "width12": 8,
                    "height12": 8,
                    "images": [
                        {
                            "image_id": "A",
                            "low_source_raw": str(low / "A.raw"),
                            "low_clean_raw": str(clean_dir / "A.raw"),
                        }
                    ],
                }
            )
        )
        out_json = root / "budget.json"
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pair-sidecar",
                str(sidecar),
                "--out-json",
                str(out_json),
                "--planes",
                "r",
                "--quant-step",
                "2",
            ],
            check=True,
            cwd=REPO,
        )
        payload = json.loads(out_json.read_text())
        assert payload["schema"] == "gpr.bayer_detail_residual_budget.v1"
        assert payload["summary"]["image_count"] == 1
        assert payload["images"][0]["output_clean_rmse"] < payload["images"][0]["codec_clean_rmse"]
        assert payload["images"][0]["bitmap_values_zlib_bytes"] > 0


if __name__ == "__main__":
    test_budget_cli()
    print("test_analyze_bayer_detail_residual_budget: PASS")
