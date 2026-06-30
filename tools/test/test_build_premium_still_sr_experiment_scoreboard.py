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
        )

        subprocess.run([sys.executable, str(TOOL), "--external-root", str(external), "--output-dir", str(out)], cwd=ROOT, check=True)
        scoreboard = json.loads((out / "scoreboard.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")

        assert scoreboard["schema"] == "gpr.premium_still_sr_experiment_scoreboard.v1"
        assert scoreboard["receipt_count"] == 3
        assert scoreboard["promotable_candidate_count"] == 1
        assert scoreboard["production_ready"] is True
        assert scoreboard["best_candidate"]["experiment"] == "premium_still_sr_candidate_ref_oracle"
        ready = [row for row in scoreboard["experiments"] if row["promotion_ready"]]
        assert ready[0]["experiment"] == "premium_still_sr_candidate_promotable_row"
        assert "Premium Still-SR Experiment Scoreboard" in html
        assert "premium_still_sr_candidate_weak" in html

    print("test_build_premium_still_sr_experiment_scoreboard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
