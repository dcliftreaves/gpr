#!/usr/bin/env python3
"""Validate Labs target-performance receipts against the release manifest.

Hosted CI does not have the 8TB artifact tree, so this checker has two layers:

1. Always enforce the manifest contract for the current Labs state.
2. When the external receipt exists, parse it and verify the manifest metrics
   and blocked/pass status are derived from that receipt.

This keeps the repo from silently promoting half-res capture while the latest
strict Pi 5 run is only a proxy for the final 24 fps camera-hardware target.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs/release_evidence_manifest.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def entries_by_id(entries: object) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            out[entry["id"]] = entry
    return out


def as_float(value: object, name: str, failures: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        failures.append(f"{name} must be numeric")
        return None


def require_close(name: str, actual: float, expected: float, tolerance: float, failures: list[str]) -> None:
    if abs(actual - expected) > tolerance:
        failures.append(f"{name} drifted: manifest={actual} receipt={expected}")


def external_root(manifest: dict[str, Any]) -> Path:
    override = os.environ.get("GPR_EXTERNAL_ROOT")
    if override:
        return Path(override)
    root = manifest.get("external_root")
    if isinstance(root, str) and root:
        return Path(root)
    return ROOT


def validate_capture_manifest(capture: dict[str, Any], failures: list[str]) -> None:
    if capture.get("status") != "blocked":
        failures.append("pi5_mission1_halfres_capture must remain blocked until a passing strict receipt exists")

    metrics = capture.get("metrics")
    if not isinstance(metrics, dict):
        failures.append("pi5_mission1_halfres_capture metrics must be an object")
        return

    fps = as_float(metrics.get("fps_median"), "pi5_mission1_halfres_capture.metrics.fps_median", failures)
    target = as_float(metrics.get("target_fps"), "pi5_mission1_halfres_capture.metrics.target_fps", failures)
    p95 = as_float(metrics.get("p95_ms"), "pi5_mission1_halfres_capture.metrics.p95_ms", failures)
    frames = metrics.get("frame_count")

    if fps is not None and target is not None:
        if target != 24.0:
            failures.append("pi5_mission1_halfres_capture target_fps must remain 24.0")
        if fps >= target:
            failures.append("blocked capture entry has fps_median >= target_fps; promote only with a passing receipt")
    if p95 is not None and p95 <= 41.7 and fps is not None and target is not None and fps < target:
        failures.append("blocked capture entry has passing p95 but failing median fps; document this as a new receipt shape")
    if frames != 14400:
        failures.append("strict Pi 5 capture evidence must remain tied to the 14,400-frame receipt")

    blocked_by = capture.get("blocked_by")
    if not isinstance(blocked_by, list) or "fps_throughput_limit" not in blocked_by:
        failures.append("pi5_mission1_halfres_capture must list fps_throughput_limit in blocked_by")


def validate_capture_receipt(capture: dict[str, Any], root: Path, failures: list[str]) -> None:
    receipts = capture.get("receipts")
    if not isinstance(receipts, list):
        failures.append("pi5_mission1_halfres_capture receipts must be a list")
        return

    strict = [
        item for item in receipts
        if isinstance(item, str) and item.endswith("labs_target_bench.json")
    ]
    if not strict:
        failures.append("pi5_mission1_halfres_capture must reference a strict labs_target_bench.json receipt")
        return

    receipt_path = root / strict[0]
    if not receipt_path.exists():
        print(f"SKIP external Labs target receipt check: {receipt_path} not mounted")
        return

    receipt = load_json(receipt_path)
    timing = receipt.get("timing")
    verdict = receipt.get("verdict")
    gvid = receipt.get("gvid")
    recovery = receipt.get("interruption_recovery")
    if not isinstance(timing, dict):
        failures.append(f"{receipt_path}: timing must be an object")
        return
    if not isinstance(verdict, dict):
        failures.append(f"{receipt_path}: verdict must be an object")
        return
    if not isinstance(gvid, dict) or not isinstance(gvid.get("validation"), dict):
        failures.append(f"{receipt_path}: gvid.validation must be an object")
        return
    if not isinstance(recovery, dict):
        failures.append(f"{receipt_path}: interruption_recovery must be an object")
        return

    metrics = capture.get("metrics")
    if not isinstance(metrics, dict):
        return

    fps = as_float(metrics.get("fps_median"), "manifest fps_median", failures)
    target = as_float(metrics.get("target_fps"), "manifest target_fps", failures)
    median_ms = as_float(metrics.get("median_ms"), "manifest median_ms", failures)
    p95_ms = as_float(metrics.get("p95_ms"), "manifest p95_ms", failures)
    if fps is None or target is None or median_ms is None or p95_ms is None:
        return

    receipt_fps = as_float(timing.get("fps_median"), f"{receipt_path}: timing.fps_median", failures)
    receipt_median_ms = as_float(timing.get("median_ms"), f"{receipt_path}: timing.median_ms", failures)
    receipt_p95_ms = as_float(timing.get("p95_ms"), f"{receipt_path}: timing.p95_ms", failures)
    target_obj = receipt.get("target")
    if not isinstance(target_obj, dict):
        target_obj = {}
    receipt_wall_fps = None
    if "actual_wall_fps" in target_obj:
        receipt_wall_fps = as_float(target_obj.get("actual_wall_fps"), f"{receipt_path}: target.actual_wall_fps", failures)
    receipt_frames = timing.get("n")
    if receipt_fps is None or receipt_median_ms is None or receipt_p95_ms is None:
        return

    require_close("pi5_mission1_halfres_capture fps_median", fps, receipt_fps, 0.01, failures)
    if "actual_wall_fps" in metrics and receipt_wall_fps is not None:
        manifest_wall_fps = as_float(metrics.get("actual_wall_fps"), "manifest actual_wall_fps", failures)
        if manifest_wall_fps is not None:
            require_close("pi5_mission1_halfres_capture actual_wall_fps", manifest_wall_fps, receipt_wall_fps, 0.01, failures)
    require_close("pi5_mission1_halfres_capture median_ms", median_ms, receipt_median_ms, 0.01, failures)
    require_close("pi5_mission1_halfres_capture p95_ms", p95_ms, receipt_p95_ms, 0.01, failures)
    if metrics.get("frame_count") != receipt_frames:
        failures.append(f"frame_count drifted: manifest={metrics.get('frame_count')} receipt={receipt_frames}")

    validation = gvid["validation"]
    if verdict.get("target_evidence") is not True:
        failures.append(f"{receipt_path}: verdict.target_evidence must be true")
    if verdict.get("gvid_valid") is not True or validation.get("valid") is not True:
        failures.append(f"{receipt_path}: strict receipt must validate .gvid output")
    if verdict.get("no_drops") is not True:
        failures.append(f"{receipt_path}: strict receipt must preserve zero-drop evidence")
    if verdict.get("interruption_recovery_proven") is not True:
        failures.append(f"{receipt_path}: strict receipt must prove interruption recovery")
    if recovery.get("validator_rejects_truncated") is not True:
        failures.append(f"{receipt_path}: truncated-tail validator rejection must be true")
    if validation.get("frame_count") != receipt_frames:
        failures.append(f"{receipt_path}: gvid frame_count must match timing.n")

    median_passes = receipt_fps >= target
    wall_passes = True if receipt_wall_fps is None else receipt_wall_fps >= target
    if "fps_median_target_met" in verdict and bool(verdict.get("fps_median_target_met")) != median_passes:
        failures.append(f"{receipt_path}: verdict.fps_median_target_met does not match timing.fps_median")
    if "fps_wall_target_met" in verdict and bool(verdict.get("fps_wall_target_met")) != wall_passes:
        failures.append(f"{receipt_path}: verdict.fps_wall_target_met does not match target.actual_wall_fps")
    receipt_passes = bool(verdict.get("fps_target_met")) and median_passes and wall_passes
    if capture.get("status") == "blocked" and receipt_passes:
        failures.append("manifest still blocked but strict receipt passes target; update Labs docs/status")
    if capture.get("status") != "blocked" and not receipt_passes:
        failures.append("manifest promoted capture without a passing strict receipt")


def validate_corrected_pixel_format_probe(
    capture: dict[str, Any],
    root: Path,
    failures: list[str],
) -> None:
    probe = capture.get("corrected_pixel_format_probe")
    if not isinstance(probe, dict):
        failures.append("pi5_mission1_halfres_capture needs corrected_pixel_format_probe")
        return
    if probe.get("verdict") != "blocked":
        failures.append("corrected_pixel_format_probe must remain blocked until it clears target")

    metrics = probe.get("metrics")
    timing_expect = probe.get("timing")
    receipt_rel = probe.get("receipt")
    timing_rel = probe.get("timing_receipt")
    if not isinstance(metrics, dict):
        failures.append("corrected_pixel_format_probe.metrics must be an object")
        return
    if not isinstance(timing_expect, dict):
        failures.append("corrected_pixel_format_probe.timing must be an object")
        return
    if not isinstance(receipt_rel, str) or not receipt_rel.endswith("labs_target_bench.json"):
        failures.append("corrected_pixel_format_probe.receipt must reference labs_target_bench.json")
        return
    if not isinstance(timing_rel, str) or not timing_rel.endswith("labs_target_bench.json"):
        failures.append("corrected_pixel_format_probe.timing_receipt must reference labs_target_bench.json")
        return

    fps = as_float(metrics.get("fps_median"), "corrected_pixel_format_probe.metrics.fps_median", failures)
    target = as_float(metrics.get("target_fps"), "corrected_pixel_format_probe.metrics.target_fps", failures)
    median_ms = as_float(metrics.get("median_ms"), "corrected_pixel_format_probe.metrics.median_ms", failures)
    p95_ms = as_float(metrics.get("p95_ms"), "corrected_pixel_format_probe.metrics.p95_ms", failures)
    frames = metrics.get("frame_count")
    if target != 24.0:
        failures.append("corrected_pixel_format_probe target_fps must be 24.0")
    if fps is not None and target is not None and fps >= target:
        failures.append("corrected_pixel_format_probe is marked blocked but clears target_fps")
    if frames != 120:
        failures.append("corrected_pixel_format_probe must stay tied to the 120-frame corrected receipt")

    receipt_path = root / receipt_rel
    if not receipt_path.exists():
        print(f"SKIP corrected pixel-format receipt check: {receipt_path} not mounted")
    elif fps is not None and median_ms is not None and p95_ms is not None:
        receipt = load_json(receipt_path)
        receipt_metrics = receipt.get("timing")
        capture_fields = receipt.get("capture")
        verdict = receipt.get("verdict")
        gvid = receipt.get("gvid")
        if not isinstance(receipt_metrics, dict):
            failures.append(f"{receipt_path}: timing must be an object")
        elif not isinstance(capture_fields, dict):
            failures.append(f"{receipt_path}: capture must be an object")
        elif not isinstance(verdict, dict):
            failures.append(f"{receipt_path}: verdict must be an object")
        elif not isinstance(gvid, dict) or not isinstance(gvid.get("validation"), dict):
            failures.append(f"{receipt_path}: gvid.validation must be an object")
        else:
            receipt_fps = as_float(receipt_metrics.get("fps_median"), f"{receipt_path}: timing.fps_median", failures)
            receipt_median = as_float(receipt_metrics.get("median_ms"), f"{receipt_path}: timing.median_ms", failures)
            receipt_p95 = as_float(receipt_metrics.get("p95_ms"), f"{receipt_path}: timing.p95_ms", failures)
            if receipt_fps is not None:
                require_close("corrected_pixel_format_probe fps_median", fps, receipt_fps, 0.01, failures)
            if receipt_median is not None:
                require_close("corrected_pixel_format_probe median_ms", median_ms, receipt_median, 0.01, failures)
            if receipt_p95 is not None:
                require_close("corrected_pixel_format_probe p95_ms", p95_ms, receipt_p95, 0.01, failures)
            if capture_fields.get("pixel_format") != 4:
                failures.append(f"{receipt_path}: corrected probe must record capture.pixel_format 4")
            if capture_fields.get("quality") != 3:
                failures.append(f"{receipt_path}: corrected probe must record capture.quality 3")
            if capture_fields.get("frames_written") != frames:
                failures.append(f"{receipt_path}: frames_written must match corrected probe frame_count")
            if verdict.get("target_evidence") is not True:
                failures.append(f"{receipt_path}: corrected probe must be target evidence")
            if verdict.get("fps_target_met") is not False:
                failures.append(f"{receipt_path}: corrected probe should show fps_target_met false")
            if verdict.get("no_drops") is not True or verdict.get("gvid_valid") is not True:
                failures.append(f"{receipt_path}: corrected probe must show valid .gvid and no drops")

    timing_path = root / timing_rel
    if not timing_path.exists():
        print(f"SKIP corrected pixel-format timing receipt check: {timing_path} not mounted")
        return
    timing_receipt = load_json(timing_path)
    fused = timing_receipt.get("fused_timing")
    if not isinstance(fused, dict) or fused.get("available") is not True:
        failures.append(f"{timing_path}: corrected timing receipt must include fused_timing")
        return
    stage = fused.get("stage_ms")
    channel = fused.get("channel_component_ms")
    if not isinstance(stage, dict) or not isinstance(channel, dict):
        failures.append(f"{timing_path}: fused_timing stage/channel summaries missing")
        return
    expected_pairs = [
        ("ml_pass1_median_ms", stage.get("ml_pass1", {}), "median_ms"),
        ("ml_pass2_median_ms", stage.get("ml_pass2", {}), "median_ms"),
        ("unpack_mean_ms", channel.get("unpack", {}), "mean_ms"),
    ]
    for manifest_key, summary, receipt_key in expected_pairs:
        expected = as_float(timing_expect.get(manifest_key), f"corrected_pixel_format_probe.timing.{manifest_key}", failures)
        actual = as_float(summary.get(receipt_key) if isinstance(summary, dict) else None, f"{timing_path}: {manifest_key}", failures)
        if expected is not None and actual is not None:
            require_close(f"corrected_pixel_format_probe {manifest_key}", expected, actual, 0.05, failures)


def validate_hardened_wall_fps_probe(
    capture: dict[str, Any],
    root: Path,
    failures: list[str],
) -> None:
    probe = capture.get("hardened_wall_fps_probe")
    if probe is None:
        return
    if not isinstance(probe, dict):
        failures.append("hardened_wall_fps_probe must be an object")
        return
    if probe.get("verdict") != "blocked":
        failures.append("hardened_wall_fps_probe must remain blocked until median and wall FPS clear target")

    metrics = probe.get("metrics")
    receipt_rel = probe.get("receipt")
    if not isinstance(metrics, dict):
        failures.append("hardened_wall_fps_probe.metrics must be an object")
        return
    if not isinstance(receipt_rel, str) or not receipt_rel.endswith("labs_target_bench.json"):
        failures.append("hardened_wall_fps_probe.receipt must reference labs_target_bench.json")
        return

    fps = as_float(metrics.get("fps_median"), "hardened_wall_fps_probe.metrics.fps_median", failures)
    wall_fps = as_float(metrics.get("actual_wall_fps"), "hardened_wall_fps_probe.metrics.actual_wall_fps", failures)
    target = as_float(metrics.get("target_fps"), "hardened_wall_fps_probe.metrics.target_fps", failures)
    median_ms = as_float(metrics.get("median_ms"), "hardened_wall_fps_probe.metrics.median_ms", failures)
    p95_ms = as_float(metrics.get("p95_ms"), "hardened_wall_fps_probe.metrics.p95_ms", failures)
    frames = metrics.get("frame_count")
    if target != 24.0:
        failures.append("hardened_wall_fps_probe target_fps must be 24.0")
    if fps is not None and target is not None and fps >= target:
        failures.append("hardened_wall_fps_probe is marked blocked but median fps clears target_fps")
    if wall_fps is not None and target is not None and wall_fps >= target:
        failures.append("hardened_wall_fps_probe is marked blocked but wall fps clears target_fps")

    receipt_path = root / receipt_rel
    if not receipt_path.exists():
        print(f"SKIP hardened wall-FPS receipt check: {receipt_path} not mounted")
        return
    receipt = load_json(receipt_path)
    timing = receipt.get("timing")
    target_obj = receipt.get("target")
    capture_fields = receipt.get("capture")
    verdict = receipt.get("verdict")
    gvid = receipt.get("gvid")
    recovery = receipt.get("interruption_recovery")
    if not isinstance(timing, dict):
        failures.append(f"{receipt_path}: timing must be an object")
        return
    if not isinstance(target_obj, dict):
        failures.append(f"{receipt_path}: target must be an object")
        return
    if not isinstance(capture_fields, dict):
        failures.append(f"{receipt_path}: capture must be an object")
        return
    if not isinstance(verdict, dict):
        failures.append(f"{receipt_path}: verdict must be an object")
        return
    if not isinstance(gvid, dict) or not isinstance(gvid.get("validation"), dict):
        failures.append(f"{receipt_path}: gvid.validation must be an object")
        return
    if not isinstance(recovery, dict):
        failures.append(f"{receipt_path}: interruption_recovery must be an object")
        return

    receipt_fps = as_float(timing.get("fps_median"), f"{receipt_path}: timing.fps_median", failures)
    receipt_wall_fps = as_float(target_obj.get("actual_wall_fps"), f"{receipt_path}: target.actual_wall_fps", failures)
    receipt_median = as_float(timing.get("median_ms"), f"{receipt_path}: timing.median_ms", failures)
    receipt_p95 = as_float(timing.get("p95_ms"), f"{receipt_path}: timing.p95_ms", failures)
    if fps is not None and receipt_fps is not None:
        require_close("hardened_wall_fps_probe fps_median", fps, receipt_fps, 0.01, failures)
    if wall_fps is not None and receipt_wall_fps is not None:
        require_close("hardened_wall_fps_probe actual_wall_fps", wall_fps, receipt_wall_fps, 0.01, failures)
    if median_ms is not None and receipt_median is not None:
        require_close("hardened_wall_fps_probe median_ms", median_ms, receipt_median, 0.01, failures)
    if p95_ms is not None and receipt_p95 is not None:
        require_close("hardened_wall_fps_probe p95_ms", p95_ms, receipt_p95, 0.01, failures)
    if capture_fields.get("frames_written") != frames:
        failures.append(f"{receipt_path}: frames_written must match hardened probe frame_count")
    if verdict.get("fps_median_target_met") is not False:
        failures.append(f"{receipt_path}: hardened probe median FPS should fail target")
    if verdict.get("fps_wall_target_met") is not False:
        failures.append(f"{receipt_path}: hardened probe wall FPS should fail target")
    if verdict.get("fps_target_met") is not False:
        failures.append(f"{receipt_path}: hardened probe should show fps_target_met false")
    if verdict.get("no_drops") is not True or verdict.get("gvid_valid") is not True:
        failures.append(f"{receipt_path}: hardened probe must show valid .gvid and no drops")
    if recovery.get("validator_rejects_truncated") is not True:
        failures.append(f"{receipt_path}: hardened probe must prove truncated-tail rejection")


def validate_native12_t236_boundary_probe(
    capture: dict[str, Any],
    root: Path,
    failures: list[str],
) -> None:
    probe = capture.get("native12_t236_boundary_probe")
    if probe is None:
        failures.append("pi5_mission1_halfres_capture needs native12_t236_boundary_probe")
        return
    if not isinstance(probe, dict):
        failures.append("native12_t236_boundary_probe must be an object")
        return
    if probe.get("verdict") != "visual-neutral-target-performance-gap":
        failures.append("native12_t236_boundary_probe must remain a visual-neutral target-performance gap")

    metrics = probe.get("metrics")
    receipt_rel = probe.get("sustained_current_source_receipt")
    if not isinstance(metrics, dict):
        failures.append("native12_t236_boundary_probe.metrics must be an object")
        return
    if not isinstance(receipt_rel, str) or not receipt_rel.endswith("labs_target_bench.json"):
        failures.append("native12_t236_boundary_probe.sustained_current_source_receipt must reference labs_target_bench.json")
        return
    capture_receipts = capture.get("receipts")
    receipt_set = set(capture_receipts) if isinstance(capture_receipts, list) else set()
    for key in (
        "quality_summary",
        "encode_only_summary",
        "real_write_summary",
        "write_contention_summary",
        "sustained_current_source_receipt",
        "explicit_loop_wall_gap_receipt",
    ):
        ref = probe.get(key)
        if not isinstance(ref, str) or not ref.startswith("artifacts/"):
            failures.append(f"native12_t236_boundary_probe.{key} must reference an artifact")
            continue
        if ref not in receipt_set:
            failures.append(f"native12_t236_boundary_probe.{key} must also be listed in capture receipts")

    source_sha = metrics.get("sustained_current_source_source_provenance_sha256")
    binary_sha = metrics.get("sustained_current_source_binary_sha256")
    for label, value in (
        ("sustained_current_source_source_provenance_sha256", source_sha),
        ("sustained_current_source_binary_sha256", binary_sha),
    ):
        if not isinstance(value, str) or len(value) != 64:
            failures.append(f"native12_t236_boundary_probe.metrics.{label} must be a 64-character digest")

    total_ms = as_float(metrics.get("sustained_current_source_total_median_ms"), "native12_t236_boundary_probe.metrics.sustained_current_source_total_median_ms", failures)
    fps = as_float(metrics.get("sustained_current_source_fps_median"), "native12_t236_boundary_probe.metrics.sustained_current_source_fps_median", failures)
    wall_fps = as_float(metrics.get("sustained_current_source_wall_fps"), "native12_t236_boundary_probe.metrics.sustained_current_source_wall_fps", failures)
    gap_ms = as_float(metrics.get("sustained_current_source_strict_24_total_gap_ms"), "native12_t236_boundary_probe.metrics.sustained_current_source_strict_24_total_gap_ms", failures)
    if fps is not None and fps >= 24.0:
        failures.append("native12_t236_boundary_probe is marked blocked but sustained median fps clears 24")
    if wall_fps is not None and wall_fps >= 24.0:
        failures.append("native12_t236_boundary_probe is marked blocked but sustained wall fps clears 24")
    if gap_ms is not None and gap_ms <= 0.0:
        failures.append("native12_t236_boundary_probe strict-24 gap must remain positive unless the status is promoted")

    write_summary_rel = probe.get("write_contention_summary")
    if isinstance(write_summary_rel, str):
        write_summary_path = root / write_summary_rel
        if not write_summary_path.exists():
            print(f"SKIP native12 write-contention summary check: {write_summary_path} not mounted")
        else:
            summary = load_json(write_summary_path)
            latest = summary.get("latest_t236_boundary")
            followups = summary.get("recent_t236_followup_probes")
            if summary.get("schema") != "mission1_write_contention_summary.v1":
                failures.append(f"{write_summary_path}: schema must be mission1_write_contention_summary.v1")
            if summary.get("blocker_class") != "block_write_cache_contention":
                failures.append(f"{write_summary_path}: blocker_class must remain block_write_cache_contention")
            if not isinstance(latest, dict):
                failures.append(f"{write_summary_path}: latest_t236_boundary must be an object")
            else:
                if latest.get("blocker_class") != "visual_neutral_write_handoff_margin":
                    failures.append(f"{write_summary_path}: latest T236 blocker must remain write-handoff margin")
                if latest.get("visual_quality_impact") != "none_detected_quality_storage_boundary":
                    failures.append(f"{write_summary_path}: latest T236 summary must stay visual-neutral")
                encode_case = latest.get("encode_only_best_case")
                write_case = latest.get("real_write_best_case")
                if not isinstance(encode_case, dict):
                    failures.append(f"{write_summary_path}: encode_only_best_case must be an object")
                else:
                    if encode_case.get("strict_24_pass") is not True:
                        failures.append(f"{write_summary_path}: encode-only T236 case must clear strict 24")
                    expected = as_float(metrics.get("best_encode_only_median_ms"), "native12_t236_boundary_probe.metrics.best_encode_only_median_ms", failures)
                    actual = as_float(encode_case.get("total_median_ms"), f"{write_summary_path}: encode-only total_median_ms", failures)
                    if expected is not None and actual is not None:
                        require_close("native12_t236_boundary_probe write-summary encode-only median", expected, actual, 0.01, failures)
                if not isinstance(write_case, dict):
                    failures.append(f"{write_summary_path}: real_write_best_case must be an object")
                else:
                    if write_case.get("strict_24_pass") is not False:
                        failures.append(f"{write_summary_path}: real-write T236 case must remain strict-24 miss")
                    for manifest_key, receipt_key, tolerance in (
                        ("best_real_write_total_median_ms", "total_median_ms", 0.01),
                        ("best_real_write_fps", "fps_median", 0.01),
                        ("best_real_write_encode_median_ms", "encode_median_ms", 0.01),
                        ("best_real_write_write_median_ms", "write_median_ms", 0.01),
                    ):
                        expected = as_float(metrics.get(manifest_key), f"native12_t236_boundary_probe.metrics.{manifest_key}", failures)
                        actual = as_float(write_case.get(receipt_key), f"{write_summary_path}: real-write {receipt_key}", failures)
                        if expected is not None and actual is not None:
                            require_close(f"native12_t236_boundary_probe write-summary {manifest_key}", expected, actual, tolerance, failures)
                    expected_gap = as_float(metrics.get("best_isolation_strict_24_total_gap_ms"), "native12_t236_boundary_probe.metrics.best_isolation_strict_24_total_gap_ms", failures)
                    actual_gap = as_float(latest.get("strict_24_total_gap_ms"), f"{write_summary_path}: latest strict_24_total_gap_ms", failures)
                    if expected_gap is not None and actual_gap is not None:
                        require_close("native12_t236_boundary_probe write-summary isolation gap", expected_gap, actual_gap, 0.01, failures)
            if not isinstance(followups, dict):
                failures.append(f"{write_summary_path}: recent_t236_followup_probes must be an object")
            else:
                sustained = followups.get("current_source_t236_sustained_240f")
                if not isinstance(sustained, dict):
                    failures.append(f"{write_summary_path}: current_source_t236_sustained_240f must be an object")
                else:
                    sustained_metrics = sustained.get("metrics")
                    if not isinstance(sustained_metrics, dict):
                        failures.append(f"{write_summary_path}: sustained metrics must be an object")
                    else:
                        if sustained.get("classification") != "visual_neutral_sustained_current_source_strict24_miss":
                            failures.append(f"{write_summary_path}: sustained source classification drifted")
                        if sustained.get("quality_impact") != "none_detected_no_codec_parameter_change":
                            failures.append(f"{write_summary_path}: sustained source summary must stay visual-neutral")
                        if sustained.get("frames") != 240:
                            failures.append(f"{write_summary_path}: sustained source summary must cover 240 frames")
                        if sustained_metrics.get("strict_24_pass") is not False:
                            failures.append(f"{write_summary_path}: sustained source summary must remain strict-24 miss")
                        if sustained_metrics.get("gvid_valid") is not True or sustained_metrics.get("storage_target_met") is not True:
                            failures.append(f"{write_summary_path}: sustained source summary must keep valid .gvid and storage pass")
                        if source_sha and sustained.get("source_provenance_sha256") != source_sha:
                            failures.append(f"{write_summary_path}: sustained source provenance sha drifted from manifest")
                        if binary_sha and sustained.get("binary_sha256") != binary_sha:
                            failures.append(f"{write_summary_path}: sustained binary sha drifted from manifest")
                        for manifest_key, summary_key, summary_source, tolerance in (
                            ("sustained_current_source_total_median_ms", "total_median_ms", sustained_metrics, 0.01),
                            ("sustained_current_source_fps_median", "fps_median", sustained_metrics, 0.01),
                            ("sustained_current_source_wall_fps", "actual_wall_fps", sustained, 0.01),
                            ("sustained_current_source_strict_24_total_gap_ms", "strict_24_gap_ms", sustained, 0.01),
                        ):
                            expected = as_float(metrics.get(manifest_key), f"native12_t236_boundary_probe.metrics.{manifest_key}", failures)
                            actual = as_float(summary_source.get(summary_key), f"{write_summary_path}: sustained {summary_key}", failures)
                            if expected is not None and actual is not None:
                                require_close(f"native12_t236_boundary_probe write-summary {manifest_key}", expected, actual, tolerance, failures)

    explicit_gap_rel = probe.get("explicit_loop_wall_gap_receipt")
    if isinstance(explicit_gap_rel, str):
        explicit_gap_path = root / explicit_gap_rel
        if not explicit_gap_path.exists():
            print(f"SKIP native12 explicit loop/wall gap receipt check: {explicit_gap_path} not mounted")
        else:
            explicit = load_json(explicit_gap_path)
            timing_obj = explicit.get("timing")
            target_obj = explicit.get("target")
            verdict_obj = explicit.get("verdict")
            writer_obj = explicit.get("writer_handoff")
            gvid_obj = explicit.get("gvid")
            storage_obj = explicit.get("storage")
            phase_obj = explicit.get("bench_phase_timing")
            phase_ms = phase_obj.get("phase_ms") if isinstance(phase_obj, dict) else {}
            total_phase = phase_ms.get("total") if isinstance(phase_ms, dict) else {}
            if not isinstance(timing_obj, dict):
                failures.append(f"{explicit_gap_path}: timing must be an object")
            if not isinstance(target_obj, dict):
                failures.append(f"{explicit_gap_path}: target must be an object")
            if not isinstance(verdict_obj, dict):
                failures.append(f"{explicit_gap_path}: verdict must be an object")
            if not isinstance(writer_obj, dict):
                failures.append(f"{explicit_gap_path}: writer_handoff must be an object")
            if not isinstance(gvid_obj, dict) or not isinstance(gvid_obj.get("validation"), dict):
                failures.append(f"{explicit_gap_path}: gvid.validation must be an object")
            if not isinstance(storage_obj, dict) or not isinstance(storage_obj.get("target"), dict):
                failures.append(f"{explicit_gap_path}: storage.target must be an object")
            if isinstance(writer_obj, dict):
                for manifest_key, writer_key in (
                    ("explicit_gap_loop_target_gap_ms", "loop_target_gap_ms"),
                    ("explicit_gap_wall_target_gap_ms", "wall_target_gap_ms"),
                    ("explicit_gap_bottleneck_target_gap_ms", "bottleneck_target_gap_ms"),
                ):
                    expected = as_float(metrics.get(manifest_key), f"native12_t236_boundary_probe.metrics.{manifest_key}", failures)
                    actual = as_float(writer_obj.get(writer_key), f"{explicit_gap_path}: writer_handoff.{writer_key}", failures)
                    if expected is not None and actual is not None:
                        require_close(f"native12_t236_boundary_probe {manifest_key}", expected, actual, 0.01, failures)
                if writer_obj.get("deferred_writer_work_present") is not False:
                    failures.append(f"{explicit_gap_path}: explicit gap receipt should not have deferred writer work")
                if writer_obj.get("fps_target_met") is not False:
                    failures.append(f"{explicit_gap_path}: explicit gap receipt should fail target")
            if isinstance(verdict_obj, dict):
                if verdict_obj.get("fps_target_met") is not False:
                    failures.append(f"{explicit_gap_path}: explicit gap verdict should fail strict 24")
                if verdict_obj.get("fps_median_target_met") is not False:
                    failures.append(f"{explicit_gap_path}: explicit gap median verdict should fail strict 24")
                if verdict_obj.get("fps_wall_target_met") is not False:
                    failures.append(f"{explicit_gap_path}: explicit gap wall verdict should fail strict 24")
                if verdict_obj.get("no_drops") is not True or verdict_obj.get("gvid_valid") is not True:
                    failures.append(f"{explicit_gap_path}: explicit gap receipt must show valid .gvid and no drops")
                if verdict_obj.get("storage_target_met") is not True:
                    failures.append(f"{explicit_gap_path}: explicit gap receipt must fit storage target")
            if isinstance(timing_obj, dict) and timing_obj.get("n") != 240:
                failures.append(f"{explicit_gap_path}: explicit gap receipt must cover the 240-frame probe")
            if isinstance(total_phase, dict):
                total_median = as_float(total_phase.get("median_ms"), f"{explicit_gap_path}: total.median_ms", failures)
                if total_median is not None and total_median <= (1000.0 / 24.0):
                    failures.append(f"{explicit_gap_path}: explicit gap total median unexpectedly clears strict 24")

    receipt_path = root / receipt_rel
    if not receipt_path.exists():
        print(f"SKIP native12 T236 sustained receipt check: {receipt_path} not mounted")
        return

    receipt = load_json(receipt_path)
    timing = receipt.get("timing")
    target = receipt.get("target")
    capture_fields = receipt.get("capture")
    verdict = receipt.get("verdict")
    gvid = receipt.get("gvid")
    recovery = receipt.get("interruption_recovery")
    storage = receipt.get("storage")
    source_provenance = receipt.get("source_provenance")
    bench = receipt.get("bench")
    if receipt.get("schema") != "gpr_labs_target_bench.v1":
        failures.append(f"{receipt_path}: schema must be gpr_labs_target_bench.v1")
    if not isinstance(timing, dict):
        failures.append(f"{receipt_path}: timing must be an object")
        return
    if not isinstance(target, dict):
        failures.append(f"{receipt_path}: target must be an object")
        return
    if not isinstance(capture_fields, dict):
        failures.append(f"{receipt_path}: capture must be an object")
        return
    if not isinstance(verdict, dict):
        failures.append(f"{receipt_path}: verdict must be an object")
        return
    if not isinstance(gvid, dict) or not isinstance(gvid.get("validation"), dict):
        failures.append(f"{receipt_path}: gvid.validation must be an object")
        return
    if not isinstance(recovery, dict):
        failures.append(f"{receipt_path}: interruption_recovery must be an object")
        return
    if not isinstance(storage, dict) or not isinstance(storage.get("target"), dict):
        failures.append(f"{receipt_path}: storage.target must be an object")
        return
    if not isinstance(source_provenance, dict):
        failures.append(f"{receipt_path}: source_provenance must be an object")
        return
    if not isinstance(bench, dict) or not isinstance(bench.get("build"), dict):
        failures.append(f"{receipt_path}: bench.build must be an object")
        return

    phase = receipt.get("bench_phase_timing")
    phase_ms = phase.get("phase_ms") if isinstance(phase, dict) else {}
    total_phase = phase_ms.get("total") if isinstance(phase_ms, dict) else {}
    receipt_total = total_phase.get("median_ms") if isinstance(total_phase, dict) else timing.get("median_ms")
    receipt_total_f = as_float(receipt_total, f"{receipt_path}: sustained total median", failures)
    receipt_fps = as_float(timing.get("fps_median"), f"{receipt_path}: timing.fps_median", failures)
    receipt_wall_fps = as_float(target.get("actual_wall_fps"), f"{receipt_path}: target.actual_wall_fps", failures)
    if total_ms is not None and receipt_total_f is not None:
        require_close("native12_t236_boundary_probe sustained total median", total_ms, receipt_total_f, 0.01, failures)
    if fps is not None and receipt_fps is not None:
        require_close("native12_t236_boundary_probe sustained fps_median", fps, receipt_fps, 0.01, failures)
    if wall_fps is not None and receipt_wall_fps is not None:
        require_close("native12_t236_boundary_probe sustained wall_fps", wall_fps, receipt_wall_fps, 0.01, failures)
    if gap_ms is not None and receipt_total_f is not None:
        require_close("native12_t236_boundary_probe sustained strict-24 gap", gap_ms, receipt_total_f - (1000.0 / 24.0), 0.01, failures)

    if timing.get("n") != 240 or capture_fields.get("frames_written") != 240:
        failures.append(f"{receipt_path}: sustained T236 receipt must cover 240 frames")
    if capture_fields.get("source_width") != 4096 or capture_fields.get("source_height") != 3072:
        failures.append(f"{receipt_path}: sustained T236 source must be native 4096x3072")
    if capture_fields.get("pixel_format") != 1 or capture_fields.get("quality") != 8:
        failures.append(f"{receipt_path}: sustained T236 receipt must record pixel_format=1 and quality=8")
    if verdict.get("target_evidence") is not True:
        failures.append(f"{receipt_path}: sustained T236 receipt must be target evidence")
    if verdict.get("fps_target_met") is not False:
        failures.append(f"{receipt_path}: sustained T236 receipt should still fail strict 24 fps")
    if verdict.get("no_drops") is not True or verdict.get("gvid_valid") is not True:
        failures.append(f"{receipt_path}: sustained T236 receipt must show valid .gvid and no drops")
    if verdict.get("storage_target_met") is not True or storage["target"].get("fits_target") is not True:
        failures.append(f"{receipt_path}: sustained T236 receipt must fit storage target")
    if recovery.get("validator_rejects_truncated") is not True:
        failures.append(f"{receipt_path}: sustained T236 receipt must prove truncated-tail rejection")
    if source_provenance.get("available") is not True:
        failures.append(f"{receipt_path}: source_provenance.available must be true")
    if source_sha and source_provenance.get("sha256") != source_sha:
        failures.append(f"{receipt_path}: source_provenance.sha256 drifted from manifest")
    if int(source_provenance.get("file_count", 0)) <= 0:
        failures.append(f"{receipt_path}: source_provenance.file_count must be positive")
    if binary_sha and bench["build"].get("binary_sha256") != binary_sha:
        failures.append(f"{receipt_path}: bench.build.binary_sha256 drifted from manifest")


def validate_decode_entry(entries: dict[str, dict[str, Any]], failures: list[str]) -> None:
    decode = entries.get("pi5_2k_l2hh_decode")
    if not decode:
        failures.append("platform_performance missing pi5_2k_l2hh_decode")
        return
    if decode.get("status") != "meets-target":
        failures.append("pi5_2k_l2hh_decode must remain meets-target or be explicitly downgraded")
    if decode.get("raw_target") != "2k_raw_0p5x_l2hh":
        failures.append("pi5_2k_l2hh_decode must reference 2k_raw_0p5x_l2hh")
    metrics = decode.get("metrics")
    if not isinstance(metrics, dict):
        failures.append("pi5_2k_l2hh_decode metrics must be an object")
        return
    fps = as_float(metrics.get("fps_median"), "pi5_2k_l2hh_decode.metrics.fps_median", failures)
    p95 = as_float(metrics.get("p95_ms"), "pi5_2k_l2hh_decode.metrics.p95_ms", failures)
    if fps is not None and fps < 24.0:
        failures.append("pi5_2k_l2hh_decode fps_median must clear 24 fps")
    if p95 is not None and p95 >= 41.7:
        failures.append("pi5_2k_l2hh_decode p95_ms must stay below 41.7")


def main() -> int:
    failures: list[str] = []
    manifest = load_json(MANIFEST_PATH)
    platform = entries_by_id(manifest.get("platform_performance"))
    capture = platform.get("pi5_mission1_halfres_capture")
    if not capture:
        failures.append("platform_performance missing pi5_mission1_halfres_capture")
    else:
        validate_capture_manifest(capture, failures)
        validate_capture_receipt(capture, external_root(manifest), failures)
        validate_corrected_pixel_format_probe(capture, external_root(manifest), failures)
        validate_hardened_wall_fps_probe(capture, external_root(manifest), failures)
        validate_native12_t236_boundary_probe(capture, external_root(manifest), failures)
    validate_decode_entry(platform, failures)

    if failures:
        print("Labs target receipt guard failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1
    print("Labs target receipt guard OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
