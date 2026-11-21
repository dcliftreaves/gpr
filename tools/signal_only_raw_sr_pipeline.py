#!/usr/bin/env python3
"""Experimental RGGB14 restoration primitives.

Noise estimates and generated grain are approximations, not recovery of the
original noise. File round trips live in signal_raw.py. No camera deployment
or quality approval is implied by this model/checkpoint.
"""

import math
import numpy as np

from optical_psf_deconvolution import (
    PEAK,
)


def box_2x2_downsample_4ch(planes_50mp: np.ndarray) -> np.ndarray:
    """Exact 2x2 same-color Bayer binning from 50MP (4, 3072, 4096) to 12MP (4, 1536, 2048)."""
    return 0.25 * (
        planes_50mp[:, 0::2, 0::2]
        + planes_50mp[:, 0::2, 1::2]
        + planes_50mp[:, 1::2, 0::2]
        + planes_50mp[:, 1::2, 1::2]
    ).astype(np.float32)


def box_2x2_consistent_upsample_4ch(
    planes_12mp: np.ndarray, bicubic_50mp: np.ndarray
) -> np.ndarray:
    """
    Enforce exact Box-2x2 cell-mean consistency on a 2x upsampled 50MP tensor:
      AvgPool_2x2(out_50mp) == planes_12mp identically (0.0000 cell-mean error).
    """
    bic_cell_mean = box_2x2_downsample_4ch(bicubic_50mp)
    cell_error = planes_12mp - bic_cell_mean
    err_nearest = np.repeat(np.repeat(cell_error, 2, axis=1), 2, axis=2)
    return bounded_cell_consistent_4ch(bicubic_50mp + err_nearest, planes_12mp)


def project_zero_dc_residual_2x2(residual_50mp: np.ndarray) -> np.ndarray:
    """
    Algebraic Zero-DC Orthogonal Projection on any 2x super-resolution residual:
    Subtracts the 2x2 block average so every 2x2 super-pixel residual sums to 0.0000.
    """
    block_mean = box_2x2_downsample_4ch(residual_50mp)
    mean_nearest = np.repeat(np.repeat(block_mean, 2, axis=1), 2, axis=2)
    return (residual_50mp - mean_nearest).astype(np.float32)


def bounded_cell_consistent_4ch(proposal: np.ndarray, low: np.ndarray) -> np.ndarray:
    """Preserve cell means and bounds together, including black/saturated cells.

    Redistribute mean error in proportion to each sample's available headroom.
    This is a bounded consistency correction, not a Euclidean projection.
    """
    if proposal.shape != (low.shape[0], low.shape[1] * 2, low.shape[2] * 2):
        raise ValueError("incompatible high/low geometry")
    if (
        not np.isfinite(proposal).all()
        or not np.isfinite(low).all()
        or np.any((low < 0) | (low > 1))
    ):
        raise ValueError("requires finite proposal and normalized low samples")
    out = np.clip(proposal.astype(np.float64), 0, 1)
    mean = 0.25 * sum(out[:, y::2, x::2] for y in range(2) for x in range(2))
    error = low.astype(np.float64) - mean
    for y in range(2):
        for x in range(2):
            v = out[:, y::2, x::2]
            capacity = np.where(error >= 0, 1 - v, v)
            average_capacity = np.where(error >= 0, 1 - mean, mean)
            v += error * capacity / np.maximum(average_capacity, 1e-30)
    return np.clip(out, 0, 1).astype(np.float32)


def bounded_cell_consistent_torch(proposal, low):
    import torch
    import torch.nn.functional as F

    out = proposal.clamp(0, 1)
    mean = F.avg_pool2d(out, 2)
    error = low - mean
    positive = F.interpolate((error >= 0).to(out.dtype), scale_factor=2, mode="nearest")
    capacity = torch.where(positive.bool(), 1 - out, out)
    average_capacity = torch.where(error >= 0, 1 - mean, mean).clamp_min(1e-12)
    adjustment = F.interpolate(error / average_capacity, scale_factor=2, mode="nearest")
    return (out + adjustment * capacity).clamp(0, 1)


