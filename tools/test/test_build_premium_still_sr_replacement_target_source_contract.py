#!/usr/bin/env python3
"""Regression test for the Premium still-SR replacement target source contract."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_replacement_target_source_contract.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_evidence(camera: str, mae: float, rmse: float, present: bool) -> dict:
    return {
        "schema": "gpr.premium_still_sr_source_evidence_audit.v1",
        "holdout_camera": camera,
        "probe": {
            "runtime_inputs": ["candidate_raw"],
            "forbidden_inputs": ["REF", "source_raw", "jpeg"],
        },
        "acceptance": {
            "min_median_mae_recovery_pct": 1.0,
            "min_median_rmse_recovery_pct": 1.0,
            "source_evidence_present": present,
            "verdict": "source_signal_detected" if present else "source_signal_not_detected_above_nearest_same_color_2x",
        },
        "summary": {
            "linear_probe_mae_recovery_pct": {"median": mae},
            "linear_probe_rmse_recovery_pct": {"median": rmse},
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_replacement_target_", dir=temp_root()) as td:
        root = Path(td)
        x2d = root / "x2d.json"
        z8 = root / "z8.json"
        distribution = root / "target_distribution.json"
        snr = root / "target_snr.json"
        blocker = root / "blocker.json"
        out = root / "out"

        write_json(x2d, source_evidence("x2d", 4.82, 11.52, True))
        write_json(z8, source_evidence("z8", 0.65, 21.90, False))
        write_json(
            distribution,
            {
                "schema": "gpr.premium_still_sr_target_distribution_audit.v1",
                "summary": {"row_count": 117, "scene_count": 13, "camera_counts": {"x2d": 81, "z8": 36}},
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
                    "target_rmse_to_noise_sigma": {"median": 3.24},
                    "target_p95_to_noise_p95": {"median": 3.10},
                    "classification_counts": {"signal_dominated": 48, "mixed_signal_noise": 50, "noise_floor": 19},
                },
                "interpretation": "The target is mixed signal/noise by calibrated SNR.",
            },
        )
        write_json(
            blocker,
            {
                "schema": "gpr.premium_still_sr_target_degradation_evidence.v1",
                "verdict": "target_degradation_evidence_required_before_next_long_run",
                "long_run_allowed": False,
                "blocker_classification": "target_degradation_or_route_conditioning_mismatch",
                "blockers": ["paired smoke failed"],
            },
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--x2d-source-evidence",
                str(x2d),
                "--z8-source-evidence",
                str(z8),
                "--target-distribution",
                str(distribution),
                "--target-snr",
                str(snr),
                "--blocker",
                str(blocker),
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

        data = json.loads((out / "replacement_target_source_contract.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_replacement_target_source_contract.v1"
        assert data["verdict"] == "replacement_target_source_contract_ready"
        assert data["paired_smoke_preflight_allowed"] is True
        assert data["long_run_allowed"] is False
        assert data["decisions"]["x2d_route"]["decision"] == "use_candidate_only_signal_but_change_sampling_or_target_weighting"
        assert data["decisions"]["z8_route"]["decision"] == "replace_degradation_source_or_exclude_from_same_objective_until_source_evidence_passes"
        assert data["decisions"]["noise_policy"]["decision"] == "use_noise_aware_loss_or_row_filtering"
        assert any("candidate-only runtime inputs" in item for item in data["required_candidate_traits"])
        assert data["acceptance"]["promotion_median_mae_recovery_pct_min"] == 15.0

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Replacement Target Source Contract" in html
        assert "replacement_target_source_contract_ready" in html
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_premium_still_sr_replacement_target_source_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
