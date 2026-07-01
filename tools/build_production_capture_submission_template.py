#!/usr/bin/env python3
"""Build a fill-in template for production capture submissions."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "docs" / "PRODUCTION_CAPTURE_REQUIREMENTS.json"
SCHEMA = "gpr.production_capture_submission.v1"
SHA_PLACEHOLDER = "<64_hex_sha256>"
SUBMISSION_STATUSES = {"open", "blocked_on_real_camera_access"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    ap.add_argument("--output", type=Path, required=True)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def base_fixture(req: dict[str, Any]) -> dict[str, Any]:
    phase = str(req.get("required_cfa_phase") or "<CFA_PHASE>").upper()
    return {
        "source_path": f"<original_{phase.lower()}_raw_path>",
        "sha256": SHA_PLACEHOLDER,
        "make": "<camera_make>",
        "model": "<camera_model>",
        "width": "<raw_width>",
        "height": "<raw_height>",
        "cfa_phase": phase,
        "bit_depth": "<bits_per_sample>",
        "black_level": "<black_level>",
        "white_level": "<white_level>",
        "iso": "<iso>",
        "original_camera_raw": True,
        "linear_raw": False,
        "metadata_receipt_path": "<metadata_or_inventory_receipt.json>",
        "metadata_receipt_sha256": SHA_PLACEHOLDER,
    }


def darkframe_row(req: dict[str, Any], idx: int) -> dict[str, Any]:
    camera = str(req.get("camera") or "<camera>")
    return {
        "source_path": f"<{camera.lower().replace(' ', '_')}_darkframe_{idx}.dng>",
        "sha256": SHA_PLACEHOLDER,
        "make": "<camera_make>",
        "model": "<camera_model>",
        "width": "<raw_width>",
        "height": "<raw_height>",
        "cfa_phase": "<CFA_PHASE>",
        "bit_depth": "<bits_per_sample>",
        "black_level": "<black_level>",
        "white_level": "<white_level>",
        "iso": "<iso>",
        "exposure": "<exposure_time>",
        "source_kind": "confirmed_darkframes",
        "extracted_bayer_path": f"<darkframe_{idx}_u16_bayer.raw>",
        "extracted_bayer_sha256": SHA_PLACEHOLDER,
        "extract_receipt_path": f"<darkframe_{idx}_extract_receipt.json>",
        "extract_receipt_sha256": SHA_PLACEHOLDER,
        "no_scene_signal": True,
        "capture_setup": "<lens_cap_or_dark_bag_or_equivalent_no_light_setup>",
        "proof": "<brief_no_scene_signal_proof_or_capture_log_reference>",
        "linear_raw": False,
    }


def camera_role_template() -> dict[str, Any]:
    return {
        "target_role": "camera",
        "source_kind": "real_sensor_dma",
        "valid_gvid": True,
        "dropped_frames": 0,
        "source_width": 4096,
        "source_height": 3072,
        "source_fps": "<measured_source_fps>",
        "encode_fps": "<measured_encode_fps>",
        "storage_medium": "<Mission_1_SD_or_internal_storage_label>",
        "storage_write_mb_s": "<measured_storage_write_MB_per_s>",
        "storage_budget_passed": True,
        "peak_rss_mb": "<peak_resident_set_MB>",
        "preview_width": 1024,
        "preview_height": 768,
        "preview_fps": "<measured_preview_fps>",
        "preview_full_frame": True,
        "gvid_path": "<camera_output.gvid>",
        "gvid_sha256": SHA_PLACEHOLDER,
        "receipts": {
            "target_preflight_receipt": {"path": "<target_preflight_receipt.json>", "sha256": SHA_PLACEHOLDER},
            "labs_target_bench": {"path": "<labs_target_bench.json>", "sha256": SHA_PLACEHOLDER},
            "camera_handoff_receipt": {"path": "<camera_handoff_receipt.json>", "sha256": SHA_PLACEHOLDER},
            "preview_decode_receipt": {"path": "<preview_decode_1024x768/receipt.json>", "sha256": SHA_PLACEHOLDER},
            "preview_ui_receipt": {"path": "<preview_ui_receipt.json>", "sha256": SHA_PLACEHOLDER},
            "mission1_camera_closure_run": {"path": "<mission1_camera_closure_run.json>", "sha256": SHA_PLACEHOLDER},
        },
    }


def psf_pair(idx: int, *, negative: bool = False) -> dict[str, Any]:
    stem = "negative_control" if negative else f"controlled_pair_{idx}"
    return {
        "id": stem,
        "high_source_path": f"<{stem}_high_8192x6144.dng>",
        "low_source_path": f"<{stem}_low_4096x3072.dng>",
        "high_source_sha256": SHA_PLACEHOLDER,
        "low_source_sha256": SHA_PLACEHOLDER,
        "high_bayer_path": f"<{stem}_high_8192x6144_u16.raw>",
        "low_bayer_path": f"<{stem}_low_4096x3072_u16.raw>",
        "high_bayer_sha256": SHA_PLACEHOLDER,
        "low_bayer_sha256": SHA_PLACEHOLDER,
        "high_extract_receipt_path": f"<{stem}_high_extract_receipt.json>",
        "low_extract_receipt_path": f"<{stem}_low_extract_receipt.json>",
        "high_extract_receipt_sha256": SHA_PLACEHOLDER,
        "low_extract_receipt_sha256": SHA_PLACEHOLDER,
        "high_width": 8192,
        "high_height": 6144,
        "low_width": 4096,
        "low_height": 3072,
        "high_bayer_bytes": 100663296,
        "low_bayer_bytes": 25165824,
        "cfa_phase": "<CFA_PHASE>",
        "iso": "<fixed_iso>",
        "exposure": "<fixed_exposure_time>",
        "white_balance": "<fixed_white_balance>",
        "lens_mode": "<fixed_lens_mode>",
        "stabilization": "<fixed_stabilization_state>",
        "sharpening": "<fixed_sharpening_state>",
        "lens_correction": "<fixed_lens_correction_state>",
        "fixed_settings": not negative,
        "static_scene": not negative,
        "accepted_by_measurement": not negative,
        "rejected_by_measurement": negative,
        "rejection_reason": "<alignment_or_scene_mismatch>" if negative else "",
        "negative_control": negative,
        "expected_reject": negative,
        "settings_receipt_path": f"<{stem}_settings_receipt.json>",
        "settings_receipt_sha256": SHA_PLACEHOLDER,
        "measurement_receipt_path": f"<{stem}_measurement_receipt.json>",
        "measurement_receipt_sha256": SHA_PLACEHOLDER,
    }


def premium_still_sr_template() -> dict[str, Any]:
    return {
        "checkpoint_path": "<checkpoint.pt>",
        "checkpoint_sha256": SHA_PLACEHOLDER,
        "training_config_path": "<training_config.json>",
        "training_config_sha256": SHA_PLACEHOLDER,
        "training_target_path": "<training_targets.npz>",
        "training_target_sha256": SHA_PLACEHOLDER,
        "editable_raw_receipt_path": "<editable_raw_receipt.json>",
        "editable_raw_receipt_sha256": SHA_PLACEHOLDER,
        "review_dashboard_path": "<dashboard/index.html>",
        "review_dashboard_sha256": SHA_PLACEHOLDER,
        "timing_memory_receipt_path": "<timing_memory_receipt.json>",
        "timing_memory_receipt_sha256": SHA_PLACEHOLDER,
        "noise_policy_receipt_path": "<noise_policy_receipt.json>",
        "noise_policy_receipt_sha256": SHA_PLACEHOLDER,
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ],
        "full_frame_gate_50mp_passed": True,
        "full_frame_gate_100mp_passed": True,
        "full_frame_gate_50mp_row_count": "<50mp_gate_row_count>",
        "full_frame_gate_100mp_row_count": "<100mp_gate_row_count>",
        "median_mae_reduction_pct_50mp": "<median_mae_reduction_pct_50mp>",
        "median_mae_reduction_pct_100mp": "<median_mae_reduction_pct_100mp>",
        "worst_row_mae_reduction_pct_50mp": "<worst_row_mae_reduction_pct_50mp>",
        "worst_row_mae_reduction_pct_100mp": "<worst_row_mae_reduction_pct_100mp>",
        "editor_latitude_passed": True,
        "no_ref_runtime": True,
        "beats_current_baseline": True,
        "severe_worst_row_failures": False,
        "render_seconds_per_50mp_frame": "<render_seconds_per_50mp_frame>",
        "render_seconds_per_100mp_frame": "<render_seconds_per_100mp_frame>",
        "peak_rss_gb": "<peak_rss_gb>",
        "noise_policy_exact_sidecars_only": True,
        "noise_policy_forbids_source_residual_noise": True,
    }


def requirement_template(req: dict[str, Any]) -> dict[str, Any]:
    rid = str(req.get("id") or "")
    sample_type = req.get("sample_type")
    row: dict[str, Any] = {
        "id": rid,
        "pillar": req.get("pillar"),
        "sample_type": sample_type,
        "_instructions": req.get("required_evidence") or [],
        "_validation_commands": req.get("validation_commands") or [],
    }
    if sample_type == "real_camera_raw_fixture":
        row["evidence"] = [base_fixture(req)]
    elif sample_type == "darkframe_stack":
        count = int(req.get("minimum_count") or 4)
        row["source_provenance_audit_path"] = "<darkframe_source_provenance_audit.json>"
        row["source_provenance_audit_sha256"] = SHA_PLACEHOLDER
        row["source_provenance_audit_schema"] = "gpr.darkframe_source_provenance_audit.v1"
        row["source_provenance_audit_ready_frame_count"] = count
        row["source_provenance_audit_production_ready"] = True
        row["evidence"] = [darkframe_row(req, idx) for idx in range(count)]
    elif sample_type == "camera_hardware_receipt":
        row.update(camera_role_template())
    elif sample_type == "controlled_same_scene_high_low_raw_pair_stack":
        pair_count = int(req.get("minimum_pair_count") or 3)
        row["pairs"] = [psf_pair(idx) for idx in range(pair_count)]
        row["pairs"].append(psf_pair(99, negative=True))
    elif sample_type == "model_promotion_receipt":
        row.update(premium_still_sr_template())
    else:
        row["_unsupported_sample_type"] = sample_type
    return row


def build_template(requirements: dict[str, Any], requirements_path: Path) -> dict[str, Any]:
    req_rows = [
        row
        for row in requirements.get("requirements") or []
        if isinstance(row, dict) and str(row.get("status")) in SUBMISSION_STATUSES
    ]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_requirements": requirements_path.as_posix(),
        "notes": [
            "Fill every placeholder before running tools/check_production_capture_submission.py.",
            "All source and receipt hashes must be lowercase or uppercase 64-character SHA-256 hex strings.",
            "Leave no-scene-signal and camera-role booleans true only after the corresponding capture or receipt proves them.",
            "Artifacts should live under /Volumes/OWC_8TB/gpr_work or a bundled handoff root with stable hashes.",
        ],
        "requirements": [requirement_template(row) for row in req_rows],
    }


def main() -> int:
    args = parse_args()
    data = build_template(load_json(args.requirements), args.requirements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
