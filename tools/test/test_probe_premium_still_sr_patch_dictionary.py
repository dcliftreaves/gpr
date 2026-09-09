#!/usr/bin/env python3
"""Regression test for the premium still-SR patch dictionary probe."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/probe_premium_still_sr_patch_dictionary.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("patch_dictionary_probe", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
        import PIL  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_probe_premium_still_sr_patch_dictionary: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_patch_dictionary_probe_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((32, 32))
        raws = []
        hfs = []
        residuals = []
        rows = []
        for i in range(5):
            raw = np.zeros((32, 32, 4), dtype=np.float32)
            raw[:, :, 0] = (x + i) / 64.0
            raw[:, :, 1] = (y + i) / 64.0
            raw[:, :, 2] = ((x + y + i) % 17) / 17.0
            raw[:, :, 3] = ((2 * x + y + i) % 19) / 19.0
            hf = raw - raw.mean(axis=(0, 1), keepdims=True)
            residual = hf * 0.02
            raws.append(raw.astype(np.float16))
            hfs.append(hf.astype(np.float16))
            residuals.append(residual.astype(np.float16))
            rows.append(
                {
                    "scene_id": "holdout_scene" if i == 4 else f"train_scene_{i}",
                    "crop": f"row_{i}",
                    "ev": float((i % 3) - 1),
                    "source_dng": f"/fixtures/{'x2d' if i == 4 else 'z8'}/frame_{i}.dng",
                }
            )
        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            candidate_raw_cfa4=np.stack(raws),
            candidate_raw_hf_cfa4=np.stack(hfs),
            raw_hf_residual_cfa4=np.stack(residuals),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": npz,
                "output_dir": root / "out",
                "holdout_scene": "holdout_scene",
                "holdout_camera": None,
                "patch_size": 8,
                "holdout_stride": 8,
                "patches_per_train_row": 4,
                "max_dictionary_patches": 20,
                "neighbors": 2,
                "max_holdout_rows": None,
                "panel_rows": 1,
                "promotion_recovery_threshold": 15.0,
                "seed": 9,
            },
        )()
        receipt = tool.run(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["production_ready"] is False
        assert receipt["runtime_policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["dictionary"]["patch_count"] > 0
        assert receipt["eval"]["row_count"] == 1
        assert "raw_residual_mae_reduction_pct" in receipt["eval"]
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["dashboard"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["panel_sheet"]).stat().st_size > 0
        html = Path(receipt["artifacts"]["dashboard"]).read_text(encoding="utf-8")
        assert "Premium Still-SR Patch Dictionary Probe" in html
        assert "candidate-only runtime probe" in html

    print("test_probe_premium_still_sr_patch_dictionary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
