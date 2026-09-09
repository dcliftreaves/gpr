#!/usr/bin/env python3
"""Train/apply a 4K Bayer cleanup model supervised by high-res RGB targets.

The model output remains editable Bayer. During training, predicted 4-plane
Bayer tiles are rendered through a differentiable RGB proxy and compared with a
target built by demosaicing the high-resolution Bayer frame and area-downsampling
RGB to the decoded 4K geometry. Use the dashboard tool for final OpenCV-rendered
gating; this trainer is the optimization counterpart.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


RAW_SCALE = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
DEMOSAIC_CODES = {
    "rggb": cv2.COLOR_BayerRGGB2RGB_EA,
    "bggr": cv2.COLOR_BayerBGGR2RGB_EA,
    "grbg": cv2.COLOR_BayerGRBG2RGB_EA,
    "gbrg": cv2.COLOR_BayerGBRG2RGB_EA,
}


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


def parse_stems(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def demosaic_high_to_low_rgb(
    high_raw: np.ndarray,
    *,
    low_width: int,
    low_height: int,
    cfa: str,
) -> np.ndarray:
    rgb = cv2.cvtColor(high_raw, DEMOSAIC_CODES[cfa]).astype(np.float32)
    return cv2.resize(rgb, (low_width, low_height), interpolation=cv2.INTER_AREA)


def rgb_to_cfa_target_planes(rgb: np.ndarray, cfa: str) -> np.ndarray:
    """Sample an RGB image into same-color Bayer target planes."""
    if cfa != "rggb":
        raise ValueError("pseudo-Bayer target currently supports rggb only")
    return np.stack(
        [
            rgb[0::2, 0::2, 0],
            rgb[0::2, 1::2, 1],
            rgb[1::2, 0::2, 1],
            rgb[1::2, 1::2, 2],
        ],
        axis=0,
    ).astype(np.float32)


class CleanupNet(nn.Module):
    def __init__(self, width: int = 48, depth: int = 5, residual_scale: float = 0.04) -> None:
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


def planes_to_rgb_proxy(planes: torch.Tensor) -> torch.Tensor:
    """Render four CFA planes to full-resolution RGB with a smooth proxy.

    This is intentionally differentiable and stable for training. The final
    gate uses OpenCV edge-aware demosaic in the dashboard tool.
    """
    r = F.interpolate(planes[:, 0:1], scale_factor=2, mode="bilinear", align_corners=False)
    g1 = F.interpolate(planes[:, 1:2], scale_factor=2, mode="bilinear", align_corners=False)
    g2 = F.interpolate(planes[:, 2:3], scale_factor=2, mode="bilinear", align_corners=False)
    b = F.interpolate(planes[:, 3:4], scale_factor=2, mode="bilinear", align_corners=False)
    return torch.cat([r, 0.5 * (g1 + g2), b], dim=1)


def y_luma(rgb: torch.Tensor) -> torch.Tensor:
    return rgb[:, 0:1] * 0.2126 + rgb[:, 1:2] * 0.7152 + rgb[:, 2:3] * 0.0722


def gradient_l1(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.l1_loss(pred[:, :, :, 1:] - pred[:, :, :, :-1], target[:, :, :, 1:] - target[:, :, :, :-1]) + F.l1_loss(
        pred[:, :, 1:, :] - pred[:, :, :-1, :],
        target[:, :, 1:, :] - target[:, :, :-1, :],
    )


def charbonnier(pred: torch.Tensor, target: torch.Tensor, eps: float = 1e-3) -> torch.Tensor:
    return torch.mean(torch.sqrt((pred - target) ** 2 + eps * eps))


def gamma_domain(x: torch.Tensor) -> torch.Tensor:
    return torch.pow(torch.clamp(x, 0.0, 1.0), 1.0 / 2.2)


class RgbTargetPair:
    def __init__(
        self,
        image_id: str,
        low_path: Path,
        high_path: Path,
        low_width: int,
        low_height: int,
        high_width: int,
        high_height: int,
        cfa: str,
    ) -> None:
        self.image_id = image_id
        self.low_path = low_path
        self.high_path = high_path
        self.low_width = low_width
        self.low_height = low_height
        self.high_width = high_width
        self.high_height = high_height
        self.plane_w = low_width // 2
        self.plane_h = low_height // 2
        self.cfa = cfa
        self._low_planes: np.ndarray | None = None
        self._target_rgb: np.ndarray | None = None
        self._target_planes: np.ndarray | None = None

    def load_low(self) -> np.ndarray:
        if self._low_planes is None:
            self._low_planes = deinterleave(read_u16(self.low_path, self.low_width, self.low_height))
        return self._low_planes

    def load_target(self) -> np.ndarray:
        if self._target_rgb is None:
            high = read_u16(self.high_path, self.high_width, self.high_height)
            self._target_rgb = demosaic_high_to_low_rgb(
                high,
                low_width=self.low_width,
                low_height=self.low_height,
                cfa=self.cfa,
            ).transpose(2, 0, 1)
        return self._target_rgb

    def load_target_planes(self) -> np.ndarray:
        if self._target_planes is None:
            target_rgb_hwc = self.load_target().transpose(1, 2, 0)
            self._target_planes = rgb_to_cfa_target_planes(target_rgb_hwc, self.cfa)
        return self._target_planes


class RgbTargetDataset:
    def __init__(self, pairs: list[RgbTargetPair], tile: int, holdout: set[str], focus: set[str], focus_weight: float) -> None:
        if not pairs:
            raise ValueError("empty RGB target dataset")
        self.pairs = pairs
        self.tile = tile
        self.train = [pair for pair in pairs if pair.image_id not in holdout]
        self.eval = [pair for pair in pairs if pair.image_id in holdout] or self.train[: max(1, min(8, len(self.train)))]
        if not self.train:
            raise ValueError("empty RGB target train split")
        weights = np.ones(len(self.train), dtype=np.float64)
        if focus:
            for idx, pair in enumerate(self.train):
                if pair.image_id in focus:
                    weights[idx] = max(1.0, focus_weight)
        self.weights = weights / float(weights.sum())

    def batch(self, batch_size: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        xs: list[np.ndarray] = []
        rgb_targets: list[np.ndarray] = []
        bayer_targets: list[np.ndarray] = []
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
            low = pair.load_low()[:, y0 : y0 + self.tile, x0 : x0 + self.tile]
            rgb = pair.load_target()[:, y0 * 2 : (y0 + self.tile) * 2, x0 * 2 : (x0 + self.tile) * 2]
            bayer = pair.load_target_planes()[:, y0 : y0 + self.tile, x0 : x0 + self.tile]
            xs.append(low)
            rgb_targets.append(rgb)
            bayer_targets.append(bayer)
        x = torch.from_numpy(np.stack(xs).astype(np.float32) / RAW_SCALE).to(DEVICE)
        y_rgb = torch.from_numpy(np.stack(rgb_targets).astype(np.float32) / RAW_SCALE).to(DEVICE)
        y_bayer = torch.from_numpy(np.stack(bayer_targets).astype(np.float32) / RAW_SCALE).to(DEVICE)
        return x, y_rgb, y_bayer


def collect_pairs(args: argparse.Namespace) -> list[RgbTargetPair]:
    pairs: list[RgbTargetPair] = []
    stems_filter = parse_stems(args.stem)
    for spec in args.dataset:
        parts = spec.split(":")
        if len(parts) != 7:
            raise ValueError("--dataset must be LOW_DIR:HIGH_TARGET_DIR:LOW_W:LOW_H:HIGH_W:HIGH_H:CFA")
        low_dir = Path(parts[0])
        high_dir = Path(parts[1])
        low_w = int(parts[2])
        low_h = int(parts[3])
        high_w = int(parts[4])
        high_h = int(parts[5])
        cfa = parts[6].lower()
        if cfa not in DEMOSAIC_CODES:
            raise ValueError(f"unsupported CFA {cfa!r}")
        for low_path in sorted(low_dir.glob("*.raw")):
            if stems_filter and low_path.stem not in stems_filter:
                continue
            high_path = high_dir / low_path.name
            if not high_path.exists():
                continue
            pairs.append(RgbTargetPair(low_path.stem, low_path, high_path, low_w, low_h, high_w, high_h, cfa))
    return pairs


def eval_model(model: nn.Module, dataset: RgbTargetDataset, max_tiles_per_image: int = 8) -> dict[str, Any]:
    rows: list[dict[str, float]] = []
    model.eval()
    with torch.no_grad():
        for pair in dataset.eval:
            rng = random.Random(hash(pair.image_id) & 0xFFFFFFFF)
            low_planes = pair.load_low()
            target_rgb = pair.load_target()
            target_planes = pair.load_target_planes()
            for _ in range(max_tiles_per_image):
                x0 = rng.randrange(0, pair.plane_w - dataset.tile + 1)
                y0 = rng.randrange(0, pair.plane_h - dataset.tile + 1)
                x_np = low_planes[:, y0 : y0 + dataset.tile, x0 : x0 + dataset.tile].astype(np.float32) / RAW_SCALE
                y_np = target_rgb[:, y0 * 2 : (y0 + dataset.tile) * 2, x0 * 2 : (x0 + dataset.tile) * 2].astype(np.float32) / RAW_SCALE
                b_np = target_planes[:, y0 : y0 + dataset.tile, x0 : x0 + dataset.tile].astype(np.float32) / RAW_SCALE
                x = torch.from_numpy(x_np[None]).to(DEVICE)
                y = torch.from_numpy(y_np[None]).to(DEVICE)
                b = torch.from_numpy(b_np[None]).to(DEVICE)
                pred = model(x)
                base_rgb = planes_to_rgb_proxy(x)
                pred_rgb = planes_to_rgb_proxy(pred)
                base_gamma = gamma_domain(base_rgb)
                pred_gamma = gamma_domain(pred_rgb)
                target_gamma = gamma_domain(y)
                rows.append(
                    {
                        "baseline_rgb_l1": float(F.l1_loss(base_rgb, y).cpu()),
                        "model_rgb_l1": float(F.l1_loss(pred_rgb, y).cpu()),
                        "baseline_gamma_l1": float(F.l1_loss(base_gamma, target_gamma).cpu()),
                        "model_gamma_l1": float(F.l1_loss(pred_gamma, target_gamma).cpu()),
                        "baseline_ygrad_l1": float(gradient_l1(y_luma(base_rgb), y_luma(y)).cpu()),
                        "model_ygrad_l1": float(gradient_l1(y_luma(pred_rgb), y_luma(y)).cpu()),
                        "baseline_bayer_l1": float(F.l1_loss(x, b).cpu()),
                        "model_bayer_l1": float(F.l1_loss(pred, b).cpu()),
                    }
                )
    model.train()
    out: dict[str, Any] = {"eval_tiles": len(rows)}
    if not rows:
        return out
    for key in rows[0]:
        out[key] = float(sum(row[key] for row in rows) / len(rows))
    for base_key, model_key, out_key in [
        ("baseline_rgb_l1", "model_rgb_l1", "rgb_l1_improvement_pct"),
        ("baseline_gamma_l1", "model_gamma_l1", "gamma_l1_improvement_pct"),
        ("baseline_ygrad_l1", "model_ygrad_l1", "ygrad_l1_improvement_pct"),
        ("baseline_bayer_l1", "model_bayer_l1", "bayer_l1_improvement_pct"),
    ]:
        out[out_key] = 100.0 * (out[base_key] - out[model_key]) / out[base_key] if out[base_key] else 0.0
    return out


def train(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    pairs = collect_pairs(args)
    holdout = parse_stems(args.holdout_image)
    focus = parse_stems(args.focus_image)
    dataset = RgbTargetDataset(pairs, args.tile, holdout, focus, args.focus_weight)
    config = {
        "architecture": "bayer_rgb_target_cleanup",
        "width": args.width,
        "depth": args.depth,
        "residual_scale": args.residual_scale,
        "tile": args.tile,
        "raw_scale": RAW_SCALE,
        "loss": {
            "rgb_weight": args.rgb_weight,
            "gamma_weight": args.gamma_weight,
            "y_gradient_weight": args.y_gradient_weight,
            "raw_anchor_weight": args.raw_anchor_weight,
            "bayer_target_weight": args.bayer_target_weight,
            "outlier_weight": args.outlier_weight,
            "outlier_threshold_counts": args.outlier_threshold_counts,
        },
    }
    model = make_model(config).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, Any]] = []
    best_eval: dict[str, Any] | None = None
    best_metric = float("inf")
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, target_rgb, target_bayer = dataset.batch(args.batch, rng)
        pred = model(x)
        pred_rgb = planes_to_rgb_proxy(pred)
        base_rgb = planes_to_rgb_proxy(x)
        loss = args.rgb_weight * charbonnier(pred_rgb, target_rgb, args.charbonnier_eps)
        if args.gamma_weight:
            loss = loss + args.gamma_weight * charbonnier(gamma_domain(pred_rgb), gamma_domain(target_rgb), args.charbonnier_eps)
        if args.y_gradient_weight:
            loss = loss + args.y_gradient_weight * gradient_l1(y_luma(pred_rgb), y_luma(target_rgb))
        if args.raw_anchor_weight:
            loss = loss + args.raw_anchor_weight * F.l1_loss(pred, x)
        if args.bayer_target_weight:
            loss = loss + args.bayer_target_weight * charbonnier(pred, target_bayer, args.charbonnier_eps)
        if args.outlier_weight:
            base_err = torch.abs(base_rgb.detach() - target_rgb)
            pred_err = torch.abs(pred_rgb - target_rgb)
            threshold = args.outlier_threshold_counts / RAW_SCALE
            mask = (base_err > threshold).to(pred_rgb.dtype)
            denom = torch.clamp(mask.sum(), min=1.0)
            loss = loss + args.outlier_weight * torch.sum(torch.clamp(pred_err - base_err.detach(), min=0.0) * mask) / denom
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()

        if step == 1 or step % args.eval_every == 0 or step == args.steps:
            ev = eval_model(model, dataset, max_tiles_per_image=args.eval_tiles_per_image)
            ev["step"] = step
            ev["loss"] = float(loss.detach().cpu())
            history.append(ev)
            metric = float(ev.get("model_gamma_l1", float("inf"))) + 0.25 * float(ev.get("model_ygrad_l1", 0.0))
            if metric < best_metric:
                best_metric = metric
                best_eval = dict(ev)
            print(
                f"step={step} loss={float(loss.detach().cpu()):.6f} "
                f"gamma_l1={ev.get('model_gamma_l1', 0.0):.6f} "
                f"base={ev.get('baseline_gamma_l1', 0.0):.6f} "
                f"improve={ev.get('gamma_l1_improvement_pct', 0.0):.3f}%",
                flush=True,
            )

    payload = {"config": config, "model": model.state_dict()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, args.out)
    receipt = {
        "schema": "gpr.bayer_rgb_target_cleanup_train.v1",
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
    step = args.tile - args.overlap
    if step <= 0:
        raise ValueError("--overlap must be smaller than --tile")
    y_starts = list(range(0, max(1, plane_h - args.tile + 1), step))
    x_starts = list(range(0, max(1, plane_w - args.tile + 1), step))
    if y_starts[-1] != plane_h - args.tile:
        y_starts.append(plane_h - args.tile)
    if x_starts[-1] != plane_w - args.tile:
        x_starts.append(plane_w - args.tile)
    out = np.empty_like(planes)
    tile_times: list[float] = []
    started = time.perf_counter()
    with torch.inference_mode():
        for yi, y0 in enumerate(y_starts):
            for xi, x0 in enumerate(x_starts):
                patch = planes[:, y0 : y0 + args.tile, x0 : x0 + args.tile].astype(np.float32) / RAW_SCALE
                x = torch.from_numpy(patch[None]).to(DEVICE)
                t0 = time.perf_counter()
                pred = model(x)
                if DEVICE.type == "mps":
                    torch.mps.synchronize()
                tile_times.append(time.perf_counter() - t0)
                pred_np = np.clip(pred[0].cpu().numpy() * RAW_SCALE + 0.5, 0, 65535).astype(np.uint16)
                crop_y0 = 0 if yi == 0 else args.overlap // 2
                crop_x0 = 0 if xi == 0 else args.overlap // 2
                crop_y1 = args.tile if yi == len(y_starts) - 1 else args.tile - args.overlap // 2
                crop_x1 = args.tile if xi == len(x_starts) - 1 else args.tile - args.overlap // 2
                out[:, y0 + crop_y0 : y0 + crop_y1, x0 + crop_x0 : x0 + crop_x1] = pred_np[
                    :, crop_y0:crop_y1, crop_x0:crop_x1
                ]
    total_s = time.perf_counter() - started
    reinterleave_to_path(args.out_raw, out)
    receipt = {
        "schema": "gpr.bayer_rgb_target_cleanup_apply.v1",
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "input": str(args.in_raw),
        "output": str(args.out_raw),
        "width": args.width,
        "height": args.height,
        "tile": args.tile,
        "overlap": args.overlap,
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
    tr.add_argument("--dataset", action="append", required=True, help="LOW_DIR:HIGH_TARGET_DIR:LOW_W:LOW_H:HIGH_W:HIGH_H:CFA")
    tr.add_argument("--out", type=Path, required=True)
    tr.add_argument("--stem", help="optional comma-separated stem filter")
    tr.add_argument("--holdout-image")
    tr.add_argument("--focus-image")
    tr.add_argument("--focus-weight", type=float, default=1.0)
    tr.add_argument("--steps", type=int, default=800)
    tr.add_argument("--batch", type=int, default=4)
    tr.add_argument("--tile", type=int, default=192, help="tile size in CFA-plane pixels; RGB crop is 2x")
    tr.add_argument("--width", type=int, default=48)
    tr.add_argument("--depth", type=int, default=5)
    tr.add_argument("--residual-scale", type=float, default=0.04)
    tr.add_argument("--lr", type=float, default=2e-4)
    tr.add_argument("--weight-decay", type=float, default=1e-4)
    tr.add_argument("--rgb-weight", type=float, default=1.0)
    tr.add_argument("--gamma-weight", type=float, default=0.5)
    tr.add_argument("--y-gradient-weight", type=float, default=0.2)
    tr.add_argument("--raw-anchor-weight", type=float, default=0.05)
    tr.add_argument("--bayer-target-weight", type=float, default=0.0)
    tr.add_argument("--outlier-weight", type=float, default=0.05)
    tr.add_argument("--outlier-threshold-counts", type=float, default=32.0)
    tr.add_argument("--charbonnier-eps", type=float, default=1e-3)
    tr.add_argument("--eval-every", type=int, default=100)
    tr.add_argument("--eval-tiles-per-image", type=int, default=8)
    tr.add_argument("--seed", type=int, default=20260625)

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
