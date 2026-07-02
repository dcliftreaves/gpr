#!/usr/bin/env python3
"""Build the Gate16 Premium still-SR full-promotion launch packet.

This is the handoff between the successful Gate16 paired smoke and the strict
50 MP / 100 MP production gate. It does not claim production readiness and it
does not convert smoke metrics into full-frame metrics. It makes the next run
unambiguous: which candidate is being promoted, which receipts authorize the
attempt, which thresholds must be met, and what evidence is still missing.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate16_promotion_launch_packet.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_CANDIDATE_ID = "premium_still_sr_gate16_tail_safe_x2d_positive_z8_noop_v1"
DEFAULT_PREFLIGHT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_tail_safe_smoke_20260702"
    / "candidate_preflight.json"
)
DEFAULT_PREFLIGHT_AUDIT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_tail_safe_smoke_20260702"
    / "preflight_audit.json"
)
DEFAULT_ACCEPTANCE = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_tail_safe_smoke_acceptance_20260702"
    / "smoke_gate_acceptance.json"
)
DEFAULT_X2D_TRAIN = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_x2d_tail_safe_0015_smoke_20260702"
    / "train_receipt.json"
)
DEFAULT_Z8_NOOP = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate15_z8_exact_noop_smoke_20260702"
    / "train_receipt.json"
)
DEFAULT_ROUTE_READINESS = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_route_readiness_with_rendered_20260702"
    / "route_readiness.json"
)
DEFAULT_EDITOR_COVERAGE = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_editor_latitude_coverage_20260702"
    / "coverage.json"
)
DEFAULT_NOISE_GATE = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_noise_policy_gate_20260702"
    / "premium_still_sr_noise_policy_gate.json"
)
DEFAULT_PROMOTION_ROLLUP = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_promotion_receipts_gate16_20260702"
    / "premium_still_sr_promotion_receipts.json"
)

MAE_RMSE_FLOOR_PCT = 15.0


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    return float(value) if isinstance(value, (int, float)) else default


def row_by_holdout(acceptance: dict[str, Any], holdout: str) -> dict[str, Any]:
    holdout = holdout.casefold()
    for row in as_list(acceptance.get("rows")):
        if isinstance(row, dict) and str(row.get("holdout") or "").casefold() == holdout:
            return row
    return {}


def route_metrics(route_readiness: dict[str, Any]) -> dict[str, Any]:
    routes = [row for row in as_list(route_readiness.get("routes")) if isinstance(row, dict)]
    by_route = {str(row.get("route_key")): row for row in routes}
    x2d = as_dict(by_route.get("x2d:100mp:dng"))
    fifty_rows = [
        row
        for row in routes
        if str(row.get("route_key") or "").endswith(":50mp:dng")
        or str(row.get("route_key") or "").endswith(":50mp:gpr")
    ]
    return {
        "required_route_count": len(as_list(route_readiness.get("required_routes"))),
        "ready_route_count": sum(1 for row in routes if row.get("positive_fullframe_metrics") is True),
        "route_coverage_ready": route_readiness.get("route_coverage_ready") is True,
        "fullframe_metric_floor_ready": route_readiness.get("fullframe_metric_floor_ready") is True,
        "rendered_proxy_review_ready": route_readiness.get("rendered_proxy_review_ready") is True,
        "best_50mp_median_mae_pct": max((number(row.get("median_mae_improvement_pct")) for row in fifty_rows), default=0.0),
        "best_50mp_median_rmse_pct": max((number(row.get("median_rmse_improvement_pct")) for row in fifty_rows), default=0.0),
        "x2d_100mp_median_mae_pct": number(x2d.get("median_mae_improvement_pct")),
        "x2d_100mp_median_rmse_pct": number(x2d.get("median_rmse_improvement_pct")),
        "note": "Route readiness is existing specialist evidence only; it is not a Gate16 full-promotion substitute.",
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    preflight = load_json(args.preflight)
    audit = load_json(args.preflight_audit)
    acceptance = load_json(args.smoke_acceptance)
    x2d_train = load_json(args.x2d_train_receipt)
    z8_noop = load_json(args.z8_noop_receipt)
    route = load_json(args.route_readiness)
    editor = load_json(args.editor_coverage)
    noise = load_json(args.noise_policy_gate)
    rollup = load_json(args.promotion_rollup)

    x2d_row = row_by_holdout(acceptance, "x2d")
    z8_row = row_by_holdout(acceptance, "z8")
    checkpoint = Path(str(x2d_train.get("checkpoint") or ""))
    checkpoint_artifact = artifact(checkpoint) if checkpoint.as_posix() else {"path": "", "exists": False, "sha256": None}
    noise_clean = as_dict(noise.get("clean_signal"))
    route_summary = route_metrics(route)

    prerequisites = [
        {
            "id": "candidate_preflight",
            "passed": preflight.get("candidate_id") == args.candidate_id
            and preflight.get("launchable_for_production_attempt") is True
            and preflight.get("uses_ref_or_source_content_at_render_time") is False
            and preflight.get("forbidden_runtime_inputs_absent") is True,
            "receipt": artifact(args.preflight),
        },
        {
            "id": "preflight_audit",
            "passed": audit.get("verdict") == "launchable_preflight_passed",
            "receipt": artifact(args.preflight_audit),
        },
        {
            "id": "paired_smoke_acceptance",
            "passed": acceptance.get("smoke_gate_passed") is True
            and acceptance.get("long_run_allowed") is True
            and number(x2d_row.get("median_mae_improvement_pct")) >= 1.0
            and number(x2d_row.get("worst_row_mae_improvement_pct"), -999.0) >= 0.0
            and number(z8_row.get("worst_row_mae_improvement_pct"), -999.0) >= 0.0,
            "receipt": artifact(args.smoke_acceptance),
        },
        {
            "id": "checkpoint_hash",
            "passed": checkpoint_artifact["exists"]
            and checkpoint_artifact["sha256"] == x2d_train.get("checkpoint_sha256"),
            "checkpoint": checkpoint_artifact,
        },
        {
            "id": "route_and_editor_coverage",
            "passed": route.get("route_coverage_ready") is True
            and editor.get("production_ready") is True
            and editor.get("openability_route_coverage_ready") is True
            and editor.get("latitude_route_coverage_ready") is True,
            "route_readiness": artifact(args.route_readiness),
            "editor_coverage": artifact(args.editor_coverage),
        },
        {
            "id": "clean_signal_noise_policy",
            "passed": noise_clean.get("policy_pass") is True
            and number(noise_clean.get("row_count")) > 0
            and number(noise_clean.get("rows_with_noise_sidecars")) > 0,
            "receipt": artifact(args.noise_policy_gate),
        },
        {
            "id": "gate16_rollup_registered",
            "passed": rollup.get("first_open_step") == "model_promotion_floor"
            and rollup.get("done_step_count") == 5
            and rollup.get("total_step_count") == 9,
            "receipt": artifact(args.promotion_rollup),
        },
    ]

    missing_evidence = [
        "Gate16-specific 50 MP full-frame MAE/RMSE rows",
        "Gate16-specific 100 MP full-frame MAE/RMSE rows",
        "nonnegative worst-row proof on both 50 MP and 100 MP rows",
        "Gate16 render_seconds_per_50mp_frame",
        "Gate16 render_seconds_per_100mp_frame",
        "Gate16 peak_rss_gb",
        "Gate16 model receipt wired to exact-sidecar-only noise policy",
        "production submission check using the Gate16 full gate receipt",
    ]
    blocked_by_existing_route_metrics = route_summary["x2d_100mp_median_mae_pct"] < MAE_RMSE_FLOOR_PCT or route_summary[
        "x2d_100mp_median_rmse_pct"
    ] < MAE_RMSE_FLOOR_PCT
    all_prereqs = all(row["passed"] for row in prerequisites)
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": args.candidate_id,
        "production_ready": False,
        "ready_to_launch_full_gate": all_prereqs,
        "first_open_step": "gate16_full_frame_metric_generation",
        "promotion_thresholds": {
            "median_mae_reduction_pct_50mp": MAE_RMSE_FLOOR_PCT,
            "median_rmse_reduction_pct_50mp": MAE_RMSE_FLOOR_PCT,
            "median_mae_reduction_pct_100mp": MAE_RMSE_FLOOR_PCT,
            "median_rmse_reduction_pct_100mp": MAE_RMSE_FLOOR_PCT,
            "worst_row_mae_reduction_pct_50mp": 0.0,
            "worst_row_mae_reduction_pct_100mp": 0.0,
        },
        "prerequisites": prerequisites,
        "smoke_summary": {
            "x2d_median_mae_reduction_pct": number(x2d_row.get("median_mae_improvement_pct")),
            "x2d_worst_row_mae_reduction_pct": number(x2d_row.get("worst_row_mae_improvement_pct"), -999.0),
            "z8_median_mae_reduction_pct": number(z8_row.get("median_mae_improvement_pct")),
            "z8_worst_row_mae_reduction_pct": number(z8_row.get("worst_row_mae_improvement_pct"), -999.0),
            "x2d_checkpoint_sha256": x2d_row.get("checkpoint_sha256") or x2d_train.get("checkpoint_sha256"),
            "z8_checkpoint_sha256": z8_row.get("checkpoint_sha256") or z8_noop.get("checkpoint_sha256"),
        },
        "existing_route_metrics": route_summary,
        "blocked_by_existing_route_metrics": blocked_by_existing_route_metrics,
        "missing_evidence_before_100_percent": missing_evidence,
        "required_commands_after_full_metrics_exist": [
            "python3 tools/build_premium_still_sr_gate_receipt.py --production-ready --real-artifacts ...",
            "python3 tools/check_premium_still_sr_promotion_gate.py --require-production-ready ...",
            "python3 tools/build_premium_still_sr_promotion_receipts.py --require-production-ready ...",
            "python3 tools/check_production_capture_submission.py ...",
        ],
        "stop_rule": (
            "Stop only when the full Gate16 receipt reaches production_ready=true, or when the full-frame "
            "run identifies a specific failed subcondition: 50 MP floor, 100 MP floor, worst-row tail, "
            "timing/memory, noise-policy wiring, editor/openability, or production-submission validation."
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "gate16_promotion_launch_packet.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": json_path.as_posix(), "dashboard": html_path.as_posix(), "ready_to_launch_full_gate": all_prereqs}, indent=2))
    if args.require_ready_to_launch and not all_prereqs:
        return receipt | {"_exit_code": 1}
    return receipt | {"_exit_code": 0}


def render_html(receipt: dict[str, Any]) -> str:
    cards = [
        ("Production ready", receipt["production_ready"]),
        ("Ready to launch full gate", receipt["ready_to_launch_full_gate"]),
        ("First open step", receipt["first_open_step"]),
        ("100 MP existing MAE", f"{receipt['existing_route_metrics']['x2d_100mp_median_mae_pct']:.3f}%"),
        ("Missing evidence", len(receipt["missing_evidence_before_100_percent"])),
    ]
    card_html = "\n".join(
        f"<section class='card'><div class='label'>{html.escape(label)}</div><div class='value'>{html.escape(str(value))}</div></section>"
        for label, value in cards
    )
    prereq_rows = "\n".join(
        f"<tr><td>{html.escape(row['id'])}</td><td>{html.escape(str(row['passed']).lower())}</td></tr>"
        for row in receipt["prerequisites"]
    )
    missing = "\n".join(f"<li>{html.escape(item)}</li>" for item in receipt["missing_evidence_before_100_percent"])
    commands = "\n".join(f"<li><code>{html.escape(item)}</code></li>" for item in receipt["required_commands_after_full_metrics_exist"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate16 Premium Still-SR Promotion Launch Packet</title>
<style>
body {{ margin: 30px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f6f8fa; }}
main {{ max-width: 1120px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }}
.sub {{ color: #5c6773; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style>
<main>
<h1>Gate16 Premium Still-SR Promotion Launch Packet</h1>
<p class="sub">This packet authorizes the full 50 MP / 100 MP Gate16 promotion attempt. It is not a production claim; production remains false until the full gate, timing/memory, noise-policy wiring, and production submission all pass.</p>
<div class="grid">{card_html}</div>
<h2>Prerequisites</h2>
<table><tr><th>item</th><th>passed</th></tr>{prereq_rows}</table>
<h2>Missing Evidence</h2>
<ul>{missing}</ul>
<h2>Required Commands After Full Metrics Exist</h2>
<ul>{commands}</ul>
</main>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID)
    ap.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    ap.add_argument("--preflight-audit", type=Path, default=DEFAULT_PREFLIGHT_AUDIT)
    ap.add_argument("--smoke-acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    ap.add_argument("--x2d-train-receipt", type=Path, default=DEFAULT_X2D_TRAIN)
    ap.add_argument("--z8-noop-receipt", type=Path, default=DEFAULT_Z8_NOOP)
    ap.add_argument("--route-readiness", type=Path, default=DEFAULT_ROUTE_READINESS)
    ap.add_argument("--editor-coverage", type=Path, default=DEFAULT_EDITOR_COVERAGE)
    ap.add_argument("--noise-policy-gate", type=Path, default=DEFAULT_NOISE_GATE)
    ap.add_argument("--promotion-rollup", type=Path, default=DEFAULT_PROMOTION_ROLLUP)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--require-ready-to-launch", action="store_true")
    return ap.parse_args()


def main() -> int:
    return int(build(parse_args()).get("_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
