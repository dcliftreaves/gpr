#!/usr/bin/env python3
"""Train a bounded RGB residual refiner from full-gate REF/PIPELINE pairs."""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image

import torch
import torch.nn.functional as F
from pytorch_msssim import ms_ssim

try:
    import lpips
except Exception:
    lpips = None

from run_lab_chroma_corrector import RGBDetailCNN


Image.MAX_IMAGE_PIXELS = None

DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def load_pairs(run_dir: Path, image_ids: list[str]) -> list[tuple[str, np.ndarray, np.ndarray]]:
    out = []
    for image_id in image_ids:
        ref = run_dir / f"{image_id}_REF.png"
        pipe = run_dir / f"{image_id}_PIPELINE.png"
        if not ref.exists() or not pipe.exists():
            raise FileNotFoundError(
                f"{image_id}: missing full-res REF/PIPELINE PNGs in {run_dir}. "
                "Run the baseline gate with --keep-fullres-pngs first."
            )
        print(f"loading {image_id}...", flush=True)
        ref_rgb = load_rgb(ref)
        pipe_rgb = load_rgb(pipe)
        h = min(ref_rgb.shape[0], pipe_rgb.shape[0])
        w = min(ref_rgb.shape[1], pipe_rgb.shape[1])
        out.append((image_id, pipe_rgb[:h, :w], ref_rgb[:h, :w]))
    return out


