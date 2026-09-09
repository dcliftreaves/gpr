#!/usr/bin/env python3
"""Validate the current Mission 1 CNN/SR production closure contract.

Hosted CI validates tracked registry, docs, and manifest state. Local runs on a
machine with /Volumes/OWC_8TB/gpr_work also validate the private production
receipts that back the current 4K cleanup and 8K SR claims.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "pipelines/registry.json"
MANIFEST = ROOT / "docs/release_evidence_manifest.json"
CNN_DOC = ROOT / "docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md"

FOURK_CNN = "mission1_native12_4k_cleanup_rgb_cfa_w40_v1"
EIGHTK_CNN = "mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1"
FOURK_PIPE = f"codec=mission1_native12_t233+cnn={FOURK_CNN}+demosaic=sips_via_gpr_tools"
EIGHTK_PIPE = f"codec=mission1_native12_t233+cnn={EIGHTK_CNN}+demosaic=sips_via_gpr_tools"
FOURK_RECEIPT = "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
EIGHTK_RECEIPT = "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def shaish(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def validate_registry(failures: list[str]) -> None:
    registry = load_json(REGISTRY)
    cnns = registry.get("cnns")
    pipes = registry.get("pipelines")
    if not isinstance(cnns, dict):
        failures.append("pipelines/registry.json missing cnns object")
        return
    if not isinstance(pipes, dict):
        failures.append("pipelines/registry.json missing pipelines object")
        return

    fourk = cnns.get(FOURK_CNN)
    eightk = cnns.get(EIGHTK_CNN)
    fourk_pipe = pipes.get(FOURK_PIPE)
    eightk_pipe = pipes.get(EIGHTK_PIPE)

    require(isinstance(fourk, dict), failures, f"missing CNN registry entry {FOURK_CNN}")
    require(isinstance(eightk, dict), failures, f"missing CNN registry entry {EIGHTK_CNN}")
    require(isinstance(fourk_pipe, dict), failures, f"missing pipeline registry entry {FOURK_PIPE}")
    require(isinstance(eightk_pipe, dict), failures, f"missing pipeline registry entry {EIGHTK_PIPE}")
    if not all(isinstance(item, dict) for item in (fourk, eightk, fourk_pipe, eightk_pipe)):
        return

    assert isinstance(fourk, dict)
    assert isinstance(eightk, dict)
    assert isinstance(fourk_pipe, dict)
    assert isinstance(eightk_pipe, dict)

    require(
        fourk.get("status") == "review_only_visual_signed_off_camera_handoff_separate",
        failures,
        f"{FOURK_CNN} must stay visual-signed-off but offline/review-only",
    )
    require(
        fourk_pipe.get("production_scope") == "offline_review_only",
        failures,
        f"{FOURK_PIPE} must have production_scope=offline_review_only",
    )
    require(
        "until final visual signoff" not in str(fourk_pipe.get("$doc", "")),
        failures,
        f"{FOURK_PIPE} doc still claims final visual signoff is pending",
    )
    require(
        "not a live-camera path" in str(fourk_pipe.get("$doc", "")),
        failures,
        f"{FOURK_PIPE} doc must keep live-camera boundary explicit",
    )
    for key in (
        "ckpt_sha256",
        "training_receipt_sha256",
        "mission42_rgb_cfa_summary_sha256",
        "mission42_tone_audit_summary_sha256",
        "gvid_4k_packaging_receipt_sha256",
        "gvid_4k_to_prores_receipt_sha256",
    ):
        require(shaish(fourk.get(key)), failures, f"{FOURK_CNN}.{key} must be a sha256")

    require(
        eightk.get("status") == "offline_production_runtime_and_packaging_refreshed",
        failures,
        f"{EIGHTK_CNN} must be marked offline-production, not review-only",
    )
    require(
        eightk_pipe.get("production_scope") == "offline_production",
        failures,
        f"{EIGHTK_PIPE} must have production_scope=offline_production",
    )
    require(
        "not a live-camera path" in str(eightk_pipe.get("$doc", "")),
        failures,
        f"{EIGHTK_PIPE} doc must keep live-camera boundary explicit",
    )
    for key in (
        "ckpt_sha256",
        "training_pairs_sha256",
        "training_receipt_sha256",
        "mission_broad_holdout_receipt_sha256",
        "z8_regenerated_holdout_receipt_sha256",
        "gvid_decode_sr_multiframe_receipt_sha256",
        "gvid_decode_sr_packaging_receipt_sha256",
        "production_promotion_receipt_sha256",
    ):
        require(shaish(eightk.get(key)), failures, f"{EIGHTK_CNN}.{key} must be a sha256")


def validate_docs_and_manifest(failures: list[str]) -> None:
    doc = CNN_DOC.read_text(encoding="utf-8")
    for token in (
        "4K cleanup",
        FOURK_CNN,
        "8K SR",
        EIGHTK_CNN,
        "camera preview",
        "capture encode",
        "Do not add CNN to camera-side encode",
        "python3 tools/check_mission1_cnn_closure.py",
    ):
        require(token in doc, failures, f"{CNN_DOC.relative_to(ROOT)} missing {token!r}")

    manifest = load_json(MANIFEST)
    for section in ("release_checks", "ci_checks"):
        checks = manifest.get(section)
        require(isinstance(checks, list), failures, f"manifest {section} must be a list")
        if isinstance(checks, list):
            closure_checks = [
                check for check in checks
                if isinstance(check, str) and check.startswith("python3 tools/check_mission1_cnn_closure.py")
            ]
            require(
                bool(closure_checks),
                failures,
                f"manifest {section} must include Mission 1 CNN closure guard",
            )
            require(
                "python3 tools/test/test_check_mission1_cnn_closure.py" in checks,
                failures,
                f"manifest {section} must include Mission 1 CNN closure guard regression",
            )


def default_external_root() -> Path | None:
    env = os.environ.get("GPR_EXTERNAL_ROOT")
    if env:
        return Path(env)
    default = Path("/Volumes/OWC_8TB/gpr_work")
    if default.exists():
        return default
    return None


def validate_external_receipts(external_root: Path | None, strict: bool, failures: list[str]) -> None:
    if external_root is None:
        if strict:
            failures.append("strict artifact validation requested but no external root is available")
        return

    from check_mission1_4k_cleanup_signoff_receipt import validate_receipt as validate_4k
    from check_mission1_8k_sr_production_promotion import validate_receipt as validate_8k

    for rel, validator, label in (
        (FOURK_RECEIPT, validate_4k, "4K cleanup production signoff"),
        (EIGHTK_RECEIPT, validate_8k, "8K SR production promotion"),
    ):
        path = external_root / rel
        if not path.is_file():
            if strict:
                failures.append(f"missing external {label} receipt: {path}")
            continue
        receipt = load_json(path)
        errors = validator(receipt)
        failures.extend(f"{label}: {error}" for error in errors)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=default_external_root())
    ap.add_argument("--strict-artifacts", action="store_true")
    args = ap.parse_args()

    failures: list[str] = []
    validate_registry(failures)
    validate_docs_and_manifest(failures)
    validate_external_receipts(args.external_root, args.strict_artifacts, failures)

    if failures:
        print("Mission 1 CNN closure guard failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1
    artifact_mode = "strict" if args.strict_artifacts else "best-effort"
    root = str(args.external_root) if args.external_root else "none"
    print(f"Mission 1 CNN closure guard OK (external_root={root}, artifacts={artifact_mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
