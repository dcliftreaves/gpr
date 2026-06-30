#!/usr/bin/env python3
"""Regression test for the premium still-SR raw-CFA residual trainer."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/train_premium_still_sr_raw_cfa_residual.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("raw_cfa_residual_train_tool", TOOL)
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
        print(f"test_train_premium_still_sr_raw_cfa_residual: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_raw_cfa_residual_train_", dir=tmp_parent) as td:
        root = Path(td)
        sidecar = root / "noise_sidecar.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"white_level": 65535.0, "black_level": 4096.0},
                    "calibrations": [
                        {
                            "iso": 800,
                            "per_plane": {
                                "r": {"sigma_black": 16.0, "temporal_noise_p95_counts": 24.0, "spatial_fpn_rms_counts": 2.0},
                                "g1": {"sigma_black": 18.0, "temporal_noise_p95_counts": 26.0, "spatial_fpn_rms_counts": 3.0},
                                "g2": {"sigma_black": 17.0, "temporal_noise_p95_counts": 25.0, "spatial_fpn_rms_counts": 3.0},
                                "b": {"sigma_black": 19.0, "temporal_noise_p95_counts": 28.0, "spatial_fpn_rms_counts": 2.0},
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        y, x = np.indices((40, 40))
        raws = []
        residuals = []
        raw_hf = []
        source_hf = []
        render_y = []
        rows = []
        for i, ev in enumerate([-2.0, 0.0, 2.0, 0.0]):
            raw = np.zeros((40, 40, 4), dtype=np.float32)
            raw[:, :, 0] = (x + i) / 64.0
            raw[:, :, 1] = (y + i) / 64.0
            raw[:, :, 2] = (x + y + i) / 96.0
            raw[:, :, 3] = ((x * 2 + y + i) % 11) / 11.0
            residual = (raw - raw.mean(axis=(0, 1), keepdims=True)) * 0.025
            raws.append(raw.astype(np.float16))
            residuals.append(residual.astype(np.float16))
            raw_hf.append((raw - raw.mean(axis=(0, 1), keepdims=True)).astype(np.float16))
            source_hf.append((raw_hf[-1].astype(np.float32) + residual).astype(np.float16))
            render_y.append(residual.mean(axis=2).astype(np.float16))
            rows.append(
                {
                    "scene_id": "holdout_scene" if i == 3 else "train_scene",
                    "crop": f"row_{i}",
                    "ev": ev,
                    "crop_xy": [0, 0],
                    "crop_size": 40,
                    "source_dng": f"/fixtures/{'x2d' if i == 3 else 'z8'}/frame_{i}.dng",
                    "noise_sidecars": [str(sidecar)],
                }
            )

        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            candidate_raw_cfa4=np.stack(raws),
            candidate_raw_hf_cfa4=np.stack(raw_hf),
            raw_hf_residual_cfa4=np.stack(residuals),
            source_raw_hf_cfa4=np.stack(source_hf),
            render_hf_residual_y=np.stack(render_y),
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
                "patch_size": 20,
                "model_arch": "residual",
                "width": 8,
                "depth": 2,
                "residual_scale": 0.08,
                "feature_mode": "raw_multiscale_coord_ev_noise",
                "feature_block": 5,
                "lr": 1.0e-3,
                "weight_decay": 0.0,
                "grad_weight": 0.0,
                "target_abs_weight": 0.5,
                "band_weight": 0.0,
                "band_blocks": [5, 9],
                "target_policy": "raw",
                "noise_threshold_scale": 1.0,
                "grad_clip": 1.0,
                "holdout_scene": "holdout_scene",
                "holdout_camera": None,
                "holdout_ev": None,
                "train_camera": "z8",
                "sample_balance": "row",
                "context_padding": 0,
                "eval_every": 0,
                "eval_tile": 40,
                "panel_rows": 2,
                "seed": 7,
                "device": "cpu",
            },
        )()
        receipt = tool.train(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["policy"]["uses_source_raw_at_training"] is True
        assert Path(receipt["checkpoint"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["dashboard"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["panel_sheet"]).stat().st_size > 0
        assert receipt["eval"]["train"]["row_count"] == 3
        assert receipt["eval"]["holdout"]["row_count"] == 1
        assert receipt["config"]["model_arch"] == "residual"
        assert receipt["config"]["feature_mode"] == "raw_multiscale_coord_ev_noise"
        assert receipt["config"]["holdout_scene"] == "holdout_scene"
        assert receipt["config"]["train_camera"] == "z8"
        assert receipt["config"]["target_policy"] == "raw"
        assert receipt["config"]["band_weight"] == 0.0
        assert receipt["config"]["band_blocks"] == [5, 9]
        assert receipt["config"]["sample_balance"] == "row"
        assert receipt["config"]["context_padding"] == 0
        assert "exact_raw_mae_reduction_pct" in receipt["eval"]["holdout"]

        args.output_dir = root / "camera_holdout"
        args.holdout_scene = None
        args.holdout_camera = "x2d"
        args.feature_mode = "raw_multiscale_storedhf_coord_ev_noise"
        args.target_policy = "noise_soft_threshold"
        args.noise_threshold_scale = 0.5
        camera_receipt = tool.train(args)
        assert camera_receipt["eval"]["holdout"]["row_count"] == 1
        assert camera_receipt["config"]["holdout_camera"] == "x2d"
        assert camera_receipt["config"]["train_camera"] == "z8"
        assert camera_receipt["config"]["feature_mode"] == "raw_multiscale_storedhf_coord_ev_noise"
        assert camera_receipt["config"]["target_policy"] == "noise_soft_threshold"
        assert camera_receipt["policy"]["target_policy"] == "noise_soft_threshold"

        args.output_dir = root / "context_holdout"
        args.holdout_scene = "holdout_scene"
        args.holdout_camera = None
        args.feature_mode = "raw_context_coord_ev_noise"
        args.target_policy = "raw"
        context_receipt = tool.train(args)
        assert context_receipt["eval"]["holdout"]["row_count"] == 1
        assert context_receipt["config"]["feature_mode"] == "raw_context_coord_ev_noise"
        assert context_receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert "pooled candidate raw/HF context planes" in context_receipt["policy"]["runtime_inputs"]

        args.output_dir = root / "context_storedhf_holdout"
        args.feature_mode = "raw_context_storedhf_coord_ev_noise"
        context_hf_receipt = tool.train(args)
        assert context_hf_receipt["eval"]["holdout"]["row_count"] == 1
        assert context_hf_receipt["config"]["feature_mode"] == "raw_context_storedhf_coord_ev_noise"
        assert context_hf_receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert "stored candidate_raw_hf_cfa4" in context_hf_receipt["policy"]["runtime_inputs"]
        assert "pooled candidate raw/HF/stored-HF context planes" in context_hf_receipt["policy"]["runtime_inputs"]

        args.output_dir = root / "band_loss_holdout"
        args.feature_mode = "raw_multiscale_coord_ev_noise"
        args.band_weight = 0.25
        args.band_blocks = [4, 9]
        band_receipt = tool.train(args)
        assert band_receipt["eval"]["holdout"]["row_count"] == 1
        assert band_receipt["config"]["band_weight"] == 0.25
        assert band_receipt["config"]["band_blocks"] == [5, 9]
        assert band_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "camera_balanced_holdout"
        args.feature_mode = "raw_multiscale_coord_ev_noise"
        args.band_weight = 0.0
        args.band_blocks = [5, 9]
        args.sample_balance = "camera"
        camera_balanced_receipt = tool.train(args)
        assert camera_balanced_receipt["eval"]["holdout"]["row_count"] == 1
        assert camera_balanced_receipt["config"]["sample_balance"] == "camera"
        assert camera_balanced_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "context_padded_holdout"
        args.sample_balance = "row"
        args.context_padding = 3
        args.patch_size = 18
        args.eval_tile = 17
        context_padded_receipt = tool.train(args)
        assert context_padded_receipt["eval"]["holdout"]["row_count"] == 1
        assert context_padded_receipt["config"]["context_padding"] == 3
        assert context_padded_receipt["eval"]["holdout"]["context_padding"] == 3
        assert context_padded_receipt["policy"]["model_context_padding_pixels"] == 3
        assert context_padded_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "unet_holdout"
        args.model_arch = "unet"
        args.context_padding = 0
        args.patch_size = 20
        args.eval_tile = 19
        unet_receipt = tool.train(args)
        assert unet_receipt["eval"]["holdout"]["row_count"] == 1
        assert unet_receipt["config"]["model_arch"] == "unet"
        assert unet_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "frame_context_holdout"
        args.model_arch = "residual"
        args.feature_mode = "raw_framectx_coord_ev_noise"
        args.context_padding = 0
        args.patch_size = 20
        args.eval_tile = 19
        frame_context_receipt = tool.train(args)
        assert frame_context_receipt["eval"]["holdout"]["row_count"] == 1
        assert frame_context_receipt["config"]["feature_mode"] == "raw_framectx_coord_ev_noise"
        assert "absolute crop position" in frame_context_receipt["policy"]["runtime_inputs"]
        assert frame_context_receipt["policy"]["uses_source_raw_at_runtime"] is False

        bad_npz = root / "bad_targets.npz"
        np.savez_compressed(
            bad_npz,
            candidate_raw_cfa4=np.stack(raws),
            raw_hf_residual_cfa4=np.stack(residuals)[..., :3],
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args.targets = bad_npz
        args.output_dir = root / "bad_out"
        args.feature_mode = "raw_multiscale_coord_ev_noise"
        args.target_policy = "raw"
        try:
            tool.train(args)
        except ValueError as exc:
            assert "candidate/target shape mismatch" in str(exc)
        else:
            raise AssertionError("trainer accepted mismatched target shape")

    print("test_train_premium_still_sr_raw_cfa_residual: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
