#!/usr/bin/env python3
"""Validate the compact release evidence manifest.

This check keeps high-level production claims tied to concrete registry entries,
committed quality-gate runs, external receipt references, and tracked docs/tools.
It intentionally does not require heavyweight external artifacts in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/release_evidence_manifest.json"
REGISTRY = ROOT / "pipelines/registry.json"
RUNS_DIR = ROOT / "tests/quality_gates/runs"

EXPECTED_SCHEMA = "gpr_release_evidence_manifest.v1"
PRODUCTION_STATUSES = {
    "production-pass",
    "production-pass-external-receipt",
    "production-supported",
}
ALLOWED_STATUSES = PRODUCTION_STATUSES | {"experimental"}
ALLOWED_RAW_CLASSIFICATIONS = {
    "live-capable",
    "p95-live-editable-raw-candidate",
    "offline-editable-raw",
    "offline-only",
}
REQUIRED_OUTPUT_IDS = {
    "still_smallest",
    "still_primary",
    "still_archival",
    "video_freeze_primary",
    "upresable_editable_raw",
    "preview_offline_review_q8_threeway",
    "preview_live_codec_only",
    "gvid_container",
    "mov_wrapper",
    "prores_review_outputs",
    "editable_dng_gpr_outputs",
}
REQUIRED_RAW_IDS = {
    "2k_raw_0p5x_fast",
    "2k_raw_0p5x_l2hh",
    "4k_raw_1x",
    "8k_raw_2x",
}
REQUIRED_EXTERNAL_RECEIPT_IDS = {
    "gvid_container",
    "mov_wrapper",
    "prores_review_outputs",
    "editable_dng_gpr_outputs",
}
REQUIRED_PLATFORM_PERFORMANCE_IDS = {
    "pi5_mission1_halfres_capture",
    "pi5_2k_fast_decode",
    "pi5_2k_l2hh_decode",
    "pi5_4k_decode_blocked",
    "mac_m5_preview_offline_render",
    "mac_m5_4k_raw_decode",
    "local_8k_raw_offline",
    "mac_m5_upres_and_gvid_pack",
    "capability_memory_matrix",
}
ALLOWED_PLATFORM_STATUSES = {
    "meets-target",
    "measured-offline",
    "blocked",
    "receipt-only",
}
ALLOWED_BLOCKERS = {
    "quality_gate_failure",
    "model_capacity",
    "source_target_mismatch",
    "codec_detail_aliasing",
    "memory_limit",
    "fps_throughput_limit",
    "missing_data",
    "ci_build_issue",
}


def tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def run_for_hash(run_hash: str) -> dict[str, Any] | None:
    path = RUNS_DIR / run_hash / "run.json"
    if not path.exists():
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def require_tracked_refs(
    entry_id: str,
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    for key in ("docs", "tools"):
        refs = entry.get(key, [])
        if not isinstance(refs, list):
            failures.append(f"{entry_id}: {key} must be a list")
            continue
        for ref in refs:
            if not isinstance(ref, str):
                failures.append(f"{entry_id}: {key} entry must be a string")
                continue
            path = ROOT / ref
            if not path.exists():
                failures.append(f"{entry_id}: referenced {key[:-1]} does not exist: {ref}")
            elif ref not in tracked and not any(t.startswith(ref.rstrip('/') + '/') for t in tracked):
                failures.append(f"{entry_id}: referenced {key[:-1]} is not tracked: {ref}")


def require_external_receipts(entry_id: str, entry: dict[str, Any], failures: list[str]) -> None:
    receipts = entry.get("external_receipts")
    if not isinstance(receipts, list) or not receipts:
        failures.append(f"{entry_id}: external_receipts must be a non-empty list")
        return
    for receipt in receipts:
        if not isinstance(receipt, str):
            failures.append(f"{entry_id}: external_receipts entries must be strings")
            continue
        if not receipt.startswith("artifacts/"):
            failures.append(f"{entry_id}: external receipt must be under artifacts/: {receipt}")


def require_receipt_refs(
    entry_id: str,
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    receipts = entry.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        failures.append(f"{entry_id}: receipts must be a non-empty list")
        return
    for receipt in receipts:
        if not isinstance(receipt, str):
            failures.append(f"{entry_id}: receipts entries must be strings")
            continue
        if receipt.startswith("artifacts/"):
            continue
        path = ROOT / receipt
        if not path.exists():
            failures.append(f"{entry_id}: referenced receipt does not exist: {receipt}")
        elif receipt not in tracked:
            failures.append(f"{entry_id}: referenced receipt is not tracked: {receipt}")


def require_platform_performance_contract(
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    entry_id = str(entry.get("id", ""))
    status = entry.get("status")
    if status not in ALLOWED_PLATFORM_STATUSES:
        failures.append(f"{entry_id}: invalid platform performance status {status!r}")

    if not isinstance(entry.get("platform"), str) or not entry.get("platform"):
        failures.append(f"{entry_id}: platform performance entry needs platform")

    raw_target = entry.get("raw_target")
    if raw_target is not None and raw_target not in REQUIRED_RAW_IDS:
        failures.append(f"{entry_id}: unknown raw_target {raw_target!r}")

    metrics = entry.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        failures.append(f"{entry_id}: platform performance entry needs metrics")
    else:
        numeric_keys = [
            "fps_median",
            "target_fps",
            "p95_ms",
            "median_ms",
            "seconds_per_image",
            "peak_rss_gb",
            "max_rss_mb",
            "mac_upres_fps",
            "gvid_pack_fps",
        ]
        has_numeric = False
        for key in numeric_keys:
            if key not in metrics:
                continue
            try:
                float(metrics[key])
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: metric {key} must be numeric")
            else:
                has_numeric = True
        if not has_numeric:
            failures.append(f"{entry_id}: platform metrics need at least one numeric timing/memory value")
        if status == "meets-target":
            try:
                fps = float(metrics.get("fps_median"))
                target_fps = float(metrics.get("target_fps"))
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: meets-target entries need fps_median and target_fps")
            else:
                if fps < target_fps:
                    failures.append(f"{entry_id}: fps_median below target_fps")

    if status == "blocked":
        blockers = entry.get("blocked_by")
        if not isinstance(blockers, list) or not blockers:
            failures.append(f"{entry_id}: blocked platform entries need blocked_by")
        else:
            for blocker in blockers:
                if blocker not in ALLOWED_BLOCKERS:
                    failures.append(f"{entry_id}: invalid platform blocker {blocker!r}")
        if not entry.get("reason"):
            failures.append(f"{entry_id}: blocked platform entries need reason")

    require_receipt_refs(entry_id, entry, tracked, failures)


def require_preview_live_experimental_contract(entry: dict[str, Any], failures: list[str]) -> None:
    entry_id = str(entry.get("id", ""))
    if entry_id != "preview_live_codec_only":
        return

    if entry.get("status") != "experimental":
        failures.append(f"{entry_id}: live/camera-back PREVIEW must remain experimental until it passes quality")

    blockers = entry.get("blocked_by")
    if not isinstance(blockers, list) or not blockers:
        failures.append(f"{entry_id}: experimental live PREVIEW needs blocked_by list")
    else:
        for blocker in blockers:
            if blocker not in ALLOWED_BLOCKERS:
                failures.append(f"{entry_id}: invalid blocker {blocker!r}")
        if "quality_gate_failure" not in blockers:
            failures.append(f"{entry_id}: live PREVIEW blocker must include quality_gate_failure")

    gate = entry.get("current_gate_result")
    if not isinstance(gate, dict):
        failures.append(f"{entry_id}: experimental live PREVIEW needs current_gate_result")
    else:
        if gate.get("run_hash") != entry.get("committed_run_hash"):
            failures.append(f"{entry_id}: current_gate_result run_hash must match committed_run_hash")
        if gate.get("verdict") != "FAIL":
            failures.append(f"{entry_id}: current_gate_result must record the current FAIL")
        try:
            pass_images = int(gate.get("passing_images"))
            total_images = int(gate.get("total_images"))
            worst_lpips = float(gate.get("worst_lpips"))
            worst_ms = float(gate.get("worst_ms_ssim"))
            worst_y = float(gate.get("worst_y_psnr"))
            worst_de = float(gate.get("worst_dE2000"))
        except (TypeError, ValueError):
            failures.append(f"{entry_id}: current_gate_result metrics must be numeric")
        else:
            if pass_images >= total_images:
                failures.append(f"{entry_id}: current_gate_result must show at least one failing image")
            if not (
                worst_lpips > 0.15
                or worst_ms < 0.95
                or worst_y < 28.0
                or worst_de > 3.0
            ):
                failures.append(f"{entry_id}: current_gate_result does not show a PREVIEW threshold miss")

    speed = entry.get("speed_evidence")
    if not isinstance(speed, dict):
        failures.append(f"{entry_id}: experimental live PREVIEW needs speed_evidence")
    else:
        try:
            fps = float(speed.get("pi5_fps_median"))
            p95_ms = float(speed.get("pi5_p95_ms"))
        except (TypeError, ValueError):
            failures.append(f"{entry_id}: speed_evidence fps/p95 must be numeric")
        else:
            if fps < 24.0 or p95_ms >= 41.7:
                failures.append(f"{entry_id}: speed_evidence must show current speed path clears 24 fps timing")

    promotion = entry.get("promotion_requirements")
    if not isinstance(promotion, list) or not promotion:
        failures.append(f"{entry_id}: experimental live PREVIEW needs promotion_requirements")
    else:
        text = "\n".join(str(item).lower() for item in promotion)
        for required in ("preview", "lpips", "ms-ssim", "y-psnr", "de2000", "24 fps"):
            if required not in text:
                failures.append(f"{entry_id}: promotion_requirements missing {required}")


def main() -> int:
    failures: list[str] = []
    manifest = load_json(MANIFEST)
    registry = load_json(REGISTRY)
    pipelines = registry.get("pipelines") or {}
    tracked = tracked_paths()

    if manifest.get("schema") != EXPECTED_SCHEMA:
        failures.append(f"schema must be {EXPECTED_SCHEMA}")

    production_paths = manifest.get("production_paths")
    if not isinstance(production_paths, list):
        failures.append("production_paths must be a list")
        production_paths = []

    seen_output_ids: set[str] = set()
    for entry in production_paths:
        if not isinstance(entry, dict):
            failures.append("production_paths entries must be objects")
            continue
        entry_id = str(entry.get("id", ""))
        seen_output_ids.add(entry_id)
        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            failures.append(f"{entry_id}: invalid status {status!r}")

        pipeline = entry.get("pipeline")
        if pipeline:
            if pipeline not in pipelines:
                failures.append(f"{entry_id}: pipeline is not registered: {pipeline}")
            else:
                expected_class = entry.get("ship_class")
                actual_class = (pipelines[pipeline] or {}).get("ship_class")
                if expected_class and actual_class != expected_class:
                    failures.append(
                        f"{entry_id}: registry ship_class {actual_class!r} != manifest {expected_class!r}"
                    )

        run_hash = entry.get("committed_run_hash")
        if run_hash:
            run = run_for_hash(str(run_hash))
            rel = f"tests/quality_gates/runs/{run_hash}/run.json"
            if not run:
                failures.append(f"{entry_id}: missing or unreadable committed run {run_hash}")
            elif rel not in tracked:
                failures.append(f"{entry_id}: committed run is not tracked: {rel}")
            else:
                if run.get("run_hash") != run_hash:
                    failures.append(f"{entry_id}: run_hash mismatch in {rel}")
                if run.get("pipeline") != pipeline:
                    failures.append(f"{entry_id}: run pipeline does not match manifest")
                if run.get("ship_class") != entry.get("ship_class"):
                    failures.append(f"{entry_id}: run ship_class does not match manifest")
                if status in PRODUCTION_STATUSES and run.get("verdict") != "PASS":
                    failures.append(f"{entry_id}: production path references non-PASS run {run_hash}")

        if status == "production-pass-external-receipt":
            receipt = entry.get("external_receipt")
            dashboard = entry.get("dashboard")
            runtime_entrypoint = entry.get("runtime_entrypoint")
            if not isinstance(receipt, str) or not receipt.startswith("artifacts/"):
                failures.append(f"{entry_id}: external receipt must be under artifacts/")
            if not isinstance(dashboard, str) or not dashboard.startswith("artifacts/"):
                failures.append(f"{entry_id}: external dashboard must be under artifacts/")
            if not isinstance(runtime_entrypoint, str) or runtime_entrypoint not in tracked:
                failures.append(f"{entry_id}: runtime entrypoint must be tracked")
            metrics = entry.get("metrics")
            if not isinstance(metrics, dict):
                failures.append(f"{entry_id}: external receipt path needs compact metrics")
            elif metrics.get("passing_rows") != metrics.get("holdout_rows"):
                failures.append(f"{entry_id}: external receipt metrics do not show full holdout pass")

        if status == "experimental" and not entry.get("reason"):
            failures.append(f"{entry_id}: experimental entries need a reason")

        if entry_id in REQUIRED_EXTERNAL_RECEIPT_IDS:
            require_external_receipts(entry_id, entry, failures)

        require_preview_live_experimental_contract(entry, failures)
        require_tracked_refs(entry_id, entry, tracked, failures)

    missing_output_ids = REQUIRED_OUTPUT_IDS - seen_output_ids
    if missing_output_ids:
        failures.append("manifest missing output ids: " + ", ".join(sorted(missing_output_ids)))

    raw_targets = manifest.get("raw_targets")
    if not isinstance(raw_targets, list):
        failures.append("raw_targets must be a list")
        raw_targets = []

    seen_raw_ids: set[str] = set()
    for target in raw_targets:
        if not isinstance(target, dict):
            failures.append("raw_targets entries must be objects")
            continue
        target_id = str(target.get("id", ""))
        seen_raw_ids.add(target_id)
        classification = target.get("classification")
        if classification not in ALLOWED_RAW_CLASSIFICATIONS:
            failures.append(f"{target_id}: invalid classification {classification!r}")
        require_external_receipts(target_id, target, failures)
        require_tracked_refs(target_id, target, tracked, failures)

    missing_raw_ids = REQUIRED_RAW_IDS - seen_raw_ids
    if missing_raw_ids:
        failures.append("manifest missing raw target ids: " + ", ".join(sorted(missing_raw_ids)))

    platform_performance = manifest.get("platform_performance")
    if not isinstance(platform_performance, list):
        failures.append("platform_performance must be a list")
        platform_performance = []

    seen_platform_ids: set[str] = set()
    for entry in platform_performance:
        if not isinstance(entry, dict):
            failures.append("platform_performance entries must be objects")
            continue
        entry_id = str(entry.get("id", ""))
        seen_platform_ids.add(entry_id)
        require_platform_performance_contract(entry, tracked, failures)
        require_tracked_refs(entry_id, entry, tracked, failures)

    missing_platform_ids = REQUIRED_PLATFORM_PERFORMANCE_IDS - seen_platform_ids
    if missing_platform_ids:
        failures.append("manifest missing platform performance ids: " + ", ".join(sorted(missing_platform_ids)))

    release_checks = manifest.get("release_checks")
    if not isinstance(release_checks, list):
        failures.append("release_checks must be a list")
        release_checks = []
    release_check_text = "\n".join(str(item) for item in release_checks)
    for required in (
        "tools/test/check_sensitive_content.py",
        "tools/test/check_repo_artifact_hygiene.py",
        "tools/test/check_release_evidence_manifest.py",
        "tests/quality_gates/check_registry_consistency.py",
        "tests/quality_gates/audit_production_readiness.py --strict",
    ):
        if required not in release_check_text:
            failures.append(f"release_checks missing {required}")

    for guard in manifest.get("guards", []):
        if not isinstance(guard, str) or guard not in tracked:
            failures.append(f"guard is not tracked: {guard}")

    if failures:
        print("Release evidence manifest check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("OK - release evidence manifest check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
