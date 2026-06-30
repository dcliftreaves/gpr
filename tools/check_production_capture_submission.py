#!/usr/bin/env python3
"""Validate a submitted production-capture evidence manifest.

The committed requirements list says what samples and receipts are still
needed. This checker validates a concrete submission manifest against those
requirements without needing private raw files in CI.
"""
from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("submission", type=Path, help="gpr.production_capture_submission.v1 manifest")
    ap.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--html-out", type=Path)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


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


def validate_darkframe_stack(rid: str, req: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    min_count = int(req.get("minimum_count") or 4)
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
        "exposure",
        "extract_receipt_sha256",
    ]
    failures: list[str] = []
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows_for(submission, rid):
        local = missing_fields(row, required)
        if local:
            failures.append(f"darkframe missing {', '.join(local)}")
            continue
        if not has_sha(row) or not has_sha(row, "extract_receipt_sha256"):
            failures.append("darkframe source and extraction receipt hashes must be 64 hex characters")
            continue
        if row.get("no_scene_signal") is not True:
            failures.append("darkframe must set no_scene_signal=true")
            continue
        if rid == "iphone_cfa_darkframe_stack" and row.get("linear_raw") is True:
            failures.append("iPhone darkframes must be CFA raw, not Linear Raw")
            continue
        grouped.setdefault(darkframe_key(row), []).append(row)

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
    if float(row.get("encode_fps") or 0.0) < 20.0:
        failures.append("encode_fps must be >= 20")
    if float(row.get("preview_fps") or 0.0) < 20.0:
        failures.append("preview_fps must be >= 20")
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
        for key in ("high_source_sha256", "low_source_sha256", "high_bayer_sha256", "low_bayer_sha256"):
            if not has_sha(pair, key):
                failures.append(f"pair {pair.get('id') or ''} missing valid {key}")
        if pair.get("negative_control") is True:
            if pair.get("expected_reject") is True:
                negative_controls += 1
            continue
        if pair.get("fixed_settings") is not True:
            failures.append(f"pair {pair.get('id') or ''} must set fixed_settings=true")
            continue
        if pair.get("static_scene") is not True:
            failures.append(f"pair {pair.get('id') or ''} must set static_scene=true")
            continue
        if pair.get("accepted_by_measurement") is not True:
            failures.append(f"pair {pair.get('id') or ''} must set accepted_by_measurement=true")
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
        "checkpoint_sha256",
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
    ]
    for key in required_true:
        if row.get(key) is not True:
            failures.append(f"{key} must be true")
    if row.get("severe_worst_row_failures") is not False:
        failures.append("severe_worst_row_failures must be false")
    if failures:
        return fail_result(rid, failures, 1 if row else 0)
    return pass_result(rid, "premium still-SR promotion evidence passes manifest checks", 1)


def validate_requirement(req: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    rid = str(req.get("id") or "")
    sample_type = req.get("sample_type")
    if sample_type == "real_camera_raw_fixture":
        return validate_real_fixture(rid, req, submission)
    if sample_type == "darkframe_stack":
        return validate_darkframe_stack(rid, req, submission)
    if sample_type == "camera_hardware_receipt":
        return validate_camera_role_receipts(rid, submission)
    if sample_type == "controlled_same_scene_high_low_raw_pair_stack":
        return validate_psf_pairs(rid, req, submission)
    if sample_type == "model_promotion_receipt":
        return validate_premium_still_sr(rid, submission)
    return fail_result(rid, [f"unsupported requirement sample_type {sample_type!r}"])


def build_audit(requirements: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if submission.get("schema") != SUBMISSION_SCHEMA:
        failures.append(f"submission schema must be {SUBMISSION_SCHEMA}")
    req_rows = [row for row in as_list(requirements.get("requirements")) if isinstance(row, dict)]
    results = [validate_requirement(row, submission) for row in req_rows]
    pass_count = sum(1 for row in results if row["status"] == "PASS")
    return {
        "schema": SCHEMA,
        "requirements_schema": requirements.get("schema"),
        "submission_schema": submission.get("schema"),
        "all_requirements_closed": not failures and pass_count == len(results),
        "pass_count": pass_count,
        "fail_count": len(results) - pass_count + len(failures),
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
<section class="card"><div class="label">Pass</div><div class="value">{audit["pass_count"]}</div></section>
<section class="card"><div class="label">Fail</div><div class="value">{audit["fail_count"]}</div></section>
</div>
<ul>{manifest_failures}</ul>
<table><thead><tr><th>Status</th><th>Requirement</th><th>Evidence</th><th>Message</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    try:
        audit = build_audit(load_json(args.requirements), load_json(args.submission))
    except Exception as exc:
        print(f"check_production_capture_submission: {exc}", file=sys.stderr)
        return 2
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.html_out:
        args.html_out.parent.mkdir(parents=True, exist_ok=True)
        args.html_out.write_text(render_html(audit), encoding="utf-8")
    if not audit["all_requirements_closed"]:
        print("Production capture submission is incomplete:")
        for failure in audit["manifest_failures"]:
            print(f"  - {failure}")
        for row in audit["results"]:
            if row["status"] != "PASS":
                print(f"  - {row['id']}: {row['message']}")
        return 1
    print("OK - production capture submission closes all committed requirements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
