#!/usr/bin/env python3
"""Collect Mission 1 closure receipts from a target host.

The target-side aggregate run writes five compact JSON files:

- hardware_audit_receipt.json
- target_preflight_receipt.json
- labs_target_bench.json
- mission1_camera_closure_run.json
- camera_handoff_receipt.json
- preview_ui_receipt.json

With `--include-timing-receipts`, the collector also copies the small timing
receipt used by the numbered-list readiness gate:

- preview_decode_1024x768/receipt.json

It intentionally does not copy `.gvid` payloads or frame data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_target_closure_collection.v1"
ROOT = Path(__file__).resolve().parents[1]
COMPACT_FILES = (
    "hardware_audit_receipt.json",
    "target_preflight_receipt.json",
    "labs_target_bench.json",
    "mission1_camera_closure_run.json",
    "camera_handoff_receipt.json",
    "preview_ui_receipt.json",
)
TIMING_FILES = (
    "preview_decode_1024x768/receipt.json",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def run(cmd: list[str]) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout_tail": proc.stdout.splitlines()[-40:],
        "stderr_tail": proc.stderr.splitlines()[-40:],
    }


def copy_local(source_dir: Path, output_dir: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    copied = []
    for name in names:
        src = source_dir / name
        dst = output_dir / name
        if not src.exists():
            copied.append({"file": name, "source": str(src), "output": str(dst), "copied": False})
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        copied.append({"file": name, "source": str(src), "output": str(dst), "copied": True})
    return copied


def copy_remote(host: str, remote_dir: str, output_dir: Path, timeout_s: int, names: tuple[str, ...]) -> list[dict[str, Any]]:
    copied = []
    for name in names:
        dst = output_dir / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        remote = f"{host}:{remote_dir.rstrip('/')}/{name}"
        step = run(
            [
                "scp",
                "-o",
                "BatchMode=yes",
                "-o",
                f"ConnectTimeout={timeout_s}",
                remote,
                str(dst),
            ]
        )
        copied.append(
            {
                "file": name,
                "source": remote,
                "output": str(dst),
                "copied": step["returncode"] == 0,
                "step": step,
            }
        )
    return copied


def file_rows(output_dir: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = []
    for name in names:
        path = output_dir / name
        row: dict[str, Any] = {"file": name, "path": str(path), "exists": path.exists()}
        if path.exists():
            row["sha256"] = sha256_file(path)
            try:
                data = read_json(path)
            except Exception as exc:
                row["json_error"] = str(exc)
            else:
                row["schema"] = data.get("schema")
                if isinstance(data.get("target"), dict):
                    row["target"] = data["target"]
                if isinstance(data.get("verdict"), dict):
                    row["verdict"] = data["verdict"]
        rows.append(row)
    return rows


def build_collection(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    file_names = COMPACT_FILES + (TIMING_FILES if args.include_timing_receipts else ())
    if args.local_source_dir:
        copy_steps = copy_local(args.local_source_dir, args.output_dir, file_names)
        source = {"mode": "local", "path": str(args.local_source_dir)}
    else:
        copy_steps = copy_remote(args.target_host, args.remote_dir, args.output_dir, args.ssh_timeout_s, file_names)
        source = {"mode": "ssh", "target_host": args.target_host, "remote_dir": args.remote_dir}

    copied_ok = all(row.get("copied") for row in copy_steps)
    validation = {"returncode": 1, "stdout_tail": [], "stderr_tail": ["copy failed"]}
    closure_path = args.output_dir / "mission1_camera_closure_run.json"
    if copied_ok:
        validation = run([sys.executable, str(ROOT / "tools/check_mission1_camera_closure_run.py"), str(closure_path)])

    closure: dict[str, Any] = {}
    if closure_path.exists():
        try:
            closure = read_json(closure_path)
        except Exception:
            closure = {}

    collection_valid = copied_ok and validation["returncode"] == 0
    closure_production_ready = closure.get("verdict", {}).get("production_ready") is True
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "output_dir": str(args.output_dir),
        "include_timing_receipts": bool(args.include_timing_receipts),
        "copy_steps": copy_steps,
        "files": file_rows(args.output_dir, file_names),
        "validation": validation,
        "closure_verdict": closure.get("verdict", {}),
        "verdict": {
            "collection_valid": collection_valid,
            "production_ready": collection_valid and closure_production_ready,
        },
    }
    collection_path = args.output_dir / "collection_receipt.json"
    collection_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt, 0 if receipt["verdict"]["collection_valid"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--target-host", help="SSH host to copy compact target receipts from")
    source.add_argument("--local-source-dir", type=Path, help="Local compact receipt source dir for tests/replays")
    ap.add_argument("--remote-dir", default="", help="Remote directory containing compact closure receipts")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--ssh-timeout-s", type=int, default=5)
    ap.add_argument("--include-timing-receipts", action="store_true", help="also copy preview_decode_1024x768/receipt.json")
    args = ap.parse_args()

    if args.target_host and not args.remote_dir:
        ap.error("--remote-dir is required with --target-host")

    try:
        receipt, status = build_collection(args)
    except Exception as exc:
        print(f"collect_mission1_target_closure: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_dir": receipt["output_dir"],
                "collection_valid": receipt["verdict"]["collection_valid"],
                "production_ready": receipt["verdict"]["production_ready"],
            },
            indent=2,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
