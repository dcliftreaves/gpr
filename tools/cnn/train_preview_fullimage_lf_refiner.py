#!/usr/bin/env python3
"""Train a full-image low-frequency PREVIEW refiner diagnostic.

This is a no-REF render-path capacity/generalization probe. Training uses REF
full-image renders as supervision, but render-time inference consumes only the
runtime source render plus normalized image coordinates. The prediction is a
bounded low-resolution residual field that is upsampled onto source crops, so
source high-frequency detail is preserved by construction.
"""
from __future__ import annotations

import argparse
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


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box, sha256_file  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


class FullImageLFResidual(nn.Module):
    def __init__(self, width: int, depth: int, residual_scale: float) -> None:
        super().__init__()
        layers: list[nn.Module] = [
            nn.Conv2d(5, width, kernel_size=5, padding=2),
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
        self.residual_scale = float(residual_scale)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        residual = torch.tanh(self.net(x)) * self.residual_scale
        return torch.clamp(source + residual, 0.0, 1.0)


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


def crop_rgb(rgb: np.ndarray, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (rgb.shape[1], rgb.shape[0]))
    pil = Image.fromarray(rgb).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def corrected_crop(
    *,
    source_rgb: np.ndarray,
    corrected_low: np.ndarray,
    source_low: np.ndarray,
    crop: dict[str, int],
    sensor_dims: list[int],
) -> np.ndarray:
    source_box = scaled_box(crop, sensor_dims, (source_rgb.shape[1], source_rgb.shape[0]))
    low_box = scaled_box(crop, sensor_dims, (source_low.shape[1], source_low.shape[0]))
    source_crop = np.asarray(Image.fromarray(source_rgb).crop(source_box).convert("RGB"), dtype=np.float32) / 255.0
    lx0, ly0, lx1, ly1 = low_box
    low_residual = corrected_low[ly0:ly1, lx0:lx1].astype(np.float32) - source_low[ly0:ly1, lx0:lx1].astype(np.float32)
    residual_crop = Image.fromarray(np.clip((low_residual + 0.5) * 255.0, 0, 255).astype(np.uint8)).resize(
        (source_crop.shape[1], source_crop.shape[0]),
        Image.Resampling.BICUBIC,
    )
    residual = np.asarray(residual_crop, dtype=np.float32) / 255.0 - 0.5
    out = np.clip(source_crop + residual, 0.0, 1.0)
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


def select_images(args: argparse.Namespace, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    selected = set(args.image_id)
    images = [image for image in manifest["images"] if not selected or str(image["id"]) in selected]
    if args.limit:
        images = images[: args.limit]
    if not images:
        raise RuntimeError("no manifest images selected")
    return images


def prepare_samples(args: argparse.Namespace, images: list[dict[str, Any]], work: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    samples = []
    render_ms: list[float] = []
    for image in images:
        image_id = str(image["id"])
        source_dng = resolve_source(image_id, args.source_root)
        if source_dng is None:
            raise FileNotFoundError(f"missing source DNG for {image_id}")
        ref_dng = resolve_ref(image, args.ref_root)
        source_tiff = work / f"{image_id}_source.tiff"
        ref_tiff = work / f"{image_id}_ref.tiff"
        print(f"[fullimage-lf] render {image_id}", flush=True)
        render_ms.append(render_dng_to_tiff(source_dng, source_tiff))
        render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))
        source_rgb = load_rgb(source_tiff)
        ref_rgb = load_rgb(ref_tiff)
        low_size = resized_dims(source_rgb.shape[1], source_rgb.shape[0], args.model_width)
        source_low = resize_rgb(source_rgb, low_size)
        ref_low = resize_rgb(ref_rgb, low_size)
        source_t = rgb_tensor(source_low)
        input_t = torch.cat([source_t, coordinate_tensor(source_low.shape[0], source_low.shape[1])], dim=0)
        samples.append(
            {
                "image_id": image_id,
                "image": image,
                "source_dng": source_dng,
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


def train_model(args: argparse.Namespace, samples: list[dict[str, Any]]) -> tuple[FullImageLFResidual, list[dict[str, float]], dict[str, float]]:
    model = FullImageLFResidual(args.width, args.depth, args.residual_scale).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, float]] = []
    fit_samples = [sample for sample in samples if sample["image_id"] not in set(args.holdout_image_id)]
    if not fit_samples:
        raise RuntimeError("all selected images were held out; no fit samples remain")
    inputs = [sample["input"].unsqueeze(0).to(DEVICE) for sample in fit_samples]
    targets = [sample["target"].unsqueeze(0).to(DEVICE) for sample in fit_samples]
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        idx = (step - 1) % len(inputs)
        pred = model(inputs[idx])
        loss = F.smooth_l1_loss(pred.contiguous(), targets[idx].contiguous())
        if args.smooth_loss_weight:
            residual = pred - inputs[idx][:, :3]
            dx = torch.abs(residual[..., :, 1:] - residual[..., :, :-1]).mean()
            dy = torch.abs(residual[..., 1:, :] - residual[..., :-1, :]).mean()
            loss = loss + args.smooth_loss_weight * (dx + dy)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            history.append({"step": float(step), "loss": float(loss.detach().cpu())})
            print(f"[fullimage-lf] step={step} loss={float(loss.detach().cpu()):.6f}", flush=True)
    train_ms = (time.perf_counter() - t0) * 1000.0
    return model, history, {"train_ms": train_ms, "train_steps_per_second": args.steps / max(train_ms / 1000.0, 1e-9)}


@torch.no_grad()
def predict_low(model: FullImageLFResidual, sample: dict[str, Any]) -> tuple[np.ndarray, float]:
    t0 = time.perf_counter()
    pred = model(sample["input"].unsqueeze(0).to(DEVICE))[0].detach().cpu()
    wall_ms = (time.perf_counter() - t0) * 1000.0
    pred_np = pred.permute(1, 2, 0).numpy().astype(np.float32)
    return pred_np, wall_ms


def score_samples(
    *,
    args: argparse.Namespace,
    model: FullImageLFResidual,
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
            variants = {
                "source_baseline": crop_rgb(sample["source_rgb"], crop, sample["image"]["sensor_dims"]),
                "fullimage_lf_refined": corrected_crop(
                    source_rgb=sample["source_rgb"],
                    corrected_low=pred_low,
                    source_low=sample["source_low"],
                    crop=crop,
                    sensor_dims=sample["image"]["sensor_dims"],
                ),
                "ref_lowfield_oracle": corrected_crop(
                    source_rgb=sample["source_rgb"],
                    corrected_low=sample["target_low"],
                    source_low=sample["source_low"],
                    crop=crop,
                    sensor_dims=sample["image"]["sensor_dims"],
                ),
            }
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
                "source_dng": str(sample["source_dng"]),
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
        "<!doctype html><meta charset='utf-8'><title>PREVIEW full-image LF refiner</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Image LF Refiner</h1>",
        "<p>Training uses REF supervision. Render-time inference uses only source RGB plus coordinates and applies a bounded low-frequency residual to source detail.</p>",
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
    rows = sorted(payload["rows"], key=lambda row: (not row["preview_pass"], row["lpips"], row["dE2000_mean"]), reverse=True)[:72]
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
    work = Path(tempfile.mkdtemp(prefix="preview_fullimage_lf_", dir=args.tmp_dir))
    try:
        samples, render_timing = prepare_samples(args, images, work)
        model, history, train_timing = train_model(args, samples)
        rows, image_receipts, inference_timing = score_samples(args=args, model=model, samples=samples, crops=crops)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    checkpoint_path = args.output_dir / "fullimage_lf_refiner.pt"
    torch.save(
        {
            "schema": "preview_fullimage_lf_refiner_checkpoint.v1",
            "state_dict": model.state_dict(),
            "width": args.width,
            "depth": args.depth,
            "residual_scale": args.residual_scale,
            "model_width": args.model_width,
            "source_policy": "runtime_source_rgb_plus_normalized_xy_only",
        },
        checkpoint_path,
    )
    return {
        "schema": "preview_fullimage_lf_refiner_receipt.v1",
        "manifest": str(args.manifest),
        "thresholds": PREVIEW,
        "device": str(DEVICE),
        "source_roots": [str(path) for path in args.source_root],
        "ref_roots": [str(path) for path in args.ref_root],
        "image_ids": [sample["image_id"] for sample in samples],
        "holdout_image_ids": [str(v) for v in args.holdout_image_id],
        "render_contract": {
            "render_time_inputs": ["source_rgb", "normalized_xy", "checkpoint"],
            "forbidden_render_time_inputs": ["ref_rgb", "ref_dng", "gate_metrics", "sample_index"],
            "correction_policy": "upsampled_bounded_low_frequency_residual_added_to_source_crop",
            "oracle_variants_not_allowed_for_production": ["ref_lowfield_oracle"],
        },
        "training": {
            "steps": args.steps,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "smooth_loss_weight": args.smooth_loss_weight,
            "history": history,
        },
        "model": {
            "architecture": "fullimage_lf_residual",
            "width": args.width,
            "depth": args.depth,
            "residual_scale": args.residual_scale,
            "model_width": args.model_width,
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
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--residual-scale", type=float, default=0.35)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--smooth-loss-weight", type=float, default=0.05)
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
            f"{row['variant']:<22} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
