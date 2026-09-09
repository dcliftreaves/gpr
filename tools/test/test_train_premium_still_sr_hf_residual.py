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
        sidecar = root / "noise_sidecar.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"white_level": 65535.0, "black_level": 4096.0},
                    "calibrations": [
                        {
                            "iso": 3200,
                            "per_plane": {
                                "r": {"sigma_black": 30.0, "temporal_noise_p95_counts": 55.0, "spatial_fpn_rms_counts": 4.0},
                                "g1": {"sigma_black": 45.0, "temporal_noise_p95_counts": 80.0, "spatial_fpn_rms_counts": 6.0},
                                "g2": {"sigma_black": 46.0, "temporal_noise_p95_counts": 82.0, "spatial_fpn_rms_counts": 6.0},
                                "b": {"sigma_black": 32.0, "temporal_noise_p95_counts": 58.0, "spatial_fpn_rms_counts": 5.0},
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        y, x = np.indices((48, 48))
        inputs = []
        residuals = []
        source_hf = []
        raw_cfa = []
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
            raw_planes = np.zeros((48, 48, 4), dtype=np.float32)
            raw_planes[:, :, 0] = base[:, :, 0]
            raw_planes[:, :, 1] = base[:, :, 1]
            raw_planes[:, :, 2] = base[:, :, 1] * 0.9
            raw_planes[:, :, 3] = base[:, :, 2]
            raw_cfa.append(raw_planes.astype(np.float16))
            rows.append(
                {
                    "scene_id": "holdout_scene" if i == 3 else "train_scene",
                    "crop": f"row_{i}",
                    "ev": ev,
                    "crop_xy": [0, 0],
                    "crop_size": 48,
                    "noise_sidecars": [str(sidecar)],
                }
            )
        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            inputs=np.stack(inputs),
            hf_residuals=np.stack(residuals),
            source_hf_targets=np.stack(source_hf),
            candidate_raw_cfa4=np.stack(raw_cfa),
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
                "model_arch": "raw_cfa_gated",
                "feature_mode": "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright",
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
        assert receipt["config"]["model_arch"] == "raw_cfa_gated"
        assert receipt["config"]["holdout_scene"] == "holdout_scene"
        assert receipt["config"]["uses_noise_sidecar_features"] is True
        assert receipt["config"]["uses_raw_cfa_features"] is True

        args.output_dir = root / "dilated_out"
        args.model_arch = "raw_cfa_dilated_gated"
        args.feature_mode = "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright"
        dilated_receipt = tool.train(args)
        assert dilated_receipt["config"]["model_arch"] == "raw_cfa_dilated_gated"
        assert Path(dilated_receipt["checkpoint"]).stat().st_size > Path(receipt["checkpoint"]).stat().st_size
        assert dilated_receipt["policy"]["uses_source_hf_at_runtime"] is False

        args.output_dir = root / "bad_out"
        args.model_arch = "raw_cfa_gated"
        args.feature_mode = "rgb_multiscale_rawcfa_coord_luma_ev_noise_bright"
        try:
            tool.train(args)
        except ValueError as exc:
            assert "requires a phase raw-CFA feature mode" in str(exc)
        else:
            raise AssertionError("raw_cfa_gated accepted incompatible feature mode")

    print("test_train_premium_still_sr_hf_residual: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
