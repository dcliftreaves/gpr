/*! @file fused_encode.c
 *
 *  @brief Fused encoder: Bayer→Wavelet→Quantize→FreqCount in one streaming pass.
 *
 *  Pass 1: For each row pair of the input image:
 *    1. Load Bayer pixels, apply log curve → GS, RG, BG, GD
 *    2. Horizontal wavelet filter into 6-row circular buffer
 *    3. When 6 rows available: vertical filter + quantize → band output
 *    4. Inline: count symbol frequencies for ANS encoding
 *
 *  Pass 2: For each band:
 *    1. Build rANS table from counted frequencies
 *    2. Re-scan band data for tokens, rANS encode
 *
 *  This eliminates 4 × 11MB intermediate component arrays and fuses
 *  the 144ms tokenization pass into the wavelet output path.
 *
 *  (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#include "headers.h"
#include "fused_encode.h"
#include "ans_joint.h"
#include "denoise.h"
#include <pthread.h>
#include <unistd.h>  /* for sysconf */

#define FUSED_TIMING
#define FUSED_TIMING_DETAIL

#if defined(FUSED_TIMING) || defined(FUSED_TIMING_DETAIL)
#include <mach/mach_time.h>
static double _fused_ms(void) {
    static double s = 0;
    if (!s) { mach_timebase_info_data_t i; mach_timebase_info(&i); s = (double)i.numer/i.denom/1e6; }
    return mach_absolute_time() * s;
}
#endif

#if ENABLED(NEON)
#include <arm_neon.h>
#endif

/* ================================================================
   FUSED_LOG_POLYNOMIAL — compile-time switch for replacing the
   scalar LUT gather inside unpack_channel_row() with a NEON
   polynomial approximation of the log curve.

   On M1 (128 KB L1d) the LUT fits comfortably and the LUT path is
   faster. Enable this on Cortex-A78 (64 KB L1d, LUT thrashes with
   other working data) where polynomial wins by 1.5-2x. Default OFF
   so M1 builds remain unchanged.

   Polynomial accuracy: validated to <=1 LSB max error vs LUT across
   the full 14- and 16-bit input range (see /tmp/test_log_approx.c).
   ================================================================ */
#if defined(FUSED_LOG_POLYNOMIAL) && ENABLED(NEON)
#include <math.h>  /* log2f */

/* log2(m) for m in [1, 2) via series in u = (m-1)/(m+1), |u| <= 1/3. */
static inline float32x4_t fused_vlog2q_mant(float32x4_t m) {
    float32x4_t mm1 = vsubq_f32(m, vdupq_n_f32(1.0f));
    float32x4_t mp1 = vaddq_f32(m, vdupq_n_f32(1.0f));
    /* 1 / (m+1) via 2 Newton-Raphson refinements on vrecpeq estimate */
    float32x4_t inv = vrecpeq_f32(mp1);
    inv = vmulq_f32(inv, vrecpsq_f32(mp1, inv));
    inv = vmulq_f32(inv, vrecpsq_f32(mp1, inv));
    float32x4_t u  = vmulq_f32(mm1, inv);
    float32x4_t u2 = vmulq_f32(u, u);
    /* 1 + u²/3 + u⁴/5 + u⁶/7 + u⁸/9 + u¹⁰/11 */
    float32x4_t p = vfmaq_f32(vdupq_n_f32(1.0f / 9.0f),  u2, vdupq_n_f32(1.0f / 11.0f));
    p = vfmaq_f32(vdupq_n_f32(1.0f / 7.0f),  u2, p);
    p = vfmaq_f32(vdupq_n_f32(1.0f / 5.0f),  u2, p);
    p = vfmaq_f32(vdupq_n_f32(1.0f / 3.0f),  u2, p);
    p = vfmaq_f32(vdupq_n_f32(1.0f),         u2, p);
    return vmulq_n_f32(vmulq_f32(u, p), 2.0f / 0.6931471805599453f);
}

static inline float32x4_t fused_vlog2q_approx(float32x4_t x) {
    int32x4_t bits  = vreinterpretq_s32_f32(x);
    int32x4_t expo  = vsubq_s32(vshrq_n_s32(bits, 23), vdupq_n_s32(127));
    int32x4_t mbits = vorrq_s32(vandq_s32(bits, vdupq_n_s32(0x007FFFFF)),
                                 vdupq_n_s32(0x3F800000));
    float32x4_t m = vreinterpretq_f32_s32(mbits);
    return vaddq_f32(vcvtq_f32_s32(expo), fused_vlog2q_mant(m));
}

/* Bayer-pixel log curve, 4-wide: y = max_v * log10(x/max_v * 112 + 1) / log10(113)
   Equivalent to LUT[x] with <=1 LSB error. Input must already be clamped to max_v.
   Output is clamped to [0, max_v] internally. */
static inline int32x4_t fused_log_curve_neon4(uint16x4_t x_u16, int max_v) {
    float scale = 112.0f / (float)max_v;
    float K     = (float)max_v / log2f(113.0f);
    float32x4_t fx   = vcvtq_f32_u32(vmovl_u16(x_u16));
    float32x4_t norm = vfmaq_n_f32(vdupq_n_f32(1.0f), fx, scale);
    float32x4_t ln   = fused_vlog2q_approx(norm);
    float32x4_t y    = vmulq_n_f32(ln, K);
    int32x4_t   yi   = vcvtq_s32_f32(y);  /* truncate, like the LUT */
    int32x4_t   lo   = vmaxq_s32(yi, vdupq_n_s32(0));
    return vminq_s32(lo, vdupq_n_s32(max_v));
}
#endif /* FUSED_LOG_POLYNOMIAL && NEON */

/* ================================================================
   Constants and quant tables
   ================================================================ */

#define FUSED_MAX_CHANNELS 4
#define FUSED_MAX_WAVELETS 3
#define FUSED_MAX_BANDS    4
#define FUSED_ROW_BUFS     6
#define FUSED_CHANNELS     4

/* Multi-level wavelet support.
   FUSED_WAVELET_LEVELS=1: original behaviour (single-level), 4 bands per channel.
   FUSED_WAVELET_LEVELS=2: 2-level wavelet. Per-channel band layout in the
                            output bitstream is, in order:
                            [0] LL1   (level-1 lowpass, quant=FUSED_LL1_DIVISOR)
                            [1] LH1   (level-1 horizontal highpass, qt[4])
                            [2] HL1   (level-1 vertical highpass,   qt[5])
                            [3] HH1   (level-1 diagonal highpass,   qt[6])
                            [4] LH0   (level-0 horizontal highpass, qt[7])
                            [5] HL0   (level-0 vertical highpass,   qt[8])
                            [6] HH0   (level-0 diagonal highpass,   qt[9])
                            LL0 is NOT emitted (it is replaced by the
                            four level-1 bands which together reconstruct it).
   FUSED_WAVELET_LEVELS=3: 3-level wavelet. Per-channel band layout is:
                            [0] LL2   (level-2 lowpass, quant=FUSED_LL2_DIVISOR)
                            [1] LH2   (level-2 horizontal highpass, qt[1])
                            [2] HL2   (level-2 vertical highpass,   qt[2])
                            [3] HH2   (level-2 diagonal highpass,   qt[3])
                            [4] LH1   (level-1 horizontal highpass, qt[4])
                            [5] HL1   (level-1 vertical highpass,   qt[5])
                            [6] HH1   (level-1 diagonal highpass,   qt[6])
                            [7] LH0   (level-0 horizontal highpass, qt[7])
                            [8] HL0   (level-0 vertical highpass,   qt[8])
                            [9] HH0   (level-0 diagonal highpass,   qt[9])
                            LL0 and LL1 are NOT emitted (intermediates).
   Default = 2 for clean output. 3-level gives ~17 % smaller files at q=3
   but introduces visible wavelet edge ringing on high-contrast features
   (the LL2 quantization error propagates through the L1/L0 inverse
   stages and is magnified by the inverse log curve near edges; verified
   2026-05-12 not to be fixable by quantizer tuning). 3-level remains
   available via -DFUSED_WAVELET_LEVELS=3 for storage-constrained ship
   profiles where motion blur masks the artifact. */
#ifndef FUSED_WAVELET_LEVELS
#define FUSED_WAVELET_LEVELS 2
#endif

/* FUSED_LL2_LOSSLESS: in 3-level mode, store LL2 with a fixed-width 16-bit
   big-endian path (bypassing rANS) instead of quantizing by FUSED_LL2_DIVISOR.
   This eliminates the rANS-alphabet-imposed quantization (LL2 values reach
   ~40000 mag on 14-bit content; the rANS 2047 cap forced a minimum divisor
   of ~20, which produced visible cascade ringing on high-contrast edges).
   With lossless LL2 the 3-level reconstruction is mathematically identical
   to 1-level + extra HF detail bands -- ringing eliminated.

   Format per band: 0xFEFEFEFE magic + u16-BE width + u16-BE height +
   width*height u16-BE coefficients (clamped to [0,65535]). Production GPR
   uses essentially the same format for its top-level lowpass; this is a
   self-contained variant for the fused encoder's band-walker. */
#ifndef FUSED_LL2_LOSSLESS
#define FUSED_LL2_LOSSLESS 0
#endif
#if FUSED_LL2_LOSSLESS && FUSED_WAVELET_LEVELS != 3
#error "FUSED_LL2_LOSSLESS only makes sense with FUSED_WAVELET_LEVELS=3"
#endif

#if FUSED_WAVELET_LEVELS == 1
#define FUSED_BANDS_PER_CHANNEL 4    /* LL0, LH0, HL0, HH0 */
#elif FUSED_WAVELET_LEVELS == 2
#define FUSED_BANDS_PER_CHANNEL 7    /* LL1, LH1, HL1, HH1, LH0, HL0, HH0 */
#elif FUSED_WAVELET_LEVELS == 3
#define FUSED_BANDS_PER_CHANNEL 10   /* LL2, LH2, HL2, HH2, LH1, HL1, HH1, LH0, HL0, HH0 */
#else
#error "FUSED_WAVELET_LEVELS must be 1, 2, or 3"
#endif

#define FUSED_NUM_P2_TASKS (FUSED_CHANNELS * FUSED_BANDS_PER_CHANNEL)

/* LL band quantizer divisor. The rANS tokenizer alphabet caps at ~2047
   (10-bit mag class). 14-bit input has LL coefficients up to ~16383, 16-bit
   up to ~65535. Divisor of 64 brings both safely into alphabet:
     14-bit: max stored ≈ 256, error ≤ ±32 per LL coefficient
     16-bit: max stored ≈ 1024, error ≤ ±32 per LL coefficient (~0.05% rel)
   After inverse wavelet diffusion the per-pixel error is much smaller. */
#define FUSED_LL_DIVISOR   64

/* Level-1 LL band divisor for 2-level mode. Measured pre-quant LL1 max on
   Z8 ISO64 16-bit is ~40K. Divisor=32 brings stored max to ~1270 (within
   the rANS 2047 alphabet cap). Divisor=64 brings it to ~635 with more
   compression headroom; PSNR difference is negligible (the inverse-wavelet
   error amplification dominates over LL1 step size). Stick with 64 to
   match the single-level encoder's FUSED_LL_DIVISOR convention. */
#define FUSED_LL1_DIVISOR  64

/* Level-2 LL band divisor for 3-level mode. LL2 is 1/64 the source resolution
   (1/4 along each spatial axis vs. LL0). With two prescale=2 stages already
   applied by the time we get to LL2, magnitudes shrink another 4× per stage
   so the dynamic range is mild. Divisor=64 matches FUSED_LL_DIVISOR /
   FUSED_LL1_DIVISOR for consistency and keeps the stored max safely within
   the rANS 2047 alphabet cap. */
#ifndef FUSED_LL2_DIVISOR
#define FUSED_LL2_DIVISOR  64
#endif

/* Quality presets: quant divisors per subband [LL, LH, HL, HH for each level] */
static const QUANT quality_tables[9][10] = {
    {1, 24, 24, 12, 64, 64, 48, 512, 512, 768},  /* 0: Low */
    {1, 24, 24, 12, 48, 48, 32, 256, 256, 384},  /* 1: Medium */
    {1, 24, 24, 12, 32, 32, 24, 128, 128, 192},  /* 2: High */
    {1, 24, 24, 12, 24, 24, 12, 96, 96, 144},    /* 3: Filmscan-1 */
    {1, 24, 24, 12, 24, 24, 12, 64, 64, 96},     /* 4: Filmscan-X */
    {1, 24, 24, 12, 24, 24, 12, 32, 32, 48},     /* 5: Filmscan-2 */
    {1, 12, 12,  6, 12, 12,  6, 16, 16, 24},     /* 6: Filmscan-3 */
    {1,  6,  6,  4, 12, 12,  6, 16, 16, 24},     /* 7: Filmscan-4 */
    {1,  4,  4,  2, 10, 10,  6, 16, 16, 24},     /* 8: Filmscan-5 */
};

/* ================================================================
   Quantization helpers (same math as forward.c QuantizeValue)
   ================================================================ */

static inline int32_t get_multiplier(int divisor) {
    return (divisor > 0) ? ((1 << 16) / divisor) : 0;
}

static inline int32_t get_midpoint(int divisor) {
    return (divisor > 1) ? (divisor >> 1) - 1 : 0;
}

static inline int32_t quantize_scalar(int32_t value, int32_t midpoint, int32_t multiplier) {
    int32_t mag = (value < 0) ? -value : value;
    int32_t q = (int32_t)(((int64_t)(mag + midpoint) * multiplier) >> 16);
    return (value < 0) ? -q : q;
}

/* ================================================================
   Horizontal wavelet filter (simplified from forward.c)
   ================================================================ */

