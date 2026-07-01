#!/usr/bin/env python3
"""Regression test for the raw-video PSF next-experiment contract builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_psf_next_experiment_contract.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_raw_video_psf_contract_", dir=temp_root()) as td:
        root = Path(td)
        modeled = root / "modeled.json"
        native = root / "native.json"
        scoreboard = root / "scoreboard.json"
        gap = root / "gap.json"
        out = root / "out"
        write_json(
            modeled,
            {
                "schema": "gpr.bayer_resize_psf_receipt.v1",
                "production_ready": False,
                "psf_model": {
                    "best_candidate_kernel": "same_color_box2",
                    "normalized_weights": [0.25, 0.25, 0.25, 0.25],
                    "rmse_14bit": 0.3,
                },
                "detail_budget": {
                    "fine_share_of_residual_abs": 0.999,
                    "mid_share_of_residual_abs": 0.003,
                    "coarse_share_of_residual_abs": 0.002,
                    "residual_to_target_cell_detail_ratio": 1.0,
                },
            },
        )
        write_json(
            native,
            {
                "schema": "gpr.mission1_native_psf_kernel_stability_audit.v1",
                "summary": {
                    "selected_pair_count": 3,
                    "accepted_pair_count": 2,
                    "rejected_pair_count": 1,
                    "combined_weight_std_max": 0.809,
                    "combined_weight_mean_min": -0.34,
                    "accepted_negative_weight_pair_count": 1,
                    "native_psf_ready_for_model_conditioning": False,
                    "combined_kernel_stable_in_source_receipt": False,
                },
            },
        )
        write_json(
            scoreboard,
            {
                "schema": "gpr.raw_video_sr_candidate_scoreboard.v1",
                "decision_count": 89,
                "promotable_row_count": 0,
                "best_candidate": {
                    "experiment": "candidate",
                    "mission_ok": False,
                    "z8_ok": True,
                    "promotable_row": False,
                },
            },
        )
        write_json(
            gap,
            {
                "schema": "gpr.raw_video_psf_gap_plan.v1",
                "summary": {"production_psf_closure_ready": False},
            },
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(root),
                "--modeled-psf",
                str(modeled),
                "--native-stability",
                str(native),
                "--sr-scoreboard",
                str(scoreboard),
                "--gap-plan",
                str(gap),
                "--created-utc",
                "2026-07-01T00:29:21Z",
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
        data = json.loads((out / "raw_video_psf_next_experiment_contract.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.raw_video_psf_next_experiment_contract.v1"
        assert data["created_utc"] == "2026-07-01T00:29:21Z"
        assert data["production_ready"] is False
        assert data["local_experiments_allowed"] is True
        assert data["current_state"]["modeled_pair_kernel"]["best_candidate_kernel"] == "same_color_box2"
        assert data["current_state"]["native_kernel"]["ready_for_model_conditioning"] is False
        assert data["current_state"]["sr_scoreboard"]["promotable_row_count"] == 0
        contract = data["next_experiment_contract"]
        assert any("unstable native Mission 1 kernel" in item for item in contract["do_not_promote_or_repeat_as_production"])
        assert any("Mission42 and Z8 all24" in item for item in contract["success_gates"])
        assert "Raw Video PSF Next Experiment Contract" in (out / "index.html").read_text(encoding="utf-8")
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_raw_video_psf_next_experiment_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
