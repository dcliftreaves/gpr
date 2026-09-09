#!/usr/bin/env python3
"""Build the Gate19 Premium still-SR positive-signal/source revision receipt."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate19_positive_signal_source_revision.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_GATE17_TARGET_RECEIPT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.json"
)
DEFAULT_GATE17_AUDIT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate17_balanced_target_row_audit_20260702/gate16_target_row_audit.json"
)
DEFAULT_GATE18_AUDIT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate18_tail_safe_context_target_row_audit_20260703/gate16_target_row_audit.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "artifacts/premium_still_sr_gate19_positive_signal_source_revision_20260703"
GATE19_CANDIDATE_ID = "premium_still_sr_gate19_source_hf_positive_signal_v1"


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


def metric(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"missing numeric metric {key!r}")
    return float(value)


def class_metric(audit: dict[str, Any], cls: str, metric_name: str, key: str) -> float:
    by_class = audit.get("metrics_by_class")
    if not isinstance(by_class, dict) or cls not in by_class:
        raise ValueError(f"audit missing class {cls!r}")
    class_summary = by_class[cls]
    if not isinstance(class_summary, dict):
        raise ValueError(f"audit class {cls!r} must be an object")
    stats = class_summary.get(metric_name)
    if not isinstance(stats, dict):
        raise ValueError(f"audit class {cls!r} missing metric {metric_name!r}")
    return metric(stats, key)


def target_npz_from_receipt(path: Path, receipt: dict[str, Any]) -> Path:
    target_npz = path.parent / str(receipt.get("artifacts", {}).get("targets_npz", "gate17_replacement_targets.npz"))
    if not target_npz.exists():
        target_npz = path.parent / "gate17_replacement_targets.npz"
    return target_npz


def validate_inputs(target_receipt: dict[str, Any], gate17_audit: dict[str, Any], gate18_audit: dict[str, Any]) -> None:
    counts = target_receipt.get("selected_class_counts")
    if not isinstance(counts, dict):
        summary = target_receipt.get("class_summary")
        if not isinstance(summary, dict):
            raise ValueError("Gate17 target receipt is missing selected class coverage")
        counts = {
            "50mp": int(summary.get("50mp", {}).get("selected_rows") or 0)
            if isinstance(summary.get("50mp"), dict)
            else 0,
            "100mp": int(summary.get("100mp", {}).get("selected_rows") or 0)
            if isinstance(summary.get("100mp"), dict)
            else 0,
        }
    if int(counts.get("50mp") or 0) < 500 or int(counts.get("100mp") or 0) < 500:
        raise ValueError("Gate19 requires the balanced Gate17 50 MP / 100 MP target package")
    for name, audit in (("Gate17", gate17_audit), ("Gate18", gate18_audit)):
        if audit.get("production_ready") is not False:
            raise ValueError(f"{name} audit should be rejection evidence")
        coverage = audit.get("coverage")
        if not isinstance(coverage, dict):
            raise ValueError(f"{name} audit missing coverage")
        classes = coverage.get("classes")
        if not isinstance(classes, dict):
            raise ValueError(f"{name} audit missing class coverage")
        if int(classes.get("50mp") or 0) <= 0 or int(classes.get("100mp") or 0) <= 0:
            raise ValueError(f"{name} audit must contain both 50mp and 100mp rows")


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    target_receipt = load_json(args.gate17_target_receipt)
    gate17_audit = load_json(args.gate17_audit)
    gate18_audit = load_json(args.gate18_audit)
    validate_inputs(target_receipt, gate17_audit, gate18_audit)
    target_npz = target_npz_from_receipt(args.gate17_target_receipt, target_receipt)

    gate18_overall = gate18_audit.get("overall_eval")
    if not isinstance(gate18_overall, dict):
        raise ValueError("Gate18 audit missing overall_eval")
    gate18_gate = gate18_overall.get("candidate_hf_noop_gate")
    if not isinstance(gate18_gate, dict):
        raise ValueError("Gate18 audit missing no-op gate metrics")

    train_output = DEFAULT_ROOT / "artifacts/premium_still_sr_gate19_source_hf_positive_signal_train_20260703"
    audit_output = DEFAULT_ROOT / "artifacts/premium_still_sr_gate19_source_hf_positive_signal_target_row_audit_20260703"
    train_command = [
        "env",
        "TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp",
        "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
        "tools/cnn/train_premium_still_sr_raw_cfa_residual.py",
        "--targets",
        str(target_npz),
        "--output-dir",
        str(train_output),
        "--model-arch",
        "global_context_unet",
        "--feature-mode",
        "raw_context_storedhf_coord_ev_noise_cfa",
        "--target-representation",
        "source_hf",
        "--target-policy",
        "raw",
        "--sample-balance",
        "scene",
        "--sample-mode",
        "random_patch",
        "--context-padding",
        "32",
        "--eval-overlap",
        "96",
        "--seam-check-width",
        "24",
        "--steps",
        "1800",
        "--batch-size",
        "4",
        "--patch-size",
        "160",
        "--width",
        "56",
        "--depth",
        "6",
        "--residual-scale",
        "0.05",
        "--lr",
        "0.00016",
        "--grad-weight",
        "0.10",
        "--target-abs-weight",
        "0.50",
        "--band-weight",
        "0.06",
        "--band-blocks",
        "9",
        "17",
        "33",
        "65",
        "--spectral-weight",
        "0.006",
        "--snr-loss-weight-policy",
        "signal_emphasis",
        "--snr-loss-weight-strength",
        "0.45",
        "--target-energy-loss-weight-policy",
        "high_energy_emphasis",
        "--target-energy-loss-weight-strength",
        "0.50",
        "--target-scale-policy",
        "none",
        "--context-mask-prob",
        "0.05",
        "--context-mask-block",
        "32",
        "--eval-holdout-rows",
        "160",
        "--eval-train-rows",
        "160",
        "--eval-during-training-rows",
        "32",
        "--save-best-holdout-checkpoint",
        "--seed",
        "260719",
    ]
    audit_command = [
        "env",
        "TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp",
        "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
        "tools/build_premium_still_sr_gate16_target_row_audit.py",
        "--candidate-id",
        GATE19_CANDIDATE_ID,
        "--train-receipt",
        str(train_output / "train_receipt.json"),
        "--targets",
        str(target_npz),
        "--output-dir",
        str(audit_output),
    ]

    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "candidate_id": GATE19_CANDIDATE_ID,
        "production_ready": False,
        "first_open_step": "gate19_train_then_broad_target_row_audit",
        "inputs": {
            "gate17_target_receipt": str(args.gate17_target_receipt),
            "gate17_target_receipt_sha256": sha256_file(args.gate17_target_receipt),
            "gate17_target_npz": str(target_npz),
            "gate17_target_npz_sha256": sha256_file(target_npz) if target_npz.exists() else None,
            "gate17_audit": str(args.gate17_audit),
            "gate17_audit_sha256": sha256_file(args.gate17_audit),
            "gate18_audit": str(args.gate18_audit),
            "gate18_audit_sha256": sha256_file(args.gate18_audit),
        },
        "prior_failures": {
            "gate17": {
                "failure": "positive wins exist but median recovery is below floor and worst rows are unsafe",
                "overall_median_mae_pct": metric(gate17_audit["overall_eval"]["raw_residual_mae_reduction_pct"], "median"),
                "overall_median_rmse_pct": metric(gate17_audit["overall_eval"]["raw_residual_rmse_reduction_pct"], "median"),
                "worst_mae_pct_50mp": class_metric(gate17_audit, "50mp", "raw_residual_mae_reduction_pct", "min"),
                "worst_mae_pct_100mp": class_metric(gate17_audit, "100mp", "raw_residual_mae_reduction_pct", "min"),
            },
            "gate18": {
                "failure": "tail safety improved but candidate collapses toward no-op",
                "overall_median_mae_pct": metric(gate18_audit["overall_eval"]["raw_residual_mae_reduction_pct"], "median"),
                "overall_median_rmse_pct": metric(gate18_audit["overall_eval"]["raw_residual_rmse_reduction_pct"], "median"),
                "noop_gate_median": metric(gate18_gate, "median"),
                "noop_row_count": int(gate18_overall.get("candidate_hf_noop_row_count") or 0),
                "worst_mae_pct_50mp": class_metric(gate18_audit, "50mp", "raw_residual_mae_reduction_pct", "min"),
                "worst_mae_pct_100mp": class_metric(gate18_audit, "100mp", "raw_residual_mae_reduction_pct", "min"),
            },
        },
        "required_changes_from_gate18": [
            "Reject another safety-only no-op: no candidate-HF no-op threshold is used in the Gate19 command.",
            "Train source_hf representation so the network predicts source high-frequency CFA, then subtract candidate HF to obtain the residual.",
            "Use candidate stored-HF features at runtime; do not use REF, source raw/RGB/HF, JPEG, or gate metrics at render time.",
            "Keep lower context masking and no target-scale shrink so positive detail can survive the objective.",
            "Audit every balanced Gate17 target row after training; target-row pass is required before any full-frame promotion attempt.",
        ],
        "runtime_policy": {
            "allowed_inputs": [
                "candidate_raw",
                "candidate_raw_hf",
                "camera_metadata",
                "validated_camera_noise_sidecar",
            ],
            "forbidden_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "JPG", "gate_metrics"],
            "candidate_only_runtime": True,
        },
        "pass_thresholds": {
            "median_mae_reduction_pct_50mp": 15.0,
            "median_rmse_reduction_pct_50mp": 15.0,
            "median_mae_reduction_pct_100mp": 15.0,
            "median_rmse_reduction_pct_100mp": 15.0,
            "worst_mae_reduction_pct_50mp": 0.0,
            "worst_mae_reduction_pct_100mp": 0.0,
            "not_noop_overall_median_mae_reduction_pct": 1.0,
        },
        "commands": {
            "train": train_command,
            "audit": audit_command,
        },
        "stop_rule": (
            "Gate19 can move to full-frame promotion only after the broad target-row audit "
            "passes both 50 MP and 100 MP floors, keeps worst rows nonnegative, and has "
            "overall median MAE recovery above the not-noop floor."
        ),
    }


def render_html(receipt: dict[str, Any]) -> str:
    prior_rows = []
    for name, payload in receipt["prior_failures"].items():
        for key, value in payload.items():
            prior_rows.append(
                f"<tr><th>{html.escape(name)}.{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
            )
    changes = "".join(f"<li>{html.escape(item)}</li>" for item in receipt["required_changes_from_gate18"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate19 Premium Still-SR Positive-Signal Source Revision</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;line-height:1.45;color:#18202a}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d9dee7;padding:8px;text-align:left}}th{{background:#f4f6f9}}
code{{background:#f4f6f9;padding:2px 4px;border-radius:4px}}
.bad{{color:#9d1d20;font-weight:700}}.ok{{color:#146b3a;font-weight:700}}
</style>
<h1>Gate19 Premium Still-SR Positive-Signal Source Revision</h1>
<p>Candidate: <code>{html.escape(receipt["candidate_id"])}</code></p>
<p class="bad">Gate17 and Gate18 are rejected. Gate19 must recover positive signal without REF/source/JPEG runtime inputs.</p>
<p class="ok">Objective: predict source high-frequency CFA from candidate CFA + candidate HF, then emit a candidate-only residual.</p>
<h2>Prior Failure Metrics</h2>
<table>{''.join(prior_rows)}</table>
<h2>Required Changes</h2>
<ol>{changes}</ol>
<h2>Next Commands</h2>
<pre>{html.escape(" ".join(receipt["commands"]["train"]))}</pre>
<pre>{html.escape(" ".join(receipt["commands"]["audit"]))}</pre>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate17-target-receipt", type=Path, default=DEFAULT_GATE17_TARGET_RECEIPT)
    ap.add_argument("--gate17-audit", type=Path, default=DEFAULT_GATE17_AUDIT)
    ap.add_argument("--gate18-audit", type=Path, default=DEFAULT_GATE18_AUDIT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    receipt_path = args.output_dir / "gate19_positive_signal_source_revision.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "dashboard": str(html_path), "candidate_id": receipt["candidate_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
