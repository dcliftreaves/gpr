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


def write_decision(path: Path, *, reject: bool, mission_delta: float, z8_delta: float, z8_count: int = 24) -> None:
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
            },
            "z8_regenerated_holdout": {
                "image_count": z8_count,
                "rmse_improvement_min": 20.0,
                "gradient_improvement_min": 2.0,
            },
        },
        "candidate": {
            "description": path.parent.name,
            "checkpoint_sha256": "b" * 64,
            "mission_holdout": {
                "image_count": 42,
                "rmse_improvement_min": 30.0 + mission_delta,
                "gradient_improvement_min": 8.0 + mission_delta,
            },
            "z8_regenerated_holdout": {
                "image_count": z8_count,
                "rmse_improvement_min": 20.0 + z8_delta,
                "gradient_improvement_min": 2.0 + z8_delta,
            },
        },
    }
    path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_sr_candidate_scoreboard_") as tmp:
        external = Path(tmp) / "external"
        out = Path(tmp) / "out"
        write_decision(external / "artifacts/current_goal_sr_good/decision.json", reject=False, mission_delta=1.5, z8_delta=0.5)
        write_decision(external / "artifacts/current_goal_sr_rejected/decision.json", reject=True, mission_delta=5.0, z8_delta=5.0)
        write_decision(external / "artifacts/current_goal_sr_z8_regress/decision.json", reject=False, mission_delta=1.0, z8_delta=-1.0)

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
        assert data["decision_count"] == 3
        assert data["promotable_row_count"] == 1
        assert data["non_rejected_row_count"] == 2
        assert data["mission_ok_row_count"] == 3
        assert data["z8_ok_row_count"] == 2
        assert data["production_ready"] is False
        assert data["best_candidate"]["experiment"] == "current_goal_sr_good"
        assert data["best_promotable_candidate"]["experiment"] == "current_goal_sr_good"
        assert data["best_non_rejected_candidate"]["experiment"] == "current_goal_sr_good"
        promotable = [row for row in data["rows"] if row["promotable_row"]]
        assert promotable[0]["experiment"] == "current_goal_sr_good"
        assert "Raw Video SR Candidate Scoreboard" in html
        assert proc.stdout.strip() == str(out / "scoreboard.json")

    print("test_build_raw_video_sr_candidate_scoreboard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
