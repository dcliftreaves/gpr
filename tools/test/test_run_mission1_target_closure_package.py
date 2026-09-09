#!/usr/bin/env python3
"""Tests for the one-command Mission 1 target closure package wrapper."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/run_mission1_target_closure_package.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_standin_dry_run_builds_package_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "target_run"
        collect = Path(tmp) / "collected"
        proc = run_tool(
            "--output-dir",
            str(out),
            "--collection-output-dir",
            str(collect),
            "--dry-run",
            "--cleanup-heavy",
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["schema"] == "gpr.mission1_target_closure_package_run.v1"
        assert payload["dry_run"] is True
        assert payload["target"]["role"] == "stand-in"
        assert payload["target"]["raw_source_kind"] == "file_standin"
        assert [step["name"] for step in payload["steps"]] == [
            "validate_dispatch_inputs",
            "target_preflight",
            "camera_closure_run",
            "collect_compact_receipts",
        ]
        assert payload["receipts"]["hardware_audit"] == str(out / "hardware_audit_receipt.json")
        assert payload["cleanup"]["dry_run"] is True
        assert payload["verdict"]["command_ready"] is True
        assert payload["verdict"]["production_ready"] is False
        assert not out.exists()
        assert not collect.exists()

        preflight_cmd = payload["steps"][1]["cmd"]
        closure_cmd = payload["steps"][2]["cmd"]
        collection_cmd = payload["steps"][3]["cmd"]
        assert "mission1_camera_target_preflight.py" in " ".join(preflight_cmd)
        assert "run_mission1_camera_closure.py" in " ".join(closure_cmd)
        assert "collect_mission1_target_closure.py" in " ".join(collection_cmd)
        assert "build-closure/source/app/bench_fused/bench_fused" in preflight_cmd
        assert "build-closure/bin/labs_encoder_bench_cli" in preflight_cmd
        assert "build-closure/bin/fused_decode_cli" in preflight_cmd
        assert "build-closure/bin/gvid_preview_rgb_cli" in preflight_cmd
        assert "build-closure/source/app/bench_fused/bench_fused" in closure_cmd
        assert "build-closure/bin/fused_decode_cli" in closure_cmd
        assert "build/bin/labs_encoder_bench_cli" not in " ".join(preflight_cmd)
        assert "--target-preflight-receipt" in closure_cmd
        assert "--source-provenance-root" in closure_cmd
        assert "--include-timing-receipts" in collection_cmd
        assert str(out / "target_preflight_receipt.json") in closure_cmd


def test_camera_dry_run_rejects_standin_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "target_run"
        proc = run_tool("--output-dir", str(out), "--target-role", "camera", "--dry-run")
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert "camera-role dispatch" in "\n".join(payload["steps"][0]["stderr_tail"])
        assert payload["verdict"]["reason"] == "validate_dispatch_inputs_failed"
        assert payload["steps"][0]["name"] == "validate_dispatch_inputs"
        assert payload["steps"][0]["returncode"] == 1
        assert any("raw_source_kind" in line for line in payload["steps"][0]["stderr_tail"])


def test_camera_ready_dry_run_is_not_production_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "target_run"
        proc = run_tool(
            "--output-dir",
            str(out),
            "--target-name",
            "Mission 1",
            "--target-role",
            "camera",
            "--raw",
            "/dev/mission1/sensor_dma_ring",
            "--raw-source-kind",
            "sensor_dma_capture",
            "--frame-source",
            "Mission 1 sensor DMA",
            "--write-path",
            "Mission 1 camera storage writer",
            "--storage-medium",
            "Mission 1 SD path",
            "--storage-ownership",
            "camera firmware owns write buffer through storage completion",
            "--display-surface",
            "Mission 1 rear display",
            "--presentation-path",
            "Mission 1 rear display presentation path",
            "--preview-buffer-ownership",
            "camera display process RGB output buffer",
            "--camera-frame-source-ready",
            "--camera-storage-path-ready",
            "--camera-display-path-ready",
            "--sensor-dma-executed",
            "--storage-handoff-executed",
            "--ui-path-executed",
            "--visual-checked",
            "--handoff-blocker-cause",
            "none",
            "--preview-blocker-cause",
            "none",
            "--dry-run",
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["dry_run"] is True
        assert payload["target"]["role"] == "camera"
        assert payload["target"]["raw_source_kind"] == "sensor_dma_capture"
        assert payload["verdict"]["command_ready"] is True
        assert payload["verdict"]["production_ready"] is False
        assert [step["name"] for step in payload["steps"]] == [
            "validate_dispatch_inputs",
            "camera_hardware_audit",
            "target_preflight",
            "camera_closure_run",
        ]
        hardware_cmd = payload["steps"][1]["cmd"]
        assert "mission1_camera_hardware_audit.py" in " ".join(hardware_cmd)
        assert "--require-camera" in hardware_cmd
        assert str(out / "hardware_audit_receipt.json") in hardware_cmd
        assert not out.exists()


def main() -> int:
    test_standin_dry_run_builds_package_contract()
    test_camera_dry_run_rejects_standin_defaults()
    test_camera_ready_dry_run_is_not_production_evidence()
    print("test_run_mission1_target_closure_package: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
