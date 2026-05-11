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
#include <pthread.h>

#define FUSED_TIMING

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
   Constants and quant tables
   ================================================================ */

#define FUSED_MAX_CHANNELS 4
#define FUSED_MAX_WAVELETS 3
#define FUSED_MAX_BANDS    4
#define FUSED_ROW_BUFS     6

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
                               int width, int prescale)
{
    int prescale_rounding = (1 << prescale) - 1;
    int half = width / 2;

    /* Prescale helper */
    #define PS(v) (((v) + prescale_rounding) >> prescale)

    /* Left boundary */
    lowpass[0] = PS(input[0]) + PS(input[1]);
    highpass[0] = PS(input[0]) - PS(input[1]);

    /* Interior */
    {
        int i = 1;
#if ENABLED(NEON)
        const int32x4_t vround = vdupq_n_s32(prescale_rounding);
        const int32x4_t four = vdupq_n_s32(4);
        const int32x4_t neg_ps = vdupq_n_s32(-prescale);

        for (; i + 3 < half - 1; i += 4) {
            /* Output i covers input indices [2i-2 .. 2i+3] (6 inputs per output) */
            /* For 4 outputs (i..i+3): need inputs [2i-2 .. 2i+9] = 12 consecutive inputs */
            int idx = 2 * i;

            /* Load 12 consecutive inputs, prescale them all */
            int32x4_t in_lo  = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx-2]), vround), neg_ps); /* [2i-2 .. 2i+1] */
            int32x4_t in_md  = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx+2]), vround), neg_ps); /* [2i+2 .. 2i+5] */
            int32x4_t in_hi  = vshlq_s32(vaddq_s32(vld1q_s32(&input[idx+6]), vround), neg_ps); /* [2i+6 .. 2i+9] */

            /* Extract even and odd samples for the 4 outputs.
               Output i uses inputs[2i], inputs[2i+1] for current pair.
               Output i+1 uses [2i+2], [2i+3]. Output i+2 uses [2i+4], [2i+5]. Output i+3 uses [2i+6], [2i+7].
               So evens = inputs at offsets 2,4,6,8 from idx-2 = [2i, 2i+2, 2i+4, 2i+6]
                   odds = inputs at offsets 3,5,7,9 from idx-2 = [2i+1, 2i+3, 2i+5, 2i+7] */
            /* Use VEXT to slide and pick: */
            /* in_lo = [2i-2, 2i-1, 2i, 2i+1], in_md = [2i+2, 2i+3, 2i+4, 2i+5], in_hi = [2i+6, 2i+7, 2i+8, 2i+9] */
            /* evens[0..3] = [2i, 2i+2, 2i+4, 2i+6] */
            /* odds[0..3]  = [2i+1, 2i+3, 2i+5, 2i+7] */
            int32x4_t cur_pair = vextq_s32(in_lo, in_md, 2);  /* [2i, 2i+1, 2i+2, 2i+3] */
            int32x4_t nxt_pair = vextq_s32(in_md, in_hi, 2);  /* [2i+4, 2i+5, 2i+6, 2i+7] */
            /* Deinterleave cur_pair and nxt_pair to get evens/odds */
            int32x4x2_t cn = vuzpq_s32(cur_pair, nxt_pair);
            int32x4_t evens = cn.val[0];  /* [2i, 2i+2, 2i+4, 2i+6] */
            int32x4_t odds  = cn.val[1];  /* [2i+1, 2i+3, 2i+5, 2i+7] */

            /* Lowpass = even + odd */
            vst1q_s32(&lowpass[i], vaddq_s32(evens, odds));

            /* For highpass: prev_sum[k] = input[2(i+k)-2] + input[2(i+k)-1]
                              next_sum[k] = input[2(i+k)+2] + input[2(i+k)+3]
               prev_sum_vec = [pair_sum at 2i-2, 2i, 2i+2, 2i+4]
               next_sum_vec = [pair_sum at 2i+2, 2i+4, 2i+6, 2i+8]

               in_lo split: [2i-2, 2i-1, 2i, 2i+1]
                  in_lo even/odd via vuzp:
                    evens_lo = [2i-2, 2i]   odds_lo = [2i-1, 2i+1]
               in_md split: [2i+2, 2i+3, 2i+4, 2i+5]
                    evens_md = [2i+2, 2i+4] odds_md = [2i+3, 2i+5]
               in_hi split: [2i+6, 2i+7, 2i+8, 2i+9]
                    evens_hi = [2i+6, 2i+8] odds_hi = [2i+7, 2i+9]
            */
            int32x4x2_t ulo = vuzpq_s32(in_lo, in_md);  /* even[0..3] = [2i-2,2i,2i+2,2i+4]; odd[0..3] = [2i-1,2i+1,2i+3,2i+5] */
            int32x4x2_t uhi = vuzpq_s32(in_md, in_hi);  /* even[0..3] = [2i+2,2i+4,2i+6,2i+8]; odd[0..3] = [2i+3,2i+5,2i+7,2i+9] */
            int32x4_t prev_sum = vaddq_s32(ulo.val[0], ulo.val[1]);  /* pair_sum at 2i-2, 2i, 2i+2, 2i+4 */
            int32x4_t next_sum = vaddq_s32(uhi.val[0], uhi.val[1]);  /* pair_sum at 2i+2, 2i+4, 2i+6, 2i+8 */

            /* Highpass = ((next_sum - prev_sum + 4) >> 3) + (even - odd) */
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
#endif

