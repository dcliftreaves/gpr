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

from check_product_pillar_receipts import validate_still_sr_gate


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
CAMERA_ROLE_MIN_SUSTAINED_FRAMES = 120
CAMERA_STORAGE_ALLOWED_TOKENS = {"mission", "camera", "sd", "internal", "lexar", "silver"}
CAMERA_STORAGE_FORBIDDEN_TOKENS = {"pi", "standin", "stand_in", "stand-in", "proxy", "ssd", "tmp", "tmpfs", "ramdisk"}
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
PSF_PAIR_SETTINGS_SCHEMA = "gpr.mission1_native_psf_pair_settings.v1"
PSF_PAIR_MEASUREMENT_SCHEMA = "gpr.mission1_native_psf_pair_measurement.v1"
PREMIUM_REQUIRED_RUNTIME_INPUTS = {"candidate_raw", "camera_metadata"}
PREMIUM_REQUIRED_SMOKE_HOLDOUTS = {"x2d", "z8"}
PREMIUM_FORBIDDEN_RUNTIME_INPUTS = {
    "REF",
    "ref",
    "reference",
    "reference_image",
    "source_raw",
    "source_rgb",
    "source_hf",
    "JPEG_target",
    "jpeg",
    "jpg",
    "jpeg_target",
    "jpg_target",
    "gate_metrics",
}
CONFIRMED_DARKFRAME_SOURCE_KINDS = {
    "confirmed_darkframes",
    "flat_dark_pair",
    "equivalent_no_scene_stack",
}
DARKFRAME_SOURCE_PROVENANCE_AUDIT_SCHEMA = "gpr.darkframe_source_provenance_audit.v1"
CAMERA_NOISE_CALIBRATION_SCHEMA = "gpr.camera_noise_calibration.v1"


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
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            pairs.append(("path", str(value["path"]), str(value["sha256"])))
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


def nested_get(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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


def darkframe_metadata_matches(submitted: dict[str, Any], audit_frame: dict[str, Any]) -> list[str]:
    metadata = audit_frame.get("metadata") if isinstance(audit_frame.get("metadata"), dict) else {}
    failures: list[str] = []
    for key in ("make", "model", "iso", "width", "height", "bit_depth", "black_level", "white_level"):
        if str(metadata.get(key)) != str(submitted.get(key)):
            failures.append(key)
    if str(metadata.get("cfa_phase") or "").upper() != str(submitted.get("cfa_phase") or "").upper():
        failures.append("cfa_phase")
    return failures


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
    frames_by_signature = {audit_frame_signature(frame): frame for frame in ready_frames}
    for frame in ready_frames:
        if frame.get("linear_raw") is not False:
            failures.append("source_provenance_audit ready frames must record linear_raw=false")
    for row in submitted_rows:
        signature = submission_darkframe_signature(row)
        audit_frame = frames_by_signature.get(signature)
        if audit_frame is None:
            failures.append(
                "darkframe evidence row is not covered by source_provenance_audit "
                f"(extracted/source/receipt hash triple {signature})"
            )
            continue
        metadata_failures = darkframe_metadata_matches(row, audit_frame)
        if metadata_failures:
            failures.append(
                "source_provenance_audit frame metadata must match submitted darkframe stack "
                f"for {', '.join(metadata_failures)}"
            )


def validate_camera_noise_sidecar(
    record: dict[str, Any],
    submitted_rows: list[dict[str, Any]],
    min_count: int,
    path_root: Path | None,
    failures: list[str],
) -> None:
    sidecar = load_local_json(record.get("camera_noise_sidecar_path"), path_root, failures, "camera_noise_sidecar")
    if sidecar is None:
        return
    if sidecar.get("schema") != CAMERA_NOISE_CALIBRATION_SCHEMA:
        failures.append(f"camera_noise_sidecar schema must be {CAMERA_NOISE_CALIBRATION_SCHEMA}")
    if sidecar.get("production_ready") is not True:
        failures.append("camera_noise_sidecar production_ready must be true")
    camera = sidecar.get("camera") if isinstance(sidecar.get("camera"), dict) else {}
    first = submitted_rows[0] if submitted_rows else {}
    for key in ("make", "model", "width", "height", "bit_depth", "black_level", "white_level"):
        if first and str(camera.get(key)) != str(first.get(key)):
            failures.append(f"camera_noise_sidecar camera.{key} must match submitted darkframe stack")
    if first and str(camera.get("cfa_phase") or "").upper() != str(first.get("cfa_phase") or "").upper():
        failures.append("camera_noise_sidecar camera.cfa_phase must match submitted darkframe stack")
    calibrations = [row for row in as_list(sidecar.get("calibrations")) if isinstance(row, dict)]
    if not calibrations:
        failures.append("camera_noise_sidecar must include at least one calibration")
        return
    calibration = calibrations[0]
    if first and str(calibration.get("iso")) != str(first.get("iso")):
        failures.append("camera_noise_sidecar calibration iso must match submitted darkframe stack")
    ok, failure = number_at_least(calibration, "sample_count", min_count)
    if not ok:
        failures.append(f"camera_noise_sidecar calibration.{failure}")
    if calibration.get("usable_for_training_targets") is not True:
        failures.append("camera_noise_sidecar calibration.usable_for_training_targets must be true")
    per_plane = calibration.get("per_plane") if isinstance(calibration.get("per_plane"), dict) else {}
    for plane in ("r", "g1", "b", "g2"):
        metrics = per_plane.get(plane)
        if not isinstance(metrics, dict):
            failures.append(f"camera_noise_sidecar per_plane.{plane} must be an object")
            continue
        ok, failure = number_at_least(metrics, "mean_black", 0.0)
        if not ok:
            failures.append(f"camera_noise_sidecar per_plane.{plane}.{failure}")
        ok, failure = number_greater_than(metrics, "sigma_black", 0.0)
        if not ok:
            failures.append(f"camera_noise_sidecar per_plane.{plane}.{failure}")
        ok, failure = number_at_least(metrics, "noise_profile_offset", 0.0)
        if not ok:
            failures.append(f"camera_noise_sidecar per_plane.{plane}.{failure}")
    audit = calibration.get("noise_signal_audit") if isinstance(calibration.get("noise_signal_audit"), dict) else {}
    if audit.get("separates_noise_from_signal") is not True:
        failures.append("camera_noise_sidecar noise_signal_audit.separates_noise_from_signal must be true")
    if audit.get("source_provenance_required") is not True:
        failures.append("camera_noise_sidecar noise_signal_audit.source_provenance_required must be true")
    if audit.get("source_provenance_ready") is not True:
        failures.append("camera_noise_sidecar noise_signal_audit.source_provenance_ready must be true")
    source = calibration.get("source") if isinstance(calibration.get("source"), dict) else {}
    ok, failure = number_at_least(source, "frame_count", min_count)
    if not ok:
        failures.append(f"camera_noise_sidecar source.{failure}")
    sidecar_frames = [
        frame
        for frame in as_list(source.get("frames"))
        if isinstance(frame, dict) and frame.get("source_provenance_ready") is True
    ]
    if len(sidecar_frames) < min_count:
        failures.append(f"camera_noise_sidecar source.frames must include at least {min_count} provenance-ready frames")
    unique_raw_hashes = {str(frame.get("raw_sha256") or "").lower() for frame in sidecar_frames}
    unique_raw_hashes.discard("")
    if len(unique_raw_hashes) < min_count:
        failures.append(f"camera_noise_sidecar source.frames must include at least {min_count} unique raw_sha256 values")
    sidecar_by_raw_hash = {str(frame.get("raw_sha256") or "").lower(): frame for frame in sidecar_frames}
    for row in submitted_rows:
        raw_hash = str(row.get("extracted_bayer_sha256") or "").lower()
        frame = sidecar_by_raw_hash.get(raw_hash)
        if frame is None:
            failures.append("camera_noise_sidecar source.frames must cover every submitted extracted Bayer hash")
            continue
        if str(frame.get("original_sha256") or "").lower() != str(row.get("sha256") or "").lower():
            failures.append("camera_noise_sidecar source.frames original_sha256 must match submitted source hash")
        if frame.get("no_scene_signal") is not True:
            failures.append("camera_noise_sidecar source.frames must preserve no_scene_signal=true")


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
        "camera_noise_sidecar_path",
        "camera_noise_sidecar_sha256",
    ]
    audit_missing = missing_fields(record, audit_required)
    if audit_missing:
        failures.append(f"darkframe stack missing {', '.join(audit_missing)}")
    else:
        if not has_sha(record, "source_provenance_audit_sha256"):
            failures.append("source_provenance_audit_sha256 must be a 64-hex hash")
        if not has_sha(record, "camera_noise_sidecar_sha256"):
            failures.append("camera_noise_sidecar_sha256 must be a 64-hex hash")
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
        validate_camera_noise_sidecar(record, evidence_rows, min_count, path_root, failures)

    best_count = max((len(rows) for rows in grouped.values()), default=0)
    if best_count < min_count:
        failures.append(f"best matching stack has {best_count} frame(s), need {min_count}")
    if failures:
        return fail_result(rid, failures, best_count)
    return pass_result(rid, f"accepted {best_count}-frame same-camera/ISO/CFA darkframe stack", best_count)


