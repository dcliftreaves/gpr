#!/usr/bin/env python3
"""Build full-frame coverage tile manifests for Mission 1 SR training.

Hard-tile mining is useful for finding local failures, but repeated probes have
shown that crop-only objectives can diverge from full-frame blocker metrics.
This helper creates deterministic grid coverage over each blocker frame while
optionally mixing in a bounded number of mined hard tiles for extra density.
The output is the same manifest contract consumed by build_mission1_sr_pairs.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "mission1_sr_hard_tile_manifest.v1"


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def image_ids_from_summary(path: Path | None) -> list[str]:
    if path is None:
        return []
    payload = read_json(path)
    rows = payload.get("images")
    if not isinstance(rows, list):
        raise ValueError(f"{path} does not contain an images list")
    ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("image") is None:
            continue
        image = str(row["image"])
        if image not in ids:
            ids.append(image)
    return ids


def grid_positions(limit: int, tile: int, stride: int) -> list[int]:
    if tile <= 0 or stride <= 0:
        raise ValueError("tile and stride must be positive")
    if tile > limit:
        raise ValueError(f"tile {tile} is larger than plane limit {limit}")
    positions = list(range(0, limit - tile + 1, stride))
    last = limit - tile
    if positions[-1] != last:
        positions.append(last)
    return positions


def grid_tiles(
    image_id: str,
    *,
    plane_width: int,
    plane_height: int,
    low_tile: int,
    stride: int,
) -> list[dict[str, Any]]:
    xs = grid_positions(plane_width, low_tile, stride)
    ys = grid_positions(plane_height, low_tile, stride)
    rows: list[dict[str, Any]] = []
    rank = 1
    for y in ys:
        for x in xs:
            rows.append(
                {
                    "image_id": image_id,
                    "low_x": int(x),
                    "low_y": int(y),
                    "low_tile": int(low_tile),
                    "rank": rank,
                    "score": 0.0,
                    "score_mode": "full_frame_grid_coverage",
                }
            )
            rank += 1
    return rows


def hard_tiles_by_image(path: Path | None, low_tile: int, top_k: int) -> dict[str, list[dict[str, Any]]]:
    if path is None or top_k <= 0:
        return {}
    payload = read_json(path)
    tiles = payload.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError(f"{path} does not contain a tiles list")
    by_image: dict[str, list[dict[str, Any]]] = {}
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        image = str(tile.get("image_id") or "")
        if not image:
            raise ValueError(f"{path} contains a hard tile without image_id")
        tile_low = int(tile.get("low_tile", low_tile))
        if tile_low != low_tile:
            raise ValueError(f"{path} tile for {image} has low_tile={tile_low}, expected {low_tile}")
        by_image.setdefault(image, []).append(tile)
    selected: dict[str, list[dict[str, Any]]] = {}
    for image, rows in by_image.items():
        ordered = sorted(rows, key=lambda row: (float(row.get("score", 0.0)), -int(row.get("rank", 0))), reverse=True)
        selected[image] = ordered[:top_k]
    return selected


def merge_hard_tiles(
    grid: list[dict[str, Any]],
    hard: list[dict[str, Any]],
    *,
    low_tile: int,
    repeat: int,
    source_manifest: Path,
) -> list[dict[str, Any]]:
    occupied = {(int(row["low_x"]), int(row["low_y"])) for row in grid}
    merged = list(grid)
    for row in hard:
        x = int(row["low_x"])
        y = int(row["low_y"])
        if (x, y) in occupied:
            continue
        out = {
            "image_id": str(row["image_id"]),
            "low_x": x,
            "low_y": y,
            "low_tile": low_tile,
            "rank": int(row.get("rank", len(merged) + 1)),
            "score": float(row.get("score", 0.0)),
            "score_mode": "full_frame_coverage_plus_hard_tile",
            "source_compare": row.get("source_compare"),
            "source_hard_manifest": str(source_manifest),
        }
        for _ in range(max(1, repeat)):
            merged.append(dict(out))
        occupied.add((x, y))
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--summary", type=Path, help="optional full-frame summary JSON; images are appended in summary order")
    ap.add_argument("--low-width", type=int, default=4096, help="raw low-frame width before CFA deinterleave")
    ap.add_argument("--low-height", type=int, default=3072, help="raw low-frame height before CFA deinterleave")
    ap.add_argument("--low-tile", type=int, default=96, help="tile size in deinterleaved CFA-plane pixels")
    ap.add_argument("--stride", type=int, default=192, help="grid stride in deinterleaved CFA-plane pixels")
    ap.add_argument("--hard-manifest", type=Path)
    ap.add_argument("--hard-top-k-per-image", type=int, default=0)
    ap.add_argument("--hard-repeat", type=int, default=1)
    args = ap.parse_args()

    images: list[str] = []
    for image in list(args.image_id) + image_ids_from_summary(args.summary):
        if image not in images:
            images.append(image)
    if not images:
        raise SystemExit("provide --image-id or --summary with at least one image")

    plane_width = args.low_width // 2
    plane_height = args.low_height // 2
    hard = hard_tiles_by_image(args.hard_manifest, args.low_tile, args.hard_top_k_per_image)
    tiles: list[dict[str, Any]] = []
    per_image: dict[str, dict[str, int]] = {}
    for image in images:
        base = grid_tiles(
            image,
            plane_width=plane_width,
            plane_height=plane_height,
            low_tile=args.low_tile,
            stride=args.stride,
        )
        merged = merge_hard_tiles(
            base,
            hard.get(image, []),
            low_tile=args.low_tile,
            repeat=args.hard_repeat,
            source_manifest=args.hard_manifest or Path(""),
        )
        tiles.extend(merged)
        per_image[image] = {
            "grid_tiles": len(base),
            "hard_tiles_added": len(merged) - len(base),
            "total_tiles": len(merged),
        }

    payload = {
        "schema": SCHEMA,
        "source": "full-frame deterministic coverage grid with optional hard-tile density",
        "low_width": args.low_width,
        "low_height": args.low_height,
        "plane_width": plane_width,
        "plane_height": plane_height,
        "low_tile": args.low_tile,
        "stride": args.stride,
        "summary": str(args.summary) if args.summary else None,
        "hard_manifest": str(args.hard_manifest) if args.hard_manifest else None,
        "hard_top_k_per_image": args.hard_top_k_per_image,
        "hard_repeat": args.hard_repeat,
        "image_count": len(images),
        "tile_count": len(tiles),
        "per_image": per_image,
        "tiles": tiles,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "image_count": len(images), "tile_count": len(tiles)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
