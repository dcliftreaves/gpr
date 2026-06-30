#!/usr/bin/env python3
"""Train a no-REF HF residual predictor for premium still-SR review.

The target NPZ is built with source DNG high-frequency content, but this model
only sees candidate-render RGB plus deterministic runtime-safe features. It is
a promotion probe: a positive result proves the residual is learnable enough to
try in the full latitude/render gate, not that the still-SR path is production.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageDraw


SCHEMA = "gpr.premium_still_sr_hf_residual_model.v1"
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "max": float(arr.max()),
    }


def gradient_l1(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.l1_loss(pred[:, :, :, 1:] - pred[:, :, :, :-1], target[:, :, :, 1:] - target[:, :, :, :-1]) + F.l1_loss(
        pred[:, :, 1:, :] - pred[:, :, :-1, :],
        target[:, :, 1:, :] - target[:, :, :-1, :],
    )


def block_highpass(x: torch.Tensor, block: int) -> torch.Tensor:
    if block <= 1:
        return x - F.avg_pool2d(x, 3, stride=1, padding=1)
    pad = block // 2
    low = F.avg_pool2d(F.pad(x, (pad, pad, pad, pad), mode="reflect"), block, stride=1)
    return x - low[:, :, : x.shape[-2], : x.shape[-1]]


def coord_planes(batch: int, height: int, width: int, device: torch.device) -> torch.Tensor:
    yy = torch.linspace(-1.0, 1.0, height, device=device).view(1, 1, height, 1).expand(batch, 1, height, width)
    xx = torch.linspace(-1.0, 1.0, width, device=device).view(1, 1, 1, width).expand(batch, 1, height, width)
    return torch.cat([xx, yy], dim=1)


def ev_plane(ev: torch.Tensor | None, batch: int, height: int, width: int, device: torch.device) -> torch.Tensor:
    if ev is None:
        ev = torch.zeros((batch,), dtype=torch.float32, device=device)
    ev = ev.to(device=device, dtype=torch.float32).view(batch, 1, 1, 1).clamp(-4.0, 4.0) / 2.0
    return ev.expand(batch, 1, height, width)


def scalar_planes(values: torch.Tensor | None, batch: int, height: int, width: int, device: torch.device, channels: int) -> torch.Tensor:
    if values is None:
        values = torch.zeros((batch, channels), dtype=torch.float32, device=device)
    values = values.to(device=device, dtype=torch.float32)
    if values.ndim == 1:
        values = values.view(batch, 1)
    if values.shape[1] != channels:
        raise ValueError(f"expected {channels} scalar channels, got {values.shape[1]}")
    return values.view(batch, channels, 1, 1).expand(batch, channels, height, width)


def luma_plane(x: torch.Tensor) -> torch.Tensor:
    return x[:, 0:1] * 0.2126 + x[:, 1:2] * 0.7152 + x[:, 2:3] * 0.0722


def brightness_planes(luma: torch.Tensor) -> torch.Tensor:
    shadow = (luma < 0.10).to(luma.dtype)
    midtone = ((luma >= 0.10) & (luma < 0.75)).to(luma.dtype)
    bright = ((luma >= 0.75) & (luma < 0.92)).to(luma.dtype)
    near_clip = (luma >= 0.92).to(luma.dtype)
    return torch.cat([shadow, midtone, bright, near_clip], dim=1)


def make_features(
    x: torch.Tensor,
    feature_mode: str,
    block: int,
    ev: torch.Tensor | None = None,
    noise: torch.Tensor | None = None,
    raw_cfa: torch.Tensor | None = None,
) -> torch.Tensor:
    if feature_mode == "rgb":
        return x
    if feature_mode == "rgb_hf":
        return torch.cat([x, block_highpass(x, block)], dim=1)
    if feature_mode == "rgb_hf_coord":
        return torch.cat([x, block_highpass(x, block), coord_planes(x.shape[0], x.shape[-2], x.shape[-1], x.device)], dim=1)
    if feature_mode == "rgb_hf_luma_ev_bright":
        luma = luma_plane(x)
        return torch.cat(
            [
                x,
                block_highpass(x, block),
                luma,
                ev_plane(ev, x.shape[0], x.shape[-2], x.shape[-1], x.device),
                brightness_planes(luma),
            ],
            dim=1,
        )
    if feature_mode == "rgb_hf_coord_luma_ev_noise_bright":
        luma = luma_plane(x)
        return torch.cat(
            [
                x,
                block_highpass(x, block),
                coord_planes(x.shape[0], x.shape[-2], x.shape[-1], x.device),
                luma,
                ev_plane(ev, x.shape[0], x.shape[-2], x.shape[-1], x.device),
                scalar_planes(noise, x.shape[0], x.shape[-2], x.shape[-1], x.device, 4),
                brightness_planes(luma),
            ],
            dim=1,
        )
    if feature_mode == "rgb_multiscale_coord_luma_ev_noise_bright":
        luma = luma_plane(x)
        coarse_block = max(block * 4, block + 2)
        return torch.cat(
            [
                x,
                block_highpass(x, block),
                block_highpass(x, coarse_block),
                coord_planes(x.shape[0], x.shape[-2], x.shape[-1], x.device),
                luma,
                ev_plane(ev, x.shape[0], x.shape[-2], x.shape[-1], x.device),
                scalar_planes(noise, x.shape[0], x.shape[-2], x.shape[-1], x.device, 4),
                brightness_planes(luma),
            ],
            dim=1,
        )
    if feature_mode == "rgb_multiscale_rawcfa_coord_luma_ev_noise_bright":
        if raw_cfa is None:
            raise ValueError("feature mode rgb_multiscale_rawcfa_coord_luma_ev_noise_bright requires candidate_raw_cfa4")
        luma = luma_plane(x)
        coarse_block = max(block * 4, block + 2)
        return torch.cat(
            [
                x,
                block_highpass(x, block),
                block_highpass(x, coarse_block),
                raw_cfa,
                block_highpass(raw_cfa, block),
                coord_planes(x.shape[0], x.shape[-2], x.shape[-1], x.device),
                luma,
                ev_plane(ev, x.shape[0], x.shape[-2], x.shape[-1], x.device),
                scalar_planes(noise, x.shape[0], x.shape[-2], x.shape[-1], x.device, 4),
                brightness_planes(luma),
            ],
            dim=1,
        )
    if feature_mode == "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright":
        if raw_cfa is None:
            raise ValueError("feature mode rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright requires candidate_raw_cfa4")
        luma = luma_plane(x)
        coarse_block = max(block * 4, block + 2)
        raw_mean = torch.mean(raw_cfa, dim=1, keepdim=True)
        raw_phase_contrast = raw_cfa - raw_mean
        return torch.cat(
            [
                x,
                block_highpass(x, block),
                block_highpass(x, coarse_block),
                coord_planes(x.shape[0], x.shape[-2], x.shape[-1], x.device),
                luma,
                ev_plane(ev, x.shape[0], x.shape[-2], x.shape[-1], x.device),
                scalar_planes(noise, x.shape[0], x.shape[-2], x.shape[-1], x.device, 4),
                brightness_planes(luma),
                raw_cfa,
                block_highpass(raw_cfa, block),
                block_highpass(raw_cfa, coarse_block),
                raw_phase_contrast,
            ],
            dim=1,
        )
    raise ValueError(f"unknown feature mode: {feature_mode}")


def feature_channels(feature_mode: str) -> int:
    return {
        "rgb": 3,
        "rgb_hf": 6,
        "rgb_hf_coord": 8,
        "rgb_hf_luma_ev_bright": 12,
        "rgb_hf_coord_luma_ev_noise_bright": 18,
        "rgb_multiscale_coord_luma_ev_noise_bright": 21,
        "rgb_multiscale_rawcfa_coord_luma_ev_noise_bright": 29,
        "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright": 37,
    }[feature_mode]


def uses_noise_sidecar_features(feature_mode: str) -> bool:
    return feature_mode in {
        "rgb_hf_coord_luma_ev_noise_bright",
        "rgb_multiscale_coord_luma_ev_noise_bright",
        "rgb_multiscale_rawcfa_coord_luma_ev_noise_bright",
        "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright",
    }


def uses_raw_cfa_features(feature_mode: str) -> bool:
    return feature_mode in {
        "rgb_multiscale_rawcfa_coord_luma_ev_noise_bright",
        "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright",
    }


def raw_cfa_guided_feature_split(feature_mode: str) -> tuple[int, int] | None:
    if feature_mode == "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright":
        return (21, 16)
    return None


def load_noise_feature_from_sidecar(path: str | Path) -> tuple[float, float, float, float]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (0.0, 0.0, 0.0, 0.0)
    camera = payload.get("camera", {}) if isinstance(payload, dict) else {}
    white = float(camera.get("white_level", 65535.0) or 65535.0)
    black = float(camera.get("black_level", 0.0) or 0.0)
    scale = max(white - black, 1.0)
    calibrations = payload.get("calibrations", []) if isinstance(payload, dict) else []
    cal = calibrations[0] if calibrations and isinstance(calibrations[0], dict) else {}
    per_plane = cal.get("per_plane", {}) if isinstance(cal, dict) else {}
    plane_values = [v for v in per_plane.values() if isinstance(v, dict)]

    def mean_key(key: str) -> float:
        vals = [float(v.get(key, 0.0) or 0.0) for v in plane_values]
        return float(sum(vals) / len(vals)) if vals else 0.0

    iso = float(cal.get("iso", 0.0) or 0.0)
    sigma_norm = mean_key("sigma_black") / scale
    p95_norm = mean_key("temporal_noise_p95_counts") / scale
    fpn_norm = mean_key("spatial_fpn_rms_counts") / scale
    iso_norm = np.log2(max(iso, 1.0) / 100.0) / 8.0
    return (
        float(np.clip(iso_norm, -1.0, 1.0)),
        float(np.clip(sigma_norm * 64.0, 0.0, 1.0)),
        float(np.clip(p95_norm * 32.0, 0.0, 1.0)),
        float(np.clip(fpn_norm * 256.0, 0.0, 1.0)),
    )


def residual_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    x: torch.Tensor,
    *,
    target_abs_weight: float,
    bright_weight: float,
    near_clip_weight: float,
) -> torch.Tensor:
    weight = torch.ones_like(target[:, 0:1])
    if target_abs_weight > 0.0:
        target_abs = torch.mean(torch.abs(target), dim=1, keepdim=True)
        weight = weight + float(target_abs_weight) * torch.clamp(target_abs / 0.08, 0.0, 4.0)
    if bright_weight > 0.0 or near_clip_weight > 0.0:
        y = luma_plane(x)
        if bright_weight > 0.0:
            weight = weight + float(bright_weight) * ((y >= 0.75) & (y < 0.92)).to(weight.dtype)
        if near_clip_weight > 0.0:
            weight = weight + float(near_clip_weight) * (y >= 0.92).to(weight.dtype)
    weight = weight / torch.mean(weight).clamp_min(1.0e-6)
    return torch.mean(torch.abs(pred - target) * weight)


class HfResidualNet(nn.Module):
    def __init__(self, in_channels: int, width: int = 32, depth: int = 5, residual_scale: float = 0.20) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        layers: list[nn.Module] = [nn.Conv2d(in_channels, width, 3, padding=1), nn.GELU()]
        for _ in range(max(0, depth - 2)):
            layers += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        tail = nn.Conv2d(width, 3, 3, padding=1)
        nn.init.zeros_(tail.weight)
        nn.init.zeros_(tail.bias)
        layers.append(tail)
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.net(x)) * self.residual_scale


class HfResidualRawCfaGatedNet(nn.Module):
    """Residual predictor with an explicit raw-CFA guide branch.

    The first raw-CFA pass concatenated raw planes with rendered RGB features.
    This version keeps RGB/render metadata as the primary signal, but lets
    phase-aware raw detail gate and bias the hidden features before the shared
    residual trunk. It is still runtime-safe: all inputs come from candidate
    render/raw data and deterministic metadata.
    """

    def __init__(
        self,
        rgb_channels: int,
        raw_channels: int,
        width: int = 32,
        depth: int = 5,
        residual_scale: float = 0.20,
    ) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.rgb_head = nn.Sequential(nn.Conv2d(rgb_channels, width, 3, padding=1), nn.GELU())
        self.raw_head = nn.Sequential(
            nn.Conv2d(raw_channels, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
        )
        self.raw_gate = nn.Conv2d(width, width, 1)
        self.raw_bias = nn.Conv2d(width, width, 1)
        trunk: list[nn.Module] = []
        for _ in range(max(0, depth - 2)):
            trunk += [nn.Conv2d(width, width, 3, padding=1), nn.GELU()]
        tail = nn.Conv2d(width, 3, 3, padding=1)
        nn.init.zeros_(tail.weight)
        nn.init.zeros_(tail.bias)
        trunk.append(tail)
        self.trunk = nn.Sequential(*trunk)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        rgb_channels = self.rgb_head[0].in_channels
        rgb = x[:, :rgb_channels]
        raw = x[:, rgb_channels:]
        rgb_hidden = self.rgb_head(rgb)
        raw_hidden = self.raw_head(raw)
        gate = 0.5 + 1.5 * torch.sigmoid(self.raw_gate(raw_hidden))
        hidden = rgb_hidden * gate + self.raw_bias(raw_hidden)
        return torch.tanh(self.trunk(hidden)) * self.residual_scale


def build_model(
    *,
    model_arch: str,
    feature_mode: str,
    width: int,
    depth: int,
    residual_scale: float,
) -> nn.Module:
    if model_arch == "plain":
        return HfResidualNet(
            in_channels=feature_channels(feature_mode),
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    if model_arch == "raw_cfa_gated":
        split = raw_cfa_guided_feature_split(feature_mode)
        if split is None:
            raise ValueError(f"model_arch raw_cfa_gated requires a phase raw-CFA feature mode, got {feature_mode}")
        rgb_channels, raw_channels = split
        return HfResidualRawCfaGatedNet(
            rgb_channels=rgb_channels,
            raw_channels=raw_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    raise ValueError(f"unknown model architecture: {model_arch}")


class HfResidualTargets:
    def __init__(self, path: Path) -> None:
        with np.load(path, allow_pickle=False) as z:
            self.inputs = z["inputs"].astype(np.float32)
            self.targets = z["hf_residuals"].astype(np.float32)
            self.source_hf_targets = z["source_hf_targets"].astype(np.float32)
            self.raw_cfa = z["candidate_raw_cfa4"].astype(np.float32) if "candidate_raw_cfa4" in z.files else None
            self.rows = json.loads(str(z["meta"]))
        if self.inputs.shape != self.targets.shape:
            raise ValueError(f"input/target shape mismatch: {self.inputs.shape} vs {self.targets.shape}")
        if self.inputs.ndim != 4 or self.inputs.shape[-1] != 3:
            raise ValueError(f"expected NHWC RGB arrays, got {self.inputs.shape}")
        if self.raw_cfa is not None and self.raw_cfa.shape[:3] != self.inputs.shape[:3]:
            raise ValueError(f"raw CFA feature shape {self.raw_cfa.shape} does not match inputs {self.inputs.shape}")
        cache: dict[str, tuple[float, float, float, float]] = {}
        self.noise_features: list[tuple[float, float, float, float]] = []
        for row in self.rows:
            sidecars = row.get("noise_sidecars", [])
            sidecar = str(sidecars[0]) if isinstance(sidecars, list) and sidecars else ""
            if sidecar and sidecar not in cache:
                cache[sidecar] = load_noise_feature_from_sidecar(sidecar)
            self.noise_features.append(cache.get(sidecar, (0.0, 0.0, 0.0, 0.0)))

    def row_indices(
        self,
        holdout_ev: float | None,
        holdout_crop: str | None = None,
        holdout_scene: str | None = None,
    ) -> tuple[list[int], list[int]]:
        if holdout_scene:
            holdout = [i for i, row in enumerate(self.rows) if str(row.get("scene_id", "")) == holdout_scene]
            train = [i for i in range(len(self.rows)) if i not in holdout]
            if not train or not holdout:
                raise ValueError(f"holdout scene {holdout_scene} produced train={len(train)} holdout={len(holdout)}")
            return train, holdout
        if holdout_crop:
            holdout = [i for i, row in enumerate(self.rows) if str(row.get("crop", "")) == holdout_crop]
            train = [i for i in range(len(self.rows)) if i not in holdout]
            if not train or not holdout:
                raise ValueError(f"holdout crop {holdout_crop} produced train={len(train)} holdout={len(holdout)}")
            return train, holdout
        if holdout_ev is None:
            return list(range(len(self.rows))), []
        holdout = [i for i, row in enumerate(self.rows) if abs(float(row.get("ev", 0.0)) - holdout_ev) < 1.0e-6]
        train = [i for i in range(len(self.rows)) if i not in holdout]
        if not train or not holdout:
            raise ValueError(f"holdout EV {holdout_ev} produced train={len(train)} holdout={len(holdout)}")
        return train, holdout

    def sample_batch(
        self,
        indices: list[int],
        batch_size: int,
        patch_size: int,
        rng: random.Random,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor | None]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        raws: list[np.ndarray] = []
        evs: list[float] = []
        noises: list[tuple[float, float, float, float]] = []
        h, w = self.inputs.shape[1:3]
        patch = min(patch_size, h, w)
        for _ in range(batch_size):
            idx = rng.choice(indices)
            y0 = rng.randrange(0, h - patch + 1) if h > patch else 0
            x0 = rng.randrange(0, w - patch + 1) if w > patch else 0
            xs.append(self.inputs[idx, y0 : y0 + patch, x0 : x0 + patch].transpose(2, 0, 1))
            ys.append(self.targets[idx, y0 : y0 + patch, x0 : x0 + patch].transpose(2, 0, 1))
            if self.raw_cfa is not None:
                raws.append(self.raw_cfa[idx, y0 : y0 + patch, x0 : x0 + patch].transpose(2, 0, 1))
            evs.append(float(self.rows[idx].get("ev", 0.0)))
            noises.append(self.noise_features[idx])
        return (
            torch.from_numpy(np.stack(xs)),
            torch.from_numpy(np.stack(ys)),
            torch.tensor(evs, dtype=torch.float32),
            torch.tensor(noises, dtype=torch.float32),
            torch.from_numpy(np.stack(raws)) if raws else None,
        )


@torch.no_grad()
def eval_rows(
    model: HfResidualNet,
    data: HfResidualTargets,
    indices: list[int],
    *,
    feature_mode: str,
    feature_block: int,
    device: torch.device,
    tile: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    model.eval()
    for idx in indices:
        cand = torch.from_numpy(data.inputs[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        target = torch.from_numpy(data.targets[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        raw_cfa_full = (
            torch.from_numpy(data.raw_cfa[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            if data.raw_cfa is not None
            else None
        )
        ev = torch.tensor([float(data.rows[idx].get("ev", 0.0))], dtype=torch.float32, device=device)
        noise = torch.tensor([data.noise_features[idx]], dtype=torch.float32, device=device)
        pred = torch.zeros_like(target)
        _, _, height, width = cand.shape
        for y0 in range(0, height, tile):
            for x0 in range(0, width, tile):
                cand_tile = cand[:, :, y0 : y0 + tile, x0 : x0 + tile]
                raw_tile = raw_cfa_full[:, :, y0 : y0 + tile, x0 : x0 + tile] if raw_cfa_full is not None else None
                pred[:, :, y0 : y0 + tile, x0 : x0 + tile] = model(
                    make_features(cand_tile, feature_mode, feature_block, ev, noise, raw_tile)
                )
        base_err = target
        pred_err = pred - target
        base_mae = float(torch.mean(torch.abs(base_err)).cpu())
        pred_mae = float(torch.mean(torch.abs(pred_err)).cpu())
        base_rmse = float(torch.sqrt(torch.mean(base_err * base_err)).cpu())
        pred_rmse = float(torch.sqrt(torch.mean(pred_err * pred_err)).cpu())
        cand_out = cand + pred
        target_out = cand + target
        out_mae = float(torch.mean(torch.abs(cand_out - target_out)).cpu())
        row_meta = dict(data.rows[idx])
        row_meta.update(
            {
                "index": idx,
                "baseline_residual_mae": base_mae,
                "model_residual_mae": pred_mae,
                "baseline_residual_rmse": base_rmse,
                "model_residual_rmse": pred_rmse,
                "output_mae_to_oracle_hf": out_mae,
                "residual_mae_reduction_pct": 100.0 * (base_mae - pred_mae) / max(base_mae, 1.0e-12),
                "residual_rmse_reduction_pct": 100.0 * (base_rmse - pred_rmse) / max(base_rmse, 1.0e-12),
            }
        )
        rows.append(row_meta)
    return {
        "row_count": len(rows),
        "baseline_residual_mae": stats([row["baseline_residual_mae"] for row in rows]),
        "model_residual_mae": stats([row["model_residual_mae"] for row in rows]),
        "residual_mae_reduction_pct": stats([row["residual_mae_reduction_pct"] for row in rows]),
        "baseline_residual_rmse": stats([row["baseline_residual_rmse"] for row in rows]),
        "model_residual_rmse": stats([row["model_residual_rmse"] for row in rows]),
        "residual_rmse_reduction_pct": stats([row["residual_rmse_reduction_pct"] for row in rows]),
        "rows": rows,
    }


@torch.no_grad()
def write_panel_sheet(
    path: Path,
    model: HfResidualNet,
    data: HfResidualTargets,
    indices: list[int],
    *,
    feature_mode: str,
    feature_block: int,
    device: torch.device,
    residual_scale: float,
    max_rows: int,
) -> None:
    selected = indices[:max_rows]
    if not selected:
        return
    crop_h, crop_w = data.inputs.shape[1:3]
    preview_w = min(384, crop_w)
    preview_h = min(384, crop_h)
    pad = 10
    label_h = 40
    cols = 4
    sheet = Image.new("RGB", (cols * (preview_w + pad) + pad, len(selected) * (preview_h + label_h + pad) + pad), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["candidate", "target residual", "pred residual", "abs error"]
    model.eval()
    for row_i, idx in enumerate(selected):
        cand = torch.from_numpy(data.inputs[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        raw_cfa = (
            torch.from_numpy(data.raw_cfa[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            if data.raw_cfa is not None
            else None
        )
        ev = torch.tensor([float(data.rows[idx].get("ev", 0.0))], dtype=torch.float32, device=device)
        noise = torch.tensor([data.noise_features[idx]], dtype=torch.float32, device=device)
        pred = model(make_features(cand, feature_mode, feature_block, ev, noise, raw_cfa)).squeeze(0).cpu().numpy().transpose(1, 2, 0)
        target = data.targets[idx]
        err = np.abs(pred - target)
        panels = [
            np.clip(data.inputs[idx], 0.0, 1.0),
            np.clip(target / residual_scale * 0.5 + 0.5, 0.0, 1.0),
            np.clip(pred / residual_scale * 0.5 + 0.5, 0.0, 1.0),
            np.clip(err / residual_scale, 0.0, 1.0),
        ]
        y0 = pad + row_i * (preview_h + label_h + pad)
        row = data.rows[idx]
        draw.text((pad, y0), f"{row.get('crop')} EV {float(row.get('ev', 0.0)):+.0f}", fill=(245, 245, 245))
        for col, panel in enumerate(panels):
            x0 = pad + col * (preview_w + pad)
            draw.text((x0, y0 + 20), headers[col], fill=(190, 190, 190))
            img = Image.fromarray((panel * 255.0 + 0.5).astype(np.uint8), "RGB").resize((preview_w, preview_h), Image.Resampling.BILINEAR)
            sheet.paste(img, (x0, y0 + label_h))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def render_html(receipt: dict[str, Any], output_dir: Path) -> str:
    train = receipt["eval"]["train"]
    holdout = receipt["eval"].get("holdout")
    panel = Path(receipt["artifacts"]["panel_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    rows = sorted(train["rows"] + (holdout["rows"] if holdout else []), key=lambda row: row["model_residual_mae"], reverse=True)
    table = []
    for row in rows:
        table.append(
            f"<tr><td>{html.escape(str(row.get('crop')))}</td><td>{float(row.get('ev', 0.0)):+.0f}</td>"
            f"<td>{row['baseline_residual_mae']:.5f}</td><td>{row['model_residual_mae']:.5f}</td>"
            f"<td>{row['residual_mae_reduction_pct']:.2f}%</td><td>{row['model_residual_rmse']:.5f}</td></tr>"
        )
    holdout_text = ""
    if holdout:
        holdout_text = (
            f"<div class='card'><h2>Holdout MAE Reduction</h2>"
            f"<p>{holdout['residual_mae_reduction_pct']['median']:.2f}% median</p></div>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR HF Residual Model</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left}}
code{{color:#b7d7ff}}img{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR HF Residual Model</h1>
<p><b>Policy:</b> trained from source-derived HF residual targets, but inference inputs are candidate-derived features and deterministic render metadata only.</p>
<p>Checkpoint: <code>{html.escape(receipt['checkpoint'])}</code></p>
<div class="grid">
<div class="card"><h2>Train Rows</h2><p>{train['row_count']}</p></div>
<div class="card"><h2>Train MAE Reduction</h2><p>{train['residual_mae_reduction_pct']['median']:.2f}% median</p></div>
{holdout_text}
<div class="card"><h2>Runtime Safety</h2><p>{html.escape(receipt['policy']['runtime_inputs'])}</p></div>
</div>
<img src="{html.escape(panel)}">
<table><tr><th>crop</th><th>EV</th><th>baseline residual MAE</th><th>model residual MAE</th><th>MAE reduction</th><th>model RMSE</th></tr>
{''.join(table)}
</table></body></html>
"""