static void vertical_filter_quantize_row(
    PIXEL *rows[6],
    int width,
    int32_t mid_lo, int32_t mul_lo,
    int32_t mid_hi, int32_t mul_hi,
    int32_t mid_unused1, int32_t mul_unused1,
    int32_t mid_unused2, int32_t mul_unused2,
    PIXEL *out_lo, PIXEL *out_hi, PIXEL *unused1, PIXEL *unused2,
    int is_top, int is_bottom)
{
    (void)mid_unused1; (void)mul_unused1; (void)mid_unused2; (void)mul_unused2;
    (void)unused1; (void)unused2;

    int col = 0;

#if ENABLED(NEON)
    if (!is_top && !is_bottom) {
        /* NEON middle row: 4-wide vertical filter + quantize */
        const int32x4_t four = vdupq_n_s32(4);
        const int width_m4 = (width / 4) * 4;

        for (; col < width_m4; col += 4) {
            int32x4_t r0 = vld1q_s32(&rows[0][col]);
            int32x4_t r1 = vld1q_s32(&rows[1][col]);
            int32x4_t r2 = vld1q_s32(&rows[2][col]);
            int32x4_t r3 = vld1q_s32(&rows[3][col]);
            int32x4_t r4 = vld1q_s32(&rows[4][col]);
            int32x4_t r5 = vld1q_s32(&rows[5][col]);

            /* low = r2 + r3 */
            int32x4_t low = vaddq_s32(r2, r3);
            /* high = ((r4+r5-r0-r1+4)>>3) + (r2-r3) */
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
   ANS frequency counting (the fusion point)
   ================================================================ */

/* Run/magnitude classification LUTs (shared with ans_joint.c) */
static const int fused_run_class_min[] = {0, 1, 2, 3, 4, 8, 16, 32, 64, 128};
static const int fused_mag_class_min[] = {0,1,2,3,4,5,6,7,8,16,32,64,128,256,512,1024};

/* O(1) classification LUTs */
static uint8_t fused_run_lut[256];
static uint8_t fused_mag_lut[2048];
static int fused_luts_initialized = 0;

static void fused_init_luts(void) {
    if (fused_luts_initialized) return;
    for (int r = 0; r < 256; r++) {
        for (int c = 9; c >= 0; c--) {
            if (r >= fused_run_class_min[c]) { fused_run_lut[r] = (uint8_t)c; break; }
        }
    }
    for (int m = 0; m < 2048; m++) {
        for (int c = 15; c >= 0; c--) {
            if (m >= fused_mag_class_min[c]) { fused_mag_lut[m] = (uint8_t)c; break; }
        }
    }
    fused_luts_initialized = 1;
}

static inline int fused_run_to_class(int run) {
    if (run < 256) return fused_run_lut[run];
    /* Fallback for >= 256 */
    for (int c = 9; c >= 0; c--)
        if (run >= fused_run_class_min[c]) return c;
    return 0;
}

static inline int fused_mag_to_class(int mag) {
    if (mag < 2048) return fused_mag_lut[mag];
    for (int c = 15; c >= 0; c--)
        if (mag >= fused_mag_class_min[c]) return c;
    return 0;
}

/* Count frequencies for one row of quantized band data.
   Maintains run state across rows via the run_state pointer.
   NEON zero-skip: scan 4 pixels at a time, skip all-zero groups. */
static void count_freq_row(const PIXEL *data, int width,
                            uint16_t *freq, int *run_state)
{
    int run = *run_state;
    int col = 0;

#if ENABLED(NEON)
    /* 8-wide zero-skip + NEON magnitude classify (no LUT).
       Wider scan amortizes the cross-lane vmaxvq across more coefficients.
       Classifier: mag_class = (|v| <= 7) ? |v| : min(36 - clz(|v|), 15). */
    const int width_m8 = (width / 8) * 8;
    const int32x4_t v_2047 = vdupq_n_s32(2047);
    const int32x4_t v_7 = vdupq_n_s32(7);
    const int32x4_t v_15 = vdupq_n_s32(15);
    const int32x4_t v_36 = vdupq_n_s32(36);
    for (; col < width_m8; col += 8) {
        int32x4_t v1 = vld1q_s32(&data[col]);
        int32x4_t v2 = vld1q_s32(&data[col + 4]);
        int32x4_t a1 = vabsq_s32(v1);
        int32x4_t a2 = vabsq_s32(v2);
        uint32_t any_nonzero = vmaxvq_u32(
            vreinterpretq_u32_s32(vmaxq_s32(a1, a2)));
        if (any_nonzero == 0) { run += 8; continue; }

        int32x4_t c1 = vminq_s32(a1, v_2047);
        int32x4_t c2 = vminq_s32(a2, v_2047);
        int32x4_t lz1 = vreinterpretq_s32_u32(
                          vclzq_u32(vreinterpretq_u32_s32(c1)));
        int32x4_t lz2 = vreinterpretq_s32_u32(
                          vclzq_u32(vreinterpretq_u32_s32(c2)));
        int32x4_t f1 = vminq_s32(vsubq_s32(v_36, lz1), v_15);
        int32x4_t f2 = vminq_s32(vsubq_s32(v_36, lz2), v_15);
        int32x4_t mc1 = vbslq_s32(vcleq_s32(c1, v_7), c1, f1);
        int32x4_t mc2 = vbslq_s32(vcleq_s32(c2, v_7), c2, f2);

        int32_t vals[8], mcs[8];
        vst1q_s32(vals,     v1); vst1q_s32(vals + 4, v2);
        vst1q_s32(mcs,      mc1); vst1q_s32(mcs + 4, mc2);

        for (int k = 0; k < 8; k++) {
            int32_t val = vals[k];
            if (val == 0) { run++; continue; }
            while (run >= 256) {
                int rc = fused_run_to_class(255);
                freq[rc * 16 + 0]++;
                run -= 255;
            }
            int rc = fused_run_to_class(run);
            freq[rc * 16 + mcs[k]]++;
            run = 0;
        }
    }
#endif

    /* Scalar cleanup */
    for (; col < width; col++) {
        int32_t val = data[col];
        if (val == 0) { run++; continue; }

        int32_t mag = (val < 0) ? -val : val;
        while (run >= 256) {
            int rc = fused_run_to_class(255);
            freq[rc * 16 + 0]++;
            run -= 255;
        }
        int rc = fused_run_to_class(run);
        int mc = fused_mag_to_class(mag > 2047 ? 2047 : mag);
        freq[rc * 16 + mc]++;
        run = 0;
    }
    *run_state = run;
}

/* Flush trailing zeros at end of band */
static void count_freq_flush(uint16_t *freq, int *run_state)
{
    int run = *run_state;
    while (run > 0) {
        int actual = (run > 255) ? 255 : run;
        int rc = fused_run_to_class(actual);
        freq[rc * 16 + 0]++;
        run -= actual;
    }
    *run_state = 0;
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
    /* Per-channel wavelet state */
    PIXEL *lowpass_buf[FUSED_ROW_BUFS];   /* Horizontal lowpass 6-row circular buffer */
    PIXEL *highpass_buf[FUSED_ROW_BUFS];  /* Horizontal highpass 6-row circular buffer */
    int buf_row;                           /* Current position in circular buffer */

    /* Per-level, per-band output */
    PIXEL *band_data[FUSED_MAX_BANDS];    /* Quantized band output buffers */
    int band_width, band_height;
    int band_pitch;                        /* In pixels */
    int band_out_row;                      /* Current output row */

    /* Quantization parameters per band */
    int32_t midpoint[FUSED_MAX_BANDS];
    int32_t multiplier[FUSED_MAX_BANDS];

    /* ANS frequency tables per band */
    uint16_t freq[FUSED_MAX_BANDS][160];  /* 10 run classes × 16 mag classes = 160 */
    int run_state[FUSED_MAX_BANDS];        /* Run counter per band */
} FUSED_CHANNEL_STATE;

/* ================================================================
   Per-channel Pass 1 (one of 4 parallel threads)
   ================================================================ */

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
#endif

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
                          ch_width, prescale);
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

            PIXEL *ll_row = cs->band_data[0] + out_row * cs->band_pitch;
            PIXEL *lh_row = cs->band_data[1] + out_row * cs->band_pitch;
            vertical_filter_quantize_row(lp_rows, bw,
                cs->midpoint[0], cs->multiplier[0],
                cs->midpoint[1], cs->multiplier[1],
                0, 0, 0, 0,
                ll_row, lh_row, NULL, NULL,
                is_top, is_bottom);

            PIXEL *hl_row = cs->band_data[2] + out_row * cs->band_pitch;
            PIXEL *hh_row = cs->band_data[3] + out_row * cs->band_pitch;
            vertical_filter_quantize_row(hp_rows, bw,
                cs->midpoint[2], cs->multiplier[2],
                cs->midpoint[3], cs->multiplier[3],
                0, 0, 0, 0,
                hl_row, hh_row, NULL, NULL,
                is_top, is_bottom);

#ifdef FUSED_TIMING_DETAIL
            t_vert += _fused_ms() - _td; _td = _fused_ms();
#endif

            count_freq_row(lh_row, bw, cs->freq[1], &cs->run_state[1]);
            count_freq_row(hl_row, bw, cs->freq[2], &cs->run_state[2]);
            count_freq_row(hh_row, bw, cs->freq[3], &cs->run_state[3]);

#ifdef FUSED_TIMING_DETAIL
            t_freq += _fused_ms() - _td;
#endif

            cs->band_out_row++;
        }
    }

    /* Flush trailing zero runs for this channel's 3 highpass bands */
    for (int band = 1; band < 4; band++) {
        count_freq_flush(cs->freq[band], &cs->run_state[band]);
    }

