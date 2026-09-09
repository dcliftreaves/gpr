#!/usr/bin/env python3
"""Regression tests for Mission 1 camera hardware enumeration audits."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/mission1_camera_hardware_audit.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("mission1_camera_hardware_audit", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse(tool, *argv: str):
    return tool.parser().parse_args(list(argv))


def payload(*, camera: bool) -> dict:
    rpicam = "Available cameras\n-----------------\n0 : imx708 [4608x2592]\n" if camera else "No cameras available!\n"
    libcamera = "Available cameras\n-----------------\n0 : imx708 [4608x2592]\n" if camera else "No cameras available!\n"
    names = (
        "/sys/class/video4linux/video0/name=unicam\n"
        "/sys/class/video4linux/video1/name=imx708\n"
        if camera
        else "/sys/class/video4linux/video20/name=pispbe-input\n"
    )
    return {
        "created_utc": "2026-06-25T00:00:00Z",
        "commands": [
            {
                "name": "tool_paths",
                "returncode": 0,
                "stdout": "\n".join(
                    [
                        "v4l2-ctl=/usr/bin/v4l2-ctl",
                        "media-ctl=/usr/bin/media-ctl",
                        "libcamera-hello=/usr/bin/libcamera-hello",
                        "rpicam-hello=/usr/bin/rpicam-hello",
                        "rpicam-raw=/usr/bin/rpicam-raw",
                    ]
                ),
                "stderr": "",
            },
            {"name": "rpicam_list_cameras", "returncode": 0, "stdout": rpicam, "stderr": ""},
            {"name": "libcamera_list_cameras", "returncode": 0, "stdout": libcamera, "stderr": ""},
            {"name": "video4linux_names", "returncode": 0, "stdout": names, "stderr": ""},
        ],
    }


def main() -> int:
    tool = load_tool()
    no_camera = tool.build_report(parse(tool), payload(camera=False), {"returncode": 0})
    assert no_camera["verdict"]["hardware_ready_for_camera_source"] is False
    assert "no camera sensor is enumerated by rpicam/libcamera/V4L" in no_camera["blockers"]
    assert no_camera["summary"]["video_node_count"] == 1
    assert no_camera["summary"]["sensor_like_v4l_node_count"] == 0

    ready = tool.build_report(parse(tool), payload(camera=True), {"returncode": 0})
    assert ready["verdict"]["hardware_ready_for_camera_source"] is True
    assert ready["blockers"] == []
    assert ready["summary"]["camera_enumerated"] is True
    assert ready["summary"]["sensor_like_v4l_node_count"] == 2

    print("test_mission1_camera_hardware_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
