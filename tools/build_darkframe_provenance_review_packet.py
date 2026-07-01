#!/usr/bin/env python3
"""Build a hash-strict review packet for darkframe candidate stacks.

This does not promote candidate-discovery photos into production darkframes.
It gives reviewers the exact source hashes and a fill-in provenance template
for the lowest-lift Mission/iPhone candidates so the next step is confirmation
or recapture, not another broad scan.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.darkframe_provenance_review_packet.v1"
DEFAULT_CAPTURE_REQUEST = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_strict_provenance_20260701/stills_capture_request.json"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture-request", type=Path, default=DEFAULT_CAPTURE_REQUEST)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def candidate_rows(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in paths:
        path = Path(item)
        exists = path.is_file()
        rows.append(
            {
                "original_path": path.as_posix(),
                "exists": exists,
                "bytes": path.stat().st_size if exists else None,
                "original_sha256": sha256_file(path) if exists else None,
                "needs_no_scene_signal_confirmation": True,
                "needs_u16_bayer_extraction": True,
            }
        )
    return rows


def provenance_template_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    template = []
    for idx, row in enumerate(rows):
        stem = Path(str(row["original_path"])).stem
        template.append(
            {
                "path": f"<extracted_u16_darkframe_{idx}_{stem}.raw>",
                "sha256": "<64_hex_extracted_raw_sha256>",
                "original_path": row["original_path"],
                "original_sha256": row["original_sha256"] or "<64_hex_original_source_sha256>",
                "extract_receipt": f"<extract_receipt_{idx}_{stem}.json>",
                "no_scene_signal": "<set true only after human/provenance confirmation>",
                "capture_setup": "<lens cap/body cap/no-light-leak proof or recapture note>",
            }
        )
    return template


def review_group(row: dict[str, Any]) -> dict[str, Any]:
    paths = [str(path) for path in row.get("candidate_paths") or []]
    candidates = candidate_rows(paths)
    existing_count = int(row.get("existing_candidate_count") or len(candidates))
    minimum_count = int(row.get("minimum_count") or max(0, 4 - existing_count))
    enough_candidates = existing_count >= 4 and minimum_count == 0
    missing_files = [candidate["original_path"] for candidate in candidates if not candidate["exists"]]
    if missing_files:
        next_action = "recover missing candidate sources or recapture a fresh four-frame dark stack"
    elif enough_candidates:
        next_action = "confirm these are true no-scene-signal darkframes, then extract uint16 Bayer frames"
    else:
        next_action = f"capture {minimum_count} more matching true darkframe frame(s), or recapture a fresh four-frame stack"
    return {
        "id": row.get("id"),
        "requirement_id": row.get("requirement_id"),
        "camera": row.get("camera"),
        "existing_group": row.get("existing_group"),
        "existing_candidate_count": existing_count,
        "minimum_additional_count": minimum_count,
        "candidate_source_count": len(candidates),
        "missing_source_count": len(missing_files),
        "enough_candidate_sources": enough_candidates,
        "production_ready": False,
        "source_provenance_manifest_ready": False,
        "next_action": next_action,
        "candidates": candidates,
        "provenance_manifest_template": {
            "schema": "gpr.darkframe_source_provenance_manifest.v1",
            "frames": provenance_template_rows(candidates),
        },
    }


def build_packet(capture_request: dict[str, Any], capture_request_path: Path) -> dict[str, Any]:
    groups = [
        review_group(row)
        for row in capture_request.get("requests") or []
        if isinstance(row, dict) and row.get("sample_type") == "matching_darkframe_topup"
    ]
    missing = sum(int(group["minimum_additional_count"]) for group in groups)
    enough_unproven = [
        str(group["requirement_id"])
        for group in groups
        if group["enough_candidate_sources"] and not group["source_provenance_manifest_ready"]
    ]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_capture_request": capture_request_path.as_posix(),
        "production_ready": False,
        "summary": {
            "review_group_count": len(groups),
            "candidate_source_count": sum(int(group["candidate_source_count"]) for group in groups),
            "missing_source_count": sum(int(group["missing_source_count"]) for group in groups),
            "minimum_additional_darkframes_needed": missing,
            "requirements_with_enough_candidates_but_missing_provenance": enough_unproven,
            "requirements_still_needing_capture": [
                str(group["requirement_id"])
                for group in groups
                if int(group["minimum_additional_count"]) > 0
            ],
            "production_sidecar_ready": False,
        },
        "policy": {
            "candidate_dark_appearance_is_not_proven_noise": True,
            "promotion_requires_no_scene_signal_true": True,
            "promotion_requires_u16_bayer_extraction_receipts": True,
            "promotion_requires_build_camera_noise_calibration_require_source_provenance": True,
        },
        "groups": groups,
    }


def render_html(data: dict[str, Any]) -> str:
    cards = [
        ("Review groups", data["summary"]["review_group_count"]),
        ("Candidate sources", data["summary"]["candidate_source_count"]),
        ("Additional darkframes needed", data["summary"]["minimum_additional_darkframes_needed"]),
        ("Production ready", data["production_ready"]),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    sections = []
    for group in data["groups"]:
        rows = "\n".join(
            "<tr>"
            f"<td><code>{html.escape(str(row['original_path']))}</code></td>"
            f"<td>{html.escape(str(row['exists']).lower())}</td>"
            f"<td>{html.escape(str(row.get('bytes') or ''))}</td>"
            f"<td><code>{html.escape(str(row.get('original_sha256') or 'missing'))}</code></td>"
            "</tr>"
            for row in group["candidates"]
        )
        sections.append(
            f"""<section class="panel">
<h2>{html.escape(str(group['camera']))}: {html.escape(str(group['existing_group']))}</h2>
<p><strong>Requirement:</strong> <code>{html.escape(str(group['requirement_id']))}</code></p>
<p><strong>Next action:</strong> {html.escape(str(group['next_action']))}</p>
<table><thead><tr><th>Original source</th><th>Exists</th><th>Bytes</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table>
</section>"""
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Darkframe Provenance Review Packet</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; max-width: 920px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 22px 0; }}
.card, .panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; margin: 14px 0; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin-top: 12px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ white-space: normal; overflow-wrap: anywhere; }}
</style></head><body><main>
<h1>Darkframe Provenance Review Packet</h1>
<p class="sub">This packet hashes the lowest-lift darkframe candidates from the raw-stills capture request. It is not a production sidecar. Promotion still requires no-scene-signal confirmation, extracted uint16 Bayer frames, extraction receipts, and <code>build_camera_noise_calibration.py --require-source-provenance</code>.</p>
<div class="grid">{card_html}</div>
{''.join(sections)}
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    data = build_packet(load_json(args.capture_request), args.capture_request)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "darkframe_provenance_review_packet.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
