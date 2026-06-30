#!/usr/bin/env python3
"""Build a scoreboard for premium still-SR experiment receipts.

The premium still-SR work has many external experiments by design. This tool
keeps promotion decisions auditable by scanning receipt JSON files, ranking the
candidate runs that have holdout metrics, and writing a compact dashboard.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_experiment_scoreboard.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
PROMOTION_HOLDOUT_MAE_REDUCTION_PCT = 15.0
PROMOTION_HOLDOUT_RMSE_REDUCTION_PCT = 15.0


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def nested_float(data: dict[str, Any], keys: list[str]) -> float | None:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return float(cur) if isinstance(cur, (int, float)) else None


def nested_value(data: dict[str, Any], keys: list[str]) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def classify_receipt(path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    schema = str(payload.get("schema", ""))
    if "premium_still_sr" not in schema:
        return None
    eval_data = payload.get("eval")
    if not isinstance(eval_data, dict):
        return None

    holdout_mae = nested_float(payload, ["eval", "holdout", "residual_mae_reduction_pct", "median"])
    holdout_rmse = nested_float(payload, ["eval", "holdout", "residual_rmse_reduction_pct", "median"])
    train_mae = nested_float(payload, ["eval", "train", "residual_mae_reduction_pct", "median"])
    train_rmse = nested_float(payload, ["eval", "train", "residual_rmse_reduction_pct", "median"])
    holdout_rows = nested_value(payload, ["eval", "holdout", "row_count"])
    train_rows = nested_value(payload, ["eval", "train", "row_count"])
    if holdout_mae is None and holdout_rmse is None and train_mae is None and train_rmse is None:
        return None

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    uses_ref_runtime = bool(policy.get("uses_source_hf_at_runtime")) if policy else None
    promotion_ready = (
        holdout_mae is not None
        and holdout_rmse is not None
        and holdout_mae >= PROMOTION_HOLDOUT_MAE_REDUCTION_PCT
        and holdout_rmse >= PROMOTION_HOLDOUT_RMSE_REDUCTION_PCT
        and uses_ref_runtime is False
    )
    return {
        "path": path.as_posix(),
        "schema": schema,
        "experiment": path.parent.name,
        "checkpoint": payload.get("checkpoint"),
        "checkpoint_sha256": payload.get("checkpoint_sha256"),
        "steps": payload.get("steps"),
        "train_seconds": payload.get("train_seconds"),
        "device": payload.get("device"),
        "model_arch": config.get("model_arch"),
        "feature_mode": config.get("feature_mode"),
        "holdout_scene": config.get("holdout_scene"),
        "holdout_crop": config.get("holdout_crop"),
        "holdout_ev": config.get("holdout_ev"),
        "train_row_count": train_rows,
        "holdout_row_count": holdout_rows,
        "train_residual_mae_reduction_pct_median": train_mae,
        "train_residual_rmse_reduction_pct_median": train_rmse,
        "holdout_residual_mae_reduction_pct_median": holdout_mae,
        "holdout_residual_rmse_reduction_pct_median": holdout_rmse,
        "uses_source_hf_at_training": policy.get("uses_source_hf_at_training"),
        "uses_source_hf_at_runtime": uses_ref_runtime,
        "production_status": policy.get("production_status"),
        "promotion_ready": promotion_ready,
    }


def score_candidate(row: dict[str, Any]) -> tuple[float, float, str]:
    holdout_mae = row.get("holdout_residual_mae_reduction_pct_median")
    holdout_rmse = row.get("holdout_residual_rmse_reduction_pct_median")
    train_mae = row.get("train_residual_mae_reduction_pct_median")
    primary = float(holdout_mae if isinstance(holdout_mae, (int, float)) else -999.0)
    secondary = float(holdout_rmse if isinstance(holdout_rmse, (int, float)) else train_mae if isinstance(train_mae, (int, float)) else -999.0)
    return (primary, secondary, str(row.get("experiment", "")))


def scan_receipts(external_root: Path) -> list[dict[str, Any]]:
    artifact_root = external_root / "artifacts"
    receipts: list[dict[str, Any]] = []
    if not artifact_root.exists():
        return receipts
    for path in sorted(artifact_root.glob("premium_still_sr*/**/train_receipt.json")):
        payload = load_json(path)
        if not payload:
            continue
        row = classify_receipt(path, payload)
        if row:
            receipts.append(row)
    return sorted(receipts, key=score_candidate, reverse=True)


def build_scoreboard(external_root: Path) -> dict[str, Any]:
    rows = scan_receipts(external_root)
    best = rows[0] if rows else None
    promotable = [row for row in rows if row["promotion_ready"]]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "receipt_count": len(rows),
        "promotion_thresholds": {
            "holdout_residual_mae_reduction_pct_median": PROMOTION_HOLDOUT_MAE_REDUCTION_PCT,
            "holdout_residual_rmse_reduction_pct_median": PROMOTION_HOLDOUT_RMSE_REDUCTION_PCT,
            "uses_source_hf_at_runtime": False,
        },
        "best_candidate": best,
        "promotable_candidate_count": len(promotable),
        "production_ready": bool(promotable),
        "interpretation": (
            "This scoreboard ranks premium still-SR training receipts only. A promotable row here is necessary "
            "but still not sufficient for production; full-frame/editor-latitude gates must also pass."
        ),
        "experiments": rows,
    }


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return ""
    return str(value)


def render_html(scoreboard: dict[str, Any]) -> str:
    rows = []
    for row in scoreboard["experiments"]:
        klass = "ready" if row["promotion_ready"] else "blocked"
        rows.append(
            "<tr class='" + klass + "'>"
            f"<td>{html.escape(str(row['experiment']))}</td>"
            f"<td>{html.escape(str(row.get('model_arch') or ''))}</td>"
            f"<td>{html.escape(fmt(row.get('holdout_residual_mae_reduction_pct_median')))}</td>"
            f"<td>{html.escape(fmt(row.get('holdout_residual_rmse_reduction_pct_median')))}</td>"
            f"<td>{html.escape(fmt(row.get('train_residual_mae_reduction_pct_median')))}</td>"
            f"<td>{html.escape(str(row.get('holdout_row_count') or ''))}</td>"
            f"<td>{html.escape(str(row.get('uses_source_hf_at_runtime')))}</td>"
            f"<td>{html.escape(str(row.get('promotion_ready')))}</td>"
            f"<td><a href='file://{html.escape(row['path'])}'>receipt</a></td>"
            "</tr>"
        )
    best = scoreboard.get("best_candidate") or {}
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Experiment Scoreboard</title>
  <style>
    body {{ margin: 28px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; }}
    h1 {{ margin-bottom: 4px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ border: 1px solid #d8dde3; border-radius: 8px; padding: 14px; background: #fafbfc; }}
    .metric {{ font-size: 30px; font-weight: 760; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f4f6; }}
    tr.ready td {{ background: #edf8f0; }}
    tr.blocked td {{ background: #fff; }}
    code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Premium Still-SR Experiment Scoreboard</h1>
  <p>{html.escape(scoreboard['interpretation'])}</p>
  <div class="cards">
    <div class="card"><div>Receipts</div><div class="metric">{scoreboard['receipt_count']}</div></div>
    <div class="card"><div>Promotable rows</div><div class="metric">{scoreboard['promotable_candidate_count']}</div></div>
    <div class="card"><div>Best holdout MAE recovery</div><div class="metric">{html.escape(fmt(best.get('holdout_residual_mae_reduction_pct_median')))}%</div></div>
    <div class="card"><div>Best experiment</div><code>{html.escape(str(best.get('experiment', 'none')))}</code></div>
  </div>
  <table>
    <thead><tr><th>Experiment</th><th>Model</th><th>Holdout MAE %</th><th>Holdout RMSE %</th><th>Train MAE %</th><th>Holdout rows</th><th>Uses source HF at runtime</th><th>Promotion row</th><th>Receipt</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    scoreboard = build_scoreboard(args.external_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "scoreboard.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(scoreboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(scoreboard), encoding="utf-8")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
