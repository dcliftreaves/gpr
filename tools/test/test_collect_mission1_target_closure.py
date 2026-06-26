#!/usr/bin/env python3
"""Regression test for compact Mission 1 target-closure collection."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = ROOT / "tools/collect_mission1_target_closure.py"
CLOSURE_FIXTURE = ROOT / "tools/test/test_mission1_camera_closure_run.py"


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


def main() -> int:
    collector = load(COLLECTOR, "collect_mission1_target_closure")
    fixture_mod = load(CLOSURE_FIXTURE, "mission1_camera_closure_fixture")
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_target_collect_", dir=work_parent) as td:
        root = Path(td)
        source = root / "source"
        out = root / "out"
        write_json(
            source / "hardware_audit_receipt.json",
            {
                "schema": "gpr.mission1_camera_hardware_audit.v1",
                "target": {"name": "Pi 5 stand-in", "role": "stand-in"},
                "summary": {"camera_enumerated": False},
                "verdict": {"hardware_ready_for_camera_source": False},
            },
        )
        write_json(
            source / "target_preflight_receipt.json",
            {
                "schema": "gpr.mission1_camera_target_preflight.v1",
                "target": {"name": "Pi 5 stand-in", "role": "stand-in"},
                "verdict": {"target_preflight_ready": True, "camera_closure_possible": False},
                "blockers": [],
            },
        )
        write_json(source / "camera_handoff_receipt.json", fixture_mod.camera_handoff())
        write_json(source / "preview_ui_receipt.json", fixture_mod.preview_ui())
        write_json(source / "labs_target_bench.json", fixture_mod.target_bench())
        closure = fixture_mod.closure_run(Path("/mnt/ssd/gpr_work/artifacts/remote"))
        write_json(source / "mission1_camera_closure_run.json", closure)
        args = type(
            "Args",
            (),
            {
                "local_source_dir": source,
                "target_host": None,
                "remote_dir": "",
                "output_dir": out,
                "ssh_timeout_s": 1,
                "include_timing_receipts": False,
            },
        )()
        receipt, status = collector.build_collection(args)
        assert status == 0, receipt
        assert receipt["verdict"]["collection_valid"] is True
        assert receipt["verdict"]["production_ready"] is False
        assert (out / "collection_receipt.json").exists()
        assert {row["file"] for row in receipt["files"]} == set(collector.COMPACT_FILES)
        preflight_row = next(row for row in receipt["files"] if row["file"] == "target_preflight_receipt.json")
        assert preflight_row["schema"] == "gpr.mission1_camera_target_preflight.v1"
        assert preflight_row["verdict"]["target_preflight_ready"] is True

        write_json(source / "preview_decode_1024x768/receipt.json", {"schema": "preview_decode_fixture.v1"})
        out_with_timing = root / "out_with_timing"
        args.output_dir = out_with_timing
        args.include_timing_receipts = True
        receipt, status = collector.build_collection(args)
        assert status == 0, receipt
        names = {row["file"] for row in receipt["files"]}
        assert names == set(collector.COMPACT_FILES + collector.TIMING_FILES)
        assert (out_with_timing / "labs_target_bench.json").exists()
        assert (out_with_timing / "preview_decode_1024x768/receipt.json").exists()
        assert receipt["include_timing_receipts"] is True

        false_claim_source = root / "false_claim_source"
        write_json(
            false_claim_source / "hardware_audit_receipt.json",
            {
                "schema": "gpr.mission1_camera_hardware_audit.v1",
                "target": {"name": "Mission 1", "role": "camera"},
                "summary": {"camera_enumerated": False},
                "verdict": {"hardware_ready_for_camera_source": False},
            },
        )
        write_json(false_claim_source / "target_preflight_receipt.json", fixture_mod.blocked_camera_preflight())
        write_json(false_claim_source / "camera_handoff_receipt.json", fixture_mod.camera_ready_handoff())
        write_json(false_claim_source / "preview_ui_receipt.json", fixture_mod.camera_ready_preview_ui())
        write_json(false_claim_source / "labs_target_bench.json", fixture_mod.target_bench())
        false_claim = fixture_mod.closure_run(Path("/mnt/ssd/gpr_work/artifacts/remote"))
        false_claim["verdict"] = {
            "production_ready": True,
            "target_preflight_ready": False,
            "camera_closure_possible": False,
            "firmware_ready": True,
            "ui_ready": True,
            "handoff_blocker": None,
            "preview_blocker": None,
        }
        write_json(false_claim_source / "mission1_camera_closure_run.json", false_claim)
        args.local_source_dir = false_claim_source
        args.output_dir = root / "false_claim_out"
        args.include_timing_receipts = False
        receipt, status = collector.build_collection(args)
        assert status == 1
        assert receipt["validation"]["returncode"] != 0
        assert receipt["closure_verdict"]["production_ready"] is True
        assert receipt["verdict"]["collection_valid"] is False
        assert receipt["verdict"]["production_ready"] is False
    print("test_collect_mission1_target_closure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
