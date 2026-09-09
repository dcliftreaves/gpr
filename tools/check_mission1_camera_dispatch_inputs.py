#!/usr/bin/env python3
"""Validate Mission 1 Labs workflow dispatch inputs.

This is a preflight guard for the final camera-side closure run. It intentionally
accepts stand-in dispatches, but camera-role dispatches must not retain stand-in
labels or unset execution flags.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any


STANDIN_TOKENS = (
    "stand-in",
    "file-backed",
    "bench_fused",
    "page-cache",
    "filesystem",
    "off-camera",
    "pi 5",
    "pi5",
)

STANDIN_PATH_TOKENS = (
    "fixture",
    "fixtures",
    "file-backed",
    "stand-in",
    "standin",
    "mission1_native12",
    "gp017",
)


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def contains_standin_token(value: str) -> str | None:
    lowered = value.lower()
    for token in STANDIN_TOKENS:
        if token in lowered:
            return token
    return None


def contains_standin_path_token(value: str) -> str | None:
    lowered = value.lower()
    for token in STANDIN_PATH_TOKENS:
        if token in lowered:
            return token
    return None


def validate(args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    if args.target_role not in {"stand-in", "camera"}:
        failures.append("target_role must be stand-in or camera")
        return failures
    if args.target_role == "stand-in":
        return failures

    required_true = {
        "sensor_dma_executed": args.sensor_dma_executed,
        "storage_handoff_executed": args.storage_handoff_executed,
        "ui_path_executed": args.ui_path_executed,
        "visual_checked": args.visual_checked,
    }
    for label, value in required_true.items():
        parsed = parse_bool(value)
        if parsed is not True:
            failures.append(f"camera-role dispatch requires {label}=true")

    if args.raw_source_kind == "file_standin":
        failures.append("camera-role dispatch requires raw_source_kind=sensor_dma_capture or camera_ring_buffer")
    raw_path = getattr(args, "raw_path", None)
    if raw_path:
        token = contains_standin_path_token(str(raw_path))
        if token:
            failures.append(f"camera-role dispatch cannot use stand-in token {token!r} in raw_path: {raw_path!r}")

    label_fields = {
        "target_name": args.target_name,
        "frame_source": args.frame_source,
        "write_path": args.write_path,
        "storage_medium": args.storage_medium,
        "storage_ownership": args.storage_ownership,
        "display_surface": args.display_surface,
        "presentation_path": args.presentation_path,
        "preview_buffer_ownership": args.preview_buffer_ownership,
    }
    for label, value in label_fields.items():
        if not isinstance(value, str) or not value.strip():
            failures.append(f"camera-role dispatch requires non-empty {label}")
            continue
        token = contains_standin_token(value)
        if token:
            failures.append(f"camera-role dispatch cannot use stand-in token {token!r} in {label}: {value!r}")
    return failures


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-role", required=True, choices=("stand-in", "camera"))
    ap.add_argument("--target-name", required=True)
    ap.add_argument("--sensor-dma-executed", required=True)
    ap.add_argument("--storage-handoff-executed", required=True)
    ap.add_argument("--ui-path-executed", required=True)
    ap.add_argument("--visual-checked", required=True)
    ap.add_argument("--frame-source", required=True)
    ap.add_argument("--write-path", required=True)
    ap.add_argument("--storage-medium", required=True)
    ap.add_argument("--storage-ownership", required=True)
    ap.add_argument("--display-surface", required=True)
    ap.add_argument("--presentation-path", required=True)
    ap.add_argument("--preview-buffer-ownership", required=True)
    ap.add_argument("--raw-source-kind", choices=("file_standin", "sensor_dma_capture", "camera_ring_buffer"), default="file_standin")
    ap.add_argument("--raw-path")
    return ap


def main() -> int:
    args = parser().parse_args()
    failures = validate(args)
    if failures:
        print("Mission 1 camera dispatch input check failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1
    print("Mission 1 camera dispatch input check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