def quantize_cell_consistent_4ch(
    high: np.ndarray, low_counts: np.ndarray
) -> np.ndarray:
    """Balanced integer rounding; every four high samples sum to 4*low_count."""
    out = bounded_cell_consistent_4ch(high, low_counts.astype(np.float64) / PEAK)
    cells = np.stack(
        [out[:, y::2, x::2] * PEAK for y in range(2) for x in range(2)], axis=-1
    ).astype(np.float64)
    floors = np.floor(cells).astype(np.int32)
    difference = 4 * low_counts.astype(np.int32) - floors.sum(axis=-1)
    fractions = cells - floors
    up = np.argsort(
        -np.where(floors < PEAK, fractions, -np.inf), axis=-1, kind="stable"
    )
    down = np.argsort(np.where(floors > 0, fractions, np.inf), axis=-1, kind="stable")
    if np.any(np.abs(difference) > 4):
        raise ValueError("rounding correction exceeds cell capacity")
    for k in range(4):
        idx = up[..., k : k + 1]
        value = np.take_along_axis(floors, idx, axis=-1)
        np.put_along_axis(floors, idx, value + (difference > k)[..., None], axis=-1)
        idx = down[..., k : k + 1]
        value = np.take_along_axis(floors, idx, axis=-1)
        np.put_along_axis(floors, idx, value - (-difference > k)[..., None], axis=-1)
    result = np.empty_like(out, dtype=np.uint16)
    for i, (y, x) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        result[:, y::2, x::2] = floors[..., i]
    return result


def synthesize_empirical_sensor_grain_4ch(
    clean_planes_4ch, noise_profile, strength=1.0, seed=42, frame_index=0, origin=(0, 0)
):
    """Optional Gaussian texture, not reconstruction of the discarded noise.

    Independent Bayer-site innovations; coordinate-keyed randomness makes crops
    and tiles deterministic while frame_index prevents fixed-pattern movies.
    The intensity-conditioned sigma estimate does not establish a full sensor
    covariance or Poisson law. No unmeasured OLPF correlation is imposed.
    """
    clean = np.asarray(clean_planes_4ch, dtype=np.float32)
    if clean.ndim != 3 or clean.shape[0] != 4 or not np.isfinite(clean).all():
        raise ValueError("requires four finite Bayer planes")
    if (
        not math.isfinite(strength)
        or strength < 0
        or not 0 <= seed < 2**64
        or not 0 <= frame_index < 2**64
    ):
        raise ValueError("invalid grain strength/seed/frame")
    lut_x = np.asarray(noise_profile["lut_intensity_counts"], dtype=np.float64)
    lut_y = np.asarray(noise_profile["lut_sigma_counts"], dtype=np.float64)
    if (
        not len(lut_x)
        or lut_x.shape != lut_y.shape
        or not np.isfinite(lut_x).all()
        or not np.isfinite(lut_y).all()
        or np.any(lut_y < 0)
        or np.any(np.diff(lut_x) <= 0)
    ):
        raise ValueError("requires a finite, ordered noise LUT")
    _, h, w = clean.shape
    yy, xx = np.mgrid[origin[0] : origin[0] + h, origin[1] : origin[1] + w].astype(
        np.uint64
    )

    def mix(z):
        with np.errstate(over="ignore"):
            z = (z ^ (z >> 30)) * np.uint64(0xBF58476D1CE4E5B9)
            z = (z ^ (z >> 27)) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> 31)

    grain = np.empty_like(clean)
    with np.errstate(over="ignore"):
        keys = (
            np.uint64(seed)
            ^ (np.uint64(frame_index) * np.uint64(0x9E3779B97F4A7C15))
            ^ (yy * np.uint64(0xD6E8FEB86659FD93))
            ^ (xx * np.uint64(0xA0761D6478BD642F))
        )
        for c in range(4):
            key = keys ^ (np.uint64(c + 1) * np.uint64(0xE7037ED1A0B428DB))
            u = ((mix(key) >> 11).astype(np.float64) + 0.5) / 2**53
            v = (
                (mix(key ^ np.uint64(0x8EBC6AF09C88C6E3)) >> 11).astype(np.float64)
                + 0.5
            ) / 2**53
            normal = np.sqrt(-2 * np.log(u)) * np.cos(2 * np.pi * v)
            sigma = np.interp(clean[c] * PEAK, lut_x, lut_y) * strength / PEAK
            grain[c] = normal * sigma
    result = np.clip(clean + grain, 0, 1).astype(np.float32)
    return result, (grain * PEAK).astype(np.float32)


