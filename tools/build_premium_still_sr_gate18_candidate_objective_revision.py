#!/usr/bin/env python3
"""Build the Gate18 Premium still-SR candidate/objective revision receipt."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate18_candidate_objective_revision.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_GATE17_TARGET_RECEIPT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.json"
)
DEFAULT_GATE17_AUDIT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate17_balanced_target_row_audit_20260702/gate16_target_row_audit.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "artifacts/premium_still_sr_gate18_candidate_objective_revision_20260703"
GATE18_CANDIDATE_ID = "premium_still_sr_gate18_tail_safe_context_objective_v1"


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


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    target_receipt = load_json(args.gate17_target_receipt)
    audit = load_json(args.gate17_audit)
    coverage = audit.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("Gate17 audit is missing coverage")
    classes = coverage.get("classes")
    if not isinstance(classes, dict):
        raise ValueError("Gate17 audit is missing class coverage")
    if int(classes.get("50mp") or 0) <= 0 or int(classes.get("100mp") or 0) <= 0:
        raise ValueError("Gate17 audit must contain both 50mp and 100mp rows")
    if audit.get("production_ready") is not False:
        raise ValueError("Gate17 audit should be a rejection receipt, not production-ready")

    overall = audit.get("overall_eval")
    by_class = audit.get("metrics_by_class")
    if not isinstance(overall, dict) or not isinstance(by_class, dict):
        raise ValueError("Gate17 audit is missing metrics")
    overall_mae = metric(overall["raw_residual_mae_reduction_pct"], "median")
    overall_rmse = metric(overall["raw_residual_rmse_reduction_pct"], "median")
    cls_100 = by_class["100mp"]
    cls_50 = by_class["50mp"]
    metrics = {
        "gate17_target_row_count": int(coverage.get("target_row_count") or 0),
        "gate17_row_count_50mp": int(classes.get("50mp") or 0),
        "gate17_row_count_100mp": int(classes.get("100mp") or 0),
        "gate17_overall_median_mae_recovery_pct": overall_mae,
        "gate17_overall_median_rmse_recovery_pct": overall_rmse,
        "gate17_median_mae_recovery_pct_100mp": metric(cls_100["raw_residual_mae_reduction_pct"], "median"),
        "gate17_median_rmse_recovery_pct_100mp": metric(cls_100["raw_residual_rmse_reduction_pct"], "median"),
        "gate17_worst_mae_recovery_pct_100mp": metric(cls_100["raw_residual_mae_reduction_pct"], "min"),
        "gate17_median_mae_recovery_pct_50mp": metric(cls_50["raw_residual_mae_reduction_pct"], "median"),
        "gate17_median_rmse_recovery_pct_50mp": metric(cls_50["raw_residual_rmse_reduction_pct"], "median"),
        "gate17_worst_mae_recovery_pct_50mp": metric(cls_50["raw_residual_mae_reduction_pct"], "min"),
        "promotion_floor_pct": 15.0,
        "worst_row_floor_pct": 0.0,
    }
    target_npz = (
        args.gate17_target_receipt.parent
        / str(target_receipt.get("artifacts", {}).get("targets_npz", "gate17_replacement_targets.npz"))
    )
    if not target_npz.exists():
        target_npz = args.gate17_target_receipt.parent / "gate17_replacement_targets.npz"

    train_output = DEFAULT_ROOT / "artifacts/premium_still_sr_gate18_tail_safe_context_train_20260703"
    audit_output = DEFAULT_ROOT / "artifacts/premium_still_sr_gate18_tail_safe_context_target_row_audit_20260703"
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
        "raw_context_coord_ev_noise_cfa",
        "--target-representation",
        "residual",
        "--target-policy",
        "noise_soft_threshold",
        "--sample-balance",
        "scene",
        "--sample-mode",
        "full_crop",
        "--context-padding",
        "32",
        "--eval-overlap",
        "96",
        "--seam-check-width",
        "24",
        "--steps",
        "1400",
        "--batch-size",
        "2",
        "--patch-size",
        "192",
        "--width",
        "56",
        "--depth",
        "6",
        "--residual-scale",
        "0.035",
        "--lr",
        "0.00012",
        "--grad-weight",
        "0.12",
        "--target-abs-weight",
        "0.45",
        "--band-weight",
        "0.08",
        "--band-blocks",
        "9",
        "17",
        "33",
        "65",
        "--spectral-weight",
        "0.01",
        "--snr-loss-weight-policy",
        "signal_emphasis",
        "--snr-loss-weight-strength",
        "0.6",
        "--target-energy-loss-weight-policy",
        "high_energy_emphasis",
        "--target-energy-loss-weight-strength",
        "0.75",
        "--target-scale-policy",
        "candidate_hf_abs_mean",
        "--target-scale-strength",
        "0.75",
        "--candidate-hf-noop-threshold",
        "0.0015",
        "--candidate-hf-noop-softness",
        "0.001",
        "--context-mask-prob",
        "0.15",
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
        "260718",
    ]
    audit_command = [
        "env",
        "TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp",
        "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
        "tools/build_premium_still_sr_gate16_target_row_audit.py",
        "--candidate-id",
        GATE18_CANDIDATE_ID,
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
        "candidate_id": GATE18_CANDIDATE_ID,
        "production_ready": False,
        "first_open_step": "gate18_train_then_broad_target_row_audit",
        "inputs": {
            "gate17_target_receipt": str(args.gate17_target_receipt),
            "gate17_target_receipt_sha256": sha256_file(args.gate17_target_receipt),
            "gate17_target_npz": str(target_npz),
            "gate17_target_npz_sha256": sha256_file(target_npz) if target_npz.exists() else None,
            "gate17_audit": str(args.gate17_audit),
            "gate17_audit_sha256": sha256_file(args.gate17_audit),
        },
        "gate17_rejection_metrics": metrics,
        "required_changes_from_gate17": [
            "Do not rerun the same Gate17 raw-CFA residual command as the production path.",
            "Use full-crop/context training so detail placement sees more than local patches.",
            "Use noise-soft-threshold targets and signal/energy weighting to avoid learning noise-floor residuals.",
            "Use candidate-only output scaling and no-op softness to reduce worst-row tail regression.",
            "Use scene-balanced sampling and an explicit holdout probe before the broad target-row audit.",
        ],
        "runtime_policy": {
            "allowed_inputs": ["candidate_raw", "camera_metadata", "validated_camera_noise_sidecar"],
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
        },
        "commands": {
            "train": train_command,
            "audit": audit_command,
        },
        "stop_rule": (
            "Gate18 can enter full promotion only after the broad target-row audit "
            "passes both 50 MP and 100 MP floors with nonnegative worst rows."
        ),
    }


def render_html(receipt: dict[str, Any]) -> str:
    metrics = receipt["gate17_rejection_metrics"]
    rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in metrics.items()
    )
    changes = "".join(f"<li>{html.escape(item)}</li>" for item in receipt["required_changes_from_gate17"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate18 Premium Still-SR Candidate Objective Revision</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;line-height:1.45;color:#18202a}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d9dee7;padding:8px;text-align:left}}th{{background:#f4f6f9}}
code{{background:#f4f6f9;padding:2px 4px;border-radius:4px}}
.bad{{color:#9d1d20;font-weight:700}}
</style>
<h1>Gate18 Premium Still-SR Candidate Objective Revision</h1>
<p>Candidate: <code>{html.escape(receipt["candidate_id"])}</code></p>
<p class="bad">Gate17 is rejected; Gate18 must change the candidate/objective before full promotion.</p>
<h2>Gate17 Rejection Metrics</h2>
<table>{rows}</table>
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
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    receipt_path = args.output_dir / "gate18_candidate_objective_revision.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "dashboard": str(html_path), "candidate_id": receipt["candidate_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
