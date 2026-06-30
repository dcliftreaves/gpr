#!/usr/bin/env python3
"""Validate productization docs and governance contracts.

This is intentionally lightweight and CI-safe. It does not require external
artifacts, but it makes sure the four product pillars plus the release bundle,
Labs handoff, `.gvid` conformance, and CNN governance contracts remain
discoverable and testable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require_file(rel: str, failures: list[str]) -> None:
    if not (ROOT / rel).is_file():
        failures.append(f"missing required file: {rel}")


def require_text(rel: str, needles: list[str], failures: list[str]) -> None:
    path = ROOT / rel
    if not path.is_file():
        failures.append(f"missing required file: {rel}")
        return
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            failures.append(f"{rel}: missing required text {needle!r}")


def is_meta_key(name: str) -> bool:
    return name.startswith("$")


def shaish(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def production_pipeline(pipe: dict[str, Any]) -> bool:
    role = str(pipe.get("$role", ""))
    scope = pipe.get("production_scope")
    use_for = str(pipe.get("use_for", ""))
    return (
        role.startswith("ship-")
        or role.startswith("offline-production-")
        or scope in {"offline_production", "offline_review_only"}
        or "OFFLINE" in use_for
    )


def validate_registry(failures: list[str]) -> None:
    registry = json.loads((ROOT / "pipelines/registry.json").read_text(encoding="utf-8"))
    cnns = registry.get("cnns", {})

    for name, cnn in cnns.items():
        if is_meta_key(name) or name == "none":
            continue
        if not isinstance(cnn, dict):
            failures.append(f"cnn {name}: entry must be an object")
            continue
        for field in ("cnn_arch_variant", "trained_against_codec", "raw_norm"):
            if field not in cnn:
                failures.append(f"cnn {name}: missing governance field {field}")
        has_checkpoint = any(k.startswith("ckpt_") or k == "ckpt_path" for k in cnn)
        has_experts = isinstance(cnn.get("expert_checkpoints"), dict)
        if not has_checkpoint and not has_experts:
            failures.append(f"cnn {name}: missing checkpoint or expert checkpoint mapping")

    for pname, pipe in registry.get("pipelines", {}).items():
        if is_meta_key(pname) or not isinstance(pipe, dict) or not production_pipeline(pipe):
            continue
        cnn_name = pipe.get("cnn")
        if cnn_name == "none":
            continue
        cnn = cnns.get(cnn_name)
        if not isinstance(cnn, dict):
            failures.append(f"pipeline {pname}: unknown production CNN {cnn_name!r}")
            continue
        doc = str(pipe.get("$doc", ""))
        if "not a live-camera path" in doc or pipe.get("production_scope") in {"offline_review_only", "offline_production"}:
            if pipe.get("production_scope") not in {"offline_review_only", "offline_production"}:
                failures.append(f"pipeline {pname}: offline doc requires explicit production_scope")
        if str(pipe.get("codec", "")).startswith("mission1_native12") and cnn_name != "none":
            has_training = any(
                shaish(cnn.get(k))
                for k in (
                    "training_receipt_sha256",
                    "training_pairs_sha256",
                    "mission_broad_holdout_receipt_sha256",
                    "mission42_rgb_cfa_summary_sha256",
                )
            )
            has_promotion = any(
                shaish(cnn.get(k))
                for k in (
                    "promotion_review_decision_sha256",
                    "gvid_decode_sr_packaging_receipt_sha256",
                    "gvid_4k_packaging_receipt_sha256",
                )
            )
            if not has_training:
                failures.append(f"pipeline {pname}: Mission CNN lacks training/holdout hash")
            if not has_promotion:
                failures.append(f"pipeline {pname}: Mission CNN lacks promotion or packaging hash")


def main() -> int:
    failures: list[str] = []

    for rel in (
        "docs/PRODUCTIZATION_CONTRACTS.md",
        "docs/RELEASE_ARTIFACTS.md",
        "docs/GVID_CONFORMANCE.md",
        "docs/LABS_FIRMWARE_API.md",
        "docs/GOPRO_MISSION1_QUICK_VALIDATION.md",
        "docs/MISSION1_STREAM_SOURCE_TIMING_2026-06-28.md",
        "docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md",
        "docs/CNN_PRODUCT_SCORECARD_2026-06-29.md",
        "docs/LABS_ARTIFACT_BUNDLE.md",
        "docs/PRODUCTION_ARTIFACTS.md",
        "tools/verify_labs_bundle.py",
        "tools/build_labs_bundle.py",
        "tools/check_mission1_cnn_closure.py",
        "tools/build_cnn_product_scorecard.py",
        "tools/test/test_gvid_conformance.py",
        "source/lib/vc5_encoder/gpr_labs_encoder.h",
        "pipelines/registry.json",
    ):
        require_file(rel, failures)

    require_text("README.md", [
        "docs/PRODUCTIZATION_CONTRACTS.md",
        "docs/RELEASE_ARTIFACTS.md",
        "docs/GVID_CONFORMANCE.md",
        "docs/CNN_PRODUCT_SCORECARD_2026-06-29.md",
    ], failures)
    require_text("docs/README.md", [
        "PRODUCTIZATION_CONTRACTS.md",
        "RELEASE_ARTIFACTS.md",
        "GVID_CONFORMANCE.md",
    ], failures)
    require_text("docs/PRODUCTIZATION_CONTRACTS.md", [
        "best RAW stills for 50 MP and 100 MP cameras",
        "GoPro / Mission 1 RAW video MVP",
        "premium spend-time-for-quality still/SR",
        "PSF-aware RAW video cleanup and reconstruction",
        "docs/PRODUCT_PILLAR_SCORECARD.md",
        "docs/PRODUCT_LOCK_LEDGER.md",
        "Current Product Boundary",
        "4096 x 3072 Bayer `.gvid` encode",
        "accepted 20 fps Pi 5 stand-in floor",
        "Real Mission 1 camera-role sensor/DMA",
        "validated sidecars",
        "Mission 1 and iPhone remain metadata-conditioning-only",
        "continuous 8K no-CNN versus CNN ProRes review media",
        "recompressed Bayer payloads",
        "packed original camera files",
        "four product pillars and the cross-cutting",
    ], failures)
    require_text("docs/RELEASE_ARTIFACTS.md", [
        "gpr_labs_bundle.v1",
        "tools/build_labs_bundle.py",
        "tools/verify_labs_bundle.py",
        "gh release upload",
        "hashes/sha256sums.txt",
    ], failures)
    require_text("docs/LABS_FIRMWARE_API.md", [
        "ABI",
        "capability discovery",
        "install",
        "rollback",
        "gpr_labs_camera_handoff_receipt.v1",
        "gpr_labs_preview_ui_receipt.v1",
    ], failures)
    require_text("docs/GOPRO_MISSION1_QUICK_VALIDATION.md", [
        "Quick Camera Probe",
        "Quick Closure Run",
        "What We Can Do Without A Mission 1 Dev Kit",
        "target.role=camera",
    ], failures)
    require_text("docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md", [
        "4K cleanup",
        "8K SR",
        "offline-production",
        "Do not add CNN to camera-side encode",
        "python3 tools/check_mission1_cnn_closure.py",
    ], failures)
    require_text("docs/CNN_PRODUCT_SCORECARD_2026-06-29.md", [
        "CNN Product Scorecard",
        "mission1_native12_4k_cleanup_rgb_cfa_w40_v1",
        "mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1",
        "offline-production",
        "not a live-camera path",
        "real fixture compatibility",
        "python3 tools/build_cnn_product_scorecard.py",
    ], failures)
    require_text("docs/MISSION1_STREAM_SOURCE_TIMING_2026-06-28.md", [
        "file-backed shim baseline",
        "RAM mmap ring",
        "production FLL2 direct",
        "production_evidence=false",
    ], failures)
    require_text("docs/GVID_CONFORMANCE.md", [
        "python3 tools/test/test_gvid_conformance.py",
        "truncated frame header",
        "frame-count hint mismatches",
        "version bump",
    ], failures)

    validate_registry(failures)

    if failures:
        print("Productization contract guard failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Productization contract guard OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
