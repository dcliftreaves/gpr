#!/usr/bin/env python3
"""Gate15 Premium still-SR target-construction preflight.

This is the fast guard that follows the Gate14 objective-gate audit. It does
not train a model. It accepts a proposed target-row manifest and answers one
question before any smoke run: does the proposed target construction contain
enough candidate-only positive X2D rows to clear a median smoke floor while
keeping Z8 exact no-op unless positive source evidence exists?
"""
from __future__ import annotations

import argparse
import html
import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate15_target_construction_preflight.v1"
PROPOSAL_SCHEMA = "gpr.premium_still_sr_gate15_target_construction_proposal.v1"
ARTIFACT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/artifacts")
DEFAULT_OBJECTIVE_AUDIT = ARTIFACT_ROOT / "premium_still_sr_gate14_objective_gate_audit_20260702" / "objective_gate_audit.json"
DEFAULT_GATE14_TARGET_BUILDER = ARTIFACT_ROOT / "premium_still_sr_gate14_floor_student_targets_20260702" / "gate14_floor_student_targets.json"
DEFAULT_OUTPUT_DIR = ARTIFACT_ROOT / "premium_still_sr_gate15_target_construction_preflight_20260702"


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def bool_value(row: dict[str, Any], key: str) -> bool:
    return row.get(key) is True


def row_domain(row: dict[str, Any]) -> str:
    return str(row.get("domain") or row.get("camera_key") or row.get("camera") or "").lower()


def summarize_gate14_audit(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "label": row.get("label"),
                "blocker_classification": row.get("blocker_classification"),
                "row_count": row.get("row_count"),
                "positive_floor_row_count": row.get("positive_floor_row_count"),
                "minimum_rows_needed_for_median_floor": row.get("minimum_rows_needed_for_median_floor"),
                "oracle_passes": (row.get("oracle_positive_noop_upper_bound") or {}).get("passes"),
                "candidate_only_feature_gate_passes": (row.get("candidate_only_feature_gate_upper_bound") or {}).get("passes"),
            }
        )
    return out


