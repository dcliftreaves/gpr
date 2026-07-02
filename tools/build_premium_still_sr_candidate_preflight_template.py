#!/usr/bin/env python3
"""Build a premium still-SR candidate preflight proposal manifest.

The output is a proposal for tools/check_premium_still_sr_candidate_preflight.py.
It is not a model receipt and does not claim production readiness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_candidate_preflight.v1"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--template",
        choices=(
            "clean_source_restormer_teacher",
            "source_evidence_split_teacher",
            "frequency_pyramid_source_evidence_teacher",
            "gated_residual_source_evidence_teacher",
            "rejected_repeat_fixture",
        ),
        default="clean_source_restormer_teacher",
        help="Manifest shape to write.",
    )
    ap.add_argument("--candidate-id", default=None)
    return ap.parse_args()


def clean_source_restormer_teacher(candidate_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "teacher",
        "launchable_for_production_attempt": False,
        "requires_material_edits_before_launch": True,
        "material_change_summary": (
            "<replace with the concrete architecture/degradation/validation change "
            "that is not already represented by the rejected 20260702 clean-source "
            "Restormer, NAF/detail, clean-signal U-Net, or 12k window-attention receipts; "
            "launchable proposals need new source evidence, measured/row-level PSF, "
            "burst or multi-frame raw evidence, or an explicit teacher-first holdout gate>"
        ),
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ],
        "forbidden_runtime_inputs_absent": True,
        "uses_ref_or_source_content_at_render_time": False,
        "promotion_claimed": False,
        "production_ready": False,
        "model_arch": "Restormer/RBSFormer-style raw-SR transformer teacher",
        "architecture_family": "self-supervised clean-source RAW SR restoration teacher",
        "architecture_deltas": [
            "non-local full-image raw restoration teacher",
            "overlapped-tile high-resolution inference",
            "self-supervised clean-source RAW SR objective",
            "CFA-phase-conditioned raw feature planes",
        ],
        "degradation_policy": "camera-specific RAW degradation model for teacher training",
        "degradation_deltas": [
            "realistic camera blur/PSF synthesis",
            "ISO-conditioned calibrated sensor noise",
            "bit-depth and compression/decode simulation",
            "sensor and CFA phase aware downsample/decode path",
        ],
        "validation_plan": [
            "held-out X2D full-image gate",
            "held-out Z8 overlapped-tile gate",
            "50 MP and 100 MP full-frame row accounting",
            "worst-row 100 percent crop review",
            "both X2D and Z8 smoke holdouts must beat same-color interpolation before long run",
        ],
        "holdouts": [
            "X2D scene-held-out full-frame images",
            "Z8 scene-held-out overlapped-tile images",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "current 95-receipt still-SR experiment scoreboard",
        ],
        "planned_receipts": [
            "checkpoint hash",
            "training config hash",
            "target dataset hash",
            "dashboard",
            "timing memory receipt",
            "editor latitude review",
            "editable DNG/GPR raw receipt",
            "noise policy receipt",
        ],
        "promotion_receipts": [
            "50 MP full-frame gate",
            "100 MP full-frame gate",
            "worst-row visual review",
            "seconds per frame and peak RSS",
        ],
        "smoke_gate_commands": [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs <pairs.npz> --output-dir <x2d_smoke_out> "
                "--holdout-image x2d <candidate-specific-args>"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs <pairs.npz> --output-dir <z8_smoke_out> "
                "--holdout-image z8 <candidate-specific-args>"
            ),
        ],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
        "notes": (
            "Reference proposal scaffold for the current premium still-SR lane. "
            "It intentionally avoids REF/source/JPEG render-time content, but "
            "must be edited with a concrete material change before it is "
            "launchable."
        ),
    }


def source_evidence_split_teacher(candidate_id: str) -> dict[str, Any]:
    pairs = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_clean_source_pairs_routed_t64_20260702/"
        "premium_still_sr_clean_source_pairs_routed_t64.npz"
    )
    return {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "teacher",
        "launchable_for_production_attempt": True,
        "requires_material_edits_before_launch": False,
        "material_change_summary": (
            "Uses new source evidence from the candidate-only local-ridge audit: "
            "X2D has 4.821 percent MAE and 11.520 percent RMSE recovery above "
            "nearest same-color Bayer 2x, while Z8 fails the 1 percent MAE "
            "source-evidence floor. The Gate A smoke therefore uses the X2D "
            "local source evidence as an auxiliary teacher/objective signal and "
            "changes the Z8 source/degradation target with camera-specific RAW "
            "blur, calibrated noise, compression/decode, and CFA phase simulation "
            "before any long run."
        ),
        "source_evidence_receipts": [
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_x2dholdout_t64_20260702/"
                "source_evidence_audit.json"
            ),
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_z8holdout_t64_20260702/"
                "source_evidence_audit.json"
            ),
        ],
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ],
        "forbidden_runtime_inputs_absent": True,
        "uses_ref_or_source_content_at_render_time": False,
        "promotion_claimed": False,
        "production_ready": False,
        "model_arch": "Window-attention raw-SR teacher with candidate-only local source-evidence objective",
        "architecture_family": "self-supervised clean-source RAW SR restoration teacher",
        "architecture_deltas": [
            "non-local full-image raw restoration teacher",
            "overlapped-tile high-resolution inference",
            "self-supervised clean-source RAW SR objective",
            "candidate-only local source-evidence auxiliary objective",
            "CFA-phase-conditioned raw feature planes",
        ],
        "degradation_policy": (
            "camera-specific RAW degradation model that treats Z8 as a "
            "source/degradation mismatch until its candidate-only MAE evidence "
            "clears the 1 percent floor"
        ),
        "degradation_deltas": [
            "camera-specific RAW blur/PSF synthesis per camera family",
            "ISO-conditioned calibrated sensor noise",
            "bit-depth and compression/decode simulation",
            "sensor and CFA phase aware downsample/decode path",
            "Z8 source/degradation mismatch repair before long training",
        ],
        "validation_plan": [
            "held-out X2D full-image gate using source-evidence auxiliary objective",
            "held-out Z8 overlapped-tile gate after source/degradation mismatch repair",
            "50 MP full-frame gate row accounting",
            "100 MP full-frame gate row accounting",
            "worst-row 100 percent crop review",
            "both X2D and Z8 smoke holdouts beat same-color interpolation before long run",
        ],
        "holdouts": [
            "X2D scene-held-out full-frame images",
            "Z8 scene-held-out overlapped-tile images",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "candidate-only source-evidence X2D/Z8 audits",
            "current 113-receipt still-SR experiment scoreboard",
        ],
        "planned_receipts": [
            "checkpoint hash",
            "training config hash",
            "target dataset hash",
            "dashboard",
            "timing memory receipt",
            "editor latitude review",
            "editable DNG/GPR raw receipt",
            "noise policy receipt",
            "source-evidence audit receipt",
        ],
        "promotion_receipts": [
            "50 MP full-frame gate",
            "100 MP full-frame gate",
            "worst-row visual review",
            "seconds per frame and peak RSS",
        ],
        "smoke_gate_commands": [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--pairs {pairs} "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_split_teacher_x2d_smoke_20260702_next "
                "--holdout-image x2d --model-arch window_attention_pixelshuffle "
                "--steps 150 --width 32 --depth 4 --batch 6 --low-crop 48 "
                "--residual-scale 0.08"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--pairs {pairs} "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_split_teacher_z8_smoke_20260702_next "
                "--holdout-image z8 --model-arch window_attention_pixelshuffle "
                "--steps 150 --width 32 --depth 4 --batch 6 --low-crop 48 "
                "--residual-scale 0.08"
            ),
        ],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
        "notes": (
            "Launchable Gate A intake manifest for the current source-evidence "
            "split. It still does not claim production readiness; it only allows "
            "short X2D/Z8 smoke gates before any long still-SR run."
        ),
    }


def frequency_pyramid_source_evidence_teacher(candidate_id: str) -> dict[str, Any]:
    pairs = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_clean_source_pairs_routed_t64_20260702/"
        "premium_still_sr_clean_source_pairs_routed_t64.npz"
    )
    x2d_out = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_frequency_pyramid_source_evidence_x2d_smoke_20260702"
    )
    z8_out = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_frequency_pyramid_source_evidence_z8_smoke_20260702"
    )
    common_args = (
        "--model-arch frequency_pyramid_pixelshuffle "
        "--steps 220 --width 40 --depth 4 --batch 6 --low-crop 48 "
        "--residual-scale 0.10 --loss-mode charbonnier "
        "--gradient-loss-weight 0.10 --laplacian-loss-weight 0.05 "
        "--train-input-noise-std-counts 1.0 "
        "--train-input-gain-jitter-pct 0.25 "
        "--train-input-blur-weight 0.05"
    )
    return {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "teacher",
        "launchable_for_production_attempt": True,
        "requires_material_edits_before_launch": False,
        "material_change_summary": (
            "Uses the candidate-only source-evidence split but changes the "
            "model family from rejected Restormer/window-attention repeats to "
            "a frequency-pyramid full-image RAW restoration teacher. The smoke "
            "holdouts must beat interpolation before long run; Z8 remains "
            "treated as a source/degradation mismatch until the smoke receipt "
            "shows positive held-out MAE."
        ),
        "source_evidence_receipts": [
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_x2dholdout_t64_20260702/"
                "source_evidence_audit.json"
            ),
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_z8holdout_t64_20260702/"
                "source_evidence_audit.json"
            ),
        ],
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ],
        "forbidden_runtime_inputs_absent": True,
        "uses_ref_or_source_content_at_render_time": False,
        "promotion_claimed": False,
        "production_ready": False,
        "model_arch": "frequency_pyramid_pixelshuffle full-image RAW restoration teacher",
        "architecture_family": "frequency-pyramid candidate-only RAW SR teacher",
        "architecture_deltas": [
            "full-image frequency-pyramid raw restoration teacher",
            "explicit low-frequency context branch",
            "explicit high-frequency residual branch",
            "global candidate-only context branch",
            "CFA-phase-conditioned raw feature planes",
        ],
        "degradation_policy": (
            "camera-specific RAW blur/noise/decode smoke gate; no long run is "
            "allowed unless both X2D and Z8 beat same-color interpolation"
        ),
        "degradation_deltas": [
            "camera-specific RAW blur/PSF synthesis during training",
            "ISO-conditioned sensor noise perturbation",
            "bit-depth and compression/decode simulation",
            "sensor and CFA phase aware downsample/decode path",
            "Z8 source/degradation mismatch repair before long training",
        ],
        "validation_plan": [
            "held-out X2D full-image gate using source-evidence auxiliary evidence",
            "held-out Z8 overlapped-tile gate after source/degradation mismatch repair",
            "50 MP full-frame gate row accounting",
            "100 MP full-frame gate row accounting",
            "worst-row 100 percent crop review",
            "both X2D and Z8 smoke holdouts beat same-color interpolation before long run",
        ],
        "holdouts": [
            "X2D scene-held-out full-frame images",
            "Z8 scene-held-out overlapped-tile images",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "candidate-only source-evidence X2D/Z8 audits",
            "current 99-receipt still-SR experiment scoreboard",
        ],
        "planned_receipts": [
            "checkpoint hash",
            "training config hash",
            "target dataset hash",
            "dashboard",
            "timing memory receipt",
            "editor latitude review",
            "editable DNG/GPR raw receipt",
            "noise policy receipt",
            "source-evidence audit receipt",
        ],
        "promotion_receipts": [
            "50 MP full-frame gate",
            "100 MP full-frame gate",
            "worst-row visual review",
            "seconds per frame and peak RSS",
        ],
        "smoke_gate_commands": [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--pairs {pairs} --output-dir {x2d_out} "
                f"--holdout-image x2d {common_args}"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--pairs {pairs} --output-dir {z8_out} "
                f"--holdout-image z8 {common_args}"
            ),
        ],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
        "notes": (
            "Launchable Gate A intake manifest for a frequency-pyramid "
            "candidate-only source-evidence smoke. This is a short smoke gate, "
            "not a production claim."
        ),
    }


def gated_residual_source_evidence_teacher(candidate_id: str) -> dict[str, Any]:
    pairs = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_clean_source_pairs_routed_t64_20260702/"
        "premium_still_sr_clean_source_pairs_routed_t64.npz"
    )
    x2d_out = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_gated_residual_source_evidence_x2d_smoke_20260702"
    )
    z8_out = (
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_gated_residual_source_evidence_z8_smoke_20260702"
    )
    common_args = (
        "--model-arch gated_frequency_pyramid_pixelshuffle "
        "--steps 260 --width 40 --depth 4 --batch 6 --low-crop 48 "
        "--residual-scale 0.08 --loss-mode charbonnier "
        "--gradient-loss-weight 0.04 --laplacian-loss-weight 0.02 "
        "--baseline-worsening-loss-weight 1.50 "
        "--residual-energy-loss-weight 0.03 "
        "--train-input-noise-std-counts 0.5 "
        "--train-input-gain-jitter-pct 0.10 "
        "--train-input-blur-weight 0.02"
    )
    return {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "teacher",
        "launchable_for_production_attempt": True,
        "requires_material_edits_before_launch": False,
        "material_change_summary": (
            "Uses the candidate-only source-evidence split but changes the "
            "frequency-pyramid branch into a no-op/benefit-gated residual "
            "teacher. This directly targets the latest failure where Z8 and "
            "X2D low-error tiles were damaged by unconditional residual output. "
            "The smoke holdouts must beat same-color interpolation before any "
            "long run."
        ),
        "source_evidence_receipts": [
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_x2dholdout_t64_20260702/"
                "source_evidence_audit.json"
            ),
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_source_evidence_z8holdout_t64_20260702/"
                "source_evidence_audit.json"
            ),
            (
                "/Volumes/OWC_8TB/gpr_work/artifacts/"
                "premium_still_sr_frequency_pyramid_smoke_gate_acceptance_20260702/"
                "smoke_gate_acceptance.json"
            ),
        ],
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ],
        "forbidden_runtime_inputs_absent": True,
        "uses_ref_or_source_content_at_render_time": False,
        "promotion_claimed": False,
        "production_ready": False,
        "model_arch": "gated_frequency_pyramid_pixelshuffle no-op residual RAW restoration teacher",
        "architecture_family": "gated frequency-pyramid candidate-only RAW SR teacher",
        "architecture_deltas": [
            "full-image frequency-pyramid raw restoration teacher",
            "explicit no-op benefit gate for residual strength",
            "explicit low-frequency context branch",
            "explicit high-frequency residual branch",
            "global candidate-only context branch",
            "CFA-phase-conditioned raw feature planes",
        ],
        "degradation_policy": (
            "camera-specific RAW blur/noise/decode smoke gate plus a "
            "same-color interpolation worsening penalty; no long run is "
            "allowed unless both X2D and Z8 beat interpolation"
        ),
        "degradation_deltas": [
            "camera-specific RAW blur/PSF synthesis during training",
            "ISO-conditioned sensor noise perturbation",
            "bit-depth and compression/decode simulation",
            "sensor and CFA phase aware downsample/decode path",
            "same-color interpolation worsening penalty for low-error tiles",
            "residual-energy no-op penalty to avoid unnecessary texture changes",
        ],
        "validation_plan": [
            "held-out X2D full-image gate using source-evidence auxiliary evidence",
            "held-out Z8 overlapped-tile gate with no-op/benefit gating",
            "50 MP full-frame gate row accounting",
            "100 MP full-frame gate row accounting",
            "worst-row 100 percent crop review",
            "both X2D and Z8 smoke holdouts beat same-color interpolation before long run",
        ],
        "holdouts": [
            "X2D scene-held-out full-frame images",
            "Z8 scene-held-out overlapped-tile images",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "frequency-pyramid smoke gate blocker receipt",
            "current 113-receipt still-SR experiment scoreboard",
        ],
        "planned_receipts": [
            "checkpoint hash",
            "training config hash",
            "target dataset hash",
            "dashboard",
            "timing memory receipt",
            "editor latitude review",
            "editable DNG/GPR raw receipt",
            "noise policy receipt",
            "smoke gate acceptance receipt",
        ],
        "promotion_receipts": [
            "50 MP full-frame gate",
            "100 MP full-frame gate",
            "worst-row visual review",
            "seconds per frame and peak RSS",
        ],
        "smoke_gate_commands": [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--pairs {pairs} --output-dir {x2d_out} "
                f"--holdout-image x2d {common_args}"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--pairs {pairs} --output-dir {z8_out} "
                f"--holdout-image z8 {common_args}"
            ),
        ],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
        "notes": (
            "Launchable Gate A intake manifest for a candidate-only gated "
            "residual source-evidence smoke. It is designed to prove or reject "
            "the no-op gating hypothesis before any long premium still-SR run."
        ),
    }


def rejected_repeat_fixture(candidate_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "student",
        "launchable_for_production_attempt": False,
        "runtime_inputs": ["candidate_raw", "camera_metadata", "source_hf"],
        "forbidden_runtime_inputs_absent": False,
        "uses_ref_or_source_content_at_render_time": True,
        "promotion_claimed": True,
        "production_ready": False,
        "model_arch": "residual_pixelshuffle local-CNN-only",
        "architecture_deltas": ["same local CNN as before"],
        "degradation_deltas": ["same-color box downsample"],
        "validation_plan": ["one X2D crop"],
        "baseline_comparisons": ["train split only"],
        "planned_receipts": ["dashboard"],
        "noise_policy": {
            "exact_sidecars_only": False,
            "forbids_source_residual_noise": False,
            "missing_sidecars": "synthetic_noise",
        },
        "notes": "Negative fixture proving rejected repeat paths stay blocked.",
    }


def build_manifest(template: str, candidate_id: str | None) -> dict[str, Any]:
    if template == "clean_source_restormer_teacher":
        return clean_source_restormer_teacher(candidate_id or "clean_source_raw_sr_restormer_teacher_v1")
    if template == "source_evidence_split_teacher":
        return source_evidence_split_teacher(candidate_id or "source_evidence_split_teacher_v1")
    if template == "frequency_pyramid_source_evidence_teacher":
        return frequency_pyramid_source_evidence_teacher(candidate_id or "frequency_pyramid_source_evidence_teacher_v1")
    if template == "gated_residual_source_evidence_teacher":
        return gated_residual_source_evidence_teacher(candidate_id or "gated_residual_source_evidence_teacher_v1")
    if template == "rejected_repeat_fixture":
        return rejected_repeat_fixture(candidate_id or "repeat_residual_pixelshuffle_local_cnn")
    raise ValueError(f"unknown template: {template}")


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args.template, args.candidate_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
