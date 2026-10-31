#!/usr/bin/env python3
"""Train/evaluate Mission 1 12MP-to-50MP Bayer SR.

Input pairs are produced by `build_mission1_sr_pairs.py`:
  inputs:  N x 4 x low_tile x low_tile uint16
  targets: N x 4 x (2*low_tile) x (2*low_tile) uint16

The models are intentionally residual: bilinear 2x is the baseline, and the
network predicts a bounded correction. `residual_highres` is the original
prototype. `lowres_pixelshuffle` keeps the trunk at 12MP-plane resolution and
uses a subpixel head for the 2x residual, which is the preferred runtime shape.
`resblock_pixelshuffle` adds local residual blocks around that low-res trunk for
the next guarded probe without changing the full-frame evaluator contract.
`edge_pixelshuffle` keeps the lowres trunk and adds a zero-initialized
highpass-conditioned residual head for targeted detail-placement probes.
`adapter_pixelshuffle` keeps a loaded lowres trunk intact and adds a
zero-initialized dilated adapter branch for context/capacity probes.
`green_detail_adapter_pixelshuffle` keeps that adapter output intact and adds a
zero-initialized green-plane detail branch for misses where g1/g2 high-frequency
signal is the narrowed blocker.
`preclean_adapter_pixelshuffle` adds a zero-initialized low-res correction
branch before that adapter trunk for codec-artifact cleanup probes.
`coord_preclean_adapter_pixelshuffle` adds absolute low-frame XY coordinate
channels to the SR trunk so full-frame coverage probes can learn
position/phase-dependent correction while preserving the 4-channel precleaner.
`coord_detail_preclean_adapter_pixelshuffle` also appends deterministic
same-color detail channels from the cleaned low Bayer planes, giving the
adapter branch explicit phase/detail evidence while zero-expanded initialization
preserves the current coord-preclean function.
"""
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


RAW_SCALE = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def parse_holdout_images(holdout_image: str | None) -> set[str]:
    if not holdout_image:
        return set()
    return {item.strip() for item in holdout_image.split(",") if item.strip()}


def parse_focus_images(focus_image: str | None) -> set[str]:
    if not focus_image:
        return set()
    return {item.strip() for item in focus_image.split(",") if item.strip()}


def parse_plane_weights(value: str | None) -> tuple[float, float, float, float]:
    if not value:
        return (1.0, 1.0, 1.0, 1.0)
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--plane-weights expects four comma-separated values: r,g1,g2,b")
    weights = tuple(float(part) for part in parts)
    if any(weight <= 0.0 for weight in weights):
        raise argparse.ArgumentTypeError("--plane-weights values must be positive")
    return weights  # type: ignore[return-value]


