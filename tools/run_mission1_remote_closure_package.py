#!/usr/bin/env python3
"""Launch the Mission 1 target-side closure package over SSH.

This is the host-side companion to `run_mission1_target_closure_package.py`.
It does not create camera evidence by itself; production still requires the
target-side package to run with real sensor/DMA, storage handoff, and display
execution flags, then emit receipts that pass the existing validators.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.mission1_remote_closure_package_run.v1"
DEFAULT_TARGET_HOST = "192.168.16.67"
DEFAULT_REMOTE_REPO = Path("/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup")
DEFAULT_REMOTE_OUTPUT = Path("/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera")
DEFAULT_REMOTE_COLLECTION = Path("/mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_compact")
DEFAULT_LOCAL_OUTPUT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera")
DEFAULT_RAW = Path("/mnt/ssd/mission1_native12/GP017602.raw")
DEFAULT_CAMERA_RAW = Path("/dev/mission1/sensor_dma_ring")
DEFAULT_TMP = Path("/mnt/ssd/gpr_work/tmp")
DEFAULT_BENCH = DEFAULT_REMOTE_REPO / "build-closure/source/app/bench_fused/bench_fused"
DEFAULT_LABS_SHIM = DEFAULT_REMOTE_REPO / "build-closure/bin/labs_encoder_bench_cli"
DEFAULT_DECODE = DEFAULT_REMOTE_REPO / "build-closure/bin/fused_decode_cli"
DEFAULT_PREVIEW = DEFAULT_REMOTE_REPO / "build-closure/bin/gvid_preview_rgb_cli"
EARLY_FAILURE_RECEIPTS = (
    "target_closure_package_run.json",
    "hardware_audit_receipt.json",
    "target_preflight_receipt.json",
)


def run(cmd: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout_tail": proc.stdout.splitlines()[-60:],
        "stderr_tail": proc.stderr.splitlines()[-60:],
        "stdout": proc.stdout,
    }


def maybe_flag(enabled: bool, flag: str) -> list[str]:
    return [flag] if enabled else []


def target_package_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        "python3",
        "tools/run_mission1_target_closure_package.py",
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
        "--repo-root",
        str(args.remote_repo_root),
        "--output-dir",
        str(args.remote_output_dir),
        "--collection-output-dir",
        str(args.remote_collection_output_dir),
        "--scratch-dir",
        str(args.remote_scratch_dir),
        "--raw",
        str(args.remote_raw),
        "--bench",
        str(args.remote_bench),
        "--labs-encoder-bench-cli",
        str(args.remote_labs_encoder_bench_cli),
        "--fused-decode-cli",
        str(args.remote_fused_decode_cli),
        "--preview-cli",
        str(args.remote_preview_cli),
        "--frames",
        str(args.frames),
        "--target-fps",
        str(args.target_fps),
        "--source-width",
        str(args.source_width),
        "--source-height",
        str(args.source_height),
        "--capture-width",
        str(args.capture_width),
        "--capture-height",
        str(args.capture_height),
        "--quality",
        str(args.quality),
        "--wavelet-levels",
        str(args.wavelet_levels),
        "--pixel-format",
        str(args.pixel_format),
        "--raw-source-kind",
        args.raw_source_kind,
        "--frame-source",
        args.frame_source,
        "--memory-ownership",
        args.memory_ownership,
        "--write-path",
        args.write_path,
        "--storage-medium",
        args.storage_medium,
        "--storage-ownership",
        args.storage_ownership,
        "--handoff-blocker-cause",
        args.handoff_blocker_cause,
        "--display-surface",
        args.display_surface,
        "--presentation-path",
        args.presentation_path,
        "--preview-buffer-ownership",
        args.preview_buffer_ownership,
        "--preview-blocker-cause",
        args.preview_blocker_cause,
    ]
    cmd += maybe_flag(args.use_mission1_fll2_profile, "--use-mission1-fll2-profile")
    cmd += maybe_flag(args.no_decimate, "--no-decimate")
    cmd += maybe_flag(args.direct_gvid, "--direct-gvid")
    cmd += maybe_flag(args.camera_frame_source_ready, "--camera-frame-source-ready")
    cmd += maybe_flag(args.camera_storage_path_ready, "--camera-storage-path-ready")
    cmd += maybe_flag(args.camera_display_path_ready, "--camera-display-path-ready")
    cmd += maybe_flag(args.sensor_dma_executed, "--sensor-dma-executed")
    cmd += maybe_flag(args.storage_handoff_executed, "--storage-handoff-executed")
    cmd += maybe_flag(args.ui_path_executed, "--ui-path-executed")
    cmd += maybe_flag(args.visual_checked, "--visual-checked")
    cmd += maybe_flag(args.cleanup_heavy, "--cleanup-heavy")
    cmd += maybe_flag(args.dry_run, "--dry-run")
    return cmd


def ssh_cmd(args: argparse.Namespace, target_cmd: list[str]) -> list[str]:
    remote = "cd " + shlex.quote(str(args.remote_repo_root)) + " && " + " ".join(shlex.quote(part) for part in target_cmd)
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={args.ssh_timeout_s}",
        args.target_host,
        remote,
    ]


def collect_cmd(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tools/collect_mission1_target_closure.py"),
        "--target-host",
        args.target_host,
        "--remote-dir",
        str(args.remote_output_dir),
        "--output-dir",
        str(args.local_output_dir),
        "--ssh-timeout-s",
        str(args.ssh_timeout_s),
        "--include-timing-receipts",
    ]


def copy_failure_receipts(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    args.local_output_dir.mkdir(parents=True, exist_ok=True)
    for name in EARLY_FAILURE_RECEIPTS:
        dst = args.local_output_dir / name
        remote = f"{args.target_host}:{str(args.remote_output_dir).rstrip('/')}/{name}"
        step = run(
            [
                "scp",
                "-o",
                "BatchMode=yes",
                "-o",
                f"ConnectTimeout={args.ssh_timeout_s}",
                remote,
                str(dst),
            ]
        )
        rows.append(
            {
                "file": name,
                "source": remote,
                "output": str(dst),
                "copied": step["returncode"] == 0,
                "step": {k: v for k, v in step.items() if k != "stdout"},
            }
        )
    copied_any = any(row["copied"] for row in rows)
    return {
        "name": "collect_early_failure_receipts",
        "returncode": 0 if copied_any else 1,
        "files": rows,
    }


def parse_json_from_stdout(stdout: str) -> dict[str, Any] | None:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def build_summary(
    args: argparse.Namespace,
    package_step: dict[str, Any],
    collection_step: dict[str, Any] | None,
    failure_collection_step: dict[str, Any] | None,
    package_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    collection_ok = collection_step is None or collection_step["returncode"] == 0
    package_ok = package_step["returncode"] == 0
    target_verdict = package_payload.get("verdict", {}) if isinstance(package_payload, dict) else {}
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_host": args.target_host,
        "dry_run": args.dry_run,
        "remote_repo_root": str(args.remote_repo_root),
        "remote_output_dir": str(args.remote_output_dir),
        "local_output_dir": str(args.local_output_dir),
        "target_role": args.target_role,
        "raw_source_kind": args.raw_source_kind,
        "camera_ready_flags": {
            "camera_frame_source_ready": args.camera_frame_source_ready,
            "camera_storage_path_ready": args.camera_storage_path_ready,
            "camera_display_path_ready": args.camera_display_path_ready,
            "sensor_dma_executed": args.sensor_dma_executed,
            "storage_handoff_executed": args.storage_handoff_executed,
            "ui_path_executed": args.ui_path_executed,
            "visual_checked": args.visual_checked,
        },
        "package_step": {k: v for k, v in package_step.items() if k != "stdout"},
        "target_package": package_payload,
        "collection_step": None if collection_step is None else {k: v for k, v in collection_step.items() if k != "stdout"},
        "failure_collection_step": failure_collection_step,
        "verdict": {
            "launch_valid": package_ok and collection_ok,
            "production_ready": target_verdict.get("production_ready") is True,
            "reason": None if package_ok and collection_ok else "package_or_collection_failed",
        },
    }


def run_remote(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    target_cmd = target_package_cmd(args)
    package_step = run(ssh_cmd(args, target_cmd))
    package_payload = parse_json_from_stdout(package_step["stdout"])

    collection_step = None
    failure_collection_step = None
    if package_step["returncode"] == 0 and not args.dry_run and not args.skip_collect:
        collection_step = run(collect_cmd(args))
    elif (
        package_step["returncode"] != 0
        and not args.dry_run
        and not args.skip_collect
        and not args.skip_failure_collect
    ):
        failure_collection_step = copy_failure_receipts(args)

    summary = build_summary(args, package_step, collection_step, failure_collection_step, package_payload)
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary, 0 if summary["verdict"]["launch_valid"] else 1


def apply_camera_ready_defaults(args: argparse.Namespace) -> None:
    if not args.camera_ready:
        return
    args.camera_frame_source_ready = True
    args.camera_storage_path_ready = True
    args.camera_display_path_ready = True
    args.sensor_dma_executed = True
    args.storage_handoff_executed = True
    args.ui_path_executed = True
    args.visual_checked = True
    args.raw_source_kind = "sensor_dma_capture"
    if args.remote_raw == DEFAULT_RAW:
        args.remote_raw = DEFAULT_CAMERA_RAW
    args.handoff_blocker_cause = "none"
    args.preview_blocker_cause = "none"


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-host", default=DEFAULT_TARGET_HOST)
    ap.add_argument("--ssh-timeout-s", type=int, default=5)
    ap.add_argument("--remote-repo-root", type=Path, default=DEFAULT_REMOTE_REPO)
    ap.add_argument("--remote-output-dir", type=Path, default=DEFAULT_REMOTE_OUTPUT)
    ap.add_argument("--remote-collection-output-dir", type=Path, default=DEFAULT_REMOTE_COLLECTION)
    ap.add_argument("--local-output-dir", type=Path, default=DEFAULT_LOCAL_OUTPUT)
    ap.add_argument("--remote-scratch-dir", type=Path, default=DEFAULT_TMP)
    ap.add_argument("--remote-raw", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--remote-bench", type=Path, default=DEFAULT_BENCH)
    ap.add_argument("--remote-labs-encoder-bench-cli", type=Path, default=DEFAULT_LABS_SHIM)
    ap.add_argument("--remote-fused-decode-cli", type=Path, default=DEFAULT_DECODE)
    ap.add_argument("--remote-preview-cli", type=Path, default=DEFAULT_PREVIEW)
    ap.add_argument("--target-name", default="Mission 1")
    ap.add_argument("--target-role", choices=("stand-in", "camera"), default="camera")
    ap.add_argument("--frames", type=int, default=1440)
    ap.add_argument("--target-fps", type=float, default=20.0)
    ap.add_argument("--source-width", type=int, default=4096)
    ap.add_argument("--source-height", type=int, default=3072)
    ap.add_argument("--capture-width", type=int, default=4096)
    ap.add_argument("--capture-height", type=int, default=3072)
    ap.add_argument("--quality", type=int, default=8)
    ap.add_argument("--wavelet-levels", type=int, default=1)
    ap.add_argument("--pixel-format", type=int, default=1)
    ap.add_argument("--raw-source-kind", choices=("file_standin", "sensor_dma_capture", "camera_ring_buffer"), default="file_standin")
    ap.add_argument("--use-mission1-fll2-profile", action="store_true", default=True)
    ap.add_argument("--no-decimate", action="store_true", default=True)
    ap.add_argument("--direct-gvid", action="store_true", default=True)
    ap.add_argument("--frame-source", default="sensor DMA")
    ap.add_argument("--memory-ownership", default="camera synchronous submit owns input through encode return")
    ap.add_argument("--write-path", default="Mission 1 camera storage writer path")
    ap.add_argument("--storage-medium", default="Mission 1 SD path")
    ap.add_argument("--storage-ownership", default="camera firmware owns write buffer through storage completion")
    ap.add_argument("--display-surface", default="Mission 1 rear display")
    ap.add_argument("--presentation-path", default="Mission 1 rear display presentation path")
    ap.add_argument("--preview-buffer-ownership", default="camera display process RGB output buffer")
    ap.add_argument("--handoff-blocker-cause", default="camera sensor/DMA and camera storage handoff not executed")
    ap.add_argument("--preview-blocker-cause", default="Mission 1 camera UI/display path not executed")
    ap.add_argument("--camera-ready", action="store_true", help="assert all real camera handoff/display paths are ready/executed")
    ap.add_argument("--camera-frame-source-ready", action="store_true")
    ap.add_argument("--camera-storage-path-ready", action="store_true")
    ap.add_argument("--camera-display-path-ready", action="store_true")
    ap.add_argument("--sensor-dma-executed", action="store_true")
    ap.add_argument("--storage-handoff-executed", action="store_true")
    ap.add_argument("--ui-path-executed", action="store_true")
    ap.add_argument("--visual-checked", action="store_true")
    ap.add_argument("--cleanup-heavy", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--skip-failure-collect", action="store_true", help="do not copy early-failure JSON receipts after a failed target package")
    ap.add_argument("--summary-json", type=Path)
    return ap


def main() -> int:
    args = parser().parse_args()
    apply_camera_ready_defaults(args)
    summary, status = run_remote(args)
    print(json.dumps(summary, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
