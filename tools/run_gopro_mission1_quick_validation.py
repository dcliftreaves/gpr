#!/usr/bin/env python3
"""Run the shortest GoPro-side Mission 1 validation sequence.

This target-side wrapper probes the camera raw source, runs the Mission 1
closure package, and validates the compact receipts. It is a convenience layer
for firmware/Labs evaluation; dry-run output is command evidence only and never
production evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.gopro_mission1_quick_validation.v1"
DEFAULT_OUTPUT = Path("/mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera")
DEFAULT_COLLECTION = Path("/mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera_compact")
DEFAULT_REPO_ROOT = Path("/mnt/ssd/gpr_work/worktrees/current_goal_sync")
DEFAULT_RAW = Path("/dev/mission1/sensor_dma_ring")


def maybe_flag(enabled: bool, flag: str) -> list[str]:
    return [flag] if enabled else []


def run_step(name: str, cmd: list[str], *, cwd: Path, dry_run: bool = False) -> dict[str, Any]:
    started = time.time()
    if dry_run:
        return {
            "name": name,
            "cmd": cmd,
            "returncode": 0,
            "elapsed_s": 0.0,
            "stdout_tail": ["dry-run"],
            "stderr_tail": [],
        }
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "name": name,
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout_tail": proc.stdout.splitlines()[-40:],
        "stderr_tail": proc.stderr.splitlines()[-40:],
    }


def source_probe_cmd(args: argparse.Namespace, receipt: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "tools/mission1_camera_source_probe.py"),
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
        "--raw",
        str(args.raw),
        "--raw-source-kind",
        args.raw_source_kind,
        "--source-width",
        str(args.source_width),
        "--source-height",
        str(args.source_height),
        "--stride-bytes",
        str(args.stride_bytes),
        "--bit-depth",
        str(args.bit_depth),
        "--pixel-format",
        str(args.pixel_format),
        "--output-json",
        str(receipt),
        "--require-ready",
    ]
    if args.target_host:
        cmd.extend(["--target-host", args.target_host])
    return cmd


def source_probe_check_cmd(receipt: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tools/check_mission1_camera_source_probe.py"),
        str(receipt),
    ]


def closure_package_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "tools/run_mission1_target_closure_package.py"),
        "--output-dir",
        str(args.output_dir),
        "--collection-output-dir",
        str(args.collection_output_dir),
        "--repo-root",
        str(args.repo_root),
        "--raw",
        str(args.raw),
        "--scratch-dir",
        str(args.scratch_dir),
        "--bench",
        str(args.bench),
        "--labs-encoder-bench-cli",
        str(args.labs_encoder_bench_cli),
        "--fused-decode-cli",
        str(args.fused_decode_cli),
        "--preview-cli",
        str(args.preview_cli),
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
        "--raw-source-kind",
        args.raw_source_kind,
        "--target-fps",
        str(args.target_fps),
        "--frames",
        str(args.frames),
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
        "--stride-bytes",
        str(args.stride_bytes),
        "--bit-depth",
        str(args.bit_depth),
        "--frame-source",
        args.frame_source,
        "--write-path",
        args.write_path,
        "--storage-medium",
        args.storage_medium,
        "--storage-ownership",
        args.storage_ownership,
        "--display-surface",
        args.display_surface,
        "--presentation-path",
        args.presentation_path,
        "--preview-buffer-ownership",
        args.preview_buffer_ownership,
        "--handoff-blocker-cause",
        args.handoff_blocker_cause,
        "--preview-blocker-cause",
        args.preview_blocker_cause,
    ]
    cmd += maybe_flag(args.no_decimate, "--no-decimate")
    cmd += maybe_flag(args.direct_gvid, "--direct-gvid")
    cmd += maybe_flag(args.use_mission1_fll2_profile, "--use-mission1-fll2-profile")
    cmd += maybe_flag(args.camera_frame_source_ready, "--camera-frame-source-ready")
    cmd += maybe_flag(args.camera_storage_path_ready, "--camera-storage-path-ready")
    cmd += maybe_flag(args.camera_display_path_ready, "--camera-display-path-ready")
    cmd += maybe_flag(args.sensor_dma_executed, "--sensor-dma-executed")
    cmd += maybe_flag(args.storage_handoff_executed, "--storage-handoff-executed")
    cmd += maybe_flag(args.ui_path_executed, "--ui-path-executed")
    cmd += maybe_flag(args.visual_checked, "--visual-checked")
    cmd += maybe_flag(args.cleanup_heavy, "--cleanup-heavy")
    return cmd


def receipt_check_cmds(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    return [
        (
            "check_camera_handoff",
            [
                sys.executable,
                str(ROOT / "tools/check_labs_camera_handoff_receipt.py"),
                str(args.output_dir / "camera_handoff_receipt.json"),
            ],
        ),
        (
            "check_preview_ui",
            [
                sys.executable,
                str(ROOT / "tools/check_labs_preview_ui_receipt.py"),
                str(args.output_dir / "preview_ui_receipt.json"),
            ],
        ),
        (
            "check_closure_run",
            [
                sys.executable,
                str(ROOT / "tools/check_mission1_camera_closure_run.py"),
                str(args.output_dir / "mission1_camera_closure_run.json"),
            ],
        ),
    ]


def summary_payload(
    args: argparse.Namespace,
    steps: list[dict[str, Any]],
    *,
    reason: str | None,
) -> dict[str, Any]:
    production_ready = False
    closure_path = args.output_dir / "mission1_camera_closure_run.json"
    if closure_path.exists() and not args.dry_run:
        try:
            closure = json.loads(closure_path.read_text(encoding="utf-8"))
            production_ready = closure.get("verdict", {}).get("production_ready") is True
        except Exception:
            production_ready = False
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dry_run": args.dry_run,
        "repo_root": str(args.repo_root),
        "output_dir": str(args.output_dir),
        "collection_output_dir": str(args.collection_output_dir),
        "target": {
            "host": args.target_host or "local",
            "name": args.target_name,
            "role": args.target_role,
            "raw_source_kind": args.raw_source_kind,
        },
        "receipts": {
            "source_probe": str(args.output_dir / "source_probe.json"),
            "camera_handoff": str(args.output_dir / "camera_handoff_receipt.json"),
            "preview_ui": str(args.output_dir / "preview_ui_receipt.json"),
            "closure_run": str(args.output_dir / "mission1_camera_closure_run.json"),
            "quick_validation": str(args.output_dir / "quick_validation.json"),
        },
        "steps": steps,
        "verdict": {
            "command_ready": all(step["returncode"] == 0 for step in steps),
            "production_ready": production_ready,
            "reason": reason,
        },
    }


def run_validation(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    source_probe = args.output_dir / "source_probe.json"
    steps: list[dict[str, Any]] = []
    commands: list[tuple[str, list[str], bool]] = [
        ("source_probe", source_probe_cmd(args, source_probe), True),
        ("check_source_probe", source_probe_check_cmd(source_probe), True),
        ("target_closure_package", closure_package_cmd(args), True),
    ]
    commands.extend((name, cmd, True) for name, cmd in receipt_check_cmds(args))

    for name, cmd, allow_dry_run in commands:
        step = run_step(name, cmd, cwd=ROOT, dry_run=args.dry_run and allow_dry_run)
        steps.append(step)
        if step["returncode"] != 0:
            payload = summary_payload(args, steps, reason=f"{name}_failed")
            if not args.dry_run:
                (args.output_dir / "quick_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            return payload, 1

    payload = summary_payload(args, steps, reason=None)
    if not args.dry_run:
        (args.output_dir / "quick_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload, 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--collection-output-dir", type=Path, default=DEFAULT_COLLECTION)
    ap.add_argument("--scratch-dir", type=Path, default=Path("/mnt/ssd/gpr_work/tmp"))
    ap.add_argument("--target-host", default="")
    ap.add_argument("--target-name", default="Mission 1")
    ap.add_argument("--target-role", choices=("stand-in", "camera"), default="camera")
    ap.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--raw-source-kind", choices=("file_standin", "sensor_dma_capture", "camera_ring_buffer"), default="sensor_dma_capture")
    ap.add_argument("--bench", type=Path, default=Path("build-closure/source/app/bench_fused/bench_fused"))
    ap.add_argument("--labs-encoder-bench-cli", type=Path, default=Path("build-closure/bin/labs_encoder_bench_cli"))
    ap.add_argument("--fused-decode-cli", type=Path, default=Path("build-closure/bin/fused_decode_cli"))
    ap.add_argument("--preview-cli", type=Path, default=Path("build-closure/bin/gvid_preview_rgb_cli"))
    ap.add_argument("--frames", type=int, default=1440)
    ap.add_argument("--target-fps", type=float, default=20.0)
    ap.add_argument("--source-width", type=int, default=4096)
    ap.add_argument("--source-height", type=int, default=3072)
    ap.add_argument("--capture-width", type=int, default=4096)
    ap.add_argument("--capture-height", type=int, default=3072)
    ap.add_argument("--quality", type=int, default=8)
    ap.add_argument("--wavelet-levels", type=int, default=1)
    ap.add_argument("--no-decimate", action="store_true", default=True)
    ap.add_argument("--pixel-format", type=int, default=1)
    ap.add_argument("--stride-bytes", type=int, default=8192)
    ap.add_argument("--bit-depth", type=int, default=14)
    ap.add_argument("--direct-gvid", action="store_true", default=True)
    ap.add_argument("--use-mission1-fll2-profile", action="store_true", default=True)
    ap.add_argument("--frame-source", default="Mission 1 sensor DMA")
    ap.add_argument("--write-path", default="Mission 1 camera storage .gvid path")
    ap.add_argument("--storage-medium", default="Mission 1 SD path")
    ap.add_argument("--storage-ownership", default="camera firmware owns write buffer through storage completion")
    ap.add_argument("--display-surface", default="Mission 1 rear display")
    ap.add_argument("--presentation-path", default="Mission 1 rear display presentation path")
    ap.add_argument("--preview-buffer-ownership", default="camera display process RGB output buffer")
    ap.add_argument("--handoff-blocker-cause", default="none")
    ap.add_argument("--preview-blocker-cause", default="none")
    ap.add_argument("--camera-frame-source-ready", action="store_true", default=True)
    ap.add_argument("--camera-storage-path-ready", action="store_true", default=True)
    ap.add_argument("--camera-display-path-ready", action="store_true", default=True)
    ap.add_argument("--sensor-dma-executed", action="store_true", default=True)
    ap.add_argument("--storage-handoff-executed", action="store_true", default=True)
    ap.add_argument("--ui-path-executed", action="store_true", default=True)
    ap.add_argument("--visual-checked", action="store_true", default=True)
    ap.add_argument("--cleanup-heavy", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main() -> int:
    args = parser().parse_args()
    payload, status = run_validation(args)
    print(json.dumps(payload, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
