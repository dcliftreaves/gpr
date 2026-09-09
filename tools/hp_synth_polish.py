"""Deterministic deblock polish for the GPR codec's LL-only-fast output.

Synthesizes plausible high-frequency texture into the codec's missing wavelet
HP bands via bandpass-on-edge noise injection. Targets the spectral mid-band
that the LP-only 5/3 synthesis filter loses by construction.

Why this isn't "just noise injection":
  - The codec's LL-only-fast path discards LH/HL/HH wavelet bands entirely.
    The inverse wavelet with HP=0 produces a soft, characteristically-blocky
    output (the 5/3 LP synthesis impulse response on the LL grid).
  - A spectrum analysis (see this session's subagent investigations) showed
    the codec output is MISSING mid-frequency energy (0.1-0.5 band has 0.01x
    source energy) — NOT excess Nyquist energy as a naive "blockiness reads
    as high-freq" intuition would suggest.
  - Injecting random texture INTO the discarded HP bands fills that
    mid-frequency gap with plausible content. The eye reads mid-freq grain
    as natural; the eye reads flat mid-freq as "blocky".

Key design constraints (learned the hard way during this session):
  - PEAK noise injection at MODERATE edges, NOT at hard edges. Hard edges
    have huge local gradient; if noise scales monotonically with std/grad,
    you get speckles along silhouettes. A Gaussian BANDPASS on gradient
    magnitude does the right thing: zero in flat regions (no spurious grain
    in sky), peak at the gradient percentile where LL-only loses real
    detail, rolls off at extreme gradients (silhouettes stay clean).
  - Noise must be IDENTICAL across the 4 Bayer planes per-position. Using
    different RNG per plane creates chroma fringing after demosaic.

Cost: ~400 ms in Python on M-series; ~50-100 ms achievable in NEON C.

Defaults validated visually on Z8_ISO64 (iso64_LLonly.raw):
    peak_pct=45  — peak at the 45th percentile of LL gradient (just-above-
                   median gradient = where moderate detail lives)
    sigma_pct=15 — Gaussian rolloff width
    scale=0.5    — overall noise magnitude
"""
import sys
import os
import argparse
import numpy as np
import cv2
from scipy.ndimage import uniform_filter


# 5/3 biorthogonal wavelet forward/inverse, single-level.
# Matches the encoder's `horizontal_filter` / `vertical_filter_quantize_row`
# kernels in source/lib/vc5_encoder/fused_encode.c so the round-trip is
# consistent with the codec's own analysis filter.

def forward_53_2d(x):
    """5/3 forward, 1 level. x: (H, W) int. Returns LL, LH, HL, HH each (H/2, W/2)."""
    h, w = x.shape
    h2, w2 = h // 2, w // 2
    x = x.astype(np.int64)
    e = x[:, 0::2]
    o = x[:, 1::2]
    lp = e + o
    e_prev = np.roll(lp, 1, axis=1); e_prev[:, 0] = lp[:, 0]
    e_next = np.roll(lp, -1, axis=1); e_next[:, -1] = lp[:, -1]
    hp = ((e_next - e_prev + 4) >> 3) + (e - o)
    lp = lp[:, :w2]
    hp = hp[:, :w2]
    e2 = lp[0::2, :]
    o2 = lp[1::2, :]
    LL = (e2 + o2)
    e2p = np.roll(LL, 1, axis=0); e2p[0, :] = LL[0, :]
    e2n = np.roll(LL, -1, axis=0); e2n[-1, :] = LL[-1, :]
    LH = ((e2n - e2p + 4) >> 3) + (e2 - o2)
    LL = LL[:h2, :]
    LH = LH[:h2, :]
    e2 = hp[0::2, :]; o2 = hp[1::2, :]
    HL = (e2 + o2)
    e2p = np.roll(HL, 1, axis=0); e2p[0, :] = HL[0, :]
    e2n = np.roll(HL, -1, axis=0); e2n[-1, :] = HL[-1, :]
    HH = ((e2n - e2p + 4) >> 3) + (e2 - o2)
    HL = HL[:h2, :]
    HH = HH[:h2, :]
    return LL, LH, HL, HH


def inverse_53_2d(LL, LH, HL, HH):
    """5/3 inverse, 1 level. Each band (H/2, W/2). Returns (H, W) int."""
    h2, w2 = LL.shape
    h, w = h2 * 2, w2 * 2
    LL = LL.astype(np.int64); LH = LH.astype(np.int64)
    HL = HL.astype(np.int64); HH = HH.astype(np.int64)
    lp = np.zeros((h, w2), dtype=np.int64)
    hp = np.zeros((h, w2), dtype=np.int64)
    LL_p = np.roll(LL, 1, axis=0); LL_p[0, :] = LL[0, :]
    LL_n = np.roll(LL, -1, axis=0); LL_n[-1, :] = LL[-1, :]
    even = (((LL_p - LL_n + 4) >> 3) + LH + LL) >> 1
    odd  = (((LL_n - LL_p + 4) >> 3) - LH + LL) >> 1
    lp[0::2, :] = even
    lp[1::2, :] = odd
    HL_p = np.roll(HL, 1, axis=0); HL_p[0, :] = HL[0, :]
    HL_n = np.roll(HL, -1, axis=0); HL_n[-1, :] = HL[-1, :]
    even = (((HL_p - HL_n + 4) >> 3) + HH + HL) >> 1
    odd  = (((HL_n - HL_p + 4) >> 3) - HH + HL) >> 1
    hp[0::2, :] = even
    hp[1::2, :] = odd
    out = np.zeros((h, w), dtype=np.int64)
    lp_p = np.roll(lp, 1, axis=1); lp_p[:, 0] = lp[:, 0]
    lp_n = np.roll(lp, -1, axis=1); lp_n[:, -1] = lp[:, -1]
    even = (((lp_p - lp_n + 4) >> 3) + hp + lp) >> 1
    odd  = (((lp_n - lp_p + 4) >> 3) - hp + lp) >> 1
    out[:, 0::2] = even
    out[:, 1::2] = odd
    return out