def receipt_path(receipts: dict[str, Any], name: str) -> Any:
    receipt = receipts.get(name)
    if isinstance(receipt, dict):
        return receipt.get("path")
    return None


def load_named_receipt(
    receipts: dict[str, Any],
    name: str,
    path_root: Path | None,
    failures: list[str],
) -> dict[str, Any] | None:
    return load_local_json(receipt_path(receipts, name), path_root, failures, name)


def label_key(value: Any) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def validate_camera_storage_medium_label(row: dict[str, Any], failures: list[str]) -> None:
    label = label_key(row.get("storage_medium"))
    if not label or label.startswith("<"):
        failures.append("storage_medium must name the real Mission/camera storage medium")
        return
    if any(token in label for token in CAMERA_STORAGE_FORBIDDEN_TOKENS):
        failures.append("storage_medium must not name Pi, SSD, tmpfs, proxy, or stand-in storage")
    if not any(token in label for token in CAMERA_STORAGE_ALLOWED_TOKENS):
        failures.append("storage_medium must name Mission/camera SD, internal, or Lexar-class storage")


def validate_strict_camera_role_receipt_content(
    row: dict[str, Any],
    *,
    path_root: Path | None,
    failures: list[str],
) -> None:
    receipts = row.get("receipts") if isinstance(row.get("receipts"), dict) else {}
    target_bench = load_named_receipt(receipts, "labs_target_bench", path_root, failures)
    target_preflight = load_named_receipt(receipts, "target_preflight_receipt", path_root, failures)
    handoff = load_named_receipt(receipts, "camera_handoff_receipt", path_root, failures)
    preview_decode = load_named_receipt(receipts, "preview_decode_receipt", path_root, failures)
    preview = load_named_receipt(receipts, "preview_ui_receipt", path_root, failures)
    closure = load_named_receipt(receipts, "mission1_camera_closure_run", path_root, failures)

    if target_bench is not None:
        if target_bench.get("schema") != "gpr_labs_target_bench.v1":
            failures.append("labs_target_bench schema must be gpr_labs_target_bench.v1")
        if target_bench.get("simulated") is True:
            failures.append("labs_target_bench must not be simulated")
        if nested_get(target_bench, "source_provenance", "available") is not True:
            failures.append("labs_target_bench source_provenance.available must be true")
        if not valid_hash_value(nested_get(target_bench, "source_provenance", "sha256")):
            failures.append("labs_target_bench source_provenance.sha256 must be a 64-hex hash")
        if nested_get(target_bench, "verdict", "target_evidence") is not True:
            failures.append("labs_target_bench verdict.target_evidence must be true")
        for key, expected in (
            ("source_width", 4096),
            ("source_height", 3072),
            ("capture_width", 4096),
            ("capture_height", 3072),
        ):
            ok, failure = number_equals(target_bench.get("capture", {}), key, expected)
            if not ok:
                failures.append(f"labs_target_bench capture.{failure}")
        ok, failure = number_equals(target_bench.get("capture", {}), "dropped_frames", 0)
        if not ok:
            failures.append(f"labs_target_bench capture.{failure}")
        ok, failure = number_at_least(
            target_bench.get("capture", {}),
            "frames_written",
            CAMERA_ROLE_MIN_SUSTAINED_FRAMES,
        )
        if not ok:
            failures.append(f"labs_target_bench capture.{failure}")
        if nested_get(target_bench, "gvid", "sha256") != row.get("gvid_sha256"):
            failures.append("labs_target_bench gvid.sha256 must match submitted gvid_sha256")
        if nested_get(target_bench, "gvid", "validation", "valid") is not True:
            failures.append("labs_target_bench gvid.validation.valid must be true")
        target_frames = numeric_value(nested_get(target_bench, "capture", "frames_written"))
        gvid_frames = numeric_value(nested_get(target_bench, "gvid", "validation", "frame_count"))
        if target_frames is not None and gvid_frames is not None and int(target_frames) != int(gvid_frames):
            failures.append("labs_target_bench gvid.validation.frame_count must match capture.frames_written")

    if target_preflight is not None:
        if target_preflight.get("schema") != "gpr.mission1_camera_target_preflight.v1":
            failures.append("target_preflight_receipt schema must be gpr.mission1_camera_target_preflight.v1")
        if nested_get(target_preflight, "target", "role") != "camera":
            failures.append("target_preflight_receipt target.role must be camera")
        if nested_get(target_preflight, "verdict", "target_preflight_ready") is not True:
            failures.append("target_preflight_receipt verdict.target_preflight_ready must be true")
        if nested_get(target_preflight, "verdict", "camera_closure_possible") is not True:
            failures.append("target_preflight_receipt verdict.camera_closure_possible must be true")

    if handoff is not None:
        if handoff.get("schema") != "gpr_labs_camera_handoff_receipt.v1":
            failures.append("camera_handoff_receipt schema must be gpr_labs_camera_handoff_receipt.v1")
        if nested_get(handoff, "source_provenance", "available") is not True:
            failures.append("camera_handoff_receipt source_provenance.available must be true")
        if not valid_hash_value(nested_get(handoff, "source_provenance", "sha256")):
            failures.append("camera_handoff_receipt source_provenance.sha256 must be a 64-hex hash")
        if nested_get(handoff, "target", "role") != "camera":
            failures.append("camera_handoff_receipt target.role must be camera")
        if nested_get(handoff, "integration", "raw_source_kind") not in {"sensor_dma_capture", "camera_ring_buffer"}:
            failures.append("camera_handoff_receipt integration.raw_source_kind must be sensor_dma_capture or camera_ring_buffer")
        if nested_get(handoff, "integration", "sensor_dma_handoff", "executed") is not True:
            failures.append("camera_handoff_receipt integration.sensor_dma_handoff.executed must be true")
        if nested_get(handoff, "integration", "storage_handoff", "executed") is not True:
            failures.append("camera_handoff_receipt integration.storage_handoff.executed must be true")
        if nested_get(handoff, "verdict", "firmware_ready") is not True:
            failures.append("camera_handoff_receipt verdict.firmware_ready must be true")
        for key in ("target_evidence", "fps_target_met", "no_drops"):
            if nested_get(handoff, "verdict", key) is not True:
                failures.append(f"camera_handoff_receipt verdict.{key} must be true")
        if nested_get(handoff, "output", "sha256") != row.get("gvid_sha256"):
            failures.append("camera_handoff_receipt output.sha256 must match submitted gvid_sha256")
        if nested_get(handoff, "output", "validation", "valid") is not True:
            failures.append("camera_handoff_receipt output.validation.valid must be true")
        ok, failure = number_equals(handoff.get("input_frame", {}), "width", 4096)
        if not ok:
            failures.append(f"camera_handoff_receipt input_frame.{failure}")
        ok, failure = number_equals(handoff.get("input_frame", {}), "height", 3072)
        if not ok:
            failures.append(f"camera_handoff_receipt input_frame.{failure}")
        ok, failure = number_equals(handoff.get("capture", {}), "dropped_frames", 0)
        if not ok:
            failures.append(f"camera_handoff_receipt capture.{failure}")
        handoff_frames = numeric_value(nested_get(handoff, "capture", "frames_written"))
        handoff_output_frames = numeric_value(nested_get(handoff, "output", "validation", "frame_count"))
        target_frames = numeric_value(nested_get(target_bench or {}, "capture", "frames_written"))
        ok, failure = number_at_least(
            handoff.get("capture", {}),
            "frames_written",
            CAMERA_ROLE_MIN_SUSTAINED_FRAMES,
        )
        if not ok:
            failures.append(f"camera_handoff_receipt capture.{failure}")
        if handoff_frames is not None and handoff_output_frames is not None and int(handoff_frames) != int(handoff_output_frames):
            failures.append("camera_handoff_receipt output.validation.frame_count must match capture.frames_written")
        if target_frames is not None and handoff_frames is not None and int(target_frames) != int(handoff_frames):
            failures.append("camera_handoff_receipt capture.frames_written must match labs_target_bench capture.frames_written")
        ok, failure = number_greater_than(handoff.get("storage", {}), "write_mb_s", 0.0)
        if not ok:
            failures.append(f"camera_handoff_receipt storage.{failure}")
        ok, failure = number_greater_than(handoff.get("memory", {}), "rss_kb", 0.0)
        if not ok:
            failures.append(f"camera_handoff_receipt memory.{failure}")
        ok, failure = number_at_least(handoff.get("timing", {}), "fps_median", 20.0)
        if not ok:
            failures.append(f"camera_handoff_receipt timing.{failure}")

    if preview_decode is not None:
        if preview_decode.get("schema") != "gvid_decode_target_bench.v1":
            failures.append("preview_decode_receipt schema must be gvid_decode_target_bench.v1")
        if preview_decode.get("gvid_sha256") != row.get("gvid_sha256"):
            failures.append("preview_decode_receipt gvid_sha256 must match submitted gvid_sha256")
        for key, expected in (("sensor_width", 4096), ("sensor_height", 3072)):
            ok, failure = number_equals(preview_decode, key, expected)
            if not ok:
                failures.append(f"preview_decode_receipt {failure}")
        if preview_decode.get("raw_target") != "mission1_preview_4x_1024x768":
            failures.append("preview_decode_receipt raw_target must be mission1_preview_4x_1024x768")
        frame_count = numeric_value(preview_decode.get("frame_count"))
        if frame_count is None or frame_count < CAMERA_ROLE_MIN_SUSTAINED_FRAMES:
            failures.append(f"preview_decode_receipt frame_count must be >= {CAMERA_ROLE_MIN_SUSTAINED_FRAMES}")
        elif target_bench is not None:
            target_frames = numeric_value(nested_get(target_bench, "capture", "frames_written"))
            if target_frames is not None and int(frame_count) != int(target_frames):
                failures.append("preview_decode_receipt frame_count must match labs_target_bench capture.frames_written")
        dims = nested_get(preview_decode, "summary", "dims")
        if dims != [[1024, 768]]:
            failures.append("preview_decode_receipt summary.dims must be [[1024, 768]]")
        ok, failure = number_at_least(
            nested_get(preview_decode, "summary", "decode_plus_target") or {},
            "fps_median",
            20.0,
        )
        if not ok:
            failures.append(f"preview_decode_receipt summary.decode_plus_target.{failure}")
        ok, failure = number_at_least(preview_decode.get("summary", {}), "actual_wall_fps_including_extract_process", 20.0)
        if not ok:
            failures.append(f"preview_decode_receipt summary.{failure}")

    if preview is not None:
        if preview.get("schema") != "gpr_labs_preview_ui_receipt.v1":
            failures.append("preview_ui_receipt schema must be gpr_labs_preview_ui_receipt.v1")
        if nested_get(preview, "source_provenance", "available") is not True:
            failures.append("preview_ui_receipt source_provenance.available must be true")
        if not valid_hash_value(nested_get(preview, "source_provenance", "sha256")):
            failures.append("preview_ui_receipt source_provenance.sha256 must be a 64-hex hash")
        if nested_get(preview, "target", "role") != "camera":
            failures.append("preview_ui_receipt target.role must be camera")
        if nested_get(preview, "verdict", "ui_ready") is not True:
            failures.append("preview_ui_receipt verdict.ui_ready must be true")
        if nested_get(preview, "verdict", "fps_target_met") is not True:
            failures.append("preview_ui_receipt verdict.fps_target_met must be true")
        if nested_get(preview, "integration", "ui_path_executed") is not True:
            failures.append("preview_ui_receipt integration.ui_path_executed must be true")
        for key in ("output_valid", "no_drops", "visual_checked"):
            if nested_get(preview, "validation", key) is not True:
                failures.append(f"preview_ui_receipt validation.{key} must be true")
        if nested_get(preview, "source", "gvid_sha256") != row.get("gvid_sha256"):
            failures.append("preview_ui_receipt source.gvid_sha256 must match submitted gvid_sha256")
        for group, key, expected in (
            ("source", "width", 4096),
            ("source", "height", 3072),
            ("preview", "width", 1024),
            ("preview", "height", 768),
        ):
            ok, failure = number_equals(preview.get(group, {}), key, expected)
            if not ok:
                failures.append(f"preview_ui_receipt {group}.{failure}")
        if nested_get(preview, "preview", "full_frame_downsample") is not True:
            failures.append("preview_ui_receipt preview.full_frame_downsample must be true")
        preview_source_frames = numeric_value(nested_get(preview, "source", "frame_count"))
        preview_frames = numeric_value(nested_get(preview, "preview", "frame_count"))
        decode_frames = numeric_value(preview_decode.get("frame_count")) if preview_decode is not None else None
        target_frames = numeric_value(nested_get(target_bench or {}, "capture", "frames_written"))
        if preview_source_frames is None or preview_source_frames < CAMERA_ROLE_MIN_SUSTAINED_FRAMES:
            failures.append(f"preview_ui_receipt source.frame_count must be >= {CAMERA_ROLE_MIN_SUSTAINED_FRAMES}")
        if preview_frames is None or preview_frames < CAMERA_ROLE_MIN_SUSTAINED_FRAMES:
            failures.append(f"preview_ui_receipt preview.frame_count must be >= {CAMERA_ROLE_MIN_SUSTAINED_FRAMES}")
        if preview_source_frames is not None and preview_frames is not None and int(preview_source_frames) != int(preview_frames):
            failures.append("preview_ui_receipt preview.frame_count must match source.frame_count")
        if decode_frames is not None and preview_frames is not None and int(decode_frames) != int(preview_frames):
            failures.append("preview_ui_receipt preview.frame_count must match preview_decode_receipt frame_count")
        if target_frames is not None and preview_frames is not None and int(target_frames) != int(preview_frames):
            failures.append("preview_ui_receipt preview.frame_count must match labs_target_bench capture.frames_written")
        for key, expected in (("width", 1024), ("height", 768)):
            ok, failure = number_equals(preview.get("preview", {}), key, expected)
            if not ok:
                failures.append(f"preview_ui_receipt preview.{failure}")
        ok, failure = number_at_least(preview.get("timing", {}), "fps_median", 20.0)
        if not ok:
            failures.append(f"preview_ui_receipt timing.{failure}")

    if target_bench is not None and handoff is not None and preview is not None:
        target_source_sha = nested_get(target_bench, "source_provenance", "sha256")
        handoff_source_sha = nested_get(handoff, "source_provenance", "sha256")
        preview_source_sha = nested_get(preview, "source_provenance", "sha256")
        if target_source_sha != handoff_source_sha:
            failures.append("labs_target_bench source_provenance.sha256 must match camera_handoff_receipt")
        if preview_source_sha != handoff_source_sha:
            failures.append("preview_ui_receipt source_provenance.sha256 must match camera_handoff_receipt")

    if closure is not None:
        if closure.get("schema") != "gpr.mission1_camera_closure_run.v1":
            failures.append("mission1_camera_closure_run schema must be gpr.mission1_camera_closure_run.v1")
        closure_receipts = closure.get("receipts") if isinstance(closure.get("receipts"), dict) else {}
        expected_refs = {
            "target_bench": receipt_path(receipts, "labs_target_bench"),
            "target_preflight": receipt_path(receipts, "target_preflight_receipt"),
            "camera_handoff": receipt_path(receipts, "camera_handoff_receipt"),
            "preview_decode": receipt_path(receipts, "preview_decode_receipt"),
            "preview_ui": receipt_path(receipts, "preview_ui_receipt"),
        }
        for key, expected in expected_refs.items():
            if closure_receipts.get(key) != expected:
                failures.append(f"mission1_camera_closure_run receipts.{key} must match submitted {key} receipt path")
        steps = closure.get("steps")
        if not isinstance(steps, list):
            failures.append("mission1_camera_closure_run steps must be a list")
            steps = []
        step_by_name = {step.get("name"): step for step in steps if isinstance(step, dict)}
        for name in ("validate_camera_handoff_receipt", "validate_preview_ui_receipt"):
            step = step_by_name.get(name)
            if not isinstance(step, dict):
                failures.append(f"mission1_camera_closure_run steps must include {name}")
            elif step.get("returncode") != 0:
                failures.append(f"mission1_camera_closure_run {name} must return 0")
        for key in (
            "production_ready",
            "target_preflight_ready",
            "camera_closure_possible",
            "firmware_ready",
            "ui_ready",
            "aggregate_consistency_ready",
        ):
            if nested_get(closure, "verdict", key) is not True:
                failures.append(f"mission1_camera_closure_run verdict.{key} must be true")
        if nested_get(closure, "verdict", "handoff_blocker") not in (None, ""):
            failures.append("mission1_camera_closure_run verdict.handoff_blocker must be empty")
        if nested_get(closure, "verdict", "preview_blocker") not in (None, ""):
            failures.append("mission1_camera_closure_run verdict.preview_blocker must be empty")


