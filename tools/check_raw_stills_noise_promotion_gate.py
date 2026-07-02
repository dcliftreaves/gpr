#!/usr/bin/env python3
"""Check the RAW-stills camera-noise promotion boundary.

This guard sits above the lower-level coverage/runtime/darkframe builders.  It
verifies the product-facing rule that nonzero noise removal/addback may be
claimed only for camera families with validated sidecars, and that
Mission/iPhone remain metadata-only until strict-provenance darkframe sidecars
exist.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_stills_noise_promotion_gate.v1"
READINESS_SCHEMA = "gpr.raw_stills_noise_sidecar_readiness.v1"
DEFAULT_READINESS = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/raw_stills_noise_sidecar_readiness_20260701/"
    "raw_stills_noise_sidecar_readiness.json"
)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def as_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else bool(value)


def rows_by_key(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = readiness.get("camera_readiness") or []
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, dict) and row.get("camera_key"):
            out[str(row["camera_key"])] = row
    return out


def validate_readiness(
    path: Path,
    readiness: dict[str, Any],
    expected_ready: list[str],
    expected_blocked: list[str],
) -> dict[str, Any]:
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    rows = rows_by_key(readiness)
    blockers: list[str] = []

    if readiness.get("schema") != READINESS_SCHEMA:
        blockers.append("readiness schema mismatch")
    if not as_bool(summary.get("source_consistency_ok")):
        blockers.append("readiness source consistency is not OK")
    if int(summary.get("source_consistency_error_count") or 0) != 0:
        blockers.append("readiness has source consistency errors")
    if not as_bool(summary.get("all_real_bayer_phases_ready")):
        blockers.append("real Bayer phase coverage is not closed")

    ready_keys = sorted(str(v) for v in summary.get("production_ready_camera_keys") or [])
    blocked_keys = sorted(str(v) for v in summary.get("blocked_camera_keys") or [])
    if sorted(expected_ready) != ready_keys:
        blockers.append(f"ready camera set changed: expected {sorted(expected_ready)}, got {ready_keys}")
    if sorted(expected_blocked) != blocked_keys:
        blockers.append(f"blocked camera set changed: expected {sorted(expected_blocked)}, got {blocked_keys}")

    for key in expected_ready:
        row = rows.get(key)
        if not row:
            blockers.append(f"{key}: missing readiness row")
            continue
        if row.get("production_ready") is not True:
            blockers.append(f"{key}: production_ready is not true")
        if row.get("runtime_nonzero_noise_addback_enabled") is not True:
            blockers.append(f"{key}: nonzero noise addback is not enabled despite expected ready status")
        if row.get("runtime_mode") != "calibrated_sidecar_required":
            blockers.append(f"{key}: runtime mode is not calibrated_sidecar_required")
        if not row.get("ready_isos"):
            blockers.append(f"{key}: no ready ISO sidecars listed")

    for key in expected_blocked:
        row = rows.get(key)
        if not row:
            blockers.append(f"{key}: missing readiness row")
            continue
        if row.get("production_ready") is not False:
            blockers.append(f"{key}: production_ready is not false")
        if row.get("runtime_nonzero_noise_addback_enabled") is not False:
            blockers.append(f"{key}: nonzero noise addback is enabled while blocked")
        if row.get("runtime_policy_declares_nonzero_noise_addback") is not False:
            blockers.append(f"{key}: runtime policy declares nonzero addback while blocked")
        if row.get("runtime_mode") != "metadata_conditioning_only":
            blockers.append(f"{key}: runtime mode is not metadata_conditioning_only")
        if not row.get("requirement_id"):
            blockers.append(f"{key}: missing capture requirement id")
        if not row.get("blocker"):
            blockers.append(f"{key}: missing blocker explanation")

    expected_open = sorted(
        str(rows[key].get("requirement_id"))
        for key in expected_blocked
        if key in rows and rows[key].get("requirement_id")
    )
    actual_open = sorted(str(v) for v in summary.get("open_requirement_ids") or [])
    if expected_open != actual_open:
        blockers.append(f"open requirement ids changed: expected {expected_open}, got {actual_open}")

    if bool(summary.get("mission_iphone_noise_addback_enabled")):
        blockers.append("Mission/iPhone noise addback is claimed enabled")
    if bool(summary.get("production_raw_stills_noise_ready")):
        blockers.append("raw-stills noise is claimed fully production-ready despite blocked cameras")
    if not bool(summary.get("nonzero_noise_addback_must_remain_disabled_for_blocked_cameras")):
        blockers.append("blocked-camera nonzero addback disable rule is not asserted")

    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": readiness.get("schema"),
        "summary": {
            "production_ready_camera_keys": ready_keys,
            "blocked_camera_keys": blocked_keys,
            "open_requirement_ids": actual_open,
            "mission_iphone_noise_addback_enabled": summary.get("mission_iphone_noise_addback_enabled"),
            "production_raw_stills_noise_ready": summary.get("production_raw_stills_noise_ready"),
            "source_consistency_ok": summary.get("source_consistency_ok"),
            "all_real_bayer_phases_ready": summary.get("all_real_bayer_phases_ready"),
            "darkframe_like_count": int(summary.get("darkframe_like_count") or 0),
            "production_stack_ready_group_count": int(summary.get("production_stack_ready_group_count") or 0),
        },
        "camera_rows": [rows[key] for key in sorted(rows)],
        "policy_pass": not blockers,
        "blockers": blockers,
    }


def render_html(receipt: dict[str, Any]) -> str:
    readiness = receipt["readiness"]
    summary = readiness["summary"]
    cards = [
        ("Promotion safe", receipt["promotion_safe"]),
        ("Ready", ", ".join(summary["production_ready_camera_keys"]) or "none"),
        ("Blocked", ", ".join(summary["blocked_camera_keys"]) or "none"),
        ("Open requirements", ", ".join(summary["open_requirement_ids"]) or "none"),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value)).lower()}</div>"
        "</section>"
        for label, value in cards
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('label') or row.get('camera_key')))}</td>"
        f"<td>{'ready' if row.get('production_ready') else 'blocked'}</td>"
        f"<td>{'yes' if row.get('runtime_nonzero_noise_addback_enabled') else 'no'}</td>"
        f"<td>{html.escape(str(row.get('runtime_mode') or ''))}</td>"
        f"<td>{html.escape(', '.join(str(v) for v in row.get('ready_isos') or []))}</td>"
        f"<td>{html.escape(str(row.get('requirement_id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('blocker') or ''))}</td>"
        "</tr>"
        for row in readiness["camera_rows"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in receipt["blockers"])
    if not blockers:
        blockers = "<li>None. Current promotion boundary is internally consistent.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>RAW Stills Noise Promotion Gate</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #121820; background: #f6f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; }}
.sub {{ color: #5c6773; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style></head><body><main>
<h1>RAW Stills Noise Promotion Gate</h1>
<p class="sub">Validates that calibrated nonzero noise removal/addback is claimed only for camera families with production sidecars, while Mission 1 and iPhone remain metadata-only until strict-provenance darkframes are promoted.</p>
<div class="grid">{card_html}</div>
<h2>Decision</h2>
<p>{html.escape(receipt["decision"])}</p>
<h2>Blockers</h2>
<ul>{blockers}</ul>
<h2>Camera Rows</h2>
<table><tr><th>camera</th><th>status</th><th>effective addback</th><th>runtime mode</th><th>ready ISOs</th><th>requirement</th><th>blocker</th></tr>{rows}</table>
<h2>Source</h2>
<p><code>{html.escape(readiness["path"])}</code></p>
</main></body></html>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    readiness = validate_readiness(
        args.readiness,
        load_json(args.readiness),
        args.expect_ready_camera,
        args.expect_blocked_camera,
    )
    blockers = list(readiness["blockers"])
    promotion_safe = not blockers
    decision = (
        "current RAW-stills noise promotion boundary is safe: X2D/Z8 sidecars are enabled and "
        "Mission/iPhone nonzero addback remains blocked"
        if promotion_safe
        else "RAW-stills noise promotion boundary is not safe; fix readiness evidence or product claims"
    )
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "promotion_safe": promotion_safe,
        "production_ready": bool(readiness["summary"]["production_raw_stills_noise_ready"]),
        "decision": decision,
        "expected_ready_cameras": sorted(args.expect_ready_camera),
        "expected_blocked_cameras": sorted(args.expect_blocked_camera),
        "readiness": readiness,
        "blockers": blockers,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_stills_noise_promotion_gate.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": json_path.as_posix(),
                "dashboard": html_path.as_posix(),
                "promotion_safe": promotion_safe,
                "production_ready": receipt["production_ready"],
            },
            indent=2,
        )
    )
    if args.require_promotion_safe and not promotion_safe:
        return receipt | {"_exit_code": 1}
    return receipt | {"_exit_code": 0}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--expect-ready-camera", action="append", default=["x2d", "z8"])
    ap.add_argument("--expect-blocked-camera", action="append", default=["iphone", "mission1"])
    ap.add_argument("--require-promotion-safe", action="store_true")
    return ap.parse_args()


def main() -> int:
    return int(build(parse_args()).get("_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
