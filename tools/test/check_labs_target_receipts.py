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
    receipt_frames = timing.get("n")
    if receipt_fps is None or receipt_median_ms is None or receipt_p95_ms is None:
        return

    require_close("pi5_mission1_halfres_capture fps_median", fps, receipt_fps, 0.01, failures)
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

    receipt_passes = bool(verdict.get("fps_target_met")) and receipt_fps >= target
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