def validate_camera_role_receipts(
    rid: str,
    submission: dict[str, Any],
    *,
    require_existing_files: bool = False,
    path_root: Path | None = None,
) -> dict[str, Any]:
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
        if require_existing_files and not receipt.get("path"):
            failures.append(f"{name} receipt needs path in strict mode")
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
    validate_camera_storage_medium_label(row, failures)
    if row.get("preview_full_frame") is not True:
        failures.append("preview_full_frame must be true")
    if require_existing_files:
        validate_strict_camera_role_receipt_content(row, path_root=path_root, failures=failures)
    if failures:
        return fail_result(rid, failures, len(receipts))
    return pass_result(rid, "camera-role encode, storage, and preview receipts pass", len(receipts))


def validate_strict_psf_pair_receipts(
    pair: dict[str, Any],
    pair_id: str,
    path_root: Path | None,
    failures: list[str],
) -> None:
    settings = load_local_json(pair.get("settings_receipt_path"), path_root, failures, f"pair {pair_id} settings_receipt")
    if settings is not None:
        if settings.get("schema") != PSF_PAIR_SETTINGS_SCHEMA:
            failures.append(f"pair {pair_id} settings_receipt schema must be {PSF_PAIR_SETTINGS_SCHEMA}")
        if settings.get("pair_id") != pair_id:
            failures.append(f"pair {pair_id} settings_receipt pair_id must match")
        for key in PSF_FIXED_SETTING_FIELDS:
            if str(settings.get(key)) != str(pair.get(key)):
                failures.append(f"pair {pair_id} settings_receipt {key} must match submitted pair")
        if settings.get("fixed_settings") is not True:
            failures.append(f"pair {pair_id} settings_receipt fixed_settings must be true")
        for key in (
            "high_source_sha256",
            "low_source_sha256",
            "high_bayer_sha256",
            "low_bayer_sha256",
        ):
            if settings.get(key) != pair.get(key):
                failures.append(f"pair {pair_id} settings_receipt {key} must match submitted pair")

    measurement = load_local_json(
        pair.get("measurement_receipt_path"),
        path_root,
        failures,
        f"pair {pair_id} measurement_receipt",
    )
    if measurement is None:
        return
    if measurement.get("schema") != PSF_PAIR_MEASUREMENT_SCHEMA:
        failures.append(f"pair {pair_id} measurement_receipt schema must be {PSF_PAIR_MEASUREMENT_SCHEMA}")
    if measurement.get("pair_id") != pair_id:
        failures.append(f"pair {pair_id} measurement_receipt pair_id must match")
    if measurement.get("high_bayer_sha256") != pair.get("high_bayer_sha256"):
        failures.append(f"pair {pair_id} measurement_receipt high_bayer_sha256 must match submitted pair")
    if measurement.get("low_bayer_sha256") != pair.get("low_bayer_sha256"):
        failures.append(f"pair {pair_id} measurement_receipt low_bayer_sha256 must match submitted pair")
    for key, expected in (
        ("high_width", PSF_HIGH_DIMS[0]),
        ("high_height", PSF_HIGH_DIMS[1]),
        ("low_width", PSF_LOW_DIMS[0]),
        ("low_height", PSF_LOW_DIMS[1]),
        ("high_bayer_bytes", PSF_HIGH_BYTES),
        ("low_bayer_bytes", PSF_LOW_BYTES),
    ):
        ok, failure = number_equals(measurement, key, expected)
        if not ok:
            failures.append(f"pair {pair_id} measurement_receipt {failure}")
    if pair.get("negative_control") is True:
        if measurement.get("rejected_by_measurement") is not True:
            failures.append(f"pair {pair_id} measurement_receipt rejected_by_measurement must be true")
        if not measurement.get("rejection_reason"):
            failures.append(f"pair {pair_id} measurement_receipt rejection_reason must be present")
    else:
        if measurement.get("accepted_by_measurement") is not True:
            failures.append(f"pair {pair_id} measurement_receipt accepted_by_measurement must be true")
        if nested_get(measurement, "alignment", "accepted_for_kernel") is not True:
            failures.append(f"pair {pair_id} measurement_receipt alignment.accepted_for_kernel must be true")
        ok, failure = number_greater_than(measurement.get("tile_summary", {}), "sharp_edge_tile_count", 0)
        if not ok:
            failures.append(f"pair {pair_id} measurement_receipt tile_summary.{failure}")
        ok, failure = number_greater_than(measurement.get("tile_summary", {}), "texture_field_tile_count", 0)
        if not ok:
            failures.append(f"pair {pair_id} measurement_receipt tile_summary.{failure}")


