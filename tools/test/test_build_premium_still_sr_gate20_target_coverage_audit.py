#!/usr/bin/env python3
"""Regression test for Gate20 target coverage audit."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/build_premium_still_sr_gate20_target_coverage_audit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("gate20_target_coverage_audit", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan = root / "plan.json"
        strict = root / "strict.json"
        build = root / "build.json"
        write_json(
            plan,
            {
                "current_target": {"row_count": 81, "scene_count": 3},
                "selected_new_targets": [
                    {"class": "100mp", "scene_id": "x2d_new"},
                    {"class": "50mp", "scene_id": "z8_new"},
                ],
            },
        )
        write_json(
            strict,
            {
                "current_target": {"row_count": 81, "scene_count": 3},
                "selected_new_targets": [{"class": "50mp", "scene_id": f"z8_{idx}"} for idx in range(22)]
                + [{"class": "100mp", "scene_id": f"x2d_{idx}"} for idx in range(6)],
            },
        )
        write_json(
            build,
            {
                "scene_results": [
                    {
                        "scene_id": "x2d_1742",
                        "source_path": "/x2d/foo.dng",
                        "built": True,
                        "command_results": [{"stdout": json.dumps({"rows": 27})}],
                    },
                    {
                        "scene_id": "z8z_1330",
                        "source_path": "/z8/Z8Z_1330.dng",
                        "built": True,
                        "command_results": [{"stdout": json.dumps({"rows": 27})}],
                    },
                ]
            },
        )
        args = type("Args", (), {"plan": plan, "strict_plan": strict, "build_receipt": build})()
        receipt = mod.build_receipt(args)
        assert receipt["gate20_training_authorized"] is False
        assert receipt["strict_plan_can_authorize_training"] is False
        assert receipt["actual_rebuilt_target_coverage"]["rows_by_class"]["100mp"] == 27
        assert receipt["actual_rebuilt_target_coverage"]["rows_by_class"]["50mp"] == 27
        assert receipt["strict_plan_coverage"]["rows_by_class"]["50mp"] == 594
        assert receipt["strict_plan_coverage"]["rows_by_class"]["100mp"] == 243
        assert receipt["next_decision"] == "gate20_target_coverage_blocked_add_100mp_rebuilt_supervision_sources"
    print("test_build_premium_still_sr_gate20_target_coverage_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
