#!/usr/bin/env python3
"""Build a Mission 1 native high/low candidate-pair inventory.

The current PSF work has modeled 50MP-to-12MP pairs. This audit looks for real
Mission 1 captures where native 8192x6144 and native 4096x3072 Bayer frames are
close enough in time to become calibration candidates for a native PSF
measurement pass.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_MEDIA_SUMMARY = DEFAULT_EXTERNAL_ROOT / "artifacts/mission1p_source_scan_20260616/media_summary.json"
DEFAULT_RAW50_DIR = DEFAULT_EXTERNAL_ROOT / "artifacts/mission1p_source_scan_20260616/raw50_decode"
DEFAULT_RAW12_DIR = DEFAULT_EXTERNAL_ROOT / "artifacts/mission1p_source_scan_20260616/raw12_decode"
SCHEMA = "gpr.mission1_native_psf_pair_inventory.v1"
HIGH_DIMS = (8192, 6144)
LOW_DIMS = (4096, 3072)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_record(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("model", {}).get("GPR") != "MISSION 1":
        return None
    dims = row.get("dims", {}).get("GPR") or row.get("dims", {}).get("DNG") or row.get("dims", {}).get("JPEG")
    if not isinstance(dims, list) or len(dims) != 2:
        return None
    width, height = int(dims[0]), int(dims[1])
    if (width, height) not in (HIGH_DIMS, LOW_DIMS):
        return None
    dt = parse_dt((row.get("datetime") or {}).get("GPR") or (row.get("datetime") or {}).get("DNG") or (row.get("datetime") or {}).get("JPEG"))
    return {
        "stem": row.get("stem"),
        "kind": "high" if (width, height) == HIGH_DIMS else "low",
        "width": width,
        "height": height,
        "datetime": dt.isoformat() if dt else None,
        "_dt": dt,
        "iso": parse_float((row.get("iso") or {}).get("GPR") or (row.get("iso") or {}).get("DNG") or (row.get("iso") or {}).get("JPEG")),
        "files": row.get("files") or {},
        "types": row.get("types") or [],
    }


def raw_status(record: dict[str, Any], raw50_dir: Path, raw12_dir: Path) -> dict[str, Any]:
    stem = str(record["stem"])
    path = (raw50_dir if record["kind"] == "high" else raw12_dir) / f"{stem}.raw"
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else None,
    }


def build_inventory(
    media_summary: Path,
    raw50_dir: Path,
    raw12_dir: Path,
    max_delta_s: float,
) -> dict[str, Any]:
    data = json.loads(media_summary.read_text(encoding="utf-8"))
    rows = [canonical_record(row) for row in data.get("stems", []) if isinstance(row, dict)]
    records = [row for row in rows if row]
    highs = [row for row in records if row["kind"] == "high"]
    lows = [row for row in records if row["kind"] == "low"]

    for row in records:
        row["decoded_raw"] = raw_status(row, raw50_dir, raw12_dir)

    candidates: list[dict[str, Any]] = []
    for low in lows:
        if low.get("_dt") is None:
            continue
        for high in highs:
            if high.get("_dt") is None:
                continue
            delta = abs((high["_dt"] - low["_dt"]).total_seconds())
            if delta > max_delta_s:
                continue
            high_raw = high["decoded_raw"]
            low_raw = low["decoded_raw"]
            iso_low = low.get("iso")
            iso_high = high.get("iso")
            iso_ratio = None
            if iso_low and iso_high and iso_low > 0 and iso_high > 0:
                iso_ratio = max(iso_low, iso_high) / min(iso_low, iso_high)
            production_candidate = (
                high_raw["exists"]
                and low_raw["exists"]
                and math.isclose(high["width"] / low["width"], 2.0)
                and math.isclose(high["height"] / low["height"], 2.0)
            )
            candidates.append(
                {
                    "low_stem": low["stem"],
                    "high_stem": high["stem"],
                    "time_delta_s": delta,
                    "low_datetime": low["datetime"],
                    "high_datetime": high["datetime"],
                    "low_iso": iso_low,
                    "high_iso": iso_high,
                    "iso_ratio": iso_ratio,
                    "high_raw": high_raw,
                    "low_raw": low_raw,
                    "production_candidate": production_candidate,
                    "notes": "candidate for native high/low PSF measurement; still requires alignment, texture/edge selection, and measured PSF receipt",
                }
            )
    candidates.sort(key=lambda row: (row["time_delta_s"], row["low_stem"], row["high_stem"]))

    best_by_low: dict[str, dict[str, Any]] = {}
    for row in candidates:
        best_by_low.setdefault(str(row["low_stem"]), row)

    for row in records:
        row.pop("_dt", None)

    best = list(best_by_low.values())
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "media_summary": str(media_summary),
        "raw50_dir": str(raw50_dir),
        "raw12_dir": str(raw12_dir),
        "max_delta_s": max_delta_s,
        "summary": {
            "mission1_high_count": len(highs),
            "mission1_low_count": len(lows),
            "candidate_pair_count": len(candidates),
            "best_pair_count": len(best),
            "decoded_candidate_pair_count": sum(1 for row in candidates if row["production_candidate"]),
            "native_psf_ready": False,
            "production_ready": False,
        },
        "blockers": [
            "Candidate pairs are near-time captures, not aligned same-moment calibration pairs.",
            "No edge/texture tile selection has been run against these native high/low candidates.",
            "No measured native PSF kernel or PSF-conditioned model gate exists yet.",
        ],
        "next_actions": [
            "Render or demosaic candidate pairs for visual scene matching and reject scene-change pairs.",
            "Run alignment and sharp-edge/texture-field mining on the best near-time candidates.",
            "Estimate a native high-to-low Bayer/RGB PSF receipt and compare it with the current modeled same-color 2x box receipt.",
            "Train/gate a PSF-conditioned 4K cleanup or 8K SR candidate only after the measured PSF receipt exists.",
        ],
        "records": records,
        "candidate_pairs": candidates,
        "best_pairs_by_low": best,
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    cards = [
        ("High captures", summary["mission1_high_count"]),
        ("Low captures", summary["mission1_low_count"]),
        ("Candidate pairs", summary["candidate_pair_count"]),
        ("Decoded candidates", summary["decoded_candidate_pair_count"]),
        ("Native PSF ready", str(summary["native_psf_ready"]).lower()),
    ]
    card_html = "\n".join(
        f'<section class="card"><div class="k">{html.escape(str(k))}</div><div class="v">{html.escape(str(v))}</div></section>'
        for k, v in cards
    )
    pair_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['low_stem']))}</td>"
        f"<td>{html.escape(str(row['high_stem']))}</td>"
        f"<td>{row['time_delta_s']:.1f}</td>"
        f"<td>{html.escape(str(row.get('low_iso')))}</td>"
        f"<td>{html.escape(str(row.get('high_iso')))}</td>"
        f"<td class=\"{'pass' if row['production_candidate'] else 'fail'}\">{str(row['production_candidate']).lower()}</td>"
        "</tr>"
        for row in data["candidate_pairs"][:80]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    next_actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mission 1 Native PSF Pair Inventory</title>
  <style>
    body {{ margin: 0; background: #f4f6f7; color: #101820; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 36px; }}
    h2 {{ margin: 24px 0 10px; }}
    .sub {{ color: #53606d; max-width: 850px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
    .k {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .v {{ font-size: 26px; font-weight: 760; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
    th, td {{ padding: 9px; border-bottom: 1px solid #e6ebef; text-align: left; }}
    th {{ color: #53606d; font-size: 12px; text-transform: uppercase; }}
    .pass {{ color: #16794c; font-weight: 760; }}
    .fail {{ color: #a33a32; font-weight: 760; }}
    .panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body><main>
  <h1>Mission 1 Native PSF Pair Inventory</h1>
  <p class="sub">Near-time native 8192x6144 and 4096x3072 Mission 1 captures are candidate inputs for a measured native PSF pass. This is an input audit, not a completed PSF receipt.</p>
  <div class="grid">{card_html}</div>
  <h2>Candidate Pairs</h2>
  <table><thead><tr><th>low</th><th>high</th><th>delta s</th><th>low ISO</th><th>high ISO</th><th>decoded raw</th></tr></thead><tbody>{pair_rows}</tbody></table>
  <h2>Blockers</h2><section class="panel"><ul>{blockers}</ul></section>
  <h2>Next Actions</h2><section class="panel"><ul>{next_actions}</ul></section>
  <p class="meta">Generated {html.escape(data['created_utc'])}. Media summary: {html.escape(data['media_summary'])}.</p>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--media-summary", type=Path, default=DEFAULT_MEDIA_SUMMARY)
    ap.add_argument("--raw50-dir", type=Path, default=DEFAULT_RAW50_DIR)
    ap.add_argument("--raw12-dir", type=Path, default=DEFAULT_RAW12_DIR)
    ap.add_argument("--max-delta-s", type=float, default=30.0)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = build_inventory(args.media_summary, args.raw50_dir, args.raw12_dir, args.max_delta_s)
    (args.output_dir / "inventory.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(args.output_dir / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