def validate_psf_pairs(
    rid: str,
    req: dict[str, Any],
    submission: dict[str, Any],
    *,
    require_existing_files: bool = False,
    path_root: Path | None = None,
) -> dict[str, Any]:
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
            "settings_receipt_path",
            "settings_receipt_sha256",
            "measurement_receipt_path",
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
        if require_existing_files:
            validate_strict_psf_pair_receipts(pair, pair_id, path_root, failures)
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


def valid_hash_value(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA_RE.match(value))


def validate_premium_smoke_receipt(
    row: dict[str, Any],
    *,
    holdout: str,
    path_key: str,
    path_root: Path | None,
    failures: list[str],
) -> None:
    receipt = load_local_json(row.get(path_key), path_root, failures, path_key)
    if receipt is None:
        return
    label = holdout.lower()
    receipt_holdout = str(receipt.get("holdout") or receipt.get("camera") or "").lower()
    if label not in receipt_holdout:
        failures.append(f"{path_key} must identify {holdout} as the smoke holdout")
    if not receipt.get("baseline_comparison"):
        failures.append(f"{path_key} must include baseline_comparison")
    for key in ("checkpoint_hash", "training_config_hash"):
        if not valid_hash_value(receipt.get(key)):
            failures.append(f"{path_key} {key} must be a 64-hex hash")
    median = receipt.get("median_mae_reduction_pct")
    if median is None:
        median = receipt.get(f"{label}_smoke_median_mae_reduction_pct")
    worst = receipt.get("worst_row_mae_reduction_pct")
    if worst is None:
        worst = receipt.get(f"{label}_smoke_worst_row_mae_reduction_pct")
    ok, failure = number_greater_than({"value": median}, "value", 0)
    if not ok:
        failures.append(f"{path_key} median_mae_reduction_pct {failure.removeprefix('value ')}")
    ok, failure = number_at_least({"value": worst}, "value", 0)
    if not ok:
        failures.append(f"{path_key} worst_row_mae_reduction_pct {failure.removeprefix('value ')}")


