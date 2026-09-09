#!/usr/bin/env python3
"""Build the replacement Premium still-SR target/degradation source contract.

The previous blocker receipt prevents another long run from the same no-op or
frame-context family. This receipt defines what must replace it: the objective,
source evidence, noise policy, and camera-route conditions a new candidate must
prove before it is allowed into paired X2D/Z8 smoke training.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_replacement_target_source_contract.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_X2D_SOURCE = DEFAULT_ARTIFACT_ROOT / "premium_still_sr_source_evidence_x2dholdout_t64_20260702/source_evidence_audit.json"
DEFAULT_Z8_SOURCE = DEFAULT_ARTIFACT_ROOT / "premium_still_sr_source_evidence_z8holdout_t64_20260702/source_evidence_audit.json"
DEFAULT_TARGET_DISTRIBUTION = DEFAULT_ARTIFACT_ROOT / "premium_still_sr_target_distribution_audit_20260701/target_distribution_audit.json"
DEFAULT_TARGET_SNR = DEFAULT_ARTIFACT_ROOT / "premium_still_sr_raw_target_snr_audit_20260701/raw_target_snr_audit.json"
DEFAULT_BLOCKER = DEFAULT_ARTIFACT_ROOT / "premium_still_sr_target_degradation_evidence_20260702/target_degradation_evidence.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def median_metric(data: dict[str, Any], metric: str) -> float:
    value = data.get("summary", {}).get(metric, {}).get("median")
    return float(value or 0.0)


def source_row(path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "holdout_camera": data.get("holdout_camera"),
        "verdict": data.get("acceptance", {}).get("verdict"),
        "source_evidence_present": bool(data.get("acceptance", {}).get("source_evidence_present")),
        "median_mae_recovery_pct": median_metric(data, "linear_probe_mae_recovery_pct"),
        "median_rmse_recovery_pct": median_metric(data, "linear_probe_rmse_recovery_pct"),
        "min_required_recovery_pct": float(data.get("acceptance", {}).get("min_median_mae_recovery_pct") or 1.0),
        "runtime_inputs": data.get("probe", {}).get("runtime_inputs", []),
        "forbidden_inputs": data.get("probe", {}).get("forbidden_inputs", []),
    }


def target_distribution_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    split = data.get("split_comparison", {})
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "row_count": int(data.get("summary", {}).get("row_count") or 0),
        "scene_count": int(data.get("summary", {}).get("scene_count") or 0),
        "camera_counts": data.get("summary", {}).get("camera_counts", {}),
        "holdout_scene": split.get("holdout_scene"),
        "holdout_distribution_mismatch": bool(split.get("distribution_mismatch")),
        "holdout_median_to_train_median": float(split.get("holdout_median_to_train_median") or 0.0),
        "holdout_rows_above_train_p90": int(split.get("holdout_rows_above_train_p90") or 0),
        "holdout_row_count": int(split.get("holdout_row_count") or 0),
    }


def target_snr_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    summary = data.get("summary", {})
    classes = summary.get("classification_counts", {})
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "row_count": int(summary.get("row_count") or 0),
        "rows_with_noise_sidecars": int(summary.get("rows_with_noise_sidecars") or 0),
        "median_target_rmse_to_noise_sigma": float(summary.get("target_rmse_to_noise_sigma", {}).get("median") or 0.0),
        "median_target_p95_to_noise_p95": float(summary.get("target_p95_to_noise_p95", {}).get("median") or 0.0),
        "classification_counts": classes,
        "interpretation": data.get("interpretation"),
    }


def blocker_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "verdict": data.get("verdict"),
        "long_run_allowed": bool(data.get("long_run_allowed")),
        "blocker_classification": data.get("blocker_classification"),
        "blockers": data.get("blockers", []),
    }


def build_contract(args: argparse.Namespace) -> dict[str, Any]:
    x2d = source_row(args.x2d_source_evidence)
    z8 = source_row(args.z8_source_evidence)
    distribution = target_distribution_summary(args.target_distribution)
    snr = target_snr_summary(args.target_snr)
    blocker = blocker_summary(args.blocker)

    x2d_actionable = x2d["source_evidence_present"] and distribution["holdout_distribution_mismatch"]
    z8_requires_replacement = not z8["source_evidence_present"]
    noise_weighting_required = snr["rows_with_noise_sidecars"] > 0 and "mixed" in str(snr.get("interpretation", "")).lower()

    preflight_allowed = bool(x2d_actionable and z8_requires_replacement and noise_weighting_required and not blocker["long_run_allowed"])
    required_candidate_traits = [
        "candidate-only runtime inputs: candidate_raw plus camera metadata and validated noise-sidecar scalars only",
        "no REF, source raw, source RGB/HF, JPEG target, gate metric, or source residual noise at render time",
        "noise-aware or row-filtered residual target because the current raw-CFA target is mixed signal/noise",
        "camera/route-conditioned objective because X2D has source signal but a held-out target-distribution mismatch",
        "Z8 degradation/source change because the candidate-only local probe does not clear the 1% median MAE source-evidence floor",
        "exact no-op behavior for low-error/no-signal tiles before paired smoke training",
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": "replacement_target_source_contract_ready" if preflight_allowed else "replacement_target_source_contract_incomplete",
        "production_ready": False,
        "long_run_allowed": False,
        "paired_smoke_preflight_allowed": preflight_allowed,
        "inputs": {
            "x2d_source_evidence": x2d,
            "z8_source_evidence": z8,
            "target_distribution": distribution,
            "target_snr": snr,
            "previous_blocker": blocker,
        },
        "decisions": {
            "x2d_route": {
                "decision": "use_candidate_only_signal_but_change_sampling_or_target_weighting",
                "evidence": (
                    f"X2D local candidate-only MAE/RMSE recovery is {x2d['median_mae_recovery_pct']:.4f}%/"
                    f"{x2d['median_rmse_recovery_pct']:.4f}%, while the holdout target median is "
                    f"{distribution['holdout_median_to_train_median']:.2f}x the same-camera train median."
                ),
            },
            "z8_route": {
                "decision": "replace_degradation_source_or_exclude_from_same_objective_until_source_evidence_passes",
                "evidence": (
                    f"Z8 local probe MAE recovery is {z8['median_mae_recovery_pct']:.4f}%, below "
                    f"{z8['min_required_recovery_pct']:.1f}%, despite RMSE recovery of {z8['median_rmse_recovery_pct']:.4f}%."
                ),
            },
            "noise_policy": {
                "decision": "use_noise_aware_loss_or_row_filtering",
                "evidence": str(snr.get("interpretation") or ""),
            },
            "training_permission": {
                "decision": "paired_smoke_only_before_long_run",
                "evidence": "The previous blocker receipt has long_run_allowed=false; this contract only permits a new paired smoke preflight.",
            },
        },
        "required_candidate_traits": required_candidate_traits,
        "next_commands": [
            "Build a new candidate preflight that declares the replacement target/degradation source policy from this contract.",
            "Run the paired X2D and Z8 smoke commands emitted by that preflight.",
            "Run tools/check_premium_still_sr_smoke_gate_acceptance.py --require-pass.",
            "Launch the 50 MP / 100 MP promotion run only if paired smoke passes with positive medians and nonnegative worst rows.",
        ],
        "acceptance": {
            "paired_smoke_median_mae_recovery_pct_min_exclusive": 0.001,
            "paired_smoke_worst_mae_recovery_pct_min": 0.0,
            "promotion_median_mae_recovery_pct_min": 15.0,
            "promotion_median_rmse_recovery_pct_min": 15.0,
            "production_submission_required": True,
        },
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    inputs = data["inputs"]
    decisions = "\n".join(
        "<tr>"
        f"<td>{html.escape(key)}</td>"
        f"<td>{html.escape(value['decision'])}</td>"
        f"<td>{html.escape(value['evidence'])}</td>"
        "</tr>"
        for key, value in data["decisions"].items()
    )
    traits = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["required_candidate_traits"])
    commands = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_commands"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Replacement Target Source Contract</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #18212b; background: #f7f8fa; }}
main {{ max-width: 1160px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 24px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin: 16px 0; }}
th, td {{ border-bottom: 1px solid #e8edf2; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Replacement Target Source Contract</h1>
<p>This receipt defines the next allowed Premium still/SR candidate source policy after the no-op/context blocker. It does not promote a model and it does not allow a long run.</p>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{html.escape(data['verdict'])}</div></section>
  <section class="card"><div class="label">Smoke preflight allowed</div><div class="value">{data['paired_smoke_preflight_allowed']}</div></section>
  <section class="card"><div class="label">Long run allowed</div><div class="value">{data['long_run_allowed']}</div></section>
  <section class="card"><div class="label">Production ready</div><div class="value">{data['production_ready']}</div></section>
</div>
<h2>Decisions</h2>
<table><tr><th>Area</th><th>Decision</th><th>Evidence</th></tr>{decisions}</table>
<h2>Required Candidate Traits</h2>
<ul>{traits}</ul>
<h2>Next Commands</h2>
<ol>{commands}</ol>
<h2>Input Receipts</h2>
<ul>
  <li>X2D source evidence: <code>{html.escape(inputs['x2d_source_evidence']['path'])}</code></li>
  <li>Z8 source evidence: <code>{html.escape(inputs['z8_source_evidence']['path'])}</code></li>
  <li>Target distribution: <code>{html.escape(inputs['target_distribution']['path'])}</code></li>
  <li>Target SNR: <code>{html.escape(inputs['target_snr']['path'])}</code></li>
  <li>Previous blocker: <code>{html.escape(inputs['previous_blocker']['path'])}</code></li>
</ul>
<p>JSON receipt: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x2d-source-evidence", type=Path, default=DEFAULT_X2D_SOURCE)
    parser.add_argument("--z8-source-evidence", type=Path, default=DEFAULT_Z8_SOURCE)
    parser.add_argument("--target-distribution", type=Path, default=DEFAULT_TARGET_DISTRIBUTION)
    parser.add_argument("--target-snr", type=Path, default=DEFAULT_TARGET_SNR)
    parser.add_argument("--blocker", type=Path, default=DEFAULT_BLOCKER)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = build_contract(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "replacement_target_source_contract.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
