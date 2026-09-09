#!/usr/bin/env python3
"""Audit/build Gate14 floor-student raw-CFA targets.

The Gate14 floor-student candidate may only train from target rows that can be
traced back to the Gate14 selector/pseudo-label surface. The accepted path
converts Gate14 clean-source pair tiles into the raw-CFA residual trainer
layout: runtime candidate planes come only from the low-resolution Bayer tile,
while the high-resolution source tile is training supervision only.
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
RAW_SCALE = 16383.0
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
    ap.add_argument("--domains", default="all", help="Comma-separated domain filter, or all.")
    ap.add_argument("--max-tiles", type=int, help="Optional development cap after domain filtering.")
    ap.add_argument("--highpass-block", type=int, default=17)
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


def load_pair_npz(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path, allow_pickle=False) as z:
        if "inputs" not in z.files or "targets" not in z.files or "meta" not in z.files:
            raise ValueError(f"{path} must contain inputs, targets, and meta arrays")
        inputs = z["inputs"].astype(np.float32) / RAW_SCALE
        targets = z["targets"].astype(np.float32) / RAW_SCALE
        meta = json.loads(str(z["meta"]))
    if inputs.ndim != 4 or targets.ndim != 4 or inputs.shape[1] != 4 or targets.shape[1] != 4:
        raise ValueError(f"{path} must contain NCHW CFA4 inputs/targets")
    if targets.shape[2] != inputs.shape[2] * 2 or targets.shape[3] != inputs.shape[3] * 2:
        raise ValueError(f"{path} target tiles must be 2x input tiles")
    if not isinstance(meta, dict):
        raise ValueError(f"{path} meta must be a JSON object")
    return inputs, targets, meta


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


def pair_images(meta: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(meta, dict):
        return {}
    images = meta.get("images")
    if not isinstance(images, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in images:
        if not isinstance(row, dict):
            continue
        image_id = str(row.get("image_id") or "")
        if image_id:
            out[image_id] = row
    return out


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


def parse_domain_filter(text: str) -> set[str] | None:
    stripped = str(text or "all").strip().lower()
    if not stripped or stripped == "all":
        return None
    return {part.strip() for part in stripped.split(",") if part.strip()}


def plane_highpass(arr: np.ndarray, block: int) -> np.ndarray:
    """High-pass NCHW CFA planes without mixing Bayer phases."""

    block = max(3, int(block))
    if block % 2 == 0:
        block += 1
    pad = block // 2
    padded = np.pad(arr, ((0, 0), (0, 0), (pad, pad), (pad, pad)), mode="reflect")
    csum = np.cumsum(np.cumsum(padded, axis=2, dtype=np.float64), axis=3, dtype=np.float64)
    csum = np.pad(csum, ((0, 0), (0, 0), (1, 0), (1, 0)), mode="constant")
    low = (
        csum[:, :, block:, block:]
        - csum[:, :, :-block, block:]
        - csum[:, :, block:, :-block]
        + csum[:, :, :-block, :-block]
    ) / float(block * block)
    return (arr.astype(np.float32) - low.astype(np.float32)).astype(np.float32)


def upsample_low_to_high(inputs: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(inputs, 2, axis=2), 2, axis=3).astype(np.float32)


def nchw_to_nhwc(arr: np.ndarray) -> np.ndarray:
    return np.transpose(arr, (0, 2, 3, 1))


def image_source_path(image: dict[str, Any]) -> str:
    source = image.get("source")
    if isinstance(source, dict):
        return str(source.get("path") or "")
    return ""


def row_cfa_phase(tile: dict[str, Any]) -> str:
    x = int(tile.get("high_x") or 0)
    y = int(tile.get("high_y") or 0)
    if (x & 1) == 0 and (y & 1) == 0:
        return "RGGB"
    if (x & 1) == 1 and (y & 1) == 0:
        return "GRBG"
    if (x & 1) == 0 and (y & 1) == 1:
        return "GBRG"
    return "BGGR"


def source_sha(image: dict[str, Any]) -> str | None:
    source = image.get("source")
    if isinstance(source, dict):
        return source.get("sha256") or image.get("source_sha256")
    return image.get("source_sha256")


def build_gate14_targets_from_pairs(
    *,
    gate14_pairs: Path,
    output_npz: Path,
    selector_sidecar_sha256: str,
    selector_smoke_sha256: str,
    launch_packet_sha256: str,
    domains: set[str] | None,
    max_tiles: int | None,
    highpass_block: int,
) -> tuple[list[dict[str, Any]], dict[str, int], str]:
    inputs, targets, meta = load_pair_npz(gate14_pairs)
    tiles = pair_tiles(meta)
    images = pair_images(meta)
    if len(tiles) != inputs.shape[0] or len(tiles) != targets.shape[0]:
        raise ValueError(f"tile metadata count {len(tiles)} does not match pair arrays {inputs.shape[0]} / {targets.shape[0]}")

    selected_indices: list[int] = []
    selected_domains: list[str] = []
    for idx, tile in enumerate(tiles):
        image = images.get(str(tile.get("image_id") or ""), {})
        d = domain({**image, **tile, "source": image.get("source")})
        if domains is None or d in domains:
            selected_indices.append(idx)
            selected_domains.append(d)
    if max_tiles is not None:
        selected_indices = selected_indices[: max(0, int(max_tiles))]
        selected_domains = selected_domains[: len(selected_indices)]
    if not selected_indices:
        raise ValueError("domain/max-tile filters selected no Gate14 tiles")

    idx_arr = np.asarray(selected_indices, dtype=np.int64)
    candidate = upsample_low_to_high(inputs[idx_arr])
    source = targets[idx_arr].astype(np.float32)
    residual = source - candidate
    candidate_hf = plane_highpass(candidate, highpass_block)
    source_hf = plane_highpass(source, highpass_block)
    residual_hf = plane_highpass(residual, highpass_block)
    render_hf_y = np.mean(residual_hf, axis=1).astype(np.float16)

    rows: list[dict[str, Any]] = []
    pairs_sha = sha256_file(gate14_pairs)
    for out_idx, source_idx in enumerate(selected_indices):
        tile = dict(tiles[source_idx])
        image = images.get(str(tile.get("image_id") or ""), {})
        crop_xy = [int(tile.get("high_x") or 0), int(tile.get("high_y") or 0)]
        high_tile = int(tile.get("high_raw_tile") or targets.shape[2] * 2)
        phase = row_cfa_phase(tile)
        rows.append(
            {
                "scene_id": str(tile.get("image_id") or image.get("image_id") or ""),
                "image_id": str(tile.get("image_id") or image.get("image_id") or ""),
                "camera": image.get("camera"),
                "camera_key": image.get("camera_key"),
                "class": image.get("class"),
                "domain": selected_domains[out_idx],
                "source_dng": image_source_path(image),
                "source_raw": image.get("raw_extract"),
                "candidate_raw": "gate14_pair_low_bayer_same_color_2x_repeat",
                "candidate_source": "Gate14 clean-source low Bayer tile only",
                "crop": f"gate14_tile_{source_idx:05d}",
                "crop_xy": crop_xy,
                "candidate_raw_cfa_origin_xy": crop_xy,
                "crop_size": high_tile,
                "tile_index": int(source_idx),
                "gate14_output_index": int(out_idx),
                "high_x": crop_xy[0],
                "high_y": crop_xy[1],
                "low_x": int(tile.get("low_x") or 0),
                "low_y": int(tile.get("low_y") or 0),
                "low_tile": int(tile.get("low_tile") or inputs.shape[2]),
                "high_raw_tile": high_tile,
                "sample_source": tile.get("sample_source"),
                "raw_target_kind": "gate14_low_bayer_to_high_bayer_same_color_highpass_residual",
                "teacher_gate_before_student": True,
                "selector_sidecar_sha256": selector_sidecar_sha256,
                "selector_smoke_sha256": selector_smoke_sha256,
                "launch_packet_sha256": launch_packet_sha256,
                "selected_source_id": "gate14_clean_source_pair_high_tile",
                "selected_route": "clean_source_pair_supervision",
                "source_cfa_phase": "RGGB",
                "crop_cfa_phase": phase,
                "cfa_phase": phase,
                "cfa_phase_source": "gate14_tile_origin_parity",
                "ev": 0.0,
                "noise_sidecars": image.get("noise_sidecars", []),
                "gate14_pairs": str(gate14_pairs),
                "gate14_pairs_sha256": pairs_sha,
                "source_sha256": source_sha(image),
                "raw_residual_abs_mean": float(np.mean(np.abs(residual[out_idx]))),
                "raw_same_color_hf_residual_abs_mean": float(np.mean(np.abs(residual_hf[out_idx]))),
                "source_raw_same_color_hf_abs_mean": float(np.mean(np.abs(source_hf[out_idx]))),
                "candidate_raw_same_color_hf_abs_mean": float(np.mean(np.abs(candidate_hf[out_idx]))),
                "render_hf_residual_y_abs_mean": float(np.mean(np.abs(render_hf_y[out_idx]))),
            }
        )

    output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_npz,
        candidate_raw_cfa4=nchw_to_nhwc(candidate).astype(np.float16),
        candidate_raw_hf_cfa4=nchw_to_nhwc(candidate_hf).astype(np.float16),
        raw_hf_residual_cfa4=nchw_to_nhwc(residual_hf).astype(np.float16),
        source_raw_hf_cfa4=nchw_to_nhwc(source_hf).astype(np.float16),
        render_hf_residual_y=render_hf_y,
        meta=np.asarray(json.dumps(rows, sort_keys=True)),
    )
    return rows, dict(sorted(Counter(selected_domains).items())), str(meta.get("schema") or "")


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
    gate14_meta = load_npz_meta(args.gate14_pairs)
    sidecar = load_json(args.selector_sidecar)
    smoke = load_json(args.selector_smoke)
    launch = load_json(args.launch_packet)

    tiles = pair_tiles(gate14_meta)
    images = pair_images(gate14_meta)
    enriched_tiles = [
        {**images.get(str(tile.get("image_id") or ""), {}), **tile, "source": images.get(str(tile.get("image_id") or ""), {}).get("source")}
        for tile in tiles
    ]
    gate14_domains = Counter(domain(row) for row in tiles)
    enriched_gate14_domains = Counter(domain(row) for row in enriched_tiles)
    domain_filter = parse_domain_filter(args.domains)
    allowed_tiles = [row for row in enriched_tiles if domain_filter is None or domain(row) in domain_filter]
    selected_domain_counts = Counter(domain(row) for row in allowed_tiles)

    selector_ok = (
        sidecar.get("schema") == "gpr.premium_still_sr_multi_source_selector_sidecar.v1"
        and smoke.get("gate14_selector_smoke_passed") is True
        and launch.get("candidate_id") == "premium_still_sr_gate14_floor_student_v1"
        and launch.get("preflight", {}).get("launchable_for_production_attempt") is True
    )
    domain_ok = selected_domain_counts.get("x2d", 0) > 0 and selected_domain_counts.get("z8", 0) > 0
    target_builder_passed = False

    blocker = None
    if not selector_ok:
        blocker = "gate14_launch_or_selector_receipt_invalid"
    elif not domain_ok:
        blocker = "gate14_raw_target_domain_coverage_missing"

    output_npz = args.output_dir / "gate14_floor_student_targets.npz"
    built_rows: list[dict[str, Any]] = []
    built_domain_counts: dict[str, int] = {}
    source_pair_schema = None
    output_npz_sha256 = None
    if blocker is None:
        built_rows, built_domain_counts, source_pair_schema = build_gate14_targets_from_pairs(
            gate14_pairs=args.gate14_pairs,
            output_npz=output_npz,
            selector_sidecar_sha256=sha256_file(args.selector_sidecar),
            selector_smoke_sha256=sha256_file(args.selector_smoke),
            launch_packet_sha256=sha256_file(args.launch_packet),
            domains=domain_filter,
            max_tiles=args.max_tiles,
            highpass_block=args.highpass_block,
        )
        target_builder_passed = bool(built_rows)
        output_npz_sha256 = sha256_file(output_npz)
    next_action = (
        "Run the paired smoke commands from the launch packet."
        if target_builder_passed
        else (
            "Fix the Gate14 selector/launch receipts or X2D/Z8 domain coverage, "
            "then rerun this builder before any smoke training."
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
        "output_npz_sha256": output_npz_sha256,
        "inputs": {
            "raw_targets": {
                "path": str(args.raw_targets),
                "sha256": sha256_file(args.raw_targets) if args.raw_targets.exists() else None,
                "role": "legacy comparison input; not used for Gate14 floor-student target generation",
            },
            "gate14_pairs": {"path": str(args.gate14_pairs), "sha256": sha256_file(args.gate14_pairs)},
            "selector_sidecar": {"path": str(args.selector_sidecar), "sha256": sha256_file(args.selector_sidecar)},
            "selector_smoke": {"path": str(args.selector_smoke), "sha256": sha256_file(args.selector_smoke)},
            "launch_packet": {"path": str(args.launch_packet), "sha256": sha256_file(args.launch_packet)},
        },
        "coverage": {
            "gate14_pair_tile_count": len(tiles),
            "gate14_pair_domain_counts": dict(sorted(gate14_domains.items())),
            "gate14_pair_domain_counts_with_image_metadata": dict(sorted(enriched_gate14_domains.items())),
            "domain_filter": sorted(domain_filter) if domain_filter is not None else ["all"],
            "selected_gate14_pair_tile_count": len(allowed_tiles),
            "selected_gate14_domain_counts": dict(sorted(selected_domain_counts.items())),
            "built_target_row_count": len(built_rows),
            "built_target_domain_counts": built_domain_counts,
            "selector_source_count": len(sidecar.get("sources") or []),
            "selector_rule_count": len(sidecar.get("rules") or []),
            "smoke_selected_row_count": smoke.get("selector_smoke_metrics", {}).get("selected_row_count"),
            "launch_packet_command_count": len(launch.get("next_commands") or []),
            "source_pair_schema": source_pair_schema,
            "highpass_block": int(args.highpass_block),
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
        "target_policy": {
            "runtime_candidate": "low Bayer tile upsampled by deterministic same-color 2x repeat",
            "training_supervision": "high Bayer tile from Gate14 clean-source pair surface",
            "render_time_forbidden_inputs": ["REF", "source raw", "JPEG", "gate metric rows"],
            "teacher_gate_before_student": True,
        },
        "sample_rows": built_rows[:8],
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
                "built_target_row_count": receipt["coverage"]["built_target_row_count"],
                "output_npz": receipt["output_npz"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
