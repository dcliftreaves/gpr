#!/usr/bin/env python3
"""Regression test for the Mission 1 camera closure package."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_mission1_camera_closure_package.py"
CHECKER = ROOT / "tools/check_mission1_camera_closure_package.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def create_fixture(root: Path) -> None:
    base = root / "artifacts/mission1_numbered_list_readiness_20260625"
    handoff = "artifacts/current/camera_handoff_receipt.json"
    preview = "artifacts/current/preview_ui_receipt.json"
    preflight = "artifacts/current/preflight.json"
    write_json(
        base / "readiness.json",
        {
            "schema": "gpr.mission1_numbered_list_readiness.v1",
            "overall_status": "evidence_passes_with_production_blockers",
            "blockers": [
                "Mission 1 firmware/camera-side handoff receipt is still required.",
                "Mission 1 camera preview UI receipt is still required.",
            ],
        },
    )
    write_json(
        base / "closure_plan.json",
        {
            "schema": "gpr.mission1_numbered_list_closure_plan.v1",
            "production_ready": False,
            "final_gate_command": "python3 tools/mission1_numbered_list_readiness.py --external-root /Volumes/OWC_8TB/gpr_work --require-production",
            "blockers": [
                {
                    "item_id": 1,
                    "blocker": "Mission 1 firmware/camera-side handoff receipt is still required.",
                    "required_receipt": handoff,
                    "validator": "tools/check_labs_camera_handoff_receipt.py",
                    "closure_run_command": "python3 tools/run_mission1_camera_closure.py --target-role camera",
                    "closure_run_validation_command": "python3 tools/check_mission1_camera_closure_run.py mission1_camera_closure_run.json",
                    "acceptance": [
                        "target.role=camera",
                        "verdict.firmware_ready=true",
                    ],
                },
                {
                    "item_id": 2,
                    "blocker": "Mission 1 camera preview UI receipt is still required.",
                    "required_receipt": preview,
                    "validator": "tools/check_labs_preview_ui_receipt.py",
                    "closure_run_command": "python3 tools/run_mission1_camera_closure.py --target-role camera",
                    "closure_run_validation_command": "python3 tools/check_mission1_camera_closure_run.py mission1_camera_closure_run.json",
                    "acceptance": [
                        "target.role=camera",
                        "verdict.ui_ready=true",
                    ],
                },
            ],
        },
    )
    write_json(
        root / handoff,
        {
            "schema": "gpr_labs_camera_handoff_receipt.v1",
            "target": {"name": "Pi 5", "role": "stand-in"},
            "verdict": {"firmware_ready": False},
            "blocker": {"cause": "camera handoff not executed"},
        },
    )
    write_json(
        root / preview,
        {
            "schema": "gpr_labs_preview_ui_receipt.v1",
            "target": {"name": "Pi 5", "role": "stand-in"},
            "verdict": {"ui_ready": False},
            "blocker": {"cause": "ui path not executed"},
        },
    )
    write_json(
        root / preflight,
        {
            "schema": "gpr.mission1_camera_target_preflight.v1",
            "target": {"name": "Mission 1", "role": "camera"},
            "inputs": {
                "frame_source": "sensor DMA ring buffer",
                "write_path": "Mission 1 camera storage writer path",
                "storage_medium": "Mission 1 SD card",
                "display_surface": "Mission 1 rear display",
                "presentation_path": "Mission 1 rear display presentation path",
            },
            "verdict": {"target_preflight_ready": False, "camera_closure_possible": False},
            "blockers": ["camera frame source ready"],
        },
    )


def main() -> int:
    builder = load(BUILDER, "build_mission1_camera_closure_package")
    checker = load(CHECKER, "check_mission1_camera_closure_package")
    assert builder.DEFAULT_PREFLIGHT_REL.endswith(
        "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_sensor_ring_20260625.json"
    )
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_camera_closure_", dir=work_parent) as td:
        fixture = Path(td)
        create_fixture(fixture)
        out_json = fixture / "package.json"
        out_md = fixture / "package.md"
        args = type(
            "Args",
            (),
            {
                "external_root": fixture,
                "readiness": "artifacts/mission1_numbered_list_readiness_20260625/readiness.json",
                "closure_plan": "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json",
                "target_preflight": "artifacts/current/preflight.json",
                "target_host": "",
                "ssh_timeout_s": 1,
                "output_json": out_json,
                "output_md": out_md,
            },
        )()
        package = builder.build_package(args)
        out_json.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
        builder.write_markdown(package, out_md)
        failures = checker.validate(package)
        assert failures == [], failures
        assert out_md.exists()
        md = out_md.read_text(encoding="utf-8")
        assert "Aggregate Camera Closure Run" in md
        assert "Target Access Probe" in md
        assert "Target Preflight" in md
        assert "Acceptance Audit" in md
        assert "tools/run_mission1_camera_closure.py" in md
        assert "tools/check_mission1_camera_closure_run.py" in md
        assert package["target_access"]["requested"] is False
        assert package["target_preflight"]["exists"] is True
        assert package["target_preflight"]["inputs"]["frame_source"] == "sensor DMA ring buffer"
        assert package["acceptance_audit"][0]["passed"] is False
        assert package["acceptance_audit"][0]["satisfied_count"] == 0
        assert package["acceptance_audit"][1]["passed"] is False
        assert package["acceptance_audit"][1]["satisfied_count"] == 0
        assert package["verdict"]["remaining_blocker_count"] == 2

        stale = json.loads(json.dumps(package))
        stale["target_preflight"]["verdict"]["target_preflight_ready"] = True
        stale["target_preflight"]["verdict"]["camera_closure_possible"] = True
        stale_failures = checker.validate(stale)
        assert any("non-production closure package" in failure for failure in stale_failures), stale_failures

        missing_inputs = json.loads(json.dumps(package))
        missing_inputs["target_preflight"].pop("inputs")
        missing_input_failures = checker.validate(missing_inputs)
        assert any("target_preflight.inputs must be an object" in failure for failure in missing_input_failures), missing_input_failures

        standin_inputs = json.loads(json.dumps(package))
        standin_inputs["target_preflight"]["inputs"]["frame_source"] = "file-backed stand-in source"
        standin_input_failures = checker.validate(standin_inputs)
        assert any("stand-in token" in failure for failure in standin_input_failures), standin_input_failures

        production = json.loads(json.dumps(package))
        production["remaining_blockers"] = []
        production["current_receipts"] = []
        production["acceptance_audit"] = []
        production["verdict"] = {
            "production_ready": True,
            "reason": "numbered_list_final_gate_ready",
            "remaining_blocker_count": 0,
        }
        production["target_preflight"]["verdict"]["target_preflight_ready"] = True
        production["target_preflight"]["verdict"]["camera_closure_possible"] = True
        production["target_preflight"]["target"]["role"] = "stand-in"
        production_failures = checker.validate(production)
        assert any("camera_handoff_receipt summary" in failure for failure in production_failures), production_failures
        assert any("preview_ui_receipt summary" in failure for failure in production_failures), production_failures
        assert any("target_preflight.target.role=camera" in failure for failure in production_failures), production_failures

        production["current_receipts"] = [
            {
                "path": "artifacts/current/camera_handoff_receipt.json",
                "exists": True,
                "sha256": "a" * 64,
                "schema": "gpr_labs_camera_handoff_receipt.v1",
                "target": {"name": "Mission 1", "role": "camera"},
                "integration": {
                    "raw_source_kind": "sensor_dma_capture",
                    "sensor_dma_handoff": {"executed": True},
                    "storage_handoff": {"executed": True},
                },
                "verdict": {"firmware_ready": True},
            },
            {
                "path": "artifacts/current/preview_ui_receipt.json",
                "exists": True,
                "sha256": "b" * 64,
                "schema": "gpr_labs_preview_ui_receipt.v1",
                "target": {"name": "Mission 1", "role": "camera"},
                "integration": {"ui_path_executed": True},
                "verdict": {"ui_ready": True},
            },
        ]
        production_failures = checker.validate(production)
        production["target_preflight"]["target"]["role"] = "camera"
        assert checker.validate(production) == []

        production["current_receipts"][0]["integration"]["raw_source_kind"] = "file_standin"
        production_failures = checker.validate(production)
        assert any("raw_source_kind" in failure for failure in production_failures), production_failures
        production["current_receipts"][0]["integration"]["raw_source_kind"] = "sensor_dma_capture"

        production["target_preflight"]["verdict"]["camera_closure_possible"] = False
        production_failures = checker.validate(production)
        assert any("camera_closure_possible=true" in failure for failure in production_failures), production_failures
    print("test_mission1_camera_closure_package: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
