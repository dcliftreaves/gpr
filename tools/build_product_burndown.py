#!/usr/bin/env python3
"""Build a concise four-pillar production burn-down dashboard."""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any

from build_product_pillar_scorecard import DEFAULT_EXTERNAL_ROOT, build_scorecard


SCHEMA = "gpr.product_burndown.v1"
ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json"
OPEN_REQUIREMENT_STATUSES = {"open", "blocked_on_real_camera_access"}
OPTIONAL_RESEARCH_STATUSES = {"research_optional"}
RELEASE_PILLAR_IDS = {"raw_stills", "raw_video_mvp", "premium_still_sr", "raw_video_reconstruction"}


def action(
    *,
    pillar: str,
    priority: int,
    title: str,
    owner: str,
    requirement_ids: list[str],
    can_do_without_camera: bool,
    blocker_type: str,
    requires_mission1_camera_role: bool,
    requires_new_samples: bool,
    evidence_required: list[str],
    next_command: str | None,
    completion_gate: str,
) -> dict[str, Any]:
    return {
        "pillar": pillar,
        "priority": priority,
        "title": title,
        "owner": owner,
        "requirement_ids": requirement_ids,
        "can_do_without_camera": can_do_without_camera,
        "blocker_type": blocker_type,
        "requires_mission1_camera_role": requires_mission1_camera_role,
        "requires_new_samples": requires_new_samples,
        "evidence_required": evidence_required,
        "next_command": next_command,
        "completion_gate": completion_gate,
    }


def load_requirements() -> dict[str, Any]:
    return json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8"))


def requirements_by_id(requirements: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in requirements["requirements"]}


def summarize_requirement(req: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": req["id"],
        "pillar": req["pillar"],
        "status": req["status"],
        "sample_type": req["sample_type"],
        "priority": req["priority"],
        "why_needed": req["why_needed"],
        "required_evidence": req["required_evidence"],
        "acceptance": req["acceptance"],
        "validation_commands": req["validation_commands"],
    }
    for key in ("minimum_count", "minimum_pair_count", "required_cfa_phase", "camera", "lowest_lift_current_group"):
        if key in req:
            result[key] = req[key]
    return result


