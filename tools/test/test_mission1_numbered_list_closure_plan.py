#!/usr/bin/env python3
"""Tests for the Mission 1 numbered-list closure plan."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/mission1_numbered_list_closure_plan.py"
READINESS_TEST = ROOT / "tools/test/test_mission1_numbered_list_readiness.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def with_registry(registry_path: Path, fn):
    old = os.environ.get("GPR_REGISTRY_PATH")
    os.environ["GPR_REGISTRY_PATH"] = str(registry_path)
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("GPR_REGISTRY_PATH", None)
        else:
            os.environ["GPR_REGISTRY_PATH"] = old


def test_current_blockers_are_actionable() -> None:
    tool = load_module(TOOL, "mission1_numbered_list_closure_plan")
    fixture_tools = load_module(READINESS_TEST, "mission1_numbered_list_readiness_fixture")
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_closure_plan_", dir=work_parent) as td:
        fixture = Path(td)
        fixture_tools.create_fixture(fixture)
        registry = fixture_tools.write_registry(fixture, "offline_review_only")
        plan = with_registry(registry, lambda: tool.build_plan(fixture))
        assert plan["readiness_status"] == "evidence_passes_with_production_blockers"
        assert plan["production_ready"] is False
        assert len(plan["blockers"]) == 4
        validators = {blocker["validator"] for blocker in plan["blockers"]}
        assert "tools/check_labs_camera_handoff_receipt.py" in validators
        assert "tools/check_labs_preview_ui_receipt.py" in validators
        assert "tools/check_mission1_4k_cleanup_signoff_receipt.py" in validators
        assert "tools/check_mission1_8k_sr_production_promotion.py" in validators
        camera_blockers = [
            blocker for blocker in plan["blockers"]
            if blocker["validator"] in {
                "tools/check_labs_camera_handoff_receipt.py",
                "tools/check_labs_preview_ui_receipt.py",
            }
        ]
        assert len(camera_blockers) == 2
        assert all("--target-preflight-receipt" in blocker["closure_run_command"] for blocker in camera_blockers)
        assert "--require-production" in plan["final_gate_command"]


def test_production_fixture_has_no_closure_blockers() -> None:
    tool = load_module(TOOL, "mission1_numbered_list_closure_plan_prod")
    fixture_tools = load_module(READINESS_TEST, "mission1_numbered_list_readiness_fixture_prod")
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_closure_plan_prod_", dir=work_parent) as td:
        fixture = Path(td)
        fixture_tools.create_fixture(fixture)
        fixture_tools.promote_fixture_to_production(fixture)
        registry = fixture_tools.write_registry(fixture, "offline_production")
        plan = with_registry(registry, lambda: tool.build_plan(fixture))
        assert plan["readiness_status"] == "production_ready"
        assert plan["production_ready"] is True
        assert plan["blockers"] == []


if __name__ == "__main__":
    test_current_blockers_are_actionable()
    test_production_fixture_has_no_closure_blockers()
    print("test_mission1_numbered_list_closure_plan: PASS")
