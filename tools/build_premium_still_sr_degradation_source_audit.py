#!/usr/bin/env python3
"""Build the Premium still-SR degradation-source audit receipt.

This is the first required receipt after Gate 10. It chooses the replacement
source policy that a Gate 11 candidate intake may use. It does not train and it
does not authorize a long run.
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


SCHEMA = "gpr.premium_still_sr_degradation_source_audit.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_GATE10 = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_gate10_target_degradation_decision_20260702"
    / "gate10_target_degradation_decision.json"
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
DEFAULT_X2D_SOURCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_source_evidence_x2dholdout_t64_20260702"
    / "source_evidence_audit.json"
)
DEFAULT_Z8_SOURCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_source_evidence_z8holdout_t64_20260702"
    / "source_evidence_audit.json"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def median_metric(data: dict[str, Any], metric: str) -> float:
    value = nested(data, ["summary", metric, "median"], 0.0)
    return float(value or 0.0)


def source_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "holdout_camera": data.get("holdout_camera"),
        "source_evidence_present": bool(nested(data, ["acceptance", "source_evidence_present"], False)),
        "median_mae_recovery_pct": median_metric(data, "linear_probe_mae_recovery_pct"),
        "median_rmse_recovery_pct": median_metric(data, "linear_probe_rmse_recovery_pct"),
        "min_required_recovery_pct": float(nested(data, ["acceptance", "min_median_mae_recovery_pct"], 1.0) or 1.0),
        "runtime_inputs": nested(data, ["probe", "runtime_inputs"], []),
        "forbidden_inputs": nested(data, ["probe", "forbidden_inputs"], []),
    }


def camera_snr_rows(data: dict[str, Any], camera: str) -> dict[str, Any]:
    for row in data.get("by_camera", []):
        if isinstance(row, dict) and str(row.get("camera")).lower() == camera.lower():
            classes = row.get("classifications") if isinstance(row.get("classifications"), dict) else {}
            row_count = int(row.get("row_count") or 0)
            return {
                "row_count": row_count,
                "classifications": classes,
                "noise_floor_rows": int(classes.get("noise_floor") or 0),
                "signal_dominated_rows": int(classes.get("signal_dominated") or 0),
                "mixed_signal_noise_rows": int(classes.get("mixed_signal_noise") or 0),
                "noise_floor_fraction": (int(classes.get("noise_floor") or 0) / row_count) if row_count else 0.0,
                "median_target_rmse_to_noise_sigma": nested(row, ["target_rmse_to_noise_sigma", "median"], 0.0),
                "median_target_p95_to_noise_p95": nested(row, ["target_p95_to_noise_p95", "median"], 0.0),
            }
    return {
        "row_count": 0,
        "classifications": {},
        "noise_floor_rows": 0,
        "signal_dominated_rows": 0,
        "mixed_signal_noise_rows": 0,
        "noise_floor_fraction": 0.0,
        "median_target_rmse_to_noise_sigma": 0.0,
        "median_target_p95_to_noise_p95": 0.0,
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    gate10 = load_json(args.gate10_decision)
    distribution = load_json(args.target_distribution)
    snr = load_json(args.target_snr)
    x2d_source = source_summary(args.x2d_source_evidence)
    z8_source = source_summary(args.z8_source_evidence)

    x2d_snr = camera_snr_rows(snr, "x2d")
    z8_snr = camera_snr_rows(snr, "z8")
    split = distribution.get("split_comparison", {})
    x2d_needs_stratified_target = bool(split.get("distribution_mismatch"))
    z8_requires_noop_or_new_source = (
        not z8_source["source_evidence_present"] or z8_snr["noise_floor_fraction"] >= args.z8_noise_floor_noop_fraction
    )
    x2d_eligible = x2d_source["source_evidence_present"] and x2d_snr["signal_dominated_rows"] > 0

    selected_family = "route_isolated_teacher_then_router"
    if not x2d_eligible and z8_requires_noop_or_new_source:
        selected_family = "non_cnn_or_noop_selector_baseline"

    route_policy = {
        "x2d": {
            "policy": "train_signal_dominated_route_with_stratified_target_sampling" if x2d_eligible else "no_train_until_source_evidence_passes",
            "source": "candidate-only local signal plus measured/synthetic degradation teacher",
            "eligible_training_rows": x2d_snr["signal_dominated_rows"] + x2d_snr["mixed_signal_noise_rows"],
            "must_filter": "exclude noise-floor target rows from positive residual loss; keep exact no-op fallback",
            "reason": (
                f"X2D source evidence is {x2d_source['median_mae_recovery_pct']:.4f}% MAE / "
                f"{x2d_source['median_rmse_recovery_pct']:.4f}% RMSE, but holdout distribution is "
                f"{float(split.get('holdout_median_to_train_median') or 0.0):.4g}x the train median."
            ),
        },
        "z8": {
            "policy": "default_noop_for_noise_floor_rows_and_require_new_source_for_positive_route"
            if z8_requires_noop_or_new_source
            else "train_route_with_signal_rows_only",
            "source": "new measured/synthetic degradation source required before positive residual training",
            "eligible_training_rows": z8_snr["signal_dominated_rows"] + z8_snr["mixed_signal_noise_rows"],
            "must_filter": "noise-floor rows must be exact no-op or zero-weighted in residual loss",
            "reason": (
                f"Z8 source evidence is {z8_source['median_mae_recovery_pct']:.4f}% MAE versus "
                f"{z8_source['min_required_recovery_pct']:.1f}% required, and "
                f"{z8_snr['noise_floor_rows']}/{z8_snr['row_count']} rows are noise-floor targets."
            ),
        },
    }

    gate11_allowed = bool(
        gate10.get("blocker_classification") == "source_degradation_target_mismatch"
        and gate10.get("long_run_allowed") is False
        and selected_family in {"route_isolated_teacher_then_router", "non_cnn_or_noop_selector_baseline"}
    )

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": "degradation_source_policy_ready_for_gate11_preflight" if gate11_allowed else "degradation_source_policy_incomplete",
        "production_ready": False,
        "long_run_allowed": False,
        "gate11_candidate_intake_allowed": gate11_allowed,
        "selected_family": selected_family,
        "inputs": {
            "gate10_decision": {
                "path": str(args.gate10_decision),
                "sha256": sha256_file(args.gate10_decision),
                "schema": gate10.get("schema"),
                "blocker_classification": gate10.get("blocker_classification"),
            },
            "target_distribution": {
                "path": str(args.target_distribution),
                "sha256": sha256_file(args.target_distribution),
                "schema": distribution.get("schema"),
                "holdout_distribution_mismatch": bool(split.get("distribution_mismatch")),
                "holdout_median_to_train_median": split.get("holdout_median_to_train_median"),
                "holdout_rows_above_train_p90": split.get("holdout_rows_above_train_p90"),
            },
            "target_snr": {
                "path": str(args.target_snr),
                "sha256": sha256_file(args.target_snr),
                "schema": snr.get("schema"),
                "x2d": x2d_snr,
                "z8": z8_snr,
            },
            "x2d_source_evidence": x2d_source,
            "z8_source_evidence": z8_source,
        },
        "route_policy": route_policy,
        "gate11_preflight_requirements": [
            "candidate runtime inputs: candidate_raw plus camera metadata and exact validated noise sidecar scalars only",
            "forbidden runtime inputs: REF, source RAW, source RGB/HF, JPEG/JPG target, source residual noise, and gate metrics",
            "X2D route must use stratified target sampling and exact no-op fallback for low-error/noise-floor tiles",
            "Z8 route must default no-op for noise-floor rows and must not train positive residuals without a new source-evidence receipt",
            "paired smoke must pass X2D and Z8 with median MAE improvement >0.001%, worst-row MAE >=0%, and baseline_beaten_on_holdout=true",
        ],
        "forbidden_gate11_sources": [
            "failed Gate 9 route-conditioned/noise-aware U-Net source policy",
            "candidate-minus-source raw-CFA residual without route isolation",
            "unweighted mixed signal/noise residual loss",
            "Z8 positive residual training on current noise-floor rows",
            "any render-time REF/source/JPEG image content",
        ],
        "next_receipts": [
            {
                "order": 1,
                "receipt": "premium_still_sr_gate11_candidate_intake_<date>",
                "done_when": "A launchable preflight encodes this route policy and rejects forbidden sources.",
            },
            {
                "order": 2,
                "receipt": "premium_still_sr_gate11_smoke_acceptance_<date>",
                "done_when": "Paired X2D/Z8 smoke passes before any long run.",
            },
            {
                "order": 3,
                "receipt": "premium_still_sr_promotion_receipts",
                "done_when": "50 MP / 100 MP promotion clears 15% / 15% recovery, nonnegative worst rows, editor/openability, timing/memory, hashes, and production submission validation.",
            },
        ],
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    policies = "\n".join(
        "<tr>"
        f"<td>{html.escape(camera)}</td>"
        f"<td>{html.escape(policy['policy'])}</td>"
        f"<td>{html.escape(str(policy['eligible_training_rows']))}</td>"
        f"<td>{html.escape(policy['reason'])}</td>"
        "</tr>"
        for camera, policy in data["route_policy"].items()
    )
    requirements = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["gate11_preflight_requirements"])
    forbidden = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["forbidden_gate11_sources"])
    next_rows = "\n".join(
        "<tr>"
        f"<td>{row['order']}</td>"
        f"<td>{html.escape(row['receipt'])}</td>"
        f"<td>{html.escape(row['done_when'])}</td>"
        "</tr>"
        for row in data["next_receipts"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Degradation Source Audit</title>
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
<h1>Premium Still-SR Degradation Source Audit</h1>
<p>This receipt selects the replacement source policy allowed for the next Premium still-SR preflight. It does not train and it does not authorize a long run.</p>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{html.escape(data['verdict'])}</div></section>
  <section class="card"><div class="label">Selected family</div><div class="value">{html.escape(data['selected_family'])}</div></section>
  <section class="card"><div class="label">Gate 11 intake allowed</div><div class="value">{data['gate11_candidate_intake_allowed']}</div></section>
  <section class="card"><div class="label">Long run allowed</div><div class="value">{data['long_run_allowed']}</div></section>
</div>
<h2>Route Policy</h2>
<table><tr><th>Route</th><th>Policy</th><th>Eligible rows</th><th>Reason</th></tr>{policies}</table>
<h2>Gate 11 Requirements</h2>
<ul>{requirements}</ul>
<h2>Forbidden Sources</h2>
<ul>{forbidden}</ul>
<h2>Next Receipts</h2>
<table><tr><th>Order</th><th>Receipt</th><th>Done when</th></tr>{next_rows}</table>
<p>JSON receipt: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate10-decision", type=Path, default=DEFAULT_GATE10)
    parser.add_argument("--target-distribution", type=Path, default=DEFAULT_TARGET_DISTRIBUTION)
    parser.add_argument("--target-snr", type=Path, default=DEFAULT_TARGET_SNR)
    parser.add_argument("--x2d-source-evidence", type=Path, default=DEFAULT_X2D_SOURCE)
    parser.add_argument("--z8-source-evidence", type=Path, default=DEFAULT_Z8_SOURCE)
    parser.add_argument("--z8-noise-floor-noop-fraction", type=float, default=0.5)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = build_audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "degradation_source_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
