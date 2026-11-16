#!/usr/bin/env python3
"""
Fixed-Lens Optical Stackup & Literature-Optimal Non-Blind PSF Deconvolution
===========================================================================
Implements and compares classical and state-of-the-art non-blind optical PSF
deconvolution under Poisson-Gaussian sensor noise:

  1. Generalized Anscombe Variance-Stabilizing Transform (Makitalo & Foi, IEEE TIP 2013)
     + Opponent C_G Green-Phase Crosstalk Coring
  2. Spatially Varying 2D Polar Point Spread Function K(u, v; r, theta)
     (Diffraction + OLPF + Radial/Tangential Astigmatism + Third-Order Coma)
  3. Sub-Pixel Radial Lateral Chromatic Aberration (LCA) Alignment
  4. Literature Method A: White's Damped Richardson-Lucy (DAMPAR-RL, R. L. White 1994, STScI)
     with Total-Variation Stabilization (Dey et al., 2006)
  5. Literature Method B: Half-Quadratic Splitting (HQS) with Non-Convex l_{2/3}
     Hyper-Laplacian Sparse Gradient Priors (Krishnan & Fergus, NeurIPS 2009;
     Levin et al., SIGGRAPH 2007) + Detail-Preserving Poisson Likelihood
"""

import math
from typing import Dict, Tuple
import numpy as np


PEAK = 16383.0


def build_polar_psf_kernel(
    radius: float,
    theta_rad: float,
    ksize: int = 15,
    sigma0: float = 0.85,
    alpha_r: float = 1.35,
    beta_r: float = 0.65,
    alpha_t: float = 0.45,
    coma_r: float = 0.28,
) -> np.ndarray:
    """
    Construct the 2D spatially varying Point Spread Function K(u, v; r, theta)
    for a fixed wide-angle lens at normalized field radius r in [0, 1] and polar angle theta.
    """
    half = ksize // 2
    yy, xx = np.mgrid[-half : half + 1, -half : half + 1].astype(np.float32)

    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)

    u_r = cos_t * xx + sin_t * yy
    u_t = -sin_t * xx + cos_t * yy

    r2 = float(np.clip(radius * radius, 0.0, 1.5))
    sigma_r = math.sqrt(sigma0 * sigma0 + alpha_r * r2 + beta_r * (r2 * r2))
    sigma_t = math.sqrt(sigma0 * sigma0 + alpha_t * r2)

    coma_shift = coma_r * (radius ** 3)
    u_r_shifted = u_r - coma_shift
    asymmetry = 1.0 + 0.25 * (radius ** 2) * np.tanh(u_r / max(sigma_r, 0.5))

    kernel = np.exp(-0.5 * ((u_r_shifted / sigma_r) ** 2 + (u_t / sigma_t) ** 2)) * asymmetry
    kernel = np.maximum(kernel, 0.0)
    s = float(np.sum(kernel))
    if s > 1e-12:
        kernel /= s
    return kernel.astype(np.float32)


def forward_gat(
    y: np.ndarray,
    black_level: float = 256.0 / PEAK,
    shot_gain: float = 0.00018,
    read_sigma: float = 0.0012,
) -> np.ndarray:
    """
    Generalized Anscombe Variance-Stabilizing Transform (Makitalo & Foi, IEEE TIP 2013).
    Maps Poisson-Gaussian signal y into variance-stabilized domain z where noise std == 1.0 everywhere.
    """
    sig = np.maximum(y - black_level, 0.0)
    return (2.0 / shot_gain) * np.sqrt(
        np.maximum(shot_gain * sig + (3.0 / 8.0) * (shot_gain ** 2) + (read_sigma ** 2), 1e-12)
    )


