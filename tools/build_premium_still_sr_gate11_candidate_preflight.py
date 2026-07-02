#!/usr/bin/env python3
"""Build the Gate 11 Premium still-SR candidate preflight.

Gate 10 classified the failed route-conditioned/noise-aware smoke as a
source/degradation target mismatch. The Gate 11 degradation-source audit then
selected a route-isolated teacher/router policy: X2D may train on
signal/mixed rows with stratified target sampling, while Z8 current
noise-floor rows must remain exact no-op unless new source evidence passes.

This builder turns that policy into a launchable candidate intake manifest for
the existing Premium still-SR preflight checker. It does not train and it does
not claim production readiness.
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
DEFAULT_AUDIT = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_degradation_source_audit_20260702/degradation_source_audit.json"
)
DEFAULT_TARGETS = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/raw_cfa_residual_targets_dedup.npz"
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
        raise ValueError(f"degradation-source audit missing route_policy.{route}")
    return policy


def train_command(
    *,
    python: Path,
    targets: Path,
    output_dir: Path,
    holdout_scene: str,
    steps: int,
    seed: int,
    train_camera: str,
    train_snr_class: str,
    snr_weight_policy: str,
    snr_weight_strength: float,
    target_energy_policy: str,
    target_energy_strength: float,
    target_scale_policy: str,
    target_scale_strength: float,
    candidate_hf_noop_threshold: float,
    candidate_hf_noop_softness: float,
) -> str:
    parts = [
        str(python),
        "tools/cnn/train_premium_still_sr_raw_cfa_residual.py",
        "--targets",
        str(targets),
        "--output-dir",
        str(output_dir),
        "--holdout-scene",
        holdout_scene,
        "--model-arch",
        "unet",
        "--feature-mode",
        "raw_multiscale_coord_ev_noise_cfa",
        "--target-representation",
        "residual",
        "--target-policy",
        "noise_soft_threshold",
        "--noise-threshold-scale",
        "1.0",
        "--train-snr-class",
        train_snr_class,
        "--snr-loss-weight-policy",
        snr_weight_policy,
        "--snr-loss-weight-strength",
        f"{snr_weight_strength:.6g}",
        "--target-energy-loss-weight-policy",
        target_energy_policy,
        "--target-energy-loss-weight-strength",
        f"{target_energy_strength:.6g}",
        "--target-scale-policy",
        target_scale_policy,
        "--target-scale-strength",
        f"{target_scale_strength:.6g}",
        "--candidate-hf-noop-threshold",
        f"{candidate_hf_noop_threshold:.6g}",
        "--candidate-hf-noop-softness",
        f"{candidate_hf_noop_softness:.6g}",
        "--sample-balance",
        "scene",
        "--sample-mode",
        "full_crop",
        "--context-padding",
        "16",
        "--eval-overlap",
        "64",
        "--seam-check-width",
        "16",
        "--steps",
        str(int(steps)),
        "--batch-size",
        "2",
        "--patch-size",
        "192",
        "--width",
        "32",
        "--depth",
        "4",
        "--residual-scale",
        "0.03",
        "--lr",
        "0.00006",
        "--grad-weight",
        "0.14",
        "--target-abs-weight",
        "0.02",
        "--band-weight",
        "0.035",
        "--band-blocks",
        "9",
        "17",
        "33",
        "--eval-holdout-rows",
        "27",
        "--eval-train-rows",
        "27",
        "--eval-during-training-rows",
        "9",
        "--save-best-holdout-checkpoint",
        "--seed",
        str(int(seed)),
        "--train-camera",
        train_camera,
    ]
    return " ".join(parts)


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    audit = load_json(args.degradation_source_audit)
    if audit.get("schema") != "gpr.premium_still_sr_degradation_source_audit.v1":
        raise ValueError(f"{args.degradation_source_audit} is not a degradation-source audit")
    if audit.get("gate11_candidate_intake_allowed") is not True:
        raise ValueError("degradation-source audit does not allow Gate 11 candidate intake")
    if audit.get("selected_family") != "route_isolated_teacher_then_router":
        raise ValueError("Gate 11 builder currently requires route_isolated_teacher_then_router")

    x2d_policy = route_policy(audit, "x2d")
    z8_policy = route_policy(audit, "z8")
    smoke_root = args.smoke_output_root or (args.output_dir / "smoke_runs")
    x2d_out = smoke_root / "x2d_smoke"
    z8_out = smoke_root / "z8_smoke"
    x2d_command = train_command(
        python=args.python,
        targets=args.targets,
        output_dir=x2d_out,
        holdout_scene=args.x2d_holdout_scene,
        steps=args.steps,
        seed=args.seed,
        train_camera="x2d",
        train_snr_class="signal_or_mixed",
        snr_weight_policy="signal_emphasis",
        snr_weight_strength=0.85,
        target_energy_policy="high_energy_emphasis",
        target_energy_strength=0.70,
        target_scale_policy="candidate_hf_abs_mean",
        target_scale_strength=0.50,
        candidate_hf_noop_threshold=args.x2d_noop_threshold,
        candidate_hf_noop_softness=args.x2d_noop_softness,
    )
    z8_command = train_command(
        python=args.python,
        targets=args.targets,
        output_dir=z8_out,
        holdout_scene=args.z8_holdout_scene,
        steps=args.steps,
        seed=args.seed + 1,
        train_camera="Z8Z",
        train_snr_class="not_noise_floor",
        snr_weight_policy="signal_emphasis",
        snr_weight_strength=1.0,
        target_energy_policy="high_energy_emphasis",
        target_energy_strength=0.80,
        target_scale_policy="candidate_hf_abs_mean",
        target_scale_strength=0.60,
        candidate_hf_noop_threshold=args.z8_noop_threshold,
        candidate_hf_noop_softness=args.z8_noop_softness,
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
            "Implements the Gate 11 degradation-source audit as a route-isolated teacher/router "
            "smoke. X2D uses local source evidence with stratified signal-or-mixed target rows. "
            "Z8 current noise-floor rows are excluded from positive residual training and forced "
            "toward no-op behavior until new source evidence exists. This is a source/degradation "
            "mismatch response, not another generic residual U-Net rerun."
        ),
        "model_arch": "unet full-image raw-CFA route-isolated teacher router",
        "architecture_family": "full-image raw-CFA route-isolated teacher with no-op router guard",
        "architecture_deltas": [
            "full-image raw-CFA route-isolated teacher instead of one shared objective",
            "route-specific X2D and Z8 commands with different row policies",
            "candidate-only no-op router guard for low-error tiles",
            "CFA-phase-conditioned raw feature planes",
            "overlapped-tile evaluation with seam diagnostics",
        ],
        "degradation_policy": (
            "Gate 11 target/objective policy from the degradation-source audit: calibrated sensor "
            "noise soft-thresholding, camera-specific route isolation, candidate-HF no-op behavior, "
            "SNR-aware loss weighting, target-energy emphasis, and candidate-only target scaling. "
            "No REF, source RAW/RGB/HF, JPEG target, source residual noise, or gate metric is a "
            "render-time input."
        ),
        "degradation_deltas": [
            "camera-specific route isolation after source/degradation mismatch evidence",
            "sensor-noise soft-threshold target policy with SNR-aware row filtering",
            "Z8 noise-floor rows excluded from positive residual training",
            "candidate-only no-op behavior for low-error tiles",
            "CFA and bit-depth aware raw decode/compression gate remains required for promotion",
        ],
        "validation_plan": [
            "held-out X2D full-image raw-CFA gate using 70 eligible signal-or-mixed rows",
            "held-out Z8 overlapped-tile raw-CFA gate with current noise-floor rows forced to no-op",
            "50 MP full-frame gate row accounting before any promotion",
            "100 MP full-frame gate row accounting before any promotion",
            "worst-row 100 percent crop review",
            "paired smoke holdouts must beat same-color interpolation before a long run",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "Gate 9 route-conditioned noise-aware smoke rejection",
            "Gate 10 target/degradation decision receipt",
            "Gate 11 degradation-source audit receipt",
            "current 124-receipt still-SR experiment scoreboard",
        ],
        "source_evidence_receipts": [
            str(args.degradation_source_audit),
            audit["inputs"]["gate10_decision"]["path"],
            audit["inputs"]["target_distribution"]["path"],
            audit["inputs"]["target_snr"]["path"],
            audit["inputs"]["x2d_source_evidence"]["path"],
            audit["inputs"]["z8_source_evidence"]["path"],
        ],
        "route_policy": {
            "selected_family": audit.get("selected_family"),
            "x2d": x2d_policy,
            "z8": z8_policy,
            "forbidden_gate11_sources": audit.get("forbidden_gate11_sources", []),
        },
        "smoke_gate_commands": [x2d_command, z8_command],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "planned_receipts": [
            "checkpoint and checkpoint hash",
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
            "Gate 11 intake only. Passing this preflight allows a small paired smoke. "
            "Passing paired smoke is still required before any long 50 MP / 100 MP run."
        ),
    }


def render_html(manifest: dict[str, Any], audit: dict[str, Any]) -> str:
    failures = "".join(f"<li>{html.escape(str(item))}</li>" for item in audit.get("failures", [])) or "<li>None</li>"
    commands = "".join(f"<li><code>{html.escape(cmd)}</code></li>" for cmd in manifest["smoke_gate_commands"])
    route = manifest.get("route_policy", {})
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Gate 11 Candidate Preflight</title>
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
<h1>Premium Still-SR Gate 11 Candidate Preflight</h1>
<p class="status"><b>{html.escape(str(audit.get('verdict')))}</b></p>
<p>{html.escape(manifest['material_change_summary'])}</p>
<h2>Route Policy</h2>
<table><tr><th>Route</th><th>Policy</th><th>Eligible rows</th></tr>
<tr><td>X2D</td><td>{html.escape(str(route.get('x2d', {}).get('policy')))}</td><td>{html.escape(str(route.get('x2d', {}).get('eligible_training_rows')))}</td></tr>
<tr><td>Z8</td><td>{html.escape(str(route.get('z8', {}).get('policy')))}</td><td>{html.escape(str(route.get('z8', {}).get('eligible_training_rows')))}</td></tr>
</table>
<h2>Smoke Commands</h2>
<ol>{commands}</ol>
<h2>Preflight Failures</h2>
<ul>{failures}</ul>
</main>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--degradation-source-audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument(
        "--smoke-output-root",
        type=Path,
        help="Directory for smoke train receipts. Avoid substrings like 'ref' because the checker scans command text.",
    )
    ap.add_argument("--candidate-id", default="gate11_route_isolated_teacher_router_rawcfa_v1")
    ap.add_argument("--x2d-holdout-scene", default="2025_10_Oct_Austin_0702")
    ap.add_argument("--z8-holdout-scene", default="Z8Z_1353")
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--seed", type=int, default=271102)
    ap.add_argument("--x2d-noop-threshold", type=float, default=0.0015)
    ap.add_argument("--x2d-noop-softness", type=float, default=0.0015)
    ap.add_argument("--z8-noop-threshold", type=float, default=0.004)
    ap.add_argument("--z8-noop-softness", type=float, default=0.004)
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
