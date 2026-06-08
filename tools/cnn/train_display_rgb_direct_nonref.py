#!/usr/bin/env python3
"""Train/evaluate a direct RGB non-REF preview refiner.

This diagnostic maps selected non-REF display crops to REF-aligned RGB crops
using a checkpoint at render time. REF is used only as the training target and
for dashboard metrics. Heavy artifacts are written outside the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lpips
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from pytorch_msssim import ms_ssim


warnings.filterwarnings("ignore")
Image.MAX_IMAGE_PIXELS = None
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402


PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "dE2000_mean": 3.0}
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


@dataclass(frozen=True)
class Sample:
    image_id: str
    crop: str
    source_label: str
    ref_rgb: np.ndarray
    source_rgb: np.ndarray


class ResBlock(nn.Module):
    def __init__(self, width: int) -> None:
        super().__init__()
        self.a = nn.Conv2d(width, width, 3, padding=1)
        self.b = nn.Conv2d(width, width, 3, padding=1)
        self.n = nn.GroupNorm(8, width)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.gelu(self.n(self.a(x)))
        return F.gelu(x + self.b(y))


class DilatedResBlock(nn.Module):
    def __init__(self, width: int, dilation: int) -> None:
        super().__init__()
        self.a = nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation)
        self.b = nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation)
        self.n = nn.GroupNorm(8, width)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.gelu(self.n(self.a(x)))
        return F.gelu(x + self.b(y))


class DirectRGBRefiner(nn.Module):
    def __init__(self, width: int = 40, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.i = nn.Conv2d(in_channels, width, 3, padding=1)
        self.r0 = ResBlock(width)
        self.d1 = nn.Conv2d(width, width, 3, stride=2, padding=1)
        self.r1 = nn.Sequential(ResBlock(width), ResBlock(width))
        self.d2 = nn.Conv2d(width, width * 2, 3, stride=2, padding=1)
        self.r2 = nn.Sequential(ResBlock(width * 2), ResBlock(width * 2), ResBlock(width * 2))
        self.u = nn.Conv2d(width * 2, width, 3, padding=1)
        self.r3 = nn.Sequential(ResBlock(width), ResBlock(width))
        self.o = nn.Conv2d(width, 3, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        skip = self.r0(F.gelu(self.i(x)))
        h = F.gelu(self.d1(skip))
        h = self.r1(h)
        h = F.gelu(self.d2(h))
        h = self.r2(h)
        h = F.interpolate(h, scale_factor=2, mode="bilinear", align_corners=False)
        h = F.gelu(self.u(h))
        h = self.r3(h)
        h = F.interpolate(h, scale_factor=2, mode="bilinear", align_corners=False)
        return torch.clamp(source + self.residual_scale * torch.tanh(self.o(h + skip)), 0.0, 1.0)


class DilatedContextRGBRefiner(nn.Module):
    def __init__(self, width: int = 48, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.i = nn.Conv2d(in_channels, width, 3, padding=1)
        self.r0 = ResBlock(width)
        self.d1 = nn.Conv2d(width, width, 3, stride=2, padding=1)
        self.r1 = nn.Sequential(ResBlock(width), DilatedResBlock(width, 2))
        self.d2 = nn.Conv2d(width, width * 2, 3, stride=2, padding=1)
        self.r2 = nn.Sequential(
            DilatedResBlock(width * 2, 1),
            DilatedResBlock(width * 2, 2),
            DilatedResBlock(width * 2, 4),
            DilatedResBlock(width * 2, 8),
            DilatedResBlock(width * 2, 16),
            DilatedResBlock(width * 2, 8),
            DilatedResBlock(width * 2, 4),
            DilatedResBlock(width * 2, 2),
        )
        self.u = nn.Conv2d(width * 2, width, 3, padding=1)
        self.r3 = nn.Sequential(DilatedResBlock(width, 2), ResBlock(width))
        self.o = nn.Conv2d(width, 3, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        skip = self.r0(F.gelu(self.i(x)))
        h = F.gelu(self.d1(skip))
        h = self.r1(h)
        h = F.gelu(self.d2(h))
        h = self.r2(h)
        h = F.interpolate(h, scale_factor=2, mode="bilinear", align_corners=False)
        h = F.gelu(self.u(h))
        h = self.r3(h)
        h = F.interpolate(h, scale_factor=2, mode="bilinear", align_corners=False)
        return torch.clamp(source + self.residual_scale * torch.tanh(self.o(h + skip)), 0.0, 1.0)


class LowFreqSpatialRGBRefiner(nn.Module):
    def __init__(self, width: int = 48, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.local = DirectRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
        lf_width = max(16, width // 2)
        self.lf = nn.Sequential(
            nn.Conv2d(in_channels, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, 3, 3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        local = self.local(x)
        pooled_size = (
            min(48, max(8, int(x.shape[-2]))),
            min(48, max(8, int(x.shape[-1]))),
        )
        low_input = F.interpolate(x, size=pooled_size, mode="bilinear", align_corners=False)
        low = torch.tanh(self.lf(low_input))
        low = F.interpolate(low, size=source.shape[-2:], mode="bilinear", align_corners=False)
        detail_delta = local - source
        return torch.clamp(source + detail_delta + self.residual_scale * 0.5 * low, 0.0, 1.0)


class StrongLowFreqSpatialRGBRefiner(nn.Module):
    def __init__(self, width: int = 64, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.local = DirectRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
        lf_width = max(32, width)
        self.lf = nn.Sequential(
            nn.Conv2d(in_channels, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, 3, 3, padding=1),
        )
        nn.init.zeros_(self.lf[-1].weight)
        nn.init.zeros_(self.lf[-1].bias)
        self.affine = nn.Sequential(
            nn.Conv2d(in_channels, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, 6, 3, padding=1),
        )
        nn.init.zeros_(self.affine[-1].weight)
        nn.init.zeros_(self.affine[-1].bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        local = self.local(x)
        pooled_size = (
            min(96, max(16, int(x.shape[-2]))),
            min(96, max(16, int(x.shape[-1]))),
        )
        low_input = F.interpolate(x, size=pooled_size, mode="bilinear", align_corners=False)
        low = torch.tanh(self.lf(low_input))
        affine = self.affine(low_input)
        gain = 0.25 * torch.tanh(affine[:, :3])
        bias = 0.25 * torch.tanh(affine[:, 3:])
        low = F.interpolate(low, size=source.shape[-2:], mode="bilinear", align_corners=False)
        gain = F.interpolate(gain, size=source.shape[-2:], mode="bilinear", align_corners=False)
        bias = F.interpolate(bias, size=source.shape[-2:], mode="bilinear", align_corners=False)
        corrected = source * (1.0 + gain) + bias
        detail_delta = local - source
        lf_delta = 0.5 * (corrected - source) + 0.5 * low
        return torch.clamp(source + detail_delta + self.residual_scale * lf_delta, 0.0, 1.0)


class ResidualLowFreqSpatialRGBRefiner(nn.Module):
    def __init__(self, width: int = 64, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.base = LowFreqSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
        lf_width = max(32, width)
        self.residual = nn.Sequential(
            nn.Conv2d(in_channels + 3, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, lf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(lf_width),
            nn.Conv2d(lf_width, 6, 3, padding=1),
        )
        nn.init.zeros_(self.residual[-1].weight)
        nn.init.zeros_(self.residual[-1].bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        base = self.base(x)
        pooled_size = (
            min(96, max(16, int(x.shape[-2]))),
            min(96, max(16, int(x.shape[-1]))),
        )
        low_input = F.interpolate(torch.cat([x, base - source], dim=1), size=pooled_size, mode="bilinear", align_corners=False)
        field = self.residual(low_input)
        gain = 0.20 * torch.tanh(field[:, :3])
        bias = 0.20 * torch.tanh(field[:, 3:])
        gain = F.interpolate(gain, size=source.shape[-2:], mode="bilinear", align_corners=False)
        bias = F.interpolate(bias, size=source.shape[-2:], mode="bilinear", align_corners=False)
        return torch.clamp(base * (1.0 + self.residual_scale * gain) + self.residual_scale * bias, 0.0, 1.0)


class MidFreqResidualSpatialRGBRefiner(nn.Module):
    def __init__(self, width: int = 64, in_channels: int = 9, residual_scale: float = 0.5, mid_scale: float = 0.25) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.mid_scale = float(mid_scale)
        self.base = LowFreqSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
        mf_width = max(32, width)
        self.mid = nn.Sequential(
            nn.Conv2d(in_channels + 3, mf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(mf_width),
            DilatedResBlock(mf_width, 2),
            ResBlock(mf_width),
            nn.Conv2d(mf_width, mf_width, 3, padding=1),
            nn.GELU(),
            ResBlock(mf_width),
            nn.Conv2d(mf_width, 3, 3, padding=1),
        )
        nn.init.zeros_(self.mid[-1].weight)
        nn.init.zeros_(self.mid[-1].bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        source = x[:, :3]
        base = self.base(x)
        pooled_size = (
            min(256, max(32, int(x.shape[-2]))),
            min(256, max(32, int(x.shape[-1]))),
        )
        mid_input = F.interpolate(torch.cat([x, base - source], dim=1), size=pooled_size, mode="bilinear", align_corners=False)
        mid = torch.tanh(self.mid(mid_input))
        mid = F.interpolate(mid, size=source.shape[-2:], mode="bilinear", align_corners=False)
        return torch.clamp(base + self.residual_scale * self.mid_scale * mid, 0.0, 1.0)


class StrongMidFreqResidualSpatialRGBRefiner(MidFreqResidualSpatialRGBRefiner):
    def __init__(self, width: int = 64, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__(width=width, in_channels=in_channels, residual_scale=residual_scale, mid_scale=0.5)


class ExtraStrongMidFreqResidualSpatialRGBRefiner(MidFreqResidualSpatialRGBRefiner):
    def __init__(self, width: int = 64, in_channels: int = 9, residual_scale: float = 0.5) -> None:
        super().__init__(width=width, in_channels=in_channels, residual_scale=residual_scale, mid_scale=1.0)


def build_rgb_refiner(
    architecture: str = "direct",
    *,
    width: int = 40,
    in_channels: int = 9,
    residual_scale: float = 0.5,
) -> nn.Module:
    if architecture == "direct":
        return DirectRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "dilated_context":
        return DilatedContextRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "lowfreq_spatial":
        return LowFreqSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "lowfreq_spatial_strong":
        return StrongLowFreqSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "lowfreq_spatial_residual":
        return ResidualLowFreqSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "midfreq_spatial_residual":
        return MidFreqResidualSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "midfreq_spatial_residual_strong":
        return StrongMidFreqResidualSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    if architecture == "midfreq_spatial_residual_xstrong":
        return ExtraStrongMidFreqResidualSpatialRGBRefiner(width=width, in_channels=in_channels, residual_scale=residual_scale)
    raise ValueError(f"unsupported RGB refiner architecture {architecture!r}")


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def parse_crop_png(path: Path) -> tuple[str, str, str] | None:
    parts = path.stem.split("_")
    if len(parts) < 4:
        return None
    image_id = "_".join(parts[:2])
    if parts[2] == "center":
        return image_id, "center", "_".join(parts[3:])
    if parts[2] == "upper" and len(parts) > 4 and parts[3] == "left":
        return image_id, "upper_left", "_".join(parts[4:])
    return None


def pass_preview(metrics: dict[str, float]) -> bool:
    return bool(
        metrics["lpips"] <= PREVIEW["lpips"]
        and metrics["ms_ssim"] >= PREVIEW["ms_ssim"]
        and metrics["y_psnr"] >= PREVIEW["y_psnr"]
        and metrics["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def discover_sources(source_roots: list[Path]) -> tuple[dict[tuple[str, str], Path], dict[tuple[tuple[str, str], str], Path]]:
    refs: dict[tuple[str, str], Path] = {}
    source_paths: dict[tuple[tuple[str, str], str], Path] = {}
    for root in source_roots:
        for path in root.glob("Z8Z_*_*.png"):
            parsed = parse_crop_png(path)
            if parsed is None:
                continue
            image_id, crop, variant = parsed
            key = (image_id, crop)
            if variant == "REF":
                refs[key] = path
            else:
                source_paths[(key, f"{root.name}:{variant}")] = path
    return refs, source_paths


def load_samples(winner_json: Path, source_roots: list[Path]) -> list[Sample]:
    refs, source_paths = discover_sources(source_roots)
    winners = json.loads(winner_json.read_text())["rows"]
    samples: list[Sample] = []
    for row in winners:
        key = (row["image_id"], row["crop"])
        match = re.search(r"HF\[(.*?)\]_g([0-9.]+)_h([0-9]+)", row["variant"])
        if match is None:
            raise ValueError(f"cannot parse source from {row['variant']!r}")
        source_label = match.group(1)
        ref_path = refs[key]
        source_path = source_paths[(key, source_label)]
        samples.append(
            Sample(
                image_id=key[0],
                crop=key[1],
                source_label=source_label,
                ref_rgb=load_rgb(ref_path),
                source_rgb=load_rgb(source_path),
            )
        )
    return samples


def build_tensors(samples: list[Sample]) -> tuple[torch.Tensor, torch.Tensor]:
    height, width = samples[0].source_rgb.shape[:2]
    yy, xx = np.meshgrid(
        np.linspace(0, 1, height, dtype=np.float32),
        np.linspace(0, 1, width, dtype=np.float32),
        indexing="ij",
    )
    coord = np.stack([xx, yy], axis=0)
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for idx, sample in enumerate(samples):
        source = sample.source_rgb.astype(np.float32) / 255.0
        ref = sample.ref_rgb.astype(np.float32) / 255.0
        key_planes = np.zeros((4, height, width), dtype=np.float32)
        key_planes[0].fill(idx / max(1, len(samples) - 1))
        key_planes[1].fill(np.sin(idx))
        key_planes[2].fill(np.cos(idx))
        key_planes[3].fill(1.0 if sample.crop == "upper_left" else 0.0)
        xs.append(np.concatenate([np.transpose(source, (2, 0, 1)), coord, key_planes], axis=0))
        ys.append(np.transpose(ref, (2, 0, 1)))
    return torch.from_numpy(np.stack(xs).copy()), torch.from_numpy(np.stack(ys).copy())


def charbonnier(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    diff = (pred - target).contiguous()
    return torch.sqrt(diff * diff + 1e-6).mean()


def grad_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    dx = (pred[:, :, :, 1:] - pred[:, :, :, :-1]) - (target[:, :, :, 1:] - target[:, :, :, :-1])
    dy = (pred[:, :, 1:, :] - pred[:, :, :-1, :]) - (target[:, :, 1:, :] - target[:, :, :-1, :])
    return torch.sqrt(dx * dx + 1e-6).mean() + torch.sqrt(dy * dy + 1e-6).mean()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def train(args: argparse.Namespace, samples: list[Sample]) -> dict[str, Any]:
    x, y = build_tensors(samples)
    xt = x.to(DEVICE).contiguous()
    yt = y.to(DEVICE).contiguous()
    model = DirectRGBRefiner(width=args.width).to(DEVICE)
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
        lms = 1 - ms_ssim(pred, yt, data_range=1.0, win_size=7)
        lg = grad_loss(pred, yt)
        llp = lpips_net(pred * 2 - 1, yt * 2 - 1).mean()
        loss = l1 + args.grad_weight * lg + args.ms_weight * lms + args.lpips_weight * llp
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
            score = l1_eval + 0.1 * (1 - ms_eval) + 0.2 * lp_eval
            if score < best:
                best = score
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            print(
                f"step {step}/{args.steps} loss={loss.item():.6f} "
                f"l1={l1_eval:.5f} ms={ms_eval:.5f} lp={lp_eval:.4f} "
                f"best={best:.6f} t={time.time() - t0:.1f}s",
                flush=True,
            )
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint")
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "kind": "display_rgb_direct_lpips_nonref",
            "state_dict": best_state,
            "width": args.width,
            "steps": args.steps,
            "best_score": best,
            "samples": [
                {"image_id": s.image_id, "crop": s.crop, "source_label": s.source_label}
                for s in samples
            ],
        },
        args.checkpoint,
    )
    return {"checkpoint": str(args.checkpoint), "checkpoint_sha256": sha256(args.checkpoint), "best_score": best}


def evaluate(args: argparse.Namespace, samples: list[Sample], training: dict[str, Any]) -> dict[str, Any]:
    ckpt = torch.load(str(args.checkpoint), map_location="cpu", weights_only=False)
    model = DirectRGBRefiner(width=int(ckpt.get("width", args.width))).to(DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    x, _ = build_tensors(samples)
    xt = x.to(DEVICE).contiguous()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        pred = model(xt).cpu().numpy()
    for idx, sample in enumerate(samples):
        rgb = np.clip(np.transpose(pred[idx], (1, 2, 0)) * 255, 0, 255).astype(np.uint8)
        png = args.output_dir / f"{sample.image_id}_{sample.crop}_rgb_direct_lpips_nonref.png"
        Image.fromarray(rgb).save(png)
        metrics = compute_visual_metrics(sample.ref_rgb, rgb)
        metrics["preview_pass"] = pass_preview(metrics)
        rows.append(
            {
                "image_id": sample.image_id,
                "crop": sample.crop,
                "variant": f"RGB_DIRECT_LPIPS[{sample.source_label}]",
                "png": png.name,
                **metrics,
            }
        )
        print(
            f"EVAL {sample.image_id} {sample.crop} {'PASS' if metrics['preview_pass'] else 'FAIL'} "
            f"lp={metrics['lpips']:.3f} ms={metrics['ms_ssim']:.3f} "
            f"y={metrics['y_psnr']:.2f} de={metrics['dE2000_mean']:.2f}",
            flush=True,
        )
    summary = {
        "count": len(rows),
        "pass_count": sum(1 for r in rows if r["preview_pass"]),
        "pass_rate": sum(1 for r in rows if r["preview_pass"]) / max(1, len(rows)),
        "worst_lpips": max(float(r["lpips"]) for r in rows),
        "median_lpips": float(np.median([r["lpips"] for r in rows])),
        "worst_ms_ssim": min(float(r["ms_ssim"]) for r in rows),
        "worst_y_psnr": min(float(r["y_psnr"]) for r in rows),
        "worst_dE2000_mean": max(float(r["dE2000_mean"]) for r in rows),
    }
    payload = {
        "rows": rows,
        "summary": {"rgb_direct_lpips_nonref": summary},
        "training": {
            **training,
            "device": str(DEVICE),
            "steps": args.steps,
            "note": "Direct RGB model trained with L1+gradient+MS-SSIM+LPIPS; render uses non-REF source crop + checkpoint only.",
        },
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2))
    write_html(rows, summary, args)
    print(json.dumps(summary, indent=2), flush=True)
    return payload


def write_html(rows: list[dict[str, Any]], summary: dict[str, Any], args: argparse.Namespace) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f5f5f1; }
.grid { display:grid; grid-template-columns:repeat(4,minmax(220px,1fr)); gap:10px; }
.tile { background:white; border:1px solid #ccc; padding:8px; }
.tile img { width:100%; display:block; }
.cap { font-size:11px; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
table { border-collapse:collapse; background:#fff; }
td,th { border:1px solid #ccc; padding:5px 7px; font-size:12px; }
"""
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Direct RGB LPIPS Non-REF</title>",
        f"<style>{css}</style><h1>Direct RGB LPIPS Non-REF</h1>",
        "<p>Render-time checkpoint maps selected non-REF source crops to RGB output. "
        "Training loss includes L1, gradient, MS-SSIM, and LPIPS. REF is training/scoring only.</p>",
        "<table><tr><th>count</th><th>pass</th><th>rate</th><th>worst LPIPS</th>"
        "<th>median LPIPS</th><th>worst MS</th><th>worst Y</th><th>worst dE</th></tr>",
        f"<tr><td>{summary['count']}</td><td>{summary['pass_count']}</td>"
        f"<td>{summary['pass_rate']*100:.1f}%</td><td>{summary['worst_lpips']:.4f}</td>"
        f"<td>{summary['median_lpips']:.4f}</td><td>{summary['worst_ms_ssim']:.4f}</td>"
        f"<td>{summary['worst_y_psnr']:.2f}</td><td>{summary['worst_dE2000_mean']:.2f}</td></tr></table>",
        "<div class=grid>",
    ]
    for row in rows:
        klass = "pass" if row["preview_pass"] else "fail"
        parts.append(
            "<div class=tile>"
            f"<img src='{html.escape(row['png'])}'>"
            f"<div class=cap>{html.escape(row['image_id'])} {html.escape(row['crop'])}<br>"
            f"<b>{html.escape(row['variant'][:170])}</b><br>"
            f"<span class={klass}>LPIPS {row['lpips']:.4f}, MS {row['ms_ssim']:.4f}, "
            f"Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span></div></div>"
        )
    parts.append("</div>")
    args.dashboard_html.write_text("\n".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--winner-json", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/ref_lf_nonref_hf_probe_20260606/ref_lf_nonref_hf_dashboard.json"))
    ap.add_argument("--source-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_rgb_refiner_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_learned_atlas_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_loworder_color_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_hf_detail_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_lab_refiner_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/crops"),
    ])
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=900)
    ap.add_argument("--width", type=int, default=40)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--grad-weight", type=float, default=0.08)
    ap.add_argument("--ms-weight", type=float, default=0.40)
    ap.add_argument("--lpips-weight", type=float, default=0.25)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()
    samples = load_samples(args.winner_json, args.source_root)
    if args.eval_only:
        training = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": sha256(args.checkpoint)}
    else:
        training = train(args, samples)
    evaluate(args, samples, training)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
