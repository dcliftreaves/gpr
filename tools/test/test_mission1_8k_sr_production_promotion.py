#!/usr/bin/env python3
"""Tests for Mission 1 8K SR production-promotion receipt validation."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_mission1_8k_sr_production_promotion.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("check_mission1_8k_sr_production_promotion", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_receipt(module):
    return {
        "schema": module.SCHEMA,
        "candidate": {"pipeline_id": module.PIPELINE_ID},
        "registry": {"production_scope": "offline_production", "registry_sha256": "a" * 64},
        "evidence": {
            "runtime_receipt_sha256": "b" * 64,
            "gvid_packaging_receipt_sha256": "c" * 64,
            "prores_receipt_sha256": "d" * 64,
            "quality_summary_sha256": "e" * 64,
            "visual_review_package_sha256": "0" * 64,
            "editable_packaging_receipt_sha256": "f" * 64,
            "metadata_transplant_audit_sha256": "1" * 64,
            "visual_review_complete": True,
            "editable_packaging_proven": True,
            "metadata_transplant_proven": True,
        },
        "verdict": {"production_ready": True, "accepted_role": "production", "blocking_issues": []},
    }


def test_valid_receipt_passes() -> None:
    module = load_tool()
    assert module.validate_receipt(valid_receipt(module)) == []


def test_review_only_scope_fails() -> None:
    module = load_tool()
    receipt = valid_receipt(module)
    receipt["registry"]["production_scope"] = "offline_review_only"
    failures = module.validate_receipt(receipt)
    assert any("promoted registry.production_scope" in failure for failure in failures)


def test_blocking_issue_fails() -> None:
    module = load_tool()
    receipt = valid_receipt(module)
    receipt["verdict"]["blocking_issues"] = ["visual review missing"]
    failures = module.validate_receipt(receipt)
    assert any("blocking_issues" in failure for failure in failures)


def test_blocked_receipt_passes() -> None:
    module = load_tool()
    receipt = valid_receipt(module)
    receipt["registry"]["production_scope"] = "offline_review_only"
    receipt["evidence"]["visual_review_complete"] = False
    receipt["evidence"]["editable_packaging_proven"] = False
    receipt["evidence"]["metadata_transplant_proven"] = False
    receipt["verdict"] = {
        "production_ready": False,
        "accepted_role": "blocked",
        "blocking_issues": [
            "registry_scope_not_promoted",
            "visual_review_incomplete",
            "editable_packaging_not_proven",
            "metadata_transplant_not_proven",
        ],
    }
    receipt["blocker"] = {"cause": "registry_scope_not_promoted"}
    assert module.validate_receipt(receipt) == []


if __name__ == "__main__":
    test_valid_receipt_passes()
    test_review_only_scope_fails()
    test_blocking_issue_fails()
    test_blocked_receipt_passes()
    print("test_mission1_8k_sr_production_promotion: PASS")