#ifdef FUSED_TIMING_DETAIL
    fprintf(stderr, "    ch%d: unpack=%.1f, horiz=%.1f, vert+quant=%.1f, freq=%.1f\n",
            channel, t_unpack, t_horiz, t_vert, t_freq);
#endif

    free(unpack_row);
}

typedef struct {
    int channel;
    const uint8_t *raw_bayer;
    int width, height;
    int log_bits, is_rggb, prescale;
    FUSED_CHANNEL_STATE *cs;
} PASS1_CHANNEL_TASK;

static void *pass1_channel_thread(void *arg) {
    PASS1_CHANNEL_TASK *t = (PASS1_CHANNEL_TASK *)arg;
    pass1_run_channel(t->channel, t->raw_bayer, t->width, t->height,
                      t->log_bits, t->is_rggb, t->prescale, t->cs);
    return NULL;
}

static int fused_pass1(
    const uint8_t *raw_bayer, int width, int height,
    int pixel_format, int quality,
    FUSED_CHANNEL_STATE ch_state[4],
    PIXEL **ll_output[4]  /* LL band pointers for recursive levels */
)
{
    (void)ll_output;
    SetupEncoderLogCurve();
    fused_init_luts();

    int ch_width = width / 2;
    int ch_height = height / 2;
    int is_rggb = (pixel_format == 1 || pixel_format == 0 || pixel_format == 4);
    int log_bits = (pixel_format >= 4) ? 16 : 14;

    const QUANT *qt = quality_tables[(quality >= 0 && quality < 9) ? quality : 3];

    /* Set up quantization for level 0 */
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 0; band < 4; band++) {
            int qi = band; /* LL=0, LH=1, HL=2, HH=3 */
            int divisor = qt[qi];
            ch_state[ch].midpoint[band] = get_midpoint(divisor);
            ch_state[ch].multiplier[band] = get_multiplier(divisor);
        }

        ch_state[ch].band_width = ch_width / 2;
        ch_state[ch].band_height = ch_height / 2;
        ch_state[ch].band_pitch = ch_state[ch].band_width;
        ch_state[ch].band_out_row = 0;
        ch_state[ch].buf_row = 0;

        memset(ch_state[ch].freq, 0, sizeof(ch_state[ch].freq));
        memset(ch_state[ch].run_state, 0, sizeof(ch_state[ch].run_state));

        /* Allocate band buffers */
        int bw = ch_state[ch].band_width;
        int bh = ch_state[ch].band_height;
        for (int band = 0; band < 4; band++) {
            ch_state[ch].band_data[band] = (PIXEL *)calloc(bw * bh, sizeof(PIXEL));
            if (!ch_state[ch].band_data[band]) return -1;
        }

        /* Allocate 6-row circular buffers */
        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            ch_state[ch].lowpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            ch_state[ch].highpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            if (!ch_state[ch].lowpass_buf[r] || !ch_state[ch].highpass_buf[r]) return -1;
        }
    }

    /* Prescale for level 0 (typically 2 for 14-bit) */
    int prescale = 2;

    /* === SPAWN 4 PARALLEL CHANNEL THREADS === */
    PASS1_CHANNEL_TASK tasks[4];
    pthread_t threads[4];
    int created[4];
    for (int ch = 0; ch < 4; ch++) {
        tasks[ch].channel = ch;
        tasks[ch].raw_bayer = raw_bayer;
        tasks[ch].width = width;
        tasks[ch].height = height;
        tasks[ch].log_bits = log_bits;
        tasks[ch].is_rggb = is_rggb;
        tasks[ch].prescale = prescale;
        tasks[ch].cs = &ch_state[ch];
        created[ch] = (pthread_create(&threads[ch], NULL,
                                       pass1_channel_thread, &tasks[ch]) == 0);
        if (!created[ch]) pass1_channel_thread(&tasks[ch]);
    }
    for (int ch = 0; ch < 4; ch++) {
        if (created[ch]) pthread_join(threads[ch], NULL);
    }

    return 0;
}

