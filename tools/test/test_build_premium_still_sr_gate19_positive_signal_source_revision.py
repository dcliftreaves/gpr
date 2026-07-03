#!/usr/bin/env python3
"""Regression test for the Gate19 Premium still-SR revision receipt builder."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate19_positive_signal_source_revision.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("gate19_revision", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def audit_payload(*, median: float, rmse: float, worst_50: float, worst_100: float, noop: bool = False) -> dict:
    overall = {
        "raw_residual_mae_reduction_pct": {"median": median},
        "raw_residual_rmse_reduction_pct": {"median": rmse},
    }
    if noop:
        overall["candidate_hf_noop_gate"] = {"median": 0.0}
        overall["candidate_hf_noop_row_count"] = 709
    return {
        "production_ready": False,
        "coverage": {"target_row_count": 1152, "classes": {"50mp": 576, "100mp": 576}},
        "overall_eval": overall,
        "metrics_by_class": {
            "100mp": {
                "raw_residual_mae_reduction_pct": {"median": median, "min": worst_100},
                "raw_residual_rmse_reduction_pct": {"median": rmse},
            },
            "50mp": {
                "raw_residual_mae_reduction_pct": {"median": median, "min": worst_50},
                "raw_residual_rmse_reduction_pct": {"median": rmse},
            },
        },
    }


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
        gate17_audit = root / "gate17_audit.json"
        gate18_audit = root / "gate18_audit.json"
        write_json(gate17_audit, audit_payload(median=-0.23, rmse=0.34, worst_50=-2.26, worst_100=-35.3))
        write_json(gate18_audit, audit_payload(median=0.0, rmse=0.0, worst_50=-0.006, worst_100=-0.09, noop=True))
        args = SimpleNamespace(
            gate17_target_receipt=target_receipt,
            gate17_audit=gate17_audit,
            gate18_audit=gate18_audit,
            output_dir=root / "out",
        )
        receipt = mod.build_receipt(args)
        assert receipt["schema"] == mod.SCHEMA
        assert receipt["candidate_id"] == mod.GATE19_CANDIDATE_ID
        assert receipt["production_ready"] is False
        assert receipt["first_open_step"] == "gate19_train_then_broad_target_row_audit"
        assert receipt["runtime_policy"]["candidate_only_runtime"] is True
        assert "candidate_raw_hf" in receipt["runtime_policy"]["allowed_inputs"]
        assert "REF" in receipt["runtime_policy"]["forbidden_inputs"]
        assert "source_hf" in receipt["runtime_policy"]["forbidden_inputs"]
        assert receipt["pass_thresholds"]["not_noop_overall_median_mae_reduction_pct"] == 1.0
        train_command = " ".join(receipt["commands"]["train"])
        assert "source_hf" in train_command
        assert "raw_context_storedhf_coord_ev_noise_cfa" in train_command
        assert "premium_still_sr_gate19_source_hf_positive_signal_train" in train_command
        assert "premium_still_sr_gate17_balanced_smoke_train" not in train_command
        assert "premium_still_sr_gate18_tail_safe_context_train" not in train_command
        assert "--candidate-hf-noop-threshold" not in train_command
        assert any("safety-only no-op" in item for item in receipt["required_changes_from_gate18"])
    print("test_build_premium_still_sr_gate19_positive_signal_source_revision: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
