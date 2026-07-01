#!/usr/bin/env python3
"""Train a raw-CFA residual predictor for premium still-SR.

This is the raw-domain sibling of the rendered HF residual probe. The training
target is source-minus-candidate same-color raw high-frequency residuals. At
runtime the model only uses candidate raw CFA planes plus deterministic metadata
features, so it is a candidate for editable RAW restoration instead of a
rendered-space review-only model.
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


SCHEMA = "gpr.premium_still_sr_raw_cfa_residual_model.v1"
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


def block_highpass(x: torch.Tensor, block: int) -> torch.Tensor:
    block = max(3, int(block))
    if block % 2 == 0:
        block += 1
    pad = block // 2
    mode = "reflect" if x.shape[-1] > pad and x.shape[-2] > pad else "replicate"
    low = F.avg_pool2d(F.pad(x, (pad, pad, pad, pad), mode=mode), block, stride=1)
    return x - low


def coord_planes(batch: int, height: int, width: int, device: torch.device) -> torch.Tensor:
    yy = torch.linspace(-1.0, 1.0, height, device=device).view(1, 1, height, 1).expand(batch, 1, height, width)
    xx = torch.linspace(-1.0, 1.0, width, device=device).view(1, 1, 1, width).expand(batch, 1, height, width)
    return torch.cat([xx, yy], dim=1)


def ev_plane(ev: torch.Tensor | None, batch: int, height: int, width: int, device: torch.device) -> torch.Tensor:
    if ev is None:
        ev = torch.zeros((batch,), dtype=torch.float32, device=device)
    ev = ev.to(device=device, dtype=torch.float32).view(batch, 1, 1, 1).clamp(-4.0, 4.0) / 2.0
    return ev.expand(batch, 1, height, width)


def scalar_planes(
    values: torch.Tensor | None,
    batch: int,
    height: int,
    width: int,
    device: torch.device,
    channels: int,
) -> torch.Tensor:
    if values is None:
        values = torch.zeros((batch, channels), dtype=torch.float32, device=device)
    values = values.to(device=device, dtype=torch.float32)
    if values.ndim == 1:
        values = values.view(batch, 1)
    if values.shape[1] != channels:
        raise ValueError(f"expected {channels} scalar channels, got {values.shape[1]}")
    return values.view(batch, channels, 1, 1).expand(batch, channels, height, width)


def apply_context_mask(
    raw: torch.Tensor,
    stored_hf: torch.Tensor | None,
    *,
    mask_prob: float,
    mask_block: int,
) -> tuple[torch.Tensor, torch.Tensor | None]:
    """Hide local candidate detail during training while preserving runtime inputs.

    This is a training-only contextual reconstruction objective. The model
    still receives normal candidate-derived inputs at evaluation/runtime, but
    the training batch is sometimes forced to infer residual structure from
    surrounding context instead of copying local candidate statistics.
    """

    prob = float(mask_prob)
    if prob <= 0.0:
        return raw, stored_hf
    prob = min(prob, 0.95)
    block = max(2, int(mask_block))
    batch, _, height, width = raw.shape
    grid_h = max(1, (height + block - 1) // block)
    grid_w = max(1, (width + block - 1) // block)
    mask = (torch.rand((batch, 1, grid_h, grid_w), device=raw.device) < prob).to(raw.dtype)
    mask = F.interpolate(mask, size=(height, width), mode="nearest")
    raw_fill = torch.mean(raw, dim=(-2, -1), keepdim=True)
    masked_raw = raw * (1.0 - mask) + raw_fill * mask
    masked_hf = None
    if stored_hf is not None:
        hf_fill = torch.zeros_like(stored_hf[:, :, :1, :1])
        masked_hf = stored_hf * (1.0 - mask) + hf_fill * mask
    return masked_raw, masked_hf


def frame_context_channels() -> int:
    return 19


def camera_onehot(camera: str) -> tuple[float, float, float]:
    return (
        1.0 if camera == "x2d" else 0.0,
        1.0 if camera == "z8" else 0.0,
        1.0 if camera == "mission1" else 0.0,
    )


def pooled_context_planes(x: torch.Tensor, grid: int = 8) -> torch.Tensor:
    grid_h = min(int(grid), int(x.shape[-2]))
    grid_w = min(int(grid), int(x.shape[-1]))
    pooled = F.adaptive_avg_pool2d(x, (grid_h, grid_w))
    return F.interpolate(pooled, size=x.shape[-2:], mode="bilinear", align_corners=False)


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


def load_noise_sigma4_from_sidecar(path: str | Path) -> tuple[float, float, float, float]:
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
    values: list[float] = []
    for key in ("r", "g1", "g2", "b"):
        plane = per_plane.get(key, {}) if isinstance(per_plane, dict) else {}
        values.append(float(plane.get("sigma_black", 0.0) or 0.0) / scale)
    if not any(values):
        vals = [float(v.get("sigma_black", 0.0) or 0.0) / scale for v in per_plane.values() if isinstance(v, dict)]
        mean = float(sum(vals) / len(vals)) if vals else 0.0
        values = [mean, mean, mean, mean]
    return tuple(float(np.clip(v, 0.0, 1.0)) for v in values)  # type: ignore[return-value]


def infer_row_camera(row: dict[str, Any]) -> str:
    scene = str(row.get("scene_id") or "").lower()
    source = str(row.get("source_dng") or row.get("candidate_raw") or "").lower()
    if "z8" in scene or "z8" in source:
        return "z8"
    if "x2d" in scene or "x2d" in source or "austin" in scene:
        return "x2d"
    if "mission" in scene or "gopro" in source or "gp0" in scene:
        return "mission1"
    return "unknown"


def context_crop_np(
    arr: np.ndarray,
    idx: int,
    y0: int,
    x0: int,
    patch_h: int,
    patch_w: int,
    context_padding: int,
) -> np.ndarray:
    if context_padding <= 0:
        return arr[idx, y0 : y0 + patch_h, x0 : x0 + patch_w]
    padded = np.pad(
        arr[idx],
        ((context_padding, context_padding), (context_padding, context_padding), (0, 0)),
        mode="edge",
    )
    return padded[y0 : y0 + patch_h + 2 * context_padding, x0 : x0 + patch_w + 2 * context_padding]


def center_crop_like(pred: torch.Tensor, target: torch.Tensor, context_padding: int) -> torch.Tensor:
    if context_padding <= 0:
        return pred
    _, _, target_h, target_w = target.shape
    return pred[:, :, context_padding : context_padding + target_h, context_padding : context_padding + target_w]


def apply_target_policy(
    target: torch.Tensor,
    sigma4: torch.Tensor | None,
    *,
    target_policy: str,
    noise_threshold_scale: float,
) -> torch.Tensor:
    if target_policy == "raw":
        return target
    if target_policy != "noise_soft_threshold":
        raise ValueError(f"unknown target policy: {target_policy}")
    if sigma4 is None:
        return target
    sigma = sigma4.to(device=target.device, dtype=target.dtype)
    if sigma.ndim == 1:
        sigma = sigma.view(1, 4)
    threshold = sigma.view(sigma.shape[0], 4, 1, 1) * float(noise_threshold_scale)
    return torch.sign(target) * torch.clamp(torch.abs(target) - threshold, min=0.0)


def classify_target_snr(target: np.ndarray, sigma4: tuple[float, float, float, float]) -> tuple[str, float, float]:
    sigma_mean = float(np.mean(np.asarray(sigma4, dtype=np.float64)))
    target_f = target.astype(np.float32, copy=False)
    target_rmse = float(np.sqrt(np.mean(target_f * target_f)))
    target_p95 = float(np.percentile(np.abs(target_f), 95.0))
    p95_proxy = sigma_mean * 3.0
    if sigma_mean <= 0.0:
        return ("missing_noise_sidecar", 0.0, 0.0)
    rmse_ratio = target_rmse / max(sigma_mean, 1.0e-12)
    p95_ratio = target_p95 / max(p95_proxy, 1.0e-12)
    if rmse_ratio >= 3.0 and p95_ratio >= 2.0:
        return ("signal_dominated", rmse_ratio, p95_ratio)
    if rmse_ratio <= 1.5 and p95_ratio <= 1.5:
        return ("noise_floor", rmse_ratio, p95_ratio)
    return ("mixed_signal_noise", rmse_ratio, p95_ratio)


def snr_class_allowed(row_class: str, policy: str) -> bool:
    if policy == "all":
        return True
    if policy == "signal_dominated":
        return row_class == "signal_dominated"
    if policy == "signal_or_mixed":
        return row_class in {"signal_dominated", "mixed_signal_noise"}
    if policy == "not_noise_floor":
        return row_class != "noise_floor"
    raise ValueError(f"unknown train_snr_class: {policy}")


def target_snr_loss_weight(row_class: str, rmse_ratio: float, p95_ratio: float, policy: str, strength: float) -> float:
    if policy == "none":
        return 1.0
    strength = float(np.clip(strength, 0.0, 2.0))
    if policy == "noise_floor_downweight":
        base = 0.35 if row_class == "noise_floor" else 1.0
    elif policy == "signal_emphasis":
        base = {
            "signal_dominated": 1.0,
            "mixed_signal_noise": 0.70,
            "noise_floor": 0.35,
            "missing_noise_sidecar": 0.50,
        }.get(row_class, 0.50)
    elif policy == "continuous_snr":
        if row_class == "missing_noise_sidecar":
            base = 0.50
        else:
            rmse_score = float(np.clip(rmse_ratio / 3.0, 0.0, 1.0))
            p95_score = float(np.clip(p95_ratio / 2.0, 0.0, 1.0))
            base = 0.30 + 0.70 * float(np.sqrt(rmse_score * p95_score))
    else:
        raise ValueError(f"unknown snr_loss_weight_policy: {policy}")
    return float(np.clip(1.0 + strength * (base - 1.0), 0.05, 2.0))


def target_energy_loss_weight(row_abs_mean: float, reference_abs_mean: float, policy: str, strength: float) -> float:
    if policy == "none":
        return 1.0
    strength = float(np.clip(strength, 0.0, 2.0))
    ratio = float(row_abs_mean) / max(float(reference_abs_mean), 1.0e-12)
    if policy == "high_energy_emphasis":
        base = float(np.clip(np.sqrt(max(ratio, 0.0)), 0.25, 3.0))
    elif policy == "inverse_energy":
        base = float(np.clip(1.0 / np.sqrt(max(ratio, 1.0e-6)), 0.25, 3.0))
    else:
        raise ValueError(f"unknown target_energy_loss_weight_policy: {policy}")
    return float(np.clip(1.0 + strength * (base - 1.0), 0.05, 4.0))


def make_features(
    raw: torch.Tensor,
    feature_mode: str,
    block: int,
    ev: torch.Tensor | None = None,
    noise: torch.Tensor | None = None,
    stored_hf: torch.Tensor | None = None,
    frame_context: torch.Tensor | None = None,
) -> torch.Tensor:
    if feature_mode == "raw":
        return raw
    fine = block_highpass(raw, block)
    if feature_mode == "raw_hf":
        return torch.cat([raw, fine], dim=1)
    if feature_mode == "raw_hf_coord_ev_noise":
        return torch.cat(
            [
                raw,
                fine,
                coord_planes(raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                ev_plane(ev, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                scalar_planes(noise, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
            ],
            dim=1,
        )
    if feature_mode == "raw_multiscale_coord_ev_noise":
        coarse_block = max(block * 3, block + 2)
        phase_mean = torch.mean(raw, dim=1, keepdim=True)
        return torch.cat(
            [
                raw,
                fine,
                block_highpass(raw, coarse_block),
                raw - phase_mean,
                coord_planes(raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                ev_plane(ev, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                scalar_planes(noise, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
            ],
            dim=1,
        )
    if feature_mode == "raw_framectx_coord_ev_noise":
        coarse_block = max(block * 3, block + 2)
        phase_mean = torch.mean(raw, dim=1, keepdim=True)
        return torch.cat(
            [
                raw,
                fine,
                block_highpass(raw, coarse_block),
                raw - phase_mean,
                coord_planes(raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                ev_plane(ev, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                scalar_planes(noise, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
                scalar_planes(frame_context, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, frame_context_channels()),
            ],
            dim=1,
        )
    if feature_mode == "raw_context_coord_ev_noise":
        coarse_block = max(block * 3, block + 2)
        phase_mean = torch.mean(raw, dim=1, keepdim=True)
        global_raw = torch.mean(raw, dim=(-2, -1))
        return torch.cat(
            [
                raw,
                fine,
                block_highpass(raw, coarse_block),
                raw - phase_mean,
                pooled_context_planes(raw),
                pooled_context_planes(fine),
                scalar_planes(global_raw, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
                coord_planes(raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                ev_plane(ev, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                scalar_planes(noise, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
            ],
            dim=1,
        )
    if feature_mode == "raw_context_storedhf_coord_ev_noise":
        if stored_hf is None:
            raise ValueError("raw_context_storedhf_coord_ev_noise requires candidate_raw_hf_cfa4")
        coarse_block = max(block * 3, block + 2)
        phase_mean = torch.mean(raw, dim=1, keepdim=True)
        clipped_hf = torch.clamp(stored_hf, -0.5, 0.5)
        global_raw = torch.mean(raw, dim=(-2, -1))
        global_hf = torch.mean(torch.abs(clipped_hf), dim=(-2, -1))
        return torch.cat(
            [
                raw,
                fine,
                block_highpass(raw, coarse_block),
                clipped_hf,
                raw - phase_mean,
                pooled_context_planes(raw),
                pooled_context_planes(fine),
                pooled_context_planes(clipped_hf),
                scalar_planes(global_raw, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
                scalar_planes(global_hf, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
                coord_planes(raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                ev_plane(ev, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                scalar_planes(noise, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
            ],
            dim=1,
        )
    if feature_mode == "raw_multiscale_storedhf_coord_ev_noise":
        if stored_hf is None:
            raise ValueError("raw_multiscale_storedhf_coord_ev_noise requires candidate_raw_hf_cfa4")
        coarse_block = max(block * 3, block + 2)
        phase_mean = torch.mean(raw, dim=1, keepdim=True)
        return torch.cat(
            [
                raw,
                fine,
                block_highpass(raw, coarse_block),
                torch.clamp(stored_hf, -0.5, 0.5),
                raw - phase_mean,
                coord_planes(raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                ev_plane(ev, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device),
                scalar_planes(noise, raw.shape[0], raw.shape[-2], raw.shape[-1], raw.device, 4),
            ],
            dim=1,
        )
    raise ValueError(f"unknown feature mode: {feature_mode}")


def feature_channels(feature_mode: str) -> int:
    return {
        "raw": 4,
        "raw_hf": 8,
        "raw_hf_coord_ev_noise": 15,
        "raw_multiscale_coord_ev_noise": 23,
        "raw_framectx_coord_ev_noise": 42,
        "raw_context_coord_ev_noise": 35,
        "raw_context_storedhf_coord_ev_noise": 47,
        "raw_multiscale_storedhf_coord_ev_noise": 27,
    }[feature_mode]


def runtime_input_summary(feature_mode: str) -> str:
    base = "candidate_raw_cfa4 + candidate_raw_highpass + deterministic coordinates/EV + camera/ISO noise sidecar scalars"
    if feature_mode == "raw_framectx_coord_ev_noise":
        return base + " + absolute crop position + camera one-hot + full-crop candidate raw/HF statistics"
    if feature_mode == "raw_context_coord_ev_noise":
        return base + " + pooled candidate raw/HF context planes + global candidate raw scalars"
    if feature_mode == "raw_context_storedhf_coord_ev_noise":
        return base + " + stored candidate_raw_hf_cfa4 + pooled candidate raw/HF/stored-HF context planes + global raw/HF scalars"
    if feature_mode == "raw_multiscale_storedhf_coord_ev_noise":
        return base + " + stored candidate_raw_hf_cfa4"
    return base


def sample_weight_map(sample_weight: torch.Tensor | None, diff: torch.Tensor) -> torch.Tensor | None:
    if sample_weight is None:
        return None
    weight = sample_weight.to(device=diff.device, dtype=diff.dtype).view(diff.shape[0], *([1] * (diff.ndim - 1)))
    return weight / torch.mean(weight).clamp_min(1.0e-6)


def weighted_abs_mean(diff: torch.Tensor, sample_weight: torch.Tensor | None = None) -> torch.Tensor:
    weight = sample_weight_map(sample_weight, diff)
    if weight is not None:
        diff = diff * weight
    return torch.mean(torch.abs(diff))


def gradient_l1(pred: torch.Tensor, target: torch.Tensor, sample_weight: torch.Tensor | None = None) -> torch.Tensor:
    return weighted_abs_mean(
        pred[:, :, :, 1:] - pred[:, :, :, :-1] - (target[:, :, :, 1:] - target[:, :, :, :-1]),
        sample_weight,
    ) + weighted_abs_mean(
        pred[:, :, 1:, :] - pred[:, :, :-1, :] - (target[:, :, 1:, :] - target[:, :, :-1, :]),
        sample_weight,
    )


def lowpass(x: torch.Tensor, block: int) -> torch.Tensor:
    block = max(3, int(block))
    if block % 2 == 0:
        block += 1
    pad = block // 2
    mode = "reflect" if x.shape[-1] > pad and x.shape[-2] > pad else "replicate"
    return F.avg_pool2d(F.pad(x, (pad, pad, pad, pad), mode=mode), block, stride=1)


def normalize_band_blocks(values: list[int]) -> list[int]:
    blocks = []
    for value in values:
        block = max(3, int(value))
        if block % 2 == 0:
            block += 1
        blocks.append(block)
    return sorted(set(blocks))


def multiscale_band_l1(pred: torch.Tensor, target: torch.Tensor, blocks: list[int], sample_weight: torch.Tensor | None = None) -> torch.Tensor:
    if not blocks:
        return torch.zeros((), dtype=pred.dtype, device=pred.device)
    loss = torch.zeros((), dtype=pred.dtype, device=pred.device)
    prev_pred_low = pred
    prev_target_low = target
    used = 0
    for block in blocks:
        pred_low = lowpass(pred, block)
        target_low = lowpass(target, block)
        pred_band = prev_pred_low - pred_low
        target_band = prev_target_low - target_low
        loss = loss + weighted_abs_mean(pred_band - target_band, sample_weight)
        prev_pred_low = pred_low
        prev_target_low = target_low
        used += 1
    loss = loss + weighted_abs_mean(prev_pred_low - prev_target_low, sample_weight)
    return loss / float(used + 1)


def spectral_magnitude_l1(pred: torch.Tensor, target: torch.Tensor, sample_weight: torch.Tensor | None = None) -> torch.Tensor:
    # MPS currently emits noisy internal-resize warnings for rfft2 on these
    # small diagnostic tensors. Keep this optional loss deterministic and quiet.
    device = pred.device
    pred_fft = torch.fft.rfft2(pred.float().contiguous().cpu(), dim=(-2, -1), norm="ortho")
    target_fft = torch.fft.rfft2(target.float().contiguous().cpu(), dim=(-2, -1), norm="ortho")
    weight = sample_weight.cpu() if sample_weight is not None else None
    return weighted_abs_mean(torch.abs(pred_fft) - torch.abs(target_fft), weight).to(device)


def residual_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    *,
    target_abs_weight: float,
    sample_weight: torch.Tensor | None = None,
) -> torch.Tensor:
    weight = torch.ones_like(target[:, 0:1])
    if target_abs_weight > 0.0:
        target_abs = torch.mean(torch.abs(target), dim=1, keepdim=True)
        weight = weight + float(target_abs_weight) * torch.clamp(target_abs / 0.03, 0.0, 5.0)
    weight = weight / torch.mean(weight).clamp_min(1.0e-6)
    diff = torch.abs(pred - target) * weight
    row_weight = sample_weight_map(sample_weight, diff)
    if row_weight is not None:
        diff = diff * row_weight
    return torch.mean(diff)


class ResidualBlock(nn.Module):
    def __init__(self, width: int, dilation: int = 1) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + 0.25 * self.net(x)


class RawCfaResidualNet(nn.Module):
    def __init__(self, in_channels: int, width: int = 48, depth: int = 6, residual_scale: float = 0.12) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        layers: list[nn.Module] = [nn.Conv2d(in_channels, width, 3, padding=1), nn.GELU()]
        dilations = [1, 2, 4, 2, 1]
        for i in range(max(1, depth)):
            layers.append(ResidualBlock(width, dilations[i % len(dilations)]))
        tail = nn.Conv2d(width, 4, 3, padding=1)
        nn.init.zeros_(tail.weight)
        nn.init.zeros_(tail.bias)
        layers.append(tail)
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.net(x)) * self.residual_scale


class ConvAct(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, stride=stride, padding=1),
            nn.GELU(),
            nn.Conv2d(out_channels, out_channels, 3, padding=1),
            nn.GELU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class RawCfaResidualUNet(nn.Module):
    def __init__(self, in_channels: int, width: int = 32, depth: int = 4, residual_scale: float = 0.12) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w1 = max(8, int(width))
        w2 = w1 * 2
        w3 = w1 * 4
        self.enc0 = ConvAct(in_channels, w1)
        self.enc1 = ConvAct(w1, w2, stride=2)
        self.enc2 = ConvAct(w2, w3, stride=2)
        self.bottleneck = nn.Sequential(*[ResidualBlock(w3, dilation=2 if i % 2 else 1) for i in range(max(1, depth))])
        self.dec1 = ConvAct(w3 + w2, w2)
        self.dec0 = ConvAct(w2 + w1, w1)
        self.tail = nn.Conv2d(w1, 4, 3, padding=1)
        nn.init.zeros_(self.tail.weight)
        nn.init.zeros_(self.tail.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e0 = self.enc0(x)
        e1 = self.enc1(e0)
        e2 = self.enc2(e1)
        b = self.bottleneck(e2)
        u1 = F.interpolate(b, size=e1.shape[-2:], mode="bilinear", align_corners=False)
        d1 = self.dec1(torch.cat([u1, e1], dim=1))
        u0 = F.interpolate(d1, size=e0.shape[-2:], mode="bilinear", align_corners=False)
        d0 = self.dec0(torch.cat([u0, e0], dim=1))
        return torch.tanh(self.tail(d0)) * self.residual_scale


class ChannelGate(nn.Module):
    def __init__(self, channels: int, reduction: int = 8) -> None:
        super().__init__()
        hidden = max(4, channels // max(1, reduction))
        self.net = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, hidden, 1),
            nn.GELU(),
            nn.Conv2d(hidden, channels, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.net(x)


class RCABlock(nn.Module):
    """Residual channel-attention block for CFA-aware teacher probes."""

    def __init__(self, width: int, dilation: int = 1, residual_scale: float = 0.25) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        self.body = nn.Sequential(
            nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=dilation, dilation=dilation),
            ChannelGate(width),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.residual_scale * self.body(x)


class RawCfaResidualRCABTeacher(nn.Module):
    """CFA-aware teacher backbone with channel attention and broad context.

    This is the first architecture in this trainer built to match the current
    premium still-SR research direction: packed CFA inputs, residual channel
    attention, a downsampled context branch, and compatibility with the existing
    spatial, multiscale-band, and Fourier losses. It remains a training probe
    until its receipts clear the still/editor-latitude gates.
    """

    def __init__(self, in_channels: int, width: int = 48, depth: int = 8, residual_scale: float = 0.12) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w1 = max(8, int(width))
        w2 = w1 * 2
        self.head = nn.Sequential(nn.Conv2d(in_channels, w1, 3, padding=1), nn.GELU())
        self.local_body = nn.Sequential(
            *[RCABlock(w1, dilation=[1, 2, 4, 2][i % 4]) for i in range(max(1, int(depth)))]
        )
        self.down = nn.Sequential(nn.Conv2d(w1, w2, 3, stride=2, padding=1), nn.GELU())
        self.context_body = nn.Sequential(
            *[RCABlock(w2, dilation=[1, 2, 4, 8][i % 4]) for i in range(max(1, int(depth) // 2))]
        )
        self.global_body = nn.Sequential(
            nn.Conv2d(w1, w2, 3, padding=1),
            nn.GELU(),
            *[RCABlock(w2, dilation=1) for _ in range(max(1, int(depth) // 3))],
        )
        self.up = nn.Conv2d(w2, w1, 3, padding=1)
        self.global_up = nn.Conv2d(w2, w1, 3, padding=1)
        self.fuse = nn.Sequential(
            nn.Conv2d(w1 * 3, w1, 3, padding=1),
            nn.GELU(),
            RCABlock(w1, dilation=1),
            RCABlock(w1, dilation=2),
        )
        self.tail = nn.Conv2d(w1, 4, 3, padding=1)
        nn.init.zeros_(self.tail.weight)
        nn.init.zeros_(self.tail.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.head(x)
        local = self.local_body(h)
        context = self.context_body(self.down(local))
        context = F.interpolate(self.up(context), size=local.shape[-2:], mode="bilinear", align_corners=False)
        global_size = (min(32, max(4, x.shape[-2] // 2)), min(32, max(4, x.shape[-1] // 2)))
        global_context = self.global_body(F.adaptive_avg_pool2d(local, global_size))
        global_context = F.interpolate(self.global_up(global_context), size=local.shape[-2:], mode="bilinear", align_corners=False)
        fused = self.fuse(torch.cat([local, context, global_context], dim=1))
        return torch.tanh(self.tail(fused)) * self.residual_scale


class SimpleGate(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        a, b = torch.chunk(x, 2, dim=1)
        return a * b


class NAFBlock(nn.Module):
    """NAFNet-style block with SimpleGate and lightweight channel attention."""

    def __init__(self, channels: int, expansion: int = 2, ffn_expansion: int = 2) -> None:
        super().__init__()
        dw_channels = max(2, channels * int(expansion))
        if dw_channels % 2:
            dw_channels += 1
        ffn_channels = max(2, channels * int(ffn_expansion))
        if ffn_channels % 2:
            ffn_channels += 1
        self.norm1 = nn.GroupNorm(1, channels)
        self.pw1 = nn.Conv2d(channels, dw_channels, 1)
        self.dwconv = nn.Conv2d(dw_channels, dw_channels, 3, padding=1, groups=dw_channels)
        self.gate = SimpleGate()
        self.channel_attn = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(dw_channels // 2, dw_channels // 2, 1),
            nn.Sigmoid(),
        )
        self.pw2 = nn.Conv2d(dw_channels // 2, channels, 1)
        self.norm2 = nn.GroupNorm(1, channels)
        self.ffn1 = nn.Conv2d(channels, ffn_channels, 1)
        self.ffn_gate = SimpleGate()
        self.ffn2 = nn.Conv2d(ffn_channels // 2, channels, 1)
        self.beta = nn.Parameter(torch.zeros((1, channels, 1, 1)))
        self.gamma = nn.Parameter(torch.zeros((1, channels, 1, 1)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.pw1(self.norm1(x))
        y = self.dwconv(y)
        y = self.gate(y)
        y = y * self.channel_attn(y)
        y = self.pw2(y)
        x = x + self.beta * y
        z = self.ffn1(self.norm2(x))
        z = self.ffn_gate(z)
        z = self.ffn2(z)
        return x + self.gamma * z


class RawCfaResidualNAFTeacher(nn.Module):
    """NAFNet-style CFA teacher for deduplicated raw residual targets.

    This mirrors the current research direction more closely than the local
    residual and RCAB probes: candidate-side packed CFA features enter a
    SimpleGate/attention backbone with a downsampled context path. The output
    remains a raw-CFA residual and the runtime input policy remains candidate
    raw plus deterministic metadata.
    """

    def __init__(self, in_channels: int, width: int = 48, depth: int = 8, residual_scale: float = 0.12) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w1 = max(8, int(width))
        w2 = w1 * 2
        self.intro = nn.Conv2d(in_channels, w1, 3, padding=1)
        self.local = nn.Sequential(*[NAFBlock(w1) for _ in range(max(1, int(depth)))])
        self.down = nn.Conv2d(w1, w2, 2, stride=2)
        self.context = nn.Sequential(*[NAFBlock(w2) for _ in range(max(1, int(depth) // 2))])
        self.global_proj = nn.Conv2d(w1, w2, 1)
        self.global_body = nn.Sequential(*[NAFBlock(w2) for _ in range(max(1, int(depth) // 3))])
        self.up = nn.Conv2d(w2, w1, 1)
        self.global_up = nn.Conv2d(w2, w1, 1)
        self.fuse = nn.Sequential(
            nn.Conv2d(w1 * 3, w1, 1),
            NAFBlock(w1),
            NAFBlock(w1),
        )
        self.tail = nn.Conv2d(w1, 4, 3, padding=1)
        nn.init.zeros_(self.tail.weight)
        nn.init.zeros_(self.tail.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        local = self.local(self.intro(x))
        context = self.context(self.down(local))
        context = F.interpolate(self.up(context), size=local.shape[-2:], mode="bilinear", align_corners=False)
        global_size = (min(32, max(4, x.shape[-2] // 2)), min(32, max(4, x.shape[-1] // 2)))
        global_context = self.global_proj(F.adaptive_avg_pool2d(local, global_size))
        global_context = self.global_body(global_context)
        global_context = F.interpolate(self.global_up(global_context), size=local.shape[-2:], mode="bilinear", align_corners=False)
        fused = self.fuse(torch.cat([local, context, global_context], dim=1))
        return torch.tanh(self.tail(fused)) * self.residual_scale


class RawCfaResidualPyramidUNet(nn.Module):
    """Deeper U-Net for full-crop raw-CFA residual probes.

    The existing U-Net is intentionally small. This variant adds one more
    pyramid level plus channel gating at each scale so a full-crop run can use
    broader candidate-only context without changing the runtime input policy.
    """

    def __init__(self, in_channels: int, width: int = 32, depth: int = 4, residual_scale: float = 0.12) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w1 = max(8, int(width))
        w2 = w1 * 2
        w3 = w1 * 4
        w4 = w1 * 6
        self.enc0 = nn.Sequential(ConvAct(in_channels, w1), ChannelGate(w1))
        self.enc1 = nn.Sequential(ConvAct(w1, w2, stride=2), ChannelGate(w2))
        self.enc2 = nn.Sequential(ConvAct(w2, w3, stride=2), ChannelGate(w3))
        self.enc3 = nn.Sequential(ConvAct(w3, w4, stride=2), ChannelGate(w4))
        blocks: list[nn.Module] = []
        dilations = [1, 2, 4, 8]
        for i in range(max(1, depth)):
            blocks.append(ResidualBlock(w4, dilation=dilations[i % len(dilations)]))
            blocks.append(ChannelGate(w4))
        self.bottleneck = nn.Sequential(*blocks)
        self.dec2 = nn.Sequential(ConvAct(w4 + w3, w3), ChannelGate(w3))
        self.dec1 = nn.Sequential(ConvAct(w3 + w2, w2), ChannelGate(w2))
        self.dec0 = nn.Sequential(ConvAct(w2 + w1, w1), ChannelGate(w1))
        self.tail = nn.Conv2d(w1, 4, 3, padding=1)
        nn.init.zeros_(self.tail.weight)
        nn.init.zeros_(self.tail.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e0 = self.enc0(x)
        e1 = self.enc1(e0)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        b = self.bottleneck(e3)
        u2 = F.interpolate(b, size=e2.shape[-2:], mode="bilinear", align_corners=False)
        d2 = self.dec2(torch.cat([u2, e2], dim=1))
        u1 = F.interpolate(d2, size=e1.shape[-2:], mode="bilinear", align_corners=False)
        d1 = self.dec1(torch.cat([u1, e1], dim=1))
        u0 = F.interpolate(d1, size=e0.shape[-2:], mode="bilinear", align_corners=False)
        d0 = self.dec0(torch.cat([u0, e0], dim=1))
        return torch.tanh(self.tail(d0)) * self.residual_scale


class RawCfaResidualGlobalContextUNet(nn.Module):
    """Full-crop U-Net with an explicit downsampled global context branch.

    This is deliberately different from the earlier pooled-statistics probes:
    the branch sees a spatially downsampled candidate-derived feature map,
    processes it with convolutional residual blocks, and injects that
    structured context at the bottleneck. It still uses only candidate-side
    runtime inputs.
    """

    def __init__(self, in_channels: int, width: int = 32, depth: int = 4, residual_scale: float = 0.12) -> None:
        super().__init__()
        self.residual_scale = float(residual_scale)
        w1 = max(8, int(width))
        w2 = w1 * 2
        w3 = w1 * 4
        self.enc0 = nn.Sequential(ConvAct(in_channels, w1), ChannelGate(w1))
        self.enc1 = nn.Sequential(ConvAct(w1, w2, stride=2), ChannelGate(w2))
        self.enc2 = nn.Sequential(ConvAct(w2, w3, stride=2), ChannelGate(w3))
        context_blocks: list[nn.Module] = [ConvAct(in_channels, w2), ConvAct(w2, w3), ChannelGate(w3)]
        for i in range(max(1, depth // 2)):
            context_blocks.append(ResidualBlock(w3, dilation=2 if i % 2 else 1))
        self.context = nn.Sequential(*context_blocks)
        bottleneck_blocks: list[nn.Module] = []
        dilations = [1, 2, 4, 8]
        for i in range(max(1, depth)):
            bottleneck_blocks.append(ResidualBlock(w3, dilation=dilations[i % len(dilations)]))
            bottleneck_blocks.append(ChannelGate(w3))
        self.bottleneck = nn.Sequential(*bottleneck_blocks)
        self.dec1 = nn.Sequential(ConvAct(w3 + w2, w2), ChannelGate(w2))
        self.dec0 = nn.Sequential(ConvAct(w2 + w1, w1), ChannelGate(w1))
        self.tail = nn.Conv2d(w1, 4, 3, padding=1)
        nn.init.zeros_(self.tail.weight)
        nn.init.zeros_(self.tail.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e0 = self.enc0(x)
        e1 = self.enc1(e0)
        e2 = self.enc2(e1)
        context_size = (min(24, x.shape[-2]), min(24, x.shape[-1]))
        g = self.context(F.adaptive_avg_pool2d(x, context_size))
        g = F.interpolate(g, size=e2.shape[-2:], mode="bilinear", align_corners=False)
        b = self.bottleneck(e2 + g)
        u1 = F.interpolate(b, size=e1.shape[-2:], mode="bilinear", align_corners=False)
        d1 = self.dec1(torch.cat([u1, e1], dim=1))
        u0 = F.interpolate(d1, size=e0.shape[-2:], mode="bilinear", align_corners=False)
        d0 = self.dec0(torch.cat([u0, e0], dim=1))
        return torch.tanh(self.tail(d0)) * self.residual_scale


def build_model(model_arch: str, in_channels: int, width: int, depth: int, residual_scale: float) -> nn.Module:
    if model_arch == "residual":
        return RawCfaResidualNet(
            in_channels=in_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    if model_arch == "unet":
        return RawCfaResidualUNet(
            in_channels=in_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    if model_arch == "rcab_teacher":
        return RawCfaResidualRCABTeacher(
            in_channels=in_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    if model_arch == "naf_teacher":
        return RawCfaResidualNAFTeacher(
            in_channels=in_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    if model_arch == "pyramid_unet":
        return RawCfaResidualPyramidUNet(
            in_channels=in_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    if model_arch == "global_context_unet":
        return RawCfaResidualGlobalContextUNet(
            in_channels=in_channels,
            width=width,
            depth=depth,
            residual_scale=residual_scale,
        )
    raise ValueError(f"unknown model_arch: {model_arch}")


class RawCfaResidualTargets:
    def __init__(self, path: Path) -> None:
        with np.load(path, allow_pickle=False) as z:
            self.candidate_raw = z["candidate_raw_cfa4"].astype(np.float32)
            self.target = z["raw_hf_residual_cfa4"].astype(np.float32)
            self.candidate_raw_hf = z["candidate_raw_hf_cfa4"].astype(np.float32) if "candidate_raw_hf_cfa4" in z.files else None
            self.source_raw_hf = z["source_raw_hf_cfa4"].astype(np.float32) if "source_raw_hf_cfa4" in z.files else None
            self.render_hf_y = z["render_hf_residual_y"].astype(np.float32) if "render_hf_residual_y" in z.files else None
            self.rows = json.loads(str(z["meta"]))
        if self.candidate_raw.shape != self.target.shape:
            raise ValueError(f"candidate/target shape mismatch: {self.candidate_raw.shape} vs {self.target.shape}")
        if self.candidate_raw.ndim != 4 or self.candidate_raw.shape[-1] != 4:
            raise ValueError(f"expected NHWC raw-CFA4 arrays, got {self.candidate_raw.shape}")
        cache: dict[str, tuple[float, float, float, float]] = {}
        sigma_cache: dict[str, tuple[float, float, float, float]] = {}
        self.noise_features: list[tuple[float, float, float, float]] = []
        self.noise_sigma4: list[tuple[float, float, float, float]] = []
        self.target_snr_classes: list[str] = []
        self.target_snr_rmse_ratios: list[float] = []
        self.target_snr_p95_ratios: list[float] = []
        self.target_abs_means: list[float] = []
        scene_dims: dict[str, tuple[float, float]] = {}
        for row in self.rows:
            scene = str(row.get("scene_id") or "unknown")
            origin = row.get("candidate_raw_cfa_origin_xy") or row.get("crop_xy") or [0, 0]
            try:
                ox = float(origin[0])
                oy = float(origin[1])
            except (TypeError, ValueError, IndexError):
                ox = oy = 0.0
            crop_size = float(row.get("crop_size") or self.candidate_raw.shape[1])
            current_w, current_h = scene_dims.get(scene, (crop_size, crop_size))
            scene_dims[scene] = (max(current_w, ox + crop_size), max(current_h, oy + crop_size))
        self.frame_context_features: list[tuple[float, ...]] = []
        for row in self.rows:
            sidecars = row.get("noise_sidecars", [])
            sidecar = str(sidecars[0]) if isinstance(sidecars, list) and sidecars else ""
            if sidecar and sidecar not in cache:
                cache[sidecar] = load_noise_feature_from_sidecar(sidecar)
                sigma_cache[sidecar] = load_noise_sigma4_from_sidecar(sidecar)
            self.noise_features.append(cache.get(sidecar, (0.0, 0.0, 0.0, 0.0)))
            self.noise_sigma4.append(sigma_cache.get(sidecar, (0.0, 0.0, 0.0, 0.0)))
        for idx, sigma4 in enumerate(self.noise_sigma4):
            row_class, rmse_ratio, p95_ratio = classify_target_snr(self.target[idx], sigma4)
            self.target_snr_classes.append(row_class)
            self.target_snr_rmse_ratios.append(rmse_ratio)
            self.target_snr_p95_ratios.append(p95_ratio)
            self.target_abs_means.append(float(np.mean(np.abs(self.target[idx].astype(np.float32, copy=False)))))
        for idx, row in enumerate(self.rows):
            scene = str(row.get("scene_id") or "unknown")
            scene_w, scene_h = scene_dims.get(scene, (float(self.candidate_raw.shape[2]), float(self.candidate_raw.shape[1])))
            origin = row.get("candidate_raw_cfa_origin_xy") or row.get("crop_xy") or [0, 0]
            try:
                ox = float(origin[0])
                oy = float(origin[1])
            except (TypeError, ValueError, IndexError):
                ox = oy = 0.0
            crop_size = float(row.get("crop_size") or self.candidate_raw.shape[1])
            cx = 2.0 * ((ox + 0.5 * crop_size) / max(scene_w, 1.0)) - 1.0
            cy = 2.0 * ((oy + 0.5 * crop_size) / max(scene_h, 1.0)) - 1.0
            crop_w = crop_size / max(scene_w, 1.0)
            crop_h = crop_size / max(scene_h, 1.0)
            raw = self.candidate_raw[idx].astype(np.float32)
            raw_mean = np.mean(raw, axis=(0, 1))
            raw_std = np.std(raw, axis=(0, 1))
            if self.candidate_raw_hf is not None:
                hf_abs = np.mean(np.abs(np.clip(self.candidate_raw_hf[idx].astype(np.float32), -0.5, 0.5)), axis=(0, 1))
            else:
                hf_abs = np.mean(np.abs(raw - np.mean(raw, axis=(0, 1), keepdims=True)), axis=(0, 1))
            context = (
                float(np.clip(cx, -1.0, 1.0)),
                float(np.clip(cy, -1.0, 1.0)),
                float(np.clip(crop_w, 0.0, 1.0)),
                float(np.clip(crop_h, 0.0, 1.0)),
                *camera_onehot(infer_row_camera(row)),
                *(float(np.clip(v, 0.0, 1.0)) for v in raw_mean.tolist()),
                *(float(np.clip(v * 4.0, 0.0, 1.0)) for v in raw_std.tolist()),
                *(float(np.clip(v * 16.0, 0.0, 1.0)) for v in hf_abs.tolist()),
            )
            if len(context) != frame_context_channels():
                raise ValueError(f"frame context has {len(context)} channels, expected {frame_context_channels()}")
            self.frame_context_features.append(context)

    def row_indices(
        self,
        holdout_scene: str | None,
        holdout_camera: str | None,
        holdout_ev: float | None,
        train_camera: str | None = None,
        train_snr_class: str = "all",
    ) -> tuple[list[int], list[int]]:
        if holdout_scene:
            holdout = [i for i, row in enumerate(self.rows) if str(row.get("scene_id", "")) == holdout_scene]
        elif holdout_camera:
            needle = holdout_camera.lower()
            holdout = [i for i, row in enumerate(self.rows) if needle in str(row.get("source_dng", "")).lower()]
        elif holdout_ev is not None:
            holdout = [i for i, row in enumerate(self.rows) if abs(float(row.get("ev", 0.0)) - holdout_ev) < 1.0e-6]
        else:
            holdout = []
        train = [i for i in range(len(self.rows)) if i not in holdout]
        if train_camera:
            needle = train_camera.lower()
            train = [i for i in train if needle in str(self.rows[i].get("source_dng", "")).lower()]
        if train_snr_class != "all":
            before = len(train)
            train = [i for i in train if snr_class_allowed(self.target_snr_classes[i], train_snr_class)]
            if before and not train:
                raise ValueError(f"train-snr-class filter {train_snr_class!r} removed all {before} training rows")
        if (holdout_scene or holdout_camera or holdout_ev is not None) and (not train or not holdout):
            raise ValueError(f"holdout split produced train={len(train)} holdout={len(holdout)}")
        if train_camera and not train:
            raise ValueError(f"train-camera filter {train_camera!r} produced no training rows")
        return train, holdout

    def snr_loss_weight_stats(self, indices: list[int], policy: str, strength: float) -> dict[str, float]:
        values = [
            target_snr_loss_weight(
                self.target_snr_classes[idx],
                self.target_snr_rmse_ratios[idx],
                self.target_snr_p95_ratios[idx],
                policy,
                strength,
            )
            for idx in indices
        ]
        return stats(values)

    def target_energy_reference(self, indices: list[int]) -> float:
        values = [self.target_abs_means[idx] for idx in indices]
        return float(np.median(np.asarray(values, dtype=np.float64))) if values else 0.0

    def target_energy_loss_weight_stats(self, indices: list[int], policy: str, strength: float, reference_abs_mean: float) -> dict[str, float]:
        values = [
            target_energy_loss_weight(
                self.target_abs_means[idx],
                reference_abs_mean,
                policy,
                strength,
            )
            for idx in indices
        ]
        return stats(values)

    def sample_batch(
        self,
        indices: list[int],
        batch_size: int,
        patch_size: int,
        rng: random.Random,
        sample_balance: str = "row",
        sample_mode: str = "random_patch",
        context_padding: int = 0,
        snr_loss_weight_policy: str = "none",
        snr_loss_weight_strength: float = 1.0,
        target_energy_loss_weight_policy: str = "none",
        target_energy_loss_weight_strength: float = 1.0,
        target_energy_reference_abs_mean: float = 0.0,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor | None]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        hfs: list[np.ndarray] = []
        evs: list[float] = []
        noises: list[tuple[float, float, float, float]] = []
        sigmas: list[tuple[float, float, float, float]] = []
        contexts: list[tuple[float, ...]] = []
        snr_weights: list[float] = []
        h, w = self.candidate_raw.shape[1:3]
        if sample_mode == "random_patch":
            patch_h = patch_w = min(patch_size, h, w)
        elif sample_mode == "full_crop":
            patch_h = h
            patch_w = w
        else:
            raise ValueError(f"unknown sample_mode: {sample_mode}")
        groups: dict[str, list[int]] | None = None
        if sample_balance != "row":
            groups = {}
            for idx in indices:
                if sample_balance == "camera":
                    key = infer_row_camera(self.rows[idx])
                elif sample_balance == "scene":
                    key = str(self.rows[idx].get("scene_id") or "unknown")
                else:
                    raise ValueError(f"unknown sample_balance: {sample_balance}")
                groups.setdefault(key, []).append(idx)
            groups = {key: value for key, value in groups.items() if value}
            if not groups:
                raise ValueError(f"sample_balance={sample_balance} produced no groups")
            group_keys = sorted(groups)
        for _ in range(batch_size):
            if groups is None:
                idx = rng.choice(indices)
            else:
                idx = rng.choice(groups[rng.choice(group_keys)])
            y0 = rng.randrange(0, h - patch_h + 1) if h > patch_h else 0
            x0 = rng.randrange(0, w - patch_w + 1) if w > patch_w else 0
            xs.append(context_crop_np(self.candidate_raw, idx, y0, x0, patch_h, patch_w, context_padding).transpose(2, 0, 1))
            ys.append(self.target[idx, y0 : y0 + patch_h, x0 : x0 + patch_w].transpose(2, 0, 1))
            if self.candidate_raw_hf is not None:
                hfs.append(
                    context_crop_np(self.candidate_raw_hf, idx, y0, x0, patch_h, patch_w, context_padding).transpose(2, 0, 1)
                )
            evs.append(float(self.rows[idx].get("ev", 0.0)))
            noises.append(self.noise_features[idx])
            sigmas.append(self.noise_sigma4[idx])
            contexts.append(self.frame_context_features[idx])
            snr_weight = target_snr_loss_weight(
                self.target_snr_classes[idx],
                self.target_snr_rmse_ratios[idx],
                self.target_snr_p95_ratios[idx],
                snr_loss_weight_policy,
                snr_loss_weight_strength,
            )
            energy_weight = target_energy_loss_weight(
                self.target_abs_means[idx],
                target_energy_reference_abs_mean,
                target_energy_loss_weight_policy,
                target_energy_loss_weight_strength,
            )
            snr_weights.append(snr_weight * energy_weight)
        return (
            torch.from_numpy(np.stack(xs)),
            torch.from_numpy(np.stack(ys)),
            torch.tensor(evs, dtype=torch.float32),
            torch.tensor(noises, dtype=torch.float32),
            torch.tensor(sigmas, dtype=torch.float32),
            torch.tensor(contexts, dtype=torch.float32),
            torch.tensor(snr_weights, dtype=torch.float32),
            torch.from_numpy(np.stack(hfs)) if hfs else None,
        )


@torch.no_grad()
def eval_rows(
    model: nn.Module,
    data: RawCfaResidualTargets,
    indices: list[int],
    *,
    feature_mode: str,
    feature_block: int,
    target_policy: str,
    noise_threshold_scale: float,
    device: torch.device,
    tile: int,
    context_padding: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    model.eval()
    for idx in indices:
        raw = torch.from_numpy(data.candidate_raw[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        raw_target = torch.from_numpy(data.target[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        ev = torch.tensor([float(data.rows[idx].get("ev", 0.0))], dtype=torch.float32, device=device)
        noise = torch.tensor([data.noise_features[idx]], dtype=torch.float32, device=device)
        frame_context = torch.tensor([data.frame_context_features[idx]], dtype=torch.float32, device=device)
        sigma = torch.tensor([data.noise_sigma4[idx]], dtype=torch.float32, device=device)
        stored_hf = (
            torch.from_numpy(data.candidate_raw_hf[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            if data.candidate_raw_hf is not None
            else None
        )
        target = apply_target_policy(
            raw_target,
            sigma,
            target_policy=target_policy,
            noise_threshold_scale=noise_threshold_scale,
        )
        pred = torch.zeros_like(target)
        _, _, height, width = raw.shape
        pad = max(0, int(context_padding))
        raw_padded = torch.nn.functional.pad(raw, (pad, pad, pad, pad), mode="replicate") if pad else raw
        stored_hf_padded = (
            torch.nn.functional.pad(stored_hf, (pad, pad, pad, pad), mode="replicate")
            if pad and stored_hf is not None
            else stored_hf
        )
        for y0 in range(0, height, tile):
            for x0 in range(0, width, tile):
                y1 = min(y0 + tile, height)
                x1 = min(x0 + tile, width)
                raw_tile = raw_padded[:, :, y0 : y1 + 2 * pad, x0 : x1 + 2 * pad]
                hf_tile = stored_hf_padded[:, :, y0 : y1 + 2 * pad, x0 : x1 + 2 * pad] if stored_hf_padded is not None else None
                pred_tile = model(make_features(raw_tile, feature_mode, feature_block, ev, noise, hf_tile, frame_context))
                pred[:, :, y0:y1, x0:x1] = pred_tile[:, :, pad : pad + (y1 - y0), pad : pad + (x1 - x0)] if pad else pred_tile
        base_err = target
        pred_err = pred - target
        raw_pred_err = pred - raw_target
        base_mae = float(torch.mean(torch.abs(base_err)).cpu())
        pred_mae = float(torch.mean(torch.abs(pred_err)).cpu())
        base_rmse = float(torch.sqrt(torch.mean(base_err * base_err)).cpu())
        pred_rmse = float(torch.sqrt(torch.mean(pred_err * pred_err)).cpu())
        raw_base_mae = float(torch.mean(torch.abs(raw_target)).cpu())
        raw_pred_mae = float(torch.mean(torch.abs(raw_pred_err)).cpu())
        row_meta = dict(data.rows[idx])
        row_meta.update(
            {
                "index": idx,
                "baseline_raw_residual_mae": base_mae,
                "model_raw_residual_mae": pred_mae,
                "baseline_raw_residual_rmse": base_rmse,
                "model_raw_residual_rmse": pred_rmse,
                "raw_residual_mae_reduction_pct": 100.0 * (base_mae - pred_mae) / max(base_mae, 1.0e-12),
                "raw_residual_rmse_reduction_pct": 100.0 * (base_rmse - pred_rmse) / max(base_rmse, 1.0e-12),
                "exact_raw_baseline_mae": raw_base_mae,
                "exact_raw_model_mae": raw_pred_mae,
                "exact_raw_mae_reduction_pct": 100.0 * (raw_base_mae - raw_pred_mae) / max(raw_base_mae, 1.0e-12),
            }
        )
        rows.append(row_meta)
    return {
        "row_count": len(rows),
        "baseline_raw_residual_mae": stats([row["baseline_raw_residual_mae"] for row in rows]),
        "model_raw_residual_mae": stats([row["model_raw_residual_mae"] for row in rows]),
        "raw_residual_mae_reduction_pct": stats([row["raw_residual_mae_reduction_pct"] for row in rows]),
        "baseline_raw_residual_rmse": stats([row["baseline_raw_residual_rmse"] for row in rows]),
        "model_raw_residual_rmse": stats([row["model_raw_residual_rmse"] for row in rows]),
        "raw_residual_rmse_reduction_pct": stats([row["raw_residual_rmse_reduction_pct"] for row in rows]),
        "exact_raw_mae_reduction_pct": stats([row["exact_raw_mae_reduction_pct"] for row in rows]),
        "context_padding": context_padding,
        "rows": rows,
    }


def cfa4_to_rgb_preview(arr: np.ndarray) -> np.ndarray:
    r = arr[..., 0]
    g = 0.5 * (arr[..., 1] + arr[..., 2])
    b = arr[..., 3]
    return np.stack([r, g, b], axis=-1)


@torch.no_grad()
def write_panel_sheet(
    path: Path,
    model: nn.Module,
    data: RawCfaResidualTargets,
    indices: list[int],
    *,
    feature_mode: str,
    feature_block: int,
    target_policy: str,
    noise_threshold_scale: float,
    device: torch.device,
    residual_scale: float,
    max_rows: int,
) -> None:
    selected = indices[:max_rows]
    if not selected:
        return
    crop_h, crop_w = data.candidate_raw.shape[1:3]
    preview_w = min(384, crop_w)
    preview_h = min(384, crop_h)
    pad = 10
    label_h = 42
    cols = 4
    sheet = Image.new("RGB", (cols * (preview_w + pad) + pad, len(selected) * (preview_h + label_h + pad) + pad), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["candidate raw RGB preview", "target raw residual", "pred raw residual", "abs error"]
    model.eval()
    for row_i, idx in enumerate(selected):
        raw = torch.from_numpy(data.candidate_raw[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        ev = torch.tensor([float(data.rows[idx].get("ev", 0.0))], dtype=torch.float32, device=device)
        noise = torch.tensor([data.noise_features[idx]], dtype=torch.float32, device=device)
        frame_context = torch.tensor([data.frame_context_features[idx]], dtype=torch.float32, device=device)
        sigma = torch.tensor([data.noise_sigma4[idx]], dtype=torch.float32, device=device)
        stored_hf = (
            torch.from_numpy(data.candidate_raw_hf[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            if data.candidate_raw_hf is not None
            else None
        )
        pred = (
            model(make_features(raw, feature_mode, feature_block, ev, noise, stored_hf, frame_context))
            .squeeze(0)
            .cpu()
            .numpy()
            .transpose(1, 2, 0)
        )
        target_t = torch.from_numpy(data.target[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        target = (
            apply_target_policy(
                target_t,
                sigma,
                target_policy=target_policy,
                noise_threshold_scale=noise_threshold_scale,
            )
            .squeeze(0)
            .cpu()
            .numpy()
            .transpose(1, 2, 0)
        )
        err = np.abs(pred - target)
        panels = [
            np.clip(cfa4_to_rgb_preview(data.candidate_raw[idx]), 0.0, 1.0),
            np.clip(cfa4_to_rgb_preview(target) / residual_scale * 0.5 + 0.5, 0.0, 1.0),
            np.clip(cfa4_to_rgb_preview(pred) / residual_scale * 0.5 + 0.5, 0.0, 1.0),
            np.clip(cfa4_to_rgb_preview(err) / residual_scale, 0.0, 1.0),
        ]
        y0 = pad + row_i * (preview_h + label_h + pad)
        row = data.rows[idx]
        draw.text((pad, y0), f"{row.get('scene_id')} / {row.get('crop')} EV {float(row.get('ev', 0.0)):+.0f}", fill=(245, 245, 245))
        for col, panel in enumerate(panels):
            x0 = pad + col * (preview_w + pad)
            draw.text((x0, y0 + 22), headers[col], fill=(190, 190, 190))
            img = Image.fromarray((panel * 255.0 + 0.5).astype(np.uint8), "RGB").resize((preview_w, preview_h), Image.Resampling.BILINEAR)
            sheet.paste(img, (x0, y0 + label_h))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def render_html(receipt: dict[str, Any], output_dir: Path) -> str:
    train = receipt["eval"]["train"]
    holdout = receipt["eval"].get("holdout")
    panel = Path(receipt["artifacts"]["panel_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    rows = sorted(train["rows"] + (holdout["rows"] if holdout else []), key=lambda row: row["model_raw_residual_mae"], reverse=True)
    table = []
    for row in rows:
        table.append(
            f"<tr><td>{html.escape(str(row.get('scene_id')))}</td><td>{html.escape(str(row.get('crop')))}</td><td>{float(row.get('ev', 0.0)):+.0f}</td>"
            f"<td>{row['baseline_raw_residual_mae']:.6f}</td><td>{row['model_raw_residual_mae']:.6f}</td>"
            f"<td>{row['raw_residual_mae_reduction_pct']:.2f}%</td><td>{row['model_raw_residual_rmse']:.6f}</td></tr>"
        )
    holdout_text = ""
    if holdout:
        holdout_text = (
            f"<div class='card'><h2>Holdout Raw MAE Reduction</h2>"
            f"<p>{holdout['raw_residual_mae_reduction_pct']['median']:.2f}% median</p></div>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR Raw-CFA Residual Model</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left}}
code{{color:#b7d7ff}}img{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR Raw-CFA Residual Model</h1>
<p><b>Policy:</b> training target uses source raw, but inference uses candidate raw CFA planes and deterministic metadata only.</p>
<p><b>Target policy:</b> <code>{html.escape(str(receipt['config']['target_policy']))}</code>, noise threshold scale <code>{float(receipt['config']['noise_threshold_scale']):.2f}</code>.</p>
<p>Checkpoint: <code>{html.escape(receipt['checkpoint'])}</code></p>
<div class="grid">
<div class="card"><h2>Train Rows</h2><p>{train['row_count']}</p></div>
<div class="card"><h2>Train Raw MAE Reduction</h2><p>{train['raw_residual_mae_reduction_pct']['median']:.2f}% median</p></div>
{holdout_text}
<div class="card"><h2>Exact Raw Holdout</h2><p>{0.0 if not holdout else holdout['exact_raw_mae_reduction_pct']['median']:.2f}% median</p></div>
<div class="card"><h2>Runtime Safety</h2><p>{html.escape(receipt['policy']['runtime_inputs'])}</p></div>
</div>
<img src="{html.escape(panel)}">
<table><tr><th>scene</th><th>crop</th><th>EV</th><th>baseline raw MAE</th><th>model raw MAE</th><th>MAE reduction</th><th>model RMSE</th></tr>
{''.join(table)}
</table></body></html>
"""


