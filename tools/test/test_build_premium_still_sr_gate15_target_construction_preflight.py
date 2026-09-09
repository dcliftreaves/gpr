#!/usr/bin/env python3
"""Regression test for Gate15 target-construction preflight."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate15_target_construction_preflight.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def objective_audit() -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate14_objective_gate_audit.v1",
        "verdict": "blocked_before_gate_construction",
        "rows": [
            {
                "label": "direct:x2d",
                "blocker_classification": "insufficient_positive_signal",
                "row_count": 4,
                "positive_floor_row_count": 1,
                "minimum_rows_needed_for_median_floor": 3,
                "oracle_positive_noop_upper_bound": {"passes": False},
                "candidate_only_feature_gate_upper_bound": {"passes": False},
            }
        ],
    }


def target_builder() -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate14_floor_student_targets.v1",
        "target_builder_passed": True,
    }


def proposal(rows: list[dict], *, valid_policy: bool = True) -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate15_target_construction_proposal.v1",
        "candidate_id": "gate15_synthetic",
        "runtime_policy": {"forbidden_runtime_inputs_absent": valid_policy},
        "target_construction": {
            "uses_ref_or_source_at_render_time": False,
            "teacher_gate_before_student": True,
            "exact_noop_fallback": True,
        },
        "pretraining_signal_rows": rows,
    }


def run_tool(base: Path, proposal_path: Path | None) -> dict:
    out = base / "out"
    objective = base / "objective.json"
    target = base / "target.json"
    write_json(objective, objective_audit())
    write_json(target, target_builder())
    cmd = [
        sys.executable,
        str(TOOL),
        "--objective-gate-audit",
        str(objective),
        "--gate14-target-builder",
        str(target),
        "--output-dir",
        str(out),
        "--minimum-domain-row-count",
        "4",
    ]
    if proposal_path is not None:
        cmd.extend(["--proposal", str(proposal_path)])
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return json.loads((out / "target_construction_preflight.json").read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate15_preflight_", dir=temp_root()) as td:
        base = Path(td)
        data = run_tool(base / "missing", None)
        assert data["verdict"] == "blocked_pending_target_construction_proposal"
        assert data["paired_smoke_allowed"] is False

        bad = base / "bad.json"
        bad_rows = [
            {"domain": "x2d", "candidate_only_positive_floor": True, "tail_safe": True},
            {"domain": "x2d", "candidate_only_positive_floor": False, "tail_safe": True},
            {"domain": "x2d", "candidate_only_positive_floor": False, "tail_safe": True},
            {"domain": "x2d", "candidate_only_positive_floor": False, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
            {"domain": "z8", "exact_noop": False, "positive_source_evidence": False, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
        ]
        write_json(bad, proposal(bad_rows))
        data = run_tool(base / "badcase", bad)
        assert data["verdict"] == "blocked_target_construction_preflight"
        assert "x2d_candidate_only_positive_rows_below_median_floor" in data["proposal_assessment"]["failures"]
        assert "z8_exact_noop_or_positive_source_evidence_failed" in data["proposal_assessment"]["failures"]

        good = base / "good.json"
        good_rows = [
            {"domain": "x2d", "candidate_only_positive_floor": True, "tail_safe": True},
            {"domain": "x2d", "candidate_only_positive_floor": True, "tail_safe": True},
            {"domain": "x2d", "candidate_only_positive_floor": True, "tail_safe": True},
            {"domain": "x2d", "candidate_only_positive_floor": False, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
            {"domain": "z8", "exact_noop": True, "tail_safe": True},
        ]
        write_json(good, proposal(good_rows))
        data = run_tool(base / "goodcase", good)
        assert data["verdict"] == "gate15_target_construction_preflight_passed"
        assert data["paired_smoke_allowed"] is True
        assert data["long_run_allowed"] is False
    print("test_build_premium_still_sr_gate15_target_construction_preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
