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
    run_root = (external_root / "artifacts/premium_still_sr_window_attention_teacher_gate_20260701").as_posix()
    tmp_root = (external_root / "tmp").as_posix()
    scenes = target.get("scenes", []) if isinstance(target.get("scenes"), list) else []
    x2d_holdout_scene = pick_scene(scenes, "x2d", "2024_April_X2D_1742")
    z8_holdout_scene = pick_scene(scenes, "z8", "Z8Z_1330")
    common_train_args = [
        "python3 tools/cnn/train_premium_still_sr_raw_cfa_residual.py",
        f"--targets {dedup_target_npz}",
        "--model-arch window_attention_teacher",
        "--feature-mode raw_multiscale_coord_ev_noise_psf_cfa",
        f"--psf-sidecar {psf_sidecar}",
        "--sample-mode full_crop",
        "--sample-balance scene",
        "--width 48",
        "--depth 8",
        "--residual-scale 0.12",
        "--steps 12000",
        "--batch-size 1",
        "--patch-size 512",
        "--lr 2.0e-4",
        "--weight-decay 1.0e-4",
        "--grad-weight 0.05",
        "--target-abs-weight 1.0",
        "--band-weight 0.10",
        "--spectral-weight 0.02",
        "--eval-every 500",
        "--eval-tile 512",
        "--eval-overlap 64",
        "--seam-check-width 16",
        "--panel-rows 12",
        "--save-best-holdout-checkpoint",
        "--device mps",
    ]
    smoke_args = [
        "python3 tools/cnn/train_premium_still_sr_raw_cfa_residual.py",
        f"--targets {dedup_target_npz}",
        f"--output-dir {run_root}/smoke_window_attention_x2d",
        "--checkpoint-name premium_still_sr_window_attention_smoke.pt",
        "--model-arch window_attention_teacher",
        "--feature-mode raw_multiscale_coord_ev_noise_psf_cfa",
        f"--psf-sidecar {psf_sidecar}",
        f"--holdout-scene {x2d_holdout_scene}",
        "--sample-mode full_crop",
        "--sample-balance scene",
        "--width 8",
        "--depth 2",
        "--steps 3",
        "--batch-size 1",
        "--patch-size 128",
        "--eval-tile 128",
        "--eval-holdout-rows 1",
        "--eval-train-rows 2",
        "--device cpu",
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
            "residual_gap_production_ready": gap_production_ready,
            "best_by_camera": best_by_camera,
            "blockers": blockers,
        },
        "research_basis": RESEARCH_BASIS,
        "next_model_contract": {
            "recommended_first_track": "full-image or structured raw-CFA residual learner",
            "implementation_blueprint": {
                "teacher_family": (
                    "SwinIR/HAT/RBSFormer-style window or hybrid-attention raw restoration teacher, "
                    "with Restormer-style high-resolution blocks as the fallback if window attention "
                    "does not clear full-image placement gates"
                ),
                "student_family": (
                    "candidate-only raw-CFA residual student distilled only after the teacher clears "
                    "the X2D and Z8 holdout gates"
                ),
                "input_tensor_contract": [
                    "four same-color candidate raw-CFA planes",
                    "candidate-derived high-frequency/detail planes",
                    "CFA phase one-hot or BayerUnify-style canonical phase mapping",
                    "camera/model and ISO conditioning",
                    "validated noise-sidecar scalar planes where available",
                    "PSF/kernel sidecar weights where row-level or modeled kernels are available",
                ],
                "output_tensor_contract": [
                    "four same-color raw-CFA residual planes",
                    "no rendered RGB output as the promoted artifact",
                    "editable DNG/GPR reconstruction before review TIFF/ProRes export",
                ],
                "training_protocol": [
                    "deduplicate the 351 rendered EV rows to the 117 unique raw scene/crop rows for raw-domain loss",
                    "use EV/rendered rows only for rendered/tone review gates, not as duplicated raw supervision",
                    "use Bayer-preserving flips/rotations or canonical phase remapping only when the output phase metadata is updated",
                    "train with spatial raw residual loss plus frequency/detail-band terms that are ablated against the same target",
                    "treat denoise, deblur/PSF, and SR as one raw-restoration target, while keeping calibrated noise addback separate from signal supervision",
                    "start with teacher-scale capacity, then distill only after teacher evidence beats the locked baselines",
                ],
                "validation_protocol": [
                    "scene-held-out X2D and Z8 gates",
                    "full-image or overlapped-tile inference with seam-band diagnostics",
                    "100 percent crop dashboard with worst rows by MAE/RMSE and rendered latitude stress",
                    "editable DNG/GPR openability and metadata transplant receipts",
                    "timing and memory receipts, even if the path is offline-only",
                ],
                "first_ablation_order": [
                    "window-attention teacher versus current best noise-floor U-Net on the same deduplicated rows",
                    "teacher with and without Bayer phase conditioning",
                    "teacher with and without validated noise-sidecar conditioning",
                    "teacher with row-level/measured PSF variation versus no PSF conditioning; global near-box PSF is a control only",
                    "teacher full-image or overlapped-tile validation versus crop-only metrics",
                    "distilled student only after teacher clears both camera holdouts",
                ],
            },
            "execution_plan": {
                "run_id": "premium_still_sr_window_attention_teacher_gate_20260701",
                "artifact_root": run_root,
                "tmp_root": tmp_root,
                "canonical_full_target_npz": residual_npz,
                "training_target_npz": dedup_target_npz,
                "target_policy": (
                    "Use the deduplicated 117-row raw-domain NPZ for raw-CFA loss. "
                    "Use the full 351-row/EV target only for rendered tone and latitude review."
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
                        "id": "x2d_scene_holdout_window_attention_teacher",
                        "holdout_scene": x2d_holdout_scene,
                        "purpose": "Prove the hard 100MP/X2D still case improves with non-local raw-CFA detail priors.",
                        "command": shell_command(
                            [
                                f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                                *common_train_args,
                                f"--output-dir {run_root}/x2d_scene_holdout_window_attention_teacher",
                                "--checkpoint-name premium_still_sr_window_attention_x2d_holdout.pt",
                                f"--holdout-scene {x2d_holdout_scene}",
                            ]
                        ),
                    },
                    {
                        "id": "z8_scene_holdout_window_attention_teacher",
                        "holdout_scene": z8_holdout_scene,
                        "purpose": "Verify the 50MP/Z8 positive baseline is preserved while improving still detail.",
                        "command": shell_command(
                            [
                                f"GPR_TMPDIR={tmp_root} TMPDIR={tmp_root}",
                                *common_train_args,
                                f"--output-dir {run_root}/z8_scene_holdout_window_attention_teacher",
                                "--checkpoint-name premium_still_sr_window_attention_z8_holdout.pt",
                                f"--holdout-scene {z8_holdout_scene}",
                            ]
                        ),
                    },
                ],
                "required_followup_receipts": [
                    "train_receipt.json for X2D holdout and Z8 holdout",
                    "overlap-vs-plain seam diagnostics from eval_overlap > 0",
                    "100 percent crop dashboard with worst rows, not only aggregate medians",
                    "editable DNG and GPR packaging/openability receipts",
                    "rendered latitude review from the full 351-row/EV review target",
                    "timing and memory receipt for the offline still path",
                    "scoreboard rebuild and premium still-SR gate receipt if the gates pass",
                ],
                "promotion_reject_conditions": [
                    f"either X2D or Z8 holdout median raw-residual MAE recovery is below {mae_threshold:.1f}%",
                    "any severe worst-row regression in editable/raw-editor or rendered-latitude review",
                    "the receipt reports source raw, source HF, REF, or JPEG target content as runtime input",
                    "overlap/seam diagnostics expose tile-boundary artifacts",
                    "the deduplicated target hash, checkpoint hash, config, and dashboard are not recorded",
                ],
            },
            "minimum_viable_next_pass": {
                "must_change_from_failed_contract": [
                    "use a full-image, full-crop, or otherwise structured context representation that is not reducible to independent local crop statistics",
                    "add a materially stronger learned detail prior, teacher-distilled target, or global/contextual objective instead of only increasing local CNN capacity",
                    "use overlapped tile inference or full-image/TLC-style validation so window/context seams and long-range placement errors are visible before promotion",
                    "condition on camera/noise and measured or modeled PSF metadata where available, rather than treating all resize/detail residuals as one distribution",
                    "treat a global near-box PSF as a negative/control input unless the sidecar has row-level or camera-specific kernel variation",
                    "treat denoising, deblurring/PSF, and SR as one raw-restoration objective while keeping the final emitted file editable raw",
                    "preserve sensor-pattern alignment for noise and CFA detail features instead of mixing Bayer phases in RGB space before the raw gate",
                    "select checkpoints by the joint X2D plus Z8 holdout gates, not train loss or a single-camera dashboard",
                    "emit the same editable raw, rendered latitude, timing, memory, config, and noise-policy receipts required for promotion even if the result fails",
                ],
                "acceptable_first_tracks": [
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
                    "best X2D raw-CFA residual baseline",
                    "best Z8 raw-CFA residual baseline",
                    "small U-Net raw-domain probe",
                    "full-crop U-Net and gated pyramid U-Net rejection probes",
                    "matched local-CNN versus window-attention/transformer raw-restoration teacher ablation on the same deduplicated target",
                    "patch-dictionary and low-order candidate-signal rejection probes",
                ],
                "early_reject_if": [
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
                "another global near-box PSF conditioning repeat without row-level camera/resize PSF variation",
                "simple CFA one-hot or metadata plane add-on without a stronger raw-restoration objective",
                "calibrated random-HF or noise addback as a substitute for learned signal detail",
                "another local CNN width/depth/loss sweep that does not add non-local attention, stronger teacher supervision, or full-image evaluation",
            ],
            "success_gates": [
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
        f"<p>{html.escape(str(row.get('purpose')))}</p>"
        f"<p><strong>Holdout:</strong> {html.escape(str(row.get('holdout_scene')))}</p>"
        f"<pre>{html.escape(str(row.get('command')))}</pre>"
        "</section>"
        for row in execution.get("full_train_commands", [])
        if isinstance(row, dict)
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
<h3>Full train commands</h3>
<div class="grid">{full_train_commands}</div>
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
    scoreboard_path = args.scoreboard or args.external_root / "artifacts/premium_still_sr_experiment_scoreboard_20260630/scoreboard.json"
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