static void horizontal_filter(const PIXEL *input, PIXEL *lowpass, PIXEL *highpass,
                               int width, int prescale, int log_bits)
{
    int prescale_rounding = (1 << prescale) - 1;
    int half = width / 2;

    /* Prescale helper */
    #define PS(v) (((v) + prescale_rounding) >> prescale)

    /* Left boundary */
    lowpass[0] = PS(input[0]) + PS(input[1]);
    highpass[0] = PS(input[0]) - PS(input[1]);

    /* The int16 fast path is safe when prescaled-pair-sums fit int16:
       PS-value max = (max_input+1) >> prescale, pair-sum = 2 × PS-max.
       Need 2 × PS-max ≤ 32767 → PS-max ≤ 16383. With prescale=2:
         14-bit input → PS-max = 4096, pair-sum ≤ 8192 ✓
         16-bit input → PS-max = 16384, pair-sum = 32768 ✗ (overflow)
       So enable int16 only for ≤14-bit input. */
    const int can_use_s16 = (log_bits <= 14);

    /* Interior */
    {
        int i = 1;
#if ENABLED(NEON)
        /* Shared NEON constants — used by both int16 fast path (when enabled)
           and the always-correct int32 4-wide cleanup below. */
        const int32x4_t vround = vdupq_n_s32(prescale_rounding);
        const int32x4_t neg_ps = vdupq_n_s32(-prescale);
      if (can_use_s16) {
        /* All horiz filter intermediates fit int16 (input ≤ 16383, PS ≤ 4095,
           pair-sums ≤ 8190, diff ≤ ±16380, +4 ≤ ±16384 — well within ±32767).
           Loads are int32 (PIXEL = int32), narrowed to int16 in-register. */
        const int16x8_t four16 = vdupq_n_s16(4);

        /* 8-wide pass: produce 8 outputs per iteration. Needs inputs [2i-2 .. 2i+17] = 20.
           Load via 5 int32x4 loads, narrow to make 3 int16x8 vectors (with 4 spare lanes). */
        for (; i + 7 < half - 1; i += 8) {
            int idx = 2 * i;

            /* Load 5 int32x4 spans of 4 inputs each: covers [idx-2 .. idx+17] */
            int32x4_t l0 = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx - 2]),  vround), neg_ps);
            int32x4_t l1 = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx + 2]),  vround), neg_ps);
            int32x4_t l2 = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx + 6]),  vround), neg_ps);
            int32x4_t l3 = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx + 10]), vround), neg_ps);
            int32x4_t l4 = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx + 14]), vround), neg_ps);

            /* Pack to int16x8: in0 = [idx-2..idx+5], in1 = [idx+6..idx+13], in2 = [idx+14..idx+21 (last 4 don't care)] */
            int16x8_t in0 = vcombine_s16(vmovn_s32(l0), vmovn_s32(l1));
            int16x8_t in1 = vcombine_s16(vmovn_s32(l2), vmovn_s32(l3));
            int16x8_t in2 = vcombine_s16(vmovn_s32(l4), vdup_n_s16(0));

            /* Current pair vectors (8 outputs × 2 inputs):
               cur1 = inputs[2i..2i+7], cur2 = inputs[2i+8..2i+15] */
            int16x8_t cur1 = vextq_s16(in0, in1, 2);
            int16x8_t cur2 = vextq_s16(in1, in2, 2);

            /* Deinterleave cur1/cur2 → 8 evens, 8 odds */
            int16x8x2_t cn = vuzpq_s16(cur1, cur2);
            int16x8_t evens = cn.val[0];  /* [2i, 2i+2, ..., 2i+14] */
            int16x8_t odds  = cn.val[1];  /* [2i+1, 2i+3, ..., 2i+15] */

            /* Lowpass = evens + odds. Output as 2× int32x4 (sign-extend). */
            int16x8_t low16 = vaddq_s16(evens, odds);
            vst1q_s32(&lowpass[i],     vmovl_s16(vget_low_s16(low16)));
            vst1q_s32(&lowpass[i + 4], vmovl_s16(vget_high_s16(low16)));

            /* prev pair set (8 outputs × pair_sum at offset 2k-2):
               positions [2i-2, 2i, 2i+2, ..., 2i+12] */
            int16x8x2_t ulo = vuzpq_s16(in0, in1);
            int16x8_t prev_sum = vaddq_s16(ulo.val[0], ulo.val[1]);
            /* ulo.val[0] = [in0[0], in0[2], in0[4], in0[6], in1[0], in1[2], in1[4], in1[6]]
                          = [2i-2, 2i, 2i+2, 2i+4, 2i+6, 2i+8, 2i+10, 2i+12]
               ulo.val[1] = [2i-1, 2i+1, 2i+3, 2i+5, 2i+7, 2i+9, 2i+11, 2i+13]
               sum = pair sums at [2i-2, 2i, 2i+2, ..., 2i+12] ✓ */

            /* next pair set: pair_sum at [2i+2, 2i+4, ..., 2i+16]
               Achieved by deinterleaving the shifted (in0, in1) and (in1, in2). */
            int16x8_t shifted01 = vextq_s16(in0, in1, 4);  /* [2i+2..2i+9] */
            int16x8_t shifted12 = vextq_s16(in1, in2, 4);  /* [2i+10..2i+17] */
            int16x8x2_t uhi = vuzpq_s16(shifted01, shifted12);
            int16x8_t next_sum = vaddq_s16(uhi.val[0], uhi.val[1]);
            /* uhi.val[0] = [2i+2, 2i+4, 2i+6, 2i+8, 2i+10, 2i+12, 2i+14, 2i+16]
               uhi.val[1] = [2i+3, 2i+5, ..., 2i+17]
               sum = pair sums at [2i+2, 2i+4, ..., 2i+16] ✓ */

            /* hp = ((next_sum - prev_sum + 4) >> 3) + (evens - odds), all in int16 */
            int16x8_t diff = vsubq_s16(next_sum, prev_sum);
            int16x8_t hp = vshrq_n_s16(vaddq_s16(diff, four16), 3);
            hp = vaddq_s16(hp, vsubq_s16(evens, odds));
            vst1q_s32(&highpass[i],     vmovl_s16(vget_low_s16(hp)));
            vst1q_s32(&highpass[i + 4], vmovl_s16(vget_high_s16(hp)));
        }
      }  /* if (can_use_s16) */

        /* 4-wide int32 cleanup (always-correct path: handles either the
           int16 fast path's leftover columns OR the entire interior when
           can_use_s16 is false). */
        const int32x4_t four = vdupq_n_s32(4);
        for (; i + 3 < half - 1; i += 4) {
            int idx = 2 * i;
            int32x4_t in_lo  = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx-2]), vround), neg_ps);
            int32x4_t in_md  = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx+2]), vround), neg_ps);
            int32x4_t in_hi  = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx+6]), vround), neg_ps);

            int32x4_t cur_pair = vextq_s32(in_lo, in_md, 2);
            int32x4_t nxt_pair = vextq_s32(in_md, in_hi, 2);
            int32x4x2_t cn = vuzpq_s32(cur_pair, nxt_pair);
            int32x4_t evens = cn.val[0];
            int32x4_t odds  = cn.val[1];

            vst1q_s32(&lowpass[i], vaddq_s32(evens, odds));

            int32x4x2_t ulo = vuzpq_s32(in_lo, in_md);
            int32x4x2_t uhi = vuzpq_s32(in_md, in_hi);
            int32x4_t prev_sum = vaddq_s32(ulo.val[0], ulo.val[1]);
            int32x4_t next_sum = vaddq_s32(uhi.val[0], uhi.val[1]);

            int32x4_t diff = vsubq_s32(next_sum, prev_sum);
            int32x4_t hp = vshrq_n_s32(vaddq_s32(diff, four), 3);
            hp = vaddq_s32(hp, vsubq_s32(evens, odds));
            vst1q_s32(&highpass[i], hp);
        }
#endif
        for (; i < half - 1; i++) {
            int idx = 2 * i;
            int32_t e0 = PS(input[idx]);
            int32_t o0 = PS(input[idx + 1]);
            lowpass[i] = e0 + o0;
            int32_t e_prev = PS(input[idx - 2]) + PS(input[idx - 1]);
            int32_t e_next = PS(input[idx + 2]) + PS(input[idx + 3]);
            highpass[i] = ((e_next - e_prev + 4) >> 3) + (e0 - o0);
        }
    }

    /* Right boundary */
    {
        int idx = 2 * (half - 1);
        lowpass[half - 1] = PS(input[idx]) + PS(input[idx + 1]);
        highpass[half - 1] = PS(input[idx]) - PS(input[idx + 1]);
    }

    #undef PS
}

/* ================================================================
   Vertical filter + quantize (simplified from forward.c)
   ================================================================ */

#if ENABLED(NEON)
static inline int32x4_t quantize_neon4(int32x4_t values, int32_t midpoint, int32_t multiplier) {
    int32x4_t abs_v = vabsq_s32(values);
    abs_v = vaddq_s32(abs_v, vdupq_n_s32(midpoint));
    /* 32×32→64 multiply, take high 32 bits (>> 16) */
    int32x2_t mul_v = vdup_n_s32(multiplier);
    int64x2_t plo = vmull_s32(vget_low_s32(abs_v), mul_v);
    int64x2_t phi = vmull_s32(vget_high_s32(abs_v), mul_v);
    int32x4_t scaled = vcombine_s32(vmovn_s64(vshrq_n_s64(plo, 16)),
                                     vmovn_s64(vshrq_n_s64(phi, 16)));
    uint32x4_t neg = vcltq_s32(values, vdupq_n_s32(0));
    return vbslq_s32(neg, vnegq_s32(scaled), scaled);
}

/* Int16 fast quantize: applies when |values|+midpoint fits int16 AND
   multiplier fits int16 (mul ≤ 32767, i.e. divisor ≥ 2). For divisor=1
   (LL band, mul=65536) the caller must fall back to quantize_neon4.
   This produces *exactly* the same result as quantize_scalar — uses
   16×16→32 widening multiply then >>16, which equals (mag*mul)>>16. */
static inline int16x8_t quantize_neon8_s16(int16x8_t values,
                                            int16_t midpoint, int16_t multiplier) {
    int16x8_t abs_v = vabsq_s16(values);
    /* mag + midpoint — saturating to be defensive (we've bounded mag ≤ ~20K,
       midpoint ≤ ~32; sum well within int16). */
    int16x8_t mag = vqaddq_s16(abs_v, vdupq_n_s16(midpoint));

    int16x4_t mul_v = vdup_n_s16(multiplier);
    int32x4_t plo = vmull_s16(vget_low_s16(mag),  mul_v);
    int32x4_t phi = vmull_s16(vget_high_s16(mag), mul_v);
    /* >> 16 then narrow back to int16 */
    int16x4_t scaled_lo = vshrn_n_s32(plo, 16);
    int16x4_t scaled_hi = vshrn_n_s32(phi, 16);
    int16x8_t scaled = vcombine_s16(scaled_lo, scaled_hi);
    /* Re-apply sign of the original value */
    uint16x8_t neg = vcltq_s16(values, vdupq_n_s16(0));
    return vbslq_s16(neg, vnegq_s16(scaled), scaled);
}
#endif

/* The previously-named mid_unused1 parameter now carries the input log_bits
   (14 or 16) so the filter can pick the int16 fast path safely. Pass 14 only
   when the input range fits int16 for the wavelet intermediates — that's
   level-0 wavelet with ≤14-bit pixel input. Pass 16 (or 0 = legacy) otherwise. */
static void vertical_filter_quantize_row(
    PIXEL *rows[6],
    int width,
    int32_t mid_lo, int32_t mul_lo,
    int32_t mid_hi, int32_t mul_hi,
    int32_t input_log_bits, int32_t mul_unused1,
    int32_t mid_unused2, int32_t mul_unused2,
    PIXEL *out_lo, PIXEL *out_hi, PIXEL *unused1, PIXEL *unused2,
    int is_top, int is_bottom)
{
    (void)mul_unused1; (void)mid_unused2; (void)mul_unused2;
    (void)unused1; (void)unused2;
    const int safe_int16 = (input_log_bits > 0 && input_log_bits <= 14);

    int col = 0;

#if ENABLED(NEON)
    if (!is_top && !is_bottom) {
        /* Note: an int16 8-wide fast path was attempted (commit f270152)
           and reverted (this commit). Analysis assumed 14-bit prescaled
           input bounds, but for 16-bit pixel formats (pf=4/5, the X2D and
           MISSION 1 RAW container size), horizontal lowpass reaches ±32768
           and vertical sums reach ±65536 — overflowing int16. The fast
           path also saturated LL coefficients on its quantize step.
           Sticking with the int32 4-wide NEON path for vertical filter:
           always correct, ~25-30% slower at 14-bit input but identical
           cost at 16-bit (where the int16 path wouldn't have worked).
           A correct int32 8-wide path could be written later. */

        const int32x4_t four = vdupq_n_s32(4);
        const int width_m8 = (width / 8) * 8;

        if (safe_int16) {
            /* int16 8-wide filter + int32 quantize. Bounds analysis (level-0
               wavelet, log_bits=14 input, prescale=2):
                 prescaled values ≤ 4096
                 horizontal lowpass ≤ ±8192
                 r2+r3 ≤ ±16380   (LL band output, fits int16)
                 (r4+r5)-(r0+r1)+4 ≤ ±32764 (just inside int16 ±32767)
                 (>>3) + (r2-r3) ≤ ±20475 (HH output, fits int16)
               Filter math is byte-identical to int32 for 14-bit level-0.
               Quantize stays int32 (LL coefficients can reach the int16
               edge — abs+midpoint would saturate with int16 quantize). */
            const int16x8_t four16 = vdupq_n_s16(4);
            for (; col < width_m8; col += 8) {
                int16x8_t r0 = vcombine_s16(vmovn_s32(vld1q_s32(&rows[0][col])),
                                             vmovn_s32(vld1q_s32(&rows[0][col + 4])));
                int16x8_t r1 = vcombine_s16(vmovn_s32(vld1q_s32(&rows[1][col])),
                                             vmovn_s32(vld1q_s32(&rows[1][col + 4])));
                int16x8_t r2 = vcombine_s16(vmovn_s32(vld1q_s32(&rows[2][col])),
                                             vmovn_s32(vld1q_s32(&rows[2][col + 4])));
                int16x8_t r3 = vcombine_s16(vmovn_s32(vld1q_s32(&rows[3][col])),
                                             vmovn_s32(vld1q_s32(&rows[3][col + 4])));
                int16x8_t r4 = vcombine_s16(vmovn_s32(vld1q_s32(&rows[4][col])),
                                             vmovn_s32(vld1q_s32(&rows[4][col + 4])));
                int16x8_t r5 = vcombine_s16(vmovn_s32(vld1q_s32(&rows[5][col])),
                                             vmovn_s32(vld1q_s32(&rows[5][col + 4])));

                int16x8_t low16  = vaddq_s16(r2, r3);
                int16x8_t r45    = vaddq_s16(r4, r5);
                int16x8_t r01    = vaddq_s16(r0, r1);
                int16x8_t hpre   = vaddq_s16(vsubq_s16(r45, r01), four16);
                int16x8_t high16 = vaddq_s16(vshrq_n_s16(hpre, 3),
                                              vsubq_s16(r2, r3));

                /* Widen to int32 for quantize (handles LL boundary safely). */
                int32x4_t low_lo  = vmovl_s16(vget_low_s16(low16));
                int32x4_t low_hi  = vmovl_s16(vget_high_s16(low16));
                int32x4_t high_lo = vmovl_s16(vget_low_s16(high16));
                int32x4_t high_hi = vmovl_s16(vget_high_s16(high16));

                vst1q_s32(&out_lo[col],     quantize_neon4(low_lo,  mid_lo, mul_lo));
                vst1q_s32(&out_lo[col + 4], quantize_neon4(low_hi,  mid_lo, mul_lo));
                vst1q_s32(&out_hi[col],     quantize_neon4(high_lo, mid_hi, mul_hi));
                vst1q_s32(&out_hi[col + 4], quantize_neon4(high_hi, mid_hi, mul_hi));
            }
        } else {
        /* Fallback: int32 8-wide filter for 16-bit input or level-1 wavelet
           (where LL0 input range can exceed int16 bounds). */
        for (; col < width_m8; col += 8) {
            int32x4_t r0a = vld1q_s32(&rows[0][col]);
            int32x4_t r0b = vld1q_s32(&rows[0][col + 4]);
            int32x4_t r1a = vld1q_s32(&rows[1][col]);
            int32x4_t r1b = vld1q_s32(&rows[1][col + 4]);
            int32x4_t r2a = vld1q_s32(&rows[2][col]);
            int32x4_t r2b = vld1q_s32(&rows[2][col + 4]);
            int32x4_t r3a = vld1q_s32(&rows[3][col]);
            int32x4_t r3b = vld1q_s32(&rows[3][col + 4]);
            int32x4_t r4a = vld1q_s32(&rows[4][col]);
            int32x4_t r4b = vld1q_s32(&rows[4][col + 4]);
            int32x4_t r5a = vld1q_s32(&rows[5][col]);
            int32x4_t r5b = vld1q_s32(&rows[5][col + 4]);

            int32x4_t low_a  = vaddq_s32(r2a, r3a);
            int32x4_t low_b  = vaddq_s32(r2b, r3b);
            int32x4_t high_a = vsubq_s32(vaddq_s32(r4a, r5a), vaddq_s32(r0a, r1a));
            int32x4_t high_b = vsubq_s32(vaddq_s32(r4b, r5b), vaddq_s32(r0b, r1b));
            high_a = vshrq_n_s32(vaddq_s32(high_a, four), 3);
            high_b = vshrq_n_s32(vaddq_s32(high_b, four), 3);
            high_a = vaddq_s32(high_a, vsubq_s32(r2a, r3a));
            high_b = vaddq_s32(high_b, vsubq_s32(r2b, r3b));

            vst1q_s32(&out_lo[col],     quantize_neon4(low_a,  mid_lo, mul_lo));
            vst1q_s32(&out_lo[col + 4], quantize_neon4(low_b,  mid_lo, mul_lo));
            vst1q_s32(&out_hi[col],     quantize_neon4(high_a, mid_hi, mul_hi));
            vst1q_s32(&out_hi[col + 4], quantize_neon4(high_b, mid_hi, mul_hi));
        }
        }  /* close else block */
        /* 4-wide tail for remaining columns < 8 */
        const int width_m4 = (width / 4) * 4;
        for (; col < width_m4; col += 4) {
            int32x4_t r0 = vld1q_s32(&rows[0][col]);
            int32x4_t r1 = vld1q_s32(&rows[1][col]);
            int32x4_t r2 = vld1q_s32(&rows[2][col]);
            int32x4_t r3 = vld1q_s32(&rows[3][col]);
            int32x4_t r4 = vld1q_s32(&rows[4][col]);
            int32x4_t r5 = vld1q_s32(&rows[5][col]);

            int32x4_t low = vaddq_s32(r2, r3);
            int32x4_t high = vsubq_s32(vaddq_s32(r4, r5), vaddq_s32(r0, r1));
            high = vshrq_n_s32(vaddq_s32(high, four), 3);
            high = vaddq_s32(high, vsubq_s32(r2, r3));

            vst1q_s32(&out_lo[col], quantize_neon4(low, mid_lo, mul_lo));
            vst1q_s32(&out_hi[col], quantize_neon4(high, mid_hi, mul_hi));
        }
    }
#endif

    /* Scalar fallback (boundaries + cleanup) */
    for (; col < width; col++) {
        int32_t r0 = rows[0][col], r1 = rows[1][col], r2 = rows[2][col];
        int32_t r3 = rows[3][col], r4 = rows[4][col], r5 = rows[5][col];
        int32_t low, high;
        if (is_top) { low = r0 + r1; }
        else if (is_bottom) { low = r4 + r5; }
        else { low = r2 + r3; }
        high = ((r4 + r5 - r0 - r1 + 4) >> 3) + (r2 - r3);
        out_lo[col] = quantize_scalar(low, mid_lo, mul_lo);
        out_hi[col] = quantize_scalar(high, mid_hi, mul_hi);
    }
}


