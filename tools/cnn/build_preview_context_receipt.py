#!/usr/bin/env python3
"""Build larger-context PREVIEW crop pairs from a runtime source receipt.

The normal PREVIEW holdout receipt stores 512x512 crop pairs. This diagnostic
builder re-renders the same source/REF DNGs, expands each crop around the same
center, and writes larger RGB crop PNGs. A companion evaluator can then render
the larger source crop and compute metrics on the centered 512 region.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image


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


def expanded_box(box: list[int], render_size: tuple[int, int], scale: float) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = [int(v) for v in box]
    width = x1 - x0
    height = y1 - y0
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    out_w = max(1, int(round(width * scale)))
    out_h = max(1, int(round(height * scale)))
    render_w, render_h = render_size
    nx0 = int(round(cx - out_w / 2.0))
    ny0 = int(round(cy - out_h / 2.0))
    nx0 = min(max(0, nx0), max(0, render_w - out_w))
    ny0 = min(max(0, ny0), max(0, render_h - out_h))
    return nx0, ny0, nx0 + out_w, ny0 + out_h


def save_context_crop(
    render_path: Path,
    out_path: Path,
    base_box: list[int],
    output_size: int,
    scale: float,
) -> dict[str, Any]:
    with Image.open(render_path) as image:
        rgb = image.convert("RGB")
        box = expanded_box(base_box, rgb.size, scale)
        crop = rgb.crop(box)
        if crop.size != (output_size, output_size):
            crop = crop.resize((output_size, output_size), Image.Resampling.LANCZOS)
        crop.save(out_path)
        return {"render_size": list(rgb.size), "crop_box_render": list(box)}


def load_cluster_map(path: Path | None) -> dict[tuple[str, str], int]:
    if path is None:
        return {}
    payload = json.loads(path.read_text())
    out: dict[tuple[str, str], int] = {}
    for row in payload.get("rows") or []:
        out[(str(row["image_id"]), str(row["crop"]))] = int(row["cluster"])
    return out


def build(args: argparse.Namespace) -> dict[str, Any]:
    base = json.loads(args.base_receipt.read_text())
    cluster_map = load_cluster_map(args.cluster_receipt)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_context_render_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    render_ms: list[float] = []
    render_cache: dict[Path, Path] = {}
    try:
        for row in base.get("rows") or []:
            image_id = str(row["image_id"])
            crop = str(row["crop"])
            ref_dng = Path(str(row["ref_dng"]))
            source_dng = Path(str(row["source_dng"]))
            if not ref_dng.exists() or not source_dng.exists():
                continue
            ref_render = render_cache.get(ref_dng)
            if ref_render is None:
                ref_render = work / f"{ref_dng.stem}_{len(render_cache)}_ref.tiff"
                render_ms.append(render_dng_to_tiff(ref_dng, ref_render))
                render_cache[ref_dng] = ref_render
            source_render = render_cache.get(source_dng)
            if source_render is None:
                source_render = work / f"{source_dng.stem}_{len(render_cache)}_source.tiff"
                render_ms.append(render_dng_to_tiff(source_dng, source_render))
                render_cache[source_dng] = source_render

            ref_png = args.out_dir / f"{image_id}_{crop}_REF_context{args.output_size}.png"
            source_png = args.out_dir / f"{image_id}_{crop}_upresable_context{args.output_size}.png"
            ref_meta = save_context_crop(
                ref_render,
                ref_png,
                row["ref_render"]["crop_box_render"],
                args.output_size,
                args.context_scale,
            )
            source_meta = save_context_crop(
                source_render,
                source_png,
                row["source_render"]["crop_box_render"],
                args.output_size,
                args.context_scale,
            )
            out_row = {
                **row,
                "source_label": f"{args.out_dir.name}:upresable_context{args.output_size}",
                "source_png": str(source_png),
                "ref_png": str(ref_png),
                "context_scale": args.context_scale,
                "output_size": args.output_size,
                "metric_center_size": args.metric_center_size,
                "ref_render": ref_meta,
                "source_render": source_meta,
            }
            cluster = cluster_map.get((image_id, crop))
            if cluster is not None:
                out_row["cluster"] = cluster
            rows.append(out_row)
    finally:
        if not args.keep_renders:
            shutil.rmtree(work, ignore_errors=True)

    return {
        "schema": "preview_context_runtime_source_receipt.v1",
        "base_receipt": str(args.base_receipt),
        "cluster_receipt": str(args.cluster_receipt) if args.cluster_receipt else None,
        "out_dir": str(args.out_dir),
        "context_scale": args.context_scale,
        "output_size": args.output_size,
        "metric_center_size": args.metric_center_size,
        "rows": rows,
        "summary": {
            "base_rows": len(base.get("rows") or []),
            "rows": len(rows),
            "images": len({row["image_id"] for row in rows}),
        },
        "timing": {
            "render_count": len(render_ms),
            "render_ms_total": sum(render_ms),
            "render_ms_median": sorted(render_ms)[len(render_ms) // 2] if render_ms else 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-receipt", type=Path, required=True)
    parser.add_argument("--cluster-receipt", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    parser.add_argument("--context-scale", type=float, default=1.5)
    parser.add_argument("--output-size", type=int, default=768)
    parser.add_argument("--metric-center-size", type=int, default=512)
    parser.add_argument("--keep-renders", action="store_true")
    args = parser.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = build(args)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
