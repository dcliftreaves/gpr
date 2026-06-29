#!/usr/bin/env python3
"""Regression test for premium still-SR pair generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - dependency-light CI environments skip
    np = None


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_pairs.py"


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
    if np is None:
        print("test_build_premium_still_sr_pairs: SKIP missing numpy")
        return 0
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_pairs_", dir=temp_root()) as tmp:
        tmp_path = Path(tmp)
        raw = (np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 4096) + 512
        raw_path = tmp_path / "fixture.raw"
        raw.astype("<u2").tofile(raw_path)
        manifest = {
            "schema": "gpr.premium_still_sr_fixture_manifest.v1",
            "fixtures": [
                {
                    "label": "synthetic_50mp_raw",
                    "camera": "Synthetic",
                    "camera_key": "synthetic",
                    "class": "50mp",
                    "extension": "raw",
                    "premium_still_sr_eligible": True,
                    "source": {
                        "path": str(raw_path),
                        "exists": True,
                        "width": 64,
                        "height": 64,
                    },
                    "black_level": 512,
                    "white_level": 4607,
                    "noise_sidecars": [],
                }
            ],
        }
        manifest_path = tmp_path / "fixture_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        out = tmp_path / "pairs.npz"
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--fixture-manifest",
                str(manifest_path),
                "--out",
                str(out),
                "--work-dir",
                str(tmp_path / "work"),
                "--tiles-per-fixture",
                "3",
                "--low-plane-tile",
                "4",
            ],
            cwd=ROOT,
            check=True,
        )
        z = np.load(out, allow_pickle=False)
        inputs = z["inputs"]
        targets = z["targets"]
        meta = json.loads(str(z["meta"]))
        assert inputs.shape == (3, 4, 4, 4), inputs.shape
        assert targets.shape == (3, 4, 8, 8), targets.shape
        assert meta["schema"] == "gpr.premium_still_sr_pairs.v1"
        assert meta["low_tile"] == 4
        assert meta["high_tile"] == 8
        assert len(meta["images"]) == 1
        assert len(meta["tiles"]) == 3
        assert inputs.min() >= 0 and targets.max() <= 16383

    print("test_build_premium_still_sr_pairs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
