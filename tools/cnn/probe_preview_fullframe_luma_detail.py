#!/usr/bin/env python3
"""Probe full-frame Lab-L detail recoverability for PREVIEW.

This diagnostic reads a full-frame PREVIEW stitched receipt and asks whether
the remaining tiled-render failures can be closed by replacing luma structure
with runtime-safe source detail. REF detail variants are oracle ceilings only;
they must not be registered or used in production rendering.
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
from skimage import color
from skimage.filters import gaussian


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import scaled_box  # noqa: E402
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


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)


def blur_l(l_chan: np.ndarray, sigma: float) -> np.ndarray:
    return gaussian(l_chan, sigma=sigma, mode="reflect", preserve_range=True).astype(np.float32)


def resize_rgb_like(rgb: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    if rgb.shape[:2] == (height, width):
        return rgb
    return np.asarray(Image.fromarray(rgb).resize((width, height), Image.Resampling.LANCZOS), dtype=np.uint8)


def crop_rgb(rgb: np.ndarray, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (rgb.shape[1], rgb.shape[0]))
    pil = Image.fromarray(rgb).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def crop_lab_l_to_rgb(
    base_lab: np.ndarray,
    l_chan: np.ndarray,
    crop: dict[str, int],
    sensor_dims: list[int],
) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (base_lab.shape[1], base_lab.shape[0]))
    x0, y0, x1, y1 = box
    crop_lab = base_lab[y0:y1, x0:x1].copy()
    crop_lab[..., 0] = np.clip(l_chan[y0:y1, x0:x1], 0.0, 100.0)
    rgb = lab_to_rgb(crop_lab)
    pil = Image.fromarray(rgb)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    pass_count = sum(1 for row in rows if row["preview_pass"])
    return {
        "count": count,
        "pass_count": pass_count,
        "pass_rate": pass_count / max(1, count),
        "worst_lpips": max(float(row["lpips"]) for row in rows),
        "median_lpips": float(np.median([float(row["lpips"]) for row in rows])),
        "worst_ms_ssim": min(float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(float(row["dE2000_mean"]) for row in rows),
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for variant in sorted({row["variant"] for row in rows}):
        vr = [row for row in rows if row["variant"] == variant]
        worst = max(vr, key=lambda row: (float(row["lpips"]), -float(row["ms_ssim"])))
        out.append({
            "variant": variant,
            "worst_image": worst["image_id"],
            "worst_crop": worst["crop"],
            **summarize(vr),
        })
    out.sort(key=lambda row: (row["pass_count"] != row["count"], -row["pass_count"], row["worst_lpips"], -row["worst_ms_ssim"]))
    return out


def safe_name(value: str) -> str:
    keep = []
    for ch in value:
        keep.append(ch if ch.isalnum() or ch in ("-", "_") else "_")
    return "".join(keep)


def highpass_l(base_l: np.ndarray, donor_l: np.ndarray, sigma: float, blur_cache: dict[tuple[str, float], np.ndarray], donor: str) -> np.ndarray:
    base_blur = blur_cache.get(("base", sigma))
    if base_blur is None:
        base_blur = blur_l(base_l, sigma)
        blur_cache[("base", sigma)] = base_blur
    donor_blur = blur_cache.get((donor, sigma))
    if donor_blur is None:
        donor_blur = blur_l(donor_l, sigma)
        blur_cache[(donor, sigma)] = donor_blur
    return np.clip(base_blur + (donor_l - donor_blur), 0.0, 100.0).astype(np.float32)


def midband_l(
    base_l: np.ndarray,
    donor_l: np.ndarray,
    low_sigma: float,
    high_sigma: float,
    blur_cache: dict[tuple[str, float], np.ndarray],
    donor: str,
) -> np.ndarray:
    base_low = blur_cache.get(("base", low_sigma))
    if base_low is None:
        base_low = blur_l(base_l, low_sigma)
        blur_cache[("base", low_sigma)] = base_low
    base_high = blur_cache.get(("base", high_sigma))
    if base_high is None:
        base_high = blur_l(base_l, high_sigma)
        blur_cache[("base", high_sigma)] = base_high
    donor_low = blur_cache.get((donor, low_sigma))
    if donor_low is None:
        donor_low = blur_l(donor_l, low_sigma)
        blur_cache[(donor, low_sigma)] = donor_low
    donor_high = blur_cache.get((donor, high_sigma))
    if donor_high is None:
        donor_high = blur_l(donor_l, high_sigma)
        blur_cache[(donor, high_sigma)] = donor_high
    base_band = base_low - base_high
    donor_band = donor_low - donor_high
    return np.clip(base_l - base_band + donor_band, 0.0, 100.0).astype(np.float32)


def variant_l(
    variant: tuple[str, str, str, float, float],
    base_l: np.ndarray,
    donors: dict[str, np.ndarray],
    blur_cache: dict[tuple[str, float], np.ndarray],
) -> np.ndarray:
    name, donor, mode, sigma_a, sigma_b = variant
    if name == "base":
        return base_l
    donor_l = donors[donor]
    if mode == "replace":
        return donor_l
    if mode == "highpass":
        return highpass_l(base_l, donor_l, sigma_a, blur_cache, donor)
    if mode == "midband":
        return midband_l(base_l, donor_l, sigma_a, sigma_b, blur_cache, donor)
    raise ValueError(f"unknown variant mode {mode!r}")


def collect(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.receipt.read_text())
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images_by_id = {str(image["id"]): image for image in manifest["images"]}
    receipt_images = receipt.get("images") or []
    selected_ids = set(args.image_id)
    if selected_ids:
        receipt_images = [image for image in receipt_images if str(image["image_id"]) in selected_ids]
    if not receipt_images:
        raise RuntimeError("no receipt images selected")

    variants: list[tuple[str, str, str, float, float]] = [("base", "none", "base", 0.0, 0.0)]
    for donor in ("source", "ref"):
        variants.append((f"{donor}_l_replace", donor, "replace", 0.0, 0.0))
        for sigma in args.highpass_sigma:
            variants.append((f"{donor}_l_highpass_s{sigma:g}", donor, "highpass", float(sigma), 0.0))
        for low_sigma, high_sigma in args.midband:
            variants.append((f"{donor}_l_midband_s{low_sigma:g}_{high_sigma:g}", donor, "midband", float(low_sigma), float(high_sigma)))

    receipt_dir = args.receipt.parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_luma_detail_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    render_ms: list[float] = []
    try:
        for image_receipt in receipt_images:
            image_id = str(image_receipt["image_id"])
            image_meta = images_by_id[image_id]
            print(f"[luma-detail] {image_id}", flush=True)
            stitched_path = receipt_dir / str(image_receipt["stitched_png"])
            source_dng = Path(str(image_receipt["source_dng"]))
            ref_dng = Path(str(image_receipt["ref_dng"]))
            source_tiff = work / f"{image_id}_source.tiff"
            ref_tiff = work / f"{image_id}_ref.tiff"
            render_ms.append(render_dng_to_tiff(source_dng, source_tiff))
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))

            base_rgb = load_rgb(stitched_path)
            source_rgb = resize_rgb_like(load_rgb(source_tiff), base_rgb.shape[:2])
            ref_rgb = load_rgb(ref_tiff)
            ref_field_rgb = resize_rgb_like(ref_rgb, base_rgb.shape[:2])

            base_lab = rgb_to_lab(base_rgb)
            base_l = base_lab[..., 0]
            donors = {
                "source": rgb_to_lab(source_rgb)[..., 0],
                "ref": rgb_to_lab(ref_field_rgb)[..., 0],
            }
            blur_cache: dict[tuple[str, float], np.ndarray] = {}
            image_variant_rows: list[dict[str, Any]] = []
            for variant in variants:
                name = variant[0]
                l_chan = variant_l(variant, base_l, donors, blur_cache)
                for crop_name, crop in crops.items():
                    out_crop = crop_lab_l_to_rgb(base_lab, l_chan, crop, image_meta["sensor_dims"])
                    ref_crop = crop_rgb(ref_rgb, crop, image_meta["sensor_dims"])
                    metrics = compute_visual_metrics(ref_crop, out_crop)
                    metrics = {k: float(v) for k, v in metrics.items()}
                    metrics["preview_pass"] = pass_preview(metrics)
                    png_name = f"{image_id}_{crop_name}_{safe_name(name)}.png"
                    Image.fromarray(out_crop).save(args.output_dir / png_name)
                    row = {
                        "image_id": image_id,
                        "crop": crop_name,
                        "variant": name,
                        "donor": variant[1],
                        "mode": variant[2],
                        "sigma_a": variant[3],
                        "sigma_b": variant[4],
                        "png": png_name,
                        **metrics,
                    }
                    rows.append(row)
                    image_variant_rows.append(row)
            image_rows.append({
                "image_id": image_id,
                "source_dng": str(source_dng),
                "ref_dng": str(ref_dng),
                "stitched_png": str(stitched_path),
                "summary": {
                    variant[0]: summarize([row for row in image_variant_rows if row["variant"] == variant[0]])
                    for variant in variants
                },
            })
            source_tiff.unlink(missing_ok=True)
            ref_tiff.unlink(missing_ok=True)
            del base_rgb, source_rgb, ref_rgb, ref_field_rgb, base_lab, base_l, donors, blur_cache
    finally:
        shutil.rmtree(work, ignore_errors=True)

    summary_rows = aggregate(rows)
    return {
        "schema": "preview_fullframe_luma_detail_probe.v1",
        "receipt": str(args.receipt),
        "manifest": str(args.manifest),
        "runtime_safe_variants": [row["variant"] for row in summary_rows if str(row["variant"]).startswith("source_") or row["variant"] == "base"],
        "oracle_variants": [row["variant"] for row in summary_rows if str(row["variant"]).startswith("ref_")],
        "thresholds": PREVIEW,
        "highpass_sigma": [float(v) for v in args.highpass_sigma],
        "midband": [[float(a), float(b)] for a, b in args.midband],
        "timing": {
            "render_ms_total": float(sum(render_ms)),
            "render_ms_median": float(np.median(render_ms)) if render_ms else 0.0,
        },
        "summary": summary_rows,
        "images": image_rows,
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
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:10px; }
.tile img { width:100%; display:block; border:1px solid #ddd; }
"""
    best = payload["summary"][0] if payload["summary"] else {}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW full-frame luma-detail probe</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Frame Luma-Detail Probe</h1>",
        "<p>Source variants are runtime-safe probes. REF variants are oracle ceilings and are not production candidates.</p>",
        "<div class=cards>",
        f"<div class=card><b>Best variant</b><br>{html.escape(str(best.get('variant', 'n/a')))}</div>",
        f"<div class=card><b>Best pass</b><br>{best.get('pass_count', 0)}/{best.get('count', 0)}</div>",
        f"<div class=card><b>Worst LPIPS</b><br>{fmt(float(best.get('worst_lpips', 0.0)))}</div>",
        f"<div class=card><b>Worst dE</b><br>{fmt(float(best.get('worst_dE2000_mean', 0.0)))}</div>",
        "</div>",
        "<h2>Variant Summary</h2><table><thead><tr><th class=left>variant</th><th>pass</th><th>rate</th><th class=left>worst</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['variant'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate'] * 100:.1f}%</td><td class=left>{html.escape(row['worst_image'])} {html.escape(row['worst_crop'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td></tr>"
        )
    parts.append("</tbody></table><h2>Worst Rows</h2><div class=grid>")
    worst_rows = sorted(payload["rows"], key=lambda row: (not row["preview_pass"], row["lpips"], row["dE2000_mean"]), reverse=True)[:48]
    for row in worst_rows:
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<div class=tile><b>{html.escape(row['image_id'])} {html.escape(row['crop'])}</b>"
            f"<br>{html.escape(row['variant'])}<br><span class={cls}>LPIPS {row['lpips']:.4f}, "
            f"MS {row['ms_ssim']:.4f}, Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            f"<img src='{html.escape(row['png'])}'></div>"
        )
    parts.append("</div>")
    out.write_text("".join(parts))


def parse_midband(value: str) -> tuple[float, float]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("--midband must be low_sigma:high_sigma")
    raw_low, raw_high = value.split(":", 1)
    low = float(raw_low)
    high = float(raw_high)
    if low <= 0 or high <= low:
        raise argparse.ArgumentTypeError("--midband requires 0 < low_sigma < high_sigma")
    return low, high


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--highpass-sigma", type=float, action="append", default=None)
    ap.add_argument("--midband", type=parse_midband, action="append", default=None)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    if args.highpass_sigma is None:
        args.highpass_sigma = [1.0, 2.0, 4.0, 8.0, 16.0]
    if args.midband is None:
        args.midband = [(1.0, 4.0), (2.0, 8.0), (4.0, 16.0), (8.0, 32.0)]
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.output_html)
    for row in payload["summary"][:14]:
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
