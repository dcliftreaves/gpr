#!/usr/bin/env python3
"""Regression test for the Premium still-SR degradation-source audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_degradation_source_audit.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source(camera: str, present: bool, mae: float, rmse: float) -> dict:
    return {
        "schema": "gpr.premium_still_sr_source_evidence_audit.v1",
        "holdout_camera": camera,
        "acceptance": {
            "source_evidence_present": present,
            "min_median_mae_recovery_pct": 1.0,
        },
        "summary": {
            "linear_probe_mae_recovery_pct": {"median": mae},
            "linear_probe_rmse_recovery_pct": {"median": rmse},
        },
        "probe": {
            "runtime_inputs": ["candidate_raw"],
            "forbidden_inputs": ["REF", "source_raw", "jpeg"],
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_degradation_source_", dir=temp_root()) as td:
        root = Path(td)
        gate10 = root / "gate10.json"
        distribution = root / "distribution.json"
        snr = root / "snr.json"
        x2d = root / "x2d.json"
        z8 = root / "z8.json"
        out = root / "out"

        write_json(
            gate10,
            {
                "schema": "gpr.premium_still_sr_gate10_target_degradation_decision.v1",
                "blocker_classification": "source_degradation_target_mismatch",
                "long_run_allowed": False,
            },
        )
        write_json(
            distribution,
            {
                "schema": "gpr.premium_still_sr_target_distribution_audit.v1",
                "split_comparison": {
                    "distribution_mismatch": True,
                    "holdout_median_to_train_median": 3.45,
                    "holdout_rows_above_train_p90": 6,
                },
            },
        )
        write_json(
            snr,
            {
                "schema": "gpr.premium_still_sr_raw_target_snr_audit.v1",
                "by_camera": [
                    {
                        "camera": "x2d",
                        "row_count": 81,
                        "classifications": {
                            "signal_dominated": 59,
                            "mixed_signal_noise": 11,
                            "noise_floor": 11,
                        },
                        "target_rmse_to_noise_sigma": {"median": 5.34},
                        "target_p95_to_noise_p95": {"median": 5.25},
                    },
                    {
                        "camera": "z8",
                        "row_count": 36,
                        "classifications": {
                            "mixed_signal_noise": 8,
                            "noise_floor": 28,
                        },
                        "target_rmse_to_noise_sigma": {"median": 0.48},
                        "target_p95_to_noise_p95": {"median": 0.39},
                    },
                ],
            },
        )
        write_json(x2d, source("x2d", True, 4.82, 11.52))
        write_json(z8, source("z8", False, 0.65, 21.90))

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate10-decision",
                str(gate10),
                "--target-distribution",
                str(distribution),
                "--target-snr",
                str(snr),
                "--x2d-source-evidence",
                str(x2d),
                "--z8-source-evidence",
                str(z8),
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

        data = json.loads((out / "degradation_source_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_degradation_source_audit.v1"
        assert data["verdict"] == "degradation_source_policy_ready_for_gate11_preflight"
        assert data["gate11_candidate_intake_allowed"] is True
        assert data["long_run_allowed"] is False
        assert data["selected_family"] == "route_isolated_teacher_then_router"
        assert data["route_policy"]["x2d"]["policy"] == "train_signal_dominated_route_with_stratified_target_sampling"
        assert data["route_policy"]["x2d"]["eligible_training_rows"] == 70
        assert data["route_policy"]["z8"]["policy"] == "default_noop_for_noise_floor_rows_and_require_new_source_for_positive_route"
        assert data["route_policy"]["z8"]["eligible_training_rows"] == 8
        assert any("Z8 positive residual" in item for item in data["forbidden_gate11_sources"])
        assert proc.stdout.strip() == str(out / "index.html")

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Degradation Source Audit" in html
        assert "route_isolated_teacher_then_router" in html

    print("test_build_premium_still_sr_degradation_source_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
