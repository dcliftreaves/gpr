#!/usr/bin/env python3
"""Build a single readiness receipt for raw-stills camera-noise sidecars.

The lower-level audits intentionally answer separate questions: which
calibrated sidecars exist, what the runtime policy allows, which dark-looking
candidate stacks were found, and what still needs to be captured. This tool
combines those receipts into the product-facing answer: which camera families
may use nonzero noise removal/addback today, and exactly why Mission/iPhone may
not yet do so.
"""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_stills_noise_sidecar_readiness.v1"
DEFAULT_COVERAGE = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/noise_coverage.json"
)
DEFAULT_RUNTIME_POLICY = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_runtime_policy_20260630/camera_noise_runtime_policy.json"
)
DEFAULT_DARKFRAME_AUDIT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/darkframe_candidate_audit.json"
)
DEFAULT_GAP_PLAN = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/stills_fixture_gap_plan.json"
)
DEFAULT_CAPTURE_REQUEST = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_noise_fullmanifest_20260701/stills_capture_request.json"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    ap.add_argument("--runtime-policy", type=Path, default=DEFAULT_RUNTIME_POLICY)
    ap.add_argument("--darkframe-audit", type=Path, default=DEFAULT_DARKFRAME_AUDIT)
    ap.add_argument("--gap-plan", type=Path, default=DEFAULT_GAP_PLAN)
    ap.add_argument("--capture-request", type=Path, default=DEFAULT_CAPTURE_REQUEST)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def coverage_by_key(coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("key")): row for row in coverage.get("coverage") or []}


def policy_by_key(runtime_policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("camera_key")): row for row in runtime_policy.get("camera_policies") or []}


