#!/usr/bin/env python3
"""Regression test for the raw-video PSF detail metric audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_psf_detail_metric_audit.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary(image_count: int, *, detail_metrics: bool) -> dict:
    row = {
        "image": "fixture",
        "rmse_improvement_pct": 10.0,
        "mae_improvement_pct": 5.0,
        "gradient_mae_improvement_pct": 1.0,
    }
    data = {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": image_count,
        "images": [dict(row)],
        "rmse_improvement_pct": {"min": 10.0, "median": 11.0},
        "mae_improvement_pct": {"min": 5.0, "median": 6.0},
        "gradient_mae_improvement_pct": {"min": 1.0, "median": 2.0},
    }
    if detail_metrics:
        data["same_cell_detail_mae_improvement_pct"] = {"min": 3.0, "median": 4.0}
        data["same_cell_fine_detail_mae_improvement_pct"] = {"min": 2.0, "median": 3.0}
        data["cfa_plane_detail_mae_improvement_pct"] = {"r": 3.0, "g1": 4.0, "g2": 4.0, "b": 2.0}
    return data


def run_tool(root: Path, out: Path, scoreboard: Path) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--external-root",
            str(root),
            "--scoreboard",
            str(scoreboard),
            "--created-utc",
            "2026-07-01T01:23:45Z",
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
        raise SystemExit(proc.returncode)
    assert proc.stdout.strip() == str(out / "index.html")
    return json.loads((out / "raw_video_psf_detail_metric_audit.json").read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_raw_video_psf_detail_metric_", dir=temp_root()) as td:
        root = Path(td)
        missing_paths = {
            "mission_candidate": root / "missing/mission_candidate.json",
            "mission_baseline": root / "missing/mission_baseline.json",
            "z8_candidate": root / "missing/z8_candidate.json",
            "z8_baseline": root / "missing/z8_baseline.json",
        }
        ready_paths = {
            "mission_candidate": root / "ready/mission_candidate.json",
            "mission_baseline": root / "ready/mission_baseline.json",
            "z8_candidate": root / "ready/z8_candidate.json",
            "z8_baseline": root / "ready/z8_baseline.json",
        }
        for key, path in missing_paths.items():
            write_json(path, summary(42 if key.startswith("mission") else 24, detail_metrics=False))
        for key, path in ready_paths.items():
            write_json(path, summary(42 if key.startswith("mission") else 24, detail_metrics=True))

        missing_scoreboard = root / "missing/scoreboard.json"
        write_json(
            missing_scoreboard,
            {
                "schema": "gpr.raw_video_sr_candidate_scoreboard.v1",
                "decision_count": 1,
                "promotable_row_count": 0,
                "best_candidate": {
                    "experiment": "missing",
                    "mission": {
                        "candidate_summary": str(missing_paths["mission_candidate"]),
                        "baseline_summary": str(missing_paths["mission_baseline"]),
                    },
                    "z8": {
                        "candidate_summary": str(missing_paths["z8_candidate"]),
                        "baseline_summary": str(missing_paths["z8_baseline"]),
                    },
                },
            },
        )
        missing = run_tool(root, root / "missing/out", missing_scoreboard)
        assert missing["schema"] == "gpr.raw_video_psf_detail_metric_audit.v1"
        assert missing["created_utc"] == "2026-07-01T01:23:45Z"
        assert missing["metrics"]["coverage_ready"] is True
        assert missing["metrics"]["same_cell_detail_metric_ready"] is False
        assert missing["metrics"]["psf_detail_gate_ready"] is False
        assert missing["production_status"] == "blocked_missing_same_cell_detail_metrics"
        assert "same_cell_detail_mae_improvement_pct" in missing["missing_by_summary"]["mission_candidate"]

        ready_scoreboard = root / "ready/scoreboard.json"
        write_json(
            ready_scoreboard,
            {
                "schema": "gpr.raw_video_sr_candidate_scoreboard.v1",
                "decision_count": 1,
                "promotable_row_count": 0,
                "best_candidate": {
                    "experiment": "ready",
                    "mission": {
                        "candidate_summary": str(ready_paths["mission_candidate"]),
                        "baseline_summary": str(ready_paths["mission_baseline"]),
                    },
                    "z8": {
                        "candidate_summary": str(ready_paths["z8_candidate"]),
                        "baseline_summary": str(ready_paths["z8_baseline"]),
                    },
                },
            },
        )
        ready = run_tool(root, root / "ready/out", ready_scoreboard)
        assert ready["metrics"]["coverage_ready"] is True
        assert ready["metrics"]["same_cell_detail_metric_ready"] is True
        assert ready["metrics"]["psf_detail_gate_ready"] is True
        assert ready["production_status"] == "psf_detail_metrics_present"
        assert not ready["missing_by_summary"]
        assert "Raw Video PSF Detail Metric Audit" in (root / "ready/out/index.html").read_text(encoding="utf-8")

    print("test_build_raw_video_psf_detail_metric_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
