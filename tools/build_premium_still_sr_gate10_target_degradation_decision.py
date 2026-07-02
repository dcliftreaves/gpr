#!/usr/bin/env python3
"""Build the Gate 10 Premium still-SR target/degradation decision receipt.

Gate 9 proved that the replacement-contract route-conditioned/noise-aware
U-Net smoke is still negative on both X2D and Z8. This tool converts that into
the next machine-readable decision: the next production attempt must replace
the target/degradation source or prove materially different route conditioning
before another paired smoke can start.
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


SCHEMA = "gpr.premium_still_sr_gate10_target_degradation_decision.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_GATE9_ACCEPTANCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_gate9_smoke_acceptance_20260702"
    / "smoke_gate_acceptance.json"
)
DEFAULT_REPLACEMENT_CONTRACT = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_replacement_target_source_contract_20260702"
    / "replacement_target_source_contract.json"
)
DEFAULT_TARGET_DISTRIBUTION = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_target_distribution_audit_20260701"
    / "target_distribution_audit.json"
)
DEFAULT_TARGET_SNR = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_raw_target_snr_audit_20260701"
    / "raw_target_snr_audit.json"
)
DEFAULT_SCOREBOARD = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_experiment_scoreboard_masked_detail_20260702"
    / "scoreboard.json"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def percentile_summary(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data
    for part in key.split("."):
        if not isinstance(value, dict):
            return {}
        value = value.get(part)
    return value if isinstance(value, dict) else {}


def summarize_gate9(path: Path) -> dict[str, Any]:
    data = load_json(path)
    rows: dict[str, dict[str, Any]] = {}
    for row in data.get("rows", []):
        if isinstance(row, dict):
            holdout = str(row.get("holdout") or row.get("camera") or "").lower()
            if holdout:
                rows[holdout] = {
                    "receipt": row.get("receipt"),
                    "checkpoint_sha256": row.get("checkpoint_sha256"),
                    "median_mae_recovery_pct": row.get("median_mae_improvement_pct"),
                    "worst_mae_recovery_pct": row.get("worst_row_mae_improvement_pct"),
                    "median_rmse_recovery_pct": row.get("median_rmse_improvement_pct"),
                    "baseline_beaten_on_holdout": bool(row.get("baseline_beaten_on_holdout")),
                    "passed": bool(row.get("passed")),
                    "elapsed_seconds": row.get("elapsed_seconds"),
                }
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "candidate_id": data.get("candidate_id"),
        "smoke_gate_passed": bool(data.get("smoke_gate_passed")),
        "long_run_allowed": bool(data.get("long_run_allowed")),
        "production_ready": bool(data.get("production_ready")),
        "verdict": data.get("verdict"),
        "failures": data.get("failures", []),
        "rows": rows,
    }


def summarize_contract(path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "verdict": data.get("verdict"),
        "paired_smoke_preflight_allowed": bool(data.get("paired_smoke_preflight_allowed")),
        "long_run_allowed": bool(data.get("long_run_allowed")),
        "decisions": data.get("decisions", {}),
        "acceptance": data.get("acceptance", {}),
    }


def summarize_distribution(path: Path) -> dict[str, Any]:
    data = load_json(path)
    split = data.get("split_comparison", {})
    summary = data.get("summary", {})
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "row_count": summary.get("row_count"),
        "camera_counts": summary.get("camera_counts", {}),
        "holdout_scene": split.get("holdout_scene"),
        "holdout_distribution_mismatch": bool(split.get("distribution_mismatch")),
        "holdout_median_to_train_median": split.get("holdout_median_to_train_median"),
        "holdout_rows_above_train_p90": split.get("holdout_rows_above_train_p90"),
        "holdout_row_count": split.get("holdout_row_count"),
    }


def summarize_snr(path: Path) -> dict[str, Any]:
    data = load_json(path)
    summary = data.get("summary", {})
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "row_count": summary.get("row_count"),
        "rows_with_noise_sidecars": summary.get("rows_with_noise_sidecars"),
        "classification_counts": summary.get("classification_counts", {}),
        "median_target_rmse_to_noise_sigma": percentile_summary(data, "summary.target_rmse_to_noise_sigma").get("median"),
        "median_target_p95_to_noise_p95": percentile_summary(data, "summary.target_p95_to_noise_p95").get("median"),
        "target_abs_to_candidate_hf_abs_median": percentile_summary(data, "summary.target_abs_to_candidate_hf_abs").get("median"),
        "by_camera": data.get("by_camera", []),
        "interpretation": data.get("interpretation"),
    }


def summarize_scoreboard(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    data = load_json(path)
    rows = data.get("rows", [])
    runtime_safe = [row for row in rows if isinstance(row, dict) and row.get("runtime_safe")]
    promotable = [row for row in runtime_safe if row.get("promotion_ready")]
    best = None
    if runtime_safe:
        best = max(runtime_safe, key=lambda row: float(row.get("median_mae_recovery_pct") or -1e9))
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "runtime_safe_receipt_count": len(runtime_safe),
        "promotable_receipt_count": len(promotable),
        "best_runtime_safe": {
            "candidate_id": best.get("candidate_id"),
            "median_mae_recovery_pct": best.get("median_mae_recovery_pct"),
            "median_rmse_recovery_pct": best.get("median_rmse_recovery_pct"),
            "receipt": best.get("receipt"),
        }
        if isinstance(best, dict)
        else None,
    }


def as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_decision(args: argparse.Namespace) -> dict[str, Any]:
    gate9 = summarize_gate9(args.gate9_acceptance)
    contract = summarize_contract(args.replacement_contract)
    distribution = summarize_distribution(args.target_distribution)
    snr = summarize_snr(args.target_snr)
    scoreboard = summarize_scoreboard(args.scoreboard)

    x2d = gate9["rows"].get("x2d", {})
    z8 = gate9["rows"].get("z8", {})
    x2d_median = as_float(x2d.get("median_mae_recovery_pct"))
    x2d_worst = as_float(x2d.get("worst_mae_recovery_pct"))
    z8_median = as_float(z8.get("median_mae_recovery_pct"))
    z8_worst = as_float(z8.get("worst_mae_recovery_pct"))
    z8_noise_floor_rows = 0
    z8_rows = 0
    for row in snr.get("by_camera", []):
        if isinstance(row, dict) and str(row.get("camera")).lower() == "z8":
            z8_rows = int(row.get("row_count") or 0)
            classes = row.get("classifications") if isinstance(row.get("classifications"), dict) else {}
            z8_noise_floor_rows = int(classes.get("noise_floor") or 0)

    failed_both_routes = x2d_median <= args.minimum_median_improvement_pct and z8_median <= args.minimum_median_improvement_pct
    severe_z8_tail = z8_worst < -args.severe_worst_row_regression_pct
    target_mismatch = bool(distribution.get("holdout_distribution_mismatch"))
    mixed_noise = int(snr.get("classification_counts", {}).get("noise_floor") or 0) > 0
    z8_mostly_noise_floor = z8_rows > 0 and z8_noise_floor_rows / z8_rows >= 0.5

    blocker_class = "source_degradation_target_mismatch"
    if not failed_both_routes:
        blocker_class = "route_conditioning_gap"
    if not target_mismatch and not mixed_noise:
        blocker_class = "model_capacity_or_objective_gap"

    allowed_candidate_families = [
        {
            "family": "measured_or_synthetic_degradation_teacher",
            "required_change": "Build a source/degradation target from a known downsample/blur/noise process or measured paired high/low capture, not from the failed candidate-minus-source residual.",
            "must_prove": "Both X2D and Z8 candidate-only smoke medians exceed 0.001% and worst rows are nonnegative before any long run.",
        },
        {
            "family": "route_isolated_teacher_then_router",
            "required_change": "Train X2D and Z8 from separate target/degradation policies; do not mix Z8 noise-floor targets into the same objective as X2D signal-dominated rows.",
            "must_prove": "The router chooses no-op for Z8 noise-floor tiles and a positive learned path only where a source-evidence receipt passes.",
        },
        {
            "family": "non_cnn_or_noop_selector_baseline",
            "required_change": "Create a deterministic selector that leaves low-error/noise-floor tiles unchanged and applies only proven camera/scene transforms.",
            "must_prove": "It beats exact no-op on positive-signal rows without any negative worst-row regression.",
        },
    ]

    forbidden_next_work = [
        "Gate 9 route-conditioned/noise-aware U-Net smoke rerun",
        "generic raw-CFA residual U-Net long run",
        "candidate-HF no-op threshold tuning",
        "simple frame-context conditioning",
        "frequency-pyramid source-evidence teacher rerun",
        "masked-detail/no-op target-objective rerun",
        "source-frequency absolute target objective",
    ]

    next_receipts = [
        {
            "order": 1,
            "receipt": "premium_still_sr_degradation_source_audit_<date>",
            "purpose": "Prove the replacement degradation/teacher source before training.",
            "done_when": "The audit names the target source, route split, no-op rule, and expected positive-signal rows for X2D and Z8.",
        },
        {
            "order": 2,
            "receipt": "premium_still_sr_gate11_candidate_intake_<date>",
            "purpose": "Preflight only a candidate from an allowed family above.",
            "done_when": "The preflight is launchable, runtime-safe, and refuses the forbidden next-work families.",
        },
        {
            "order": 3,
            "receipt": "premium_still_sr_gate11_smoke_acceptance_<date>",
            "purpose": "Run paired X2D/Z8 smoke before long training.",
            "done_when": "Both routes have median MAE improvement >0.001%, worst-row MAE >=0%, and baseline_beaten_on_holdout=true.",
        },
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": "replace_target_degradation_source_before_next_smoke",
        "production_ready": False,
        "long_run_allowed": False,
        "paired_smoke_allowed": False,
        "blocker_classification": blocker_class,
        "inputs": {
            "gate9_acceptance": gate9,
            "replacement_contract": contract,
            "target_distribution": distribution,
            "target_snr": snr,
            "scoreboard": scoreboard,
        },
        "finding": {
            "failed_both_routes": failed_both_routes,
            "x2d_median_mae_recovery_pct": x2d_median,
            "x2d_worst_mae_recovery_pct": x2d_worst,
            "z8_median_mae_recovery_pct": z8_median,
            "z8_worst_mae_recovery_pct": z8_worst,
            "severe_z8_tail": severe_z8_tail,
            "x2d_holdout_distribution_mismatch": target_mismatch,
            "x2d_holdout_median_to_train_median": distribution.get("holdout_median_to_train_median"),
            "mixed_signal_noise_targets": mixed_noise,
            "z8_noise_floor_rows": z8_noise_floor_rows,
            "z8_row_count": z8_rows,
            "z8_mostly_noise_floor_targets": z8_mostly_noise_floor,
            "scoreboard_promotable_receipts": (scoreboard or {}).get("promotable_receipt_count"),
        },
        "allowed_candidate_families": allowed_candidate_families,
        "forbidden_next_work": forbidden_next_work,
        "next_receipts": next_receipts,
        "acceptance": {
            "minimum_median_mae_recovery_pct_exclusive": args.minimum_median_improvement_pct,
            "minimum_worst_row_mae_recovery_pct": 0.0,
            "promotion_median_mae_recovery_pct_min": 15.0,
            "promotion_median_rmse_recovery_pct_min": 15.0,
            "production_submission_required": True,
        },
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    finding = data["finding"]
    allowed = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['family'])}</td>"
        f"<td>{html.escape(item['required_change'])}</td>"
        f"<td>{html.escape(item['must_prove'])}</td>"
        "</tr>"
        for item in data["allowed_candidate_families"]
    )
    forbidden = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["forbidden_next_work"])
    receipts = "\n".join(
        "<tr>"
        f"<td>{item['order']}</td>"
        f"<td>{html.escape(item['receipt'])}</td>"
        f"<td>{html.escape(item['purpose'])}</td>"
        f"<td>{html.escape(item['done_when'])}</td>"
        "</tr>"
        for item in data["next_receipts"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Gate 10 Decision</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #18212b; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin: 16px 0; }}
th, td {{ border-bottom: 1px solid #e8edf2; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Gate 10 Decision</h1>
<p>Gate 9 regressed both routes. The next production step is target/degradation replacement, not another weight-tuned smoke from the rejected family.</p>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{html.escape(data['verdict'])}</div></section>
  <section class="card"><div class="label">Blocker</div><div class="value">{html.escape(data['blocker_classification'])}</div></section>
  <section class="card"><div class="label">Long run allowed</div><div class="value">{data['long_run_allowed']}</div></section>
  <section class="card"><div class="label">Paired smoke allowed</div><div class="value">{data['paired_smoke_allowed']}</div></section>
</div>
<div class="grid">
  <section class="card"><div class="label">X2D median / worst MAE</div><div class="value">{finding['x2d_median_mae_recovery_pct']:.6g}% / {finding['x2d_worst_mae_recovery_pct']:.6g}%</div></section>
  <section class="card"><div class="label">Z8 median / worst MAE</div><div class="value">{finding['z8_median_mae_recovery_pct']:.6g}% / {finding['z8_worst_mae_recovery_pct']:.6g}%</div></section>
  <section class="card"><div class="label">X2D holdout/train median</div><div class="value">{finding['x2d_holdout_median_to_train_median']:.4g}x</div></section>
  <section class="card"><div class="label">Z8 noise-floor rows</div><div class="value">{finding['z8_noise_floor_rows']} / {finding['z8_row_count']}</div></section>
</div>
<h2>Allowed Next Candidate Families</h2>
<table><tr><th>Family</th><th>Required change</th><th>Must prove</th></tr>{allowed}</table>
<h2>Forbidden Next Work</h2>
<ul>{forbidden}</ul>
<h2>Next Receipts</h2>
<table><tr><th>Order</th><th>Receipt</th><th>Purpose</th><th>Done when</th></tr>{receipts}</table>
<p>JSON receipt: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate9-acceptance", type=Path, default=DEFAULT_GATE9_ACCEPTANCE)
    parser.add_argument("--replacement-contract", type=Path, default=DEFAULT_REPLACEMENT_CONTRACT)
    parser.add_argument("--target-distribution", type=Path, default=DEFAULT_TARGET_DISTRIBUTION)
    parser.add_argument("--target-snr", type=Path, default=DEFAULT_TARGET_SNR)
    parser.add_argument("--scoreboard", type=Path, default=DEFAULT_SCOREBOARD)
    parser.add_argument("--minimum-median-improvement-pct", type=float, default=0.001)
    parser.add_argument("--severe-worst-row-regression-pct", type=float, default=10.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = build_decision(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "gate10_target_degradation_decision.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
