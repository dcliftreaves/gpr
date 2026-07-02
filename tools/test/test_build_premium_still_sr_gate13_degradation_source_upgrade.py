#!/usr/bin/env python3
"""Regression test for the Gate 13 Premium still-SR source upgrade audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate13_degradation_source_upgrade.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt(*, median: float, worst: float, rmse: float, camera: str, beaten: bool, name: str) -> dict:
    return {
        "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
        "pairs": "/pairs.npz",
        "pairs_sha256": "a" * 64,
        "config": {
            "holdout_images": [f"{camera}_holdout_00"],
            "model_arch": name,
            "steps": 25,
        },
        "eval": {
            "holdout": {
                "mae_improvement_pct": {"count": 4, "median": median, "min": worst},
                "rmse_improvement_pct": {"count": 4, "median": rmse, "min": rmse},
            }
        },
        "promotion": {
            "baseline": "nearest_same_color_2x",
            "baseline_beaten_on_holdout": beaten,
            "promotion_ready": beaten,
        },
    }


def gate12_acceptance() -> dict:
    return {
        "schema": "gpr.premium_still_sr_smoke_gate_acceptance.v1",
        "candidate_id": "gate12_synthetic_x2d_teacher_z8_exact_noop_v1",
        "verdict": "blocked_before_long_run",
        "smoke_gate_passed": False,
        "long_run_allowed": False,
        "failures": ["x2d failed"],
        "rows": [
            {
                "holdout": "x2d",
                "passed": False,
                "median_mae_improvement_pct": -0.01,
                "worst_row_mae_improvement_pct": -0.2,
            },
            {
                "holdout": "z8",
                "passed": True,
                "exact_noop": True,
                "median_mae_improvement_pct": 0.0,
                "worst_row_mae_improvement_pct": 0.0,
            },
        ],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate13_", dir=temp_root()) as td:
        base = Path(td)
        artifacts = base / "artifacts"
        write_json(base / "gate12.json", gate12_acceptance())
        write_json(
            artifacts / "premium_still_sr_positive_tail_bad_x2d/train_receipt.json",
            receipt(median=0.25, worst=-2.0, rmse=0.2, camera="x2d", beaten=True, name="window_attention"),
        )
        write_json(
            artifacts / "premium_still_sr_near_noop_x2d/train_receipt.json",
            receipt(median=0.0005, worst=0.0, rmse=0.0005, camera="x2d", beaten=True, name="noop_gate"),
        )
        write_json(
            artifacts / "premium_still_sr_negative_z8/train_receipt.json",
            receipt(median=-0.5, worst=-1.0, rmse=-0.3, camera="z8", beaten=False, name="z8_bad"),
        )
        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate12-acceptance",
                str(base / "gate12.json"),
                "--artifact-root",
                str(artifacts),
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
        data = json.loads((out / "gate13_degradation_source_upgrade.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_gate13_degradation_source_upgrade.v1"
        assert data["source_upgrade_passed"] is False
        assert data["gate14_candidate_intake_allowed"] is False
        assert data["blocker_classification"] == "objective_gating_tail_regression"
        assert data["summary"]["positive_median_x2d_source_receipt_count"] == 1
        assert data["summary"]["z8_exact_noop_ok"] is True
        assert data["summary"]["best_x2d_by_median"]["name"] == "premium_still_sr_positive_tail_bad_x2d"
        assert "Premium Still-SR Gate 13" in (out / "index.html").read_text(encoding="utf-8")

    print("test_build_premium_still_sr_gate13_degradation_source_upgrade: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
