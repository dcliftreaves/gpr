#!/usr/bin/env python3
"""Regression test for the premium still-SR blocker audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_blocker_audit.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_blocker_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"

        write_json(
            root / "artifacts/premium_still_sr_experiment_scoreboard_20260630/scoreboard.json",
            {
                "schema": "gpr.premium_still_sr_experiment_scoreboard.v1",
                "promotable_candidate_count": 0,
                "best_candidate": {
                    "experiment": "weak_scene_probe",
                    "holdout_residual_mae_reduction_pct_median": 4.0,
                    "holdout_residual_rmse_reduction_pct_median": 3.7,
                    "uses_source_hf_at_runtime": False,
                },
            },
        )
        write_json(
            root / "artifacts/premium_still_sr_readiness_20260630/readiness.json",
            {
                "schema": "gpr.premium_still_sr_readiness.v1",
                "production_ready": False,
                "evidence_summary": {
                    "latest_no_ref_hf_holdout_mae_reduction_pct_median": 2.5,
                    "latest_no_ref_hf_holdout_rmse_reduction_pct_median": 2.8,
                    "has_validated_x2d_z8_noise_sidecars": True,
                    "has_raw_editor_latitude_receipt": False,
                },
            },
        )
        write_json(
            root / "artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/merged/merge_receipt.json",
            {
                "schema": "gpr.premium_still_sr_hf_residual_targets_merged.v1",
                "summary": {
                    "row_count": 81,
                    "scene_count": 3,
                    "residual_abs_mean": {"median": 0.03},
                    "hf_y_correlation": {"median": 0.46},
                },
            },
        )
        write_json(
            root / "artifacts/premium_still_sr_x2d_multiscene_hf_residual_band_analysis_20260630/band_analysis.json",
            {
                "schema": "gpr.premium_still_sr_hf_residual_band_analysis.v1",
                "summary": {
                    "residual_corr_with_candidate_gradient": {"median": 0.10},
                    "bands": {
                        "fine": {
                            "share_of_residual_abs": {"median": 0.97},
                            "corr_with_target_band": {"median": 0.88},
                        },
                        "mid": {"share_of_residual_abs": {"median": 0.24}},
                    },
                    "brightness": {
                        "shadow": {"residual_abs_mean": {"median": 0.032}},
                        "highlight": {"residual_abs_mean": {"median": 0.021}},
                    },
                },
            },
        )

        proc = subprocess.run(
            [sys.executable, str(TOOL), "--external-root", str(root), "--output-dir", str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        audit = json.loads((out / "blocker_audit.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")
        assert audit["schema"] == "gpr.premium_still_sr_blocker_audit.v1"
        assert audit["production_ready"] is False
        assert audit["summary"]["promotable_candidate_count"] == 0
        assert audit["summary"]["best_holdout_mae_recovery_pct"] == 4.0
        assert audit["summary"]["target_scene_count"] == 3
        assert audit["summary"]["fine_band_residual_share_median"] == 0.97
        assert audit["summary"]["candidate_gradient_correlation_median"] == 0.10
        assert audit["sources"]["scoreboard"]["loaded"] is True
        assert [axis["id"] for axis in audit["axes"]] == [
            "promotion_metric_gap",
            "target_coverage_gap",
            "runtime_feature_gap",
            "noise_policy_gap",
            "promotion_gate_gap",
        ]
        assert audit["recommended_next_experiment"]["minimum_acceptance"]["minimum_target_rows"] == 256
        assert "Premium Still-SR Blocker Audit" in html
        assert "larger_context_raw_domain_noise_conditioned_texture_model" in html
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_premium_still_sr_blocker_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
