#!/usr/bin/env python3
"""Train a q8-source crop PREVIEW refiner diagnostic.

This tests whether q8 source crops can support a direct no-REF CNN expert for
the rows that the q8 low-field/full-image models cannot clear. REF is used only
as training supervision and metrics reference. Render-time inputs are q8 source
RGB crop, source-derived feature planes, normalized coordinates, and checkpoint.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lpips
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from pytorch_msssim import ms_ssim


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, scaled_box, sha256_file  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, build_rgb_refiner, grad_loss, pass_preview  # noqa: E402
from train_preview_fullimage_band_refiner import coordinate_tensor, source_multiband_tensor  # noqa: E402


Image.MAX_IMAGE_PIXELS = None
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


@dataclass
class Sample:
    image_id: str
    crop: str
    fit_role: str
    source_rgb: np.ndarray
    ref_rgb: np.ndarray
    input: torch.Tensor
    target: torch.Tensor


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


def render_dng_to_png(dng_path: Path, png_path: Path) -> float:
    t0 = time.perf_counter()
    result = subprocess.run(
        ["sips", "-s", "format", "png", str(dng_path), "--out", str(png_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed for {dng_path}: {result.stderr[-400:]}")
    return (time.perf_counter() - t0) * 1000.0


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def crop_rgb(rgb: np.ndarray, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (rgb.shape[1], rgb.shape[0]))
    pil = Image.fromarray(rgb).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def rgb_tensor(rgb: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(rgb.astype(np.float32) / 255.0).permute(2, 0, 1)


def build_input(source_rgb: np.ndarray) -> torch.Tensor:
    source01 = source_rgb.astype(np.float32) / 255.0
    planes = [
        rgb_tensor(source_rgb),
        coordinate_tensor(source_rgb.shape[0], source_rgb.shape[1]),
        source_multiband_tensor(source_rgb),
    ]
    mean = source01.mean(axis=(0, 1), dtype=np.float64).astype(np.float32)
    std = source01.std(axis=(0, 1), dtype=np.float64).astype(np.float32)
    stats = np.concatenate([mean, std]).astype(np.float32)
    stat_planes = np.broadcast_to(stats[:, None, None], (6, source_rgb.shape[0], source_rgb.shape[1])).copy()
    planes.append(torch.from_numpy(stat_planes))
    return torch.cat(planes, dim=0).float()


def load_source_receipt(path: Path) -> dict[str, Path]:
    payload = json.loads(path.read_text())
    root = path.parent
    out: dict[str, Path] = {}
    for image in payload.get("images") or []:
        stitched = root / str(image["stitched_png"])
        if not stitched.exists():
            raise FileNotFoundError(f"missing q8 source fullframe {stitched}")
        out[str(image["image_id"])] = stitched
    return out


def selected_images(args: argparse.Namespace, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = set(args.image_id)
    images = [image for image in manifest["images"] if not wanted or str(image["id"]) in wanted]
    if args.limit:
        images = images[: args.limit]
    if not images:
        raise RuntimeError("no selected images")
    return images


def prepare_samples(args: argparse.Namespace, work: Path) -> tuple[list[Sample], dict[str, Any]]:
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    requested_crops = set(args.crop)
    q8_sources = load_source_receipt(args.source_fullframe_receipt)
    holdouts = set(args.holdout_image_id)
    samples: list[Sample] = []
    render_ms: list[float] = []
    for image in selected_images(args, manifest):
        image_id = str(image["id"])
        q8_path = q8_sources.get(image_id)
        if q8_path is None:
            raise FileNotFoundError(f"missing q8 source fullframe for {image_id}")
        ref_dng = resolve_ref(image, args.ref_root)
        ref_png = work / f"{image_id}_ref.png"
        print(f"[q8-crop] render REF {image_id}", flush=True)
        render_ms.append(render_dng_to_png(ref_dng, ref_png))
        source_full = load_rgb(q8_path)
        ref_full = load_rgb(ref_png)
        for crop_name, crop in crops.items():
            if requested_crops and crop_name not in requested_crops:
                continue
            source_crop = crop_rgb(source_full, crop, image["sensor_dims"])
            ref_crop = crop_rgb(ref_full, crop, image["sensor_dims"])
            samples.append(
                Sample(
                    image_id=image_id,
                    crop=crop_name,
                    fit_role="holdout" if image_id in holdouts else "fit",
                    source_rgb=source_crop,
                    ref_rgb=ref_crop,
                    input=build_input(source_crop),
                    target=rgb_tensor(ref_crop),
                )
            )
        ref_png.unlink(missing_ok=True)
    return samples, {
        "render_ms_total": float(sum(render_ms)),
        "render_ms_median": float(np.median(render_ms)) if render_ms else 0.0,
    }


def charbonnier(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    diff = (pred - target).contiguous()
    return torch.sqrt(diff * diff + 1e-6).mean()


def train_model(args: argparse.Namespace, samples: list[Sample]) -> tuple[torch.nn.Module, list[dict[str, float]], dict[str, float]]:
    fit_samples = [sample for sample in samples if sample.fit_role == "fit"]
    if not fit_samples:
        raise RuntimeError("no fit samples")
    in_channels = int(samples[0].input.shape[0])
    model = build_rgb_refiner(
        args.architecture,
        width=args.width,
        in_channels=in_channels,
        residual_scale=args.residual_scale,
    ).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    lpips_net = lpips.LPIPS(net="alex").to(DEVICE).eval()
    for param in lpips_net.parameters():
        param.requires_grad_(False)
    inputs = [sample.input.unsqueeze(0).to(DEVICE) for sample in fit_samples]
    targets = [sample.target.unsqueeze(0).to(DEVICE) for sample in fit_samples]
    best_state: dict[str, torch.Tensor] | None = None
    best_loss = float("inf")
    best_step = 0
    history: list[dict[str, float]] = []
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        start = ((step - 1) * args.batch_size) % len(inputs)
        batch_idx = [(start + offset) % len(inputs) for offset in range(min(args.batch_size, len(inputs)))]
        x = torch.cat([inputs[idx] for idx in batch_idx], dim=0)
        y = torch.cat([targets[idx] for idx in batch_idx], dim=0)
        pred = model(x).contiguous()
        l1 = charbonnier(pred, y)
        lgrad = grad_loss(pred, y)
        lms = 1.0 - ms_ssim(pred, y, data_range=1.0, win_size=7)
        llp = lpips_net(pred * 2.0 - 1.0, y * 2.0 - 1.0).mean()
        loss = l1 + args.grad_weight * lgrad + args.ms_weight * lms + args.lpips_weight * llp
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        loss_value = float(loss.detach().cpu())
        if loss_value < best_loss:
            best_loss = loss_value
            best_step = step
            best_state = copy.deepcopy({key: value.detach().cpu() for key, value in model.state_dict().items()})
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            row = {
                "step": float(step),
                "loss": loss_value,
                "l1": float(l1.detach().cpu()),
                "grad": float(lgrad.detach().cpu()),
                "ms_loss": float(lms.detach().cpu()),
                "lpips": float(llp.detach().cpu()),
                "best_step": float(best_step),
                "best_loss": float(best_loss),
            }
            history.append(row)
            print(
                f"[q8-crop] step={step} loss={loss_value:.6f} "
                f"l1={row['l1']:.5f} ms_loss={row['ms_loss']:.5f} lp={row['lpips']:.4f}",
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
def evaluate(args: argparse.Namespace, model: torch.nn.Module, samples: list[Sample]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    model_ms: list[float] = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        t0 = time.perf_counter()
        pred = model(sample.input.unsqueeze(0).to(DEVICE))[0].detach().cpu()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        model_ms.append(elapsed_ms)
        rgb = np.clip(pred.permute(1, 2, 0).numpy() * 255.0, 0, 255).astype(np.uint8)
        png = args.output_dir / f"{sample.image_id}_{sample.crop}_q8_crop_refiner.png"
        Image.fromarray(rgb).save(png)
        metrics = {key: float(value) for key, value in compute_visual_metrics(sample.ref_rgb, rgb).items()}
        metrics["preview_pass"] = pass_preview(metrics)
        rows.append(
            {
                "image_id": sample.image_id,
                "crop": sample.crop,
                "fit_role": sample.fit_role,
                "variant": "q8_crop_refiner",
                "png": png.name,
                **metrics,
            }
        )
        print(
            f"[q8-crop] EVAL {sample.image_id} {sample.crop} {sample.fit_role} "
            f"{'PASS' if metrics['preview_pass'] else 'FAIL'} "
            f"lp={metrics['lpips']:.4f} ms={metrics['ms_ssim']:.4f} "
            f"y={metrics['y_psnr']:.2f} de={metrics['dE2000_mean']:.2f}",
            flush=True,
        )
    return rows, {
        "model_ms_total": float(sum(model_ms)),
        "model_ms_median": float(np.median(model_ms)) if model_ms else 0.0,
        "model_ms_per_crop_avg": float(np.mean(model_ms)) if model_ms else 0.0,
    }


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
    return {
        "count": len(rows),
        "pass_count": sum(1 for row in rows if row["preview_pass"]),
        "pass_rate": sum(1 for row in rows if row["preview_pass"]) / len(rows),
        "worst_lpips": max(float(row["lpips"]) for row in rows),
        "median_lpips": float(np.median([float(row["lpips"]) for row in rows])),
        "worst_ms_ssim": min(float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(float(row["dE2000_mean"]) for row in rows),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "all": summarize(rows),
        "fit": summarize([row for row in rows if row["fit_role"] == "fit"]),
        "holdout": summarize([row for row in rows if row["fit_role"] == "holdout"]),
    }


def write_html(payload: dict[str, Any], out: Path) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f7f8f9; color:#222; }
.cards { display:grid; grid-template-columns:repeat(3,minmax(170px,1fr)); gap:10px; margin:14px 0; }
.card,.tile { background:#fff; border:1px solid #d4d8de; border-radius:6px; padding:10px; }
table { border-collapse:collapse; background:#fff; width:100%; font-size:12px; margin:14px 0; }
td,th { border:1px solid #ccd2d9; padding:5px 7px; text-align:right; }
th.left,td.left { text-align:left; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
.tile img { width:100%; display:block; border:1px solid #ddd; }
"""
    def fmt(value: float) -> str:
        return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"

    parts = [
        "<!doctype html><meta charset='utf-8'><title>q8 crop PREVIEW refiner</title>",
        f"<style>{css}</style><h1>q8 Crop PREVIEW Refiner</h1>",
        "<p>Runtime inputs are q8 source crop, source-derived feature planes, normalized coordinates, and checkpoint only.</p>",
        "<div class=cards>",
    ]
    for name, summary in payload["summary"].items():
        parts.append(f"<div class=card><b>{html.escape(name)}</b><br>{summary['pass_count']}/{summary['count']}</div>")
    parts.append("</div><table><thead><tr><th class=left>role</th><th>pass</th><th>rate</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>")
    for name, summary in payload["summary"].items():
        cls = "pass" if summary["pass_count"] == summary["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(name)}</td><td class={cls}>{summary['pass_count']}/{summary['count']}</td>"
            f"<td>{summary['pass_rate'] * 100:.1f}%</td><td>{fmt(summary['worst_lpips'])}</td>"
            f"<td>{fmt(summary['worst_ms_ssim'])}</td><td>{fmt(summary['worst_y_psnr'])}</td>"
            f"<td>{fmt(summary['worst_dE2000_mean'])}</td></tr>"
        )
    parts.append("</tbody></table><div class=grid>")
    for row in sorted(payload["rows"], key=lambda item: (not item["preview_pass"], item["lpips"], item["dE2000_mean"]), reverse=True):
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<div class=tile><b>{html.escape(row['image_id'])} {html.escape(row['crop'])}</b>"
            f"<br>{html.escape(row['fit_role'])}<br><span class={cls}>LPIPS {row['lpips']:.4f}, "
            f"MS {row['ms_ssim']:.4f}, Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            f"<img src='{html.escape(row['png'])}'></div>"
        )
    parts.append("</div>")
    out.write_text("".join(parts))


