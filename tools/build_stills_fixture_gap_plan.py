#!/usr/bin/env python3
"""Build a closure plan for the remaining raw-stills fixture gaps.

This tool does not discover new files. It consumes the current Bayer phase,
darkframe-candidate, and camera-noise coverage receipts and turns them into a
small machine-readable capture/checklist artifact.
"""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.stills_fixture_gap_plan.v1"
DEFAULT_BAYER_INVENTORY = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/inventory.json"
)
DEFAULT_DARKFRAME_AUDIT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_broad_20260701/darkframe_candidate_audit.json"
)
DEFAULT_NOISE_COVERAGE = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/noise_coverage.json"
)
NORMAL_BAYER_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR")
REQUIREMENT_BY_PHASE = {
    "GRBG": "real_grbg_fixture",
    "BGGR": "real_bggr_fixture",
}
REQUIREMENT_BY_NOISE_KEY = {
    "mission1": "mission1_darkframe_stack",
    "iphone": "iphone_cfa_darkframe_stack",
}
NOISE_STACK_MATCHERS = {
    "mission1": ("mission 1",),
    "iphone": ("iphone",),
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--bayer-inventory",
        type=Path,
        action="append",
        default=None,
        help="Bayer phase inventory JSON. Repeat to union evidence across scans.",
    )
    ap.add_argument("--darkframe-audit", type=Path, default=DEFAULT_DARKFRAME_AUDIT)
    ap.add_argument("--noise-coverage", type=Path, default=DEFAULT_NOISE_COVERAGE)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def sorted_stack_groups(darkframe_audit: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for group in darkframe_audit.get("stack_groups") or []:
        count = int(group.get("candidate_count") or 0)
        groups.append(
            {
                "key": group.get("key"),
                "candidate_count": count,
                "needed_for_stack": max(0, 4 - count),
                "production_stack_ready": bool(group.get("production_stack_ready")),
                "paths": list(group.get("paths") or []),
            }
        )
    return sorted(groups, key=lambda row: (-int(row["candidate_count"]), str(row.get("key") or "")))


def stack_matches_noise_key(stack_key: str, noise_key: str) -> bool:
    lowered = stack_key.lower()
    return any(token in lowered for token in NOISE_STACK_MATCHERS.get(noise_key, (noise_key,)))


def nearest_stack_by_noise_key(stack_groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nearest: dict[str, dict[str, Any]] = {}
    for noise_key in REQUIREMENT_BY_NOISE_KEY:
        matches = [row for row in stack_groups if stack_matches_noise_key(str(row.get("key") or ""), noise_key)]
        if matches:
            nearest[noise_key] = matches[0]
    return nearest


def build_plan(
    bayer_inventories: list[dict[str, Any]],
    darkframe_audit: dict[str, Any],
    noise_coverage: dict[str, Any],
    sources: dict[str, Any],
) -> dict[str, Any]:
    noise_summary = noise_coverage.get("summary") or {}
    phase_counts = dict.fromkeys(NORMAL_BAYER_PHASES, 0)
    for inventory in bayer_inventories:
        bayer_summary = inventory.get("summary") or {}
        for phase in NORMAL_BAYER_PHASES:
            phase_counts[phase] += int((bayer_summary.get("phase_counts") or {}).get(phase) or 0)
    missing_phases = [phase for phase, count in phase_counts.items() if count <= 0]

    coverage_rows = noise_coverage.get("coverage") or []
    missing_noise = [
        {
            "key": row.get("key"),
            "label": row.get("label"),
            "blocker": row.get("blocker"),
            "fixture_status": row.get("fixture_status"),
        }
        for row in coverage_rows
        if not row.get("ready")
    ]
    ready_noise = [
        {
            "key": row.get("key"),
            "label": row.get("label"),
            "ready_isos": row.get("ready_isos") or [],
        }
        for row in coverage_rows
        if row.get("ready")
    ]
    stack_groups = sorted_stack_groups(darkframe_audit)
    nearest_stack = stack_groups[0] if stack_groups else None
    nearest_by_noise_key = nearest_stack_by_noise_key(stack_groups)

    capture_actions: list[dict[str, Any]] = []
    for phase in missing_phases:
        capture_actions.append(
            {
                "requirement_id": REQUIREMENT_BY_PHASE.get(phase),
                "priority": "required",
                "pillar": "raw_stills",
                "action": f"Add at least one real camera fixture with {phase} CFA phase",
                "why": "Synthetic conformance covers the phase, but broad production claims need real metadata, black/white levels, and openability evidence.",
                "done_when": f"Bayer phase inventory reports {phase} present from a real parsed fixture.",
            }
        )
    for row in missing_noise:
        key = str(row.get("key") or "")
        capture_actions.append(
            {
                "requirement_id": REQUIREMENT_BY_NOISE_KEY.get(key),
                "priority": "required",
                "pillar": "raw_stills_noise",
                "action": f"Capture or locate a four-frame same-camera/ISO darkframe stack for {row.get('label')}",
                "why": row.get("blocker") or "missing validated noise sidecar",
                "done_when": "camera-noise coverage audit marks this camera family ready with a production_ready sidecar.",
            }
        )
    for row in missing_noise:
        key = str(row.get("key") or "")
        nearest_for_key = nearest_by_noise_key.get(key)
        if not nearest_for_key:
            continue
        label = row.get("label") or key
        capture_actions.append(
            {
                "requirement_id": REQUIREMENT_BY_NOISE_KEY.get(key),
                "priority": "lowest_lift",
                "pillar": "raw_stills_noise",
                "action": (
                    f"Validate or top up {label} darkframe group {nearest_for_key.get('key')} "
                    f"with {nearest_for_key['needed_for_stack']} more matching frame(s)"
                ),
                "why": (
                    f"Current audit already has {nearest_for_key['candidate_count']} darkframe-like "
                    "candidate(s) in that camera family. Candidate-discovery scene frames still need "
                    "confirmed no-scene-signal provenance before promotion."
                ),
                "done_when": (
                    "darkframe candidate audit reports production_stack_ready=true for the group, "
                    "then sidecar builder emits gpr.camera_noise_calibration.v1."
                ),
            }
        )

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {
            key: [item.as_posix() for item in value] if isinstance(value, list) else value.as_posix()
            for key, value in sources.items()
        },
        "summary": {
            "all_real_bayer_phases_ready": not missing_phases,
            "phase_counts": phase_counts,
            "missing_real_bayer_phases": missing_phases,
            "missing_real_bayer_phase_requirement_ids": [
                REQUIREMENT_BY_PHASE[phase] for phase in missing_phases if phase in REQUIREMENT_BY_PHASE
            ],
            "noise_ready_camera_count": int(noise_summary.get("ready_camera_count") or len(ready_noise)),
            "noise_missing_camera_keys": noise_summary.get("missing_camera_keys") or [row["key"] for row in missing_noise],
            "noise_missing_requirement_ids": [
                REQUIREMENT_BY_NOISE_KEY[str(row["key"])]
                for row in missing_noise
                if str(row.get("key") or "") in REQUIREMENT_BY_NOISE_KEY
            ],
            "darkframe_stack_ready_group_count": int((darkframe_audit.get("summary") or {}).get("production_stack_ready_group_count") or 0),
            "nearest_darkframe_stack_key": nearest_stack.get("key") if nearest_stack else None,
            "nearest_darkframe_stack_candidate_count": nearest_stack.get("candidate_count") if nearest_stack else 0,
            "nearest_darkframe_stack_by_noise_key": {
                key: {
                    "key": row.get("key"),
                    "candidate_count": row.get("candidate_count"),
                    "needed_for_stack": row.get("needed_for_stack"),
                    "production_stack_ready": row.get("production_stack_ready"),
                    "paths": row.get("paths") or [],
                }
                for key, row in nearest_by_noise_key.items()
            },
            "open_requirement_ids": sorted(
                {
                    *(REQUIREMENT_BY_PHASE[phase] for phase in missing_phases if phase in REQUIREMENT_BY_PHASE),
                    *(
                        REQUIREMENT_BY_NOISE_KEY[str(row["key"])]
                        for row in missing_noise
                        if str(row.get("key") or "") in REQUIREMENT_BY_NOISE_KEY
                    ),
                }
            ),
            "production_stills_fixture_closure_ready": not missing_phases and not missing_noise,
        },
        "ready_noise_coverage": ready_noise,
        "missing_noise_coverage": missing_noise,
        "darkframe_stack_groups": stack_groups,
        "capture_actions": capture_actions,
        "policy": {
            "real_phase_claim_requires_real_fixture": True,
            "noise_removal_addback_requires_validated_darkframe_sidecar": True,
            "ordinary_scene_frames_are_not_noise_targets": True,
        },
    }


def render_html(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    cards = [
        ("Ready", summary["production_stills_fixture_closure_ready"]),
        ("Real phase counts", ", ".join(f"{k}:{v}" for k, v in summary["phase_counts"].items())),
        ("Missing phases", ", ".join(summary["missing_real_bayer_phases"]) or "none"),
        ("Missing noise", ", ".join(summary["noise_missing_camera_keys"]) or "none"),
        ("Nearest stack", summary["nearest_darkframe_stack_key"] or "none"),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    action_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('requirement_id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('priority') or ''))}</td>"
        f"<td>{html.escape(str(row.get('pillar') or ''))}</td>"
        f"<td>{html.escape(str(row.get('action') or ''))}</td>"
        f"<td>{html.escape(str(row.get('why') or ''))}</td>"
        f"<td>{html.escape(str(row.get('done_when') or ''))}</td>"
        "</tr>"
        for row in plan["capture_actions"]
    )
    stack_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('key') or ''))}</td>"
        f"<td>{html.escape(str(row.get('candidate_count') or 0))}</td>"
        f"<td>{html.escape(str(row.get('needed_for_stack') or 0))}</td>"
        f"<td>{html.escape(str(row.get('production_stack_ready')))}</td>"
        "</tr>"
        for row in plan["darkframe_stack_groups"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Stills Fixture Gap Plan</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
</style></head><body><main>
<h1>Stills Fixture Gap Plan</h1>
<p class="sub">Schema {html.escape(plan["schema"])}. This is the concrete closure list for raw-stills phase and camera-noise evidence.</p>
<div class="grid">{card_html}</div>
<h2>Capture Actions</h2>
<table><thead><tr><th>Requirement</th><th>Priority</th><th>Pillar</th><th>Action</th><th>Why</th><th>Done when</th></tr></thead><tbody>{action_rows}</tbody></table>
<h2>Darkframe Candidate Groups</h2>
<table><thead><tr><th>Group</th><th>Candidates</th><th>Needed</th><th>Stack ready</th></tr></thead><tbody>{stack_rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    bayer_inventory_paths = args.bayer_inventory or [DEFAULT_BAYER_INVENTORY]
    sources = {
        "bayer_inventories": bayer_inventory_paths,
        "darkframe_audit": args.darkframe_audit,
        "noise_coverage": args.noise_coverage,
    }
    plan = build_plan(
        [load_json(path) for path in bayer_inventory_paths],
        load_json(args.darkframe_audit),
        load_json(args.noise_coverage),
        sources,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.output_dir / "stills_fixture_gap_plan.json"
    html_path = args.output_dir / "index.html"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(plan), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
