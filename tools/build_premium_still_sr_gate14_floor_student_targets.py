#!/usr/bin/env python3
"""Audit/build Gate14 floor-student raw-CFA targets.

The Gate14 floor-student candidate may only train from target rows that can be
traced back to the Gate14 selector/pseudo-label surface. This tool checks that
identity before creating any training NPZ. If the current raw-CFA targets do not
share row identity with the Gate14 rows, it writes a blocker receipt instead of
silently launching a proxy run.
"""
from __future__ import annotations

import argparse
import html
import json
import time
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by dev env variability
    raise SystemExit("build_premium_still_sr_gate14_floor_student_targets.py requires numpy") from exc


SCHEMA = "gpr.premium_still_sr_gate14_floor_student_targets.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_RAW_TARGETS = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701"
    / "raw_cfa_residual_targets_dedup.npz"
)
DEFAULT_GATE14_PAIRS = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_clean_source_pairs_routed_t64_20260702"
    / "premium_still_sr_clean_source_pairs_routed_t64.npz"
)
DEFAULT_SELECTOR_SIDECAR = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate14_candidate_intake_20260702"
    / "selector_sidecar.json"
)
DEFAULT_SELECTOR_SMOKE = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate14_selector_smoke_20260702"
    / "selector_smoke.json"
)
DEFAULT_LAUNCH_PACKET = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate14_floor_student_launch_packet_20260702"
    / "launch_packet.json"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--raw-targets", type=Path, default=DEFAULT_RAW_TARGETS)
    ap.add_argument("--gate14-pairs", type=Path, default=DEFAULT_GATE14_PAIRS)
    ap.add_argument("--selector-sidecar", type=Path, default=DEFAULT_SELECTOR_SIDECAR)
    ap.add_argument("--selector-smoke", type=Path, default=DEFAULT_SELECTOR_SMOKE)
    ap.add_argument("--launch-packet", type=Path, default=DEFAULT_LAUNCH_PACKET)
    return ap.parse_args()


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def load_npz_meta(path: Path) -> Any:
    with np.load(path, allow_pickle=False) as z:
        if "meta" not in z.files:
            raise ValueError(f"{path} has no meta entry")
        return json.loads(str(z["meta"]))


def raw_rows(meta: Any) -> list[dict[str, Any]]:
    if not isinstance(meta, list):
        return []
    return [row for row in meta if isinstance(row, dict)]


def pair_tiles(meta: Any) -> list[dict[str, Any]]:
    if not isinstance(meta, dict):
        return []
    tiles = meta.get("tiles")
    if not isinstance(tiles, list):
        return []
    return [row for row in tiles if isinstance(row, dict)]


def raw_identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    crop_xy = row.get("crop_xy") or row.get("candidate_raw_cfa_origin_xy") or []
    return (
        str(row.get("scene_id") or row.get("image_id") or ""),
        json.dumps(crop_xy, sort_keys=True, default=str),
        str(row.get("source_dng") or row.get("source_raw") or ""),
        str(row.get("candidate_raw") or row.get("candidate_dng") or ""),
    )


def gate14_identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    high_xy = [row.get("high_x"), row.get("high_y")]
    return (
        str(row.get("scene_id") or row.get("image_id") or ""),
        json.dumps(high_xy, sort_keys=True, default=str),
        str(row.get("source_dng") or row.get("source_raw") or row.get("sample_source") or ""),
        str(row.get("candidate_raw") or row.get("candidate_dng") or ""),
    )


def domain(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("scene_id", "image_id", "source_dng", "source"))
    text_l = text.lower()
    if "z8" in text_l or "z8z" in text_l:
        return "z8"
    if "x2d" in text_l or "austin" in text_l:
        return "x2d"
    if "mission" in text_l or "gopro" in text_l:
        return "mission1"
    return "unknown"


