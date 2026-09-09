#!/usr/bin/env python3
"""Audit whether a Gate14 still-SR objective can be saved by runtime gating.

This is a pre-long-run receipt. It reads one or more smoke receipts, computes
the oracle best case where every positive row may be selected and every other
row becomes exact no-op, then checks candidate-only threshold predicates. If
the oracle cannot clear the smoke median floor, no runtime-safe gate can rescue
that objective; the target/objective must change.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import statistics
import time
from hashlib import sha256
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate14_objective_gate_audit.v1"
ARTIFACT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/artifacts")
DEFAULT_RECEIPTS = [
    ARTIFACT_ROOT
    / "premium_still_sr_gate14_direct_clean2x_x2d_smoke_20260702"
    / "train_receipt.json",
    ARTIFACT_ROOT
    / "premium_still_sr_gate14_direct_clean2x_z8_smoke_20260702"
    / "train_receipt.json",
    ARTIFACT_ROOT
    / "premium_still_sr_gate14_sourcehf_storedhf_x2d_smoke_20260702"
    / "train_receipt.json",
    ARTIFACT_ROOT
    / "premium_still_sr_gate14_sourcehf_storedhf_z8_smoke_20260702"
    / "train_receipt.json",
]
DEFAULT_OUTPUT_DIR = ARTIFACT_ROOT / "premium_still_sr_gate14_objective_gate_audit_20260702"

DISALLOWED_FEATURE_FRAGMENTS = (
    "source_",
    "raw_residual",
    "model_",
    "baseline_",
    "mae",
    "rmse",
    "psnr",
    "target",
    "gate_metric",
    "oracle",
    "sha256",
)
ALLOWED_NUMERIC_PREFIXES = (
    "candidate_",
    "crop_",
    "high_",
    "low_",
    "ev",
    "tile_index",
    "index",
    "gate14_output_index",
)


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def metric_value(row: dict[str, Any]) -> float | None:
    for key in ("raw_residual_mae_reduction_pct", "mae_improvement_pct"):
        value = row.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return None


def median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def stat(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "median": median(values),
        "mean": sum(values) / len(values) if values else None,
        "max": max(values) if values else None,
        "negative_count": sum(1 for value in values if value < 0.0),
        "positive_count": sum(1 for value in values if value > 0.0),
    }


def receipt_label(path: Path, receipt: dict[str, Any]) -> str:
    config = receipt.get("config") if isinstance(receipt.get("config"), dict) else {}
    holdout = config.get("holdout_scene")
    if not holdout and isinstance(config.get("holdout_images"), list):
        holdout = ",".join(config.get("holdout_images", []))
    if not holdout:
        rows = receipt_rows(receipt)
        holdouts = sorted({str(row.get("image_id") or row.get("scene_id") or "") for row in rows if isinstance(row, dict)})
        holdout = ",".join(item for item in holdouts if item) or "unknown"
    return f"{path.parent.name}:{holdout}"


def receipt_rows(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    rows = receipt.get("eval", {}).get("holdout", {}).get("rows") if isinstance(receipt.get("eval"), dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def numeric_candidate_features(rows: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                continue
            if any(fragment in key for fragment in DISALLOWED_FEATURE_FRAGMENTS):
                continue
            if key.startswith(ALLOWED_NUMERIC_PREFIXES):
                keys.add(key)
    return sorted(keys)


def predicate_masks(rows: list[dict[str, Any]], feature_keys: list[str]) -> list[dict[str, Any]]:
    predicates: list[dict[str, Any]] = []
    seen: set[int] = {0}
    for key in feature_keys:
        values = sorted({float(row[key]) for row in rows if isinstance(row.get(key), (int, float))})
        if len(values) < 2:
            continue
        thresholds = [(a + b) / 2.0 for a, b in zip(values, values[1:])]
        for op in (">=", "<="):
            for threshold in thresholds:
                mask = 0
                for i, row in enumerate(rows):
                    value = row.get(key)
                    if not isinstance(value, (int, float)):
                        continue
                    if (float(value) >= threshold) if op == ">=" else (float(value) <= threshold):
                        mask |= 1 << i
                if mask in seen:
                    continue
                seen.add(mask)
                predicates.append({"name": f"{key} {op} {threshold:.8g}", "mask": mask})
    return predicates


def values_for_mask(values: list[float], mask: int) -> list[float]:
    out: list[float] = []
    for i, value in enumerate(values):
        out.append(value if ((mask >> i) & 1) and value > 0.0 else 0.0)
    return out


def passes(values: list[float], median_floor: float, worst_floor: float) -> bool:
    return bool(values) and min(values) >= worst_floor and float(statistics.median(values)) >= median_floor


def audit_receipt(path: Path, median_floor: float, worst_floor: float) -> dict[str, Any]:
    receipt = load_json(path)
    rows = receipt_rows(receipt)
    if not rows:
        raise ValueError(f"{path} has no eval.holdout.rows")
    values: list[float] = []
    kept_rows: list[dict[str, Any]] = []
    for row in rows:
        value = metric_value(row)
        if value is None:
            continue
        values.append(value)
        kept_rows.append(row)
    if not values:
        raise ValueError(f"{path} has no supported per-row MAE improvement values")

    oracle_values = [value if value > 0.0 else 0.0 for value in values]
    feature_keys = numeric_candidate_features(kept_rows)
    predicates = predicate_masks(kept_rows, feature_keys)
    negative_mask = 0
    positive_floor_mask = 0
    for i, value in enumerate(values):
        if value < worst_floor:
            negative_mask |= 1 << i
        if value >= median_floor:
            positive_floor_mask |= 1 << i

    safe_union = 0
    safe_predicate_count = 0
    examples: list[dict[str, Any]] = []
    for predicate in predicates:
        mask = int(predicate["mask"])
        if mask & negative_mask:
            continue
        if not (mask & positive_floor_mask):
            continue
        safe_predicate_count += 1
        safe_union |= mask
        if len(examples) < 10:
            examples.append(
                {
                    "predicate": predicate["name"],
                    "selected_rows": int(mask.bit_count()),
                    "positive_floor_rows": int((mask & positive_floor_mask).bit_count()),
                }
            )

    safe_values = values_for_mask(values, safe_union)
    oracle_passes = passes(oracle_values, median_floor, worst_floor)
    safe_passes = passes(safe_values, median_floor, worst_floor)
    if not oracle_passes:
        blocker = "insufficient_positive_signal"
    elif not safe_passes:
        blocker = "runtime_feature_separability_gap"
    else:
        blocker = "none"
    return {
        "label": receipt_label(path, receipt),
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": receipt.get("schema"),
        "checkpoint_sha256": receipt.get("checkpoint_sha256"),
        "row_count": len(values),
        "positive_floor_row_count": int(positive_floor_mask.bit_count()),
        "negative_row_count": int(negative_mask.bit_count()),
        "minimum_rows_needed_for_median_floor": len(values) // 2 + 1,
        "raw_smoke_values": stat(values),
        "oracle_positive_noop_upper_bound": {
            "passes": oracle_passes,
            "values": stat(oracle_values),
        },
        "candidate_only_feature_gate_upper_bound": {
            "passes": safe_passes,
            "feature_count": len(feature_keys),
            "predicate_count": len(predicates),
            "safe_predicate_count": safe_predicate_count,
            "values": stat(safe_values),
            "examples": examples,
        },
        "blocker_classification": blocker,
    }


def render_html(receipt: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['label'])}</td>"
        f"<td>{html.escape(row['blocker_classification'])}</td>"
        f"<td>{row['positive_floor_row_count']} / {row['minimum_rows_needed_for_median_floor']}</td>"
        f"<td>{row['raw_smoke_values']['median']:.6g}</td>"
        f"<td>{row['raw_smoke_values']['min']:.6g}</td>"
        f"<td>{row['oracle_positive_noop_upper_bound']['values']['median']:.6g}</td>"
        f"<td>{row['candidate_only_feature_gate_upper_bound']['values']['median']:.6g}</td>"
        "</tr>"
        for row in receipt["rows"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Gate14 Objective Gate Audit</title>
<style>
body {{ margin: 28px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin-top: 12px; }}
th, td {{ border-bottom: 1px solid #e9edf1; padding: 8px; text-align: left; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; font-size: 12px; }}
</style></head><body><main>
<h1>Gate14 Objective Gate Audit</h1>
<p>This receipt checks whether a failed Premium still-SR objective can be rescued by candidate-only runtime gating before any long run.</p>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{html.escape(receipt['verdict'])}</div></section>
  <section class="card"><div class="label">Blocker</div><div class="value">{html.escape(receipt['blocker_classification'])}</div></section>
  <section class="card"><div class="label">Receipts</div><div class="value">{len(receipt['rows'])}</div></section>
  <section class="card"><div class="label">Median Floor</div><div class="value">{receipt['acceptance']['minimum_median_mae_reduction_pct']}%</div></section>
</div>
<table>
<tr><th>receipt</th><th>blocker</th><th>positive rows / needed</th><th>raw median</th><th>raw worst</th><th>oracle median</th><th>feature-gate median</th></tr>
{rows}
</table>
<p><strong>Next action:</strong> {html.escape(receipt['next_unambiguous_action'])}</p>
</main></body></html>
"""


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    rows = [audit_receipt(path, args.minimum_median_mae_reduction_pct, args.minimum_worst_row_mae_reduction_pct) for path in args.receipt]
    blockers = sorted({row["blocker_classification"] for row in rows if row["blocker_classification"] != "none"})
    gate_rescue_possible = all(row["candidate_only_feature_gate_upper_bound"]["passes"] for row in rows)
    oracle_possible = all(row["oracle_positive_noop_upper_bound"]["passes"] for row in rows)
    if gate_rescue_possible:
        verdict = "gate14_objective_gate_rescue_possible"
        blocker = "none"
        next_action = "Build a candidate preflight around the passing gate and rerun paired X2D/Z8 smokes."
    elif not oracle_possible:
        verdict = "blocked_before_gate_construction"
        blocker = "insufficient_positive_signal"
        next_action = (
            "Do not tune thresholds or run longer training. Change the target/objective so the holdout creates "
            "enough positive candidate-only rows before reattempting paired smokes."
        )
    else:
        verdict = "blocked_runtime_feature_gate"
        blocker = "runtime_feature_separability_gap"
        next_action = "Do not run long training. Add better candidate-only gate features or a safer target construction."
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "production_ready": False,
        "long_run_allowed": False,
        "gate_rescue_possible": gate_rescue_possible,
        "oracle_positive_signal_possible": oracle_possible,
        "blocker_classification": blocker if blocker != "none" else (blockers[0] if blockers else "none"),
        "next_unambiguous_action": next_action,
        "acceptance": {
            "minimum_median_mae_reduction_pct": args.minimum_median_mae_reduction_pct,
            "minimum_worst_row_mae_reduction_pct": args.minimum_worst_row_mae_reduction_pct,
            "candidate_only_runtime_gate_required": True,
            "unselected_rows_are_exact_noop": True,
        },
        "runtime_policy": {
            "allowed_runtime_inputs": [
                "candidate_raw",
                "camera_metadata",
                "candidate_hf_abs_mean",
                "candidate_tile_coordinates",
                "candidate_tile_statistics",
                "validated_noise_sidecar_optional",
            ],
            "forbidden_runtime_inputs": [
                "REF",
                "source_raw",
                "source_rgb",
                "source_hf",
                "JPEG",
                "target_mae",
                "gate_metric",
                "oracle_row_label",
            ],
        },
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=Path, action="append", default=[])
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-median-mae-reduction-pct", type=float, default=1.0)
    ap.add_argument("--minimum-worst-row-mae-reduction-pct", type=float, default=0.0)
    args = ap.parse_args()
    if not args.receipt:
        args.receipt = DEFAULT_RECEIPTS
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    json_path = args.output_dir / "objective_gate_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(json_path), "dashboard": str(html_path), "verdict": receipt["verdict"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
