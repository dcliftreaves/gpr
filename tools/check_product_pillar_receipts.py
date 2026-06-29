#!/usr/bin/env python3
"""Validate high-level product-pillar planning receipts.

These schemas are intentionally small. They do not replace the large visual
dashboards or release manifests; they guard the metadata needed before a large
artifact can be promoted as product evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


NOISE_SCHEMA = "gpr.camera_noise_calibration.v1"
STILL_SR_SCHEMA = "gpr.premium_still_sr_gate.v1"
PSF_SCHEMA = "gpr.bayer_resize_psf_receipt.v1"

NORMAL_BAYER_PHASES = {"RGGB", "GBRG", "BGGR", "GRBG"}
NOISE_SOURCE_KINDS = {"darkframes", "frame_stack", "dng_noise_profile", "flat_dark_pair"}


def require_obj(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> dict[str, Any]:
    value = obj.get(key)
    label = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return {}
    return value


def require_list(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> list[Any]:
    value = obj.get(key)
    label = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, list) or not value:
        failures.append(f"{label} must be a non-empty list")
        return []
    return value


def require_string(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> str | None:
    value = obj.get(key)
    label = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, str) or not value:
        failures.append(f"{label} must be a non-empty string")
        return None
    return value


def require_sha256(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> str | None:
    value = require_string(obj, key, failures, prefix)
    label = f"{prefix}.{key}" if prefix else key
    if value and (len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value)):
        failures.append(f"{label} must be a 64-character hex digest")
    return value


def require_bool(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> bool | None:
    value = obj.get(key)
    label = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, bool):
        failures.append(f"{label} must be boolean")
        return None
    return value


def require_int(
    obj: dict[str, Any],
    key: str,
    failures: list[str],
    prefix: str,
    *,
    minimum: int | None = None,
) -> int | None:
    value = obj.get(key)
    label = f"{prefix}.{key}" if prefix else key
    if isinstance(value, bool) or not isinstance(value, int):
        failures.append(f"{label} must be integer")
        return None
    if minimum is not None and value < minimum:
        failures.append(f"{label} must be >= {minimum}")
    return value


def require_number(
    obj: dict[str, Any],
    key: str,
    failures: list[str],
    prefix: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    value = obj.get(key)
    label = f"{prefix}.{key}" if prefix else key
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        failures.append(f"{label} must be numeric")
        return None
    result = float(value)
    if minimum is not None and result < minimum:
        failures.append(f"{label} must be >= {minimum}")
    if maximum is not None and result > maximum:
        failures.append(f"{label} must be <= {maximum}")
    return result


def validate_artifact_ref(obj: dict[str, Any], failures: list[str], prefix: str) -> None:
    require_string(obj, "path", failures, prefix)
    require_sha256(obj, "sha256", failures, prefix)


def validate_noise_calibration(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != NOISE_SCHEMA:
        failures.append(f"schema must be {NOISE_SCHEMA}")

    camera = require_obj(data, "camera", failures, "")
    require_string(camera, "make", failures, "camera")
    require_string(camera, "model", failures, "camera")
    require_int(camera, "width", failures, "camera", minimum=2)
    require_int(camera, "height", failures, "camera", minimum=2)
    require_int(camera, "bit_depth", failures, "camera", minimum=8)
    cfa = require_string(camera, "cfa_phase", failures, "camera")
    if cfa and cfa not in NORMAL_BAYER_PHASES:
        failures.append("camera.cfa_phase must be one of RGGB, GBRG, BGGR, GRBG")
    require_number(camera, "black_level", failures, "camera", minimum=0)
    require_number(camera, "white_level", failures, "camera", minimum=1)

    calibrations = require_list(data, "calibrations", failures, "")
    usable_count = 0
    for idx, item in enumerate(calibrations):
        prefix = f"calibrations[{idx}]"
        if not isinstance(item, dict):
            failures.append(f"{prefix} must be an object")
            continue
        require_int(item, "iso", failures, prefix, minimum=1)
        require_string(item, "calibration_method", failures, prefix)
        source_kind = require_string(item, "source_kind", failures, prefix)
        if source_kind and source_kind not in NOISE_SOURCE_KINDS:
            failures.append(f"{prefix}.source_kind must be one of {sorted(NOISE_SOURCE_KINDS)}")
        require_int(item, "sample_count", failures, prefix, minimum=1)
        validate_artifact_ref(require_obj(item, "source", failures, prefix), failures, f"{prefix}.source")
        planes = require_obj(item, "per_plane", failures, prefix)
        for plane in ("r", "g1", "b", "g2"):
            metrics = require_obj(planes, plane, failures, f"{prefix}.per_plane")
            require_number(metrics, "noise_profile_scale", failures, f"{prefix}.per_plane.{plane}", minimum=0)
            require_number(metrics, "noise_profile_offset", failures, f"{prefix}.per_plane.{plane}", minimum=0)
            require_number(metrics, "mean_black", failures, f"{prefix}.per_plane.{plane}", minimum=0)
            require_number(metrics, "sigma_black", failures, f"{prefix}.per_plane.{plane}", minimum=0)
        audit = require_obj(item, "noise_signal_audit", failures, prefix)
        separates = require_bool(audit, "separates_noise_from_signal", failures, f"{prefix}.noise_signal_audit")
        require_string(audit, "method", failures, f"{prefix}.noise_signal_audit")
        require_string(audit, "evidence", failures, f"{prefix}.noise_signal_audit")
        usable = require_bool(item, "usable_for_training_targets", failures, prefix)
        if usable:
            usable_count += 1
            if separates is not True:
                failures.append(f"{prefix} cannot be usable_for_training_targets without a passing noise/signal audit")
            if item.get("sample_count", 0) < 4 and source_kind in {"darkframes", "frame_stack", "flat_dark_pair"}:
                failures.append(f"{prefix} needs at least 4 frames before training targets can use it")
            if source_kind == "dng_noise_profile":
                failures.append(f"{prefix} cannot mark a metadata-only DNG NoiseProfile as usable_for_training_targets")

    if require_bool(data, "production_ready", failures, "") is True and usable_count == 0:
        failures.append("production_ready noise calibration requires at least one usable calibration")
    return failures


def validate_still_sr_gate(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != STILL_SR_SCHEMA:
        failures.append(f"schema must be {STILL_SR_SCHEMA}")

    candidate = require_obj(data, "candidate", failures, "")
    require_string(candidate, "pipeline_id", failures, "candidate")
    require_sha256(candidate, "checkpoint_sha256", failures, "candidate")
    require_string(candidate, "target_role", failures, "candidate")

    fixtures = require_obj(data, "fixture_summary", failures, "")
    require_int(fixtures, "camera_count", failures, "fixture_summary", minimum=1)
    require_int(fixtures, "fifty_mp_or_larger_count", failures, "fixture_summary", minimum=0)
    require_int(fixtures, "hundred_mp_or_larger_count", failures, "fixture_summary", minimum=0)
    phases = fixtures.get("cfa_phases")
    if not isinstance(phases, list) or not phases:
        failures.append("fixture_summary.cfa_phases must be a non-empty list")
    elif any(phase not in NORMAL_BAYER_PHASES for phase in phases):
        failures.append("fixture_summary.cfa_phases must contain only normal Bayer phases")

    outputs = require_obj(data, "outputs", failures, "")
    for key in ("editable_dng", "editable_gpr", "review_tiff_or_prores", "dashboard"):
        validate_artifact_ref(require_obj(outputs, key, failures, "outputs"), failures, f"outputs.{key}")

    comparison = require_obj(data, "baseline_comparison", failures, "")
    passed_gate = require_bool(comparison, "passed_gate", failures, "baseline_comparison")
    require_number(comparison, "worst_lpips", failures, "baseline_comparison", minimum=0)
    require_number(comparison, "worst_delta_e2000", failures, "baseline_comparison", minimum=0)
    require_number(comparison, "min_raw_psnr_delta_db", failures, "baseline_comparison")
    require_number(comparison, "editor_latitude_score_delta", failures, "baseline_comparison")

    noise = require_obj(data, "noise_policy", failures, "")
    require_string(noise, "mode", failures, "noise_policy")
    audit_passed = require_bool(noise, "raw_noise_signal_audit_passed", failures, "noise_policy")

    if require_bool(data, "production_ready", failures, "") is True:
        if passed_gate is not True:
            failures.append("production_ready still-SR requires baseline_comparison.passed_gate=true")
        if audit_passed is not True:
            failures.append("production_ready still-SR requires noise_policy.raw_noise_signal_audit_passed=true")
        if fixtures.get("fifty_mp_or_larger_count", 0) <= 0:
            failures.append("production_ready still-SR requires 50 MP-class fixtures")
        if fixtures.get("hundred_mp_or_larger_count", 0) <= 0:
            failures.append("production_ready still-SR requires 100 MP-class fixtures")
    return failures


def validate_psf_receipt(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != PSF_SCHEMA:
        failures.append(f"schema must be {PSF_SCHEMA}")

    model = require_obj(data, "psf_model", failures, "")
    require_string(model, "model_id", failures, "psf_model")
    require_string(model, "estimation_method", failures, "psf_model")
    require_number(model, "kernel_width_px", failures, "psf_model", minimum=0)
    require_number(model, "kernel_height_px", failures, "psf_model", minimum=0)
    require_number(model, "fit_rmse_px", failures, "psf_model", minimum=0)

    dataset = require_obj(data, "dataset", failures, "")
    require_int(dataset, "pair_count", failures, "dataset", minimum=1)
    require_int(dataset, "sharp_edge_count", failures, "dataset", minimum=0)
    require_int(dataset, "texture_field_count", failures, "dataset", minimum=0)
    phases = dataset.get("cfa_phases")
    if not isinstance(phases, list) or not phases:
        failures.append("dataset.cfa_phases must be a non-empty list")
    elif any(phase not in NORMAL_BAYER_PHASES for phase in phases):
        failures.append("dataset.cfa_phases must contain only normal Bayer phases")

    gates = require_obj(data, "gate_results", failures, "")
    mission_passed = require_bool(gates, "mission42_passed", failures, "gate_results")
    z8_passed = require_bool(gates, "z8_all24_passed", failures, "gate_results")
    require_number(gates, "min_raw_psnr_delta_db", failures, "gate_results")
    require_number(gates, "min_gradient_mae_improvement_pct", failures, "gate_results")

    receipts = require_obj(data, "receipts", failures, "")
    for key in ("gvid", "editable_dng_or_gpr", "prores", "timing_memory"):
        validate_artifact_ref(require_obj(receipts, key, failures, "receipts"), failures, f"receipts.{key}")

    if require_bool(data, "production_ready", failures, "") is True:
        if mission_passed is not True:
            failures.append("production_ready PSF receipt requires gate_results.mission42_passed=true")
        if z8_passed is not True:
            failures.append("production_ready PSF receipt requires gate_results.z8_all24_passed=true")
        if dataset.get("sharp_edge_count", 0) <= 0 or dataset.get("texture_field_count", 0) <= 0:
            failures.append("production_ready PSF receipt requires sharp-edge and texture-field evidence")
    return failures


def validate_receipt(data: dict[str, Any]) -> list[str]:
    schema = data.get("schema")
    if schema == NOISE_SCHEMA:
        return validate_noise_calibration(data)
    if schema == STILL_SR_SCHEMA:
        return validate_still_sr_gate(data)
    if schema == PSF_SCHEMA:
        return validate_psf_receipt(data)
    return [f"unsupported schema: {schema!r}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("receipt", type=Path, nargs="+", help="receipt JSON file(s)")
    args = ap.parse_args()

    failed = False
    for path in args.receipt:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print(f"{path}: receipt must be a JSON object", file=sys.stderr)
            failed = True
            continue
        failures = validate_receipt(data)
        if failures:
            print(f"{path}: product-pillar receipt failed:", file=sys.stderr)
            for failure in failures:
                print(f" - {failure}", file=sys.stderr)
            failed = True
        else:
            print(f"{path}: product-pillar receipt OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
