#!/usr/bin/env python3
"""Tests for the Mission 1 numbered-list readiness audit."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/mission1_numbered_list_readiness.py"
MISSION1_8K_SR_PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1"
    "+demosaic=sips_via_gpr_tools"
)


def load_tool():
    spec = importlib.util.spec_from_file_location("mission1_numbered_list_readiness", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(root: Path, rel: str, payload: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(root: Path, rel: str, payload: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def write_registry(root: Path, production_scope: str) -> Path:
    write_json(
        root,
        "registry.json",
        {
            "pipelines": {
                MISSION1_8K_SR_PIPELINE_ID: {
                    "production_scope": production_scope,
                }
            }
        },
    )
    return root / "registry.json"


def create_fixture(root: Path) -> None:
    write_json(
        root,
        "artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/labs_target_bench.json",
        {
            "capture": {
                "frames_written": 420,
                "dropped_frames": 0,
                "capture_width": 4096,
                "capture_height": 3072,
                "pixel_format": 1,
            },
            "target": {"actual_wall_fps": 24.3},
            "writer_handoff": {"loop_fps_median": 25.3},
            "storage": {
                "target": {
                    "fits_target": True,
                    "required_write_MBps": 88.7,
                    "budget_write_MBps": 135.0,
                }
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/camera_handoff_receipt.json",
        {
            "schema": "gpr_labs_camera_handoff_receipt.v1",
            "target": {"name": "Pi 5 stand-in", "role": "stand-in"},
            "integration": {
                "frame_source": "file-backed Bayer stand-in",
                "memory_ownership": "synchronous submit; caller owns input through return",
                "write_path": "bench_fused direct .gvid path on Pi 5 stand-in",
                "sensor_dma_handoff": {"executed": False},
                "storage_handoff": {
                    "executed": False,
                    "medium": "/mnt/ssd filesystem stand-in",
                    "ownership": "OS/page-cache writeback; not camera firmware DMA",
                },
            },
            "input_frame": {
                "width": 4096,
                "height": 3072,
                "stride_bytes": 16560,
                "bit_depth": 14,
                "pixel_format": 1,
                "target_fps": 20.0,
            },
            "capture": {"frames_requested": 420, "frames_written": 420, "dropped_frames": 0},
            "timing": {"fps_median": 25.3, "median_ms": 39.5, "p95_ms": 47.5, "p99_ms": 52.6},
            "storage": {"write_mb_s": 102.8, "flush_policy": "bench_fused sequential .gvid fwrite"},
            "memory": {"rss_kb": 140800},
            "output": {"sha256": "a" * 64, "validation": {"valid": True, "frame_count": 420}},
            "interruption_recovery": {"proven": True, "validator_rejects_truncated": True},
            "verdict": {
                "firmware_ready": False,
                "target_evidence": True,
                "fps_target_met": True,
                "fps_median_target_met": True,
                "fps_wall_target_met": True,
                "no_drops": True,
            },
            "blocker": {"cause": "camera sensor/DMA and camera storage handoff not executed"},
        },
    )
    write_json(
        root,
        "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/labs_target_bench.json",
        {
            "capture": {
                "frames_written": 1440,
                "dropped_frames": 0,
                "capture_width": 4096,
                "capture_height": 3072,
                "pixel_format": 1,
            },
            "target": {"actual_wall_fps": 20.5},
            "timing": {"fps_median": 21.3},
            "storage": {
                "target": {
                    "fits_target": True,
                    "required_write_MBps": 109.5,
                    "budget_write_MBps": 135.0,
                }
            },
            "gvid": {
                "validation": {
                    "valid": True,
                    "frame_count": 1440,
                    "payload_bytes": 7882678080,
                }
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/camera_handoff_receipt.json",
        {
            "schema": "gpr_labs_camera_handoff_receipt.v1",
            "target": {"name": "Pi 5 stand-in", "role": "stand-in"},
            "integration": {
                "frame_source": "file-backed Bayer stand-in",
                "memory_ownership": "synchronous submit; caller owns input through return",
                "write_path": "bench_fused direct .gvid path on Pi 5 stand-in",
                "sensor_dma_handoff": {"executed": False},
                "storage_handoff": {
                    "executed": False,
                    "medium": "/mnt/ssd filesystem stand-in",
                    "ownership": "OS/page-cache writeback; not camera firmware DMA",
                },
            },
            "input_frame": {
                "width": 4096,
                "height": 3072,
                "stride_bytes": 16560,
                "bit_depth": 14,
                "pixel_format": 1,
                "target_fps": 20.0,
            },
            "capture": {"frames_requested": 1440, "frames_written": 1440, "dropped_frames": 0},
            "timing": {"fps_median": 21.3, "median_ms": 47.0, "p95_ms": 57.4, "p99_ms": 64.1},
            "storage": {"write_mb_s": 109.5, "flush_policy": "bench_fused sequential .gvid fwrite"},
            "memory": {"rss_kb": 140800},
            "output": {"sha256": "d" * 64, "validation": {"valid": True, "frame_count": 1440}},
            "interruption_recovery": {"proven": True, "validator_rejects_truncated": True},
            "verdict": {
                "firmware_ready": False,
                "target_evidence": True,
                "fps_target_met": True,
                "fps_median_target_met": True,
                "fps_wall_target_met": True,
                "no_drops": True,
            },
            "blocker": {"cause": "camera sensor/DMA and camera storage handoff not executed"},
        },
    )
    write_json(
        root,
        (
            "artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/"
            "preview_decode_ll_direct_named_1024x768_20260624/receipt.json"
        ),
        {
            "frame_count": 420,
            "summary": {
                "dims": [[1024, 768]],
                "actual_wall_fps_including_extract_process": 25.8,
                "decode_plus_target": {"fps_median": 36.2},
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/preview_decode_1024x768/receipt.json",
        {
            "frame_count": 1440,
            "summary": {
                "dims": [[1024, 768]],
                "actual_wall_fps_including_extract_process": 23.5,
                "decode_plus_target": {"fps_median": 42.5},
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/preview_ui_receipt.json",
        {
            "schema": "gpr_labs_preview_ui_receipt.v1",
            "source_provenance": {
                "available": True,
                "policy": "source_tree_digest_v1",
                "sha256": "e" * 64,
                "file_count": 12,
                "total_bytes": 3456,
            },
            "target": {"name": "Pi 5 stand-in", "role": "stand-in"},
            "source": {
                "width": 4096,
                "height": 3072,
                "frame_count": 1440,
                "bit_depth": 14,
                "pixel_format": 1,
                "gvid_sha256": "f" * 64,
            },
            "preview": {
                "width": 1024,
                "height": 768,
                "frame_count": 1440,
                "target_fps": 20.0,
                "full_frame_downsample": True,
                "color_pipeline": "full-frame Bayer decode to RGB preview",
                "tone_pipeline": "preview tone path from fused decoder target",
            },
            "integration": {
                "ui_path_executed": False,
                "decode_path": "fused_decode_cli mission1_preview_4x_1024x768",
                "presentation_path": "off-camera preview decode receipt",
                "buffer_ownership": "process-owned RGB output buffer",
                "display_surface": "stand-in raw preview receipt output",
            },
            "timing": {
                "fps_median": 42.5,
                "actual_wall_fps": 23.5,
                "median_ms": 23.5,
                "p95_ms": 27.6,
                "p99_ms": 28.8,
            },
            "memory": {"rss_kb": 70000},
            "validation": {
                "output_valid": True,
                "no_drops": True,
                "visual_checked": False,
            },
            "verdict": {
                "ui_ready": False,
                "target_evidence": True,
                "fps_target_met": True,
            },
            "blocker": {"cause": "Mission 1 camera UI/display path not executed"},
        },
    )
    write_json(
        root,
        "artifacts/mission1_camera_closure_run_20260625/current_standin/mission1_camera_closure_run.json",
        {
            "schema": "gpr.mission1_camera_closure_run.v1",
            "receipts": {
                "target_bench": (
                    "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/"
                    "labs_target_bench.json"
                ),
                "camera_handoff": (
                    "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/"
                    "camera_handoff_receipt.json"
                ),
                "preview_decode": (
                    "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/"
                    "preview_decode_1024x768/receipt.json"
                ),
                "preview_ui": (
                    "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/"
                    "preview_ui_receipt.json"
                ),
                "target_preflight": (
                    "artifacts/mission1_camera_closure_run_20260625/current_standin/"
                    "target_preflight_receipt.json"
                ),
            },
            "steps": [
                {"name": "validate_camera_handoff_receipt", "returncode": 0},
                {"name": "validate_preview_ui_receipt", "returncode": 0},
            ],
            "verdict": {
                "production_ready": False,
                "firmware_ready": False,
                "ui_ready": False,
                "handoff_blocker": "camera sensor/DMA and camera storage handoff not executed",
                "preview_blocker": "Mission 1 camera UI/display path not executed",
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_camera_closure_run_20260625/current_standin/target_preflight_receipt.json",
        {
            "schema": "gpr.mission1_camera_target_preflight.v1",
            "target": {"host": "192.168.16.67", "role": "stand-in", "name": "Pi 5 stand-in"},
            "checks": [
                {"name": "repo root exists", "passed": True, "detail": "/mnt/ssd/gpr_work/src"},
                {"name": "raw source exists", "passed": True, "detail": "/mnt/ssd/mission1_native12/GP017602.raw"},
                {"name": "raw source has unpacked Bayer size", "passed": True, "detail": "size=25165824 expected_min=25165824"},
                {"name": "executable available: bench_fused", "passed": True, "detail": "build/bin/bench_fused"},
                {"name": "executable available: labs_encoder_bench_cli", "passed": True, "detail": "build/bin/labs_encoder_bench_cli"},
                {"name": "executable available: fused_decode_cli", "passed": True, "detail": "build/bin/fused_decode_cli"},
                {"name": "executable available: gvid_preview_rgb_cli", "passed": True, "detail": "build/bin/gvid_preview_rgb_cli"},
                {"name": "output_dir writable", "passed": True, "detail": "/mnt/ssd/gpr_work/artifacts/out"},
                {"name": "scratch_dir writable", "passed": True, "detail": "/mnt/ssd/gpr_work/tmp"},
            ],
            "blockers": [],
            "verdict": {
                "target_preflight_ready": True,
                "camera_closure_possible": False,
                "remaining_blocker_count": 0,
            },
        },
    )
    for name, detail_suffix in (
        ("preflight_192_168_16_67_camera_latest_20260625.json", "stale"),
        ("preflight_192_168_16_67_camera_refresh_20260625.json", "refresh"),
        ("preflight_192_168_16_67_camera_codex_refresh2_20260625.json", "refresh2"),
    ):
        write_json(
            root,
            f"artifacts/mission1_camera_target_preflight_20260625/{name}",
            {
                "schema": "gpr.mission1_camera_target_preflight.v1",
                "target": {"host": "192.168.16.67", "role": "camera", "name": "Mission 1"},
                "checks": [
                    {"name": "repo root exists", "passed": True, "detail": f"/mnt/ssd/gpr_work/{detail_suffix}"},
                    {"name": "raw source exists", "passed": True, "detail": "/mnt/ssd/mission1_native12/GP017602.raw"},
                    {"name": "raw source has unpacked Bayer size", "passed": True, "detail": "size=25165824 expected_min=25165824"},
                    {"name": "camera frame source ready", "passed": False, "detail": "operator assertion"},
                    {"name": "camera storage path ready", "passed": False, "detail": "operator assertion"},
                    {"name": "camera display path ready", "passed": False, "detail": "operator assertion"},
                ],
                "blockers": [
                    "camera frame source ready",
                    "camera storage path ready",
                    "camera display path ready",
                ],
                "verdict": {
                    "target_preflight_ready": False,
                    "camera_closure_possible": False,
                    "remaining_blocker_count": 3,
                },
            },
        )
    write_json(
        root,
        (
            "artifacts/mission1_camera_target_preflight_20260625/"
            "source_probe_192_168_16_67_camera_sensor_ring_followup_20260625.json"
        ),
        {
            "schema": "gpr.mission1_camera_source_probe.v1",
            "target": {"host": "192.168.16.67", "role": "camera", "name": "Mission 1"},
            "inputs": {
                "raw": "/dev/mission1/sensor_dma_ring",
                "raw_source_kind": "sensor_dma_capture",
            },
            "checks": [
                {"name": "ssh target probe", "passed": True, "detail": "returncode=0"},
                {"name": "camera raw source endpoint exists", "passed": False, "detail": "missing"},
                {"name": "camera raw source endpoint is device-like", "passed": False, "detail": "missing"},
            ],
            "blockers": ["camera raw source endpoint is missing on target"],
            "verdict": {"source_ready": False, "remaining_blocker_count": 1},
        },
    )

    base = "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
    write_json(
        root,
        f"{base}/mission42_rgb_cfa_target_gate_wb_review/summary.json",
        {
            "summary": {
                "rgb_rmse_improvement_pct": {"min": 4.5},
                "cfa_raw_rmse_improvement_pct": {"min": 4.6},
                "y_gradient_improvement_pct": {"min": 1.6},
            }
        },
    )
    write_text(root, f"{base}/mission42_rgb_cfa_target_gate_wb_review/index.html", "<html></html>")
    write_json(
        root,
        f"{base}/mission42_4k_cnn_tone_audit_20260625/summary.json",
        {
            "summary": {
                "row_count": 126,
                "candidate_green_delta_vs_target": {"abs_p95": 0.012},
                "baseline_green_delta_vs_target": {"abs_p95": 0.016},
                "candidate_better_display_mae_count": 120,
                "candidate_worse_display_mae_count": 6,
            }
        },
    )
    write_text(root, f"{base}/mission42_4k_cnn_tone_audit_20260625/index.html", "<html></html>")
    write_json(
        root,
        f"{base}/mission42_4k_cnn_gvid_packaging_q8/labs_target_bench.json",
        {
            "capture": {"frames_written": 42},
            "gvid": {
                "sha256": "abc",
                "validation": {"valid": True, "width": 4096, "height": 3072},
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff.json",
        {
            "schema": "gpr.mission1_4k_cleanup_visual_signoff.v1",
            "verdict": "objective_visual_metrics_pass_manual_signoff_required",
            "production_ready": False,
            "manual_visual_signoff": False,
            "manual_visual_signoff_required": True,
            "checks": [{"name": "synthetic", "passed": True, "detail": "ok"}],
        },
    )
    write_text(
        root,
        "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff_contact_sheet.jpg",
        "synthetic",
    )
    write_text(
        root,
        "artifacts/mission1_4k_cleanup_visual_signoff_20260625/index.html",
        (
            "<html><body><h2>Production Signoff Commands</h2>"
            "build_mission1_4k_cleanup_signoff_receipt.py "
            "check_mission1_4k_cleanup_signoff_receipt.py</body></html>"
        ),
    )
    write_json(
        root,
        "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff_blocked.json",
        {
            "schema": "gpr.mission1_4k_cleanup_production_signoff.v1",
            "candidate": {
                "pipeline_id": "mission1_native12_4k_cleanup_rgb_cfa_w40_v1",
                "checkpoint_sha256": "a" * 64,
                "visual_signoff_sha256": "b" * 64,
                "contact_sheet_sha256": "c" * 64,
            },
            "objective_visual_signoff": {
                "verdict": "objective_visual_metrics_pass_manual_signoff_required",
                "all_checks_passed": True,
                "check_count": 1,
            },
            "raw_domain_guard": {
                "path": f"{base}/mission42_raw_guard/summary.json",
                "sha256": "d" * 64,
                "kind": "high_res_cfa_target",
                "target": "high-resolution-derived CFA raw target",
                "source_schema": "gpr.bayer_rgb_cfa_target_dashboard.v1",
                "row_count": 42,
                "thresholds": {
                    "min_rmse_improvement_pct": 0.0,
                    "min_mae_improvement_pct": 0.0,
                    "min_psnr_delta_db": 0.0,
                },
                "metrics": {
                    "rmse_improvement_pct": {"n": 42, "min": -1.0, "median": -0.5, "mean": -0.5, "max": -0.1},
                    "mae_improvement_pct": {"n": 42, "min": -1.0, "median": -0.5, "mean": -0.5, "max": -0.1},
                    "psnr_delta_db": {"n": 42, "min": -1.0, "median": -0.5, "mean": -0.5, "max": -0.1},
                },
                "source_metric_names": {
                    "rmse_improvement_pct": "cfa_raw_rmse_improvement_pct",
                    "mae_improvement_pct": "cfa_raw_mae_improvement_pct",
                    "psnr_delta_db": "cfa_raw_psnr_delta_db",
                },
                "passed": False,
            },
            "reviewer": {
                "name": "Synthetic Reviewer",
                "role": "project-owner",
                "reviewed_at_utc": "2026-06-25T00:00:00Z",
            },
            "review": {
                "visual_checked": False,
                "contact_sheet_path": "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff_contact_sheet.jpg",
                "dashboard_paths": [
                    f"{base}/mission42_rgb_cfa_target_gate_wb_review/index.html",
                    f"{base}/mission42_4k_cnn_tone_audit_20260625/index.html",
                ],
                "blocking_issues": ["raw-domain guard does not beat the baseline"],
            },
            "verdict": {
                "production_ready": False,
                "accepted_role": "blocked",
                "no_blocking_visual_issues": False,
            },
            "blocker": {"cause": "current_4k_cleanup_candidate_degrades_raw_rmse_mae"},
        },
    )
    write_json(
        root,
        f"{base}/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_packaging_q3_after_bounds_fix/receipt.json",
        {
            "gvid_header": {"width": 8192, "height": 6144, "frame_count": 42},
            "gvid_payload_checks": [{"matches_source": True}],
            "gvid_decode_validation": [{"returncode": 0}],
        },
    )
    write_json(
        root,
        f"{base}/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_broad_fullframe/summary.json",
        {
            "image_count": 42,
            "rmse_improvement_pct": {"min": 32.2},
            "mae_improvement_pct": {"min": 15.7},
            "gradient_mae_improvement_pct": {"min": 4.0},
        },
    )
    write_json(
        root,
        f"{base}/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/z8_all24_fullframe/summary.json",
        {
            "image_count": 24,
            "rmse_improvement_pct": {"min": 41.1},
            "mae_improvement_pct": {"min": 7.3},
            "gradient_mae_improvement_pct": {"min": 2.5},
        },
    )
    write_json(
        root,
        "artifacts/mission1_8k_sr_visual_review_20260625/visual_review.json",
        {
            "schema": "gpr.mission1_8k_sr_visual_review.v1",
            "verdict": "objective_visual_metrics_pass_manual_review_required",
            "production_ready": False,
            "manual_visual_review_complete": False,
            "manual_visual_review_required": True,
            "checks": [{"name": "synthetic", "passed": True, "detail": "ok"}],
        },
    )
    write_text(
        root,
        "artifacts/mission1_8k_sr_visual_review_20260625/index.html",
        "<html><body>Mission 1 8K SR Visual Review</body></html>",
    )
    write_text(
        root,
        "artifacts/mission1_8k_sr_visual_review_20260625/visual_review_contact_sheet.jpg",
        "synthetic",
    )
    write_json(
        root,
        f"{base}/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_gvid_to_8k_sr_full42/receipt.json",
        {
            "frames_rendered": 42,
            "max_rss_mb": 1033.0,
            "summary": {"fps_median_decode_plus_sr": 1.09},
        },
    )
    write_json(
        root,
        "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion_blocked.json",
        {
            "schema": "gpr.mission1_8k_sr_production_promotion.v1",
            "candidate": {"pipeline_id": MISSION1_8K_SR_PIPELINE_ID},
            "registry": {
                "production_scope": "offline_review_only",
                "registry_sha256": "1" * 64,
            },
            "evidence": {
                "runtime_receipt_sha256": "2" * 64,
                "gvid_packaging_receipt_sha256": "3" * 64,
                "prores_receipt_sha256": "4" * 64,
                "quality_summary_sha256": "5" * 64,
                "visual_review_complete": False,
                "editable_packaging_proven": False,
                "metadata_transplant_proven": False,
            },
            "verdict": {
                "production_ready": False,
                "accepted_role": "blocked",
                "blocking_issues": [
                    "registry_scope_not_promoted",
                    "visual_review_incomplete",
                    "editable_packaging_not_proven",
                    "metadata_transplant_not_proven",
                ],
            },
            "blocker": {"cause": "registry_scope_not_promoted"},
        },
    )
    write_json(
        root,
        f"{base}/mission42_4k_cnn_prores_review/receipt.json",
        {
            "ffprobe": {
                "streams": [
                    {
                        "codec_name": "prores",
                        "width": 4096,
                        "height": 3072,
                        "nb_frames": "42",
                    }
                ]
            }
        },
    )
    write_json(
        root,
        f"{base}/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_to_prores_42f_after_bounds_fix/receipt.json",
        {
            "ffprobe": {
                "stdout": json.dumps(
                    {
                        "streams": [
                            {
                                "codec_name": "prores",
                                "width": 8192,
                                "height": 6144,
                                "nb_frames": "42",
                            }
                        ]
                    }
                )
            }
        },
    )


def promote_fixture_to_production(root: Path) -> None:
    standin_handoff_path = root / "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/camera_handoff_receipt.json"
    current_handoff_path = root / "artifacts/mission1_camera_closure_run_20260625/current_camera/camera_handoff_receipt.json"
    current_handoff = json.loads(standin_handoff_path.read_text(encoding="utf-8"))
    current_handoff["source_provenance"] = {
        "available": True,
        "policy": "source_tree_digest_v1",
        "sha256": "1" * 64,
        "file_count": 12,
        "total_bytes": 3456,
    }
    current_handoff["target"] = {"name": "Mission 1 camera", "role": "camera"}
    current_handoff["integration"]["frame_source"] = "Mission 1 sensor DMA Bayer frame source"
    current_handoff["integration"]["raw_source_kind"] = "sensor_dma_capture"
    current_handoff["integration"]["write_path"] = "Mission 1 firmware camera storage path"
    current_handoff["integration"]["sensor_dma_handoff"]["executed"] = True
    current_handoff["integration"]["storage_handoff"]["executed"] = True
    current_handoff["integration"]["storage_handoff"]["medium"] = "Mission 1 SD media"
    current_handoff["integration"]["storage_handoff"]["ownership"] = "camera firmware storage handoff"
    current_handoff["verdict"]["firmware_ready"] = True
    current_handoff.pop("blocker", None)
    current_handoff_path.parent.mkdir(parents=True, exist_ok=True)
    current_handoff_path.write_text(json.dumps(current_handoff, indent=2) + "\n", encoding="utf-8")

    standin_preview_ui_path = root / "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/preview_ui_receipt.json"
    preview_ui_path = root / "artifacts/mission1_camera_closure_run_20260625/current_camera/preview_ui_receipt.json"
    preview_ui = json.loads(standin_preview_ui_path.read_text(encoding="utf-8"))
    preview_ui["target"] = {"name": "Mission 1 camera", "role": "camera"}
    preview_ui["integration"]["ui_path_executed"] = True
    preview_ui["integration"]["presentation_path"] = "Mission 1 rear display presentation path"
    preview_ui["integration"]["display_surface"] = "Mission 1 rear display"
    preview_ui["validation"]["visual_checked"] = True
    preview_ui["verdict"]["ui_ready"] = True
    preview_ui.pop("blocker", None)
    preview_ui_path.parent.mkdir(parents=True, exist_ok=True)
    preview_ui_path.write_text(json.dumps(preview_ui, indent=2) + "\n", encoding="utf-8")

    standin_preflight_path = root / "artifacts/mission1_camera_closure_run_20260625/current_standin/target_preflight_receipt.json"
    preflight_path = root / "artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json"
    preflight = json.loads(standin_preflight_path.read_text(encoding="utf-8"))
    preflight["target"] = {"host": "mission1-camera", "role": "camera", "name": "Mission 1 camera"}
    preflight["checks"].extend(
        [
            {"name": "camera frame source ready", "passed": True, "detail": "operator assertion"},
            {"name": "camera storage path ready", "passed": True, "detail": "operator assertion"},
            {"name": "camera display path ready", "passed": True, "detail": "operator assertion"},
        ]
    )
    preflight["verdict"]["camera_closure_possible"] = True
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    standin_closure_run_path = root / "artifacts/mission1_camera_closure_run_20260625/current_standin/mission1_camera_closure_run.json"
    closure_run_path = root / "artifacts/mission1_camera_closure_run_20260625/current_camera/mission1_camera_closure_run.json"
    closure_run = json.loads(standin_closure_run_path.read_text(encoding="utf-8"))
    closure_run["receipts"]["camera_handoff"] = str(current_handoff_path)
    closure_run["receipts"]["preview_ui"] = str(preview_ui_path)
    closure_run["receipts"]["target_preflight"] = str(preflight_path)
    closure_run["verdict"] = {
        "production_ready": True,
        "firmware_ready": True,
        "ui_ready": True,
        "handoff_blocker": None,
        "preview_blocker": None,
    }
    closure_run_path.parent.mkdir(parents=True, exist_ok=True)
    closure_run_path.write_text(json.dumps(closure_run, indent=2) + "\n", encoding="utf-8")

    base = "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
    write_json(
        root,
        "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json",
        {
            "schema": "gpr.mission1_4k_cleanup_production_signoff.v1",
            "candidate": {
                "pipeline_id": "mission1_native12_4k_cleanup_rgb_cfa_w40_v1",
                "checkpoint_sha256": "a" * 64,
                "visual_signoff_sha256": "b" * 64,
                "contact_sheet_sha256": "c" * 64,
            },
            "objective_visual_signoff": {
                "verdict": "objective_visual_metrics_pass_manual_signoff_required",
                "all_checks_passed": True,
                "check_count": 1,
            },
            "raw_domain_guard": {
                "path": f"{base}/mission42_raw_guard/summary.json",
                "sha256": "d" * 64,
                "kind": "high_res_cfa_target",
                "target": "high-resolution-derived CFA raw target",
                "source_schema": "gpr.bayer_rgb_cfa_target_dashboard.v1",
                "row_count": 42,
                "thresholds": {
                    "min_rmse_improvement_pct": 0.0,
                    "min_mae_improvement_pct": 0.0,
                    "min_psnr_delta_db": 0.0,
                },
                "metrics": {
                    "rmse_improvement_pct": {"n": 42, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
                    "mae_improvement_pct": {"n": 42, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
                    "psnr_delta_db": {"n": 42, "min": 0.1, "median": 0.2, "mean": 0.2, "max": 0.3},
                },
                "source_metric_names": {
                    "rmse_improvement_pct": "cfa_raw_rmse_improvement_pct",
                    "mae_improvement_pct": "cfa_raw_mae_improvement_pct",
                    "psnr_delta_db": "cfa_raw_psnr_delta_db",
                },
                "passed": True,
            },
            "reviewer": {
                "name": "Synthetic Reviewer",
                "role": "project-owner",
                "reviewed_at_utc": "2026-06-25T00:00:00Z",
            },
            "review": {
                "visual_checked": True,
                "contact_sheet_path": "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff_contact_sheet.jpg",
                "dashboard_paths": [
                    f"{base}/mission42_rgb_cfa_target_gate_wb_review/index.html",
                    f"{base}/mission42_4k_cnn_tone_audit_20260625/index.html",
                ],
                "blocking_issues": [],
            },
            "verdict": {
                "production_ready": True,
                "accepted_role": "production",
                "no_blocking_visual_issues": True,
            },
        },
    )
    write_json(
        root,
        "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json",
        {
            "schema": "gpr.mission1_8k_sr_production_promotion.v1",
            "candidate": {"pipeline_id": MISSION1_8K_SR_PIPELINE_ID},
            "registry": {
                "production_scope": "offline_production",
                "registry_sha256": "1" * 64,
            },
            "evidence": {
                "runtime_receipt_sha256": "2" * 64,
                "gvid_packaging_receipt_sha256": "3" * 64,
                "prores_receipt_sha256": "4" * 64,
                "quality_summary_sha256": "5" * 64,
                "visual_review_package_sha256": "0" * 64,
                "editable_packaging_receipt_sha256": "6" * 64,
                "metadata_transplant_audit_sha256": "7" * 64,
                "visual_review_complete": True,
                "editable_packaging_proven": True,
                "metadata_transplant_proven": True,
            },
            "verdict": {
                "production_ready": True,
                "accepted_role": "production",
                "blocking_issues": [],
            },
        },
    )


def test_build_report_passes_with_review_blockers() -> None:
    tool = load_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_readiness_", dir=work_parent) as td:
        fixture = Path(td)
        create_fixture(fixture)
        tool.REGISTRY_PATH = write_registry(fixture, "offline_review_only")
        report = tool.build_report(fixture)
        assert report["overall_status"] == "evidence_passes_with_production_blockers"
        assert all(item["passed"] for item in report["items"])
        assert [item["production_ready"] for item in report["items"]] == [False, False, False, True]
        preflight_checks = [
            check
            for item in report["items"]
            for check in item["checks"]
            if check["name"] == "camera-role target preflight blocker specificity"
        ]
        assert preflight_checks
        assert all(
            check["evidence"].endswith(
                "artifacts/mission1_camera_target_preflight_20260625/"
                "preflight_192_168_16_67_camera_codex_refresh2_20260625.json"
            )
            for check in preflight_checks
        )
        source_probe_checks = [
            check
            for item in report["items"]
            for check in item["checks"]
            if check["name"] == "camera source endpoint probe blocker specificity"
        ]
        assert len(source_probe_checks) == 2
        assert all(check["passed"] for check in source_probe_checks)
        assert all(
            check["evidence"].endswith(
                "artifacts/mission1_camera_target_preflight_20260625/"
                "source_probe_192_168_16_67_camera_sensor_ring_followup_20260625.json"
            )
            for check in source_probe_checks
        )
        assert all(
            isinstance(check["passed"], bool)
            for item in report["items"]
            for check in item["checks"]
        )
        assert (
            "Mission 1 4K cleanup production signoff is blocked by "
            "current_4k_cleanup_candidate_degrades_raw_rmse_mae."
        ) in report["blockers"]
        assert (
            "Mission 1 8K SR registry candidate remains offline_review_only and needs production promotion evidence."
            in report["blockers"]
        )


def test_build_report_can_reach_production_ready() -> None:
    tool = load_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_readiness_production_", dir=work_parent) as td:
        fixture = Path(td)
        create_fixture(fixture)
        promote_fixture_to_production(fixture)
        tool.REGISTRY_PATH = write_registry(fixture, "offline_production")
        report = tool.build_report(fixture)
        assert report["overall_status"] == "production_ready"
        assert report["blockers"] == []
        assert all(item["status"] == "pass" for item in report["items"])
        assert all(item["passed"] for item in report["items"])
        assert all(item["production_ready"] for item in report["items"])


def test_require_production_exits_until_blockers_close() -> None:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_readiness_cli_", dir=work_parent) as td:
        fixture = Path(td)
        create_fixture(fixture)
        registry = write_registry(fixture, "offline_review_only")
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(fixture),
                "--require-production",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "GPR_REGISTRY_PATH": str(registry)},
        )
        assert result.returncode == 2
        assert "evidence_passes_with_production_blockers" in result.stdout
        assert (
            "Production promotion blocked: overall_status=evidence_passes_with_production_blockers"
            in result.stderr
        )
        assert "Mission 1 firmware/camera-side handoff receipt is still required." in result.stderr
        assert "Mission 1 camera preview UI receipt is still required." in result.stderr
        assert (
            "Mission 1 4K cleanup production signoff is blocked by "
            "current_4k_cleanup_candidate_degrades_raw_rmse_mae."
            in result.stderr
        )
        assert "Mission 1 8K SR registry candidate remains offline_review_only" in result.stderr


def test_require_production_exits_zero_when_receipts_are_ready() -> None:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_readiness_cli_production_", dir=work_parent) as td:
        fixture = Path(td)
        create_fixture(fixture)
        promote_fixture_to_production(fixture)
        registry = write_registry(fixture, "offline_production")
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(fixture),
                "--require-production",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "GPR_REGISTRY_PATH": str(registry)},
        )
        assert result.returncode == 0
        assert "production_ready" in result.stdout
        assert result.stderr == ""


if __name__ == "__main__":
    test_build_report_passes_with_review_blockers()
    test_build_report_can_reach_production_ready()
    test_require_production_exits_until_blockers_close()
    test_require_production_exits_zero_when_receipts_are_ready()
    print("test_mission1_numbered_list_readiness: PASS")
