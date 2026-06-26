#!/usr/bin/env python3
"""Audit Mission 1/Pi camera hardware enumeration without reading frames."""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_camera_hardware_audit.v1"
REMOTE_SCRIPT = r'''
import json
import subprocess
import time
from pathlib import Path

def run(name, cmd, timeout=8):
    started = time.time()
    proc = subprocess.run(
        cmd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return {
        "name": name,
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

commands = [
    ("uname", "uname -a"),
    ("device_tree_model", "tr -d '\\0' </proc/device-tree/model 2>/dev/null || true"),
    ("device_tree_compatible", "tr '\\0' '\\n' </proc/device-tree/compatible 2>/dev/null || true"),
    ("tool_paths", "for t in v4l2-ctl media-ctl libcamera-hello rpicam-hello rpicam-raw vcgencmd; do printf '%s=' \"$t\"; command -v \"$t\" || true; done"),
    ("rpicam_list_cameras", "timeout 10 rpicam-hello --list-cameras"),
    ("libcamera_list_cameras", "timeout 10 libcamera-hello --list-cameras"),
    ("video4linux_names", "for p in /sys/class/video4linux/video*/name; do [ -f \"$p\" ] && printf '%s=' \"$p\" && cat \"$p\"; done"),
    ("media_models", "for p in /sys/class/media/media*/model; do [ -f \"$p\" ] && printf '%s=' \"$p\" && cat \"$p\"; done"),
    ("drm_status", "for p in /sys/class/drm/card*/status; do [ -f \"$p\" ] && printf '%s=' \"$p\" && cat \"$p\"; done"),
    ("boot_camera_config", "for f in /boot/firmware/config.txt /boot/config.txt; do [ -f \"$f\" ] && echo --- $f --- && grep -Ein 'camera|cam|csi|dtoverlay|start_x|gpu_mem|imx|ov' \"$f\" || true; done"),
    ("vcgencmd_camera", "vcgencmd get_camera 2>/dev/null || true"),
    ("dmesg_camera", "dmesg 2>&1 | grep -Ei 'camera|libcamera|rpicam|unicam|csi|imx|ov[0-9]|pisp|rp1|mission|gopro' || true"),
]
payload = {
    "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "commands": [run(name, cmd) for name, cmd in commands],
}
print(json.dumps(payload))
'''


def run_local_script() -> tuple[dict[str, Any], dict[str, Any] | None]:
    proc = subprocess.run(
        ["python3", "-"],
        input=REMOTE_SCRIPT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    step = {
        "cmd": ["python3", "-", "<mission1_camera_hardware_audit>"],
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr.splitlines()[-20:],
    }
    if proc.returncode != 0:
        return {"commands": []}, step
    return json.loads(proc.stdout), step


def run_remote_script(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    started = time.time()
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={args.ssh_timeout_s}",
            args.target_host,
            "python3",
            "-",
        ],
        input=REMOTE_SCRIPT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    step = {
        "cmd": ["ssh", args.target_host, "python3", "-", "<mission1_camera_hardware_audit>"],
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stderr_tail": proc.stderr.splitlines()[-20:],
    }
    if proc.returncode != 0:
        return {"commands": []}, step
    try:
        return json.loads(proc.stdout), step
    except json.JSONDecodeError as exc:
        step["returncode"] = 1
        step["stderr_tail"].append(f"invalid remote JSON: {exc}")
        return {"commands": []}, step


def command_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row.get("name"): row for row in payload.get("commands", []) if isinstance(row, dict)}


def stdout_for(commands: dict[str, dict[str, Any]], name: str) -> str:
    row = commands.get(name) or {}
    return str(row.get("stdout") or "")


