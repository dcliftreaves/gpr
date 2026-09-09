#!/usr/bin/env python3
"""Regression test for the raw-video SR candidate scoreboard."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_sr_candidate_scoreboard.py"


def write_decision(
    path: Path,
    *,
    reject: bool,
    mission_delta: float,
    z8_delta: float,
    z8_count: int = 24,
    detail_delta: float | None = 1.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    decision = {
        "schema": "gpr.test_sr_decision.v1",
        "decision": "reject_do_not_register" if reject else "keep_for_review",
        "reason": "reject regression" if reject else "candidate improves shared holdouts",
        "baseline": {
            "mission_holdout": {
                "image_count": 42,
                "rmse_improvement_min": 30.0,
                "gradient_improvement_min": 8.0,
                "same_cell_detail_improvement_median": 4.0,
                "same_cell_fine_detail_improvement_median": 3.0,
                "cfa_plane_detail_improvement_median": 4.0,
            },
            "z8_regenerated_holdout": {
                "image_count": z8_count,
                "rmse_improvement_min": 20.0,
                "gradient_improvement_min": 2.0,
                "same_cell_detail_improvement_median": 1.0,
                "same_cell_fine_detail_improvement_median": 0.8,
                "cfa_plane_detail_improvement_median": 1.0,
            },
        },
        "candidate": {
            "description": path.parent.name,
            "checkpoint_sha256": "b" * 64,
            "mission_holdout": {
                "image_count": 42,
                "rmse_improvement_min": 30.0 + mission_delta,
                "gradient_improvement_min": 8.0 + mission_delta,
                "same_cell_detail_improvement_median": 4.0 + (detail_delta or 0.0),
                "same_cell_fine_detail_improvement_median": 3.0 + (detail_delta or 0.0),
                "cfa_plane_detail_improvement_median": 4.0 + (detail_delta or 0.0),
            },
            "z8_regenerated_holdout": {
                "image_count": z8_count,
                "rmse_improvement_min": 20.0 + z8_delta,
                "gradient_improvement_min": 2.0 + z8_delta,
                "same_cell_detail_improvement_median": 1.0 + (detail_delta or 0.0),
                "same_cell_fine_detail_improvement_median": 0.8 + (detail_delta or 0.0),
                "cfa_plane_detail_improvement_median": 1.0 + (detail_delta or 0.0),
            },
        },
    }
    if detail_delta is None:
        for group in ("baseline", "candidate"):
            for holdout in ("mission_holdout", "z8_regenerated_holdout"):
                decision[group][holdout].pop("same_cell_detail_improvement_median", None)
                decision[group][holdout].pop("same_cell_fine_detail_improvement_median", None)
                decision[group][holdout].pop("cfa_plane_detail_improvement_median", None)
    path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_sr_candidate_scoreboard_") as tmp:
        external = Path(tmp) / "external"
        out = Path(tmp) / "out"
        write_decision(external / "artifacts/current_goal_sr_good/decision.json", reject=False, mission_delta=1.5, z8_delta=0.5)
        write_decision(external / "artifacts/current_goal_sr_rejected/decision.json", reject=True, mission_delta=5.0, z8_delta=5.0)
        write_decision(external / "artifacts/current_goal_sr_z8_regress/decision.json", reject=False, mission_delta=1.0, z8_delta=-1.0)
        write_decision(
            external / "artifacts/current_goal_sr_missing_detail/decision.json",
            reject=False,
            mission_delta=2.0,
            z8_delta=2.0,
            detail_delta=None,
        )

        proc = subprocess.run(
            [sys.executable, str(TOOL), "--external-root", str(external), "--output-dir", str(out)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        data = json.loads((out / "scoreboard.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")
        assert data["schema"] == "gpr.raw_video_sr_candidate_scoreboard.v1"
        assert data["decision_count"] == 4
        assert data["promotable_row_count"] == 1
        assert data["non_rejected_row_count"] == 3
        assert data["mission_ok_row_count"] == 4
        assert data["z8_ok_row_count"] == 3
        assert data["psf_detail_ready_row_count"] == 3
        assert data["psf_detail_ok_row_count"] == 3
        assert data["production_ready"] is False
        assert data["best_candidate"]["experiment"] == "current_goal_sr_good"
        assert data["best_promotable_candidate"]["experiment"] == "current_goal_sr_good"
        assert data["best_non_rejected_candidate"]["experiment"] == "current_goal_sr_good"
        promotable = [row for row in data["rows"] if row["promotable_row"]]
        assert promotable[0]["experiment"] == "current_goal_sr_good"
        missing_detail = [row for row in data["rows"] if row["experiment"] == "current_goal_sr_missing_detail"][0]
        assert missing_detail["mission_ok"] is True
        assert missing_detail["z8_ok"] is True
        assert missing_detail["psf_detail_ready"] is False
        assert missing_detail["promotable_row"] is False
        assert "Raw Video SR Candidate Scoreboard" in html
        assert "PSF detail-ready rows" in html
        assert proc.stdout.strip() == str(out / "scoreboard.json")

    print("test_build_raw_video_sr_candidate_scoreboard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
