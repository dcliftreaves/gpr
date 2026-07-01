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
        cfa_phases = ["RGGB", "GBRG", "GRBG", "BGGR"]
        for i, ev in enumerate([-2.0, 0.0, 2.0, 0.0]):
            raw = np.zeros((40, 40, 4), dtype=np.float32)
            raw[:, :, 0] = (x + i) / 64.0
            raw[:, :, 1] = (y + i) / 64.0
            raw[:, :, 2] = (x + y + i) / 96.0
            raw[:, :, 3] = ((x * 2 + y + i) % 11) / 11.0
            residual = (raw - raw.mean(axis=(0, 1), keepdims=True)) * 0.025
            if i == 2:
                residual = residual * 0.01
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
                    "cfa_phase": cfa_phases[i],
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
                "psf_receipt": None,
                "psf_sidecar": None,
                "psf_kernel_weight": None,
                "feature_block": 5,
                "lr": 1.0e-3,
                "weight_decay": 0.0,
                "grad_weight": 0.0,
                "target_abs_weight": 0.5,
                "band_weight": 0.0,
                "band_blocks": [5, 9],
                "spectral_weight": 0.0,
                "target_policy": "raw",
                "noise_threshold_scale": 1.0,
                "grad_clip": 1.0,
                "holdout_scene": "holdout_scene",
                "holdout_camera": None,
                "holdout_ev": None,
                "train_camera": "z8",
                "train_snr_class": "all",
                "snr_loss_weight_policy": "none",
                "snr_loss_weight_strength": 1.0,
                "target_energy_loss_weight_policy": "none",
                "target_energy_loss_weight_strength": 1.0,
                "target_scale_policy": "none",
                "target_scale_strength": 1.0,
                "target_representation": "residual",
                "sample_balance": "row",
                "sample_mode": "random_patch",
                "context_padding": 0,
                "context_mask_prob": 0.0,
                "context_mask_block": 16,
                "eval_every": 0,
                "eval_tile": 40,
                "eval_overlap": 0,
                "seam_check_width": 0,
                "eval_train_rows": 0,
                "eval_holdout_rows": 0,
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
        progress_path = Path(receipt["artifacts"]["progress_jsonl"])
        assert progress_path.stat().st_size > 0
        progress_rows = [
            json.loads(line)
            for line in progress_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert progress_rows[0]["event"] == "start"
        assert any(row["event"] == "history" and row["step"] == 1 for row in progress_rows)
        assert progress_rows[-1]["event"] == "complete"
        assert receipt["history"][0]["elapsed_seconds"] >= 0.0
        assert receipt["history"][0]["seconds_per_step"] >= 0.0
        assert receipt["config"]["progress_jsonl"] == str(progress_path)
        assert receipt["eval"]["train"]["row_count"] == 3
        assert receipt["eval"]["holdout"]["row_count"] == 1
        assert receipt["config"]["model_arch"] == "residual"
        assert receipt["config"]["feature_mode"] == "raw_multiscale_coord_ev_noise"
        assert receipt["config"]["holdout_scene"] == "holdout_scene"
        assert receipt["config"]["train_camera"] == "z8"
        assert receipt["config"]["train_snr_class"] == "all"
        assert receipt["config"]["snr_loss_weight_policy"] == "none"
        assert receipt["config"]["snr_loss_weight_strength"] == 1.0
        assert receipt["config"]["train_snr_loss_weight_stats"]["median"] == 1.0
        assert receipt["config"]["target_energy_loss_weight_policy"] == "none"
        assert receipt["config"]["target_energy_loss_weight_strength"] == 1.0
        assert receipt["config"]["train_target_energy_loss_weight_stats"]["median"] == 1.0
        assert receipt["config"]["target_scale_policy"] == "none"
        assert receipt["config"]["target_scale_strength"] == 1.0
        assert receipt["config"]["train_target_scale_stats"]["median"] == 1.0
        assert receipt["config"]["psf_conditioning_enabled"] is False
        assert receipt["config"]["psf_kernel_weights"] == [0.25, 0.25, 0.25, 0.25]
        assert receipt["config"]["cfa_phase_conditioning_enabled"] is False
        assert receipt["config"]["cfa_phase_counts"] == {"BGGR": 1, "GBRG": 1, "GRBG": 1, "RGGB": 1, "unknown": 0}
        assert receipt["eval"]["holdout"]["rows"][0]["cfa_phase"] == "BGGR"
        assert receipt["config"]["target_representation"] == "residual"
        assert receipt["policy"]["target_energy_loss_weight_policy"] == "none"
        assert receipt["policy"]["target_scale_policy"] == "none"
        assert receipt["policy"]["target_representation"] == "residual"
        assert receipt["policy"]["snr_loss_weight_policy"] == "none"
        assert receipt["config"]["target_policy"] == "raw"
        assert receipt["config"]["band_weight"] == 0.0
        assert receipt["config"]["band_blocks"] == [5, 9]
        assert receipt["config"]["spectral_weight"] == 0.0
        assert receipt["config"]["sample_balance"] == "row"
        assert receipt["config"]["sample_mode"] == "random_patch"
        assert receipt["config"]["context_padding"] == 0
        assert receipt["config"]["eval_overlap"] == 0
        assert receipt["config"]["seam_check_width"] == 0
        assert receipt["policy"]["eval_overlap_contract"] == "disabled"
        assert receipt["config"]["context_mask_prob"] == 0.0
        assert receipt["policy"]["training_context_mask"] == "disabled"
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

        args.output_dir = root / "snr_filtered_holdout"
        args.target_policy = "raw"
        args.train_snr_class = "signal_dominated"
        snr_receipt = tool.train(args)
        assert snr_receipt["eval"]["holdout"]["row_count"] == 1
        assert snr_receipt["eval"]["train"]["row_count"] == 2
        assert snr_receipt["config"]["train_snr_class"] == "signal_dominated"
        assert snr_receipt["config"]["train_snr_class_counts"] == {"signal_dominated": 2}
        assert snr_receipt["config"]["holdout_snr_class_counts"] == {"signal_dominated": 1}
        assert snr_receipt["policy"]["train_snr_class_filter"] == "signal_dominated"
        args.train_snr_class = "all"

        args.output_dir = root / "snr_weighted_holdout"
        args.snr_loss_weight_policy = "signal_emphasis"
        weighted_receipt = tool.train(args)
        assert weighted_receipt["eval"]["holdout"]["row_count"] == 1
        assert weighted_receipt["config"]["snr_loss_weight_policy"] == "signal_emphasis"
        assert weighted_receipt["config"]["snr_loss_weight_strength"] == 1.0
        assert weighted_receipt["config"]["train_snr_loss_weight_stats"]["min"] < 1.0
        assert weighted_receipt["policy"]["snr_loss_weight_policy"] == "signal_emphasis"
        args.snr_loss_weight_policy = "none"

        args.output_dir = root / "target_energy_weighted_holdout"
        args.target_energy_loss_weight_policy = "high_energy_emphasis"
        energy_receipt = tool.train(args)
        assert energy_receipt["eval"]["holdout"]["row_count"] == 1
        assert energy_receipt["config"]["target_energy_loss_weight_policy"] == "high_energy_emphasis"
        assert energy_receipt["config"]["target_energy_loss_weight_strength"] == 1.0
        assert energy_receipt["config"]["train_target_energy_loss_weight_stats"]["max"] > 1.0
        assert energy_receipt["policy"]["target_energy_loss_weight_policy"] == "high_energy_emphasis"
        args.target_energy_loss_weight_policy = "none"

        args.output_dir = root / "target_scaled_holdout"
        args.target_scale_policy = "candidate_hf_abs_mean"
        scale_receipt = tool.train(args)
        assert scale_receipt["eval"]["holdout"]["row_count"] == 1
        assert scale_receipt["config"]["target_scale_policy"] == "candidate_hf_abs_mean"
        assert scale_receipt["config"]["target_scale_strength"] == 1.0
        assert scale_receipt["config"]["train_target_scale_stats"]["max"] > 1.0
        assert scale_receipt["config"]["holdout_target_scale_stats"]["median"] > 0.0
        assert scale_receipt["policy"]["target_scale_policy"] == "candidate_hf_abs_mean"
        assert "target_scale" in scale_receipt["eval"]["holdout"]["rows"][0]
        args.target_scale_policy = "none"

        args.output_dir = root / "source_hf_holdout"
        args.target_representation = "source_hf"
        args.target_policy = "raw"
        args.feature_mode = "raw_multiscale_storedhf_coord_ev_noise"
        source_hf_receipt = tool.train(args)
        assert source_hf_receipt["eval"]["holdout"]["row_count"] == 1
        assert source_hf_receipt["config"]["target_representation"] == "source_hf"
        assert source_hf_receipt["policy"]["target_representation"] == "source_hf"
        assert source_hf_receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert source_hf_receipt["eval"]["holdout"]["rows"][0]["target_representation"] == "source_hf"
        assert "stored candidate_raw_hf_cfa4" in source_hf_receipt["policy"]["runtime_inputs"]
        args.target_representation = "residual"

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

        args.output_dir = root / "spectral_loss_holdout"
        args.band_weight = 0.0
        args.band_blocks = [5, 9]
        args.spectral_weight = 0.3
        spectral_receipt = tool.train(args)
        assert spectral_receipt["eval"]["holdout"]["row_count"] == 1
        assert spectral_receipt["config"]["spectral_weight"] == 0.3
        assert spectral_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "camera_balanced_holdout"
        args.feature_mode = "raw_multiscale_coord_ev_noise"
        args.band_weight = 0.0
        args.band_blocks = [5, 9]
        args.spectral_weight = 0.0
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

        args.output_dir = root / "overlap_eval_holdout"
        args.eval_tile = 17
        args.eval_overlap = 8
        args.seam_check_width = 4
        overlap_receipt = tool.train(args)
        assert overlap_receipt["eval"]["holdout"]["row_count"] == 1
        assert overlap_receipt["config"]["eval_overlap"] == 8
        assert overlap_receipt["config"]["seam_check_width"] == 4
        assert "enabled: metrics use overlapped tile accumulation" in overlap_receipt["policy"]["eval_overlap_contract"]
        assert "overlap_vs_plain_mae" in overlap_receipt["eval"]["holdout"]
        assert "overlap_vs_plain_mae" in overlap_receipt["eval"]["holdout"]["rows"][0]
        assert "overlap_vs_plain_seam_mae" in overlap_receipt["eval"]["holdout"]["rows"][0]
        args.eval_overlap = 0
        args.seam_check_width = 0

        args.output_dir = root / "unet_holdout"
        args.model_arch = "unet"
        args.context_padding = 0
        args.patch_size = 20
        args.eval_tile = 19
        unet_receipt = tool.train(args)
        assert unet_receipt["eval"]["holdout"]["row_count"] == 1
        assert unet_receipt["config"]["model_arch"] == "unet"
        assert unet_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "rcab_teacher_holdout"
        args.model_arch = "rcab_teacher"
        args.feature_mode = "raw_multiscale_storedhf_coord_ev_noise"
        args.width = 8
        args.depth = 2
        args.batch_size = 1
        args.patch_size = 20
        args.sample_mode = "full_crop"
        args.eval_tile = 40
        args.band_weight = 0.1
        args.band_blocks = [5, 9]
        args.spectral_weight = 0.1
        rcab_receipt = tool.train(args)
        assert rcab_receipt["eval"]["holdout"]["row_count"] == 1
        assert rcab_receipt["config"]["model_arch"] == "rcab_teacher"
        assert rcab_receipt["config"]["feature_mode"] == "raw_multiscale_storedhf_coord_ev_noise"
        assert rcab_receipt["config"]["sample_mode"] == "full_crop"
        assert rcab_receipt["config"]["band_weight"] == 0.1
        assert rcab_receipt["config"]["spectral_weight"] == 0.1
        assert "stored candidate_raw_hf_cfa4" in rcab_receipt["policy"]["runtime_inputs"]
        assert rcab_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "naf_teacher_holdout"
        args.model_arch = "naf_teacher"
        args.feature_mode = "raw_multiscale_storedhf_coord_ev_noise"
        args.width = 8
        args.depth = 2
        args.batch_size = 1
        args.patch_size = 20
        args.sample_mode = "full_crop"
        args.eval_tile = 40
        args.band_weight = 0.1
        args.band_blocks = [5, 9]
        args.spectral_weight = 0.1
        naf_receipt = tool.train(args)
        assert naf_receipt["eval"]["holdout"]["row_count"] == 1
        assert naf_receipt["config"]["model_arch"] == "naf_teacher"
        assert naf_receipt["config"]["feature_mode"] == "raw_multiscale_storedhf_coord_ev_noise"
        assert naf_receipt["config"]["sample_mode"] == "full_crop"
        assert naf_receipt["config"]["band_weight"] == 0.1
        assert naf_receipt["config"]["spectral_weight"] == 0.1
        assert "stored candidate_raw_hf_cfa4" in naf_receipt["policy"]["runtime_inputs"]
        assert naf_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "window_attention_teacher_holdout"
        args.model_arch = "window_attention_teacher"
        args.feature_mode = "raw_multiscale_storedhf_coord_ev_noise"
        args.width = 8
        args.depth = 2
        args.batch_size = 1
        args.patch_size = 20
        args.sample_mode = "full_crop"
        args.eval_tile = 40
        args.band_weight = 0.1
        args.band_blocks = [5, 9]
        args.spectral_weight = 0.1
        window_receipt = tool.train(args)
        assert window_receipt["eval"]["holdout"]["row_count"] == 1
        assert window_receipt["config"]["model_arch"] == "window_attention_teacher"
        assert window_receipt["config"]["feature_mode"] == "raw_multiscale_storedhf_coord_ev_noise"
        assert window_receipt["config"]["sample_mode"] == "full_crop"
        assert window_receipt["config"]["band_weight"] == 0.1
        assert window_receipt["config"]["spectral_weight"] == 0.1
        assert "stored candidate_raw_hf_cfa4" in window_receipt["policy"]["runtime_inputs"]
        assert window_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "restormer_teacher_holdout"
        args.model_arch = "restormer_teacher"
        args.feature_mode = "raw_multiscale_storedhf_coord_ev_noise"
        args.width = 8
        args.depth = 2
        args.batch_size = 1
        args.patch_size = 20
        args.sample_mode = "full_crop"
        args.eval_tile = 40
        args.band_weight = 0.1
        args.band_blocks = [5, 9]
        args.spectral_weight = 0.1
        restormer_receipt = tool.train(args)
        assert restormer_receipt["eval"]["holdout"]["row_count"] == 1
        assert restormer_receipt["config"]["model_arch"] == "restormer_teacher"
        assert restormer_receipt["config"]["feature_mode"] == "raw_multiscale_storedhf_coord_ev_noise"
        assert restormer_receipt["config"]["sample_mode"] == "full_crop"
        assert restormer_receipt["config"]["band_weight"] == 0.1
        assert restormer_receipt["config"]["spectral_weight"] == 0.1
        assert "stored candidate_raw_hf_cfa4" in restormer_receipt["policy"]["runtime_inputs"]
        assert restormer_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "pyramid_unet_holdout"
        args.model_arch = "pyramid_unet"
        args.feature_mode = "raw_context_coord_ev_noise"
        args.band_weight = 0.0
        args.spectral_weight = 0.0
        args.width = 8
        args.depth = 2
        args.context_padding = 0
        args.patch_size = 20
        args.eval_tile = 19
        pyramid_receipt = tool.train(args)
        assert pyramid_receipt["eval"]["holdout"]["row_count"] == 1
        assert pyramid_receipt["config"]["model_arch"] == "pyramid_unet"
        assert pyramid_receipt["config"]["feature_mode"] == "raw_context_coord_ev_noise"
        assert "pooled candidate raw/HF context planes" in pyramid_receipt["policy"]["runtime_inputs"]
        assert pyramid_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "global_context_unet_holdout"
        args.model_arch = "global_context_unet"
        args.feature_mode = "raw_multiscale_coord_ev_noise"
        args.sample_mode = "full_crop"
        args.context_mask_prob = 0.25
        args.context_mask_block = 8
        args.batch_size = 1
        args.patch_size = 20
        args.eval_tile = 40
        args.eval_train_rows = 2
        global_receipt = tool.train(args)
        assert global_receipt["eval"]["holdout"]["row_count"] == 1
        assert global_receipt["eval"]["train"]["row_count"] == 2
        assert global_receipt["config"]["model_arch"] == "global_context_unet"
        assert global_receipt["config"]["sample_mode"] == "full_crop"
        assert global_receipt["config"]["context_mask_prob"] == 0.25
        assert global_receipt["config"]["context_mask_block"] == 8
        assert "training-only random candidate detail mask" in global_receipt["policy"]["training_context_mask"]
        assert global_receipt["config"]["eval_train_rows"] == 2
        assert "diagnostic bounded evaluation" in global_receipt["policy"]["eval_contract"]
        assert global_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "frame_context_holdout"
        args.model_arch = "residual"
        args.feature_mode = "raw_framectx_coord_ev_noise"
        args.sample_mode = "random_patch"
        args.context_mask_prob = 0.0
        args.context_mask_block = 16
        args.batch_size = 2
        args.context_padding = 0
        args.patch_size = 20
        args.eval_tile = 19
        args.eval_train_rows = 0
        frame_context_receipt = tool.train(args)
        assert frame_context_receipt["eval"]["holdout"]["row_count"] == 1
        assert frame_context_receipt["config"]["feature_mode"] == "raw_framectx_coord_ev_noise"
        assert "absolute crop position" in frame_context_receipt["policy"]["runtime_inputs"]
        assert frame_context_receipt["policy"]["uses_source_raw_at_runtime"] is False

        args.output_dir = root / "psf_conditioned_holdout"
        args.model_arch = "global_context_unet"
        args.feature_mode = "raw_context_coord_ev_noise_psf"
        args.psf_kernel_weight = [0.52, 0.23, 0.17, 0.08]
        args.sample_mode = "full_crop"
        args.batch_size = 1
        args.patch_size = 20
        args.eval_tile = 40
        psf_receipt = tool.train(args)
        assert psf_receipt["eval"]["holdout"]["row_count"] == 1
        assert psf_receipt["config"]["feature_mode"] == "raw_context_coord_ev_noise_psf"
        assert psf_receipt["config"]["psf_conditioning_enabled"] is True
        assert psf_receipt["config"]["psf_kernel_weights"] == [0.52, 0.23, 0.17, 0.08]
        assert "PSF/kernel scalar conditioning" in psf_receipt["policy"]["runtime_inputs"]
        assert psf_receipt["policy"]["psf_conditioning"].startswith("enabled")
        assert psf_receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert psf_receipt["eval"]["holdout"]["rows"][0]["psf_kernel_weights"] == [0.52, 0.23, 0.17, 0.08]
        assert psf_receipt["eval"]["holdout"]["rows"][0]["psf_source"] == "default"
        args.psf_kernel_weight = None

        psf_sidecar = root / "psf_sidecar.json"
        sidecar_rows = []
        for idx, row in enumerate(rows):
            weights = [0.4, 0.3, 0.2, 0.1] if idx != 3 else [0.11, 0.22, 0.33, 0.34]
            sidecar_rows.append(
                {
                    "target_row_index": idx,
                    "row_key": tool.target_row_key(row, idx),
                    "scene": row["scene_id"],
                    "crop": row["crop"],
                    "camera": "x2d" if idx == 3 else "z8",
                    "assignment_policy": "camera_specific",
                    "psf_kernel_weights": weights,
                    "psf_receipt_path": f"/fixtures/psf_{idx}.json",
                    "psf_receipt_sha256": "0" * 64,
                }
            )
        psf_sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_psf_sidecar.v1",
                    "created_unix": 1,
                    "targets": str(npz),
                    "targets_sha256": tool.sha256_file(npz),
                    "row_key_algorithm": "sha256(index, scene_id, crop, crop_xy, candidate_raw, source_raw, ev)",
                    "rows": sidecar_rows,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        args.output_dir = root / "psf_sidecar_holdout"
        args.model_arch = "global_context_unet"
        args.feature_mode = "raw_context_coord_ev_noise_psf"
        args.psf_sidecar = psf_sidecar
        args.psf_kernel_weight = [0.25, 0.25, 0.25, 0.25]
        sidecar_receipt = tool.train(args)
        assert sidecar_receipt["eval"]["holdout"]["row_count"] == 1
        assert sidecar_receipt["config"]["psf_sidecar"] == str(psf_sidecar)
        assert sidecar_receipt["config"]["psf_sidecar_stats"]["matched_rows"] == 4
        assert sidecar_receipt["config"]["psf_sidecar_stats"]["default_rows"] == 0
        assert sidecar_receipt["config"]["psf_sidecar_stats"]["unique_kernel_count"] == 2
        assert sidecar_receipt["eval"]["holdout"]["rows"][0]["psf_kernel_weights"] == [0.11, 0.22, 0.33, 0.34]
        assert sidecar_receipt["eval"]["holdout"]["rows"][0]["psf_source"] == "psf_sidecar"
        args.psf_sidecar = None
        args.psf_kernel_weight = None

        args.output_dir = root / "cfa_phase_holdout"
        args.model_arch = "residual"
        args.feature_mode = "raw_multiscale_coord_ev_noise_cfa"
        cfa_receipt = tool.train(args)
        assert cfa_receipt["eval"]["holdout"]["row_count"] == 1
        assert cfa_receipt["config"]["feature_mode"] == "raw_multiscale_coord_ev_noise_cfa"
        assert cfa_receipt["config"]["cfa_phase_conditioning_enabled"] is True
        assert cfa_receipt["config"]["cfa_phase_counts"]["RGGB"] == 1
        assert cfa_receipt["config"]["cfa_phase_counts"]["BGGR"] == 1
        assert cfa_receipt["eval"]["holdout"]["rows"][0]["cfa_phase"] == "BGGR"
        assert "CFA phase one-hot metadata" in cfa_receipt["policy"]["runtime_inputs"]

        args.output_dir = root / "full_crop_holdout"
        args.model_arch = "unet"
        args.feature_mode = "raw_multiscale_coord_ev_noise"
        args.sample_mode = "full_crop"
        args.batch_size = 1
        args.patch_size = 8
        args.eval_tile = 40
        full_crop_receipt = tool.train(args)
        assert full_crop_receipt["eval"]["holdout"]["row_count"] == 1
        assert full_crop_receipt["config"]["sample_mode"] == "full_crop"
        assert full_crop_receipt["config"]["patch_size"] == 8
        assert full_crop_receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert "full target crops" in full_crop_receipt["policy"]["sample_contract"]

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
