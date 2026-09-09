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
FORBIDDEN_PRODUCTION_RUNTIME_INPUTS = {
    "ref",
    "reference",
    "reference_image",
    "source_raw",
    "source_rgb",
    "source_hf",
    "jpeg",
    "jpg",
    "jpeg_target",
    "jpg_target",
    "gate_metrics",
}


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


def output_refs(args: argparse.Namespace, placeholder_payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    if args.real_artifacts:
        return {
            "editable_dng": artifact_ref(args.editable_dng),
            "editable_gpr": artifact_ref(args.editable_gpr),
            "review_tiff_or_prores": artifact_ref(args.review_media),
            "dashboard": artifact_ref(args.dashboard_artifact),
        }
    return {
        "editable_dng": write_placeholder(args.out_dir / "editable_still_sr_placeholder.dng.json", "editable_dng", placeholder_payload),
        "editable_gpr": write_placeholder(args.out_dir / "editable_still_sr_placeholder.gpr.json", "editable_gpr", placeholder_payload),
        "review_tiff_or_prores": write_placeholder(args.out_dir / "review_still_sr_placeholder.tiff.json", "review_tiff_or_prores", placeholder_payload),
        "dashboard": write_placeholder(args.out_dir / "dashboard.html", "dashboard", placeholder_payload),
    }


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


def runtime_input_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_")


def production_validation_errors(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    for label, path in (
        ("--editable-dng", args.editable_dng),
        ("--editable-gpr", args.editable_gpr),
        ("--review-media", args.review_media),
        ("--dashboard-artifact", args.dashboard_artifact),
    ):
        if args.real_artifacts and path is None:
            errors.append(f"--real-artifacts requires {label}")
        elif args.production_ready and path is None:
            errors.append(f"--production-ready requires {label}")
        elif path is not None and not path.exists():
            errors.append(f"{label} path does not exist: {path}")
    if not args.production_ready:
        return errors
    if not args.real_artifacts:
        errors.append("--production-ready requires --real-artifacts")
    if not args.checkpoint_sha256:
        errors.append("--production-ready requires --checkpoint-sha256")
    elif len(args.checkpoint_sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in args.checkpoint_sha256):
        errors.append("--checkpoint-sha256 must be a 64-character hex SHA-256")
    required_runtime = {"candidate_raw", "camera_metadata"}
    runtime_inputs = set(args.runtime_input or [])
    missing_runtime = sorted(required_runtime - runtime_inputs)
    if missing_runtime:
        errors.append("--runtime-input is missing required production input(s): " + ", ".join(missing_runtime))
    forbidden_runtime = sorted(
        item
        for item in runtime_inputs
        if runtime_input_key(item) in FORBIDDEN_PRODUCTION_RUNTIME_INPUTS
    )
    if forbidden_runtime:
        errors.append("--runtime-input contains forbidden production input(s): " + ", ".join(forbidden_runtime))
    required_flags = (
        ("--passed-gate", args.passed_gate),
        ("--no-ref-runtime", args.no_ref_runtime),
        ("--forbidden-source-content-absent", args.forbidden_source_content_absent),
        ("--full-frame-gate-50mp-passed", args.full_frame_gate_50mp_passed),
        ("--full-frame-gate-100mp-passed", args.full_frame_gate_100mp_passed),
        ("--editor-latitude-passed", args.editor_latitude_passed),
        ("--beats-current-baseline", args.beats_current_baseline),
        ("--raw-noise-signal-audit-passed", args.raw_noise_signal_audit_passed),
        ("--noise-policy-exact-sidecars-only", args.noise_policy_exact_sidecars_only),
        ("--noise-policy-forbids-source-residual-noise", args.noise_policy_forbids_source_residual_noise),
    )
    for label, value in required_flags:
        if value is not True:
            errors.append(f"--production-ready requires {label}")
    if args.severe_worst_row_failures:
        errors.append("--production-ready requires no --severe-worst-row-failures")
    required_positive_ints = (
        ("--camera-count", args.camera_count),
        ("--fifty-mp-or-larger-count", args.fifty_mp_or_larger_count),
        ("--hundred-mp-or-larger-count", args.hundred_mp_or_larger_count),
        ("--full-frame-gate-50mp-row-count", args.full_frame_gate_50mp_row_count),
        ("--full-frame-gate-100mp-row-count", args.full_frame_gate_100mp_row_count),
    )
    for label, value in required_positive_ints:
        if value <= 0:
            errors.append(f"--production-ready requires {label} > 0")
    required_positive_numbers = (
        ("--median-mae-reduction-pct-50mp", args.median_mae_reduction_pct_50mp),
        ("--median-mae-reduction-pct-100mp", args.median_mae_reduction_pct_100mp),
        ("--render-seconds-per-50mp-frame", args.render_seconds_per_50mp_frame),
        ("--render-seconds-per-100mp-frame", args.render_seconds_per_100mp_frame),
        ("--peak-rss-gb", args.peak_rss_gb),
    )
    for label, value in required_positive_numbers:
        if value <= 0:
            errors.append(f"--production-ready requires {label} > 0")
    nonnegative_numbers = (
        ("--worst-row-mae-reduction-pct-50mp", args.worst_row_mae_reduction_pct_50mp),
        ("--worst-row-mae-reduction-pct-100mp", args.worst_row_mae_reduction_pct_100mp),
    )
    for label, value in nonnegative_numbers:
        if value < 0:
            errors.append(f"--production-ready requires {label} >= 0")
    return errors


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    production_ready = bool(args.production_ready)
    placeholder_payload = {
        "pipeline_id": args.pipeline_id,
        "synthetic_or_placeholder": not args.real_artifacts,
        "production_evidence": production_ready,
        "note": "CI skeleton receipt; real still-SR promotion requires real editable raw, review media, dashboard, and gate metrics",
    }

    outputs = output_refs(args, placeholder_payload)

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
        "runtime_policy": {
            "runtime_inputs": args.runtime_input,
            "no_ref_runtime": args.no_ref_runtime,
            "forbidden_source_content_absent": args.forbidden_source_content_absent,
        },
        "promotion_metrics": {
            "full_frame_gate_50mp_passed": args.full_frame_gate_50mp_passed,
            "full_frame_gate_100mp_passed": args.full_frame_gate_100mp_passed,
            "full_frame_gate_50mp_row_count": args.full_frame_gate_50mp_row_count,
            "full_frame_gate_100mp_row_count": args.full_frame_gate_100mp_row_count,
            "median_mae_reduction_pct_50mp": args.median_mae_reduction_pct_50mp,
            "median_mae_reduction_pct_100mp": args.median_mae_reduction_pct_100mp,
            "worst_row_mae_reduction_pct_50mp": args.worst_row_mae_reduction_pct_50mp,
            "worst_row_mae_reduction_pct_100mp": args.worst_row_mae_reduction_pct_100mp,
            "editor_latitude_passed": args.editor_latitude_passed,
            "beats_current_baseline": args.beats_current_baseline,
            "severe_worst_row_failures": args.severe_worst_row_failures,
        },
        "performance": {
            "render_seconds_per_50mp_frame": args.render_seconds_per_50mp_frame,
            "render_seconds_per_100mp_frame": args.render_seconds_per_100mp_frame,
            "peak_rss_gb": args.peak_rss_gb,
        },
        "noise_policy": {
            "mode": args.noise_policy_mode,
            "raw_noise_signal_audit_passed": args.raw_noise_signal_audit_passed,
            "exact_sidecars_only": args.noise_policy_exact_sidecars_only,
            "forbids_source_residual_noise": args.noise_policy_forbids_source_residual_noise,
        },
        "production_ready": production_ready,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--pipeline-id", default="premium_still_sr_skeleton_v1")
    ap.add_argument("--checkpoint-sha256")
    ap.add_argument("--editable-dng", type=Path)
    ap.add_argument("--editable-gpr", type=Path)
    ap.add_argument("--review-media", type=Path)
    ap.add_argument("--dashboard-artifact", type=Path)
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
    ap.add_argument("--runtime-input", action="append", default=["candidate_raw", "camera_metadata"])
    ap.add_argument("--no-ref-runtime", action="store_true")
    ap.add_argument("--forbidden-source-content-absent", action="store_true")
    ap.add_argument("--full-frame-gate-50mp-passed", action="store_true")
    ap.add_argument("--full-frame-gate-100mp-passed", action="store_true")
    ap.add_argument("--full-frame-gate-50mp-row-count", type=int, default=0)
    ap.add_argument("--full-frame-gate-100mp-row-count", type=int, default=0)
    ap.add_argument("--median-mae-reduction-pct-50mp", type=float, default=0.0)
    ap.add_argument("--median-mae-reduction-pct-100mp", type=float, default=0.0)
    ap.add_argument("--worst-row-mae-reduction-pct-50mp", type=float, default=0.0)
    ap.add_argument("--worst-row-mae-reduction-pct-100mp", type=float, default=0.0)
    ap.add_argument("--editor-latitude-passed", action="store_true")
    ap.add_argument("--beats-current-baseline", action="store_true")
    ap.add_argument("--severe-worst-row-failures", action="store_true")
    ap.add_argument("--render-seconds-per-50mp-frame", type=float, default=0.0)
    ap.add_argument("--render-seconds-per-100mp-frame", type=float, default=0.0)
    ap.add_argument("--peak-rss-gb", type=float, default=0.0)
    ap.add_argument("--noise-policy-mode", default="requires_calibrated_camera_noise_sidecar")
    ap.add_argument("--raw-noise-signal-audit-passed", action="store_true")
    ap.add_argument("--noise-policy-exact-sidecars-only", action="store_true")
    ap.add_argument("--noise-policy-forbids-source-residual-noise", action="store_true")
    ap.add_argument("--production-ready", action="store_true")
    ap.add_argument("--real-artifacts", action="store_true")
    args = ap.parse_args()

    if not args.cfa_phase:
        args.cfa_phase = ["RGGB"]
    validation_errors = production_validation_errors(args)
    if validation_errors:
        print("build_premium_still_sr_gate_receipt: invalid production receipt request", file=sys.stderr)
        for error in validation_errors:
            print(f"  - {error}", file=sys.stderr)
        return 2

    receipt = build_receipt(args)
    path = args.out_dir / "premium_still_sr_gate_receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
