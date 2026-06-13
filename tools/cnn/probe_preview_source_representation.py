#!/usr/bin/env python3
"""Compare runtime-legal source representations for PREVIEW.

This diagnostic scores the same manifest crops from several source render
paths against the existing REF render. It is intended to separate a source
representation/rendering problem from a model-capacity problem before another
PREVIEW CNN pass.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import rawpy
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box, sha256_file  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None


def render_sips(dng_path: Path, tiff_path: Path) -> float:
    t0 = time.perf_counter()
    result = subprocess.run(
        ["sips", "-s", "format", "tiff", str(dng_path), "--out", str(tiff_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed for {dng_path}: {result.stderr[-500:]}")
    return (time.perf_counter() - t0) * 1000.0


def rawpy_postprocess(dng_path: Path, *, use_camera_wb: bool, no_auto_bright: bool) -> tuple[Image.Image, float]:
    t0 = time.perf_counter()
    with rawpy.imread(str(dng_path)) as raw:
        rgb = raw.postprocess(
            use_camera_wb=use_camera_wb,
            no_auto_bright=no_auto_bright,
            output_bps=8,
            user_flip=0,
        )
    return Image.fromarray(rgb, "RGB"), (time.perf_counter() - t0) * 1000.0


def load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def resized_dims(width: int, height: int, max_width: int) -> tuple[int, int]:
    if width <= max_width:
        return width, height
    out_w = int(max_width)
    out_h = max(1, int(round(height * (out_w / width))))
    return out_w, out_h


def downsample(image: Image.Image, max_width: int | None) -> Image.Image:
    if max_width is None:
        return image.copy()
    size = resized_dims(image.size[0], image.size[1], max_width)
    if size == image.size:
        return image.copy()
    return image.resize(size, Image.Resampling.LANCZOS)


def crop_metric_image(image: Image.Image, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, image.size)
    out = image.crop(box)
    if out.size != (512, 512):
        out = out.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(out.convert("RGB"), dtype=np.uint8)


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


def selected_images(args: argparse.Namespace, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = set(args.image_id)
    images = [image for image in manifest["images"] if not wanted or str(image["id"]) in wanted]
    if not images:
        raise RuntimeError("no manifest images selected")
    return images


def score_crop(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    image_id: str,
    crop_name: str,
    variant: str,
    ref_crop: np.ndarray,
    out_crop: np.ndarray,
    source_size: tuple[int, int],
    render_ms: float,
) -> None:
    metrics = {k: float(v) for k, v in compute_visual_metrics(ref_crop, out_crop).items()}
    metrics["preview_pass"] = pass_preview(metrics)
    png_name = f"{image_id}_{crop_name}_{safe_name(variant)}.png"
    Image.fromarray(out_crop).save(args.output_dir / png_name)
    rows.append(
        {
            "image_id": image_id,
            "crop": crop_name,
            "variant": variant,
            "source_size": list(source_size),
            "render_ms": float(render_ms),
            "png": png_name,
            **metrics,
        }
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "worst_lpips": 0.0,
            "median_lpips": 0.0,
            "worst_ms_ssim": 0.0,
            "worst_y_psnr": 0.0,
            "worst_dE2000_mean": 0.0,
            "median_render_ms": 0.0,
        }
    pass_count = sum(1 for row in rows if row["preview_pass"])
    return {
        "count": len(rows),
        "pass_count": pass_count,
        "pass_rate": pass_count / len(rows),
        "worst_lpips": max(float(row["lpips"]) for row in rows),
        "median_lpips": float(np.median([float(row["lpips"]) for row in rows])),
        "worst_ms_ssim": min(float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(float(row["dE2000_mean"]) for row in rows),
        "median_render_ms": float(np.median([float(row["render_ms"]) for row in rows])),
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for variant in sorted({str(row["variant"]) for row in rows}):
        vr = [row for row in rows if str(row["variant"]) == variant]
        worst = max(vr, key=lambda row: (float(row["lpips"]), -float(row["ms_ssim"])))
        out.append(
            {
                "variant": variant,
                "worst_image": worst["image_id"],
                "worst_crop": worst["crop"],
                **summarize(vr),
            }
        )
    out.sort(key=lambda row: (row["pass_count"] != row["count"], -row["pass_count"], row["worst_lpips"]))
    return out


def metadata(path: Path) -> dict[str, Any]:
    tags = [
        "-ImageWidth",
        "-ImageHeight",
        "-DefaultCropSize",
        "-DefaultCropOrigin",
        "-AsShotNeutral",
        "-ProfileName",
        "-UniqueCameraModel",
        "-ISO",
        "-NoiseProfile",
    ]
    result = subprocess.run(["exiftool", "-json", *tags, str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        return {"error": result.stderr[-400:]}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"error": str(exc)}
    if not payload:
        return {}
    out = payload[0]
    out.pop("SourceFile", None)
    return out


def source_variants(args: argparse.Namespace, image_id: str, source_dng: Path, work: Path) -> list[tuple[str, Image.Image, float, str]]:
    variants: list[tuple[str, Image.Image, float, str]] = []
    source_tiff = work / f"{image_id}_source_sips.tiff"
    sips_ms = render_sips(source_dng, source_tiff)
    variants.append(("editable_dng_sips", load_rgb(source_tiff), sips_ms, str(source_dng)))

    frame_tiff = args.frame_root / f"{image_id}.tiff"
    if frame_tiff.exists():
        variants.append(("clean_bundle_frame_tiff", load_rgb(frame_tiff), 0.0, str(frame_tiff)))

    if args.rawpy:
        rawpy_camera, rawpy_camera_ms = rawpy_postprocess(source_dng, use_camera_wb=True, no_auto_bright=True)
        variants.append(("editable_dng_rawpy_camera_noauto", rawpy_camera, rawpy_camera_ms, str(source_dng)))
        rawpy_auto, rawpy_auto_ms = rawpy_postprocess(source_dng, use_camera_wb=True, no_auto_bright=False)
        variants.append(("editable_dng_rawpy_camera_auto", rawpy_auto, rawpy_auto_ms, str(source_dng)))

    return variants


def collect(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images = selected_images(args, manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_source_repr_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    image_receipts: list[dict[str, Any]] = []
    ref_render_ms: list[float] = []
    try:
        for image in images:
            image_id = str(image["id"])
            source_dng = resolve_source(image_id, args.source_root)
            if source_dng is None:
                raise FileNotFoundError(f"missing source DNG for {image_id}")
            ref_dng = resolve_ref(image, args.ref_root)
            ref_tiff = work / f"{image_id}_ref_sips.tiff"
            print(f"[source-repr] render REF {image_id}", flush=True)
            ref_render_ms.append(render_sips(ref_dng, ref_tiff))
            ref = load_rgb(ref_tiff)
            image_rows: list[dict[str, Any]] = []
            variants = source_variants(args, image_id, source_dng, work)
            for variant, source, render_ms, source_path in variants:
                for max_width in args.max_width:
                    suffix = "fullres" if max_width is None else f"w{max_width}"
                    field = downsample(source, max_width)
                    variant_name = f"{variant}_{suffix}"
                    print(f"[source-repr] {image_id} {variant_name}", flush=True)
                    for crop_name, crop in crops.items():
                        ref_crop = crop_metric_image(ref, crop, image["sensor_dims"])
                        out_crop = crop_metric_image(field, crop, image["sensor_dims"])
                        score_crop(
                            args=args,
                            rows=image_rows,
                            image_id=image_id,
                            crop_name=crop_name,
                            variant=variant_name,
                            ref_crop=ref_crop,
                            out_crop=out_crop,
                            source_size=field.size,
                            render_ms=render_ms,
                        )
                    field.close()
                image_receipts.append(
                    {
                        "image_id": image_id,
                        "variant": variant,
                        "source_path": source_path,
                        "source_size": list(source.size),
                        "render_ms": float(render_ms),
                    }
                )
                source.close()
            rows.extend(image_rows)
            image_receipts.append(
                {
                    "image_id": image_id,
                    "ref_dng": str(ref_dng),
                    "source_dng": str(source_dng),
                    "ref_metadata": metadata(ref_dng),
                    "source_metadata": metadata(source_dng),
                    "summary": aggregate(image_rows),
                }
            )
            ref.close()
            ref_tiff.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "schema": "preview_source_representation_probe.v1",
        "manifest": str(args.manifest),
        "tool_sha256": sha256_file(Path(__file__)),
        "thresholds": PREVIEW,
        "source_roots": [str(path) for path in args.source_root],
        "ref_roots": [str(path) for path in args.ref_root],
        "frame_root": str(args.frame_root),
        "image_ids": [str(image["id"]) for image in images],
        "max_widths": ["fullres" if value is None else int(value) for value in args.max_width],
        "render_contract": {
            "uses_ref_at_render_time": False,
            "ref_usage": "scoring only",
            "question": "whether an existing runtime-legal source representation is closer than editable DNG rendered by sips",
        },
        "timing": {
            "ref_render_ms_total": float(sum(ref_render_ms)),
            "ref_render_ms_median": float(np.median(ref_render_ms)) if ref_render_ms else 0.0,
        },
        "summary": aggregate(rows),
        "images": image_receipts,
        "rows": rows,
    }


def write_html(payload: dict[str, Any], out: Path) -> None:
    def fmt(value: float) -> str:
        return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"

    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f7f8f9; color:#222; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(170px,1fr)); gap:10px; margin:14px 0; }
.card,.tile { background:#fff; border:1px solid #d4d8de; border-radius:6px; padding:10px; }
table { border-collapse:collapse; background:#fff; width:100%; font-size:12px; margin:14px 0; }
td,th { border:1px solid #ccd2d9; padding:5px 7px; text-align:right; }
th.left,td.left { text-align:left; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
.tile img { width:100%; display:block; border:1px solid #ddd; }
"""
    best = payload["summary"][0] if payload["summary"] else {}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW source representation probe</title>",
        f"<style>{css}</style><h1>PREVIEW Source Representation Probe</h1>",
        "<p>All source variants are runtime-legal inputs. REF is used only for scoring.</p>",
        "<div class=cards>",
        f"<div class=card><b>Best variant</b><br>{html.escape(str(best.get('variant', 'n/a')))}</div>",
        f"<div class=card><b>Best pass</b><br>{best.get('pass_count', 0)}/{best.get('count', 0)}</div>",
        f"<div class=card><b>Worst LPIPS</b><br>{fmt(float(best.get('worst_lpips', 0.0)))}</div>",
        f"<div class=card><b>Worst dE</b><br>{fmt(float(best.get('worst_dE2000_mean', 0.0)))}</div>",
        "</div><h2>Summary</h2><table><thead><tr><th class=left>variant</th><th>pass</th><th>rate</th><th class=left>worst</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th><th>median render ms</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['variant'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate'] * 100:.1f}%</td><td class=left>{html.escape(row['worst_image'])} {html.escape(row['worst_crop'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td>"
            f"<td>{row['median_render_ms']:.1f}</td></tr>"
        )
    rows = sorted(payload["rows"], key=lambda row: (not row["preview_pass"], row["lpips"], row["dE2000_mean"]), reverse=True)[:96]
    parts.append("</tbody></table><h2>Worst Rows</h2><div class=grid>")
    for row in rows:
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<div class=tile><b>{html.escape(row['image_id'])} {html.escape(row['crop'])}</b>"
            f"<br>{html.escape(row['variant'])}"
            f"<br><span class={cls}>LPIPS {row['lpips']:.4f}, MS {row['ms_ssim']:.4f}, "
            f"Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            f"<img src='{html.escape(row['png'])}'></div>"
        )
    parts.append("</div>")
    out.write_text("".join(parts))


def parse_max_width(values: list[str] | None) -> list[int | None]:
    if not values:
        return [None, 6144, 4096]
    out: list[int | None] = []
    for value in values:
        if value.lower() in ("none", "full", "fullres"):
            out.append(None)
        else:
            out.append(int(value))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--source-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607/editable_dng"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/editable_dng"),
    ])
    ap.add_argument("--ref-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"),
        Path("/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs"),
    ])
    ap.add_argument("--frame-root", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607/frames"))
    ap.add_argument("--max-width", action="append", default=None)
    ap.add_argument("--rawpy", action="store_true")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.max_width = parse_max_width(args.max_width)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    for row in payload["summary"]:
        print(
            f"{row['variant']:<48} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
