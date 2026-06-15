#!/usr/bin/env python3
"""CI-safe guard for the Labs firmware-intake evidence contract.

This intentionally does not verify large external media. It keeps the
firmware-intake docs, release manifest, and CI workflow aligned on the current
state: `.gvid` review is ready for Labs exploration, 2K decode/display has a
passing Pi-side target, and sustained half-res capture remains blocked until a
new target receipt proves otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/release_evidence_manifest.json"
CI = ROOT / ".github/workflows/ci.yml"
TARGET_CI = ROOT / ".github/workflows/labs-target.yml"
CMAKE = ROOT / "CMakeLists.txt"

REQUIRED_DOCS = {
    "docs/LABS_READINESS_GOAL.md": [
        "Stop Criteria",
        "Current Blocker",
        "Immediate Next Step",
        "Pass1/highpass",
        "24 fps",
        "current-head direct",
        "16.00 fps",
    ],
    "docs/LABS_INTAKE.md": [
        "What Ships In The Prototype",
        "What Does Not Ship In The Prototype",
        "Half-res 24 fps capture target",
        "19.98 fps",
        "23.54 fps",
        "luma-pair",
        "2K live/camera-back preview",
        "2k_raw_0p5x_l2hh",
    ],
    "docs/LABS_FIRMWARE_API.md": [
        "Input Frame Contract",
        "Memory Ownership",
        "Backpressure And Drops",
        "Partial-File Recovery",
        "Target Bench Requirements",
    ],
    "docs/LABS_TARGET_BENCH.md": [
        "Current Evidence",
        "Required Target Run",
        "Timing-Diagnostic Build",
        "FUSED_TIMING_DETAIL",
        "fused_timing",
        "Current Gap",
        "19.98 fps",
        "23.54 fps",
        "luma-pair",
        "current-head direct",
        "16.00 fps",
        "2k_raw_0p5x_l2hh",
    ],
    "docs/LABS_ARTIFACT_BUNDLE.md": [
        "Bundle Layout",
        "Required Manifest Fields",
        "Verification Commands",
        "Current Bundle",
        "zero-frame",
        "out-of-order",
    ],
    "docs/LABS_CI_PLAN.md": [
        "Hosted CI",
        "Target Or Self-Hosted CI",
        ".github/workflows/labs-target.yml",
        "gpr-labs-pi5",
        "Skip Policy",
        "not a pass for firmware readiness",
    ],
    "docs/LABS_READINESS_REVIEW.md": [
        "Decision",
        "Ready Now",
        "Not Ready Yet",
        "Current Risk",
        "Next Work",
        "fused_timing",
        "zero-frame",
        "out-of-order",
        "current-head direct",
        "16.00 fps",
    ],
    "docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md": [
        "Highpass Lower-Bound Probe",
        "Quality Env And Quant Probe",
        "U16 Log-Scratch Candidate",
        "Prescale-2 Fixed-Shift Candidate",
        "Timing Profile",
        "Reproducible Timing Build",
        "FUSED_TIMING_DETAIL",
        "fused_timing",
        "23.54 fps",
        "luma-pair",
        "Current-Head Direct Rehearsal",
        "16.00 fps",
    ],
}

REQUIRED_MANIFEST_DOC_REFS = {
    "docs/LABS_INTAKE.md",
    "docs/LABS_TARGET_BENCH.md",
    "docs/LABS_READINESS_REVIEW.md",
    "docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md",
}


def tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def load_manifest() -> dict[str, Any]:
    with MANIFEST.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError("release evidence manifest must be a JSON object")
    return data


def entries_by_id(entries: object) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            out[entry["id"]] = entry
    return out


def require_docs(tracked: set[str], failures: list[str]) -> None:
    for rel, tokens in REQUIRED_DOCS.items():
        path = ROOT / rel
        if rel not in tracked:
            failures.append(f"{rel} must be tracked")
            continue
        if not path.exists():
            failures.append(f"{rel} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                failures.append(f"{rel} missing Labs contract token {token!r}")


def require_manifest_contract(manifest: dict[str, Any], failures: list[str]) -> None:
    platform = entries_by_id(manifest.get("platform_performance"))
    raw_targets = entries_by_id(manifest.get("raw_targets"))
    production_paths = entries_by_id(manifest.get("production_paths"))

    capture = platform.get("pi5_mission1_halfres_capture")
    if not capture:
        failures.append("manifest missing platform_performance pi5_mission1_halfres_capture")
    else:
        if capture.get("status") != "blocked":
            failures.append("pi5_mission1_halfres_capture must remain blocked until a passing target receipt exists")
        metrics = capture.get("metrics")
        if not isinstance(metrics, dict):
            failures.append("pi5_mission1_halfres_capture needs metrics")
        else:
            try:
                fps = float(metrics.get("fps_median"))
                target = float(metrics.get("target_fps"))
            except (TypeError, ValueError):
                failures.append("pi5_mission1_halfres_capture needs numeric fps_median and target_fps")
            else:
                if fps >= target:
                    failures.append("blocked capture entry has fps_median >= target_fps; update status and receipts")
        docs = set(capture.get("docs", [])) if isinstance(capture.get("docs"), list) else set()
        missing_docs = REQUIRED_MANIFEST_DOC_REFS - docs
        if missing_docs:
            failures.append(
                "pi5_mission1_halfres_capture docs missing Labs refs: "
                + ", ".join(sorted(missing_docs))
            )

    decode = platform.get("pi5_2k_l2hh_decode")
    if not decode:
        failures.append("manifest missing platform_performance pi5_2k_l2hh_decode")
    else:
        if decode.get("status") != "meets-target":
            failures.append("pi5_2k_l2hh_decode must stay meets-target or be explicitly downgraded with docs")
        if decode.get("raw_target") != "2k_raw_0p5x_l2hh":
            failures.append("pi5_2k_l2hh_decode must reference raw_target 2k_raw_0p5x_l2hh")
        metrics = decode.get("metrics")
        if isinstance(metrics, dict):
            try:
                fps = float(metrics.get("fps_median"))
                p95 = float(metrics.get("p95_ms"))
            except (TypeError, ValueError):
                failures.append("pi5_2k_l2hh_decode needs numeric fps_median and p95_ms")
            else:
                if fps < 24.0 or p95 >= 41.7:
                    failures.append("pi5_2k_l2hh_decode must clear 24 fps and 41.7 ms p95")
        else:
            failures.append("pi5_2k_l2hh_decode needs metrics")

    raw_2k = raw_targets.get("2k_raw_0p5x_l2hh")
    if not raw_2k:
        failures.append("manifest missing raw target 2k_raw_0p5x_l2hh")
    elif raw_2k.get("classification") != "live-capable":
        failures.append("2k_raw_0p5x_l2hh must remain live-capable or be explicitly downgraded")

    preview = production_paths.get("preview_live_2k_l2hh_edge_safe")
    if not preview:
        failures.append("manifest missing production path preview_live_2k_l2hh_edge_safe")
    else:
        if preview.get("status") != "production-pass-external-receipt":
            failures.append("preview_live_2k_l2hh_edge_safe must remain tied to an external receipt")
        constraints = " ".join(str(item) for item in preview.get("constraints", []))
        if "16 px edge-safe" not in constraints or "Exact outer-edge" not in constraints:
            failures.append("preview_live_2k_l2hh_edge_safe must document viewport and exact-edge limits")


def require_ci_contract(tracked: set[str], failures: list[str]) -> None:
    rel = ".github/workflows/ci.yml"
    if rel not in tracked:
        failures.append(".github/workflows/ci.yml must be tracked")
        return
    text = CI.read_text(encoding="utf-8")
    if "python3 tools/test/check_labs_readiness.py" not in text:
        failures.append("CI must run python3 tools/test/check_labs_readiness.py")
    if "python3 tools/test/check_labs_target_receipts.py" not in text:
        failures.append("CI must run python3 tools/test/check_labs_target_receipts.py")
    if "tools/test/test_fused_context_env_capture.sh" not in text:
        failures.append("CI must run tools/test/test_fused_context_env_capture.sh")


def require_target_workflow_contract(tracked: set[str], failures: list[str]) -> None:
    rel = ".github/workflows/labs-target.yml"
    if rel not in tracked:
        failures.append(".github/workflows/labs-target.yml must be tracked")
        return
    text = TARGET_CI.read_text(encoding="utf-8")
    for token in (
        "workflow_dispatch",
        "self-hosted",
        "gpr-labs-pi5",
        "bench_fused",
        "tools/run_labs_target_bench.py",
        "labs_target_bench.json",
        "actions/upload-artifact",
        "Enforce target verdict",
    ):
        if token not in text:
            failures.append(f".github/workflows/labs-target.yml missing target workflow token {token!r}")


def require_timing_build_contract(tracked: set[str], failures: list[str]) -> None:
    rel = "CMakeLists.txt"
    if rel not in tracked:
        failures.append("CMakeLists.txt must be tracked")
        return
    text = CMAKE.read_text(encoding="utf-8")
    for token in (
        'option(FUSED_TIMING "Enable fused encoder stage timing prints" OFF)',
        'option(FUSED_TIMING_DETAIL "Enable detailed fused encoder channel timing prints" OFF)',
        "FUSED_TIMING_DETAIL",
        "add_compile_definitions(FUSED_TIMING=1)",
        "add_compile_definitions(FUSED_TIMING_DETAIL=1)",
    ):
        if token not in text:
            failures.append(f"CMakeLists.txt missing Labs timing-build token {token!r}")


def main() -> int:
    failures: list[str] = []
    tracked = tracked_paths()
    require_docs(tracked, failures)
    require_manifest_contract(load_manifest(), failures)
    require_ci_contract(tracked, failures)
    require_target_workflow_contract(tracked, failures)
    require_timing_build_contract(tracked, failures)

    if failures:
        print("Labs readiness guard failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1
    print("Labs readiness guard OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