def train(args: argparse.Namespace) -> dict[str, Any]:
    data = HfResidualTargets(args.targets)
    if uses_raw_cfa_features(args.feature_mode) and data.raw_cfa is None:
        raise ValueError(f"{args.feature_mode} requires targets built with --include-raw-cfa-features")
    if args.model_arch == "raw_cfa_gated" and raw_cfa_guided_feature_split(args.feature_mode) is None:
        raise ValueError(f"model_arch raw_cfa_gated requires a phase raw-CFA feature mode, got {args.feature_mode}")
    train_indices, holdout_indices = data.row_indices(args.holdout_ev, args.holdout_crop, args.holdout_scene)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    model = build_model(
        model_arch=args.model_arch,
        feature_mode=args.feature_mode,
        width=args.width,
        depth=args.depth,
        residual_scale=args.residual_scale,
    ).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        x, y, ev, noise, raw_cfa = data.sample_batch(train_indices, args.batch_size, args.patch_size, rng)
        x = x.to(DEVICE)
        y = y.to(DEVICE)
        ev = ev.to(DEVICE)
        noise = noise.to(DEVICE)
        raw_cfa = raw_cfa.to(DEVICE) if raw_cfa is not None else None
        pred = model(make_features(x, args.feature_mode, args.feature_block, ev, noise, raw_cfa))
        loss = residual_loss(
            pred,
            y,
            x,
            target_abs_weight=args.target_abs_weight,
            bright_weight=args.bright_weight,
            near_clip_weight=args.near_clip_weight,
        ) + args.grad_weight * gradient_l1(pred, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step == 1 or step == args.steps or (args.eval_every > 0 and step % args.eval_every == 0):
            history.append({"step": step, "loss": float(loss.detach().cpu())})
    train_s = time.perf_counter() - t0
    train_eval = eval_rows(
        model,
        data,
        train_indices,
        feature_mode=args.feature_mode,
        feature_block=args.feature_block,
        device=DEVICE,
        tile=args.eval_tile,
    )
    holdout_eval = None
    if holdout_indices:
        holdout_eval = eval_rows(
            model,
            data,
            holdout_indices,
            feature_mode=args.feature_mode,
            feature_block=args.feature_block,
            device=DEVICE,
            tile=args.eval_tile,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / args.checkpoint_name
    torch.save(
        {
            "schema": SCHEMA,
            "state_dict": model.state_dict(),
            "config": {
                "model_arch": args.model_arch,
                "feature_mode": args.feature_mode,
                "feature_block": args.feature_block,
                "width": args.width,
                "depth": args.depth,
                "residual_scale": args.residual_scale,
                "target_abs_weight": args.target_abs_weight,
                "bright_weight": args.bright_weight,
                "near_clip_weight": args.near_clip_weight,
                "uses_noise_sidecar_features": uses_noise_sidecar_features(args.feature_mode),
                "uses_raw_cfa_features": uses_raw_cfa_features(args.feature_mode),
            },
        },
        checkpoint,
    )
    panel = args.output_dir / "panel_sheet.jpg"
    write_panel_sheet(
        panel,
        model,
        data,
        train_indices + holdout_indices,
        feature_mode=args.feature_mode,
        feature_block=args.feature_block,
        device=DEVICE,
        residual_scale=args.residual_scale,
        max_rows=args.panel_rows,
    )
    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "targets": str(args.targets),
        "targets_sha256": sha256_file(args.targets),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "device": str(DEVICE),
        "train_seconds": train_s,
        "steps": args.steps,
        "config": {
            "model_arch": args.model_arch,
            "feature_mode": args.feature_mode,
            "feature_block": args.feature_block,
            "width": args.width,
            "depth": args.depth,
            "residual_scale": args.residual_scale,
            "patch_size": args.patch_size,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "grad_weight": args.grad_weight,
            "target_abs_weight": args.target_abs_weight,
            "bright_weight": args.bright_weight,
            "near_clip_weight": args.near_clip_weight,
            "uses_noise_sidecar_features": uses_noise_sidecar_features(args.feature_mode),
            "uses_raw_cfa_features": uses_raw_cfa_features(args.feature_mode),
            "holdout_ev": args.holdout_ev,
            "holdout_crop": args.holdout_crop,
            "holdout_scene": args.holdout_scene,
            "seed": args.seed,
        },
        "policy": {
            "uses_source_hf_at_training": True,
            "uses_source_hf_at_runtime": False,
            "runtime_inputs": (
                "candidate_render_rgb + candidate_highpass/multiscale_highpass + candidate_raw_cfa4 when selected "
                "+ deterministic coordinates + candidate_luma/brightness_buckets + deterministic_render_ev + camera/ISO noise sidecar scalars when selected"
            ),
            "production_status": "smoke_training_probe_not_registered_production_algorithm",
        },
        "history": history,
        "eval": {"train": train_eval, "holdout": holdout_eval},
        "artifacts": {"panel_sheet": str(panel)},
    }
    receipt_path = args.output_dir / "train_receipt.json"
    index = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    index.write_text(render_html(receipt, args.output_dir), encoding="utf-8")
    receipt["artifacts"]["receipt"] = str(receipt_path)
    receipt["artifacts"]["dashboard"] = str(index)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--checkpoint-name", default="premium_still_sr_hf_residual.pt")
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--patch-size", type=int, default=128)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument("--residual-scale", type=float, default=0.20)
    ap.add_argument(
        "--model-arch",
        choices=("plain", "raw_cfa_gated"),
        default="plain",
        help="Model architecture. raw_cfa_gated requires the phase raw-CFA feature mode.",
    )
    ap.add_argument(
        "--feature-mode",
        choices=(
            "rgb",
            "rgb_hf",
            "rgb_hf_coord",
            "rgb_hf_luma_ev_bright",
            "rgb_hf_coord_luma_ev_noise_bright",
            "rgb_multiscale_coord_luma_ev_noise_bright",
            "rgb_multiscale_rawcfa_coord_luma_ev_noise_bright",
            "rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright",
        ),
        default="rgb_hf_coord",
    )
    ap.add_argument("--feature-block", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1.0e-3)
    ap.add_argument("--weight-decay", type=float, default=1.0e-4)
    ap.add_argument("--grad-weight", type=float, default=0.15)
    ap.add_argument("--target-abs-weight", type=float, default=0.0)
    ap.add_argument("--bright-weight", type=float, default=0.0)
    ap.add_argument("--near-clip-weight", type=float, default=0.0)
    ap.add_argument("--holdout-ev", type=float, default=2.0)
    ap.add_argument("--holdout-crop")
    ap.add_argument("--holdout-scene")
    ap.add_argument("--eval-every", type=int, default=50)
    ap.add_argument("--eval-tile", type=int, default=384)
    ap.add_argument("--panel-rows", type=int, default=9)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()
    receipt = train(args)
    holdout = receipt["eval"].get("holdout")
    print(
        json.dumps(
            {
                "receipt": receipt["artifacts"]["receipt"],
                "dashboard": receipt["artifacts"]["dashboard"],
                "checkpoint": receipt["checkpoint"],
                "checkpoint_sha256": receipt["checkpoint_sha256"],
                "train_median_mae_reduction_pct": receipt["eval"]["train"]["residual_mae_reduction_pct"]["median"],
                "holdout_median_mae_reduction_pct": None if holdout is None else holdout["residual_mae_reduction_pct"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
