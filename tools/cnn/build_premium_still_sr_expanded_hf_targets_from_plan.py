#!/usr/bin/env python3
"""Execute a premium still-SR target expansion plan.

The plan builder chooses the scenes and ISO-matched noise sidecars. This
executor turns that plan into artifacts: deterministic degraded candidate raws,
per-scene HF residual target NPZs, and a merged target set that includes the
existing baseline target receipt.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_expanded_hf_target_build.v1"
ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def run_command(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = time.perf_counter() - t0
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "elapsed_s": elapsed,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def selected_sidecar(row: dict[str, Any]) -> str:
    selected = row.get("selected_noise_sidecars")
    if isinstance(selected, list) and selected and isinstance(selected[0], dict):
        path = selected[0].get("path")
        if path:
            return str(path)
    sidecars = row.get("noise_sidecars")
    if isinstance(sidecars, list) and sidecars and isinstance(sidecars[0], dict):
        path = sidecars[0].get("path")
        if path:
            return str(path)
    raise ValueError(f"target row {row.get('scene_id')} has no usable noise sidecar")


def planned_scene_commands(
    row: dict[str, Any],
    output_dir: Path,
    python: str,
    *,
    include_raw_cfa_features: bool = False,
) -> tuple[Path, Path, list[list[str]]]:
    scene_id = str(row["scene_id"])
    source = str(row["source_path"])
    sidecar = selected_sidecar(row)
    candidate_raw = output_dir / "candidate_raws" / f"{scene_id}_box2_candidate.raw"
    target_dir = output_dir / scene_id
    build_target_cmd = [
        python,
        "tools/cnn/build_premium_still_sr_hf_residual_targets.py",
        "--source-dng",
        source,
        "--candidate-raw",
        str(candidate_raw),
        "--output-dir",
        str(target_dir),
        "--noise-sidecar",
        sidecar,
        "--crop-size",
        "768",
        "--crop-grid",
        "3",
        "--block",
        "16",
        "--output-bps",
        "16",
        "--contact-rows",
        "9",
    ]
    if include_raw_cfa_features:
        build_target_cmd.append("--include-raw-cfa-features")
    commands = [
        [
            python,
            "tools/cnn/build_premium_still_sr_degraded_candidate_raw.py",
            "--source-dng",
            source,
            "--output-raw",
            str(candidate_raw),
        ],
        build_target_cmd,
    ]
    return candidate_raw, target_dir, commands


def existing_target_paths(plan: dict[str, Any]) -> list[str]:
    merged_path = Path(plan["sources"]["merged_target"])
    merged = load_json(merged_path)
    sources = merged.get("sources", [])
    return [str(row["path"]) for row in sources if isinstance(row, dict) and row.get("path")]


def build(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_json(args.plan)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = plan.get("selected_new_targets", [])
    if args.max_scenes is not None:
        rows = rows[: max(0, args.max_scenes)]
    if not isinstance(rows, list):
        raise TypeError("selected_new_targets must be a list")

    scene_results: list[dict[str, Any]] = []
    target_npzs: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_raw, target_dir, commands = planned_scene_commands(
            row,
            output_dir,
            args.python,
            include_raw_cfa_features=args.include_raw_cfa_features,
        )
        scene_result: dict[str, Any] = {
            "scene_id": row.get("scene_id"),
            "source_path": row.get("source_path"),
            "source_iso": row.get("source_iso"),
            "selected_noise_sidecar": selected_sidecar(row),
            "candidate_raw": str(candidate_raw),
            "target_dir": str(target_dir),
            "commands": commands,
            "skipped_existing": False,
            "built": False,
        }
        target_npz = target_dir / "hf_residual_targets.npz"
        if args.dry_run:
            scene_results.append(scene_result)
            continue
        if target_npz.exists() and not args.force:
            scene_result["skipped_existing"] = True
            scene_result["built"] = True
            target_npzs.append(str(target_npz))
            scene_results.append(scene_result)
            continue
        for cmd in commands:
            result = run_command(cmd, cwd=ROOT)
            scene_result.setdefault("command_results", []).append(result)
            if result["returncode"] != 0:
                scene_result["built"] = False
                scene_results.append(scene_result)
                raise RuntimeError(f"{row.get('scene_id')} failed command: {' '.join(cmd)}\n{result['stderr']}")
        scene_result["built"] = target_npz.exists()
        target_npzs.append(str(target_npz))
        scene_results.append(scene_result)

    merge_inputs = existing_target_paths(plan) + target_npzs
    merge_cmd = [
        args.python,
        "tools/cnn/merge_premium_still_sr_hf_residual_targets.py",
        "--output-dir",
        str(output_dir / "merged"),
    ]
    for path in merge_inputs:
        merge_cmd += ["--target", path]

    merge_result: dict[str, Any] | None = None
    if not args.dry_run:
        merge_result = run_command(merge_cmd, cwd=ROOT)
        if merge_result["returncode"] != 0:
            raise RuntimeError(f"merge failed: {merge_result['stderr']}")

    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "plan": str(args.plan),
        "output_dir": str(output_dir),
        "dry_run": args.dry_run,
        "include_raw_cfa_features": args.include_raw_cfa_features,
        "scene_count": len(scene_results),
        "scene_results": scene_results,
        "merge_inputs": merge_inputs,
        "merge_command": merge_cmd,
        "merge_result": merge_result,
        "artifacts": {
            "receipt": str(output_dir / "expanded_target_build_receipt.json"),
            "merged_receipt": str(output_dir / "merged" / "merge_receipt.json"),
            "merged_npz": str(output_dir / "merged" / "hf_residual_targets_merged.npz"),
        },
    }
    receipt_path = output_dir / "expanded_target_build_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--max-scenes", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-raw-cfa-features", action="store_true")
    args = ap.parse_args()
    receipt = build(args)
    print(
        json.dumps(
            {
                "receipt": receipt["artifacts"]["receipt"],
                "scene_count": receipt["scene_count"],
                "dry_run": receipt["dry_run"],
                "merged_npz": receipt["artifacts"]["merged_npz"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