/* ================================================================
   Log curve setup
   ================================================================ */

extern uint16_t EncoderLogCurve14[];
extern uint16_t EncoderLogCurve16[];
extern void SetupEncoderLogCurve(void);

static inline uint16_t apply_log_curve(uint16_t value, int bits) {
    if (bits <= 14) {
        if (value > 16383) value = 16383;
        return EncoderLogCurve14[value];
    } else {
        return EncoderLogCurve16[value];
    }
}

/* ================================================================
   Pass 1: Fused Unpack → Wavelet → Quantize → FreqCount
   ================================================================ */

typedef struct {
    /* Per-channel wavelet state (level 0 streaming) */
    PIXEL *lowpass_buf[FUSED_ROW_BUFS];   /* Horizontal lowpass 6-row circular buffer */
    PIXEL *highpass_buf[FUSED_ROW_BUFS];  /* Horizontal highpass 6-row circular buffer */
    int buf_row;                           /* Current position in circular buffer */

    /* Level-0 output. band_data[0..3] are LL0, LH0, HL0, HH0 at (bw × bh).
       In FUSED_WAVELET_LEVELS=2 mode, LL0 (band_data[0]) is an intermediate
       buffer that is consumed by the level-1 pass and NOT emitted.
       In FUSED_WAVELET_LEVELS=1 mode, LL0 IS emitted. */
    PIXEL *band_data[FUSED_MAX_BANDS];    /* Quantized band buffers (NULL in inline mode) */
    PIXEL *row_scratch[FUSED_MAX_BANDS];  /* Per-row scratch (~5KB × 4) used in inline mode */
    int band_width, band_height;
    int band_pitch;                        /* In pixels */
    int band_out_row;                      /* Current output row */

    /* Quantization parameters per band (level 0) */
    int32_t midpoint[FUSED_MAX_BANDS];
    int32_t multiplier[FUSED_MAX_BANDS];

#if FUSED_WAVELET_LEVELS >= 2
    /* Level-1 output. band_data_l1[0..3] are LL1, LH1, HL1, HH1 at (bw/2 × bh/2).
       The level-1 wavelet operates on UNQUANTIZED level-0 LL coefficients,
       which means the level-0 LL0 buffer must hold pre-quant values when
       FUSED_WAVELET_LEVELS>=2 (see use of midpoint_l0/multiplier_l0 below). */
    PIXEL *band_data_l1[4];
    int band_width_l1, band_height_l1;
    int32_t midpoint_l1[4];
    int32_t multiplier_l1[4];
    /* In multi-level mode, LL0 must be stored without quantization so the
       level-1 wavelet sees the true coefficients. The other level-0 bands
       still apply quantization at production time. */
#endif

#if FUSED_WAVELET_LEVELS >= 3
    /* Level-2 output. band_data_l2[0..3] are LL2, LH2, HL2, HH2 at (bw/4 × bh/4).
       The level-2 wavelet operates on UNQUANTIZED level-1 LL coefficients,
       so LL1 (band_data_l1[0]) must hold pre-quant values in 3-level mode. */
    PIXEL *band_data_l2[4];
    int band_width_l2, band_height_l2;
    int32_t midpoint_l2[4];
    int32_t multiplier_l2[4];
#endif

    /* ANS frequency tables per band (legacy/unused since the freq-removal commit) */
    uint16_t freq[FUSED_MAX_BANDS][160];
    int run_state[FUSED_MAX_BANDS];

    /* Inline-tokenize state per highpass band (NULL in split-pass mode).
       Owned by FUSED_ENCODER; reset each frame. */
    JANS_INLINE_STATE *inline_state[FUSED_MAX_BANDS];
} FUSED_CHANNEL_STATE;

/* ================================================================
   Per-channel Pass 1 (one of 4 parallel threads)
   ================================================================ */

/* Hand-tuned ARM64 assembly inner-loop for the combined unpack. Pure-GPR
   arithmetic version: bypasses the compiler's NEON-umin + 32× umov + 32×
   lane-insert lowering of the NEON-intrinsic body below. See
   fused_encode_arm64.S for details and benchmarks. */
#if defined(__aarch64__)
extern int fused_unpack_row_rggb_asm(
    const uint16_t *row1, const uint16_t *row2,
    const uint16_t *log_tbl,
    int32_t *out_gs, int32_t *out_rg, int32_t *out_bg, int32_t *out_gd,
    int ch_width, int log_max, int mid2);
extern int fused_unpack_row_gbrg_asm(
    const uint16_t *row1, const uint16_t *row2,
    const uint16_t *log_tbl,
    int32_t *out_gs, int32_t *out_rg, int32_t *out_bg, int32_t *out_gd,
    int ch_width, int log_max, int mid2);
#endif

/* Combined 4-channel unpack from one Bayer row pair.
   Each Bayer 2×2 block produces exactly 4 unique log_tbl lookups (R, G1, G2, B)
   shared across all 4 channel outputs:
     GS = (G1+G2)>>1
     RG = ((R-GS)+mid2)>>1
     BG = ((B-GS)+mid2)>>1
     GD = ((G1-G2)+mid2)>>1
   vs. the per-channel unpack which redundantly looks up G1/G2 four times
   (2 LUTs ch0+ch3 each, 3 LUTs ch1+ch2 each = 10 LUTs per block, only 4 unique).
   NEON path uses vld2q_u16 to deinterleave Bayer pairs and vminq_u16 for
   branchless clip. */
static void unpack_all_channels_row(
    int is_rggb,
    const uint16_t *log_tbl, int log_max, int32_t mid2,
    const uint16_t *row1, const uint16_t *row2,
    PIXEL *out_gs, PIXEL *out_rg, PIXEL *out_bg, PIXEL *out_gd,
    int ch_width)
{
    int col = 0;

#if defined(__aarch64__) && !defined(FUSED_DISABLE_UNPACK_ASM)
    /* Hand-tuned asm fast path (see fused_encode_arm64.S). Processes all
       multiples of 8 columns; the scalar tail below handles the remainder.
       Runtime opt-in via env var FUSED_UNPACK_ASM=1 so A/B benchmarking is
       trivial (no rebuild needed). Default OFF on M1 since baseline matches;
       expected to be ON for A78 production target. */
    static int unpack_asm_enabled = -1;
    if (unpack_asm_enabled < 0) {
        const char *e = getenv("FUSED_UNPACK_ASM");
        unpack_asm_enabled = (e && e[0] == '1') ? 1 : 0;
    }
    if (unpack_asm_enabled) {
        int processed;
        if (is_rggb) {
            processed = fused_unpack_row_rggb_asm(
                row1, row2, log_tbl,
                (int32_t *)out_gs, (int32_t *)out_rg,
                (int32_t *)out_bg, (int32_t *)out_gd,
                ch_width, log_max, mid2);
        } else {
            processed = fused_unpack_row_gbrg_asm(
                row1, row2, log_tbl,
                (int32_t *)out_gs, (int32_t *)out_rg,
                (int32_t *)out_bg, (int32_t *)out_gd,
                ch_width, log_max, mid2);
        }
        col = processed;
        goto unpack_tail;
    }
#endif
#if ENABLED(NEON)
    /* Process 8 Bayer blocks (16 source pixels per row, 8 outputs per channel) per iter. */
    const int ch_width_m8 = (ch_width / 8) * 8;
    const int32x4_t vmid2 = vdupq_n_s32(mid2);
    const uint16x8_t vclip = vdupq_n_u16((uint16_t)log_max);

    for (; col < ch_width_m8; col += 8) {
        /* Deinterleaved load: row1 holds [A B A B ...], row2 holds [C D C D ...].
           For RGGB: A=R, B=G1 in row1; C=G2, D=B in row2.
           For GBRG: A=G1, B=B in row1; C=R, D=G2 in row2. */
        uint16x8x2_t r1 = vld2q_u16(&row1[2*col]);
        uint16x8x2_t r2 = vld2q_u16(&row2[2*col]);

        uint16x8_t Rv, G1v, G2v, Bv;
        if (is_rggb) {
            Rv  = r1.val[0]; G1v = r1.val[1];
            G2v = r2.val[0]; Bv  = r2.val[1];
        } else {
            G1v = r1.val[0]; Bv  = r1.val[1];
            Rv  = r2.val[0]; G2v = r2.val[1];
        }
        /* Branchless clip to log_max. */
        Rv  = vminq_u16(Rv,  vclip);
        G1v = vminq_u16(G1v, vclip);
        G2v = vminq_u16(G2v, vclip);
        Bv  = vminq_u16(Bv,  vclip);

        /* Spill clipped values to stack and gather 4 LUT lookups per lane (8 lanes). */
        uint16_t Rs[8], G1s[8], G2s[8], Bs[8];
        vst1q_u16(Rs,  Rv);
        vst1q_u16(G1s, G1v);
        vst1q_u16(G2s, G2v);
        vst1q_u16(Bs,  Bv);

        int32_t r_arr[8], g1_arr[8], g2_arr[8], b_arr[8];
        for (int k = 0; k < 8; k++) {
            r_arr[k]  = log_tbl[Rs[k]];
            g1_arr[k] = log_tbl[G1s[k]];
            g2_arr[k] = log_tbl[G2s[k]];
            b_arr[k]  = log_tbl[Bs[k]];
        }

        /* Process the 8 outputs as 2 × 4-wide NEON tiles. */
        for (int half = 0; half < 2; half++) {
            int32x4_t vr  = vld1q_s32(&r_arr[half*4]);
            int32x4_t vg1 = vld1q_s32(&g1_arr[half*4]);
            int32x4_t vg2 = vld1q_s32(&g2_arr[half*4]);
            int32x4_t vb  = vld1q_s32(&b_arr[half*4]);

            int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            int32x4_t vgd = vshrq_n_s32(vaddq_s32(vsubq_s32(vg1, vg2), vmid2), 1);
            int32x4_t vrg = vshrq_n_s32(vaddq_s32(vsubq_s32(vr, vgs), vmid2), 1);
            int32x4_t vbg = vshrq_n_s32(vaddq_s32(vsubq_s32(vb, vgs), vmid2), 1);

            vst1q_s32(&out_gs[col + half*4], vgs);
            vst1q_s32(&out_rg[col + half*4], vrg);
            vst1q_s32(&out_bg[col + half*4], vbg);
            vst1q_s32(&out_gd[col + half*4], vgd);
        }
    }
#endif

#if defined(__aarch64__) && !defined(FUSED_DISABLE_UNPACK_ASM)
unpack_tail:
#endif
    /* Scalar cleanup for tail columns. */
    for (; col < ch_width; col++) {
        uint16_t R1, G1, G2, B1;
        if (is_rggb) {
            R1 = row1[2*col];   G1 = row1[2*col+1];
            G2 = row2[2*col];   B1 = row2[2*col+1];
        } else {
            G1 = row1[2*col];   B1 = row1[2*col+1];
            R1 = row2[2*col];   G2 = row2[2*col+1];
        }
        if (R1 > log_max) R1 = log_max;
        if (G1 > log_max) G1 = log_max;
        if (G2 > log_max) G2 = log_max;
        if (B1 > log_max) B1 = log_max;
        int32_t r  = log_tbl[R1];
        int32_t g1 = log_tbl[G1];
        int32_t g2 = log_tbl[G2];
        int32_t b  = log_tbl[B1];
        int32_t gs = (g1 + g2) >> 1;
        out_gs[col] = gs;
        out_rg[col] = ((r - gs) + mid2) >> 1;
        out_bg[col] = ((b - gs) + mid2) >> 1;
        out_gd[col] = ((g1 - g2) + mid2) >> 1;
    }
}

/* Unpack ONE channel from a Bayer row pair (called per output row by a channel thread).
   GS/GD need G1+G2 only. RG/BG also need R or B and compute GS as an intermediate.
   NEON path: 4-wide arithmetic with scalar LUT lookups (gather phase + NEON compute). */