def validate_premium_smoke_acceptance(
    acceptance: Any,
    *,
    label: str,
    failures: list[str],
) -> None:
    if not isinstance(acceptance, dict):
        failures.append(f"{label} missing smoke_gate_acceptance")
        return
    baseline = str(acceptance.get("baseline") or "").lower()
    if "same-color" not in baseline or "interpolation" not in baseline:
        failures.append(f"{label} smoke_gate_acceptance baseline must be same-color Bayer interpolation")
    holdouts = {str(item).lower() for item in as_list(acceptance.get("required_holdouts"))}
    missing = sorted(PREMIUM_REQUIRED_SMOKE_HOLDOUTS - holdouts)
    if missing:
        failures.append(f"{label} smoke_gate_acceptance missing holdout(s): " + ", ".join(missing))


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def runtime_input_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_")


def forbidden_runtime_inputs(runtime_inputs: list[str]) -> list[str]:
    forbidden_keys = {runtime_input_key(item) for item in PREMIUM_FORBIDDEN_RUNTIME_INPUTS}
    return sorted(item for item in runtime_inputs if runtime_input_key(item) in forbidden_keys)


def receipt_number(receipt: dict[str, Any], key: str) -> float | None:
    value = numeric_value(receipt.get(key))
    if value is not None:
        return value
    for group_key in ("performance", "timing", "memory"):
        group = receipt.get(group_key)
        if isinstance(group, dict):
            value = numeric_value(group.get(key))
            if value is not None:
                return value
    return None


