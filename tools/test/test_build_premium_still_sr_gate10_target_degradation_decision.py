#!/usr/bin/env python3
"""Regression test for the Premium still-SR Gate 10 decision receipt."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate10_target_degradation_decision.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate10_decision_", dir=temp_root()) as td:
        root = Path(td)
        gate9 = root / "gate9.json"
        contract = root / "contract.json"
        distribution = root / "distribution.json"
        snr = root / "snr.json"
        scoreboard = root / "scoreboard.json"
        out = root / "out"

        write_json(
            gate9,
            {
                "schema": "gpr.premium_still_sr_smoke_gate_acceptance.v1",
                "candidate_id": "gate9_route_conditioned_noise_weighted_rawcfa_v1",
                "smoke_gate_passed": False,
                "long_run_allowed": False,
                "production_ready": False,
                "verdict": "blocked_before_long_run",
                "failures": ["x2d failed", "z8 failed"],
                "rows": [
                    {
                        "holdout": "x2d",
                        "receipt": "/x2d/train_receipt.json",
                        "checkpoint_sha256": "a" * 64,
                        "median_mae_improvement_pct": -0.1683,
                        "worst_row_mae_improvement_pct": -6.051,
                        "median_rmse_improvement_pct": -0.0007,
                        "baseline_beaten_on_holdout": False,
                        "passed": False,
                    },
                    {
                        "holdout": "z8",
                        "receipt": "/z8/train_receipt.json",
                        "checkpoint_sha256": "b" * 64,
                        "median_mae_improvement_pct": -1.586,
                        "worst_row_mae_improvement_pct": -55.7,
                        "median_rmse_improvement_pct": -0.0001,
                        "baseline_beaten_on_holdout": False,
                        "passed": False,
                    },
                ],
            },
        )
        write_json(
            contract,
            {
                "schema": "gpr.premium_still_sr_replacement_target_source_contract.v1",
                "verdict": "replacement_target_source_contract_ready",
                "paired_smoke_preflight_allowed": True,
                "long_run_allowed": False,
                "decisions": {},
                "acceptance": {},
            },
        )
        write_json(
            distribution,
            {
                "schema": "gpr.premium_still_sr_target_distribution_audit.v1",
                "summary": {"row_count": 117, "camera_counts": {"x2d": 81, "z8": 36}},
                "split_comparison": {
                    "holdout_scene": "2024_April_X2D_1742",
                    "distribution_mismatch": True,
                    "holdout_median_to_train_median": 3.45,
                    "holdout_rows_above_train_p90": 6,
                    "holdout_row_count": 9,
                },
            },
        )
        write_json(
            snr,
            {
                "schema": "gpr.premium_still_sr_raw_target_snr_audit.v1",
                "summary": {
                    "row_count": 117,
                    "rows_with_noise_sidecars": 117,
                    "classification_counts": {
                        "signal_dominated": 59,
                        "mixed_signal_noise": 19,
                        "noise_floor": 39,
                    },
                    "target_rmse_to_noise_sigma": {"median": 3.24},
                    "target_p95_to_noise_p95": {"median": 3.10},
                    "target_abs_to_candidate_hf_abs": {"median": 0.09},
                },
                "by_camera": [
                    {
                        "camera": "z8",
                        "row_count": 36,
                        "classifications": {"noise_floor": 28, "mixed_signal_noise": 8},
                    }
                ],
                "interpretation": "mixed signal/noise",
            },
        )
        write_json(
            scoreboard,
            {
                "schema": "gpr.premium_still_sr_experiment_scoreboard.v1",
                "rows": [
                    {
                        "candidate_id": "best_runtime_safe",
                        "runtime_safe": True,
                        "promotion_ready": False,
                        "median_mae_recovery_pct": 4.03,
                        "median_rmse_recovery_pct": 3.75,
                        "receipt": "/best.json",
                    }
                ],
            },
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate9-acceptance",
                str(gate9),
                "--replacement-contract",
                str(contract),
                "--target-distribution",
                str(distribution),
                "--target-snr",
                str(snr),
                "--scoreboard",
                str(scoreboard),
                "--output-dir",
                str(out),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        data = json.loads((out / "gate10_target_degradation_decision.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_gate10_target_degradation_decision.v1"
        assert data["production_ready"] is False
        assert data["long_run_allowed"] is False
        assert data["paired_smoke_allowed"] is False
        assert data["blocker_classification"] == "source_degradation_target_mismatch"
        assert data["finding"]["failed_both_routes"] is True
        assert data["finding"]["severe_z8_tail"] is True
        assert data["finding"]["z8_mostly_noise_floor_targets"] is True
        assert len(data["allowed_candidate_families"]) == 3
        assert any("Gate 9" in item for item in data["forbidden_next_work"])
        assert data["next_receipts"][0]["receipt"] == "premium_still_sr_degradation_source_audit_<date>"
        assert proc.stdout.strip() == str(out / "index.html")

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Gate 10 Decision" in html
        assert "replace_target_degradation_source_before_next_smoke" in html
        assert "source_degradation_target_mismatch" in html

    print("test_build_premium_still_sr_gate10_target_degradation_decision: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
