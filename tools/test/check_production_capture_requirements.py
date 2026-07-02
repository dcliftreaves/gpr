#!/usr/bin/env python3
"""Validate the committed production capture requirements contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REQ_PATH = ROOT / "docs" / "PRODUCTION_CAPTURE_REQUIREMENTS.json"
DOC_PATH = ROOT / "docs" / "PRODUCTION_CAPTURE_REQUIREMENTS.md"

EXPECTED_SCHEMA = "gpr.production_capture_requirements.v1"
EXPECTED_ROOT = "/Volumes/OWC_8TB/gpr_work"
EXPECTED_IDS = {
    "real_grbg_fixture": ("raw_stills", "real_camera_raw_fixture"),
    "real_bggr_fixture": ("raw_stills", "real_camera_raw_fixture"),
    "mission1_darkframe_stack": ("raw_stills", "darkframe_stack"),
    "iphone_cfa_darkframe_stack": ("raw_stills", "darkframe_stack"),
    "mission1_camera_role_receipts": ("raw_video_mvp", "camera_hardware_receipt"),
    "premium_still_sr_promotion_receipts": ("premium_still_sr", "model_promotion_receipt"),
}
OPTIONAL_RESEARCH_IDS = {
    "controlled_mission1_psf_pairs": ("raw_video_psf_research", "controlled_same_scene_high_low_raw_pair_stack"),
}
EXPECTED_PILLARS = {"raw_stills", "raw_video_mvp", "premium_still_sr"}
VALID_STATUSES = {"open", "closed", "blocked_on_real_camera_access", "research_optional"}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate() -> list[str]:
    failures: list[str] = []
    if not REQ_PATH.is_file():
        return [f"missing {display_path(REQ_PATH)}"]
    if not DOC_PATH.is_file():
        failures.append(f"missing {display_path(DOC_PATH)}")

    try:
        data = json.loads(REQ_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{display_path(REQ_PATH)} is invalid JSON: {exc}"]

    if data.get("schema") != EXPECTED_SCHEMA:
        failures.append(f"schema is {data.get('schema')!r}, expected {EXPECTED_SCHEMA!r}")
    if data.get("external_artifact_root") != EXPECTED_ROOT:
        failures.append(f"external_artifact_root must be {EXPECTED_ROOT}")

    rows = as_list(data.get("requirements"))
    by_id: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            failures.append(f"requirements[{idx}] must be an object")
            continue
        rid = str(row.get("id") or "")
        if not rid:
            failures.append(f"requirements[{idx}] missing id")
            continue
        if rid in by_id:
            failures.append(f"duplicate requirement id {rid!r}")
        by_id[rid] = row

    known_ids = set(EXPECTED_IDS) | set(OPTIONAL_RESEARCH_IDS)
    missing = sorted(set(EXPECTED_IDS) - set(by_id))
    extra = sorted(set(by_id) - known_ids)
    for rid in missing:
        failures.append(f"missing required requirement {rid!r}")
    for rid in extra:
        failures.append(f"unexpected requirement {rid!r}; update the guard if this is intentional")

    seen_pillars: set[str] = set()
    for rid, (expected_pillar, expected_type) in {**EXPECTED_IDS, **OPTIONAL_RESEARCH_IDS}.items():
        row = by_id.get(rid)
        if not row:
            continue
        pillar = row.get("pillar")
        sample_type = row.get("sample_type")
        status = row.get("status")
        priority = row.get("priority")
        if rid in EXPECTED_IDS:
            seen_pillars.add(str(pillar))
        if pillar != expected_pillar:
            failures.append(f"{rid}: pillar is {pillar!r}, expected {expected_pillar!r}")
        if sample_type != expected_type:
            failures.append(f"{rid}: sample_type is {sample_type!r}, expected {expected_type!r}")
        expected_priority = "research_optional" if rid in OPTIONAL_RESEARCH_IDS else "required"
        if priority != expected_priority:
            failures.append(f"{rid}: priority must be {expected_priority}")
        if rid in OPTIONAL_RESEARCH_IDS and status != "research_optional":
            failures.append(f"{rid}: optional research requirement status must be research_optional")
        if status not in VALID_STATUSES:
            failures.append(f"{rid}: status {status!r} must be one of {sorted(VALID_STATUSES)}")
        if not row.get("why_needed"):
            failures.append(f"{rid}: missing why_needed")
        if not as_list(row.get("required_evidence")):
            failures.append(f"{rid}: missing required_evidence")
        if not as_list(row.get("acceptance")):
            failures.append(f"{rid}: missing acceptance")
        if not as_list(row.get("validation_commands")):
            failures.append(f"{rid}: missing validation_commands")

        if sample_type == "darkframe_stack" and int(row.get("minimum_count") or 0) < 4:
            failures.append(f"{rid}: darkframe stacks require minimum_count >= 4")
        if sample_type == "darkframe_stack":
            acceptance = " ".join(str(item) for item in as_list(row.get("acceptance")))
            commands = "\n".join(str(item) for item in as_list(row.get("validation_commands")))
            required_evidence = " ".join(str(item) for item in as_list(row.get("required_evidence")))
            if "source_provenance_ready=true" not in acceptance:
                failures.append(f"{rid}: darkframe acceptance must require source_provenance_ready=true")
            if "--require-source-provenance" not in commands:
                failures.append(f"{rid}: darkframe validation must require --require-source-provenance")
            if "--source-provenance-manifest" not in commands:
                failures.append(f"{rid}: darkframe validation must include --source-provenance-manifest")
            if "check_darkframe_source_provenance.py" not in commands:
                failures.append(f"{rid}: darkframe validation must include check_darkframe_source_provenance.py")
            if "source-provenance manifest" not in required_evidence:
                failures.append(f"{rid}: darkframe evidence must require a source-provenance manifest")
            if "gpr.darkframe_source_provenance_audit.v1" not in required_evidence:
                failures.append(f"{rid}: darkframe evidence must require a darkframe source-provenance audit")
        if sample_type == "real_camera_raw_fixture" and int(row.get("minimum_count") or 0) < 1:
            failures.append(f"{rid}: real fixtures require minimum_count >= 1")
        if sample_type == "camera_hardware_receipt":
            acceptance = " ".join(str(item) for item in as_list(row.get("acceptance")))
            required_evidence = " ".join(str(item) for item in as_list(row.get("required_evidence")))
            for token in (
                "source_width=4096",
                "source_height=3072",
                "preview_width=1024",
                "preview_height=768",
                "source_fps",
                "encode_fps",
                "preview_fps",
                "gvid_sha256",
                "storage_write_mb_s",
                "storage_budget_passed=true",
                "peak_rss_mb",
            ):
                if token not in required_evidence:
                    failures.append(f"{rid}: camera evidence must require {token}")
            if "source/write/preview/memory scalar fields" not in acceptance:
                failures.append(f"{rid}: camera acceptance must require source/write/preview/memory scalar fields")
        if sample_type == "controlled_same_scene_high_low_raw_pair_stack" and int(row.get("minimum_pair_count") or 0) < 3:
            failures.append(f"{rid}: PSF capture requires minimum_pair_count >= 3")
        if sample_type == "model_promotion_receipt":
            why_needed = str(row.get("why_needed") or "")
            commands = "\n".join(str(item) for item in as_list(row.get("validation_commands")))
            required_evidence = " ".join(str(item) for item in as_list(row.get("required_evidence")))
            acceptance = " ".join(str(item) for item in as_list(row.get("acceptance")))
            for token in (
                "X2D and Z8 smoke_gate_commands",
                "smoke_gate_acceptance",
                "/Volumes/OWC_8TB/gpr_work",
                "candidate raw",
                "camera metadata",
                "50 MP and 100 MP",
                "seconds per 50 MP frame",
                "seconds per 100 MP frame",
                "peak RSS",
                "source residual noise",
            ):
                if token not in required_evidence and token not in acceptance:
                    failures.append(f"{rid}: model promotion requirement must mention {token!r}")
            if "current no-REF residual/local-CNN models remain diagnostic" not in why_needed:
                failures.append(f"{rid}: why_needed must describe current residual/local-CNN models as diagnostic")
            if "check_premium_still_sr_candidate_preflight.py" not in commands:
                failures.append(f"{rid}: validation must include check_premium_still_sr_candidate_preflight.py")
            if "build_premium_still_sr_candidate_preflight_template.py" not in commands:
                failures.append(f"{rid}: validation must include build_premium_still_sr_candidate_preflight_template.py")
            if "build_premium_still_sr_launch_packet.py" not in commands:
                failures.append(f"{rid}: validation must include build_premium_still_sr_launch_packet.py")
            if "X2D and Z8 smoke_gate_commands" not in required_evidence + " " + acceptance:
                failures.append(f"{rid}: model promotion requirement must require concrete X2D and Z8 smoke_gate_commands")
            if "positive median MAE recovery" not in required_evidence + " " + acceptance:
                failures.append(f"{rid}: model promotion requirement must require positive smoke median MAE recovery")
            if "nonnegative worst-row MAE recovery" not in required_evidence + " " + acceptance:
                failures.append(f"{rid}: model promotion requirement must require nonnegative smoke worst-row MAE recovery")
            if "--manifest" not in commands:
                failures.append(f"{rid}: launch packet validation must require an explicit --manifest")
            if "--require-launchable" not in commands:
                failures.append(f"{rid}: candidate preflight must require --require-launchable")
            if "train_premium_still_sr_raw_cfa_residual.py --help" in commands:
                failures.append(f"{rid}: validation must not route the next action back to the stale raw-CFA residual trainer help command")

    if seen_pillars != EXPECTED_PILLARS:
        failures.append(f"pillars covered are {sorted(seen_pillars)}, expected {sorted(EXPECTED_PILLARS)}")

    if DOC_PATH.is_file():
        doc = DOC_PATH.read_text(encoding="utf-8")
        for token in (
            *EXPECTED_IDS.keys(),
            *OPTIONAL_RESEARCH_IDS.keys(),
            "Product pillar scorecard",
            "release of the approved current raw-video SR workflow",
            "Optional Research Requests",
            "optional PSF research pairs",
            "stills_capture_request_strict_provenance_20260701",
            "darkframe_provenance_review_packet_commands_20260702",
            "production_sidecar_ready=false",
            "source_provenance_manifest_templates",
            "promotion command path",
            "raw_video_psf_capture_request_20260630",
        ):
            if token not in doc:
                failures.append(f"{display_path(DOC_PATH)} missing {token!r}")
        forbidden_phrases = (
            "PSF pairs, and model-promotion receipts still needed",
            "PSF pairs still needed",
        )
        for phrase in forbidden_phrases:
            if phrase in doc:
                failures.append(
                    f"{display_path(DOC_PATH)} must not imply optional PSF pairs are release blockers: {phrase!r}"
                )

    return failures


def main() -> int:
    failures = validate()
    if failures:
        print("Production capture requirements check failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("OK - production capture requirements contract passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
