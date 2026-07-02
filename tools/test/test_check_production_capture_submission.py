#!/usr/bin/env python3
"""Regression-test production capture submission manifest validation."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_production_capture_submission.py"
SHA = "a" * 64
SHA_B = "b" * 64


def path_hash_key(key: str) -> str | None:
    if key == "source_path":
        return "sha256"
    if key == "gvid_path":
        return "gvid_sha256"
    if key.endswith("_path"):
        return f"{key[:-5]}_sha256"
    return None


def materialize_path_hashes(value, bundle: Path, counter: list[int]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            counter[0] += 1
            rel = Path("evidence") / f"{counter[0]:03d}_path.bin"
            full = bundle / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            payload = f"path:{counter[0]}\n".encode("utf-8")
            full.write_bytes(payload)
            value["path"] = rel.as_posix()
            value["sha256"] = hashlib.sha256(payload).hexdigest()
        for key in list(value):
            hash_key = path_hash_key(key)
            if hash_key and isinstance(value.get(hash_key), str):
                counter[0] += 1
                rel = Path("evidence") / f"{counter[0]:03d}_{key}.bin"
                full = bundle / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                payload = f"{key}:{counter[0]}\n".encode("utf-8")
                full.write_bytes(payload)
                value[key] = rel.as_posix()
                value[hash_key] = hashlib.sha256(payload).hexdigest()
            materialize_path_hashes(value[key], bundle, counter)
    elif isinstance(value, list):
        for item in value:
            materialize_path_hashes(item, bundle, counter)


def write_darkframe_audits(submission: dict, bundle: Path) -> None:
    for record in submission["requirements"]:
        if record["id"] not in {"mission1_darkframe_stack", "iphone_cfa_darkframe_stack"}:
            continue
        frames = []
        for idx, row in enumerate(record["evidence"]):
            frames.append(
                {
                    "index": idx,
                    "raw_sha256": row["extracted_bayer_sha256"],
                    "original_sha256": row["sha256"],
                    "extract_receipt_sha256": row["extract_receipt_sha256"],
                    "ready": True,
                    "linear_raw": False,
                }
            )
        audit = {
            "schema": "gpr.darkframe_source_provenance_audit.v1",
            "production_ready": True,
            "ready_frame_count": len(frames),
            "frames": frames,
        }
        path = bundle / record["source_provenance_audit_path"]
        path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        record["source_provenance_audit_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        first = record["evidence"][0]
        sidecar = {
            "schema": "gpr.camera_noise_calibration.v1",
            "camera": {
                "make": first["make"],
                "model": first["model"],
                "width": first["width"],
                "height": first["height"],
                "bit_depth": first["bit_depth"],
                "cfa_phase": first["cfa_phase"],
                "black_level": first["black_level"],
                "white_level": first["white_level"],
            },
            "calibrations": [
                {
                    "iso": first["iso"],
                    "calibration_method": "darkframe_stack_per_plane_sigma_v1",
                    "source_kind": "darkframes",
                    "sample_count": len(record["evidence"]),
                    "source": {
                        "path": "raw_stack:test_fixture",
                        "sha256": SHA,
                        "frame_count": len(record["evidence"]),
                        "frames": [
                            {
                                "raw_path": row["extracted_bayer_path"],
                                "raw_sha256": row["extracted_bayer_sha256"],
                                "original_path": row["source_path"],
                                "original_sha256": row["sha256"],
                                "extract_receipt": row["extract_receipt_path"],
                                "no_scene_signal": True,
                                "capture_setup": row["capture_setup"],
                                "source_provenance_ready": True,
                                "source_provenance_failure": None,
                            }
                            for row in record["evidence"]
                        ],
                        "source_provenance_manifest": "darkframe_source_provenance.json",
                    },
                    "per_plane": {
                        "r": {"mean_black": 64.0, "sigma_black": 1.0, "noise_profile_offset": 0.000001},
                        "g1": {"mean_black": 64.0, "sigma_black": 1.0, "noise_profile_offset": 0.000001},
                        "b": {"mean_black": 64.0, "sigma_black": 1.0, "noise_profile_offset": 0.000001},
                        "g2": {"mean_black": 64.0, "sigma_black": 1.0, "noise_profile_offset": 0.000001},
                    },
                    "noise_signal_audit": {
                        "separates_noise_from_signal": True,
                        "method": "darkframe_stack_sigma",
                        "source_provenance_required": True,
                        "source_provenance_ready": True,
                        "source_provenance_manifest_present": True,
                    },
                    "usable_for_training_targets": True,
                }
            ],
            "production_ready": True,
        }
        sidecar_path = bundle / record["camera_noise_sidecar_path"]
        sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        record["camera_noise_sidecar_sha256"] = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()


def write_camera_role_receipts(submission: dict, bundle: Path) -> None:
    record = next(row for row in submission["requirements"] if row["id"] == "mission1_camera_role_receipts")
    receipts = record["receipts"]
    gvid_sha = record["gvid_sha256"]
    source_provenance = {
        "available": True,
        "policy": "source_tree_digest_v1",
        "sha256": "c" * 64,
        "file_count": 4,
        "total_bytes": 4096,
    }

    def write_receipt(name: str, payload: dict) -> None:
        path = bundle / receipts[name]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        receipts[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    write_receipt(
        "target_preflight_receipt",
        {
            "schema": "gpr.mission1_camera_target_preflight.v1",
            "target": {"name": "Mission 1", "role": "camera"},
            "verdict": {"target_preflight_ready": True, "camera_closure_possible": True},
            "blockers": [],
        },
    )
    write_receipt(
        "labs_target_bench",
        {
            "schema": "gpr_labs_target_bench.v1",
            "source_provenance": source_provenance,
            "target": {"name": "Mission 1", "fps": 20.0, "actual_wall_fps": 20.8},
            "capture": {
                "source_width": 4096,
                "source_height": 3072,
                "capture_width": 4096,
                "capture_height": 3072,
                "pixel_format": 1,
                "frames_written": 120,
                "dropped_frames": 0,
            },
            "gvid": {"sha256": gvid_sha, "validation": {"valid": True, "frame_count": 120}},
            "verdict": {"target_evidence": True},
        },
    )
    write_receipt(
        "camera_handoff_receipt",
        {
            "schema": "gpr_labs_camera_handoff_receipt.v1",
            "source_provenance": source_provenance,
            "target": {"name": "Mission 1", "role": "camera"},
            "integration": {
                "raw_source_kind": "sensor_dma_capture",
                "frame_source": "Mission 1 sensor DMA Bayer frame callback",
                "memory_ownership": "firmware owns input until encoder return",
                "write_path": "Mission 1 firmware SD writer",
                "sensor_dma_handoff": {"executed": True},
                "storage_handoff": {
                    "executed": True,
                    "medium": "Mission 1 SD card writer",
                    "ownership": "firmware storage queue",
                },
            },
            "input_frame": {
                "width": 4096,
                "height": 3072,
                "stride_bytes": 8192,
                "bit_depth": 14,
                "pixel_format": 1,
                "target_fps": 20.0,
            },
            "capture": {"frames_requested": 120, "frames_written": 120, "dropped_frames": 0},
            "timing": {"fps_median": 20.5, "median_ms": 48.7, "p95_ms": 50.0, "p99_ms": 52.0},
            "storage": {"write_mb_s": 126.0, "flush_policy": "firmware storage completion"},
            "memory": {"rss_kb": 393216},
            "output": {"sha256": gvid_sha, "validation": {"valid": True, "frame_count": 120}},
            "interruption_recovery": {"proven": True, "validator_rejects_truncated": True},
            "verdict": {
                "firmware_ready": True,
                "target_evidence": True,
                "fps_target_met": True,
                "no_drops": True,
            },
        },
    )
    write_receipt(
        "preview_decode_receipt",
        {
            "schema": "gvid_decode_target_bench.v1",
            "gvid_sha256": gvid_sha,
            "sensor_width": 4096,
            "sensor_height": 3072,
            "raw_target": "mission1_preview_4x_1024x768",
            "frame_count": 120,
            "summary": {
                "decode_plus_target": {"n": 120, "fps_median": 43.0},
                "actual_wall_fps_including_extract_process": 21.0,
                "dims": [[1024, 768]],
            },
            "rows": [
                {
                    "frame_index": 0,
                    "decode_width": 1024,
                    "decode_height": 768,
                    "width": 1024,
                    "height": 768,
                }
            ],
        },
    )
    write_receipt(
        "preview_ui_receipt",
        {
            "schema": "gpr_labs_preview_ui_receipt.v1",
            "source_provenance": source_provenance,
            "target": {"name": "Mission 1", "role": "camera"},
            "source": {
                "width": 4096,
                "height": 3072,
                "frame_count": 120,
                "bit_depth": 14,
                "pixel_format": 1,
                "gvid_sha256": gvid_sha,
            },
            "preview": {
                "width": 1024,
                "height": 768,
                "frame_count": 120,
                "target_fps": 20.0,
                "full_frame_downsample": True,
                "color_pipeline": "camera-wb + lightweight preview tone",
                "tone_pipeline": "fixed preview tone curve",
            },
            "integration": {
                "ui_path_executed": True,
                "decode_path": "gvid preview RGB stream",
                "presentation_path": "Mission 1 rear display compositor",
                "buffer_ownership": "camera UI owns preview buffer through display present",
                "display_surface": "Mission 1 rear display",
            },
            "timing": {"fps_median": 21.0, "median_ms": 47.6, "p95_ms": 49.0, "p99_ms": 51.0},
            "memory": {"rss_kb": 65536},
            "validation": {"output_valid": True, "no_drops": True, "visual_checked": True},
            "verdict": {"ui_ready": True, "target_evidence": True, "fps_target_met": True},
        },
    )
    write_receipt(
        "mission1_camera_closure_run",
        {
            "schema": "gpr.mission1_camera_closure_run.v1",
            "receipts": {
                "target_bench": receipts["labs_target_bench"]["path"],
                "target_preflight": receipts["target_preflight_receipt"]["path"],
                "camera_handoff": receipts["camera_handoff_receipt"]["path"],
                "preview_decode": receipts["preview_decode_receipt"]["path"],
                "preview_ui": receipts["preview_ui_receipt"]["path"],
            },
            "steps": [
                {"name": "validate_camera_handoff_receipt", "returncode": 0},
                {"name": "validate_preview_ui_receipt", "returncode": 0},
            ],
            "verdict": {
                "production_ready": True,
                "target_preflight_ready": True,
                "camera_closure_possible": True,
                "firmware_ready": True,
                "ui_ready": True,
                "aggregate_consistency_ready": True,
                "handoff_blocker": None,
                "preview_blocker": None,
            },
        },
    )


def write_premium_still_sr_receipts(submission: dict, bundle: Path) -> None:
    record = next(row for row in submission["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")

    def write_record(path_key: str, hash_key: str, payload: dict) -> None:
        path = bundle / record[path_key]
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        record[hash_key] = hashlib.sha256(path.read_bytes()).hexdigest()

    write_record(
        "candidate_preflight_manifest_path",
        "candidate_preflight_manifest_sha256",
        {
            "schema": "gpr.premium_still_sr_candidate_preflight.v1",
            "candidate_id": "fixture_candidate",
            "launchable_for_production_attempt": True,
            "smoke_gate_acceptance": {
                "baseline": "same-color Bayer interpolation",
                "required_holdouts": ["X2D", "Z8"],
            },
        },
    )
    write_record(
        "candidate_preflight_audit_path",
        "candidate_preflight_audit_sha256",
        {
            "schema": "gpr.premium_still_sr_candidate_preflight_audit.v1",
            "launchable_for_production_attempt": True,
            "production_ready": False,
            "promotion_claimed": False,
            "verdict": "launchable_preflight_passed",
            "smoke_gate_acceptance": {
                "baseline": "same-color Bayer interpolation",
                "required_holdouts": ["X2D", "Z8"],
            },
        },
    )
    write_record(
        "launch_packet_path",
        "launch_packet_sha256",
        {
            "schema": "gpr.premium_still_sr_launch_packet.v1",
            "preflight": {
                "launchable_for_production_attempt": True,
                "verdict": "launchable_preflight_passed",
            },
        },
    )
    write_record(
        "x2d_smoke_receipt_path",
        "x2d_smoke_receipt_sha256",
        {
            "holdout": "X2D",
            "baseline_comparison": "same-color Bayer interpolation",
            "checkpoint_hash": SHA,
            "training_config_hash": SHA,
            "median_mae_reduction_pct": record["x2d_smoke_median_mae_reduction_pct"],
            "worst_row_mae_reduction_pct": record["x2d_smoke_worst_row_mae_reduction_pct"],
        },
    )
    write_record(
        "z8_smoke_receipt_path",
        "z8_smoke_receipt_sha256",
        {
            "holdout": "Z8",
            "baseline_comparison": "same-color Bayer interpolation",
            "checkpoint_hash": SHA,
            "training_config_hash": SHA,
            "median_mae_reduction_pct": record["z8_smoke_median_mae_reduction_pct"],
            "worst_row_mae_reduction_pct": record["z8_smoke_worst_row_mae_reduction_pct"],
        },
    )
    write_record(
        "baseline_comparison_path",
        "baseline_comparison_sha256",
        {"baseline": "same-color Bayer interpolation", "holdouts": ["X2D", "Z8"]},
    )
    write_record(
        "still_sr_gate_receipt_path",
        "still_sr_gate_receipt_sha256",
        {
            "schema": "gpr.premium_still_sr_gate.v1",
            "candidate": {
                "pipeline_id": "fixture_candidate",
                "checkpoint_sha256": record["checkpoint_sha256"],
                "target_role": "offline_premium_still",
            },
            "fixture_summary": {
                "camera_count": 2,
                "fifty_mp_or_larger_count": 8,
                "hundred_mp_or_larger_count": 6,
                "cfa_phases": ["RGGB", "GBRG"],
            },
            "outputs": {
                "editable_dng": {
                    "path": record["editable_raw_receipt_path"],
                    "sha256": record["editable_raw_receipt_sha256"],
                },
                "editable_gpr": {
                    "path": record["editable_raw_receipt_path"],
                    "sha256": record["editable_raw_receipt_sha256"],
                },
                "review_tiff_or_prores": {
                    "path": record["review_dashboard_path"],
                    "sha256": record["review_dashboard_sha256"],
                },
                "dashboard": {
                    "path": record["review_dashboard_path"],
                    "sha256": record["review_dashboard_sha256"],
                },
            },
            "baseline_comparison": {
                "passed_gate": True,
                "worst_lpips": 0.2,
                "worst_delta_e2000": 1.0,
                "min_raw_psnr_delta_db": 0.1,
                "editor_latitude_score_delta": 0.1,
            },
            "runtime_policy": {
                "runtime_inputs": record["runtime_inputs"],
                "no_ref_runtime": True,
                "forbidden_source_content_absent": True,
            },
            "promotion_metrics": {
                "full_frame_gate_50mp_passed": record["full_frame_gate_50mp_passed"],
                "full_frame_gate_100mp_passed": record["full_frame_gate_100mp_passed"],
                "full_frame_gate_50mp_row_count": record["full_frame_gate_50mp_row_count"],
                "full_frame_gate_100mp_row_count": record["full_frame_gate_100mp_row_count"],
                "median_mae_reduction_pct_50mp": record["median_mae_reduction_pct_50mp"],
                "median_mae_reduction_pct_100mp": record["median_mae_reduction_pct_100mp"],
                "worst_row_mae_reduction_pct_50mp": record["worst_row_mae_reduction_pct_50mp"],
                "worst_row_mae_reduction_pct_100mp": record["worst_row_mae_reduction_pct_100mp"],
                "editor_latitude_passed": record["editor_latitude_passed"],
                "beats_current_baseline": record["beats_current_baseline"],
                "severe_worst_row_failures": record["severe_worst_row_failures"],
            },
            "performance": {
                "render_seconds_per_50mp_frame": record["render_seconds_per_50mp_frame"],
                "render_seconds_per_100mp_frame": record["render_seconds_per_100mp_frame"],
                "peak_rss_gb": record["peak_rss_gb"],
            },
            "noise_policy": {
                "mode": "requires_calibrated_camera_noise_sidecar",
                "raw_noise_signal_audit_passed": True,
                "exact_sidecars_only": record["noise_policy_exact_sidecars_only"],
                "forbids_source_residual_noise": record["noise_policy_forbids_source_residual_noise"],
            },
            "production_ready": True,
        },
    )
    write_record(
        "timing_memory_receipt_path",
        "timing_memory_receipt_sha256",
        {
            "schema": "gpr.premium_still_sr_timing_memory.v1",
            "performance": {
                "render_seconds_per_50mp_frame": record["render_seconds_per_50mp_frame"],
                "render_seconds_per_100mp_frame": record["render_seconds_per_100mp_frame"],
                "peak_rss_gb": record["peak_rss_gb"],
            },
        },
    )
    write_record(
        "noise_policy_receipt_path",
        "noise_policy_receipt_sha256",
        {
            "schema": "gpr.premium_still_sr_noise_policy_gate.v1",
            "production_ready": True,
            "clean_signal": {
                "policy_pass": True,
                "row_count": 12,
                "rows_with_noise_sidecars": 12,
            },
            "model_receipts": [
                {
                    "policy_pass": True,
                    "promotion_ready_claimed": True,
                    "runtime_policy": {
                        "uses_source_raw_at_runtime": False,
                        "uses_ref_or_jpeg_content_at_runtime": False,
                    },
                }
            ],
            "blockers": [],
        },
    )


def write_psf_pair_receipts(submission: dict, bundle: Path) -> None:
    record = next(row for row in submission["requirements"] if row["id"] == "controlled_mission1_psf_pairs")
    for pair in record["pairs"]:
        settings = {
            "schema": "gpr.mission1_native_psf_pair_settings.v1",
            "pair_id": pair["id"],
            "high_source_sha256": pair["high_source_sha256"],
            "low_source_sha256": pair["low_source_sha256"],
            "high_bayer_sha256": pair["high_bayer_sha256"],
            "low_bayer_sha256": pair["low_bayer_sha256"],
            "fixed_settings": True,
            "iso": pair["iso"],
            "exposure": pair["exposure"],
            "white_balance": pair["white_balance"],
            "lens_mode": pair["lens_mode"],
            "stabilization": pair["stabilization"],
            "sharpening": pair["sharpening"],
            "lens_correction": pair["lens_correction"],
        }
        settings_path = bundle / pair["settings_receipt_path"]
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        pair["settings_receipt_sha256"] = hashlib.sha256(settings_path.read_bytes()).hexdigest()
        measurement = {
            "schema": "gpr.mission1_native_psf_pair_measurement.v1",
            "pair_id": pair["id"],
            "high_bayer_sha256": pair["high_bayer_sha256"],
            "low_bayer_sha256": pair["low_bayer_sha256"],
            "high_width": pair["high_width"],
            "high_height": pair["high_height"],
            "low_width": pair["low_width"],
            "low_height": pair["low_height"],
            "high_bayer_bytes": pair["high_bayer_bytes"],
            "low_bayer_bytes": pair["low_bayer_bytes"],
        }
        if pair.get("negative_control") is True:
            measurement.update(
                {
                    "accepted_by_measurement": False,
                    "rejected_by_measurement": True,
                    "rejection_reason": pair["rejection_reason"],
                }
            )
        else:
            measurement.update(
                {
                    "accepted_by_measurement": True,
                    "rejected_by_measurement": False,
                    "alignment": {"accepted_for_kernel": True, "correlation": 0.95},
                    "tile_summary": {"sharp_edge_tile_count": 32, "texture_field_tile_count": 32},
                }
            )
        measurement_path = bundle / pair["measurement_receipt_path"]
        measurement_path.write_text(json.dumps(measurement, indent=2) + "\n", encoding="utf-8")
        pair["measurement_receipt_sha256"] = hashlib.sha256(measurement_path.read_bytes()).hexdigest()


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def fixture(phase: str) -> dict:
    return {
        "source_path": f"/captures/{phase}.dng",
        "sha256": SHA,
        "make": "Example",
        "model": "RawCam",
        "width": 4000,
        "height": 3000,
        "cfa_phase": phase,
        "bit_depth": 14,
        "black_level": 512,
        "white_level": 16383,
        "iso": 100,
        "original_camera_raw": True,
        "linear_raw": False,
    }


def darkframe(model: str, idx: int, *, iphone: bool = False) -> dict:
    return {
        "source_path": f"/captures/{model}_{idx}.dng",
        "sha256": SHA,
        "extracted_bayer_path": f"/captures/{model}_{idx}.raw",
        "extracted_bayer_sha256": SHA,
        "extract_receipt_path": f"/captures/{model}_{idx}_extract.json",
        "extract_receipt_sha256": SHA_B,
        "make": "Apple" if iphone else "GoPro",
        "model": model,
        "width": 4032,
        "height": 3024,
        "cfa_phase": "RGGB",
        "bit_depth": 12,
        "black_level": 64,
        "white_level": 4095,
        "iso": 232,
        "exposure": "1/30",
        "source_kind": "confirmed_darkframes",
        "no_scene_signal": True,
        "capture_setup": "lens cap on, camera in dark bag",
        "proof": "capture log marks this burst as darkframes",
        "linear_raw": False,
    }


def pair(idx: int, *, negative: bool = False) -> dict:
    return {
        "id": f"pair_{idx}",
        "high_source_path": f"/captures/pair_{idx}_high.dng",
        "low_source_path": f"/captures/pair_{idx}_low.dng",
        "high_source_sha256": SHA,
        "low_source_sha256": SHA_B,
        "high_bayer_path": f"/captures/pair_{idx}_high.raw",
        "low_bayer_path": f"/captures/pair_{idx}_low.raw",
        "high_bayer_sha256": SHA,
        "low_bayer_sha256": SHA_B,
        "high_extract_receipt_sha256": SHA,
        "low_extract_receipt_sha256": SHA_B,
        "settings_receipt_path": f"/captures/pair_{idx}_settings.json",
        "settings_receipt_sha256": SHA,
        "measurement_receipt_path": f"/captures/pair_{idx}_measurement.json",
        "measurement_receipt_sha256": SHA_B,
        "high_width": 8192,
        "high_height": 6144,
        "low_width": 4096,
        "low_height": 3072,
        "high_bayer_bytes": 100663296,
        "low_bayer_bytes": 25165824,
        "cfa_phase": "GBRG",
        "iso": 100,
        "exposure": "1/240",
        "white_balance": "5500K",
        "lens_mode": "wide",
        "stabilization": "off",
        "sharpening": "off",
        "lens_correction": "off",
        "fixed_settings": not negative,
        "static_scene": not negative,
        "accepted_by_measurement": not negative,
        "negative_control": negative,
        "expected_reject": negative,
        "rejected_by_measurement": negative,
        "rejection_reason": "alignment mismatch" if negative else "",
    }


def valid_submission() -> dict:
    return {
        "schema": "gpr.production_capture_submission.v1",
        "requirements": [
            {"id": "real_grbg_fixture", "evidence": [fixture("GRBG")]},
            {"id": "real_bggr_fixture", "evidence": [fixture("BGGR")]},
            {
                "id": "mission1_darkframe_stack",
                "source_provenance_audit_path": "/captures/mission1_darkframe_source_provenance_audit.json",
                "source_provenance_audit_sha256": SHA,
                "source_provenance_audit_schema": "gpr.darkframe_source_provenance_audit.v1",
                "source_provenance_audit_ready_frame_count": 4,
                "source_provenance_audit_production_ready": True,
                "camera_noise_sidecar_path": "/captures/mission1_camera_noise_sidecar.json",
                "camera_noise_sidecar_sha256": SHA,
                "evidence": [darkframe("MISSION 1", idx) for idx in range(4)],
            },
            {
                "id": "iphone_cfa_darkframe_stack",
                "source_provenance_audit_path": "/captures/iphone_darkframe_source_provenance_audit.json",
                "source_provenance_audit_sha256": SHA,
                "source_provenance_audit_schema": "gpr.darkframe_source_provenance_audit.v1",
                "source_provenance_audit_ready_frame_count": 4,
                "source_provenance_audit_production_ready": True,
                "camera_noise_sidecar_path": "/captures/iphone_camera_noise_sidecar.json",
                "camera_noise_sidecar_sha256": SHA,
                "evidence": [darkframe("iPhone 15 Pro", idx, iphone=True) for idx in range(4)],
            },
            {
                "id": "mission1_camera_role_receipts",
                "target_role": "camera",
                "source_kind": "real_sensor_dma",
                "valid_gvid": True,
                "dropped_frames": 0,
                "source_width": 4096,
                "source_height": 3072,
                "source_fps": 20.8,
                "encode_fps": 20.5,
                "storage_medium": "Lexar SILVER PLUS SD",
                "storage_write_mb_s": 126.0,
                "storage_budget_passed": True,
                "peak_rss_mb": 384.0,
                "preview_width": 1024,
                "preview_height": 768,
                "preview_fps": 21.0,
                "preview_full_frame": True,
                "gvid_path": "/captures/mission1_camera_output.gvid",
                "gvid_sha256": SHA,
                "receipts": {
                    "target_preflight_receipt": {"path": "/captures/target_preflight_receipt.json", "sha256": SHA},
                    "labs_target_bench": {"path": "/captures/labs_target_bench.json", "sha256": SHA},
                    "camera_handoff_receipt": {"path": "/captures/camera_handoff_receipt.json", "sha256": SHA},
                    "preview_decode_receipt": {
                        "path": "/captures/preview_decode_1024x768_receipt.json",
                        "sha256": SHA,
                    },
                    "preview_ui_receipt": {"path": "/captures/preview_ui_receipt.json", "sha256": SHA},
                    "mission1_camera_closure_run": {
                        "path": "/captures/mission1_camera_closure_run.json",
                        "sha256": SHA,
                    },
                },
            },
            {
                "id": "controlled_mission1_psf_pairs",
                "pairs": [pair(0), pair(1), pair(2), pair(99, negative=True)],
            },
            {
                "id": "premium_still_sr_promotion_receipts",
                "candidate_preflight_manifest_path": "/captures/candidate_preflight.json",
                "candidate_preflight_manifest_sha256": SHA,
                "candidate_preflight_audit_path": "/captures/preflight_audit.json",
                "candidate_preflight_audit_sha256": SHA,
                "candidate_preflight_launchable": True,
                "launch_packet_path": "/captures/launch_packet.json",
                "launch_packet_sha256": SHA,
                "smoke_gate_baseline": "same-color Bayer interpolation",
                "smoke_gate_required_holdouts": ["X2D", "Z8"],
                "smoke_gate_passed": True,
                "smoke_gate_long_run_blocked_if_smoke_fails": True,
                "x2d_smoke_receipt_path": "/captures/x2d_smoke_receipt.json",
                "x2d_smoke_receipt_sha256": SHA,
                "z8_smoke_receipt_path": "/captures/z8_smoke_receipt.json",
                "z8_smoke_receipt_sha256": SHA,
                "baseline_comparison_path": "/captures/baseline_comparison.json",
                "baseline_comparison_sha256": SHA,
                "still_sr_gate_receipt_path": "/captures/premium_still_sr_gate_receipt.json",
                "still_sr_gate_receipt_sha256": SHA,
                "x2d_smoke_median_mae_reduction_pct": 0.25,
                "z8_smoke_median_mae_reduction_pct": 0.5,
                "x2d_smoke_worst_row_mae_reduction_pct": 0.0,
                "z8_smoke_worst_row_mae_reduction_pct": 0.1,
                "checkpoint_sha256": SHA,
                "training_config_sha256": SHA,
                "training_target_path": "/captures/training_targets.npz",
                "training_target_sha256": SHA,
                "editable_raw_receipt_path": "/captures/editable_raw_receipt.json",
                "editable_raw_receipt_sha256": SHA,
                "review_dashboard_path": "/captures/dashboard.html",
                "review_dashboard_sha256": SHA,
                "timing_memory_receipt_path": "/captures/timing_memory_receipt.json",
                "timing_memory_receipt_sha256": SHA,
                "noise_policy_receipt_path": "/captures/noise_policy_receipt.json",
                "noise_policy_receipt_sha256": SHA,
                "runtime_inputs": [
                    "candidate_raw",
                    "camera_metadata",
                    "validated_noise_sidecar_optional",
                ],
                "full_frame_gate_50mp_passed": True,
                "full_frame_gate_100mp_passed": True,
                "full_frame_gate_50mp_row_count": 8,
                "full_frame_gate_100mp_row_count": 6,
                "median_mae_reduction_pct_50mp": 4.5,
                "median_mae_reduction_pct_100mp": 2.25,
                "worst_row_mae_reduction_pct_50mp": 0.0,
                "worst_row_mae_reduction_pct_100mp": 0.1,
                "editor_latitude_passed": True,
                "no_ref_runtime": True,
                "beats_current_baseline": True,
                "severe_worst_row_failures": False,
                "render_seconds_per_50mp_frame": 120.0,
                "render_seconds_per_100mp_frame": 310.0,
                "peak_rss_gb": 14.5,
                "noise_policy_exact_sidecars_only": True,
                "noise_policy_forbids_source_residual_noise": True,
            },
        ],
    }


def valid_release_blocking_submission() -> dict:
    data = valid_submission()
    data["requirements"] = [
        row
        for row in data["requirements"]
        if row["id"]
        in {
            "mission1_darkframe_stack",
            "iphone_cfa_darkframe_stack",
            "mission1_camera_role_receipts",
            "premium_still_sr_promotion_receipts",
        }
    ]
    return data


def run_tool(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(path), *extra],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_capture_submission_", dir=temp_root()) as td:
        work = Path(td)
        manifest = work / "submission.json"
        out_json = work / "audit.json"
        out_html = work / "audit.html"
        manifest.write_text(json.dumps(valid_submission(), indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--json-out", str(out_json), "--html-out", str(out_html))
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(out_json.read_text(encoding="utf-8"))
        assert audit["schema"] == "gpr.production_capture_submission_audit.v1"
        assert audit["all_requirements_closed"] is True
        assert audit["submission_valid"] is True
        assert audit["pass_count"] == 7
        assert audit["skip_count"] == 0
        assert audit["required_for_closure_count"] == 4
        assert audit["required_for_closure_pass_count"] == 4
        assert "Production Capture Submission Audit" in out_html.read_text(encoding="utf-8")

        release_only = valid_release_blocking_submission()
        manifest.write_text(json.dumps(release_only, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--json-out", str(out_json), "--html-out", str(out_html))
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(out_json.read_text(encoding="utf-8"))
        assert audit["all_requirements_closed"] is True
        assert audit["submission_valid"] is True
        assert audit["pass_count"] == 4
        assert audit["skip_count"] == 3
        assert audit["optional_research_fail_count"] == 0
        skipped = {row["id"] for row in audit["results"] if row["status"] == "SKIP"}
        assert skipped == {"real_grbg_fixture", "real_bggr_fixture", "controlled_mission1_psf_pairs"}

        bad = valid_submission()
        bad["requirements"][2]["evidence"] = bad["requirements"][2]["evidence"][:3]
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "mission1_darkframe_stack" in proc.stdout
        assert "need 4" in proc.stdout

        bad = valid_submission()
        bad["requirements"][2]["evidence"][0]["source_kind"] = "candidate_discovery"
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "source_kind must be confirmed_darkframes" in proc.stdout

        bad = valid_submission()
        bad["requirements"][2]["evidence"][0]["capture_setup"] = ""
        bad["requirements"][2]["evidence"][0]["proof"] = ""
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "capture_setup or proof" in proc.stdout

        bad = valid_submission()
        bad["requirements"][2]["source_provenance_audit_production_ready"] = False
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "source_provenance_audit_production_ready must be true" in proc.stdout

        bad = valid_submission()
        del bad["requirements"][2]["source_provenance_audit_path"]
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "source_provenance_audit_path" in proc.stdout

        bad = valid_submission()
        bad["requirements"][4]["target_role"] = "pi_stand_in"
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "target_role must be camera" in proc.stdout

        bad = valid_submission()
        bad["requirements"][4]["source_width"] = 3840
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "source_width must equal 4096" in proc.stdout

        bad = valid_submission()
        bad["requirements"][4]["storage_budget_passed"] = False
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "storage_budget_passed must be true" in proc.stdout

        bad = valid_submission()
        bad["requirements"][4]["storage_medium"] = "Pi 5 SSD tmpfs stand-in"
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "storage_medium must not name Pi, SSD, tmpfs, proxy, or stand-in storage" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["no_ref_runtime"] = False
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "no_ref_runtime must be true" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["runtime_inputs"].append("REF")
        bad["requirements"][6]["runtime_inputs"].append("Source_Raw")
        bad["requirements"][6]["runtime_inputs"].append("JPG-target")
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "forbidden render-time input" in proc.stdout
        assert "Source_Raw" in proc.stdout
        assert "JPG-target" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["median_mae_reduction_pct_100mp"] = 0.0
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "median_mae_reduction_pct_100mp must be > 0" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["x2d_smoke_median_mae_reduction_pct"] = 0.0
        bad["requirements"][6]["smoke_gate_required_holdouts"] = ["X2D"]
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "x2d_smoke_median_mae_reduction_pct must be > 0" in proc.stdout
        assert "smoke_gate_required_holdouts missing: z8" in proc.stdout

        bad = valid_submission()
        bad["requirements"][5]["pairs"][-1]["rejected_by_measurement"] = False
        bad["requirements"][5]["pairs"][-1]["rejection_reason"] = ""
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "negative control must set expected_reject=true" in proc.stdout

        bad = valid_release_blocking_submission()
        bad["requirements"].append(
            {
                "id": "controlled_mission1_psf_pairs",
                "pairs": [pair(0), pair(1), pair(99, negative=True)],
            }
        )
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--json-out", str(out_json))
        assert proc.returncode == 1
        audit = json.loads(out_json.read_text(encoding="utf-8"))
        assert audit["all_requirements_closed"] is True
        assert audit["submission_valid"] is False
        assert audit["optional_research_fail_count"] == 1
        assert "controlled_mission1_psf_pairs" in proc.stdout

        strict_all = valid_submission()
        psf_bundle = work / "psf_bundle"
        materialize_path_hashes(strict_all, psf_bundle, [0])
        write_darkframe_audits(strict_all, psf_bundle)
        write_camera_role_receipts(strict_all, psf_bundle)
        write_premium_still_sr_receipts(strict_all, psf_bundle)
        write_psf_pair_receipts(strict_all, psf_bundle)
        manifest.write_text(json.dumps(strict_all, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(psf_bundle), "--json-out", str(out_json))
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(out_json.read_text(encoding="utf-8"))
        assert audit["pass_count"] == 7
        assert audit["optional_research_fail_count"] == 0

        bad = json.loads(json.dumps(strict_all))
        psf = next(row for row in bad["requirements"] if row["id"] == "controlled_mission1_psf_pairs")
        bad_pair = psf["pairs"][0]
        measurement_path = psf_bundle / bad_pair["measurement_receipt_path"]
        measurement = json.loads(measurement_path.read_text(encoding="utf-8"))
        measurement["accepted_by_measurement"] = False
        measurement["alignment"]["accepted_for_kernel"] = False
        measurement["tile_summary"]["sharp_edge_tile_count"] = 0
        measurement_path.write_text(json.dumps(measurement, indent=2) + "\n", encoding="utf-8")
        bad_pair["measurement_receipt_sha256"] = hashlib.sha256(measurement_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(psf_bundle))
        assert proc.returncode == 1
        assert "measurement_receipt accepted_by_measurement must be true" in proc.stdout
        assert "measurement_receipt alignment.accepted_for_kernel must be true" in proc.stdout
        assert "measurement_receipt tile_summary.sharp_edge_tile_count must be > 0" in proc.stdout

        strict = valid_release_blocking_submission()
        bundle = work / "bundle"
        materialize_path_hashes(strict, bundle, [0])
        write_darkframe_audits(strict, bundle)
        write_camera_role_receipts(strict, bundle)
        write_premium_still_sr_receipts(strict, bundle)
        manifest.write_text(json.dumps(strict, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        bad = json.loads(json.dumps(strict))
        camera = next(row for row in bad["requirements"] if row["id"] == "mission1_camera_role_receipts")
        handoff_path = bundle / camera["receipts"]["camera_handoff_receipt"]["path"]
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff["target"]["role"] = "stand-in"
        handoff["integration"]["raw_source_kind"] = "file_standin"
        handoff["verdict"]["firmware_ready"] = False
        handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
        camera["receipts"]["camera_handoff_receipt"]["sha256"] = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "camera_handoff_receipt target.role must be camera" in proc.stdout
        assert "camera_handoff_receipt integration.raw_source_kind must be sensor_dma_capture or camera_ring_buffer" in proc.stdout
        write_camera_role_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        camera = next(row for row in bad["requirements"] if row["id"] == "mission1_camera_role_receipts")
        target_bench_path = bundle / camera["receipts"]["labs_target_bench"]["path"]
        target_bench = json.loads(target_bench_path.read_text(encoding="utf-8"))
        target_bench["gvid"]["validation"]["valid"] = False
        target_bench["gvid"]["validation"]["frame_count"] = 119
        target_bench_path.write_text(json.dumps(target_bench, indent=2) + "\n", encoding="utf-8")
        camera["receipts"]["labs_target_bench"]["sha256"] = hashlib.sha256(target_bench_path.read_bytes()).hexdigest()
        handoff_path = bundle / camera["receipts"]["camera_handoff_receipt"]["path"]
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff["output"]["validation"]["frame_count"] = 119
        handoff_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
        camera["receipts"]["camera_handoff_receipt"]["sha256"] = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "labs_target_bench gvid.validation.valid must be true" in proc.stdout
        assert "labs_target_bench gvid.validation.frame_count must match capture.frames_written" in proc.stdout
        assert "camera_handoff_receipt output.validation.frame_count must match capture.frames_written" in proc.stdout
        write_camera_role_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        camera = next(row for row in bad["requirements"] if row["id"] == "mission1_camera_role_receipts")
        preview_decode_path = bundle / camera["receipts"]["preview_decode_receipt"]["path"]
        preview_decode = json.loads(preview_decode_path.read_text(encoding="utf-8"))
        preview_decode["summary"]["dims"] = [[960, 720]]
        preview_decode["summary"]["decode_plus_target"]["fps_median"] = 12.0
        preview_decode_path.write_text(json.dumps(preview_decode, indent=2) + "\n", encoding="utf-8")
        camera["receipts"]["preview_decode_receipt"]["sha256"] = hashlib.sha256(
            preview_decode_path.read_bytes()
        ).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "preview_decode_receipt summary.dims must be [[1024, 768]]" in proc.stdout
        assert "preview_decode_receipt summary.decode_plus_target.fps_median must be >= 20" in proc.stdout
        write_camera_role_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        camera = next(row for row in bad["requirements"] if row["id"] == "mission1_camera_role_receipts")
        preview_ui_path = bundle / camera["receipts"]["preview_ui_receipt"]["path"]
        preview_ui = json.loads(preview_ui_path.read_text(encoding="utf-8"))
        preview_ui["source_provenance"]["sha256"] = "d" * 64
        preview_ui_path.write_text(json.dumps(preview_ui, indent=2) + "\n", encoding="utf-8")
        camera["receipts"]["preview_ui_receipt"]["sha256"] = hashlib.sha256(preview_ui_path.read_bytes()).hexdigest()
        closure_path = bundle / camera["receipts"]["mission1_camera_closure_run"]["path"]
        closure = json.loads(closure_path.read_text(encoding="utf-8"))
        closure["receipts"]["preview_ui"] = "stale_preview_ui_receipt.json"
        closure["steps"][1]["returncode"] = 1
        closure_path.write_text(json.dumps(closure, indent=2) + "\n", encoding="utf-8")
        camera["receipts"]["mission1_camera_closure_run"]["sha256"] = hashlib.sha256(closure_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "preview_ui_receipt source_provenance.sha256 must match camera_handoff_receipt" in proc.stdout
        assert "mission1_camera_closure_run receipts.preview_ui must match submitted preview_ui receipt path" in proc.stdout
        assert "mission1_camera_closure_run validate_preview_ui_receipt must return 0" in proc.stdout
        write_camera_role_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        premium = next(row for row in bad["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        preflight_manifest_path = bundle / premium["candidate_preflight_manifest_path"]
        preflight_manifest = json.loads(preflight_manifest_path.read_text(encoding="utf-8"))
        preflight_manifest["launchable_for_production_attempt"] = False
        preflight_manifest_path.write_text(json.dumps(preflight_manifest, indent=2) + "\n", encoding="utf-8")
        premium["candidate_preflight_manifest_sha256"] = hashlib.sha256(preflight_manifest_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "candidate_preflight_manifest launchable_for_production_attempt must be true" in proc.stdout
        write_premium_still_sr_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        premium = next(row for row in bad["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        baseline_path = bundle / premium["baseline_comparison_path"]
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline["baseline"] = "nearest-neighbor raw copy"
        baseline["holdouts"] = ["X2D"]
        baseline_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        premium["baseline_comparison_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "baseline_comparison baseline must be same-color Bayer interpolation" in proc.stdout
        assert "baseline_comparison missing holdout(s): z8" in proc.stdout
        write_premium_still_sr_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        premium = next(row for row in bad["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        timing_path = bundle / premium["timing_memory_receipt_path"]
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        timing["performance"]["render_seconds_per_100mp_frame"] = -1.0
        timing_path.write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
        premium["timing_memory_receipt_sha256"] = hashlib.sha256(timing_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "timing_memory_receipt render_seconds_per_100mp_frame must be > 0" in proc.stdout
        write_premium_still_sr_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        premium = next(row for row in bad["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        noise_path = bundle / premium["noise_policy_receipt_path"]
        noise = json.loads(noise_path.read_text(encoding="utf-8"))
        noise["production_ready"] = False
        noise["clean_signal"]["policy_pass"] = False
        noise["blockers"] = ["diagnostic model only"]
        noise_path.write_text(json.dumps(noise, indent=2) + "\n", encoding="utf-8")
        premium["noise_policy_receipt_sha256"] = hashlib.sha256(noise_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "noise_policy_receipt production_ready must be true" in proc.stdout
        assert "noise_policy_receipt clean_signal.policy_pass must be true" in proc.stdout
        write_premium_still_sr_receipts(strict, bundle)

        bad = json.loads(json.dumps(strict))
        premium = next(row for row in bad["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        gate_path = bundle / premium["still_sr_gate_receipt_path"]
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        gate["promotion_metrics"]["median_mae_reduction_pct_50mp"] = -2.0
        gate["runtime_policy"]["no_ref_runtime"] = False
        gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
        premium["still_sr_gate_receipt_sha256"] = hashlib.sha256(gate_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "still_sr_gate_receipt production_ready still-SR requires runtime_policy.no_ref_runtime=true" in proc.stdout
        assert "still_sr_gate_receipt promotion_metrics.median_mae_reduction_pct_50mp must match submitted" in proc.stdout
        write_premium_still_sr_receipts(strict, bundle)

        bad = json.loads(manifest.read_text(encoding="utf-8"))
        bad["requirements"][0]["evidence"][0]["sha256"] = SHA
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "sha256 mismatch" in proc.stdout

        bad = json.loads(manifest.read_text(encoding="utf-8"))
        bad["requirements"][0]["evidence"][0]["sha256"] = strict["requirements"][0]["evidence"][0]["sha256"]
        audit_path = bundle / bad["requirements"][0]["source_provenance_audit_path"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["frames"][0]["raw_sha256"] = "c" * 64
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        bad["requirements"][0]["source_provenance_audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "not covered by source_provenance_audit" in proc.stdout
        write_darkframe_audits(strict, bundle)

        bad = json.loads(json.dumps(strict))
        dark = bad["requirements"][0]
        audit_path = bundle / dark["source_provenance_audit_path"]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["frames"][0]["linear_raw"] = True
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        dark["source_provenance_audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "source_provenance_audit ready frames must record linear_raw=false" in proc.stdout
        write_darkframe_audits(strict, bundle)

        bad = json.loads(json.dumps(strict))
        dark = bad["requirements"][0]
        sidecar_path = bundle / dark["camera_noise_sidecar_path"]
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["production_ready"] = False
        sidecar["calibrations"][0]["noise_signal_audit"]["separates_noise_from_signal"] = False
        sidecar["calibrations"][0]["usable_for_training_targets"] = False
        sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        dark["camera_noise_sidecar_sha256"] = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "camera_noise_sidecar production_ready must be true" in proc.stdout
        assert "camera_noise_sidecar noise_signal_audit.separates_noise_from_signal must be true" in proc.stdout
        write_darkframe_audits(strict, bundle)

        bad = json.loads(json.dumps(strict))
        dark = bad["requirements"][0]
        sidecar_path = bundle / dark["camera_noise_sidecar_path"]
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["calibrations"][0]["per_plane"]["r"]["sigma_black"] = 0.0
        sidecar["calibrations"][0]["per_plane"]["g1"].pop("mean_black")
        sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        dark["camera_noise_sidecar_sha256"] = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "camera_noise_sidecar per_plane.r.sigma_black must be > 0" in proc.stdout
        assert "camera_noise_sidecar per_plane.g1.mean_black must be numeric and >= 0" in proc.stdout

        bad = json.loads(json.dumps(strict))
        premium = next(row for row in bad["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        preflight_path = bundle / premium["candidate_preflight_audit_path"]
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight["launchable_for_production_attempt"] = False
        preflight["verdict"] = "blocked_before_long_run"
        preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
        premium["candidate_preflight_audit_sha256"] = hashlib.sha256(preflight_path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "candidate_preflight_audit launchable_for_production_attempt must be true" in proc.stdout

    print("test_check_production_capture_submission: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