def train(args: argparse.Namespace) -> dict[str, Any]:
    if not hasattr(args, "eval_during_training_rows"):
        args.eval_during_training_rows = 0
    if not hasattr(args, "save_best_holdout_checkpoint"):
        args.save_best_holdout_checkpoint = False
    if not hasattr(args, "snr_loss_weight_policy"):
        args.snr_loss_weight_policy = "none"
    if not hasattr(args, "snr_loss_weight_strength"):
        args.snr_loss_weight_strength = 1.0
    if not hasattr(args, "target_energy_loss_weight_policy"):
        args.target_energy_loss_weight_policy = "none"
    if not hasattr(args, "target_energy_loss_weight_strength"):
        args.target_energy_loss_weight_strength = 1.0
    data = RawCfaResidualTargets(args.targets)
    if args.feature_mode in {"raw_multiscale_storedhf_coord_ev_noise", "raw_context_storedhf_coord_ev_noise"} and data.candidate_raw_hf is None:
        raise ValueError(f"{args.feature_mode} requires candidate_raw_hf_cfa4 in the target NPZ")
    band_blocks = normalize_band_blocks(args.band_blocks)
    train_indices, holdout_indices = data.row_indices(
        args.holdout_scene,
        args.holdout_camera,
        args.holdout_ev,
        args.train_camera,
        args.train_snr_class,
    )
    target_energy_reference_abs_mean = data.target_energy_reference(train_indices)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device) if args.device else DEVICE
    model = build_model(
        args.model_arch,
        in_channels=feature_channels(args.feature_mode),
        width=args.width,
        depth=args.depth,
        residual_scale=args.residual_scale,
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, Any]] = []
    best_holdout: dict[str, Any] | None = None
    best_state: dict[str, torch.Tensor] | None = None
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        x, y, ev, noise, sigma, frame_context, snr_weight, stored_hf = data.sample_batch(
            train_indices,
            args.batch_size,
            args.patch_size,
            rng,
            args.sample_balance,
            args.sample_mode,
            args.context_padding,
            args.snr_loss_weight_policy,
            args.snr_loss_weight_strength,
            args.target_energy_loss_weight_policy,
            args.target_energy_loss_weight_strength,
            target_energy_reference_abs_mean,
        )
        x = x.to(device)
        y = y.to(device)
        ev = ev.to(device)
        noise = noise.to(device)
        sigma = sigma.to(device)
        frame_context = frame_context.to(device)
        snr_weight = snr_weight.to(device)
        stored_hf = stored_hf.to(device) if stored_hf is not None else None
        y = apply_target_policy(
            y,
            sigma,
            target_policy=args.target_policy,
            noise_threshold_scale=args.noise_threshold_scale,
        )
        x_train, stored_hf_train = apply_context_mask(
            x,
            stored_hf,
            mask_prob=args.context_mask_prob,
            mask_block=args.context_mask_block,
        )
        pred = model(make_features(x_train, args.feature_mode, args.feature_block, ev, noise, stored_hf_train, frame_context))
        pred = center_crop_like(pred, y, args.context_padding)
        loss = (
            residual_loss(pred, y, target_abs_weight=args.target_abs_weight, sample_weight=snr_weight)
            + args.grad_weight * gradient_l1(pred, y, snr_weight)
        )
        if args.band_weight > 0.0:
            loss = loss + args.band_weight * multiscale_band_l1(pred, y, band_blocks, snr_weight)
        if args.spectral_weight > 0.0:
            loss = loss + args.spectral_weight * spectral_magnitude_l1(pred, y, snr_weight)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        opt.step()
        if step == 1 or step == args.steps or (args.eval_every > 0 and step % args.eval_every == 0):
            row: dict[str, Any] = {"step": step, "loss": float(loss.detach().cpu())}
            if args.eval_during_training_rows > 0 and holdout_indices:
                probe_indices = holdout_indices[: min(args.eval_during_training_rows, len(holdout_indices))]
                probe_eval = eval_rows(
                    model,
                    data,
                    probe_indices,
                    feature_mode=args.feature_mode,
                    feature_block=args.feature_block,
                    target_policy=args.target_policy,
                    noise_threshold_scale=args.noise_threshold_scale,
                    device=device,
                    tile=args.eval_tile,
                    context_padding=args.context_padding,
                )
                probe_median = float(probe_eval["raw_residual_mae_reduction_pct"]["median"])
                row["holdout_probe_row_count"] = len(probe_indices)
                row["holdout_probe_raw_mae_reduction_pct_median"] = probe_median
                if best_holdout is None or probe_median > float(best_holdout["raw_mae_reduction_pct_median"]):
                    best_holdout = {
                        "step": step,
                        "raw_mae_reduction_pct_median": probe_median,
                        "row_count": len(probe_indices),
                        "selection_metric": "holdout_probe_raw_mae_reduction_pct_median",
                    }
                    if args.save_best_holdout_checkpoint:
                        best_state = {
                            key: value.detach().cpu().clone()
                            for key, value in model.state_dict().items()
                        }
                model.train()
            history.append(row)
    train_s = time.perf_counter() - t0
    if args.save_best_holdout_checkpoint and best_state is not None:
        model.load_state_dict({key: value.to(device) for key, value in best_state.items()})
    eval_train_indices = train_indices
    if args.eval_train_rows > 0:
        eval_train_indices = train_indices[: min(args.eval_train_rows, len(train_indices))]
    eval_holdout_indices = holdout_indices
    if args.eval_holdout_rows > 0:
        eval_holdout_indices = holdout_indices[: min(args.eval_holdout_rows, len(holdout_indices))]
    train_eval = eval_rows(
        model,
        data,
        eval_train_indices,
        feature_mode=args.feature_mode,
        feature_block=args.feature_block,
        target_policy=args.target_policy,
        noise_threshold_scale=args.noise_threshold_scale,
        device=device,
        tile=args.eval_tile,
        context_padding=args.context_padding,
    )
    holdout_eval = None
    if eval_holdout_indices:
        holdout_eval = eval_rows(
            model,
            data,
            eval_holdout_indices,
            feature_mode=args.feature_mode,
            feature_block=args.feature_block,
            target_policy=args.target_policy,
            noise_threshold_scale=args.noise_threshold_scale,
            device=device,
            tile=args.eval_tile,
            context_padding=args.context_padding,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / args.checkpoint_name
    torch.save(
        {
            "schema": SCHEMA,
            "state_dict": model.state_dict(),
            "config": {
                "feature_mode": args.feature_mode,
                "model_arch": args.model_arch,
                "feature_block": args.feature_block,
                "steps": args.steps,
                "width": args.width,
                "depth": args.depth,
                "residual_scale": args.residual_scale,
                "target_abs_weight": args.target_abs_weight,
                "band_weight": args.band_weight,
                "band_blocks": band_blocks,
                "spectral_weight": args.spectral_weight,
                "target_policy": args.target_policy,
                "noise_threshold_scale": args.noise_threshold_scale,
                "train_camera": args.train_camera,
                "train_snr_class": args.train_snr_class,
                "snr_loss_weight_policy": args.snr_loss_weight_policy,
                "snr_loss_weight_strength": args.snr_loss_weight_strength,
                "target_energy_loss_weight_policy": args.target_energy_loss_weight_policy,
                "target_energy_loss_weight_strength": args.target_energy_loss_weight_strength,
                "target_energy_reference_abs_mean": target_energy_reference_abs_mean,
                "sample_balance": args.sample_balance,
                "sample_mode": args.sample_mode,
                "context_padding": args.context_padding,
                "context_mask_prob": args.context_mask_prob,
                "context_mask_block": args.context_mask_block,
                "eval_during_training_rows": args.eval_during_training_rows,
                "save_best_holdout_checkpoint": args.save_best_holdout_checkpoint,
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
        target_policy=args.target_policy,
        noise_threshold_scale=args.noise_threshold_scale,
        device=device,
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
        "device": str(device),
        "train_seconds": train_s,
        "steps": args.steps,
        "config": {
            "feature_mode": args.feature_mode,
            "model_arch": args.model_arch,
            "feature_block": args.feature_block,
            "steps": args.steps,
            "width": args.width,
            "depth": args.depth,
            "residual_scale": args.residual_scale,
            "patch_size": args.patch_size,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "grad_weight": args.grad_weight,
            "target_abs_weight": args.target_abs_weight,
            "band_weight": args.band_weight,
            "band_blocks": band_blocks,
            "spectral_weight": args.spectral_weight,
            "target_policy": args.target_policy,
            "noise_threshold_scale": args.noise_threshold_scale,
            "holdout_scene": args.holdout_scene,
            "holdout_camera": args.holdout_camera,
            "holdout_ev": args.holdout_ev,
            "train_camera": args.train_camera,
            "train_snr_class": args.train_snr_class,
            "snr_loss_weight_policy": args.snr_loss_weight_policy,
            "snr_loss_weight_strength": args.snr_loss_weight_strength,
            "target_energy_loss_weight_policy": args.target_energy_loss_weight_policy,
            "target_energy_loss_weight_strength": args.target_energy_loss_weight_strength,
            "target_energy_reference_abs_mean": target_energy_reference_abs_mean,
            "train_snr_class_counts": {
                key: sum(1 for idx in train_indices if data.target_snr_classes[idx] == key)
                for key in sorted(set(data.target_snr_classes[idx] for idx in train_indices))
            },
            "holdout_snr_class_counts": {
                key: sum(1 for idx in holdout_indices if data.target_snr_classes[idx] == key)
                for key in sorted(set(data.target_snr_classes[idx] for idx in holdout_indices))
            },
            "train_snr_loss_weight_stats": data.snr_loss_weight_stats(
                train_indices,
                args.snr_loss_weight_policy,
                args.snr_loss_weight_strength,
            ),
            "holdout_snr_loss_weight_stats": data.snr_loss_weight_stats(
                holdout_indices,
                args.snr_loss_weight_policy,
                args.snr_loss_weight_strength,
            ),
            "train_target_energy_loss_weight_stats": data.target_energy_loss_weight_stats(
                train_indices,
                args.target_energy_loss_weight_policy,
                args.target_energy_loss_weight_strength,
                target_energy_reference_abs_mean,
            ),
            "holdout_target_energy_loss_weight_stats": data.target_energy_loss_weight_stats(
                holdout_indices,
                args.target_energy_loss_weight_policy,
                args.target_energy_loss_weight_strength,
                target_energy_reference_abs_mean,
            ),
            "sample_balance": args.sample_balance,
            "sample_mode": args.sample_mode,
            "context_padding": args.context_padding,
            "context_mask_prob": args.context_mask_prob,
            "context_mask_block": args.context_mask_block,
            "eval_train_rows": args.eval_train_rows,
            "eval_holdout_rows": args.eval_holdout_rows,
            "eval_during_training_rows": args.eval_during_training_rows,
            "save_best_holdout_checkpoint": args.save_best_holdout_checkpoint,
            "seed": args.seed,
        },
        "policy": {
            "uses_source_raw_at_training": True,
            "uses_source_raw_at_runtime": False,
            "runtime_inputs": runtime_input_summary(args.feature_mode),
            "sample_contract": (
                "training samples are full target crops"
                if args.sample_mode == "full_crop"
                else "training samples are random local patches"
            ),
            "eval_contract": (
                "full train/holdout evaluation"
                if args.eval_train_rows <= 0 and args.eval_holdout_rows <= 0
                else "diagnostic bounded evaluation; use full evaluation before promotion"
            ),
            "model_context_padding_pixels": args.context_padding,
            "training_context_mask": (
                "disabled"
                if args.context_mask_prob <= 0.0
                else f"training-only random candidate detail mask prob={args.context_mask_prob:.3f}, block={args.context_mask_block}px"
            ),
            "production_status": "training_probe_not_registered_production_algorithm",
            "target_policy": args.target_policy,
            "train_snr_class_filter": args.train_snr_class,
            "snr_loss_weight_policy": args.snr_loss_weight_policy,
            "snr_loss_weight_strength": args.snr_loss_weight_strength,
            "target_energy_loss_weight_policy": args.target_energy_loss_weight_policy,
            "target_energy_loss_weight_strength": args.target_energy_loss_weight_strength,
            "holdout_selection_policy": (
                "diagnostic_best_holdout_probe_checkpoint"
                if args.save_best_holdout_checkpoint and best_holdout is not None
                else "final_step_checkpoint"
            ),
        },
        "history": history,
        "best_holdout_probe": best_holdout,
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
    ap.add_argument("--checkpoint-name", default="premium_still_sr_raw_cfa_residual.pt")
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--patch-size", type=int, default=128)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--residual-scale", type=float, default=0.12)
    ap.add_argument(
        "--model-arch",
        choices=("residual", "unet", "rcab_teacher", "naf_teacher", "pyramid_unet", "global_context_unet"),
        default="residual",
        help="Residual keeps the legacy local/dilated stack; unet adds multi-scale encoder/decoder context; rcab_teacher adds residual channel attention and broad context; naf_teacher adds NAFNet-style SimpleGate blocks; pyramid_unet adds a deeper gated full-crop probe; global_context_unet adds a downsampled full-crop context branch.",
    )
    ap.add_argument(
        "--feature-mode",
        choices=(
            "raw",
            "raw_hf",
            "raw_hf_coord_ev_noise",
            "raw_multiscale_coord_ev_noise",
            "raw_framectx_coord_ev_noise",
            "raw_context_coord_ev_noise",
            "raw_context_storedhf_coord_ev_noise",
            "raw_multiscale_storedhf_coord_ev_noise",
        ),
        default="raw_multiscale_coord_ev_noise",
    )
    ap.add_argument("--feature-block", type=int, default=9)
    ap.add_argument("--lr", type=float, default=5.0e-4)
    ap.add_argument("--weight-decay", type=float, default=1.0e-4)
    ap.add_argument("--grad-weight", type=float, default=0.05)
    ap.add_argument("--target-abs-weight", type=float, default=1.0)
    ap.add_argument(
        "--band-weight",
        type=float,
        default=0.0,
        help="Optional multiscale residual-band consistency loss weight. Zero preserves the legacy objective.",
    )
    ap.add_argument(
        "--band-blocks",
        type=int,
        nargs="*",
        default=[9, 27],
        help="Odd-ish lowpass block sizes used by the multiscale residual-band loss.",
    )
    ap.add_argument(
        "--spectral-weight",
        type=float,
        default=0.0,
        help="Optional global FFT-magnitude residual loss weight. Zero preserves the legacy objective.",
    )
    ap.add_argument(
        "--target-policy",
        choices=("raw", "noise_soft_threshold"),
        default="raw",
        help="raw trains against exact source-minus-candidate residual; noise_soft_threshold removes calibrated per-plane noise amplitude first.",
    )
    ap.add_argument("--noise-threshold-scale", type=float, default=1.0)
    ap.add_argument("--grad-clip", type=float, default=1.0)
    ap.add_argument("--holdout-scene")
    ap.add_argument("--holdout-camera")
    ap.add_argument("--holdout-ev", type=float)
    ap.add_argument("--train-camera", help="Restrict training rows to source paths containing this camera/domain token after holdout removal.")
    ap.add_argument(
        "--train-snr-class",
        choices=("all", "signal_dominated", "signal_or_mixed", "not_noise_floor"),
        default="all",
        help="Filter training rows by raw-target SNR class after holdout/camera filtering. Holdout rows are never filtered.",
    )
    ap.add_argument(
        "--snr-loss-weight-policy",
        choices=("none", "noise_floor_downweight", "signal_emphasis", "continuous_snr"),
        default="none",
        help="Per-row loss weighting from calibrated raw-target SNR. Unlike --train-snr-class, this keeps all rows available.",
    )
    ap.add_argument(
        "--snr-loss-weight-strength",
        type=float,
        default=1.0,
        help="Blend strength for --snr-loss-weight-policy. 0 preserves unweighted loss; 1 uses the policy defaults.",
    )
    ap.add_argument(
        "--target-energy-loss-weight-policy",
        choices=("none", "high_energy_emphasis", "inverse_energy"),
        default="none",
        help="Per-row training loss weighting from source residual energy. This is training-only and does not add runtime inputs.",
    )
    ap.add_argument(
        "--target-energy-loss-weight-strength",
        type=float,
        default=1.0,
        help="Blend strength for --target-energy-loss-weight-policy. 0 preserves unweighted loss; 1 uses the policy defaults.",
    )
    ap.add_argument(
        "--sample-balance",
        choices=("row", "camera", "scene"),
        default="row",
        help="Training sampler. row preserves legacy behavior; camera and scene sample groups uniformly before rows.",
    )
    ap.add_argument(
        "--sample-mode",
        choices=("random_patch", "full_crop"),
        default="random_patch",
        help="random_patch preserves legacy local sampling; full_crop trains on whole target crops for detail-placement probes.",
    )
    ap.add_argument(
        "--context-padding",
        type=int,
        default=0,
        help="Candidate raw/HF context pixels added around each training/eval tile; loss and metrics are computed on the center target crop.",
    )
    ap.add_argument(
        "--context-mask-prob",
        type=float,
        default=0.0,
        help="Training-only probability for masking candidate local detail blocks before feature extraction. Evaluation/runtime are unmasked.",
    )
    ap.add_argument(
        "--context-mask-block",
        type=int,
        default=32,
        help="Approximate block size in pixels for --context-mask-prob.",
    )
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--eval-tile", type=int, default=384)
    ap.add_argument(
        "--eval-train-rows",
        type=int,
        default=0,
        help="Diagnostic speed knob. Zero evaluates all train rows; positive values evaluate only the first N train rows.",
    )
    ap.add_argument(
        "--eval-holdout-rows",
        type=int,
        default=0,
        help="Diagnostic speed knob. Zero evaluates all holdout rows; positive values evaluate only the first N holdout rows.",
    )
    ap.add_argument(
        "--eval-during-training-rows",
        type=int,
        default=0,
        help="Diagnostic early-selection knob. Positive values evaluate the first N holdout rows at history steps.",
    )
    ap.add_argument(
        "--save-best-holdout-checkpoint",
        action="store_true",
        help="Save/evaluate the best diagnostic holdout-probe step instead of the final step. Not a production promotion policy.",
    )
    ap.add_argument("--panel-rows", type=int, default=9)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--device", help="Override torch device, for example cpu/mps/cuda.")
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
                "train_median_raw_mae_reduction_pct": receipt["eval"]["train"]["raw_residual_mae_reduction_pct"]["median"],
                "holdout_median_raw_mae_reduction_pct": None if holdout is None else holdout["raw_residual_mae_reduction_pct"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
