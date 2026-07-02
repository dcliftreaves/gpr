#!/usr/bin/env python3
"""Audit premium still-SR routed specialist readiness.

This is a production-closure receipt, not a trainer. It reconciles the routed
specialist plan, full-frame specialist summaries, and rejected clean-source
smoke receipts so the next premium still-SR step is explicit.
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


SCHEMA = "gpr.premium_still_sr_route_readiness.v1"
REQUIRED_ROUTES = (
    "mission1:50mp:dng",
    "mission1:50mp:gpr",
    "z8:50mp:dng",
    "x2d:100mp:dng",
)
REQUIRED_BLOCKERS = (
    "rendered/editor-latitude review is not present for every route",
    "exact-sidecar-only noise policy is not wired into every routed target",
    "50 MP and 100 MP promotion submission has not passed check_production_capture_submission.py",
)


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path),
    }


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def parse_mapping(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected route_key=path")
    key, raw_path = value.split("=", 1)
    key = key.strip()
    raw_path = raw_path.strip()
    if not key or not raw_path:
        raise argparse.ArgumentTypeError("expected non-empty route_key and path")
    return key, Path(raw_path)


def stat_value(data: dict[str, Any], key: str, stat: str = "median") -> float | None:
    section = data.get(key)
    if isinstance(section, dict) and isinstance(section.get(stat), (int, float)):
        return float(section[stat])
    if isinstance(section, (int, float)):
        return float(section)
    return None


def summarize_fullframe(root: Path, route_key: str, path: Path) -> dict[str, Any]:
    resolved = resolve(root, path)
    data = load_json(resolved)
    image_count = int(data.get("image_count") or len(data.get("images", [])))
    rmse = stat_value(data, "rmse_improvement_pct")
    mae = stat_value(data, "mae_improvement_pct")
    grad = stat_value(data, "gradient_mae_improvement_pct")
    fps = stat_value(data, "fps_with_write")
    return {
        "route_key": route_key,
        "summary": artifact_ref(resolved),
        "dashboard": data.get("dashboard"),
        "checkpoint": data.get("checkpoint"),
        "checkpoint_sha256": sha256_file(Path(str(data.get("checkpoint")))) if data.get("checkpoint") else None,
        "image_count": image_count,
        "median_rmse_improvement_pct": rmse,
        "median_mae_improvement_pct": mae,
        "median_gradient_mae_improvement_pct": grad,
        "median_fps_with_write": fps,
        "positive_fullframe_metrics": all(isinstance(v, float) and v > 0.0 for v in (rmse, mae, grad)),
    }


def summarize_smoke(root: Path, path: Path) -> dict[str, Any]:
    resolved = resolve(root, path)
    data = load_json(resolved)
    holdout = data.get("eval", {}).get("holdout", {})
    promotion = data.get("promotion", {})
    config = data.get("config", {})
    mae_stats = holdout.get("mae_improvement_pct", {}) if isinstance(holdout, dict) else {}
    rmse_stats = holdout.get("rmse_improvement_pct", {}) if isinstance(holdout, dict) else {}
    return {
        "receipt": artifact_ref(resolved),
        "dashboard": data.get("dashboard"),
        "holdout_image": data.get("holdout_image") or config.get("holdout_image"),
        "holdout_images": config.get("holdout_images"),
        "checkpoint_sha256": data.get("checkpoint_sha256"),
        "median_mae_recovery_pct": mae_stats.get("median") if isinstance(mae_stats, dict) else data.get("median_mae_recovery_pct"),
        "median_rmse_recovery_pct": rmse_stats.get("median") if isinstance(rmse_stats, dict) else data.get("median_rmse_recovery_pct"),
        "baseline_beaten_on_holdout": promotion.get("baseline_beaten_on_holdout", data.get("baseline_beaten_on_holdout")),
        "promotion_ready": promotion.get("promotion_ready", data.get("promotion_ready")),
    }


def candidate_for_route(router: dict[str, Any], route_key: str) -> str | None:
    routes = router.get("routing_policy", {}).get("routes", [])
    if not isinstance(routes, list):
        return None
    for row in routes:
        if isinstance(row, dict) and row.get("route_key") == route_key:
            candidate = row.get("candidate_id")
            return str(candidate) if candidate is not None else None
    return None


def build_readiness(args: argparse.Namespace) -> dict[str, Any]:
    root = args.external_root
    router_path = resolve(root, args.router_plan)
    router = load_json(router_path)
    fullframe = dict(parse_mapping(item) for item in args.fullframe_summary)
    fullframe_rows = {
        route: summarize_fullframe(root, route, summary_path)
        for route, summary_path in sorted(fullframe.items())
    }
    smoke_rows = [summarize_smoke(root, path) for path in args.rejected_smoke]

    route_rows: list[dict[str, Any]] = []
    blockers: list[str] = list(REQUIRED_BLOCKERS)
    for route in REQUIRED_ROUTES:
        row = {
            "route_key": route,
            "candidate_id": candidate_for_route(router, route),
            "route_in_router_plan": candidate_for_route(router, route) is not None,
            "has_fullframe_summary": route in fullframe_rows,
        }
        summary = fullframe_rows.get(route)
        if summary:
            row.update(
                {
                    "image_count": summary["image_count"],
                    "median_rmse_improvement_pct": summary["median_rmse_improvement_pct"],
                    "median_mae_improvement_pct": summary["median_mae_improvement_pct"],
                    "median_gradient_mae_improvement_pct": summary["median_gradient_mae_improvement_pct"],
                    "positive_fullframe_metrics": summary["positive_fullframe_metrics"],
                }
            )
            if not summary["positive_fullframe_metrics"]:
                blockers.append(f"{route} full-frame summary does not have positive RMSE/MAE/gradient recovery")
        else:
            blockers.append(f"{route} has no full-frame specialist summary")
        if row["candidate_id"] is None:
            blockers.append(f"{route} is missing a routed candidate")
        route_rows.append(row)

    rejected_clean_source = any(smoke.get("promotion_ready") is False for smoke in smoke_rows)
    if rejected_clean_source:
        blockers.append("clean-source split candidate is rejected for long training because a paired smoke gate failed")

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": root.as_posix(),
        "router_plan": artifact_ref(router_path),
        "required_routes": list(REQUIRED_ROUTES),
        "routes": route_rows,
        "fullframe_summaries": fullframe_rows,
        "rejected_clean_source_smokes": smoke_rows,
        "route_coverage_ready": all(row["route_in_router_plan"] and row["has_fullframe_summary"] for row in route_rows),
        "fullframe_metric_floor_ready": all(row.get("positive_fullframe_metrics") is True for row in route_rows),
        "production_ready": False,
        "blockers": sorted(set(blockers)),
        "next_unambiguous_steps": [
            "Use the routed specialist/raw-CFA path as the next premium still-SR candidate direction; do not extend the rejected clean-source split into long training.",
            "Refresh routed full-frame gates with at least the Mission 1 50 MP DNG/GPR routes, Z8 50 MP DNG route, and X2D 100 MP DNG route.",
            "Add rendered visual and editor-latitude receipts for every route.",
            "Wire exact-sidecar-only noise policy into target construction and reject any source residual noise at render time.",
            "Build a production submission and run check_production_capture_submission.py before moving Premium still/SR above 60 percent.",
        ],
    }


def fmt_pct(value: Any) -> str:
    return f"{float(value):.3f}%" if isinstance(value, (int, float)) and not isinstance(value, bool) else "n/a"


def render_html(data: dict[str, Any]) -> str:
    route_rows = []
    for row in data["routes"]:
        route_rows.append(
            "<tr>"
            f"<td>{html.escape(row['route_key'])}</td>"
            f"<td>{html.escape(str(row.get('candidate_id')))}</td>"
            f"<td>{html.escape(str(row['route_in_router_plan']))}</td>"
            f"<td>{html.escape(str(row['has_fullframe_summary']))}</td>"
            f"<td>{html.escape(str(row.get('image_count')))}</td>"
            f"<td>{fmt_pct(row.get('median_rmse_improvement_pct'))}</td>"
            f"<td>{fmt_pct(row.get('median_mae_improvement_pct'))}</td>"
            f"<td>{fmt_pct(row.get('median_gradient_mae_improvement_pct'))}</td>"
            f"<td>{html.escape(str(row.get('positive_fullframe_metrics')))}</td>"
            "</tr>"
        )
    blocker_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    next_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_unambiguous_steps"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Route Readiness</title>
<style>
body {{ font: 14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
table {{ border-collapse: collapse; width: 100%; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f4f6f8; }}
.warn {{ display: inline-block; padding: 6px 10px; background: #fff3cd; border: 1px solid #d7a500; border-radius: 6px; }}
</style>
<h1>Premium Still-SR Route Readiness</h1>
<p><span class="warn">production_ready={data["production_ready"]}</span></p>
<p>Route coverage ready: {data["route_coverage_ready"]}; full-frame metric floor ready: {data["fullframe_metric_floor_ready"]}</p>
<h2>Routes</h2>
<table><thead><tr><th>route</th><th>candidate</th><th>in router</th><th>full-frame summary</th><th>images</th><th>RMSE improvement</th><th>MAE improvement</th><th>gradient improvement</th><th>positive metrics</th></tr></thead><tbody>
{''.join(route_rows)}
</tbody></table>
<h2>Blockers</h2>
<ul>{blocker_items}</ul>
<h2>Next Steps</h2>
<ol>{next_items}</ol>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--router-plan", type=Path, required=True)
    ap.add_argument("--fullframe-summary", action="append", required=True, help="route_key=summary.json")
    ap.add_argument("--rejected-smoke", action="append", type=Path, default=[])
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    data = build_readiness(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "route_readiness.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(args.output_dir / "route_readiness.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