/* === OLD SERIAL PASS 1 (kept for reference / debugging) === */
#if 0
static int fused_pass1_serial(
    const uint8_t *raw_bayer, int width, int height,
    int pixel_format, int quality,
    FUSED_CHANNEL_STATE ch_state[4],
    PIXEL **ll_output[4])
{
    SetupEncoderLogCurve();
    fused_init_luts();

    int ch_width = width / 2;
    int ch_height = height / 2;
    int is_rggb = (pixel_format == 1 || pixel_format == 0 || pixel_format == 4);
    int log_bits = (pixel_format >= 4) ? 16 : 14;

    const QUANT *qt = quality_tables[(quality >= 0 && quality < 9) ? quality : 3];

    /* Set up quantization for level 0 */
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 0; band < 4; band++) {
            int qi = band; /* LL=0, LH=1, HL=2, HH=3 */
            int divisor = qt[qi];
            ch_state[ch].midpoint[band] = get_midpoint(divisor);
            ch_state[ch].multiplier[band] = get_multiplier(divisor);
        }

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
            ch_state[ch].band_data[band] = (PIXEL *)calloc(bw * bh, sizeof(PIXEL));
            if (!ch_state[ch].band_data[band]) return -1;
        }

        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            ch_state[ch].lowpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            ch_state[ch].highpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            if (!ch_state[ch].lowpass_buf[r] || !ch_state[ch].highpass_buf[r]) return -1;
        }
    }

    PIXEL *unpack_row[4];
    for (int ch = 0; ch < 4; ch++) {
        unpack_row[ch] = (PIXEL *)malloc(ch_width * sizeof(PIXEL));
        if (!unpack_row[ch]) return -1;
    }

    int prescale = 2;

    /* === MAIN ROW LOOP === */
    const uint16_t *bayer = (const uint16_t *)raw_bayer;
    int bayer_pitch = width; /* In uint16_t elements */