static void unpack_channel_row(
    int channel, int is_rggb,
    const uint16_t *log_tbl, int log_max, int32_t mid2,
    const uint16_t *row1, const uint16_t *row2,
    PIXEL *output, int ch_width)
{
    int col = 0;

#if ENABLED(NEON)
    const int ch_width_m4 = (ch_width / 4) * 4;
    const int32x4_t vmid2 = vdupq_n_s32(mid2);

#if defined(FUSED_LOG_POLYNOMIAL)
    /* Polynomial path: NEON-vectorize the log curve directly, skip the
       per-pixel LUT gather and the int32-temp-array roundtrip. */
    const uint16x4_t vlog_max_u16 = vdup_n_u16((uint16_t)log_max);
    (void)log_tbl;  /* silence unused warning when polynomial path active */

    if (channel == 0) {  /* GS = (G1+G2)>>1 */
        for (; col < ch_width_m4; col += 4) {
            uint16_t g1in[4], g2in[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                if (is_rggb) { g1in[k] = row1[2*c+1]; g2in[k] = row2[2*c]; }
                else         { g1in[k] = row1[2*c];   g2in[k] = row2[2*c+1]; }
            }
            uint16x4_t vg1u = vmin_u16(vld1_u16(g1in), vlog_max_u16);
            uint16x4_t vg2u = vmin_u16(vld1_u16(g2in), vlog_max_u16);
            int32x4_t vg1 = fused_log_curve_neon4(vg1u, log_max);
            int32x4_t vg2 = fused_log_curve_neon4(vg2u, log_max);
            vst1q_s32(&output[col], vshrq_n_s32(vaddq_s32(vg1, vg2), 1));
        }
    }
    else if (channel == 1) {  /* RG = ((R - GS) + mid2) >> 1 */
        for (; col < ch_width_m4; col += 4) {
            uint16_t rin[4], g1in[4], g2in[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                if (is_rggb) { rin[k] = row1[2*c];   g1in[k] = row1[2*c+1]; g2in[k] = row2[2*c]; }
                else         { rin[k] = row2[2*c];   g1in[k] = row1[2*c];   g2in[k] = row2[2*c+1]; }
            }
            uint16x4_t vru  = vmin_u16(vld1_u16(rin),  vlog_max_u16);
            uint16x4_t vg1u = vmin_u16(vld1_u16(g1in), vlog_max_u16);
            uint16x4_t vg2u = vmin_u16(vld1_u16(g2in), vlog_max_u16);
            int32x4_t vr  = fused_log_curve_neon4(vru,  log_max);
            int32x4_t vg1 = fused_log_curve_neon4(vg1u, log_max);
            int32x4_t vg2 = fused_log_curve_neon4(vg2u, log_max);
            int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            vst1q_s32(&output[col],
                vshrq_n_s32(vaddq_s32(vsubq_s32(vr, vgs), vmid2), 1));
        }
    }
    else if (channel == 2) {  /* BG = ((B - GS) + mid2) >> 1 */
        for (; col < ch_width_m4; col += 4) {
            uint16_t bin[4], g1in[4], g2in[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                if (is_rggb) { bin[k] = row2[2*c+1]; g1in[k] = row1[2*c+1]; g2in[k] = row2[2*c]; }
                else         { bin[k] = row1[2*c+1]; g1in[k] = row1[2*c];   g2in[k] = row2[2*c+1]; }
            }
            uint16x4_t vbu  = vmin_u16(vld1_u16(bin),  vlog_max_u16);
            uint16x4_t vg1u = vmin_u16(vld1_u16(g1in), vlog_max_u16);
            uint16x4_t vg2u = vmin_u16(vld1_u16(g2in), vlog_max_u16);
            int32x4_t vb  = fused_log_curve_neon4(vbu,  log_max);
            int32x4_t vg1 = fused_log_curve_neon4(vg1u, log_max);
            int32x4_t vg2 = fused_log_curve_neon4(vg2u, log_max);
            int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            vst1q_s32(&output[col],
                vshrq_n_s32(vaddq_s32(vsubq_s32(vb, vgs), vmid2), 1));
        }
    }
    else {  /* channel == 3, GD = ((G1 - G2) + mid2) >> 1 */
        for (; col < ch_width_m4; col += 4) {
            uint16_t g1in[4], g2in[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                if (is_rggb) { g1in[k] = row1[2*c+1]; g2in[k] = row2[2*c]; }
                else         { g1in[k] = row1[2*c];   g2in[k] = row2[2*c+1]; }
            }
            uint16x4_t vg1u = vmin_u16(vld1_u16(g1in), vlog_max_u16);
            uint16x4_t vg2u = vmin_u16(vld1_u16(g2in), vlog_max_u16);
            int32x4_t vg1 = fused_log_curve_neon4(vg1u, log_max);
            int32x4_t vg2 = fused_log_curve_neon4(vg2u, log_max);
            vst1q_s32(&output[col],
                vshrq_n_s32(vaddq_s32(vsubq_s32(vg1, vg2), vmid2), 1));
        }
    }
#else  /* !FUSED_LOG_POLYNOMIAL — default LUT-based path */
    if (channel == 0) {  /* GS = (G1+G2)>>1 */
        for (; col < ch_width_m4; col += 4) {
            int32_t g1a[4], g2a[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                uint16_t G1, G2;
                if (is_rggb) { G1 = row1[2*c+1]; G2 = row2[2*c]; }
                else         { G1 = row1[2*c];   G2 = row2[2*c+1]; }
                if (G1 > log_max) G1 = log_max;
                if (G2 > log_max) G2 = log_max;
                g1a[k] = log_tbl[G1]; g2a[k] = log_tbl[G2];
            }
            int32x4_t vg1 = vld1q_s32(g1a), vg2 = vld1q_s32(g2a);
            vst1q_s32(&output[col], vshrq_n_s32(vaddq_s32(vg1, vg2), 1));
        }
    }
    else if (channel == 1) {  /* RG = ((R - GS) + mid2) >> 1 */
        for (; col < ch_width_m4; col += 4) {
            int32_t ra[4], g1a[4], g2a[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                uint16_t R, G1, G2;
                if (is_rggb) { R = row1[2*c];   G1 = row1[2*c+1]; G2 = row2[2*c]; }
                else         { R = row2[2*c];   G1 = row1[2*c];   G2 = row2[2*c+1]; }
                if (R  > log_max) R  = log_max;
                if (G1 > log_max) G1 = log_max;
                if (G2 > log_max) G2 = log_max;
                ra[k] = log_tbl[R]; g1a[k] = log_tbl[G1]; g2a[k] = log_tbl[G2];
            }
            int32x4_t vr = vld1q_s32(ra), vg1 = vld1q_s32(g1a), vg2 = vld1q_s32(g2a);
            int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            vst1q_s32(&output[col],
                vshrq_n_s32(vaddq_s32(vsubq_s32(vr, vgs), vmid2), 1));
        }
    }
    else if (channel == 2) {  /* BG = ((B - GS) + mid2) >> 1 */
        for (; col < ch_width_m4; col += 4) {
            int32_t ba[4], g1a[4], g2a[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                uint16_t B, G1, G2;
                if (is_rggb) { B = row2[2*c+1]; G1 = row1[2*c+1]; G2 = row2[2*c]; }
                else         { B = row1[2*c+1]; G1 = row1[2*c];   G2 = row2[2*c+1]; }
                if (B  > log_max) B  = log_max;
                if (G1 > log_max) G1 = log_max;
                if (G2 > log_max) G2 = log_max;
                ba[k] = log_tbl[B]; g1a[k] = log_tbl[G1]; g2a[k] = log_tbl[G2];
            }
            int32x4_t vb = vld1q_s32(ba), vg1 = vld1q_s32(g1a), vg2 = vld1q_s32(g2a);
            int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            vst1q_s32(&output[col],
                vshrq_n_s32(vaddq_s32(vsubq_s32(vb, vgs), vmid2), 1));
        }
    }
    else {  /* channel == 3, GD = ((G1 - G2) + mid2) >> 1 */
        for (; col < ch_width_m4; col += 4) {
            int32_t g1a[4], g2a[4];
            for (int k = 0; k < 4; k++) {
                int c = col + k;
                uint16_t G1, G2;
                if (is_rggb) { G1 = row1[2*c+1]; G2 = row2[2*c]; }
                else         { G1 = row1[2*c];   G2 = row2[2*c+1]; }
                if (G1 > log_max) G1 = log_max;
                if (G2 > log_max) G2 = log_max;
                g1a[k] = log_tbl[G1]; g2a[k] = log_tbl[G2];
            }
            int32x4_t vg1 = vld1q_s32(g1a), vg2 = vld1q_s32(g2a);
            vst1q_s32(&output[col],
                vshrq_n_s32(vaddq_s32(vsubq_s32(vg1, vg2), vmid2), 1));
        }
    }
#endif  /* FUSED_LOG_POLYNOMIAL */
#endif  /* NEON */

    /* Scalar cleanup for tail columns */
    for (; col < ch_width; col++) {
        uint16_t Rv, G1v, G2v, Bv;
        if (is_rggb) {
            Rv = row1[2*col]; G1v = row1[2*col+1]; G2v = row2[2*col]; Bv = row2[2*col+1];
        } else {
            G1v = row1[2*col]; Bv = row1[2*col+1]; Rv = row2[2*col]; G2v = row2[2*col+1];
        }
        if (G1v > log_max) G1v = log_max;
        if (G2v > log_max) G2v = log_max;
        int32_t g1 = log_tbl[G1v], g2 = log_tbl[G2v];

        switch (channel) {
            case 0: output[col] = (g1 + g2) >> 1; break;
            case 1: {
                if (Rv > log_max) Rv = log_max;
                int32_t r = log_tbl[Rv], gs = (g1 + g2) >> 1;
                output[col] = ((r - gs) + mid2) >> 1;
            } break;
            case 2: {
                if (Bv > log_max) Bv = log_max;
                int32_t b = log_tbl[Bv], gs = (g1 + g2) >> 1;
                output[col] = ((b - gs) + mid2) >> 1;
            } break;
            case 3: output[col] = ((g1 - g2) + mid2) >> 1; break;
        }
    }
}

/* Run the entire Pass 1 pipeline for a single channel: unpack → horiz → vert+quant → freq.
   Each invocation owns its 6-row buffer and freq tables in *cs. */
static void pass1_run_channel(
    int channel,
    const uint8_t *raw_bayer, int width, int height,
    int log_bits, int is_rggb, int prescale,
    FUSED_CHANNEL_STATE *cs)
{
    int ch_width = width / 2;
    int ch_height = height / 2;
    const uint16_t *bayer = (const uint16_t *)raw_bayer;
    int bayer_pitch = width;

    int32_t mid2 = 2 * (1 << (log_bits - 1));
    uint16_t *log_tbl = (log_bits <= 14) ? EncoderLogCurve14 : EncoderLogCurve16;
    int log_max = (log_bits <= 14) ? 16383 : 65535;

    PIXEL *unpack_row = (PIXEL *)malloc(ch_width * sizeof(PIXEL));
    if (!unpack_row) return;

#ifdef FUSED_TIMING_DETAIL
    double t_unpack = 0, t_horiz = 0, t_vert = 0, t_freq = 0;
    double _td;
    double _ch_start = _fused_ms();
#endif

    for (int row = 0; row < ch_height; row++) {
        const uint16_t *row1 = bayer + (row * 2) * bayer_pitch;
        const uint16_t *row2 = row1 + bayer_pitch;

#ifdef FUSED_TIMING_DETAIL
        _td = _fused_ms();
#endif

        unpack_channel_row(channel, is_rggb, log_tbl, log_max, mid2,
                           row1, row2, unpack_row, ch_width);

#ifdef FUSED_TIMING_DETAIL
        t_unpack += _fused_ms() - _td; _td = _fused_ms();
#endif

        int buf_idx = cs->buf_row % FUSED_ROW_BUFS;
        horizontal_filter(unpack_row,
                          cs->lowpass_buf[buf_idx],
                          cs->highpass_buf[buf_idx],
                          ch_width, prescale, log_bits);
        cs->buf_row++;

#ifdef FUSED_TIMING_DETAIL
        t_horiz += _fused_ms() - _td; _td = _fused_ms();
#endif

        if (cs->buf_row >= 6 && (cs->buf_row % 2) == 0) {
            int out_row = cs->band_out_row;
            if (out_row >= cs->band_height) continue;

            PIXEL *lp_rows[6], *hp_rows[6];
            int base = (cs->buf_row - 6) % FUSED_ROW_BUFS;
            for (int r = 0; r < 6; r++) {
                int idx = (base + r) % FUSED_ROW_BUFS;
                lp_rows[r] = cs->lowpass_buf[idx];
                hp_rows[r] = cs->highpass_buf[idx];
            }

            int is_top = (out_row == 0);
            int is_bottom = (out_row == cs->band_height - 1);
            int bw = cs->band_width;

            /* Output destinations: either into the full band buffer (split mode)
               or into a per-row scratch (inline mode). LL is discarded either
               way at this level. */
            const int inline_mode = (cs->inline_state[1] != NULL);
            PIXEL *ll_row = inline_mode ? cs->row_scratch[0]
                                        : (cs->band_data[0] + out_row * cs->band_pitch);
            PIXEL *lh_row = inline_mode ? cs->row_scratch[1]
                                        : (cs->band_data[1] + out_row * cs->band_pitch);
            PIXEL *hl_row = inline_mode ? cs->row_scratch[2]
                                        : (cs->band_data[2] + out_row * cs->band_pitch);
            PIXEL *hh_row = inline_mode ? cs->row_scratch[3]
                                        : (cs->band_data[3] + out_row * cs->band_pitch);

            vertical_filter_quantize_row(lp_rows, bw,
                cs->midpoint[0], cs->multiplier[0],
                cs->midpoint[1], cs->multiplier[1],
                log_bits, 0, 0, 0,
                ll_row, lh_row, NULL, NULL,
                is_top, is_bottom);

            vertical_filter_quantize_row(hp_rows, bw,
                cs->midpoint[2], cs->multiplier[2],
                cs->midpoint[3], cs->multiplier[3],
                log_bits, 0, 0, 0,
                hl_row, hh_row, NULL, NULL,
                is_top, is_bottom);

#ifdef FUSED_TIMING_DETAIL
            t_vert += _fused_ms() - _td; _td = _fused_ms();
#endif

            /* Inline-mode: tokenize each highpass band's row immediately while
               it's still hot in L1. Pass 2 will only do rANS encode. */
            if (inline_mode) {
                jans_inline_row(cs->inline_state[1], lh_row, bw);
                jans_inline_row(cs->inline_state[2], hl_row, bw);
                jans_inline_row(cs->inline_state[3], hh_row, bw);
            }

#ifdef FUSED_TIMING_DETAIL
            t_freq += _fused_ms() - _td;
#endif

            cs->band_out_row++;
        }
    }

    /* The 6-tap vertical filter underflows by 2 rows at the bottom — the last
       2 band rows are never produced by the loop. The split-pass encoder's
       jans_encode_band_x4 still tokenizes the full band (those untouched
       trailing rows are calloc'd zero), so inline mode must do the same to
       stay bit-identical: emit zero-row tokens for the missing rows. */
    if (cs->inline_state[1] != NULL) {
        int bw = cs->band_width;
        PIXEL *zero_row = (PIXEL *)calloc(bw, sizeof(PIXEL));
        if (zero_row) {
            while (cs->band_out_row < cs->band_height) {
                jans_inline_row(cs->inline_state[1], zero_row, bw);
                jans_inline_row(cs->inline_state[2], zero_row, bw);
                jans_inline_row(cs->inline_state[3], zero_row, bw);
                cs->band_out_row++;
            }
            free(zero_row);
        }
    }

#ifdef FUSED_TIMING_DETAIL
    double _ch_end = _fused_ms();
    double _ch_total = _ch_end - _ch_start;
    double _ch_other = _ch_total - t_unpack - t_horiz - t_vert - t_freq;
    fprintf(stderr, "    ch%d: unpack=%.1f, horiz=%.1f, vert+quant=%.1f, tokenize=%.1f, other=%.1f, TOTAL=%.1f\n",
            channel, t_unpack, t_horiz, t_vert, t_freq, _ch_other, _ch_total);
#endif

    free(unpack_row);
}

/* Sync structure: shared between Pass 1 and Pass 2 threads to overlap them.
   Pass 2 band threads wait on their channel's p1_done flag before encoding. */
typedef struct {
    pthread_mutex_t lock;
    pthread_cond_t cv;
    volatile int p1_done[4];
} CHANNEL_SYNC;

/* ================================================================
   Shared-unpack ring buffer (N producers + 4 consumers)
   ----------------------------------------------------------------
   N producer threads (row-interleaved: producer p handles rows where
   row % N_PRODUCERS == p) cooperatively fill a small ring of unpacked
   rows (4 channel-row pointers per slot). The 4 P1 channel consumer
   threads each consume their channel from the ring and run
   horiz+vert+quant as before. This eliminates the ~10 LUT lookups per
   Bayer block (only 4 unique) duplicated across the 4 prior per-channel
   unpack threads — each Bayer block now goes through the log curve once
   per pixel-lane instead of 2.5×.

   Each ring slot s carries the row number currently occupying it in
   slot_row[s]; consumers wait for slot_row[s] == r before reading row r.
   Producers wait for min_consumer > r - N_RING before writing slot s.
   N_RING = 64 → ~4.5 MB at 50 MP. Signalling batched every
   RING_BATCH rows to keep mutex traffic low. */
#define UNPACK_RING_SIZE  64
#define UNPACK_RING_BATCH 16
#ifndef UNPACK_PRODUCERS
#define UNPACK_PRODUCERS  4
#endif

typedef struct {
    PIXEL *rows[UNPACK_RING_SIZE][4];  /* row buf per slot per channel */
    int ch_width;
    int total_rows;

    /* slot_row[s] = row number currently occupying slot s (or s - N_RING
       initially). When producer finishes writing row r to slot s, it sets
       slot_row[s] = r. Consumers read slot s for row r once slot_row[s] >= r. */
    volatile int slot_row[UNPACK_RING_SIZE];

    /* Per-producer position (rows produced so far in this producer's stride). */
    volatile int prod_max_row[UNPACK_PRODUCERS];

    /* Per-consumer position (rows consumed so far, monotonic). */
    volatile int consumed[4];

    pthread_mutex_t lock;
    pthread_cond_t  prod_cv;   /* producers wait when ring is full */
    pthread_cond_t  cons_cv;   /* consumers wait when ring is empty */
} UNPACK_RING;

