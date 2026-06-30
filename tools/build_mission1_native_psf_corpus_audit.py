#!/usr/bin/env python3
"""Audit whether the local Mission 1 corpus can close the native PSF gap."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_native_psf_corpus_audit.v1"
DEFAULT_MEDIA_SUMMARY = Path("/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/media_summary.json")
DEFAULT_PAIR_INVENTORY = Path("/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630/inventory.json")
DEFAULT_MEASUREMENT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/native_psf_measurement.json")
DEFAULT_CAPTURE_REQUEST = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_capture_request_20260630/raw_video_psf_capture_request.json")

HIGH_DIMS = (8192, 6144)
LOW_DIMS = (4096, 3072)
HIGH_BYTES = HIGH_DIMS[0] * HIGH_DIMS[1] * 2
LOW_BYTES = LOW_DIMS[0] * LOW_DIMS[1] * 2


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--media-summary", type=Path, default=DEFAULT_MEDIA_SUMMARY)
    ap.add_argument("--pair-inventory", type=Path, default=DEFAULT_PAIR_INVENTORY)
    ap.add_argument("--measurement", type=Path, default=DEFAULT_MEASUREMENT)
    ap.add_argument("--capture-request", type=Path, default=DEFAULT_CAPTURE_REQUEST)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--hash-files", action="store_true", help="hash candidate source and decoded raw files")
    ap.add_argument("--iso-ratio-max", type=float, default=1.02)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def int_at(data: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return int(cur) if isinstance(cur, (int, float)) else default


def bool_at(data: dict[str, Any], keys: tuple[str, ...], default: bool = False) -> bool:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if isinstance(cur, bool) else default


def stem_map(media_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in media_summary.get("stems", []):
        if isinstance(row, dict) and row.get("stem"):
            rows[str(row["stem"])] = row
    return rows


def source_path(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    files = row.get("files") if isinstance(row.get("files"), dict) else {}
    return files.get("DNG") or files.get("GPR")


def dims_for(row: dict[str, Any] | None) -> list[int] | None:
    if not row:
        return None
    dims = row.get("dims") if isinstance(row.get("dims"), dict) else {}
    value = dims.get("DNG") or dims.get("GPR") or dims.get("JPEG")
    return value if isinstance(value, list) and len(value) == 2 else None


def pair_audit(
    pair: dict[str, Any],
    stems: dict[str, dict[str, Any]],
    *,
    hash_files: bool,
    iso_ratio_max: float,
) -> dict[str, Any]:
    high_stem = str(pair.get("high_stem") or "")
    low_stem = str(pair.get("low_stem") or "")
    high_media = stems.get(high_stem)
    low_media = stems.get(low_stem)
    high_source = source_path(high_media)
    low_source = source_path(low_media)
    high_raw = pair.get("high_raw") if isinstance(pair.get("high_raw"), dict) else {}
    low_raw = pair.get("low_raw") if isinstance(pair.get("low_raw"), dict) else {}
    high_raw_path = Path(str(high_raw.get("path") or ""))
    low_raw_path = Path(str(low_raw.get("path") or ""))
    high_raw_bytes = int(high_raw.get("bytes") or 0)
    low_raw_bytes = int(low_raw.get("bytes") or 0)
    iso_ratio = pair.get("iso_ratio")
    iso_fixed_proxy = isinstance(iso_ratio, (int, float)) and float(iso_ratio) <= iso_ratio_max
    high_dims = dims_for(high_media)
    low_dims = dims_for(low_media)
    high_source_path = Path(high_source) if high_source else None
    low_source_path = Path(low_source) if low_source else None
    high_source_exists = bool(high_source_path and high_source_path.exists())
    low_source_exists = bool(low_source_path and low_source_path.exists())

    high_source_sha = sha256_file(high_source_path) if hash_files and high_source_path else None
    low_source_sha = sha256_file(low_source_path) if hash_files and low_source_path else None
    high_raw_sha = sha256_file(high_raw_path) if hash_files else None
    low_raw_sha = sha256_file(low_raw_path) if hash_files else None
    source_hashes_ready = bool(high_source_sha and low_source_sha) if hash_files else bool(high_source_exists and low_source_exists)
    decoded_hashes_ready = bool(high_raw_sha and low_raw_sha) if hash_files else bool(high_raw_path.exists() and low_raw_path.exists())
    expected_decoded_bytes = high_raw_bytes == HIGH_BYTES and low_raw_bytes == LOW_BYTES
    expected_dims = high_dims == list(HIGH_DIMS) and low_dims == list(LOW_DIMS)

    # The current media summary does not carry WB/lens/stabilization/sharpening
    # state. Treat that as missing metadata even when ISO/time/dimensions match.
    fixed_camera_settings_complete = False
    strict_ready = all(
        [
            bool(pair.get("production_candidate")),
            source_hashes_ready,
            decoded_hashes_ready,
            expected_decoded_bytes,
            expected_dims,
            iso_fixed_proxy,
            fixed_camera_settings_complete,
        ]
    )
    return {
        "low_stem": low_stem,
        "high_stem": high_stem,
        "time_delta_s": pair.get("time_delta_s"),
        "iso_ratio": iso_ratio,
        "iso_fixed_proxy": iso_fixed_proxy,
        "high_source_path": str(high_source_path) if high_source_path else None,
        "low_source_path": str(low_source_path) if low_source_path else None,
        "high_source_sha256": high_source_sha,
        "low_source_sha256": low_source_sha,
        "high_raw_path": str(high_raw_path),
        "low_raw_path": str(low_raw_path),
        "high_raw_sha256": high_raw_sha,
        "low_raw_sha256": low_raw_sha,
        "source_hashes_ready": source_hashes_ready,
        "decoded_raw_hashes_ready": decoded_hashes_ready,
        "expected_decoded_bytes": expected_decoded_bytes,
        "expected_source_dims": expected_dims,
        "fixed_camera_settings_complete": fixed_camera_settings_complete,
        "strict_controlled_pair_ready": strict_ready,
        "missing": [
            label
            for label, ok in (
                ("source hashes", source_hashes_ready),
                ("decoded raw hashes", decoded_hashes_ready),
                ("expected decoded bytes", expected_decoded_bytes),
                ("expected source dimensions", expected_dims),
                (f"ISO ratio <= {iso_ratio_max:.3f}", iso_fixed_proxy),
                ("fixed WB/lens/stabilization/sharpening metadata", fixed_camera_settings_complete),
            )
            if not ok
        ],
    }


def build_audit(
    media_summary_path: Path,
    pair_inventory_path: Path,
    measurement_path: Path,
    capture_request_path: Path,
    *,
    hash_files: bool,
    iso_ratio_max: float,
) -> dict[str, Any]:
    media_summary = load_json(media_summary_path)
    inventory = load_json(pair_inventory_path)
    measurement = load_json(measurement_path)
    capture_request = load_json(capture_request_path)
    stems = stem_map(media_summary)
    pairs = [
        pair_audit(pair, stems, hash_files=hash_files, iso_ratio_max=iso_ratio_max)
        for pair in inventory.get("candidate_pairs", [])
        if isinstance(pair, dict)
    ]

    strict_pairs = [row for row in pairs if row["strict_controlled_pair_ready"]]
    accepted_pairs = int_at(measurement, ("summary", "accepted_pair_count"))
    kernel_stable = bool_at(measurement, ("summary", "kernel_stable"))
    native_psf_ready = bool_at(measurement, ("native_psf_ready_for_model_conditioning"))
    minimum_new_pairs = int_at(capture_request, ("summary", "minimum_new_controlled_pair_count"), 3)
    negative_controls_required = bool_at(capture_request, ("promotion_policy", "pair_promotion_requires_negative_controls"))
    source_hash_policy = bool_at(capture_request, ("promotion_policy", "pair_promotion_requires_source_hashes_and_decoded_raw_hashes"))
    fixed_settings_policy = bool_at(capture_request, ("promotion_policy", "pair_promotion_requires_fixed_camera_settings"))

    blockers: list[str] = []
    if len(strict_pairs) < 3:
        blockers.append(f"Only {len(strict_pairs)} strict controlled pairs are available; at least 3 are required.")
    if accepted_pairs < 3:
        blockers.append(f"Existing measurement accepted {accepted_pairs} pairs; at least 3 are required.")
    if not kernel_stable:
        blockers.append("Existing near-time measurement produced an unstable native kernel.")
    if negative_controls_required:
        blockers.append("The current local corpus has no marked negative-control pairs for measurement rejection testing.")
    if fixed_settings_policy:
        blockers.append("The current media summary lacks fixed WB/lens/stabilization/sharpening metadata for candidate pairs.")
    if source_hash_policy and not hash_files:
        blockers.append("Run with --hash-files to emit source and decoded raw hashes for candidate pairs.")

    local_corpus_can_close = len(strict_pairs) >= 3 and accepted_pairs >= 3 and kernel_stable and native_psf_ready
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_ready": False,
        "local_corpus_can_close_psf_gap": local_corpus_can_close,
        "inputs": {
            "media_summary": str(media_summary_path),
            "pair_inventory": str(pair_inventory_path),
            "measurement": str(measurement_path),
            "capture_request": str(capture_request_path),
        },
        "policy": {
            "minimum_strict_controlled_pairs": 3,
            "minimum_new_controlled_pair_count": minimum_new_pairs,
            "iso_ratio_max_for_fixed_iso_proxy": iso_ratio_max,
            "hash_files": hash_files,
            "source_and_decoded_hashes_required": source_hash_policy,
            "fixed_settings_required": fixed_settings_policy,
            "negative_controls_required": negative_controls_required,
        },
        "summary": {
            "mission1_high_count": int_at(inventory, ("summary", "mission1_high_count")),
            "mission1_low_count": int_at(inventory, ("summary", "mission1_low_count")),
            "candidate_pair_count": int_at(inventory, ("summary", "candidate_pair_count"), len(pairs)),
            "decoded_candidate_pair_count": int_at(inventory, ("summary", "decoded_candidate_pair_count")),
            "strict_controlled_pair_count": len(strict_pairs),
            "hashed_candidate_pair_count": sum(1 for row in pairs if row["source_hashes_ready"] and row["decoded_raw_hashes_ready"]),
            "existing_measurement_accepted_pair_count": accepted_pairs,
            "existing_measurement_kernel_stable": kernel_stable,
            "native_psf_ready_for_model_conditioning": native_psf_ready,
        },
        "blockers": blockers,
        "next_actions": [
            "Capture or locate controlled same-scene Mission 1 high/low pairs with fixed camera settings and explicit source/extraction receipts.",
            "Include negative controls that should fail scene/alignment vetting.",
            "Re-run the native PSF measurement only after at least three strict controlled pairs are available.",
        ],
        "candidate_pairs": pairs,
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    cards = [
        ("Can close locally", str(data["local_corpus_can_close_psf_gap"]).lower()),
        ("High captures", summary["mission1_high_count"]),
        ("Low captures", summary["mission1_low_count"]),
        ("Candidate pairs", summary["candidate_pair_count"]),
        ("Strict pairs", summary["strict_controlled_pair_count"]),
        ("Accepted measured", summary["existing_measurement_accepted_pair_count"]),
        ("Kernel stable", str(summary["existing_measurement_kernel_stable"]).lower()),
    ]
    card_html = "\n".join(
        f"<section class='card'><div class='label'>{html.escape(str(k))}</div><div class='value'>{html.escape(str(v))}</div></section>"
        for k, v in cards
    )
    pair_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['low_stem'])}</td>"
        f"<td>{html.escape(row['high_stem'])}</td>"
        f"<td>{html.escape(str(row['time_delta_s']))}</td>"
        f"<td>{html.escape(str(row['iso_ratio']))}</td>"
        f"<td>{html.escape(str(row['source_hashes_ready']).lower())}</td>"
        f"<td>{html.escape(str(row['decoded_raw_hashes_ready']).lower())}</td>"
        f"<td>{html.escape(str(row['strict_controlled_pair_ready']).lower())}</td>"
        f"<td>{html.escape('; '.join(row['missing']))}</td>"
        "</tr>"
        for row in data["candidate_pairs"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Mission 1 Native PSF Corpus Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; max-width: 940px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
.panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
</style></head><body><main>
<h1>Mission 1 Native PSF Corpus Audit</h1>
<p class="sub">This audit checks whether the existing local Mission 1 high/low corpus satisfies the stricter PSF promotion contract: source hashes, decoded Bayer hashes, fixed settings, negative controls, accepted measurement pairs, and stable native kernel.</p>
<div class="grid">{card_html}</div>
<h2>Blockers</h2><section class="panel"><ul>{blockers}</ul></section>
<h2>Candidate Pair Readiness</h2>
<table><thead><tr><th>low</th><th>high</th><th>delta s</th><th>ISO ratio</th><th>source hashes</th><th>decoded hashes</th><th>strict</th><th>missing</th></tr></thead><tbody>{pair_rows}</tbody></table>
<h2>Next Actions</h2><section class="panel"><ul>{actions}</ul></section>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    data = build_audit(
        args.media_summary,
        args.pair_inventory,
        args.measurement,
        args.capture_request,
        hash_files=args.hash_files,
        iso_ratio_max=args.iso_ratio_max,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "mission1_native_psf_corpus_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
