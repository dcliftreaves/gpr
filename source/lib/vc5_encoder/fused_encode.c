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

/* POSIX feature test must precede any system header so clock_gettime
   and CLOCK_MONOTONIC are exposed on Linux (Pi). */
#if !defined(__APPLE__)
#  ifndef _POSIX_C_SOURCE
#  define _POSIX_C_SOURCE 199309L
#  endif
#endif

#include "headers.h"
#include "fused_encode.h"
#include "ans_joint.h"
#include "denoise.h"
#include <pthread.h>
#include <unistd.h>  /* for sysconf */

/* Per-frame timing prints. Comment out for clean micro-benchmarks. */
/* #define FUSED_TIMING */
/* #define FUSED_TIMING_DETAIL */

#if defined(FUSED_TIMING) || defined(FUSED_TIMING_DETAIL)
#if defined(__APPLE__)
#include <mach/mach_time.h>
static double _fused_ms(void) {
    static double s = 0;
    if (!s) { mach_timebase_info_data_t i; mach_timebase_info(&i); s = (double)i.numer/i.denom/1e6; }
    return mach_absolute_time() * s;
}
#else
#include <time.h>
static double _fused_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1.0e6;
}
#endif
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

    /* Odd-width tail: produce one extra output for the unpaired last
       column by treating it as a pair with itself (replicated). Without
       this, every wavelet level whose input width is odd silently drops
       the right-most column — visible as a chunk of dead pixels in the
       reconstructed image. */
    if (width & 1) {
        int idx = width - 1;
        PIXEL last = PS(input[idx]);
        lowpass[half]  = last + last;
        highpass[half] = 0;
    }

    #undef PS
}

/* ================================================================
   Vertical filter + quantize (simplified from forward.c)
   ================================================================ */

#if ENABLED(NEON)
/* Quantize 4 int32 lanes: out = sign(v) * ((|v| + midpoint) * multiplier) >> 16.
   A76 tuning: fuses (>>16) + narrow into one `vshrn_n_s64` (shrn) per half
   instead of `vshrq_n_s64 + vmovn_s64`. Saves a dispatch slot; shrn issues
   on V1 freeing V0 for the next iteration's smull. Byte-exact result. */