def request_by_requirement(capture_request: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for row in capture_request.get("requests") or []:
        requirement_id = str(row.get("requirement_id") or "")
        if requirement_id:
            rows.setdefault(requirement_id, []).append(row)
    return rows


def readiness_row(
    key: str,
    coverage_row: dict[str, Any],
    policy_row: dict[str, Any],
    gap_plan: dict[str, Any],
    requests: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    summary = gap_plan.get("summary") or {}
    nearest = (summary.get("nearest_darkframe_stack_by_noise_key") or {}).get(key) or {}
    requirement_id = {
        "mission1": "mission1_darkframe_stack",
        "iphone": "iphone_cfa_darkframe_stack",
    }.get(key)
    request_rows = requests.get(str(requirement_id), []) if requirement_id else []
    sidecar_ready = bool(coverage_row.get("ready"))
    runtime_ready = bool(policy_row.get("allow_nonzero_noise_addback"))
    production_ready = sidecar_ready and runtime_ready
    candidate_count = int(nearest.get("candidate_count") or 0)
    needed = int(nearest.get("needed_for_stack") or max(0, 4 - candidate_count))
    blocker = None
    if not production_ready:
        if candidate_count >= 4:
            blocker = (
                "candidate stack has enough dark-looking frames, but source provenance "
                "does not prove true no-scene-signal darkframes"
            )
        elif candidate_count > 0:
            blocker = (
                f"candidate stack has {candidate_count} dark-like frame(s), "
                f"needs {needed} more matching true darkframe frame(s)"
            )
        else:
            blocker = str(coverage_row.get("blocker") or policy_row.get("missing_sidecar_blocker") or "")
    return {
        "camera_key": key,
        "label": coverage_row.get("label") or policy_row.get("label") or key,
        "production_ready": production_ready,
        "sidecar_ready": sidecar_ready,
        "runtime_nonzero_noise_addback_enabled": runtime_ready,
        "runtime_mode": (policy_row.get("runtime_fallback") or {}).get("mode"),
        "ready_isos": coverage_row.get("ready_isos") or policy_row.get("ready_isos") or [],
        "requirement_id": requirement_id,
        "nearest_candidate_stack": nearest,
        "candidate_count": candidate_count,
        "needed_for_stack": needed,
        "capture_request_count": len(request_rows),
        "blocker": blocker,
    }


def build_readiness(
    coverage: dict[str, Any],
    runtime_policy: dict[str, Any],
    darkframe_audit: dict[str, Any],
    gap_plan: dict[str, Any],
    capture_request: dict[str, Any],
    sources: dict[str, Path],
) -> dict[str, Any]:
    by_coverage = coverage_by_key(coverage)
    by_policy = policy_by_key(runtime_policy)
    by_request = request_by_requirement(capture_request)
    camera_keys = sorted(set(by_coverage) | set(by_policy))
    rows = [
        readiness_row(
            key,
            by_coverage.get(key, {}),
            by_policy.get(key, {}),
            gap_plan,
            by_request,
        )
        for key in camera_keys
        if key and key != "None"
    ]
    ready = [row["camera_key"] for row in rows if row["production_ready"]]
    blocked = [row["camera_key"] for row in rows if not row["production_ready"]]
    gap_summary = gap_plan.get("summary") or {}
    dark_summary = darkframe_audit.get("summary") or {}
    cap_summary = capture_request.get("summary") or {}
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {key: value.as_posix() for key, value in sources.items()},
        "summary": {
            "camera_count": len(rows),
            "production_ready_camera_count": len(ready),
            "production_ready_camera_keys": ready,
            "blocked_camera_count": len(blocked),
            "blocked_camera_keys": blocked,
            "mission_iphone_noise_addback_enabled": all(
                row["production_ready"] for row in rows if row["camera_key"] in {"mission1", "iphone"}
            ),
            "nonzero_noise_addback_must_remain_disabled_for_blocked_cameras": bool(blocked),
            "all_real_bayer_phases_ready": bool(gap_summary.get("all_real_bayer_phases_ready")),
            "darkframe_like_count": int(dark_summary.get("darkframe_like_count") or 0),
            "production_stack_ready_group_count": int(dark_summary.get("production_stack_ready_group_count") or 0),
            "required_capture_request_count": int(cap_summary.get("required_request_count") or 0),
            "open_requirement_ids": sorted(
                {
                    str(row.get("requirement_id"))
                    for row in rows
                    if not row["production_ready"] and row.get("requirement_id")
                }
            ),
            "production_raw_stills_noise_ready": not blocked,
        },
        "camera_readiness": rows,
        "rules": [
            "Enable nonzero noise removal/addback only for camera families with production_ready camera-noise sidecars.",
            "Candidate-discovery photos, even dark-looking ones, are not calibration targets without no-scene-signal provenance.",
            "DNG NoiseProfile or ISO metadata may condition models, but does not by itself prove removable noise.",
            "Blocked camera families must remain metadata-conditioning-only until a sidecar validates.",
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    cards = [
        ("Ready cameras", f"{summary['production_ready_camera_count']} / {summary['camera_count']}"),
        ("Noise addback enabled", ", ".join(summary["production_ready_camera_keys"]) or "none"),
        ("Blocked", ", ".join(summary["blocked_camera_keys"]) or "none"),
        ("Mission/iPhone enabled", summary["mission_iphone_noise_addback_enabled"]),
        ("Open requirements", ", ".join(summary["open_requirement_ids"]) or "none"),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['label']))}</td>"
        f"<td>{'ready' if row['production_ready'] else 'blocked'}</td>"
        f"<td>{'yes' if row['runtime_nonzero_noise_addback_enabled'] else 'no'}</td>"
        f"<td>{html.escape(', '.join(str(v) for v in row.get('ready_isos') or []) or '')}</td>"
        f"<td>{html.escape(str((row.get('nearest_candidate_stack') or {}).get('key') or ''))}</td>"
        f"<td>{html.escape(str(row.get('candidate_count') or 0))}</td>"
        f"<td>{html.escape(str(row.get('needed_for_stack') or 0))}</td>"
        f"<td>{html.escape(str(row.get('blocker') or ''))}</td>"
        "</tr>"
        for row in data["camera_readiness"]
    )
    rule_items = "\n".join(f"<li>{html.escape(rule)}</li>" for rule in data["rules"])
    source_items = "\n".join(
        f"<li><code>{html.escape(label)}: {html.escape(path)}</code></li>"
        for label, path in data["sources"].items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Stills Noise Sidecar Readiness</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
section.panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; margin: 14px 0 26px; }}
code {{ white-space: normal; overflow-wrap: anywhere; }}
</style></head><body><main>
<h1>Raw Stills Noise Sidecar Readiness</h1>
<p class="sub">Schema {html.escape(data["schema"])}. This is the product-facing receipt for camera-noise removal/addback readiness across raw-stills camera families.</p>
<div class="grid">{card_html}</div>
<section class="panel"><h2>Rules</h2><ul>{rule_items}</ul></section>
<h2>Camera Readiness</h2>
<table><thead><tr><th>Camera</th><th>Status</th><th>Runtime addback</th><th>Ready ISOs</th><th>Nearest candidate stack</th><th>Candidates</th><th>Needed</th><th>Blocker</th></tr></thead><tbody>{rows}</tbody></table>
<section class="panel"><h2>Sources</h2><ul>{source_items}</ul></section>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    sources = {
        "coverage": args.coverage,
        "runtime_policy": args.runtime_policy,
        "darkframe_audit": args.darkframe_audit,
        "gap_plan": args.gap_plan,
        "capture_request": args.capture_request,
    }
    data = build_readiness(
        load_json(args.coverage),
        load_json(args.runtime_policy),
        load_json(args.darkframe_audit),
        load_json(args.gap_plan),
        load_json(args.capture_request),
        sources,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_stills_noise_sidecar_readiness.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
