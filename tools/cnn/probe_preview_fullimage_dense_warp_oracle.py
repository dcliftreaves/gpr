#!/usr/bin/env python3
"""Probe whether dense REF-guided warping closes the full-image PREVIEW gap.

This diagnostic renders full source and REF images, downsamples them to a fixed
working width, estimates dense optical flow using REF and source luminance, and
scores manifest crops from warped source fields. The flow uses REF, so every
warped variant is an oracle only. It answers whether the remaining no-REF
PREVIEW blocker is mostly local geometry/detail placement, or whether warping
the current source representation is still insufficient.
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
from PIL import Image
from skimage.registration import optical_flow_ilk, optical_flow_tvl1
from skimage.transform import warp


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box, sha256_file  # noqa: E402
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
        raise RuntimeError(f"sips failed for {dng_path}: {result.stderr[-500:]}")
    return (time.perf_counter() - t0) * 1000.0


def load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def resized_dims(width: int, height: int, max_width: int) -> tuple[int, int]:
    if width <= max_width:
        return width, height
    out_w = int(max_width)
    out_h = max(1, int(round(height * (out_w / width))))
    return out_w, out_h


def downsample(image: Image.Image, max_width: int) -> Image.Image:
    size = resized_dims(image.size[0], image.size[1], max_width)
    if size == image.size:
        return image.copy()
    return image.resize(size, Image.Resampling.LANCZOS)


def resize_like(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    if image.size == size:
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


def gray01(rgb: np.ndarray) -> np.ndarray:
    arr = rgb.astype(np.float32) / 255.0
    return (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]).astype(np.float32)


def estimate_flow(ref_rgb: np.ndarray, source_rgb: np.ndarray, method: str) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    ref_gray = gray01(ref_rgb)
    source_gray = gray01(source_rgb)
    t0 = time.perf_counter()
    if method == "tvl1":
        v, u = optical_flow_tvl1(ref_gray, source_gray)
    elif method == "ilk":
        v, u = optical_flow_ilk(ref_gray, source_gray, radius=7)
    else:
        raise ValueError(f"unsupported flow method {method!r}")
    flow_ms = (time.perf_counter() - t0) * 1000.0
    mag = np.sqrt((u.astype(np.float32) ** 2) + (v.astype(np.float32) ** 2))
    return v.astype(np.float32), u.astype(np.float32), {
        "flow_ms": float(flow_ms),
        "flow_px_median": float(np.median(mag)),
        "flow_px_p95": float(np.percentile(mag, 95)),
        "flow_px_max": float(np.max(mag)),
    }


def warp_rgb(source_rgb: np.ndarray, v: np.ndarray, u: np.ndarray, sign: float) -> np.ndarray:
    rows, cols = source_rgb.shape[:2]
    rr, cc = np.meshgrid(np.arange(rows, dtype=np.float32), np.arange(cols, dtype=np.float32), indexing="ij")
    coords = np.array([rr + sign * v, cc + sign * u], dtype=np.float32)
    src01 = source_rgb.astype(np.float32) / 255.0
    out = np.empty_like(src01)
    for channel in range(3):
        out[..., channel] = warp(
            src01[..., channel],
            coords,
            mode="edge",
            preserve_range=True,
        ).astype(np.float32)
    return (np.clip(out, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def score_crop(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    image_id: str,
    crop_name: str,
    variant: str,
    max_width: int,
    ref_crop: np.ndarray,
    out_crop: np.ndarray,
    fit: dict[str, float] | None = None,
) -> None:
    metrics = {k: float(v) for k, v in compute_visual_metrics(ref_crop, out_crop).items()}
    metrics["preview_pass"] = pass_preview(metrics)
    png_name = f"{image_id}_{crop_name}_{safe_name(variant)}.png"
    Image.fromarray(out_crop).save(args.output_dir / png_name)
    row = {
        "image_id": image_id,
        "crop": crop_name,
        "variant": variant,
        "max_width": int(max_width),
        "png": png_name,
        **metrics,
    }
    if fit:
        row.update(fit)
    rows.append(row)


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
    work = Path(tempfile.mkdtemp(prefix="preview_dense_warp_oracle_", dir=args.tmp_dir))
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
            print(f"[dense-warp-oracle] render {image_id}", flush=True)
            render_ms.append(render_dng_to_tiff(source_dng, source_tiff))
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
            source = load_rgb(source_tiff)
            ref = load_rgb(ref_tiff)
            image_rows: list[dict[str, Any]] = []
            for max_width in args.max_width:
                print(f"[dense-warp-oracle] {image_id} max_width={max_width}", flush=True)
                source_low = downsample(source, max_width)
                ref_low = resize_like(downsample(ref, max_width), source_low.size)
                source_arr = np.asarray(source_low, dtype=np.uint8)
                ref_arr = np.asarray(ref_low, dtype=np.uint8)
                for crop_name, crop in crops.items():
                    ref_crop = crop_metric_image(ref, crop, image["sensor_dims"])
                    score_crop(
                        args=args,
                        rows=image_rows,
                        image_id=image_id,
                        crop_name=crop_name,
                        variant=f"source_baseline_w{max_width}",
                        max_width=max_width,
                        ref_crop=ref_crop,
                        out_crop=crop_metric_image(source_low, crop, image["sensor_dims"]),
                    )
                for method in args.method:
                    print(f"[dense-warp-oracle] {image_id} method={method}", flush=True)
                    v, u, fit = estimate_flow(ref_arr, source_arr, method)
                    for sign, label in ((1.0, "plus"), (-1.0, "minus")):
                        warped = Image.fromarray(warp_rgb(source_arr, v, u, sign))
                        variant = f"dense_warp_{method}_{label}_w{max_width}"
                        for crop_name, crop in crops.items():
                            ref_crop = crop_metric_image(ref, crop, image["sensor_dims"])
                            score_crop(
                                args=args,
                                rows=image_rows,
                                image_id=image_id,
                                crop_name=crop_name,
                                variant=variant,
                                max_width=max_width,
                                ref_crop=ref_crop,
                                out_crop=crop_metric_image(warped, crop, image["sensor_dims"]),
                                fit=fit,
                            )
                        warped.close()
                source_low.close()
                ref_low.close()
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
        "schema": "preview_fullimage_dense_warp_oracle.v1",
        "manifest": str(args.manifest),
        "tool_sha256": sha256_file(Path(__file__)),
        "thresholds": PREVIEW,
        "source_roots": [str(path) for path in args.source_root],
        "ref_roots": [str(path) for path in args.ref_root],
        "image_ids": [str(image["id"]) for image in images],
        "max_widths": [int(v) for v in args.max_width],
        "methods": [str(v) for v in args.method],
        "oracle_variants_not_allowed_for_production": ["dense_warp_*_w*"],
        "render_contract": {
            "uses_ref_to_estimate_dense_flow": True,
            "production_allowed": False,
            "question": "whether REF-guided dense local warping closes the full-image PREVIEW source/REF mismatch",
        },
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
        "<!doctype html><meta charset='utf-8'><title>PREVIEW dense warp oracle</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Image Dense Warp Oracle</h1>",
        "<p>Dense warp variants estimate optical flow from REF/source luminance and are diagnostic only.</p>",
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
    ap.add_argument("--source-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607/editable_dng"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/editable_dng"),
    ])
    ap.add_argument("--ref-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"),
        Path("/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs"),
    ])
    ap.add_argument("--max-width", type=int, action="append", default=None)
    ap.add_argument("--method", action="append", choices=["tvl1", "ilk"], default=None)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    if args.max_width is None:
        args.max_width = [1024]
    if args.method is None:
        args.method = ["tvl1"]
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    for row in payload["summary"]:
        print(
            f"{row['variant']:<36} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