def deinterleave_bayer(bayer):
    return (bayer[0::2, 0::2], bayer[0::2, 1::2],
            bayer[1::2, 0::2], bayer[1::2, 1::2])


def reinterleave_bayer(R, G1, G2, B):
    h, w = R.shape
    out = np.zeros((h * 2, w * 2), dtype=np.int64)
    out[0::2, 0::2] = R; out[0::2, 1::2] = G1
    out[1::2, 0::2] = G2; out[1::2, 1::2] = B
    return out


def synthesize_hp_bandpass(LL, scale=0.5, seed=0,
                           peak_pct=45, sigma_pct=15):
    """Bandpass-on-edge noise for HP bands.

    Weight = Gaussian on gradient magnitude centered at the peak_pct
    percentile, falling off both ways (toward flat AND toward hard edges).
    Times a clamped local std (so flat regions truly get 0). All 4 Bayer
    planes use the same seed -> identical noise per-position -> no chroma
    fringing from per-plane decorrelation.
    """
    rng = np.random.RandomState(seed)
    LL_f = LL.astype(np.float64)
    LL_32 = LL_f.astype(np.float32)
    gx = cv2.Sobel(LL_32, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(LL_32, cv2.CV_64F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)
    grad_peak  = np.percentile(grad, peak_pct)
    grad_sigma = max(np.percentile(grad, peak_pct + sigma_pct) - grad_peak, 1e-6)
    weight = np.exp(-0.5 * ((grad - grad_peak) / grad_sigma) ** 2)
    mean = uniform_filter(LL_f, size=5)
    var = np.maximum(uniform_filter(LL_f * LL_f, size=5) - mean ** 2, 0)
    std = np.sqrt(var)
    std_clipped = np.minimum(std, np.percentile(std, 90))
    std_eff = weight * std_clipped
    LH = (rng.randn(*LL.shape) * std_eff * scale).astype(np.int64)
    HL = (rng.randn(*LL.shape) * std_eff * scale).astype(np.int64)
    HH = (rng.randn(*LL.shape) * std_eff * scale * 0.5).astype(np.int64)
    return LH, HL, HH


def polish(codec_bayer, scale=0.5, peak_pct=45, sigma_pct=15, seed=0):
    """Apply the polish to a decoded codec Bayer (RGGB, u16). Returns u16 Bayer
    with synthesized HP added."""
    h, w = codec_bayer.shape
    bayer_int = codec_bayer.astype(np.int64)
    R, G1, G2, B = deinterleave_bayer(bayer_int)
    outs = []
    for ch in (R, G1, G2, B):
        LL, _, _, _ = forward_53_2d(ch)
        LH, HL, HH = synthesize_hp_bandpass(LL, scale=scale, peak_pct=peak_pct,
                                            sigma_pct=sigma_pct, seed=seed)
        out = inverse_53_2d(LL, LH, HL, HH)[:ch.shape[0], :ch.shape[1]]
        outs.append(out)
    final = reinterleave_bayer(*outs)
    return np.clip(final, 0, 16383).astype(np.uint16)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codec-raw", required=True,
                    help="input codec Bayer u16 LE (LL-only-decoded)")
    ap.add_argument("--codec-w", type=int, required=True)
    ap.add_argument("--codec-h", type=int, required=True)
    ap.add_argument("--out-raw", required=True,
                    help="output polished Bayer u16 LE")
    ap.add_argument("--peak-pct", type=float, default=45,
                    help="gradient percentile where noise injection peaks "
                         "(40-60 reasonable; smaller=more conservative)")
    ap.add_argument("--sigma-pct", type=float, default=15,
                    help="Gaussian rolloff width in percentile units")
    ap.add_argument("--scale", type=float, default=0.5,
                    help="overall noise magnitude (0.3-0.8)")
    ap.add_argument("--seed", type=int, default=0,
                    help="RNG seed (kept identical across the 4 Bayer planes "
                         "so noise correlates → no chroma fringing)")
    args = ap.parse_args()

    bayer = np.fromfile(args.codec_raw, dtype=np.uint16).reshape(args.codec_h,
                                                                   args.codec_w)
    out = polish(bayer, scale=args.scale, peak_pct=args.peak_pct,
                 sigma_pct=args.sigma_pct, seed=args.seed)
    out.tofile(args.out_raw)
    print(f"wrote {args.out_raw}  shape={out.shape}  "
          f"peak_pct={args.peak_pct} sigma_pct={args.sigma_pct} scale={args.scale}")


if __name__ == "__main__":
    main()
