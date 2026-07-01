#!/usr/bin/env python3
"""Build a scoreboard for raw-video SR/detail candidate decisions.

The raw-video improvement pillar has many historical Mission/Z8 detail and SR
experiments. This tool scans their decision receipts, extracts comparable
baseline-vs-candidate holdout metrics when present, and keeps the PSF/SR
promotion state auditable.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_video_sr_candidate_scoreboard.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def as_num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def get_obj(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur if isinstance(cur, dict) else None


def first_obj(data: dict[str, Any], paths: list[tuple[str, ...]]) -> dict[str, Any] | None:
    for path in paths:
        obj = get_obj(data, *path)
        if obj:
            return obj
    return None


def metric(obj: dict[str, Any] | None, *names: str) -> float | None:
    if not obj:
        return None
    for name in names:
        value = as_num(obj.get(name))
        if value is not None:
            return value
    return None


def delta(candidate: float | None, baseline: float | None) -> float | None:
    return candidate - baseline if candidate is not None and baseline is not None else None


def extract_holdout_pair(data: dict[str, Any], key: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if key == "mission":
        candidate_paths = [
            ("candidate", "mission_holdout"),
            ("candidate", "mission42"),
            ("candidate_step400", "mission42"),
        ]
        baseline_paths = [
            ("baseline", "mission_holdout"),
            ("baseline", "mission42"),
            ("baseline_step200", "mission42"),
        ]
    else:
        candidate_paths = [
            ("candidate", "z8_regenerated_holdout"),
            ("candidate", "z8_all24"),
            ("candidate_step400", "z8_all24"),
        ]
        baseline_paths = [
            ("baseline", "z8_regenerated_holdout"),
            ("baseline", "z8_all24"),
            ("baseline_step200", "z8_all24"),
        ]
    return first_obj(data, candidate_paths), first_obj(data, baseline_paths)


def summarize_pair(candidate: dict[str, Any] | None, baseline: dict[str, Any] | None) -> dict[str, Any]:
    cand_rmse_min = metric(candidate, "rmse_improvement_min", "rmse_lift_min")
    base_rmse_min = metric(baseline, "rmse_improvement_min", "rmse_lift_min")
    cand_rmse_med = metric(candidate, "rmse_improvement_median", "rmse_lift_median")
    base_rmse_med = metric(baseline, "rmse_improvement_median", "rmse_lift_median")
    cand_grad_min = metric(candidate, "gradient_improvement_min", "gradient_lift_min")
    base_grad_min = metric(baseline, "gradient_improvement_min", "gradient_lift_min")
    cand_mae_min = metric(candidate, "mae_improvement_min", "mae_lift_min")
    base_mae_min = metric(baseline, "mae_improvement_min", "mae_lift_min")
    return {
        "candidate_image_count": int(metric(candidate, "image_count") or 0),
        "baseline_image_count": int(metric(baseline, "image_count") or 0),
        "candidate_dashboard": candidate.get("dashboard") if candidate else None,
        "candidate_summary": candidate.get("path") if candidate else None,
        "baseline_summary": baseline.get("path") if baseline else None,
        "candidate_rmse_min": cand_rmse_min,
        "baseline_rmse_min": base_rmse_min,
        "delta_rmse_min": delta(cand_rmse_min, base_rmse_min),
        "candidate_rmse_median": cand_rmse_med,
        "baseline_rmse_median": base_rmse_med,
        "delta_rmse_median": delta(cand_rmse_med, base_rmse_med),
        "candidate_gradient_min": cand_grad_min,
        "baseline_gradient_min": base_grad_min,
        "delta_gradient_min": delta(cand_grad_min, base_grad_min),
        "candidate_mae_min": cand_mae_min,
        "baseline_mae_min": base_mae_min,
        "delta_mae_min": delta(cand_mae_min, base_mae_min),
    }


def has_useful_pair(summary: dict[str, Any]) -> bool:
    return any(summary.get(key) is not None for key in ("delta_rmse_min", "delta_rmse_median", "delta_gradient_min", "delta_mae_min"))


def classify_decision(path: Path, data: dict[str, Any]) -> dict[str, Any] | None:
    text = json.dumps(data).lower()
    if "mission" not in text and "z8" not in text:
        return None
    mission_candidate, mission_baseline = extract_holdout_pair(data, "mission")
    z8_candidate, z8_baseline = extract_holdout_pair(data, "z8")
    mission = summarize_pair(mission_candidate, mission_baseline)
    z8 = summarize_pair(z8_candidate, z8_baseline)
    if not has_useful_pair(mission) and not has_useful_pair(z8):
        return None
    decision = str(data.get("decision") or data.get("best_label") or "unknown")
    reason = str(data.get("reason") or data.get("decision_reason") or "")
    candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
    candidate_label = str(candidate.get("description") or candidate.get("pipeline_id") or path.parent.name)
    checkpoint_sha = candidate.get("checkpoint_sha256") or data.get("checkpoint_sha256")
    mission_ok = (
        mission.get("candidate_image_count", 0) >= 42
        and (mission.get("delta_rmse_min") or -999.0) >= 0.0
        and (mission.get("delta_gradient_min") or -999.0) >= 0.0
    )
    z8_ok = (
        z8.get("candidate_image_count", 0) >= 24
        and (z8.get("delta_rmse_min") or -999.0) >= 0.0
        and (z8.get("delta_gradient_min") or -999.0) >= 0.0
    )
    explicit_reject = decision.lower().startswith("reject") or "reject" in reason.lower()
    promotable_row = mission_ok and z8_ok and not explicit_reject
    return {
        "path": path.as_posix(),
        "schema": data.get("schema"),
        "experiment": path.parent.name,
        "decision": decision,
        "reason": reason,
        "candidate_label": candidate_label,
        "checkpoint_sha256": checkpoint_sha,
        "mission": mission,
        "z8": z8,
        "mission_ok": mission_ok,
        "z8_ok": z8_ok,
        "explicit_reject": explicit_reject,
        "promotable_row": promotable_row,
    }


def score_row(row: dict[str, Any]) -> tuple[float, float, float, float, float, str]:
    mission = row["mission"]
    z8 = row["z8"]
    return (
        1.0 if row["promotable_row"] else 0.0,
        1.0 if not row["explicit_reject"] else 0.0,
        float(row["mission_ok"]) + float(row["z8_ok"]),
        float(mission.get("delta_rmse_min") or -999.0),
        float(z8.get("delta_rmse_min") or -999.0),
        float(mission.get("delta_gradient_min") or -999.0),
        str(row["experiment"]),
    )


def scan(external_root: Path) -> list[dict[str, Any]]:
    artifact_root = external_root / "artifacts"
    rows: list[dict[str, Any]] = []
    if not artifact_root.exists():
        return rows
    patterns = ["current_goal_sr*/**/*decision*.json", "current_goal_cnn*/**/*decision*.json"]
    seen: set[Path] = set()
    for pattern in patterns:
        for path in artifact_root.glob(pattern):
            if path in seen:
                continue
            seen.add(path)
            data = load_json(path)
            if not data:
                continue
            row = classify_decision(path, data)
            if row:
                rows.append(row)
    return sorted(rows, key=score_row, reverse=True)


def build_scoreboard(external_root: Path) -> dict[str, Any]:
    rows = scan(external_root)
    promotable = [row for row in rows if row["promotable_row"]]
    non_rejected = [row for row in rows if not row["explicit_reject"]]
    mission_ok = [row for row in rows if row["mission_ok"]]
    z8_ok = [row for row in rows if row["z8_ok"]]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "decision_count": len(rows),
        "promotable_row_count": len(promotable),
        "non_rejected_row_count": len(non_rejected),
        "mission_ok_row_count": len(mission_ok),
        "z8_ok_row_count": len(z8_ok),
        "production_ready": False,
        "best_candidate": rows[0] if rows else None,
        "best_promotable_candidate": promotable[0] if promotable else None,
        "best_non_rejected_candidate": non_rejected[0] if non_rejected else None,
        "interpretation": (
            "This ranks historical SR/detail decisions with promotable rows first, then non-rejected "
            "diagnostic rows, then explicit rejects. A row can be useful evidence, but PSF production "
            "promotion still requires native PSF receipt, current Mission42/Z8 gates, packaging, timing, "
            "memory, and visual signoff."
        ),
        "rows": rows,
    }


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return ""
    return str(value)


def render_html(scoreboard: dict[str, Any]) -> str:
    table_rows = []
    for row in scoreboard["rows"]:
        mission = row["mission"]
        z8 = row["z8"]
        klass = "ready" if row["promotable_row"] else "blocked"
        table_rows.append(
            f"<tr class='{klass}'>"
            f"<td>{html.escape(row['experiment'])}</td>"
            f"<td>{html.escape(row['decision'])}</td>"
            f"<td>{html.escape(fmt(mission.get('delta_rmse_min')))}</td>"
            f"<td>{html.escape(fmt(mission.get('delta_gradient_min')))}</td>"
            f"<td>{html.escape(fmt(z8.get('delta_rmse_min')))}</td>"
            f"<td>{html.escape(fmt(z8.get('delta_gradient_min')))}</td>"
            f"<td>{html.escape(str(row['explicit_reject']))}</td>"
            f"<td>{html.escape(str(row['promotable_row']))}</td>"
            f"<td><a href='file://{html.escape(row['path'])}'>decision</a></td>"
            "</tr>"
        )
    best = scoreboard.get("best_candidate") or {}
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Raw Video SR Candidate Scoreboard</title>
  <style>
    body {{ margin: 28px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f6f8fa; }}
    h1 {{ margin-bottom: 4px; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:18px 0; }}
    .card {{ background:white; border:1px solid #d8e0e6; border-radius:8px; padding:14px; }}
    .metric {{ font-size:30px; font-weight:760; }}
    table {{ width:100%; border-collapse:collapse; background:white; border:1px solid #d8e0e6; }}
    th,td {{ border-bottom:1px solid #e4e9ed; padding:8px; text-align:left; vertical-align:top; }}
    th {{ background:#eef2f5; font-size:12px; text-transform:uppercase; color:#52606d; }}
    tr.ready td {{ background:#edf8f0; }}
    code {{ font-size:12px; }}
  </style>
</head>
<body>
  <h1>Raw Video SR Candidate Scoreboard</h1>
  <p>{html.escape(scoreboard['interpretation'])}</p>
  <div class="cards">
    <div class="card"><div>Decision receipts</div><div class="metric">{scoreboard['decision_count']}</div></div>
    <div class="card"><div>Promotable rows</div><div class="metric">{scoreboard['promotable_row_count']}</div></div>
    <div class="card"><div>Non-rejected rows</div><div class="metric">{scoreboard['non_rejected_row_count']}</div></div>
    <div class="card"><div>Production ready</div><div class="metric">{str(scoreboard['production_ready']).lower()}</div></div>
    <div class="card"><div>Top ranked experiment</div><code>{html.escape(str(best.get('experiment', 'none')))}</code></div>
  </div>
  <table>
    <thead><tr><th>Experiment</th><th>Decision</th><th>Mission dRMSE min</th><th>Mission dGrad min</th><th>Z8 dRMSE min</th><th>Z8 dGrad min</th><th>Explicit reject</th><th>Promotion row</th><th>Receipt</th></tr></thead>
    <tbody>{''.join(table_rows)}</tbody>
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