#ifdef FUSED_TIMING_DETAIL
    double t_unpack = 0, t_horiz = 0, t_vert = 0, t_freq = 0;
    double _td;
#endif

    for (int row = 0; row < ch_height; row++) {
        const uint16_t *row1 = bayer + (row * 2) * bayer_pitch;
        const uint16_t *row2 = row1 + bayer_pitch;

#ifdef FUSED_TIMING_DETAIL
        _td = _fused_ms();
#endif

        /* --- UNPACK: Bayer → GS, RG, BG, GD with log curve --- */
        {
            const int32_t mid2 = 2 * (1 << (log_bits - 1));
            uint16_t *log_tbl = (log_bits <= 14) ? EncoderLogCurve14 : EncoderLogCurve16;
            int log_max = (log_bits <= 14) ? 16383 : 65535;

            int col = 0;
#if ENABLED(NEON)
            /* NEON: batch 4 pixels — scalar LUT lookups, then NEON color convert */
            const int ch_width_m4 = (ch_width / 4) * 4;
            const int32x4_t vmid2 = vdupq_n_s32(mid2);

            for (; col < ch_width_m4; col += 4) {
                /* Scalar: 4× Bayer load + log curve */
                int32_t ra[4], g1a[4], g2a[4], ba[4];
                for (int k = 0; k < 4; k++) {
                    int c = col + k;
                    uint16_t R1, G1, G2, B1;
                    if (is_rggb) {
                        R1 = row1[2*c]; G1 = row1[2*c+1]; G2 = row2[2*c]; B1 = row2[2*c+1];
                    } else {
                        G1 = row1[2*c]; B1 = row1[2*c+1]; R1 = row2[2*c]; G2 = row2[2*c+1];
                    }
                    if (R1 > log_max) R1 = log_max;
                    if (G1 > log_max) G1 = log_max;
                    if (G2 > log_max) G2 = log_max;
                    if (B1 > log_max) B1 = log_max;
                    ra[k] = log_tbl[R1]; g1a[k] = log_tbl[G1];
                    g2a[k] = log_tbl[G2]; ba[k] = log_tbl[B1];
                }

                /* NEON: color conversion for 4 pixels */
                int32x4_t vr  = vld1q_s32(ra);
                int32x4_t vg1 = vld1q_s32(g1a);
                int32x4_t vg2 = vld1q_s32(g2a);
                int32x4_t vb  = vld1q_s32(ba);

                int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
                int32x4_t vgd = vshrq_n_s32(vaddq_s32(vsubq_s32(vg1, vg2), vmid2), 1);
                int32x4_t vrg = vshrq_n_s32(vaddq_s32(vsubq_s32(vr, vgs), vmid2), 1);
                int32x4_t vbg = vshrq_n_s32(vaddq_s32(vsubq_s32(vb, vgs), vmid2), 1);

                vst1q_s32(&unpack_row[0][col], vgs);
                vst1q_s32(&unpack_row[1][col], vrg);
                vst1q_s32(&unpack_row[2][col], vbg);
                vst1q_s32(&unpack_row[3][col], vgd);
            }
#endif
            /* Scalar cleanup */
            for (; col < ch_width; col++) {
                uint16_t R1, G1, G2, B1;
                if (is_rggb) {
                    R1 = row1[2*col]; G1 = row1[2*col+1]; G2 = row2[2*col]; B1 = row2[2*col+1];
                } else {
                    G1 = row1[2*col]; B1 = row1[2*col+1]; R1 = row2[2*col]; G2 = row2[2*col+1];
                }
                int32_t r = apply_log_curve(R1, log_bits);
                int32_t g1 = apply_log_curve(G1, log_bits);
                int32_t g2 = apply_log_curve(G2, log_bits);
                int32_t b = apply_log_curve(B1, log_bits);
                int32_t gs = (g1 + g2) >> 1;
                int32_t gd = ((g1 - g2) + mid2) >> 1;
                int32_t rg = ((r - gs) + mid2) >> 1;
                int32_t bg_v = ((b - gs) + mid2) >> 1;
                unpack_row[0][col] = gs; unpack_row[1][col] = rg;
                unpack_row[2][col] = bg_v; unpack_row[3][col] = gd;
            }
        }

#ifdef FUSED_TIMING_DETAIL
        t_unpack += _fused_ms() - _td; _td = _fused_ms();
#endif

        /* --- HORIZONTAL FILTER for each channel --- */
        for (int ch = 0; ch < 4; ch++) {
            int buf_idx = ch_state[ch].buf_row % FUSED_ROW_BUFS;
            horizontal_filter(unpack_row[ch],
                              ch_state[ch].lowpass_buf[buf_idx],
                              ch_state[ch].highpass_buf[buf_idx],
                              ch_width, prescale);
            ch_state[ch].buf_row++;
        }

#ifdef FUSED_TIMING_DETAIL
        t_horiz += _fused_ms() - _td; _td = _fused_ms();
#endif

        /* --- VERTICAL FILTER + QUANTIZE + FREQ COUNT --- */
        /* Vertical filter needs 6 rows, fires every 2 input rows */
        if (ch_state[0].buf_row >= 6 && (ch_state[0].buf_row % 2) == 0) {
            for (int ch = 0; ch < 4; ch++) {
                FUSED_CHANNEL_STATE *cs = &ch_state[ch];
                int out_row = cs->band_out_row;
                if (out_row >= cs->band_height) continue;

                /* Build ordered row pointer array from circular buffer */
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

                /* Vertical filter on lowpass rows → LL + LH bands */
                PIXEL *ll_row = cs->band_data[0] + out_row * cs->band_pitch;
                PIXEL *lh_row = cs->band_data[1] + out_row * cs->band_pitch;

                vertical_filter_quantize_row(lp_rows, bw,
                    cs->midpoint[0], cs->multiplier[0],
                    cs->midpoint[1], cs->multiplier[1],
                    0, 0, 0, 0,  /* HL/HH not used here */
                    ll_row, lh_row, NULL, NULL,
                    is_top, is_bottom);

                /* Vertical filter on highpass rows → HL + HH bands */
                PIXEL *hl_row = cs->band_data[2] + out_row * cs->band_pitch;
                PIXEL *hh_row = cs->band_data[3] + out_row * cs->band_pitch;

                vertical_filter_quantize_row(hp_rows, bw,
                    cs->midpoint[2], cs->multiplier[2],
                    cs->midpoint[3], cs->multiplier[3],
                    0, 0, 0, 0,
                    hl_row, hh_row, NULL, NULL,
                    is_top, is_bottom);

#ifdef FUSED_TIMING_DETAIL
                t_vert += _fused_ms() - _td; _td = _fused_ms();
#endif

                /* --- INLINE FREQUENCY COUNT (the fusion!) --- */
                count_freq_row(lh_row, bw, cs->freq[1], &cs->run_state[1]);
                count_freq_row(hl_row, bw, cs->freq[2], &cs->run_state[2]);
                count_freq_row(hh_row, bw, cs->freq[3], &cs->run_state[3]);

#ifdef FUSED_TIMING_DETAIL
                t_freq += _fused_ms() - _td;
#endif

                cs->band_out_row++;
            }
        }
    }

