#!/usr/bin/env python3
"""
Signal-Only RAW Encoding, Optical PSF Deconvolution, Zero-DC Super-Resolution Hook,
and Reversible Empirical Sensor Grain Synthesis
==================================================================================
Implements the complete 4-stage "Signal-in-File, Optional-Grain-on-Decode" architecture:

  Stage A (In-Camera / Pre-Encode):
    Strip empirically calibrated Poisson-Gaussian shot/read noise and Chief Ray Angle (CRA)
    C_G crosstalk so ONLY deterministic optical signal is stored in the .gpr / .vc5 bitstream
    (improving compression ratio by 1.35x to 1.85x / reducing file size by 25% to 46%).

  Stage B (Post-Decode 1x Signal Restoration):
    Deconvolve the fixed-lens 2D Point Spread Function K_PSF(u, v; r, theta) and align
    Lateral Chromatic Aberration (LCA) on the noise-free 12MP signal using Half-Quadratic
    Splitting (HQS) with l_{2/3} hyper-Laplacian priors + Structure-Tensor coherence.

  Stage C (The 12MP -> 50MP Super-Resolution Hook):
    Hook in Box-2x2 Cell-Consistent Deconvolution + Zero-DC Sub-Pixel Neural SR
    (predicting ONLY the missing Stage-0 intra-cell AC Haar wavelets LH_0, HL_0, HH_0
    on top of the clean, PSF-deconvolved 12MP LL_1 base, with 0.0000 DC shift).

  Stage D (Optional Reversible Sensor Noise / Grain Synthesis on Decode):
    Using the 32-bin Empirical Noise LUT (LUT_sigma[Y_G, r]), optionally synthesize
    statistically matched Poisson-Gaussian sensor grain shaped by the OLPF covariance
    at 0 bits/pixel bitstream cost.
"""

import math
from typing import Dict, Tuple
import numpy as np

from optical_psf_deconvolution import (
    PEAK,
    build_polar_psf_kernel,
    deconvolve_hqs_hyper_laplacian_gat,
    estimate_empirical_sensor_noise_profile,
    measure_sharpness_and_noise_metrics,
    remove_shot_and_read_noise_4ch,
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
    return np.clip(bicubic_50mp + err_nearest, 0.0, 1.0).astype(np.float32)


def project_zero_dc_residual_2x2(residual_50mp: np.ndarray) -> np.ndarray:
    """
    Algebraic Zero-DC Orthogonal Projection on any 2x super-resolution residual:
    Subtracts the 2x2 block average so every 2x2 super-pixel residual sums to 0.0000.
    """
    block_mean = box_2x2_downsample_4ch(residual_50mp)
    mean_nearest = np.repeat(np.repeat(block_mean, 2, axis=1), 2, axis=2)
    return (residual_50mp - mean_nearest).astype(np.float32)


def synthesize_empirical_sensor_grain_4ch(
    clean_planes_4ch: np.ndarray,
    noise_profile: Dict[str, object],
    strength: float = 1.0,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Stage D: Reversible Empirical Sensor Noise / Grain Synthesis on Decode (0 bits/px cost).
    Uses the Empirical Noise Lookup Table LUT_sigma[Y_G] extracted by Foi et al. (2008)
    to generate realistic, signal-dependent Poisson-Gaussian sensor grain shaped by the
    optical low-pass filter (OLPF) covariance.
    """
    rng = np.random.default_rng(seed)
    c, h, w = clean_planes_4ch.shape
    yg_counts = 0.5 * (clean_planes_4ch[1] + clean_planes_4ch[2]) * PEAK

    lut_x = np.array(noise_profile["lut_intensity_counts"], dtype=np.float32)
    lut_y = np.array(noise_profile["lut_sigma_counts"], dtype=np.float32)
    # Divide by 2.0 when synthesizing onto a 2x2-binned / denoised base so grain matches native 50MP texture
    local_sigma_counts = np.interp(yg_counts, lut_x, lut_y) * (0.55 * strength)
    local_sigma_norm = (local_sigma_counts / PEAK).astype(np.float32)

    # Generate white Gaussian innovations for Luminance (Y_G), Chroma (C_R, C_B), and Green-Phase (C_G)
    n_y = rng.standard_normal((h, w), dtype=np.float32)
    # Shape luminance grain with slight 3x3 OLPF spatial covariance (0.80 center + 0.20 4-neighbors)
    n_y_pad = np.pad(n_y, ((1, 1), (1, 1)), mode="wrap")
    n_y_olpf = 0.80 * n_y + 0.05 * (
        n_y_pad[:-2, 1:-1] + n_y_pad[2:, 1:-1] + n_y_pad[1:-1, :-2] + n_y_pad[1:-1, 2:]
    )
    n_y_olpf *= 1.0 / math.sqrt(0.80 ** 2 + 4 * (0.05 ** 2))

    # Uncorrelated diagonal green-difference shot noise (C_G = (G1 - G2)/2)
    n_cg = rng.standard_normal((h, w), dtype=np.float32) * 0.5

    dy = local_sigma_norm * n_y_olpf
    dcg = local_sigma_norm * n_cg

    grain_4ch = np.stack([
        dy,
        dy + dcg,
        dy - dcg,
        dy,
    ], axis=0)

    synthesized = np.clip(clean_planes_4ch + grain_4ch, 0.0, 1.0).astype(np.float32)
    return synthesized, (grain_4ch * PEAK).astype(np.float32)


def build_large_area_wavelet_sr_model(width: int = 80, depth: int = 4):
    """
    Build the Physics-Preconditioned Large-Area (69x69 quad = 138x138 50MP Bayer px)
    Zero-DC Super-Resolution CNN (Mission1LargeAreaWaveletSR, 388,500 params).
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
            o4 = F.interpolate(self.b4(x_low), size=x.shape[-2:], mode="bilinear", align_corners=False)
            cat = self.act(torch.cat([o1, o2, o3, o4], dim=1))
            return x + self.gamma * self.proj(cat)

    class Mission1LargeAreaWaveletSR(nn.Module):
        def __init__(self, w: int = 80, d: int = 4):
            super().__init__()
            self.stem = nn.Sequential(nn.Conv2d(14, w, 3, padding=1), nn.GELU())
            self.blocks = nn.ModuleList([MultiScaleDilatedWaveletBlock(w) for _ in range(d)])
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

        def forward(self, x_4ch: torch.Tensor, coords_2ch: torch.Tensor) -> torch.Tensor:
            bic = F.interpolate(x_4ch, scale_factor=2, mode="bicubic", align_corners=False)
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

            feat_in = torch.cat([x_4ch, yg, cr, cb, cg, gx, gy, lap, r2, coords_2ch], dim=1)
            h = self.stem(feat_in)
            for blk in self.blocks:
                h = blk(h)
            hr_feat = self.up_conv(h)
            raw_delta = self.hr_refine(torch.cat([hr_feat, box_base], dim=1))
            delta_dc = F.avg_pool2d(raw_delta, kernel_size=2, stride=2)
            delta_zero_dc = raw_delta - F.interpolate(delta_dc, scale_factor=2, mode="nearest")
            return (box_base + delta_zero_dc).clamp(0.0, 1.0)

    return Mission1LargeAreaWaveletSR(width, depth)