def proposal_rows(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = proposal.get("pretraining_signal_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def assess_proposal(proposal: dict[str, Any], *, minimum_domain_row_count: int) -> dict[str, Any]:
    rows = proposal_rows(proposal)
    x2d_rows = [row for row in rows if "x2d" in row_domain(row)]
    z8_rows = [row for row in rows if "z8" in row_domain(row) or "z8z" in row_domain(row)]

    x2d_positive_rows = [
        row
        for row in x2d_rows
        if bool_value(row, "candidate_only_positive_floor") and bool_value(row, "tail_safe")
    ]
    x2d_needed = len(x2d_rows) // 2 + 1 if x2d_rows else None
    z8_unsafe_rows = [
        row
        for row in z8_rows
        if not bool_value(row, "tail_safe")
        or (not bool_value(row, "exact_noop") and not bool_value(row, "positive_source_evidence"))
    ]

    runtime_policy = proposal.get("runtime_policy") if isinstance(proposal.get("runtime_policy"), dict) else {}
    target_policy = proposal.get("target_construction") if isinstance(proposal.get("target_construction"), dict) else {}
    failures: list[str] = []
    if proposal.get("schema") != PROPOSAL_SCHEMA:
        failures.append("proposal_schema_invalid")
    if runtime_policy.get("forbidden_runtime_inputs_absent") is not True:
        failures.append("forbidden_runtime_inputs_not_proven_absent")
    if target_policy.get("uses_ref_or_source_at_render_time") is True:
        failures.append("proposal_uses_ref_or_source_at_render_time")
    if target_policy.get("teacher_gate_before_student") is not True:
        failures.append("teacher_gate_before_student_missing")
    if target_policy.get("exact_noop_fallback") is not True:
        failures.append("exact_noop_fallback_missing")
    if len(x2d_rows) < minimum_domain_row_count:
        failures.append("x2d_row_count_below_floor")
    if len(z8_rows) < minimum_domain_row_count:
        failures.append("z8_row_count_below_floor")
    if x2d_needed is None or len(x2d_positive_rows) < x2d_needed:
        failures.append("x2d_candidate_only_positive_rows_below_median_floor")
    if z8_unsafe_rows:
        failures.append("z8_exact_noop_or_positive_source_evidence_failed")

    return {
        "proposal_id": proposal.get("candidate_id") or proposal.get("proposal_id"),
        "row_count": len(rows),
        "x2d": {
            "row_count": len(x2d_rows),
            "candidate_only_positive_floor_row_count": len(x2d_positive_rows),
            "minimum_rows_needed_for_median_floor": x2d_needed,
        },
        "z8": {
            "row_count": len(z8_rows),
            "unsafe_row_count": len(z8_unsafe_rows),
            "exact_noop_row_count": sum(1 for row in z8_rows if bool_value(row, "exact_noop")),
            "positive_source_evidence_row_count": sum(1 for row in z8_rows if bool_value(row, "positive_source_evidence")),
        },
        "failures": failures,
        "passes": not failures,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    objective_audit = load_json(args.objective_gate_audit)
    target_builder = load_json(args.gate14_target_builder) if args.gate14_target_builder.exists() else {}
    proposal = load_json(args.proposal) if args.proposal else None
    proposal_assessment = (
        assess_proposal(proposal, minimum_domain_row_count=args.minimum_domain_row_count)
        if proposal is not None
        else None
    )
    if proposal_assessment is None:
        verdict = "blocked_pending_target_construction_proposal"
        blocker = "proposal_missing"
        next_action = (
            "Build a Gate15 target-construction proposal with pretraining_signal_rows. "
            "It must prove X2D candidate-only positive rows before smoke training."
        )
    elif proposal_assessment["passes"]:
        verdict = "gate15_target_construction_preflight_passed"
        blocker = "none"
        next_action = "Run paired X2D/Z8 smokes; do not run long training until the paired smoke gate passes."
    else:
        verdict = "blocked_target_construction_preflight"
        blocker = str(proposal_assessment["failures"][0])
        next_action = "Revise target construction; do not run paired smokes or long training from this proposal."

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "production_ready": False,
        "paired_smoke_allowed": bool(proposal_assessment and proposal_assessment["passes"]),
        "long_run_allowed": False,
        "blocker_classification": blocker,
        "next_unambiguous_action": next_action,
        "inputs": {
            "objective_gate_audit": {
                "path": str(args.objective_gate_audit),
                "sha256": sha256_file(args.objective_gate_audit),
                "verdict": objective_audit.get("verdict"),
            },
            "gate14_target_builder": {
                "path": str(args.gate14_target_builder),
                "sha256": sha256_file(args.gate14_target_builder) if args.gate14_target_builder.exists() else None,
                "target_builder_passed": target_builder.get("target_builder_passed"),
            },
            "proposal": {
                "path": str(args.proposal) if args.proposal else None,
                "sha256": sha256_file(args.proposal) if args.proposal else None,
            },
        },
        "acceptance": {
            "minimum_domain_row_count": args.minimum_domain_row_count,
            "x2d_requires_candidate_only_positive_rows_for_median": True,
            "z8_requires_exact_noop_or_positive_source_evidence": True,
            "forbidden_runtime_inputs_absent_required": True,
            "teacher_gate_before_student_required": True,
            "exact_noop_fallback_required": True,
        },
        "gate14_objective_audit_summary": summarize_gate14_audit(objective_audit),
        "proposal_assessment": proposal_assessment,
    }


def render_html(data: dict[str, Any]) -> str:
    assessment = data.get("proposal_assessment") or {}
    failures = ", ".join(assessment.get("failures") or [])
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('label')))}</td>"
        f"<td>{html.escape(str(row.get('positive_floor_row_count')))} / {html.escape(str(row.get('minimum_rows_needed_for_median_floor')))}</td>"
        f"<td>{html.escape(str(row.get('blocker_classification')))}</td>"
        "</tr>"
        for row in data.get("gate14_objective_audit_summary", [])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Gate15 Target Construction Preflight</title>
<style>
body {{ margin: 28px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; }}
.card {{ border: 1px solid #d8dde3; border-radius: 8px; padding: 14px; margin: 12px 0; }}
.value {{ font-size: 22px; font-weight: 760; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; }}
th {{ background: #eef2f7; }}
</style></head><body>
<h1>Gate15 Target Construction Preflight</h1>
<section class="card"><div>Verdict</div><div class="value">{html.escape(data['verdict'])}</div></section>
<section class="card"><div>Blocker</div><div class="value">{html.escape(data['blocker_classification'])}</div></section>
<p><strong>Next action:</strong> {html.escape(data['next_unambiguous_action'])}</p>
<h2>Proposal Assessment</h2>
<pre>{html.escape(json.dumps(assessment, indent=2, sort_keys=True))}</pre>
<p>{html.escape(failures)}</p>
<h2>Gate14 Failed Objective Capacity</h2>
<table><tr><th>receipt</th><th>positive rows / needed</th><th>blocker</th></tr>{rows}</table>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--objective-gate-audit", type=Path, default=DEFAULT_OBJECTIVE_AUDIT)
    ap.add_argument("--gate14-target-builder", type=Path, default=DEFAULT_GATE14_TARGET_BUILDER)
    ap.add_argument("--proposal", type=Path)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-domain-row-count", type=int, default=32)
    args = ap.parse_args()

    receipt = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "target_construction_preflight.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(json_path),
                "dashboard": str(html_path),
                "verdict": receipt["verdict"],
                "paired_smoke_allowed": receipt["paired_smoke_allowed"],
                "blocker_classification": receipt["blocker_classification"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