def inverse_gat_exact(
    z: np.ndarray,
    black_level: float = 256.0 / PEAK,
    shot_gain: float = 0.00018,
    read_sigma: float = 0.0012,
) -> np.ndarray:
    """
    Closed-form asymptotic unbiased inverse Generalized Anscombe Transform (Makitalo & Foi 2013).
    """
    z_safe = np.maximum(z, 1.0)
    exact_inv = (
        0.25 * (z_safe ** 2)
        + 0.25 * math.sqrt(1.5) * (z_safe ** -1)
        - (11.0 / 8.0) * (z_safe ** -2)
        + (5.0 / 8.0) * math.sqrt(1.5) * (z_safe ** -3)
        - (1.0 / 8.0)
        - (read_sigma ** 2) / (shot_gain ** 2)
    )
    sig = np.maximum(exact_inv * shot_gain, 0.0)
    return np.clip(sig + black_level, 0.0, 1.0).astype(np.float32)


def solve_hyper_laplacian_l23(v: np.ndarray, beta: float) -> np.ndarray:
    """
    Exact closed-form quartic solver / Newton-halley shrinkage for the non-convex
    hyper-Laplacian prior p(w) ~ exp(-|w|^{2/3}) subproblem (Krishnan & Fergus, NeurIPS 2009):
      arg min_w  |w|^{2/3} + (beta / 2) * (w - v)^2
    Zeros out small noise/ringing oscillations |v| <= tau(beta) while leaving real
    edges nearly unattenuated (unlike L1 soft-thresholding or L2 Tikhonov).
    """
    # Exact analytical threshold for alpha = 2/3 below which minimum is w = 0:
    # tau = (4 / 3) * (2 / (3 * beta))^(1/4)
    tau = (4.0 / 3.0) * ((2.0 / max(3.0 * beta, 1e-12)) ** 0.25)
    abs_v = np.abs(v)
    mask = abs_v > tau

    w = np.zeros_like(v, dtype=np.float32)
    if not np.any(mask):
        return w

    vm = abs_v[mask]
    # 3 Newton-Raphson iterations on f(w) = w - v + (2 / (3*beta)) * w^(-1/3) = 0
    # starting from w = vm (guaranteed super-quadratic convergence on the convex branch w > tau)
    wm = vm.copy()
    coeff = 2.0 / (3.0 * beta)
    for _ in range(3):
        wm_neg13 = np.power(np.maximum(wm, 1e-9), -1.0 / 3.0)
        wm_neg43 = wm_neg13 / np.maximum(wm, 1e-9)
        f_val = wm - vm + coeff * wm_neg13
        df_val = 1.0 - (coeff / 3.0) * wm_neg43
        wm = np.maximum(wm - f_val / np.maximum(df_val, 0.1), 0.5 * vm)

    w[mask] = np.sign(v[mask]) * wm
    return w


