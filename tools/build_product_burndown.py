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


def action(
    *,
    pillar: str,
    priority: int,
    title: str,
    owner: str,
    can_do_without_camera: bool,
    evidence_required: list[str],
    next_command: str | None,
    completion_gate: str,
) -> dict[str, Any]:
    return {
        "pillar": pillar,
        "priority": priority,
        "title": title,
        "owner": owner,
        "can_do_without_camera": can_do_without_camera,
        "evidence_required": evidence_required,
        "next_command": next_command,
        "completion_gate": completion_gate,
    }


def pillar_by_id(scorecard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in scorecard["pillars"]}


def build_burndown(external_root: Path) -> dict[str, Any]:
    scorecard = build_scorecard(external_root)
    pillars = pillar_by_id(scorecard)
    actions = [
        action(
            pillar="raw_stills",
            priority=1,
            title="Close real Bayer phase fixture gaps",
            owner="repo/sample curator",
            can_do_without_camera=True,
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
            can_do_without_camera=True,
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
            can_do_without_camera=False,
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
            title="Promote a true raw-CFA residual still-SR model",
            owner="CNN researcher",
            can_do_without_camera=True,
            evidence_required=[
                "candidate-only runtime inputs",
                "Z8 held-out raw-residual recovery clears promotion threshold",
                "X2D held-out raw-residual recovery clears promotion threshold",
                "50 MP / 100 MP visual and editor-latitude review dashboards",
                "worst-row dashboard shows no severe texture or tone failures",
            ],
            next_command=(
                "python3 tools/build_premium_still_sr_raw_cfa_residual_gap.py "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_gap_<date>"
            ),
            completion_gate="The model beats the current raw-CFA residual baselines on both Z8 and X2D broad holdouts and passes the still/editor-latitude gate.",
        ),
        action(
            pillar="raw_video_psf_sr",
            priority=1,
            title="Capture or locate controlled Mission 1 high/low PSF pairs",
            owner="sample curator",
            can_do_without_camera=True,
            evidence_required=[
                "at least three same-scene 8192 x 6144 / 4096 x 3072 pairs",
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
            pillar="raw_video_psf_sr",
            priority=2,
            title="Gate a PSF-conditioned 4K/8K video SR candidate",
            owner="CNN researcher",
            can_do_without_camera=True,
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
    actions.sort(key=lambda row: (row["priority"], row["pillar"], row["title"]))
    by_pillar: dict[str, list[dict[str, Any]]] = {}
    for row in actions:
        by_pillar.setdefault(str(row["pillar"]), []).append(row)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": str(external_root),
        "source_scorecard_schema": scorecard["schema"],
        "four_pillar_completion_percent": scorecard["four_pillar_completion_percent"],
        "production_ready": scorecard["production_ready"],
        "summary": {
            "action_count": len(actions),
            "camera_required_action_count": sum(1 for row in actions if not row["can_do_without_camera"]),
            "non_camera_action_count": sum(1 for row in actions if row["can_do_without_camera"]),
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
                "current_blocker": pillars[pillar_id]["open_work"][0],
                "burn_down_actions": by_pillar.get(pillar_id, []),
            }
            for pillar_id in ["raw_stills", "raw_video_mvp", "premium_still_sr", "raw_video_psf_sr"]
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
        action_rows = []
        for row in pillar["burn_down_actions"]:
            evidence = "<br>".join(html.escape(str(item)) for item in row["evidence_required"])
            command = row["next_command"] or "defined after prerequisite evidence exists"
            camera = "yes" if row["can_do_without_camera"] else "no"
            action_rows.append(
                "<tr>"
                f"<td>{row['priority']}</td>"
                f"<td>{html.escape(row['title'])}</td>"
                f"<td>{html.escape(row['owner'])}</td>"
                f"<td>{camera}</td>"
                f"<td>{evidence}</td>"
                f"<td><code>{html.escape(command)}</code></td>"
                f"<td>{html.escape(row['completion_gate'])}</td>"
                "</tr>"
            )
        rows = "\n".join(action_rows) or "<tr><td colspan='7'>No burn-down action recorded.</td></tr>"
        sections.append(
            f"""<section class="detail">
  <h2>{html.escape(pillar["title"])}</h2>
  <table><thead><tr><th>Priority</th><th>Action</th><th>Owner</th><th>No camera?</th><th>Evidence required</th><th>Command</th><th>Completion gate</th></tr></thead><tbody>{rows}</tbody></table>
</section>"""
        )
    summary = data["summary"]
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
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body>
<main>
  <h1>GPR Production Burn-Down</h1>
  <p class="sub">The scorecard says where the four product pillars are. This burn-down says what evidence moves each pillar toward production and which steps can proceed without Mission 1 firmware access.</p>
  <div class="headline">
    <div class="overall">{data["four_pillar_completion_percent"]}%</div>
    <div class="overall-label">four-pillar completion; production ready: {str(data["production_ready"]).lower()}; {summary["non_camera_action_count"]} non-camera actions, {summary["camera_required_action_count"]} camera-required action</div>
  </div>
  <div class="grid">{''.join(cards)}</div>
  {''.join(sections)}
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
