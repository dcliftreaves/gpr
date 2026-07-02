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
        choices=("clean_source_restormer_teacher", "rejected_repeat_fixture"),
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
