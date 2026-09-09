#!/usr/bin/env python3
"""Regression test for the Gate20 Premium still-SR revision receipt builder."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate20_supervision_objective_revision.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("gate20_revision", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    mod = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gate17 = root / "gate17.json"
        gate19 = root / "gate19.json"
        direction = root / "direction.json"
        candidate = root / "candidate_hf.json"
        write_json(
            gate17,
            {"coverage": {"selected_class_counts": {"50mp": 576, "100mp": 576}}},
        )
        write_json(
            gate19,
            {
                "production_ready": False,
                "overall_eval": {
                    "raw_residual_mae_reduction_pct": {"median": -14.18},
                    "raw_residual_rmse_reduction_pct": {"median": -13.18},
                },
            },
        )
        write_json(
            direction,
            {
                "next_decision": "direction_or_objective_wrong",
                "best_alpha_summary": {"alpha": 0.025, "mae_reduction_pct": {"median": 0.018}},
            },
        )
        write_json(
            candidate,
            {
                "next_decision": "candidate_hf_feature_not_predictive_change_supervision",
                "best_alpha_summary": {"alpha": -0.025, "mae_reduction_pct": {"median": -0.004}},
            },
        )
        args = SimpleNamespace(
            gate17_target_receipt=gate17,
            gate19_audit=gate19,
            direction_calibration=direction,
            candidate_hf_audit=candidate,
            output_dir=root / "out",
        )
        receipt = mod.build_receipt(args)
        assert receipt["schema"] == mod.SCHEMA
        assert receipt["candidate_id"] == mod.GATE20_CANDIDATE_ID
        assert receipt["first_open_step"] == "gate20_rebuild_supervision_targets"
        assert receipt["runtime_policy"]["candidate_only_runtime"] is True
        assert "REF" in receipt["runtime_policy"]["forbidden_inputs"]
        assert "source_raw" in receipt["runtime_policy"]["forbidden_inputs"]
        assert receipt["prior_rejection_metrics"]["candidate_hf_best_alpha"] == -0.025
        commands = " ".join(" ".join(cmd) for cmd in receipt["target_rebuild_commands"])
        assert "build_premium_still_sr_target_expansion_plan.py" in commands
        assert "build_premium_still_sr_expanded_hf_targets_from_plan.py" in commands
        assert "--rebuild-existing-targets" in commands
        assert any("Do not train another Gate17" in item for item in receipt["required_changes"])
    print("test_build_premium_still_sr_gate20_supervision_objective_revision: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
