#!/usr/bin/env python3
"""Build a Mission 1 4K cleanup production-signoff receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_4k_cleanup_production_signoff.v1"
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_BASE = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
)
DEFAULT_VISUAL_DIR = DEFAULT_EXTERNAL_ROOT / "artifacts/mission1_4k_cleanup_visual_signoff_20260625"
DEFAULT_PIPELINE_ID = "mission1_native12_4k_cleanup_rgb_cfa_w40_v1"
RAW_GUARD_METRICS = {
    "high_res_cfa_target": {
        "rmse": "cfa_raw_rmse_improvement_pct",
        "mae": "cfa_raw_mae_improvement_pct",
        "psnr": "cfa_raw_psnr_delta_db",
        "target": "high-resolution-derived CFA raw target",
    },
    "legacy_clean_low": {
        "rmse": "rmse_improvement_pct",
        "mae": "mae_improvement_pct",
        "psnr": "psnr_delta_db",
        "target": "legacy clean-low Bayer proxy",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def relpath(path: Path, external_root: Path) -> str:
    try:
        return str(path.relative_to(external_root))
    except ValueError:
        return str(path)


def metric_summary_value(summary: dict[str, Any], metric: str, key: str) -> float | None:
    values = summary.get(metric)
    if not isinstance(values, dict):
        return None
    value = values.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def raw_domain_guard(args: argparse.Namespace) -> dict[str, Any]:
    payload = read_json(args.raw_guard_summary)
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise TypeError("raw_guard_summary.summary must be an object")
    metric_names = RAW_GUARD_METRICS[args.raw_guard_kind]
    row_count = int(summary.get("count") or 0)
    rmse_min = metric_summary_value(summary, metric_names["rmse"], "min")
    mae_min = metric_summary_value(summary, metric_names["mae"], "min")
    psnr_min = metric_summary_value(summary, metric_names["psnr"], "min")
    passed = (
        row_count > 0
        and rmse_min is not None
        and mae_min is not None
        and psnr_min is not None
        and rmse_min >= args.min_raw_rmse_improvement_pct
        and mae_min >= args.min_raw_mae_improvement_pct
        and psnr_min >= args.min_raw_psnr_delta_db
    )
    return {
        "path": relpath(args.raw_guard_summary, args.external_root),
        "sha256": sha256_file(args.raw_guard_summary),
        "kind": args.raw_guard_kind,
        "target": metric_names["target"],
        "source_schema": payload.get("schema"),
        "row_count": row_count,
        "thresholds": {
            "min_rmse_improvement_pct": args.min_raw_rmse_improvement_pct,
            "min_mae_improvement_pct": args.min_raw_mae_improvement_pct,
            "min_psnr_delta_db": args.min_raw_psnr_delta_db,
        },
        "metrics": {
            "rmse_improvement_pct": summary.get(metric_names["rmse"]),
            "mae_improvement_pct": summary.get(metric_names["mae"]),
            "psnr_delta_db": summary.get(metric_names["psnr"]),
        },
        "source_metric_names": {
            "rmse_improvement_pct": metric_names["rmse"],
            "mae_improvement_pct": metric_names["mae"],
            "psnr_delta_db": metric_names["psnr"],
        },
        "passed": passed,
    }


def legacy_clean_low_diagnostic(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.legacy_clean_low_summary.exists():
        return None
    payload = read_json(args.legacy_clean_low_summary)
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return None
    return {
        "path": relpath(args.legacy_clean_low_summary, args.external_root),
        "sha256": sha256_file(args.legacy_clean_low_summary),
        "target": RAW_GUARD_METRICS["legacy_clean_low"]["target"],
        "metrics": {
            "rmse_improvement_pct": summary.get("rmse_improvement_pct"),
            "mae_improvement_pct": summary.get("mae_improvement_pct"),
            "psnr_delta_db": summary.get("psnr_delta_db"),
        },
        "production_blocking": False,
        "note": "Diagnostic only for this branch; the 4K cleanup CNN targets the high-resolution-derived CFA raw objective.",
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    visual = read_json(args.visual_signoff)
    checks = visual.get("checks", [])
    if not isinstance(checks, list):
        raise TypeError("visual_signoff.checks must be a list")
    all_checks_passed = all(isinstance(check, dict) and check.get("passed") is True for check in checks)

    blocking_issues = list(args.blocking_issue or [])
    production_ready = bool(args.production_ready)
    if production_ready and blocking_issues:
        raise ValueError("--production-ready cannot be combined with --blocking-issue")
    if production_ready and not all_checks_passed:
        raise ValueError("--production-ready requires all objective visual checks to pass")
    raw_guard = raw_domain_guard(args)
    if not raw_guard["passed"]:
        blocking_issues.append("raw-domain guard does not beat the baseline")
    if production_ready and not raw_guard["passed"]:
        raise ValueError("--production-ready requires the raw-domain guard to pass")
    if not production_ready and not args.blocker_cause:
        raise ValueError("blocked/non-production receipt requires --blocker-cause")

    dashboard_paths = args.dashboard_path or [
        str(DEFAULT_BASE / "mission42_rgb_cfa_target_gate_wb_review/index.html"),
        str(DEFAULT_BASE / "mission42_4k_cnn_tone_audit_20260625/index.html"),
    ]

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "candidate": {
            "pipeline_id": args.pipeline_id,
            "checkpoint_path": relpath(args.checkpoint, args.external_root),
            "checkpoint_sha256": sha256_file(args.checkpoint),
            "visual_signoff_path": relpath(args.visual_signoff, args.external_root),
            "visual_signoff_sha256": sha256_file(args.visual_signoff),
            "contact_sheet_path": relpath(args.contact_sheet, args.external_root),
            "contact_sheet_sha256": sha256_file(args.contact_sheet),
        },
        "objective_visual_signoff": {
            "verdict": str(visual.get("verdict", "")),
            "all_checks_passed": all_checks_passed,
            "check_count": len(checks),
        },
        "raw_domain_guard": raw_guard,
        "diagnostics": {},
        "reviewer": {
            "name": args.reviewer_name,
            "role": args.reviewer_role,
            "reviewed_at_utc": args.reviewed_at_utc,
        },
        "review": {
            "visual_checked": bool(args.visual_checked),
            "contact_sheet_path": relpath(args.contact_sheet, args.external_root),
            "dashboard_paths": [relpath(Path(path), args.external_root) for path in dashboard_paths],
            "blocking_issues": blocking_issues,
        },
        "verdict": {
            "production_ready": production_ready,
            "accepted_role": "production" if production_ready else "blocked",
            "no_blocking_visual_issues": not blocking_issues,
        },
    }
    legacy_diagnostic = legacy_clean_low_diagnostic(args)
    if legacy_diagnostic:
        receipt["diagnostics"]["legacy_clean_low_raw_guard"] = legacy_diagnostic
    if not production_ready:
        receipt["blocker"] = {"cause": args.blocker_cause}
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--pipeline-id", default=DEFAULT_PIPELINE_ID)
    ap.add_argument("--checkpoint", type=Path, default=DEFAULT_BASE / "bayer_rgb_target_w40_d5_rs015_gamma2_grad1_raw2_bayer2_step1000.pt")
    ap.add_argument("--visual-signoff", type=Path, default=DEFAULT_VISUAL_DIR / "visual_signoff.json")
    ap.add_argument("--contact-sheet", type=Path, default=DEFAULT_VISUAL_DIR / "visual_signoff_contact_sheet.jpg")
    ap.add_argument("--raw-guard-summary", type=Path, default=DEFAULT_BASE / "mission42_rgb_cfa_target_gate_wb_review/summary.json")
    ap.add_argument("--raw-guard-kind", choices=sorted(RAW_GUARD_METRICS), default="high_res_cfa_target")
    ap.add_argument("--legacy-clean-low-summary", type=Path, default=DEFAULT_BASE / "mission42_raw_guard/summary.json")
    ap.add_argument("--min-raw-rmse-improvement-pct", type=float, default=0.0)
    ap.add_argument("--min-raw-mae-improvement-pct", type=float, default=0.0)
    ap.add_argument("--min-raw-psnr-delta-db", type=float, default=0.0)
    ap.add_argument("--dashboard-path", action="append", default=[])
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--reviewer-name", required=True)
    ap.add_argument("--reviewer-role", default="project-owner")
    ap.add_argument("--reviewed-at-utc", required=True)
    ap.add_argument("--visual-checked", action="store_true")
    ap.add_argument("--production-ready", action="store_true")
    ap.add_argument("--blocking-issue", action="append", default=[])
    ap.add_argument("--blocker-cause", default="")
    args = ap.parse_args()

    try:
        receipt = build_receipt(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"build_mission1_4k_cleanup_signoff_receipt: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"output": str(args.output), "production_ready": receipt["verdict"]["production_ready"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
