#!/usr/bin/env python3
"""Regression test for the premium still-SR next experiment contract."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_next_experiment_contract.py"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_next_contract_") as td:
        base = Path(td)
        inventory = base / "inventory.json"
        scoreboard = base / "scoreboard.json"
        residual_gap = base / "gap.json"
        requirements = base / "requirements.json"
        out_dir = base / "out"

        write_json(
            inventory,
            {
                "schema": "gpr.cnn_dataset_inventory.v1",
                "datasets": [
                    {
                        "id": "premium_still_sr_expanded_rawcfa_targets",
                        "path": "/synthetic/rawcfa",
                        "ready_for_current_work": True,
                        "missing_expected_artifacts": [],
                        "role": "canonical raw-CFA target",
                    },
                    {
                        "id": "premium_still_sr_raw_cfa_residual_targets",
                        "path": "/synthetic/residual",
                        "ready_for_current_work": True,
                        "missing_expected_artifacts": [],
                        "role": "raw residual target",
                    },
                ],
            },
        )
        write_json(
            scoreboard,
            {
                "schema": "gpr.premium_still_sr_experiment_scoreboard.v1",
                "receipt_count": 3,
                "promotable_candidate_count": 0,
                "production_ready": False,
                "best_candidate": {
                    "experiment": "synthetic_best",
                    "holdout_residual_mae_reduction_pct_median": 4.0,
                    "uses_source_hf_at_runtime": False,
                },
            },
        )
        write_json(
            residual_gap,
            {
                "schema": "gpr.premium_still_sr_raw_cfa_residual_gap.v1",
                "production_ready": False,
                "promotion_thresholds": {
                    "holdout_mae_recovery_pct_median_min": 15.0,
                    "holdout_rmse_recovery_pct_median_min": 0.0,
                    "runtime_source_raw_allowed": False,
                },
                "target": {
                    "path": "/synthetic/residual/raw_cfa_residual_targets.json",
                    "sha256": "abc",
                    "row_count": 351,
                    "scene_count": 13,
                    "scenes": ["x2d", "z8"],
                    "render_to_raw_corr_abs_median": 0.69,
                    "raw_to_render_hf_abs_ratio_median": 0.34,
                },
                "camera_summary": [
                    {
                        "camera": "X2D",
                        "best_holdout_mae_recovery_pct_median": 0.02,
                        "best_holdout_rmse_recovery_pct_median": -0.08,
                        "passes_threshold": False,
                        "best_path": "/synthetic/x2d/train_receipt.json",
                    },
                    {
                        "camera": "Z8",
                        "best_holdout_mae_recovery_pct_median": 0.49,
                        "best_holdout_rmse_recovery_pct_median": 1.7,
                        "passes_threshold": False,
                        "best_path": "/synthetic/z8/train_receipt.json",
                    },
                ],
                "blockers": [
                    "X2D holdout best median MAE recovery 0.020% is below 15.0%",
                    "Z8 holdout best median MAE recovery 0.490% is below 15.0%",
                ],
                "next_experiments": [
                    {
                        "priority": 1,
                        "name": "domain-balanced raw-CFA residual learner",
                        "purpose": "synthetic",
                        "must_prove": ["X2D median raw-residual MAE recovery >= 15.0%"],
                    }
                ],
            },
        )
        write_json(
            requirements,
            {
                "schema": "gpr.production_capture_requirements.v1",
                "requirements": [
                    {
                        "id": "premium_still_sr_promotion_receipts",
                        "status": "open",
                        "required_evidence": ["checkpoint"],
                        "acceptance": ["passes gate"],
                    }
                ],
            },
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(base),
                "--inventory",
                str(inventory),
                "--scoreboard",
                str(scoreboard),
                "--residual-gap",
                str(residual_gap),
                "--requirements",
                str(requirements),
                "--output-dir",
                str(out_dir),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        data = json.loads((out_dir / "premium_still_sr_next_experiment_contract.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_next_experiment_contract.v1"
        assert data["production_ready"] is False
        assert data["should_start_next_model_pass"] is True
        assert data["requirement"]["id"] == "premium_still_sr_promotion_receipts"
        assert all(row["ready_for_current_work"] for row in data["canonical_targets"])
        assert data["target_lock"]["row_count"] == 351
        assert data["current_model_state"]["scoreboard_promotable_candidate_count"] == 0
        assert data["current_model_state"]["best_by_camera"]["X2D"]["passes_threshold"] is False
        contract = data["next_model_contract"]
        research = data["research_basis"]
        assert any(row["id"] == "ntire_2024_raw_sr" for row in research)
        assert any("hardware-specific Bayer restoration" in row["repo_implication"] for row in research)
        assert any(row["id"] == "rethinking_raw_noise" for row in research)
        assert any("darkframe" in row["repo_implication"] for row in research)
        assert "source raw content" in contract["forbidden_runtime_inputs"]
        assert "JPEG-derived target content" in contract["forbidden_runtime_inputs"]
        assert "trained model priors distilled from external or offline teachers" in contract["allowed_runtime_inputs"]
        assert any("X2D median raw-residual MAE recovery >= 15.0%" == gate for gate in contract["success_gates"])
        assert any("stored candidate-HF" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("camera-balanced sampling" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("context-padding" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("pyramid U-Net" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("global-context U-Net" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("random context masking" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("nearest-neighbor residual patch dictionary" in item for item in contract["do_not_repeat_as_primary_path"])
        assert any("low-order linear candidate raw/HF/metadata" in item for item in contract["do_not_repeat_as_primary_path"])
        minimum = contract["minimum_viable_next_pass"]
        assert any("not reducible to independent local crop statistics" in item for item in minimum["must_change_from_failed_contract"])
        assert any("denoising, deblurring/PSF, and SR as one raw-restoration objective" in item for item in minimum["must_change_from_failed_contract"])
        assert any("sensor-pattern alignment" in item for item in minimum["must_change_from_failed_contract"])
        assert any("teacher-distilled" in item for item in minimum["acceptable_first_tracks"])
        assert any("NAF-style or transformer-style" in item for item in minimum["acceptable_first_tracks"])
        assert any("sensor-pattern-aligned real-noise conditioning" in item for item in minimum["acceptable_first_tracks"])
        assert any("patch-dictionary" in item for item in minimum["baseline_comparisons_required"])
        assert any("source raw" in item for item in minimum["early_reject_if"])
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Next Experiment Contract" in html
        assert "Forbidden Runtime Inputs" in html
        assert "Minimum Viable Next Pass" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")

    print("test_build_premium_still_sr_next_experiment_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