def validate_premium_timing_memory_receipt(
    row: dict[str, Any],
    path_root: Path | None,
    failures: list[str],
) -> None:
    receipt = load_local_json(row.get("timing_memory_receipt_path"), path_root, failures, "timing_memory_receipt")
    if receipt is None:
        return
    if receipt.get("schema") != "gpr.premium_still_sr_timing_memory.v1":
        failures.append("timing_memory_receipt schema must be gpr.premium_still_sr_timing_memory.v1")
    for key in ("render_seconds_per_50mp_frame", "render_seconds_per_100mp_frame", "peak_rss_gb"):
        value = receipt_number(receipt, key)
        expected = numeric_value(row.get(key))
        if value is None:
            failures.append(f"timing_memory_receipt {key} must be numeric")
        elif value <= 0:
            failures.append(f"timing_memory_receipt {key} must be > 0")
        elif expected is not None and abs(value - expected) > max(1.0e-6, abs(expected) * 1.0e-6):
            failures.append(f"timing_memory_receipt {key} must match submitted {key}")


def validate_premium_noise_policy_receipt(
    row: dict[str, Any],
    path_root: Path | None,
    failures: list[str],
) -> None:
    receipt = load_local_json(row.get("noise_policy_receipt_path"), path_root, failures, "noise_policy_receipt")
    if receipt is None:
        return
    if receipt.get("schema") != "gpr.premium_still_sr_noise_policy_gate.v1":
        failures.append("noise_policy_receipt schema must be gpr.premium_still_sr_noise_policy_gate.v1")
    if receipt.get("production_ready") is not True:
        failures.append("noise_policy_receipt production_ready must be true")
    clean = receipt.get("clean_signal") if isinstance(receipt.get("clean_signal"), dict) else {}
    if clean.get("policy_pass") is not True:
        failures.append("noise_policy_receipt clean_signal.policy_pass must be true")
    row_count = numeric_value(clean.get("row_count"))
    rows_with_noise = numeric_value(clean.get("rows_with_noise_sidecars"))
    if row_count is None or row_count <= 0:
        failures.append("noise_policy_receipt clean_signal.row_count must be > 0")
    if rows_with_noise is None or rows_with_noise <= 0:
        failures.append("noise_policy_receipt clean_signal.rows_with_noise_sidecars must be > 0")
    if row_count is not None and rows_with_noise is not None and rows_with_noise < row_count:
        failures.append("noise_policy_receipt clean_signal.rows_with_noise_sidecars must cover every row")
    models = [item for item in as_list(receipt.get("model_receipts")) if isinstance(item, dict)]
    if not any(model.get("policy_pass") is True for model in models):
        failures.append("noise_policy_receipt needs at least one model receipt with policy_pass=true")
    blockers = receipt.get("blockers")
    if isinstance(blockers, list) and blockers:
        failures.append("noise_policy_receipt blockers must be empty for production submission")
    if row.get("noise_policy_exact_sidecars_only") is not True:
        failures.append("noise_policy_exact_sidecars_only must be true")
    if row.get("noise_policy_forbids_source_residual_noise") is not True:
        failures.append("noise_policy_forbids_source_residual_noise must be true")


