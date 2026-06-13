#!/usr/bin/env python3
"""Build full-frame PREVIEW source PNGs from a registered codec pipeline."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import sha256_file  # noqa: E402
from score_preview_codec_teacher_sources import render_pipeline_png  # noqa: E402


DEFAULT_PIPELINE = "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools"


def select_images(manifest: dict[str, Any], image_ids: list[str], limit: int) -> list[dict[str, Any]]:
    selected = set(image_ids)
    images = [image for image in manifest["images"] if not selected or str(image["id"]) in selected]
    if limit:
        images = images[:limit]
    if not images:
        raise RuntimeError("no manifest images selected")
    return images


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--registry", type=Path, default=REPO / "pipelines/registry.json")
    ap.add_argument("--pipeline", default=DEFAULT_PIPELINE)
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    registry = json.loads(args.registry.read_text())
    if args.pipeline not in registry["pipelines"]:
        raise KeyError(f"unknown pipeline {args.pipeline}")
    images = select_images(manifest, args.image_id, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    work = Path(tempfile.mkdtemp(prefix="preview_codec_source_fullframes_", dir=args.tmp_dir))
    try:
        for image in images:
            image_id = str(image["id"])
            print(f"[codec-source-fullframe] {image_id} {args.pipeline}", flush=True)
            png, timing = render_pipeline_png(image, args.pipeline, registry, work)
            out_png = args.output_dir / f"{image_id}_{args.pipeline.replace('+', '_').replace('=', '-').replace('/', '_')}.png"
            png.replace(out_png)
            rows.append(
                {
                    "image_id": image_id,
                    "source_dng": str(image["path"]),
                    "stitched_png": out_png.name,
                    "stitched_sha256": sha256_file(out_png),
                    "stitched_bytes": out_png.stat().st_size,
                    "timing": timing,
                }
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    payload = {
        "schema": "preview_codec_source_fullframes.v1",
        "manifest": str(args.manifest),
        "pipeline": args.pipeline,
        "render_contract": {
            "render_time_inputs": ["source_dng", "registered codec pipeline"],
            "uses_ref_at_render_time": False,
            "intended_use": "runtime source receipt for full-image PREVIEW candidate training/evaluation",
        },
        "images": rows,
    }
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    total_bytes = sum(int(row["stitched_bytes"]) for row in rows)
    print(f"images={len(rows)} bytes={total_bytes}")
    print(args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
