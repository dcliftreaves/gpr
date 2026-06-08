#!/usr/bin/env python3
"""Probe full-image frequency-band oracles for PREVIEW.

This diagnostic renders source and REF full images, then scores crop metrics
after exchanging low/high RGB bands at several Gaussian radii. REF-band
variants are oracle ceilings only. They identify which frequency bands the
next no-REF model must learn or preserve; they are not production candidates.
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
from PIL import Image, ImageFilter


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None


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


def crop_box(crop: dict[str, int], sensor_dims: list[int], image: Image.Image) -> tuple[int, int, int, int]:
    return scaled_box(crop, sensor_dims, image.size)


def crop_metric(image: Image.Image, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    out = image.crop(crop_box(crop, sensor_dims, image))
    if out.size != (512, 512):
        out = out.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(out.convert("RGB"), dtype=np.uint8)


def band_crop(
    *,
    low_image: Image.Image,
    high_image: Image.Image,
    low_blur: Image.Image,
    high_blur: Image.Image,
    crop: dict[str, int],
    sensor_dims: list[int],
) -> np.ndarray:
    box = crop_box(crop, sensor_dims, low_image)
    low = np.asarray(low_blur.crop(box).convert("RGB"), dtype=np.float32) / 255.0
    high = np.asarray(high_image.crop(box).convert("RGB"), dtype=np.float32) / 255.0
    high_low = np.asarray(high_blur.crop(box).convert("RGB"), dtype=np.float32) / 255.0
    out = np.clip(low + (high - high_low), 0.0, 1.0)
    pil = Image.fromarray((out * 255.0 + 0.5).astype(np.uint8))
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


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


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


def score_crop(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    image_id: str,
    crop_name: str,
    variant: str,
    ref_crop: np.ndarray,
    out_crop: np.ndarray,
) -> None:
    metrics = compute_visual_metrics(ref_crop, out_crop)
    metrics = {k: float(v) for k, v in metrics.items()}
    metrics["preview_pass"] = pass_preview(metrics)
    png_name = f"{image_id}_{crop_name}_{safe_name(variant)}.png"
    Image.fromarray(out_crop).save(args.output_dir / png_name)
    rows.append(
        {
            "image_id": image_id,
            "crop": crop_name,
            "variant": variant,
            "png": png_name,
            **metrics,
        }
    )


def selected_images(args: argparse.Namespace, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = set(args.image_id)
    images = [image for image in manifest["images"] if not wanted or str(image["id"]) in wanted]
    if not images:
        raise RuntimeError("no manifest images selected")
    return images


def collect(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images = selected_images(args, manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_freq_oracle_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    image_receipts: list[dict[str, Any]] = []
    render_ms: list[float] = []
    try:
        for image in images:
            image_id = str(image["id"])
            source_dng = resolve_source(image_id, args.source_root)
            if source_dng is None:
                raise FileNotFoundError(f"missing source DNG for {image_id}")
            ref_dng = resolve_ref(image, args.ref_root)
            source_tiff = work / f"{image_id}_source.tiff"
            ref_tiff = work / f"{image_id}_ref.tiff"
            print(f"[freq-oracle] render {image_id}", flush=True)
            render_ms.append(render_dng_to_tiff(source_dng, source_tiff))
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
            source = Image.open(source_tiff).convert("RGB")
            ref = Image.open(ref_tiff).convert("RGB")
            image_rows: list[dict[str, Any]] = []
            for crop_name, crop in crops.items():
                ref_crop = crop_metric(ref, crop, image["sensor_dims"])
                source_crop = crop_metric(source, crop, image["sensor_dims"])
                score_crop(
                    args=args,
                    rows=image_rows,
                    image_id=image_id,
                    crop_name=crop_name,
                    variant="source_baseline",
                    ref_crop=ref_crop,
                    out_crop=source_crop,
                )
                score_crop(
                    args=args,
                    rows=image_rows,
                    image_id=image_id,
                    crop_name=crop_name,
                    variant="ref_exact_oracle",
                    ref_crop=ref_crop,
                    out_crop=ref_crop,
                )
            for sigma in args.sigma:
                print(f"[freq-oracle] {image_id} sigma={sigma:g}", flush=True)
                source_blur = source.filter(ImageFilter.GaussianBlur(radius=float(sigma)))
                ref_blur = ref.filter(ImageFilter.GaussianBlur(radius=float(sigma)))
                for crop_name, crop in crops.items():
                    ref_crop = crop_metric(ref, crop, image["sensor_dims"])
                    variants = {
                        f"ref_low_source_high_s{sigma:g}": band_crop(
                            low_image=ref,
                            high_image=source,
                            low_blur=ref_blur,
                            high_blur=source_blur,
                            crop=crop,
                            sensor_dims=image["sensor_dims"],
                        ),
                        f"source_low_ref_high_s{sigma:g}": band_crop(
                            low_image=source,
                            high_image=ref,
                            low_blur=source_blur,
                            high_blur=ref_blur,
                            crop=crop,
                            sensor_dims=image["sensor_dims"],
                        ),
                    }
                    for variant, out_crop in variants.items():
                        score_crop(
                            args=args,
                            rows=image_rows,
                            image_id=image_id,
                            crop_name=crop_name,
                            variant=variant,
                            ref_crop=ref_crop,
                            out_crop=out_crop,
                        )
                source_blur.close()
                ref_blur.close()
            rows.extend(image_rows)
            image_receipts.append(
                {
                    "image_id": image_id,
                    "source_dng": str(source_dng),
                    "ref_dng": str(ref_dng),
                    "render_size": list(source.size),
                    "summary": aggregate(image_rows),
                }
            )
            source.close()
            ref.close()
            source_tiff.unlink(missing_ok=True)
            ref_tiff.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {
        "schema": "preview_fullimage_frequency_oracle.v1",
        "manifest": str(args.manifest),
        "thresholds": PREVIEW,
        "source_roots": [str(path) for path in args.source_root],
        "ref_roots": [str(path) for path in args.ref_root],
        "image_ids": [str(image["id"]) for image in images],
        "sigmas": [float(v) for v in args.sigma],
        "oracle_variants_not_allowed_for_production": [
            "ref_exact_oracle",
            "ref_low_source_high_s*",
            "source_low_ref_high_s*",
        ],
        "timing": {
            "render_ms_total": float(sum(render_ms)),
            "render_ms_median": float(np.median(render_ms)) if render_ms else 0.0,
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
        "<!doctype html><meta charset='utf-8'><title>PREVIEW full-image frequency oracle</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Image Frequency Oracle</h1>",
        "<p>REF-band variants are oracle ceilings for diagnosis only and are not production candidates.</p>",
        "<div class=cards>",
        f"<div class=card><b>Best variant</b><br>{html.escape(str(best.get('variant', 'n/a')))}</div>",
        f"<div class=card><b>Best pass</b><br>{best.get('pass_count', 0)}/{best.get('count', 0)}</div>",
        f"<div class=card><b>Worst LPIPS</b><br>{fmt(float(best.get('worst_lpips', 0.0)))}</div>",
        f"<div class=card><b>Worst dE</b><br>{fmt(float(best.get('worst_dE2000_mean', 0.0)))}</div>",
        "</div><h2>Summary</h2><table><thead><tr><th class=left>variant</th><th>pass</th><th>rate</th><th class=left>worst</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['variant'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate'] * 100:.1f}%</td><td class=left>{html.escape(row['worst_image'])} {html.escape(row['worst_crop'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td></tr>"
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--sigma", type=float, action="append", default=None)
    ap.add_argument(
        "--source-root",
        type=Path,
        action="append",
        default=[
            Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607/editable_dng"),
            Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng"),
            Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/editable_dng"),
        ],
    )
    ap.add_argument(
        "--ref-root",
        type=Path,
        action="append",
        default=[
            Path("/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"),
            Path("/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs"),
        ],
    )
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    if args.sigma is None:
        args.sigma = [2.0, 4.0, 8.0, 16.0, 32.0]
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.output_html)
    for row in payload["summary"][:16]:
        print(
            f"{row['variant']:<30} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
