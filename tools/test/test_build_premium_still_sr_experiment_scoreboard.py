#!/usr/bin/env python3
"""Regression test for the premium still-SR experiment scoreboard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_experiment_scoreboard.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_receipt(
    root: Path,
    name: str,
    *,
    holdout_mae: float,
    holdout_rmse: float,
    train_mae: float,
    uses_source_hf_at_runtime: bool,
    model_arch: str = "plain",
) -> None:
    path = root / "artifacts" / name / "train_receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "gpr.premium_still_sr_hf_residual_model.v1",
        "checkpoint": f"{name}.pt",
        "checkpoint_sha256": "a" * 64,
        "steps": 10,
        "train_seconds": 1.25,
        "device": "cpu",
        "config": {
            "model_arch": model_arch,
            "feature_mode": "rgb_multiscale_coord_luma_ev_noise_bright",
            "holdout_scene": "scene_b",
        },
        "policy": {
            "uses_source_hf_at_training": True,
            "uses_source_hf_at_runtime": uses_source_hf_at_runtime,
            "production_status": "smoke_training_probe_not_registered_production_algorithm",
        },
        "eval": {
            "train": {
                "row_count": 4,
                "residual_mae_reduction_pct": {"median": train_mae},
                "residual_rmse_reduction_pct": {"median": train_mae + 0.5},
            },
            "holdout": {
                "row_count": 2,
                "residual_mae_reduction_pct": {"median": holdout_mae},
                "residual_rmse_reduction_pct": {"median": holdout_rmse},
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_raw_cfa_receipt(
    root: Path,
    name: str,
    *,
    holdout_mae: float,
    holdout_rmse: float,
    train_mae: float,
    uses_source_raw_at_runtime: bool,
    model_arch: str = "window_attention_teacher",
) -> None:
    path = root / "artifacts" / name / "train_receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
        "checkpoint": f"{name}.pt",
        "checkpoint_sha256": "b" * 64,
        "steps": 12,
        "train_seconds": 2.5,
        "device": "cpu",
        "config": {
            "model_arch": model_arch,
            "feature_mode": "raw_multiscale_coord_ev_noise_psf_cfa",
            "holdout_scene": "x2d_scene",
        },
        "policy": {
            "uses_source_raw_at_training": True,
            "uses_source_raw_at_runtime": uses_source_raw_at_runtime,
            "production_status": "training_probe_not_registered_production_algorithm",
        },
        "eval": {
            "train": {
                "row_count": 6,
                "raw_residual_mae_reduction_pct": {"median": train_mae},
                "raw_residual_rmse_reduction_pct": {"median": train_mae + 0.2},
            },
            "holdout": {
                "row_count": 3,
                "raw_residual_mae_reduction_pct": {"median": holdout_mae},
                "raw_residual_rmse_reduction_pct": {"median": holdout_rmse},
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_clean_source_pair_receipt(
    root: Path,
    name: str,
    *,
    holdout_mae: float,
    holdout_rmse: float,
    train_mae: float,
    model_arch: str = "restormer_pixelshuffle",
) -> None:
    path = root / "artifacts" / name / "train_receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
        "checkpoint": f"{name}.pt",
        "checkpoint_sha256": "c" * 64,
        "elapsed_seconds": 12.5,
        "device": "mps",
        "config": {
            "model_arch": model_arch,
            "steps": 100,
            "holdout_images": ["x2d_scene"],
        },
        "eval": {
            "train": {
                "tile_count": 64,
                "mae_improvement_pct": {"median": train_mae},
                "rmse_improvement_pct": {"median": train_mae + 0.1},
            },
            "holdout": {
                "tile_count": 32,
                "mae_improvement_pct": {"median": holdout_mae},
                "rmse_improvement_pct": {"median": holdout_rmse},
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_scoreboard_", dir=temp_root()) as tmp:
        external = Path(tmp) / "external"
        out = Path(tmp) / "out"
        write_receipt(
            external,
            "premium_still_sr_candidate_weak",
            holdout_mae=2.5,
            holdout_rmse=2.8,
            train_mae=4.0,
            uses_source_hf_at_runtime=False,
        )
        write_receipt(
            external,
            "premium_still_sr_candidate_ref_oracle",
            holdout_mae=30.0,
            holdout_rmse=32.0,
            train_mae=35.0,
            uses_source_hf_at_runtime=True,
        )
        write_receipt(
            external,
            "premium_still_sr_candidate_promotable_row",
            holdout_mae=16.0,
            holdout_rmse=17.0,
            train_mae=18.0,
            uses_source_hf_at_runtime=False,
            model_arch="raw_cfa_dilated_gated",
        )
        write_raw_cfa_receipt(
            external,
            "premium_still_sr_raw_cfa_window_attention_smoke",
            holdout_mae=4.0,
            holdout_rmse=4.2,
            train_mae=4.5,
            uses_source_raw_at_runtime=False,
        )
        write_raw_cfa_receipt(
            external,
            "premium_still_sr_raw_cfa_oracle",
            holdout_mae=40.0,
            holdout_rmse=41.0,
            train_mae=45.0,
            uses_source_raw_at_runtime=True,
        )
        write_clean_source_pair_receipt(
            external,
            "premium_still_sr_clean_source_pair_restormer_smoke",
            holdout_mae=0.2,
            holdout_rmse=0.3,
            train_mae=0.4,
        )

        subprocess.run([sys.executable, str(TOOL), "--external-root", str(external), "--output-dir", str(out)], cwd=ROOT, check=True)
        scoreboard = json.loads((out / "scoreboard.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")

        assert scoreboard["schema"] == "gpr.premium_still_sr_experiment_scoreboard.v1"
        assert scoreboard["receipt_count"] == 6
        assert scoreboard["promotable_candidate_count"] == 1
        assert scoreboard["runtime_safe_candidate_count"] == 4
        assert scoreboard["production_ready"] is True
        assert scoreboard["best_candidate"]["experiment"] == "premium_still_sr_raw_cfa_oracle"
        assert scoreboard["best_candidate"]["runtime_safe"] is False
        assert scoreboard["best_runtime_safe_candidate"]["experiment"] == "premium_still_sr_candidate_promotable_row"
        ready = [row for row in scoreboard["experiments"] if row["promotion_ready"]]
        assert ready[0]["experiment"] == "premium_still_sr_candidate_promotable_row"
        assert ready[0]["model_arch"] == "raw_cfa_dilated_gated"
        raw_rows = [row for row in scoreboard["experiments"] if row["experiment"] == "premium_still_sr_raw_cfa_window_attention_smoke"]
        assert raw_rows and raw_rows[0]["holdout_mae_metric"].endswith("raw_residual_mae_reduction_pct.median")
        assert raw_rows[0]["runtime_safe"] is True
        clean_rows = [
            row for row in scoreboard["experiments"]
            if row["experiment"] == "premium_still_sr_clean_source_pair_restormer_smoke"
        ]
        assert clean_rows
        assert clean_rows[0]["model_arch"] == "restormer_pixelshuffle"
        assert clean_rows[0]["holdout_mae_metric"].endswith("mae_improvement_pct.median")
        assert clean_rows[0]["holdout_row_count"] == 32
        assert clean_rows[0]["runtime_safe"] is True
        assert clean_rows[0]["production_status"] == "clean_source_teacher_not_final_candidate"
        assert "Premium Still-SR Experiment Scoreboard" in html
        assert "premium_still_sr_candidate_weak" in html
        assert "window_attention_teacher" in html
        assert "restormer_pixelshuffle" in html

    print("test_build_premium_still_sr_experiment_scoreboard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
