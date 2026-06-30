#!/usr/bin/env python3
"""Build a concrete capture request for the remaining raw-stills gaps."""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.stills_capture_request.v1"
DEFAULT_GAP_PLAN = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_20260630/stills_fixture_gap_plan.json"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gap-plan", type=Path, default=DEFAULT_GAP_PLAN)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def darkframe_request(camera_key: str, label: str) -> dict[str, Any]:
    return {
        "id": f"{camera_key}_darkframe_stack",
        "priority": "required",
        "pillar": "raw_stills_noise",
        "sample_type": "darkframe_stack",
        "camera": label,
        "minimum_count": 4,
        "capture_guidance": [
            "Use true no-scene-signal darkframes: lens/body cap on, no light leaks, same raw mode as production still/video capture.",
            "Keep camera model, dimensions, CFA phase, bit depth, black level, white level, ISO, and exposure fixed across the stack.",
            "Prefer the ISO values used by the real scenes that will be compressed or used for SR training.",
        ],
        "acceptance": [
            "darkframe candidate audit groups at least four frames under one camera/ISO/CFA key",
            "camera-noise calibration builder emits gpr.camera_noise_calibration.v1 with production_ready=true",
            "camera-noise coverage audit marks the camera family ready",
        ],
    }


def build_request(gap_plan: dict[str, Any], gap_plan_path: Path) -> dict[str, Any]:
    summary = gap_plan.get("summary") or {}
    missing_phases = list(summary.get("missing_real_bayer_phases") or [])
    missing_noise_keys = list(summary.get("noise_missing_camera_keys") or [])
    nearest_stack_key = summary.get("nearest_darkframe_stack_key")
    nearest_stack_count = int(summary.get("nearest_darkframe_stack_candidate_count") or 0)

    requests: list[dict[str, Any]] = []
    for phase in missing_phases:
        requests.append(
            {
                "id": f"real_{phase.lower()}_fixture",
                "priority": "required",
                "pillar": "raw_stills_phase_coverage",
                "sample_type": "real_camera_raw_fixture",
                "camera": "any real camera that records normal 2x2 Bayer",
                "minimum_count": 1,
                "required_cfa_phase": phase,
                "capture_guidance": [
                    "Provide the original camera raw file, not a demosaiced or linearized derivative.",
                    "Include normal metadata for dimensions, black level, white level, bit depth, CFA phase, ISO, and camera model.",
                    "A simple exposed daylight scene is enough; the fixture is for metadata/openability/phase coverage, not image quality.",
                ],
                "acceptance": [
                    f"Bayer phase fixture inventory reports at least one real parsed {phase} fixture",
                    "legacy still matrix and capability checks continue to pass for all normal Bayer phases",
                ],
            }
        )

    labels = {
        "mission1": "GoPro Mission 1",
        "iphone": "iPhone CFA raw",
    }
    for key in missing_noise_keys:
        requests.append(darkframe_request(str(key), labels.get(str(key), str(key))))

    if nearest_stack_key:
        requests.append(
            {
                "id": "mission1_lowest_lift_darkframe_topup",
                "priority": "lowest_lift",
                "pillar": "raw_stills_noise",
                "sample_type": "matching_darkframe_topup",
                "camera": "GoPro Mission 1",
                "minimum_count": max(0, 4 - nearest_stack_count),
                "existing_group": nearest_stack_key,
                "capture_guidance": [
                    f"Match the existing group exactly: {nearest_stack_key}.",
                    "Capture only the missing matching frames; do not mix ISO or raw mode.",
                    "If exact matching is impossible, capture a fresh four-frame same-ISO stack instead.",
                ],
                "acceptance": [
                    "darkframe candidate audit reports production_stack_ready=true for this group",
                    "sidecar builder emits a production-ready gpr.camera_noise_calibration.v1 receipt",
                ],
            }
        )

    validation_commands = [
        "python3 tools/build_bayer_phase_fixture_inventory.py --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_<date>",
        "python3 tools/build_darkframe_candidate_audit.py --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_<date> <new dng roots>",
        "python3 tools/build_camera_noise_calibration.py --raw <darkframe0.raw> --raw <darkframe1.raw> --raw <darkframe2.raw> --raw <darkframe3.raw> --out <sidecar.json> --camera-model <model> --iso <iso> --width <w> --height <h> --bit-depth <bits> --black-level <black> --white-level <white> --cfa-phase <phase>",
        "python3 tools/build_camera_noise_coverage_audit.py --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_<date>",
        "python3 tools/build_stills_fixture_gap_plan.py --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_<date>",
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_gap_plan": gap_plan_path.as_posix(),
        "summary": {
            "request_count": len(requests),
            "required_request_count": sum(1 for row in requests if row.get("priority") == "required"),
            "missing_real_bayer_phases": missing_phases,
            "missing_noise_camera_keys": missing_noise_keys,
            "nearest_darkframe_stack_key": nearest_stack_key,
            "nearest_darkframe_stack_candidate_count": nearest_stack_count,
            "raw_stills_capture_request_ready": bool(requests),
            "production_stills_fixture_closure_ready": bool(summary.get("production_stills_fixture_closure_ready")),
        },
        "requests": requests,
        "validation_commands": validation_commands,
        "promotion_policy": {
            "real_phase_claim_requires_real_fixture": True,
            "noise_addback_requires_production_ready_noise_sidecar": True,
            "ordinary_scene_frames_are_not_noise_targets": True,
            "new_artifacts_stay_under_external_root": "/Volumes/OWC_8TB/gpr_work",
        },
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    cards = [
        ("Requests", summary["request_count"]),
        ("Required", summary["required_request_count"]),
        ("Missing phases", ", ".join(summary["missing_real_bayer_phases"]) or "none"),
        ("Missing noise", ", ".join(summary["missing_noise_camera_keys"]) or "none"),
        ("Nearest top-up", summary["nearest_darkframe_stack_key"] or "none"),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    request_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('priority') or ''))}</td>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('sample_type') or ''))}</td>"
        f"<td>{html.escape(str(row.get('camera') or ''))}</td>"
        f"<td>{html.escape(str(row.get('minimum_count') or 0))}</td>"
        f"<td>{html.escape('; '.join(str(x) for x in row.get('acceptance') or []))}</td>"
        "</tr>"
        for row in data["requests"]
    )
    command_rows = "\n".join(
        f"<tr><td><code>{html.escape(command)}</code></td></tr>" for command in data["validation_commands"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Stills Capture Request</title>
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
code {{ white-space: normal; overflow-wrap: anywhere; }}
</style></head><body><main>
<h1>Raw Stills Capture Request</h1>
<p class="sub">Schema {html.escape(data["schema"])}. This is the handoff list for closing real Bayer phase and camera-noise gaps in the 50 MP / 100 MP stills pillar.</p>
<div class="grid">{card_html}</div>
<h2>Requested Samples</h2>
<table><thead><tr><th>Priority</th><th>ID</th><th>Type</th><th>Camera</th><th>Count</th><th>Acceptance</th></tr></thead><tbody>{request_rows}</tbody></table>
<h2>Validation Commands</h2>
<table><tbody>{command_rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    data = build_request(load_json(args.gap_plan), args.gap_plan)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "stills_capture_request.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
