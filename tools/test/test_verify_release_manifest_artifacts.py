#!/usr/bin/env python3
"""Smoke-test release manifest artifact verification semantics."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/verify_release_manifest_artifacts.py"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def import_tool():
    spec = importlib.util.spec_from_file_location("verify_release_manifest_artifacts_smoke", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def patched_env(**updates: str):
    old = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def write_manifest(path: Path, external_root: Path, blockers: int) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "gpr_release_evidence_manifest.v1",
                "external_root": str(external_root),
                "dashboards": [
                    {
                        "id": "mission1_numbered_list_closure_plan",
                        "family": "mission1_readiness",
                        "status": "diagnostic",
                        "purpose": "fixture",
                        "dashboard": "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json",
                        "docs": [],
                        "receipts": [
                            "artifacts/mission1_numbered_list_readiness_20260625/readiness.json",
                            "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.md",
                            "artifacts/mission1_camera_closure_package_20260625/closure_package.json",
                            "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json",
                            "artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json",
                            "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json",
                            "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/target_closure_package_run.json",
                            "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/hardware_audit_receipt.json",
                            "artifacts/mission1_camera_target_preflight_20260625/source_probe_fixture_followup_20260625.json",
                            "artifacts/mission1_camera_target_preflight_20260625/preflight_fixture_camera_20260625.json",
                            "artifacts/mission1_camera_target_discovery_20260625/hardware_audit_192_168_16_67_20260625.json",
                            "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/collection_receipt.json",
                            "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json",
                        ],
                        "metrics": {
                            "blockers": blockers,
                            "production_ready": 0,
                            "production_ready_items": 3,
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_artifacts(external_root: Path) -> None:
    out = external_root / "artifacts/mission1_numbered_list_readiness_20260625"
    out.mkdir(parents=True)
    (out / "readiness.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_numbered_list_readiness.v1",
                "external_root": str(external_root),
                "overall_status": "evidence_passes_with_production_blockers",
                "items": [
                    {
                        "id": 1,
                        "title": "item 1",
                        "status": "pass_with_handoff_gap",
                        "checks": [{"name": "check", "passed": True, "detail": "ok", "evidence": "fixture"}],
                        "blockers": ["camera handoff missing"],
                        "passed": True,
                        "production_ready": False,
                    },
                    {
                        "id": 2,
                        "title": "item 2",
                        "status": "pass",
                        "checks": [{"name": "check", "passed": True, "detail": "ok", "evidence": "fixture"}],
                        "blockers": [],
                        "passed": True,
                        "production_ready": True,
                    },
                    {
                        "id": 3,
                        "title": "item 3",
                        "status": "pass",
                        "checks": [{"name": "check", "passed": True, "detail": "ok", "evidence": "fixture"}],
                        "blockers": [],
                        "passed": True,
                        "production_ready": True,
                    },
                    {
                        "id": 4,
                        "title": "item 4",
                        "status": "pass",
                        "checks": [{"name": "check", "passed": True, "detail": "ok", "evidence": "fixture"}],
                        "blockers": [],
                        "passed": True,
                        "production_ready": True,
                    },
                ],
                "blockers": ["camera handoff missing"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "closure_plan.md").write_text("# fixture\n", encoding="utf-8")
    (out / "closure_plan.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_numbered_list_closure_plan.v1",
                "readiness_status": "evidence_passes_with_production_blockers",
                "production_ready": False,
                "final_gate_command": "python3 tools/mission1_numbered_list_readiness.py --require-production",
                "blockers": [
                    {
                        "item_id": 1,
                        "current_blocker": "camera handoff missing",
                        "required_receipt": "artifacts/example/camera_handoff_receipt.json",
                        "validator": "tools/check_labs_camera_handoff_receipt.py",
                        "validation_command": "python3 tools/check_labs_camera_handoff_receipt.py artifacts/example/camera_handoff_receipt.json",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    package = external_root / "artifacts/mission1_camera_closure_package_20260625"
    package.mkdir(parents=True)
    (package / "closure_package.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_camera_closure_package.v1",
                "readiness": {
                    "path": "artifacts/mission1_numbered_list_readiness_20260625/readiness.json",
                    "sha256": "a" * 64,
                    "overall_status": "evidence_passes_with_production_blockers",
                    "production_ready": False,
                    "blockers": ["camera handoff missing"],
                },
                "closure_plan": {
                    "path": "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json",
                    "sha256": "b" * 64,
                    "production_ready": False,
                    "final_gate_command": "python3 tools/mission1_numbered_list_readiness.py --require-production",
                },
                "remaining_blockers": [
                    {
                        "item_id": 1,
                        "blocker": "Mission 1 firmware/camera-side handoff receipt is still required.",
                        "required_receipt": "artifacts/current/camera_handoff_receipt.json",
                        "validator": "tools/check_labs_camera_handoff_receipt.py",
                    },
                    {
                        "item_id": 2,
                        "blocker": "Mission 1 camera preview UI receipt is still required.",
                        "required_receipt": "artifacts/current/preview_ui_receipt.json",
                        "validator": "tools/check_labs_preview_ui_receipt.py",
                    },
                ],
                "current_receipts": [
                    {
                        "path": "artifacts/current/camera_handoff_receipt.json",
                        "exists": True,
                        "sha256": "c" * 64,
                        "target": {"role": "stand-in"},
                        "verdict": {"firmware_ready": False},
                        "blocker": {"cause": "camera handoff not executed"},
                    },
                    {
                        "path": "artifacts/current/preview_ui_receipt.json",
                        "exists": True,
                        "sha256": "d" * 64,
                        "target": {"role": "stand-in"},
                        "verdict": {"ui_ready": False},
                        "blocker": {"cause": "ui path not executed"},
                    },
                ],
                "acceptance_audit": [
                    {
                        "item_id": 1,
                        "required_receipt": "artifacts/current/camera_handoff_receipt.json",
                        "checks": [{"expression": "target.role=camera", "passed": False}],
                        "passed": False,
                        "satisfied_count": 0,
                        "check_count": 1,
                    },
                    {
                        "item_id": 2,
                        "required_receipt": "artifacts/current/preview_ui_receipt.json",
                        "checks": [{"expression": "target.role=camera", "passed": False}],
                        "passed": False,
                        "satisfied_count": 0,
                        "check_count": 1,
                    },
                ],
                "target_preflight": {
                    "path": "artifacts/current/target_preflight_receipt.json",
                    "exists": True,
                    "sha256": "e" * 64,
                    "schema": "gpr.mission1_camera_target_preflight.v1",
                    "target": {"role": "stand-in"},
                    "verdict": {
                        "target_preflight_ready": True,
                        "camera_closure_possible": False,
                    },
                    "blockers": [],
                },
                "target_access": {"requested": False},
                "runbook": {
                    "camera_handoff_validator": "python3 tools/check_labs_camera_handoff_receipt.py camera_handoff_receipt.json",
                    "preview_ui_validator": "python3 tools/check_labs_preview_ui_receipt.py preview_ui_receipt.json",
                    "final_gate": "python3 tools/mission1_numbered_list_readiness.py --require-production",
                },
                "verdict": {
                    "production_ready": False,
                    "reason": "camera_receipts_missing",
                    "remaining_blocker_count": 2,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    launch = external_root / "artifacts/mission1_camera_closure_launch_20260625"
    launch.mkdir(parents=True)
    (launch / "mission1_camera_closure_package_dry_run.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_target_closure_package_run.v1",
                "dry_run": True,
                "repo_root": "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup",
                "target": {"name": "Mission 1", "role": "camera", "raw_source_kind": "sensor_dma_capture"},
                "steps": [
                    {
                        "name": "validate_dispatch_inputs",
                        "returncode": 0,
                        "cmd": [
                            "python3",
                            "tools/check_mission1_camera_dispatch_inputs.py",
                            "--raw-source-kind",
                            "sensor_dma_capture",
                            "--raw-path",
                            "/dev/mission1/sensor_dma_ring",
                        ],
                    },
                    {
                        "name": "camera_hardware_audit",
                        "returncode": 0,
                        "cmd": [
                            "python3",
                            "tools/mission1_camera_hardware_audit.py",
                            "--output-json",
                            "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/hardware_audit_receipt.json",
                            "--require-camera",
                        ],
                    },
                    {
                        "name": "target_preflight",
                        "returncode": 0,
                        "cmd": [
                            "python3",
                            "tools/mission1_camera_target_preflight.py",
                            "--raw-source-kind",
                            "sensor_dma_capture",
                            "--frame-source",
                            "sensor DMA ring buffer",
                            "--write-path",
                            "Mission 1 camera storage writer path",
                            "--storage-medium",
                            "Mission 1 SD card",
                            "--display-surface",
                            "Mission 1 rear display",
                            "--presentation-path",
                            "Mission 1 rear display presentation path",
                        ],
                    },
                    {
                        "name": "camera_closure_run",
                        "returncode": 0,
                        "cmd": [
                            "python3",
                            "tools/run_mission1_camera_closure.py",
                            "--raw-source-kind",
                            "sensor_dma_capture",
                            "--raw",
                            "/dev/mission1/sensor_dma_ring",
                            "--target-preflight-receipt",
                            "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json",
                        ],
                    },
                    {
                        "name": "collect_compact_receipts",
                        "returncode": 0,
                        "cmd": [
                            "python3",
                            "tools/collect_mission1_target_closure.py",
                            "--include-timing-receipts",
                        ],
                    },
                ],
                "verdict": {"command_ready": True, "production_ready": False},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (launch / "mission1_remote_closure_package_dry_run.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_remote_closure_package_run.v1",
                "dry_run": True,
                "target_host": "192.168.16.67",
                "remote_repo_root": "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup",
                "remote_output_dir": "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera",
                "local_output_dir": "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera",
                "target_role": "camera",
                "raw_source_kind": "sensor_dma_capture",
                "camera_ready_flags": {
                    "camera_frame_source_ready": True,
                    "camera_storage_path_ready": True,
                    "camera_display_path_ready": True,
                    "sensor_dma_executed": True,
                    "storage_handoff_executed": True,
                    "ui_path_executed": True,
                    "visual_checked": True,
                },
                "package_step": {
                    "cmd": [
                        "ssh",
                        "192.168.16.67",
                        "cd /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup && python3 tools/run_mission1_target_closure_package.py --dry-run --raw /dev/mission1/sensor_dma_ring --raw-source-kind sensor_dma_capture --frame-source 'sensor DMA ring buffer' --write-path 'Mission 1 camera storage writer path' --storage-medium 'Mission 1 SD card' --display-surface 'Mission 1 rear display' --presentation-path 'Mission 1 rear display presentation path'",
                    ],
                    "returncode": 0,
                    "elapsed_s": 0.1,
                    "stdout_tail": [],
                    "stderr_tail": [],
                },
                "target_package": {
                    "schema": "gpr.mission1_target_closure_package_run.v1",
                    "dry_run": True,
                    "repo_root": "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup",
                    "target": {"name": "Mission 1", "role": "camera", "raw_source_kind": "sensor_dma_capture"},
                    "steps": [
                        {
                            "name": "validate_dispatch_inputs",
                            "returncode": 0,
                            "cmd": [
                                "/usr/bin/python3",
                                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/check_mission1_camera_dispatch_inputs.py",
                                "--raw-source-kind",
                                "sensor_dma_capture",
                                "--raw-path",
                                "/dev/mission1/sensor_dma_ring",
                            ],
                        },
                        {
                            "name": "camera_hardware_audit",
                            "returncode": 0,
                            "cmd": [
                                "/usr/bin/python3",
                                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/mission1_camera_hardware_audit.py",
                                "--output-json",
                                "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/hardware_audit_receipt.json",
                                "--require-camera",
                            ],
                        },
                        {
                            "name": "target_preflight",
                            "returncode": 0,
                            "cmd": [
                                "/usr/bin/python3",
                                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/mission1_camera_target_preflight.py",
                                "--raw-source-kind",
                                "sensor_dma_capture",
                                "--frame-source",
                                "sensor DMA ring buffer",
                                "--write-path",
                                "Mission 1 camera storage writer path",
                                "--storage-medium",
                                "Mission 1 SD card",
                                "--display-surface",
                                "Mission 1 rear display",
                                "--presentation-path",
                                "Mission 1 rear display presentation path",
                            ],
                        },
                        {
                            "name": "camera_closure_run",
                            "returncode": 0,
                            "cmd": [
                                "/usr/bin/python3",
                                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/run_mission1_camera_closure.py",
                                "--raw-source-kind",
                                "sensor_dma_capture",
                                "--raw",
                                "/dev/mission1/sensor_dma_ring",
                                "--target-preflight-receipt",
                                "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json",
                            ],
                        },
                        {
                            "name": "collect_compact_receipts",
                            "returncode": 0,
                            "cmd": [
                                "/usr/bin/python3",
                                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/collect_mission1_target_closure.py",
                                "--include-timing-receipts",
                            ],
                        },
                    ],
                    "verdict": {"command_ready": True, "production_ready": False},
                },
                "collection_step": None,
                "verdict": {"launch_valid": True, "production_ready": False, "reason": None},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    preflight = external_root / "artifacts/mission1_camera_target_preflight_20260625"
    preflight.mkdir(parents=True)
    (preflight / "source_probe_fixture_followup_20260625.json").write_text(
        json.dumps(
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
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (preflight / "preflight_fixture_camera_20260625.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_camera_target_preflight.v1",
                "target": {"host": "192.168.16.67", "role": "camera", "name": "Mission 1"},
                "inputs": {
                    "raw_source_kind": "sensor_dma_capture",
                    "frame_source": "sensor DMA ring buffer",
                    "write_path": "Mission 1 camera storage writer path",
                    "storage_medium": "Mission 1 SD card",
                    "display_surface": "Mission 1 rear display",
                    "presentation_path": "Mission 1 rear display presentation path",
                },
                "checks": [
                    {"name": "ssh target probe", "passed": True, "detail": "returncode=0"},
                    {"name": "repo root exists", "passed": True, "detail": "/mnt/ssd/gpr_work/src"},
                    {"name": "raw source exists", "passed": True, "detail": "/mnt/ssd/mission1_native12/GP017602.raw"},
                    {"name": "raw source has unpacked Bayer size", "passed": True, "detail": "size=25165824 expected_min=25165824"},
                    {"name": "tool available: python3", "passed": True, "detail": "/usr/bin/python3"},
                    {"name": "executable available: bench_fused", "passed": True, "detail": "/mnt/ssd/gpr_work/build/bench_fused"},
                    {"name": "executable available: labs_encoder_bench_cli", "passed": True, "detail": "/mnt/ssd/gpr_work/build/labs_encoder_bench_cli"},
                    {"name": "executable available: fused_decode_cli", "passed": True, "detail": "/mnt/ssd/gpr_work/build/fused_decode_cli"},
                    {"name": "executable available: gvid_preview_rgb_cli", "passed": True, "detail": "/mnt/ssd/gpr_work/build/gvid_preview_rgb_cli"},
                    {"name": "output_dir writable", "passed": True, "detail": "/mnt/ssd/gpr_work/artifacts/current_camera"},
                    {"name": "scratch_dir writable", "passed": True, "detail": "/mnt/ssd/gpr_work/tmp"},
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
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    hardware = external_root / "artifacts/mission1_camera_target_discovery_20260625"
    hardware.mkdir(parents=True)
    (hardware / "hardware_audit_192_168_16_67_20260625.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_camera_hardware_audit.v1",
                "target": {"host": "192.168.16.67", "role": "camera", "name": "Mission 1"},
                "summary": {
                    "camera_enumerated": False,
                    "rpicam_has_camera": False,
                    "libcamera_has_camera": False,
                    "sensor_like_v4l_node_count": 0,
                    "video_node_count": 17,
                    "tools": {
                        "v4l2-ctl": "/usr/bin/v4l2-ctl",
                        "media-ctl": "/usr/bin/media-ctl",
                        "libcamera-hello": "/usr/bin/libcamera-hello",
                        "rpicam-hello": "/usr/bin/rpicam-hello",
                        "rpicam-raw": "/usr/bin/rpicam-raw",
                    },
                },
                "blockers": ["no camera sensor is enumerated by rpicam/libcamera/V4L"],
                "verdict": {
                    "hardware_ready_for_camera_source": False,
                    "remaining_blocker_count": 1,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    blocked = external_root / "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625"
    blocked.mkdir(parents=True)
    hardware_receipt = {
        "schema": "gpr.mission1_camera_hardware_audit.v1",
        "target": {"host": "local", "role": "camera", "name": "Mission 1"},
        "summary": {
            "camera_enumerated": False,
            "rpicam_has_camera": False,
            "libcamera_has_camera": False,
            "sensor_like_v4l_node_count": 0,
            "video_node_count": 17,
            "tools": {
                "v4l2-ctl": "/usr/bin/v4l2-ctl",
                "media-ctl": "/usr/bin/media-ctl",
                "libcamera-hello": "/usr/bin/libcamera-hello",
                "rpicam-hello": "/usr/bin/rpicam-hello",
                "rpicam-raw": "/usr/bin/rpicam-raw",
            },
        },
        "blockers": ["no camera sensor is enumerated by rpicam/libcamera/V4L"],
        "verdict": {
            "hardware_ready_for_camera_source": False,
            "remaining_blocker_count": 1,
        },
    }
    (blocked / "hardware_audit_receipt.json").write_text(
        json.dumps(hardware_receipt, indent=2) + "\n",
        encoding="utf-8",
    )
    blocked_steps = [
        {
            "name": "validate_dispatch_inputs",
            "cmd": [
                "/usr/bin/python3",
                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/check_mission1_camera_dispatch_inputs.py",
                "--raw-source-kind",
                "sensor_dma_capture",
                "--raw-path",
                "/dev/mission1/sensor_dma_ring",
            ],
            "returncode": 0,
            "elapsed_s": 0.037,
            "stdout_tail": ["Mission 1 camera dispatch input check OK"],
            "stderr_tail": [],
        },
        {
            "name": "camera_hardware_audit",
            "cmd": [
                "/usr/bin/python3",
                "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/tools/mission1_camera_hardware_audit.py",
                "--output-json",
                "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/hardware_audit_receipt.json",
                "--require-camera",
            ],
            "returncode": 2,
            "elapsed_s": 0.145,
            "stdout_tail": [],
            "stderr_tail": [],
        },
    ]
    target_package = {
        "schema": "gpr.mission1_target_closure_package_run.v1",
        "dry_run": False,
        "repo_root": "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup",
        "output_dir": "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625",
        "collection_output_dir": "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_compact_20260625",
        "target": {"name": "Mission 1", "role": "camera", "raw_source_kind": "sensor_dma_capture"},
        "steps": blocked_steps,
        "verdict": {
            "command_ready": False,
            "production_ready": False,
            "reason": "camera_hardware_audit_failed",
        },
    }
    (blocked / "target_closure_package_run.json").write_text(
        json.dumps(target_package, indent=2) + "\n",
        encoding="utf-8",
    )
    (blocked / "remote_closure_summary.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_remote_closure_package_run.v1",
                "dry_run": False,
                "target_host": "192.168.16.67",
                "remote_repo_root": "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup",
                "remote_output_dir": "/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625",
                "local_output_dir": str(blocked),
                "target_role": "camera",
                "raw_source_kind": "sensor_dma_capture",
                "camera_ready_flags": {
                    "camera_frame_source_ready": True,
                    "camera_storage_path_ready": True,
                    "camera_display_path_ready": True,
                    "sensor_dma_executed": True,
                    "storage_handoff_executed": True,
                    "ui_path_executed": True,
                    "visual_checked": True,
                },
                "package_step": {
                    "cmd": [
                        "ssh",
                        "192.168.16.67",
                        "python3 tools/run_mission1_target_closure_package.py --raw /dev/mission1/sensor_dma_ring --raw-source-kind sensor_dma_capture",
                    ],
                    "returncode": 1,
                    "elapsed_s": 0.55,
                    "stdout_tail": [],
                    "stderr_tail": [],
                },
                "target_package": target_package,
                "collection_step": None,
                "failure_collection_step": {
                    "name": "collect_early_failure_receipts",
                    "returncode": 0,
                    "files": [
                        {"file": "target_closure_package_run.json", "copied": True},
                        {"file": "hardware_audit_receipt.json", "copied": True},
                        {"file": "target_preflight_receipt.json", "copied": False},
                    ],
                },
                "verdict": {
                    "launch_valid": False,
                    "production_ready": False,
                    "reason": "package_or_collection_failed",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    collection = external_root / "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625"
    collection.mkdir(parents=True)
    (collection / "collection_receipt.json").write_text(
        json.dumps(
            {
                "schema": "gpr.mission1_target_closure_collection.v1",
                "files": [
                    {
                        "file": "target_preflight_receipt.json",
                        "exists": True,
                        "schema": "gpr.mission1_camera_target_preflight.v1",
                        "verdict": {
                            "target_preflight_ready": True,
                            "camera_closure_possible": False,
                        },
                    },
                    {
                        "file": "labs_target_bench.json",
                        "exists": True,
                        "schema": "gpr_labs_target_bench.v1",
                    },
                    {
                        "file": "mission1_camera_closure_run.json",
                        "exists": True,
                        "schema": "gpr.mission1_camera_closure_run.v1",
                        "verdict": {
                            "production_ready": False,
                            "target_preflight_ready": True,
                            "camera_closure_possible": False,
                        },
                    },
                    {
                        "file": "camera_handoff_receipt.json",
                        "exists": True,
                        "schema": "gpr_labs_camera_handoff_receipt.v1",
                    },
                    {
                        "file": "preview_ui_receipt.json",
                        "exists": True,
                        "schema": "gpr_labs_preview_ui_receipt.v1",
                    },
                ],
                "validation": {"returncode": 0},
                "closure_verdict": {
                    "production_ready": False,
                    "target_preflight_ready": True,
                    "camera_closure_possible": False,
                },
                "verdict": {"collection_valid": True, "production_ready": False},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    signoff = external_root / "artifacts/mission1_4k_cleanup_visual_signoff_20260625"
    signoff.mkdir(parents=True)
    (signoff / "production_signoff.json").write_text(
        json.dumps(
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
                    "check_count": 7,
                },
                "raw_domain_guard": {
                    "path": "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_rgb_cfa_target_gate_wb_review/summary.json",
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
                    "name": "fixture reviewer",
                    "role": "engineering-review",
                    "reviewed_at_utc": "2026-06-25T00:00:00Z",
                },
                "review": {
                    "visual_checked": True,
                    "contact_sheet_path": "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff_contact_sheet.jpg",
                    "dashboard_paths": ["artifacts/example/index.html"],
                    "blocking_issues": [],
                },
                "verdict": {
                    "production_ready": True,
                    "accepted_role": "production",
                    "no_blocking_visual_issues": True,
                },
                "diagnostics": {
                    "legacy_clean_low_raw_guard": {
                        "production_blocking": False,
                        "note": "diagnostic",
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    extra = external_root / "artifacts/non_manifest_hash_receipt.json"
    extra.write_text(json.dumps({"schema": "fixture.extra_hash.v1"}, indent=2) + "\n", encoding="utf-8")


def write_production_artifacts_doc(
    repo_root: Path,
    external_root: Path,
    source_probe_sha: str | None = None,
    extra_sha: str | None = None,
) -> None:
    source_probe_rel = (
        "artifacts/mission1_camera_target_preflight_20260625/"
        "source_probe_fixture_followup_20260625.json"
    )
    extra_rel = "artifacts/non_manifest_hash_receipt.json"
    source_probe = external_root / source_probe_rel
    extra = external_root / extra_rel
    sha = source_probe_sha or sha256_file(source_probe)
    extra_digest = extra_sha or sha256_file(extra)
    docs = repo_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PRODUCTION_ARTIFACTS.md").write_text(
        "\n".join(
            [
                "# Fixture Production Artifacts",
                "",
                "| artifact | path | sha256 |",
                "|---|---|---|",
                f"| fixture source probe | `{source_probe_rel}` | `{sha}` |",
                f"| fixture non-manifest receipt | `{extra_rel}` | `{extra_digest}` |",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_tool(module, manifest: Path) -> tuple[int, dict]:
    old_manifest = module.MANIFEST
    old_repo = module.REPO
    old_argv = sys.argv[:]
    stdout = io.StringIO()
    try:
        module.REPO = manifest.parent
        module.MANIFEST = manifest
        sys.argv = ["verify_release_manifest_artifacts.py", "--strict", "--json"]
        with contextlib.redirect_stdout(stdout):
            code = module.main()
    finally:
        module.REPO = old_repo
        module.MANIFEST = old_manifest
        sys.argv = old_argv
    return code, json.loads(stdout.getvalue())


def run_tool_text(module, manifest: Path, *args: str) -> tuple[int, str]:
    old_manifest = module.MANIFEST
    old_repo = module.REPO
    old_argv = sys.argv[:]
    stdout = io.StringIO()
    try:
        module.REPO = manifest.parent
        module.MANIFEST = manifest
        sys.argv = ["verify_release_manifest_artifacts.py", *args]
        with contextlib.redirect_stdout(stdout):
            code = module.main()
    finally:
        module.REPO = old_repo
        module.MANIFEST = old_manifest
        sys.argv = old_argv
    return code, stdout.getvalue()


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="verify_release_manifest_artifacts_", dir=work_parent) as td:
        root = Path(td)
        external = root / "external"
        manifest = root / "manifest.json"
        write_artifacts(external)
        write_production_artifacts_doc(root, external)

        module = import_tool()
        with patched_env(GPR_EXTERNAL_ROOT=str(external), GPR_ARTIFACT_ROOT=str(external / "artifacts")):
            write_manifest(manifest, external, blockers=1)
            code, payload = run_tool(module, manifest)
            if code != 0 or payload.get("failures") != 0:
                print(f"expected verifier success, got code={code} payload={payload}", file=sys.stderr)
                return 1
            summary_code, summary_text = run_tool_text(module, manifest, "--strict", "--summary")
            if summary_code != 0 or "failures=0" not in summary_text:
                print(
                    "expected summary verifier success with failures=0: "
                    f"code={summary_code} text={summary_text}",
                    file=sys.stderr,
                )
                return 1
            if "=== artifact failures ===" in summary_text:
                print(
                    f"expected successful summary to omit failure rows: {summary_text}",
                    file=sys.stderr,
                )
                return 1
            production_rows = payload.get("production_artifacts") or []
            if not any(row.get("ref") == "artifacts/non_manifest_hash_receipt.json" for row in production_rows):
                print(
                    f"expected non-manifest production artifact hash row, got {production_rows}",
                    file=sys.stderr,
                )
                return 1

            write_production_artifacts_doc(root, external, source_probe_sha="0" * 64)
            hash_code, hash_payload = run_tool(module, manifest)
            hash_rows = [
                row for row in hash_payload.get("artifacts", [])
                if row.get("ref")
                == "artifacts/mission1_camera_target_preflight_20260625/source_probe_fixture_followup_20260625.json"
            ]
            if hash_code == 0 or not hash_rows or hash_rows[0].get("status") != "sha_mismatch":
                print(
                    "expected production artifact hash mismatch to fail: "
                    f"code={hash_code} rows={hash_rows}",
                    file=sys.stderr,
                )
                return 1
            summary_hash_code, summary_hash_text = run_tool_text(module, manifest, "--strict", "--summary")
            if (
                summary_hash_code == 0
                or "failures=" not in summary_hash_text
                or "sha_mismatch" not in summary_hash_text
                or "=== artifact failures ===" not in summary_hash_text
            ):
                print(
                    "expected summary verifier failure to show bad rows: "
                    f"code={summary_hash_code} text={summary_hash_text}",
                    file=sys.stderr,
                )
                return 1
            write_production_artifacts_doc(root, external)

            write_production_artifacts_doc(root, external, extra_sha="0" * 64)
            extra_hash_code, extra_hash_payload = run_tool(module, manifest)
            extra_hash_rows = [
                row for row in extra_hash_payload.get("production_artifacts", [])
                if row.get("ref") == "artifacts/non_manifest_hash_receipt.json"
            ]
            if (
                extra_hash_code == 0
                or not extra_hash_rows
                or extra_hash_rows[0].get("status") != "sha_mismatch"
            ):
                print(
                    "expected non-manifest production artifact hash mismatch to fail: "
                    f"code={extra_hash_code} rows={extra_hash_rows}",
                    file=sys.stderr,
                )
                return 1
            write_production_artifacts_doc(root, external)

            source_probe_path = external / "artifacts/mission1_camera_target_preflight_20260625/source_probe_fixture_followup_20260625.json"
            source_probe = json.loads(source_probe_path.read_text(encoding="utf-8"))
            source_probe["checks"][1]["passed"] = True
            source_probe_path.write_text(json.dumps(source_probe, indent=2) + "\n", encoding="utf-8")
            source_probe_code, source_probe_payload = run_tool(module, manifest)
            source_probe_rows = [
                row for row in source_probe_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_target_preflight_20260625/source_probe_fixture_followup_20260625.json"
            ]
            if source_probe_code == 0 or not source_probe_rows or source_probe_rows[0].get("status") != "bad_semantics":
                print(
                    "expected follow-up source probe with passing endpoint check to fail: "
                    f"code={source_probe_code} rows={source_probe_rows}",
                    file=sys.stderr,
                )
                return 1
            source_probe["checks"][1]["passed"] = False
            source_probe_path.write_text(json.dumps(source_probe, indent=2) + "\n", encoding="utf-8")

            hardware_path = external / "artifacts/mission1_camera_target_discovery_20260625/hardware_audit_192_168_16_67_20260625.json"
            hardware = json.loads(hardware_path.read_text(encoding="utf-8"))
            hardware["summary"]["camera_enumerated"] = True
            hardware_path.write_text(json.dumps(hardware, indent=2) + "\n", encoding="utf-8")
            hardware_code, hardware_payload = run_tool(module, manifest)
            hardware_rows = [
                row for row in hardware_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_target_discovery_20260625/hardware_audit_192_168_16_67_20260625.json"
            ]
            if hardware_code == 0 or not hardware_rows or hardware_rows[0].get("status") != "bad_semantics":
                print(
                    "expected hardware audit with false camera enumeration claim to fail: "
                    f"code={hardware_code} rows={hardware_rows}",
                    file=sys.stderr,
                )
                return 1
            hardware["summary"]["camera_enumerated"] = False
            hardware_path.write_text(json.dumps(hardware, indent=2) + "\n", encoding="utf-8")

            blocked_remote_path = external / "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json"
            blocked_remote = json.loads(blocked_remote_path.read_text(encoding="utf-8"))
            blocked_remote["verdict"]["launch_valid"] = True
            blocked_remote_path.write_text(json.dumps(blocked_remote, indent=2) + "\n", encoding="utf-8")
            blocked_remote_code, blocked_remote_payload = run_tool(module, manifest)
            blocked_remote_rows = [
                row for row in blocked_remote_payload.get("artifacts", [])
                if row.get("ref")
                == "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json"
            ]
            if (
                blocked_remote_code == 0
                or not blocked_remote_rows
                or blocked_remote_rows[0].get("status") != "bad_semantics"
            ):
                print(
                    "expected hardware-blocked remote run with launch_valid=true to fail: "
                    f"code={blocked_remote_code} rows={blocked_remote_rows}",
                    file=sys.stderr,
                )
                return 1
            blocked_remote["verdict"]["launch_valid"] = False
            blocked_remote_path.write_text(json.dumps(blocked_remote, indent=2) + "\n", encoding="utf-8")

            preflight_path = external / "artifacts/mission1_camera_target_preflight_20260625/preflight_fixture_camera_20260625.json"
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            preflight["blockers"] = ["camera frame source ready"]
            preflight["verdict"]["remaining_blocker_count"] = 1
            preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
            preflight_code, preflight_payload = run_tool(module, manifest)
            preflight_rows = [
                row for row in preflight_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_target_preflight_20260625/preflight_fixture_camera_20260625.json"
            ]
            if preflight_code == 0 or not preflight_rows or preflight_rows[0].get("status") != "bad_semantics":
                print(
                    "expected camera preflight missing camera blockers to fail: "
                    f"code={preflight_code} rows={preflight_rows}",
                    file=sys.stderr,
                )
                return 1
            preflight["blockers"] = [
                "camera frame source ready",
                "camera storage path ready",
                "camera display path ready",
            ]
            preflight["verdict"]["remaining_blocker_count"] = 3
            preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

            saved_frame_source = preflight["inputs"].pop("frame_source")
            preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
            label_code, label_payload = run_tool(module, manifest)
            label_rows = [
                row for row in label_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_target_preflight_20260625/preflight_fixture_camera_20260625.json"
            ]
            if label_code == 0 or not label_rows or label_rows[0].get("status") != "bad_semantics":
                print(
                    "expected camera preflight missing concrete label to fail: "
                    f"code={label_code} rows={label_rows}",
                    file=sys.stderr,
                )
                return 1
            preflight["inputs"]["frame_source"] = saved_frame_source
            preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

            write_manifest(manifest, external, blockers=3)
            bad_code, bad_payload = run_tool(module, manifest)
            bad_rows = [
                row for row in bad_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json"
            ]
            if bad_code == 0 or not bad_rows or bad_rows[0].get("status") != "bad_semantics":
                print(
                    "expected closure plan semantic mismatch to fail: "
                    f"code={bad_code} rows={bad_rows}",
                    file=sys.stderr,
                )
                return 1

            write_manifest(manifest, external, blockers=1)
            readiness_path = external / "artifacts/mission1_numbered_list_readiness_20260625/readiness.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            readiness["overall_status"] = "production_ready"
            readiness_path.write_text(json.dumps(readiness, indent=2) + "\n", encoding="utf-8")
            drift_code, drift_payload = run_tool(module, manifest)
            drift_rows = [
                row for row in drift_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_numbered_list_readiness_20260625/readiness.json"
            ]
            if drift_code == 0 or not drift_rows or drift_rows[0].get("status") != "bad_semantics":
                print(
                    "expected readiness/closure semantic mismatch to fail: "
                    f"code={drift_code} rows={drift_rows}",
                    file=sys.stderr,
                )
                return 1

            readiness["overall_status"] = "evidence_passes_with_production_blockers"
            readiness_path.write_text(json.dumps(readiness, indent=2) + "\n", encoding="utf-8")
            collection_path = external / "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/collection_receipt.json"
            collection = json.loads(collection_path.read_text(encoding="utf-8"))
            collection["files"] = [
                row for row in collection["files"]
                if row.get("file") != "target_preflight_receipt.json"
            ]
            collection_path.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
            collection_code, collection_payload = run_tool(module, manifest)
            collection_rows = [
                row for row in collection_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/collection_receipt.json"
            ]
            if collection_code == 0 or not collection_rows or collection_rows[0].get("status") != "bad_semantics":
                print(
                    "expected closure collection missing preflight to fail: "
                    f"code={collection_code} rows={collection_rows}",
                    file=sys.stderr,
                )
                return 1

            collection["files"].append(
                {
                    "file": "target_preflight_receipt.json",
                    "exists": True,
                    "schema": "gpr.mission1_camera_target_preflight.v1",
                    "verdict": {
                        "target_preflight_ready": True,
                        "camera_closure_possible": False,
                    },
                }
            )
            collection_path.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
            collection["verdict"]["production_ready"] = True
            collection_path.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
            false_ready_code, false_ready_payload = run_tool(module, manifest)
            false_ready_rows = [
                row for row in false_ready_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/collection_receipt.json"
            ]
            if (
                false_ready_code == 0
                or not false_ready_rows
                or false_ready_rows[0].get("status") != "bad_semantics"
            ):
                print(
                    "expected closure collection false production_ready to fail: "
                    f"code={false_ready_code} rows={false_ready_rows}",
                    file=sys.stderr,
                )
                return 1

            collection["verdict"]["production_ready"] = False
            collection_path.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
            signoff_path = external / "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
            signoff = json.loads(signoff_path.read_text(encoding="utf-8"))
            signoff["raw_domain_guard"]["passed"] = False
            signoff_path.write_text(json.dumps(signoff, indent=2) + "\n", encoding="utf-8")
            signoff_code, signoff_payload = run_tool(module, manifest)
            signoff_rows = [
                row for row in signoff_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
            ]
            if signoff_code == 0 or not signoff_rows or signoff_rows[0].get("status") != "bad_semantics":
                print(
                    "expected current 4K cleanup signoff with failing high-res raw guard to fail: "
                    f"code={signoff_code} rows={signoff_rows}",
                    file=sys.stderr,
                )
                return 1
            signoff["raw_domain_guard"]["passed"] = True
            signoff_path.write_text(json.dumps(signoff, indent=2) + "\n", encoding="utf-8")

            package_path = external / "artifacts/mission1_camera_closure_package_20260625/closure_package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["target_preflight"]["target"]["role"] = "camera"
            package["target_preflight"]["verdict"]["camera_closure_possible"] = True
            package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
            package_code, package_payload = run_tool(module, manifest)
            package_rows = [
                row for row in package_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_package_20260625/closure_package.json"
            ]
            if package_code == 0 or not package_rows or package_rows[0].get("status") != "bad_semantics":
                print(
                    "expected stale non-production closure package preflight to fail: "
                    f"code={package_code} rows={package_rows}",
                    file=sys.stderr,
                )
                return 1

            package["target_preflight"]["target"]["role"] = "stand-in"
            package["target_preflight"]["verdict"]["camera_closure_possible"] = False
            package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

            production_package = json.loads(json.dumps(package))
            production_package["remaining_blockers"] = []
            production_package["current_receipts"] = []
            production_package["acceptance_audit"] = []
            production_package["target_preflight"]["target"]["role"] = "camera"
            production_package["target_preflight"]["verdict"]["target_preflight_ready"] = True
            production_package["target_preflight"]["verdict"]["camera_closure_possible"] = True
            production_package["verdict"] = {
                "production_ready": True,
                "reason": "numbered_list_final_gate_ready",
                "remaining_blocker_count": 0,
            }
            package_path.write_text(json.dumps(production_package, indent=2) + "\n", encoding="utf-8")
            production_package_code, production_package_payload = run_tool(module, manifest)
            production_package_rows = [
                row for row in production_package_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_package_20260625/closure_package.json"
            ]
            if (
                production_package_code == 0
                or not production_package_rows
                or production_package_rows[0].get("status") != "bad_semantics"
                or "camera_handoff_receipt summary" not in production_package_rows[0].get("error", "")
            ):
                print(
                    "expected production closure package without final receipts to fail: "
                    f"code={production_package_code} rows={production_package_rows}",
                    file=sys.stderr,
                )
                return 1

            package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
            launch_path = external / "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json"
            launch = json.loads(launch_path.read_text(encoding="utf-8"))
            saved_raw_source_kind = launch["target"].pop("raw_source_kind")
            launch_path.write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
            raw_kind_code, raw_kind_payload = run_tool(module, manifest)
            raw_kind_rows = [
                row for row in raw_kind_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json"
            ]
            if raw_kind_code == 0 or not raw_kind_rows or raw_kind_rows[0].get("status") != "bad_semantics":
                print(
                    "expected camera launch without raw_source_kind to fail: "
                    f"code={raw_kind_code} rows={raw_kind_rows}",
                    file=sys.stderr,
                )
                return 1

            launch["target"]["raw_source_kind"] = saved_raw_source_kind
            saved_dispatch_cmd = list(launch["steps"][0]["cmd"])
            raw_idx = launch["steps"][0]["cmd"].index("--raw-path")
            del launch["steps"][0]["cmd"][raw_idx:raw_idx + 2]
            launch_path.write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
            raw_path_code, raw_path_payload = run_tool(module, manifest)
            raw_path_rows = [
                row for row in raw_path_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json"
            ]
            if raw_path_code == 0 or not raw_path_rows or raw_path_rows[0].get("status") != "bad_semantics":
                print(
                    "expected camera launch without raw-path to fail: "
                    f"code={raw_path_code} rows={raw_path_rows}",
                    file=sys.stderr,
                )
                return 1

            launch["steps"][0]["cmd"] = saved_dispatch_cmd
            saved_closure_cmd = list(launch["steps"][3]["cmd"])
            preflight_idx = launch["steps"][3]["cmd"].index("--target-preflight-receipt")
            del launch["steps"][3]["cmd"][preflight_idx:preflight_idx + 2]
            launch_path.write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
            preflight_flag_code, preflight_flag_payload = run_tool(module, manifest)
            preflight_flag_rows = [
                row for row in preflight_flag_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json"
            ]
            if (
                preflight_flag_code == 0
                or not preflight_flag_rows
                or preflight_flag_rows[0].get("status") != "bad_semantics"
            ):
                print(
                    "expected camera launch without target-preflight receipt to fail: "
                    f"code={preflight_flag_code} rows={preflight_flag_rows}",
                    file=sys.stderr,
                )
                return 1

            launch["steps"][3]["cmd"] = saved_closure_cmd
            launch["steps"][-1]["cmd"] = ["python3", "tools/collect_mission1_target_closure.py"]
            launch_path.write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
            launch_code, launch_payload = run_tool(module, manifest)
            launch_rows = [
                row for row in launch_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json"
            ]
            if launch_code == 0 or not launch_rows or launch_rows[0].get("status") != "bad_semantics":
                print(
                    "expected camera launch without timing receipts to fail: "
                    f"code={launch_code} rows={launch_rows}",
                    file=sys.stderr,
                )
                return 1

            launch["steps"][-1]["cmd"] = [
                "python3",
                "tools/collect_mission1_target_closure.py",
                "--include-timing-receipts",
            ]
            launch["steps"][0]["cmd"][1] = "/Volumes/OWC_8TB/gpr_work/tools/check_mission1_camera_dispatch_inputs.py"
            launch_path.write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
            host_path_code, host_path_payload = run_tool(module, manifest)
            host_path_rows = [
                row for row in host_path_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json"
            ]
            if host_path_code == 0 or not host_path_rows or host_path_rows[0].get("status") != "bad_semantics":
                print(
                    "expected camera launch with host-local path to fail: "
                    f"code={host_path_code} rows={host_path_rows}",
                    file=sys.stderr,
                )
                return 1

            remote_launch_path = external / "artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json"
            remote_launch = json.loads(remote_launch_path.read_text(encoding="utf-8"))
            saved_remote_raw_source_kind = remote_launch.pop("raw_source_kind")
            remote_launch_path.write_text(json.dumps(remote_launch, indent=2) + "\n", encoding="utf-8")
            remote_raw_kind_code, remote_raw_kind_payload = run_tool(module, manifest)
            remote_raw_kind_rows = [
                row for row in remote_raw_kind_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json"
            ]
            if remote_raw_kind_code == 0 or not remote_raw_kind_rows or remote_raw_kind_rows[0].get("status") != "bad_semantics":
                print(
                    "expected remote camera launch without raw_source_kind to fail: "
                    f"code={remote_raw_kind_code} rows={remote_raw_kind_rows}",
                    file=sys.stderr,
                )
                return 1

            remote_launch["raw_source_kind"] = saved_remote_raw_source_kind
            saved_package_cmd = list(remote_launch["package_step"]["cmd"])
            remote_launch["package_step"]["cmd"][-1] = remote_launch["package_step"]["cmd"][-1].replace(
                "/dev/mission1/sensor_dma_ring",
                "/mnt/ssd/mission1_native12/GP017602.raw",
            )
            remote_launch_path.write_text(json.dumps(remote_launch, indent=2) + "\n", encoding="utf-8")
            remote_raw_path_code, remote_raw_path_payload = run_tool(module, manifest)
            remote_raw_path_rows = [
                row for row in remote_raw_path_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json"
            ]
            if remote_raw_path_code == 0 or not remote_raw_path_rows or remote_raw_path_rows[0].get("status") != "bad_semantics":
                print(
                    "expected remote camera launch with fixture raw path to fail: "
                    f"code={remote_raw_path_code} rows={remote_raw_path_rows}",
                    file=sys.stderr,
                )
                return 1

            remote_launch["package_step"]["cmd"] = saved_package_cmd
            remote_launch["target_package"]["steps"][0]["cmd"][1] = "/Volumes/OWC_8TB/gpr_work/tools/check_mission1_camera_dispatch_inputs.py"
            remote_launch_path.write_text(json.dumps(remote_launch, indent=2) + "\n", encoding="utf-8")
            remote_launch_code, remote_launch_payload = run_tool(module, manifest)
            remote_launch_rows = [
                row for row in remote_launch_payload.get("artifacts", [])
                if row.get("ref") == "artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json"
            ]
            if remote_launch_code == 0 or not remote_launch_rows or remote_launch_rows[0].get("status") != "bad_semantics":
                print(
                    "expected remote camera launch with target host-local path to fail: "
                    f"code={remote_launch_code} rows={remote_launch_rows}",
                    file=sys.stderr,
                )
                return 1

    print("test_verify_release_manifest_artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
