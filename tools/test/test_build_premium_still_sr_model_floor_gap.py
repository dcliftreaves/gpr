#!/usr/bin/env python3
"""Regression test for Premium still-SR model-floor gap receipt."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_model_floor_gap.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("build_premium_still_sr_model_floor_gap", TOOL)
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
        "receipt_count": 2,
        "runtime_safe_candidate_count": 2,
        "promotable_candidate_count": 0,
        "production_ready": False,
        "best_runtime_safe_candidate": {
            "experiment": "best_current",
            "path": "/external/train_receipt.json",
            "checkpoint_sha256": "a" * 64,
            "holdout_residual_mae_reduction_pct_median": 4.0,
            "holdout_residual_rmse_reduction_pct_median": 3.5,
        },
    }


def selector() -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate14_selector_smoke.v1",
        "gate14_selector_smoke_passed": True,
        "promotion_gate_allowed": True,
        "production_ready": False,
        "selector_smoke_metrics": {
            "median": 0.25,
            "negative_row_count": 0,
            "selected_row_count": 8,
            "by_image": {
                "a": {"median": 0.1},
                "b": {"median": 0.4},
            },
        },
    }


def rollup() -> dict:
    return {
        "schema": "gpr.premium_still_sr_promotion_receipts.v1",
        "production_ready": False,
        "completion_percent": 50.0,
        "done_step_count": 4,
        "total_step_count": 8,
        "first_open_step": "model_promotion_floor",
        "blocker_classifications": ["model_promotion_floor_not_met"],
    }


def sidecar() -> dict:
    return {
        "schema": "gpr.premium_still_sr_multi_source_selector_sidecar.v1",
        "selector_id": "selector",
        "rules": [{}, {}],
        "sources": [{}, {}, {}],
        "runtime_policy": {
            "allowed_runtime_inputs": ["candidate_raw", "camera_metadata"],
            "forbidden_runtime_inputs": ["REF", "source_raw"],
            "fallback": "exact_noop",
            "rule_resolution": "first_match_wins",
        },
    }


def main() -> int:
    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_model_floor_gap_", dir=tmp_parent) as td:
        root = Path(td)
        write_json(root / "scoreboard.json", scoreboard())
        write_json(root / "selector.json", selector())
        write_json(root / "rollup.json", rollup())
        write_json(root / "sidecar.json", sidecar())
        args = type(
            "Args",
            (),
            {
                "scoreboard": root / "scoreboard.json",
                "selector_smoke": root / "selector.json",
                "promotion_rollup": root / "rollup.json",
                "selector_sidecar": root / "sidecar.json",
                "output_dir": root / "out",
                "require_pass": False,
            },
        )()
        receipt = tool.build(args)
        assert receipt["schema"] == "gpr.premium_still_sr_model_floor_gap.v1"
        assert receipt["production_ready"] is False
        assert receipt["verdict"] == "blocked_below_model_promotion_floor"
        assert receipt["scoreboard"]["best_runtime_safe_mae_gap_pct"] == 11.0
        assert receipt["scoreboard"]["best_runtime_safe_rmse_gap_pct"] == 11.5
        assert receipt["gate14_selector"]["global_floor_gap_pct"] == 14.75
        assert receipt["next_candidate_contract"]["candidate_id"] == "premium_still_sr_gate14_floor_student_v1"
        assert (root / "out" / "index.html").is_file()
    print("test_build_premium_still_sr_model_floor_gap: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