def attach_requirements(
    actions: list[dict[str, Any]],
    requirement_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for row in actions:
        attached = dict(row)
        source_requirements = []
        for req_id in row["requirement_ids"]:
            if req_id not in requirement_map:
                raise KeyError(f"unknown production capture requirement: {req_id}")
            source_requirements.append(summarize_requirement(requirement_map[req_id]))
        attached["source_requirements"] = source_requirements
        attached["source_requirement_statuses"] = {
            str(req["id"]): str(req["status"]) for req in source_requirements
        }
        attached["validation_commands"] = [
            str(command)
            for req in source_requirements
            for command in req.get("validation_commands", [])
        ]
        result.append(attached)
    return result


def has_open_requirement(action_row: dict[str, Any], requirement_map: dict[str, dict[str, Any]]) -> bool:
    return any(
        str(requirement_map[req_id].get("status")) in OPEN_REQUIREMENT_STATUSES
        for req_id in action_row["requirement_ids"]
    )


def is_release_action(action_row: dict[str, Any], requirement_map: dict[str, dict[str, Any]]) -> bool:
    """Return true only for actions that can affect the current release burn-down."""
    if str(action_row.get("pillar")) not in RELEASE_PILLAR_IDS:
        return False
    return all(
        str(requirement_map[req_id].get("status")) not in OPTIONAL_RESEARCH_STATUSES
        and str(requirement_map[req_id].get("priority")) != "research_optional"
        for req_id in action_row["requirement_ids"]
    )


def is_optional_research_action(action_row: dict[str, Any], requirement_map: dict[str, dict[str, Any]]) -> bool:
    return any(
        str(requirement_map[req_id].get("status")) in OPTIONAL_RESEARCH_STATUSES
        or str(requirement_map[req_id].get("priority")) == "research_optional"
        for req_id in action_row["requirement_ids"]
    )


def optional_research_requirement_ids(requirements: dict[str, Any]) -> list[str]:
    return [
        str(req["id"])
        for req in requirements["requirements"]
        if str(req.get("status")) in OPTIONAL_RESEARCH_STATUSES
        or str(req.get("priority")) == "research_optional"
    ]


def pillar_by_id(scorecard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in scorecard["pillars"]}


def build_burndown(external_root: Path) -> dict[str, Any]:
    scorecard = build_scorecard(external_root)
    requirements = load_requirements()
    requirement_map = requirements_by_id(requirements)
    pillars = pillar_by_id(scorecard)
    actions = [
        action(
            pillar="raw_stills",
            priority=1,
            title="Close real Bayer phase fixture gaps",
            owner="repo/sample curator",
            requirement_ids=["real_grbg_fixture", "real_bggr_fixture"],
            can_do_without_camera=True,
            blocker_type="sample_acquisition",
            requires_mission1_camera_role=False,
            requires_new_samples=True,
            evidence_required=[
                "one parsed real GRBG fixture",
                "one parsed real BGGR fixture",
                "updated Bayer phase fixture discovery dashboard",
                "still matrix and capabilities tests still pass",
            ],
            next_command=(
                "python3 tools/build_bayer_phase_fixture_inventory.py "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_<date>"
            ),
            completion_gate="Real GRBG and BGGR fixtures are present; synthetic-only phase coverage is no longer the broad-camera blocker.",
        ),
        action(
            pillar="raw_stills",
            priority=2,
            title="Add Mission 1 and iPhone darkframe sidecars",
            owner="sample curator",
            requirement_ids=["mission1_darkframe_stack", "iphone_cfa_darkframe_stack"],
            can_do_without_camera=True,
            blocker_type="sample_acquisition",
            requires_mission1_camera_role=False,
            requires_new_samples=True,
            evidence_required=[
                "four same-camera/same-ISO Mission 1 darkframes",
                "four same-camera/same-ISO iPhone CFA darkframes",
                "gpr.camera_noise_calibration.v1 sidecars with production_ready=true",
                "camera-noise coverage audit marks both camera families ready",
            ],
            next_command=(
                "python3 tools/build_stills_capture_request.py "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_<date>"
            ),
            completion_gate="Nonzero camera-noise removal/addback can be enabled for Mission 1 and iPhone only after the sidecars validate.",
        ),
        action(
            pillar="raw_video_mvp",
            priority=1,
            title="Replace Pi stand-in receipts with Mission 1 camera-role receipts",
            owner="GoPro firmware engineer",
            requirement_ids=["mission1_camera_role_receipts"],
            can_do_without_camera=False,
            blocker_type="hardware_integration",
            requires_mission1_camera_role=True,
            requires_new_samples=False,
            evidence_required=[
                "real sensor/DMA or camera ring-buffer source receipt",
                "real SD writer receipt",
                "real rear-display/UI preview receipt",
                "valid .gvid with zero drops at the accepted frame-rate floor",
            ],
            next_command="python3 tools/run_gopro_mission1_quick_validation.py --help",
            completion_gate="The same 4096 x 3072 Bayer .gvid encode and 1024 preview path is proven on Mission 1 hardware, not only on the Pi 5 stand-in.",
        ),
        action(
            pillar="premium_still_sr",
            priority=1,
            title="Launch a preflighted premium still-SR restoration candidate",
            owner="CNN researcher",
            requirement_ids=["premium_still_sr_promotion_receipts"],
            can_do_without_camera=True,
            blocker_type="model_promotion",
            requires_mission1_camera_role=False,
            requires_new_samples=False,
            evidence_required=[
                "runtime_inputs includes candidate_raw and camera_metadata but excludes REF/source/JPEG content",
                "candidate preflight passes with a materially new restoration-teacher, non-local/full-image, burst, or clean-source RAW SR architecture",
                "realistic RAW degradation policy covers at least two of PSF/blur, noise/ISO, bit depth, compression/decode, sensor, and CFA behavior",
                "same-color Bayer interpolation and the current 82-receipt still-SR scoreboard are explicit baselines",
                "Z8 held-out raw-residual recovery clears promotion threshold",
                "X2D held-out raw-residual recovery clears promotion threshold",
                "positive median_mae_reduction_pct_50mp and median_mae_reduction_pct_100mp",
                "nonnegative worst_row_mae_reduction_pct_50mp and worst_row_mae_reduction_pct_100mp",
                "50 MP / 100 MP visual and editor-latitude review dashboards",
                "render_seconds_per_50mp_frame, render_seconds_per_100mp_frame, and peak_rss_gb timing/memory receipt",
                "exact-sidecar-only noise policy with source residual noise forbidden",
                "worst-row dashboard shows no severe texture or tone failures",
            ],
            next_command=(
                "python3 tools/build_premium_still_sr_launch_packet.py "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_launch_packet_<date> "
                "--require-launchable"
            ),
            completion_gate=(
                "The candidate first passes the launch preflight, then beats the current still-SR scoreboard on both Z8 and X2D broad holdouts, "
                "passes the 50 MP / 100 MP still/editor-latitude gate, validates through tools/build_premium_still_sr_gate_receipt.py "
                "and tools/check_production_capture_submission.py, and records runtime-input, noise-policy, timing, and memory receipts."
            ),
        ),
        action(
            pillar="raw_video_psf_research",
            priority=1,
            title="Capture or locate controlled Mission 1 high/low PSF pairs",
            owner="sample curator",
            requirement_ids=["controlled_mission1_psf_pairs"],
            can_do_without_camera=True,
            blocker_type="sample_acquisition",
            requires_mission1_camera_role=False,
            requires_new_samples=True,
            evidence_required=[
                "at least three same-scene 8192 x 6144 / 4096 x 3072 pairs",
                "source hashes and decoded little-endian uint16 Bayer hashes for both sides of each pair",
                "fixed ISO/exposure/WB/lens/stabilization/sharpening/lens-correction settings",
                "negative controls that fail scene/alignment vetting",
                "scene and alignment vetting pass",
                "stable measured native PSF kernel",
                "native PSF receipt accepted for model conditioning",
            ],
            next_command=(
                "python3 tools/build_mission1_native_psf_measurement.py "
                "--help"
            ),
            completion_gate="The native PSF kernel is stable enough to condition 4K cleanup and 8K SR training.",
        ),
        action(
            pillar="raw_video_psf_research",
            priority=2,
            title="Gate a PSF-conditioned 4K/8K video SR candidate",
            owner="CNN researcher",
            requirement_ids=["controlled_mission1_psf_pairs"],
            can_do_without_camera=True,
            blocker_type="model_promotion",
            requires_mission1_camera_role=False,
            requires_new_samples=False,
            evidence_required=[
                "PSF-conditioned training config",
                "Mission42 and Z8 all24 full-frame gates",
                "4K cleanup and 8K .gvid receipts",
                "4K/8K ProRes review outputs",
                "worst-row dashboard against current approved baselines",
            ],
            next_command=None,
            completion_gate="The PSF-conditioned candidate beats the current approved 4K cleanup and 8K SR baselines without worse worst-row failures.",
        ),
    ]
    release_actions = [
        row for row in actions
        if is_release_action(row, requirement_map) and has_open_requirement(row, requirement_map)
    ]
    optional_research_actions = [
        row for row in actions
        if is_optional_research_action(row, requirement_map)
    ]
    actions = attach_requirements(release_actions, requirement_map)
    optional_research_actions = attach_requirements(optional_research_actions, requirement_map)
    actions.sort(key=lambda row: (row["priority"], row["pillar"], row["title"]))
    optional_research_actions.sort(key=lambda row: (row["priority"], row["pillar"], row["title"]))
    by_pillar: dict[str, list[dict[str, Any]]] = {}
    for row in actions:
        by_pillar.setdefault(str(row["pillar"]), []).append(row)
    blocker_type_counts = {
        blocker_type: sum(1 for row in actions if row["blocker_type"] == blocker_type)
        for blocker_type in sorted({str(row["blocker_type"]) for row in actions})
    }
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": str(external_root),
        "source_scorecard_schema": scorecard["schema"],
        "source_requirements_schema": requirements["schema"],
        "source_requirements_path": str(REQUIREMENTS_PATH.relative_to(ROOT)),
        "open_requirement_ids": [
            str(req["id"])
            for req in requirements["requirements"]
            if str(req["status"]) in OPEN_REQUIREMENT_STATUSES
        ],
        "optional_research_requirement_ids": optional_research_requirement_ids(requirements),
        "optional_research_actions": optional_research_actions,
        "four_pillar_completion_percent": scorecard["four_pillar_completion_percent"],
        "production_ready": scorecard["production_ready"],
        "summary": {
            "action_count": len(actions),
            "optional_research_action_count": len(optional_research_actions),
            "open_requirement_count": sum(
                1
                for req in requirements["requirements"]
                if str(req["status"]) in OPEN_REQUIREMENT_STATUSES
            ),
            "optional_research_requirement_count": len(optional_research_requirement_ids(requirements)),
            "camera_required_action_count": sum(1 for row in actions if not row["can_do_without_camera"]),
            "non_camera_action_count": sum(1 for row in actions if row["can_do_without_camera"]),
            "mission1_camera_role_required_action_count": sum(
                1 for row in actions if row["requires_mission1_camera_role"]
            ),
            "new_sample_required_action_count": sum(1 for row in actions if row["requires_new_samples"]),
            "model_promotion_action_count": sum(1 for row in actions if row["blocker_type"] == "model_promotion"),
            "blocker_type_counts": blocker_type_counts,
            "lowest_readiness_pillar": min(
                scorecard["pillars"], key=lambda row: int(row["readiness_percent"])
            )["id"],
        },
        "pillars": [
            {
                "id": pillar_id,
                "title": pillars[pillar_id]["title"],
                "readiness_percent": pillars[pillar_id]["readiness_percent"],
                "production_ready": pillars[pillar_id]["production_ready"],
                "lock_ledger_paths": pillars[pillar_id]["lock_ledger_paths"],
                "locked_artifacts": pillars[pillar_id]["locked_artifacts"],
                "open_production_gates": pillars[pillar_id]["open_production_gates"],
                "current_blocker": pillars[pillar_id]["open_work"][0],
                "burn_down_actions": by_pillar.get(pillar_id, []),
            }
            for pillar_id in ["raw_stills", "raw_video_mvp", "premium_still_sr", "raw_video_reconstruction"]
        ],
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    cards = []
    sections = []
    for pillar in data["pillars"]:
        cards.append(
            f"""<section class="card">
  <div class="label">{html.escape(pillar["title"])}</div>
  <div class="pct">{pillar["readiness_percent"]}%</div>
  <p>{html.escape(pillar["current_blocker"])}</p>
</section>"""
        )
        ledger_paths = "<br>".join(html.escape(str(item)) for item in pillar["lock_ledger_paths"])
        open_gates = "<br>".join(html.escape(str(item)) for item in pillar["open_production_gates"])
        locked = "<br>".join(html.escape(str(item)) for item in pillar["locked_artifacts"])
        action_rows = []
        for row in pillar["burn_down_actions"]:
            evidence = "<br>".join(html.escape(str(item)) for item in row["evidence_required"])
            req_ids = "<br>".join(
                f"<code>{html.escape(str(req_id))}</code>" for req_id in row["requirement_ids"]
            )
            statuses = "<br>".join(
                f"{html.escape(str(req_id))}: {html.escape(str(status))}"
                for req_id, status in row["source_requirement_statuses"].items()
            )
            commands = row["validation_commands"] or ([row["next_command"]] if row["next_command"] else [])
            if row["next_command"] and row["next_command"] not in commands:
                commands = [row["next_command"], *commands]
            command_html = "<br>".join(f"<code>{html.escape(str(command))}</code>" for command in commands)
            if not command_html:
                command_html = "defined after prerequisite evidence exists"
            camera = "yes" if row["can_do_without_camera"] else "no"
            blocker = str(row["blocker_type"]).replace("_", " ")
            mission1 = "yes" if row["requires_mission1_camera_role"] else "no"
            samples = "yes" if row["requires_new_samples"] else "no"
            action_rows.append(
                "<tr>"
                f"<td>{row['priority']}</td>"
                f"<td>{html.escape(row['title'])}</td>"
                f"<td>{html.escape(row['owner'])}</td>"
                f"<td>{req_ids}</td>"
                f"<td>{statuses}</td>"
                f"<td>{html.escape(blocker)}</td>"
                f"<td>{camera}</td>"
                f"<td>{mission1}</td>"
                f"<td>{samples}</td>"
                f"<td>{evidence}</td>"
                f"<td>{command_html}</td>"
                f"<td>{html.escape(row['completion_gate'])}</td>"
                "</tr>"
            )
        rows = "\n".join(action_rows) or "<tr><td colspan='12'>No burn-down action recorded.</td></tr>"
        sections.append(
            f"""<section class="detail">
  <h2>{html.escape(pillar["title"])}</h2>
  <p><strong>Lock ledger paths:</strong><br>{ledger_paths}</p>
  <p><strong>Locked artifacts:</strong><br>{locked}</p>
  <p><strong>Open production gates:</strong><br>{open_gates}</p>
  <table><thead><tr><th>Priority</th><th>Action</th><th>Owner</th><th>Requirement IDs</th><th>Requirement status</th><th>Blocker type</th><th>No camera?</th><th>Mission 1 role?</th><th>New samples?</th><th>Evidence required</th><th>Validation commands</th><th>Completion gate</th></tr></thead><tbody>{rows}</tbody></table>
</section>"""
        )
    summary = data["summary"]
    blocker_counts = ", ".join(
        f"{str(key).replace('_', ' ')}: {value}"
        for key, value in sorted(summary["blocker_type_counts"].items())
    )
    open_ids = ", ".join(f"`{item}`" for item in data["open_requirement_ids"])
    research_ids = ", ".join(f"`{item}`" for item in data["optional_research_requirement_ids"])
    research_rows = []
    for row in data.get("optional_research_actions", []):
        evidence = "<br>".join(html.escape(str(item)) for item in row["evidence_required"])
        req_ids = "<br>".join(
            f"<code>{html.escape(str(req_id))}</code>" for req_id in row["requirement_ids"]
        )
        statuses = "<br>".join(
            f"{html.escape(str(req_id))}: {html.escape(str(status))}"
            for req_id, status in row["source_requirement_statuses"].items()
        )
        commands = row["validation_commands"] or ([row["next_command"]] if row["next_command"] else [])
        if row["next_command"] and row["next_command"] not in commands:
            commands = [row["next_command"], *commands]
        command_html = "<br>".join(f"<code>{html.escape(str(command))}</code>" for command in commands)
        if not command_html:
            command_html = "defined after prerequisite evidence exists"
        research_rows.append(
            "<tr>"
            f"<td>{row['priority']}</td>"
            f"<td>{html.escape(str(row['pillar']).replace('_', ' '))}</td>"
            f"<td>{html.escape(row['title'])}</td>"
            f"<td>{html.escape(row['owner'])}</td>"
            f"<td>{req_ids}</td>"
            f"<td>{statuses}</td>"
            f"<td>{evidence}</td>"
            f"<td>{command_html}</td>"
            f"<td>{html.escape(row['completion_gate'])}</td>"
            "</tr>"
        )
    research_body = (
        "\n".join(research_rows)
        or "<tr><td colspan='9'>No optional research actions recorded.</td></tr>"
    )
    research_section = f"""<section class="detail research">
  <h2>Research Parking Lot</h2>
  <p>These actions are retained for traceability but excluded from release blocker counts, production action counts, and four-pillar readiness. They can replace a locked path only after they beat the locked baseline and provide the same receipts.</p>
  <table><thead><tr><th>Priority</th><th>Research track</th><th>Action</th><th>Owner</th><th>Requirement IDs</th><th>Requirement status</th><th>Evidence required</th><th>Validation commands</th><th>Completion gate</th></tr></thead><tbody>{research_body}</tbody></table>
</section>"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GPR Production Burn-Down</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #101418; background: #f5f7f8; }}
    main {{ max-width: 1260px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 23px; }}
    p {{ margin: 8px 0 0; }}
    code {{ white-space: normal; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
    th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f5; color: #53606d; font-size: 12px; text-transform: uppercase; }}
    .sub {{ max-width: 900px; color: #56616d; font-size: 17px; }}
    .headline {{ display: flex; gap: 20px; align-items: end; flex-wrap: wrap; margin-top: 18px; }}
    .overall {{ font-size: 54px; font-weight: 760; }}
    .overall-label {{ color: #56616d; padding-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; border-top: 5px solid #1267a3; padding: 16px; min-height: 150px; }}
    .label {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .pct {{ font-size: 36px; font-weight: 760; margin-top: 6px; }}
    .detail {{ margin-top: 18px; background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 18px; }}
    .research {{ border-top: 5px solid #7a8591; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body>
<main>
  <h1>GPR Production Burn-Down</h1>
  <p class="sub">The scorecard says where the four product pillars are. This burn-down says what evidence moves each pillar toward production and whether the remaining work is hardware integration, sample acquisition, or model promotion. Each action is tied back to the committed production capture requirement IDs and validation commands. These categories are not locked-artifact regression signals.</p>
  <div class="headline">
    <div class="overall">{data["four_pillar_completion_percent"]}%</div>
    <div class="overall-label">four-pillar completion; production ready: {str(data["production_ready"]).lower()}; {summary["non_camera_action_count"]} non-camera actions, {summary["camera_required_action_count"]} camera-required action; {html.escape(blocker_counts)}</div>
  </div>
  <p class="meta">Open production requirement IDs from {html.escape(data["source_requirements_path"])}: {html.escape(open_ids)}</p>
  <p class="meta">Optional research requirement IDs, excluded from release blocker counts: {html.escape(research_ids or 'none')}</p>
  <div class="grid">{''.join(cards)}</div>
  {''.join(sections)}
  {research_section}
  <p class="meta">Generated {html.escape(data["created_utc"])}. JSON: {html.escape(str(json_path))}. External root: {html.escape(data["external_root"])}.</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=Path(os.environ.get("GPR_EXTERNAL_ROOT") or DEFAULT_EXTERNAL_ROOT))
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    data = build_burndown(args.external_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "product_burndown.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