def tool_paths(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        out[name.strip()] = value.strip()
    return out


def has_enumerated_camera(text: str) -> bool:
    lowered = text.lower()
    if "no cameras available" in lowered or "available cameras" not in lowered and "camera" not in lowered:
        return False
    patterns = (
        r"^\s*\d+\s*:",
        r"^\s*\[\d+\]",
        r"\bimx\d+",
        r"\bov\d+",
        r"\bcamera module\b",
    )
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def parse_name_lines(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if "=" not in line:
            continue
        path, name = line.split("=", 1)
        rows.append({"path": path.strip(), "name": name.strip()})
    return rows


def sensor_like_video_nodes(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        name = row["name"].lower()
        if any(token in name for token in ("imx", "ov", "camera", "unicam", "csi")):
            out.append(row)
    return out


def build_report(args: argparse.Namespace, payload: dict[str, Any], step: dict[str, Any] | None) -> dict[str, Any]:
    commands = command_map(payload)
    tools = tool_paths(stdout_for(commands, "tool_paths"))
    rpicam_text = stdout_for(commands, "rpicam_list_cameras")
    libcamera_text = stdout_for(commands, "libcamera_list_cameras")
    video_nodes = parse_name_lines(stdout_for(commands, "video4linux_names"))
    sensor_nodes = sensor_like_video_nodes(video_nodes)
    rpicam_has_camera = has_enumerated_camera(rpicam_text)
    libcamera_has_camera = has_enumerated_camera(libcamera_text)
    camera_enumerated = rpicam_has_camera or libcamera_has_camera or bool(sensor_nodes)

    checks = [
        {
            "name": "ssh/local audit command completed",
            "passed": step is None or step.get("returncode") == 0,
            "detail": f"returncode={(step or {}).get('returncode', 0)}",
        },
        {
            "name": "rpicam tooling available",
            "passed": bool(tools.get("rpicam-hello") and tools.get("rpicam-raw")),
            "detail": f"rpicam-hello={tools.get('rpicam-hello', '')} rpicam-raw={tools.get('rpicam-raw', '')}",
        },
        {
            "name": "libcamera tooling available",
            "passed": bool(tools.get("libcamera-hello")),
            "detail": tools.get("libcamera-hello", ""),
        },
        {
            "name": "v4l/media tooling available",
            "passed": bool(tools.get("v4l2-ctl") and tools.get("media-ctl")),
            "detail": f"v4l2-ctl={tools.get('v4l2-ctl', '')} media-ctl={tools.get('media-ctl', '')}",
        },
        {
            "name": "rpicam enumerates a camera",
            "passed": rpicam_has_camera,
            "detail": first_nonempty_line(rpicam_text),
        },
        {
            "name": "libcamera enumerates a camera",
            "passed": libcamera_has_camera,
            "detail": first_nonempty_line(libcamera_text),
        },
        {
            "name": "sensor-like V4L node present",
            "passed": bool(sensor_nodes),
            "detail": ", ".join(f"{row['path']}={row['name']}" for row in sensor_nodes[:8]) or "none",
        },
    ]
    blockers: list[str] = []
    if step is not None and step.get("returncode") != 0:
        blockers.append("target host hardware audit command failed")
    if not camera_enumerated:
        blockers.append("no camera sensor is enumerated by rpicam/libcamera/V4L")

    return {
        "schema": SCHEMA,
        "created_utc": payload.get("created_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": {
            "host": args.target_host or "local",
            "name": args.target_name,
            "role": args.target_role,
        },
        "target_step": step,
        "summary": {
            "camera_enumerated": camera_enumerated,
            "rpicam_has_camera": rpicam_has_camera,
            "libcamera_has_camera": libcamera_has_camera,
            "sensor_like_v4l_node_count": len(sensor_nodes),
            "video_node_count": len(video_nodes),
            "tools": tools,
        },
        "video_nodes": video_nodes,
        "sensor_like_video_nodes": sensor_nodes,
        "commands": payload.get("commands", []),
        "checks": checks,
        "blockers": blockers,
        "verdict": {
            "hardware_ready_for_camera_source": camera_enumerated and not blockers,
            "remaining_blocker_count": len(blockers),
        },
    }


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-host", default="")
    ap.add_argument("--ssh-timeout-s", type=int, default=5)
    ap.add_argument("--target-name", default="Mission 1")
    ap.add_argument("--target-role", choices=("stand-in", "camera"), default="camera")
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--require-camera", action="store_true")
    return ap


def main() -> int:
    args = parser().parse_args()
    payload, step = run_remote_script(args) if args.target_host else run_local_script()
    report = build_report(args, payload, step)
    text = json.dumps(report, indent=2) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.require_camera and report["verdict"]["hardware_ready_for_camera_source"] is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