def gate_bool(gate: dict[str, Any], group: str, key: str) -> Any:
    value = gate.get(group)
    if isinstance(value, dict):
        return value.get(key)
    return None


def gate_number(gate: dict[str, Any], group: str, key: str) -> float | None:
    value = gate.get(group)
    if not isinstance(value, dict):
        return None
    return numeric_value(value.get(key))


def validate_premium_gate_receipt(
    row: dict[str, Any],
    path_root: Path | None,
    failures: list[str],
) -> None:
    receipt = load_local_json(row.get("still_sr_gate_receipt_path"), path_root, failures, "still_sr_gate_receipt")
    if receipt is None:
        return
    for failure in validate_still_sr_gate(receipt):
        failures.append(f"still_sr_gate_receipt {failure}")
    if receipt.get("production_ready") is not True:
        failures.append("still_sr_gate_receipt production_ready must be true")
    if nested_get(receipt, "candidate", "checkpoint_sha256") != row.get("checkpoint_sha256"):
        failures.append("still_sr_gate_receipt candidate.checkpoint_sha256 must match submitted checkpoint_sha256")
    runtime_inputs = nested_get(receipt, "runtime_policy", "runtime_inputs")
    if isinstance(runtime_inputs, list) and set(str(item) for item in runtime_inputs) != set(row.get("runtime_inputs") or []):
        failures.append("still_sr_gate_receipt runtime_policy.runtime_inputs must match submitted runtime_inputs")
    if gate_bool(receipt, "runtime_policy", "no_ref_runtime") is not True:
        failures.append("still_sr_gate_receipt runtime_policy.no_ref_runtime must be true")
    if gate_bool(receipt, "runtime_policy", "forbidden_source_content_absent") is not True:
        failures.append("still_sr_gate_receipt runtime_policy.forbidden_source_content_absent must be true")
    for key in (
        "full_frame_gate_50mp_passed",
        "full_frame_gate_100mp_passed",
        "editor_latitude_passed",
        "beats_current_baseline",
    ):
        if gate_bool(receipt, "promotion_metrics", key) is not row.get(key):
            failures.append(f"still_sr_gate_receipt promotion_metrics.{key} must match submitted {key}")
    if gate_bool(receipt, "promotion_metrics", "severe_worst_row_failures") is not row.get("severe_worst_row_failures"):
        failures.append(
            "still_sr_gate_receipt promotion_metrics.severe_worst_row_failures must match submitted severe_worst_row_failures"
        )
    for key in (
        "full_frame_gate_50mp_row_count",
        "full_frame_gate_100mp_row_count",
        "median_mae_reduction_pct_50mp",
        "median_mae_reduction_pct_100mp",
        "worst_row_mae_reduction_pct_50mp",
        "worst_row_mae_reduction_pct_100mp",
    ):
        value = gate_number(receipt, "promotion_metrics", key)
        expected = numeric_value(row.get(key))
        if value is None:
            failures.append(f"still_sr_gate_receipt promotion_metrics.{key} must be numeric")
        elif expected is not None and abs(value - expected) > max(1.0e-6, abs(expected) * 1.0e-6):
            failures.append(f"still_sr_gate_receipt promotion_metrics.{key} must match submitted {key}")
    for key in ("render_seconds_per_50mp_frame", "render_seconds_per_100mp_frame", "peak_rss_gb"):
        value = gate_number(receipt, "performance", key)
        expected = numeric_value(row.get(key))
        if value is None:
            failures.append(f"still_sr_gate_receipt performance.{key} must be numeric")
        elif expected is not None and abs(value - expected) > max(1.0e-6, abs(expected) * 1.0e-6):
            failures.append(f"still_sr_gate_receipt performance.{key} must match submitted {key}")
    if gate_bool(receipt, "noise_policy", "exact_sidecars_only") is not True:
        failures.append("still_sr_gate_receipt noise_policy.exact_sidecars_only must be true")
    if gate_bool(receipt, "noise_policy", "forbids_source_residual_noise") is not True:
        failures.append("still_sr_gate_receipt noise_policy.forbids_source_residual_noise must be true")