def chw(batch: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(np.transpose(batch, (0, 3, 1, 2))).to(DEVICE)


def random_batch(
    pairs: list[tuple[str, np.ndarray, np.ndarray]],
    batch: int,
    crop: int,
    rng: random.Random,
) -> tuple[torch.Tensor, torch.Tensor]:
    xs, ys = [], []
    for _ in range(batch):
        _, pipe_rgb, ref_rgb = rng.choice(pairs)
        h, w, _ = pipe_rgb.shape
        y0 = rng.randrange(0, h - crop + 1)
        x0 = rng.randrange(0, w - crop + 1)
        xs.append(pipe_rgb[y0:y0 + crop, x0:x0 + crop])
        ys.append(ref_rgb[y0:y0 + crop, x0:x0 + crop])
    return chw(np.stack(xs)), chw(np.stack(ys))


def fixed_eval(
    model: RGBDetailCNN,
    pairs: list[tuple[str, np.ndarray, np.ndarray]],
    crop: int,
    residual_limit: float,
) -> dict:
    model.eval()
    rows = {}
    with torch.no_grad():
        for image_id, pipe_rgb, ref_rgb in pairs:
            h, w, _ = pipe_rgb.shape
            coords = [
                (max(0, h // 2 - crop // 2), max(0, w // 2 - crop // 2)),
                (min(h - crop, 2000), min(w - crop, 3000)),
                (min(h - crop, 2800), min(w - crop, 4000)),
            ]
            vals = []
            for y0, x0 in coords:
                x = chw(pipe_rgb[None, y0:y0 + crop, x0:x0 + crop])
                y = chw(ref_rgb[None, y0:y0 + crop, x0:x0 + crop])
                pred = (x + model(x).clamp(-residual_limit, residual_limit)).clamp(0, 1)
                l1 = F.l1_loss(pred, y).item()
                ms = ms_ssim(pred, y, data_range=1.0, win_size=11).item()
                vals.append((l1, ms))
            rows[image_id] = {
                "l1": float(np.mean([v[0] for v in vals])),
                "ms_ssim": float(np.mean([v[1] for v in vals])),
            }
    model.train()
    return rows


def train(args: argparse.Namespace) -> None:
    image_ids = [s.strip() for s in args.images.split(",") if s.strip()]
    dilations = tuple(int(s.strip()) for s in args.dilations.split(",") if s.strip())
    if not dilations:
        raise ValueError("--dilations must contain at least one integer")
    pairs = load_pairs(args.run_dir, image_ids)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)

    model = RGBDetailCNN(width=args.width, dilations=dilations).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    lpips_net = None
    if args.lpips_weight > 0:
        if lpips is None:
            raise RuntimeError("lpips package is required for --lpips-weight > 0")
        lpips_net = lpips.LPIPS(net="alex").to(DEVICE).eval()
        for p in lpips_net.parameters():
            p.requires_grad_(False)

    best_score = float("inf")
    best_step = 0
    last_stats = {}
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, y = random_batch(pairs, args.batch, args.crop, rng)
        residual = model(x).clamp(-args.residual_limit, args.residual_limit)
        pred = (x + residual).clamp(0, 1)
        l_charb = torch.sqrt((pred - y) ** 2 + 1e-6).mean()
        l_ms = 1.0 - ms_ssim(pred, y, data_range=1.0, win_size=11)
        loss = args.l1_weight * l_charb + args.msssim_weight * l_ms
        l_lpips = torch.tensor(0.0, device=DEVICE)
        if lpips_net is not None and step > args.lpips_warmup:
            l_lpips = lpips_net(pred * 2 - 1, y * 2 - 1).mean()
            loss = loss + args.lpips_weight * l_lpips

        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % args.log_every == 0 or step == 1:
            rows = fixed_eval(model, pairs, args.eval_crop, args.residual_limit)
            score = float(np.mean([v["l1"] + (1.0 - v["ms_ssim"]) for v in rows.values()]))
            if score < best_score:
                best_score = score
                best_step = step
                args.out.parent.mkdir(parents=True, exist_ok=True)
                torch.save({
                    "kind": "rgb_detail_refiner",
                    "state_dict": model.state_dict(),
                    "width": args.width,
                    "dilations": list(dilations),
                    "residual_limit": args.residual_limit,
                    "train_run": str(args.run_dir),
                    "train_images": image_ids,
                    "step": step,
                    "score": score,
                    "loss": float(loss.item()),
                    "l1": float(l_charb.item()),
                    "ms_ssim_loss": float(l_ms.item()),
                    "lpips_loss": float(l_lpips.item()),
                }, args.out)
                marker = " [SAVED]"
            else:
                marker = ""
            print(
                f"step {step:5d}/{args.steps} loss={loss.item():.5f} "
                f"l1={l_charb.item():.5f} msssim={l_ms.item():.5f} "
                f"lpips={l_lpips.item():.5f} eval={score:.5f} "
                f"t={time.time() - t0:.1f}s{marker}",
                flush=True,
            )
        last_stats = {
            "step": step,
            "loss": float(loss.item()),
            "l1": float(l_charb.item()),
            "ms_ssim_loss": float(l_ms.item()),
            "lpips_loss": float(l_lpips.item()),
        }

    if args.save_final:
        torch.save({
            "kind": "rgb_detail_refiner",
            "state_dict": model.state_dict(),
            "width": args.width,
            "dilations": list(dilations),
            "residual_limit": args.residual_limit,
            "train_run": str(args.run_dir),
            "train_images": image_ids,
            "step": args.steps,
            "score": None,
            **last_stats,
        }, args.out)
        best_step = args.steps
        best_score = float(last_stats.get("loss", 0.0))

    sidecar = args.out.with_suffix(args.out.suffix + ".json")
    sidecar.write_text(json.dumps({
        "kind": "rgb_detail_refiner",
        "checkpoint": str(args.out),
        "train_run": str(args.run_dir),
        "train_images": image_ids,
        "width": args.width,
        "dilations": list(dilations),
        "residual_limit": args.residual_limit,
        "steps": args.steps,
        "best_step": best_step,
        "best_score": best_score,
        "loss": {
            "l1_weight": args.l1_weight,
            "msssim_weight": args.msssim_weight,
            "lpips_weight": args.lpips_weight,
            "lpips_warmup": args.lpips_warmup,
        },
    }, indent=2))
    print(f"wrote {args.out}", flush=True)
    print(f"wrote {sidecar}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--images", default=",".join(DEFAULT_IMAGES))
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--crop", type=int, default=384)
    ap.add_argument("--eval-crop", type=int, default=384)
    ap.add_argument("--width", type=int, default=16)
    ap.add_argument("--dilations", default="1,1",
                    help="Comma-separated dilation schedule for hidden RGB residual convolutions.")
    ap.add_argument("--residual-limit", type=float, default=0.06)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--l1-weight", type=float, default=1.0)
    ap.add_argument("--msssim-weight", type=float, default=0.25)
    ap.add_argument("--lpips-weight", type=float, default=0.10)
    ap.add_argument("--lpips-warmup", type=int, default=300)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--save-final", action="store_true",
                    help="Write the final weights instead of the best L1/MS-SSIM eval checkpoint.")
    ap.add_argument("--seed", type=int, default=20260601)
    train(ap.parse_args())


if __name__ == "__main__":
    main()
