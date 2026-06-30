#!/usr/bin/env python3
"""Build a closure plan for the remaining raw-video PSF/SR gap."""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_video_psf_gap_plan.v1"
DEFAULT_PAIR_INVENTORY = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630/inventory.json"
)
DEFAULT_MEASUREMENT_PLAN = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630/measurement_plan.json"
)
DEFAULT_MEASUREMENT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/native_psf_measurement.json"
)
DEFAULT_AUDIT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630/raw_video_psf_audit.json"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair-inventory", type=Path, default=DEFAULT_PAIR_INVENTORY)
    ap.add_argument("--measurement-plan", type=Path, default=DEFAULT_MEASUREMENT_PLAN)
    ap.add_argument("--measurement", type=Path, default=DEFAULT_MEASUREMENT)
    ap.add_argument("--psf-audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def int_at(data: dict[str, Any], path: tuple[str, ...], default: int = 0) -> int:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return int(cur) if isinstance(cur, (int, float)) else default


def bool_at(data: dict[str, Any], path: tuple[str, ...], default: bool = False) -> bool:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return bool(cur) if isinstance(cur, bool) else default


def list_len(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    return len(value) if isinstance(value, list) else 0


def artifact(label: str, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "path": path.as_posix(),
        "schema": data.get("schema"),
        "exists": path.exists(),
    }


def build_plan(
    pair_inventory: dict[str, Any],
    measurement_plan: dict[str, Any],
    measurement: dict[str, Any],
    psf_audit: dict[str, Any],
    sources: dict[str, Path],
) -> dict[str, Any]:
    candidate_pairs = int_at(pair_inventory, ("summary", "candidate_pair_count"), list_len(pair_inventory, "candidate_pairs"))
    decoded_pairs = int_at(pair_inventory, ("summary", "decoded_candidate_pair_count"))
    selected_pairs = int_at(measurement_plan, ("summary", "selected_pair_count"), list_len(measurement_plan, "selected_pairs"))
    accepted_pairs = int_at(measurement, ("summary", "accepted_pair_count"))
    rejected_pairs = int_at(measurement, ("summary", "rejected_pair_count"))
    sharp_tiles = int_at(measurement, ("summary", "accepted_sharp_edge_tile_count"))
    texture_tiles = int_at(measurement, ("summary", "accepted_texture_field_tile_count"))
    kernel_stable = bool_at(measurement, ("summary", "kernel_stable"))
    measured_ready = bool_at(measurement, ("native_psf_ready_for_model_conditioning"))
    approved_baselines_ready = bool_at(psf_audit, ("approved_baselines_ready",))
    psf_replacement_ready = bool_at(psf_audit, ("psf_replacement_ready",))

    enough_pairs = accepted_pairs >= 3
    tile_support_ready = sharp_tiles >= 96 and texture_tiles >= 96
    measurement_ready = enough_pairs and tile_support_ready and kernel_stable and measured_ready
    production_ready = measurement_ready and psf_replacement_ready

    blockers: list[dict[str, Any]] = []
    if not approved_baselines_ready:
        blockers.append(
            {
                "id": "baseline_missing",
                "status": "required",
                "detail": "Approved 4K cleanup and 8K SR baselines must remain available before measuring a replacement.",
            }
        )
    if accepted_pairs < 3:
        blockers.append(
            {
                "id": "accepted_pair_count",
                "status": "required",
                "detail": f"Need at least 3 accepted same-scene high/low pairs; current measurement accepted {accepted_pairs}.",
            }
        )
    if not tile_support_ready:
        blockers.append(
            {
                "id": "tile_support",
                "status": "required",
                "detail": f"Need >=96 sharp-edge and texture-field tiles; current accepted support is {sharp_tiles} and {texture_tiles}.",
            }
        )
    if not kernel_stable:
        blockers.append(
            {
                "id": "kernel_stability",
                "status": "required",
                "detail": "Measured native kernel is unstable and cannot condition a model yet.",
            }
        )
    if not psf_replacement_ready:
        blockers.append(
            {
                "id": "conditioned_model_gate",
                "status": "required_after_measurement",
                "detail": "No PSF-conditioned 4K cleanup or 8K SR replacement has beaten the approved baselines yet.",
            }
        )

    next_actions = [
        {
            "priority": 1,
            "action": "Capture or locate controlled same-scene Mission 1 high/low pairs.",
            "done_when": "At least three pairs pass scene/alignment vetting with native 8192x6144 and 4096x3072 Bayer sources.",
        },
        {
            "priority": 2,
            "action": "Re-run native PSF measurement on the controlled pairs.",
            "done_when": "The combined kernel is stable, has no invalid negative weights, and is marked ready for model conditioning.",
        },
        {
            "priority": 3,
            "action": "Train a PSF-conditioned 4K cleanup and/or 8K SR candidate.",
            "done_when": "Mission42 and Z8 all24 gates beat the current approved 4K/8K baselines with clean worst rows.",
        },
        {
            "priority": 4,
            "action": "Promote only with production artifacts.",
            "done_when": ".gvid, editable DNG/GPR, ProRes review, timing, memory, checkpoint, config, and hash receipts exist.",
        },
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {key: path.as_posix() for key, path in sources.items()},
        "summary": {
            "candidate_pair_count": candidate_pairs,
            "decoded_candidate_pair_count": decoded_pairs,
            "selected_pair_count": selected_pairs,
            "accepted_pair_count": accepted_pairs,
            "rejected_pair_count": rejected_pairs,
            "accepted_sharp_edge_tile_count": sharp_tiles,
            "accepted_texture_field_tile_count": texture_tiles,
            "kernel_stable": kernel_stable,
            "tile_support_ready": tile_support_ready,
            "native_psf_ready_for_model_conditioning": measured_ready,
            "approved_baselines_ready": approved_baselines_ready,
            "psf_replacement_ready": psf_replacement_ready,
            "production_psf_closure_ready": production_ready,
        },
        "policy": {
            "minimum_accepted_pairs": 3,
            "minimum_sharp_edge_tiles": 96,
            "minimum_texture_field_tiles": 96,
            "use_near_time_pairs_only_as_candidates": True,
            "do_not_replace_baseline_until_conditioned_gate_passes": True,
        },
        "blockers": blockers,
        "next_actions": next_actions,
        "artifacts": [
            artifact("Mission 1 native high/low pair inventory", sources["pair_inventory"], pair_inventory),
            artifact("Mission 1 native PSF measurement plan", sources["measurement_plan"], measurement_plan),
            artifact("Mission 1 native PSF measurement", sources["measurement"], measurement),
            artifact("raw-video PSF/SR readiness audit", sources["psf_audit"], psf_audit),
        ],
    }


def render_html(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    cards = [
        ("Closure ready", summary["production_psf_closure_ready"]),
        ("Approved baselines", summary["approved_baselines_ready"]),
        ("Candidate pairs", summary["candidate_pair_count"]),
        ("Accepted pairs", f"{summary['accepted_pair_count']} / 3 required"),
        ("Sharp-edge tiles", summary["accepted_sharp_edge_tile_count"]),
        ("Texture-field tiles", summary["accepted_texture_field_tile_count"]),
        ("Kernel stable", summary["kernel_stable"]),
        ("Model gate", summary["psf_replacement_ready"]),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    blocker_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('status') or ''))}</td>"
        f"<td>{html.escape(str(row.get('detail') or ''))}</td>"
        "</tr>"
        for row in plan["blockers"]
    )
    action_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('priority') or ''))}</td>"
        f"<td>{html.escape(str(row.get('action') or ''))}</td>"
        f"<td>{html.escape(str(row.get('done_when') or ''))}</td>"
        "</tr>"
        for row in plan["next_actions"]
    )
    artifact_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('label') or ''))}</td>"
        f"<td>{html.escape(str(row.get('exists')))}</td>"
        f"<td>{html.escape(str(row.get('schema') or 'missing'))}</td>"
        f"<td>{html.escape(str(row.get('path') or ''))}</td>"
        "</tr>"
        for row in plan["artifacts"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Video PSF Gap Plan</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; max-width: 880px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
</style></head><body><main>
<h1>Raw Video PSF Gap Plan</h1>
<p class="sub">Schema {html.escape(plan["schema"])}. This turns the current native Mission 1 PSF measurement into the concrete closure list for a PSF-conditioned 4K/8K replacement.</p>
<div class="grid">{card_html}</div>
<h2>Blockers</h2>
<table><thead><tr><th>ID</th><th>Status</th><th>Detail</th></tr></thead><tbody>{blocker_rows}</tbody></table>
<h2>Next Actions</h2>
<table><thead><tr><th>Priority</th><th>Action</th><th>Done when</th></tr></thead><tbody>{action_rows}</tbody></table>
<h2>Artifacts</h2>
<table><thead><tr><th>Artifact</th><th>Exists</th><th>Schema</th><th>Path</th></tr></thead><tbody>{artifact_rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    sources = {
        "pair_inventory": args.pair_inventory,
        "measurement_plan": args.measurement_plan,
        "measurement": args.measurement,
        "psf_audit": args.psf_audit,
    }
    plan = build_plan(
        load_json(args.pair_inventory),
        load_json(args.measurement_plan),
        load_json(args.measurement),
        load_json(args.psf_audit),
        sources,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_video_psf_gap_plan.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(plan), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
