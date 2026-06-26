#!/usr/bin/env python3
"""Run the complete local Mission 1 closure package on a target host.

This is the one-command wrapper for the final numbered-list camera evidence.
It runs the same components used by the self-hosted workflow:

1. camera/stand-in dispatch-label validation
2. target preflight receipt
3. aggregate camera closure run
4. optional compact local collection receipt
5. optional cleanup of heavy transient `.gvid` payloads

It is intended to run on the Pi/Mission target filesystem. It does not turn a
stand-in run into camera evidence; `--target-role camera` still requires real
sensor/DMA, camera storage, and camera display assertions.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.mission1_target_closure_package_run.v1"
DEFAULT_PREVIEW_TARGET = "mission1_preview_4x_1024x768"
DEFAULT_CARD_NAME = "Lexar Professional SILVER PLUS SDXC/microSDXC UHS-I (128GB-1TB)"
DEFAULT_CARD_NOTE = "Published 128GB-1TB SILVER PLUS profile: 205 MB/s read, 150 MB/s write; 64GB microSD is 205/100."


def bool_text(value: bool) -> str:
    return "true" if value else "false"


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


def dispatch_cmd(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tools/check_mission1_camera_dispatch_inputs.py"),
        "--target-role",
        args.target_role,
        "--target-name",
        args.target_name,
        "--sensor-dma-executed",
        bool_text(args.sensor_dma_executed),
        "--storage-handoff-executed",
        bool_text(args.storage_handoff_executed),
        "--ui-path-executed",
        bool_text(args.ui_path_executed),
        "--visual-checked",
        bool_text(args.visual_checked),
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
        "--raw-source-kind",
        args.raw_source_kind,
        "--raw-path",
        str(args.raw),
    ]


def preflight_cmd(args: argparse.Namespace, preflight_receipt: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "tools/mission1_camera_target_preflight.py"),
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
        "--repo-root",
        str(args.repo_root),
        "--raw",
        str(args.raw),
        "--output-dir",
        str(args.output_dir),
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
        "--source-width",
        str(args.source_width),
        "--source-height",
        str(args.source_height),
        "--raw-source-kind",
        args.raw_source_kind,
        "--frame-source",
        args.frame_source,
        "--write-path",
        args.write_path,
        "--storage-medium",
        args.storage_medium,
        "--display-surface",
        args.display_surface,
        "--presentation-path",
        args.presentation_path,
        "--output-json",
        str(preflight_receipt),
        "--require-ready",
    ]
    cmd += maybe_flag(args.camera_frame_source_ready, "--camera-frame-source-ready")
    cmd += maybe_flag(args.camera_storage_path_ready, "--camera-storage-path-ready")
    cmd += maybe_flag(args.camera_display_path_ready, "--camera-display-path-ready")
    return cmd


def hardware_audit_cmd(args: argparse.Namespace, hardware_audit_receipt: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "tools/mission1_camera_hardware_audit.py"),
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
        "--output-json",
        str(hardware_audit_receipt),
    ]
    if args.target_role == "camera":
        cmd.append("--require-camera")
    return cmd


def closure_cmd(args: argparse.Namespace, preflight_receipt: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "tools/run_mission1_camera_closure.py"),
        "--output-dir",
        str(args.output_dir),
        "--bench",
        str(args.bench),
        "--raw",
        str(args.raw),
        "--fused-decode-cli",
        str(args.fused_decode_cli),
        "--target-preflight-receipt",
        str(preflight_receipt),
        "--source-provenance-root",
        str(args.repo_root),
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
        "--storage-target-name",
        args.storage_target_name,
        "--storage-target-read-mbps",
        str(args.storage_target_read_mbps),
        "--storage-target-write-mbps",
        str(args.storage_target_write_mbps),
        "--storage-target-safety-margin",
        str(args.storage_target_safety_margin),
        "--storage-target-note",
        args.storage_target_note,
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
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
        "--stride-bytes",
        str(args.stride_bytes),
        "--bit-depth",
        str(args.bit_depth),
        "--handoff-blocker-cause",
        args.handoff_blocker_cause,
        "--preview-target",
        args.preview_target,
        "--preview-limit",
        str(args.preview_limit),
        "--display-surface",
        args.display_surface,
        "--presentation-path",
        args.presentation_path,
        "--preview-buffer-ownership",
        args.preview_buffer_ownership,
        "--preview-decode-path",
        args.preview_decode_path,
        "--preview-color-pipeline",
        args.preview_color_pipeline,
        "--preview-tone-pipeline",
        args.preview_tone_pipeline,
        "--preview-blocker-cause",
        args.preview_blocker_cause,
    ]
    cmd += maybe_flag(args.use_mission1_fll2_profile, "--use-mission1-fll2-profile")
    cmd += maybe_flag(args.no_decimate, "--no-decimate")
    if not args.no_decimate:
        cmd.extend(["--col-decimate", str(args.col_decimate), "--row-decimate", str(args.row_decimate)])
    cmd += maybe_flag(args.direct_gvid, "--direct-gvid")
    cmd += maybe_flag(args.sensor_dma_executed, "--sensor-dma-executed")
    cmd += maybe_flag(args.storage_handoff_executed, "--storage-handoff-executed")
    cmd += maybe_flag(args.ui_path_executed, "--ui-path-executed")
    cmd += maybe_flag(args.visual_checked, "--visual-checked")
    return cmd


def collection_cmd(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tools/collect_mission1_target_closure.py"),
        "--local-source-dir",
        str(args.output_dir),
        "--output-dir",
        str(args.collection_output_dir),
        "--include-timing-receipts",
    ]


def cleanup_heavy_outputs(output_dir: Path, *, dry_run: bool) -> dict[str, Any]:
    targets = [
        output_dir / "capture.gvid",
        output_dir / "capture_interrupted_tail.gvid",
        output_dir / "frames",
    ]
    rows = []
    for path in targets:
        row: dict[str, Any] = {"path": str(path), "exists": path.exists(), "removed": False}
        if path.exists() and not dry_run:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            row["removed"] = True
        rows.append(row)
    return {"name": "cleanup_heavy_outputs", "targets": rows, "dry_run": dry_run}


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_package(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    hardware_audit_receipt = args.output_dir / "hardware_audit_receipt.json"
    preflight_receipt = args.output_dir / "target_preflight_receipt.json"
    summary_path = args.output_dir / "target_closure_package_run.json"
    steps: list[dict[str, Any]] = []

    commands: list[tuple[str, list[str]]] = [("validate_dispatch_inputs", dispatch_cmd(args))]
    if args.target_role == "camera":
        commands.append(("camera_hardware_audit", hardware_audit_cmd(args, hardware_audit_receipt)))
    commands.extend(
        [
            ("target_preflight", preflight_cmd(args, preflight_receipt)),
            ("camera_closure_run", closure_cmd(args, preflight_receipt)),
        ]
    )

    for name, cmd in commands:
        step = run_step(name, cmd, cwd=ROOT, dry_run=args.dry_run and name != "validate_dispatch_inputs")
        steps.append(step)
        if step["returncode"] != 0:
            payload = summary_payload(args, steps, cleanup=None, production_ready=False, reason=f"{name}_failed")
            if not args.dry_run:
                write_summary(summary_path, payload)
            return payload, 1

    if args.collection_output_dir:
        if not args.dry_run:
            args.collection_output_dir.mkdir(parents=True, exist_ok=True)
        step = run_step("collect_compact_receipts", collection_cmd(args), cwd=ROOT, dry_run=args.dry_run)
        steps.append(step)
        if step["returncode"] != 0:
            payload = summary_payload(args, steps, cleanup=None, production_ready=False, reason="collect_compact_receipts_failed")
            if not args.dry_run:
                write_summary(summary_path, payload)
            return payload, 1

    cleanup = cleanup_heavy_outputs(args.output_dir, dry_run=args.dry_run) if args.cleanup_heavy else None
    production_ready = False
    closure_path = args.output_dir / "mission1_camera_closure_run.json"
    if closure_path.exists() and not args.dry_run:
        try:
            closure = json.loads(closure_path.read_text(encoding="utf-8"))
            production_ready = closure.get("verdict", {}).get("production_ready") is True
        except Exception:
            production_ready = False

    payload = summary_payload(args, steps, cleanup=cleanup, production_ready=production_ready, reason=None)
    if not args.dry_run:
        write_summary(summary_path, payload)
    return payload, 0


def summary_payload(
    args: argparse.Namespace,
    steps: list[dict[str, Any]],
    *,
    cleanup: dict[str, Any] | None,
    production_ready: bool,
    reason: str | None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dry_run": args.dry_run,
        "repo_root": str(args.repo_root),
        "output_dir": str(args.output_dir),
        "collection_output_dir": str(args.collection_output_dir) if args.collection_output_dir else None,
        "target": {
            "name": args.target_name,
            "role": args.target_role,
            "raw_source_kind": args.raw_source_kind,
        },
        "receipts": {
            "hardware_audit": str(args.output_dir / "hardware_audit_receipt.json"),
            "target_preflight": str(args.output_dir / "target_preflight_receipt.json"),
            "target_bench": str(args.output_dir / "labs_target_bench.json"),
            "camera_handoff": str(args.output_dir / "camera_handoff_receipt.json"),
            "preview_ui": str(args.output_dir / "preview_ui_receipt.json"),
            "closure_run": str(args.output_dir / "mission1_camera_closure_run.json"),
            "package_run": str(args.output_dir / "target_closure_package_run.json"),
        },
        "steps": steps,
        "cleanup": cleanup,
        "verdict": {
            "command_ready": all(step["returncode"] == 0 for step in steps),
            "production_ready": production_ready,
            "reason": reason,
        },
    }


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--collection-output-dir", type=Path)
    ap.add_argument("--scratch-dir", type=Path, default=Path("/mnt/ssd/gpr_work/tmp"))
    ap.add_argument("--raw", type=Path, default=Path("/mnt/ssd/mission1_native12/GP017602.raw"))
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
    ap.add_argument("--col-decimate", type=int, default=1)
    ap.add_argument("--row-decimate", type=int, default=1)
    ap.add_argument("--pixel-format", type=int, default=1)
    ap.add_argument("--direct-gvid", action="store_true", default=True)
    ap.add_argument("--use-mission1-fll2-profile", action="store_true")
    ap.add_argument("--storage-target-name", default=DEFAULT_CARD_NAME)
    ap.add_argument("--storage-target-read-mbps", type=float, default=205.0)
    ap.add_argument("--storage-target-write-mbps", type=float, default=150.0)
    ap.add_argument("--storage-target-safety-margin", type=float, default=0.90)
    ap.add_argument("--storage-target-note", default=DEFAULT_CARD_NOTE)
    ap.add_argument("--target-name", default="Pi 5 stand-in")
    ap.add_argument("--target-role", choices=("stand-in", "camera"), default="stand-in")
    ap.add_argument("--raw-source-kind", choices=("file_standin", "sensor_dma_capture", "camera_ring_buffer"), default="file_standin")
    ap.add_argument("--frame-source", default="file-backed Bayer stand-in")
    ap.add_argument("--memory-ownership", default="synchronous submit; caller owns input through return")
    ap.add_argument("--write-path", default="bench_fused target-bench .gvid path")
    ap.add_argument("--sensor-dma-executed", action="store_true")
    ap.add_argument("--storage-handoff-executed", action="store_true")
    ap.add_argument("--storage-medium", default="target-bench filesystem stand-in")
    ap.add_argument("--storage-ownership", default="OS/page-cache writeback; not camera firmware DMA")
    ap.add_argument("--stride-bytes", type=int, default=8192)
    ap.add_argument("--bit-depth", type=int, default=14)
    ap.add_argument("--handoff-blocker-cause", default="camera sensor/DMA and camera storage handoff not executed")
    ap.add_argument("--camera-frame-source-ready", action="store_true")
    ap.add_argument("--camera-storage-path-ready", action="store_true")
    ap.add_argument("--camera-display-path-ready", action="store_true")
    ap.add_argument("--preview-target", default=DEFAULT_PREVIEW_TARGET)
    ap.add_argument("--preview-limit", type=int, default=0)
    ap.add_argument("--ui-path-executed", action="store_true")
    ap.add_argument("--visual-checked", action="store_true")
    ap.add_argument("--display-surface", default="stand-in raw preview receipt output")
    ap.add_argument("--presentation-path", default="off-camera preview decode receipt")
    ap.add_argument("--preview-buffer-ownership", default="process-owned RGB output buffer")
    ap.add_argument("--preview-decode-path", default="fused_decode_cli mission1_preview_4x_1024x768")
    ap.add_argument("--preview-color-pipeline", default="full-frame Bayer decode to RGB preview")
    ap.add_argument("--preview-tone-pipeline", default="preview tone path from fused decoder target")
    ap.add_argument("--preview-blocker-cause", default="Mission 1 camera UI/display path not executed")
    ap.add_argument("--cleanup-heavy", action="store_true", help="remove capture.gvid, interrupted-tail .gvid, and frame dir after receipts are written")
    ap.add_argument("--dry-run", action="store_true", help="write/print planned commands without running target encode/decode")
    return ap


def main() -> int:
    args = parser().parse_args()
    payload, status = build_package(args)
    print(json.dumps(payload, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
