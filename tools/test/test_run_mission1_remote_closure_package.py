#!/usr/bin/env python3
"""Tests for the host-side Mission 1 remote closure launcher."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/run_mission1_remote_closure_package.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("run_mission1_remote_closure_package", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    tool = load_tool()
    args = tool.parser().parse_args(
        [
            "--target-host",
            "192.168.16.67",
            "--dry-run",
            "--camera-ready",
            "--summary-json",
            "/tmp/remote_summary.json",
        ]
    )
    tool.apply_camera_ready_defaults(args)

    assert args.camera_frame_source_ready is True
    assert args.camera_storage_path_ready is True
    assert args.camera_display_path_ready is True
    assert args.sensor_dma_executed is True
    assert args.storage_handoff_executed is True
    assert args.ui_path_executed is True
    assert args.visual_checked is True
    assert args.raw_source_kind == "sensor_dma_capture"
    assert args.handoff_blocker_cause == "none"
    assert args.preview_blocker_cause == "none"

    target_cmd = tool.target_package_cmd(args)
    assert target_cmd[:2] == ["python3", "tools/run_mission1_target_closure_package.py"]
    for flag in (
        "--dry-run",
        "--camera-frame-source-ready",
        "--camera-storage-path-ready",
        "--camera-display-path-ready",
        "--sensor-dma-executed",
        "--storage-handoff-executed",
        "--ui-path-executed",
        "--visual-checked",
        "--cleanup-heavy",
        "--raw-source-kind",
    ):
        assert flag in target_cmd
    assert "sensor_dma_capture" in target_cmd
    assert "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup" in target_cmd
    assert "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/bin/labs_encoder_bench_cli" in target_cmd
    assert "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/bin/fused_decode_cli" in target_cmd
    assert "/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/bin/gvid_preview_rgb_cli" in target_cmd
    assert "/mnt/ssd/gpr_work/tmp/build_labs_shim_20260625" not in " ".join(target_cmd)
    assert "/Volumes/OWC_8TB" not in " ".join(target_cmd)

    ssh = tool.ssh_cmd(args, target_cmd)
    assert ssh[:5] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    assert ssh[5] == "192.168.16.67"
    assert "cd /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup" in ssh[6]
    assert "run_mission1_target_closure_package.py" in ssh[6]

    collect = tool.collect_cmd(args)
    assert "tools/collect_mission1_target_closure.py" in collect[1]
    assert "--include-timing-receipts" in collect
    assert "--target-host" in collect
    assert "192.168.16.67" in collect
    assert tool.EARLY_FAILURE_RECEIPTS == (
        "target_closure_package_run.json",
        "hardware_audit_receipt.json",
        "target_preflight_receipt.json",
    )

    failed_summary = tool.build_summary(
        args,
        {"cmd": ["ssh"], "returncode": 1, "stdout": "", "stderr_tail": ["failed"]},
        None,
        {
            "name": "collect_early_failure_receipts",
            "returncode": 0,
            "files": [{"file": "hardware_audit_receipt.json", "copied": True}],
        },
        {"verdict": {"production_ready": False, "reason": "camera_hardware_audit_failed"}},
    )
    assert failed_summary["verdict"]["launch_valid"] is False
    assert failed_summary["failure_collection_step"]["returncode"] == 0
    assert failed_summary["collection_step"] is None

    print("test_run_mission1_remote_closure_package: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
