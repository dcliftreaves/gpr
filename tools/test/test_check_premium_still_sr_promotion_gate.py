#!/usr/bin/env python3
"""Regression test for the premium still-SR promotion gate."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_premium_still_sr_promotion_gate.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("premium_still_sr_promotion_gate", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def scoreboard() -> dict:
    return {
        "schema": "gpr.premium_still_sr_experiment_scoreboard.v1",
        "receipt_count": 4,
        "runtime_safe_candidate_count": 4,
        "promotable_candidate_count": 0,
        "production_ready": False,
        "promotion_thresholds": {
            "holdout_residual_mae_reduction_pct_median": 15.0,
            "holdout_residual_rmse_reduction_pct_median": 15.0,
            "runtime_safe": True,
        },
        "best_runtime_safe_candidate": {
            "experiment": "diagnostic_candidate",
            "path": "/external/train_receipt.json",
            "checkpoint_sha256": "a" * 64,
            "holdout_residual_mae_reduction_pct_median": 4.0,
            "holdout_residual_rmse_reduction_pct_median": 3.0,
            "runtime_safe": True,
            "promotion_ready": False,
        },
    }


def noise_gate() -> dict:
    return {
        "schema": "gpr.premium_still_sr_noise_policy_gate.v1",
        "production_ready": False,
        "decision": "clean policy passes, models remain diagnostic",
        "clean_signal": {
            "policy_pass": True,
            "row_count": 8,
            "rows_with_noise_sidecars": 8,
        },
        "model_receipts": [
            {
                "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
                "policy_pass": False,
                "promotion_ready_claimed": False,
            }
        ],
    }


def gate_receipt() -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate.v1",
        "production_ready": False,
        "candidate": {"pipeline_id": "blocked", "checkpoint_sha256": "b" * 64, "target_role": "offline"},
        "fixture_summary": {
            "camera_count": 2,
            "fifty_mp_or_larger_count": 1,
            "hundred_mp_or_larger_count": 1,
            "cfa_phases": ["RGGB"],
        },
        "runtime_policy": {
            "no_ref_runtime": True,
            "forbidden_source_content_absent": True,
            "runtime_inputs": ["candidate_raw", "camera_metadata"],
        },
        "promotion_metrics": {
            "full_frame_gate_50mp_passed": False,
            "full_frame_gate_100mp_passed": False,
            "full_frame_gate_50mp_row_count": 0,
            "full_frame_gate_100mp_row_count": 0,
            "median_mae_reduction_pct_50mp": 0.0,
            "median_mae_reduction_pct_100mp": 0.0,
            "worst_row_mae_reduction_pct_50mp": 0.0,
            "worst_row_mae_reduction_pct_100mp": 0.0,
            "beats_current_baseline": False,
            "editor_latitude_passed": False,
            "severe_worst_row_failures": False,
        },
        "performance": {
            "render_seconds_per_50mp_frame": 0.0,
            "render_seconds_per_100mp_frame": 0.0,
            "peak_rss_gb": 0.0,
        },
        "noise_policy": {
            "mode": "diagnostic",
            "raw_noise_signal_audit_passed": False,
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
        },
    }


def next_contract() -> dict:
    return {
        "schema": "gpr.premium_still_sr_next_experiment_contract.v1",
        "production_ready": False,
        "requirement": {
            "id": "premium_still_sr_promotion_receipts",
            "status": "open",
        },
        "current_model_state": {
            "scoreboard_receipt_count": 4,
            "scoreboard_promotable_candidate_count": 0,
        },
    }


def main() -> int:
    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_premium_promotion_", dir=tmp_parent) as td:
        root = Path(td)
        scoreboard_path = root / "scoreboard.json"
        noise_path = root / "noise.json"
        gate_path = root / "gate.json"
        contract_path = root / "contract.json"
        write_json(scoreboard_path, scoreboard())
        write_json(noise_path, noise_gate())
        write_json(gate_path, gate_receipt())
        write_json(contract_path, next_contract())

        args = type(
            "Args",
            (),
            {
                "scoreboard": scoreboard_path,
                "noise_policy_gate": noise_path,
                "gate_receipt": gate_path,
                "next_contract": contract_path,
                "output_dir": root / "pass",
                "require_promotion_safe": False,
                "require_production_ready": False,
            },
        )()
        passed = tool.build(args)
        assert passed["schema"] == "gpr.premium_still_sr_promotion_gate.v1"
        assert passed["promotion_safe"] is True
        assert passed["production_ready"] is False
        assert passed["blockers"] == []
        assert "safely not promoted" in passed["decision"]
        assert (root / "pass" / "index.html").read_text(encoding="utf-8").find("Promotion Gate") >= 0

        bad_scoreboard = scoreboard()
        bad_scoreboard["production_ready"] = True
        bad_scoreboard["promotable_candidate_count"] = 1
        bad_scoreboard["best_runtime_safe_candidate"]["promotion_ready"] = True
        bad_scoreboard["best_runtime_safe_candidate"]["holdout_residual_mae_reduction_pct_median"] = 20.0
        bad_scoreboard["best_runtime_safe_candidate"]["holdout_residual_rmse_reduction_pct_median"] = 21.0
        bad_scoreboard_path = root / "bad_scoreboard.json"
        write_json(bad_scoreboard_path, bad_scoreboard)
        args.scoreboard = bad_scoreboard_path
        args.output_dir = root / "fail"
        failed = tool.build(args)
        assert failed["promotion_safe"] is False
        assert any("scoreboard claims production_ready" in item for item in failed["blockers"])
    print("test_check_premium_still_sr_promotion_gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