class Mission1SRPairs:
    def __init__(
        self,
        path: Path,
        holdout_image: str | None,
        focus_image: str | None = None,
        focus_weight: float = 1.0,
        load_low_clean_targets: bool = False,
    ) -> None:
        z = np.load(path, allow_pickle=False)
        self.inputs = z["inputs"].astype(np.float32) / RAW_SCALE
        self.targets = z["targets"].astype(np.float32) / RAW_SCALE
        self.meta = json.loads(str(z["meta"]))
        self.tiles = list(self.meta["tiles"])
        self.image_ids = np.array([row["image_id"] for row in self.meta["tiles"]])
        self.tile_low_x = np.array([int(row["low_x"]) for row in self.tiles], dtype=np.int32)
        self.tile_low_y = np.array([int(row["low_y"]) for row in self.tiles], dtype=np.int32)
        width12 = int(self.meta.get("width12") or 0)
        height12 = int(self.meta.get("height12") or 0)
        if width12 <= 0 or height12 <= 0:
            widths = [int(row.get("low_width") or 0) for row in self.meta.get("images", []) if isinstance(row, dict)]
            heights = [int(row.get("low_height") or 0) for row in self.meta.get("images", []) if isinstance(row, dict)]
            width12 = max(widths or [0])
            height12 = max(heights or [0])
        if width12 <= 0 or height12 <= 0:
            raise ValueError(f"{path} lacks width12/height12 and per-image low dimensions")
        self.plane_width = width12 // 2
        self.plane_height = height12 // 2
        self.low_clean_targets: np.ndarray | None = None
        if load_low_clean_targets:
            self.low_clean_targets = self._load_low_clean_targets(path)
        holdout_images = parse_holdout_images(holdout_image)
        if holdout_images:
            holdout_mask = np.isin(self.image_ids, list(holdout_images))
            self.train_idx = np.where(~holdout_mask)[0]
            self.eval_idx = np.where(holdout_mask)[0]
            if len(self.eval_idx) == 0:
                raise ValueError(f"holdout image(s) {sorted(holdout_images)} not found in {path}")
        else:
            rng = np.random.default_rng(20260616)
            order = rng.permutation(len(self.inputs))
            n_eval = max(1, len(order) // 5)
            self.eval_idx = order[:n_eval]
            self.train_idx = order[n_eval:]
        if len(self.train_idx) == 0:
            raise ValueError("empty training split")
        self.focus_images = parse_focus_images(focus_image)
        self.focus_weight = max(1.0, float(focus_weight))
        self.train_weights: np.ndarray | None = None
        if self.focus_images:
            missing = sorted(self.focus_images - set(self.image_ids.tolist()))
            if missing:
                raise ValueError(f"focus image(s) {missing} not found in {path}")
            weights = np.ones(len(self.train_idx), dtype=np.float64)
            focus_mask = np.isin(self.image_ids[self.train_idx], list(self.focus_images))
            weights[focus_mask] = self.focus_weight
            weights_sum = float(weights.sum())
            if weights_sum <= 0.0:
                raise ValueError("invalid focus weights")
            self.train_weights = weights / weights_sum

    def _load_low_clean_targets(self, path: Path) -> np.ndarray:
        images = {str(row["image_id"]): row for row in self.meta.get("images", [])}
        low_tile = int(self.meta["low_tile"])
        cache: dict[str, np.ndarray] = {}
        targets: list[np.ndarray] = []
        for tile in self.meta["tiles"]:
            image_id = str(tile["image_id"])
            image = images.get(image_id)
            if not image or not image.get("low_clean_raw"):
                raise ValueError(f"{path} lacks low_clean_raw metadata for {image_id}")
            if image_id not in cache:
                raw_path = Path(str(image["low_clean_raw"]))
                width = int(image["low_width"])
                height = int(image["low_height"])
                arr = np.fromfile(raw_path, dtype="<u2")
                expected = width * height
                if arr.size != expected:
                    raise ValueError(f"{raw_path} has {arr.size} pixels, expected {expected}")
                bayer = arr.reshape(height, width)
                cache[image_id] = np.stack(
                    [
                        bayer[0::2, 0::2],
                        bayer[0::2, 1::2],
                        bayer[1::2, 0::2],
                        bayer[1::2, 1::2],
                    ],
                    axis=0,
                )
            x = int(tile["low_x"])
            y = int(tile["low_y"])
            targets.append(cache[image_id][:, y : y + low_tile, x : x + low_tile])
        return np.stack(targets).astype(np.float32) / RAW_SCALE

    def coord_channels_for_indices(self, idx: list[int] | np.ndarray) -> torch.Tensor:
        _, _, h, w = self.inputs.shape
        rows = []
        x_base = np.arange(w, dtype=np.float32)[None, :]
        y_base = np.arange(h, dtype=np.float32)[:, None]
        x_den = max(1, self.plane_width - 1)
        y_den = max(1, self.plane_height - 1)
        for item in idx:
            i = int(item)
            x0 = float(self.tile_low_x[i])
            y0 = float(self.tile_low_y[i])
            x_coord = ((x0 + x_base) / x_den) * 2.0 - 1.0
            y_coord = ((y0 + y_base) / y_den) * 2.0 - 1.0
            rows.append(np.stack([np.broadcast_to(x_coord, (h, w)), np.broadcast_to(y_coord, (h, w))], axis=0))
        return torch.from_numpy(np.stack(rows).astype(np.float32)).to(DEVICE)

    def batch(
        self,
        batch_size: int,
        rng: random.Random,
        with_coords: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None, torch.Tensor | None]:
        if self.train_weights is not None:
            idx = np.random.default_rng(rng.randrange(0, 2**32 - 1)).choice(
                self.train_idx,
                size=batch_size,
                replace=True,
                p=self.train_weights,
            )
            idx = [int(i) for i in idx]
        else:
            idx = [int(self.train_idx[rng.randrange(0, len(self.train_idx))]) for _ in range(batch_size)]
        x = torch.from_numpy(self.inputs[idx]).to(DEVICE)
        y = torch.from_numpy(self.targets[idx]).to(DEVICE)
        low_clean = torch.from_numpy(self.low_clean_targets[idx]).to(DEVICE) if self.low_clean_targets is not None else None
        coords = self.coord_channels_for_indices(idx) if with_coords else None
        return x, y, low_clean, coords


class ResidualSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        layers: list[nn.Module] = [nn.Conv2d(4, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        layers.append(nn.Conv2d(width, 4, 3, padding=1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
        residual = self.net(base)
        return torch.clamp(base + residual * self.residual_scale, 0.0, 1.0)


class LowResPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        layers: list[nn.Module] = [nn.Conv2d(4, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        residual_head = nn.Conv2d(width, 16, 3, padding=1)
        nn.init.zeros_(residual_head.weight)
        nn.init.zeros_(residual_head.bias)
        layers += [residual_head, nn.PixelShuffle(2)]
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
        residual = self.net(x)
        return torch.clamp(base + residual * self.residual_scale, 0.0, 1.0)


class ResidualBlock(nn.Module):
    def __init__(self, width: int, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        self.net = nn.Sequential(
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.net(x) * self.residual_scale


class ResBlockPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        block_count = max(1, depth - 2)
        self.residual_scale = residual_scale
        self.head = nn.Conv2d(4, width, 3, padding=1)
        self.body = nn.Sequential(*[ResidualBlock(width) for _ in range(block_count)])
        residual_head = nn.Conv2d(width, 16, 3, padding=1)
        nn.init.zeros_(residual_head.weight)
        nn.init.zeros_(residual_head.bias)
        self.tail = nn.Sequential(
            nn.GELU(),
            residual_head,
            nn.PixelShuffle(2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
        feat = self.head(x)
        residual = self.tail(self.body(feat))
        return torch.clamp(base + residual * self.residual_scale, 0.0, 1.0)


class EdgePixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        layers: list[nn.Module] = [nn.Conv2d(4, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        residual_head = nn.Conv2d(width, 16, 3, padding=1)
        nn.init.zeros_(residual_head.weight)
        nn.init.zeros_(residual_head.bias)
        layers += [residual_head, nn.PixelShuffle(2)]
        self.net = nn.Sequential(*layers)
        edge_head = nn.Conv2d(4, 16, 3, padding=1)
        nn.init.zeros_(edge_head.weight)
        nn.init.zeros_(edge_head.bias)
        self.edge = nn.Sequential(edge_head, nn.PixelShuffle(2))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
        residual = self.net(x)
        blur = F.avg_pool2d(x, kernel_size=3, stride=1, padding=1)
        edge_residual = self.edge(x - blur)
        return torch.clamp(base + (residual + edge_residual) * self.residual_scale, 0.0, 1.0)


class AdapterPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1, input_channels: int = 4) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        self.input_channels = input_channels
        layers: list[nn.Module] = [nn.Conv2d(input_channels, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        residual_head = nn.Conv2d(width, 16, 3, padding=1)
        nn.init.zeros_(residual_head.weight)
        nn.init.zeros_(residual_head.bias)
        layers += [residual_head, nn.PixelShuffle(2)]
        self.net = nn.Sequential(*layers)

        adapter_layers: list[nn.Module] = [
            nn.Conv2d(input_channels, width, 3, padding=2, dilation=2),
            nn.GELU(),
        ]
        for dilation in (2, 4):
            adapter_layers += [
                nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation),
                nn.GELU(),
            ]
        adapter_head = nn.Conv2d(width, 16, 3, padding=1)
        nn.init.zeros_(adapter_head.weight)
        nn.init.zeros_(adapter_head.bias)
        adapter_layers += [adapter_head, nn.PixelShuffle(2)]
        self.adapter = nn.Sequential(*adapter_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = F.interpolate(x[:, :4], scale_factor=2, mode="bilinear", align_corners=False)
        residual = self.net(x) + self.adapter(x)
        return torch.clamp(base + residual * self.residual_scale, 0.0, 1.0)


class GreenDetailAdapterPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.residual_scale = residual_scale
        self.sr = AdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
        detail_layers: list[nn.Module] = [
            nn.Conv2d(4, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=4, dilation=4),
            nn.GELU(),
        ]
        detail_head = nn.Conv2d(width, 8, 3, padding=1)
        nn.init.zeros_(detail_head.weight)
        nn.init.zeros_(detail_head.bias)
        detail_layers += [detail_head, nn.PixelShuffle(2)]
        self.green_detail = nn.Sequential(*detail_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.sr(x)
        green_residual = self.green_detail(x)
        green = torch.clamp(out[:, 1:3] + green_residual * self.residual_scale, 0.0, 1.0)
        return torch.cat([out[:, 0:1], green, out[:, 3:4]], dim=1)


class PrecleanAdapterPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.preclean_scale = 0.05
        self.sr = AdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
        preclean_head = nn.Conv2d(4, width, 3, padding=1)
        preclean_tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(preclean_tail.weight)
        nn.init.zeros_(preclean_tail.bias)
        self.preclean = nn.Sequential(
            preclean_head,
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            preclean_tail,
        )

    def clean_low(self, x: torch.Tensor) -> torch.Tensor:
        return torch.clamp(x + self.preclean(x) * self.preclean_scale, 0.0, 1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.sr(self.clean_low(x))


class CoordPrecleanAdapterPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.preclean_scale = 0.05
        self.sr = AdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale, input_channels=6)
        preclean_head = nn.Conv2d(4, width, 3, padding=1)
        preclean_tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(preclean_tail.weight)
        nn.init.zeros_(preclean_tail.bias)
        self.preclean = nn.Sequential(
            preclean_head,
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            preclean_tail,
        )

    def clean_low(self, x: torch.Tensor) -> torch.Tensor:
        raw = x[:, :4]
        return torch.clamp(raw + self.preclean(raw) * self.preclean_scale, 0.0, 1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] != 6:
            raise ValueError("coord_preclean_adapter_pixelshuffle expects 6 input channels")
        clean = self.clean_low(x)
        return self.sr(torch.cat([clean, x[:, 4:6]], dim=1))


class CoordDeepPrecleanAdapterPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.preclean_scale = 0.05
        self.sr = AdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale, input_channels=6)
        preclean_head = nn.Conv2d(4, width, 3, padding=1)
        preclean_tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(preclean_tail.weight)
        nn.init.zeros_(preclean_tail.bias)
        self.preclean = nn.Sequential(
            preclean_head,
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            preclean_tail,
        )

        extra_layers: list[nn.Module] = [
            nn.Conv2d(4, width, 3, padding=1),
            nn.GELU(),
        ]
        for dilation in (1, 2, 4, 2, 1):
            extra_layers += [
                nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation),
                nn.GELU(),
            ]
        extra_tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(extra_tail.weight)
        nn.init.zeros_(extra_tail.bias)
        extra_layers.append(extra_tail)
        self.preclean_extra = nn.Sequential(*extra_layers)

    def clean_low(self, x: torch.Tensor) -> torch.Tensor:
        raw = x[:, :4]
        correction = self.preclean(raw) + self.preclean_extra(raw)
        return torch.clamp(raw + correction * self.preclean_scale, 0.0, 1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] != 6:
            raise ValueError("coord_deep_preclean_adapter_pixelshuffle expects 6 input channels")
        clean = self.clean_low(x)
        return self.sr(torch.cat([clean, x[:, 4:6]], dim=1))


class CoordDetailPrecleanAdapterPixelShuffleSR(nn.Module):
    def __init__(self, width: int = 32, depth: int = 5, residual_scale: float = 0.1) -> None:
        super().__init__()
        self.preclean_scale = 0.05
        self.sr = AdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale, input_channels=10)
        preclean_head = nn.Conv2d(4, width, 3, padding=1)
        preclean_tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(preclean_tail.weight)
        nn.init.zeros_(preclean_tail.bias)
        self.preclean = nn.Sequential(
            preclean_head,
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            preclean_tail,
        )

    def clean_low(self, x: torch.Tensor) -> torch.Tensor:
        raw = x[:, :4]
        return torch.clamp(raw + self.preclean(raw) * self.preclean_scale, 0.0, 1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] != 6:
            raise ValueError("coord_detail_preclean_adapter_pixelshuffle expects 6 input channels")
        clean = self.clean_low(x)
        detail = binomial_detail(clean)
        return self.sr(torch.cat([clean, x[:, 4:6], detail], dim=1))


def make_model(architecture: str, width: int, depth: int, residual_scale: float) -> nn.Module:
    if architecture == "residual_highres":
        return ResidualSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "lowres_pixelshuffle":
        return LowResPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "resblock_pixelshuffle":
        return ResBlockPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "edge_pixelshuffle":
        return EdgePixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "adapter_pixelshuffle":
        return AdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "green_detail_adapter_pixelshuffle":
        return GreenDetailAdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "preclean_adapter_pixelshuffle":
        return PrecleanAdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "coord_preclean_adapter_pixelshuffle":
        return CoordPrecleanAdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "coord_detail_preclean_adapter_pixelshuffle":
        return CoordDetailPrecleanAdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    if architecture == "coord_deep_preclean_adapter_pixelshuffle":
        return CoordDeepPrecleanAdapterPixelShuffleSR(width=width, depth=depth, residual_scale=residual_scale)
    raise ValueError(f"unknown architecture: {architecture}")


def make_model_from_config(config: dict[str, Any]) -> nn.Module:
    return make_model(
        str(config.get("architecture", "residual_highres")),
        width=int(config["width"]),
        depth=int(config["depth"]),
        residual_scale=float(config["residual_scale"]),
    )


def expand_lowres_pixelshuffle_state(
    source_state: dict[str, torch.Tensor],
    target_state: dict[str, torch.Tensor],
) -> tuple[dict[str, torch.Tensor], list[str], list[str]]:
    """Copy a narrower lowres_pixelshuffle checkpoint into a wider model.

    New channels and cross-channel links are zeroed so the widened model starts
    as the original function with dormant extra capacity. This is different
    from non-strict loading, which leaves the target model mostly random when
    layer names or shapes differ.
    """
    expanded: dict[str, torch.Tensor] = {}
    skipped: list[str] = []
    copied: list[str] = []
    for key, target_value in target_state.items():
        source_value = source_state.get(key)
        if source_value is None:
            skipped.append(key)
            expanded[key] = target_value
            continue
        if source_value.shape == target_value.shape:
            expanded[key] = source_value.clone()
            copied.append(key)
            continue
        if len(source_value.shape) != len(target_value.shape):
            skipped.append(key)
            expanded[key] = target_value
            continue
        if any(int(src) > int(dst) for src, dst in zip(source_value.shape, target_value.shape)):
            skipped.append(key)
            expanded[key] = target_value
            continue
        if source_value.ndim not in {1, 4}:
            skipped.append(key)
            expanded[key] = target_value
            continue

        widened = torch.zeros_like(target_value)
        slices = tuple(slice(0, int(dim)) for dim in source_value.shape)
        widened[slices] = source_value
        expanded[key] = widened
        copied.append(key)
    unexpected = sorted(set(source_state) - set(target_state))
    return expanded, skipped, unexpected


def expand_input_channels(value: torch.Tensor, target_shape: torch.Size) -> torch.Tensor | None:
    if value.ndim != 4 or len(target_shape) != 4:
        return None
    if value.shape[0] != target_shape[0] or value.shape[2:] != target_shape[2:]:
        return None
    if value.shape[1] > target_shape[1]:
        return None
    expanded = torch.zeros(target_shape, dtype=value.dtype)
    expanded[:, : value.shape[1], :, :] = value
    return expanded


def initialize_coord_preclean_from_preclean(
    source_state: dict[str, torch.Tensor],
    target_state: dict[str, torch.Tensor],
) -> tuple[dict[str, torch.Tensor], list[str], list[str]]:
    expanded: dict[str, torch.Tensor] = {}
    skipped: list[str] = []
    copied: list[str] = []
    for key, target_value in target_state.items():
        source_value = source_state.get(key)
        if source_value is None:
            expanded[key] = target_value
            skipped.append(key)
            continue
        if source_value.shape == target_value.shape:
            expanded[key] = source_value.clone()
            copied.append(key)
            continue
        widened = expand_input_channels(source_value, target_value.shape)
        if widened is not None:
            expanded[key] = widened
            copied.append(key)
            continue
        expanded[key] = target_value
        skipped.append(key)
    unexpected = sorted(set(source_state) - set(target_state))
    return expanded, skipped, unexpected


def initialize_model(
    model: nn.Module,
    init_checkpoint: Path,
    *,
    architecture: str,
    width: int,
    depth: int,
    residual_scale: float,
    init_nonstrict: bool,
    init_expand_lowres: bool,
) -> tuple[Any, dict[str, Any]]:
    ckpt = torch.load(init_checkpoint, map_location="cpu", weights_only=False)
    if architecture == "green_detail_adapter_pixelshuffle":
        source_config = ckpt.get("config", {})
        if source_config.get("architecture") == "green_detail_adapter_pixelshuffle":
            result = model.load_state_dict(ckpt["model"], strict=not init_nonstrict)
            return result, {
                "mode": "load_state_dict",
                "source_config": source_config,
                "expanded_keys": [],
            }
        if source_config.get("architecture") != "adapter_pixelshuffle":
            raise ValueError("--init-checkpoint for green_detail_adapter_pixelshuffle must be adapter_pixelshuffle")
        remapped = {f"sr.{key}": value for key, value in ckpt["model"].items()}
        result = model.load_state_dict(remapped, strict=False)
        return result, {
            "mode": "adapter_to_green_detail_adapter",
            "source_config": source_config,
            "expanded_keys": sorted(remapped),
            "missing_keys": list(result.missing_keys),
            "unexpected_keys": list(result.unexpected_keys),
        }

    if architecture == "preclean_adapter_pixelshuffle":
        source_config = ckpt.get("config", {})
        if source_config.get("architecture") == "preclean_adapter_pixelshuffle":
            result = model.load_state_dict(ckpt["model"], strict=not init_nonstrict)
            return result, {
                "mode": "load_state_dict",
                "source_config": source_config,
                "expanded_keys": [],
            }
        if source_config.get("architecture") != "adapter_pixelshuffle":
            raise ValueError("--init-checkpoint for preclean_adapter_pixelshuffle must be adapter_pixelshuffle")
        remapped = {}
        for key, value in ckpt["model"].items():
            remapped[f"sr.{key}"] = value
        result = model.load_state_dict(remapped, strict=False)
        return result, {
            "mode": "adapter_to_preclean_adapter",
            "source_config": source_config,
            "expanded_keys": sorted(remapped),
        }

    if architecture in {
        "coord_preclean_adapter_pixelshuffle",
        "coord_deep_preclean_adapter_pixelshuffle",
        "coord_detail_preclean_adapter_pixelshuffle",
    }:
        source_config = ckpt.get("config", {})
        if source_config.get("architecture") == architecture:
            result = model.load_state_dict(ckpt["model"], strict=not init_nonstrict)
            return result, {
                "mode": "load_state_dict",
                "source_config": source_config,
                "expanded_keys": [],
            }
        if (
            architecture == "coord_deep_preclean_adapter_pixelshuffle"
            and source_config.get("architecture") == "coord_preclean_adapter_pixelshuffle"
        ):
            result = model.load_state_dict(ckpt["model"], strict=False)
            return result, {
                "mode": "coord_preclean_to_coord_deep_preclean",
                "source_config": source_config,
                "expanded_keys": sorted(ckpt["model"]),
                "missing_keys": list(result.missing_keys),
                "unexpected_keys": list(result.unexpected_keys),
            }
        if source_config.get("architecture") != "preclean_adapter_pixelshuffle":
            if (
                architecture == "coord_detail_preclean_adapter_pixelshuffle"
                and source_config.get("architecture") == "coord_preclean_adapter_pixelshuffle"
            ):
                expanded, skipped, unexpected = initialize_coord_preclean_from_preclean(
                    ckpt["model"],
                    model.state_dict(),
                )
                result = model.load_state_dict(expanded, strict=True)
                return result, {
                    "mode": "coord_preclean_to_coord_detail_preclean",
                    "source_config": source_config,
                    "expanded_keys": sorted(set(expanded) - set(skipped)),
                    "skipped_keys": skipped,
                    "unexpected_keys": unexpected,
                }
            raise ValueError(
                f"--init-checkpoint for {architecture} must be preclean_adapter_pixelshuffle"
                " or coord_preclean_adapter_pixelshuffle"
            )
        expanded, skipped, unexpected = initialize_coord_preclean_from_preclean(ckpt["model"], model.state_dict())
        result = model.load_state_dict(expanded, strict=True)
        return result, {
            "mode": "preclean_adapter_to_coord_preclean_adapter",
            "source_config": source_config,
            "expanded_keys": sorted(set(expanded) - set(skipped)),
            "skipped_keys": skipped,
            "unexpected_keys": unexpected,
        }

    if not init_expand_lowres:
        result = model.load_state_dict(ckpt["model"], strict=not init_nonstrict)
        return result, {
            "mode": "load_state_dict",
            "expanded_keys": [],
        }

    source_config = ckpt.get("config", {})
    if source_config.get("architecture") != "lowres_pixelshuffle" or architecture not in {
        "lowres_pixelshuffle",
        "adapter_pixelshuffle",
    }:
        raise ValueError("--init-expand-lowres requires lowres_pixelshuffle source and compatible target")
    if int(source_config.get("depth", -1)) != int(depth):
        raise ValueError("--init-expand-lowres requires matching depth")
    if float(source_config.get("residual_scale", residual_scale)) != float(residual_scale):
        raise ValueError("--init-expand-lowres requires matching residual scale")
    if int(source_config.get("width", width)) > int(width):
        raise ValueError("--init-expand-lowres can only copy into the same or wider width")

    expanded, skipped, unexpected = expand_lowres_pixelshuffle_state(ckpt["model"], model.state_dict())
    result = model.load_state_dict(expanded, strict=True)
    return result, {
        "mode": "expand_lowres_pixelshuffle",
        "source_config": source_config,
        "expanded_keys": sorted(set(expanded) - set(skipped)),
        "skipped_keys": skipped,
        "unexpected_keys": unexpected,
    }


def configure_trainable_scope(model: nn.Module, scope: str) -> dict[str, Any]:
    if scope == "all":
        for param in model.parameters():
            param.requires_grad = True
    else:
        prefixes_by_scope = {
            "adapter_only": ("sr.adapter.", "adapter."),
            "green_detail_only": ("green_detail.",),
            "adapter_and_green_detail": ("sr.adapter.", "adapter.", "green_detail."),
            "preclean_only": ("preclean.", "preclean_extra."),
            "adapter_and_preclean": ("sr.adapter.", "adapter.", "preclean.", "preclean_extra."),
        }
        prefixes = prefixes_by_scope.get(scope)
        if prefixes is None:
            raise ValueError(f"unknown trainable scope: {scope}")
        for name, param in model.named_parameters():
            param.requires_grad = name.startswith(prefixes)

    trainable_names = [name for name, param in model.named_parameters() if param.requires_grad]
    frozen_names = [name for name, param in model.named_parameters() if not param.requires_grad]
    trainable_parameter_count = sum(param.numel() for param in model.parameters() if param.requires_grad)
    frozen_parameter_count = sum(param.numel() for param in model.parameters() if not param.requires_grad)
    if trainable_parameter_count == 0:
        raise ValueError(f"trainable scope {scope} matched no parameters")
    return {
        "scope": scope,
        "trainable_parameter_count": int(trainable_parameter_count),
        "frozen_parameter_count": int(frozen_parameter_count),
        "trainable_names": trainable_names,
        "frozen_names": frozen_names,
    }


def rmse_counts(pred: torch.Tensor, target: torch.Tensor) -> float:
    return float(torch.sqrt(torch.mean((pred - target) ** 2)).detach().cpu() * RAW_SCALE)


def mae_counts(pred: torch.Tensor, target: torch.Tensor) -> float:
    return float(torch.mean(torch.abs(pred - target)).detach().cpu() * RAW_SCALE)


def plane_weight_tensor(weights: tuple[float, float, float, float], device: torch.device) -> torch.Tensor:
    return torch.tensor(weights, dtype=torch.float32, device=device).view(1, 4, 1, 1)


def weighted_mean(loss_map: torch.Tensor, weights: torch.Tensor | None) -> torch.Tensor:
    if weights is None:
        return torch.mean(loss_map)
    return torch.sum(loss_map * weights) / torch.sum(torch.ones_like(loss_map) * weights)


def robust_l1(
    pred: torch.Tensor,
    target: torch.Tensor,
    mode: str,
    weights: torch.Tensor | None = None,
) -> torch.Tensor:
    if mode == "l1":
        return weighted_mean(torch.abs(pred - target), weights)
    if mode == "charbonnier":
        eps = 1e-3
        return weighted_mean(torch.sqrt((pred - target) ** 2 + eps * eps), weights)
    raise ValueError(f"unknown loss mode: {mode}")


def laplacian(x: torch.Tensor) -> torch.Tensor:
    center = x[:, :, 1:-1, 1:-1] * -4.0
    return (
        center
        + x[:, :, :-2, 1:-1]
        + x[:, :, 2:, 1:-1]
        + x[:, :, 1:-1, :-2]
        + x[:, :, 1:-1, 2:]
    )


def binomial_detail(x: torch.Tensor) -> torch.Tensor:
    kernel = torch.tensor(
        [[1.0, 2.0, 1.0], [2.0, 4.0, 2.0], [1.0, 2.0, 1.0]],
        dtype=x.dtype,
        device=x.device,
    ).view(1, 1, 3, 3) / 16.0
    kernel = kernel.repeat(x.shape[1], 1, 1, 1)
    low = F.conv2d(F.pad(x, (1, 1, 1, 1), mode="reflect"), kernel, groups=x.shape[1])
    return x - low


def detail_phase_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    mode: str,
    weights: torch.Tensor | None = None,
    threshold_counts: float = 0.0,
) -> torch.Tensor:
    pred_detail = binomial_detail(pred)
    target_detail = binomial_detail(target)
    if mode == "l1":
        loss_map = torch.abs(pred_detail - target_detail)
    elif mode == "charbonnier":
        eps = 1e-3
        loss_map = torch.sqrt((pred_detail - target_detail) ** 2 + eps * eps)
    else:
        raise ValueError(f"unknown loss mode: {mode}")

    mask = torch.ones_like(loss_map)
    if threshold_counts > 0.0:
        mask = (torch.abs(target_detail) >= float(threshold_counts) / RAW_SCALE).to(loss_map.dtype)
    effective = mask if weights is None else mask * weights
    denom = torch.sum(effective).clamp_min(1.0)
    return torch.sum(loss_map * effective) / denom


def append_coord_channels(x: torch.Tensor, coords: torch.Tensor | None) -> torch.Tensor:
    if coords is None:
        return x
    return torch.cat([x, coords], dim=1)


def architecture_uses_coords(architecture: str) -> bool:
    return architecture in {
        "coord_preclean_adapter_pixelshuffle",
        "coord_deep_preclean_adapter_pixelshuffle",
        "coord_detail_preclean_adapter_pixelshuffle",
    }


def evaluate(model: nn.Module, dataset: Mission1SRPairs, max_tiles: int = 512, with_coords: bool = False) -> dict[str, Any]:
    model.eval()
    idx = dataset.eval_idx[:max_tiles]
    rows = []
    with torch.no_grad():
        for start in range(0, len(idx), 16):
            part = idx[start : start + 16]
            x = torch.from_numpy(dataset.inputs[part]).to(DEVICE)
            y = torch.from_numpy(dataset.targets[part]).to(DEVICE)
            coords = dataset.coord_channels_for_indices(part) if with_coords else None
            base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
            pred = model(append_coord_channels(x, coords))
            rows.append(
                {
                    "n": int(len(part)),
                    "baseline_rmse_counts": rmse_counts(base, y),
                    "model_rmse_counts": rmse_counts(pred, y),
                    "baseline_mae_counts": mae_counts(base, y),
                    "model_mae_counts": mae_counts(pred, y),
                }
            )
    model.train()
    total = sum(r["n"] for r in rows)

    def weighted(key: str) -> float:
        return float(sum(r[key] * r["n"] for r in rows) / total)

    return {
        "eval_tiles": int(total),
        "baseline_rmse_counts": weighted("baseline_rmse_counts"),
        "model_rmse_counts": weighted("model_rmse_counts"),
        "baseline_mae_counts": weighted("baseline_mae_counts"),
        "model_mae_counts": weighted("model_mae_counts"),
        "rmse_improvement_pct": float(
            100.0 * (weighted("baseline_rmse_counts") - weighted("model_rmse_counts")) / weighted("baseline_rmse_counts")
        ),
        "mae_improvement_pct": float(
            100.0 * (weighted("baseline_mae_counts") - weighted("model_mae_counts")) / weighted("baseline_mae_counts")
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout-image")
    ap.add_argument("--focus-image", help="comma-separated image ids to oversample during training")
    ap.add_argument("--focus-weight", type=float, default=1.0, help="per-tile sampling weight for --focus-image ids")
    ap.add_argument("--init-checkpoint", type=Path, help="initialize model weights from an existing checkpoint")
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument(
        "--architecture",
        choices=(
            "residual_highres",
            "lowres_pixelshuffle",
            "resblock_pixelshuffle",
            "edge_pixelshuffle",
            "adapter_pixelshuffle",
            "green_detail_adapter_pixelshuffle",
            "preclean_adapter_pixelshuffle",
            "coord_preclean_adapter_pixelshuffle",
            "coord_detail_preclean_adapter_pixelshuffle",
            "coord_deep_preclean_adapter_pixelshuffle",
        ),
        default="lowres_pixelshuffle",
    )
    ap.add_argument(
        "--init-nonstrict",
        action="store_true",
        help="allow partial checkpoint initialization for compatible architecture probes",
    )
    ap.add_argument(
        "--init-expand-lowres",
        action="store_true",
        help="expand a lowres_pixelshuffle checkpoint into a wider lowres_pixelshuffle model",
    )
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--residual-scale", type=float, default=0.1)
    ap.add_argument("--gradient-weight", type=float, default=0.2)
    ap.add_argument("--laplacian-weight", type=float, default=0.0)
    ap.add_argument(
        "--detail-phase-weight",
        type=float,
        default=0.0,
        help="same-color binomial-detail loss weight for phase-sensitive SR probes",
    )
    ap.add_argument(
        "--detail-phase-threshold",
        type=float,
        default=0.0,
        help="target-detail threshold in raw counts for --detail-phase-weight",
    )
    ap.add_argument(
        "--plane-weights",
        type=parse_plane_weights,
        default=(1.0, 1.0, 1.0, 1.0),
        help="comma-separated CFA plane loss weights in r,g1,g2,b order",
    )
    ap.add_argument(
        "--trainable-scope",
        choices=(
            "all",
            "adapter_only",
            "green_detail_only",
            "adapter_and_green_detail",
            "preclean_only",
            "adapter_and_preclean",
        ),
        default="all",
        help="freeze all parameters outside the selected correction branch",
    )
    ap.add_argument(
        "--low-clean-aux-weight",
        type=float,
        default=0.0,
        help="auxiliary low-res codec-cleanup loss for preclean_adapter_pixelshuffle",
    )
    ap.add_argument(
        "--low-clean-detail-aux-weight",
        type=float,
        default=0.0,
        help="auxiliary same-color low-res detail loss on the preclean branch",
    )
    ap.add_argument(
        "--low-clean-detail-threshold",
        type=float,
        default=0.0,
        help="target low-clean detail threshold in raw counts for --low-clean-detail-aux-weight",
    )
    ap.add_argument("--loss", choices=("l1", "charbonnier"), default="l1")
    ap.add_argument("--seed", type=int, default=20260616)
    ap.add_argument("--eval-every", type=int, default=200)
    ap.add_argument(
        "--save-eval-checkpoints-dir",
        type=Path,
        help="optional directory for saving the model state at every evaluation step",
    )
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.save_eval_checkpoints_dir:
        args.save_eval_checkpoints_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    dataset = Mission1SRPairs(
        args.pairs,
        args.holdout_image,
        args.focus_image,
        args.focus_weight,
        load_low_clean_targets=args.low_clean_aux_weight > 0.0,
    )
    model = make_model(
        args.architecture,
        width=args.width,
        depth=args.depth,
        residual_scale=args.residual_scale,
    ).to(DEVICE)
    with_coords = architecture_uses_coords(args.architecture)
    if args.init_checkpoint:
        init_result, init_details = initialize_model(
            model,
            args.init_checkpoint,
            architecture=args.architecture,
            width=args.width,
            depth=args.depth,
            residual_scale=args.residual_scale,
            init_nonstrict=args.init_nonstrict,
            init_expand_lowres=args.init_expand_lowres,
        )
    else:
        init_result = None
        init_details = {"mode": "fresh", "expanded_keys": []}
    trainable_details = configure_trainable_scope(model, args.trainable_scope)
    plane_weights = plane_weight_tensor(args.plane_weights, DEVICE)
    uniform_plane_weights = tuple(float(v) for v in args.plane_weights) == (1.0, 1.0, 1.0, 1.0)
    loss_plane_weights = None if uniform_plane_weights else plane_weights
    opt = torch.optim.AdamW(
        [param for param in model.parameters() if param.requires_grad],
        lr=args.lr,
        weight_decay=1e-4,
    )
    best_metric = float("inf")
    best_eval: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []
    eval_checkpoints: list[dict[str, Any]] = []
    t0 = time.time()

    for step in range(1, args.steps + 1):
        x, y, low_clean, coords = dataset.batch(args.batch, rng, with_coords=with_coords)
        model_input = append_coord_channels(x, coords)
        pred = model(model_input)
        loss_l1 = robust_l1(pred, y, args.loss, loss_plane_weights)
        loss_grad = robust_l1(
            pred[:, :, :, 1:] - pred[:, :, :, :-1],
            y[:, :, :, 1:] - y[:, :, :, :-1],
            args.loss,
            loss_plane_weights,
        )
        loss_grad = loss_grad + robust_l1(
            pred[:, :, 1:, :] - pred[:, :, :-1, :],
            y[:, :, 1:, :] - y[:, :, :-1, :],
            args.loss,
            loss_plane_weights,
        )
        loss = loss_l1 + args.gradient_weight * loss_grad
        if args.laplacian_weight > 0.0:
            loss_lap = robust_l1(laplacian(pred), laplacian(y), args.loss, loss_plane_weights)
            loss = loss + args.laplacian_weight * loss_lap
        loss_phase = None
        if args.detail_phase_weight > 0.0:
            loss_phase = detail_phase_loss(
                pred,
                y,
                args.loss,
                loss_plane_weights,
                threshold_counts=args.detail_phase_threshold,
            )
            loss = loss + args.detail_phase_weight * loss_phase
        loss_low_clean = None
        loss_low_clean_detail = None
        if args.low_clean_aux_weight > 0.0:
            if low_clean is None or not hasattr(model, "clean_low"):
                raise ValueError("--low-clean-aux-weight requires preclean_adapter_pixelshuffle")
            low_pred = model.clean_low(model_input)  # type: ignore[attr-defined]
            loss_low_clean = robust_l1(low_pred, low_clean, args.loss, loss_plane_weights)
            loss = loss + args.low_clean_aux_weight * loss_low_clean
            if args.low_clean_detail_aux_weight > 0.0:
                loss_low_clean_detail = detail_phase_loss(
                    low_pred,
                    low_clean,
                    args.loss,
                    loss_plane_weights,
                    threshold_counts=args.low_clean_detail_threshold,
                )
                loss = loss + args.low_clean_detail_aux_weight * loss_low_clean_detail
        elif args.low_clean_detail_aux_weight > 0.0:
            raise ValueError("--low-clean-detail-aux-weight requires --low-clean-aux-weight")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step == 1 or step % args.eval_every == 0 or step == args.steps:
            ev = evaluate(model, dataset, with_coords=with_coords)
            ev.update({
                "step": step,
                "loss": float(loss.detach().cpu()),
                "loss_phase": float(loss_phase.detach().cpu()) if loss_phase is not None else None,
                "loss_low_clean": float(loss_low_clean.detach().cpu()) if loss_low_clean is not None else None,
                "loss_low_clean_detail": (
                    float(loss_low_clean_detail.detach().cpu()) if loss_low_clean_detail is not None else None
                ),
            })
            history.append(ev)
            if args.save_eval_checkpoints_dir:
                eval_path = args.save_eval_checkpoints_dir / f"{args.out.stem}_step{step:06d}.pt"
                torch.save(
                    {
                        "model": model.state_dict(),
                        "config": {
                            "architecture": args.architecture,
                            "width": args.width,
                            "depth": args.depth,
                            "residual_scale": args.residual_scale,
                            "coordinate_channels": with_coords,
                        },
                    },
                    eval_path,
                )
                eval_checkpoints.append({
                    "step": step,
                    "checkpoint": str(eval_path),
                    "eval": ev,
                })
            if ev["model_rmse_counts"] < best_metric:
                best_metric = ev["model_rmse_counts"]
                best_eval = ev
                torch.save(
                    {
                        "model": model.state_dict(),
                        "config": {
                            "architecture": args.architecture,
                            "width": args.width,
                            "depth": args.depth,
                            "residual_scale": args.residual_scale,
                            "coordinate_channels": with_coords,
                        },
                    },
                    args.out,
                )
            print(
                f"step={step} loss={float(loss.detach().cpu()):.5f} "
                f"rmse={ev['model_rmse_counts']:.2f} "
                f"baseline={ev['baseline_rmse_counts']:.2f} "
                f"improve={ev['rmse_improvement_pct']:.2f}%",
                flush=True,
            )

    receipt = {
        "schema": "mission1_sr_train_receipt.v1",
        "pairs": str(args.pairs),
        "checkpoint": str(args.out),
        "init_checkpoint": str(args.init_checkpoint) if args.init_checkpoint else None,
        "init_nonstrict": bool(args.init_nonstrict),
        "init_expand_lowres": bool(args.init_expand_lowres),
        "init_mode": init_details.get("mode"),
        "init_details": init_details,
        "init_missing_keys": list(getattr(init_result, "missing_keys", [])) if init_result is not None else [],
        "init_unexpected_keys": list(getattr(init_result, "unexpected_keys", [])) if init_result is not None else [],
        "device": str(DEVICE),
        "train_tiles": int(len(dataset.train_idx)),
        "eval_tiles_total": int(len(dataset.eval_idx)),
        "holdout_image": args.holdout_image,
        "focus_image": args.focus_image,
        "focus_weight": args.focus_weight,
        "steps": args.steps,
        "batch": args.batch,
        "width": args.width,
        "depth": args.depth,
        "architecture": args.architecture,
        "coordinate_channels": with_coords,
        "residual_scale": args.residual_scale,
        "gradient_weight": args.gradient_weight,
        "laplacian_weight": args.laplacian_weight,
        "detail_phase_weight": args.detail_phase_weight,
        "detail_phase_threshold": args.detail_phase_threshold,
        "plane_weights": list(args.plane_weights),
        "trainable_scope": args.trainable_scope,
        "trainable_details": trainable_details,
        "low_clean_aux_weight": args.low_clean_aux_weight,
        "low_clean_detail_aux_weight": args.low_clean_detail_aux_weight,
        "low_clean_detail_threshold": args.low_clean_detail_threshold,
        "loss": args.loss,
        "elapsed_s": time.time() - t0,
        "best_eval": best_eval,
        "eval_checkpoints": eval_checkpoints,
        "history": history,
        "pair_meta": dataset.meta,
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({"checkpoint": str(args.out), "best_eval": best_eval}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
