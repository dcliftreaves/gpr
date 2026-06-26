#!/usr/bin/env python3
"""Validate a Mission 1 4K cleanup production-signoff receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_4k_cleanup_production_signoff.v1"


def as_bool(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> bool | None:
    value = obj.get(key)
    if not isinstance(value, bool):
        failures.append(f"{prefix}.{key} must be boolean")
        return None
    return value


def as_int(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> int | None:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        failures.append(f"{prefix}.{key} must be integer")
        return None
    return value


def require_obj(root: dict[str, Any], key: str, failures: list[str]) -> dict[str, Any]:
    value = root.get(key)
    if not isinstance(value, dict):
        failures.append(f"{key} must be an object")
        return {}
    return value


def require_string(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        failures.append(f"{prefix}.{key} must be a non-empty string")
        return None
    return value


def require_sha256(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> str | None:
    value = require_string(obj, key, failures, prefix)
    if value and (len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value)):
        failures.append(f"{prefix}.{key} must be a 64-character hex digest")
    return value


def as_number(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> float | None:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        failures.append(f"{prefix}.{key} must be numeric")
        return None
    return float(value)


def validate_metric_summary(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> None:
    metric = obj.get(key)
    metric_prefix = f"{prefix}.{key}"
    if not isinstance(metric, dict):
        failures.append(f"{metric_prefix} must be an object")
        return
    as_int(metric, "n", failures, metric_prefix)
    for item in ("min", "median", "mean", "max"):
        as_number(metric, item, failures, metric_prefix)


def validate_receipt(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")

    candidate = require_obj(data, "candidate", failures)
    require_string(candidate, "pipeline_id", failures, "candidate")
    require_sha256(candidate, "checkpoint_sha256", failures, "candidate")
    require_sha256(candidate, "visual_signoff_sha256", failures, "candidate")
    require_sha256(candidate, "contact_sheet_sha256", failures, "candidate")

    objective = require_obj(data, "objective_visual_signoff", failures)
    objective_passed = as_bool(objective, "all_checks_passed", failures, "objective_visual_signoff")
    check_count = as_int(objective, "check_count", failures, "objective_visual_signoff")
    require_string(objective, "verdict", failures, "objective_visual_signoff")
    if check_count is not None and check_count <= 0:
        failures.append("objective_visual_signoff.check_count must be positive")

    raw_guard = require_obj(data, "raw_domain_guard", failures)
    require_string(raw_guard, "path", failures, "raw_domain_guard")
    require_sha256(raw_guard, "sha256", failures, "raw_domain_guard")
    raw_kind = require_string(raw_guard, "kind", failures, "raw_domain_guard")
    require_string(raw_guard, "target", failures, "raw_domain_guard")
    require_string(raw_guard, "source_schema", failures, "raw_domain_guard")
    if raw_kind and raw_kind not in {"high_res_cfa_target", "legacy_clean_low"}:
        failures.append("raw_domain_guard.kind must be high_res_cfa_target or legacy_clean_low")
    raw_row_count = as_int(raw_guard, "row_count", failures, "raw_domain_guard")
    raw_passed = as_bool(raw_guard, "passed", failures, "raw_domain_guard")
    if raw_row_count is not None and raw_row_count <= 0:
        failures.append("raw_domain_guard.row_count must be positive")
    thresholds = require_obj(raw_guard, "thresholds", failures)
    for key in ("min_rmse_improvement_pct", "min_mae_improvement_pct", "min_psnr_delta_db"):
        as_number(thresholds, key, failures, "raw_domain_guard.thresholds")
    metrics = require_obj(raw_guard, "metrics", failures)
    for key in ("rmse_improvement_pct", "mae_improvement_pct", "psnr_delta_db"):
        validate_metric_summary(metrics, key, failures, "raw_domain_guard.metrics")
    source_metric_names = require_obj(raw_guard, "source_metric_names", failures)
    for key in ("rmse_improvement_pct", "mae_improvement_pct", "psnr_delta_db"):
        require_string(source_metric_names, key, failures, "raw_domain_guard.source_metric_names")
    diagnostics = data.get("diagnostics", {})
    if diagnostics is not None and not isinstance(diagnostics, dict):
        failures.append("diagnostics must be an object when present")

    reviewer = require_obj(data, "reviewer", failures)
    require_string(reviewer, "name", failures, "reviewer")
    require_string(reviewer, "role", failures, "reviewer")
    require_string(reviewer, "reviewed_at_utc", failures, "reviewer")

    review = require_obj(data, "review", failures)
    visual_checked = as_bool(review, "visual_checked", failures, "review")
    require_string(review, "contact_sheet_path", failures, "review")
    dashboards = review.get("dashboard_paths")
    if not isinstance(dashboards, list) or not dashboards or not all(isinstance(item, str) and item for item in dashboards):
        failures.append("review.dashboard_paths must be a non-empty list of strings")
    blocking_issues = review.get("blocking_issues")
    if not isinstance(blocking_issues, list) or not all(isinstance(item, str) for item in blocking_issues):
        failures.append("review.blocking_issues must be a list of strings")

    verdict = require_obj(data, "verdict", failures)
    production_ready = as_bool(verdict, "production_ready", failures, "verdict")
    no_blocking_visual_issues = as_bool(verdict, "no_blocking_visual_issues", failures, "verdict")
    accepted_role = require_string(verdict, "accepted_role", failures, "verdict")
    if accepted_role and accepted_role not in {"production", "review_only", "blocked"}:
        failures.append("verdict.accepted_role must be production, review_only, or blocked")

    has_blocking_issues = bool(blocking_issues) if isinstance(blocking_issues, list) else True
    if production_ready:
        if accepted_role != "production":
            failures.append("production-ready signoff must set verdict.accepted_role=production")
        for label, value in (
            ("objective_visual_signoff.all_checks_passed", objective_passed),
            ("review.visual_checked", visual_checked),
            ("verdict.no_blocking_visual_issues", no_blocking_visual_issues),
        ):
            if value is not True:
                failures.append(f"production-ready signoff requires {label}=true")
        if raw_passed is not True:
            failures.append("production-ready signoff requires raw_domain_guard.passed=true")
        if has_blocking_issues:
            failures.append("production-ready signoff must have no review.blocking_issues")
        if data.get("blocker") is not None:
            failures.append("production-ready signoff must not include blocker")
    else:
        blocker = data.get("blocker")
        if not isinstance(blocker, dict) or not blocker.get("cause"):
            failures.append("non-production signoff must include blocker.cause")

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("receipt", type=Path, help="4K cleanup signoff receipt JSON")
    args = ap.parse_args()

    data = json.loads(args.receipt.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("receipt must be a JSON object", file=sys.stderr)
        return 1
    failures = validate_receipt(data)
    if failures:
        print("Mission 1 4K cleanup signoff receipt failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1
    print("Mission 1 4K cleanup signoff receipt OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
