#!/usr/bin/env python3
"""Regression test for the premium still-SR HF residual trainer."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/train_premium_still_sr_hf_residual.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("hf_residual_train_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
        import PIL  # noqa: F401
        import torch  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_train_premium_still_sr_hf_residual: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_hf_residual_train_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((48, 48))
        inputs = []
        residuals = []
        source_hf = []
        rows = []
        for i, ev in enumerate([-2.0, 0.0, 2.0, 0.0]):
            base = np.zeros((48, 48, 3), dtype=np.float32)
            base[:, :, 0] = (x + i) / 64.0
            base[:, :, 1] = (y + i) / 64.0
            base[:, :, 2] = ((x + y + i) % 9) / 9.0
            residual = (base - base.mean(axis=(0, 1), keepdims=True)) * 0.035
            inputs.append(base.astype(np.float16))
            residuals.append(residual.astype(np.float16))
            source_hf.append((residual * 1.5).astype(np.float16))
            rows.append(
                {
                    "scene_id": "holdout_scene" if i == 3 else "train_scene",
                    "crop": f"row_{i}",
                    "ev": ev,
                    "crop_xy": [0, 0],
                    "crop_size": 48,
                }
            )
        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            inputs=np.stack(inputs),
            hf_residuals=np.stack(residuals),
            source_hf_targets=np.stack(source_hf),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )

        args = type(
            "Args",
            (),
            {
                "targets": npz,
                "output_dir": root / "out",
                "checkpoint_name": "smoke.pt",
                "steps": 3,
                "batch_size": 2,
                "patch_size": 24,
                "width": 8,
                "depth": 3,
                "residual_scale": 0.08,
                "feature_mode": "rgb_hf_luma_ev_bright",
                "feature_block": 8,
                "lr": 1.0e-3,
                "weight_decay": 0.0,
                "grad_weight": 0.0,
                "target_abs_weight": 0.5,
                "bright_weight": 0.25,
                "near_clip_weight": 0.5,
                "holdout_ev": 2.0,
                "holdout_crop": None,
                "holdout_scene": "holdout_scene",
                "eval_every": 0,
                "eval_tile": 48,
                "panel_rows": 2,
                "seed": 7,
            },
        )()
        receipt = tool.train(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["policy"]["uses_source_hf_at_runtime"] is False
        assert Path(receipt["checkpoint"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["dashboard"]).stat().st_size > 0
        assert receipt["eval"]["train"]["row_count"] == 3
        assert receipt["eval"]["holdout"]["row_count"] == 1
        assert receipt["config"]["holdout_scene"] == "holdout_scene"

    print("test_train_premium_still_sr_hf_residual: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
