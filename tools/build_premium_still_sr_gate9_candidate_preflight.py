#!/usr/bin/env python3
"""Build the Gate 9 Premium still-SR candidate preflight.

Gate 8 closed with a replacement target/source contract. This builder turns
that contract into the next executable intake manifest: a paired X2D/Z8 smoke
run that is allowed to spend only small compute until it beats same-color Bayer
interpolation on both holdouts.
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
DEFAULT_CONTRACT = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_replacement_target_source_contract_20260702/replacement_target_source_contract.json"
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


def train_command(
    *,
    python: Path,
    targets: Path,
    output_dir: Path,
    holdout_scene: str,
    steps: int,
    seed: int,
    train_camera: str | None,
    train_snr_class: str,
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
        "continuous_snr",
        "--snr-loss-weight-strength",
        "0.75",
        "--target-energy-loss-weight-policy",
        "high_energy_emphasis",
        "--target-energy-loss-weight-strength",
        "0.60",
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
        "0.035",
        "--lr",
        "0.00008",
        "--grad-weight",
        "0.12",
        "--target-abs-weight",
        "0.015",
        "--band-weight",
        "0.03",
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
    ]
    if train_camera:
        parts.extend(["--train-camera", train_camera])
    return " ".join(parts)


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_json(args.contract)
    if contract.get("schema") != "gpr.premium_still_sr_replacement_target_source_contract.v1":
        raise ValueError(f"{args.contract} is not a replacement target/source contract")
    if contract.get("paired_smoke_preflight_allowed") is not True:
        raise ValueError("replacement contract does not allow paired smoke preflight")

    smoke_root = args.smoke_output_root or (args.output_dir / "smoke_runs")
    x2d_out = smoke_root / "x2d_smoke"
    z8_out = smoke_root / "z8_smoke"
    smoke_commands = [
        train_command(
            python=args.python,
            targets=args.targets,
            output_dir=x2d_out,
            holdout_scene=args.x2d_holdout_scene,
            steps=args.steps,
            seed=args.seed,
            train_camera="x2d",
            train_snr_class="signal_or_mixed",
        ),
        train_command(
            python=args.python,
            targets=args.targets,
            output_dir=z8_out,
            holdout_scene=args.z8_holdout_scene,
            steps=args.steps,
            seed=args.seed + 1,
            train_camera="Z8Z",
            train_snr_class="all",
        ),
    ]
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
            "Implements the replacement target/source contract as a route-conditioned, "
            "noise-aware raw-CFA residual smoke. X2D trains only from same-camera "
            "signal-or-mixed rows because source evidence is present but target "
            "distribution is mismatched. Z8 is kept as a separate route with a "
            "changed degradation/source policy and must prove source evidence by "
            "beating same-color interpolation in this paired smoke before any long run."
        ),
        "model_arch": "unet raw-CFA route-conditioned residual restoration teacher",
        "architecture_family": "full-image raw-CFA candidate-only residual teacher",
        "architecture_deltas": [
            "full-image raw-CFA residual restoration teacher with full-crop sampling",
            "route-conditioned X2D and Z8 smoke commands instead of one shared objective",
            "CFA-phase-conditioned raw feature planes",
            "overlapped-tile evaluation with seam diagnostics",
            "candidate-only residual prediction in raw-CFA space",
        ],
        "degradation_policy": (
            "Target/objective smoke gate from the replacement source contract: "
            "candidate-only raw residual prediction with calibrated sensor noise "
            "soft-thresholding, continuous SNR loss weighting, route-conditioned row "
            "filtering, high-energy target emphasis, and no REF/source/JPEG content at render time."
        ),
        "degradation_deltas": [
            "ISO-conditioned calibrated sensor noise soft-thresholding and continuous SNR loss weighting",
            "camera-specific route split for X2D source evidence and Z8 source/degradation replacement",
            "sensor and CFA phase aware candidate raw decode path",
            "bit-depth and compression/decode simulation remains part of the full gate",
            "target/objective change from the rejected no-op and source-HF receipts",
        ],
        "validation_plan": [
            "held-out X2D full-image raw-CFA gate using route-conditioned signal-or-mixed rows",
            "held-out Z8 overlapped-tile raw-CFA gate using a separate route/degradation source policy",
            "50 MP full-frame gate row accounting before any promotion",
            "100 MP full-frame gate row accounting before any promotion",
            "worst-row 100 percent crop review",
            "both X2D and Z8 smoke holdouts must beat same-color interpolation before a long run",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "target/degradation blocker receipt",
            "replacement target/source contract receipt",
            "current 124-receipt still-SR experiment scoreboard",
        ],
        "source_evidence_receipts": [
            str(args.contract),
            contract["inputs"]["x2d_source_evidence"]["path"],
            contract["inputs"]["z8_source_evidence"]["path"],
            contract["inputs"]["target_distribution"]["path"],
            contract["inputs"]["target_snr"]["path"],
        ],
        "smoke_gate_commands": smoke_commands,
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
            "dashboard with X2D/Z8 rows",
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
            "Gate 9 smoke only. Passing this manifest and its paired smoke gate "
            "allows a larger Premium still-SR run; it does not claim production readiness."
        ),
    }


def render_html(manifest: dict[str, Any], audit: dict[str, Any]) -> str:
    failures = "".join(f"<li>{html.escape(str(item))}</li>" for item in audit.get("failures", [])) or "<li>None</li>"
    commands = "".join(f"<li><code>{html.escape(cmd)}</code></li>" for cmd in manifest["smoke_gate_commands"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Gate 9 Candidate Preflight</title>
<style>
body {{ margin: 32px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #16212b; }}
main {{ max-width: 1120px; margin: 0 auto; }}
code {{ word-break: break-all; font-size: 12px; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: {'#d5f5e3' if audit.get('launchable_for_production_attempt') else '#fadbd8'}; }}
</style>
<main>
<h1>Premium Still-SR Gate 9 Candidate Preflight</h1>
<p class="status"><b>{html.escape(str(audit.get('verdict')))}</b></p>
<p>{html.escape(manifest['material_change_summary'])}</p>
<h2>Smoke Commands</h2>
<ol>{commands}</ol>
<h2>Preflight Failures</h2>
<ul>{failures}</ul>
</main>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument(
        "--smoke-output-root",
        type=Path,
        help=(
            "Directory for smoke train receipts. Use a path without substrings "
            "like 'ref' because the preflight guard scans command text for "
            "forbidden render-time source tokens."
        ),
    )
    ap.add_argument("--candidate-id", default="gate9_route_conditioned_noise_weighted_rawcfa_v1")
    ap.add_argument("--x2d-holdout-scene", default="2025_10_Oct_Austin_0702")
    ap.add_argument("--z8-holdout-scene", default="Z8Z_1353")
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--seed", type=int, default=270902)
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
