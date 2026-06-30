#!/usr/bin/env python3
"""Build the capture request for closing the raw-video native PSF gap."""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_video_psf_capture_request.v1"
DEFAULT_GAP_PLAN = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gap_plan_20260630/raw_video_psf_gap_plan.json")


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


def build_request(gap_plan: dict[str, Any], gap_plan_path: Path) -> dict[str, Any]:
    summary = gap_plan.get("summary") or {}
    accepted = int(summary.get("accepted_pair_count") or 0)
    required = 3
    minimum_new_pairs = max(required - accepted + 1, 3)
    requests = [
        {
            "id": "mission1_static_high_low_psf_pairs",
            "priority": "required",
            "sample_type": "controlled_same_scene_high_low_raw_pair_stack",
            "camera": "GoPro Mission 1",
            "minimum_pair_count": minimum_new_pairs,
            "capture_guidance": [
                "Use a locked camera and static scene; tripod or fixed mount, no handheld framing drift.",
                "Capture native 8192 x 6144 Bayer and native 4096 x 3072 Bayer versions back-to-back without moving the camera.",
                "Keep exposure, ISO, white balance, lens mode, sharpening, stabilization, and any lens correction mode fixed across each high/low pair.",
                "Use scenes with hard edges and fine texture across the frame: printed Siemens/star chart, slanted edges, foliage/brick/fabric, and high-contrast text.",
                "Capture at least five high/low pairs if practical, because the current local corpus accepted only two near-time pairs and produced an unstable kernel.",
                "Keep original GPR/DNG/JPEG triplets and decoded raw Bayer files; do not crop, demosaic, tone-map, or resize before the PSF tools run.",
            ],
            "metadata_required": [
                "original high-resolution and low-resolution GPR/DNG paths with SHA-256 source hashes",
                "decoded little-endian uint16 Bayer paths, byte counts, dimensions, CFA phase, and SHA-256 hashes for both sides of every pair",
                "extraction receipt or command for each decoded raw file, including whether tools/extract_raw_bayer_u16.py or camera firmware produced it",
                "make, model, capture mode, ISO, exposure time, white balance, lens mode, stabilization state, sharpening state, and lens-correction state",
                "pair label, capture order, timestamp delta, and confirmation that the camera and scene did not move between high/low captures",
            ],
            "acceptance": [
                "pair inventory reports at least three decoded native high/low Mission 1 candidate pairs",
                "each accepted pair has source hashes plus decoded raw hashes for both the 8192 x 6144 and 4096 x 3072 Bayer inputs",
                "each decoded raw input has the exact expected byte size for its dimensions and little-endian uint16 Bayer format",
                "measurement plan selects at least three pairs",
                "native PSF measurement accepts at least three pairs after scene/alignment vetting",
                "accepted pairs provide at least 96 sharp-edge and 96 texture-field tiles",
                "combined kernel has no invalid negative weights and max normalized-weight std <= 0.10",
                "native_psf_ready_for_model_conditioning=true",
            ],
        },
        {
            "id": "mission1_psf_negative_controls",
            "priority": "recommended",
            "sample_type": "negative_control_pairs",
            "camera": "GoPro Mission 1",
            "minimum_pair_count": 2,
            "capture_guidance": [
                "Include two intentionally changed-scene or moved-camera high/low pairs.",
                "These should fail alignment/scene vetting and verify the measurement does not accept bad calibration data.",
            ],
            "metadata_required": [
                "original high-resolution and low-resolution GPR/DNG paths with SHA-256 source hashes",
                "decoded little-endian uint16 Bayer paths, byte counts, dimensions, and SHA-256 hashes for both sides of every control pair",
                "explicit label describing the intended negative-control defect: moved camera, changed scene, or mismatched capture settings",
            ],
            "acceptance": [
                "native PSF measurement rejects the negative controls",
                "rejection reasons point to alignment/scene mismatch rather than tool failure",
            ],
        },
    ]
    validation_commands = [
        "python3 tools/extract_raw_bayer_u16.py --input <high_8192x6144.dng> --output <high_8192x6144.raw> --write-receipt <high_extract_receipt.json>",
        "python3 tools/extract_raw_bayer_u16.py --input <low_4096x3072.dng> --output <low_4096x3072.raw> --write-receipt <low_extract_receipt.json>",
        "python3 tools/build_mission1_native_psf_pair_inventory.py --media-summary <media_summary.json> --raw50-dir <decoded_8192x6144_raw_dir> --raw12-dir <decoded_4096x3072_raw_dir> --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_<date>",
        "python3 tools/build_mission1_native_psf_measurement_plan.py --pair-inventory /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_<date>/inventory.json --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_<date>",
        "/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python3 tools/build_mission1_native_psf_measurement.py --measurement-plan /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_<date>/measurement_plan.json --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_<date>",
        "python3 tools/build_raw_video_psf_gap_plan.py --pair-inventory /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_<date>/inventory.json --measurement-plan /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_<date>/measurement_plan.json --measurement /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_<date>/native_psf_measurement.json --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gap_plan_<date>",
    ]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_gap_plan": gap_plan_path.as_posix(),
        "current_gap_summary": {
            "candidate_pair_count": int(summary.get("candidate_pair_count") or 0),
            "decoded_candidate_pair_count": int(summary.get("decoded_candidate_pair_count") or 0),
            "selected_pair_count": int(summary.get("selected_pair_count") or 0),
            "accepted_pair_count": accepted,
            "kernel_stable": bool(summary.get("kernel_stable")),
            "native_psf_ready_for_model_conditioning": bool(summary.get("native_psf_ready_for_model_conditioning")),
        },
        "summary": {
            "request_count": len(requests),
            "required_request_count": sum(1 for row in requests if row["priority"] == "required"),
            "minimum_new_controlled_pair_count": minimum_new_pairs,
            "production_psf_capture_request_ready": True,
        },
        "requests": requests,
        "validation_commands": validation_commands,
        "promotion_policy": {
            "near_time_pairs_are_diagnostic_only": True,
            "controlled_same_scene_pairs_required_for_kernel_promotion": True,
            "pair_promotion_requires_source_hashes_and_decoded_raw_hashes": True,
            "pair_promotion_requires_fixed_camera_settings": True,
            "pair_promotion_requires_negative_controls": True,
            "psf_conditioned_model_gate_required_after_kernel": True,
            "new_artifacts_stay_under_external_root": "/Volumes/OWC_8TB/gpr_work",
        },
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    gap = data["current_gap_summary"]
    cards = [
        ("Requests", summary["request_count"]),
        ("Required", summary["required_request_count"]),
        ("New pairs", summary["minimum_new_controlled_pair_count"]),
        ("Current accepted", gap["accepted_pair_count"]),
        ("Kernel stable", str(gap["kernel_stable"]).lower()),
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
        f"<td>{html.escape(str(row['priority']))}</td>"
        f"<td>{html.escape(str(row['id']))}</td>"
        f"<td>{html.escape(str(row['sample_type']))}</td>"
        f"<td>{html.escape(str(row['minimum_pair_count']))}</td>"
        f"<td>{html.escape('; '.join(row['capture_guidance']))}</td>"
        f"<td>{html.escape('; '.join(row.get('metadata_required') or []))}</td>"
        f"<td>{html.escape('; '.join(row['acceptance']))}</td>"
        "</tr>"
        for row in data["requests"]
    )
    command_rows = "\n".join(
        f"<tr><td><code>{html.escape(command)}</code></td></tr>" for command in data["validation_commands"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Video PSF Capture Request</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; max-width: 920px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ white-space: normal; overflow-wrap: anywhere; }}
</style></head><body><main>
<h1>Raw Video PSF Capture Request</h1>
<p class="sub">Schema {html.escape(data["schema"])}. The current Mission 1 native PSF run has tile support but only two accepted near-time pairs and an unstable kernel. This is the controlled capture handoff needed before a PSF-conditioned 4K/8K SR model can replace the approved baselines.</p>
<div class="grid">{card_html}</div>
<h2>Requested Samples</h2>
<table><thead><tr><th>Priority</th><th>ID</th><th>Type</th><th>Pairs</th><th>Capture guidance</th><th>Metadata required</th><th>Acceptance</th></tr></thead><tbody>{request_rows}</tbody></table>
<h2>Validation Commands</h2>
<table><tbody>{command_rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    data = build_request(load_json(args.gap_plan), args.gap_plan)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_video_psf_capture_request.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