def validate_premium_preflight_content(row: dict[str, Any], path_root: Path | None, failures: list[str]) -> None:
    manifest = load_local_json(
        row.get("candidate_preflight_manifest_path"),
        path_root,
        failures,
        "candidate_preflight_manifest",
    )
    if manifest is not None:
        if manifest.get("schema") != "gpr.premium_still_sr_candidate_preflight.v1":
            failures.append("candidate_preflight_manifest schema must be gpr.premium_still_sr_candidate_preflight.v1")
        if manifest.get("launchable_for_production_attempt") is not True:
            failures.append("candidate_preflight_manifest launchable_for_production_attempt must be true")
        validate_premium_smoke_acceptance(
            manifest.get("smoke_gate_acceptance"),
            label="candidate_preflight_manifest",
            failures=failures,
        )

    audit = load_local_json(
        row.get("candidate_preflight_audit_path"),
        path_root,
        failures,
        "candidate_preflight_audit",
    )
    if audit is not None:
        if audit.get("schema") != "gpr.premium_still_sr_candidate_preflight_audit.v1":
            failures.append("candidate_preflight_audit schema must be gpr.premium_still_sr_candidate_preflight_audit.v1")
        if audit.get("launchable_for_production_attempt") is not True:
            failures.append("candidate_preflight_audit launchable_for_production_attempt must be true")
        if audit.get("verdict") != "launchable_preflight_passed":
            failures.append("candidate_preflight_audit verdict must be launchable_preflight_passed")
        if audit.get("production_ready") is True or audit.get("promotion_claimed") is True:
            failures.append("candidate_preflight_audit must not claim production readiness or promotion")
        validate_premium_smoke_acceptance(
            audit.get("smoke_gate_acceptance"),
            label="candidate_preflight_audit",
            failures=failures,
        )

    packet = load_local_json(row.get("launch_packet_path"), path_root, failures, "launch_packet")
    if packet is not None:
        if packet.get("schema") != "gpr.premium_still_sr_launch_packet.v1":
            failures.append("launch_packet schema must be gpr.premium_still_sr_launch_packet.v1")
        preflight = packet.get("preflight") if isinstance(packet.get("preflight"), dict) else {}
        if preflight.get("launchable_for_production_attempt") is not True:
            failures.append("launch_packet preflight.launchable_for_production_attempt must be true")
        if preflight.get("verdict") != "launchable_preflight_passed":
            failures.append("launch_packet preflight.verdict must be launchable_preflight_passed")

    baseline = load_local_json(row.get("baseline_comparison_path"), path_root, failures, "baseline_comparison")
    if baseline is not None:
        baseline_name = str(baseline.get("baseline") or "").lower()
        if "same-color" not in baseline_name or "interpolation" not in baseline_name:
            failures.append("baseline_comparison baseline must be same-color Bayer interpolation")
        holdouts = {str(item).lower() for item in as_list(baseline.get("holdouts"))}
        missing = sorted(PREMIUM_REQUIRED_SMOKE_HOLDOUTS - holdouts)
        if missing:
            failures.append("baseline_comparison missing holdout(s): " + ", ".join(missing))

    validate_premium_smoke_receipt(
        row,
        holdout="X2D",
        path_key="x2d_smoke_receipt_path",
        path_root=path_root,
        failures=failures,
    )
    validate_premium_smoke_receipt(
        row,
        holdout="Z8",
        path_key="z8_smoke_receipt_path",
        path_root=path_root,
        failures=failures,
    )
    validate_premium_timing_memory_receipt(row, path_root, failures)
    validate_premium_noise_policy_receipt(row, path_root, failures)
    validate_premium_gate_receipt(row, path_root, failures)


def validate_premium_still_sr(
    rid: str,
    submission: dict[str, Any],
    *,
    require_existing_files: bool = False,
    path_root: Path | None = None,
) -> dict[str, Any]:
    row = record_for(submission, rid)
    required_hashes = [
        "candidate_preflight_manifest_sha256",
        "candidate_preflight_audit_sha256",
        "launch_packet_sha256",
        "x2d_smoke_receipt_sha256",
        "z8_smoke_receipt_sha256",
        "baseline_comparison_sha256",
        "still_sr_gate_receipt_sha256",
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
        forbidden_runtime = forbidden_runtime_inputs(runtime_inputs)
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
    if require_existing_files:
        validate_premium_preflight_content(row, path_root, failures)
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
        return validate_camera_role_receipts(
            rid,
            submission,
            require_existing_files=require_existing_files,
            path_root=path_root,
        )
    if sample_type == "controlled_same_scene_high_low_raw_pair_stack":
        return validate_psf_pairs(
            rid,
            req,
            submission,
            require_existing_files=require_existing_files,
            path_root=path_root,
        )
    if sample_type == "model_promotion_receipt":
        return validate_premium_still_sr(
            rid,
            submission,
            require_existing_files=require_existing_files,
            path_root=path_root,
        )
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
