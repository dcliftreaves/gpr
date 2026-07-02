#!/usr/bin/env python3
"""Build the Gate 12 Premium still-SR candidate preflight.

Gate 12 is different from Gate 11: X2D may launch a synthetic
known-degradation clean-source Bayer teacher smoke, while Z8 is not allowed to
train a positive route from the current noise-floor rows. Z8 must be an exact
no-op receipt unless a future source audit supplies new positive evidence.

This builder creates a launchable preflight manifest and validates it with the
shared Premium still-SR preflight checker. It does not train, does not authorize
a long run, and does not claim production readiness.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from check_premium_still_sr_candidate_preflight import validate_preflight, write_html as write_audit_html  # noqa: E402


SCHEMA = "gpr.premium_still_sr_candidate_preflight.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_SOURCE_AUDIT = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_measured_degradation_teacher_source_audit_20260702"
    / "measured_degradation_teacher_source_audit.json"
)
DEFAULT_PAIRS = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_clean_source_pairs_routed_t64_20260702"
    / "premium_still_sr_clean_source_pairs_routed_t64.npz"
)
DEFAULT_PYTHON = DEFAULT_EXTERNAL_ROOT / "venvs/gpr_ml/bin/python"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def route_policy(data: dict[str, Any], route: str) -> dict[str, Any]:
    policy = data.get("route_policy", {}).get(route)
    if not isinstance(policy, dict):
        raise ValueError(f"Gate 12 source audit missing route_policy.{route}")
    return policy


def input_path(data: dict[str, Any], key: str) -> str:
    inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    item = inputs.get(key)
    if isinstance(item, dict) and item.get("path"):
        return str(item["path"])
    return ""


def clean_source_train_command(
    *,
    python: Path,
    pairs: Path,
    output_dir: Path,
    holdout_image: str,
    steps: int,
    seed: int,
) -> str:
    parts = [
        str(python),
        "tools/cnn/train_premium_still_sr_clean_source_pairs.py",
        "--pairs",
        str(pairs),
        "--output-dir",
        str(output_dir),
        "--holdout-image",
        holdout_image,
        "--model-arch",
        "frequency_pyramid_pixelshuffle",
        "--steps",
        str(int(steps)),
        "--batch",
        "3",
        "--low-crop",
        "64",
        "--width",
        "40",
        "--depth",
        "5",
        "--residual-scale",
        "0.18",
        "--loss-mode",
        "charbonnier",
        "--train-input-noise-std-counts",
        "0.75",
        "--train-input-gain-jitter-pct",
        "0.35",
        "--train-input-blur-weight",
        "0.08",
        "--baseline-worsening-loss-weight",
        "1.25",
        "--residual-energy-loss-weight",
        "0.12",
        "--detail-mask-threshold-counts",
        "2.0",
        "--detail-mask-loss-weight",
        "0.35",
        "--no-detail-noop-loss-weight",
        "1.00",
        "--lr",
        "0.00035",
        "--weight-decay",
        "0.0001",
        "--eval-every",
        "25",
        "--seed",
        str(int(seed)),
    ]
    return " ".join(parts)


def exact_noop_command(*, output_dir: Path, holdout: str, row_count: int) -> str:
    return " ".join(
        [
            "python3",
            "tools/build_premium_still_sr_exact_noop_receipt.py",
            "--output-dir",
            str(output_dir),
            "--holdout",
            holdout,
            "--mode",
            "exact-noop",
            "--row-count",
            str(int(row_count)),
        ]
    )


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    source_audit = load_json(args.source_audit)
    if source_audit.get("schema") != "gpr.premium_still_sr_measured_degradation_teacher_source_audit.v1":
        raise ValueError(f"{args.source_audit} is not a Gate 12 source audit")
    if source_audit.get("gate12_candidate_intake_allowed") is not True:
        raise ValueError("Gate 12 source audit does not allow candidate intake")
    if source_audit.get("selected_family") != "synthetic_known_degradation_teacher_x2d_plus_z8_noop":
        raise ValueError("Gate 12 builder requires synthetic_known_degradation_teacher_x2d_plus_z8_noop")

    x2d_policy = route_policy(source_audit, "x2d")
    z8_policy = route_policy(source_audit, "z8")
    if x2d_policy.get("positive_training_allowed") is not True:
        raise ValueError("Gate 12 X2D route is not allowed to train")
    if z8_policy.get("positive_training_allowed") is not False:
        raise ValueError("Gate 12 Z8 route must be exact no-op/new-source, not positive training")

    smoke_root = args.smoke_output_root or (args.output_dir / "smoke_runs")
    x2d_out = smoke_root / "x2d_synthetic_teacher_smoke"
    z8_out = smoke_root / "z8_exact_noop_smoke"
    x2d_command = clean_source_train_command(
        python=args.python,
        pairs=args.pairs,
        output_dir=x2d_out,
        holdout_image=args.x2d_holdout_image,
        steps=args.steps,
        seed=args.seed,
    )
    z8_command = exact_noop_command(
        output_dir=z8_out,
        holdout="z8",
        row_count=int(z8_policy.get("row_count") or 36),
    )

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": args.candidate_id,
        "candidate_kind": "teacher",
        "production_ready": False,
        "promotion_claimed": False,
        "launchable_for_production_attempt": True,
        "requires_material_edits_before_launch": False,
        "uses_ref_or_source_content_at_render_time": False,
        "forbidden_runtime_inputs_absent": True,
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ],
        "material_change_summary": (
            "Implements the Gate 12 measured/synthetic teacher-source audit. X2D uses "
            "synthetic known-degradation clean-source Bayer high/low pairs that already "
            "show local source evidence. Z8 is not trained from current noise-floor rows; "
            "it emits an exact no-op receipt until new source evidence exists. This is a "
            "source/degradation mismatch response with no-op behavior for low-error tiles."
        ),
        "model_arch": "frequency_pyramid_pixelshuffle full-image raw-CFA synthetic degradation teacher with Z8 exact no-op selector",
        "architecture_family": "full-image raw-CFA synthetic known-degradation teacher plus exact no-op route selector",
        "architecture_deltas": [
            "full-image raw-CFA synthetic known-degradation teacher for X2D",
            "frequency-pyramid restoration teacher over same-color Bayer high/low pairs",
            "exact no-op route selector for Z8 until new source evidence exists",
            "overlapped-tile validation before any long 50 MP / 100 MP run",
        ],
        "degradation_policy": (
            "X2D trains on clean-source high Bayer to same-color 2x2 averaged low Bayer "
            "pairs with training-only blur, calibrated sensor noise, gain jitter, "
            "bit-depth aware RAW scaling, baseline-worsening loss, residual-energy loss, "
            "and no-detail no-op loss. Z8 uses no learned degradation on current "
            "noise-floor rows and must remain exact same-color interpolation no-op."
        ),
        "degradation_deltas": [
            "synthetic known-degradation clean-source Bayer high/low pairs",
            "camera-specific source evidence from the Gate 12 source audit",
            "training-only sensor noise and gain jitter",
            "small blur/PSF proxy for low Bayer generation robustness",
            "bit-depth aware RAW normalization",
            "exact no-op behavior for low-error and Z8 noise-floor tiles",
        ],
        "validation_plan": [
            "held-out X2D full-image raw-CFA synthetic teacher smoke",
            "held-out Z8 exact no-op smoke receipt with zero worst-row regression",
            "50 MP full-frame gate row accounting before promotion",
            "100 MP full-frame gate row accounting before promotion",
            "overlapped-tile and worst-row 100 percent crop review",
            "paired smoke must pass before a long run",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "Gate 11 route-isolated residual smoke rejection",
            "Gate 12 measured/synthetic teacher-source audit",
            "current 124-receipt still-SR experiment scoreboard",
        ],
        "source_evidence_receipts": [
            str(args.source_audit),
            input_path(source_audit, "x2d_source_evidence"),
            input_path(source_audit, "z8_source_evidence"),
            input_path(source_audit, "x2d_teacher_smoke"),
            input_path(source_audit, "z8_teacher_smoke"),
            input_path(source_audit, "synthetic_known_degradation_pairs"),
        ],
        "route_policy": {
            "selected_family": source_audit.get("selected_family"),
            "x2d": x2d_policy,
            "z8": z8_policy,
            "forbidden_gate12_sources": source_audit.get("forbidden_gate12_sources", []),
        },
        "smoke_gate_commands": [x2d_command, z8_command],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "route_acceptance": {
                "z8": {
                    "requires_exact_noop": True,
                    "minimum_median_mae_reduction_pct": 0.0,
                    "minimum_worst_row_mae_reduction_pct": 0.0,
                }
            },
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "planned_receipts": [
            "X2D checkpoint and checkpoint hash",
            "Z8 exact no-op config hash",
            "training config and config hash",
            "dashboard with X2D/Z8 route rows",
            "timing and elapsed_seconds",
            "memory receipt from broader gate before production",
            "editor/editable DNG or GPR latitude receipt before promotion",
            "exact noise sidecar policy and calibrated noise weighting",
        ],
        "promotion_receipts": [
            "50 MP / 100 MP promotion gate",
            "full-frame dashboard",
            "production submission validation",
            "timing and memory receipts",
        ],
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
        "notes": (
            "Gate 12 intake only. Passing this preflight allows the X2D synthetic teacher "
            "smoke and the Z8 exact-noop receipt. Passing paired smoke is still required "
            "before any long 50 MP / 100 MP run."
        ),
    }


def render_html(manifest: dict[str, Any], audit: dict[str, Any]) -> str:
    failures = "".join(f"<li>{html.escape(str(item))}</li>" for item in audit.get("failures", [])) or "<li>None</li>"
    commands = "".join(f"<li><code>{html.escape(cmd)}</code></li>" for cmd in manifest["smoke_gate_commands"])
    route = manifest.get("route_policy", {})
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Gate 12 Candidate Preflight</title>
<style>
body {{ margin: 32px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #16212b; }}
main {{ max-width: 1120px; margin: 0 auto; }}
code {{ word-break: break-all; font-size: 12px; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: {'#d5f5e3' if audit.get('launchable_for_production_attempt') else '#fadbd8'}; }}
table {{ width: 100%; border-collapse: collapse; margin: 18px 0; }}
td, th {{ border: 1px solid #d9e1e8; padding: 8px; vertical-align: top; }}
th {{ background: #eef3f7; }}
</style>
<main>
<h1>Premium Still-SR Gate 12 Candidate Preflight</h1>
<p class="status"><b>{html.escape(str(audit.get('verdict')))}</b></p>
<p>{html.escape(manifest['material_change_summary'])}</p>
<h2>Route Policy</h2>
<table><tr><th>Route</th><th>Policy</th><th>Positive training</th></tr>
<tr><td>X2D</td><td>{html.escape(str(route.get('x2d', {}).get('policy')))}</td><td>{html.escape(str(route.get('x2d', {}).get('positive_training_allowed')))}</td></tr>
<tr><td>Z8</td><td>{html.escape(str(route.get('z8', {}).get('policy')))}</td><td>{html.escape(str(route.get('z8', {}).get('positive_training_allowed')))}</td></tr>
</table>
<h2>Smoke Commands</h2>
<ol>{commands}</ol>
<h2>Preflight Failures</h2>
<ul>{failures}</ul>
</main>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-audit", type=Path, default=DEFAULT_SOURCE_AUDIT)
    ap.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS)
    ap.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument(
        "--smoke-output-root",
        type=Path,
        help="Directory for smoke receipts. Avoid substrings like 'ref' because the checker scans command text.",
    )
    ap.add_argument("--candidate-id", default="gate12_synthetic_x2d_teacher_z8_exact_noop_v1")
    ap.add_argument("--x2d-holdout-image", default="x2d_2025_austin_07")
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--seed", type=int, default=271202)
    ap.add_argument("--require-launchable", action="store_true")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(args)
    manifest_path = args.output_dir / "candidate_preflight.json"
    audit_path = args.output_dir / "preflight_audit.json"
    audit_html = args.output_dir / "preflight_audit.html"
    index = args.output_dir / "index.html"

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = validate_preflight(manifest)
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_audit_html(audit, audit_html)
    index.write_text(render_html(manifest, audit), encoding="utf-8")
    print(index)
    if args.require_launchable and not audit["launchable_for_production_attempt"]:
        for failure in audit["failures"]:
            print(f"preflight failure: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
