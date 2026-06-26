#!/usr/bin/env python3
"""Validate the Mission 1 camera-side closure package."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_camera_closure_package.v1"
EXPECTED_BLOCKERS = {
    "Mission 1 firmware/camera-side handoff receipt is still required.",
    "Mission 1 camera preview UI receipt is still required.",
}
CAMERA_RAW_SOURCE_KINDS = {"sensor_dma_capture", "camera_ring_buffer"}
STANDIN_TOKENS = (
    "stand-in",
    "file-backed",
    "bench_fused",
    "page-cache",
    "filesystem",
    "off-camera",
    "pi 5",
    "pi5",
)


def require_obj(root: dict[str, Any], key: str, failures: list[str]) -> dict[str, Any]:
    value = root.get(key)
    if not isinstance(value, dict):
        failures.append(f"{key} must be an object")
        return {}
    return value


def require_sha(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> None:
    value = obj.get(key)
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
        failures.append(f"{prefix}.{key} must be a sha256 hex digest")


def receipt_by_schema(receipts: list[Any], schema: str) -> dict[str, Any] | None:
    for receipt in receipts:
        if isinstance(receipt, dict) and receipt.get("schema") == schema:
            return receipt
    return None


def validate_camera_preflight_inputs(preflight: dict[str, Any], failures: list[str]) -> None:
    inputs = preflight.get("inputs")
    if not isinstance(inputs, dict):
        failures.append("target_preflight.inputs must be an object for camera-role preflight")
        return
    for key in ("frame_source", "write_path", "storage_medium", "display_surface", "presentation_path"):
        value = inputs.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"target_preflight.inputs.{key} must be a non-empty string")
            continue
        lowered = value.lower()
        for token in STANDIN_TOKENS:
            if token in lowered:
                failures.append(f"target_preflight.inputs.{key} contains stand-in token {token!r}")
                break


def validate_production_receipts(receipts: list[Any], failures: list[str]) -> None:
    handoff = receipt_by_schema(receipts, "gpr_labs_camera_handoff_receipt.v1")
    if handoff is None:
        failures.append("production-ready package requires camera_handoff_receipt summary")
    else:
        require_sha(handoff, "sha256", failures, "camera_handoff_receipt")
        target = handoff.get("target") if isinstance(handoff.get("target"), dict) else {}
        verdict = handoff.get("verdict") if isinstance(handoff.get("verdict"), dict) else {}
        integration = handoff.get("integration") if isinstance(handoff.get("integration"), dict) else {}
        sensor_dma = integration.get("sensor_dma_handoff") if isinstance(integration.get("sensor_dma_handoff"), dict) else {}
        storage = integration.get("storage_handoff") if isinstance(integration.get("storage_handoff"), dict) else {}
        if handoff.get("exists") is not True:
            failures.append("production-ready package requires camera_handoff_receipt to exist")
        if target.get("role") != "camera":
            failures.append("production-ready package requires camera_handoff target.role=camera")
        if verdict.get("firmware_ready") is not True:
            failures.append("production-ready package requires camera_handoff verdict.firmware_ready=true")
        if integration.get("raw_source_kind") not in CAMERA_RAW_SOURCE_KINDS:
            failures.append("production-ready package requires camera_handoff raw_source_kind=sensor_dma_capture or camera_ring_buffer")
        if sensor_dma.get("executed") is not True:
            failures.append("production-ready package requires camera_handoff sensor_dma_handoff.executed=true")
        if storage.get("executed") is not True:
            failures.append("production-ready package requires camera_handoff storage_handoff.executed=true")

    preview = receipt_by_schema(receipts, "gpr_labs_preview_ui_receipt.v1")
    if preview is None:
        failures.append("production-ready package requires preview_ui_receipt summary")
    else:
        require_sha(preview, "sha256", failures, "preview_ui_receipt")
        target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
        verdict = preview.get("verdict") if isinstance(preview.get("verdict"), dict) else {}
        integration = preview.get("integration") if isinstance(preview.get("integration"), dict) else {}
        if preview.get("exists") is not True:
            failures.append("production-ready package requires preview_ui_receipt to exist")
        if target.get("role") != "camera":
            failures.append("production-ready package requires preview_ui target.role=camera")
        if verdict.get("ui_ready") is not True:
            failures.append("production-ready package requires preview_ui verdict.ui_ready=true")
        if integration.get("ui_path_executed") is not True:
            failures.append("production-ready package requires preview_ui integration.ui_path_executed=true")


def validate(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")
    readiness = require_obj(data, "readiness", failures)
    closure = require_obj(data, "closure_plan", failures)
    verdict = require_obj(data, "verdict", failures)
    require_sha(readiness, "sha256", failures, "readiness")
    require_sha(closure, "sha256", failures, "closure_plan")

    blockers = data.get("remaining_blockers")
    if not isinstance(blockers, list):
        failures.append("remaining_blockers must be a list")
        blockers = []
    blocker_labels = {row.get("blocker") for row in blockers if isinstance(row, dict)}
    if verdict.get("production_ready") is True:
        if blockers:
            failures.append("production-ready closure package must not list blockers")
    else:
        if blocker_labels != EXPECTED_BLOCKERS:
            failures.append(f"remaining blockers must be the two camera-side blockers, got {sorted(str(x) for x in blocker_labels)}")
        if verdict.get("remaining_blocker_count") != len(blockers):
            failures.append("verdict.remaining_blocker_count must match remaining_blockers length")

    receipts = data.get("current_receipts")
    if not isinstance(receipts, list):
        failures.append("current_receipts must be a list")
        receipts = []
    elif verdict.get("production_ready") is True:
        validate_production_receipts(receipts, failures)
    elif len(receipts) != len(blockers):
        failures.append("current_receipts must match remaining blockers")

    if verdict.get("production_ready") is not True:
        for idx, receipt in enumerate(receipts):
            if not isinstance(receipt, dict):
                failures.append(f"current_receipts[{idx}] must be an object")
                continue
            receipt_exists = receipt.get("exists") is True
            if verdict.get("production_ready") is True and not receipt_exists:
                failures.append(f"production-ready package requires current_receipts[{idx}] to exist")
            if "sha256" in receipt:
                require_sha(receipt, "sha256", failures, f"current_receipts[{idx}]")
            if not receipt_exists:
                continue
            target = receipt.get("target")
            if not isinstance(target, dict) or target.get("role") != "stand-in":
                failures.append(f"current_receipts[{idx}] must currently be a stand-in receipt")
            blocker = receipt.get("blocker")
            if not isinstance(blocker, dict) or not blocker.get("cause"):
                failures.append(f"current_receipts[{idx}] must include a blocker cause")

    audits = data.get("acceptance_audit")
    if not isinstance(audits, list) or len(audits) != len(blockers):
        failures.append("acceptance_audit must match remaining blockers")
    else:
        for idx, audit in enumerate(audits):
            if not isinstance(audit, dict):
                failures.append(f"acceptance_audit[{idx}] must be an object")
                continue
            checks = audit.get("checks")
            if not isinstance(checks, list):
                failures.append(f"acceptance_audit[{idx}].checks must be a list")
                continue
            if audit.get("check_count") != len(checks):
                failures.append(f"acceptance_audit[{idx}].check_count must match checks length")
            satisfied = sum(1 for check in checks if isinstance(check, dict) and check.get("passed") is True)
            if audit.get("satisfied_count") != satisfied:
                failures.append(f"acceptance_audit[{idx}].satisfied_count must match passed checks")
            if verdict.get("production_ready") is True and audit.get("passed") is not True:
                failures.append(f"production-ready package requires acceptance_audit[{idx}].passed=true")

    runbook = require_obj(data, "runbook", failures)
    for key in ("camera_handoff_validator", "preview_ui_validator", "final_gate"):
        if not isinstance(runbook.get(key), str) or not runbook[key]:
            failures.append(f"runbook.{key} must be a non-empty string")
    target_access = require_obj(data, "target_access", failures)
    if not isinstance(target_access.get("requested"), bool):
        failures.append("target_access.requested must be boolean")
    if target_access.get("requested") is True:
        if not isinstance(target_access.get("host"), str) or not target_access["host"]:
            failures.append("target_access.host must be a non-empty string when requested")
        if not isinstance(target_access.get("returncode"), int):
            failures.append("target_access.returncode must be integer when requested")
        if not isinstance(target_access.get("stdout"), list):
            failures.append("target_access.stdout must be a list when requested")
        if not isinstance(target_access.get("stderr"), list):
            failures.append("target_access.stderr must be a list when requested")
    preflight = require_obj(data, "target_preflight", failures)
    if not isinstance(preflight.get("exists"), bool):
        failures.append("target_preflight.exists must be boolean")
    if preflight.get("exists") is True:
        require_sha(preflight, "sha256", failures, "target_preflight")
        if preflight.get("schema") != "gpr.mission1_camera_target_preflight.v1":
            failures.append("target_preflight.schema must be gpr.mission1_camera_target_preflight.v1")
        preflight_target = preflight.get("target")
        if not isinstance(preflight_target, dict):
            failures.append("target_preflight.target must be an object when receipt exists")
            preflight_target = {}
        if preflight_target.get("role") == "camera":
            validate_camera_preflight_inputs(preflight, failures)
        preflight_verdict = preflight.get("verdict")
        if not isinstance(preflight_verdict, dict):
            failures.append("target_preflight.verdict must be an object when receipt exists")
        else:
            for key in ("target_preflight_ready", "camera_closure_possible"):
                if not isinstance(preflight_verdict.get(key), bool):
                    failures.append(f"target_preflight.verdict.{key} must be boolean")
            if verdict.get("production_ready") is True:
                if preflight_target.get("role") != "camera":
                    failures.append("production-ready package requires target_preflight.target.role=camera")
                if preflight_verdict.get("target_preflight_ready") is not True:
                    failures.append("production-ready package requires target_preflight_ready=true")
                if preflight_verdict.get("camera_closure_possible") is not True:
                    failures.append("production-ready package requires camera_closure_possible=true")
            else:
                if preflight_target.get("role") == "camera" and preflight_verdict.get("camera_closure_possible") is True:
                    failures.append("non-production closure package cannot include camera-closure-capable preflight")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("package", type=Path)
    args = ap.parse_args()
    data = json.loads(args.package.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("package must be a JSON object", file=sys.stderr)
        return 1
    failures = validate(data)
    if failures:
        print("Mission 1 camera closure package failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1
    print("Mission 1 camera closure package OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