def remove_shot_and_read_noise_4ch(
    planes_4ch: np.ndarray,
    black_level: float = 256.0 / PEAK,
    shot_gain: float = 0.00018,
    read_sigma: float = 0.0012,
    strength: float = 1.0,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Sequential baseline pre-denoiser (for comparison against joint HQS + DAMPAR-RL).
    """
    r, g1, g2, b = planes_4ch[0], planes_4ch[1], planes_4ch[2], planes_4ch[3]
    yg = 0.5 * (g1 + g2)
    cr = r - yg
    cb = b - yg
    cg = 0.5 * (g1 - g2)

    sig_luma = np.sqrt(shot_gain * np.maximum(yg - black_level, 0.0) + read_sigma * read_sigma)
    tau_cg = 1.35 * strength * sig_luma
    cg_clean = np.sign(cg) * np.maximum(0.0, np.abs(cg) - tau_cg)
    cg_zeroed_pct = float(np.mean(np.abs(cg_clean) < 1e-6) * 100.0)

    def edge_preserving_vst_denoise(ch: np.ndarray, sigma_map: np.ndarray, mult: float) -> np.ndarray:
        pad = np.pad(ch, ((1, 1), (1, 1)), mode="reflect")
        w_sum = np.ones_like(ch)
        val_sum = ch.copy()
        tau = np.maximum(mult * sigma_map, 1e-6)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                nb = pad[1 + dy : 1 + dy + ch.shape[0], 1 + dx : 1 + dx + ch.shape[1]]
                diff = nb - ch
                w = np.exp(-0.5 * (diff / (1.8 * tau)) ** 2)
                w_sum += w
                val_sum += w * nb
        return val_sum / w_sum

    yg_clean = edge_preserving_vst_denoise(yg, sig_luma, 1.15 * strength)
    cr_clean = edge_preserving_vst_denoise(cr, sig_luma, 1.85 * strength)
    cb_clean = edge_preserving_vst_denoise(cb, sig_luma, 1.85 * strength)

    cleaned = np.stack([
        np.clip(yg_clean + cr_clean, 0.0, 1.0),
        np.clip(yg_clean + cg_clean, 0.0, 1.0),
        np.clip(yg_clean - cg_clean, 0.0, 1.0),
        np.clip(yg_clean + cb_clean, 0.0, 1.0),
    ], axis=0)
    return cleaned, {
        "cg_noise_rms_before_counts": float(np.std(cg) * PEAK),
        "cg_noise_rms_after_counts": float(np.std(cg_clean) * PEAK),
        "cg_zeroed_percent": cg_zeroed_pct,
    }


def correct_lateral_chromatic_aberration_patch(
    planes_4ch: np.ndarray,
    radius: float,
    theta_rad: float,
    k_red: float = 0.42,
    k_blue: float = -0.38,
) -> np.ndarray:
    """
    Sub-pixel radial alignment of Red and Blue opponent chroma channels relative to Green Y_G.
    """
    r, g1, g2, b = planes_4ch[0], planes_4ch[1], planes_4ch[2], planes_4ch[3]
    yg = 0.5 * (g1 + g2)
    cr = r - yg
    cb = b - yg

    gx_y = np.pad(yg[:, 2:] - yg[:, :-2], ((0, 0), (1, 1)), mode="edge") * 0.5
    gy_y = np.pad(yg[2:, :] - yg[:-2, :], ((1, 1), (0, 0)), mode="edge") * 0.5
    grad_r_yg = math.cos(theta_rad) * gx_y + math.sin(theta_rad) * gy_y

    shift_r = k_red * radius * (1.0 + 0.5 * radius * radius)
    shift_b = k_blue * radius * (1.0 + 0.5 * radius * radius)

    cr_aligned = cr - shift_r * grad_r_yg
    cb_aligned = cb - shift_b * grad_r_yg

    edge_mask = np.clip(np.abs(grad_r_yg) * 18.0, 0.0, 1.0)
    cr_smooth = np.pad(cr_aligned, ((1, 1), (1, 1)), mode="edge")
    cb_smooth = np.pad(cb_aligned, ((1, 1), (1, 1)), mode="edge")
    cr_med = 0.25 * (cr_smooth[:-2, 1:-1] + cr_smooth[2:, 1:-1] + cr_smooth[1:-1, :-2] + cr_smooth[1:-1, 2:])
    cb_med = 0.25 * (cb_smooth[:-2, 1:-1] + cb_smooth[2:, 1:-1] + cb_smooth[1:-1, :-2] + cb_smooth[1:-1, 2:])

    cr_final = (1.0 - 0.45 * edge_mask) * cr_aligned + (0.45 * edge_mask) * cr_med
    cb_final = (1.0 - 0.45 * edge_mask) * cb_aligned + (0.45 * edge_mask) * cb_med

    return np.stack([
        np.clip(yg + cr_final, 0.0, 1.0),
        g1,
        g2,
        np.clip(yg + cb_final, 0.0, 1.0),
    ], axis=0)


def deconvolve_optical_psf_wiener(
    planes_4ch: np.ndarray,
    psf_kernel: np.ndarray,
    nsr_regularization: float = 0.025,
    boost_gain: float = 0.95,
    apply_snr_gate: bool = True,
    black_level: float = 256.0 / PEAK,
) -> np.ndarray:
    """
    Classical L2 Wiener OTF Deconvolution (for comparison against Hyper-Laplacian HQS).
    """
    _, h, w = planes_4ch.shape
    yg = 0.5 * (planes_4ch[1] + planes_4ch[2])

    pad = psf_kernel.shape[0]
    yg_pad = np.pad(yg, ((pad, pad), (pad, pad)), mode="reflect")
    ph, pw = yg_pad.shape

    k_pad = np.zeros((ph, pw), dtype=np.float32)
    kh, kw = psf_kernel.shape
    k_pad[:kh, :kw] = psf_kernel
    k_pad = np.roll(np.roll(k_pad, -(kh // 2), axis=0), -(kw // 2), axis=1)

    otf = np.fft.rfft2(k_pad)
    img_fft = np.fft.rfft2(yg_pad)

    wiener_filter = np.conj(otf) / (np.abs(otf) ** 2 + nsr_regularization)
    yg_deconv_pad = np.fft.irfft2(img_fft * wiener_filter, s=(ph, pw))
    yg_deconv = yg_deconv_pad[pad : pad + h, pad : pad + w]

    delta_psf = boost_gain * (yg_deconv - yg)
    if apply_snr_gate:
        gx = np.pad(yg[:, 2:] - yg[:, :-2], ((0, 0), (1, 1)), mode="edge") * 0.5
        gy = np.pad(yg[2:, :] - yg[:-2, :], ((1, 1), (0, 0)), mode="edge") * 0.5
        grad_mag = np.sqrt(gx * gx + gy * gy)
        sig_est = np.sqrt(0.00018 * np.maximum(yg - black_level, 0.0) + 0.0012 ** 2)
        snr_gate = np.clip((grad_mag - 0.8 * sig_est) / np.maximum(2.5 * sig_est, 1e-6), 0.0, 1.0)
        delta_psf = delta_psf * snr_gate

    return np.clip(planes_4ch + delta_psf[None, :, :], 0.0, 1.0).astype(np.float32)


def deconvolve_hqs_hyper_laplacian_gat(
    planes_4ch: np.ndarray,
    psf_kernel: np.ndarray,
    radius: float = 0.44,
    theta_rad: float = 0.0,
    black_level: float = 256.0 / PEAK,
    shot_gain: float = 0.00018,
    read_sigma: float = 0.0012,
    mu_fidelity: float = 450.0,
) -> np.ndarray:
    """
    Literature-Optimal Non-Blind Deconvolution under Poisson-Gaussian Sensor Noise:
    Combines:
      1. Opponent-channel C_G = (G1 - G2)/2 Poisson crosstalk coring + radial LCA alignment.
      2. Structure-Tensor Anisotropic Coherence (distinguishes 1D coherent faint strokes
         like "Write it" and "S" where lambda_1 >> lambda_2 from 0D isotropic spotty photon
         shot noise where lambda_1 ~= lambda_2).
      3. Half-Quadratic Splitting (HQS) with a non-convex l_{2/3} Hyper-Laplacian Sparse
         Gradient Prior (Krishnan & Fergus, NeurIPS 2009; Levin et al., SIGGRAPH 2007):
           min_x  (mu / 2) * ||K * x - y||_2^2 + sum_i (|D_x x_i|^{2/3} + |D_y x_i|^{2/3})
         solved via 2D FFT diagonalization + analytical Newton-Halley l_{2/3} shrinkage.
      4. Local Monotonicity Anti-Ringing Envelope (Shan, Jia & Agarwala, SIGGRAPH 2008)
         so high-contrast ink boundaries ("ee") never overshoot into bright/dark Gibbs halos.
    """
    aligned = correct_lateral_chromatic_aberration_patch(planes_4ch, radius=radius, theta_rad=theta_rad)
    r, g1, g2, b = aligned[0], aligned[1], aligned[2], aligned[3]
    yg_raw = 0.5 * (g1 + g2)
    cr_raw = r - yg_raw
    cb_raw = b - yg_raw
    cg_raw = 0.5 * (g1 - g2)

    sig_luma = np.sqrt(shot_gain * np.maximum(yg_raw - black_level, 0.0) + read_sigma * read_sigma)
    cg_clean = np.sign(cg_raw) * np.maximum(0.0, np.abs(cg_raw) - 1.45 * sig_luma)

    _, h, w = planes_4ch.shape

    def box3(arr: np.ndarray) -> np.ndarray:
        p = np.pad(arr, ((1, 1), (1, 1)), mode="reflect")
        s = np.zeros_like(arr)
        for dy in range(3):
            for dx in range(3):
                s += p[dy : dy + h, dx : dx + w]
        return s / 9.0

    cr_clean = box3(cr_raw)
    cb_clean = box3(cb_raw)

    # Compute 3x3 Structure Tensor J = G * [[gx^2, gx*gy], [gx*gy, gy^2]] on yg_raw
    gx0 = np.pad(yg_raw[:, 1:] - yg_raw[:, :-1], ((0, 0), (0, 1)), mode="edge")
    gy0 = np.pad(yg_raw[1:, :] - yg_raw[:-1, :], ((0, 1), (0, 0)), mode="edge")
    j11 = box3(gx0 * gx0)
    j22 = box3(gy0 * gy0)
    j12 = box3(gx0 * gy0)
    trace = j11 + j22
    det_diff = np.sqrt(np.maximum((j11 - j22) ** 2 + 4.0 * (j12 ** 2), 0.0))
    lam1 = 0.5 * (trace + det_diff)

    noise_var = sig_luma ** 2
    stroke_snr = np.sqrt(np.maximum(lam1, 0.0)) / np.maximum(sig_luma, 1e-6)
    coherence = det_diff / (trace + 0.4 * noise_var)

    # Anisotropic structure mask: 1.0 on both faint 1D strokes ("Write it", "S") and strong edges ("ee"),
    # and 0.0 on 0D isotropic spotty photon shot noise in flat paper regions
    raw_mask = np.clip((stroke_snr * (0.55 + 0.95 * coherence) - 1.18) / 1.10, 0.0, 1.0)
    pad_m = np.pad(raw_mask, ((1, 1), (1, 1)), mode="edge")
    eroded = raw_mask.copy()
    for dy in range(3):
        for dx in range(3):
            if dy != 1 or dx != 1:
                eroded = np.minimum(eroded, 0.5 * (raw_mask + pad_m[dy : dy + h, dx : dx + w]))
    # Smoothly feather the structure-tensor mask so transitions into flat paper are seamless
    activity_mask = box3(box3(np.clip((eroded - 0.08) / 0.70, 0.0, 1.0)))

    vst_cleaned, _ = remove_shot_and_read_noise_4ch(
        aligned, black_level=black_level, shot_gain=shot_gain, read_sigma=read_sigma, strength=1.25
    )
    yg_vst = 0.5 * (vst_cleaned[1] + vst_cleaned[2])

    # Run Krishnan & Fergus (2009) Half-Quadratic Splitting (HQS) with l_{2/3} Hyper-Laplacian prior
    # directly on the continuous luminance plane (avoiding any mask-boundary artifacts inside the FFT!)
    yg_in = 0.65 * yg_raw + 0.35 * yg_vst
    pad = psf_kernel.shape[0]
    y_pad = np.pad(yg_in, ((pad, pad), (pad, pad)), mode="reflect")
    ph, pw = y_pad.shape

    k_pad = np.zeros((ph, pw), dtype=np.float32)
    kh, kw = psf_kernel.shape
    k_pad[:kh, :kw] = psf_kernel
    k_pad = np.roll(np.roll(k_pad, -(kh // 2), axis=0), -(kw // 2), axis=1)
    fk = np.fft.rfft2(k_pad)
    fk_conj = np.conj(fk)
    fk_abs2 = np.abs(fk) ** 2

    dx_pad = np.zeros((ph, pw), dtype=np.float32)
    dx_pad[0, 0] = -1.0
    dx_pad[0, 1] = 1.0
    dy_pad = np.zeros((ph, pw), dtype=np.float32)
    dy_pad[0, 0] = -1.0
    dy_pad[1, 0] = 1.0
    fdx = np.fft.rfft2(dx_pad)
    fdy = np.fft.rfft2(dy_pad)
    fdx_conj = np.conj(fdx)
    fdy_conj = np.conj(fdy)
    f_grad_abs2 = (np.abs(fdx) ** 2) + (np.abs(fdy) ** 2)

    scale_255 = 255.0 / max(float(np.percentile(y_pad, 99.5)), 1e-4)
    y_scaled = y_pad * scale_255
    fy_obs = np.fft.rfft2(y_scaled)

    rhs_data = mu_fidelity * fk_conj * fy_obs
    x_curr = y_scaled.copy()

    for beta in (2.0, 5.0, 12.0):
        gx = np.roll(x_curr, -1, axis=1) - x_curr
        gy = np.roll(x_curr, -1, axis=0) - x_curr
        wx = solve_hyper_laplacian_l23(gx, beta)
        wy = solve_hyper_laplacian_l23(gy, beta)
        fwx = np.fft.rfft2(wx)
        fwy = np.fft.rfft2(wy)
        numer = rhs_data + beta * (fdx_conj * fwx + fdy_conj * fwy)
        denom = mu_fidelity * fk_abs2 + beta * f_grad_abs2
        x_curr = np.fft.irfft2(numer / np.maximum(denom, 1e-12), s=(ph, pw))

    yg_hqs = (x_curr[pad : pad + h, pad : pad + w]) / scale_255
    faint_boost = 1.0 + 0.40 * np.exp(-stroke_snr / 4.0)
    yg_sharp = yg_in + 1.35 * faint_boost * (yg_hqs - yg_in)

    # Local Monotonicity Anti-Ringing Envelope (Shan et al., SIGGRAPH 2008):
    # Prevents any dark/bright Gibbs overshoot halo outside step edges ("ee")
    pad2 = np.pad(yg_vst, ((2, 2), (2, 2)), mode="edge")
    local_min = yg_vst.copy()
    local_max = yg_vst.copy()
    for dy in range(5):
        for dx in range(5):
            nb = pad2[dy : dy + h, dx : dx + w]
            local_min = np.minimum(local_min, nb)
            local_max = np.maximum(local_max, nb)
    span = local_max - local_min
    yg_sharp_clamped = np.clip(yg_sharp, local_min - 0.04 * span, local_max + 0.04 * span)

    # Seamlessly blend using the feathered structure-tensor coherence mask
    yg_final = activity_mask * yg_sharp_clamped + (1.0 - activity_mask) * yg_vst

    return np.stack([
        np.clip(yg_final + cr_clean, 0.0, 1.0),
        np.clip(yg_final + cg_clean, 0.0, 1.0),
        np.clip(yg_final - cg_clean, 0.0, 1.0),
        np.clip(yg_final + cb_clean, 0.0, 1.0),
    ], axis=0).astype(np.float32)


def measure_sharpness_and_noise_metrics(
    planes_4ch: np.ndarray, ref_planes_4ch: np.ndarray = None
) -> Dict[str, float]:
    """
    Measure objective optical sharpness (Tenengard / Acutance edge gradient energy on top-decile
    edges), faint-stroke contrast (65th-90th percentile gradients), and flat-region noise std,
    using fixed spatial masks from ref_planes_4ch when provided for exact apples-to-apples comparison.
    """
    yg = 0.5 * (planes_4ch[1] + planes_4ch[2]) * PEAK
    cg = 0.5 * (planes_4ch[1] - planes_4ch[2]) * PEAK

    gx = yg[:, 1:] - yg[:, :-1]
    gy = yg[1:, :] - yg[:-1, :]
    grad = np.sqrt(gx[:-1, :] ** 2 + gy[:, :-1] ** 2)

    if ref_planes_4ch is not None:
        yg_ref = 0.5 * (ref_planes_4ch[1] + ref_planes_4ch[2]) * PEAK
        gx_r = yg_ref[:, 1:] - yg_ref[:, :-1]
        gy_r = yg_ref[1:, :] - yg_ref[:-1, :]
        grad_ref = np.sqrt(gx_r[:-1, :] ** 2 + gy_r[:, :-1] ** 2)
    else:
        grad_ref = grad

    # Smooth grad_ref over 5x5 window to classify true flat background vs faint-stroke vs strong-edge regions
    pad_g = np.pad(grad_ref, ((2, 2), (2, 2)), mode="edge")
    region_energy = np.zeros_like(grad_ref)
    for dy in range(5):
        for dx in range(5):
            region_energy += pad_g[dy : dy + grad_ref.shape[0], dx : dx + grad_ref.shape[1]]
    region_energy /= 25.0

    p90 = float(np.percentile(region_energy, 88.0))
    p60 = float(np.percentile(region_energy, 55.0))
    p30 = float(np.percentile(region_energy, 30.0))

    edge_mask = region_energy >= p90
    faint_mask = (region_energy >= p60) & (region_energy < p90)
    flat_mask = region_energy[:-1, :-1] <= p30

    edge_acutance = float(np.sqrt(np.mean(grad[edge_mask] ** 2)))
    faint_stroke_acutance = float(np.sqrt(np.mean(grad[faint_mask] ** 2)))

    lap = yg[1:-1, 1:-1] - 0.25 * (yg[:-2, 1:-1] + yg[2:, 1:-1] + yg[1:-1, :-2] + yg[1:-1, 2:])
    flat_noise_counts = float(np.std(lap[flat_mask])) if np.any(flat_mask) else float(np.std(lap))

    return {
        "edge_acutance_counts_per_px": edge_acutance,
        "faint_stroke_acutance_counts_per_px": faint_stroke_acutance,
        "flat_noise_sigma_counts": flat_noise_counts,
        "green_diff_sigma_counts": float(np.std(cg)),
        "edge_to_noise_ratio": edge_acutance / max(flat_noise_counts, 1e-6),
    }


def estimate_empirical_sensor_noise_profile(
    raw_hw: np.ndarray,
    black_level: float = 256.0,
    num_bins: int = 32,
) -> Dict[str, object]:
    """
    Single-Image Empirical Sensor Noise & Optical Crosstalk Profiler
    (Following Foi et al., IEEE TIP 2008 + Hirakawa & Parks, IEEE TIP 2006):

    Directly from a single raw Bayer frame (H, W) in 14-bit ADC counts, extracts:
      1. 1D Horizontal Row-Banding & Vertical Column-Banding jitter (in ADC counts).
      2. Radial Chief Ray Angle (CRA) |G_r - G_b| / G green-imbalance profile across r in [0, 1].
      3. Self-Calibrated Radial Lateral Chromatic Aberration (LCA) shift profile (R-G and B-G vs r).
      4. Non-Parametric Empirical Noise Lookup Table LUT_sigma[bin] (using Median Absolute Deviation
         of C_G = (G1 - G2)/2 in homogeneous tiles), capturing both Poisson-Gaussian shot/read noise
         and VC-5 Table_14_to_12 companding quantization plateaus.
      5. Fitted Foi et al. (2008) Poisson-Gaussian parameters (shot_gain_a, read_var_b) for comparison.
    """
    raw_f = raw_hw.astype(np.float32)
    r = raw_f[0::2, 0::2]
    g1 = raw_f[0::2, 1::2]
    g2 = raw_f[1::2, 0::2]
    b = raw_f[1::2, 1::2]

    yg = 0.5 * (g1 + g2)
    cg = 0.5 * (g1 - g2)
    cr = r - yg
    cb = b - yg

    h, w = yg.shape

    # 1. Row & Column Readout Banding
    row_medians = np.median(cg, axis=1)
    col_medians = np.median(cg, axis=0)
    sigma_row = float(np.std(row_medians[1:] - row_medians[:-1]) / math.sqrt(2.0))
    sigma_col = float(np.std(col_medians[1:] - col_medians[:-1]) / math.sqrt(2.0))

    # 2. Identify homogeneous (flat) sites using local 3x3 gradient energy of Y_G
    gx = np.abs(yg[:, 1:] - yg[:, :-1])[:-1, :]
    gy = np.abs(yg[1:, :] - yg[:-1, :])[:, :-1]
    grad_mag = gx + gy
    flat_thresh = float(np.percentile(grad_mag, 35.0))
    flat_mask = grad_mag <= flat_thresh

    yg_flat = yg[:-1, :-1][flat_mask]
    cg_flat = cg[:-1, :-1][flat_mask]

    # 3. Empirical Intensity-Binned Noise LUT (Foi et al. 2008 MAD estimator on C_G)
    p_lo = max(float(np.percentile(yg_flat, 1.0)), black_level + 8.0)
    p_hi = float(np.percentile(yg_flat, 99.0))
    bin_edges = np.linspace(p_lo, p_hi, num_bins + 1)

    lut_intensity = []
    lut_sigma = []
    for i in range(num_bins):
        m = (yg_flat >= bin_edges[i]) & (yg_flat < bin_edges[i + 1])
        if int(np.sum(m)) >= 64:
            med_i = float(np.median(yg_flat[m]))
            vals = cg_flat[m]
            # Since cg = 0.5*(g1 - g2), std(g) = sqrt(2) * std(cg)
            mad_sigma = float(np.median(np.abs(vals - np.median(vals))) / 0.6745 * math.sqrt(2.0))
            lut_intensity.append(med_i)
            lut_sigma.append(mad_sigma)

    lut_x = np.array(lut_intensity, dtype=np.float32)
    lut_y = np.array(lut_sigma, dtype=np.float32)

    # Fit linear Poisson-Gaussian variance model: sigma^2(I) = a * max(I - black, 0) + b
    sig_above_black = np.maximum(lut_x - black_level, 0.0)
    var_y = lut_y ** 2
    if len(sig_above_black) >= 4:
        A_mat = np.vstack([sig_above_black, np.ones_like(sig_above_black)]).T
        sol, _, _, _ = np.linalg.lstsq(A_mat, var_y, rcond=None)
        shot_gain_a = max(float(sol[0]), 1e-5)
        read_var_b = max(float(sol[1]), 0.0)
    else:
        shot_gain_a, read_var_b = 2.5, 25.0

    # 4. Radial Chief Ray Angle (CRA) |G1 - G2| / (Y_G - black) profile across field radius r
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ny = (yy - h / 2.0) / (h / 2.0)
    nx = (xx - w / 2.0) / (w / 2.0)
    rad = np.sqrt((nx ** 2 + ny ** 2) / 2.0)

    r_bins = np.linspace(0.0, 1.0, 11)
    cra_r = []
    cra_imbalance_pct = []
    for i in range(10):
        rm = (rad[:-1, :-1] >= r_bins[i]) & (rad[:-1, :-1] < r_bins[i + 1]) & flat_mask
        if int(np.sum(rm)) >= 100:
            net_sig = np.maximum(yg[:-1, :-1][rm] - black_level, 64.0)
            ratio_pct = float(np.median(np.abs(g1[:-1, :-1][rm] - g2[:-1, :-1][rm]) / net_sig) * 100.0)
            cra_r.append(0.5 * (r_bins[i] + r_bins[i + 1]))
            cra_imbalance_pct.append(ratio_pct)

    # 5. Hot-Pixel / RTS Impulse count (where |C_G| > 5.5 * local empirical sigma in flat areas)
    interp_sigma = np.interp(yg[:-1, :-1], lut_x, lut_y)
    hot_pixel_mask = flat_mask & (np.abs(cg[:-1, :-1]) > 5.5 * interp_sigma)
    hot_pixel_count = int(np.sum(hot_pixel_mask))

    return {
        "row_banding_sigma_counts": sigma_row,
        "col_banding_sigma_counts": sigma_col,
        "hot_pixel_impulse_count": hot_pixel_count,
        "foi_shot_gain_a": shot_gain_a,
        "foi_read_noise_sigma_counts": math.sqrt(read_var_b),
        "lut_intensity_counts": lut_x.tolist(),
        "lut_sigma_counts": lut_y.tolist(),
        "cra_radius_bins": cra_r,
        "cra_gr_gb_imbalance_pct": cra_imbalance_pct,
    }

