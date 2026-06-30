#!/usr/bin/env python3
"""Build a non-production router plan for premium still-SR specialists.

The plan is metadata-only: it maps fixture camera/source classes to candidate
receipts and records why the routed suite is or is not ready for production.
It does not run inference and it does not promote a model.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_router_plan.v1"


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
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size if path.is_file() else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def route_key(fixture: dict[str, Any]) -> str:
    camera_key = str(fixture.get("camera_key") or "unknown")
    klass = str(fixture.get("class") or "unknown")
    extension = str(fixture.get("extension") or "unknown").lower()
    return f"{camera_key}:{klass}:{extension}"


def summarize_fixtures(manifest: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fixture in manifest.get("fixtures", []):
        if not isinstance(fixture, dict):
            continue
        if fixture.get("premium_still_sr_eligible") is not True:
            continue
        if fixture.get("source", {}).get("exists") is not True:
            continue
        grouped[route_key(fixture)].append(fixture)
    routes = []
    for key, fixtures in sorted(grouped.items()):
        cameras = sorted({str(f.get("camera") or "unknown") for f in fixtures})
        labels = sorted(str(f.get("label") or "unknown") for f in fixtures)
        noise_sidecars = sum(len(f.get("noise_sidecars", [])) for f in fixtures if isinstance(f.get("noise_sidecars"), list))
        routes.append(
            {
                "route_key": key,
                "camera_key": key.split(":")[0],
                "class": key.split(":")[1],
                "extension": key.split(":")[2],
                "fixture_count": len(fixtures),
                "cameras": cameras,
                "labels": labels,
                "noise_sidecar_ref_count": noise_sidecars,
            }
        )
    return {
        "route_count": len(routes),
        "fixture_count": sum(row["fixture_count"] for row in routes),
        "routes": routes,
    }


def candidate_from_receipt(root: Path, path: Path, candidate_id: str | None = None) -> dict[str, Any]:
    path = resolve(root, path)
    data = load_json(path)
    checkpoint = Path(str(data.get("checkpoint", "")))
    pairs = Path(str(data.get("pairs", "")))
    best = data.get("best_eval") if isinstance(data.get("best_eval"), dict) else {}
    return {
        "candidate_id": candidate_id or checkpoint.stem or path.stem,
        "receipt": artifact_ref(path),
        "checkpoint": artifact_ref(checkpoint),
        "pairs": artifact_ref(pairs),
        "architecture": data.get("architecture"),
        "width": data.get("width"),
        "depth": data.get("depth"),
        "holdout_image": data.get("holdout_image"),
        "train_tiles": data.get("train_tiles"),
        "eval_tiles": data.get("eval_tiles_total"),
        "best_step": best.get("step"),
        "rmse_improvement_pct": best.get("rmse_improvement_pct"),
        "mae_improvement_pct": best.get("mae_improvement_pct"),
        "production_ready": False,
        "blockers": [
            "candidate is tile-level only",
            "no full-frame still visual gate receipt",
            "no raw-editor latitude receipt",
            "noise-sidecar policy is not active in target construction",
        ],
    }


def parse_mapping(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--route expects route_key=candidate_id")
    key, candidate = value.split("=", 1)
    key = key.strip()
    candidate = candidate.strip()
    if not key or not candidate:
        raise argparse.ArgumentTypeError("--route expects non-empty route_key and candidate_id")
    return key, candidate


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = args.external_root
    manifest_path = resolve(root, args.fixture_manifest)
    manifest = load_json(manifest_path)
    fixture_summary = summarize_fixtures(manifest)
    candidates = [candidate_from_receipt(root, path, candidate_id=f"candidate_{idx}") for idx, path in enumerate(args.receipt)]

    aliases: dict[str, str] = {}
    for alias in args.candidate_alias or []:
        key, value = parse_mapping(alias)
        aliases[key] = value
    for idx, candidate in enumerate(candidates):
        default_id = candidate["candidate_id"]
        if default_id in aliases:
            candidate["candidate_id"] = aliases[default_id]
        elif f"candidate_{idx}" in aliases:
            candidate["candidate_id"] = aliases[f"candidate_{idx}"]

    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    route_map = dict(parse_mapping(item) for item in (args.route or []))
    default_candidate = args.default_candidate

    routes = []
    blockers: list[str] = []
    for route in fixture_summary["routes"]:
        candidate_id = route_map.get(route["route_key"], default_candidate)
        candidate = candidate_by_id.get(candidate_id) if candidate_id else None
        row = dict(route)
        row["candidate_id"] = candidate_id
        row["candidate_found"] = candidate is not None
        if candidate is not None:
            row["candidate_rmse_improvement_pct"] = candidate.get("rmse_improvement_pct")
            row["candidate_mae_improvement_pct"] = candidate.get("mae_improvement_pct")
        else:
            blockers.append(f"route {route['route_key']} has no candidate")
        routes.append(row)

    for candidate in candidates:
        if candidate.get("production_ready") is not True:
            blockers.append(f"candidate {candidate['candidate_id']} is not production-ready")
    if not routes:
        blockers.append("fixture manifest has no eligible premium still-SR routes")
    if any(not route["candidate_found"] for route in routes):
        blockers.append("one or more routes are unmapped")

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": root.as_posix(),
        "fixture_manifest": artifact_ref(manifest_path),
        "fixture_summary": fixture_summary,
        "candidates": candidates,
        "routing_policy": {
            "source": "metadata_route_key",
            "route_key": "camera_key:class:extension",
            "default_candidate": default_candidate,
            "explicit_routes": route_map,
            "routes": routes,
        },
        "production_ready": False,
        "blockers": sorted(set(blockers)),
        "next_steps": [
            "Add Mission 1 and Z8 specialist candidates or prove the shared candidate is better for those routes.",
            "Run full-frame still visual gates and raw-editor latitude checks for every routed candidate.",
            "Wire validated camera/ISO noise sidecars into target construction before production promotion.",
        ],
    }


def pct(value: Any) -> str:
    return f"{float(value):.3f}%" if isinstance(value, (int, float)) and not isinstance(value, bool) else "n/a"


def render_html(data: dict[str, Any]) -> str:
    candidate_rows = []
    for c in data["candidates"]:
        candidate_rows.append(
            "<tr>"
            f"<td>{html.escape(c['candidate_id'])}</td>"
            f"<td>{html.escape(Path(str(c['checkpoint']['path'])).name)}</td>"
            f"<td>{html.escape(str(c.get('holdout_image')))}</td>"
            f"<td>{pct(c.get('rmse_improvement_pct'))}</td>"
            f"<td>{pct(c.get('mae_improvement_pct'))}</td>"
            f"<td>{html.escape(str(c['production_ready']))}</td>"
            "</tr>"
        )
    route_rows = []
    for route in data["routing_policy"]["routes"]:
        route_rows.append(
            "<tr>"
            f"<td>{html.escape(route['route_key'])}</td>"
            f"<td>{route['fixture_count']}</td>"
            f"<td>{html.escape(str(route.get('candidate_id')))}</td>"
            f"<td>{html.escape(str(route['candidate_found']))}</td>"
            f"<td>{pct(route.get('candidate_rmse_improvement_pct'))}</td>"
            f"<td>{html.escape(', '.join(route['labels']))}</td>"
            "</tr>"
        )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Router Plan</title>
<style>
body {{ font: 14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
table {{ border-collapse: collapse; width: 100%; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f4f6f8; }}
.warn {{ display: inline-block; padding: 6px 10px; background: #fff3cd; border: 1px solid #d7a500; border-radius: 6px; }}
</style>
<h1>Premium Still-SR Router Plan</h1>
<p><span class="warn">production_ready={data["production_ready"]}</span></p>
<h2>Candidates</h2>
<table><thead><tr><th>candidate</th><th>checkpoint</th><th>holdout</th><th>RMSE improvement</th><th>MAE improvement</th><th>production</th></tr></thead><tbody>
{''.join(candidate_rows)}
</tbody></table>
<h2>Routes</h2>
<table><thead><tr><th>route</th><th>fixtures</th><th>candidate</th><th>found</th><th>candidate RMSE improvement</th><th>fixture labels</th></tr></thead><tbody>
{''.join(route_rows)}
</tbody></table>
<h2>Blockers</h2>
<ul>{blockers}</ul>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--fixture-manifest", type=Path, required=True)
    ap.add_argument("--receipt", action="append", type=Path, required=True)
    ap.add_argument("--candidate-alias", action="append", help="candidate_N=alias or checkpoint_stem=alias")
    ap.add_argument("--route", action="append", help="route_key=candidate_id, e.g. x2d:100mp:dng=x2d_specialist")
    ap.add_argument("--default-candidate")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    plan = build_plan(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "router_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(plan), encoding="utf-8")
    print(args.output_dir / "router_plan.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
