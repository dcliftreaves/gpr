#!/usr/bin/env python3
"""Regression tests for Mission 1 camera dispatch input preflight."""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_mission1_camera_dispatch_inputs.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("check_mission1_camera_dispatch_inputs", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def args(**overrides):
    base = {
        "target_role": "camera",
        "target_name": "Mission 1 camera",
        "raw_source_kind": "sensor_dma_capture",
        "raw_path": "/dev/mission1/sensor_dma_ring",
        "sensor_dma_executed": "true",
        "storage_handoff_executed": "true",
        "ui_path_executed": "true",
        "visual_checked": "true",
        "frame_source": "sensor DMA",
        "write_path": "Mission 1 camera storage .gvid path",
        "storage_medium": "Mission 1 SD path",
        "storage_ownership": "camera firmware owns write buffer through storage completion",
        "display_surface": "Mission 1 rear display",
        "presentation_path": "Mission 1 rear display presentation path",
        "preview_buffer_ownership": "camera display pipeline owns RGB buffer through presentation",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def main() -> int:
    tool = load_tool()
    assert tool.validate(args()) == []
    assert tool.validate(args(target_role="stand-in", sensor_dma_executed="false")) == []
    failures = tool.validate(args(sensor_dma_executed="false"))
    assert any("sensor_dma_executed=true" in failure for failure in failures), failures
    failures = tool.validate(args(raw_source_kind="file_standin"))
    assert any("raw_source_kind" in failure for failure in failures), failures
    failures = tool.validate(args(raw_path="/mnt/ssd/mission1_native12/GP017602.raw"))
    assert any("mission1_native12" in failure and "raw_path" in failure for failure in failures), failures
    failures = tool.validate(args(write_path="bench_fused target-bench .gvid path"))
    assert any("bench_fused" in failure and "write_path" in failure for failure in failures), failures
    failures = tool.validate(args(presentation_path="off-camera preview decode receipt"))
    assert any("off-camera" in failure and "presentation_path" in failure for failure in failures), failures
    failures = tool.validate(args(target_name="Pi 5 stand-in"))
    assert any("target_name" in failure for failure in failures), failures
    print("test_mission1_camera_dispatch_inputs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