static int unpack_ring_init(UNPACK_RING *ring, int ch_width, int total_rows) {
    memset(ring, 0, sizeof(*ring));
    ring->ch_width = ch_width;
    ring->total_rows = total_rows;
    for (int s = 0; s < UNPACK_RING_SIZE; s++) {
        for (int c = 0; c < 4; c++) {
            ring->rows[s][c] = (PIXEL *)malloc(ch_width * sizeof(PIXEL));
            if (!ring->rows[s][c]) return -1;
        }
        ring->slot_row[s] = s - UNPACK_RING_SIZE;  /* "before-start" sentinel */
    }
    pthread_mutex_init(&ring->lock, NULL);
    pthread_cond_init(&ring->prod_cv, NULL);
    pthread_cond_init(&ring->cons_cv, NULL);
    return 0;
}

static void unpack_ring_destroy(UNPACK_RING *ring) {
    for (int s = 0; s < UNPACK_RING_SIZE; s++) {
        for (int c = 0; c < 4; c++) {
            if (ring->rows[s][c]) free(ring->rows[s][c]);
        }
    }
    pthread_mutex_destroy(&ring->lock);
    pthread_cond_destroy(&ring->prod_cv);
    pthread_cond_destroy(&ring->cons_cv);
}

typedef struct {
    UNPACK_RING *ring;
    int producer_id;       /* 0..UNPACK_PRODUCERS-1 */
    const uint8_t *raw_bayer;
    int width, height;     /* full image dimensions (rows = height/2 = ring->total_rows) */
    int log_bits, is_rggb;
} UNPACK_PRODUCER_TASK;

static void *unpack_producer_thread(void *arg) {
    UNPACK_PRODUCER_TASK *t = (UNPACK_PRODUCER_TASK *)arg;
    UNPACK_RING *ring = t->ring;
    int pid = t->producer_id;
    const uint16_t *bayer = (const uint16_t *)t->raw_bayer;
    int bayer_pitch = t->width;
    int ch_width = ring->ch_width;
    int total_rows = ring->total_rows;
    int log_bits = t->log_bits;
    int is_rggb = t->is_rggb;
    int32_t mid2 = 2 * (1 << (log_bits - 1));
    uint16_t *log_tbl = (log_bits <= 14) ? EncoderLogCurve14 : EncoderLogCurve16;
    int log_max = (log_bits <= 14) ? 16383 : 65535;
    int batch_counter = 0;

#ifdef FUSED_TIMING_DETAIL
    double _start = _fused_ms();
#endif

    /* Row-interleaved: each producer handles rows where row % N_PRODUCERS == pid. */
    for (int row = pid; row < total_rows; row += UNPACK_PRODUCERS) {
        int slot = row % UNPACK_RING_SIZE;

        /* Wait until all consumers have advanced past row - UNPACK_RING_SIZE
           so the slot is free to overwrite. */
        if (row >= UNPACK_RING_SIZE) {
            pthread_mutex_lock(&ring->lock);
            for (;;) {
                int min_cons = ring->consumed[0];
                if (ring->consumed[1] < min_cons) min_cons = ring->consumed[1];
                if (ring->consumed[2] < min_cons) min_cons = ring->consumed[2];
                if (ring->consumed[3] < min_cons) min_cons = ring->consumed[3];
                if (min_cons > row - UNPACK_RING_SIZE) break;
                pthread_cond_wait(&ring->prod_cv, &ring->lock);
            }
            pthread_mutex_unlock(&ring->lock);
        }

        const uint16_t *row1 = bayer + (row * 2) * bayer_pitch;
        const uint16_t *row2 = row1 + bayer_pitch;

        unpack_all_channels_row(is_rggb, log_tbl, log_max, mid2,
                                row1, row2,
                                ring->rows[slot][0], ring->rows[slot][1],
                                ring->rows[slot][2], ring->rows[slot][3],
                                ch_width);

        /* Publish this slot. Use a per-slot row-number tag so the consumer
           knows when slot s contains row r (slot_row[s] == r).
           Periodic mutex broadcast wakes the consumer; in between, the plain
           volatile stores are picked up by the consumer's spin-then-wait. */
        ring->slot_row[slot] = row;
        ring->prod_max_row[pid] = row;
        batch_counter++;
        if (batch_counter >= UNPACK_RING_BATCH || row + UNPACK_PRODUCERS >= total_rows) {
            pthread_mutex_lock(&ring->lock);
            pthread_cond_broadcast(&ring->cons_cv);
            pthread_mutex_unlock(&ring->lock);
            batch_counter = 0;
        }
    }

#ifdef FUSED_TIMING_DETAIL
    double _end = _fused_ms();
    if (pid == 0) {
        fprintf(stderr, "    producer-unpack[0..%d]: %.1fms (P0 thread, %d producers total)\n",
                UNPACK_PRODUCERS - 1, _end - _start, UNPACK_PRODUCERS);
    }
#endif
    return NULL;
}

typedef struct {
    int channel;
    const uint8_t *raw_bayer;
    int width, height;
    int log_bits, is_rggb, prescale;
    FUSED_CHANNEL_STATE *cs;
    CHANNEL_SYNC *sync;
    UNPACK_RING *ring;   /* if non-NULL, consume from ring instead of unpacking */
} PASS1_CHANNEL_TASK;

/* Producer/consumer variant of pass1_run_channel: consumes unpacked channel
   rows from the shared ring (filled by unpack_producer_thread). Otherwise
   identical to pass1_run_channel: horiz → vert+quant → optional tokenize. */
static void pass1_run_channel_consumer(
    int channel,
    int width, int height,
    int prescale, int log_bits,
    FUSED_CHANNEL_STATE *cs,
    UNPACK_RING *ring)
{
    int ch_width = width / 2;
    int ch_height = height / 2;
    (void)ch_width;  /* used via ring->ch_width */

#ifdef FUSED_TIMING_DETAIL
    double t_wait = 0, t_horiz = 0, t_vert = 0, t_freq = 0;
    double _td;
    double _ch_start = _fused_ms();
#endif

    for (int row = 0; row < ch_height; row++) {
        int slot = row % UNPACK_RING_SIZE;
#ifdef FUSED_TIMING_DETAIL
        _td = _fused_ms();
#endif
        /* Wait for SOME producer to have published this row. slot_row[slot]
           starts negative and only grows in increments of UNPACK_RING_SIZE;
           we want slot_row[slot] == row. */
        if (ring->slot_row[slot] < row) {
            /* Brief spin in case the producer is about to publish (avoid the
               mutex when the producer is already finishing this row). */
            for (int spin = 0; spin < 1024; spin++) {
                if (ring->slot_row[slot] >= row) break;
            }
            if (ring->slot_row[slot] < row) {
                pthread_mutex_lock(&ring->lock);
                while (ring->slot_row[slot] < row) {
                    pthread_cond_wait(&ring->cons_cv, &ring->lock);
                }
                pthread_mutex_unlock(&ring->lock);
            }
        }
#ifdef FUSED_TIMING_DETAIL
        t_wait += _fused_ms() - _td; _td = _fused_ms();
#endif

        PIXEL *unpack_row = ring->rows[slot][channel];

        int buf_idx = cs->buf_row % FUSED_ROW_BUFS;
        horizontal_filter(unpack_row,
                          cs->lowpass_buf[buf_idx],
                          cs->highpass_buf[buf_idx],
                          width / 2, prescale, log_bits);
        cs->buf_row++;

#ifdef FUSED_TIMING_DETAIL
        t_horiz += _fused_ms() - _td; _td = _fused_ms();
#endif

        if (cs->buf_row >= 6 && (cs->buf_row % 2) == 0) {
            int out_row = cs->band_out_row;
            if (out_row >= cs->band_height) goto advance_consumer;

            PIXEL *lp_rows[6], *hp_rows[6];
            int base = (cs->buf_row - 6) % FUSED_ROW_BUFS;
            for (int r = 0; r < 6; r++) {
                int idx = (base + r) % FUSED_ROW_BUFS;
                lp_rows[r] = cs->lowpass_buf[idx];
                hp_rows[r] = cs->highpass_buf[idx];
            }

            int is_top = (out_row == 0);
            int is_bottom = (out_row == cs->band_height - 1);
            int bw = cs->band_width;

            const int inline_mode = (cs->inline_state[1] != NULL);
            PIXEL *ll_row = inline_mode ? cs->row_scratch[0]
                                        : (cs->band_data[0] + out_row * cs->band_pitch);
            PIXEL *lh_row = inline_mode ? cs->row_scratch[1]
                                        : (cs->band_data[1] + out_row * cs->band_pitch);
            PIXEL *hl_row = inline_mode ? cs->row_scratch[2]
                                        : (cs->band_data[2] + out_row * cs->band_pitch);
            PIXEL *hh_row = inline_mode ? cs->row_scratch[3]
                                        : (cs->band_data[3] + out_row * cs->band_pitch);

            vertical_filter_quantize_row(lp_rows, bw,
                cs->midpoint[0], cs->multiplier[0],
                cs->midpoint[1], cs->multiplier[1],
                log_bits, 0, 0, 0,
                ll_row, lh_row, NULL, NULL,
                is_top, is_bottom);

            vertical_filter_quantize_row(hp_rows, bw,
                cs->midpoint[2], cs->multiplier[2],
                cs->midpoint[3], cs->multiplier[3],
                log_bits, 0, 0, 0,
                hl_row, hh_row, NULL, NULL,
                is_top, is_bottom);

#ifdef FUSED_TIMING_DETAIL
            t_vert += _fused_ms() - _td; _td = _fused_ms();
#endif

            if (inline_mode) {
                jans_inline_row(cs->inline_state[1], lh_row, bw);
                jans_inline_row(cs->inline_state[2], hl_row, bw);
                jans_inline_row(cs->inline_state[3], hh_row, bw);
            }

#ifdef FUSED_TIMING_DETAIL
            t_freq += _fused_ms() - _td;
#endif
            cs->band_out_row++;
        }

advance_consumer:
        /* Release the slot. Batch the signal so the producer isn't woken
           per row; the producer only blocks when min_consumer is far behind. */
        {
            int new_cons = row + 1;
            if ((new_cons % UNPACK_RING_BATCH) == 0 || new_cons == ch_height) {
                pthread_mutex_lock(&ring->lock);
                ring->consumed[channel] = new_cons;
                pthread_cond_signal(&ring->prod_cv);
                pthread_mutex_unlock(&ring->lock);
            } else {
                ring->consumed[channel] = new_cons;
            }
        }
    }

    /* Same bottom-of-band zero-row flush as the original per-channel path. */
    if (cs->inline_state[1] != NULL) {
        int bw = cs->band_width;
        PIXEL *zero_row = (PIXEL *)calloc(bw, sizeof(PIXEL));
        if (zero_row) {
            while (cs->band_out_row < cs->band_height) {
                jans_inline_row(cs->inline_state[1], zero_row, bw);
                jans_inline_row(cs->inline_state[2], zero_row, bw);
                jans_inline_row(cs->inline_state[3], zero_row, bw);
                cs->band_out_row++;
            }
            free(zero_row);
        }
    }

#ifdef FUSED_TIMING_DETAIL
    double _ch_end = _fused_ms();
    double _ch_total = _ch_end - _ch_start;
    double _ch_other = _ch_total - t_wait - t_horiz - t_vert - t_freq;
    fprintf(stderr, "    ch%d: wait=%.1f, horiz=%.1f, vert+quant=%.1f, tokenize=%.1f, other=%.1f, TOTAL=%.1f\n",
            channel, t_wait, t_horiz, t_vert, t_freq, _ch_other, _ch_total);
#endif
}

#if FUSED_WAVELET_LEVELS >= 2
/* Run the level-1 wavelet on a channel's already-produced LL0 buffer.
   LL0 lives in cs->band_data[0] at (cs->band_width × cs->band_height).
   Outputs 4 quantised bands into cs->band_data_l1[0..3] at (bw/2 × bh/2):
       [0] LL1, [1] LH1, [2] HL1, [3] HH1.

   Mirrors the level-0 streaming path: horizontal filter into a 6-row
   circular buffer; emit one band-row every 2 input rows once the 6-row
   window is full; vertical filter + quantise (level-1 midpoints/multipliers)
   into the 4 output bands.

   Prescale for level 1: we use prescale=2 (same as level 0). LL0 values are
   roughly in 14-bit-channel range (the level-0 pass has already applied
   prescale=2), so a further prescale=2 inside FilterHorizontalRow brings
   them down a factor of 4 each time. The decoder's inverse wavelet will
   reapply prescale on output (handled in the test_video_full_roundtrip
   harness via cumulative prescale).
*/
static void run_level1_wavelet(FUSED_CHANNEL_STATE *cs)
{
    const int in_w = cs->band_width;
    const int in_h = cs->band_height;
    const int bw1  = cs->band_width_l1;
    const int bh1  = cs->band_height_l1;
    /* Level-1 prescale: production uses 2 (14-bit) or 3 (16-bit). The fused
       encoder runs all inputs at log_bits=14 or 16 (via the encoder log curve)
       and applies prescale=2 at level 0 universally. For level 1 we use
       prescale=2 to keep LL1 dynamic range manageable; production-equivalent
       prescale=3 (for 16-bit) reduces LL1 by another factor of 2. */
    const int prescale = 2;
    /* log_bits is only used by horizontal_filter for the can_use_s16 check.
       Level-1 input is bounded by level-0 LL values which are 14-bit-ish
       (with prescale=2 already applied at level 0), so 14 is safe. We pass
       16 to be conservative — disables the int16 fast path inside horiz
       filter for level 1, but level 1 is 1/16 the data so cost is tiny. */
    const int log_bits = 16;

    /* 6-row circular buffer for horizontal filter outputs */
    PIXEL *lp_buf[FUSED_ROW_BUFS];
    PIXEL *hp_buf[FUSED_ROW_BUFS];
    for (int r = 0; r < FUSED_ROW_BUFS; r++) {
        lp_buf[r] = (PIXEL *)calloc(bw1, sizeof(PIXEL));
        hp_buf[r] = (PIXEL *)calloc(bw1, sizeof(PIXEL));
        if (!lp_buf[r] || !hp_buf[r]) goto cleanup;
    }

    int buf_row = 0;
    int out_row = 0;

    PIXEL *ll0 = cs->band_data[0];

    for (int row = 0; row < in_h; row++) {
        const PIXEL *src = ll0 + (size_t)row * in_w;
        int idx = buf_row % FUSED_ROW_BUFS;
        horizontal_filter(src, lp_buf[idx], hp_buf[idx], in_w, prescale, log_bits);
        buf_row++;

        if (buf_row >= 6 && (buf_row % 2) == 0) {
            if (out_row >= bh1) continue;
            int is_top = (out_row == 0);
            int is_bottom = (out_row == bh1 - 1);

            PIXEL *lp_rows[6], *hp_rows[6];
            int base = (buf_row - 6) % FUSED_ROW_BUFS;
            for (int r = 0; r < 6; r++) {
                int ii = (base + r) % FUSED_ROW_BUFS;
                lp_rows[r] = lp_buf[ii];
                hp_rows[r] = hp_buf[ii];
            }

            PIXEL *ll1 = cs->band_data_l1[0] + (size_t)out_row * bw1;
            PIXEL *lh1 = cs->band_data_l1[1] + (size_t)out_row * bw1;
            PIXEL *hl1 = cs->band_data_l1[2] + (size_t)out_row * bw1;
            PIXEL *hh1 = cs->band_data_l1[3] + (size_t)out_row * bw1;

            vertical_filter_quantize_row(lp_rows, bw1,
                cs->midpoint_l1[0], cs->multiplier_l1[0],
                cs->midpoint_l1[1], cs->multiplier_l1[1],
                0, 0, 0, 0,
                ll1, lh1, NULL, NULL,
                is_top, is_bottom);

            vertical_filter_quantize_row(hp_rows, bw1,
                cs->midpoint_l1[2], cs->multiplier_l1[2],
                cs->midpoint_l1[3], cs->multiplier_l1[3],
                0, 0, 0, 0,
                hl1, hh1, NULL, NULL,
                is_top, is_bottom);

            out_row++;
        }
    }
    /* Trailing 2 band rows untouched (calloc'd zero) — same as level 0. */

cleanup:
    for (int r = 0; r < FUSED_ROW_BUFS; r++) {
        if (lp_buf[r]) free(lp_buf[r]);
        if (hp_buf[r]) free(hp_buf[r]);
    }
}
#endif  /* FUSED_WAVELET_LEVELS >= 2 */

