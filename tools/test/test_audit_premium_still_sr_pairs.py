#!/usr/bin/env python3
"""Regression test for premium still-SR pair audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_pairs.py"


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
        print("test_audit_premium_still_sr_pairs: SKIP missing numpy")
        return 0
    with tempfile.TemporaryDirectory(prefix="gpr_pair_audit_", dir=temp_root()) as tmp:
        td = Path(tmp)
        inputs = np.array(
            [
                [
                    [[10, 20], [30, 40]],
                    [[11, 21], [31, 41]],
                    [[12, 22], [32, 42]],
                    [[13, 23], [33, 43]],
                ]
            ],
            dtype=np.uint16,
        )
        base = np.repeat(np.repeat(inputs, 2, axis=2), 2, axis=3)
        targets = (base + 2).astype(np.uint16)
        meta = {
            "schema": "gpr.premium_still_sr_pairs.v1",
            "dataset_label": "synthetic",
            "fixture_manifest": "/tmp/manifest.json",
            "fixture_manifest_sha256": "abc",
            "low_tile": 2,
            "high_tile": 4,
            "tiles_per_fixture": 1,
            "include_gpr": False,
            "images": [
                {
                    "image_id": "synthetic_x2d",
                    "camera_key": "x2d",
                    "class": "100mp",
                    "source": {"path": "/tmp/source.dng"},
                }
            ],
            "tiles": [{"image_id": "synthetic_x2d"}],
        }
        pairs = td / "pairs.npz"
        np.savez_compressed(pairs, inputs=inputs, targets=targets, meta=json.dumps(meta, sort_keys=True))
        out = td / "audit"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--pairs", str(pairs), "--output-dir", str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads((out / "pair_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_pair_audit.v1"
        assert data["pair_meta"]["tile_count"] == 1
        assert data["pair_meta"]["input_shape"] == [1, 4, 2, 2]
        assert data["pair_meta"]["target_shape"] == [1, 4, 4, 4]
        assert data["baseline"]["name"] == "nearest_same_color_2x"
        assert data["baseline"]["mae"]["median"] == 2.0
        assert data["baseline"]["rmse"]["median"] == 2.0
        assert data["by_camera"]["x2d"]["tile_count"] == 1
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Pair Audit" in html
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_audit_premium_still_sr_pairs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
