#!/usr/bin/env python3
"""Build and validate companion source metadata for .gvid streams."""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np


GVID_MAGIC = 0x44495647
FRAME_MAGIC = 0x004D5246
GVID_VERSION = 1
SCHEMA = "gvid_source_metadata.v1"


def read_gvid_frame_tags(path: Path) -> list[int]:
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError(f"{path} is too small to be a .gvid stream")
    header = struct.unpack("<IBBHHHIIIII", data[:32])
    if header[0] != GVID_MAGIC:
        raise ValueError(f"{path} does not have GVID magic")
    if header[1] != GVID_VERSION:
        raise ValueError(f"{path} has unsupported GVID version {header[1]}")
    frame_count_hint = int(header[10])
    tags: list[int] = []
    pos = 32
    while pos < len(data):
        if pos + 16 > len(data):
            raise ValueError(f"{path} has a truncated frame header at byte {pos}")
        magic, payload_size, frame_tag = struct.unpack("<IIQ", data[pos:pos + 16])
        if magic != FRAME_MAGIC:
            raise ValueError(f"{path} has bad frame magic at byte {pos}")
        pos += 16
        if pos + payload_size > len(data):
            raise ValueError(f"{path} has a truncated frame payload at byte {pos}")
        tags.append(int(frame_tag))
        pos += int(payload_size)
    if frame_count_hint not in (0, len(tags)):
        raise ValueError(f"{path} frame_count_hint={frame_count_hint} but stream has {len(tags)} frames")
    return tags


def validate_against_gvid(meta: dict[str, Any], gvid: Path) -> None:
    tags = read_gvid_frame_tags(gvid)
    meta_tags = [int(frame["frame_tag"]) for frame in meta["frames"]]
    if len(tags) != len(meta_tags):
        raise ValueError(f"{gvid} has {len(tags)} frames but metadata has {len(meta_tags)} frames")
    if tags != meta_tags:
        raise ValueError(f"{gvid} frame tags {tags} do not match metadata frame tags {meta_tags}")


def load_crop_xywh(npz_path: Path) -> list[int]:
    z = np.load(npz_path, allow_pickle=False)
    if "crop_xywh" not in z:
        raise ValueError(f"{npz_path} does not contain crop_xywh")
    return [int(v) for v in z["crop_xywh"].tolist()]


def build_from_raw_clean_targets(targets: Path, out: Path, *, gvid: Path | None) -> dict[str, Any]:
    data = json.loads(targets.read_text())
    rows_by_image: dict[str, list[dict[str, Any]]] = {}
    for row in data["rows"]:
        rows_by_image.setdefault(row["image_id"], []).append(row)

    frames = []
    for frame_index, image_id in enumerate(rows_by_image):
        rows = rows_by_image[image_id]
        iso_values = {int(row["iso"]) for row in rows}
        if len(iso_values) != 1:
            raise ValueError(f"{image_id} has inconsistent ISO values {sorted(iso_values)}")
        tiles = []
        for row in rows:
            tiles.append({
                "crop": row["crop"],
                "source_xywh": load_crop_xywh(Path(row["npz"])),
                "accepted": bool(row.get("accepted", True)),
                "reject_reasons": list(row.get("reject_reasons", [])),
                "sigma_rms_counts": float(row["sigma_rms_counts"]),
                "exact_residual_to_sigma_rms": float(row["exact_residual_to_sigma_rms"]),
                "lag_max_abs": float(row["lag_max_abs"]),
                "edge_removed_energy_ratio": float(row["edge_removed_energy_ratio"]),
            })
        frames.append({
            "frame_index": frame_index,
            "frame_tag": frame_index,
            "source_id": image_id,
            "source_path": rows[0]["path"],
            "iso": next(iter(iso_values)),
            "raw_clean_tiles": tiles,
        })

    meta = {
        "schema": SCHEMA,
        "source": "raw_clean_ref_targets",
        "targets": str(targets),
        "gvid": str(gvid) if gvid else None,
        "frame_count": len(frames),
        "frames": frames,
    }
    validate_metadata(meta)
    if gvid:
        validate_against_gvid(meta, gvid)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta, indent=2))
    return meta


def validate_metadata(meta: dict[str, Any]) -> None:
    if meta.get("schema") != SCHEMA:
        raise ValueError(f"unsupported metadata schema {meta.get('schema')!r}")
    frames = meta.get("frames")
    if not isinstance(frames, list):
        raise ValueError("frames must be a list")
    if int(meta.get("frame_count", -1)) != len(frames):
        raise ValueError("frame_count does not match frames length")
    seen_indices: set[int] = set()
    seen_tags: set[int] = set()
    for frame in frames:
        frame_index = int(frame["frame_index"])
        frame_tag = int(frame["frame_tag"])
        if frame_index in seen_indices:
            raise ValueError(f"duplicate frame_index {frame_index}")
        if frame_tag in seen_tags:
            raise ValueError(f"duplicate frame_tag {frame_tag}")
        seen_indices.add(frame_index)
        seen_tags.add(frame_tag)
        if frame_index < 0 or frame_tag < 0:
            raise ValueError("frame_index/frame_tag must be non-negative")
        tiles = frame.get("raw_clean_tiles")
        if not isinstance(tiles, list):
            raise ValueError(f"frame {frame_index} raw_clean_tiles must be a list")
        for tile in tiles:
            xywh = tile.get("source_xywh")
            if not (isinstance(xywh, list) and len(xywh) == 4 and all(int(v) >= 0 for v in xywh)):
                raise ValueError(f"frame {frame_index} tile {tile.get('crop')} has invalid source_xywh")
            if any(int(v) % 2 for v in xywh):
                raise ValueError(f"frame {frame_index} tile {tile.get('crop')} source_xywh is not CFA aligned")
            if not isinstance(tile.get("accepted"), bool):
                raise ValueError(f"frame {frame_index} tile {tile.get('crop')} accepted must be bool")
            if not isinstance(tile.get("reject_reasons"), list):
                raise ValueError(f"frame {frame_index} tile {tile.get('crop')} reject_reasons must be list")
            for key in (
                "sigma_rms_counts",
                "exact_residual_to_sigma_rms",
                "lag_max_abs",
                "edge_removed_energy_ratio",
            ):
                value = float(tile[key])
                if not np.isfinite(value):
                    raise ValueError(f"frame {frame_index} tile {tile.get('crop')} {key} is not finite")


def cmd_from_targets(args: argparse.Namespace) -> int:
    meta = build_from_raw_clean_targets(args.targets, args.output, gvid=args.gvid)
    accepted = sum(
        1
        for frame in meta["frames"]
        for tile in frame["raw_clean_tiles"]
        if tile["accepted"]
    )
    total = sum(len(frame["raw_clean_tiles"]) for frame in meta["frames"])
    print(args.output)
    print(f"frames={meta['frame_count']} tiles={total} accepted_tiles={accepted}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    meta = json.loads(args.metadata.read_text())
    validate_metadata(meta)
    if args.gvid:
        validate_against_gvid(meta, args.gvid)
    print(f"{args.metadata}: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build and validate .gvid source metadata sidecars.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("from-raw-clean-targets")
    build.add_argument("targets", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--gvid", type=Path)
    build.set_defaults(func=cmd_from_targets)

    validate = sub.add_parser("validate")
    validate.add_argument("metadata", type=Path)
    validate.add_argument("--gvid", type=Path)
    validate.set_defaults(func=cmd_validate)

    args = ap.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"gvid_metadata: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