#if FUSED_WAVELET_LEVELS >= 3
/* Run the level-2 wavelet on a channel's already-produced (unquantized) LL1
   buffer. LL1 lives in cs->band_data_l1[0] at (bw1 × bh1) = (band_width_l1 ×
   band_height_l1). Outputs 4 quantised bands into cs->band_data_l2[0..3] at
   (bw1/2 × bh1/2):
       [0] LL2, [1] LH2, [2] HL2, [3] HH2.

   Mirrors run_level1_wavelet exactly: same prescale=2 streaming pattern.
   Caller must ensure LL1 was produced lossless (divisor=1 in midpoint_l1[0] /
   multiplier_l1[0] when FUSED_WAVELET_LEVELS>=3). */
static void run_level2_wavelet(FUSED_CHANNEL_STATE *cs)
{
    const int in_w = cs->band_width_l1;
    const int in_h = cs->band_height_l1;
    const int bw2  = cs->band_width_l2;
    const int bh2  = cs->band_height_l2;
    const int prescale = 2;
    const int log_bits = 16;  /* conservative — disables int16 fast path */

    PIXEL *lp_buf[FUSED_ROW_BUFS];
    PIXEL *hp_buf[FUSED_ROW_BUFS];
    for (int r = 0; r < FUSED_ROW_BUFS; r++) {
        lp_buf[r] = (PIXEL *)calloc(bw2, sizeof(PIXEL));
        hp_buf[r] = (PIXEL *)calloc(bw2, sizeof(PIXEL));
        if (!lp_buf[r] || !hp_buf[r]) goto cleanup;
    }

    int buf_row = 0;
    int out_row = 0;

    PIXEL *ll1 = cs->band_data_l1[0];

    for (int row = 0; row < in_h; row++) {
        const PIXEL *src = ll1 + (size_t)row * in_w;
        int idx = buf_row % FUSED_ROW_BUFS;
        horizontal_filter(src, lp_buf[idx], hp_buf[idx], in_w, prescale, log_bits);
        buf_row++;

        if (buf_row >= 6 && (buf_row % 2) == 0) {
            if (out_row >= bh2) continue;
            int is_top = (out_row == 0);
            int is_bottom = (out_row == bh2 - 1);

            PIXEL *lp_rows[6], *hp_rows[6];
            int base = (buf_row - 6) % FUSED_ROW_BUFS;
            for (int r = 0; r < 6; r++) {
                int ii = (base + r) % FUSED_ROW_BUFS;
                lp_rows[r] = lp_buf[ii];
                hp_rows[r] = hp_buf[ii];
            }

            PIXEL *ll2 = cs->band_data_l2[0] + (size_t)out_row * bw2;
            PIXEL *lh2 = cs->band_data_l2[1] + (size_t)out_row * bw2;
            PIXEL *hl2 = cs->band_data_l2[2] + (size_t)out_row * bw2;
            PIXEL *hh2 = cs->band_data_l2[3] + (size_t)out_row * bw2;

            vertical_filter_quantize_row(lp_rows, bw2,
                cs->midpoint_l2[0], cs->multiplier_l2[0],
                cs->midpoint_l2[1], cs->multiplier_l2[1],
                0, 0, 0, 0,
                ll2, lh2, NULL, NULL,
                is_top, is_bottom);

            vertical_filter_quantize_row(hp_rows, bw2,
                cs->midpoint_l2[2], cs->multiplier_l2[2],
                cs->midpoint_l2[3], cs->multiplier_l2[3],
                0, 0, 0, 0,
                hl2, hh2, NULL, NULL,
                is_top, is_bottom);

            out_row++;
        }
    }
    /* Trailing band rows untouched (calloc'd zero) — same as level 0/1. */

cleanup:
    for (int r = 0; r < FUSED_ROW_BUFS; r++) {
        if (lp_buf[r]) free(lp_buf[r]);
        if (hp_buf[r]) free(hp_buf[r]);
    }
}
#endif  /* FUSED_WAVELET_LEVELS >= 3 */

static void *pass1_channel_thread(void *arg) {
    PASS1_CHANNEL_TASK *t = (PASS1_CHANNEL_TASK *)arg;
    if (t->ring) {
        pass1_run_channel_consumer(t->channel, t->width, t->height,
                                    t->prescale, t->log_bits, t->cs, t->ring);
    } else {
        pass1_run_channel(t->channel, t->raw_bayer, t->width, t->height,
                          t->log_bits, t->is_rggb, t->prescale, t->cs);
    }

#if FUSED_WAVELET_LEVELS >= 2
    /* Run the level-1 wavelet on this channel's LL0 buffer.
       Done inside the per-channel Pass 1 thread so all 4 channels' level-1
       passes run in parallel. The LL0 buffer (cs->band_data[0]) was produced
       with divisor=1 (no quantization) by Pass 1, so level-1 sees true values. */
    run_level1_wavelet(t->cs);
#endif

#if FUSED_WAVELET_LEVELS >= 3
    /* Run the level-2 wavelet on this channel's LL1 buffer.
       In 3-level mode, setup_channel_state sets LL1's divisor to 1, so
       band_data_l1[0] holds the unquantized level-1 lowpass needed here. */
    run_level2_wavelet(t->cs);
#endif

    /* Signal that this channel's Pass 1 is complete — unblocks its P2 bands */
    if (t->sync) {
        pthread_mutex_lock(&t->sync->lock);
        t->sync->p1_done[t->channel] = 1;
        pthread_cond_broadcast(&t->sync->cv);
        pthread_mutex_unlock(&t->sync->lock);
    }
    return NULL;
}

/* One-time channel state setup. In inline_mode, skips the per-band full-image
   buffers and allocates per-row scratch instead — ~85 MB savings at 23 MP,
   ~200 MB at 50 MP.
   When FUSED_WAVELET_LEVELS >= 2, inline_mode is forced off (the level-1 pass
   needs the full LL0 buffer materialised). */
static int setup_channel_state(
    FUSED_CHANNEL_STATE ch_state[4],
    int width, int height, int quality, int inline_mode,
    int *out_is_rggb, int *out_log_bits,
    int32_t out_base_divisors[4])
{
    int ch_width = width / 2;
    int ch_height = height / 2;
    const QUANT *qt = quality_tables[(quality >= 0 && quality < 9) ? quality : 3];

    /* The quality_tables row layout is for the production encoder's 3-level
       codec: [LL_final, LH_L2, HL_L2, HH_L2, LH_L1, HL_L1, HH_L1, LH_L0, HL_L0, HH_L0].
       In single-level mode the 3 highpass bands ARE the finest level (level 0):
         use qt[7..9] for LH/HL/HH. LL uses FUSED_LL_DIVISOR.
       In 2-level mode:
         LL0 is intermediate (NOT emitted) — use divisor=1 so the level-1
              wavelet sees unquantized values, matching production's "all
              LL bands use qt[0]=1" behaviour.
         LH0/HL0/HH0 use qt[7..9] (finest-level highpass).
         Level-1 quant params (midpoint_l1/multiplier_l1) are set from qt[4..6]
              plus FUSED_LL_DIVISOR for LL1. */
#if FUSED_WAVELET_LEVELS >= 3
    /* In 3-level mode both LL0 and LL1 must be unquantized so the next
       deeper wavelet sees true coefficients. LL2 is the deepest LL.
       Default: quantize by FUSED_LL2_DIVISOR. With FUSED_LL2_LOSSLESS=1,
       LL2 is also stored unquantized (divisor=1) and goes through the
       fixed-width u16-BE path in Pass 2 instead of rANS, sidestepping
       the alphabet-cap quantization that caused visible cascade ringing. */
    int base_divisors[4] = { 1, qt[7], qt[8], qt[9] };  /* LL0 lossless */
    #if FUSED_HF_ALL_LOSSLESS
    /* Experimental: every HF band lossless (huge file, used for ringing
       isolation experiments). */
    int base_divisors_l1[4] = { 1, 1, 1, 1 };
    int base_divisors_l2[4] = { 1, 1, 1, 1 };
    #else
    int base_divisors_l1[4] = { 1, qt[4], qt[5], qt[6] }; /* LL1 lossless */
    #if FUSED_LL2_LOSSLESS
    int base_divisors_l2[4] = { 1, qt[1], qt[2], qt[3] };  /* LL2 lossless too */
    #else
    int base_divisors_l2[4] = { FUSED_LL2_DIVISOR, qt[1], qt[2], qt[3] };
    #endif
    #endif
#elif FUSED_WAVELET_LEVELS >= 2
    int base_divisors[4] = { 1, qt[7], qt[8], qt[9] };  /* LL0 lossless */
    int base_divisors_l1[4] = { FUSED_LL1_DIVISOR, qt[4], qt[5], qt[6] };
#else
    int base_divisors[4] = { FUSED_LL_DIVISOR, qt[7], qt[8], qt[9] };
#endif
    if (out_base_divisors) {
        for (int band = 0; band < 4; band++) out_base_divisors[band] = base_divisors[band];
    }
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 0; band < 4; band++) {
            ch_state[ch].midpoint[band] = get_midpoint(base_divisors[band]);
            ch_state[ch].multiplier[band] = get_multiplier(base_divisors[band]);
        }
#if FUSED_WAVELET_LEVELS >= 2
        for (int band = 0; band < 4; band++) {
            ch_state[ch].midpoint_l1[band] = get_midpoint(base_divisors_l1[band]);
            ch_state[ch].multiplier_l1[band] = get_multiplier(base_divisors_l1[band]);
        }
#endif
#if FUSED_WAVELET_LEVELS >= 3
        for (int band = 0; band < 4; band++) {
            ch_state[ch].midpoint_l2[band] = get_midpoint(base_divisors_l2[band]);
            ch_state[ch].multiplier_l2[band] = get_multiplier(base_divisors_l2[band]);
        }
#endif
        ch_state[ch].band_width = ch_width / 2;
        ch_state[ch].band_height = ch_height / 2;
        ch_state[ch].band_pitch = ch_state[ch].band_width;
        ch_state[ch].band_out_row = 0;
        ch_state[ch].buf_row = 0;
        memset(ch_state[ch].freq, 0, sizeof(ch_state[ch].freq));
        memset(ch_state[ch].run_state, 0, sizeof(ch_state[ch].run_state));

        int bw = ch_state[ch].band_width;
        int bh = ch_state[ch].band_height;
        for (int band = 0; band < 4; band++) {
            if (inline_mode) {
                /* Need only a small row scratch instead of the full band */
                ch_state[ch].band_data[band] = NULL;
                ch_state[ch].row_scratch[band] = (PIXEL *)calloc(bw, sizeof(PIXEL));
                if (!ch_state[ch].row_scratch[band]) return -1;
            } else {
                ch_state[ch].band_data[band] = (PIXEL *)calloc(bw * bh, sizeof(PIXEL));
                ch_state[ch].row_scratch[band] = NULL;
                if (!ch_state[ch].band_data[band]) return -1;
            }
        }
        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            ch_state[ch].lowpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            ch_state[ch].highpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            if (!ch_state[ch].lowpass_buf[r] || !ch_state[ch].highpass_buf[r]) return -1;
        }

#if FUSED_WAVELET_LEVELS >= 2
        /* Allocate level-1 band buffers (1/4 the size of level-0 bands). */
        int bw1 = bw / 2;
        int bh1 = bh / 2;
        ch_state[ch].band_width_l1 = bw1;
        ch_state[ch].band_height_l1 = bh1;
        for (int band = 0; band < 4; band++) {
            ch_state[ch].band_data_l1[band] = (PIXEL *)calloc((size_t)bw1 * bh1, sizeof(PIXEL));
            if (!ch_state[ch].band_data_l1[band]) return -1;
        }
#endif
#if FUSED_WAVELET_LEVELS >= 3
        /* Allocate level-2 band buffers (1/4 the size of level-1 bands = 1/16 level-0). */
        int bw2 = bw1 / 2;
        int bh2 = bh1 / 2;
        ch_state[ch].band_width_l2 = bw2;
        ch_state[ch].band_height_l2 = bh2;
        for (int band = 0; band < 4; band++) {
            ch_state[ch].band_data_l2[band] = (PIXEL *)calloc((size_t)bw2 * bh2, sizeof(PIXEL));
            if (!ch_state[ch].band_data_l2[band]) return -1;
        }
#endif
    }
    (void)ch_height;
    *out_is_rggb = 0; *out_log_bits = 14; /* caller sets actual values */
    return 0;
}


/* ================================================================
   Pass 2: rANS Encode using pre-counted frequencies
   ================================================================ */


typedef struct {
    int channel;        /* Which channel's P1 we depend on (0..3) */
    /* Split mode: scan band_data here in Pass 2's tokenize+rANS */
    PIXEL *band_data;
    int width, height, pitch;
    /* Inline mode: pre-built tokens/freq/bitbuf from Pass 1, just rANS-encode */
    JANS_INLINE_STATE *inline_state;
    /* Common */
    uint8_t *enc_buf;
    size_t enc_cap;
    int enc_size;
    CHANNEL_SYNC *sync;
    /* Optional wavelet-domain denoise (split mode only; ignored if inline). */
    double denoise_strength;
    double noise_scale;
    double noise_offset;
    /* Lossless-LL fast path: bypass rANS entirely, emit fixed-width u16-BE
       coefficients (see FUSED_LL2_LOSSLESS comment above). When set,
       inline_state and band_data semantics are unchanged but the encode
       step is replaced. */
    int lossless_u16_be;
} PASS2_BAND_TASK;

static void fused_denoise_band(PIXEL *band_data, int width, int height,
                               int pitch_bytes,
                               double noise_scale, double noise_offset,
                               double strength);

static void *pass2_band_thread(void *arg) {
    PASS2_BAND_TASK *t = (PASS2_BAND_TASK *)arg;

    /* Wait for our channel's Pass 1 to complete (overlap with other channels' P1) */
    if (t->sync) {
        pthread_mutex_lock(&t->sync->lock);
        while (!t->sync->p1_done[t->channel]) {
            pthread_cond_wait(&t->sync->cv, &t->sync->lock);
        }
        pthread_mutex_unlock(&t->sync->lock);
    }

    if (t->lossless_u16_be) {
        /* Lossless LL2 path: write fixed-width u16-BE per coefficient with a
           magic+dims header. See FUSED_LL2_LOSSLESS comment for format.
           This entirely bypasses rANS and the 2047-magnitude alphabet cap. */
        const int w = t->width, h = t->height;
        const size_t needed = (size_t)8 + (size_t)2 * w * h;
        if (needed > t->enc_cap) {
            t->enc_size = -1;
            return NULL;
        }
        uint8_t *p = t->enc_buf;
        /* Magic 0xFEFEFEFE distinguishes this from the stripe-format magic
           0xFFFFFFFF and from the legacy 3-byte token-count framing. */
        p[0] = 0xFE; p[1] = 0xFE; p[2] = 0xFE; p[3] = 0xFE;
        p[4] = (uint8_t)((w >> 8) & 0xFF); p[5] = (uint8_t)(w & 0xFF);
        p[6] = (uint8_t)((h >> 8) & 0xFF); p[7] = (uint8_t)(h & 0xFF);
        p += 8;
        const int32_t *src = (const int32_t *)t->band_data;
        const int pitch_pix = t->pitch / (int)sizeof(int32_t);
        for (int r = 0; r < h; r++) {
            const int32_t *row = src + (size_t)r * pitch_pix;
            for (int c = 0; c < w; c++) {
                int32_t v = row[c];
                if (v < 0) v = 0; else if (v > 65535) v = 65535;
                *p++ = (uint8_t)((v >> 8) & 0xFF);
                *p++ = (uint8_t)(v & 0xFF);
            }
        }
        t->enc_size = (int)needed;
        return NULL;
    }

    if (t->inline_state) {
        /* Inline mode: Pass 1 already tokenized; just do rANS encode + emit */
        t->enc_size = jans_inline_finalize(t->enc_buf, t->enc_cap, t->inline_state);
    } else {
        /* Split mode: optional wavelet-domain denoise, then tokenize + rANS */
        if (t->denoise_strength > 0.0) {
            fused_denoise_band(t->band_data, t->width, t->height, t->pitch,
                               t->noise_scale, t->noise_offset,
                               t->denoise_strength);
        }
        t->enc_size = jans_encode_band_x4(t->enc_buf, t->enc_cap,
                                           (const int32_t *)t->band_data,
                                           t->width, t->height, t->pitch);
    }
    return NULL;
}


