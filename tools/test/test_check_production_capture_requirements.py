#!/usr/bin/env python3
"""Regression-test the production capture requirements guard."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/test/check_production_capture_requirements.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_production_capture_requirements_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_failure(module, req_path: Path, payload: dict, needle: str) -> None:
    req_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    failures = module.validate()
    if not any(needle in failure for failure in failures):
        raise AssertionError(f"expected failure containing {needle!r}, got {failures!r}")


def main() -> int:
    module = import_tool()
    source = json.loads((ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json").read_text(encoding="utf-8"))
    source_doc = (ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        req_path = tmp / "PRODUCTION_CAPTURE_REQUIREMENTS.json"
        doc_path = tmp / "PRODUCTION_CAPTURE_REQUIREMENTS.md"
        req_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
        doc_path.write_text(source_doc, encoding="utf-8")

        module.REQ_PATH = req_path
        module.DOC_PATH = doc_path

        failures = module.validate()
        if failures:
            print(f"valid capture requirements unexpectedly failed: {failures}", file=sys.stderr)
            return 1

        bad_schema = copy.deepcopy(source)
        bad_schema["schema"] = "wrong"
        expect_failure(module, req_path, bad_schema, "schema")

        missing_id = copy.deepcopy(source)
        missing_id["requirements"] = [
            row for row in missing_id["requirements"] if row["id"] != "premium_still_sr_promotion_receipts"
        ]
        expect_failure(module, req_path, missing_id, "premium_still_sr_promotion_receipts")

        bad_optional_psf = copy.deepcopy(source)
        for row in bad_optional_psf["requirements"]:
            if row["id"] == "controlled_mission1_psf_pairs":
                row["priority"] = "required"
        expect_failure(module, req_path, bad_optional_psf, "priority must be research_optional")

        bad_darkframes = copy.deepcopy(source)
        for row in bad_darkframes["requirements"]:
            if row["id"] == "mission1_darkframe_stack":
                row["minimum_count"] = 3
        expect_failure(module, req_path, bad_darkframes, "minimum_count >= 4")

        bad_pillar = copy.deepcopy(source)
        for row in bad_pillar["requirements"]:
            if row["id"] == "premium_still_sr_promotion_receipts":
                row["pillar"] = "raw_stills"
        expect_failure(module, req_path, bad_pillar, "premium_still_sr")

        bad_still_sr_smoke_gates = copy.deepcopy(source)
        for row in bad_still_sr_smoke_gates["requirements"]:
            if row["id"] == "premium_still_sr_promotion_receipts":
                row["required_evidence"] = [
                    item for item in row["required_evidence"] if "smoke_gate_commands" not in item
                ]
                row["acceptance"] = [
                    item for item in row["acceptance"] if "smoke_gate_commands" not in item
                ]
        expect_failure(module, req_path, bad_still_sr_smoke_gates, "X2D and Z8 smoke_gate_commands")

        bad_still_sr_smoke_acceptance = copy.deepcopy(source)
        for row in bad_still_sr_smoke_acceptance["requirements"]:
            if row["id"] == "premium_still_sr_promotion_receipts":
                row["required_evidence"] = [
                    item for item in row["required_evidence"] if "smoke_gate_acceptance" not in item
                ]
                row["acceptance"] = [
                    item for item in row["acceptance"] if "smoke_gate_acceptance" not in item
                ]
        expect_failure(module, req_path, bad_still_sr_smoke_acceptance, "smoke_gate_acceptance")

        req_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
        doc_path.write_text(source_doc.replace("mission1_camera_role_receipts", "camera_receipts"), encoding="utf-8")
        failures = module.validate()
        if not any("mission1_camera_role_receipts" in failure for failure in failures):
            print(f"missing doc token did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

    print("test_check_production_capture_requirements: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
