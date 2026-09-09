#!/usr/bin/env python3
"""Regression test for the Gate14 objective gate audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate14_objective_gate_audit.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt(values: list[float], *, feature_values: list[float] | None = None) -> dict:
    if feature_values is None:
        feature_values = list(range(len(values)))
    return {
        "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
        "checkpoint_sha256": "a" * 64,
        "config": {"holdout_scene": "x2d_test"},
        "eval": {
            "holdout": {
                "rows": [
                    {
                        "image_id": "x2d_test",
                        "tile_index": idx,
                        "candidate_hf_abs_mean": feature_values[idx],
                        "raw_residual_mae_reduction_pct": value,
                    }
                    for idx, value in enumerate(values)
                ]
            }
        },
    }


def run_tool(base: Path, *receipts: Path) -> dict:
    out = base / "out"
    cmd = [sys.executable, str(TOOL), "--output-dir", str(out)]
    for path in receipts:
        cmd.extend(["--receipt", str(path)])
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return json.loads((out / "objective_gate_audit.json").read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate14_obj_", dir=temp_root()) as td:
        base = Path(td)
        insufficient = base / "insufficient.json"
        write_json(insufficient, receipt([2.0, 2.0, 0.0, 0.0, -4.0, 0.0]))
        data = run_tool(base / "case1", insufficient)
        assert data["schema"] == "gpr.premium_still_sr_gate14_objective_gate_audit.v1"
        assert data["verdict"] == "blocked_before_gate_construction"
        assert data["rows"][0]["blocker_classification"] == "insufficient_positive_signal"
        assert data["rows"][0]["positive_floor_row_count"] == 2
        assert data["rows"][0]["minimum_rows_needed_for_median_floor"] == 4

        separable = base / "separable.json"
        write_json(separable, receipt([2.0, 2.0, 2.0, 2.0, -5.0, 0.0], feature_values=[10, 11, 12, 13, 0, 1]))
        data = run_tool(base / "case2", separable)
        assert data["verdict"] == "gate14_objective_gate_rescue_possible"
        assert data["rows"][0]["oracle_positive_noop_upper_bound"]["passes"] is True
        assert data["rows"][0]["candidate_only_feature_gate_upper_bound"]["passes"] is True
        assert data["rows"][0]["candidate_only_feature_gate_upper_bound"]["safe_predicate_count"] >= 1
    print("test_build_premium_still_sr_gate14_objective_gate_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
