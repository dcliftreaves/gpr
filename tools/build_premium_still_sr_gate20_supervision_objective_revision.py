#!/usr/bin/env python3
"""Build the Gate20 Premium still-SR supervision/objective revision receipt."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate20_supervision_objective_revision.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_GATE17_TARGET_RECEIPT = (
    DEFAULT_ROOT / "artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.json"
)
DEFAULT_GATE19_AUDIT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate19_source_hf_positive_signal_target_row_audit_20260703/gate16_target_row_audit.json"
)
DEFAULT_DIRECTION_CALIBRATION = (
    DEFAULT_ROOT / "artifacts/premium_still_sr_gate17_direction_calibration_audit_20260703/direction_calibration_audit.json"
)
DEFAULT_CANDIDATE_HF_AUDIT = (
    DEFAULT_ROOT / "artifacts/premium_still_sr_candidate_hf_feature_audit_20260703/candidate_hf_feature_audit.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "artifacts/premium_still_sr_gate20_supervision_objective_revision_20260703"
GATE20_CANDIDATE_ID = "premium_still_sr_gate20_rebuilt_supervision_v1"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def metric(stats: dict[str, Any], key: str) -> float:
    value = stats.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"missing numeric metric {key!r}")
    return float(value)


def class_counts(target_receipt: dict[str, Any]) -> dict[str, int]:
    coverage = target_receipt.get("coverage")
    if isinstance(coverage, dict) and isinstance(coverage.get("selected_class_counts"), dict):
        return {str(k): int(v) for k, v in coverage["selected_class_counts"].items()}
    summary = target_receipt.get("class_summary")
    if isinstance(summary, dict):
        return {
            cls: int(row.get("selected_rows") or 0)
            for cls, row in summary.items()
            if isinstance(row, dict)
        }
    raise ValueError("Gate17 target receipt is missing class counts")


def validate_inputs(
    target_receipt: dict[str, Any],
    gate19_audit: dict[str, Any],
    direction_calibration: dict[str, Any],
    candidate_hf_audit: dict[str, Any],
) -> None:
    counts = class_counts(target_receipt)
    if int(counts.get("50mp") or 0) < 500 or int(counts.get("100mp") or 0) < 500:
        raise ValueError("Gate20 requires the balanced Gate17 50 MP / 100 MP target package")
    if gate19_audit.get("production_ready") is not False:
        raise ValueError("Gate19 audit should be rejection evidence")
    if direction_calibration.get("next_decision") != "direction_or_objective_wrong":
        raise ValueError("Gate20 requires scalar direction calibration rejection")
    if candidate_hf_audit.get("next_decision") != "candidate_hf_feature_not_predictive_change_supervision":
        raise ValueError("Gate20 requires candidate-HF feature rejection")


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    target_receipt = load_json(args.gate17_target_receipt)
    gate19_audit = load_json(args.gate19_audit)
    direction_calibration = load_json(args.direction_calibration)
    candidate_hf_audit = load_json(args.candidate_hf_audit)
    validate_inputs(target_receipt, gate19_audit, direction_calibration, candidate_hf_audit)

    counts = class_counts(target_receipt)
    gate19_overall = gate19_audit["overall_eval"]
    direction_best = direction_calibration["best_alpha_summary"]
    candidate_best = candidate_hf_audit["best_alpha_summary"]
    output_dir = DEFAULT_ROOT / "artifacts/premium_still_sr_gate20_rebuilt_supervision_targets_20260703"
    target_rebuild_commands = [
        [
            "env",
            "TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp",
            "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
            "tools/build_premium_still_sr_target_expansion_plan.py",
            "--output-dir",
            str(output_dir / "target_expansion_plan"),
        ],
        [
            "env",
            "TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp",
            "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
            "tools/cnn/build_premium_still_sr_expanded_hf_targets_from_plan.py",
            "--plan",
            str(output_dir / "target_expansion_plan" / "target_expansion_plan.json"),
            "--output-dir",
            str(output_dir / "expanded_hf_targets"),
            "--include-raw-cfa-features",
            "--rebuild-existing-targets",
        ],
    ]
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "candidate_id": GATE20_CANDIDATE_ID,
        "production_ready": False,
        "first_open_step": "gate20_rebuild_supervision_targets",
        "inputs": {
            "gate17_target_receipt": str(args.gate17_target_receipt),
            "gate17_target_receipt_sha256": sha256_file(args.gate17_target_receipt),
            "gate19_audit": str(args.gate19_audit),
            "gate19_audit_sha256": sha256_file(args.gate19_audit),
            "direction_calibration": str(args.direction_calibration),
            "direction_calibration_sha256": sha256_file(args.direction_calibration),
            "candidate_hf_audit": str(args.candidate_hf_audit),
            "candidate_hf_audit_sha256": sha256_file(args.candidate_hf_audit),
        },
        "prior_rejection_metrics": {
            "gate17_rows_50mp": int(counts.get("50mp") or 0),
            "gate17_rows_100mp": int(counts.get("100mp") or 0),
            "gate19_overall_median_mae_pct": metric(gate19_overall["raw_residual_mae_reduction_pct"], "median"),
            "gate19_overall_median_rmse_pct": metric(gate19_overall["raw_residual_rmse_reduction_pct"], "median"),
            "gate17_direction_best_alpha": float(direction_best["alpha"]),
            "gate17_direction_best_median_mae_pct": metric(direction_best["mae_reduction_pct"], "median"),
            "candidate_hf_best_alpha": float(candidate_best["alpha"]),
            "candidate_hf_best_median_mae_pct": metric(candidate_best["mae_reduction_pct"], "median"),
        },
        "required_changes": [
            "Do not train another Gate17/Gate18/Gate19 candidate on the same raw_hf_residual target family.",
            "Do not use candidate_raw_hf scalar tuning or stored-HF direct prediction as the primary Gate20 path.",
            "Rebuild supervision so source high Bayer, synthetic low Bayer, degradation metadata, PSF/kernel metadata, and exact camera-noise sidecars are all emitted together.",
            "Keep render-time inputs candidate-only: candidate raw, candidate-derived features, camera metadata, CFA phase, PSF/degradation sidecar, and validated camera-noise sidecar.",
            "Only after rebuilt targets pass the no-REF preflight may Gate20 train and then run the broad 576-row-per-class target-row audit.",
        ],
        "runtime_policy": {
            "allowed_inputs": [
                "candidate_raw",
                "candidate_derived_features",
                "camera_metadata",
                "cfa_phase",
                "degradation_or_psf_sidecar",
                "validated_camera_noise_sidecar",
            ],
            "forbidden_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "JPG", "gate_metrics"],
            "candidate_only_runtime": True,
        },
        "target_rebuild_commands": target_rebuild_commands,
        "pass_thresholds_after_rebuild": {
            "median_mae_reduction_pct_50mp": 15.0,
            "median_rmse_reduction_pct_50mp": 15.0,
            "median_mae_reduction_pct_100mp": 15.0,
            "median_rmse_reduction_pct_100mp": 15.0,
            "worst_mae_reduction_pct_50mp": 0.0,
            "worst_mae_reduction_pct_100mp": 0.0,
        },
        "stop_rule": (
            "Gate20 may train only after rebuilt supervision targets pass a no-REF/candidate-only "
            "preflight. It may promote only after broad 50 MP / 100 MP target-row audit and full-frame "
            "promotion evidence pass the floor."
        ),
    }


def render_html(receipt: dict[str, Any]) -> str:
    metrics = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in receipt["prior_rejection_metrics"].items()
    )
    changes = "".join(f"<li>{html.escape(item)}</li>" for item in receipt["required_changes"])
    commands = "".join(
        f"<pre>{html.escape(' '.join(command))}</pre>" for command in receipt["target_rebuild_commands"]
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate20 Premium Still-SR Supervision Objective Revision</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;line-height:1.45;color:#18202a}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d9dee7;padding:8px;text-align:left}}th{{background:#f4f6f9}}
code{{background:#f4f6f9;padding:2px 4px;border-radius:4px}}
.bad{{color:#9d1d20;font-weight:700}}.ok{{color:#146b3a;font-weight:700}}
</style>
<h1>Gate20 Premium Still-SR Supervision Objective Revision</h1>
<p>Candidate: <code>{html.escape(receipt["candidate_id"])}</code></p>
<p class="bad">Gate17/Gate18/Gate19 and scalar candidate-HF paths are rejected.</p>
<p class="ok">Next action: rebuild supervision targets before more long CNN training.</p>
<h2>Prior Rejection Metrics</h2>
<table>{metrics}</table>
<h2>Required Changes</h2>
<ol>{changes}</ol>
<h2>Target Rebuild Commands</h2>
{commands}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate17-target-receipt", type=Path, default=DEFAULT_GATE17_TARGET_RECEIPT)
    ap.add_argument("--gate19-audit", type=Path, default=DEFAULT_GATE19_AUDIT)
    ap.add_argument("--direction-calibration", type=Path, default=DEFAULT_DIRECTION_CALIBRATION)
    ap.add_argument("--candidate-hf-audit", type=Path, default=DEFAULT_CANDIDATE_HF_AUDIT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    receipt_path = args.output_dir / "gate20_supervision_objective_revision.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "dashboard": str(html_path), "candidate_id": receipt["candidate_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
