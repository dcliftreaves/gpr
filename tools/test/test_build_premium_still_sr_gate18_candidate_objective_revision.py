#!/usr/bin/env python3
"""Regression test for the Gate18 Premium still-SR revision receipt builder."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate18_candidate_objective_revision.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("gate18_revision", TOOL)
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
        target_npz = root / "gate17_replacement_targets.npz"
        target_npz.write_bytes(b"fake-npz")
        target_receipt = root / "gate17_replacement_targets.json"
        write_json(
            target_receipt,
            {
                "artifacts": {"targets_npz": target_npz.name},
                "selected_class_counts": {"50mp": 576, "100mp": 576},
            },
        )
        audit = root / "gate16_target_row_audit.json"
        write_json(
            audit,
            {
                "production_ready": False,
                "coverage": {"target_row_count": 1152, "classes": {"50mp": 576, "100mp": 576}},
                "overall_eval": {
                    "raw_residual_mae_reduction_pct": {"median": -0.23},
                    "raw_residual_rmse_reduction_pct": {"median": 0.34},
                },
                "metrics_by_class": {
                    "100mp": {
                        "raw_residual_mae_reduction_pct": {"median": -0.2, "min": -35.3},
                        "raw_residual_rmse_reduction_pct": {"median": -0.2},
                    },
                    "50mp": {
                        "raw_residual_mae_reduction_pct": {"median": -0.24, "min": -2.26},
                        "raw_residual_rmse_reduction_pct": {"median": 0.84},
                    },
                },
            },
        )
        args = SimpleNamespace(gate17_target_receipt=target_receipt, gate17_audit=audit, output_dir=root / "out")
        receipt = mod.build_receipt(args)
        assert receipt["schema"] == mod.SCHEMA
        assert receipt["candidate_id"] == mod.GATE18_CANDIDATE_ID
        assert receipt["production_ready"] is False
        assert receipt["first_open_step"] == "gate18_train_then_broad_target_row_audit"
        assert receipt["runtime_policy"]["candidate_only_runtime"] is True
        assert "REF" in receipt["runtime_policy"]["forbidden_inputs"]
        assert receipt["gate17_rejection_metrics"]["gate17_row_count_50mp"] == 576
        assert receipt["gate17_rejection_metrics"]["gate17_row_count_100mp"] == 576
        train_command = " ".join(receipt["commands"]["train"])
        assert "global_context_unet" in train_command
        assert "noise_soft_threshold" in train_command
        assert "premium_still_sr_gate18_tail_safe_context_train" in train_command
        assert "premium_still_sr_gate17_balanced_smoke_train" not in train_command
        assert any("Do not rerun the same Gate17" in item for item in receipt["required_changes_from_gate17"])
    print("test_build_premium_still_sr_gate18_candidate_objective_revision: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
