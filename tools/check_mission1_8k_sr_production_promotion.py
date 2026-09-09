#!/usr/bin/env python3
"""Validate a Mission 1 8K SR production-promotion receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_8k_sr_production_promotion.v1"
PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1"
    "+demosaic=sips_via_gpr_tools"
)


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


def require_bool(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> bool | None:
    value = obj.get(key)
    if not isinstance(value, bool):
        failures.append(f"{prefix}.{key} must be boolean")
        return None
    return value


def require_sha256(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> str | None:
    value = require_string(obj, key, failures, prefix)
    if value and (len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value)):
        failures.append(f"{prefix}.{key} must be a 64-character hex digest")
    return value


def validate_receipt(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")

    candidate = require_obj(data, "candidate", failures)
    pipeline_id = require_string(candidate, "pipeline_id", failures, "candidate")
    if pipeline_id and pipeline_id != PIPELINE_ID:
        failures.append(f"candidate.pipeline_id must be {PIPELINE_ID}")

    registry = require_obj(data, "registry", failures)
    scope = require_string(registry, "production_scope", failures, "registry")
    if scope and scope not in {"offline_review_only", "offline_production", "production"}:
        failures.append("registry.production_scope must be offline_review_only, offline_production, or production")
    require_sha256(registry, "registry_sha256", failures, "registry")

    evidence = require_obj(data, "evidence", failures)
    for key in (
        "runtime_receipt_sha256",
        "gvid_packaging_receipt_sha256",
        "prores_receipt_sha256",
        "quality_summary_sha256",
    ):
        require_sha256(evidence, key, failures, "evidence")
    if "editable_packaging_receipt_sha256" in evidence:
        require_sha256(evidence, "editable_packaging_receipt_sha256", failures, "evidence")
    if "metadata_transplant_audit_sha256" in evidence:
        require_sha256(evidence, "metadata_transplant_audit_sha256", failures, "evidence")
    if "visual_review_package_sha256" in evidence:
        require_sha256(evidence, "visual_review_package_sha256", failures, "evidence")
    for key in (
        "visual_review_complete",
        "editable_packaging_proven",
        "metadata_transplant_proven",
    ):
        require_bool(evidence, key, failures, "evidence")

    verdict = require_obj(data, "verdict", failures)
    production_ready = require_bool(verdict, "production_ready", failures, "verdict")
    accepted_role = require_string(verdict, "accepted_role", failures, "verdict")
    if accepted_role and accepted_role not in {"production", "blocked"}:
        failures.append("verdict.accepted_role must be production or blocked")
    blocking_issues = verdict.get("blocking_issues")
    if not isinstance(blocking_issues, list) or any(not isinstance(item, str) for item in blocking_issues):
        failures.append("verdict.blocking_issues must be a list of strings")

    evidence_bools = {
        "visual_review_complete": evidence.get("visual_review_complete"),
        "editable_packaging_proven": evidence.get("editable_packaging_proven"),
        "metadata_transplant_proven": evidence.get("metadata_transplant_proven"),
    }
    if production_ready:
        if accepted_role != "production":
            failures.append("production-ready receipt must set verdict.accepted_role=production")
        if scope not in {"offline_production", "production"}:
            failures.append("production-ready receipt requires promoted registry.production_scope")
        if any(value is not True for value in evidence_bools.values()):
            failures.append("production-ready receipt requires all evidence booleans true")
        if evidence_bools["visual_review_complete"] is True and not evidence.get("visual_review_package_sha256"):
            failures.append("production-ready receipt requires evidence.visual_review_package_sha256")
        if evidence_bools["editable_packaging_proven"] is True and not evidence.get("editable_packaging_receipt_sha256"):
            failures.append("production-ready receipt requires evidence.editable_packaging_receipt_sha256")
        if evidence_bools["metadata_transplant_proven"] is True and not evidence.get("metadata_transplant_audit_sha256"):
            failures.append("production-ready receipt requires evidence.metadata_transplant_audit_sha256")
        if blocking_issues:
            failures.append("production-ready receipt must have no verdict.blocking_issues")
        if data.get("blocker") is not None:
            failures.append("production-ready receipt must not include blocker")
    else:
        if accepted_role != "blocked":
            failures.append("non-production receipt must set verdict.accepted_role=blocked")
        if not blocking_issues:
            failures.append("non-production receipt must list verdict.blocking_issues")
        blocker = data.get("blocker")
        if not isinstance(blocker, dict) or not blocker.get("cause"):
            failures.append("non-production receipt must include blocker.cause")

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("receipt", type=Path, help="8K SR production-promotion receipt JSON")
    args = ap.parse_args()

    data = json.loads(args.receipt.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("receipt must be a JSON object", file=sys.stderr)
        return 1
    failures = validate_receipt(data)
    if failures:
        print("Mission 1 8K SR production-promotion receipt failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1
    print("Mission 1 8K SR production-promotion receipt OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
