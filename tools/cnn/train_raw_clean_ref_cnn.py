#!/usr/bin/env python3
"""Train a small sigma-aware raw clean-target model from sidecar NPZs."""
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


DEFAULT_TARGETS = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets.json")
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
RAW_SCALE = 16383.0


def deinterleave(arr: np.ndarray) -> np.ndarray:
    return np.stack(
        [arr[0::2, 0::2], arr[0::2, 1::2], arr[1::2, 0::2], arr[1::2, 1::2]],
        axis=0,
    ).astype(np.float32)


def interleave(ch: np.ndarray) -> np.ndarray:
    _, h, w = ch.shape
    out = np.zeros((h * 2, w * 2), dtype=np.float32)
    out[0::2, 0::2] = ch[0]
    out[0::2, 1::2] = ch[1]
    out[1::2, 0::2] = ch[2]
    out[1::2, 1::2] = ch[3]
    return out


class RawCleanDataset:
    def __init__(self, target_json: Path, include_rejected: bool) -> None:
        data = json.loads(target_json.read_text())
        self.rows: list[dict[str, Any]] = []
        for row in data["rows"]:
            if include_rejected or row.get("accepted", True):
                self.rows.append(row)
        if not self.rows:
            raise ValueError(f"{target_json} contains no usable rows")
        self.arrays: list[dict[str, Any]] = []
        for row in self.rows:
            z = np.load(row["npz"])
            raw = deinterleave(z["raw"]) / RAW_SCALE
            clean = deinterleave(z["clean"]) / RAW_SCALE
            sigma = deinterleave(z["sigma"]) / RAW_SCALE
            exact = deinterleave(z["exact_residual"]) / RAW_SCALE
            self.arrays.append({
                "row": row,
                "raw": raw,
                "clean": clean,
                "sigma": sigma,
                "exact": exact,
            })

    def random_batch(self, batch: int, crop: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        for _ in range(batch):
            item = rng.choice(self.arrays)
            raw = item["raw"]
            clean = item["clean"]
            sigma = item["sigma"]
            _, h, w = raw.shape
            if crop > h or crop > w:
                raise ValueError(f"crop {crop} larger than sidecar plane {h}x{w}")
            y0 = rng.randrange(0, h - crop + 1)
            x0 = rng.randrange(0, w - crop + 1)
            xs.append(np.concatenate(
                [raw[:, y0:y0 + crop, x0:x0 + crop], sigma[:, y0:y0 + crop, x0:x0 + crop]],
                axis=0,
            ))
            ys.append(clean[:, y0:y0 + crop, x0:x0 + crop])
        x = torch.from_numpy(np.stack(xs)).to(DEVICE)
        y = torch.from_numpy(np.stack(ys)).to(DEVICE)
        return x, y


class RawCleanCNN(nn.Module):
    def __init__(self, width: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(8, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, 4, 3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        raw = x[:, :4]
        return torch.clamp(raw + self.net(x), 0.0, 1.0)


def evaluate(model: RawCleanCNN, dataset: RawCleanDataset) -> dict[str, Any]:
    model.eval()
    rows = []
    with torch.no_grad():
        for item in dataset.arrays:
            x_np = np.concatenate([item["raw"], item["sigma"]], axis=0)[None]
            x = torch.from_numpy(x_np).to(DEVICE)
            pred = model(x).cpu().numpy()[0]
            clean = item["clean"]
            raw = item["raw"]
            exact = item["exact"]
            pred_exact_addback = np.clip(pred + exact, 0.0, 1.0)
            clean_l1 = float(np.mean(np.abs(pred - clean)))
            raw_addback_l1 = float(np.mean(np.abs(pred_exact_addback - raw)))
            clean_rmse_counts = float(np.sqrt(np.mean((pred - clean) ** 2)) * RAW_SCALE)
            addback_rmse_counts = float(np.sqrt(np.mean((pred_exact_addback - raw) ** 2)) * RAW_SCALE)
            rows.append({
                "image_id": item["row"]["image_id"],
                "crop": item["row"]["crop"],
                "iso": item["row"]["iso"],
                "accepted": item["row"].get("accepted", True),
                "clean_l1": clean_l1,
                "raw_exact_addback_l1": raw_addback_l1,
                "clean_rmse_counts": clean_rmse_counts,
                "raw_exact_addback_rmse_counts": addback_rmse_counts,
            })
    model.train()
    accepted = [row for row in rows if row["accepted"]]
    rejected = [row for row in rows if not row["accepted"]]

    def mean_or_none(items: list[dict[str, Any]], key: str) -> float | None:
        if not items:
            return None
        return float(np.mean([r[key] for r in items]))

    return {
        "rows": rows,
        "mean_clean_l1": float(np.mean([r["clean_l1"] for r in rows])),
        "mean_raw_exact_addback_l1": float(np.mean([r["raw_exact_addback_l1"] for r in rows])),
        "mean_clean_rmse_counts": float(np.mean([r["clean_rmse_counts"] for r in rows])),
        "mean_raw_exact_addback_rmse_counts": float(np.mean([r["raw_exact_addback_rmse_counts"] for r in rows])),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_mean_clean_rmse_counts": mean_or_none(accepted, "clean_rmse_counts"),
        "accepted_mean_raw_exact_addback_rmse_counts": mean_or_none(accepted, "raw_exact_addback_rmse_counts"),
        "rejected_mean_clean_rmse_counts": mean_or_none(rejected, "clean_rmse_counts"),
        "rejected_mean_raw_exact_addback_rmse_counts": mean_or_none(rejected, "raw_exact_addback_rmse_counts"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--crop", type=int, default=128)
    ap.add_argument("--width", type=int, default=24)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260604)
    ap.add_argument("--accepted-only", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    dataset = RawCleanDataset(args.targets, include_rejected=not args.accepted_only)
    model = RawCleanCNN(args.width).to(DEVICE)
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
            score = metrics["mean_clean_l1"]
            marker = ""
            if score < best:
                best = score
                best_eval = metrics
                args.out.parent.mkdir(parents=True, exist_ok=True)
                torch.save({
                    "kind": "raw_clean_ref_cnn",
                    "state_dict": model.state_dict(),
                    "width": args.width,
                    "raw_scale": RAW_SCALE,
                    "targets": str(args.targets),
                    "accepted_only": args.accepted_only,
                    "step": step,
                    "score": score,
                }, args.out)
                marker = " [SAVED]"
            print(
                f"step {step:5d}/{args.steps} loss={loss.item():.7f} "
                f"clean_l1={metrics['mean_clean_l1']:.7f} "
                f"addback_l1={metrics['mean_raw_exact_addback_l1']:.7f} "
                f"clean_rmse_counts={metrics['mean_clean_rmse_counts']:.3f} "
                f"accepted_rmse_counts={metrics['accepted_mean_clean_rmse_counts'] or 0.0:.3f} "
                f"addback_rmse_counts={metrics['mean_raw_exact_addback_rmse_counts']:.3f} "
                f"t={time.time() - t0:.1f}s{marker}",
                flush=True,
            )

    sidecar = args.out.with_suffix(args.out.suffix + ".json")
    sidecar.write_text(json.dumps({
        "kind": "raw_clean_ref_cnn",
        "checkpoint": str(args.out),
        "targets": str(args.targets),
        "steps": args.steps,
        "batch": args.batch,
        "crop": args.crop,
        "width": args.width,
        "accepted_only": args.accepted_only,
        "best_score": best,
        "best_eval": best_eval,
    }, indent=2))
    print(f"wrote {args.out}", flush=True)
    print(f"wrote {sidecar}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