static int fused_pass2(
    FUSED_CHANNEL_STATE ch_state[4],
    uint8_t *output_buf, size_t output_cap, size_t *output_written
)
{
    size_t pos = 0;

    /* Parallel encode: 12 independent band tasks (4 channels × 3 highpass bands).
       Allocate buffers and dispatch threads. */
    PASS2_BAND_TASK tasks[FUSED_NUM_P2_TASKS];
    pthread_t threads[FUSED_NUM_P2_TASKS];
    int task_count = 0;
    int created[FUSED_NUM_P2_TASKS];

    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ch_state[ch];
        for (int band = 0; band < 4; band++) {
            PASS2_BAND_TASK *t = &tasks[task_count];
            t->band_data = cs->band_data[band];
            t->width = cs->band_width;
            t->height = cs->band_height;
            t->pitch = cs->band_width * sizeof(int32_t);
            t->enc_cap = (size_t)t->width * t->height * 4 + 8192;
            t->enc_buf = (uint8_t *)malloc(t->enc_cap);
            t->enc_size = 0;
            t->lossless_u16_be = 0;  /* legacy path: no lossless LL */
            if (!t->enc_buf) return -1;

            /* Spawn thread */
            created[task_count] = (pthread_create(&threads[task_count], NULL,
                                                    pass2_band_thread, t) == 0);
            if (!created[task_count]) pass2_band_thread(t);
            task_count++;
        }
    }

    /* Wait for all threads, then concatenate outputs in order */
    for (int i = 0; i < task_count; i++) {
        if (created[i]) pthread_join(threads[i], NULL);
    }

    /* Sequential output concat (preserves band order) */
    for (int i = 0; i < task_count; i++) {
        PASS2_BAND_TASK *t = &tasks[i];
        if (t->enc_size > 0 && pos + t->enc_size <= output_cap) {
            memcpy(output_buf + pos, t->enc_buf, t->enc_size);
            pos += t->enc_size;
        }
        free(t->enc_buf);
    }

    *output_written = pos;
    return 0;
}

/* OLD serial version kept for reference */
static int fused_pass2_serial(
    FUSED_CHANNEL_STATE ch_state[4],
    uint8_t *output_buf, size_t output_cap, size_t *output_written
)
{
    size_t pos = 0;

    /* For each channel, for each highpass band: rANS encode */
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ch_state[ch];

        for (int band = 0; band < 4; band++) {
            PIXEL *data = cs->band_data[band];
            int bw = cs->band_width;
            int bh = cs->band_height;
            int pitch = bw * sizeof(int32_t);

            /* Encode band using existing jans_encode_band_x4 */
            size_t buf_cap = (size_t)bw * bh * 4 + 8192;
            uint8_t *enc_buf = (uint8_t *)malloc(buf_cap);
            if (!enc_buf) return -1;

            int enc_size = jans_encode_band_x4(enc_buf, buf_cap,
                                                (const int32_t *)data,
                                                bw, bh, pitch);
            if (enc_size > 0 && pos + enc_size <= output_cap) {
                memcpy(output_buf + pos, enc_buf, enc_size);
                pos += enc_size;
            }
            free(enc_buf);
        }
    }

    *output_written = pos;
    return 0;
}

/* ================================================================
   Reusable encoder context (for video / batch frames)
   ================================================================ */

struct FUSED_ENCODER {
    int width, height;
    int pixel_format;
    int quality;
    int is_rggb;
    int log_bits;
    int prescale;
    int inline_mode;  /* 1 = tokenize inline in Pass 1 (low DRAM, embedded);
                          0 = split-pass (band_data buffer + Pass 2 tokenize) */

    FUSED_CHANNEL_STATE ch_state[4];

    /* Persistent Pass 2 enc buffers (one per band) */
    uint8_t *enc_bufs[FUSED_NUM_P2_TASKS];
    size_t   enc_caps[FUSED_NUM_P2_TASKS];

    /* Persistent output stream buffer */
    uint8_t *stream_buf;
    size_t   stream_cap;

    /* Wavelet-domain denoise (BayesShrink). When denoise_strength > 0,
       inline mode is disabled (split-pass only — denoise needs the band
       buffer to compute per-band thresholds). noise_scale/noise_offset
       are in raw-pixel units (multiply DNG NoiseProfile by max_val and
       max_val^2 respectively before passing in). */
    double   noise_scale;
    double   noise_offset;
    double   denoise_strength;

    /* Per-band base divisors from the chosen quality preset; the actual
       midpoint/multiplier in ch_state are derived from base × quant_scale.
       quant_scale defaults to 1.0; the video encoder's rate controller
       varies it per frame to hit a target bitrate. Larger scale → more
       aggressive quantization → smaller output. */
    int32_t  base_divisors[FUSED_MAX_BANDS];
    double   quant_scale;

    /* Shared 4-channel unpack ring. Producer thread fills, 4 P1 channel
       threads consume. When NULL, falls back to the legacy per-channel
       unpack inside each P1 thread. */
    UNPACK_RING *unpack_ring;
};

/* Decide which mode to use. Default: inline mode when CPU count is ≤6
   (typical embedded camera SoC like GP3 with 4× A78). M1 / large servers
   default to split-pass for the wider Pass 2 parallelism. Override via env. */
static int fused_choose_inline_mode(void) {
    const char *env = getenv("FUSED_INLINE_TOKENIZE");
    if (env) {
        if (env[0] == '0') return 0;
        if (env[0] == '1') return 1;
    }
    long ncpu = sysconf(_SC_NPROCESSORS_ONLN);
    return (ncpu > 0 && ncpu <= 6) ? 1 : 0;
}

/* Reset just the per-frame state on a context (counters, run state, freq tables,
   inline-tokenize state). Band buffers / row scratch are overwritten as work
   progresses so no per-frame zeroing needed. */
static void fused_reset_frame_state(FUSED_ENCODER *ctx) {
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        cs->band_out_row = 0;
        cs->buf_row = 0;
        memset(cs->freq, 0, sizeof(cs->freq));
        memset(cs->run_state, 0, sizeof(cs->run_state));
        for (int band = 0; band < 4; band++) {
            if (cs->inline_state[band]) jans_inline_reset(cs->inline_state[band]);
        }
#if FUSED_WAVELET_LEVELS >= 2
        /* Zero the level-1 band buffers: the streaming level-1 wavelet does
           not produce values for the bottom 2 rows (6-tap filter underflows),
           so without zeroing previous frames' values would leak through. */
        size_t l1_bytes = (size_t)cs->band_width_l1 * cs->band_height_l1 * sizeof(PIXEL);
        for (int band = 0; band < 4; band++) {
            if (cs->band_data_l1[band]) memset(cs->band_data_l1[band], 0, l1_bytes);
        }
#endif
#if FUSED_WAVELET_LEVELS >= 3
        /* Same rationale for level-2 bands. */
        size_t l2_bytes = (size_t)cs->band_width_l2 * cs->band_height_l2 * sizeof(PIXEL);
        for (int band = 0; band < 4; band++) {
            if (cs->band_data_l2[band]) memset(cs->band_data_l2[band], 0, l2_bytes);
        }
#endif
    }
    if (ctx->unpack_ring) {
        for (int s = 0; s < UNPACK_RING_SIZE; s++) {
            ctx->unpack_ring->slot_row[s] = s - UNPACK_RING_SIZE;
        }
        for (int p = 0; p < UNPACK_PRODUCERS; p++) {
            ctx->unpack_ring->prod_max_row[p] = -1;
        }
        for (int c = 0; c < 4; c++) ctx->unpack_ring->consumed[c] = 0;
    }
}

FUSED_ENCODER *gpr_encode_fused_create(int width, int height, int pixel_format, int quality) {
    FUSED_ENCODER *ctx = (FUSED_ENCODER *)calloc(1, sizeof(*ctx));
    if (!ctx) return NULL;
    ctx->width = width;
    ctx->height = height;
    ctx->pixel_format = pixel_format;
    ctx->quality = quality;
    ctx->is_rggb = (pixel_format == 1 || pixel_format == 0 || pixel_format == 4);
    ctx->log_bits = (pixel_format >= 4) ? 16 : 14;
    ctx->prescale = 2;
    ctx->inline_mode = fused_choose_inline_mode();
#if FUSED_WAVELET_LEVELS >= 2
    /* Multi-level mode requires the LL0 band buffer to be materialised so the
       level-1 wavelet can read it. Inline tokenisation streams band rows to
       per-band rANS state without keeping a band buffer, so it is incompatible
       with multi-level. Force split-pass mode here. */
    ctx->inline_mode = 0;
#endif

    SetupEncoderLogCurve();

    int dummy_is_rggb, dummy_log_bits;
    if (setup_channel_state(ctx->ch_state, width, height, quality,
                             ctx->inline_mode,
                             &dummy_is_rggb, &dummy_log_bits,
                             ctx->base_divisors) != 0) {
        gpr_encode_fused_destroy(ctx);
        return NULL;
    }
    ctx->quant_scale = 1.0;

    /* Pre-allocate persistent enc buffers + (if inline) inline-tokenize state.
       In single-level mode: 4 bands per channel (LL0, LH0, HL0, HH0).
       In 2-level mode: 7 bands per channel (LL1, LH1, HL1, HH1, LH0, HL0, HH0).
       Inline tokenisation is disabled in 2-level mode (the level-1 pass needs
       the full LL0 buffer materialised, which is incompatible with inline). */
    int p2_idx = 0;
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        size_t band_coeffs_l0 = (size_t)cs->band_width * cs->band_height;
        for (int band = 0; band < FUSED_BANDS_PER_CHANNEL; band++) {
            /* Allocate enc buffer sized for this band's dimensions. In 2-level
               mode the first 4 bands are level-1 (smaller) and the next 3
               are level-0 (full size). In 3-level mode bands 0..3 are level-2,
               4..6 are level-1, and 7..9 are level-0. */
            size_t this_coeffs = band_coeffs_l0;
#if FUSED_WAVELET_LEVELS == 3
            if (band < 4) {
                this_coeffs = (size_t)cs->band_width_l2 * cs->band_height_l2;
            } else if (band < 7) {
                this_coeffs = (size_t)cs->band_width_l1 * cs->band_height_l1;
            }
#elif FUSED_WAVELET_LEVELS == 2
            if (band < 4) {
                this_coeffs = (size_t)cs->band_width_l1 * cs->band_height_l1;
            }
#endif
            size_t cap = this_coeffs * 4 + 8192;
            ctx->enc_caps[p2_idx] = cap;
            ctx->enc_bufs[p2_idx] = (uint8_t *)malloc(cap);
            if (!ctx->enc_bufs[p2_idx]) {
                gpr_encode_fused_destroy(ctx);
                return NULL;
            }
            if (ctx->inline_mode && band < 4) {
                /* Stripe encoding: adaptive default based on band height,
                   overridable via env vars.

                   Sweep data:
                     23 MP HERO10 (band_height=1044): 128 wins (4.36 MB vs
                       4.39 MB at 64 — 0.7% better)
                     50 MP MISSION 1 (band_height=1450): 64 wins (9.50 MB vs
                       10.55 MB at 128 — 10% better)
                   Larger bands benefit from more stripes (tighter local
                   freq fit per stripe outweighs per-stripe table overhead).

                   Heuristic: 128 below 1200 rows, 64 above.
                   Env overrides take precedence. */
                int rows = (cs->band_height < 1200) ? 128 : 64;
                const char *e_global = getenv("FUSED_STRIPE_ROWS");
                if (e_global) { int v = atoi(e_global); if (v > 0) rows = v; }
                const char *band_env = NULL;
                if (band == 1) band_env = getenv("FUSED_STRIPE_ROWS_LH");
                if (band == 2) band_env = getenv("FUSED_STRIPE_ROWS_HL");
                if (band == 3) band_env = getenv("FUSED_STRIPE_ROWS_HH");
                if (band_env) { int v = atoi(band_env); if (v > 0) rows = v; }

                size_t stripe_coeffs = (size_t)cs->band_width * (size_t)rows;
                if (stripe_coeffs > band_coeffs_l0) stripe_coeffs = band_coeffs_l0;
                cs->inline_state[band] = jans_inline_create(stripe_coeffs);
                if (!cs->inline_state[band]) {
                    gpr_encode_fused_destroy(ctx);
                    return NULL;
                }
                jans_inline_set_stripe_rows(cs->inline_state[band], rows);
            }
            p2_idx++;
        }
    }

    /* Pre-allocate output stream buffer */
    ctx->stream_cap = (size_t)width * height * 2;
    ctx->stream_buf = (uint8_t *)malloc(ctx->stream_cap);
    if (!ctx->stream_buf) {
        gpr_encode_fused_destroy(ctx);
        return NULL;
    }

    /* Pre-allocate the shared 4-channel unpack ring (producer + 4 consumers).
       Can be disabled via FUSED_PRODUCER_UNPACK=0 to fall back to the legacy
       per-channel unpack inside each P1 thread. */
    int use_producer = 1;
    const char *prod_env = getenv("FUSED_PRODUCER_UNPACK");
    if (prod_env && prod_env[0] == '0') use_producer = 0;
    if (use_producer) {
        ctx->unpack_ring = (UNPACK_RING *)calloc(1, sizeof(UNPACK_RING));
        if (!ctx->unpack_ring ||
            unpack_ring_init(ctx->unpack_ring, width / 2, height / 2) != 0) {
            gpr_encode_fused_destroy(ctx);
            return NULL;
        }
    }

    /* Lazy paging strategy: skip pre-fault on stream_buf and enc_bufs (both
       are heavily over-sized for the typical encoded output ~10% of capacity).
       Only band_data is pre-faulted in split mode because vert+quant writes
       every pixel; inline mode doesn't allocate band_data at all.

       This pushes ~150 MB of RSS off the books at 50 MP, paid only for the
       actually-written portion of each buffer. */
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        for (int band = 0; band < 4; band++) {
            if (cs->band_data[band]) {
                memset(cs->band_data[band], 0,
                       (size_t)cs->band_width * cs->band_height * sizeof(PIXEL));
            }
        }
    }

    return ctx;
}

void gpr_encode_fused_set_denoise(FUSED_ENCODER *ctx,
                                  double noise_scale,
                                  double noise_offset,
                                  double strength)
{
    if (!ctx) return;
    if (strength > 0.0 && ctx->inline_mode) {
        fprintf(stderr, "gpr_encode_fused_set_denoise: denoise requires split mode; "
                        "set FUSED_INLINE_TOKENIZE=0 before gpr_encode_fused_create. "
                        "Denoise NOT enabled.\n");
        return;
    }
    ctx->noise_scale = noise_scale;
    ctx->noise_offset = noise_offset;
    ctx->denoise_strength = strength;
}

void gpr_encode_fused_set_quant_scale(FUSED_ENCODER *ctx, double scale)
{
    if (!ctx) return;
    if (scale < 0.25) scale = 0.25;
    if (scale > 16.0) scale = 16.0;
    if (scale == ctx->quant_scale) return;   /* no-op */
    ctx->quant_scale = scale;
    for (int band = 0; band < 4; band++) {
        int eff_divisor = (int)((double)ctx->base_divisors[band] * scale + 0.5);
        if (eff_divisor < 1) eff_divisor = 1;
        int32_t mp = get_midpoint(eff_divisor);
        int32_t ml = get_multiplier(eff_divisor);
        for (int ch = 0; ch < 4; ch++) {
            ctx->ch_state[ch].midpoint[band]   = mp;
            ctx->ch_state[ch].multiplier[band] = ml;
        }
    }
}

/* Per-band BayesShrink denoise: estimate noise sigma from this band (MAD on
   the band itself, since the fused encoder doesn't keep an LL band around for
   calibrated sigma), compute the threshold, then noise-aware-requantize. Falls
   back to soft-thresholding when the band is pure noise (no signal energy). */
