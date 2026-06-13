#!/usr/bin/env python3
"""Build PREVIEW post-refiner samples from stitched full-frame outputs.

The source side of each row is an already assembled no-REF full-frame crop.
REF is rendered only to create supervised targets and later scoring references.
This receipt lets the runtime refiner train on the distribution that actually
fails in the tiled full-frame path instead of isolated source tiles.
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

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_fullframe_tile_receipt import intersects, parse_tile_offsets, tile_origins_with_offset  # noqa: E402
from build_preview_holdout_runtime_receipt import scaled_box  # noqa: E402
from evaluate_preview_scene_routed_fullframe import crop_metric_image  # noqa: E402


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


def image_stats(image: np.ndarray) -> dict[str, float]:
    rgb = image.astype(np.float32) / 255.0
    gray = rgb.mean(axis=2)
    return {
        "r_mean": float(rgb[:, :, 0].mean()),
        "g_mean": float(rgb[:, :, 1].mean()),
        "b_mean": float(rgb[:, :, 2].mean()),
        "gray_std": float(gray.std()),
    }


def output_root(receipt_path: Path, receipt: dict[str, Any]) -> Path:
    rows = receipt.get("rows") or []
    if rows and rows[0].get("png"):
        candidate = receipt_path.parent / str(rows[0]["png"])
        if candidate.exists():
            return receipt_path.parent
    images = receipt.get("images") or []
    if images and images[0].get("stitched_png"):
        candidate = receipt_path.parent / str(images[0]["stitched_png"])
        if candidate.exists():
            return receipt_path.parent
    raise RuntimeError(f"cannot locate full-frame output PNGs next to {receipt_path}")


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


def selected_tile_boxes(
    *,
    width: int,
    height: int,
    tile: int,
    stride: int,
    mode: str,
    crop_boxes: dict[str, tuple[int, int, int, int]],
    max_tiles: int,
    tile_offsets: list[tuple[int, int]] | None = None,
) -> list[tuple[int, int, int, int, list[str]]]:
    rows: list[tuple[int, int, int, int, list[str]]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for offset_x, offset_y in tile_offsets or [(0, 0)]:
        for y0 in tile_origins_with_offset(height, tile, stride, offset_y):
            for x0 in tile_origins_with_offset(width, tile, stride, offset_x):
                box = (x0, y0, min(width, x0 + tile), min(height, y0 + tile))
                if box in seen:
                    continue
                seen.add(box)
                crop_hits = [name for name, crop_box in crop_boxes.items() if intersects(box, crop_box)]
                if mode == "intersect_tiles" and not crop_hits:
                    continue
                rows.append((*box, crop_hits))
    if max_tiles > 0 and len(rows) > max_tiles:
        rows = rows[:max_tiles]
    return rows


def append_manifest_crop_rows(
    *,
    args: argparse.Namespace,
    fullframe: dict[str, Any],
    root: Path,
    manifest_images: dict[str, dict[str, Any]],
    manifest_crops: dict[str, dict[str, int]],
    image_receipts: dict[str, dict[str, Any]],
    ref_cache: dict[str, np.ndarray],
    render_ms: list[float],
    work: Path,
    rows: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    for row in fullframe.get("rows", []):
        image_id = str(row["image_id"])
        if args.image_id and image_id not in set(args.image_id):
            continue
        crop_name = str(row["crop"])
        if crop_name not in manifest_crops:
            missing.append({"image_id": image_id, "crop": crop_name, "reason": "missing_manifest_crop"})
            continue
        source_png = root / str(row["png"])
        if not source_png.exists():
            missing.append({"image_id": image_id, "crop": crop_name, "reason": "missing_source_png", "path": str(source_png)})
            continue
        image_meta = manifest_images.get(image_id)
        image_receipt = image_receipts.get(image_id)
        if image_meta is None or image_receipt is None:
            missing.append({"image_id": image_id, "crop": crop_name, "reason": "missing_image_receipt"})
            continue
        if image_id not in ref_cache:
            ref_dng = Path(str(image_receipt["ref_dng"]))
            ref_tiff = work / f"{image_id}_REF.tiff"
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
            ref_cache[image_id] = np.asarray(Image.open(ref_tiff).convert("RGB"), dtype=np.uint8)
        ref_crop = crop_metric_image(ref_cache[image_id], manifest_crops[crop_name], image_meta["sensor_dims"])
        ref_png = args.out_dir / f"{image_id}_{crop_name}_REF.png"
        Image.fromarray(ref_crop).save(ref_png)
        source_rgb = np.asarray(Image.open(source_png).convert("RGB"), dtype=np.uint8)
        copied_source = args.out_dir / f"{image_id}_{crop_name}_stitched_source.png"
        shutil.copyfile(source_png, copied_source)
        full_size = image_receipt.get("source_render_size") or [source_rgb.shape[1], source_rgb.shape[0]]
        crop_box = scaled_box(manifest_crops[crop_name], image_meta["sensor_dims"], tuple(int(v) for v in full_size))
        rows.append(
            {
                "image_id": image_id,
                "crop": crop_name,
                "source_label": "stitched_fullframe:no_ref_base_output",
                "source_png": str(copied_source),
                "source_png_resolved": str(copied_source),
                "ref_png": str(ref_png),
                "source_render_size": [int(full_size[0]), int(full_size[1])],
                "tile_xywh": [int(crop_box[0]), int(crop_box[1]), int(crop_box[2] - crop_box[0]), int(crop_box[3] - crop_box[1])],
                "source_global_stats": image_stats(source_rgb),
                "base_metrics": {
                    key: float(row[key])
                    for key in ("lpips", "ms_ssim", "y_psnr", "dE2000_mean")
                    if key in row
                },
                "base_preview_pass": bool(row.get("preview_pass", False)),
            }
        )


def append_tile_rows(
    *,
    args: argparse.Namespace,
    root: Path,
    manifest_images: dict[str, dict[str, Any]],
    manifest_crops: dict[str, dict[str, int]],
    image_receipts: dict[str, dict[str, Any]],
    ref_cache: dict[str, np.ndarray],
    render_ms: list[float],
    work: Path,
    rows: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    for image_id, image_receipt in image_receipts.items():
        if args.image_id and image_id not in set(args.image_id):
            continue
        image_meta = manifest_images.get(image_id)
        if image_meta is None:
            missing.append({"image_id": image_id, "reason": "missing_manifest_image"})
            continue
        stitched_png = root / str(image_receipt["stitched_png"])
        if not stitched_png.exists():
            missing.append({"image_id": image_id, "reason": "missing_stitched_png", "path": str(stitched_png)})
            continue
        stitched = Image.open(stitched_png).convert("RGB")
        stitched_rgb = np.asarray(stitched, dtype=np.uint8)
        if image_id not in ref_cache:
            ref_dng = Path(str(image_receipt["ref_dng"]))
            ref_tiff = work / f"{image_id}_REF.tiff"
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
            ref_cache[image_id] = np.asarray(Image.open(ref_tiff).convert("RGB"), dtype=np.uint8)
        ref_image = Image.fromarray(ref_cache[image_id]).convert("RGB")
        crop_boxes = {
            name: scaled_box(crop, image_meta["sensor_dims"], stitched.size)
            for name, crop in manifest_crops.items()
        }
        tile_rows = selected_tile_boxes(
            width=stitched.size[0],
            height=stitched.size[1],
            tile=args.tile_size,
            stride=max(1, args.tile_size - args.overlap),
            mode=args.sample_mode,
            crop_boxes=crop_boxes,
            max_tiles=args.max_tiles_per_image,
            tile_offsets=args.tile_offsets,
        )
        stats = image_stats(stitched_rgb)
        for x0, y0, x1, y1, crop_hits in tile_rows:
            tile_name = f"tile_{x0}_{y0}"
            source_tile = stitched.crop((x0, y0, x1, y1)).convert("RGB")
            ref_box = map_box_between_sizes((x0, y0, x1, y1), stitched.size, ref_image.size)
            ref_tile = ref_image.crop(ref_box).convert("RGB")
            if ref_tile.size != source_tile.size:
                ref_tile = ref_tile.resize(source_tile.size, Image.Resampling.LANCZOS)
            source_png = args.out_dir / f"{image_id}_{tile_name}_stitched_source.png"
            ref_png = args.out_dir / f"{image_id}_{tile_name}_REF.png"
            source_tile.save(source_png)
            ref_tile.save(ref_png)
            rows.append(
                {
                    "image_id": image_id,
                    "crop": tile_name,
                    "source_label": "stitched_fullframe:no_ref_base_tile",
                    "source_png": str(source_png),
                    "source_png_resolved": str(source_png),
                    "ref_png": str(ref_png),
                    "source_render_size": [int(stitched.size[0]), int(stitched.size[1])],
                    "tile_xywh": [x0, y0, x1 - x0, y1 - y0],
                    "source_global_stats": stats,
                    "intersects_crops": crop_hits,
                }
            )


def build(args: argparse.Namespace) -> dict[str, Any]:
    fullframe = json.loads(args.fullframe_receipt.read_text())
    manifest = json.loads(args.manifest.read_text())
    crops = {name: crop for name, crop in manifest["crops"].items() if not name.startswith("$")}
    images_by_id = {str(image["id"]): image for image in manifest["images"]}
    image_receipts = {str(image["image_id"]): image for image in fullframe.get("images", [])}
    root = output_root(args.fullframe_receipt, fullframe)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_stitched_post_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    render_ms: list[float] = []
    try:
        ref_cache: dict[str, np.ndarray] = {}
        if args.sample_mode == "manifest_crops":
            append_manifest_crop_rows(
                args=args,
                fullframe=fullframe,
                root=root,
                manifest_images=images_by_id,
                manifest_crops=crops,
                image_receipts=image_receipts,
                ref_cache=ref_cache,
                render_ms=render_ms,
                work=work,
                rows=rows,
                missing=missing,
            )
        else:
            append_tile_rows(
                args=args,
                root=root,
                manifest_images=images_by_id,
                manifest_crops=crops,
                image_receipts=image_receipts,
                ref_cache=ref_cache,
                render_ms=render_ms,
                work=work,
                rows=rows,
                missing=missing,
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    payload = {
        "schema": "preview_stitched_post_receipt.v1",
        "fullframe_receipt": str(args.fullframe_receipt),
        "manifest": str(args.manifest),
        "out_dir": str(args.out_dir),
        "source_policy": "stitched_fullframe_no_ref_base_output",
        "sample_mode": args.sample_mode,
        "tile_size": args.tile_size if args.sample_mode != "manifest_crops" else None,
        "overlap": args.overlap if args.sample_mode != "manifest_crops" else None,
        "tile_offsets": args.tile_offsets if args.sample_mode != "manifest_crops" else None,
        "forbidden_render_inputs": ["REF image content", "REF HF/LF fields", "gate metrics"],
        "rows": rows,
        "missing": missing,
        "summary": {
            "rows": len(rows),
            "images": len({row["image_id"] for row in rows}),
            "missing": len(missing),
        },
        "timing": {
            "ref_render_count": len(render_ms),
            "ref_render_ms_total": float(sum(render_ms)),
            "ref_render_ms_median": float(sorted(render_ms)[len(render_ms) // 2]) if render_ms else 0.0,
        },
    }
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fullframe-receipt", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    parser.add_argument("--image-id", action="append", default=[])
    parser.add_argument("--sample-mode", choices=["manifest_crops", "intersect_tiles", "full_grid"], default="manifest_crops")
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=0)
    parser.add_argument("--tile-offset", action="append", default=[], help="Tile origin offset as X,Y pixels. Repeat for multi-origin receipts.")
    parser.add_argument("--max-tiles-per-image", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = parser.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.tile_offsets = parse_tile_offsets(args.tile_offset)
    payload = build(args)
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
