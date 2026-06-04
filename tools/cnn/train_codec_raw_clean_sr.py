#!/usr/bin/env python3
"""Train a small codec-decoded-raw -> clean-raw 2x model."""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


DEFAULT_PAIRS = Path("/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_20260604/ml2_q3_dec2_raw_clean_pairs.npz")
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
RAW_SCALE = 16383.0


class PairDataset:
    def __init__(self, path: Path, include_rejected: bool) -> None:
        z = np.load(path)
        accepted = z["accepted"].astype(bool)
        keep = np.ones_like(accepted, dtype=bool) if include_rejected else accepted
        self.codec = z["codec_planes"][keep].astype(np.float32) / RAW_SCALE
        self.clean = z["target_clean_planes"][keep].astype(np.float32) / RAW_SCALE
        self.raw = z["target_raw_planes"][keep].astype(np.float32) / RAW_SCALE
        self.exact = z["exact_residual_planes"][keep].astype(np.float32) / RAW_SCALE
        self.sigma = z["sigma_planes"][keep].astype(np.float32) / RAW_SCALE
        self.image_id = z["image_id"][keep].astype(str)
        self.crop = z["crop"][keep].astype(str)
        self.iso = z["iso"][keep].astype(np.int32)
        self.accepted = accepted[keep]
        if len(self.codec) == 0:
            raise ValueError(f"{path} has no usable pairs")
        self.codec_up = np.stack([
            upsample_codec(codec, self.clean[idx].shape[1:]).astype(np.float32)
            for idx, codec in enumerate(self.codec)
        ])

    def random_batch(self, batch: int, crop: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        for _ in range(batch):
            idx = rng.randrange(0, len(self.codec))
            codec_up = self.codec_up[idx]
            clean = self.clean[idx]
            sigma = self.sigma[idx]
            _, h, w = clean.shape
            if crop > h or crop > w:
                raise ValueError(f"crop {crop} larger than target plane {h}x{w}")
            y0 = rng.randrange(0, h - crop + 1)
            x0 = rng.randrange(0, w - crop + 1)
            xs.append(np.concatenate(
                [codec_up[:, y0:y0 + crop, x0:x0 + crop], sigma[:, y0:y0 + crop, x0:x0 + crop]],
                axis=0,
            ))
            ys.append(clean[:, y0:y0 + crop, x0:x0 + crop])
        return torch.from_numpy(np.stack(xs)).to(DEVICE), torch.from_numpy(np.stack(ys)).to(DEVICE)


class CodecRawCleanSR(nn.Module):
    def __init__(self, width: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(8, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=4, dilation=4),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, 4, 3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = x[:, :4]
        return torch.clamp(base + self.net(x), 0.0, 1.0)


def upsample_codec(codec: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    x = torch.from_numpy(codec[None]).float()
    with torch.no_grad():
        y = F.interpolate(x, size=target_shape, mode="bilinear", align_corners=False)
    return y.numpy()[0]


def evaluate(model: CodecRawCleanSR, dataset: PairDataset) -> dict[str, Any]:
    rows = []
    model.eval()
    with torch.no_grad():
        for idx in range(len(dataset.codec)):
            clean = dataset.clean[idx]
            raw = dataset.raw[idx]
            exact = dataset.exact[idx]
            sigma = dataset.sigma[idx]
            codec_up = dataset.codec_up[idx]
            x = torch.from_numpy(np.concatenate([codec_up, sigma], axis=0)[None]).to(DEVICE)
            pred = model(x).cpu().numpy()[0]
            addback = np.clip(pred + exact, 0.0, 1.0)
            clean_err = pred - clean
            addback_err = addback - raw
            rows.append({
                "image_id": str(dataset.image_id[idx]),
                "crop": str(dataset.crop[idx]),
                "iso": int(dataset.iso[idx]),
                "accepted": bool(dataset.accepted[idx]),
                "clean_l1": float(np.mean(np.abs(clean_err))),
                "addback_l1": float(np.mean(np.abs(addback_err))),
                "clean_rmse_counts": float(np.sqrt(np.mean(clean_err * clean_err)) * RAW_SCALE),
                "addback_rmse_counts": float(np.sqrt(np.mean(addback_err * addback_err)) * RAW_SCALE),
            })
    model.train()
    accepted = [r for r in rows if r["accepted"]]
    rejected = [r for r in rows if not r["accepted"]]

    def mean_or_none(items: list[dict[str, Any]], key: str) -> float | None:
        if not items:
            return None
        return float(np.mean([r[key] for r in items]))

    return {
        "rows": rows,
        "mean_clean_rmse_counts": mean_or_none(rows, "clean_rmse_counts"),
        "mean_addback_rmse_counts": mean_or_none(rows, "addback_rmse_counts"),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_mean_clean_rmse_counts": mean_or_none(accepted, "clean_rmse_counts"),
        "accepted_mean_addback_rmse_counts": mean_or_none(accepted, "addback_rmse_counts"),
        "rejected_mean_clean_rmse_counts": mean_or_none(rejected, "clean_rmse_counts"),
        "rejected_mean_addback_rmse_counts": mean_or_none(rejected, "addback_rmse_counts"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--crop", type=int, default=128)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260604)
    ap.add_argument("--accepted-only", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    dataset = PairDataset(args.pairs, include_rejected=not args.accepted_only)
    model = CodecRawCleanSR(args.width).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best = float("inf")
    best_eval: dict[str, Any] | None = None
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, y = dataset.random_batch(args.batch, args.crop, rng)
        pred = model(x)
        loss = torch.sqrt((pred - y) ** 2 + 1e-8).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            metrics = evaluate(model, dataset)
            score = metrics["accepted_mean_clean_rmse_counts"] or metrics["mean_clean_rmse_counts"]
            marker = ""
            if score < best:
                best = float(score)
                best_eval = metrics
                args.out.parent.mkdir(parents=True, exist_ok=True)
                torch.save({
                    "kind": "codec_raw_clean_sr",
                    "state_dict": model.state_dict(),
                    "width": args.width,
                    "raw_scale": RAW_SCALE,
                    "pairs": str(args.pairs),
                    "accepted_only": args.accepted_only,
                    "step": step,
                    "score": best,
                }, args.out)
                marker = " [SAVED]"
            print(
                f"step {step:5d}/{args.steps} loss={loss.item():.7f} "
                f"accepted_rmse={metrics['accepted_mean_clean_rmse_counts'] or 0.0:.3f} "
                f"all_rmse={metrics['mean_clean_rmse_counts'] or 0.0:.3f} "
                f"t={time.time() - t0:.1f}s{marker}",
                flush=True,
            )
    sidecar = args.out.with_suffix(args.out.suffix + ".json")
    sidecar.write_text(json.dumps({
        "kind": "codec_raw_clean_sr",
        "checkpoint": str(args.out),
        "pairs": str(args.pairs),
        "steps": args.steps,
        "batch": args.batch,
        "crop": args.crop,
        "width": args.width,
        "accepted_only": args.accepted_only,
        "best_score": best,
        "best_eval": best_eval,
    }, indent=2))
    print(args.out)
    print(sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