def collect(args: argparse.Namespace) -> dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="preview_q8_crop_refiner_", dir=args.tmp_dir))
    try:
        samples, render_timing = prepare_samples(args, work)
        model, history, train_timing = train_model(args, samples)
        rows, inference_timing = evaluate(args, model, samples)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    checkpoint = args.output_dir / "q8_crop_refiner.pt"
    torch.save(
        {
            "schema": "preview_q8_crop_refiner_checkpoint.v1",
            "state_dict": model.state_dict(),
            "architecture": args.architecture,
            "width": args.width,
            "in_channels": int(samples[0].input.shape[0]),
            "residual_scale": args.residual_scale,
            "source_policy": "q8_source_crop_plus_source_derived_features_only",
        },
        checkpoint,
    )
    return {
        "schema": "preview_q8_crop_refiner_receipt.v1",
        "manifest": str(args.manifest),
        "source_fullframe_receipt": str(args.source_fullframe_receipt),
        "thresholds": PREVIEW,
        "device": str(DEVICE),
        "image_ids": sorted({sample.image_id for sample in samples}),
        "holdout_image_ids": [str(value) for value in args.holdout_image_id],
        "render_contract": {
            "render_time_inputs": ["q8_source_rgb_crop", "normalized_xy", "source_rgb_multiscale_bands", "source_rgb_grad_lap", "source_rgb_global_mean_std", "checkpoint"],
            "forbidden_render_time_inputs": ["ref_rgb", "ref_dng", "gate_metrics", "sample_index", "crop_identity_key_planes"],
            "source_policy": "q8_source_crop_plus_source_derived_features_only",
        },
        "training": {
            "steps": args.steps,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "grad_weight": args.grad_weight,
            "ms_weight": args.ms_weight,
            "lpips_weight": args.lpips_weight,
            "history": history,
        },
        "model": {
            "architecture": args.architecture,
            "width": args.width,
            "in_channels": int(samples[0].input.shape[0]),
            "residual_scale": args.residual_scale,
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": sha256_file(checkpoint),
            "checkpoint_bytes": checkpoint.stat().st_size,
        },
        "timing": {
            **render_timing,
            **train_timing,
            **inference_timing,
            "max_rss_mb": max_rss_mb(),
            **mps_memory_mb(),
        },
        "summary": aggregate(rows),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument(
        "--source-fullframe-receipt",
        type=Path,
        default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_fullframes_holdout28_v1/preview_codec_source_fullframes.json"),
    )
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--holdout-image-id", action="append", default=[])
    ap.add_argument("--crop", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--ref-root",
        type=Path,
        action="append",
        default=[
            Path("/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"),
            Path("/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs"),
        ],
    )
    ap.add_argument("--architecture", choices=["direct", "dilated_context", "context_unet"], default="direct")
    ap.add_argument("--width", type=int, default=40)
    ap.add_argument("--residual-scale", type=float, default=0.5)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--grad-weight", type=float, default=0.08)
    ap.add_argument("--ms-weight", type=float, default=0.40)
    ap.add_argument("--lpips-weight", type=float, default=0.25)
    ap.add_argument("--log-every", type=int, default=50)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n")
    write_html(payload, args.output_html)
    for name, summary in payload["summary"].items():
        print(
            f"{name:<8} {summary['pass_count']:>3}/{summary['count']:<3} "
            f"LPIPS={summary['worst_lpips']:.4f} MS={summary['worst_ms_ssim']:.4f} "
            f"Y={summary['worst_y_psnr']:.2f} dE={summary['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
