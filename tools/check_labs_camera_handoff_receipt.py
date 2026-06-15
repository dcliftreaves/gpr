#!/usr/bin/env python3
"""Validate a Labs camera-handoff receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr_labs_camera_handoff_receipt.v1"


def as_bool(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> bool | None:
    value = obj.get(key)
    if not isinstance(value, bool):
        failures.append(f"{prefix}.{key} must be boolean")
        return None
    return value


def as_number(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> float | None:
    value = obj.get(key)
    if isinstance(value, bool):
        failures.append(f"{prefix}.{key} must be numeric")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        failures.append(f"{prefix}.{key} must be numeric")
        return None


def as_int(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> int | None:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        failures.append(f"{prefix}.{key} must be integer")
        return None
    return value


def require_obj(root: dict[str, Any], key: str, failures: list[str]) -> dict[str, Any]:
    value = root.get(key)
    if not isinstance(value, dict):
        failures.append(f"{key} must be an object")
        return {}
    return value


def require_string(obj: dict[str, Any], key: str, failures: list[str], prefix: str) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        failures.append(f"{prefix}.{key} must be a non-empty string")
        return None
    return value


def validate_receipt(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != SCHEMA:
        failures.append(f"schema must be {SCHEMA}")

    target = require_obj(data, "target", failures)
    require_string(target, "name", failures, "target")
    role = require_string(target, "role", failures, "target")
    if role and role not in {"camera", "stand-in"}:
        failures.append("target.role must be camera or stand-in")

    integration = require_obj(data, "integration", failures)
    sensor_dma = require_obj(integration, "sensor_dma_handoff", failures)
    sensor_dma_executed = as_bool(sensor_dma, "executed", failures, "integration.sensor_dma_handoff")
    require_string(integration, "frame_source", failures, "integration")
    require_string(integration, "memory_ownership", failures, "integration")
    require_string(integration, "write_path", failures, "integration")

    input_frame = require_obj(data, "input_frame", failures)
    width = as_int(input_frame, "width", failures, "input_frame")
    height = as_int(input_frame, "height", failures, "input_frame")
    stride = as_int(input_frame, "stride_bytes", failures, "input_frame")
    bit_depth = as_int(input_frame, "bit_depth", failures, "input_frame")
    pixel_format = as_int(input_frame, "pixel_format", failures, "input_frame")
    target_fps = as_number(input_frame, "target_fps", failures, "input_frame")
    if width is not None and width <= 0:
        failures.append("input_frame.width must be positive")
    if height is not None and height <= 0:
        failures.append("input_frame.height must be positive")
    if stride is not None and stride <= 0:
        failures.append("input_frame.stride_bytes must be positive")
    if bit_depth is not None and bit_depth <= 0:
        failures.append("input_frame.bit_depth must be positive")
    if pixel_format is not None and not (0 <= pixel_format <= 5):
        failures.append("input_frame.pixel_format must be in 0..5")
    if target_fps is not None and target_fps <= 0:
        failures.append("input_frame.target_fps must be positive")

    capture = require_obj(data, "capture", failures)
    frames_requested = as_int(capture, "frames_requested", failures, "capture")
    frames_written = as_int(capture, "frames_written", failures, "capture")
    dropped = as_int(capture, "dropped_frames", failures, "capture")
    if frames_requested is not None and frames_requested <= 0:
        failures.append("capture.frames_requested must be positive")
    if frames_written is not None and frames_written <= 0:
        failures.append("capture.frames_written must be positive")
    if dropped is not None and dropped < 0:
        failures.append("capture.dropped_frames must be non-negative")

    timing = require_obj(data, "timing", failures)
    fps_median = as_number(timing, "fps_median", failures, "timing")
    as_number(timing, "median_ms", failures, "timing")
    as_number(timing, "p95_ms", failures, "timing")
    as_number(timing, "p99_ms", failures, "timing")

    storage = require_obj(data, "storage", failures)
    as_number(storage, "write_mb_s", failures, "storage")
    require_string(storage, "flush_policy", failures, "storage")

    memory = require_obj(data, "memory", failures)
    if memory.get("heap_high_water_bytes") is None and memory.get("rss_kb") is None:
        failures.append("memory must include heap_high_water_bytes or rss_kb")
    if memory.get("heap_high_water_bytes") is not None:
        as_number(memory, "heap_high_water_bytes", failures, "memory")
    if memory.get("rss_kb") is not None:
        as_number(memory, "rss_kb", failures, "memory")

    output = require_obj(data, "output", failures)
    validation = require_obj(output, "validation", failures)
    gvid_valid = as_bool(validation, "valid", failures, "output.validation")
    validation_frames = as_int(validation, "frame_count", failures, "output.validation")
    require_string(output, "sha256", failures, "output")

    recovery = require_obj(data, "interruption_recovery", failures)
    recovery_proven = as_bool(recovery, "proven", failures, "interruption_recovery")
    validator_rejects = as_bool(recovery, "validator_rejects_truncated", failures, "interruption_recovery")

    verdict = require_obj(data, "verdict", failures)
    firmware_ready = as_bool(verdict, "firmware_ready", failures, "verdict")
    fps_target_met = as_bool(verdict, "fps_target_met", failures, "verdict")
    no_drops = as_bool(verdict, "no_drops", failures, "verdict")
    target_evidence = as_bool(verdict, "target_evidence", failures, "verdict")

    if frames_written is not None and validation_frames is not None and frames_written != validation_frames:
        failures.append("capture.frames_written must match output.validation.frame_count")
    if dropped is not None and no_drops is not None and no_drops != (dropped == 0):
        failures.append("verdict.no_drops must match capture.dropped_frames")
    if fps_median is not None and target_fps is not None and fps_target_met is not None:
        if fps_target_met != (fps_median >= target_fps):
            failures.append("verdict.fps_target_met must match timing.fps_median >= input_frame.target_fps")

    if firmware_ready:
        if role != "camera":
            failures.append("firmware-ready receipt must use target.role=camera")
        if sensor_dma_executed is not True:
            failures.append("firmware-ready receipt must execute sensor/DMA handoff")
        if target_evidence is not True:
            failures.append("firmware-ready receipt must mark target_evidence true")
        for label, value in (
            ("verdict.fps_target_met", fps_target_met),
            ("verdict.no_drops", no_drops),
            ("output.validation.valid", gvid_valid),
            ("interruption_recovery.proven", recovery_proven),
            ("interruption_recovery.validator_rejects_truncated", validator_rejects),
        ):
            if value is not True:
                failures.append(f"firmware-ready receipt requires {label}=true")
    elif role == "camera":
        blocker = data.get("blocker")
        if not isinstance(blocker, dict) or not blocker.get("cause"):
            failures.append("blocked camera receipt must include blocker.cause")

    if role == "camera" and sensor_dma_executed is not True:
        failures.append("camera receipt must set integration.sensor_dma_handoff.executed=true")

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("receipt", type=Path, help="camera handoff receipt JSON")
    args = ap.parse_args()

    data = json.loads(args.receipt.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("receipt must be a JSON object", file=sys.stderr)
        return 1
    failures = validate_receipt(data)
    if failures:
        print("Labs camera handoff receipt failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1
    print("Labs camera handoff receipt OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