static inline int32x4_t quantize_neon4(int32x4_t values, int32_t midpoint, int32_t multiplier) {
    int32x4_t abs_v = vabsq_s32(values);
    abs_v = vaddq_s32(abs_v, vdupq_n_s32(midpoint));
    int32x2_t mul_v = vdup_n_s32(multiplier);
    int64x2_t plo = vmull_s32(vget_low_s32(abs_v), mul_v);
    int64x2_t phi = vmull_s32(vget_high_s32(abs_v), mul_v);
    int32x4_t scaled = vcombine_s32(vshrn_n_s64(plo, 16), vshrn_n_s64(phi, 16));
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
        /* NEON middle row: 4-wide vertical filter + quantize.
           A76 tuning: hoist row pointers into __restrict locals + use
           post-incremented loads so the compiler emits `ldr q,[x],#16`
           (single dispatch slot) instead of indexed `ldr q,[x,x]`
           (5-cycle latency). Without restrict-locals + post-inc, clang
           reloads the rows[] pointer array inside the loop on every
           iteration (verified in clang -S output on aarch64). */
        const int32x4_t four = vdupq_n_s32(4);
        const int width_m4 = (width / 4) * 4;
        const PIXEL *__restrict__ p0 = rows[0];
        const PIXEL *__restrict__ p1 = rows[1];
        const PIXEL *__restrict__ p2 = rows[2];
        const PIXEL *__restrict__ p3 = rows[3];
        const PIXEL *__restrict__ p4 = rows[4];
        const PIXEL *__restrict__ p5 = rows[5];
        PIXEL *__restrict__ qlo = out_lo;
        PIXEL *__restrict__ qhi = out_hi;

        for (int c = 0; c < width_m4; c += 4) {
            int32x4_t r0 = vld1q_s32(p0); p0 += 4;
            int32x4_t r1 = vld1q_s32(p1); p1 += 4;
            int32x4_t r2 = vld1q_s32(p2); p2 += 4;
            int32x4_t r3 = vld1q_s32(p3); p3 += 4;
            int32x4_t r4 = vld1q_s32(p4); p4 += 4;
            int32x4_t r5 = vld1q_s32(p5); p5 += 4;

            /* low = r2 + r3 */
            int32x4_t low = vaddq_s32(r2, r3);
            /* high = ((r4+r5-r0-r1+4)>>3) + (r2-r3) */
            int32x4_t high = vsubq_s32(vaddq_s32(r4, r5), vaddq_s32(r0, r1));
            high = vshrq_n_s32(vaddq_s32(high, four), 3);
            high = vaddq_s32(high, vsubq_s32(r2, r3));

            vst1q_s32(qlo, quantize_neon4(low, mid_lo, mul_lo)); qlo += 4;
            vst1q_s32(qhi, quantize_neon4(high, mid_hi, mul_hi)); qhi += 4;
        }
        col = width_m4;
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
   Multi-level helper: apply a full wavelet decomposition to a PIXEL
   buffer. Used for levels 2 and 3 after Pass 1 fills the level-1
   LL band. Sequential (not fused with the unpack/log stage that
   only exists for the raw Bayer input).
   ================================================================ */

/* Decompose `input` (in_width × in_height PIXEL) into 4 quantized subbands
   of (in_width/2 × in_height/2). prescale=2 — without this the LL magnitude
   grows 4× per level and quickly overflows the rANS encoder's mag-class
   ceiling (2047). Matches the production encoder's {0,2,2} prescale table:
   level 1 (this encoder's level 1) uses prescale=2 already, and so do
   levels 2 and 3 here, keeping LL bounded at every level.
   LL is NOT quantized here even if mid[0]/mul[0] are passed —
   divisor=1 in the quant table produces a no-op. */
static void wavelet_decompose_buffer(
    const PIXEL *input, int in_width, int in_height,
    const int32_t mid[4], const int32_t mul[4],
    PIXEL *out_ll, PIXEL *out_lh, PIXEL *out_hl, PIXEL *out_hh)
{
    int out_width = in_width / 2;
    int out_height = in_height / 2;

    PIXEL *lp_rows[FUSED_ROW_BUFS];
    PIXEL *hp_rows[FUSED_ROW_BUFS];
    for (int r = 0; r < FUSED_ROW_BUFS; r++) {
        lp_rows[r] = (PIXEL *)malloc(out_width * sizeof(PIXEL));
        hp_rows[r] = (PIXEL *)malloc(out_width * sizeof(PIXEL));
        if (!lp_rows[r] || !hp_rows[r]) {
            for (int q = 0; q <= r; q++) {
                if (lp_rows[q]) free(lp_rows[q]);
                if (hp_rows[q]) free(hp_rows[q]);
            }
            return;
        }
    }

    int out_row = 0;
    int buf_filled = 0;

    for (int row = 0; row < in_height; row++) {
        int slot = row % FUSED_ROW_BUFS;
        horizontal_filter(input + row * in_width,
                          lp_rows[slot], hp_rows[slot],
                          in_width, /*prescale=*/2);
        buf_filled++;

        /* Emit one output row every 2 input rows once we have 6 rows queued. */
        if (buf_filled >= 6 && (buf_filled % 2) == 0) {
            if (out_row >= out_height) break;
            int base = (row + 1 - 6) % FUSED_ROW_BUFS;
            PIXEL *lprefs[6], *hprefs[6];
            for (int r = 0; r < 6; r++) {
                int idx = (base + r) % FUSED_ROW_BUFS;
                if (idx < 0) idx += FUSED_ROW_BUFS;
                lprefs[r] = lp_rows[idx];
                hprefs[r] = hp_rows[idx];
            }
            int is_top = (out_row == 0);
            int is_bottom = (out_row == out_height - 1);

            vertical_filter_quantize_row(lprefs, out_width,
                mid[0], mul[0],  mid[1], mul[1],
                0,0, 0,0,
                out_ll + out_row * out_width,
                out_lh + out_row * out_width,
                NULL, NULL,
                is_top, is_bottom);

            vertical_filter_quantize_row(hprefs, out_width,
                mid[2], mul[2],  mid[3], mul[3],
                0,0, 0,0,
                out_hl + out_row * out_width,
                out_hh + out_row * out_width,
                NULL, NULL,
                is_top, is_bottom);

            out_row++;
        }
    }

    /* Bottom-edge handling: the 6-tap vertical filter under-runs by 2 rows.
       Production code clamps the last two output rows with is_bottom=true.
       For multi-level we accept the under-run (rows stay zero); the lost
       rows are 2 of out_height = ~0.1% of coefficients for 1380-row band. */

    for (int r = 0; r < FUSED_ROW_BUFS; r++) {
        free(lp_rows[r]);
        free(hp_rows[r]);
    }
}

/* ================================================================
   Pass 1: Fused Unpack → Wavelet → Quantize → FreqCount
   ================================================================ */

typedef struct {
    /* Per-channel wavelet state (level 1 only — see below for higher levels) */
    PIXEL *lowpass_buf[FUSED_ROW_BUFS];   /* Horizontal lowpass 6-row circular buffer */
    PIXEL *highpass_buf[FUSED_ROW_BUFS];  /* Horizontal highpass 6-row circular buffer */
    int buf_row;                           /* Current position in circular buffer */

    /* Level-1 (largest) per-band output. band_data[0] = LL1 — fed into the
       level-2 wavelet pass post-Pass-1 in multi-level mode, discarded
       otherwise. band_data[1..3] = LH1/HL1/HH1 (encoded). */
    PIXEL *band_data[FUSED_MAX_BANDS];    /* Quantized band buffers (NULL in inline mode) */
    PIXEL *row_scratch[FUSED_MAX_BANDS];  /* Per-row scratch (~5KB × 4) used in inline mode */
    int band_width, band_height;
    int band_pitch;                        /* In pixels */
    int band_out_row;                      /* Current output row */

    /* Quantization parameters per band (level 1) */
    int32_t midpoint[FUSED_MAX_BANDS];
    int32_t multiplier[FUSED_MAX_BANDS];

    /* ANS frequency tables per band (legacy/unused since the freq-removal commit) */
    uint16_t freq[FUSED_MAX_BANDS][160];
    int run_state[FUSED_MAX_BANDS];

    /* Inline-tokenize state per highpass band (NULL in split-pass mode).
       Owned by FUSED_ENCODER; reset each frame. */
    JANS_INLINE_STATE *inline_state[FUSED_MAX_BANDS];

    /* ---- Multi-level (3-level wavelet) extension. NULL when multi_level off.
       Sequential mode: band_data_l2[0] holds the entire LL2 band (input to
       level-3). Streaming mode: band_data_l2[0] is NULL — LL2 rows feed
       directly into the level-3 horizontal filter via lp_buf_l3.
       LH/HL/HH at each level are always allocated (they are Pass 2 inputs).
       LL3 is always allocated and encoded. */
    PIXEL *band_data_l2[FUSED_MAX_BANDS];
    PIXEL *band_data_l3[FUSED_MAX_BANDS];
    int band_width_l2, band_height_l2;
    int band_width_l3, band_height_l3;
    int32_t midpoint_l2[FUSED_MAX_BANDS], multiplier_l2[FUSED_MAX_BANDS];
    int32_t midpoint_l3[FUSED_MAX_BANDS], multiplier_l3[FUSED_MAX_BANDS];

    /* Streaming pyramid: per-level 6-row horizontal filter buffer fed by
       the previous level's vertical-filter output. NULL when not in
       streaming mode. */
    PIXEL *lp_buf_l2[FUSED_ROW_BUFS], *hp_buf_l2[FUSED_ROW_BUFS];
    int buf_row_l2;
    int band_out_row_l2;
    PIXEL *ll2_row_scratch;  /* 1-row buffer for the unused LL2 result */

    PIXEL *lp_buf_l3[FUSED_ROW_BUFS], *hp_buf_l3[FUSED_ROW_BUFS];
    int buf_row_l3;
    int band_out_row_l3;

    int streaming_active;  /* 1 = run cascade in pass1; 0 = sequential post-pass */
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
    const int ch_width_m8 = (ch_width / 8) * 8;
    const int ch_width_m4 = (ch_width / 4) * 4;
    const int32x4_t vmid2 = vdupq_n_s32(mid2);
    const uint16x8_t v_log_max = vdupq_n_u16((uint16_t)log_max);

    /* 8-wide path: load + branchless clip via NEON; LUT gather stays scalar
       (ARM has no arbitrary u16 gather). Outputs are emitted in two 4-wide
       NEON chunks so the downstream arithmetic stays identical to the
       4-wide path. */
    for (; col < ch_width_m8; col += 8) {
        /* vld2q_u16 deinterleaves the strided Bayer reads:
             RGGB: row1 = R G1 R G1 ... → (R[0..7], G1[0..7])
                   row2 = G2 B G2 B ... → (G2[0..7], B[0..7])
             GBRG: row1 = G1 B G1 B ... → (G1[0..7], B[0..7])
                   row2 = R G2 R G2 ... → (R[0..7], G2[0..7])
           One vld2q replaces 8 strided u16 loads + an 8-way clip. */
        uint16x8x2_t r1d = vld2q_u16(&row1[2*col]);
        uint16x8x2_t r2d = vld2q_u16(&row2[2*col]);

        uint16x8_t vR, vG1, vG2, vB;
        if (is_rggb) {
            vR  = vminq_u16(r1d.val[0], v_log_max);
            vG1 = vminq_u16(r1d.val[1], v_log_max);
            vG2 = vminq_u16(r2d.val[0], v_log_max);
            vB  = vminq_u16(r2d.val[1], v_log_max);
        } else {
            vG1 = vminq_u16(r1d.val[0], v_log_max);
            vB  = vminq_u16(r1d.val[1], v_log_max);
            vR  = vminq_u16(r2d.val[0], v_log_max);
            vG2 = vminq_u16(r2d.val[1], v_log_max);
        }

        uint16_t Rs[8], G1s[8], G2s[8], Bs[8];
        if (channel == 1) vst1q_u16(Rs, vR);
        if (channel == 2) vst1q_u16(Bs, vB);
        vst1q_u16(G1s, vG1);
        vst1q_u16(G2s, vG2);

        /* Emit two 4-wide NEON output chunks per 8-pixel iter. */
        for (int half = 0; half < 2; half++) {
            int32_t g1a[4], g2a[4];
            for (int k = 0; k < 4; k++) {
                g1a[k] = log_tbl[G1s[half*4 + k]];
                g2a[k] = log_tbl[G2s[half*4 + k]];
            }
            int32x4_t vg1 = vld1q_s32(g1a);
            int32x4_t vg2 = vld1q_s32(g2a);

            int32x4_t result;
            if (channel == 0) {
                result = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            } else if (channel == 3) {
                result = vshrq_n_s32(vaddq_s32(vsubq_s32(vg1, vg2), vmid2), 1);
            } else {
                int32_t xa[4];
                if (channel == 1) {
                    for (int k = 0; k < 4; k++) xa[k] = log_tbl[Rs[half*4 + k]];
                } else {
                    for (int k = 0; k < 4; k++) xa[k] = log_tbl[Bs[half*4 + k]];
                }
                int32x4_t vx = vld1q_s32(xa);
                int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
                result = vshrq_n_s32(vaddq_s32(vsubq_s32(vx, vgs), vmid2), 1);
            }
            vst1q_s32(&output[col + half*4], result);
        }
    }

    /* 4-wide tail when ch_width isn't a multiple of 8 (rare — almost
       always 0 cols for the common Z8/X2D widths). */
    for (; col < ch_width_m4; col += 4) {
        int32_t ra[4], ba[4], g1a[4], g2a[4];
        for (int k = 0; k < 4; k++) {
            int c = col + k;
            uint16_t R, G1, G2, B;
            if (is_rggb) {
                R  = row1[2*c]; G1 = row1[2*c+1]; G2 = row2[2*c]; B  = row2[2*c+1];
            } else {
                G1 = row1[2*c]; B  = row1[2*c+1]; R  = row2[2*c]; G2 = row2[2*c+1];
            }
            if (R  > log_max) R  = log_max;
            if (G1 > log_max) G1 = log_max;
            if (G2 > log_max) G2 = log_max;
            if (B  > log_max) B  = log_max;
            ra[k] = log_tbl[R]; g1a[k] = log_tbl[G1];
            g2a[k] = log_tbl[G2]; ba[k] = log_tbl[B];
        }
        int32x4_t vg1 = vld1q_s32(g1a), vg2 = vld1q_s32(g2a);
        int32x4_t result;
        if (channel == 0) {
            result = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
        } else if (channel == 3) {
            result = vshrq_n_s32(vaddq_s32(vsubq_s32(vg1, vg2), vmid2), 1);
        } else {
            int32x4_t vx = vld1q_s32(channel == 1 ? ra : ba);
            int32x4_t vgs = vshrq_n_s32(vaddq_s32(vg1, vg2), 1);
            result = vshrq_n_s32(vaddq_s32(vsubq_s32(vx, vgs), vmid2), 1);
        }
        vst1q_s32(&output[col], result);
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

/* Streaming cascade: feed one newly-produced LL1 row into level-2's
   horizontal filter, then (if enough rows are queued) run level-2's
   vertical filter, then cascade the LL2 row into level-3's horizontal
   filter, then (if enough rows) run level-3's vertical filter.

   This eliminates the LL1 and LL2 full-image buffers (saves ~57 MB at
   50 MP), keeping only the small 6-row horizontal buffers per level. */
static void stream_cascade_higher_levels(FUSED_CHANNEL_STATE *cs,
                                         const PIXEL *ll1_row)
{
    int bw_l2 = cs->band_width_l2;
    int bw_l3 = cs->band_width_l3;

    /* ---- Level 2 horizontal filter ---- */
    int slot2 = cs->buf_row_l2 % FUSED_ROW_BUFS;
    horizontal_filter(ll1_row,
                      cs->lp_buf_l2[slot2], cs->hp_buf_l2[slot2],
                      cs->band_width, /*prescale=*/2);
    cs->buf_row_l2++;

    /* ---- Level 2 vertical filter (emit one output row every 2 inputs after row 6) ---- */
    if (cs->buf_row_l2 >= 6 && (cs->buf_row_l2 % 2) == 0) {
        int out_row_l2 = cs->band_out_row_l2;
        /* Allow writing up to band_height_l2 + 4 (extra scratch rows in
           band_data_l2) so the cascade can still drive level-3 even after
           the "real" band is full. */
        if (out_row_l2 >= cs->band_height_l2 + 4) return;

        PIXEL *lp_rows[6], *hp_rows[6];
        int base = (cs->buf_row_l2 - 6) % FUSED_ROW_BUFS;
        for (int r = 0; r < 6; r++) {
            int idx = (base + r) % FUSED_ROW_BUFS;
            if (idx < 0) idx += FUSED_ROW_BUFS;
            lp_rows[r] = cs->lp_buf_l2[idx];
            hp_rows[r] = cs->hp_buf_l2[idx];
        }
        int is_top = (out_row_l2 == 0);
        int is_bottom = (out_row_l2 == cs->band_height_l2 - 1);

        PIXEL *ll2 = cs->ll2_row_scratch;  /* fed to level 3 below */
        PIXEL *lh2 = cs->band_data_l2[1] + out_row_l2 * bw_l2;
        PIXEL *hl2 = cs->band_data_l2[2] + out_row_l2 * bw_l2;
        PIXEL *hh2 = cs->band_data_l2[3] + out_row_l2 * bw_l2;

        vertical_filter_quantize_row(lp_rows, bw_l2,
            cs->midpoint_l2[0], cs->multiplier_l2[0],
            cs->midpoint_l2[1], cs->multiplier_l2[1],
            0,0, 0,0,
            ll2, lh2, NULL, NULL,
            is_top, is_bottom);

        vertical_filter_quantize_row(hp_rows, bw_l2,
            cs->midpoint_l2[2], cs->multiplier_l2[2],
            cs->midpoint_l2[3], cs->multiplier_l2[3],
            0,0, 0,0,
            hl2, hh2, NULL, NULL,
            is_top, is_bottom);

        cs->band_out_row_l2++;

        /* ---- Cascade the LL2 row into level 3 ---- */
        int slot3 = cs->buf_row_l3 % FUSED_ROW_BUFS;
        horizontal_filter(ll2,
                          cs->lp_buf_l3[slot3], cs->hp_buf_l3[slot3],
                          bw_l2, /*prescale=*/2);
        cs->buf_row_l3++;

        /* ---- Level 3 vertical filter ---- */
        if (cs->buf_row_l3 >= 6 && (cs->buf_row_l3 % 2) == 0) {
            int out_row_l3 = cs->band_out_row_l3;
            /* Allow writing into the +4 scratch rows of band_data_l3. */
            if (out_row_l3 >= cs->band_height_l3 + 4) return;

            PIXEL *lp_rows3[6], *hp_rows3[6];
            int base3 = (cs->buf_row_l3 - 6) % FUSED_ROW_BUFS;
            for (int r = 0; r < 6; r++) {
                int idx = (base3 + r) % FUSED_ROW_BUFS;
                if (idx < 0) idx += FUSED_ROW_BUFS;
                lp_rows3[r] = cs->lp_buf_l3[idx];
                hp_rows3[r] = cs->hp_buf_l3[idx];
            }
            int is_top3 = (out_row_l3 == 0);
            int is_bottom3 = (out_row_l3 == cs->band_height_l3 - 1);

            PIXEL *ll3 = cs->band_data_l3[0] + out_row_l3 * bw_l3;
            PIXEL *lh3 = cs->band_data_l3[1] + out_row_l3 * bw_l3;
            PIXEL *hl3 = cs->band_data_l3[2] + out_row_l3 * bw_l3;
            PIXEL *hh3 = cs->band_data_l3[3] + out_row_l3 * bw_l3;

            vertical_filter_quantize_row(lp_rows3, bw_l3,
                cs->midpoint_l3[0], cs->multiplier_l3[0],
                cs->midpoint_l3[1], cs->multiplier_l3[1],
                0,0, 0,0,
                ll3, lh3, NULL, NULL,
                is_top3, is_bottom3);

            vertical_filter_quantize_row(hp_rows3, bw_l3,
                cs->midpoint_l3[2], cs->multiplier_l3[2],
                cs->midpoint_l3[3], cs->multiplier_l3[3],
                0,0, 0,0,
                hl3, hh3, NULL, NULL,
                is_top3, is_bottom3);

            cs->band_out_row_l3++;
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

    /* Bottom-edge handling: the 6-tap vertical filter under-runs by 2
       rows per level. To produce the missing bottom outputs, we run
       extra "tail" iterations beyond ch_height that replicate the last
       horizontal-filter result instead of consuming new input. The number
       of extras needed depends on how many levels are stacked. */
    int tail_extras = 4;  /* enough for pass1 alone */
    if (cs->streaming_active) {
        /* Each cascade level needs 4 extra inputs to emit its 2 missing
           bottom-edge outputs. Three levels stacked needs
             tail = 2*(2*(2*band_h_l3+4)+4)+4 - 2*band_h_l1 = 28.
           Derivation: L_in(L_out)=2*L_out+4 per level, applied 3 times. */
        tail_extras = 28;
    }
    int total_rows = ch_height + tail_extras;

    for (int row = 0; row < total_rows; row++) {
        int buf_idx = cs->buf_row % FUSED_ROW_BUFS;

        if (row < ch_height) {
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

            horizontal_filter(unpack_row,
                              cs->lowpass_buf[buf_idx],
                              cs->highpass_buf[buf_idx],
                              ch_width, prescale);
        } else {
            /* Tail: replicate the previous slot's lp/hp. */
            int prev = (cs->buf_row - 1) % FUSED_ROW_BUFS;
            if (prev != buf_idx) {
                memcpy(cs->lowpass_buf[buf_idx], cs->lowpass_buf[prev],
                       (size_t)(ch_width / 2) * sizeof(PIXEL));
                memcpy(cs->highpass_buf[buf_idx], cs->highpass_buf[prev],
                       (size_t)(ch_width / 2) * sizeof(PIXEL));
            }
        }
        cs->buf_row++;

#ifdef FUSED_TIMING_DETAIL
        t_horiz += _fused_ms() - _td; _td = _fused_ms();
#endif

        if (cs->buf_row >= 6 && (cs->buf_row % 2) == 0) {
            int out_row = cs->band_out_row;
            /* Allow the tail to write into the +12 scratch rows so the
               streaming cascade can drive level 3 all the way to
               band_height_l3. */
            if (out_row >= cs->band_height + 12) continue;

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

            /* Output destinations:
               - single-level inline tokenize: per-row scratch (band rows are
                 immediately tokenized, no full band buffer needed)
               - multi-level streaming: LL1 goes to row_scratch[0] (consumed
                 immediately by the streaming cascade); LH1/HL1/HH1 go to
                 their full band buffers (Pass 2 input)
               - everything else (split mode): full band buffers */
            const int inline_mode = (cs->inline_state[1] != NULL);
            const int streaming = cs->streaming_active;
            PIXEL *ll_row = inline_mode    ? cs->row_scratch[0]
                          : streaming      ? cs->row_scratch[0]
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
                0, 0, 0, 0,
                ll_row, lh_row, NULL, NULL,
                is_top, is_bottom);

            vertical_filter_quantize_row(hp_rows, bw,
                cs->midpoint[2], cs->multiplier[2],
                cs->midpoint[3], cs->multiplier[3],
                0, 0, 0, 0,
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

            /* Multi-level streaming: cascade the fresh LL1 row through
               level-2 and level-3 wavelets while it's hot in cache. */
            if (streaming) {
                stream_cascade_higher_levels(cs, ll_row);
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

typedef struct {
    int channel;
    const uint8_t *raw_bayer;
    int width, height;
    int log_bits, is_rggb, prescale;
    FUSED_CHANNEL_STATE *cs;
    CHANNEL_SYNC *sync;
} PASS1_CHANNEL_TASK;

static void *pass1_channel_thread(void *arg) {
    PASS1_CHANNEL_TASK *t = (PASS1_CHANNEL_TASK *)arg;
    pass1_run_channel(t->channel, t->raw_bayer, t->width, t->height,
                      t->log_bits, t->is_rggb, t->prescale, t->cs);

    /* Signal that this channel's Pass 1 is complete — unblocks its 3 P2 bands */
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
   ~200 MB at 50 MP. When multi_level is on, also allocates level-2 and
   level-3 band buffers (each is 1/4 and 1/16 the level-1 band size). */
static int setup_channel_state(
    FUSED_CHANNEL_STATE ch_state[4],
    int width, int height, int quality,
    int inline_mode, int multi_level, int streaming,
    int *out_is_rggb, int *out_log_bits)
{
    int ch_width = width / 2;
    int ch_height = height / 2;
    const QUANT *qt = quality_tables[(quality >= 0 && quality < 9) ? quality : 3];

    for (int ch = 0; ch < 4; ch++) {
        /* Level-1 quant: qt[0]=LL1 (effectively no-op divisor=1),
           qt[7,8,9]=LH1,HL1,HH1 in multi-level mode (coarsest quantization
           on the largest bands). Single-level mode uses qt[1..3]. */
        int q_ll1 = 0, q_lh1 = 1, q_hl1 = 2, q_hh1 = 3;
        if (multi_level) {
            q_ll1 = 0; q_lh1 = 7; q_hl1 = 8; q_hh1 = 9;
        }
        ch_state[ch].midpoint[0] = get_midpoint(qt[q_ll1]);
        ch_state[ch].multiplier[0] = get_multiplier(qt[q_ll1]);
        ch_state[ch].midpoint[1] = get_midpoint(qt[q_lh1]);
        ch_state[ch].multiplier[1] = get_multiplier(qt[q_lh1]);
        ch_state[ch].midpoint[2] = get_midpoint(qt[q_hl1]);
        ch_state[ch].multiplier[2] = get_multiplier(qt[q_hl1]);
        ch_state[ch].midpoint[3] = get_midpoint(qt[q_hh1]);
        ch_state[ch].multiplier[3] = get_multiplier(qt[q_hh1]);

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
            if (inline_mode && !multi_level) {
                /* Need only a small row scratch instead of the full band */
                ch_state[ch].band_data[band] = NULL;
                ch_state[ch].row_scratch[band] = (PIXEL *)calloc(bw, sizeof(PIXEL));
                if (!ch_state[ch].row_scratch[band]) return -1;
            } else if (multi_level && streaming && band == 0) {
                /* Streaming multi-level: LL1 is consumed inline as it's
                   produced — no need to buffer the full band. Use a 1-row
                   scratch instead. */
                ch_state[ch].band_data[band] = NULL;
                ch_state[ch].row_scratch[band] = (PIXEL *)calloc(bw, sizeof(PIXEL));
                if (!ch_state[ch].row_scratch[band]) return -1;
            } else {
                /* +12 extra rows for the bottom-edge tail handler.
                   Derivation: each cascade level under-runs by 2 outputs;
                   to fill 2 extra L3 outputs we need 4 extra L2 outputs
                   (= 8 extra L1 outputs). Plus L1's own under-run = 12
                   extras. Pass 2 still only encodes band_height rows. */
                ch_state[ch].band_data[band] = (PIXEL *)calloc((size_t)bw * (bh + 12), sizeof(PIXEL));
                ch_state[ch].row_scratch[band] = NULL;
                if (!ch_state[ch].band_data[band]) return -1;
            }
        }
        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            ch_state[ch].lowpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            ch_state[ch].highpass_buf[r] = (PIXEL *)calloc(ch_width / 2, sizeof(PIXEL));
            if (!ch_state[ch].lowpass_buf[r] || !ch_state[ch].highpass_buf[r]) return -1;
        }

        /* Multi-level: allocate level-2 and level-3 band buffers + quant.
           Use ceil at each step so odd-width inputs don't silently drop
           the unpaired column. */
        if (multi_level) {
            int bw2 = (bw + 1) / 2, bh2 = (bh + 1) / 2;
            int bw3 = (bw2 + 1) / 2, bh3 = (bh2 + 1) / 2;
            ch_state[ch].band_width_l2 = bw2;
            ch_state[ch].band_height_l2 = bh2;
            ch_state[ch].band_width_l3 = bw3;
            ch_state[ch].band_height_l3 = bh3;
            for (int band = 0; band < 4; band++) {
                /* Streaming mode: skip the LL2 full-image buffer (band==0). */
                int need_l2 = !(streaming && band == 0);
                if (need_l2) {
                    /* +4 extra rows so the bottom-edge tail cascade can
                       write past band_height without overflowing. */
                    ch_state[ch].band_data_l2[band] = (PIXEL *)calloc(
                        (size_t)bw2 * (bh2 + 4), sizeof(PIXEL));
                    if (!ch_state[ch].band_data_l2[band]) return -1;
                } else {
                    ch_state[ch].band_data_l2[band] = NULL;
                }
                ch_state[ch].band_data_l3[band] = (PIXEL *)calloc(
                    (size_t)bw3 * (bh3 + 4), sizeof(PIXEL));
                if (!ch_state[ch].band_data_l3[band]) return -1;
            }
            /* Streaming buffers — only in streaming mode */
            if (streaming) {
                for (int r = 0; r < FUSED_ROW_BUFS; r++) {
                    ch_state[ch].lp_buf_l2[r] = (PIXEL *)calloc(bw2, sizeof(PIXEL));
                    ch_state[ch].hp_buf_l2[r] = (PIXEL *)calloc(bw2, sizeof(PIXEL));
                    ch_state[ch].lp_buf_l3[r] = (PIXEL *)calloc(bw3, sizeof(PIXEL));
                    ch_state[ch].hp_buf_l3[r] = (PIXEL *)calloc(bw3, sizeof(PIXEL));
                    if (!ch_state[ch].lp_buf_l2[r] || !ch_state[ch].hp_buf_l2[r] ||
                        !ch_state[ch].lp_buf_l3[r] || !ch_state[ch].hp_buf_l3[r])
                        return -1;
                }
                ch_state[ch].ll2_row_scratch = (PIXEL *)calloc(bw2, sizeof(PIXEL));
                if (!ch_state[ch].ll2_row_scratch) return -1;
                ch_state[ch].buf_row_l2 = 0;
                ch_state[ch].band_out_row_l2 = 0;
                ch_state[ch].buf_row_l3 = 0;
                ch_state[ch].band_out_row_l3 = 0;
                ch_state[ch].streaming_active = 1;
            } else {
                ch_state[ch].streaming_active = 0;
            }
            /* Level-2: qt[0]=LL2 (no-op), qt[4,5,6]=LH2,HL2,HH2 */
            ch_state[ch].midpoint_l2[0] = get_midpoint(qt[0]);
            ch_state[ch].multiplier_l2[0] = get_multiplier(qt[0]);
            ch_state[ch].midpoint_l2[1] = get_midpoint(qt[4]);
            ch_state[ch].multiplier_l2[1] = get_multiplier(qt[4]);
            ch_state[ch].midpoint_l2[2] = get_midpoint(qt[5]);
            ch_state[ch].multiplier_l2[2] = get_multiplier(qt[5]);
            ch_state[ch].midpoint_l2[3] = get_midpoint(qt[6]);
            ch_state[ch].multiplier_l2[3] = get_multiplier(qt[6]);
            /* Level-3: qt[0]=LL3 (encoded), qt[1,2,3]=LH3,HL3,HH3.
               The LL3 divisor needs to keep magnitudes under rANS's
               2047 mag-class ceiling. With prescale=2 at every wavelet
               level, LL3 magnitude stays near the original log value
               (≤16383 for 14-bit input). Divisor of 16 keeps worst-case
               ≤1024 with safe headroom. Empirically, going to 8 doesn't
               move PSNR meaningfully (LL3 isn't the quality bottleneck —
               highpass quant is). */
            #define FUSED_LL3_EXTRA_DIVISOR 16
            int ll3_div = qt[0] * FUSED_LL3_EXTRA_DIVISOR;
            ch_state[ch].midpoint_l3[0] = get_midpoint(ll3_div);
            ch_state[ch].multiplier_l3[0] = get_multiplier(ll3_div);
            ch_state[ch].midpoint_l3[1] = get_midpoint(qt[1]);
            ch_state[ch].multiplier_l3[1] = get_multiplier(qt[1]);
            ch_state[ch].midpoint_l3[2] = get_midpoint(qt[2]);
            ch_state[ch].multiplier_l3[2] = get_multiplier(qt[2]);
            ch_state[ch].midpoint_l3[3] = get_midpoint(qt[3]);
            ch_state[ch].multiplier_l3[3] = get_multiplier(qt[3]);
        } else {
            for (int band = 0; band < 4; band++) {
                ch_state[ch].band_data_l2[band] = NULL;
                ch_state[ch].band_data_l3[band] = NULL;
            }
        }
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
    int multi_level;  /* 1 = 3-level wavelet decomposition (10 bands × 4 ch);
                          0 = single-level (3 bands × 4 ch, legacy) */
    int streaming;    /* When multi_level=1: 1 = stream level-2/3 inline with
                          level-1 (no LL1/LL2 band buffers, embedded-friendly);
                          0 = sequential (full LL1/LL2 buffers, simpler). */

    FUSED_CHANNEL_STATE ch_state[4];

    /* Persistent Pass 2 enc buffers (one per band) */
    uint8_t *enc_bufs[12];
    size_t   enc_caps[12];

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

/* Multi-level mode is off by default while it stabilizes; opt in via env.
   When on, the encoder produces 10 bands/channel (40 total) instead of 3,
   giving ~2× tighter compression at the cost of extra memory (LL1 + LL2 +
   LL3 buffers) and serial post-Pass-1 work. */
static int fused_choose_multi_level(void) {
    const char *env = getenv("FUSED_MULTI_LEVEL");
    if (env) {
        if (env[0] == '0') return 0;
        if (env[0] == '1') return 1;
    }
    return 0;
}

/* Multi-level streaming: when set (and multi_level=1), runs levels 2 and 3
   inline inside each channel's Pass 1 thread instead of as a separate
   post-Pass-1 stage. Saves the LL1 and LL2 full-image buffers
   (~57 MB at 50 MP) at the cost of slightly more complex bookkeeping.
   Default: 1 (streaming is the embedded-friendly choice; sequential
   is kept as a debug/comparison path). */
static int fused_choose_streaming(void) {
    const char *env = getenv("FUSED_MULTI_LEVEL_STREAMING");
    if (env) {
        if (env[0] == '0') return 0;
        if (env[0] == '1') return 1;
    }
    return 1;
}

/* Reset just the per-frame state on a context (counters, run state, freq tables,
   inline-tokenize state). Band buffers / row scratch are overwritten as work
   progresses so no per-frame zeroing needed. */
static void fused_reset_frame_state(FUSED_ENCODER *ctx) {
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        cs->band_out_row = 0;
        cs->buf_row = 0;
        cs->buf_row_l2 = 0;
        cs->band_out_row_l2 = 0;
        cs->buf_row_l3 = 0;
        cs->band_out_row_l3 = 0;
        memset(cs->freq, 0, sizeof(cs->freq));
        memset(cs->run_state, 0, sizeof(cs->run_state));
        for (int band = 1; band < 4; band++) {
            if (cs->inline_state[band]) jans_inline_reset(cs->inline_state[band]);
        }
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
    ctx->multi_level = fused_choose_multi_level();
    ctx->streaming = ctx->multi_level ? fused_choose_streaming() : 0;
    /* Multi-level requires split mode (we need LL1/LL2 buffers in memory). */
    if (ctx->multi_level && ctx->inline_mode) {
        ctx->inline_mode = 0;
    }

    SetupEncoderLogCurve();

    int dummy_is_rggb, dummy_log_bits;
    if (setup_channel_state(ctx->ch_state, width, height, quality,
                             ctx->inline_mode, ctx->multi_level, ctx->streaming,
                             &dummy_is_rggb, &dummy_log_bits) != 0) {
        gpr_encode_fused_destroy(ctx);
        return NULL;
    }

    /* Pre-allocate persistent enc buffers + (if inline) inline-tokenize state */
    int p2_idx = 0;
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        size_t band_coeffs = (size_t)cs->band_width * cs->band_height;
        for (int band = 1; band < 4; band++) {
            size_t cap = band_coeffs * 4 + 8192;
            ctx->enc_caps[p2_idx] = cap;
            ctx->enc_bufs[p2_idx] = (uint8_t *)malloc(cap);
            if (!ctx->enc_bufs[p2_idx]) {
                gpr_encode_fused_destroy(ctx);
                return NULL;
            }
            if (ctx->inline_mode) {
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
                if (stripe_coeffs > band_coeffs) stripe_coeffs = band_coeffs;
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
    for (int i = 0; i < 12; i++) if (ctx->enc_bufs[i]) free(ctx->enc_bufs[i]);
    if (ctx->stream_buf) free(ctx->stream_buf);
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];
        for (int band = 0; band < 4; band++) {
            if (cs->band_data[band])   free(cs->band_data[band]);
            if (cs->row_scratch[band]) free(cs->row_scratch[band]);
            if (cs->inline_state[band]) jans_inline_destroy(cs->inline_state[band]);
            if (cs->band_data_l2[band]) free(cs->band_data_l2[band]);
            if (cs->band_data_l3[band]) free(cs->band_data_l3[band]);
        }
        for (int r = 0; r < FUSED_ROW_BUFS; r++) {
            if (cs->lowpass_buf[r])  free(cs->lowpass_buf[r]);
            if (cs->highpass_buf[r]) free(cs->highpass_buf[r]);
            if (cs->lp_buf_l2[r])    free(cs->lp_buf_l2[r]);
            if (cs->hp_buf_l2[r])    free(cs->hp_buf_l2[r]);
            if (cs->lp_buf_l3[r])    free(cs->lp_buf_l3[r]);
            if (cs->hp_buf_l3[r])    free(cs->hp_buf_l3[r]);
        }
        if (cs->ll2_row_scratch) free(cs->ll2_row_scratch);
    }
    free(ctx);
}

/* Forward decl — multi-level path is implemented below. */
static int gpr_encode_fused_frame_multilevel(FUSED_ENCODER *ctx,
                                              const uint8_t *raw_bayer,
                                              uint8_t **vc5_out,
                                              size_t *vc5_size);

int gpr_encode_fused_frame(FUSED_ENCODER *ctx,
                            const uint8_t *raw_bayer, size_t raw_size,
                            uint8_t **vc5_out, size_t *vc5_size)
{
    (void)raw_size;
    if (!ctx || !raw_bayer || !vc5_out || !vc5_size) return -1;
    if (ctx->multi_level) {
        return gpr_encode_fused_frame_multilevel(ctx, raw_bayer, vc5_out, vc5_size);
    }
    int rc = 0;
    PASS2_BAND_TASK p2_tasks[12];
    memset(p2_tasks, 0, sizeof(p2_tasks));
    pthread_t p2_threads[12];
    int p2_created[12] = {0};
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
        for (int band = 1; band < 4; band++) {
            PASS2_BAND_TASK *pt = &p2_tasks[p2_count];
            pt->channel = ch;
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
    }

    if (!run_serial) {
        for (int ch = 0; ch < 4; ch++) {
            if (!p1_created[ch]) pass1_channel_thread(&p1_tasks[ch]);
        }
    }
    for (int ch = 0; ch < 4; ch++) {
        if (p1_created[ch]) pthread_join(p1_threads[ch], NULL);
    }

#ifdef FUSED_TIMING
    double t1 = _fused_ms();
    fprintf(stderr, "  FUSED Pass1 (parallel, signals P2):      %.1fms\n", t1 - t0);
#endif

    for (int i = 0; i < 12; i++) {
        if (p2_created[i]) pthread_join(p2_threads[i], NULL);
    }

#ifdef FUSED_TIMING
    double t2 = _fused_ms();
    fprintf(stderr, "  FUSED Pass2 (overlapped w/ P1):          %.1fms (since P1 end)\n", t2 - t1);
#endif

    pthread_mutex_destroy(&sync.lock);
    pthread_cond_destroy(&sync.cv);

    /* Emit header + band manifest + band data into stream_buf. */
    const int num_bands = 12;
    FUSED_HEADER hdr;
    hdr.magic = FUSED_MAGIC;
    hdr.version = FUSED_VERSION;
    hdr.width = ctx->width;
    hdr.height = ctx->height;
    hdr.pixel_format = ctx->pixel_format;
    hdr.quality = ctx->quality;
    hdr.is_rggb = ctx->is_rggb;
    hdr.log_bits = ctx->log_bits;
    hdr.prescale = ctx->prescale;
    hdr.multi_level = 0;
    hdr.num_bands = num_bands;
    hdr.reserved = 0;

    size_t pos = 0;
    memcpy(ctx->stream_buf + pos, &hdr, sizeof(hdr)); pos += sizeof(hdr);
    /* Band-size table */
    for (int i = 0; i < num_bands; i++) {
        uint32_t sz = (uint32_t)p2_tasks[i].enc_size;
        memcpy(ctx->stream_buf + pos, &sz, sizeof(sz)); pos += sizeof(sz);
    }
    /* Band data */
    for (int i = 0; i < num_bands; i++) {
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
   Multi-level path (3-level wavelet decomposition)
   ================================================================ */

/* Run level-2 and level-3 wavelets for a single channel. Called after Pass 1
   completes (so band_data[0] = LL1 is populated). Sequential — the two passes
   chain (LL2 from level-2 is input to level-3). */
typedef struct {
    FUSED_CHANNEL_STATE *cs;
} LEVEL23_TASK;

static void *level23_run_channel(void *arg) {
    LEVEL23_TASK *t = (LEVEL23_TASK *)arg;
    FUSED_CHANNEL_STATE *cs = t->cs;

    /* Level 2: decompose LL1 → LL2/LH2/HL2/HH2 */
    wavelet_decompose_buffer(
        cs->band_data[0], cs->band_width, cs->band_height,
        cs->midpoint_l2, cs->multiplier_l2,
        cs->band_data_l2[0], cs->band_data_l2[1],
        cs->band_data_l2[2], cs->band_data_l2[3]);

    /* Level 3: decompose LL2 → LL3/LH3/HL3/HH3 */
    wavelet_decompose_buffer(
        cs->band_data_l2[0], cs->band_width_l2, cs->band_height_l2,
        cs->midpoint_l3, cs->multiplier_l3,
        cs->band_data_l3[0], cs->band_data_l3[1],
        cs->band_data_l3[2], cs->band_data_l3[3]);

    return NULL;
}

/* Layout of the 40 Pass-2 tasks in multi-level mode:
     For each channel (0..3):
       0: LH1   1: HL1   2: HH1     (level-1 highpass)
       3: LH2   4: HL2   5: HH2     (level-2 highpass)
       6: LH3   7: HL3   8: HH3     (level-3 highpass)
       9: LL3                       (level-3 lowpass — encoded)
   Index = channel * 10 + slot. */
static int gpr_encode_fused_frame_multilevel(FUSED_ENCODER *ctx,
                                              const uint8_t *raw_bayer,
                                              uint8_t **vc5_out,
                                              size_t *vc5_size)
{
    int rc = 0;
    const int p2_tasks_total = 40;
    PASS2_BAND_TASK *p2_tasks = (PASS2_BAND_TASK *)calloc(p2_tasks_total, sizeof(PASS2_BAND_TASK));
    pthread_t *p2_threads = (pthread_t *)calloc(p2_tasks_total, sizeof(pthread_t));
    int *p2_created = (int *)calloc(p2_tasks_total, sizeof(int));
    if (!p2_tasks || !p2_threads || !p2_created) {
        free(p2_tasks); free(p2_threads); free(p2_created);
        return -1;
    }

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

    /* ---- Dispatch Pass 1 (level-1 wavelet) ---- */
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
        if (run_serial) {
            pass1_channel_thread(&p1_tasks[ch]);
        } else {
            p1_created[ch] = (pthread_create(&p1_threads[ch], NULL,
                                              pass1_channel_thread, &p1_tasks[ch]) == 0);
            if (!p1_created[ch]) pass1_channel_thread(&p1_tasks[ch]);
        }
    }
    for (int ch = 0; ch < 4; ch++) {
        if (p1_created[ch]) pthread_join(p1_threads[ch], NULL);
    }

#ifdef FUSED_TIMING
    double t1 = _fused_ms();
    fprintf(stderr, "  FUSED ML Pass1 (level-1, parallel):       %.1fms\n", t1 - t0);
#endif

    /* ---- Level 2 + Level 3 wavelets per channel (parallel).
       Streaming mode: skip — already run inline in pass1 per channel. */
    if (!ctx->streaming) {
        LEVEL23_TASK l23_tasks[4];
        pthread_t l23_threads[4];
        int l23_created[4] = {0};
        for (int ch = 0; ch < 4; ch++) {
            l23_tasks[ch].cs = &ctx->ch_state[ch];
            if (run_serial) {
                level23_run_channel(&l23_tasks[ch]);
            } else {
                l23_created[ch] = (pthread_create(&l23_threads[ch], NULL,
                                                   level23_run_channel, &l23_tasks[ch]) == 0);
                if (!l23_created[ch]) level23_run_channel(&l23_tasks[ch]);
            }
        }
        for (int ch = 0; ch < 4; ch++) {
            if (l23_created[ch]) pthread_join(l23_threads[ch], NULL);
        }
    }

#ifdef FUSED_TIMING
    double t2 = _fused_ms();
    fprintf(stderr, "  FUSED ML Level23 (%s):     %.1fms\n",
            ctx->streaming ? "streamed in pass1" : "post-pass1 per ch",
            t2 - t1);
#endif

    /* ---- Dispatch Pass 2 for all 40 bands ---- */
    int p2_count = 0;
    for (int ch = 0; ch < 4; ch++) {
        FUSED_CHANNEL_STATE *cs = &ctx->ch_state[ch];

        struct {
            PIXEL *data;
            int width, height;
        } slots[10] = {
            { cs->band_data[1],    cs->band_width,    cs->band_height    }, /* LH1 */
            { cs->band_data[2],    cs->band_width,    cs->band_height    }, /* HL1 */
            { cs->band_data[3],    cs->band_width,    cs->band_height    }, /* HH1 */
            { cs->band_data_l2[1], cs->band_width_l2, cs->band_height_l2 }, /* LH2 */
            { cs->band_data_l2[2], cs->band_width_l2, cs->band_height_l2 }, /* HL2 */
            { cs->band_data_l2[3], cs->band_width_l2, cs->band_height_l2 }, /* HH2 */
            { cs->band_data_l3[1], cs->band_width_l3, cs->band_height_l3 }, /* LH3 */
            { cs->band_data_l3[2], cs->band_width_l3, cs->band_height_l3 }, /* HL3 */
            { cs->band_data_l3[3], cs->band_width_l3, cs->band_height_l3 }, /* HH3 */
            { cs->band_data_l3[0], cs->band_width_l3, cs->band_height_l3 }, /* LL3 */
        };

        for (int s = 0; s < 10; s++) {
            PASS2_BAND_TASK *pt = &p2_tasks[p2_count];
            pt->channel = ch;
            pt->band_data = slots[s].data;
            pt->inline_state = NULL;
            pt->width = slots[s].width;
            pt->height = slots[s].height;
            pt->pitch = slots[s].width * sizeof(int32_t);
            pt->enc_cap = (size_t)slots[s].width * slots[s].height * 4 + 8192;
            pt->enc_buf = (uint8_t *)malloc(pt->enc_cap);
            if (!pt->enc_buf) { rc = -1; goto cleanup; }
            pt->enc_size = 0;
            pt->sync = NULL;  /* Pass 1 already waited */
            pt->denoise_strength = 0.0;
            pt->noise_scale = 0;
            pt->noise_offset = 0;

            if (run_serial) {
                pass2_band_thread(pt);
            } else {
                p2_created[p2_count] = (pthread_create(&p2_threads[p2_count], NULL,
                                                       pass2_band_thread, pt) == 0);
                if (!p2_created[p2_count]) pass2_band_thread(pt);
            }
            p2_count++;
        }
    }

    for (int i = 0; i < p2_tasks_total; i++) {
        if (p2_created[i]) pthread_join(p2_threads[i], NULL);
    }

#ifdef FUSED_TIMING
    double t3 = _fused_ms();
    fprintf(stderr, "  FUSED ML Pass2 (40 bands, parallel):      %.1fms\n", t3 - t2);
#endif

    /* ---- Emit header + band manifest + band data ---- */
    FUSED_HEADER hdr;
    hdr.magic = FUSED_MAGIC;
    hdr.version = FUSED_VERSION;
    hdr.width = ctx->width;
    hdr.height = ctx->height;
    hdr.pixel_format = ctx->pixel_format;
    hdr.quality = ctx->quality;
    hdr.is_rggb = ctx->is_rggb;
    hdr.log_bits = ctx->log_bits;
    hdr.prescale = ctx->prescale;
    hdr.multi_level = 1;
    hdr.num_bands = p2_tasks_total;
    hdr.reserved = 0;

    size_t pos = 0;
    memcpy(ctx->stream_buf + pos, &hdr, sizeof(hdr)); pos += sizeof(hdr);
    for (int i = 0; i < p2_tasks_total; i++) {
        uint32_t sz = (uint32_t)p2_tasks[i].enc_size;
        memcpy(ctx->stream_buf + pos, &sz, sizeof(sz)); pos += sizeof(sz);
    }
    for (int i = 0; i < p2_tasks_total; i++) {
        PASS2_BAND_TASK *pt = &p2_tasks[i];
        if (pt->enc_size > 0 && pos + pt->enc_size <= ctx->stream_cap) {
            memcpy(ctx->stream_buf + pos, pt->enc_buf, pt->enc_size);
            pos += pt->enc_size;
        }
    }

#ifdef FUSED_TIMING
    double t4 = _fused_ms();
    fprintf(stderr, "  FUSED ML Total:                           %.1fms\n", t4 - t0);
#endif

    *vc5_out = ctx->stream_buf;
    *vc5_size = pos;

cleanup:
    pthread_mutex_destroy(&sync.lock);
    pthread_cond_destroy(&sync.cv);
    for (int i = 0; i < p2_tasks_total; i++) {
        if (p2_tasks[i].enc_buf) free(p2_tasks[i].enc_buf);
    }
    free(p2_tasks);
    free(p2_threads);
    free(p2_created);
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
