#!/usr/bin/env python3
"""Build a PREVIEW exact-crop teacher distillation receipt.

Rows use arbitrary full-frame tiled PREVIEW output as the runtime source and
exact manifest-crop PREVIEW output as the supervised teacher. REF is not the
teacher for this receipt; it is copied only as optional metadata for later
scoring dashboards.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["image_id"]), str(row["crop"])


def rows_by_key(receipt: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {row_key(row): row for row in receipt.get("rows") or []}


def images_by_id(receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["image_id"]): row for row in receipt.get("images") or []}


def copy_named(src: Path, dst: Path) -> None:
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)


def image_stats(path: Path) -> dict[str, float]:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    gray = rgb.mean(axis=2)
    return {
        "r_mean": float(rgb[:, :, 0].mean()),
        "g_mean": float(rgb[:, :, 1].mean()),
        "b_mean": float(rgb[:, :, 2].mean()),
        "gray_std": float(gray.std()),
    }


def optional_path(root: Path, row: dict[str, Any], key: str) -> Path | None:
    value = row.get(key)
    if value is None:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return root / path


def build(args: argparse.Namespace) -> dict[str, Any]:
    exact_receipt = json.loads(args.exact_receipt.read_text())
    tiled_receipt = json.loads(args.tiled_receipt.read_text())
    source_receipt = json.loads(args.source_receipt.read_text()) if args.source_receipt else None
    exact_rows = rows_by_key(exact_receipt)
    tiled_rows = rows_by_key(tiled_receipt)
    tiled_images = images_by_id(tiled_receipt)
    source_rows = rows_by_key(source_receipt) if source_receipt else {}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for key in sorted(set(exact_rows) & set(tiled_rows)):
        image_id, crop = key
        if args.image_id and image_id not in set(args.image_id):
            continue
        exact_row = exact_rows[key]
        tiled_row = tiled_rows[key]
        exact_path = optional_path(args.exact_receipt.parent, exact_row, "png")
        tiled_path = optional_path(args.tiled_receipt.parent, tiled_row, "png")
        if exact_path is None or not exact_path.exists():
            missing.append({"image_id": image_id, "crop": crop, "reason": "missing_exact_teacher"})
            continue
        if tiled_path is None or not tiled_path.exists():
            missing.append({"image_id": image_id, "crop": crop, "reason": "missing_tiled_source"})
            continue

        out_source = args.out_dir / f"{image_id}_{crop}_tiled_source.png"
        out_teacher = args.out_dir / f"{image_id}_{crop}_exact_teacher.png"
        copy_named(tiled_path, out_source)
        copy_named(exact_path, out_teacher)
        context_path = None
        if args.include_global_context:
            image_receipt = tiled_images.get(image_id) or {}
            stitched_name = image_receipt.get("stitched_png") or image_receipt.get("stitched_output")
            if not stitched_name:
                missing.append({"image_id": image_id, "crop": crop, "reason": "missing_stitched_context"})
                continue
            stitched_path = Path(str(stitched_name))
            if not stitched_path.is_absolute():
                stitched_path = args.tiled_receipt.parent / stitched_path
            if not stitched_path.exists():
                missing.append({"image_id": image_id, "crop": crop, "reason": "missing_stitched_context_file", "path": str(stitched_path)})
                continue
            with Image.open(out_source) as source_image, Image.open(stitched_path) as stitched_image:
                context_path = args.out_dir / f"{image_id}_{crop}_global_context.png"
                stitched_image.convert("RGB").resize(source_image.size, Image.Resampling.BILINEAR).save(context_path)

        row: dict[str, Any] = {
            "image_id": image_id,
            "crop": crop,
            "source_label": "tiled_fullframe:no_ref_output",
            "source_png": str(out_source),
            "source_png_resolved": str(out_source),
            "ref_png": str(out_teacher),
            "teacher_png": str(out_teacher),
            "context_png": str(context_path) if context_path is not None else None,
            "source_global_stats": image_stats(out_source),
            "tiled_metrics_vs_ref": {
                k: tiled_row[k]
                for k in ("lpips", "ms_ssim", "y_psnr", "dE2000_mean", "preview_pass")
                if k in tiled_row
            },
            "exact_teacher_metrics_vs_ref": {
                k: exact_row[k]
                for k in ("lpips", "ms_ssim", "y_psnr", "dE2000_mean", "preview_pass")
                if k in exact_row
            },
        }
        source_row = source_rows.get(key)
        if source_row:
            source_ref = optional_path(args.source_receipt.parent, source_row, "ref_png") if args.source_receipt else None
            if source_ref is not None and source_ref.exists():
                true_ref = args.out_dir / f"{image_id}_{crop}_REF_for_scoring.png"
                copy_named(source_ref, true_ref)
                row["true_ref_png"] = str(true_ref)
            source_render = source_row.get("source_render") or {}
            if source_render:
                row["source_render"] = source_render
        rows.append(row)

    return {
        "schema": "preview_exact_teacher_distill_receipt.v1",
        "exact_receipt": str(args.exact_receipt),
        "tiled_receipt": str(args.tiled_receipt),
        "source_receipt": str(args.source_receipt) if args.source_receipt else None,
        "out_dir": str(args.out_dir),
        "runtime_contract": {
            "source_policy": "tiled_fullframe_no_ref_output_to_exact_crop_no_ref_teacher",
            "teacher": "exact manifest-crop no-REF PREVIEW output",
            "global_context": "resized tiled no-REF full-frame output" if args.include_global_context else None,
            "forbidden_render_inputs": [
                "REF image content",
                "REF HF/LF fields",
                "winner JSON",
                "sample index",
                "crop identity key planes",
                "gate metrics",
            ],
            "render_inputs": [
                item
                for item in [
                    "tiled no-REF RGB crop/full frame",
                    "resized tiled no-REF full-frame context" if args.include_global_context else None,
                    "normalized pixel coordinates",
                    "checkpoint",
                ]
                if item is not None
            ],
        },
        "summary": {
            "rows": len(rows),
            "images": len({row["image_id"] for row in rows}),
            "missing": len(missing),
            "teacher_pass_vs_ref": sum(1 for row in rows if row["exact_teacher_metrics_vs_ref"].get("preview_pass")),
            "source_pass_vs_ref": sum(1 for row in rows if row["tiled_metrics_vs_ref"].get("preview_pass")),
        },
        "rows": rows,
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exact-receipt", type=Path, required=True)
    parser.add_argument("--tiled-receipt", type=Path, required=True)
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--include-global-context", action="store_true")
    parser.add_argument("--image-id", action="append", default=[])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(args.out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
