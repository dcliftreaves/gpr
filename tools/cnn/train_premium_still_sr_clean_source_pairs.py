#!/usr/bin/env python3
"""Train/evaluate clean-source RAW pair SR for premium stills.

This is the production-facing next step after
`audit_premium_still_sr_pairs.py`: it trains only from low-resolution Bayer
planes to high-resolution Bayer planes, compares every evaluated tile against
the nearest same-color 2x baseline, and refuses promotion unless held-out tiles
beat that baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in lean CLI envs
    np = None  # type: ignore[assignment]
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]

    class _MissingNN:
        Module = object

    nn = _MissingNN()  # type: ignore[assignment]
    _MISSING_DEPS_ERROR: ModuleNotFoundError | None = exc
else:
    _MISSING_DEPS_ERROR = None


SCHEMA = "gpr.premium_still_sr_clean_source_pair_model.v1"
RAW_SCALE = 16383.0
DEVICE = (
    torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    if torch is not None
    else "unavailable"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "max": float(arr.max()),
    }


def psnr_from_mse(mse: float) -> float:
    if mse <= 0.0:
        return float("inf")
    return float(20.0 * math.log10(RAW_SCALE) - 10.0 * math.log10(mse))


def parse_image_list(values: list[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        out.update(item.strip() for item in value.split(",") if item.strip())
    return out


def resolve_holdout_images(requested: set[str], unique_images: list[str]) -> set[str]:
    if not requested:
        return {unique_images[-1]}
    available = set(unique_images)
    resolved: set[str] = set()
    missing: list[str] = []
    for item in sorted(requested):
        exact = item in available
        prefix_matches = {image_id for image_id in available if image_id.startswith(item)}
        if exact:
            resolved.add(item)
        elif prefix_matches:
            resolved.update(prefix_matches)
        else:
            missing.append(item)
    if missing:
        raise ValueError(f"holdout image/group(s) not found in pairs: {missing}")
    return resolved


class CleanSourcePairs:
    def __init__(self, path: Path, holdout_images: set[str]) -> None:
        with np.load(path, allow_pickle=False) as z:
            self.inputs = z["inputs"].astype(np.float32) / RAW_SCALE
            self.targets = z["targets"].astype(np.float32) / RAW_SCALE
            self.meta = json.loads(str(z["meta"]))
        if self.meta.get("schema") != "gpr.premium_still_sr_pairs.v1":
            raise ValueError(f"{path} is not a premium still-SR pair NPZ")
        if self.inputs.ndim != 4 or self.targets.ndim != 4:
            raise ValueError("inputs and targets must be NCHW arrays")
        if self.targets.shape[2] != self.inputs.shape[2] * 2 or self.targets.shape[3] != self.inputs.shape[3] * 2:
            raise ValueError(f"target shape must be 2x input shape: {self.inputs.shape} vs {self.targets.shape}")
        self.tiles = list(self.meta.get("tiles", []))
        if len(self.tiles) != len(self.inputs):
            raise ValueError("tile metadata count does not match input batch")
        self.image_ids = np.asarray([str(row.get("image_id")) for row in self.tiles])
        unique_images = sorted(set(self.image_ids.tolist()))
        holdout_images = resolve_holdout_images(holdout_images, unique_images)
        holdout_mask = np.isin(self.image_ids, sorted(holdout_images))
        self.train_idx = np.where(~holdout_mask)[0]
        self.eval_idx = np.where(holdout_mask)[0]
        if len(self.train_idx) == 0 or len(self.eval_idx) == 0:
            raise ValueError("pair split must contain both train and holdout tiles")
        self.holdout_images = sorted(holdout_images)

    def batch(self, batch_size: int, low_crop: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        _, _, h, w = self.inputs.shape
        crop = min(int(low_crop), h, w)
        for _ in range(batch_size):
            idx = int(self.train_idx[rng.randrange(0, len(self.train_idx))])
            y0 = rng.randrange(0, h - crop + 1)
            x0 = rng.randrange(0, w - crop + 1)
            xs.append(self.inputs[idx, :, y0 : y0 + crop, x0 : x0 + crop])
            ys.append(self.targets[idx, :, y0 * 2 : (y0 + crop) * 2, x0 * 2 : (x0 + crop) * 2])
        return torch.from_numpy(np.stack(xs)).to(DEVICE), torch.from_numpy(np.stack(ys)).to(DEVICE)


class ResidualPixelShuffleSR(nn.Module):
    def __init__(self, width: int, depth: int, residual_scale: float) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        layers: list[nn.Module] = [nn.Conv2d(4, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        layers.append(nn.Conv2d(width, 16, 3, padding=1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = torch.repeat_interleave(torch.repeat_interleave(x, 2, dim=2), 2, dim=3)
        residual = F.pixel_shuffle(self.net(x), 2)
        return torch.clamp(base + residual * self.residual_scale, 0.0, 1.0)


class NAFLikeBlock(nn.Module):
    """Small restoration block with depthwise mixing and channel attention."""

    def __init__(self, channels: int) -> None:
        super().__init__()
        hidden = channels * 2
        self.expand = nn.Conv2d(channels, hidden, 1)
        self.depthwise = nn.Conv2d(hidden, hidden, 3, padding=1, groups=hidden)
        self.project = nn.Conv2d(channels, channels, 1)
        self.attn = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, max(4, channels // 4), 1),
            nn.GELU(),
            nn.Conv2d(max(4, channels // 4), channels, 1),
            nn.Sigmoid(),
        )
        self.ffn = nn.Sequential(
            nn.Conv2d(channels, hidden, 1),
            nn.GELU(),
            nn.Conv2d(hidden, channels, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.depthwise(self.expand(x))
        a, b = torch.chunk(y, 2, dim=1)
        y = self.project(a * torch.sigmoid(b))
        x = x + y * self.attn(y)
        return x + self.ffn(x) * 0.1


class NAFResidualPixelShuffleSR(nn.Module):
    def __init__(self, width: int, depth: int, residual_scale: float) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.stem = nn.Conv2d(4, width, 3, padding=1)
        self.blocks = nn.Sequential(*[NAFLikeBlock(width) for _ in range(max(1, depth))])
        self.out = nn.Conv2d(width, 16, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = torch.repeat_interleave(torch.repeat_interleave(x, 2, dim=2), 2, dim=3)
        residual = F.pixel_shuffle(self.out(self.blocks(self.stem(x))), 2)
        return torch.clamp(base + residual * self.residual_scale, 0.0, 1.0)


class SimpleGate(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        a, b = torch.chunk(x, 2, dim=1)
        return a * b


def attention_heads(channels: int) -> int:
    for heads in (8, 4, 2):
        if channels % heads == 0 and channels >= heads:
            return heads
    return 1


class RestormerChannelAttentionBlock(nn.Module):
    """Restormer-style transposed attention over feature channels."""

    def __init__(self, channels: int, ffn_expansion: int = 2) -> None:
        super().__init__()
        self.channels = int(channels)
        heads = attention_heads(self.channels)
        self.heads = heads
        self.channels_per_head = self.channels // heads
        hidden = max(self.channels * int(ffn_expansion), self.channels)
        if hidden % 2:
            hidden += 1
        self.norm1 = nn.GroupNorm(1, self.channels)
        self.qkv = nn.Conv2d(self.channels, self.channels * 3, 1)
        self.qkv_dw = nn.Conv2d(
            self.channels * 3,
            self.channels * 3,
            3,
            padding=1,
            groups=self.channels * 3,
        )
        self.temperature = nn.Parameter(torch.ones((heads, 1, 1)))
        self.project = nn.Conv2d(self.channels, self.channels, 1)
        self.norm2 = nn.GroupNorm(1, self.channels)
        self.ffn_in = nn.Conv2d(self.channels, hidden, 1)
        self.ffn_dw = nn.Conv2d(hidden, hidden, 3, padding=1, groups=hidden)
        self.ffn_gate = SimpleGate()
        self.ffn_out = nn.Conv2d(hidden // 2, self.channels, 1)
        self.attn_scale = nn.Parameter(torch.zeros((1, self.channels, 1, 1)))
        self.ffn_scale = nn.Parameter(torch.zeros((1, self.channels, 1, 1)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, channels, height, width = x.shape
        y = self.qkv_dw(self.qkv(self.norm1(x)))
        q, k, v = torch.chunk(y, 3, dim=1)
        q = q.view(batch, self.heads, self.channels_per_head, height * width)
        k = k.view(batch, self.heads, self.channels_per_head, height * width)
        v = v.view(batch, self.heads, self.channels_per_head, height * width)
        q = F.normalize(q, dim=-1)
        k = F.normalize(k, dim=-1)
        attn = torch.matmul(q, k.transpose(-2, -1)) * self.temperature
        attn = torch.softmax(attn, dim=-1)
        y = torch.matmul(attn, v).view(batch, channels, height, width)
        x = x + self.attn_scale * self.project(y)
        z = self.ffn_dw(self.ffn_in(self.norm2(x)))
        z = self.ffn_out(self.ffn_gate(z))
        return x + self.ffn_scale * z


class RestormerPixelShuffleSR(nn.Module):
    """Clean-source RAW SR teacher with local, pyramid, and global context."""

    def __init__(self, width: int, depth: int, residual_scale: float) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w1 = max(8, int(width))
        w2 = w1 * 2
        self.head = nn.Sequential(nn.Conv2d(4, w1, 3, padding=1), nn.GELU())
        self.local = nn.Sequential(*[RestormerChannelAttentionBlock(w1) for _ in range(max(1, int(depth)))])
        self.down = nn.Sequential(nn.Conv2d(w1, w2, 3, stride=2, padding=1), nn.GELU())
        self.context = nn.Sequential(*[RestormerChannelAttentionBlock(w2) for _ in range(max(1, int(depth) // 2))])
        self.global_proj = nn.Sequential(nn.Conv2d(w1, w2, 1), nn.GELU())
        self.global_body = nn.Sequential(*[RestormerChannelAttentionBlock(w2) for _ in range(max(1, int(depth) // 3))])
        self.up = nn.Conv2d(w2, w1, 1)
        self.global_up = nn.Conv2d(w2, w1, 1)
        self.fuse = nn.Sequential(
            nn.Conv2d(w1 * 3, w1, 1),
            RestormerChannelAttentionBlock(w1),
            RestormerChannelAttentionBlock(w1),
        )
        self.out = nn.Conv2d(w1, 16, 3, padding=1)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = torch.repeat_interleave(torch.repeat_interleave(x, 2, dim=2), 2, dim=3)
        local = self.local(self.head(x))
        context = self.context(self.down(local))
        context = F.interpolate(self.up(context), size=local.shape[-2:], mode="bilinear", align_corners=False)
        global_size = (min(32, max(4, x.shape[-2] // 2)), min(32, max(4, x.shape[-1] // 2)))
        global_context = self.global_proj(F.adaptive_avg_pool2d(local, global_size))
        global_context = self.global_body(global_context)
        global_context = F.interpolate(self.global_up(global_context), size=local.shape[-2:], mode="bilinear", align_corners=False)
        fused = self.fuse(torch.cat([local, context, global_context], dim=1))
        residual = F.pixel_shuffle(self.out(fused), 2)
        return torch.clamp(base + torch.tanh(residual) * self.residual_scale, 0.0, 1.0)


class WindowAttentionBlock(nn.Module):
    """Shifted-window spatial attention over raw feature planes."""

    def __init__(self, channels: int, window_size: int = 8, shifted: bool = False) -> None:
        super().__init__()
        self.channels = int(channels)
        self.window_size = int(window_size)
        self.shifted = bool(shifted)
        self.norm1 = nn.LayerNorm(self.channels)
        self.attn = nn.MultiheadAttention(
            self.channels,
            attention_heads(self.channels),
            batch_first=True,
        )
        self.norm2 = nn.GroupNorm(1, self.channels)
        hidden = max(self.channels * 2, self.channels)
        self.ffn = nn.Sequential(
            nn.Conv2d(self.channels, hidden, 1),
            nn.GELU(),
            nn.Conv2d(hidden, hidden, 3, padding=1, groups=hidden),
            nn.GELU(),
            nn.Conv2d(hidden, self.channels, 1),
        )
        self.attn_scale = nn.Parameter(torch.zeros((1, self.channels, 1, 1)))
        self.ffn_scale = nn.Parameter(torch.zeros((1, self.channels, 1, 1)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, channels, height, width = x.shape
        window = max(2, min(self.window_size, height, width))
        shift = window // 2 if self.shifted and height > window and width > window else 0
        y = torch.roll(x, shifts=(-shift, -shift), dims=(2, 3)) if shift else x
        pad_h = (window - height % window) % window
        pad_w = (window - width % window) % window
        if pad_h or pad_w:
            y = F.pad(y, (0, pad_w, 0, pad_h), mode="reflect")
        padded_h, padded_w = y.shape[-2:]
        n_h = padded_h // window
        n_w = padded_w // window
        tokens = (
            y.view(batch, channels, n_h, window, n_w, window)
            .permute(0, 2, 4, 3, 5, 1)
            .reshape(batch * n_h * n_w, window * window, channels)
        )
        attn_tokens, _ = self.attn(self.norm1(tokens), self.norm1(tokens), tokens, need_weights=False)
        attn_map = (
            attn_tokens.reshape(batch, n_h, n_w, window, window, channels)
            .permute(0, 5, 1, 3, 2, 4)
            .reshape(batch, channels, padded_h, padded_w)
        )
        if pad_h or pad_w:
            attn_map = attn_map[:, :, :height, :width]
        if shift:
            attn_map = torch.roll(attn_map, shifts=(shift, shift), dims=(2, 3))
        x = x + self.attn_scale * attn_map
        return x + self.ffn_scale * self.ffn(self.norm2(x))


class WindowAttentionPixelShuffleSR(nn.Module):
    """Clean-source RAW SR teacher with shifted spatial windows and global context."""

    def __init__(self, width: int, depth: int, residual_scale: float) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w = max(8, int(width))
        blocks: list[nn.Module] = []
        for idx in range(max(1, int(depth))):
            blocks.append(WindowAttentionBlock(w, window_size=8, shifted=bool(idx % 2)))
        self.head = nn.Sequential(nn.Conv2d(4, w, 3, padding=1), nn.GELU())
        self.body = nn.Sequential(*blocks)
        self.context = nn.Sequential(
            nn.AdaptiveAvgPool2d((16, 16)),
            WindowAttentionBlock(w, window_size=8, shifted=False),
            WindowAttentionBlock(w, window_size=8, shifted=True),
        )
        self.fuse = nn.Sequential(
            nn.Conv2d(w * 2, w, 1),
            nn.GELU(),
            nn.Conv2d(w, w, 3, padding=1),
            nn.GELU(),
        )
        self.out = nn.Conv2d(w, 16, 3, padding=1)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = torch.repeat_interleave(torch.repeat_interleave(x, 2, dim=2), 2, dim=3)
        local = self.body(self.head(x))
        context = self.context(local)
        context = F.interpolate(context, size=local.shape[-2:], mode="bilinear", align_corners=False)
        residual = F.pixel_shuffle(self.out(self.fuse(torch.cat([local, context], dim=1))), 2)
        return torch.clamp(base + torch.tanh(residual) * self.residual_scale, 0.0, 1.0)


class FrequencyPyramidPixelShuffleSR(nn.Module):
    """RAW SR teacher with explicit LF/HF/global candidate-only branches."""

    def __init__(self, width: int, depth: int, residual_scale: float) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w = max(8, int(width))
        block_count = max(1, int(depth))
        self.local_head = nn.Sequential(nn.Conv2d(4, w, 3, padding=1), nn.GELU())
        self.local_body = nn.Sequential(
            *[
                nn.Sequential(
                    nn.Conv2d(w, w, 3, padding=1),
                    nn.GELU(),
                    nn.Conv2d(w, w, 3, padding=1),
                    nn.GELU(),
                )
                for _ in range(block_count)
            ]
        )
        self.low_branch = nn.Sequential(
            nn.Conv2d(4, w, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(w, w, 3, padding=1),
            nn.GELU(),
        )
        self.high_branch = nn.Sequential(
            nn.Conv2d(4, w, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(w, w, 3, padding=1),
            nn.GELU(),
        )
        self.global_branch = nn.Sequential(
            nn.AdaptiveAvgPool2d((16, 16)),
            nn.Conv2d(4, w, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(w, w, 3, padding=1),
            nn.GELU(),
        )
        self.fuse = nn.Sequential(
            nn.Conv2d(w * 4, w * 2, 1),
            nn.GELU(),
            nn.Conv2d(w * 2, w, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(w, 16, 3, padding=1),
        )
        nn.init.zeros_(self.fuse[-1].weight)
        nn.init.zeros_(self.fuse[-1].bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = torch.repeat_interleave(torch.repeat_interleave(x, 2, dim=2), 2, dim=3)
        local = self.local_body(self.local_head(x))
        low_input = F.avg_pool2d(x, kernel_size=3, stride=1, padding=1)
        high_input = x - low_input
        low = self.low_branch(low_input)
        high = self.high_branch(high_input)
        global_context = self.global_branch(x)
        global_context = F.interpolate(global_context, size=x.shape[-2:], mode="bilinear", align_corners=False)
        residual = F.pixel_shuffle(self.fuse(torch.cat([local, low, high, global_context], dim=1)), 2)
        return torch.clamp(base + torch.tanh(residual) * self.residual_scale, 0.0, 1.0)


def build_model(model_arch: str, width: int, depth: int, residual_scale: float) -> nn.Module:
    if model_arch == "residual_pixelshuffle":
        return ResidualPixelShuffleSR(width, depth, residual_scale)
    if model_arch == "naf_residual_pixelshuffle":
        return NAFResidualPixelShuffleSR(width, depth, residual_scale)
    if model_arch == "restormer_pixelshuffle":
        return RestormerPixelShuffleSR(width, depth, residual_scale)
    if model_arch == "window_attention_pixelshuffle":
        return WindowAttentionPixelShuffleSR(width, depth, residual_scale)
    if model_arch == "frequency_pyramid_pixelshuffle":
        return FrequencyPyramidPixelShuffleSR(width, depth, residual_scale)
    raise ValueError(f"unknown model architecture: {model_arch}")


def gradient_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    pred_dx = pred[:, :, :, 1:] - pred[:, :, :, :-1]
    targ_dx = target[:, :, :, 1:] - target[:, :, :, :-1]
    pred_dy = pred[:, :, 1:, :] - pred[:, :, :-1, :]
    targ_dy = target[:, :, 1:, :] - target[:, :, :-1, :]
    return F.l1_loss(pred_dx, targ_dx) + F.l1_loss(pred_dy, targ_dy)


def charbonnier_loss(pred: torch.Tensor, target: torch.Tensor, eps: float = 1.0e-3) -> torch.Tensor:
    diff = pred - target
    return torch.mean(torch.sqrt(diff * diff + float(eps) * float(eps)))


def laplacian_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    channels = pred.shape[1]
    kernel = pred.new_tensor([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])
    kernel = kernel.view(1, 1, 3, 3).repeat(channels, 1, 1, 1)
    pred_lap = F.conv2d(F.pad(pred, (1, 1, 1, 1), mode="reflect"), kernel, groups=channels)
    targ_lap = F.conv2d(F.pad(target, (1, 1, 1, 1), mode="reflect"), kernel, groups=channels)
    return F.l1_loss(pred_lap, targ_lap)


def degrade_training_input(
    x: torch.Tensor,
    *,
    noise_std_counts: float,
    gain_jitter_pct: float,
    blur_weight: float,
) -> torch.Tensor:
    out = x
    if gain_jitter_pct > 0.0:
        jitter = float(gain_jitter_pct) / 100.0
        gain = 1.0 + (torch.rand((out.shape[0], out.shape[1], 1, 1), device=out.device) * 2.0 - 1.0) * jitter
        out = out * gain
    if noise_std_counts > 0.0:
        out = out + torch.randn_like(out) * (float(noise_std_counts) / RAW_SCALE)
    if blur_weight > 0.0:
        channels = out.shape[1]
        kernel = out.new_tensor([[1.0, 2.0, 1.0], [2.0, 4.0, 2.0], [1.0, 2.0, 1.0]]) / 16.0
        kernel = kernel.view(1, 1, 3, 3).repeat(channels, 1, 1, 1)
        blurred = F.conv2d(F.pad(out, (1, 1, 1, 1), mode="reflect"), kernel, groups=channels)
        out = torch.lerp(out, blurred, min(max(float(blur_weight), 0.0), 1.0))
    return torch.clamp(out, 0.0, 1.0)


def tile_metrics(pred: np.ndarray, target: np.ndarray, baseline: np.ndarray) -> dict[str, float]:
    pred_counts = pred.astype(np.float64) * RAW_SCALE
    target_counts = target.astype(np.float64) * RAW_SCALE
    base_counts = baseline.astype(np.float64) * RAW_SCALE
    model_diff = pred_counts - target_counts
    base_diff = base_counts - target_counts
    model_mse = float(np.mean(model_diff * model_diff))
    base_mse = float(np.mean(base_diff * base_diff))
    model_mae = float(np.mean(np.abs(model_diff)))
    base_mae = float(np.mean(np.abs(base_diff)))
    model_rmse = float(math.sqrt(model_mse))
    base_rmse = float(math.sqrt(base_mse))
    return {
        "model_mae": model_mae,
        "baseline_mae": base_mae,
        "mae_improvement_pct": float(100.0 * (base_mae - model_mae) / base_mae) if base_mae > 0.0 else 0.0,
        "model_rmse": model_rmse,
        "baseline_rmse": base_rmse,
        "rmse_improvement_pct": float(100.0 * (base_rmse - model_rmse) / base_rmse) if base_rmse > 0.0 else 0.0,
        "model_psnr_db": psnr_from_mse(model_mse),
        "baseline_psnr_db": psnr_from_mse(base_mse),
    }


def evaluate(model: nn.Module, dataset: CleanSourcePairs, indices: np.ndarray, split: str) -> dict[str, Any]:
    model.eval()
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for idx in indices:
            i = int(idx)
            x_np = dataset.inputs[i]
            target_np = dataset.targets[i]
            baseline_np = np.repeat(np.repeat(x_np, 2, axis=1), 2, axis=2)
            pred = model(torch.from_numpy(x_np[None]).to(DEVICE)).cpu().numpy()[0]
            rows.append(
                {
                    "tile_index": i,
                    "split": split,
                    "image_id": str(dataset.image_ids[i]),
                    **tile_metrics(pred, target_np, baseline_np),
                }
            )
    model.train()
    return {
        "split": split,
        "tile_count": len(rows),
        "model_mae": stats([row["model_mae"] for row in rows]),
        "baseline_mae": stats([row["baseline_mae"] for row in rows]),
        "mae_improvement_pct": stats([row["mae_improvement_pct"] for row in rows]),
        "model_rmse": stats([row["model_rmse"] for row in rows]),
        "baseline_rmse": stats([row["baseline_rmse"] for row in rows]),
        "rmse_improvement_pct": stats([row["rmse_improvement_pct"] for row in rows]),
        "model_psnr_db": stats([row["model_psnr_db"] for row in rows]),
        "baseline_psnr_db": stats([row["baseline_psnr_db"] for row in rows]),
        "rows": rows,
    }


def render_html(receipt: dict[str, Any]) -> str:
    holdout = receipt["eval"]["holdout"]
    train = receipt["eval"]["train"]
    status = "PROMOTABLE" if receipt["promotion"]["baseline_beaten_on_holdout"] else "DIAGNOSTIC ONLY"
    row_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['split'])}</td>"
        f"<td>{html.escape(row['image_id'])}</td>"
        f"<td>{row['tile_index']}</td>"
        f"<td>{row['baseline_mae']:.3f}</td>"
        f"<td>{row['model_mae']:.3f}</td>"
        f"<td>{row['mae_improvement_pct']:.2f}%</td>"
        f"<td>{row['baseline_rmse']:.3f}</td>"
        f"<td>{row['model_rmse']:.3f}</td>"
        "</tr>"
        for split in (train, holdout)
        for row in split["rows"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Clean-Source Pair Model</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 24px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin-top: 12px; }}
th, td {{ border-bottom: 1px solid #e9edf1; padding: 8px; text-align: left; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; font-size: 12px; }}
</style></head><body><main>
<h1>Premium Still-SR Clean-Source Pair Model</h1>
<p>Held-out same-color Bayer SR candidate compared against nearest same-color 2x. Status: <strong>{status}</strong>.</p>
<div class="grid">
  <section class="card"><div class="label">Holdout tiles</div><div class="value">{holdout['tile_count']}</div></section>
  <section class="card"><div class="label">Holdout MAE gain</div><div class="value">{holdout['mae_improvement_pct']['median']:.2f}%</div></section>
  <section class="card"><div class="label">Holdout RMSE gain</div><div class="value">{holdout['rmse_improvement_pct']['median']:.2f}%</div></section>
  <section class="card"><div class="label">Train MAE gain</div><div class="value">{train['mae_improvement_pct']['median']:.2f}%</div></section>
</div>
<p><strong>Pairs:</strong> <code>{html.escape(receipt['pairs'])}</code></p>
<p><strong>Checkpoint:</strong> <code>{html.escape(receipt['checkpoint'])}</code></p>
<h2>Rows</h2>
<table><tr><th>split</th><th>image</th><th>tile</th><th>baseline MAE</th><th>model MAE</th><th>MAE gain</th><th>baseline RMSE</th><th>model RMSE</th></tr>{row_html}</table>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--checkpoint-name", default="premium_still_sr_clean_source_pair_model.pt")
    ap.add_argument("--holdout-image", action="append", default=[])
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--low-crop", type=int, default=48)
    ap.add_argument(
        "--model-arch",
        choices=[
            "residual_pixelshuffle",
            "naf_residual_pixelshuffle",
            "restormer_pixelshuffle",
            "window_attention_pixelshuffle",
            "frequency_pyramid_pixelshuffle",
        ],
        default="residual_pixelshuffle",
    )
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument("--residual-scale", type=float, default=0.25)
    ap.add_argument("--gradient-loss-weight", type=float, default=0.0)
    ap.add_argument("--laplacian-loss-weight", type=float, default=0.0)
    ap.add_argument(
        "--loss-mode",
        choices=["l1", "charbonnier"],
        default="l1",
        help="pixel-domain loss used before optional detail losses",
    )
    ap.add_argument(
        "--train-input-noise-std-counts",
        type=float,
        default=0.0,
        help="training-only Gaussian RAW noise injected into low planes, in normalized 14-bit counts",
    )
    ap.add_argument(
        "--train-input-gain-jitter-pct",
        type=float,
        default=0.0,
        help="training-only per-plane multiplicative gain jitter on low planes, in percent",
    )
    ap.add_argument(
        "--train-input-blur-weight",
        type=float,
        default=0.0,
        help="training-only blend weight for a same-plane 3x3 blur on low planes",
    )
    ap.add_argument("--lr", type=float, default=1.0e-3)
    ap.add_argument("--weight-decay", type=float, default=1.0e-4)
    ap.add_argument("--seed", type=int, default=20260702)
    ap.add_argument("--eval-every", type=int, default=100)
    args = ap.parse_args()

    if _MISSING_DEPS_ERROR is not None:
        print(
            "train_premium_still_sr_clean_source_pairs.py requires numpy and torch "
            "for training. Install tools/cnn/requirements.txt in the active "
            "Python environment before running a model.",
            file=sys.stderr,
        )
        print(f"missing dependency: {_MISSING_DEPS_ERROR.name}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    dataset = CleanSourcePairs(args.pairs, parse_image_list(args.holdout_image))
    model = build_model(args.model_arch, args.width, args.depth, args.residual_scale).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, Any]] = []
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, y = dataset.batch(args.batch, args.low_crop, rng)
        degraded_x = degrade_training_input(
            x,
            noise_std_counts=args.train_input_noise_std_counts,
            gain_jitter_pct=args.train_input_gain_jitter_pct,
            blur_weight=args.train_input_blur_weight,
        )
        pred = model(degraded_x)
        pixel_l1 = F.l1_loss(pred, y)
        pixel_loss = charbonnier_loss(pred, y) if args.loss_mode == "charbonnier" else pixel_l1
        detail_l1 = gradient_loss(pred, y) if args.gradient_loss_weight > 0.0 else pred.new_tensor(0.0)
        lap_l1 = laplacian_loss(pred, y) if args.laplacian_loss_weight > 0.0 else pred.new_tensor(0.0)
        loss = pixel_loss + float(args.gradient_loss_weight) * detail_l1 + float(args.laplacian_loss_weight) * lap_l1
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step == 1 or step == args.steps or (args.eval_every > 0 and step % args.eval_every == 0):
            history.append(
                {
                    "step": step,
                    "train_loss": float(loss.detach().cpu().item()),
                    "pixel_l1": float(pixel_l1.detach().cpu().item()),
                    "pixel_loss": float(pixel_loss.detach().cpu().item()),
                    "gradient_l1": float(detail_l1.detach().cpu().item()),
                    "laplacian_l1": float(lap_l1.detach().cpu().item()),
                }
            )

    train_eval = evaluate(model, dataset, dataset.train_idx, "train")
    holdout_eval = evaluate(model, dataset, dataset.eval_idx, "holdout")
    checkpoint = args.output_dir / args.checkpoint_name
    torch.save(
        {
            "schema": SCHEMA,
            "state_dict": model.state_dict(),
            "config": {
                "architecture": args.model_arch,
                "width": args.width,
                "depth": args.depth,
                "residual_scale": args.residual_scale,
                "gradient_loss_weight": args.gradient_loss_weight,
                "laplacian_loss_weight": args.laplacian_loss_weight,
                "loss_mode": args.loss_mode,
                "train_input_noise_std_counts": args.train_input_noise_std_counts,
                "train_input_gain_jitter_pct": args.train_input_gain_jitter_pct,
                "train_input_blur_weight": args.train_input_blur_weight,
                "raw_scale": RAW_SCALE,
            },
            "pair_npz_sha256": sha256_file(args.pairs),
        },
        checkpoint,
    )
    holdout_mae_gain = float(holdout_eval["mae_improvement_pct"]["median"] or 0.0)
    holdout_rmse_gain = float(holdout_eval["rmse_improvement_pct"]["median"] or 0.0)
    baseline_beaten = holdout_mae_gain > 0.0 and holdout_rmse_gain > 0.0
    enough_coverage = len(set(dataset.image_ids[dataset.eval_idx].tolist())) >= 2 and len(dataset.eval_idx) >= 16
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pairs": args.pairs.as_posix(),
        "pairs_sha256": sha256_file(args.pairs),
        "checkpoint": checkpoint.as_posix(),
        "checkpoint_sha256": sha256_file(checkpoint),
        "device": str(DEVICE),
        "config": {
            "steps": args.steps,
            "batch": args.batch,
            "low_crop": args.low_crop,
            "model_arch": args.model_arch,
            "width": args.width,
            "depth": args.depth,
            "residual_scale": args.residual_scale,
            "gradient_loss_weight": args.gradient_loss_weight,
            "laplacian_loss_weight": args.laplacian_loss_weight,
            "loss_mode": args.loss_mode,
            "train_input_noise_std_counts": args.train_input_noise_std_counts,
            "train_input_gain_jitter_pct": args.train_input_gain_jitter_pct,
            "train_input_blur_weight": args.train_input_blur_weight,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "seed": args.seed,
            "holdout_images": dataset.holdout_images,
        },
        "pair_meta": {
            "dataset_label": dataset.meta.get("dataset_label"),
            "image_count": len(dataset.meta.get("images", [])),
            "tile_count": len(dataset.inputs),
            "input_shape": list(map(int, dataset.inputs.shape)),
            "target_shape": list(map(int, dataset.targets.shape)),
        },
        "history": history,
        "eval": {"train": train_eval, "holdout": holdout_eval},
        "promotion": {
            "baseline": "nearest_same_color_2x",
            "baseline_beaten_on_holdout": baseline_beaten,
            "coverage_sufficient_for_promotion": enough_coverage,
            "promotion_ready": bool(baseline_beaten and enough_coverage),
            "decision": (
                "candidate may enter broader premium still-SR gate"
                if baseline_beaten and enough_coverage
                else "diagnostic only; broaden pairs and beat held-out baseline before promotion"
            ),
        },
        "elapsed_seconds": time.time() - t0,
    }
    receipt_path = args.output_dir / "train_receipt.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "dashboard": str(html_path), "promotion": receipt["promotion"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