#ifdef FUSED_TIMING_DETAIL
    fprintf(stderr, "    Pass1 detail: unpack=%.1f, horiz=%.1f, vert+quant=%.1f, freq=%.1f\n",
            t_unpack, t_horiz, t_vert, t_freq);
#endif

    /* Flush trailing zero runs */
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 1; band < 4; band++) {
            count_freq_flush(ch_state[ch].freq[band], &ch_state[ch].run_state[band]);
        }
    }

    /* Free temporary unpack buffers */
    for (int ch = 0; ch < 4; ch++) free(unpack_row[ch]);

    return 0;
}
#endif /* old serial fused_pass1 */

/* ================================================================
   Pass 2: rANS Encode using pre-counted frequencies
   ================================================================ */


typedef struct {
    PIXEL *band_data;
    int width, height, pitch;
    uint8_t *enc_buf;
    size_t enc_cap;
    int enc_size;
} PASS2_BAND_TASK;

static void *pass2_band_thread(void *arg) {
    PASS2_BAND_TASK *t = (PASS2_BAND_TASK *)arg;
    t->enc_size = jans_encode_band_x4(t->enc_buf, t->enc_cap,
                                       (const int32_t *)t->band_data,
                                       t->width, t->height, t->pitch);
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
    PASS2_BAND_TASK tasks[12];
    pthread_t threads[12];
    int task_count = 0;
    int created[12];

    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ch_state[ch];
        for (int band = 1; band < 4; band++) {
            PASS2_BAND_TASK *t = &tasks[task_count];
            t->band_data = cs->band_data[band];
            t->width = cs->band_width;
            t->height = cs->band_height;
            t->pitch = cs->band_width * sizeof(int32_t);
            t->enc_cap = (size_t)t->width * t->height * 4 + 8192;
            t->enc_buf = (uint8_t *)malloc(t->enc_cap);
            t->enc_size = 0;
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

        for (int band = 1; band < 4; band++) {
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
   Main entry point
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
    FUSED_CHANNEL_STATE ch_state[4];
    memset(ch_state, 0, sizeof(ch_state));

#ifdef FUSED_TIMING
    double t0 = _fused_ms();
#endif

    /* === PASS 1: Fused unpack → wavelet → quantize → freq count === */
    int rc = fused_pass1(raw_bayer, width, height, pixel_format, quality,
                          ch_state, NULL);
    if (rc != 0) goto cleanup;

#ifdef FUSED_TIMING
    double t1 = _fused_ms();
    fprintf(stderr, "  FUSED Pass1 (unpack+wavelet+quant+freq): %.1fms\n", t1 - t0);
#endif

    /* === PASS 2: rANS encode === */
    size_t stream_cap = raw_size;
    uint8_t *stream_buf = (uint8_t *)malloc(stream_cap);
    if (!stream_buf) { rc = -1; goto cleanup; }

    size_t written = 0;
    rc = fused_pass2(ch_state, stream_buf, stream_cap, &written);
    if (rc != 0) { free(stream_buf); goto cleanup; }

#ifdef FUSED_TIMING
    double t2 = _fused_ms();
    fprintf(stderr, "  FUSED Pass2 (rANS encode):              %.1fms\n", t2 - t1);
    fprintf(stderr, "  FUSED Total:                             %.1fms\n", t2 - t0);
#endif

    *vc5_out = stream_buf;
    *vc5_size = written;

cleanup:
    /* Free band buffers and circular buffers */
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 0; band < 4; band++) {
            if (ch_state[ch].band_data[band]) free(ch_state[ch].band_data[band]);
        }
        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            if (ch_state[ch].lowpass_buf[r]) free(ch_state[ch].lowpass_buf[r]);
            if (ch_state[ch].highpass_buf[r]) free(ch_state[ch].highpass_buf[r]);
        }
    }

    return rc;
}
