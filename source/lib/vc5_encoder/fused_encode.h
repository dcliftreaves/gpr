/*! @file fused_encode.h
 *
 *  @brief Fused encoder: Bayer→Wavelet→Quantize→FreqCount in one streaming pass.
 *
 *  Replaces the 4-stage serial pipeline with a 2-pass fused design:
 *  Pass 1: Stream Bayer pixels through log curve → horizontal filter → vertical
 *          filter + quantize, with optional inline tokenization (embedded mode).
 *  Pass 2: rANS encode using per-band (or per-stripe) frequency tables.
 *
 *  Designed for GoPro ARM (Cortex-A78), testable on Mac ARM64.
 *
 *  ## Wavelet levels
 *
 *  The encoder applies a 2-level wavelet transform by default
 *  (FUSED_WAVELET_LEVELS=2). The bitstream per channel is:
 *    [0..3] LL1, LH1, HL1, HH1   (level-1 bands, 1/16 of channel pixels each)
 *    [4..6] LH0, HL0, HH0        (level-0 highpass, 1/4 of channel pixels each)
 *  LL0 is computed without quantization as an intermediate buffer and is
 *  NOT emitted in the bitstream — the four level-1 bands together
 *  represent the level-0 lowpass.
 *
 *  Set FUSED_WAVELET_LEVELS=1 at compile time to fall back to the original
 *  single-level layout (LL0, LH0, HL0, HH0 per channel).
 *
 *  Production GPR uses 3 levels with a fixed-width LL encoding (separate
 *  from rANS, lossless). The 2-level fused encoder gets within ~30-50 %
 *  of production's compression at substantially higher throughput and
 *  lower peak RAM. PSNR vs raw Bayer at quality 3 is ~45 dB on real
 *  images, vs ~48 dB for single-level (which trades size for fidelity).
 *
 *  Measured at quality 3 (Filmscan-1):
 *
 *    Input              | Standard GPR | Fused split | Fused stripe
 *    -------------------+--------------+-------------+--------------
 *    HERO10 23 MP 14-bit| ~4-6 MB      |  5.4 MB     |  4.4 MB
 *    MISSION 1 50 MP    | n/a yet      | 11.7 MB     | 10.5 MB
 *    X2D 100 MP 16-bit  |  23.5 MB     | 55.8 MB     | 46.4 MB
 *
 *  (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifndef FUSED_ENCODE_H
#define FUSED_ENCODE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*!
    @brief Fused encode: raw Bayer pixels → VC5 bitstream.

    Two-pass design:
    Pass 1: Fused unpack→wavelet→quantize→frequency count (no intermediate arrays)
    Pass 2: rANS encode using counted frequencies

    @param raw_bayer    Raw Bayer pixel data (uint16_t interleaved)
    @param raw_size     Size of raw data in bytes
    @param width        Image width in pixels
    @param height       Image height in pixels
    @param pixel_format 0=RGGB12, 1=RGGB14, 2=GBRG12, 3=GBRG14, 4=RGGB16, 5=GBRG16
    @param quality      Quality preset (0-8, default 3 = Filmscan-1)
    @param vc5_out      Output: allocated VC5 bitstream (caller must free)
    @param vc5_size     Output: size of VC5 bitstream
    @return 0 on success, -1 on error
*/
int gpr_encode_fused(
    const uint8_t *raw_bayer,
    size_t raw_size,
    int width, int height,
    int pixel_format,
    int quality,
    uint8_t **vc5_out,
    size_t *vc5_size
);

/*!
    @brief Reusable encoder context for video / batch encoding.

    Pre-allocates band buffers, row buffers, and the output stream buffer.
    Subsequent encode_frame calls touch already-faulted pages, eliminating
    the ~5ms-per-frame calloc+page-fault cost.

    Single-thread is the embedded baseline; the same context works with
    parallel mode (the FUSED_THREADS=1 env var still selects serial).

    Lifetime:
        ctx = gpr_encode_fused_create(width, height, pixel_format, quality);
        for each frame: gpr_encode_fused_frame(ctx, raw, ...);
        gpr_encode_fused_destroy(ctx);
*/
typedef struct FUSED_ENCODER FUSED_ENCODER;

FUSED_ENCODER *gpr_encode_fused_create(
    int width, int height,
    int pixel_format,
    int quality);

/*! Encode one frame using a pre-allocated context.
    @param ctx        Encoder context from gpr_encode_fused_create().
    @param raw_bayer  Raw input pixels (uint16_t interleaved).
    @param raw_size   Size of raw data in bytes.
    @param vc5_out    Output pointer (points into ctx-owned buffer; do not free).
    @param vc5_size   Output: size of VC5 bitstream.
    @return 0 on success, -1 on error.
*/
int gpr_encode_fused_frame(
    FUSED_ENCODER *ctx,
    const uint8_t *raw_bayer,
    size_t raw_size,
    uint8_t **vc5_out,
    size_t *vc5_size);

void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);

/*!
    @brief Enable wavelet-domain BayesShrink denoise on the fused encoder.

    Operates on each highpass band between Pass 1 (wavelet+quantize) and
    Pass 2 (tokenize+rANS), thresholding noise-dominated coefficients.
    Measured on the production-encoder equivalent: 3-38% file-size win
    at SSIM 0.9998, signal-detail preserved.

    Enabling denoise forces split-pass mode (the band buffer must exist
    for per-band threshold estimation). With strength=0 (default) the
    encoder behaves as before.

    @param ctx           Encoder context from gpr_encode_fused_create().
    @param noise_scale   Poisson noise component in raw-pixel units
                         (multiply DNG NoiseProfile scale by max_val).
                         Pass 0 to use MAD-based auto-estimation per band.
    @param noise_offset  Gaussian noise component in raw-pixel units
                         (multiply DNG NoiseProfile offset by max_val^2).
    @param strength      Threshold multiplier [0.0-1.0]. 0 disables denoise.
                         1.0 = full BayesShrink strength.
*/
void gpr_encode_fused_set_denoise(FUSED_ENCODER *ctx,
                                  double noise_scale,
                                  double noise_offset,
                                  double strength);

/*!
    @brief Per-frame quantization scale knob for rate control.

    Multiplies the base quality preset's divisors by @p scale. Larger
    scale → coarser quantization → smaller output. Clamped to a sane
    range; the encoder won't crash on extreme values, just produce
    very bad output.

    Intended for use by a rate controller (e.g. gpr_video_encoder)
    between frames to hit a target bitrate independent of scene
    content. Safe to call at any time but only takes effect on the
    next frame's encode.

    @param scale   1.0 = base quality preset, 2.0 = double the divisor
                   (≈ one quality preset coarser), 0.5 = halve the
                   divisor (≈ one preset finer). Clamped to [0.25, 16].
*/
void gpr_encode_fused_set_quant_scale(FUSED_ENCODER *ctx, double scale);

#ifdef __cplusplus
}
#endif

#endif /* FUSED_ENCODE_H */
