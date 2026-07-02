#!/usr/bin/env python3
"""Validate a submitted production-capture evidence manifest.

The committed requirements list says what samples and receipts are still
needed. This checker validates a concrete submission manifest against those
requirements without needing private raw files in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "docs" / "PRODUCTION_CAPTURE_REQUIREMENTS.json"
SCHEMA = "gpr.production_capture_submission_audit.v1"
SUBMISSION_SCHEMA = "gpr.production_capture_submission.v1"
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")

REQUIRED_CAMERA_ROLE_RECEIPTS = {
    "target_preflight_receipt",
    "labs_target_bench",
    "camera_handoff_receipt",
    "preview_decode_receipt",
    "preview_ui_receipt",
    "mission1_camera_closure_run",
}
PSF_HIGH_DIMS = (8192, 6144)
PSF_LOW_DIMS = (4096, 3072)
PSF_HIGH_BYTES = PSF_HIGH_DIMS[0] * PSF_HIGH_DIMS[1] * 2
PSF_LOW_BYTES = PSF_LOW_DIMS[0] * PSF_LOW_DIMS[1] * 2
PSF_FIXED_SETTING_FIELDS = [
    "iso",
    "exposure",
    "white_balance",
    "lens_mode",
    "stabilization",
    "sharpening",
    "lens_correction",
]
PREMIUM_REQUIRED_RUNTIME_INPUTS = {"candidate_raw", "camera_metadata"}
PREMIUM_REQUIRED_SMOKE_HOLDOUTS = {"x2d", "z8"}
PREMIUM_FORBIDDEN_RUNTIME_INPUTS = {
    "REF",
    "reference",
    "reference_image",
    "source_raw",
    "source_rgb",
    "source_hf",
    "JPEG_target",
    "jpeg_target",
}
CONFIRMED_DARKFRAME_SOURCE_KINDS = {
    "confirmed_darkframes",
    "flat_dark_pair",
    "equivalent_no_scene_stack",
}
DARKFRAME_SOURCE_PROVENANCE_AUDIT_SCHEMA = "gpr.darkframe_source_provenance_audit.v1"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("submission", type=Path, help="gpr.production_capture_submission.v1 manifest")
    ap.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--html-out", type=Path)
    ap.add_argument(
        "--require-existing-files",
        action="store_true",
        help="Also require every path/hash pair in the submission to exist locally and match its SHA-256.",
    )
    ap.add_argument(
        "--path-root",
        type=Path,
        help="Resolve relative evidence paths against this root when --require-existing-files is used.",
    )
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_evidence_path(value: Any, path_root: Path | None) -> Path | None:
    if not isinstance(value, str) or not value or value.startswith("<"):
        return None
    path = Path(value)
    if not path.is_absolute() and path_root is not None:
        path = path_root / path
    return path


def hash_key_for_path_key(path_key: str) -> str | None:
    if path_key == "source_path":
        return "sha256"
    if path_key == "gvid_path":
        return "gvid_sha256"
    if path_key.endswith("_path"):
        return f"{path_key[:-5]}_sha256"
    return None


def iter_path_hash_pairs(value: Any) -> list[tuple[str, str, str]]:
    pairs: list[tuple[str, str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_path") or key in {"source_path", "gvid_path"}:
                hash_key = hash_key_for_path_key(key)
                if hash_key and isinstance(item, str) and isinstance(value.get(hash_key), str):
                    pairs.append((key, item, str(value[hash_key])))
            pairs.extend(iter_path_hash_pairs(item))
    elif isinstance(value, list):
        for item in value:
            pairs.extend(iter_path_hash_pairs(item))
    return pairs


def validate_existing_files(submission: dict[str, Any], path_root: Path | None) -> list[str]:
    failures: list[str] = []
    for key, raw_path, expected_hash in iter_path_hash_pairs(submission):
        path = resolve_evidence_path(raw_path, path_root)
        if path is None:
            continue
        if not SHA_RE.match(expected_hash):
            failures.append(f"{key} {raw_path} has invalid expected hash")
            continue
        if not path.is_file():
            failures.append(f"{key} {raw_path} does not exist")
            continue
        actual = sha256_file(path)
        if actual.lower() != expected_hash.lower():
            failures.append(f"{key} {raw_path} sha256 mismatch: expected {expected_hash}, got {actual}")
    return failures


def load_local_json(path_text: Any, path_root: Path | None, failures: list[str], label: str) -> dict[str, Any] | None:
    path = resolve_evidence_path(path_text, path_root)
    if path is None:
        failures.append(f"{label} path is missing or unresolved")
        return None
    if not path.is_file():
        failures.append(f"{label} {path_text} does not exist")
        return None
    try:
        return load_json(path)
    except Exception as exc:
        failures.append(f"{label} {path_text} is not valid JSON: {exc}")
        return None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def rows_for(submission: dict[str, Any], rid: str, key: str = "evidence") -> list[dict[str, Any]]:
    rows = submission.get("requirements")
    if not isinstance(rows, list):
        return []
    for row in rows:
        if isinstance(row, dict) and row.get("id") == rid:
            return [item for item in as_list(row.get(key)) if isinstance(item, dict)]
    return []


def record_for(submission: dict[str, Any], rid: str) -> dict[str, Any]:
    rows = submission.get("requirements")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and row.get("id") == rid:
            return row
    return {}


def has_sha(row: dict[str, Any], key: str = "sha256") -> bool:
    value = row.get(key)
    return isinstance(value, str) and bool(SHA_RE.match(value))


def number_at_least(row: dict[str, Any], key: str, minimum: float) -> tuple[bool, str]:
    value = row.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False, f"{key} must be numeric and >= {minimum:g}"
    if parsed < minimum:
        return False, f"{key} must be >= {minimum:g}"
    return True, ""


def number_greater_than(row: dict[str, Any], key: str, minimum: float) -> tuple[bool, str]:
    value = row.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False, f"{key} must be numeric and > {minimum:g}"
    if parsed <= minimum:
        return False, f"{key} must be > {minimum:g}"
    return True, ""


def number_equals(row: dict[str, Any], key: str, expected: int) -> tuple[bool, str]:
    value = row.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return False, f"{key} must be numeric and equal {expected}"
    if parsed != expected:
        return False, f"{key} must equal {expected}"
    return True, ""


def missing_fields(row: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if row.get(field) in (None, "")]


def pass_result(rid: str, message: str, evidence_count: int = 0) -> dict[str, Any]:
    return {"id": rid, "status": "PASS", "evidence_count": evidence_count, "message": message, "failures": []}


def fail_result(rid: str, failures: list[str], evidence_count: int = 0) -> dict[str, Any]:
    return {
        "id": rid,
        "status": "FAIL",
        "evidence_count": evidence_count,
        "message": "; ".join(failures),
        "failures": failures,
    }


def skip_result(rid: str, message: str) -> dict[str, Any]:
    return {"id": rid, "status": "SKIP", "evidence_count": 0, "message": message, "failures": []}


def submission_has_requirement(submission: dict[str, Any], rid: str) -> bool:
    rows = submission.get("requirements")
    return any(isinstance(row, dict) and row.get("id") == rid for row in as_list(rows))


def required_for_release_closure(req: dict[str, Any]) -> bool:
    return req.get("priority") == "required" and req.get("status") != "closed"


def validate_real_fixture(rid: str, req: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    expected_phase = str(req.get("required_cfa_phase") or "")
    min_count = int(req.get("minimum_count") or 1)
    required = [
        "source_path",
        "sha256",
        "make",
        "model",
        "width",
        "height",
        "cfa_phase",
        "bit_depth",
        "black_level",
        "white_level",
        "iso",
    ]
    accepted: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in rows_for(submission, rid):
        local = missing_fields(row, required)
        if local:
            failures.append(f"fixture missing {', '.join(local)}")
            continue
        if not has_sha(row):
            failures.append("fixture sha256 must be 64 hex characters")
            continue
        if str(row.get("cfa_phase")).upper() != expected_phase:
            failures.append(f"fixture cfa_phase must be {expected_phase}")
            continue
        if row.get("original_camera_raw") is not True:
            failures.append("fixture must set original_camera_raw=true")
            continue
        if row.get("linear_raw") is True:
            failures.append("fixture must not be Linear Raw")
            continue
        accepted.append(row)
    if len(accepted) < min_count:
        failures.append(f"accepted {len(accepted)} fixture(s), need {min_count}")
    if failures:
        return fail_result(rid, failures, len(accepted))
    return pass_result(rid, f"accepted {len(accepted)} real {expected_phase} fixture(s)", len(accepted))


def darkframe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("make"),
        row.get("model"),
        row.get("iso"),
        str(row.get("cfa_phase") or "").upper(),
        row.get("width"),
        row.get("height"),
        row.get("bit_depth"),
        row.get("black_level"),
        row.get("white_level"),
    )


def audit_frame_signature(frame: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        str(frame.get("raw_sha256") or "").lower() or None,
        str(frame.get("original_sha256") or "").lower() or None,
        str(frame.get("extract_receipt_sha256") or "").lower() or None,
    )


def submission_darkframe_signature(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        str(row.get("extracted_bayer_sha256") or "").lower() or None,
        str(row.get("sha256") or "").lower() or None,
        str(row.get("extract_receipt_sha256") or "").lower() or None,
    )


def validate_darkframe_audit_coverage(
    record: dict[str, Any],
    submitted_rows: list[dict[str, Any]],
    min_count: int,
    path_root: Path | None,
    failures: list[str],
) -> None:
    audit = load_local_json(record.get("source_provenance_audit_path"), path_root, failures, "source_provenance_audit")
    if audit is None:
        return
    if audit.get("schema") != DARKFRAME_SOURCE_PROVENANCE_AUDIT_SCHEMA:
        failures.append(f"source_provenance_audit file schema must be {DARKFRAME_SOURCE_PROVENANCE_AUDIT_SCHEMA}")
    if audit.get("production_ready") is not True:
        failures.append("source_provenance_audit file production_ready must be true")
    ok, failure = number_at_least(audit, "ready_frame_count", min_count)
    if not ok:
        failures.append(f"source_provenance_audit file {failure}")
    ready_frames = [row for row in as_list(audit.get("frames")) if isinstance(row, dict) and row.get("ready") is True]
    audit_signatures = {audit_frame_signature(frame) for frame in ready_frames}
    if len(audit_signatures) < min_count:
        failures.append(f"source_provenance_audit file has {len(audit_signatures)} ready frame signature(s), need {min_count}")
    for row in submitted_rows:
        signature = submission_darkframe_signature(row)
        if signature not in audit_signatures:
            failures.append(
                "darkframe evidence row is not covered by source_provenance_audit "
                f"(extracted/source/receipt hash triple {signature})"
            )


def validate_darkframe_stack(
    rid: str,
    req: dict[str, Any],
    submission: dict[str, Any],
    *,
    require_existing_files: bool = False,
    path_root: Path | None = None,
) -> dict[str, Any]:
    min_count = int(req.get("minimum_count") or 4)
    record = record_for(submission, rid)
    required = [
        "source_path",
        "sha256",
        "extracted_bayer_path",
        "extracted_bayer_sha256",
        "extract_receipt_path",
        "make",
        "model",
        "width",
        "height",
        "cfa_phase",
        "bit_depth",
        "black_level",
        "white_level",
        "iso",
        "exposure",
        "extract_receipt_sha256",
        "source_kind",
    ]
    failures: list[str] = []
    audit_required = [
        "source_provenance_audit_path",
        "source_provenance_audit_sha256",
        "source_provenance_audit_schema",
        "source_provenance_audit_ready_frame_count",
        "source_provenance_audit_production_ready",
    ]
    audit_missing = missing_fields(record, audit_required)
    if audit_missing:
        failures.append(f"darkframe stack missing {', '.join(audit_missing)}")
    else:
        if not has_sha(record, "source_provenance_audit_sha256"):
            failures.append("source_provenance_audit_sha256 must be a 64-hex hash")
        if record.get("source_provenance_audit_schema") != DARKFRAME_SOURCE_PROVENANCE_AUDIT_SCHEMA:
            failures.append(f"source_provenance_audit_schema must be {DARKFRAME_SOURCE_PROVENANCE_AUDIT_SCHEMA}")
        ok, failure = number_at_least(record, "source_provenance_audit_ready_frame_count", min_count)
        if not ok:
            failures.append(failure)
        if record.get("source_provenance_audit_production_ready") is not True:
            failures.append("source_provenance_audit_production_ready must be true")

    evidence_rows = rows_for(submission, rid)
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in evidence_rows:
        local = missing_fields(row, required)
        if local:
            failures.append(f"darkframe missing {', '.join(local)}")
            continue
        if not has_sha(row) or not has_sha(row, "extracted_bayer_sha256") or not has_sha(row, "extract_receipt_sha256"):
            failures.append("darkframe source, extracted Bayer, and extraction receipt hashes must be 64 hex characters")
            continue
        if row.get("source_kind") not in CONFIRMED_DARKFRAME_SOURCE_KINDS:
            failures.append(
                "darkframe source_kind must be confirmed_darkframes, flat_dark_pair, or equivalent_no_scene_stack"
            )
            continue
        if row.get("no_scene_signal") is not True:
            failures.append("darkframe must set no_scene_signal=true")
            continue
        if not (row.get("capture_setup") or row.get("proof")):
            failures.append("darkframe must include capture_setup or proof for no-scene-signal provenance")
            continue
        if rid == "iphone_cfa_darkframe_stack" and row.get("linear_raw") is True:
            failures.append("iPhone darkframes must be CFA raw, not Linear Raw")
            continue
        grouped.setdefault(darkframe_key(row), []).append(row)

    if require_existing_files and not audit_missing:
        validate_darkframe_audit_coverage(record, evidence_rows, min_count, path_root, failures)

    best_count = max((len(rows) for rows in grouped.values()), default=0)
    if best_count < min_count:
        failures.append(f"best matching stack has {best_count} frame(s), need {min_count}")
    if failures:
        return fail_result(rid, failures, best_count)
    return pass_result(rid, f"accepted {best_count}-frame same-camera/ISO/CFA darkframe stack", best_count)


def validate_camera_role_receipts(rid: str, submission: dict[str, Any]) -> dict[str, Any]:
    row = record_for(submission, rid)
    receipts = row.get("receipts") if isinstance(row.get("receipts"), dict) else {}
    failures: list[str] = []
    required_fields = [
        "gvid_path",
        "gvid_sha256",
        "source_width",
        "source_height",
        "source_fps",
        "encode_fps",
        "preview_width",
        "preview_height",
        "preview_fps",
        "storage_medium",
        "storage_write_mb_s",
        "storage_budget_passed",
        "peak_rss_mb",
    ]
    missing = missing_fields(row, required_fields)
    if missing:
        failures.append(f"missing camera performance field(s): {', '.join(missing)}")
    if row.get("gvid_path") and not has_sha(row, "gvid_sha256"):
        failures.append("gvid_sha256 needs sha256")
    missing = sorted(REQUIRED_CAMERA_ROLE_RECEIPTS - set(receipts))
    if missing:
        failures.append(f"missing receipt(s): {', '.join(missing)}")
    for name, receipt in receipts.items():
        if not isinstance(receipt, dict):
            failures.append(f"{name} receipt must be an object")
            continue
        if not has_sha(receipt):
            failures.append(f"{name} receipt needs sha256")
    if row.get("target_role") != "camera":
        failures.append("target_role must be camera")
    if row.get("source_kind") not in {"real_sensor_dma", "camera_ring_buffer"}:
        failures.append("source_kind must be real_sensor_dma or camera_ring_buffer")
    if row.get("valid_gvid") is not True:
        failures.append("valid_gvid must be true")
    if int(row.get("dropped_frames") or 0) != 0:
        failures.append("dropped_frames must be 0")
    for key in ("source_fps", "encode_fps", "preview_fps"):
        ok, failure = number_at_least(row, key, 20.0)
        if not ok:
            failures.append(failure)
    for key, expected in (
        ("source_width", 4096),
        ("source_height", 3072),
        ("preview_width", 1024),
        ("preview_height", 768),
    ):
        ok, failure = number_equals(row, key, expected)
        if not ok:
            failures.append(failure)
    ok, failure = number_greater_than(row, "storage_write_mb_s", 0.0)
    if not ok:
        failures.append(failure)
    ok, failure = number_greater_than(row, "peak_rss_mb", 0.0)
    if not ok:
        failures.append(failure)
    if row.get("storage_budget_passed") is not True:
        failures.append("storage_budget_passed must be true")
    if row.get("preview_full_frame") is not True:
        failures.append("preview_full_frame must be true")
    if failures:
        return fail_result(rid, failures, len(receipts))
    return pass_result(rid, "camera-role encode, storage, and preview receipts pass", len(receipts))


def validate_psf_pairs(rid: str, req: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    row = record_for(submission, rid)
    pairs = [item for item in as_list(row.get("pairs")) if isinstance(item, dict)]
    min_pairs = int(req.get("minimum_pair_count") or 3)
    failures: list[str] = []
    accepted = 0
    negative_controls = 0
    for pair in pairs:
        pair_id = str(pair.get("id") or "")
        required = [
            "high_source_path",
            "low_source_path",
            "high_bayer_path",
            "low_bayer_path",
            "high_width",
            "high_height",
            "low_width",
            "low_height",
            "high_bayer_bytes",
            "low_bayer_bytes",
            "cfa_phase",
            "settings_receipt_sha256",
            "measurement_receipt_sha256",
        ]
        missing = missing_fields(pair, required)
        if missing:
            failures.append(f"pair {pair_id} missing {', '.join(missing)}")
            continue
        for key in (
            "high_source_sha256",
            "low_source_sha256",
            "high_bayer_sha256",
            "low_bayer_sha256",
            "high_extract_receipt_sha256",
            "low_extract_receipt_sha256",
            "settings_receipt_sha256",
            "measurement_receipt_sha256",
        ):
            if not has_sha(pair, key):
                failures.append(f"pair {pair_id} missing valid {key}")
        for key, expected in (
            ("high_width", PSF_HIGH_DIMS[0]),
            ("high_height", PSF_HIGH_DIMS[1]),
            ("low_width", PSF_LOW_DIMS[0]),
            ("low_height", PSF_LOW_DIMS[1]),
            ("high_bayer_bytes", PSF_HIGH_BYTES),
            ("low_bayer_bytes", PSF_LOW_BYTES),
        ):
            ok, failure = number_equals(pair, key, expected)
            if not ok:
                failures.append(f"pair {pair_id} {failure}")
        if str(pair.get("cfa_phase") or "").upper() not in {"RGGB", "GBRG", "GRBG", "BGGR"}:
            failures.append(f"pair {pair_id} cfa_phase must be a normal 2x2 Bayer phase")
        fixed_missing = missing_fields(pair, PSF_FIXED_SETTING_FIELDS)
        if fixed_missing:
            failures.append(f"pair {pair_id} missing fixed setting field(s): {', '.join(fixed_missing)}")
        if pair.get("negative_control") is True:
            if pair.get("expected_reject") is True and pair.get("rejected_by_measurement") is True and pair.get("rejection_reason"):
                negative_controls += 1
            else:
                failures.append(
                    f"pair {pair_id} negative control must set expected_reject=true, rejected_by_measurement=true, and rejection_reason"
                )
            continue
        if pair.get("fixed_settings") is not True:
            failures.append(f"pair {pair_id} must set fixed_settings=true")
            continue
        if pair.get("static_scene") is not True:
            failures.append(f"pair {pair_id} must set static_scene=true")
            continue
        if pair.get("accepted_by_measurement") is not True:
            failures.append(f"pair {pair_id} must set accepted_by_measurement=true")
            continue
        accepted += 1
    if accepted < min_pairs:
        failures.append(f"accepted {accepted} controlled pair(s), need {min_pairs}")
    if negative_controls < 1:
        failures.append("at least one expected-reject negative control is required")
    if failures:
        return fail_result(rid, failures, accepted)
    return pass_result(rid, f"accepted {accepted} controlled PSF pair(s) plus negative controls", accepted)


def validate_premium_still_sr(rid: str, submission: dict[str, Any]) -> dict[str, Any]:
    row = record_for(submission, rid)
    required_hashes = [
        "candidate_preflight_manifest_sha256",
        "candidate_preflight_audit_sha256",
        "launch_packet_sha256",
        "x2d_smoke_receipt_sha256",
        "z8_smoke_receipt_sha256",
        "baseline_comparison_sha256",
        "checkpoint_sha256",
        "training_config_sha256",
        "training_target_sha256",
        "editable_raw_receipt_sha256",
        "review_dashboard_sha256",
        "timing_memory_receipt_sha256",
        "noise_policy_receipt_sha256",
    ]
    failures: list[str] = []
    for key in required_hashes:
        if not has_sha(row, key):
            failures.append(f"{key} must be a 64-hex hash")
    required_true = [
        "full_frame_gate_50mp_passed",
        "full_frame_gate_100mp_passed",
        "editor_latitude_passed",
        "no_ref_runtime",
        "beats_current_baseline",
        "candidate_preflight_launchable",
        "smoke_gate_passed",
        "smoke_gate_long_run_blocked_if_smoke_fails",
    ]
    for key in required_true:
        if row.get(key) is not True:
            failures.append(f"{key} must be true")
    if row.get("severe_worst_row_failures") is not False:
        failures.append("severe_worst_row_failures must be false")

    runtime_inputs = row.get("runtime_inputs")
    if not isinstance(runtime_inputs, list) or not all(isinstance(item, str) for item in runtime_inputs):
        failures.append("runtime_inputs must list production runtime inputs")
    else:
        runtime_set = set(runtime_inputs)
        missing_runtime = sorted(PREMIUM_REQUIRED_RUNTIME_INPUTS - runtime_set)
        forbidden_runtime = sorted(PREMIUM_FORBIDDEN_RUNTIME_INPUTS & runtime_set)
        if missing_runtime:
            failures.append(f"runtime_inputs missing required input(s): {', '.join(missing_runtime)}")
        if forbidden_runtime:
            failures.append(f"runtime_inputs contains forbidden render-time input(s): {', '.join(forbidden_runtime)}")

    smoke_baseline = str(row.get("smoke_gate_baseline") or "").lower()
    if "same-color" not in smoke_baseline or "interpolation" not in smoke_baseline:
        failures.append("smoke_gate_baseline must be same-color Bayer interpolation")
    smoke_holdouts = {str(item).lower() for item in as_list(row.get("smoke_gate_required_holdouts"))}
    missing_holdouts = sorted(PREMIUM_REQUIRED_SMOKE_HOLDOUTS - smoke_holdouts)
    if missing_holdouts:
        failures.append(f"smoke_gate_required_holdouts missing: {', '.join(missing_holdouts)}")
    for key in ("x2d_smoke_median_mae_reduction_pct", "z8_smoke_median_mae_reduction_pct"):
        ok, failure = number_greater_than(row, key, 0)
        if not ok:
            failures.append(failure)
    for key in ("x2d_smoke_worst_row_mae_reduction_pct", "z8_smoke_worst_row_mae_reduction_pct"):
        ok, failure = number_at_least(row, key, 0)
        if not ok:
            failures.append(failure)

    for key in ("full_frame_gate_50mp_row_count", "full_frame_gate_100mp_row_count"):
        ok, failure = number_at_least(row, key, 1)
        if not ok:
            failures.append(failure)
    for key in ("median_mae_reduction_pct_50mp", "median_mae_reduction_pct_100mp"):
        ok, failure = number_greater_than(row, key, 0)
        if not ok:
            failures.append(failure)
    for key in ("worst_row_mae_reduction_pct_50mp", "worst_row_mae_reduction_pct_100mp"):
        ok, failure = number_at_least(row, key, 0)
        if not ok:
            failures.append(failure)
    for key in ("render_seconds_per_50mp_frame", "render_seconds_per_100mp_frame", "peak_rss_gb"):
        ok, failure = number_greater_than(row, key, 0)
        if not ok:
            failures.append(failure)
    if row.get("noise_policy_exact_sidecars_only") is not True:
        failures.append("noise_policy_exact_sidecars_only must be true")
    if row.get("noise_policy_forbids_source_residual_noise") is not True:
        failures.append("noise_policy_forbids_source_residual_noise must be true")
    if failures:
        return fail_result(rid, failures, 1 if row else 0)
    return pass_result(rid, "premium still-SR promotion evidence passes manifest checks", 1)


def validate_requirement(
    req: dict[str, Any],
    submission: dict[str, Any],
    *,
    require_existing_files: bool = False,
    path_root: Path | None = None,
) -> dict[str, Any]:
    rid = str(req.get("id") or "")
    sample_type = req.get("sample_type")
    if sample_type == "real_camera_raw_fixture":
        return validate_real_fixture(rid, req, submission)
    if sample_type == "darkframe_stack":
        return validate_darkframe_stack(
            rid,
            req,
            submission,
            require_existing_files=require_existing_files,
            path_root=path_root,
        )
    if sample_type == "camera_hardware_receipt":
        return validate_camera_role_receipts(rid, submission)
    if sample_type == "controlled_same_scene_high_low_raw_pair_stack":
        return validate_psf_pairs(rid, req, submission)
    if sample_type == "model_promotion_receipt":
        return validate_premium_still_sr(rid, submission)
    return fail_result(rid, [f"unsupported requirement sample_type {sample_type!r}"])


def build_audit(
    requirements: dict[str, Any],
    submission: dict[str, Any],
    *,
    require_existing_files: bool = False,
    path_root: Path | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    if submission.get("schema") != SUBMISSION_SCHEMA:
        failures.append(f"submission schema must be {SUBMISSION_SCHEMA}")
    if require_existing_files:
        failures.extend(validate_existing_files(submission, path_root))
    req_rows = [row for row in as_list(requirements.get("requirements")) if isinstance(row, dict)]
    results = []
    for row in req_rows:
        rid = str(row.get("id") or "")
        closure_blocking = required_for_release_closure(row)
        if closure_blocking or submission_has_requirement(submission, rid):
            result = validate_requirement(
                row,
                submission,
                require_existing_files=require_existing_files,
                path_root=path_root,
            )
        else:
            priority = str(row.get("priority") or "required")
            status = str(row.get("status") or "")
            if priority == "research_optional":
                result = skip_result(rid, "optional research evidence was not submitted")
            else:
                result = skip_result(rid, f"requirement is already {status or 'not release-blocking'}")
        result["closure_blocking"] = closure_blocking
        result["priority"] = row.get("priority")
        result["requirement_status"] = row.get("status")
        results.append(result)

    pass_count = sum(1 for row in results if row["status"] == "PASS")
    skip_count = sum(1 for row in results if row["status"] == "SKIP")
    fail_count = sum(1 for row in results if row["status"] == "FAIL")
    required_results = [row for row in results if row["closure_blocking"]]
    required_pass_count = sum(1 for row in required_results if row["status"] == "PASS")
    optional_fail_count = sum(
        1
        for row in results
        if not row["closure_blocking"] and row["status"] == "FAIL"
    )
    all_required_closed = not failures and required_pass_count == len(required_results)
    submission_valid = all_required_closed and optional_fail_count == 0
    return {
        "schema": SCHEMA,
        "requirements_schema": requirements.get("schema"),
        "submission_schema": submission.get("schema"),
        "all_requirements_closed": all_required_closed,
        "submission_valid": submission_valid,
        "pass_count": pass_count,
        "skip_count": skip_count,
        "fail_count": fail_count + len(failures),
        "required_for_closure_count": len(required_results),
        "required_for_closure_pass_count": required_pass_count,
        "optional_research_fail_count": optional_fail_count,
        "manifest_failures": failures,
        "results": results,
    }


def render_html(audit: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['status'])}</td>"
        f"<td>{html.escape(row['id'])}</td>"
        f"<td>{html.escape(str(row['evidence_count']))}</td>"
        f"<td>{html.escape(row['message'])}</td>"
        "</tr>"
        for row in audit["results"]
    )
    manifest_failures = "".join(f"<li>{html.escape(item)}</li>" for item in audit["manifest_failures"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Production Capture Submission Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1100px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin-bottom: 8px; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
</style></head><body><main>
<h1>Production Capture Submission Audit</h1>
<div class="summary">
<section class="card"><div class="label">All closed</div><div class="value">{html.escape(str(audit["all_requirements_closed"]))}</div></section>
<section class="card"><div class="label">Submission valid</div><div class="value">{html.escape(str(audit["submission_valid"]))}</div></section>
<section class="card"><div class="label">Pass</div><div class="value">{audit["pass_count"]}</div></section>
<section class="card"><div class="label">Fail</div><div class="value">{audit["fail_count"]}</div></section>
<section class="card"><div class="label">Skip</div><div class="value">{audit["skip_count"]}</div></section>
</div>
<ul>{manifest_failures}</ul>
<table><thead><tr><th>Status</th><th>Requirement</th><th>Evidence</th><th>Message</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    try:
        audit = build_audit(
            load_json(args.requirements),
            load_json(args.submission),
            require_existing_files=args.require_existing_files,
            path_root=args.path_root,
        )
    except Exception as exc:
        print(f"check_production_capture_submission: {exc}", file=sys.stderr)
        return 2
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.html_out:
        args.html_out.parent.mkdir(parents=True, exist_ok=True)
        args.html_out.write_text(render_html(audit), encoding="utf-8")
    if not audit["submission_valid"]:
        print("Production capture submission is incomplete:")
        for failure in audit["manifest_failures"]:
            print(f"  - {failure}")
        for row in audit["results"]:
            if row["status"] == "FAIL" or (row.get("closure_blocking") and row["status"] != "PASS"):
                print(f"  - {row['id']}: {row['message']}")
        return 1
    print("OK - production capture submission closes all release-blocking requirements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
