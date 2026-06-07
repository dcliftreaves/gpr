#!/usr/bin/env python3
"""Build full-frame PREVIEW tile source/REF receipts.

This creates deterministic tile pairs from full source and REF renders. It is
used to train/evaluate PREVIEW candidates on the same arbitrary full-frame tile
distribution used by the tiled runtime diagnostic. REF is target/scoring data
only; receipt rows point at source PNGs for render-time inputs.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image
import numpy as np


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box, sha256_file  # noqa: E402
from evaluate_preview_scene_routed import route_from_sidecar  # noqa: E402


DEFAULT_REF_ROOTS = [
    Path("/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"),
    Path("/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs"),
]
DEFAULT_SOURCE_ROOTS = [
    Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607/editable_dng"),
    Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng"),
    Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/editable_dng"),
]


def render_dng_to_tiff(dng_path: Path, tiff_path: Path) -> float:
    t0 = time.perf_counter()
    result = subprocess.run(
        ["sips", "-s", "format", "tiff", str(dng_path), "--out", str(tiff_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed for {dng_path}: {result.stderr[-400:]}")
    return (time.perf_counter() - t0) * 1000.0


def tile_origins(length: int, tile: int, stride: int) -> list[int]:
    if length <= tile:
        return [0]
    out = list(range(0, max(1, length - tile + 1), stride))
    last = length - tile
    if out[-1] != last:
        out.append(last)
    return out


def intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def map_box_between_sizes(
    box: tuple[int, int, int, int],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    sx = target_size[0] / source_size[0]
    sy = target_size[1] / source_size[1]
    x0 = int(round(box[0] * sx))
    y0 = int(round(box[1] * sy))
    x1 = int(round(box[2] * sx))
    y1 = int(round(box[3] * sy))
    x0 = min(max(0, x0), target_size[0] - 1)
    y0 = min(max(0, y0), target_size[1] - 1)
    x1 = min(max(x0 + 1, x1), target_size[0])
    y1 = min(max(y0 + 1, y1), target_size[1])
    return x0, y0, x1, y1


def selected_tiles(
    *,
    width: int,
    height: int,
    tile: int,
    stride: int,
    mode: str,
    crop_boxes: dict[str, tuple[int, int, int, int]],
    max_tiles: int,
) -> list[tuple[int, int, int, int, list[str]]]:
    rows: list[tuple[int, int, int, int, list[str]]] = []
    for y0 in tile_origins(height, tile, stride):
        for x0 in tile_origins(width, tile, stride):
            box = (x0, y0, min(width, x0 + tile), min(height, y0 + tile))
            crop_hits = [name for name, crop_box in crop_boxes.items() if intersects(box, crop_box)]
            if mode == "intersect_crops" and not crop_hits:
                continue
            rows.append((*box, crop_hits))
    if max_tiles > 0 and len(rows) > max_tiles:
        if mode == "intersect_crops":
            rows = rows[:max_tiles]
        else:
            step = max(1, len(rows) // max_tiles)
            rows = rows[::step][:max_tiles]
    return rows


def save_tile_pair(
    *,
    source_image: Image.Image,
    ref_image: Image.Image,
    source_box: tuple[int, int, int, int],
    out_source: Path,
    out_ref: Path,
) -> None:
    source_tile = source_image.crop(source_box).convert("RGB")
    ref_box = map_box_between_sizes(source_box, source_image.size, ref_image.size)
    ref_tile = ref_image.crop(ref_box).convert("RGB")
    if ref_tile.size != source_tile.size:
        ref_tile = ref_tile.resize(source_tile.size, Image.Resampling.LANCZOS)
    source_tile.save(out_source)
    ref_tile.save(out_ref)


def image_stats(image: Image.Image) -> dict[str, float]:
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    gray = rgb.mean(axis=2)
    return {
        "r_mean": float(rgb[:, :, 0].mean()),
        "g_mean": float(rgb[:, :, 1].mean()),
        "b_mean": float(rgb[:, :, 2].mean()),
        "gray_std": float(gray.std()),
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text())
    sidecar = json.loads(args.router_sidecar.read_text()) if args.router_sidecar else None
    args.out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_fullframe_tiles_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    render_ms: list[float] = []
    try:
        for image in manifest["images"]:
            image_id = str(image["id"])
            if args.image_id and image_id not in set(args.image_id):
                continue
            ref_dng = resolve_ref(image, args.ref_root)
            source_dng = resolve_source(image_id, args.source_root)
            if not ref_dng.exists():
                missing.append({"image_id": image_id, "reason": "missing_ref_dng", "path": str(ref_dng)})
                continue
            if source_dng is None:
                missing.append({"image_id": image_id, "reason": "missing_source_dng"})
                continue
            ref_sha = sha256_file(ref_dng)
            source_sha = sha256_file(source_dng)
            if ref_sha == source_sha:
                missing.append({"image_id": image_id, "reason": "source_is_ref_hash", "path": str(source_dng)})
                continue

            ref_tiff = work / f"{image_id}_REF.tiff"
            source_tiff = work / f"{image_id}_source.tiff"
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
            render_ms.append(render_dng_to_tiff(source_dng, source_tiff))
            with Image.open(source_tiff) as source_image_raw, Image.open(ref_tiff) as ref_image_raw:
                source_image = source_image_raw.convert("RGB")
                ref_image = ref_image_raw.convert("RGB")
                source_global_stats = image_stats(source_image)
                crop_boxes = {
                    name: scaled_box(crop, image["sensor_dims"], source_image.size)
                    for name, crop in manifest["crops"].items()
                    if not name.startswith("$")
                }
                tile_rows = selected_tiles(
                    width=source_image.size[0],
                    height=source_image.size[1],
                    tile=args.tile_size,
                    stride=max(1, args.tile_size - args.overlap),
                    mode=args.tile_mode,
                    crop_boxes=crop_boxes,
                    max_tiles=args.max_tiles_per_image,
                )
                for x0, y0, x1, y1, crop_hits in tile_rows:
                    crop_name = f"tile_{x0}_{y0}"
                    source_png = args.out_dir / f"{image_id}_{crop_name}_upresable_preview.png"
                    ref_png = args.out_dir / f"{image_id}_{crop_name}_REF.png"
                    save_tile_pair(
                        source_image=source_image,
                        ref_image=ref_image,
                        source_box=(x0, y0, x1, y1),
                        out_source=source_png,
                        out_ref=ref_png,
                    )
                    cluster = None
                    if sidecar is not None:
                        cluster, _route = route_from_sidecar(source_png, sidecar)
                    rows.append(
                        {
                            "image_id": image_id,
                            "crop": crop_name,
                            "source_label": f"{args.out_dir.name}:upresable_preview",
                            "source_png": str(source_png),
                            "ref_png": str(ref_png),
                            "ref_dng": str(ref_dng),
                            "source_dng": str(source_dng),
                            "ref_dng_sha256": ref_sha,
                            "source_dng_sha256": source_sha,
                            "source_render_size": list(source_image.size),
                            "ref_render_size": list(ref_image.size),
                            "source_global_stats": source_global_stats,
                            "tile_xywh": [x0, y0, x1 - x0, y1 - y0],
                            "intersects_crops": crop_hits,
                            "cluster": cluster,
                            "strata": image.get("strata", []),
                        }
                    )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "schema": "preview_fullframe_tile_receipt.v1",
        "manifest": str(args.manifest),
        "source_roots": [str(path) for path in args.source_root],
        "ref_roots": [str(path) for path in args.ref_root],
        "router_sidecar": str(args.router_sidecar) if args.router_sidecar else None,
        "out_dir": str(args.out_dir),
        "tile_mode": args.tile_mode,
        "tile_size": args.tile_size,
        "overlap": args.overlap,
        "rows": rows,
        "missing": missing,
        "summary": {
            "images_in_manifest": len(manifest["images"]),
            "images_with_tiles": len({row["image_id"] for row in rows}),
            "rows": len(rows),
            "missing_images": len(missing),
        },
        "timing": {
            "render_count": len(render_ms),
            "render_ms_total": sum(render_ms),
            "render_ms_median": sorted(render_ms)[len(render_ms) // 2] if render_ms else 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    parser.add_argument("--ref-root", type=Path, action="append")
    parser.add_argument("--source-root", type=Path, action="append")
    parser.add_argument("--router-sidecar", type=Path)
    parser.add_argument("--image-id", action="append", default=[])
    parser.add_argument("--tile-mode", choices=["intersect_crops", "full_grid"], default="intersect_crops")
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=0)
    parser.add_argument("--max-tiles-per-image", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = parser.parse_args()
    if args.ref_root is None:
        args.ref_root = DEFAULT_REF_ROOTS
    if args.source_root is None:
        args.source_root = DEFAULT_SOURCE_ROOTS
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = build(args)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
