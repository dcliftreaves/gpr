#!/usr/bin/env python3
"""Build the current raw-stills noise blocker audit.

This is a closure aide for the remaining Mission 1 and iPhone camera-noise
sidecar work. It does not promote candidate-discovery files into production
darkframes; it records whether the known local source roots contain enough
same-camera/same-ISO candidate frames and what evidence is still missing.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_stills_noise_blocker_audit.v1"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_inventory(path: Path) -> list[Path]:
    return [Path(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stem_without_raw_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".dng", ".gpr"}:
        return path.stem
    return path.name


def mission_inventory_summary(paths: list[Path]) -> dict[str, Any]:
    dng = [p for p in paths if p.suffix.lower() == ".dng"]
    gpr = [p for p in paths if p.suffix.lower() == ".gpr"]
    dng_stems = {stem_without_raw_suffix(p) for p in dng}
    gpr_stems = {stem_without_raw_suffix(p) for p in gpr}
    return {
        "raw_file_count": len(paths),
        "dng_count": len(dng),
        "gpr_count": len(gpr),
        "matched_dng_gpr_stem_count": len(dng_stems & gpr_stems),
        "dng_without_gpr_stems": sorted(dng_stems - gpr_stems),
        "gpr_without_dng_stems": sorted(gpr_stems - dng_stems),
        "unique_frame_stem_count": len(dng_stems | gpr_stems),
        "adds_unique_mission_frames_beyond_dng": bool(gpr_stems - dng_stems),
    }


def group_by_key(audit: dict[str, Any], key: str) -> dict[str, Any] | None:
    for group in audit.get("stack_groups", []):
        if isinstance(group, dict) and group.get("key") == key:
            return group
    return None


def top_groups(audit: dict[str, Any], prefix: str, limit: int = 8) -> list[dict[str, Any]]:
    groups = [
        group
        for group in audit.get("stack_groups", [])
        if isinstance(group, dict) and str(group.get("key", "")).startswith(prefix)
    ]
    groups.sort(key=lambda row: int(row.get("candidate_count") or 0), reverse=True)
    return [
        {
            "key": group.get("key"),
            "candidate_count": group.get("candidate_count"),
            "candidate_stack_ready": bool(group.get("candidate_stack_ready")),
            "production_stack_ready": bool(group.get("production_stack_ready")),
            "paths": group.get("paths", []),
        }
        for group in groups[:limit]
    ]


def build(args: argparse.Namespace) -> dict[str, Any]:
    mission_inventory_paths = read_inventory(args.mission_inventory)
    mission_audit = load_json(args.mission_audit)
    full_audit = load_json(args.fullmanifest_audit)
    packet = load_json(args.provenance_packet)
    extraction_progress = load_json(args.extraction_progress)

    mission_summary = mission_inventory_summary(mission_inventory_paths)
    mission_iso232 = group_by_key(mission_audit, "GoPro|MISSION 1|ISO232|RGGB") or {}
    iphone_iso1250 = group_by_key(full_audit, "Apple|iPhone 7 Plus|ISO1250|RGGB") or {}
    mission_candidate_count = int(mission_iso232.get("candidate_count") or 0)
    iphone_candidate_count = int(iphone_iso1250.get("candidate_count") or 0)
    mission_needed = max(0, 4 - mission_candidate_count)

    return {
        "schema": SCHEMA,
        "created_utc": args.created_utc
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "inputs": {
            "mission_inventory": args.mission_inventory.as_posix(),
            "mission_inventory_sha256": sha256(args.mission_inventory),
            "mission_audit": args.mission_audit.as_posix(),
            "mission_audit_sha256": sha256(args.mission_audit),
            "fullmanifest_audit": args.fullmanifest_audit.as_posix(),
            "fullmanifest_audit_sha256": sha256(args.fullmanifest_audit),
            "provenance_packet": args.provenance_packet.as_posix(),
            "provenance_packet_sha256": sha256(args.provenance_packet),
            "extraction_progress": args.extraction_progress.as_posix(),
            "extraction_progress_sha256": sha256(args.extraction_progress),
        },
        "summary": {
            "production_ready": False,
            "mission_inventory_exhausted": True,
            "mission_known_unique_frame_count": mission_summary["unique_frame_stem_count"],
            "mission_iso232_candidate_count": mission_candidate_count,
            "mission_additional_matching_darkframes_needed": mission_needed,
            "iphone_iso1250_candidate_count": iphone_candidate_count,
            "iphone_candidate_count_is_sufficient": iphone_candidate_count >= 4,
            "extracted_frame_count": extraction_progress.get("extracted_frame_count"),
            "mission1_extracted_count": extraction_progress.get("mission1_extracted_count"),
            "iphone_extracted_count": extraction_progress.get("iphone_extracted_count"),
            "packet_candidate_source_count": (packet.get("summary") or {}).get("candidate_source_count"),
            "packet_production_sidecar_ready": bool((packet.get("summary") or {}).get("production_sidecar_ready")),
        },
        "mission1": {
            "inventory": mission_summary,
            "best_group": {
                "key": mission_iso232.get("key"),
                "candidate_count": mission_candidate_count,
                "paths": mission_iso232.get("paths", []),
                "candidate_stack_ready": bool(mission_iso232.get("candidate_stack_ready")),
                "production_stack_ready": bool(mission_iso232.get("production_stack_ready")),
            },
            "top_groups": top_groups(mission_audit, "GoPro|MISSION 1|"),
            "next_action": (
                "Capture two more matching ISO232 RGGB true darkframes, or recapture a fresh four-frame same-settings "
                "Mission 1 darkframe stack. The known local 49-frame Mission DNG set is exhausted; the matching GPR "
                "files do not add unique frames."
            ),
        },
        "iphone": {
            "best_group": {
                "key": iphone_iso1250.get("key"),
                "candidate_count": iphone_candidate_count,
                "paths": iphone_iso1250.get("paths", []),
                "candidate_stack_ready": bool(iphone_iso1250.get("candidate_stack_ready")),
                "production_stack_ready": bool(iphone_iso1250.get("production_stack_ready")),
            },
            "top_groups": top_groups(full_audit, "Apple|iPhone 7 Plus|"),
            "next_action": (
                "Confirm no-scene-signal provenance for four ISO1250 RGGB CFA candidates, or recapture four true "
                "iPhone CFA darkframes. Candidate statistics alone are not enough for production noise addback."
            ),
        },
        "remaining_blockers": [
            "Mission 1 lacks a four-frame same-ISO true-dark stack in the known local source root.",
            "iPhone has enough dark-like CFA candidates but lacks no-scene-signal provenance.",
            "Neither Mission 1 nor iPhone may enable nonzero production noise addback until source provenance and camera-noise sidecar validation pass.",
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    def table(rows: list[tuple[str, Any]]) -> str:
        body = "\n".join(
            f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(json.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v))}</td></tr>"
            for k, v in rows
        )
        return f"<table>{body}</table>"

    summary = data["summary"]
    mission = data["mission1"]
    iphone = data["iphone"]
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in data["remaining_blockers"])
    mission_groups = "".join(
        f"<tr><td>{html.escape(str(g['key']))}</td><td>{g['candidate_count']}</td><td>{g['candidate_stack_ready']}</td><td>{g['production_stack_ready']}</td></tr>"
        for g in mission["top_groups"]
    )
    iphone_groups = "".join(
        f"<tr><td>{html.escape(str(g['key']))}</td><td>{g['candidate_count']}</td><td>{g['candidate_stack_ready']}</td><td>{g['production_stack_ready']}</td></tr>"
        for g in iphone["top_groups"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>RAW Stills Noise Blocker Audit</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
h1, h2 {{ margin-bottom: 0.25rem; }}
.sub {{ color: #52616f; margin-top: 0; }}
.status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; background: #fff3cd; color: #6b4e00; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0 28px; }}
th, td {{ border: 1px solid #d8dee4; padding: 8px 10px; text-align: left; vertical-align: top; }}
th {{ background: #f6f8fa; width: 260px; }}
code, pre {{ background: #f6f8fa; padding: 2px 4px; border-radius: 3px; }}
</style>
</head>
<body>
<h1>RAW Stills Noise Blocker Audit</h1>
<p class="sub">Generated {html.escape(data['created_utc'])}. This is a blocker audit, not a production sidecar promotion.</p>
<p><span class="status">production_ready={str(summary['production_ready']).lower()}</span></p>
<h2>Summary</h2>
{table(list(summary.items()))}
<h2>Mission 1</h2>
{table([('next_action', mission['next_action']), ('inventory', mission['inventory']), ('best_group', mission['best_group'])])}
<table><tr><th>group</th><th>candidates</th><th>candidate stack ready</th><th>production ready</th></tr>{mission_groups}</table>
<h2>iPhone CFA</h2>
{table([('next_action', iphone['next_action']), ('best_group', iphone['best_group'])])}
<table><tr><th>group</th><th>candidates</th><th>candidate stack ready</th><th>production ready</th></tr>{iphone_groups}</table>
<h2>Remaining Blockers</h2>
<ul>{blockers}</ul>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-inventory", type=Path, required=True)
    parser.add_argument("--mission-audit", type=Path, required=True)
    parser.add_argument("--fullmanifest-audit", type=Path, required=True)
    parser.add_argument("--provenance-packet", type=Path, required=True)
    parser.add_argument("--extraction-progress", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--created-utc", help="Fixed timestamp for reproducible release artifacts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = build(args)
    (args.output_dir / "raw_stills_noise_blocker_audit.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(args.output_dir / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
