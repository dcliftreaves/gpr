#!/usr/bin/env python3
"""Build a premium still-SR gate receipt skeleton.

This keeps the "spend time for an amazing still" pillar executable without
requiring private 50 MP / 100 MP fixtures in CI. By default it writes a
non-production receipt with placeholder artifacts. Real candidates can pass
explicit artifact paths and metrics, but production promotion remains guarded
by `tools/check_product_pillar_receipts.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate.v1"
NORMAL_BAYER_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": sha256_file(path)}


def write_placeholder(path: Path, role: str, payload: dict[str, Any]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".html":
        body = json.dumps(payload, indent=2, sort_keys=True)
        path.write_text(f"<!doctype html><title>{role}</title><pre>{body}</pre>\n", encoding="utf-8")
    else:
        path.write_text(json.dumps({"artifact_role": role, **payload}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact_ref(path)


def hash_candidate(args: argparse.Namespace) -> str:
    if args.checkpoint_sha256:
        return args.checkpoint_sha256.lower()
    h = hashlib.sha256()
    h.update(
        json.dumps(
            {
                "pipeline_id": args.pipeline_id,
                "target_role": args.target_role,
                "camera_count": args.camera_count,
                "fifty_mp_or_larger_count": args.fifty_mp_or_larger_count,
                "hundred_mp_or_larger_count": args.hundred_mp_or_larger_count,
                "cfa_phases": args.cfa_phase,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return h.hexdigest()


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    production_ready = bool(args.production_ready)
    placeholder_payload = {
        "pipeline_id": args.pipeline_id,
        "synthetic_or_placeholder": not args.real_artifacts,
        "production_evidence": production_ready,
        "note": "CI skeleton receipt; real still-SR promotion requires real editable raw, review media, dashboard, and gate metrics",
    }

    outputs = {
        "editable_dng": write_placeholder(args.out_dir / "editable_still_sr_placeholder.dng.json", "editable_dng", placeholder_payload),
        "editable_gpr": write_placeholder(args.out_dir / "editable_still_sr_placeholder.gpr.json", "editable_gpr", placeholder_payload),
        "review_tiff_or_prores": write_placeholder(args.out_dir / "review_still_sr_placeholder.tiff.json", "review_tiff_or_prores", placeholder_payload),
        "dashboard": write_placeholder(args.out_dir / "dashboard.html", "dashboard", placeholder_payload),
    }

    return {
        "schema": SCHEMA,
        "candidate": {
            "pipeline_id": args.pipeline_id,
            "checkpoint_sha256": hash_candidate(args),
            "target_role": args.target_role,
        },
        "fixture_summary": {
            "camera_count": args.camera_count,
            "fifty_mp_or_larger_count": args.fifty_mp_or_larger_count,
            "hundred_mp_or_larger_count": args.hundred_mp_or_larger_count,
            "cfa_phases": args.cfa_phase,
        },
        "outputs": outputs,
        "baseline_comparison": {
            "passed_gate": args.passed_gate,
            "worst_lpips": args.worst_lpips,
            "worst_delta_e2000": args.worst_delta_e2000,
            "min_raw_psnr_delta_db": args.min_raw_psnr_delta_db,
            "editor_latitude_score_delta": args.editor_latitude_score_delta,
        },
        "noise_policy": {
            "mode": args.noise_policy_mode,
            "raw_noise_signal_audit_passed": args.raw_noise_signal_audit_passed,
        },
        "production_ready": production_ready,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--pipeline-id", default="premium_still_sr_skeleton_v1")
    ap.add_argument("--checkpoint-sha256")
    ap.add_argument("--target-role", default="offline_premium_still")
    ap.add_argument("--camera-count", type=int, default=0)
    ap.add_argument("--fifty-mp-or-larger-count", type=int, default=0)
    ap.add_argument("--hundred-mp-or-larger-count", type=int, default=0)
    ap.add_argument("--cfa-phase", action="append", choices=NORMAL_BAYER_PHASES, default=None)
    ap.add_argument("--passed-gate", action="store_true")
    ap.add_argument("--worst-lpips", type=float, default=1.0)
    ap.add_argument("--worst-delta-e2000", type=float, default=99.0)
    ap.add_argument("--min-raw-psnr-delta-db", type=float, default=0.0)
    ap.add_argument("--editor-latitude-score-delta", type=float, default=0.0)
    ap.add_argument("--noise-policy-mode", default="requires_calibrated_camera_noise_sidecar")
    ap.add_argument("--raw-noise-signal-audit-passed", action="store_true")
    ap.add_argument("--production-ready", action="store_true")
    ap.add_argument("--real-artifacts", action="store_true")
    args = ap.parse_args()

    if not args.cfa_phase:
        args.cfa_phase = ["RGGB"]
    if args.production_ready and not args.real_artifacts:
        print("build_premium_still_sr_gate_receipt: --production-ready requires --real-artifacts", file=sys.stderr)
        return 2

    receipt = build_receipt(args)
    path = args.out_dir / "premium_still_sr_gate_receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
