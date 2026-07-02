#!/usr/bin/env python3
"""Regression test for the premium still-SR signal/noise policy gate."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_premium_still_sr_noise_policy.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("premium_noise_policy_gate", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clean_receipt() -> dict:
    return {
        "schema": "gpr.premium_still_sr_clean_signal_targets.v1",
        "policy": {
            "uses_source_raw_at_training_target": True,
            "uses_source_raw_at_runtime": False,
            "uses_ref_or_jpeg_content_at_runtime": False,
            "exact_source_noise_addback_allowed_at_runtime": False,
            "runtime_addback_policy": "validated camera noise sidecar or future synthetic noise model only",
        },
        "summary": {
            "row_count": 4,
            "rows_with_noise_sidecars": 4,
            "target_energy_retained_fraction": {"median": 0.8},
            "active_pixel_fraction": {"median": 0.4},
            "classification_counts": {"retained_signal": 3, "suppressed_noise_floor": 1},
        },
    }


def main() -> int:
    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_premium_noise_policy_", dir=tmp_parent) as td:
        root = Path(td)
        clean_path = root / "clean.json"
        blocked_model_path = root / "blocked_model.json"
        pass_model_path = root / "pass_model.json"
        write_json(clean_path, clean_receipt())
        write_json(
            blocked_model_path,
            {
                "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
                "checkpoint_sha256": "abc",
                "config": {"model_arch": "residual_pixelshuffle", "steps": 100},
                "promotion": {
                    "promotion_ready": False,
                    "baseline_beaten_on_holdout": False,
                    "coverage_sufficient_for_promotion": False,
                },
                "eval": {
                    "train": {
                        "tile_count": 8,
                        "mae_improvement_pct": {"median": 12.0},
                        "rmse_improvement_pct": {"median": 16.0},
                    },
                    "holdout": {
                        "tile_count": 4,
                        "mae_improvement_pct": {"median": -2.0},
                        "rmse_improvement_pct": {"median": -1.0},
                    },
                },
            },
        )
        args = type(
            "Args",
            (),
            {
                "clean_signal_targets": clean_path,
                "model_receipt": [blocked_model_path],
                "output_dir": root / "blocked",
                "mae_floor": 15.0,
                "rmse_floor": 15.0,
                "require_production_ready": False,
            },
        )()
        blocked = tool.build(args)
        assert blocked["production_ready"] is False
        assert blocked["clean_signal"]["policy_pass"] is True
        assert blocked["model_receipts"][0]["policy_pass"] is False
        assert any("does not beat nearest same-color interpolation" in item for item in blocked["model_receipts"][0]["blockers"])
        assert "clean-signal/noise policy passes" in blocked["decision"]
        assert (root / "blocked" / "index.html").read_text(encoding="utf-8").find("Noise Policy Gate") >= 0

        write_json(
            pass_model_path,
            {
                "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
                "checkpoint_sha256": "def",
                "production_ready": True,
                "config": {"model_arch": "global_teacher", "feature_mode": "candidate_raw_noise_cfa", "steps": 1000},
                "policy": {
                    "uses_source_raw_at_runtime": False,
                    "uses_ref_or_jpeg_content_at_runtime": False,
                    "production_status": "registered_candidate",
                    "runtime_inputs": "candidate raw plus metadata and validated noise sidecar scalars",
                },
                "eval": {
                    "train": {
                        "row_count": 8,
                        "raw_residual_mae_reduction_pct": {"median": 20.0},
                        "raw_residual_rmse_reduction_pct": {"median": 18.0},
                    },
                    "holdout": {
                        "row_count": 4,
                        "raw_residual_mae_reduction_pct": {"median": 16.0},
                        "raw_residual_rmse_reduction_pct": {"median": 15.5},
                    },
                },
            },
        )
        args.model_receipt = [pass_model_path]
        args.output_dir = root / "pass"
        passed = tool.build(args)
        assert passed["production_ready"] is True
        assert passed["model_receipts"][0]["policy_pass"] is True
        assert passed["blockers"] == []

        bad_clean = clean_receipt()
        bad_clean["summary"]["rows_with_noise_sidecars"] = 3
        bad_clean_path = root / "bad_clean.json"
        write_json(bad_clean_path, bad_clean)
        args.clean_signal_targets = bad_clean_path
        args.output_dir = root / "bad_clean"
        failed = tool.build(args)
        assert failed["production_ready"] is False
        assert any("not every clean-signal row" in item for item in failed["clean_signal"]["blockers"])

    print("test_check_premium_still_sr_noise_policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
