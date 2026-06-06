#!/usr/bin/env python3
"""Train a runtime-shaped no-REF PREVIEW RGB refiner.

Unlike train_display_rgb_direct_nonref.py, this trainer fixes source policy
before training and does not provide sample-index, crop-key, or winner-derived
conditioning. REF is the supervised target and metric reference only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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

from evaluate_preview_runtime_policy import build_input, build_samples, load_rgb, sha256_file, summarize, write_html  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import DirectRGBRefiner, grad_loss, pass_preview  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def build_tensors(args: argparse.Namespace) -> tuple[list[Any], torch.Tensor, torch.Tensor]:
    samples = build_samples(args)
    xs: list[torch.Tensor] = []
    ys: list[np.ndarray] = []
    for sample in samples:
        source = load_rgb(sample.source_path)
        ref = load_rgb(sample.ref_path)
        xs.append(build_input(source, args.conditioning).cpu()[0])
        ys.append(np.transpose(ref.astype(np.float32) / 255.0, (2, 0, 1)))
    return samples, torch.stack(xs).contiguous(), torch.from_numpy(np.stack(ys).copy()).contiguous()


def charbonnier(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    diff = (pred - target).contiguous()
    return torch.sqrt(diff * diff + 1e-6).mean()


def lowfreq_color_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    pred_mean = pred.mean(dim=(2, 3))
    target_mean = target.mean(dim=(2, 3))
    pred_std = pred.std(dim=(2, 3), unbiased=False)
    target_std = target.std(dim=(2, 3), unbiased=False)
    pooled_pred = F.interpolate(pred, size=(64, 64), mode="area")
    pooled_target = F.interpolate(target, size=(64, 64), mode="area")
    return (
        (pred_mean - target_mean).abs().mean()
        + 0.5 * (pred_std - target_std).abs().mean()
        + (pooled_pred - pooled_target).abs().mean()
    )


def train(args: argparse.Namespace) -> dict[str, Any]:
    samples, x, y = build_tensors(args)
    xt = x.to(DEVICE).contiguous()
    yt = y.to(DEVICE).contiguous()
    model = DirectRGBRefiner(width=args.width).to(DEVICE)
    if args.init_checkpoint is not None:
        init = torch.load(str(args.init_checkpoint), map_location="cpu", weights_only=False)
        model.load_state_dict(init["state_dict"])
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    lpips_net = lpips.LPIPS(net="alex").to(DEVICE).eval()
    for param in lpips_net.parameters():
        param.requires_grad_(False)

    best = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    t0 = time.time()
    for step in range(1, args.steps + 1):
        pred = model(xt).contiguous()
        l1 = charbonnier(pred, yt)
        lms = 1.0 - ms_ssim(pred, yt, data_range=1.0, win_size=7)
        lg = grad_loss(pred, yt)
        llp = lpips_net(pred * 2 - 1, yt * 2 - 1).mean()
        lcolor = lowfreq_color_loss(pred, yt)
        loss = (
            l1
            + args.grad_weight * lg
            + args.ms_weight * lms
            + args.lpips_weight * llp
            + args.color_weight * lcolor
        )
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            with torch.no_grad():
                pred_eval = model(xt).contiguous()
                l1_eval = (pred_eval - yt).abs().mean().item()
                ms_eval = ms_ssim(pred_eval, yt, data_range=1.0, win_size=7).item()
                lp_eval = lpips_net(pred_eval * 2 - 1, yt * 2 - 1).mean().item()
            score = l1_eval + 0.1 * (1.0 - ms_eval) + 0.2 * lp_eval
            if score < best:
                best = score
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            print(
                f"step {step}/{args.steps} loss={loss.item():.6f} "
                f"l1={l1_eval:.5f} ms={ms_eval:.5f} lp={lp_eval:.4f} color={lcolor.item():.5f} "
                f"best={best:.6f} t={time.time() - t0:.1f}s",
                flush=True,
            )
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint")

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "kind": "preview_runtime_refiner",
            "state_dict": best_state,
            "width": args.width,
            "steps": args.steps,
            "best_score": best,
            "source_policy": args.policy,
            "conditioning": args.conditioning,
            "color_weight": args.color_weight,
            "forbidden_inputs": ["winner JSON", "sample index", "crop identity key planes"],
            "samples": [
                {
                    "image_id": s.image_id,
                    "crop": s.crop,
                    "source_label": s.source_label,
                }
                for s in samples
            ],
        },
        args.checkpoint,
    )
    return {
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "best_score": best,
        "samples": samples,
    }


def evaluate(args: argparse.Namespace, training: dict[str, Any]) -> dict[str, Any]:
    ckpt = torch.load(str(args.checkpoint), map_location="cpu", weights_only=False)
    model = DirectRGBRefiner(width=int(ckpt.get("width", args.width))).to(DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    samples = training.get("samples") or build_samples(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for sample in samples:
            source = load_rgb(sample.source_path)
            ref = load_rgb(sample.ref_path)
            pred = model(build_input(source, args.conditioning)).detach().cpu().numpy()[0]
            rgb = np.clip(np.transpose(pred, (1, 2, 0)) * 255, 0, 255).astype(np.uint8)
            png = args.output_dir / f"{sample.image_id}_{sample.crop}_{args.policy}_{args.conditioning}_runtime_refiner.png"
            Image.fromarray(rgb).save(png)
            metrics = compute_visual_metrics(ref, rgb)
            metrics["preview_pass"] = pass_preview(metrics)
            rows.append({
                "image_id": sample.image_id,
                "crop": sample.crop,
                "source_label": sample.source_label,
                "png": png.name,
                **metrics,
            })
            print(
                f"EVAL {sample.image_id} {sample.crop} {'PASS' if metrics['preview_pass'] else 'FAIL'} "
                f"lp={metrics['lpips']:.4f} ms={metrics['ms_ssim']:.4f} "
                f"y={metrics['y_psnr']:.2f} de={metrics['dE2000_mean']:.2f}",
                flush=True,
            )
    payload = {
        "schema": "preview_runtime_refiner_train_receipt.v1",
        "summary": {"preview_runtime_policy": summarize(rows)},
        "runtime_contract": {
            "source_policy": args.policy,
            "conditioning": args.conditioning,
            "forbidden_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes"],
            "render_inputs": ["source RGB frame/crop", "normalized pixel coordinates", "checkpoint"],
            "device": str(DEVICE),
        },
        "training": {k: v for k, v in training.items() if k != "samples"},
        "rows": rows,
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2))
    write_html(payload | {"checkpoint_sha256": training["checkpoint_sha256"], "timing": {"model_ms_per_crop_median": 0.0}, "memory": {"max_rss_mb": 0.0}}, args.dashboard_html)
    print(json.dumps(payload["summary"]["preview_runtime_policy"], indent=2), flush=True)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/crops"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_learned_atlas_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_rgb_refiner_20260606"),
    ])
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--init-checkpoint", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--policy", choices=["runtime_priority_v1", "fixed_upresable", "fixed_learned_atlas"], default="runtime_priority_v1")
    ap.add_argument("--conditioning", choices=["zero", "content_stats"], default="zero")
    ap.add_argument("--image-id", action="append")
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--width", type=int, default=40)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--grad-weight", type=float, default=0.08)
    ap.add_argument("--ms-weight", type=float, default=0.40)
    ap.add_argument("--lpips-weight", type=float, default=0.25)
    ap.add_argument("--color-weight", type=float, default=0.0)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard_html.parent.mkdir(parents=True, exist_ok=True)
    if args.eval_only:
        training = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": sha256_file(args.checkpoint)}
    else:
        training = train(args)
    evaluate(args, training)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
