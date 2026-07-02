#!/usr/bin/env python3
"""Build the Gate 13 Premium still-SR degradation/source upgrade audit.

Gate 12 proved that the current synthetic known-degradation teacher is not
safe enough for a long run: X2D has a small negative median and a negative
worst row, while Z8 exact no-op is safe. Gate 13 scans the existing clean-source
and teacher receipts to decide whether any current source already clears the
source-smoke floor, or whether the next work must change the degradation source
or add a tail-safe no-op gate before another candidate intake.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate13_degradation_source_upgrade.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_GATE12_ACCEPTANCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_gate12_smoke_acceptance_20260702"
    / "smoke_gate_acceptance.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ARTIFACT_ROOT / "premium_still_sr_gate13_degradation_source_upgrade_20260702"
RECEIPT_SCHEMAS = {
    "gpr.premium_still_sr_clean_source_pair_model.v1",
    "gpr.premium_still_sr_exact_noop_smoke.v1",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def as_float(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def holdout_text(receipt: dict[str, Any]) -> str:
    config = receipt.get("config") if isinstance(receipt.get("config"), dict) else {}
    holdouts = as_list(config.get("holdout_images") or config.get("holdout"))
    if not holdouts:
        holdouts = as_list(nested(receipt, ["eval", "holdout", "rows", 0, "image_id"]))
    return ",".join(holdouts).lower()


def camera_from_holdout(text: str) -> str:
    lower = text.lower()
    if "x2d" in lower:
        return "x2d"
    if "z8" in lower or "z8z" in lower:
        return "z8"
    return "unknown"


def receipt_summary(path: Path, artifact_root: Path) -> dict[str, Any] | None:
    try:
        data = load_json(path)
    except Exception:
        return None
    schema = str(data.get("schema") or "")
    if schema not in RECEIPT_SCHEMAS:
        return None
    eval_holdout = nested(data, ["eval", "holdout"], {})
    if not isinstance(eval_holdout, dict):
        eval_holdout = {}
    mae = eval_holdout.get("mae_improvement_pct") if isinstance(eval_holdout.get("mae_improvement_pct"), dict) else {}
    rmse = eval_holdout.get("rmse_improvement_pct") if isinstance(eval_holdout.get("rmse_improvement_pct"), dict) else {}
    promotion = data.get("promotion") if isinstance(data.get("promotion"), dict) else {}
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    holdout = holdout_text(data)
    camera = camera_from_holdout(holdout)
    rel = path
    try:
        rel = path.relative_to(artifact_root)
    except ValueError:
        pass
    exact_noop = (
        schema == "gpr.premium_still_sr_exact_noop_smoke.v1"
        and data.get("mode") == "exact-noop"
        and as_float(mae.get("median"), 0.0) == 0.0
        and as_float(mae.get("min"), 0.0) == 0.0
    )
    return {
        "name": path.parent.name,
        "path": str(path),
        "artifact_relative_path": str(rel),
        "sha256": sha256_file(path),
        "schema": schema,
        "camera": camera,
        "holdout": holdout,
        "model_arch": config.get("model_arch"),
        "steps": config.get("steps"),
        "pairs": data.get("pairs"),
        "pairs_sha256": data.get("pairs_sha256"),
        "median_mae_improvement_pct": as_float(mae.get("median")),
        "worst_row_mae_improvement_pct": as_float(mae.get("min")),
        "median_rmse_improvement_pct": as_float(rmse.get("median")),
        "worst_row_rmse_improvement_pct": as_float(rmse.get("min")),
        "holdout_count": mae.get("count") or eval_holdout.get("row_count"),
        "baseline": promotion.get("baseline"),
        "baseline_beaten_on_holdout": bool(promotion.get("baseline_beaten_on_holdout")),
        "promotion_ready": bool(promotion.get("promotion_ready")),
        "exact_noop": exact_noop,
    }


def passes_x2d_source(row: dict[str, Any], minimum_median: float, minimum_worst: float) -> bool:
    median_mae = as_float(row.get("median_mae_improvement_pct"), -1e9)
    worst_mae = as_float(row.get("worst_row_mae_improvement_pct"), -1e9)
    return (
        row.get("camera") == "x2d"
        and row.get("baseline_beaten_on_holdout") is True
        and median_mae is not None
        and worst_mae is not None
        and median_mae > minimum_median
        and worst_mae >= minimum_worst
    )


def gate12_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    rows = {}
    for row in data.get("rows", []):
        if isinstance(row, dict):
            key = str(row.get("holdout") or "").lower()
            if key:
                rows[key] = row
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "candidate_id": data.get("candidate_id"),
        "verdict": data.get("verdict"),
        "smoke_gate_passed": bool(data.get("smoke_gate_passed")),
        "long_run_allowed": bool(data.get("long_run_allowed")),
        "failures": data.get("failures", []),
        "x2d": rows.get("x2d", {}),
        "z8": rows.get("z8", {}),
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    gate12 = gate12_summary(args.gate12_acceptance)
    receipt_paths = sorted(args.artifact_root.glob(args.receipt_glob))
    receipts = []
    for path in receipt_paths:
        summary = receipt_summary(path, args.artifact_root)
        if summary is not None:
            receipts.append(summary)

    x2d_receipts = [row for row in receipts if row["camera"] == "x2d"]
    z8_receipts = [row for row in receipts if row["camera"] == "z8"]
    pass_rows = [
        row
        for row in x2d_receipts
        if passes_x2d_source(row, args.minimum_median_mae_improvement_pct, args.minimum_worst_row_mae_improvement_pct)
    ]
    best_median = max(
        x2d_receipts,
        key=lambda row: as_float(row.get("median_mae_improvement_pct"), -1e9) or -1e9,
        default=None,
    )
    best_worst = max(
        x2d_receipts,
        key=lambda row: as_float(row.get("worst_row_mae_improvement_pct"), -1e9) or -1e9,
        default=None,
    )
    positive_median_rows = [
        row
        for row in x2d_receipts
        if (as_float(row.get("median_mae_improvement_pct"), -1e9) or -1e9)
        > args.minimum_median_mae_improvement_pct
        and row.get("baseline_beaten_on_holdout") is True
    ]
    z8_exact_noop_ok = bool(nested(gate12, ["z8", "exact_noop"], False)) and bool(nested(gate12, ["z8", "passed"], False))

    source_upgrade_passed = bool(pass_rows) and z8_exact_noop_ok
    if source_upgrade_passed:
        blocker = "none"
        verdict = "gate13_source_upgrade_passed"
        next_action = "Build a new candidate preflight from the passing Gate 13 source and keep Z8 exact-noop unless new Z8 source evidence appears."
    elif positive_median_rows:
        blocker = "objective_gating_tail_regression"
        verdict = "blocked_tail_safe_noop_gate_required"
        next_action = (
            "Use the best positive X2D source only behind a tail-safe no-op gate: "
            "the next smoke must preserve the median gain and make worst-row MAE nonnegative before any long run."
        )
    elif x2d_receipts:
        blocker = "source_degradation_mismatch"
        verdict = "blocked_source_degradation_upgrade_required"
        next_action = (
            "Replace the X2D degradation/teacher source; current source receipts do not produce a positive baseline-beaten smoke."
        )
    else:
        blocker = "missing_source_receipts"
        verdict = "blocked_missing_source_receipts"
        next_action = "Generate at least one X2D source/teacher smoke receipt before candidate intake."

    median_values = [
        as_float(row.get("median_mae_improvement_pct"))
        for row in x2d_receipts
        if as_float(row.get("median_mae_improvement_pct")) is not None
    ]
    worst_values = [
        as_float(row.get("worst_row_mae_improvement_pct"))
        for row in x2d_receipts
        if as_float(row.get("worst_row_mae_improvement_pct")) is not None
    ]
    top_x2d = sorted(
        x2d_receipts,
        key=lambda row: as_float(row.get("median_mae_improvement_pct"), -1e9) or -1e9,
        reverse=True,
    )[: args.max_rows]
    top_z8 = sorted(
        z8_receipts,
        key=lambda row: as_float(row.get("median_mae_improvement_pct"), -1e9) or -1e9,
        reverse=True,
    )[: args.max_rows]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "production_ready": False,
        "long_run_allowed": False,
        "gate14_candidate_intake_allowed": bool(source_upgrade_passed),
        "source_upgrade_passed": bool(source_upgrade_passed),
        "blocker_classification": blocker,
        "next_unambiguous_action": next_action,
        "acceptance": {
            "x2d_minimum_median_mae_improvement_pct": args.minimum_median_mae_improvement_pct,
            "x2d_minimum_worst_row_mae_improvement_pct": args.minimum_worst_row_mae_improvement_pct,
            "x2d_requires_baseline_beaten_on_holdout": True,
            "z8_requires_exact_noop_until_new_source_evidence": True,
        },
        "inputs": {
            "gate12_acceptance": {
                "path": str(args.gate12_acceptance),
                "sha256": gate12["sha256"],
            },
            "artifact_root": str(args.artifact_root),
            "receipt_glob": args.receipt_glob,
            "receipt_count": len(receipts),
            "x2d_receipt_count": len(x2d_receipts),
            "z8_receipt_count": len(z8_receipts),
        },
        "gate12": gate12,
        "summary": {
            "passing_x2d_source_receipt_count": len(pass_rows),
            "positive_median_x2d_source_receipt_count": len(positive_median_rows),
            "x2d_median_mae_improvement_pct_median": median([v for v in median_values if v is not None]),
            "x2d_worst_row_mae_improvement_pct_median": median([v for v in worst_values if v is not None]),
            "z8_exact_noop_ok": z8_exact_noop_ok,
            "best_x2d_by_median": best_median,
            "best_x2d_by_worst_row": best_worst,
        },
        "passing_x2d_sources": pass_rows,
        "top_x2d_sources_by_median": top_x2d,
        "top_z8_sources_by_median": top_z8,
        "forbidden_next_work": [
            "Gate 12 synthetic teacher smoke rerun without a new source or tail-safe no-op gate",
            "long training from any receipt whose worst-row MAE is negative",
            "positive Z8 residual training from the current noise-floor rows",
            "source-minus-candidate raw-HF residual targets",
            "JPEG/REF/source-content targets at render time",
        ],
        "required_next_receipts": [
            {
                "id": "premium_still_sr_gate13_tail_safe_source_smoke_<date>",
                "required_if": "blocker_classification == objective_gating_tail_regression",
                "done_when": "X2D median MAE remains >0.001%, worst-row MAE >=0%, baseline_beaten_on_holdout=true, and Z8 exact-noop remains zero-regression.",
            },
            {
                "id": "premium_still_sr_gate13_degradation_source_replacement_<date>",
                "required_if": "blocker_classification == source_degradation_mismatch",
                "done_when": "The replacement source produces a positive X2D source/teacher smoke without REF/JPEG/source content at runtime.",
            },
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return html.escape(f"{value:.6g}")
        return html.escape(str(value))

    def rows(items: list[dict[str, Any]]) -> str:
        body = []
        for item in items:
            body.append(
                "<tr>"
                f"<td>{cell(item.get('name'))}</td>"
                f"<td>{cell(item.get('camera'))}</td>"
                f"<td>{cell(item.get('model_arch'))}</td>"
                f"<td>{cell(item.get('median_mae_improvement_pct'))}</td>"
                f"<td>{cell(item.get('worst_row_mae_improvement_pct'))}</td>"
                f"<td>{cell(item.get('median_rmse_improvement_pct'))}</td>"
                f"<td>{cell(item.get('baseline_beaten_on_holdout'))}</td>"
                f"<td>{cell(item.get('steps'))}</td>"
                "</tr>"
            )
        return "\n".join(body)

    best = data["summary"].get("best_x2d_by_median") or {}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Premium Still-SR Gate 13 Degradation Source Upgrade</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#17202a;background:#f7f8fa}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:14px}}
.label{{font-size:12px;text-transform:uppercase;color:#667085;letter-spacing:.04em}}
.value{{font-size:22px;font-weight:700;margin-top:4px}}
table{{border-collapse:collapse;width:100%;background:#fff;margin-top:12px}}
th,td{{border:1px solid #d9dee7;padding:8px;text-align:left;font-size:13px}}
th{{background:#eef2f7}}
code{{background:#eef2f7;padding:2px 4px;border-radius:4px}}
</style></head><body>
<h1>Premium Still-SR Gate 13 Degradation Source Upgrade</h1>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{cell(data['verdict'])}</div></section>
  <section class="card"><div class="label">Blocker</div><div class="value">{cell(data['blocker_classification'])}</div></section>
  <section class="card"><div class="label">Gate 14 intake allowed</div><div class="value">{cell(data['gate14_candidate_intake_allowed'])}</div></section>
  <section class="card"><div class="label">X2D receipts scanned</div><div class="value">{cell(data['inputs']['x2d_receipt_count'])}</div></section>
</div>
<h2>Current Decision</h2>
<p>{html.escape(data['next_unambiguous_action'])}</p>
<h2>Best X2D Source By Median</h2>
<p><code>{cell(best.get('artifact_relative_path'))}</code></p>
<table><thead><tr><th>Name</th><th>Camera</th><th>Arch</th><th>Median MAE %</th><th>Worst MAE %</th><th>Median RMSE %</th><th>Baseline beaten</th><th>Steps</th></tr></thead>
<tbody>{rows(data['top_x2d_sources_by_median'])}</tbody></table>
<h2>Top Z8 Evidence</h2>
<table><thead><tr><th>Name</th><th>Camera</th><th>Arch</th><th>Median MAE %</th><th>Worst MAE %</th><th>Median RMSE %</th><th>Baseline beaten</th><th>Steps</th></tr></thead>
<tbody>{rows(data['top_z8_sources_by_median'])}</tbody></table>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate12-acceptance", type=Path, default=DEFAULT_GATE12_ACCEPTANCE)
    ap.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    ap.add_argument("--receipt-glob", default="premium_still_sr*/train_receipt.json")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-median-mae-improvement-pct", type=float, default=0.001)
    ap.add_argument("--minimum-worst-row-mae-improvement-pct", type=float, default=0.0)
    ap.add_argument("--max-rows", type=int, default=12)
    args = ap.parse_args()

    data = build_audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "gate13_degradation_source_upgrade.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
