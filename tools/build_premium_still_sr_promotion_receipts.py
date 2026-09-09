#!/usr/bin/env python3
"""Build the Premium still-SR promotion receipt.

This is the strict product-row receipt for the slow offline still-SR pillar. It
does not train a model and it does not promote diagnostic selector-smoke work.
It consolidates the current Gate 14 selector smoke, route coverage,
editor/openability, noise policy, formal promotion gate, and production-capture
requirements into one receipt so the next blocker is explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_promotion_receipts.v1"
REQUIREMENT_ID = "premium_still_sr_promotion_receipts"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_SELECTOR_SMOKE = DEFAULT_ROOT / "artifacts/premium_still_sr_gate14_selector_smoke_20260702/selector_smoke.json"
DEFAULT_ROUTE_READINESS = DEFAULT_ROOT / "artifacts/premium_still_sr_route_readiness_with_rendered_20260702/route_readiness.json"
DEFAULT_EDITOR_COVERAGE = DEFAULT_ROOT / "artifacts/premium_still_sr_editor_latitude_coverage_20260702/coverage.json"
DEFAULT_NOISE_GATE = DEFAULT_ROOT / "artifacts/premium_still_sr_noise_policy_gate_20260702/premium_still_sr_noise_policy_gate.json"
DEFAULT_PROMOTION_GATE = DEFAULT_ROOT / "artifacts/premium_still_sr_promotion_gate_current_20260702/premium_still_sr_promotion_gate.json"
DEFAULT_SMOKE_ACCEPTANCE = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_tail_safe_smoke_acceptance_20260702"
    / "smoke_gate_acceptance.json"
)
DEFAULT_REQUIREMENTS = Path("docs/PRODUCTION_CAPTURE_REQUIREMENTS.json")

PROMOTION_THRESHOLD_PCT = 15.0


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


def integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    return int(value) if isinstance(value, int) else default


def selector_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    metrics = as_dict(data.get("selector_smoke_metrics"))
    by_image = as_dict(metrics.get("by_image"))
    source_failures = as_list(data.get("source_model_failures"))
    passed = (
        data.get("schema") == "gpr.premium_still_sr_gate14_selector_smoke.v1"
        and data.get("gate14_selector_smoke_passed") is True
        and data.get("promotion_gate_allowed") is True
        and not source_failures
        and metrics.get("negative_row_count") == 0
    )
    medians = [
        number(row.get("median"), -999.0)
        for row in by_image.values()
        if isinstance(row, dict) and "median" in row
    ]
    return {
        "artifact": artifact(path),
        "passed": passed,
        "production_ready": bool(data.get("production_ready")),
        "promotion_gate_allowed": data.get("promotion_gate_allowed") is True,
        "long_run_allowed": data.get("long_run_allowed") is True,
        "rule_count": integer(data.get("rule_count")),
        "source_count": integer(data.get("source_count")),
        "assigned_row_count": integer(data.get("assigned_row_count")),
        "fallback_exact_noop_count": integer(data.get("fallback_exact_noop_count")),
        "source_model_failure_count": len(source_failures),
        "global_median_mae_pct": number(metrics.get("median")),
        "global_worst_mae_pct": number(metrics.get("min")),
        "best_image_median_mae_pct": max(medians) if medians else 0.0,
        "worst_image_median_mae_pct": min(medians) if medians else 0.0,
        "negative_row_count": integer(metrics.get("negative_row_count")),
    }


def route_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    blockers = as_list(data.get("blockers"))
    return {
        "artifact": artifact(path),
        "route_coverage_ready": data.get("route_coverage_ready") is True,
        "fullframe_metric_floor_ready": data.get("fullframe_metric_floor_ready") is True,
        "rendered_proxy_review_ready": data.get("rendered_proxy_review_ready") is True,
        "production_ready": data.get("production_ready") is True,
        "blockers": blockers,
        "route_count": len(as_list(data.get("routes"))),
    }


def editor_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": artifact(path),
        "production_ready": data.get("production_ready") is True,
        "openability_route_coverage_ready": data.get("openability_route_coverage_ready") is True,
        "latitude_route_coverage_ready": data.get("latitude_route_coverage_ready") is True,
        "blockers": as_list(data.get("blockers")),
    }


def noise_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    clean = as_dict(data.get("clean_signal"))
    model_receipts = as_list(data.get("model_receipts"))
    return {
        "artifact": artifact(path),
        "production_ready": data.get("production_ready") is True,
        "clean_signal_policy_pass": clean.get("policy_pass") is True,
        "clean_signal_rows": integer(clean.get("row_count")),
        "rows_with_noise_sidecars": integer(clean.get("rows_with_noise_sidecars")),
        "model_receipt_count": len(model_receipts),
        "model_policy_pass_count": sum(1 for row in model_receipts if isinstance(row, dict) and row.get("policy_pass") is True),
        "blockers": as_list(data.get("blockers")),
        "decision": data.get("decision"),
    }


def promotion_gate_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    full_gate = as_dict(data.get("full_gate_receipt"))
    promotion = as_dict(full_gate.get("promotion_metrics"))
    performance = as_dict(full_gate.get("performance"))
    return {
        "artifact": artifact(path),
        "promotion_safe": data.get("promotion_safe") is True,
        "production_ready": data.get("production_ready") is True,
        "decision": data.get("decision"),
        "blockers": as_list(data.get("blockers")),
        "full_frame_gate_50mp_row_count": integer(promotion.get("full_frame_gate_50mp_row_count")),
        "full_frame_gate_100mp_row_count": integer(promotion.get("full_frame_gate_100mp_row_count")),
        "median_mae_reduction_pct_50mp": number(promotion.get("median_mae_reduction_pct_50mp")),
        "median_mae_reduction_pct_100mp": number(promotion.get("median_mae_reduction_pct_100mp")),
        "render_seconds_per_50mp_frame": number(performance.get("render_seconds_per_50mp_frame")),
        "render_seconds_per_100mp_frame": number(performance.get("render_seconds_per_100mp_frame")),
        "peak_rss_gb": number(performance.get("peak_rss_gb")),
    }


def smoke_acceptance_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in as_list(data.get("rows")) if isinstance(row, dict)]
    by_holdout = {str(row.get("holdout") or "").lower(): row for row in rows}
    x2d = as_dict(by_holdout.get("x2d"))
    z8 = as_dict(by_holdout.get("z8"))
    return {
        "artifact": artifact(path),
        "smoke_gate_passed": data.get("smoke_gate_passed") is True,
        "long_run_allowed": data.get("long_run_allowed") is True,
        "verdict": data.get("verdict"),
        "candidate_id": data.get("candidate_id"),
        "x2d_median_mae_reduction_pct": number(x2d.get("median_mae_improvement_pct")),
        "x2d_worst_row_mae_reduction_pct": number(x2d.get("worst_row_mae_improvement_pct"), -999.0),
        "z8_median_mae_reduction_pct": number(z8.get("median_mae_improvement_pct")),
        "z8_worst_row_mae_reduction_pct": number(z8.get("worst_row_mae_improvement_pct"), -999.0),
        "x2d_checkpoint_sha256": x2d.get("checkpoint_sha256"),
        "z8_checkpoint_sha256": z8.get("checkpoint_sha256"),
        "failures": as_list(data.get("failures")),
    }


def requirements_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in as_list(data.get("requirements")) if isinstance(row, dict)]
    row = next((item for item in rows if item.get("id") == REQUIREMENT_ID), {})
    commands = "\n".join(str(item) for item in as_list(row.get("validation_commands")))
    acceptance = " ".join(str(item) for item in as_list(row.get("acceptance")))
    required_evidence = " ".join(str(item) for item in as_list(row.get("required_evidence")))
    required_tokens = (
        "50 MP and 100 MP",
        "candidate raw",
        "camera metadata",
        "seconds per 50 MP frame",
        "seconds per 100 MP frame",
        "peak RSS",
        "source residual noise",
    )
    return {
        "artifact": artifact(path),
        "requirement_found": bool(row),
        "status": row.get("status"),
        "sample_type": row.get("sample_type"),
        "required_tokens_present": all(token in acceptance + " " + required_evidence for token in required_tokens),
        "has_candidate_preflight_command": "check_premium_still_sr_candidate_preflight.py" in commands,
        "has_launch_packet_command": "build_premium_still_sr_launch_packet.py" in commands,
    }


def build_steps(statuses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    selector = statuses["gate14_selector_smoke"]
    route = statuses["route_readiness"]
    editor = statuses["editor_openability"]
    noise = statuses["noise_policy"]
    promotion = statuses["promotion_gate"]
    smoke = statuses["smoke_acceptance"]
    requirements = statuses["production_requirements"]
    return [
        {
            "id": "gate14_selector_smoke",
            "done": selector["passed"],
            "done_when": "Persisted selector sidecar reloads, recomputes candidate-only runtime features, verifies source/checkpoint hashes, routes deterministically, and matches intake.",
            "next": "Protect the receipt and do not rerun Gate 14 as production work.",
        },
        {
            "id": "route_coverage",
            "done": route["route_coverage_ready"] and route["fullframe_metric_floor_ready"] and route["rendered_proxy_review_ready"],
            "done_when": "Mission 1 50 MP DNG/GPR, Z8 50 MP DNG, and X2D 100 MP DNG routes have full-frame positive metric floors and rendered proxy review.",
            "next": "Use these routes in the full promotion gate.",
        },
        {
            "id": "editor_openability",
            "done": editor["production_ready"] and editor["openability_route_coverage_ready"] and editor["latitude_route_coverage_ready"],
            "done_when": "Every required route opens as editable raw and has non-oracle raw-editor latitude evidence.",
            "next": "Keep linked editor receipts as promotion inputs.",
        },
        {
            "id": "clean_signal_noise_policy",
            "done": noise["clean_signal_policy_pass"],
            "done_when": "Clean target policy passes and render-time source residual noise is forbidden.",
            "next": "Wire exact-sidecar-only policy into the promotable model receipt.",
        },
        {
            "id": "paired_smoke_gate",
            "done": (
                smoke["smoke_gate_passed"]
                and smoke["long_run_allowed"]
                and smoke["x2d_median_mae_reduction_pct"] >= 1.0
                and smoke["x2d_worst_row_mae_reduction_pct"] >= 0.0
                and smoke["z8_worst_row_mae_reduction_pct"] >= 0.0
            ),
            "done_when": "Candidate-specific X2D and Z8 smoke acceptance passes before any long/full promotion run.",
            "next": "Use the accepted smoke candidate in the full 50 MP / 100 MP promotion gate.",
        },
        {
            "id": "model_promotion_floor",
            "done": noise["production_ready"] and promotion["production_ready"],
            "done_when": "A candidate-only model clears 15% / 15% held-out MAE/RMSE, with no REF/source/JPEG/gate metric runtime inputs.",
            "next": "Train or distill a candidate that beats the floor, then rebuild the promotion gate.",
        },
        {
            "id": "full_50mp_100mp_gate",
            "done": (
                promotion["full_frame_gate_50mp_row_count"] > 0
                and promotion["full_frame_gate_100mp_row_count"] > 0
                and promotion["median_mae_reduction_pct_50mp"] >= PROMOTION_THRESHOLD_PCT
                and promotion["median_mae_reduction_pct_100mp"] >= PROMOTION_THRESHOLD_PCT
            ),
            "done_when": "50 MP and 100 MP full gates have row counts and median MAE/RMSE recovery >= 15%.",
            "next": "Run full-image/holdout promotion validation, not another crop-only selector smoke.",
        },
        {
            "id": "timing_memory",
            "done": (
                promotion["render_seconds_per_50mp_frame"] > 0.0
                and promotion["render_seconds_per_100mp_frame"] > 0.0
                and promotion["peak_rss_gb"] > 0.0
            ),
            "done_when": "50 MP seconds/frame, 100 MP seconds/frame, and peak RSS are recorded for the actual render path.",
            "next": "Run timing around the exact model/render path used by the full gate.",
        },
        {
            "id": "production_submission",
            "done": (
                requirements["requirement_found"]
                and requirements["required_tokens_present"]
                and requirements["has_candidate_preflight_command"]
                and requirements["has_launch_packet_command"]
                and promotion["production_ready"]
            ),
            "done_when": "Production capture submission validates with explicit Premium still-SR promotion receipts.",
            "next": "Build the submission only after model, full-gate, editor, noise, timing, and memory receipts pass.",
        },
    ]


def classify_blockers(steps: list[dict[str, Any]], statuses: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    ids = {step["id"]: bool(step["done"]) for step in steps}
    if not ids["model_promotion_floor"]:
        blockers.append("model_promotion_floor_not_met")
    if not ids["paired_smoke_gate"]:
        blockers.append("paired_smoke_gate_not_passed")
    if not ids["full_50mp_100mp_gate"]:
        blockers.append("full_50mp_100mp_gate_missing")
    if not ids["timing_memory"]:
        blockers.append("timing_memory_missing")
    if not ids["production_submission"]:
        blockers.append("production_submission_missing_or_failed")
    if not ids["editor_openability"]:
        blockers.append("editor_openability_missing")
    if statuses["noise_policy"]["clean_signal_policy_pass"] and not statuses["noise_policy"]["production_ready"]:
        blockers.append("noise_policy_not_wired")
    elif not statuses["noise_policy"]["clean_signal_policy_pass"]:
        blockers.append("noise_policy_not_wired")
    if not ids["gate14_selector_smoke"]:
        blockers.append("checkpoint_or_sidecar_drift")
    return sorted(set(blockers))


def render_html(receipt: dict[str, Any]) -> str:
    cards = [
        ("Production ready", receipt["production_ready"]),
        ("Done steps", f"{receipt['done_step_count']}/{receipt['total_step_count']}"),
        ("Completion", f"{receipt['completion_percent']:.1f}%"),
        ("First open row", receipt["first_open_step"]),
        ("Blockers", len(receipt["blocker_classifications"])),
    ]
    card_html = "\n".join(
        f"<section class='card'><div class='label'>{html.escape(label)}</div><div class='value'>{html.escape(str(value))}</div></section>"
        for label, value in cards
    )
    step_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(step['id'])}</td>"
        f"<td>{html.escape(str(step['done']).lower())}</td>"
        f"<td>{html.escape(step['done_when'])}</td>"
        f"<td>{html.escape(step['next'])}</td>"
        "</tr>"
        for step in receipt["steps"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in receipt["blocker_classifications"]) or "<li>None</li>"
    inputs = "\n".join(
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td><code>{html.escape(section['artifact']['path'])}</code></td>"
        f"<td>{html.escape(str(section['artifact']['exists']).lower())}</td>"
        f"<td><code>{html.escape(str(section['artifact']['sha256']))}</code></td>"
        "</tr>"
        for label, section in receipt["inputs"].items()
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Promotion Receipts</title>
<style>
body {{ margin: 30px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f6f8fa; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; font-size: 31px; }}
.sub {{ color: #5c6773; max-width: 920px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 21px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style>
<main>
<h1>Premium Still-SR Promotion Receipts</h1>
<p class="sub">Strict product-row receipt. It can only report production ready when the no-REF model floor, 50 MP / 100 MP gates, editor/openability, timing/memory, exact-sidecar-only noise policy, and production submission all pass.</p>
<div class="grid">{card_html}</div>
<h2>Blockers</h2>
<ul>{blockers}</ul>
<h2>Steps</h2>
<table><tr><th>step</th><th>done</th><th>done when</th><th>next</th></tr>{step_rows}</table>
<h2>Inputs</h2>
<table><tr><th>input</th><th>path</th><th>exists</th><th>sha256</th></tr>{inputs}</table>
</main>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    statuses = {
        "gate14_selector_smoke": selector_status(args.selector_smoke, load_json(args.selector_smoke)),
        "route_readiness": route_status(args.route_readiness, load_json(args.route_readiness)),
        "editor_openability": editor_status(args.editor_coverage, load_json(args.editor_coverage)),
        "noise_policy": noise_status(args.noise_policy_gate, load_json(args.noise_policy_gate)),
        "promotion_gate": promotion_gate_status(args.promotion_gate, load_json(args.promotion_gate)),
        "smoke_acceptance": smoke_acceptance_status(args.smoke_acceptance, load_json(args.smoke_acceptance)),
        "production_requirements": requirements_status(args.production_requirements, load_json(args.production_requirements)),
    }
    steps = build_steps(statuses)
    done_count = sum(1 for step in steps if step["done"])
    blockers = classify_blockers(steps, statuses)
    first_open = next((step["id"] for step in steps if not step["done"]), None)
    production_ready = done_count == len(steps) and not blockers
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_ready": production_ready,
        "requirement_id": REQUIREMENT_ID,
        "completion_percent": round(100.0 * done_count / len(steps), 1),
        "done_step_count": done_count,
        "total_step_count": len(steps),
        "first_open_step": first_open,
        "blocker_classifications": blockers,
        "inputs": statuses,
        "steps": steps,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "premium_still_sr_promotion_receipts.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": json_path.as_posix(),
                "dashboard": html_path.as_posix(),
                "production_ready": production_ready,
                "completion_percent": receipt["completion_percent"],
                "first_open_step": first_open,
                "blockers": blockers,
            },
            indent=2,
        )
    )
    if args.require_production_ready and not production_ready:
        return receipt | {"_exit_code": 1}
    return receipt | {"_exit_code": 0}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selector-smoke", type=Path, default=DEFAULT_SELECTOR_SMOKE)
    ap.add_argument("--route-readiness", type=Path, default=DEFAULT_ROUTE_READINESS)
    ap.add_argument("--editor-coverage", type=Path, default=DEFAULT_EDITOR_COVERAGE)
    ap.add_argument("--noise-policy-gate", type=Path, default=DEFAULT_NOISE_GATE)
    ap.add_argument("--promotion-gate", type=Path, default=DEFAULT_PROMOTION_GATE)
    ap.add_argument("--smoke-acceptance", type=Path, default=DEFAULT_SMOKE_ACCEPTANCE)
    ap.add_argument("--production-requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--require-production-ready", action="store_true")
    return ap.parse_args()


def main() -> int:
    return int(build(parse_args()).get("_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