def render_html(receipt: dict[str, Any]) -> str:
    blocker = receipt.get("blocker_classification") or "none"
    rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in receipt["coverage"].items()
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate14 Floor-Student Target Builder</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #17202a; }}
table {{ border-collapse: collapse; min-width: 620px; }}
th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px 10px; text-align: left; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: {'#d5f5e3' if receipt['target_builder_passed'] else '#fadbd8'}; }}
code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
</style>
<h1>Gate14 Floor-Student Target Builder</h1>
<p class="status"><b>{'PASS' if receipt['target_builder_passed'] else 'BLOCKED'}</b> {html.escape(str(blocker))}</p>
<p>This receipt checks whether a true Gate14 pseudo-label raw-CFA target can be built. It does not claim production readiness.</p>
<table>{rows}</table>
<h2>Next Action</h2>
<p>{html.escape(str(receipt['next_unambiguous_action']))}</p>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    raw_meta = load_npz_meta(args.raw_targets)
    gate14_meta = load_npz_meta(args.gate14_pairs)
    sidecar = load_json(args.selector_sidecar)
    smoke = load_json(args.selector_smoke)
    launch = load_json(args.launch_packet)

    raw = raw_rows(raw_meta)
    tiles = pair_tiles(gate14_meta)
    raw_keys = {raw_identity(row) for row in raw}
    gate14_keys = {gate14_identity(row) for row in tiles}
    direct_matches = sorted(raw_keys & gate14_keys)
    raw_domains = Counter(domain(row) for row in raw)
    gate14_domains = Counter(domain(row) for row in tiles)

    selector_ok = (
        sidecar.get("schema") == "gpr.premium_still_sr_multi_source_selector_sidecar.v1"
        and smoke.get("gate14_selector_smoke_passed") is True
        and launch.get("candidate_id") == "premium_still_sr_gate14_floor_student_v1"
        and launch.get("preflight", {}).get("launchable_for_production_attempt") is True
    )
    direct_identity_ok = bool(direct_matches)
    domain_ok = raw_domains.get("x2d", 0) > 0 and raw_domains.get("z8", 0) > 0
    target_builder_passed = bool(selector_ok and direct_identity_ok and domain_ok)

    blocker = None
    if not selector_ok:
        blocker = "gate14_launch_or_selector_receipt_invalid"
    elif not direct_identity_ok:
        blocker = "gate14_raw_target_identity_missing"
    elif not domain_ok:
        blocker = "gate14_raw_target_domain_coverage_missing"

    output_npz = args.output_dir / "gate14_floor_student_targets.npz"
    next_action = (
        "Run the paired smoke commands from the launch packet."
        if target_builder_passed
        else (
            "Regenerate raw-CFA residual targets from the Gate14 fixture/pair surface "
            "while preserving image_id, tile_index, high_x/high_y, source raw path, "
            "candidate raw path, selector sidecar hash, and selected source id per row; "
            "then rerun this builder before any X2D/Z8 smoke training."
        )
    )
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": "premium_still_sr_gate14_floor_student_v1",
        "production_ready": False,
        "promotion_claimed": False,
        "target_builder_passed": target_builder_passed,
        "blocker_classification": blocker,
        "output_npz": str(output_npz) if target_builder_passed else None,
        "output_npz_sha256": sha256_file(output_npz) if target_builder_passed and output_npz.exists() else None,
        "inputs": {
            "raw_targets": {"path": str(args.raw_targets), "sha256": sha256_file(args.raw_targets)},
            "gate14_pairs": {"path": str(args.gate14_pairs), "sha256": sha256_file(args.gate14_pairs)},
            "selector_sidecar": {"path": str(args.selector_sidecar), "sha256": sha256_file(args.selector_sidecar)},
            "selector_smoke": {"path": str(args.selector_smoke), "sha256": sha256_file(args.selector_smoke)},
            "launch_packet": {"path": str(args.launch_packet), "sha256": sha256_file(args.launch_packet)},
        },
        "coverage": {
            "raw_target_row_count": len(raw),
            "gate14_pair_tile_count": len(tiles),
            "direct_row_identity_match_count": len(direct_matches),
            "raw_target_domain_counts": dict(sorted(raw_domains.items())),
            "gate14_pair_domain_counts": dict(sorted(gate14_domains.items())),
            "selector_source_count": len(sidecar.get("sources") or []),
            "selector_rule_count": len(sidecar.get("rules") or []),
            "smoke_selected_row_count": smoke.get("selector_smoke_metrics", {}).get("selected_row_count"),
            "launch_packet_command_count": len(launch.get("next_commands") or []),
        },
        "identity_contract": {
            "required_shared_fields": [
                "image_id",
                "tile_index",
                "high_x",
                "high_y",
                "source raw path",
                "candidate raw path",
                "selector sidecar sha256",
                "selected source id or exact-noop route",
            ],
            "forbidden_substitute": (
                "Do not train the floor student from unrelated raw-CFA rows or "
                "from a proxy domain-only selection; that would not distill the "
                "Gate14 selector/source evidence named by the model-floor gap."
            ),
        },
        "next_unambiguous_action": next_action,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "gate14_floor_student_targets.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    receipt["receipt"] = str(json_path)
    receipt["dashboard"] = str(html_path)
    return receipt


def main() -> int:
    args = parse_args()
    receipt = build(args)
    print(
        json.dumps(
            {
                "receipt": receipt["receipt"],
                "dashboard": receipt["dashboard"],
                "target_builder_passed": receipt["target_builder_passed"],
                "blocker_classification": receipt["blocker_classification"],
                "direct_row_identity_match_count": receipt["coverage"]["direct_row_identity_match_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
