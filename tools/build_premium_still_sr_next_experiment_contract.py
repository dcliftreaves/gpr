#!/usr/bin/env python3
"""Build the next-experiment contract for premium still-SR.

This is not a training script. It consumes the current dataset inventory,
experiment scoreboard, raw-CFA residual gap audit, and production capture
requirements, then writes the narrow contract for the next model pass. The
purpose is to keep premium still-SR work pointed at the canonical raw-CFA
targets and away from already-rejected local/context/noise/sampling-only probes.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.premium_still_sr_next_experiment_contract.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
RESEARCH_BASIS = [
    {
        "id": "ntire_2024_raw_sr",
        "title": "Deep RAW Image Super-Resolution. A NTIRE 2024 Challenge Survey",
        "url": "https://arxiv.org/abs/2404.16223",
        "repo_implication": (
            "Treat RAW SR as a hardware-specific Bayer restoration problem with "
            "unknown noise and blur, not as generic RGB sharpening."
        ),
    },
    {
        "id": "rbsformer_raw_sr",
        "title": "RBSFormer: Enhanced Transformer Network for Raw Image Super-Resolution",
        "url": "https://openaccess.thecvf.com/content/CVPR2024W/NTIRE/html/Jiang_RBSFormer_Enhanced_Transformer_Network_for_Raw_Image_Super-Resolution_CVPRW_2024_paper.html",
        "repo_implication": (
            "Use RAW-SR-specific transformer blocks and explicit degradation modeling "
            "as the teacher direction instead of treating the problem as ordinary RGB SR."
        ),
    },
    {
        "id": "ntire_2025_raw_restoration_sr",
        "title": "NTIRE 2025 Challenge on RAW Image Restoration and Super-Resolution",
        "url": "https://arxiv.org/abs/2506.02197",
        "repo_implication": (
            "Keep denoising, deblurring, and super-resolution coupled in the "
            "model/gate because portable-camera RAW degradations are mixed."
        ),
    },
    {
        "id": "jdndmsr",
        "title": "End-to-End Learning for Joint Image Demosaicing, Denoising and Super-Resolution",
        "url": "https://openaccess.thecvf.com/content/CVPR2021/papers/Xing_End-to-End_Learning_for_Joint_Image_Demosaicing_Denoising_and_Super-Resolution_CVPR_2021_paper.pdf",
        "repo_implication": (
            "Do not separate demosaic, denoise, and SR thinking too early; train the "
            "raw-CFA target as a coupled restoration problem, then verify editable raw output."
        ),
    },
    {
        "id": "rethinking_raw_noise",
        "title": "Rethinking Noise Synthesis and Modeling in Raw Denoising",
        "url": "https://openaccess.thecvf.com/content/ICCV2021/html/Zhang_Rethinking_Noise_Synthesis_and_Modeling_in_Raw_Denoising_ICCV_2021_paper.html",
        "repo_implication": (
            "Use sensor/ISO-specific darkframe or real-noise sidecars for noise "
            "conditioning/addback; do not learn a generic noise residual from "
            "single-image REF differences."
        ),
    },
    {
        "id": "bayer_unify_aug",
        "title": "Learning Raw Image Denoising with Bayer Pattern Unification and Bayer Preserving Augmentation",
        "url": "https://arxiv.org/abs/1904.12945",
        "repo_implication": (
            "Keep Bayer phase handling and augmentation sensor-pattern preserving; "
            "ordinary RGB flips/rotations can silently corrupt raw-CFA supervision."
        ),
    },
    {
        "id": "nafnet",
        "title": "Simple Baselines for Image Restoration",
        "url": "https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/3043_ECCV_2022_paper.php",
        "repo_implication": (
            "Use NAF-style restoration blocks as an efficient baseline, but gate "
            "against full-image behavior because patch-only evaluation can hide artifacts."
        ),
    },
    {
        "id": "swinir",
        "title": "SwinIR: Image Restoration Using Swin Transformer",
        "url": "https://arxiv.org/abs/2108.10257",
        "repo_implication": (
            "Use shifted-window attention plus residual groups as the first serious "
            "non-local detail prior for SR/denoise/compression restoration, rather "
            "than only widening local convolutional probes."
        ),
    },
    {
        "id": "restormer",
        "title": "Restormer: Efficient Transformer for High-Resolution Image Restoration",
        "url": "https://arxiv.org/abs/2111.09881",
        "repo_implication": (
            "For high-resolution stills, prefer restoration blocks that model long-range "
            "dependencies with feasible memory instead of independent crop-local context."
        ),
    },
    {
        "id": "hat",
        "title": "HAT: Hybrid Attention Transformer for Image Restoration",
        "url": "https://arxiv.org/abs/2309.05239",
        "repo_implication": (
            "Hybrid channel/window attention plus overlapping cross-window interaction is "
            "a stronger candidate for activating more source pixels and placing fine detail."
        ),
    },
    {
        "id": "raw_enhanced_realsr",
        "title": "Unveiling Hidden Details: A RAW Data-Enhanced Paradigm for Real-World Super-Resolution",
        "url": "https://arxiv.org/abs/2411.10798",
        "repo_implication": (
            "RAW carries recoverable fine detail that RGB-only supervision loses; "
            "model the RAW adapter/noise alignment explicitly."
        ),
    },
]


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def dataset_by_id(inventory: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    for row in inventory.get("datasets", []):
        if isinstance(row, dict) and row.get("id") == dataset_id:
            return row
    return {"id": dataset_id, "exists": False, "ready_for_current_work": False, "missing_expected_artifacts": ["dataset row missing"]}


def requirement_by_id(requirements: dict[str, Any], requirement_id: str) -> dict[str, Any]:
    for row in requirements.get("requirements", []):
        if isinstance(row, dict) and row.get("id") == requirement_id:
            return row
    return {"id": requirement_id, "status": "missing", "required_evidence": [], "acceptance": []}


def num(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def first_expected_artifact_path(dataset: dict[str, Any], suffix: str, fallback_name: str) -> str:
    for row in dataset.get("expected_artifacts", []):
        if isinstance(row, dict):
            path = str(row.get("path") or "")
            if path.endswith(suffix):
                return path
    base = Path(str(dataset.get("path") or "."))
    return (base / fallback_name).as_posix()


def shell_command(parts: list[str]) -> str:
    return " \\\n  ".join(parts)


def pick_scene(scenes: list[Any], token: str, fallback: str) -> str:
    token_lower = token.lower()
    for scene in scenes:
        value = str(scene)
        if token_lower in value.lower():
            return value
    return fallback


def find_rejected_full_window_attention(scoreboard: dict[str, Any]) -> dict[str, Any] | None:
    """Return the known expensive window-attention rejection, if indexed."""

    candidates: list[dict[str, Any]] = []
    for row in scoreboard.get("experiments", []):
        if not isinstance(row, dict):
            continue
        if row.get("model_arch") != "window_attention_teacher":
            continue
        steps = row.get("steps")
        if not isinstance(steps, int) or steps < 12000:
            continue
        holdout_mae = row.get("holdout_residual_mae_reduction_pct_median")
        if isinstance(holdout_mae, (int, float)) and float(holdout_mae) <= 0.0:
            candidates.append(row)
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: str(row.get("path") or ""))[-1]


def nested(data: dict[str, Any], keys: list[str]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def clean_signal_evidence(external_root: Path) -> dict[str, Any]:
    target_json = external_root / "artifacts/premium_still_sr_clean_signal_targets_20260702/clean_signal_targets.json"
    model_receipt = (
        external_root
        / "artifacts/premium_still_sr_clean_signal_model_x2dsceneholdout_unet_w32_700_20260702/train_receipt.json"
    )
    target_data = load_optional_json(target_json)
    model_data = load_optional_json(model_receipt)
    summary = target_data.get("summary", {}) if isinstance(target_data, dict) else {}
    return {
        "target_receipt": target_json.as_posix(),
        "target_receipt_present": target_data is not None,
        "target_rows": nested(summary, ["row_count"]),
        "rows_with_noise_sidecars": nested(summary, ["rows_with_noise_sidecars"]),
        "classification_counts": nested(summary, ["classification_counts"]),
        "median_target_energy_retained_fraction": nested(summary, ["target_energy_retained_fraction", "median"]),
        "median_active_pixel_fraction": nested(summary, ["active_pixel_fraction", "median"]),
        "model_receipt": model_receipt.as_posix(),
        "model_receipt_present": model_data is not None,
        "model_steps": model_data.get("steps") if isinstance(model_data, dict) else None,
        "model_checkpoint_sha256": model_data.get("checkpoint_sha256") if isinstance(model_data, dict) else None,
        "model_train_median_raw_mae_recovery_pct": nested(
            model_data or {}, ["eval", "train", "raw_residual_mae_reduction_pct", "median"]
        ),
        "model_holdout_median_raw_mae_recovery_pct": nested(
            model_data or {}, ["eval", "holdout", "raw_residual_mae_reduction_pct", "median"]
        ),
        "verdict": (
            "clean-signal target exists, but the bounded same-family U-Net probe failed to improve the "
            "X2D holdout; do not rerun clean-signal residual training as the next primary path"
            if model_data is not None
            else "clean-signal target evidence is absent or incomplete"
        ),
    }


def build_contract(
    *,
    inventory: dict[str, Any],
    scoreboard: dict[str, Any],
    residual_gap: dict[str, Any],
    requirements: dict[str, Any],
    external_root: Path,
) -> dict[str, Any]:
    rawcfa_dataset = dataset_by_id(inventory, "premium_still_sr_expanded_rawcfa_targets")
    residual_dataset = dataset_by_id(inventory, "premium_still_sr_raw_cfa_residual_targets")
    requirement = requirement_by_id(requirements, "premium_still_sr_promotion_receipts")
    target = residual_gap.get("target") if isinstance(residual_gap.get("target"), dict) else {}
    thresholds = residual_gap.get("promotion_thresholds") if isinstance(residual_gap.get("promotion_thresholds"), dict) else {}
    camera_summary = [row for row in residual_gap.get("camera_summary", []) if isinstance(row, dict)]
    blockers = [str(row) for row in residual_gap.get("blockers", [])]
    next_experiments = [row for row in residual_gap.get("next_experiments", []) if isinstance(row, dict)]
    promotable_count = int(scoreboard.get("promotable_candidate_count") or 0)

    canonical_targets_ready = bool(rawcfa_dataset.get("ready_for_current_work")) and bool(
        residual_dataset.get("ready_for_current_work")
    )
    gap_production_ready = bool(residual_gap.get("production_ready"))
    scoreboard_production_ready = bool(scoreboard.get("production_ready"))
    requirement_open = requirement.get("status") in {"open", "blocked_on_real_camera_access", "missing"}
    production_ready = canonical_targets_ready and gap_production_ready and scoreboard_production_ready and not requirement_open

    best_by_camera = {
        str(row.get("camera")): {
            "best_holdout_mae_recovery_pct_median": row.get("best_holdout_mae_recovery_pct_median"),
            "best_holdout_rmse_recovery_pct_median": row.get("best_holdout_rmse_recovery_pct_median"),
            "passes_threshold": bool(row.get("passes_threshold")),
            "best_path": row.get("best_path"),
        }
        for row in camera_summary
    }
    mae_threshold = num(thresholds.get("holdout_mae_recovery_pct_median_min"), 15.0)
    rmse_threshold = num(thresholds.get("holdout_rmse_recovery_pct_median_min"), 0.0)
    residual_npz = first_expected_artifact_path(residual_dataset, ".npz", "raw_cfa_residual_targets.npz")
    dedup_target_npz = (
        external_root
        / "artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_20260701/raw_cfa_residual_targets_dedup.npz"
    ).as_posix()
    psf_sidecar = (
        external_root / "artifacts/premium_still_sr_psf_sidecar_contract_20260701/premium_still_sr_psf_sidecar.json"
    ).as_posix()
    clean_evidence = clean_signal_evidence(external_root)
    run_root = (external_root / "artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702").as_posix()
    tmp_root = (external_root / "tmp").as_posix()
    scenes = target.get("scenes", []) if isinstance(target.get("scenes"), list) else []
    x2d_holdout_scene = pick_scene(scenes, "x2d", "2024_April_X2D_1742")
    z8_holdout_scene = pick_scene(scenes, "z8", "Z8Z_1330")
    rejected_full_window_attention = find_rejected_full_window_attention(scoreboard)
    fixture_manifest = (
        external_root / "artifacts/premium_still_sr_fixture_manifest_routed_20260630/fixture_manifest.json"
    ).as_posix()
    pair_npz = (
        external_root
        / "artifacts/premium_still_sr_self_supervised_raw_sr_pairs_routed_t16_20260702/premium_still_sr_clean_source_pairs_routed_t16.npz"
    ).as_posix()
    pair_work_root = (
        external_root / "artifacts/premium_still_sr_self_supervised_raw_sr_pairs_routed_t16_20260702/work"
    ).as_posix()
    pair_audit_root = (
        external_root / "artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702"
    ).as_posix()
    x2d_pair_model_root = (
        external_root / "artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702"
    ).as_posix()
    z8_pair_model_root = (
        external_root / "artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702"
    ).as_posix()
    smoke_args = [
        "python3 tools/cnn/build_premium_still_sr_pairs.py",
        f"--fixture-manifest {fixture_manifest}",
        f"--out {pair_npz}",
        f"--work-dir {pair_work_root}",
        "--tiles-per-fixture 16",
        "--low-plane-tile 96",
        "--dataset-label premium_still_sr_clean_source_raw_sr_pairs_routed_t16",
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "production_ready": production_ready,
        "should_start_next_model_pass": canonical_targets_ready and not production_ready,
        "requirement": {
            "id": requirement.get("id"),
            "status": requirement.get("status"),
            "required_evidence": requirement.get("required_evidence", []),
            "acceptance": requirement.get("acceptance", []),
        },
        "canonical_targets": [
            {
                "id": rawcfa_dataset.get("id"),
                "path": rawcfa_dataset.get("path"),
                "ready_for_current_work": bool(rawcfa_dataset.get("ready_for_current_work")),
                "missing_expected_artifacts": rawcfa_dataset.get("missing_expected_artifacts", []),
                "role": rawcfa_dataset.get("role"),
            },
            {
                "id": residual_dataset.get("id"),
                "path": residual_dataset.get("path"),
                "ready_for_current_work": bool(residual_dataset.get("ready_for_current_work")),
                "missing_expected_artifacts": residual_dataset.get("missing_expected_artifacts", []),
                "role": residual_dataset.get("role"),
            },
        ],
        "target_lock": {
            "path": target.get("path"),
            "sha256": target.get("sha256"),
            "row_count": target.get("row_count"),
            "scene_count": target.get("scene_count"),
            "scenes": target.get("scenes", []),
            "render_to_raw_corr_abs_median": target.get("render_to_raw_corr_abs_median"),
            "raw_to_render_hf_abs_ratio_median": target.get("raw_to_render_hf_abs_ratio_median"),
            "runtime_policy": "source raw/HF is training-target only; render-time candidate must use no REF/source content",
        },
        "current_model_state": {
            "scoreboard_receipt_count": scoreboard.get("receipt_count"),
            "scoreboard_promotable_candidate_count": promotable_count,
            "scoreboard_best_candidate": scoreboard.get("best_candidate"),
            "rejected_full_window_attention_teacher": rejected_full_window_attention,
            "residual_gap_production_ready": gap_production_ready,
            "best_by_camera": best_by_camera,
            "blockers": blockers,
            "clean_signal_evidence": clean_evidence,
        },
        "research_basis": RESEARCH_BASIS,
        "next_model_contract": {
            "recommended_first_track": (
                "self-supervised clean-source raw SR teacher with realistic degradation, "
                "then candidate-only distillation"
            ),
            "implementation_blueprint": {
                "teacher_family": (
                    "self-supervised clean-source RAW SR teacher built from real high-quality 50 MP / "
                    "100 MP Bayer sources degraded into low-resolution same-color Bayer planes; use "
                    "SwinIR/HAT/RBSFormer, Restormer, NAF-style, or similarly capable raw restoration "
                    "backbones only after the pair builder and interpolation baseline gates pass"
                ),
                "student_family": (
                    "candidate-only raw-CFA reconstruction student distilled from the clean-source "
                    "teacher only after the teacher beats interpolation on X2D/Z8 holdouts and then "
                    "improves actual still candidates without REF/source/JPEG runtime inputs"
                ),
                "self_supervised_raw_sr_contract": {
                    "pair_builder": "tools/cnn/build_premium_still_sr_pairs.py",
                    "trainer": "tools/cnn/train_premium_still_sr_clean_source_pairs.py",
                    "pair_layout": [
                        "inputs: four same-color low-resolution Bayer planes built from real source RAW",
                        "targets: four same-color high-resolution Bayer planes from the same source RAW",
                        "metadata: camera key, CFA phase/pattern, source sha256, noise sidecars, and dimensions",
                    ],
                    "degradation_policy": [
                        "same-color 2x box degradation is the CI-safe baseline",
                        "next production variant must add realistic camera blur/PSF, noise, bit depth, and compression simulation",
                        "degradation must be generated from source RAW only during training; render-time output may use candidate RAW and metadata only",
                    ],
                    "holdout_policy": [
                        "hold out entire images/scenes, not random tiles, to prevent leakage",
                        "cover both 50 MP Z8-class and 100 MP X2D-class sources",
                        "report interpolation baseline, teacher result, and candidate-distilled result separately",
                    ],
                },
                "input_tensor_contract": [
                    "teacher input: four same-color degraded Bayer planes from source RAW training data",
                    "student/render input: four same-color candidate raw-CFA planes",
                    "student/render input: candidate-derived high-frequency/detail planes only if produced from candidate RAW",
                    "CFA phase one-hot or BayerUnify-style canonical phase mapping",
                    "camera/model and ISO conditioning",
                    "validated noise-sidecar scalar planes where available",
                    "PSF/kernel sidecar weights where row-level or modeled kernels are available",
                ],
                "output_tensor_contract": [
                    "teacher output: four same-color high-resolution Bayer planes",
                    "student output: four same-color editable raw-CFA reconstruction or residual planes",
                    "no rendered RGB output as the promoted artifact",
                    "editable DNG/GPR reconstruction before review TIFF/ProRes export",
                ],
                "training_protocol": [
                    "start with self-supervised clean-source RAW SR pairs from real high-quality Bayer sources, not source-minus-candidate residuals",
                    "compare against same-color interpolation and a no-CNN baseline before any long teacher run",
                    "separate calibrated sensor noise from signal supervision; train clean signal first and add validated noise texture back only after reconstruction",
                    "use the 117-row residual/clean-signal targets as rejection evidence and actual-still gate inputs, not as the next primary teacher target",
                    "use EV/rendered rows only for rendered/tone review gates, not as duplicated raw supervision",
                    "use Bayer-preserving flips/rotations or canonical phase remapping only when the output phase metadata is updated",
                    "train with spatial raw signal loss plus frequency/detail-band terms against the clean source target",
                    "treat denoise, deblur/PSF, and SR as one raw-restoration target, while keeping calibrated noise addback separate from signal supervision",
                    "start with teacher-scale capacity, then distill only after teacher evidence beats the locked baselines",
                ],
                "validation_protocol": [
                    "image/scene-held-out X2D and Z8 clean-source RAW SR gates",
                    "actual candidate still gate after teacher success: candidate raw -> model -> editable DNG/GPR -> rendered review",
                    "full-image or overlapped-tile inference with seam-band diagnostics",
                    "100 percent crop dashboard with worst rows by MAE/RMSE and rendered latitude stress",
                    "editable DNG/GPR openability and metadata transplant receipts",
                    "timing and memory receipts, even if the path is offline-only",
                ],
                "first_ablation_order": [
                    "self-supervised clean-source RAW SR pair build smoke with CFA/noise metadata preserved",
                    "same-color interpolation baseline from audit_premium_still_sr_pairs.py on the exact held-out pair set",
                    "teacher smoke against held-out X2D and Z8 source images",
                    "teacher with realistic degradation/noise/PSF variants versus simple same-color box degradation",
                    "teacher full-image or overlapped-tile validation versus crop-only metrics",
                    "distilled candidate-only student only after teacher clears both camera holdouts",
                    "actual still/editor-latitude gate only after the distilled candidate beats the current still baseline",
                ],
            },
            "execution_plan": {
                "run_id": "premium_still_sr_self_supervised_raw_sr_contract_20260702",
                "artifact_root": run_root,
                "tmp_root": tmp_root,
                "canonical_full_target_npz": residual_npz,
                "training_target_npz": dedup_target_npz,
                "clean_source_pair_npz": pair_npz,
                "clean_source_pair_audit_root": pair_audit_root,
                "clean_source_pair_model_x2d_root": x2d_pair_model_root,
                "clean_source_pair_model_z8_root": z8_pair_model_root,
                "target_policy": (
                    "Use the deduplicated 117-row raw-domain NPZ and 20260702 clean-signal target as blocker evidence "
                    "and actual-still review inputs, not as the next primary teacher objective. The next CNN should "
                    "first train on self-supervised clean-source RAW SR pairs from real high-quality Bayer sources with "
                    "realistic degradation, then distill to a candidate-only render path only if the teacher beats "
                    "same-color interpolation on held-out X2D/Z8 images."
                ),
                "psf_sidecar": psf_sidecar,
                "runtime_input_policy": (
                    "candidate raw/CFA, candidate-derived detail, metadata, CFA phase, ISO/noise/PSF sidecars only; "
                    "no REF/source/JPEG pixels at render time"
                ),
                "smoke_command": shell_command(
                    [
                        f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                        *smoke_args,
                    ]
                ),
                "full_train_commands": [
                    {
                        "id": "build_clean_source_raw_sr_pairs",
                        "holdout_scene": x2d_holdout_scene,
                        "status": "launchable_pair_builder",
                        "launchable_for_production_attempt": True,
                        "purpose": "Build the next primary target: source-RAW-derived low/high same-color Bayer pairs with metadata preserved for clean-source RAW SR.",
                        "command": shell_command(
                            [
                                f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                                "python3 tools/cnn/build_premium_still_sr_pairs.py",
                                f"--fixture-manifest {fixture_manifest}",
                                f"--out {pair_npz}",
                                f"--work-dir {pair_work_root}",
                                "--tiles-per-fixture 16",
                                "--low-plane-tile 96",
                                "--dataset-label premium_still_sr_clean_source_raw_sr_pairs_routed_t16",
                            ]
                        ),
                    },
                    {
                        "id": "teacher_clean_source_raw_sr_x2d_holdout",
                        "holdout_scene": x2d_holdout_scene,
                        "status": "rejected_reference_do_not_rerun_as_primary",
                        "launchable_for_production_attempt": False,
                        "rejection_reason": (
                            "Existing 1500-step routed local residual-pixelshuffle teacher improved train loss "
                            "but regressed held-out X2D; keep this command only as reproduction evidence."
                        ),
                        "purpose": "Reference command for the rejected routed X2D clean-source teacher; not the next production attempt.",
                        "command": shell_command(
                            [
                                f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py",
                                f"--pairs {pair_npz}",
                                f"--output-dir {x2d_pair_model_root}",
                                "--holdout-image x2d_100mp_dng",
                                "--steps 1500",
                                "--batch 16",
                                "--low-crop 96",
                                "--width 48",
                                "--depth 6",
                            ]
                        ),
                    },
                    {
                        "id": "teacher_clean_source_raw_sr_z8_holdout",
                        "holdout_scene": z8_holdout_scene,
                        "status": "rejected_reference_do_not_rerun_as_primary",
                        "launchable_for_production_attempt": False,
                        "rejection_reason": (
                            "Existing 1500-step routed local residual-pixelshuffle teacher improved train loss "
                            "but regressed held-out Z8 MAE; keep this command only as reproduction evidence."
                        ),
                        "purpose": "Reference command for the rejected routed Z8 clean-source teacher; not the next production attempt.",
                        "command": shell_command(
                            [
                                f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py",
                                f"--pairs {pair_npz}",
                                f"--output-dir {z8_pair_model_root}",
                                "--holdout-image z8_z8z_1330",
                                "--steps 1500",
                                "--batch 16",
                                "--low-crop 96",
                                "--width 48",
                                "--depth 6",
                            ]
                        ),
                    },
                ],
                "next_candidate_preflight": {
                    "purpose": (
                        "Prevent the next premium still-SR pass from being another expensive replay "
                        "of a rejected local clean-source teacher."
                    ),
                    "new_run_must_not_match": [
                        "residual_pixelshuffle or local-CNN-only teacher over the same routed_t16 pair set",
                        "NAF-like residual pixelshuffle plus gradient/detail loss without changed degradation or non-local context",
                        "clean-signal residual U-Net over the same 20260702 X2D scene holdout",
                        "12k-step PSF/CFA window-attention raw-residual objective that already regressed X2D",
                    ],
                    "required_architecture_delta": [
                        "non-local raw restoration teacher such as shifted-window, hybrid-attention, Restormer/RBSFormer-style, or equivalent full-image/context model",
                        "explicit candidate-only student path only after the teacher beats same-color interpolation on both X2D and Z8 holdouts",
                    ],
                    "required_degradation_delta": [
                        "realistic RAW degradation beyond same-color 2x box alone: camera blur/PSF, noise, bit depth, and compression/decode simulation",
                        "camera/ISO conditioning that uses validated noise sidecars where available and leaves missing sidecars as metadata-only",
                    ],
                    "required_validation_delta": [
                        "full-image or overlapped-tile evaluation before any promotion claim",
                        "joint X2D plus Z8 holdout selection, not train loss and not a single-camera dashboard",
                        "worst-row 100 percent crops plus editable DNG/GPR and rendered latitude receipts",
                    ],
                    "promotion_attempt_allowed_after_preflight": False,
                    "promotion_attempt_allowed_when": (
                        "a new teacher receipt records the architecture/degradation/validation deltas above "
                        "and beats same-color interpolation on both held-out X2D and Z8 images"
                    ),
                },
                "pair_audit_command": shell_command(
                    [
                        f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                        "python3 tools/cnn/audit_premium_still_sr_pairs.py",
                        f"--pairs {pair_npz}",
                        f"--output-dir {pair_audit_root}",
                    ]
                ),
                "required_followup_receipts": [
                    "clean-source RAW SR pair receipt with source sha256, CFA phase, camera metadata, and noise sidecar provenance",
                    "pair_audit.json same-color interpolation baseline receipt on the exact held-out pair set",
                    "train_premium_still_sr_clean_source_pairs.py train_receipt.json proving whether the held-out teacher beats interpolation",
                    "teacher train_receipt.json showing held-out X2D and Z8 improvement over interpolation",
                    "candidate-only distillation receipt only after teacher holdout success",
                    "overlap-vs-plain seam diagnostics from eval_overlap > 0 after a model exists",
                    "100 percent crop dashboard with worst rows, not only aggregate medians",
                    "editable DNG and GPR packaging/openability receipts",
                    "rendered latitude review from the full 351-row/EV review target",
                    "timing and memory receipt for the offline still path",
                    "scoreboard rebuild and premium still-SR gate receipt if the gates pass",
                ],
                "promotion_reject_conditions": [
                    "self-supervised clean-source teacher fails to beat same-color interpolation on X2D or Z8 holdout",
                    "clean-source pair metadata loses CFA phase, source sha256, camera key, or noise sidecar provenance",
                    "distilled candidate-only still path fails to beat the existing 50 MP / 100 MP still baseline",
                    f"either X2D or Z8 holdout median raw-residual MAE recovery is below {mae_threshold:.1f}%",
                    "any severe worst-row regression in editable/raw-editor or rendered-latitude review",
                    "the receipt reports source raw, source HF, REF, or JPEG target content as runtime input",
                    "overlap/seam diagnostics expose tile-boundary artifacts",
                    "the deduplicated target hash, checkpoint hash, config, and dashboard are not recorded",
                ],
            },
            "minimum_viable_next_pass": {
                "must_change_from_failed_contract": [
                    "do not repeat the full-crop PSF/CFA window-attention run; it trained for 12k steps and regressed the X2D holdout",
                    "do not repeat clean-signal residual gating plus the same small U-Net family; the 700-step X2D holdout probe regressed",
                    "train the next teacher on clean-source RAW SR pairs from real high-quality Bayer sources instead of source-minus-candidate residual targets",
                    "prove the clean-source teacher beats same-color interpolation before candidate-only distillation",
                    "do not repeat a local NAF-like residual pixelshuffle teacher plus gradient/detail loss over the routed clean-source pairs; the 500-step X2D/Z8 holdout probes still regressed held-out MAE",
                    "add a materially stronger learned detail prior, clean-source teacher, or global/contextual objective instead of only increasing local CNN capacity",
                    "use overlapped tile inference or full-image/TLC-style validation so window/context seams and long-range placement errors are visible before promotion",
                    "condition on camera/noise and measured or modeled PSF metadata where available, rather than treating all resize/detail residuals as one distribution",
                    "treat a global near-box PSF as a negative/control input unless the sidecar has row-level or camera-specific kernel variation",
                    "treat denoising, deblurring/PSF, and SR as one raw-restoration objective while keeping the final emitted file editable raw",
                    "preserve sensor-pattern alignment for noise and CFA detail features instead of mixing Bayer phases in RGB space before the raw gate",
                    "select checkpoints by the joint X2D plus Z8 holdout gates, not train loss or a single-camera dashboard",
                    "emit the same editable raw, rendered latitude, timing, memory, config, and noise-policy receipts required for promotion even if the result fails",
                ],
                "acceptable_first_tracks": [
                    "self-supervised clean-source RAW SR pairs from real 50 MP / 100 MP sources with same-color Bayer degradation",
                    "clean-source teacher that beats same-color interpolation before any candidate-only distillation",
                    "realistic RAW degradation/noise/PSF synthesis calibrated by camera and ISO, then validated against actual still candidates",
                    "global-context encoder with raw-CFA residual decoder and candidate-only runtime inputs",
                    "PSF/kernel-conditioned global-context raw-CFA residual model using candidate raw plus measured or modeled kernel metadata",
                    "CFA-phase-conditioned raw-CFA residual model using RGGB/GBRG/GRBG/BGGR/unknown one-hot metadata for mixed normal-Bayer target sets",
                    "teacher-distilled raw-CFA detail prior whose teacher never appears at render time",
                    "masked/contextual raw-detail reconstruction objective trained on the locked 351-row target set",
                    "NAF-style or transformer-style raw restoration teacher with full-image/TLC-style evaluation and candidate-only runtime inputs",
                    "SwinIR/HAT-style shifted-window or hybrid-attention raw restoration teacher adapted to four-plane CFA residual output",
                    "Restormer-style high-resolution raw restoration teacher for denoise/deblur/SR coupling before distilling to a smaller runtime model",
                    "sensor-pattern-aligned real-noise conditioning/addback using validated darkframe sidecars for cameras with calibrated sidecars",
                    "scene-family routed specialists only if the router uses candidate raw/metadata and beats the shared baseline per family",
                ],
                "baseline_comparisons_required": [
                    "same-color Bayer interpolation baseline on the clean-source pair holdouts",
                    "actual still baseline after candidate-only distillation",
                    "full 12k-step X2D window-attention rejection",
                    "best X2D raw-CFA residual baseline",
                    "best Z8 raw-CFA residual baseline",
                    "small U-Net raw-domain probe",
                    "full-crop U-Net and gated pyramid U-Net rejection probes",
                    "matched local-CNN versus window-attention/transformer raw-restoration teacher ablation on the same deduplicated target",
                    "patch-dictionary and low-order candidate-signal rejection probes",
                ],
                "early_reject_if": [
                    "the clean-source pair builder cannot preserve CFA phase/source sha256/noise sidecar metadata",
                    "the clean-source teacher does not beat same-color interpolation on X2D and Z8 held-out images",
                    "the distilled candidate-only path does not improve actual still candidates after teacher success",
                    "X2D median raw-residual MAE recovery is not positive",
                    "Z8 median raw-residual MAE recovery drops below the existing positive baseline without a documented tradeoff",
                    "runtime input policy includes REF, source raw, source HF, or JPEG target content",
                    "improvement appears only in local crop metrics and disappears in full still/editor-latitude review",
                    "tile-overlap/full-image evaluation shows window seams or long-range detail placement regressions",
                    "checkpoint selection depends on train loss without passing held-out X2D and Z8 receipts",
                ],
            },
            "allowed_runtime_inputs": [
                "candidate raw/CFA planes",
                "candidate-derived luma/detail features",
                "camera metadata",
                "CFA phase / Bayer pattern metadata",
                "ISO/noise sidecar scalar conditioning where validated",
                "PSF/kernel metadata sidecar or per-row kernel weights",
                "trained model priors distilled from external or offline teachers",
            ],
            "forbidden_runtime_inputs": [
                "REF image content",
                "source raw content",
                "source high-frequency residuals",
                "JPEG-derived target content",
            ],
            "do_not_repeat_as_primary_path": [
                "rendered-context-only target coverage change",
                "stored candidate-HF feature concatenation",
                "naive one-sigma noise-thresholded targets",
                "simple pooled local raw context",
                "combined stored-HF plus pooled-context features",
                "simple multiscale band-loss reweighting",
                "X2D-only domain filtering without a stronger context/objective",
                "camera-balanced sampling without a stronger context/objective",
                "small context-padding around the same local objective",
                "small U-Net/multiscale architecture without stronger supervision or full-image context",
                "absolute crop-position/full-crop scalar frame context without stronger supervision or full-image context",
                "bounded full-crop U-Net training without a stronger full-image objective or model capacity",
                "bounded full-crop stored-HF/context U-Net training without a materially stronger objective or model capacity",
                "bounded full-crop spectral-loss U-Net training without a materially stronger model or target",
                "larger full-crop raw-context U-Net training over the same candidate-only local/full-crop statistics",
                "deeper gated pyramid U-Net training over the same candidate-only local/full-crop statistics",
                "bounded global-context U-Net training over the same candidate-only raw-multiscale full-crop target",
                "training-only random context masking over the same global-context U-Net and candidate-only raw-multiscale target",
                "nearest-neighbor residual patch dictionary over current candidate raw/HF patch statistics",
                "low-order linear candidate raw/HF/metadata signal probes over current residual targets",
                "simple RCAB or NAF teacher scale-up over the same deduplicated raw-CFA residual objective without a stronger target, objective, or validation contract",
                "NAF-like residual pixelshuffle plus gradient/detail loss over the routed clean-source pair set without changing degradation policy or adding non-local/full-image teacher context",
                "another global near-box PSF conditioning repeat without row-level camera/resize PSF variation",
                "simple CFA one-hot or metadata plane add-on without a stronger raw-restoration objective",
                "calibrated random-HF or noise addback as a substitute for learned signal detail",
                "the 12k-step full-crop PSF/CFA window-attention teacher over the same raw residual target",
                "clean-signal residual target plus the same small U-Net family after the 20260702 X2D holdout rejection",
                "another residual-target pass that does not first prove clean-source RAW SR teacher lift over same-color interpolation",
                "another local CNN width/depth/loss sweep that does not add non-local attention, stronger teacher supervision, or full-image evaluation",
            ],
            "success_gates": [
                "clean-source RAW SR teacher beats same-color interpolation on held-out X2D and Z8 images",
                "candidate-only distillation improves actual 50 MP and 100 MP still candidates with no REF/source/JPEG runtime inputs",
                f"X2D median raw-residual MAE recovery >= {mae_threshold:.1f}%",
                f"Z8 median raw-residual MAE recovery >= {mae_threshold:.1f}%",
                f"holdout raw-residual RMSE recovery >= {rmse_threshold:.1f}%",
                "no severe negative worst rows in full still/editor-latitude review",
                "50 MP and 100 MP editable raw outputs open and roundtrip",
                "checkpoint, target hashes, config, dashboard, timing, memory, and noise-policy receipts are recorded",
            ],
            "candidate_experiments": next_experiments,
        },
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    targets = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('id')))}</td>"
        f"<td>{'ready' if row.get('ready_for_current_work') else 'missing'}</td>"
        f"<td><code>{html.escape(str(row.get('path')))}</code></td>"
        f"<td>{html.escape(', '.join(map(str, row.get('missing_expected_artifacts') or [])))}</td>"
        "</tr>"
        for row in data["canonical_targets"]
    )
    cameras = "\n".join(
        "<tr>"
        f"<td>{html.escape(camera)}</td>"
        f"<td>{html.escape(str(row.get('best_holdout_mae_recovery_pct_median')))}</td>"
        f"<td>{html.escape(str(row.get('best_holdout_rmse_recovery_pct_median')))}</td>"
        f"<td>{html.escape(str(row.get('passes_threshold')))}</td>"
        f"<td><code>{html.escape(str(row.get('best_path')))}</code></td>"
        "</tr>"
        for camera, row in sorted(data["current_model_state"]["best_by_camera"].items())
    )
    forbidden = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_model_contract"]["forbidden_runtime_inputs"])
    do_not_repeat = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_model_contract"]["do_not_repeat_as_primary_path"])
    gates = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_model_contract"]["success_gates"])
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in data["current_model_state"]["blockers"])
    research = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('title')))}</td>"
        f"<td><a href=\"{html.escape(str(row.get('url')))}\">source</a></td>"
        f"<td>{html.escape(str(row.get('repo_implication')))}</td>"
        "</tr>"
        for row in data.get("research_basis", [])
    )
    minimum = data["next_model_contract"]["minimum_viable_next_pass"]
    blueprint = data["next_model_contract"].get("implementation_blueprint", {})
    execution = data["next_model_contract"].get("execution_plan", {})
    input_contract = "".join(f"<li>{html.escape(item)}</li>" for item in blueprint.get("input_tensor_contract", []))
    output_contract = "".join(f"<li>{html.escape(item)}</li>" for item in blueprint.get("output_tensor_contract", []))
    training_protocol = "".join(f"<li>{html.escape(item)}</li>" for item in blueprint.get("training_protocol", []))
    validation_protocol = "".join(f"<li>{html.escape(item)}</li>" for item in blueprint.get("validation_protocol", []))
    first_ablation_order = "".join(f"<li>{html.escape(item)}</li>" for item in blueprint.get("first_ablation_order", []))
    full_train_commands = "".join(
        "<section class=\"card\">"
        f"<h3>{html.escape(str(row.get('id')))}</h3>"
        f"<p><strong>Status:</strong> {html.escape(str(row.get('status') or 'unspecified'))}</p>"
        f"<p><strong>Launchable production attempt:</strong> {html.escape(str(row.get('launchable_for_production_attempt')).lower())}</p>"
        f"<p>{html.escape(str(row.get('purpose')))}</p>"
        f"<p><strong>Holdout:</strong> {html.escape(str(row.get('holdout_scene')))}</p>"
        f"<p>{html.escape(str(row.get('rejection_reason') or ''))}</p>"
        f"<pre>{html.escape(str(row.get('command')))}</pre>"
        "</section>"
        for row in execution.get("full_train_commands", [])
        if isinstance(row, dict)
    )
    preflight = execution.get("next_candidate_preflight", {}) if isinstance(execution.get("next_candidate_preflight"), dict) else {}
    preflight_must_not_match = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in preflight.get("new_run_must_not_match", [])
    )
    preflight_architecture = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in preflight.get("required_architecture_delta", [])
    )
    preflight_degradation = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in preflight.get("required_degradation_delta", [])
    )
    preflight_validation = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in preflight.get("required_validation_delta", [])
    )
    required_followup_receipts = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in execution.get("required_followup_receipts", [])
    )
    promotion_reject_conditions = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in execution.get("promotion_reject_conditions", [])
    )
    must_change = "".join(f"<li>{html.escape(item)}</li>" for item in minimum["must_change_from_failed_contract"])
    acceptable_tracks = "".join(f"<li>{html.escape(item)}</li>" for item in minimum["acceptable_first_tracks"])
    baseline_comparisons = "".join(f"<li>{html.escape(item)}</li>" for item in minimum["baseline_comparisons_required"])
    early_reject = "".join(f"<li>{html.escape(item)}</li>" for item in minimum["early_reject_if"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Next Experiment Contract</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #121820; background: #f6f8fa; }}
main {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; letter-spacing: 0; }}
h2 {{ margin-top: 26px; }}
.sub {{ color: #5f6b76; max-width: 880px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #5f6b76; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
pre {{ white-space: pre-wrap; word-break: break-word; background: #121820; color: #f6f8fa; padding: 12px; border-radius: 6px; font-size: 12px; }}
.warn {{ color: #9a4b00; font-weight: 700; }}
.ok {{ color: #0c6b3d; font-weight: 700; }}
</style></head><body><main>
<h1>Premium Still-SR Next Experiment Contract</h1>
<p class="sub">This locks the next premium still-SR pass to the current raw-CFA target evidence and records what must not be repeated as the primary path.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value {'ok' if data['production_ready'] else 'warn'}">{str(data['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Start next model pass</div><div class="value">{str(data['should_start_next_model_pass']).lower()}</div></section>
  <section class="card"><div class="label">Promotable candidates</div><div class="value">{data['current_model_state']['scoreboard_promotable_candidate_count']}</div></section>
  <section class="card"><div class="label">Target rows</div><div class="value">{data['target_lock'].get('row_count')}</div></section>
</div>
<h2>Canonical Targets</h2>
<table><tr><th>id</th><th>status</th><th>path</th><th>missing</th></tr>{targets}</table>
<h2>Current Camera Blockers</h2>
<table><tr><th>camera</th><th>best MAE recovery</th><th>best RMSE recovery</th><th>passes</th><th>receipt</th></tr>{cameras}</table>
<ul>{blockers}</ul>
<h2>Research Basis</h2>
<table><tr><th>source</th><th>link</th><th>repo implication</th></tr>{research}</table>
<h2>Implementation Blueprint</h2>
<table>
  <tr><th>teacher family</th><td>{html.escape(str(blueprint.get('teacher_family')))}</td></tr>
  <tr><th>student family</th><td>{html.escape(str(blueprint.get('student_family')))}</td></tr>
</table>
<h3>Input tensor contract</h3>
<ul>{input_contract}</ul>
<h3>Output tensor contract</h3>
<ul>{output_contract}</ul>
<h3>Training protocol</h3>
<ul>{training_protocol}</ul>
<h3>Validation protocol</h3>
<ul>{validation_protocol}</ul>
<h3>First ablation order</h3>
<ul>{first_ablation_order}</ul>
<h2>Executable Next Pass</h2>
<table>
  <tr><th>run id</th><td>{html.escape(str(execution.get('run_id')))}</td></tr>
  <tr><th>artifact root</th><td><code>{html.escape(str(execution.get('artifact_root')))}</code></td></tr>
  <tr><th>tmp root</th><td><code>{html.escape(str(execution.get('tmp_root')))}</code></td></tr>
  <tr><th>full target</th><td><code>{html.escape(str(execution.get('canonical_full_target_npz')))}</code></td></tr>
  <tr><th>training target</th><td><code>{html.escape(str(execution.get('training_target_npz')))}</code></td></tr>
  <tr><th>PSF sidecar</th><td><code>{html.escape(str(execution.get('psf_sidecar')))}</code></td></tr>
</table>
<p>{html.escape(str(execution.get('target_policy')))}</p>
<p>{html.escape(str(execution.get('runtime_input_policy')))}</p>
<h3>Smoke command</h3>
<pre>{html.escape(str(execution.get('smoke_command')))}</pre>
<h3>Pair audit command</h3>
<pre>{html.escape(str(execution.get('pair_audit_command')))}</pre>
<h3>Reference and launch commands</h3>
<div class="grid">{full_train_commands}</div>
<h3>Next candidate preflight</h3>
<p>{html.escape(str(preflight.get('purpose') or ''))}</p>
<table>
  <tr><th>promotion attempt allowed now</th><td>{html.escape(str(preflight.get('promotion_attempt_allowed_after_preflight')).lower())}</td></tr>
  <tr><th>allowed when</th><td>{html.escape(str(preflight.get('promotion_attempt_allowed_when') or ''))}</td></tr>
</table>
<h4>New run must not match</h4>
<ul>{preflight_must_not_match}</ul>
<h4>Required architecture delta</h4>
<ul>{preflight_architecture}</ul>
<h4>Required degradation delta</h4>
<ul>{preflight_degradation}</ul>
<h4>Required validation delta</h4>
<ul>{preflight_validation}</ul>
<h3>Required follow-up receipts</h3>
<ul>{required_followup_receipts}</ul>
<h3>Promotion reject conditions</h3>
<ul>{promotion_reject_conditions}</ul>
<h2>Forbidden Runtime Inputs</h2>
<ul>{forbidden}</ul>
<h2>Minimum Viable Next Pass</h2>
<h3>Must change from the failed contract</h3>
<ul>{must_change}</ul>
<h3>Acceptable first tracks</h3>
<ul>{acceptable_tracks}</ul>
<h3>Required baseline comparisons</h3>
<ul>{baseline_comparisons}</ul>
<h3>Early reject if</h3>
<ul>{early_reject}</ul>
<h2>Do Not Repeat As Primary Path</h2>
<ul>{do_not_repeat}</ul>
<h2>Promotion Gates</h2>
<ul>{gates}</ul>
<p>JSON: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--inventory", type=Path, default=None)
    ap.add_argument("--scoreboard", type=Path, default=None)
    ap.add_argument("--residual-gap", type=Path, default=None)
    ap.add_argument("--requirements", type=Path, default=ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json")
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    inventory_path = args.inventory or args.external_root / "artifacts/cnn_dataset_inventory_20260630/cnn_dataset_inventory.json"
    scoreboard_path = args.scoreboard or args.external_root / "artifacts/premium_still_sr_experiment_scoreboard_restormer_t64_20260702/scoreboard.json"
    residual_gap_path = args.residual_gap or args.external_root / "artifacts/premium_still_sr_raw_cfa_residual_gap_20260701/raw_cfa_residual_gap.json"
    data = build_contract(
        inventory=load_json(inventory_path),
        scoreboard=load_json(scoreboard_path),
        residual_gap=load_json(residual_gap_path),
        requirements=load_json(args.requirements),
        external_root=args.external_root,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "premium_still_sr_next_experiment_contract.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
