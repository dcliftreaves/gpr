#!/usr/bin/env python3
"""Regression-test the product burn-down contract guard."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/test/check_product_burndown_contract.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_product_burndown_contract_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_failure(module, payload: dict, needle: str) -> None:
    failures = module.validate_burndown(payload)
    if not any(needle in failure for failure in failures):
        raise AssertionError(f"expected failure containing {needle!r}, got {failures!r}")


def main() -> int:
    module = import_tool()
    data = module.build_burndown(module.DEFAULT_EXTERNAL_ROOT)
    failures = module.validate_burndown(data)
    if failures:
        print(f"current burn-down unexpectedly failed: {failures}", file=sys.stderr)
        return 1

    bad_ready = copy.deepcopy(data)
    bad_ready["production_ready"] = True
    expect_failure(module, bad_ready, "production_ready=false")

    bad_camera = copy.deepcopy(data)
    bad_camera["summary"]["camera_required_action_count"] = 0
    expect_failure(module, bad_camera, "camera-required")

    bad_stills = copy.deepcopy(data)
    bad_stills["pillars"][0]["burn_down_actions"][0]["evidence_required"] = [
        "updated Bayer phase fixture discovery dashboard"
    ]
    bad_stills["pillars"][0]["burn_down_actions"][0]["completion_gate"] = "Fixture discovery dashboard exists."
    expect_failure(module, bad_stills, "GRBG")

    bad_psf = copy.deepcopy(data)
    bad_psf["pillars"][3]["burn_down_actions"] = [
        row for row in bad_psf["pillars"][3]["burn_down_actions"]
        if "PSF-conditioned" not in row["title"]
    ]
    expect_failure(module, bad_psf, "PSF-conditioned")

    print("test_check_product_burndown_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
