#!/usr/bin/env python3
"""Check premium still-SR signal/noise and promotion policy receipts.

This is a productionization guard, not a model trainer.  It verifies that the
current premium still-SR target/model receipts keep calibrated signal recovery
separate from render-time noise addback and that diagnostic teacher/model runs
are not accidentally promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_noise_policy_gate.v1"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def nested(data: dict[str, Any], keys: list[str]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def number(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def is_false(value: Any) -> bool:
    return value is False or value == 0


def clean_signal_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    policy = data.get("policy", {}) if isinstance(data.get("policy"), dict) else {}
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    row_count = int(summary.get("row_count") or 0)
    rows_with_noise = int(summary.get("rows_with_noise_sidecars") or 0)
    blockers: list[str] = []
    if data.get("schema") != "gpr.premium_still_sr_clean_signal_targets.v1":
        blockers.append("clean-signal receipt schema mismatch")
    if not is_false(policy.get("uses_source_raw_at_runtime")):
        blockers.append("clean-signal target allows source raw at runtime")
    if not is_false(policy.get("uses_ref_or_jpeg_content_at_runtime")):
        blockers.append("clean-signal target allows REF/JPEG content at runtime")
    if not is_false(policy.get("exact_source_noise_addback_allowed_at_runtime")):
        blockers.append("clean-signal target allows exact source-noise addback at runtime")
    if row_count <= 0:
        blockers.append("clean-signal target has no rows")
    if rows_with_noise != row_count:
        blockers.append("not every clean-signal row has a calibrated noise sidecar")
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "row_count": row_count,
        "rows_with_noise_sidecars": rows_with_noise,
        "median_target_energy_retained_fraction": nested(summary, ["target_energy_retained_fraction", "median"]),
        "median_active_pixel_fraction": nested(summary, ["active_pixel_fraction", "median"]),
        "classification_counts": summary.get("classification_counts", {}),
        "policy": {
            "uses_source_raw_at_training_target": bool(policy.get("uses_source_raw_at_training_target")),
            "uses_source_raw_at_runtime": policy.get("uses_source_raw_at_runtime"),
            "uses_ref_or_jpeg_content_at_runtime": policy.get("uses_ref_or_jpeg_content_at_runtime"),
            "exact_source_noise_addback_allowed_at_runtime": policy.get("exact_source_noise_addback_allowed_at_runtime"),
            "runtime_addback_policy": policy.get("runtime_addback_policy"),
        },
        "policy_pass": not blockers,
        "blockers": blockers,
    }


def metric_median(receipt: dict[str, Any], keys: list[str]) -> float | None:
    value = nested(receipt, keys)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, dict):
        median = value.get("median")
        if isinstance(median, (int, float)) and not isinstance(median, bool):
            return float(median)
    return None


def model_metrics(data: dict[str, Any]) -> dict[str, Any]:
    schema = str(data.get("schema") or "")
    if schema == "gpr.premium_still_sr_clean_source_pair_model.v1":
        return {
            "metric_family": "clean_source_pair_teacher_vs_same_color_interpolation",
            "holdout_mae_gain_pct": metric_median(data, ["eval", "holdout", "mae_improvement_pct"]),
            "holdout_rmse_gain_pct": metric_median(data, ["eval", "holdout", "rmse_improvement_pct"]),
            "train_mae_gain_pct": metric_median(data, ["eval", "train", "mae_improvement_pct"]),
            "train_rmse_gain_pct": metric_median(data, ["eval", "train", "rmse_improvement_pct"]),
            "holdout_rows": int(nested(data, ["eval", "holdout", "tile_count"]) or 0),
            "train_rows": int(nested(data, ["eval", "train", "tile_count"]) or 0),
        }
    return {
        "metric_family": "raw_cfa_residual_candidate_vs_baseline",
        "holdout_mae_gain_pct": metric_median(data, ["eval", "holdout", "raw_residual_mae_reduction_pct"]),
        "holdout_rmse_gain_pct": metric_median(data, ["eval", "holdout", "raw_residual_rmse_reduction_pct"]),
        "train_mae_gain_pct": metric_median(data, ["eval", "train", "raw_residual_mae_reduction_pct"]),
        "train_rmse_gain_pct": metric_median(data, ["eval", "train", "raw_residual_rmse_reduction_pct"]),
        "holdout_rows": int(nested(data, ["eval", "holdout", "row_count"]) or nested(data, ["eval", "holdout", "count"]) or 0),
        "train_rows": int(nested(data, ["eval", "train", "row_count"]) or nested(data, ["eval", "train", "count"]) or 0),
    }


def model_status(path: Path, data: dict[str, Any], mae_floor: float, rmse_floor: float) -> dict[str, Any]:
    policy = data.get("policy", {}) if isinstance(data.get("policy"), dict) else {}
    promotion = data.get("promotion", {}) if isinstance(data.get("promotion"), dict) else {}
    config = data.get("config", {}) if isinstance(data.get("config"), dict) else {}
    metrics = model_metrics(data)
    mae = metrics["holdout_mae_gain_pct"]
    rmse = metrics["holdout_rmse_gain_pct"]
    production_status = str(policy.get("production_status") or "")
    promotion_ready = bool(promotion.get("promotion_ready") or data.get("production_ready"))
    baseline_beaten = bool(promotion.get("baseline_beaten_on_holdout")) if promotion else False
    runtime_source = policy.get("uses_source_raw_at_runtime")
    if runtime_source is None:
        runtime_source = False if data.get("schema") == "gpr.premium_still_sr_clean_source_pair_model.v1" else None

    blockers: list[str] = []
    if runtime_source not in (False, 0):
        blockers.append("model receipt does not prove source raw is absent at runtime")
    if policy.get("uses_ref_or_jpeg_content_at_runtime") not in (False, 0, None):
        blockers.append("model receipt allows REF/JPEG content at runtime")
    if mae is None or mae < mae_floor:
        blockers.append(f"holdout median MAE gain is below {mae_floor:.1f}%")
    if rmse is None or rmse < rmse_floor:
        blockers.append(f"holdout median RMSE gain is below {rmse_floor:.1f}%")
    if data.get("schema") == "gpr.premium_still_sr_clean_source_pair_model.v1" and not baseline_beaten:
        blockers.append("clean-source teacher does not beat nearest same-color interpolation on holdout")
    if "not_registered_production_algorithm" in production_status:
        blockers.append("receipt is explicitly diagnostic and not registered as a production algorithm")
    if promotion_ready and blockers:
        blockers.insert(0, "receipt claims promotion readiness but policy/metric blockers remain")

    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "checkpoint_sha256": data.get("checkpoint_sha256"),
        "steps": data.get("steps") or config.get("steps"),
        "model_arch": config.get("model_arch") or ("residual_pixelshuffle" if data.get("schema") == "gpr.premium_still_sr_clean_source_pair_model.v1" else None),
        "feature_mode": config.get("feature_mode"),
        "promotion_ready_claimed": promotion_ready,
        "baseline_beaten_on_holdout": baseline_beaten,
        "runtime_policy": {
            "uses_source_raw_at_runtime": runtime_source,
            "uses_ref_or_jpeg_content_at_runtime": policy.get("uses_ref_or_jpeg_content_at_runtime"),
            "production_status": policy.get("production_status"),
            "runtime_inputs": policy.get("runtime_inputs"),
        },
        "metrics": metrics,
        "passes_promotion_metric_floor": not any("holdout median" in blocker for blocker in blockers),
        "policy_pass": not blockers,
        "blockers": blockers,
    }


def render_html(receipt: dict[str, Any]) -> str:
    model_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(Path(row['path']).name)}</td>"
        f"<td>{html.escape(str(row.get('schema')))}</td>"
        f"<td>{html.escape(str(row.get('model_arch')))}</td>"
        f"<td>{number(row['metrics'].get('holdout_mae_gain_pct')):.3f}%</td>"
        f"<td>{number(row['metrics'].get('holdout_rmse_gain_pct')):.3f}%</td>"
        f"<td>{'pass' if row['policy_pass'] else 'blocked'}</td>"
        f"<td>{html.escape('; '.join(row['blockers']))}</td>"
        "</tr>"
        for row in receipt["model_receipts"]
    )
    clean = receipt["clean_signal"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Noise Policy Gate</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #131820; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dde3e9; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 25px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3e9; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Noise Policy Gate</h1>
<p class="sub">Checks that clean-signal targets use calibrated sidecars, forbid source/REF/JPEG content at render time, and that diagnostic still-SR model receipts are not promoted before holdout gains and runtime policy clear the gate.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value">{str(receipt['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Clean target rows</div><div class="value">{clean['row_count']}</div></section>
  <section class="card"><div class="label">Noise sidecars</div><div class="value">{clean['rows_with_noise_sidecars']}</div></section>
  <section class="card"><div class="label">Model receipts</div><div class="value">{len(receipt['model_receipts'])}</div></section>
</div>
<h2>Decision</h2>
<p>{html.escape(receipt['decision'])}</p>
<h2>Blockers</h2>
<ul>{"".join(f"<li>{html.escape(item)}</li>" for item in receipt["blockers"])}</ul>
<h2>Clean-Signal Target</h2>
<p><code>{html.escape(clean['path'])}</code></p>
<h2>Model Receipts</h2>
<table><tr><th>receipt</th><th>schema</th><th>arch</th><th>holdout MAE</th><th>holdout RMSE</th><th>policy</th><th>blockers</th></tr>{model_rows}</table>
</main></body></html>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    clean_path = args.clean_signal_targets
    clean_data = load_json(clean_path)
    clean = clean_signal_status(clean_path, clean_data)
    models = [
        model_status(path, load_json(path), args.mae_floor, args.rmse_floor)
        for path in args.model_receipt
    ]
    blockers = list(clean["blockers"])
    if not models:
        blockers.append("no model receipts supplied")
    if not any(row["policy_pass"] for row in models):
        blockers.append("no supplied model receipt clears the promotion policy and holdout floors")
    promotion_claims = [row for row in models if row["promotion_ready_claimed"]]
    unsafe_claims = [row for row in promotion_claims if not row["policy_pass"]]
    if unsafe_claims:
        blockers.append("one or more receipts claim promotion readiness despite blockers")
    production_ready = clean["policy_pass"] and bool(models) and any(row["policy_pass"] for row in models)
    if production_ready:
        decision = "promotion noise policy and holdout floors pass for at least one supplied model receipt"
    elif clean["policy_pass"]:
        decision = (
            "clean-signal/noise policy passes, but the supplied still-SR models remain diagnostic; "
            "do not promote until a candidate-only receipt beats the holdout floors"
        )
    else:
        decision = "clean-signal/noise policy is incomplete; fix sidecar/runtime policy before model promotion"

    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_ready": production_ready,
        "decision": decision,
        "thresholds": {
            "holdout_mae_gain_pct_min": float(args.mae_floor),
            "holdout_rmse_gain_pct_min": float(args.rmse_floor),
        },
        "clean_signal": clean,
        "model_receipts": models,
        "blockers": blockers,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "premium_still_sr_noise_policy_gate.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": json_path.as_posix(), "dashboard": html_path.as_posix(), "production_ready": production_ready}, indent=2))
    if args.require_production_ready and not production_ready:
        return receipt | {"_exit_code": 1}
    return receipt | {"_exit_code": 0}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean-signal-targets", type=Path, required=True)
    ap.add_argument("--model-receipt", type=Path, action="append", default=[])
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--mae-floor", type=float, default=15.0)
    ap.add_argument("--rmse-floor", type=float, default=15.0)
    ap.add_argument("--require-production-ready", action="store_true")
    return ap.parse_args()


def main() -> int:
    return int(build(parse_args()).get("_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