static void fused_denoise_band(PIXEL *band_data, int width, int height,
                               int pitch_bytes,
                               double noise_scale, double noise_offset,
                               double strength)
{
    if (!band_data || strength <= 0.0) return;

    /* Estimate noise sigma. Prefer calibrated noise model when available
       (operates on the band's local mean signal), otherwise MAD. */
    double sigma_noise;
    if (noise_scale > 0.0) {
        sigma_noise = CalibratedNoiseSigma(band_data, width, height,
                                            pitch_bytes,
                                            noise_scale, noise_offset);
    } else {
        sigma_noise = EstimateNoiseSigma(band_data, width, height, pitch_bytes);
    }
    if (sigma_noise <= 0.0) return;

    /* Sample band variance for the BayesShrink threshold. Stride directly
       across band_data — old code iterated every pixel just to sample every
       Nth, wasting ~99% of the loop body on a modulo check. */
    int pitch_pixels = pitch_bytes / (int)sizeof(PIXEL);
    int N = width * height;
    int step = (N > 10000) ? (N / 10000) : 1;
    int sample_target = (N + step - 1) / step;
    if (sample_target > 10000) sample_target = 10000;
    double sum_sq = 0.0;
    int sample_count = 0;
    for (int s = 0; s < sample_target; s++) {
        int idx = s * step;
        int row = idx / width;
        if (row >= height) break;
        int col = idx - row * width;
        double v = (double)band_data[row * pitch_pixels + col];
        sum_sq += v * v;
        sample_count++;
    }
    double sigma_band_sq = (sample_count > 0) ? sum_sq / sample_count : 0.0;
    double sigma_noise_sq = sigma_noise * sigma_noise;
    double sigma_signal_sq = sigma_band_sq - sigma_noise_sq;

    if (sigma_signal_sq > sigma_noise_sq * 0.01) {
        /* Signal present: noise-aware requantize at sigma_noise step. */
        NoiseAwareRequantize(band_data, width, height, pitch_bytes,
                             sigma_noise, strength);
    } else {
        /* Pure noise band: soft threshold at the VisuShrink scale. */
        double T = sigma_noise * sqrt(2.0 * log((double)N)) * strength;
        SoftThresholdBand(band_data, width, height, pitch_bytes, T);
    }
}

void gpr_encode_fused_destroy(FUSED_ENCODER *ctx) {
    if (!ctx) return;
    if (ctx->unpack_ring) {
        unpack_ring_destroy(ctx->unpack_ring);
        free(ctx->unpack_ring);
        ctx->unpack_ring = NULL;
    }
    for (int i = 0; i < FUSED_NUM_P2_TASKS; i++) if (ctx->enc_bufs[i]) free(ctx->enc_bufs[i]);
    if (ctx->stream_buf) free(ctx->stream_buf);
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        for (int band = 0; band < 4; band++) {
            if (cs->band_data[band])   free(cs->band_data[band]);
            if (cs->row_scratch[band]) free(cs->row_scratch[band]);
            if (cs->inline_state[band]) jans_inline_destroy(cs->inline_state[band]);
#if FUSED_WAVELET_LEVELS >= 2
            if (cs->band_data_l1[band]) free(cs->band_data_l1[band]);
#endif
#if FUSED_WAVELET_LEVELS >= 3
            if (cs->band_data_l2[band]) free(cs->band_data_l2[band]);
#endif
        }
        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            if (cs->lowpass_buf[r])  free(cs->lowpass_buf[r]);
            if (cs->highpass_buf[r]) free(cs->highpass_buf[r]);
        }
    }
    free(ctx);
}

int gpr_encode_fused_frame(FUSED_ENCODER *ctx,
                            const uint8_t *raw_bayer, size_t raw_size,
                            uint8_t **vc5_out, size_t *vc5_size)
{
    (void)raw_size;
    if (!ctx || !raw_bayer || !vc5_out || !vc5_size) return -1;
    int rc = 0;
    PASS2_BAND_TASK p2_tasks[FUSED_NUM_P2_TASKS];
    memset(p2_tasks, 0, sizeof(p2_tasks));
    pthread_t p2_threads[FUSED_NUM_P2_TASKS];
    int p2_created[FUSED_NUM_P2_TASKS] = {0};
    pthread_t p1_threads[4];
    int p1_created[4] = {0};

#ifdef FUSED_TIMING
    double t0 = _fused_ms();
#endif

    const char *threads_env = getenv("FUSED_THREADS");
    int run_serial = (threads_env && threads_env[0] == '1' && threads_env[1] == '\0');

    fused_reset_frame_state(ctx);

    CHANNEL_SYNC sync;
    pthread_mutex_init(&sync.lock, NULL);
    pthread_cond_init(&sync.cv, NULL);
    for (int i = 0; i < 4; i++) sync.p1_done[i] = 0;

    /* Producer-unpack threads: when ctx->unpack_ring is set and we're running
       parallel, UNPACK_PRODUCERS dedicated threads cooperatively do the
       combined 4-channel Bayer unpack (deinterleaved NEON load, 4 unique LUT
       lookups per Bayer block, branchless clip) and the 4 channel threads
       consume from the ring. Falls back to per-channel unpack inside each P1
       thread when the ring is disabled or run_serial. */
    UNPACK_RING *ring = (!run_serial) ? ctx->unpack_ring : NULL;
    UNPACK_PRODUCER_TASK prod_tasks[UNPACK_PRODUCERS];
    pthread_t prod_threads[UNPACK_PRODUCERS];
    int prod_created[UNPACK_PRODUCERS] = {0};
    if (ring) {
        for (int p = 0; p < UNPACK_PRODUCERS; p++) {
            prod_tasks[p].ring = ring;
            prod_tasks[p].producer_id = p;
            prod_tasks[p].raw_bayer = raw_bayer;
            prod_tasks[p].width = ctx->width;
            prod_tasks[p].height = ctx->height;
            prod_tasks[p].log_bits = ctx->log_bits;
            prod_tasks[p].is_rggb = ctx->is_rggb;
            prod_created[p] = (pthread_create(&prod_threads[p], NULL,
                                              unpack_producer_thread,
                                              &prod_tasks[p]) == 0);
        }
        /* If we failed to launch ANY producer, abort the ring path; the four
           channel consumers would deadlock waiting for slot_row to advance. */
        int any_failed = 0;
        for (int p = 0; p < UNPACK_PRODUCERS; p++) if (!prod_created[p]) any_failed = 1;
        if (any_failed) {
            /* Wait for whatever did launch, then disable the ring. */
            for (int p = 0; p < UNPACK_PRODUCERS; p++) {
                if (prod_created[p]) pthread_join(prod_threads[p], NULL);
                prod_created[p] = 0;
            }
            ring = NULL;
        }
    }

    PASS1_CHANNEL_TASK p1_tasks[4];
    for (int ch = 0; ch < 4; ch++) {
        p1_tasks[ch].channel = ch;
        p1_tasks[ch].raw_bayer = raw_bayer;
        p1_tasks[ch].width = ctx->width;
        p1_tasks[ch].height = ctx->height;
        p1_tasks[ch].log_bits = ctx->log_bits;
        p1_tasks[ch].is_rggb = ctx->is_rggb;
        p1_tasks[ch].prescale = ctx->prescale;
        p1_tasks[ch].cs = &ctx->ch_state[ch];
        p1_tasks[ch].sync = &sync;
        p1_tasks[ch].ring = ring;
        if (run_serial) {
            pass1_channel_thread(&p1_tasks[ch]);
            p1_created[ch] = 0;
        } else {
            p1_created[ch] = (pthread_create(&p1_threads[ch], NULL,
                                              pass1_channel_thread, &p1_tasks[ch]) == 0);
        }
    }

    int p2_count = 0;
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
#if FUSED_WAVELET_LEVELS == 3
        /* 3-level bitstream band order per channel:
             [0..3] LL2, LH2, HL2, HH2   (from band_data_l2, smallest)
             [4..6] LH1, HL1, HH1        (from band_data_l1[1..3])
             [7..9] LH0, HL0, HH0        (from band_data[1..3], level-0)
           LL0 (band_data[0]) and LL1 (band_data_l1[0]) are intermediates
           and are NOT emitted — they are reconstructed by inverting the
           deeper-level bands. */
        for (int band = 0; band < 10; band++) {
            PASS2_BAND_TASK *pt = &p2_tasks[p2_count];
            pt->channel = ch;
            pt->lossless_u16_be = 0;
            if (band < 4) {
                /* Level-2 band: LL2, LH2, HL2, HH2 */
                pt->band_data    = cs->band_data_l2[band];
                pt->width        = cs->band_width_l2;
                pt->height       = cs->band_height_l2;
                pt->pitch        = cs->band_width_l2 * sizeof(int32_t);
                #if FUSED_LL2_LOSSLESS
                if (band == 0) pt->lossless_u16_be = 1;  /* LL2 bypasses rANS */
                #endif
            } else if (band < 7) {
                /* Level-1 highpass: LH1(=l1[1]), HL1(=l1[2]), HH1(=l1[3]) */
                int l1_band = band - 4 + 1;
                pt->band_data    = cs->band_data_l1[l1_band];
                pt->width        = cs->band_width_l1;
                pt->height       = cs->band_height_l1;
                pt->pitch        = cs->band_width_l1 * sizeof(int32_t);
            } else {
                /* Level-0 highpass: LH0(=band1), HL0(=band2), HH0(=band3) */
                int l0_band = band - 7 + 1;
                pt->band_data    = cs->band_data[l0_band];
                pt->width        = cs->band_width;
                pt->height       = cs->band_height;
                pt->pitch        = cs->band_width * sizeof(int32_t);
            }
            pt->inline_state = NULL;  /* 3-level always uses split mode */
            pt->enc_cap = ctx->enc_caps[p2_count];
            pt->enc_buf = ctx->enc_bufs[p2_count];  /* persistent */
            pt->enc_size = 0;
            pt->sync = &sync;
            pt->denoise_strength = ctx->denoise_strength;
            pt->noise_scale = ctx->noise_scale;
            pt->noise_offset = ctx->noise_offset;
            if (run_serial) {
                pass2_band_thread(pt);
                p2_created[p2_count] = 0;
            } else {
                p2_created[p2_count] = (pthread_create(&p2_threads[p2_count], NULL,
                                                       pass2_band_thread, pt) == 0);
            }
            p2_count++;
        }
#elif FUSED_WAVELET_LEVELS == 2
        /* 2-level bitstream band order per channel:
             [0..3] LL1, LH1, HL1, HH1   (from band_data_l1, smaller dimensions)
             [4..6] LH0, HL0, HH0        (from band_data[1..3], level-0 dimensions)
           LL0 (band_data[0]) is intermediate and is NOT emitted. */
        for (int band = 0; band < 7; band++) {
            PASS2_BAND_TASK *pt = &p2_tasks[p2_count];
            pt->channel = ch;
            pt->lossless_u16_be = 0;
            if (band < 4) {
                /* Level-1 band: LL1, LH1, HL1, HH1 */
                pt->band_data    = cs->band_data_l1[band];
                pt->width        = cs->band_width_l1;
                pt->height       = cs->band_height_l1;
                pt->pitch        = cs->band_width_l1 * sizeof(int32_t);
            } else {
                /* Level-0 highpass: LH0(=band1), HL0(=band2), HH0(=band3) */
                int l0_band = band - 4 + 1;
                pt->band_data    = cs->band_data[l0_band];
                pt->width        = cs->band_width;
                pt->height       = cs->band_height;
                pt->pitch        = cs->band_width * sizeof(int32_t);
            }
            pt->inline_state = NULL;  /* 2-level always uses split mode */
            pt->enc_cap = ctx->enc_caps[p2_count];
            pt->enc_buf = ctx->enc_bufs[p2_count];  /* persistent */
            pt->enc_size = 0;
            pt->sync = &sync;
            pt->denoise_strength = ctx->denoise_strength;
            pt->noise_scale = ctx->noise_scale;
            pt->noise_offset = ctx->noise_offset;
            if (run_serial) {
                pass2_band_thread(pt);
                p2_created[p2_count] = 0;
            } else {
                p2_created[p2_count] = (pthread_create(&p2_threads[p2_count], NULL,
                                                       pass2_band_thread, pt) == 0);
            }
            p2_count++;
        }
#else
        for (int band = 0; band < 4; band++) {
            PASS2_BAND_TASK *pt = &p2_tasks[p2_count];
            pt->channel = ch;
            pt->lossless_u16_be = 0;
            pt->band_data    = cs->band_data[band];     /* NULL in inline mode */
            pt->inline_state = cs->inline_state[band];  /* NULL in split mode */
            pt->width = cs->band_width;
            pt->height = cs->band_height;
            pt->pitch = cs->band_width * sizeof(int32_t);
            pt->enc_cap = ctx->enc_caps[p2_count];
            pt->enc_buf = ctx->enc_bufs[p2_count];  /* persistent */
            pt->enc_size = 0;
            pt->sync = &sync;
            pt->denoise_strength = ctx->denoise_strength;
            pt->noise_scale = ctx->noise_scale;
            pt->noise_offset = ctx->noise_offset;
            if (run_serial) {
                pass2_band_thread(pt);
                p2_created[p2_count] = 0;
            } else {
                p2_created[p2_count] = (pthread_create(&p2_threads[p2_count], NULL,
                                                       pass2_band_thread, pt) == 0);
            }
            p2_count++;
        }
#endif
    }

    if (!run_serial) {
        for (int ch = 0; ch < 4; ch++) {
            if (!p1_created[ch]) pass1_channel_thread(&p1_tasks[ch]);
        }
    }
    for (int ch = 0; ch < 4; ch++) {
        if (p1_created[ch]) pthread_join(p1_threads[ch], NULL);
    }
    for (int p = 0; p < UNPACK_PRODUCERS; p++) {
        if (prod_created[p]) pthread_join(prod_threads[p], NULL);
    }

#ifdef FUSED_TIMING
    double t1 = _fused_ms();
    fprintf(stderr, "  FUSED Pass1 (parallel, signals P2):      %.1fms\n", t1 - t0);
#endif

    for (int i = 0; i < FUSED_NUM_P2_TASKS; i++) {
        if (p2_created[i]) pthread_join(p2_threads[i], NULL);
    }

#ifdef FUSED_TIMING
    double t2 = _fused_ms();
    fprintf(stderr, "  FUSED Pass2 (overlapped w/ P1):          %.1fms (since P1 end)\n", t2 - t1);
#endif

    pthread_mutex_destroy(&sync.lock);
    pthread_cond_destroy(&sync.cv);

    /* Concat into the persistent stream buffer */
    size_t pos = 0;
    for (int i = 0; i < FUSED_NUM_P2_TASKS; i++) {
        PASS2_BAND_TASK *pt = &p2_tasks[i];
        if (pt->enc_size > 0 && pos + pt->enc_size <= ctx->stream_cap) {
            memcpy(ctx->stream_buf + pos, pt->enc_buf, pt->enc_size);
            pos += pt->enc_size;
        }
    }

#ifdef FUSED_TIMING
    double t3 = _fused_ms();
    fprintf(stderr, "  FUSED Total:                             %.1fms\n", t3 - t0);
#endif

    *vc5_out = ctx->stream_buf;  /* context-owned; caller must NOT free */
    *vc5_size = pos;
    return rc;
}

/* ================================================================
   One-shot entry point (back-compat: creates context per call)
   ================================================================ */

int gpr_encode_fused(
    const uint8_t *raw_bayer,
    size_t raw_size,
    int width, int height,
    int pixel_format,
    int quality,
    uint8_t **vc5_out,
    size_t *vc5_size)
{
    FUSED_ENCODER *ctx = gpr_encode_fused_create(width, height, pixel_format, quality);
    if (!ctx) return -1;
    uint8_t *internal_out = NULL;
    size_t internal_size = 0;
    int rc = gpr_encode_fused_frame(ctx, raw_bayer, raw_size, &internal_out, &internal_size);
    if (rc == 0) {
        /* Copy the context-owned bytes into a fresh malloc'd buffer for the caller */
        *vc5_out = (uint8_t *)malloc(internal_size);
        if (!*vc5_out) { rc = -1; goto out; }
        memcpy(*vc5_out, internal_out, internal_size);
        *vc5_size = internal_size;
    }
out:
    gpr_encode_fused_destroy(ctx);
    return rc;
}
