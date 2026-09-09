#!/usr/bin/env python3
"""Train or apply a CFA-plane codec-low to clean-low Bayer cleanup model."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


RAW_SCALE = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_u16(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected}")
    return arr.reshape((height, width))


def deinterleave(raw: np.ndarray) -> np.ndarray:
    return np.stack(
        [
            raw[0::2, 0::2],
            raw[0::2, 1::2],
            raw[1::2, 0::2],
            raw[1::2, 1::2],
        ],
        axis=0,
    )


def reinterleave_to_path(path: Path, planes: np.ndarray) -> None:
    _, h, w = planes.shape
    out = np.empty((h * 2, w * 2), dtype="<u2")
    out[0::2, 0::2] = planes[0]
    out[0::2, 1::2] = planes[1]
    out[1::2, 0::2] = planes[2]
    out[1::2, 1::2] = planes[3]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.tofile(path)


def parse_stems(value: str | None) -> set[str] | None:
    if not value:
        return None
    stems = {item.strip() for item in value.split(",") if item.strip()}
    return stems or None


class CleanupNet(nn.Module):
    def __init__(self, width: int = 32, depth: int = 4, residual_scale: float = 0.05) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        layers: list[nn.Module] = [nn.Conv2d(4, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(tail.weight)
        nn.init.zeros_(tail.bias)
        layers.append(tail)
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.clamp(x + self.net(x) * self.residual_scale, 0.0, 1.0)


def make_model(config: dict[str, Any]) -> CleanupNet:
    return CleanupNet(
        width=int(config["width"]),
        depth=int(config["depth"]),
        residual_scale=float(config["residual_scale"]),
    )


class RawPair:
    def __init__(self, image_id: str, low: Path, clean: Path, width: int, height: int) -> None:
        self.image_id = image_id
        self.low = low
        self.clean = clean
        self.width = width
        self.height = height
        self.plane_w = width // 2
        self.plane_h = height // 2
        self._low_planes: np.ndarray | None = None
        self._clean_planes: np.ndarray | None = None

    def load(self) -> None:
        if self._low_planes is None:
            self._low_planes = deinterleave(read_u16(self.low, self.width, self.height))
            self._clean_planes = deinterleave(read_u16(self.clean, self.width, self.height))

    @property
    def low_planes(self) -> np.ndarray:
        self.load()
        assert self._low_planes is not None
        return self._low_planes

    @property
    def clean_planes(self) -> np.ndarray:
        self.load()
        assert self._clean_planes is not None
        return self._clean_planes


class CleanupDataset:
    def __init__(self, pairs: list[RawPair], tile: int, holdout: set[str], focus: set[str], focus_weight: float) -> None:
        if not pairs:
            raise ValueError("empty cleanup dataset")
        self.pairs = pairs
        self.tile = tile
        self.train = [p for p in pairs if p.image_id not in holdout]
        self.eval = [p for p in pairs if p.image_id in holdout] or self.train[: max(1, min(8, len(self.train)))]
        if not self.train:
            raise ValueError("empty cleanup train split")
        weights = np.ones(len(self.train), dtype=np.float64)
        if focus:
            for i, pair in enumerate(self.train):
                if pair.image_id in focus:
                    weights[i] = max(1.0, focus_weight)
        self.weights = weights / float(weights.sum())

    def batch(self, batch_size: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        choices = np.random.default_rng(rng.randrange(0, 2**32 - 1)).choice(
            len(self.train),
            size=batch_size,
            replace=True,
            p=self.weights,
        )
        for idx in choices:
            pair = self.train[int(idx)]
            x0 = rng.randrange(0, pair.plane_w - self.tile + 1)
            y0 = rng.randrange(0, pair.plane_h - self.tile + 1)
            xs.append(pair.low_planes[:, y0 : y0 + self.tile, x0 : x0 + self.tile])
            ys.append(pair.clean_planes[:, y0 : y0 + self.tile, x0 : x0 + self.tile])
        x = torch.from_numpy(np.stack(xs).astype(np.float32) / RAW_SCALE).to(DEVICE)
        y = torch.from_numpy(np.stack(ys).astype(np.float32) / RAW_SCALE).to(DEVICE)
        return x, y


def gradient_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.l1_loss(pred[:, :, :, 1:] - pred[:, :, :, :-1], target[:, :, :, 1:] - target[:, :, :, :-1]) + F.l1_loss(
        pred[:, :, 1:, :] - pred[:, :, :-1, :],
        target[:, :, 1:, :] - target[:, :, :-1, :],
    )


def _plane_weights(value: str, channels: int) -> torch.Tensor:
    parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    if len(parts) != channels:
        raise ValueError(f"expected {channels} plane weights, got {len(parts)}")
    return torch.tensor(parts, dtype=torch.float32, device=DEVICE).view(1, channels, 1, 1)


def binomial_detail(x: torch.Tensor) -> torch.Tensor:
    channels = x.shape[1]
    kernel_1d = torch.tensor([1.0, 4.0, 6.0, 4.0, 1.0], dtype=x.dtype, device=x.device) / 16.0
    kx = kernel_1d.view(1, 1, 1, 5).repeat(channels, 1, 1, 1)
    ky = kernel_1d.view(1, 1, 5, 1).repeat(channels, 1, 1, 1)
    padded = F.pad(x, (2, 2, 0, 0), mode="reflect")
    blurred = F.conv2d(padded, kx, groups=channels)
    padded = F.pad(blurred, (0, 0, 2, 2), mode="reflect")
    blurred = F.conv2d(padded, ky, groups=channels)
    return x - blurred


def detail_content_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    threshold_counts: float,
    plane_weights: torch.Tensor,
) -> torch.Tensor:
    pred_detail = binomial_detail(pred)
    target_detail = binomial_detail(target)
    if threshold_counts > 0.0:
        mask = (torch.abs(target_detail) >= (threshold_counts / RAW_SCALE)).to(pred.dtype)
    else:
        mask = torch.ones_like(target_detail)
    weighted = torch.abs(pred_detail - target_detail) * mask * plane_weights.to(dtype=pred.dtype, device=pred.device)
    denom = torch.clamp(torch.sum(mask * plane_weights.to(dtype=pred.dtype, device=pred.device)), min=1.0)
    return torch.sum(weighted) / denom


def charbonnier(pred: torch.Tensor, target: torch.Tensor, eps_counts: float) -> torch.Tensor:
    eps = max(0.0, eps_counts) / RAW_SCALE
    if eps <= 0.0:
        return torch.mean(torch.abs(pred - target))
    return torch.mean(torch.sqrt((pred - target) ** 2 + eps * eps))


def eval_model(model: nn.Module, dataset: CleanupDataset, max_tiles_per_image: int = 16) -> dict[str, Any]:
    model.eval()
    rows: list[dict[str, float]] = []
    with torch.no_grad():
        for pair in dataset.eval:
            rng = random.Random(hash(pair.image_id) & 0xFFFFFFFF)
            for _ in range(max_tiles_per_image):
                x0 = rng.randrange(0, pair.plane_w - dataset.tile + 1)
                y0 = rng.randrange(0, pair.plane_h - dataset.tile + 1)
                x_np = pair.low_planes[:, y0 : y0 + dataset.tile, x0 : x0 + dataset.tile].astype(np.float32) / RAW_SCALE
                y_np = pair.clean_planes[:, y0 : y0 + dataset.tile, x0 : x0 + dataset.tile].astype(np.float32) / RAW_SCALE
                x = torch.from_numpy(x_np[None]).to(DEVICE)
                y = torch.from_numpy(y_np[None]).to(DEVICE)
                pred = model(x)
                base_rmse = torch.sqrt(torch.mean((x - y) ** 2))
                model_rmse = torch.sqrt(torch.mean((pred - y) ** 2))
                base_mae = torch.mean(torch.abs(x - y))
                model_mae = torch.mean(torch.abs(pred - y))
                rows.append(
                    {
                        "baseline_rmse_counts": float(base_rmse.cpu() * RAW_SCALE),
                        "model_rmse_counts": float(model_rmse.cpu() * RAW_SCALE),
                        "baseline_mae_counts": float(base_mae.cpu() * RAW_SCALE),
                        "model_mae_counts": float(model_mae.cpu() * RAW_SCALE),
                    }
                )
    model.train()
    if not rows:
        return {}
    out: dict[str, Any] = {"eval_tiles": len(rows)}
    for key in rows[0]:
        vals = [r[key] for r in rows]
        out[key] = float(sum(vals) / len(vals))
    out["rmse_improvement_pct"] = 100.0 * (out["baseline_rmse_counts"] - out["model_rmse_counts"]) / out["baseline_rmse_counts"]
    out["mae_improvement_pct"] = 100.0 * (out["baseline_mae_counts"] - out["model_mae_counts"]) / out["baseline_mae_counts"]
    return out


def collect_pairs(args: argparse.Namespace) -> list[RawPair]:
    pairs: list[RawPair] = []
    specs = args.dataset or []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) != 4:
            raise ValueError("--dataset must be LOW_DIR:CLEAN_DIR:WIDTH:HEIGHT")
        low_dir = Path(parts[0])
        clean_dir = Path(parts[1])
        width = int(parts[2])
        height = int(parts[3])
        stems = parse_stems(args.stem)
        for low in sorted(low_dir.glob("*.raw")):
            if stems and low.stem not in stems:
                continue
            clean = clean_dir / low.name
            if not clean.exists():
                continue
            pairs.append(RawPair(low.stem, low, clean, width, height))
    return pairs


def train(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    holdout = parse_stems(args.holdout_image) or set()
    focus = parse_stems(args.focus_image) or set()
    pairs = collect_pairs(args)
    dataset = CleanupDataset(pairs, args.tile, holdout, focus, args.focus_weight)
    config = {
        "architecture": "bayer_low_cleanup",
        "width": args.width,
        "depth": args.depth,
        "residual_scale": args.residual_scale,
        "tile": args.tile,
        "raw_scale": RAW_SCALE,
        "loss": args.loss,
        "charbonnier_eps_counts": args.charbonnier_eps_counts,
    }
    model = make_model(config).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    plane_weights = _plane_weights(args.detail_plane_weights, 4)
    history: list[dict[str, Any]] = []
    best_eval: dict[str, Any] | None = None
    best_metric = float("inf")
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, y = dataset.batch(args.batch, rng)
        pred = model(x)
        if args.loss == "l1":
            loss = torch.mean(torch.abs(pred - y))
        elif args.loss == "mse":
            loss = F.mse_loss(pred, y)
        else:
            loss = charbonnier(pred, y, args.charbonnier_eps_counts)
        loss = loss + args.gradient_weight * gradient_loss(pred, y)
        if args.detail_weight:
            loss = loss + args.detail_weight * detail_content_loss(pred, y, args.detail_threshold, plane_weights)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step == 1 or step % args.eval_every == 0 or step == args.steps:
            ev = eval_model(model, dataset)
            ev["step"] = step
            ev["loss"] = float(loss.detach().cpu())
            history.append(ev)
            if ev.get("model_rmse_counts", float("inf")) < best_metric:
                best_metric = float(ev["model_rmse_counts"])
                best_eval = dict(ev)
            print(
                f"step={step} loss={float(loss.detach().cpu()):.5f} "
                f"cleanup_rmse={ev.get('model_rmse_counts', 0.0):.3f} "
                f"baseline={ev.get('baseline_rmse_counts', 0.0):.3f} "
                f"improve={ev.get('rmse_improvement_pct', 0.0):.2f}%",
                flush=True,
            )
    payload = {
        "config": config,
        "model": model.state_dict(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, args.out)
    receipt = {
        "schema": "mission1_bayer_low_cleanup_train.v1",
        "checkpoint": str(args.out),
        "checkpoint_sha256": sha256_file(args.out),
        "datasets": args.dataset,
        "image_count": len(pairs),
        "train_image_count": len(dataset.train),
        "eval_image_count": len(dataset.eval),
        "holdout_image": args.holdout_image,
        "focus_image": args.focus_image,
        "focus_weight": args.focus_weight,
        "steps": args.steps,
        "batch": args.batch,
        "lr": args.lr,
        "gradient_weight": args.gradient_weight,
        "loss": args.loss,
        "charbonnier_eps_counts": args.charbonnier_eps_counts,
        "detail_weight": args.detail_weight,
        "detail_threshold": args.detail_threshold,
        "detail_plane_weights": args.detail_plane_weights,
        "elapsed_s": time.time() - t0,
        "best_eval": best_eval,
        "history": history,
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checkpoint": str(args.out), "best_eval": best_eval}, indent=2))
    return 0


def apply(args: argparse.Namespace) -> int:
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    config = dict(ckpt["config"])
    model = make_model(config).to(DEVICE)
    model.load_state_dict(ckpt["model"], strict=True)
    model.eval()
    raw = read_u16(args.in_raw, args.width, args.height)
    planes = deinterleave(raw)
    _, plane_h, plane_w = planes.shape
    tile = args.tile
    overlap = args.overlap
    step = tile - overlap
    if step <= 0:
        raise ValueError("--overlap must be smaller than --tile")
    out = np.empty_like(planes)
    y_starts = list(range(0, max(1, plane_h - tile + 1), step))
    x_starts = list(range(0, max(1, plane_w - tile + 1), step))
    if y_starts[-1] != plane_h - tile:
        y_starts.append(plane_h - tile)
    if x_starts[-1] != plane_w - tile:
        x_starts.append(plane_w - tile)
    tile_times: list[float] = []
    started = time.perf_counter()
    with torch.no_grad():
        for yi, y0 in enumerate(y_starts):
            for xi, x0 in enumerate(x_starts):
                patch = planes[:, y0 : y0 + tile, x0 : x0 + tile].astype(np.float32) / RAW_SCALE
                x = torch.from_numpy(patch[None]).to(DEVICE)
                t0 = time.perf_counter()
                pred = model(x)
                if DEVICE.type == "mps":
                    torch.mps.synchronize()
                tile_times.append(time.perf_counter() - t0)
                pred_np = np.clip(pred[0].cpu().numpy() * RAW_SCALE + 0.5, 0, 65535).astype(np.uint16)
                crop_y0 = 0 if yi == 0 else overlap // 2
                crop_x0 = 0 if xi == 0 else overlap // 2
                crop_y1 = tile if yi == len(y_starts) - 1 else tile - overlap // 2
                crop_x1 = tile if xi == len(x_starts) - 1 else tile - overlap // 2
                out[:, y0 + crop_y0 : y0 + crop_y1, x0 + crop_x0 : x0 + crop_x1] = pred_np[
                    :, crop_y0:crop_y1, crop_x0:crop_x1
                ]
    total_s = time.perf_counter() - started
    reinterleave_to_path(args.out_raw, out)
    receipt = {
        "schema": "mission1_bayer_low_cleanup_apply.v1",
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "input": str(args.in_raw),
        "output": str(args.out_raw),
        "width": args.width,
        "height": args.height,
        "tile": tile,
        "overlap": overlap,
        "tile_count": len(tile_times),
        "total_s": total_s,
        "fps": 1.0 / total_s if total_s else 0.0,
        "tile_time_s_median": float(np.median(tile_times)) if tile_times else 0.0,
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    tr = sub.add_parser("train")
    tr.add_argument("--dataset", action="append", required=True, help="LOW_DIR:CLEAN_DIR:WIDTH:HEIGHT; repeatable")
    tr.add_argument("--out", type=Path, required=True)
    tr.add_argument("--stem", help="optional comma-separated stem filter")
    tr.add_argument("--holdout-image")
    tr.add_argument("--focus-image")
    tr.add_argument("--focus-weight", type=float, default=1.0)
    tr.add_argument("--steps", type=int, default=1000)
    tr.add_argument("--batch", type=int, default=8)
    tr.add_argument("--tile", type=int, default=192)
    tr.add_argument("--width", type=int, default=32)
    tr.add_argument("--depth", type=int, default=4)
    tr.add_argument("--residual-scale", type=float, default=0.05)
    tr.add_argument("--lr", type=float, default=1e-3)
    tr.add_argument("--gradient-weight", type=float, default=0.1)
    tr.add_argument("--loss", choices=("charbonnier", "l1", "mse"), default="charbonnier")
    tr.add_argument(
        "--charbonnier-eps-counts",
        type=float,
        default=16.383,
        help="Charbonnier epsilon in raw-count units; old behavior was about 16.383 counts.",
    )
    tr.add_argument("--detail-weight", type=float, default=0.0)
    tr.add_argument("--detail-threshold", type=float, default=0.0, help="target same-color detail threshold in raw counts")
    tr.add_argument("--detail-plane-weights", default="1,1,1,1")
    tr.add_argument("--eval-every", type=int, default=100)
    tr.add_argument("--seed", type=int, default=20260618)

    aply = sub.add_parser("apply")
    aply.add_argument("--checkpoint", type=Path, required=True)
    aply.add_argument("--in-raw", type=Path, required=True)
    aply.add_argument("--out-raw", type=Path, required=True)
    aply.add_argument("--width", type=int, required=True)
    aply.add_argument("--height", type=int, required=True)
    aply.add_argument("--tile", type=int, default=512)
    aply.add_argument("--overlap", type=int, default=64)
    aply.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    if args.cmd == "train":
        return train(args)
    if args.cmd == "apply":
        return apply(args)
    raise ValueError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
