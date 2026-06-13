#!/usr/bin/env python3
"""Train a full-image band PREVIEW refiner diagnostic.

This no-REF capacity probe tests whether the current PREVIEW blocker is
learnable from full-frame source context. Training uses REF renders as
supervision, but render-time scoring consumes only source RGB, normalized
coordinates, and the checkpoint. The model predicts a downsampled full-image RGB
field; scored variants either use that field directly or combine it with source
high-frequency crop detail.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from skimage.filters import gaussian


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box, sha256_file  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


class FullImageBandGenerator(nn.Module):
    def __init__(self, width: int, depth: int, in_channels: int = 5) -> None:
        super().__init__()
        layers: list[nn.Module] = [
            nn.Conv2d(in_channels, width, kernel_size=7, padding=3),
            nn.SiLU(inplace=True),
        ]
        for _ in range(max(0, depth - 1)):
            layers.extend(
                [
                    nn.Conv2d(width, width, kernel_size=3, padding=1),
                    nn.SiLU(inplace=True),
                ]
            )
        layers.append(nn.Conv2d(width, 3, kernel_size=3, padding=1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.net(x))


def max_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(rss) / (1024.0 * 1024.0)
    return float(rss) / 1024.0


def mps_memory_mb() -> dict[str, float]:
    if not hasattr(torch, "mps") or not torch.backends.mps.is_available():
        return {}
    out: dict[str, float] = {}
    for name in ("current_allocated_memory", "driver_allocated_memory"):
        fn = getattr(torch.mps, name, None)
        if callable(fn):
            out[name.replace("_memory", "_mb")] = float(fn()) / (1024.0 * 1024.0)
    return out


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
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def resized_dims(width: int, height: int, max_width: int) -> tuple[int, int]:
    if width <= max_width:
        return width, height
    out_w = int(max_width)
    out_h = max(1, int(round(height * (out_w / width))))
    return out_w, out_h


def resize_rgb(rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(Image.fromarray(rgb).resize(size, Image.Resampling.LANCZOS), dtype=np.uint8)


def rgb_tensor(rgb: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(rgb.astype(np.float32) / 255.0).permute(2, 0, 1)


def coordinate_tensor(height: int, width: int) -> torch.Tensor:
    yy, xx = torch.meshgrid(
        torch.linspace(-1.0, 1.0, height),
        torch.linspace(-1.0, 1.0, width),
        indexing="ij",
    )
    return torch.stack([xx, yy], dim=0)


def build_model_input(source_low: np.ndarray, conditioning: str) -> torch.Tensor:
    source01 = source_low.astype(np.float32) / 255.0
    planes = [rgb_tensor(source_low), coordinate_tensor(source_low.shape[0], source_low.shape[1])]
    if conditioning == "xy":
        return torch.cat(planes, dim=0)
    if conditioning == "xy_global_color_stats":
        mean = source01.mean(axis=(0, 1), dtype=np.float64).astype(np.float32)
        std = source01.std(axis=(0, 1), dtype=np.float64).astype(np.float32)
        stats = np.concatenate([mean, std]).astype(np.float32)
        stat_planes = np.broadcast_to(stats[:, None, None], (6, source_low.shape[0], source_low.shape[1])).copy()
        planes.append(torch.from_numpy(stat_planes))
        return torch.cat(planes, dim=0)
    raise ValueError(f"unsupported conditioning {conditioning!r}")


def crop_rgb(rgb: np.ndarray, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (rgb.shape[1], rgb.shape[0]))
    pil = Image.fromarray(rgb).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def crop_low_field(low_rgb: np.ndarray, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (low_rgb.shape[1], low_rgb.shape[0]))
    pil = Image.fromarray(np.clip(low_rgb * 255.0, 0, 255).astype(np.uint8)).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.BICUBIC)
    return np.asarray(pil.convert("RGB"), dtype=np.float32) / 255.0


def blur_rgb(rgb01: np.ndarray, sigma: float) -> np.ndarray:
    out = np.empty_like(rgb01, dtype=np.float32)
    for channel in range(3):
        out[..., channel] = gaussian(rgb01[..., channel], sigma=sigma, mode="reflect", preserve_range=True)
    return out


def source_high_composite(low_crop01: np.ndarray, source_crop: np.ndarray, sigma: float) -> np.ndarray:
    source01 = source_crop.astype(np.float32) / 255.0
    high = source01 - blur_rgb(source01, sigma)
    out = np.clip(low_crop01 + high, 0.0, 1.0)
    return (out * 255.0 + 0.5).astype(np.uint8)


def lowfield_residual_composite(low_crop01: np.ndarray, source_low_crop01: np.ndarray, source_crop: np.ndarray) -> np.ndarray:
    source01 = source_crop.astype(np.float32) / 255.0
    out = np.clip(source01 + (low_crop01 - source_low_crop01), 0.0, 1.0)
    return (out * 255.0 + 0.5).astype(np.uint8)


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


def render_time_inputs(conditioning: str) -> list[str]:
    inputs = ["source_rgb", "normalized_xy", "checkpoint"]
    if conditioning == "xy_global_color_stats":
        inputs.append("source_rgb_global_mean_std")
    return inputs


def select_images(args: argparse.Namespace, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    selected = set(args.image_id)
    images = [image for image in manifest["images"] if not selected or str(image["id"]) in selected]
    if args.limit:
        images = images[: args.limit]
    if not images:
        raise RuntimeError("no manifest images selected")
    return images


def source_receipt_images(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    if args.source_fullframe_receipt is None:
        return {}
    receipt = json.loads(args.source_fullframe_receipt.read_text())
    root = args.source_fullframe_receipt.parent
    out: dict[str, dict[str, Any]] = {}
    for image in receipt.get("images", []):
        image_id = str(image["image_id"])
        stitched = root / str(image["stitched_png"])
        if not stitched.exists():
            raise FileNotFoundError(f"missing stitched source for {image_id}: {stitched}")
        out[image_id] = {**image, "stitched_path": stitched}
    return out


def prepare_samples(args: argparse.Namespace, images: list[dict[str, Any]], work: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    samples = []
    render_ms: list[float] = []
    receipt_sources = source_receipt_images(args)
    for image in images:
        image_id = str(image["id"])
        source_dng = resolve_source(image_id, args.source_root)
        receipt_source = receipt_sources.get(image_id)
        if source_dng is None and receipt_source is None:
            raise FileNotFoundError(f"missing source DNG/source receipt image for {image_id}")
        ref_dng = resolve_ref(image, args.ref_root)
        source_tiff = work / f"{image_id}_source.tiff"
        ref_tiff = work / f"{image_id}_ref.tiff"
        print(f"[fullimage-band] render {image_id}", flush=True)
        render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
        if receipt_source is not None:
            source_rgb = load_rgb(Path(receipt_source["stitched_path"]))
        else:
            assert source_dng is not None
            render_ms.append(render_dng_to_tiff(source_dng, source_tiff))
            source_rgb = load_rgb(source_tiff)
        ref_rgb = load_rgb(ref_tiff)
        low_size = resized_dims(source_rgb.shape[1], source_rgb.shape[0], args.model_width)
        source_low = resize_rgb(source_rgb, low_size)
        ref_low = resize_rgb(ref_rgb, low_size)
        input_t = build_model_input(source_low, args.conditioning)
        samples.append(
            {
                "image_id": image_id,
                "image": image,
                "source_dng": source_dng,
                "source_fullframe_png": str(receipt_source["stitched_path"]) if receipt_source is not None else None,
                "ref_dng": ref_dng,
                "source_rgb": source_rgb,
                "ref_rgb": ref_rgb,
                "source_low": source_low.astype(np.float32) / 255.0,
                "target_low": ref_low.astype(np.float32) / 255.0,
                "input": input_t,
                "target": rgb_tensor(ref_low),
                "low_size": list(low_size),
            }
        )
        source_tiff.unlink(missing_ok=True)
        ref_tiff.unlink(missing_ok=True)
    return samples, {
        "render_ms_total": float(sum(render_ms)),
        "render_ms_median": float(np.median(render_ms)) if render_ms else 0.0,
    }


def low_crop_slices(crop: dict[str, int], sensor_dims: list[int], low_size: list[int]) -> tuple[slice, slice]:
    box = scaled_box(crop, sensor_dims, (int(low_size[0]), int(low_size[1])))
    x0, y0, x1, y1 = box
    return slice(max(0, y0), max(y0 + 1, y1)), slice(max(0, x0), max(x0 + 1, x1))


def crop_region_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    sample: dict[str, Any],
    crops: dict[str, dict[str, int]],
) -> torch.Tensor:
    losses = []
    for crop in crops.values():
        y_slice, x_slice = low_crop_slices(crop, sample["image"]["sensor_dims"], sample["low_size"])
        pred_crop = pred[..., y_slice, x_slice]
        target_crop = target[..., y_slice, x_slice]
        losses.append(F.smooth_l1_loss(pred_crop.contiguous(), target_crop.contiguous()))
    if not losses:
        return pred.new_tensor(0.0)
    return torch.stack(losses).mean()


def train_model(
    args: argparse.Namespace,
    samples: list[dict[str, Any]],
    crops: dict[str, dict[str, int]],
) -> tuple[FullImageBandGenerator, list[dict[str, float]], dict[str, float]]:
    in_channels = int(samples[0]["input"].shape[0])
    model = FullImageBandGenerator(args.width, args.depth, in_channels=in_channels).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, float]] = []
    fit_samples = [sample for sample in samples if sample["image_id"] not in set(args.holdout_image_id)]
    if not fit_samples:
        raise RuntimeError("all selected images were held out; no fit samples remain")
    inputs = [sample["input"].unsqueeze(0).to(DEVICE) for sample in fit_samples]
    targets = [sample["target"].unsqueeze(0).to(DEVICE) for sample in fit_samples]
    best_state: dict[str, torch.Tensor] | None = None
    best_loss = float("inf")
    best_step = 0
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        idx = (step - 1) % len(inputs)
        pred = model(inputs[idx])
        full_loss = F.smooth_l1_loss(pred.contiguous(), targets[idx].contiguous())
        loss = args.background_loss_weight * full_loss
        crop_loss = crop_region_loss(pred, targets[idx], fit_samples[idx], crops)
        if args.crop_loss_weight:
            loss = loss + args.crop_loss_weight * crop_loss
        if args.gradient_loss_weight:
            pred_dx = pred[..., :, 1:] - pred[..., :, :-1]
            tgt_dx = targets[idx][..., :, 1:] - targets[idx][..., :, :-1]
            pred_dy = pred[..., 1:, :] - pred[..., :-1, :]
            tgt_dy = targets[idx][..., 1:, :] - targets[idx][..., :-1, :]
            loss = loss + args.gradient_loss_weight * (
                F.smooth_l1_loss(pred_dx.contiguous(), tgt_dx.contiguous())
                + F.smooth_l1_loss(pred_dy.contiguous(), tgt_dy.contiguous())
            )
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        loss_value = float(loss.detach().cpu())
        if loss_value < best_loss:
            best_loss = loss_value
            best_step = step
            best_state = copy.deepcopy({key: value.detach().cpu() for key, value in model.state_dict().items()})
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            history.append(
                {
                    "step": float(step),
                    "loss": loss_value,
                    "full_loss": float(full_loss.detach().cpu()),
                    "crop_loss": float(crop_loss.detach().cpu()),
                    "best_step": float(best_step),
                    "best_loss": float(best_loss),
                }
            )
            print(
                f"[fullimage-band] step={step} loss={loss_value:.6f} "
                f"full={float(full_loss.detach().cpu()):.6f} crop={float(crop_loss.detach().cpu()):.6f}",
                flush=True,
            )
    train_ms = (time.perf_counter() - t0) * 1000.0
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, history, {
        "train_ms": train_ms,
        "train_steps_per_second": args.steps / max(train_ms / 1000.0, 1e-9),
        "best_step": float(best_step),
        "best_loss": float(best_loss),
    }


@torch.no_grad()
def predict_low(model: FullImageBandGenerator, sample: dict[str, Any]) -> tuple[np.ndarray, float]:
    t0 = time.perf_counter()
    pred = model(sample["input"].unsqueeze(0).to(DEVICE))[0].detach().cpu()
    wall_ms = (time.perf_counter() - t0) * 1000.0
    return pred.permute(1, 2, 0).numpy().astype(np.float32), wall_ms


def score_samples(
    *,
    args: argparse.Namespace,
    model: FullImageBandGenerator,
    samples: list[dict[str, Any]],
    crops: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    inference_ms: list[float] = []
    for sample in samples:
        image_id = sample["image_id"]
        pred_low, model_ms = predict_low(model, sample)
        inference_ms.append(model_ms)
        image_rows = []
        for crop_name, crop in crops.items():
            ref_crop = crop_rgb(sample["ref_rgb"], crop, sample["image"]["sensor_dims"])
            source_crop = crop_rgb(sample["source_rgb"], crop, sample["image"]["sensor_dims"])
            pred_low_crop = crop_low_field(pred_low, crop, sample["image"]["sensor_dims"])
            source_low_crop = crop_low_field(sample["source_low"], crop, sample["image"]["sensor_dims"])
            ref_low_crop = crop_low_field(sample["target_low"], crop, sample["image"]["sensor_dims"])
            variants: dict[str, np.ndarray] = {
                "source_baseline": source_crop,
                "generated_low_direct": (np.clip(pred_low_crop, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8),
                "source_lowfield_residual_sanity": lowfield_residual_composite(source_low_crop, source_low_crop, source_crop),
                "generated_lowfield_residual": lowfield_residual_composite(pred_low_crop, source_low_crop, source_crop),
                "ref_lowfield_residual": lowfield_residual_composite(ref_low_crop, source_low_crop, source_crop),
            }
            for sigma in args.high_sigma:
                variants[f"source_low_plus_source_high_s{sigma:g}"] = source_high_composite(source_low_crop, source_crop, sigma)
                variants[f"generated_low_plus_source_high_s{sigma:g}"] = source_high_composite(pred_low_crop, source_crop, sigma)
                variants[f"ref_low_plus_source_high_s{sigma:g}"] = source_high_composite(ref_low_crop, source_crop, sigma)
            for variant, out_crop in variants.items():
                metrics = compute_visual_metrics(ref_crop, out_crop)
                metrics = {k: float(v) for k, v in metrics.items()}
                metrics["preview_pass"] = pass_preview(metrics)
                png_name = f"{image_id}_{crop_name}_{safe_name(variant)}.png"
                Image.fromarray(out_crop).save(args.output_dir / png_name)
                row = {
                    "image_id": image_id,
                    "crop": crop_name,
                    "variant": variant,
                    "fit_role": "holdout" if image_id in set(args.holdout_image_id) else "fit",
                    "png": png_name,
                    **metrics,
                }
                rows.append(row)
                image_rows.append(row)
        images.append(
            {
                "image_id": image_id,
                "fit_role": "holdout" if image_id in set(args.holdout_image_id) else "fit",
                "source_dng": str(sample["source_dng"]) if sample["source_dng"] is not None else None,
                "source_fullframe_png": sample.get("source_fullframe_png"),
                "ref_dng": str(sample["ref_dng"]),
                "low_size": sample["low_size"],
                "model_ms": model_ms,
                "summary": aggregate(image_rows),
            }
        )
    return rows, images, {
        "model_ms_total": float(sum(inference_ms)),
        "model_ms_median": float(np.median(inference_ms)) if inference_ms else 0.0,
        "model_ms_per_image_avg": float(np.mean(inference_ms)) if inference_ms else 0.0,
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
        "<!doctype html><meta charset='utf-8'><title>PREVIEW full-image band refiner</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Image Band Refiner</h1>",
        "<p>Training uses REF supervision. Runtime variants use source RGB, normalized coordinates, and checkpoint output only; REF-low variants are oracle rows.</p>",
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
            f"<br>{html.escape(row['variant'])} / {html.escape(row['fit_role'])}"
            f"<br><span class={cls}>LPIPS {row['lpips']:.4f}, MS {row['ms_ssim']:.4f}, "
            f"Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            f"<img src='{html.escape(row['png'])}'></div>"
        )
    parts.append("</div>")
    out.write_text("".join(parts))


def collect(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images = select_images(args, manifest)
    work = Path(tempfile.mkdtemp(prefix="preview_fullimage_band_", dir=args.tmp_dir))
    try:
        samples, render_timing = prepare_samples(args, images, work)
        model, history, train_timing = train_model(args, samples, crops)
        rows, image_receipts, inference_timing = score_samples(args=args, model=model, samples=samples, crops=crops)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    checkpoint_path = args.output_dir / "fullimage_band_refiner.pt"
    torch.save(
        {
            "schema": "preview_fullimage_band_refiner_checkpoint.v1",
            "state_dict": model.state_dict(),
            "width": args.width,
            "depth": args.depth,
            "in_channels": int(samples[0]["input"].shape[0]),
            "model_width": args.model_width,
            "conditioning": args.conditioning,
            "high_sigma": [float(v) for v in args.high_sigma],
            "source_policy": "runtime_source_rgb_plus_normalized_xy_and_optional_source_stats_only",
        },
        checkpoint_path,
    )
    return {
        "schema": "preview_fullimage_band_refiner_receipt.v1",
        "manifest": str(args.manifest),
        "thresholds": PREVIEW,
        "device": str(DEVICE),
        "source_roots": [str(path) for path in args.source_root],
        "source_fullframe_receipt": str(args.source_fullframe_receipt) if args.source_fullframe_receipt else None,
        "ref_roots": [str(path) for path in args.ref_root],
        "image_ids": [sample["image_id"] for sample in samples],
        "holdout_image_ids": [str(v) for v in args.holdout_image_id],
        "render_contract": {
            "render_time_inputs": render_time_inputs(args.conditioning),
            "conditioning": args.conditioning,
            "forbidden_render_time_inputs": ["ref_rgb", "ref_dng", "gate_metrics", "sample_index"],
            "runtime_variants": ["generated_low_direct", "generated_low_plus_source_high"],
            "oracle_variants_not_allowed_for_production": ["ref_low_plus_source_high"],
        },
        "training": {
            "steps": args.steps,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "background_loss_weight": args.background_loss_weight,
            "crop_loss_weight": args.crop_loss_weight,
            "gradient_loss_weight": args.gradient_loss_weight,
            "history": history,
        },
        "model": {
            "architecture": "fullimage_band_generator",
            "width": args.width,
            "depth": args.depth,
            "in_channels": int(samples[0]["input"].shape[0]),
            "model_width": args.model_width,
            "conditioning": args.conditioning,
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "checkpoint_bytes": checkpoint_path.stat().st_size,
        },
        "timing": {
            **render_timing,
            **train_timing,
            **inference_timing,
            "max_rss_mb": max_rss_mb(),
            **mps_memory_mb(),
        },
        "summary": aggregate(rows),
        "images": image_receipts,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--holdout-image-id", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--source-fullframe-receipt",
        type=Path,
        help="Use stitched full-frame PNGs from a scene-routed receipt as the runtime source instead of rendering source DNGs.",
    )
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
    ap.add_argument("--model-width", type=int, default=768)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--conditioning", choices=["xy", "xy_global_color_stats"], default="xy")
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--background-loss-weight", type=float, default=1.0)
    ap.add_argument("--crop-loss-weight", type=float, default=0.0)
    ap.add_argument("--gradient-loss-weight", type=float, default=0.1)
    ap.add_argument("--high-sigma", type=float, action="append", default=[1.0, 2.0, 4.0])
    ap.add_argument("--log-every", type=int, default=50)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.output_html)
    for row in payload["summary"]:
        print(
            f"{row['variant']:<38} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