def build_large_area_wavelet_sr_model(width: int = 80, depth: int = 4):
    """
    Architecture of the shipped 388,500-parameter exploratory checkpoint.
    The original nominal 138-pixel context claim is not independently certified.
    Pooling requires global phase alignment during tiled execution.
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class MultiScaleDilatedWaveletBlock(nn.Module):
        def __init__(self, w: int):
            super().__init__()
            hw = w // 4
            self.b1 = nn.Conv2d(w, hw, 3, padding=1, dilation=1)
            self.b2 = nn.Conv2d(w, hw, 3, padding=3, dilation=3)
            self.b3 = nn.Conv2d(w, hw, 3, padding=7, dilation=7)
            self.b4 = nn.Conv2d(w, w - 3 * hw, 3, padding=1)
            self.act = nn.GELU()
            self.proj = nn.Conv2d(w, w, 1)
            self.gamma = nn.Parameter(torch.full((1, w, 1, 1), 0.25))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            o1 = self.b1(x)
            o2 = self.b2(x)
            o3 = self.b3(x)
            x_low = F.avg_pool2d(x, kernel_size=4, stride=4)
            o4 = F.interpolate(
                self.b4(x_low), size=x.shape[-2:], mode="bilinear", align_corners=False
            )
            cat = self.act(torch.cat([o1, o2, o3, o4], dim=1))
            return x + self.gamma * self.proj(cat)

    class Mission1LargeAreaWaveletSR(nn.Module):
        def __init__(self, w: int = 80, d: int = 4):
            super().__init__()
            self.stem = nn.Sequential(nn.Conv2d(14, w, 3, padding=1), nn.GELU())
            self.blocks = nn.ModuleList(
                [MultiScaleDilatedWaveletBlock(w) for _ in range(d)]
            )
            self.up_conv = nn.Sequential(
                nn.Conv2d(w, w * 2, 1),
                nn.GELU(),
                nn.Conv2d(w * 2, 16 * 4, 3, padding=1),
                nn.PixelShuffle(2),
            )
            self.hr_refine = nn.Sequential(
                nn.Conv2d(16 + 4, 32, 3, padding=1),
                nn.GELU(),
                nn.Conv2d(32, 32, 3, padding=1),
                nn.GELU(),
                nn.Conv2d(32, 4, 3, padding=1),
            )

        def forward(
            self, x_4ch: torch.Tensor, coords_2ch: torch.Tensor
        ) -> torch.Tensor:
            original_h, original_w = x_4ch.shape[-2:]
            padding = (0, (-original_w) % 4, 0, (-original_h) % 4)
            x_4ch = F.pad(x_4ch, padding, mode="replicate")
            coords_2ch = F.pad(coords_2ch, padding, mode="replicate")
            bic = F.interpolate(
                x_4ch, scale_factor=2, mode="bicubic", align_corners=False
            )
            cell_err = x_4ch - F.avg_pool2d(bic, kernel_size=2, stride=2)
            box_base = bic + F.interpolate(cell_err, scale_factor=2, mode="nearest")

            r, g1, g2, b = x_4ch[:, 0:1], x_4ch[:, 1:2], x_4ch[:, 2:3], x_4ch[:, 3:4]
            yg = 0.5 * (g1 + g2)
            cr = r - yg
            cb = b - yg
            cg = 0.5 * (g1 - g2)
            gx = F.pad(yg[:, :, :, 2:] - yg[:, :, :, :-2], (1, 1, 0, 0)) * 0.5
            gy = F.pad(yg[:, :, 2:, :] - yg[:, :, :-2, :], (0, 0, 1, 1)) * 0.5
            lap = yg - F.avg_pool2d(yg, kernel_size=3, stride=1, padding=1)
            r2 = 0.5 * (coords_2ch[:, 0:1] ** 2 + coords_2ch[:, 1:2] ** 2)

            feat_in = torch.cat(
                [x_4ch, yg, cr, cb, cg, gx, gy, lap, r2, coords_2ch], dim=1
            )
            h = self.stem(feat_in)
            for blk in self.blocks:
                h = blk(h)
            hr_feat = self.up_conv(h)
            raw_delta = self.hr_refine(torch.cat([hr_feat, box_base], dim=1))
            delta_dc = F.avg_pool2d(raw_delta, kernel_size=2, stride=2)
            delta_zero_dc = raw_delta - F.interpolate(
                delta_dc, scale_factor=2, mode="nearest"
            )
            return bounded_cell_consistent_torch(box_base + delta_zero_dc, x_4ch)[
                :, :, : original_h * 2, : original_w * 2
            ]

    return Mission1LargeAreaWaveletSR(width, depth)


def restore_tiled(planes, model, tile=128, halo=64, device="cpu", telemetry=None):
    """Globally phase-aligned pooling and sufficient halo; balanced count output.

    Inputs are four uint16 RGGB14 site planes. No physical-sensor/VC-5 LL1
    equivalence is assumed. The conserved measurement is the decoded input.
    """
    import torch

    if (
        planes.ndim != 3
        or planes.shape[0] != 4
        or planes.dtype != np.uint16
        or np.any(planes > PEAK)
    ):
        raise ValueError("requires four uint16 RGGB14 site planes")
    if tile < 4 or tile % 4 or halo < 64 or halo % 4:
        raise ValueError(
            "tile must be divisible by 4; halo must be >=64 and divisible by 4"
        )
    _, h, w = planes.shape
    result = np.empty((4, h * 2, w * 2), dtype=np.uint16)
    model = model.to(device).eval()
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            y1, x1 = min(y + tile, h), min(x + tile, w)
            ya, xa = max(0, y - halo), max(0, x - halo)
            yb, xb = min(h, y1 + halo), min(w, x1 + halo)
            coords = np.empty((2, yb - ya, xb - xa), dtype=np.float32)
            coords[0] = np.linspace(-1, 1, w, dtype=np.float32)[None, xa:xb]
            coords[1] = np.linspace(-1, 1, h, dtype=np.float32)[ya:yb, None]
            source = torch.from_numpy(
                planes[:, ya:yb, xa:xb].astype(np.float32) / PEAK
            )[None].to(device)
            with torch.inference_mode():
                out = (
                    model(source, torch.from_numpy(coords)[None].to(device))[0]
                    .cpu()
                    .numpy()
                )
            if telemetry is not None and device == "mps":
                observed = int(torch.mps.driver_allocated_memory())
                telemetry["max_observed_mps_driver_bytes"] = max(
                    telemetry.get("max_observed_mps_driver_bytes", 0), observed
                )
            core = out[:, 2 * (y - ya) : 2 * (y1 - ya), 2 * (x - xa) : 2 * (x1 - xa)]
            result[:, 2 * y : 2 * y1, 2 * x : 2 * x1] = quantize_cell_consistent_4ch(
                core, planes[:, y:y1, x:x1]
            )
    return result
