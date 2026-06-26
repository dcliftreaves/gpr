#!/usr/bin/env python3
"""Tests for direct raw-dir Mission 1 SR pair generation."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    print("test_build_mission1_sr_pairs_from_raw_dirs: SKIP missing numpy")
    raise SystemExit(0)


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "cnn" / "build_mission1_sr_pairs_from_raw_dirs.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("build_mission1_sr_pairs_from_raw_dirs", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_raw(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.astype("<u2", copy=False).tofile(path)


def test_manifest_tile_maps_low_to_2x_high_planes() -> None:
    tool = load_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_raw_dir_pairs_", dir=work_parent) as td:
        root = Path(td)
        low = np.arange(8 * 8, dtype=np.uint16).reshape(8, 8)
        high = np.arange(16 * 16, dtype=np.uint16).reshape(16, 16)
        write_raw(root / "low" / "A.raw", low)
        write_raw(root / "high" / "A.raw", high)
        manifest = {
            "schema": "mission1_sr_hard_tile_manifest.v1",
            "tiles": [
                {
                    "image_id": "A",
                    "low_x": 1,
                    "low_y": 1,
                    "low_tile": 2,
                    "score": 7.0,
                }
            ],
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        out = root / "pairs.npz"

        old_argv = __import__("sys").argv
        try:
            __import__("sys").argv = [
                str(TOOL),
                "--low-dir",
                str(root / "low"),
                "--target-dir",
                str(root / "high"),
                "--out",
                str(out),
                "--low-width",
                "8",
                "--low-height",
                "8",
                "--high-width",
                "16",
                "--high-height",
                "16",
                "--low-tile",
                "2",
                "--tile-manifest",
                str(manifest_path),
                "--manifest-only",
            ]
            assert tool.main() == 0
        finally:
            __import__("sys").argv = old_argv

        z = np.load(out, allow_pickle=False)
        inputs = z["inputs"]
        targets = z["targets"]
        meta = json.loads(str(z["meta"]))

    low_planes = tool.deinterleave(low)
    high_planes = tool.deinterleave(high)
    np.testing.assert_array_equal(inputs[0], low_planes[:, 1:3, 1:3])
    np.testing.assert_array_equal(targets[0], high_planes[:, 2:6, 2:6])
    assert meta["schema"] == "mission1_sr_pairs_from_raw_dirs.v1"
    assert meta["tiles"][0]["score"] == 7.0


if __name__ == "__main__":
    test_manifest_tile_maps_low_to_2x_high_planes()
    print("test_build_mission1_sr_pairs_from_raw_dirs: PASS")
