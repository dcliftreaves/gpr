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
    low = F.avg_pool2d(F.pad(x, (pad, pad, pad, pad), mode="reflect"), block, stride=1)
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


def make_features(
    raw: torch.Tensor,
    feature_mode: str,
    block: int,
    ev: torch.Tensor | None = None,
    noise: torch.Tensor | None = None,
    stored_hf: torch.Tensor | None = None,
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
        "raw_context_coord_ev_noise": 35,
        "raw_multiscale_storedhf_coord_ev_noise": 27,
    }[feature_mode]


def gradient_l1(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.l1_loss(pred[:, :, :, 1:] - pred[:, :, :, :-1], target[:, :, :, 1:] - target[:, :, :, :-1]) + F.l1_loss(
        pred[:, :, 1:, :] - pred[:, :, :-1, :],
        target[:, :, 1:, :] - target[:, :, :-1, :],
    )


def residual_loss(pred: torch.Tensor, target: torch.Tensor, *, target_abs_weight: float) -> torch.Tensor:
    weight = torch.ones_like(target[:, 0:1])
    if target_abs_weight > 0.0:
        target_abs = torch.mean(torch.abs(target), dim=1, keepdim=True)
        weight = weight + float(target_abs_weight) * torch.clamp(target_abs / 0.03, 0.0, 5.0)
    weight = weight / torch.mean(weight).clamp_min(1.0e-6)
    return torch.mean(torch.abs(pred - target) * weight)


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
        for row in self.rows:
            sidecars = row.get("noise_sidecars", [])
            sidecar = str(sidecars[0]) if isinstance(sidecars, list) and sidecars else ""
            if sidecar and sidecar not in cache:
                cache[sidecar] = load_noise_feature_from_sidecar(sidecar)
                sigma_cache[sidecar] = load_noise_sigma4_from_sidecar(sidecar)
            self.noise_features.append(cache.get(sidecar, (0.0, 0.0, 0.0, 0.0)))
            self.noise_sigma4.append(sigma_cache.get(sidecar, (0.0, 0.0, 0.0, 0.0)))

    def row_indices(self, holdout_scene: str | None, holdout_camera: str | None, holdout_ev: float | None) -> tuple[list[int], list[int]]:
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
        if (holdout_scene or holdout_camera or holdout_ev is not None) and (not train or not holdout):
            raise ValueError(f"holdout split produced train={len(train)} holdout={len(holdout)}")
        return train, holdout

    def sample_batch(
        self,
        indices: list[int],
        batch_size: int,
        patch_size: int,
        rng: random.Random,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor | None]:
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        hfs: list[np.ndarray] = []
        evs: list[float] = []
        noises: list[tuple[float, float, float, float]] = []
        sigmas: list[tuple[float, float, float, float]] = []
        h, w = self.candidate_raw.shape[1:3]
        patch = min(patch_size, h, w)
        for _ in range(batch_size):
            idx = rng.choice(indices)
            y0 = rng.randrange(0, h - patch + 1) if h > patch else 0
            x0 = rng.randrange(0, w - patch + 1) if w > patch else 0
            xs.append(self.candidate_raw[idx, y0 : y0 + patch, x0 : x0 + patch].transpose(2, 0, 1))
            ys.append(self.target[idx, y0 : y0 + patch, x0 : x0 + patch].transpose(2, 0, 1))
            if self.candidate_raw_hf is not None:
                hfs.append(self.candidate_raw_hf[idx, y0 : y0 + patch, x0 : x0 + patch].transpose(2, 0, 1))
            evs.append(float(self.rows[idx].get("ev", 0.0)))
            noises.append(self.noise_features[idx])
            sigmas.append(self.noise_sigma4[idx])
        return (
            torch.from_numpy(np.stack(xs)),
            torch.from_numpy(np.stack(ys)),
            torch.tensor(evs, dtype=torch.float32),
            torch.tensor(noises, dtype=torch.float32),
            torch.tensor(sigmas, dtype=torch.float32),
            torch.from_numpy(np.stack(hfs)) if hfs else None,
        )


@torch.no_grad()
def eval_rows(
    model: RawCfaResidualNet,
    data: RawCfaResidualTargets,
    indices: list[int],
    *,
    feature_mode: str,
    feature_block: int,
    target_policy: str,
    noise_threshold_scale: float,
    device: torch.device,
    tile: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    model.eval()
    for idx in indices:
        raw = torch.from_numpy(data.candidate_raw[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        raw_target = torch.from_numpy(data.target[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
        ev = torch.tensor([float(data.rows[idx].get("ev", 0.0))], dtype=torch.float32, device=device)
        noise = torch.tensor([data.noise_features[idx]], dtype=torch.float32, device=device)
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
        for y0 in range(0, height, tile):
            for x0 in range(0, width, tile):
                raw_tile = raw[:, :, y0 : y0 + tile, x0 : x0 + tile]
                hf_tile = stored_hf[:, :, y0 : y0 + tile, x0 : x0 + tile] if stored_hf is not None else None
                pred[:, :, y0 : y0 + tile, x0 : x0 + tile] = model(
                    make_features(raw_tile, feature_mode, feature_block, ev, noise, hf_tile)
                )
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
    model: RawCfaResidualNet,
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
        sigma = torch.tensor([data.noise_sigma4[idx]], dtype=torch.float32, device=device)
        stored_hf = (
            torch.from_numpy(data.candidate_raw_hf[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            if data.candidate_raw_hf is not None
            else None
        )
        pred = model(make_features(raw, feature_mode, feature_block, ev, noise, stored_hf)).squeeze(0).cpu().numpy().transpose(1, 2, 0)
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
    data = RawCfaResidualTargets(args.targets)
    if args.feature_mode == "raw_multiscale_storedhf_coord_ev_noise" and data.candidate_raw_hf is None:
        raise ValueError("raw_multiscale_storedhf_coord_ev_noise requires candidate_raw_hf_cfa4 in the target NPZ")
    train_indices, holdout_indices = data.row_indices(args.holdout_scene, args.holdout_camera, args.holdout_ev)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device) if args.device else DEVICE
    model = RawCfaResidualNet(
        in_channels=feature_channels(args.feature_mode),
        width=args.width,
        depth=args.depth,
        residual_scale=args.residual_scale,
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        x, y, ev, noise, sigma, stored_hf = data.sample_batch(train_indices, args.batch_size, args.patch_size, rng)
        x = x.to(device)
        y = y.to(device)
        ev = ev.to(device)
        noise = noise.to(device)
        sigma = sigma.to(device)
        stored_hf = stored_hf.to(device) if stored_hf is not None else None
        y = apply_target_policy(
            y,
            sigma,
            target_policy=args.target_policy,
            noise_threshold_scale=args.noise_threshold_scale,
        )
        pred = model(make_features(x, args.feature_mode, args.feature_block, ev, noise, stored_hf))
        loss = residual_loss(pred, y, target_abs_weight=args.target_abs_weight) + args.grad_weight * gradient_l1(pred, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
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
        target_policy=args.target_policy,
        noise_threshold_scale=args.noise_threshold_scale,
        device=device,
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
            target_policy=args.target_policy,
            noise_threshold_scale=args.noise_threshold_scale,
            device=device,
            tile=args.eval_tile,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / args.checkpoint_name
    torch.save(
        {
            "schema": SCHEMA,
            "state_dict": model.state_dict(),
            "config": {
                "feature_mode": args.feature_mode,
                "feature_block": args.feature_block,
                "width": args.width,
                "depth": args.depth,
                "residual_scale": args.residual_scale,
                "target_abs_weight": args.target_abs_weight,
                "target_policy": args.target_policy,
                "noise_threshold_scale": args.noise_threshold_scale,
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
            "feature_block": args.feature_block,
            "width": args.width,
            "depth": args.depth,
            "residual_scale": args.residual_scale,
            "patch_size": args.patch_size,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "grad_weight": args.grad_weight,
            "target_abs_weight": args.target_abs_weight,
            "target_policy": args.target_policy,
            "noise_threshold_scale": args.noise_threshold_scale,
            "holdout_scene": args.holdout_scene,
            "holdout_camera": args.holdout_camera,
            "holdout_ev": args.holdout_ev,
            "seed": args.seed,
        },
        "policy": {
            "uses_source_raw_at_training": True,
            "uses_source_raw_at_runtime": False,
            "runtime_inputs": "candidate_raw_cfa4 + candidate_raw_highpass + deterministic coordinates/EV + camera/ISO noise sidecar scalars",
            "production_status": "training_probe_not_registered_production_algorithm",
            "target_policy": args.target_policy,
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
    ap.add_argument("--checkpoint-name", default="premium_still_sr_raw_cfa_residual.pt")
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--patch-size", type=int, default=128)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--residual-scale", type=float, default=0.12)
    ap.add_argument(
        "--feature-mode",
        choices=(
            "raw",
            "raw_hf",
            "raw_hf_coord_ev_noise",
            "raw_multiscale_coord_ev_noise",
            "raw_context_coord_ev_noise",
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
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--eval-tile", type=int, default=384)
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
