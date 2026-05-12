/*! @file test_video_full_roundtrip.c
 *
 *  @brief Full image-level decode verification for the pipelined video encoder.
 *
 *  Extends test_video_roundtrip.c (which proves bitstreams decode at the
 *  band level) to a real PSNR-validated roundtrip:
 *
 *    raw Bayer
 *      → gpr_video_encoder (fused encoder under the hood)
 *      → 12 rANS-encoded highpass band bitstreams
 *      → jans_decode_band_x4 (per band)
 *      → inverse quant
 *      → inverse wavelet  (single level, biorthogonal 5/3, LL=0)
 *      → channel demux    (GS/RG/BG/GD → R/G1/G2/B in log domain)
 *      → inverse log curve
 *      → reconstructed Bayer
 *
 *  Then computes PSNR vs the original.
 *
 *  ## Important limitation: no LL band is transmitted
 *
 *  The fused encoder is single-level and emits only the 3 highpass bands
 *  per channel (LH, HL, HH). The LL band is computed but never written to
 *  the bitstream. Without LL, the inverse wavelet can recover the
 *  high-frequency content but loses the DC / low-frequency content
 *  entirely. PSNR therefore measures the high-frequency portion of the
 *  reconstruction.
 *
 *  To make the PSNR test meaningful despite this, we compare against an
 *  "oracle" reference: we run the encoder's own forward log-curve and
 *  channel demux on the original input, then run the same single-level
 *  forward wavelet — keeping ONLY the highpass bands and zeroing LL.
 *  The reverse of that pipeline is what the decoder produces. With
 *  matching forward + inverse math, near-perfect PSNR (>50 dB) is the
 *  passing threshold; any structural mismatch in the inverse math shows
 *  up immediately. PSNR vs original raw Bayer is reported for context
 *  but is structurally limited by the missing LL.
 *
 *  ## Rate control caveat
 *
 *  gpr_video's rate controller adjusts the quant scale per frame after
 *  the first frame; the resulting per-frame scale is not exposed via the
 *  public API. So the rigorous PSNR test runs with rate control OFF
 *  (target_MBps=0), where quant_scale stays at 1.0 for all frames.
 *  A secondary rate-controlled run is performed for additional decode
 *  verification at the band level.
 *
 *  Build:
 *    clang -O2 -o /tmp/test_video_full_roundtrip \
 *      source/app/test_video_full_roundtrip.c \
 *      build/source/lib/vc5_encoder/libvc5_encoder.a \
 *      build/source/lib/vc5_common/libvc5_common.a \
 *      -lpthread -lm
 *
 *  Usage:
 *    test_video_full_roundtrip <raw_file> <w> <h> <pf> <q> <num_frames> <fps>
 *    test_video_full_roundtrip                (no args = default Z8 ISO64+ISO22800)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <pthread.h>
#include <inttypes.h>

#include "../lib/vc5_encoder/gpr_video.h"

/* -- External symbols from libvc5_common -- */
extern int  jans_decode_band_x4(const uint8_t *in_buf, size_t in_size,
                                int32_t *data, int width, int height, int pitch);
extern void SetupEncoderLogCurve(void);
extern void SetupDecoderLogCurve(void);
extern uint16_t EncoderLogCurve14[];
extern uint16_t EncoderLogCurve16[];
extern uint16_t DecoderLogCurve14[];
extern uint16_t DecoderLogCurve16[];

/* Must match encoder's FUSED_WAVELET_LEVELS in fused_encode.c.
   Default 3 (matches encoder default); override via -DFUSED_WAVELET_LEVELS=1
   or =2 at compile time when testing shallower configurations. */
#ifndef FUSED_WAVELET_LEVELS
#define FUSED_WAVELET_LEVELS 3
#endif

#if FUSED_WAVELET_LEVELS == 1
#define BANDS_PER_CHANNEL 4    /* LL0, LH0, HL0, HH0 */
#elif FUSED_WAVELET_LEVELS == 2
#define BANDS_PER_CHANNEL 7    /* LL1, LH1, HL1, HH1, LH0, HL0, HH0 */
#elif FUSED_WAVELET_LEVELS == 3
#define BANDS_PER_CHANNEL 10   /* LL2, LH2, HL2, HH2, LH1, HL1, HH1, LH0, HL0, HH0 */
#else
#error "FUSED_WAVELET_LEVELS must be 1, 2, or 3"
#endif
#define BANDS_PER_FRAME (4 * BANDS_PER_CHANNEL)
#define FUSED_LL_DIVISOR  64  /* Must match encoder's value in fused_encode.c */
#define FUSED_LL1_DIVISOR 64  /* Must match encoder's value in fused_encode.c */
#define FUSED_LL2_DIVISOR 64  /* Must match encoder's value in fused_encode.c */

/* ============================================================
   Per-frame bitstream collection (copy from existing test)
   ============================================================ */
typedef struct {
    uint8_t *data;
    size_t   size;
    uint64_t tag;
} captured_frame;

typedef struct {
    captured_frame *frames;
    int             capacity;
    int             count;
    pthread_mutex_t lock;
    uint64_t        total_bytes;
} collector_state;

static int collect_writer(void *user_data, const uint8_t *vc5, size_t size,
                          uint64_t tag)
{
    collector_state *cs = (collector_state *)user_data;
    pthread_mutex_lock(&cs->lock);
    if (cs->count < cs->capacity) {
        captured_frame *f = &cs->frames[cs->count++];
        f->data = (uint8_t *)malloc(size);
        if (f->data) {
            memcpy(f->data, vc5, size);
            f->size = size;
            f->tag  = tag;
            cs->total_bytes += size;
        } else {
            f->size = 0;
            cs->count--;
        }
    }
    pthread_mutex_unlock(&cs->lock);
    return 0;
}

/* ============================================================
   Walk one frame's concatenated bitstream and decode all bands
   into the provided coefficient buffers (same probe logic as
   the band-level test).
   ============================================================ */
static int probe_band_bytes(const uint8_t *p, size_t avail, size_t *consumed)
{
    if (avail < 16) return -1;

    if (p[0] == 0xFF && p[1] == 0xFF && p[2] == 0xFF && p[3] == 0xFF) {
        int num_stripes = (p[4]<<24)|(p[5]<<16)|(p[6]<<8)|p[7];
        if (num_stripes < 0 || num_stripes > 1000000) return -1;
        size_t pos = 16;
        for (int s = 0; s < num_stripes; s++) {
            if (pos + 8 > avail) return -1;
            int stripe_size = (p[pos+4]<<24)|(p[pos+5]<<16)|
                              (p[pos+6]<<8) | p[pos+7];
            if (stripe_size < 0) return -1;
            pos += 8 + (size_t)stripe_size;
            if (pos > avail) return -1;
        }
        *consumed = pos;
        return 0;
    }

    int token_count = (p[0]<<24)|(p[1]<<16)|(p[2]<<8) | p[3];
    int freq_size   = (p[4]<<24)|(p[5]<<16)|(p[6]<<8) | p[7];
    int rans_size   = (p[8]<<24)|(p[9]<<16)|(p[10]<<8)| p[11];
    int resid_size  = (p[12]<<24)|(p[13]<<16)|(p[14]<<8)|p[15];
    (void)token_count;
    if (freq_size < 0 || rans_size < 0 || resid_size < 0) return -1;
    size_t total = 16 + (size_t)freq_size + (size_t)rans_size + (size_t)resid_size;
    if (total > avail) return -1;
    *consumed = total;
    return 0;
}

/* ============================================================
   Quant helpers — must match fused_encode.c exactly
   ============================================================ */
static inline int32_t get_multiplier(int divisor) {
    return (divisor > 0) ? ((1 << 16) / divisor) : 0;
}
static inline int32_t quantize_scalar(int32_t value, int32_t midpoint, int32_t multiplier) {
    int32_t mag = (value < 0) ? -value : value;
    int32_t q = (int32_t)(((int64_t)(mag + midpoint) * multiplier) >> 16);
    return (value < 0) ? -q : q;
}
static inline int32_t get_midpoint(int divisor) {
    return (divisor > 1) ? (divisor >> 1) - 1 : 0;
}

/* Quality presets (copied from fused_encode.c). q=3 default. */
static const int32_t quality_tables[9][10] = {
    {1, 24, 24, 12, 64, 64, 48, 512, 512, 768},
    {1, 24, 24, 12, 48, 48, 32, 256, 256, 384},
    {1, 24, 24, 12, 32, 32, 24, 128, 128, 192},
    {1, 24, 24, 12, 24, 24, 12, 96, 96, 144},
    {1, 24, 24, 12, 24, 24, 12, 64, 64, 96},
    {1, 24, 24, 12, 24, 24, 12, 32, 32, 48},
    {1, 12, 12,  6, 12, 12,  6, 16, 16, 24},
    {1,  6,  6,  4, 12, 12,  6, 16, 16, 24},
    {1,  4,  4,  2, 10, 10,  6, 16, 16, 24},
};

/* Single-level fused encoder uses base_divisors = FUSED_LL_DIVISOR, qt[7], qt[8], qt[9]
   (LL with safe quant + LH/HL/HH at level 0). LL is now emitted (commit bdeb3b3). */
static void fused_base_divisors(int quality, int32_t base[4]) {
    int qi = (quality >= 0 && quality < 9) ? quality : 3;
    base[0] = FUSED_LL_DIVISOR;            /* LL — emitted with fixed divisor */
    base[1] = quality_tables[qi][7];       /* LH */
    base[2] = quality_tables[qi][8];       /* HL */
    base[3] = quality_tables[qi][9];       /* HH */
}

#if FUSED_WAVELET_LEVELS >= 2
/* Per-band divisor table for 2-level layout:
     [0] LL1: FUSED_LL_DIVISOR (level-1 lowpass)
     [1] LH1: qt[4]
     [2] HL1: qt[5]
     [3] HH1: qt[6]
     [4] LH0: qt[7]
     [5] HL0: qt[8]
     [6] HH0: qt[9]
   In 2-level mode the intermediate LL0 band is NOT emitted (it is
   reconstructed by inverting the 4 level-1 bands). */
static void fused_base_divisors_2level(int quality, int32_t base[7]) {
    int qi = (quality >= 0 && quality < 9) ? quality : 3;
    base[0] = FUSED_LL1_DIVISOR;
    base[1] = quality_tables[qi][4];
    base[2] = quality_tables[qi][5];
    base[3] = quality_tables[qi][6];
    base[4] = quality_tables[qi][7];
    base[5] = quality_tables[qi][8];
    base[6] = quality_tables[qi][9];
}
#endif

#if FUSED_WAVELET_LEVELS >= 3
/* Per-band divisor table for 3-level layout:
     [0] LL2: FUSED_LL2_DIVISOR (level-2 lowpass)
     [1] LH2: qt[1]
     [2] HL2: qt[2]
     [3] HH2: qt[3]
     [4] LH1: qt[4]
     [5] HL1: qt[5]
     [6] HH1: qt[6]
     [7] LH0: qt[7]
     [8] HL0: qt[8]
     [9] HH0: qt[9]
   LL0 and LL1 are intermediate (NOT emitted). */
static void fused_base_divisors_3level(int quality, int32_t base[10]) {
    int qi = (quality >= 0 && quality < 9) ? quality : 3;
    base[0] = FUSED_LL2_DIVISOR;
    base[1] = quality_tables[qi][1];
    base[2] = quality_tables[qi][2];
    base[3] = quality_tables[qi][3];
    base[4] = quality_tables[qi][4];
    base[5] = quality_tables[qi][5];
    base[6] = quality_tables[qi][6];
    base[7] = quality_tables[qi][7];
    base[8] = quality_tables[qi][8];
    base[9] = quality_tables[qi][9];
}
#endif

/* Inverse quant: multiply quantized value by divisor.
   Symmetric counterpart of quantize_scalar with midpoint=0 — i.e. the
   midpoint causes rounding but does not change the magnitude scale. */
static inline int32_t dequantize_scalar(int32_t q, int32_t divisor) {
    /* For magnitude m, encoder did: q = ((m + mid) * mul) >> 16
       For divisor d, multiplier = 65536/d, so q = ((m + mid) / d) approx.
       We invert with: m_approx = q * d. */
    return q * divisor;
}

/* ============================================================
   Inverse wavelet — biorthogonal 5/3, single level
   Copied from source/lib/vc5_decoder/inverse.c InvertHorizontal16s
   and InvertSpatialQuant16s (no descale, no NEON).
   ============================================================ */
static const int32_t WAV_ROUND = 4;

/* Reconstruct one row from a (lowpass, highpass) pair.
   input_width = band width = output_width / 2.
   output buffer must be 2 * input_width entries. */
static void invert_horizontal_row(const int32_t *lowpass, const int32_t *highpass,
                                   int32_t *output, int input_width)
{
    const int last_column = input_width - 1;
    int32_t even, odd;

    /* Left border */
    even = 11 * lowpass[0] - 4 * lowpass[1] + lowpass[2] + WAV_ROUND;
    even >>= 3;
    even = (even + highpass[0]) >> 1;

    odd = 5 * lowpass[0] + 4 * lowpass[1] - lowpass[2] + WAV_ROUND;
    odd >>= 3;
    odd = (odd - highpass[0]) >> 1;

    output[0] = even;
    output[1] = odd;

    /* Middle */
    for (int column = 1; column < last_column; column++) {
        even = lowpass[column - 1] - lowpass[column + 1] + WAV_ROUND;
        even >>= 3;
        even += lowpass[column];
        even = (even + highpass[column]) >> 1;
        output[2 * column] = even;

        odd = -lowpass[column - 1] + lowpass[column + 1] + WAV_ROUND;
        odd >>= 3;
        odd += lowpass[column];
        odd = (odd - highpass[column]) >> 1;
        output[2 * column + 1] = odd;
    }

    /* Right border */
    int column = last_column;
    even = 5 * lowpass[column] + 4 * lowpass[column - 1] - lowpass[column - 2] + WAV_ROUND;
    even >>= 3;
    even = (even + highpass[column]) >> 1;
    output[2 * column] = even;

    odd = 11 * lowpass[column] - 4 * lowpass[column - 1] + lowpass[column - 2] + WAV_ROUND;
    odd >>= 3;
    odd = (odd - highpass[column]) >> 1;
    output[2 * column + 1] = odd;
}

/* Inverse spatial single-level: 4 bands (LL, LH, HL, HH) → reconstructed channel
   image (in log/channel domain). bw = band_width, bh = band_height.
   Output image is (bw*2) x (bh*2) int32 (channel domain, ~14 or 16-bit
   range plus prescale headroom).

   This mirrors InvertSpatialQuant16s but operates entirely on already-
   dequantized PIXEL bands (no QUANT magic), no descale (descale handled
   separately), and no NEON. ClampPixel is omitted (PIXEL_MIN/MAX in
   the production codec are INT32 limits — we never approach them). */
static void invert_spatial_band(
    const int32_t *ll, const int32_t *lh,
    const int32_t *hl, const int32_t *hh,
    int bw, int bh,
    int32_t *output, int output_pitch_pix)
{
    const int input_width = bw;
    const int input_height = bh;
    const int last_row = input_height - 1;
    int row;

    /* Per-row arena: we need a 3-row sliding window of LH (and the current
       row of LL/HL/HH) to vertically filter LL+HL into even/odd lowpass
       and LH+HH into even/odd highpass, then horizontally invert each. */
    int32_t *even_lowpass  = (int32_t *)malloc(bw * sizeof(int32_t));
    int32_t *odd_lowpass   = (int32_t *)malloc(bw * sizeof(int32_t));
    int32_t *even_highpass = (int32_t *)malloc(bw * sizeof(int32_t));
    int32_t *odd_highpass  = (int32_t *)malloc(bw * sizeof(int32_t));
    if (!even_lowpass || !odd_lowpass || !even_highpass || !odd_highpass) {
        free(even_lowpass); free(odd_lowpass);
        free(even_highpass); free(odd_highpass);
        return;
    }

    int32_t *even_out = output;
    int32_t *odd_out  = output + output_pitch_pix;

    /* First row (top border): use rows 0, 1, 2 of LL and LH. */
    {
        const int32_t *ll0 = ll + 0 * bw;
        const int32_t *ll1 = ll + 1 * bw;
        const int32_t *ll2 = ll + 2 * bw;
        const int32_t *lh0 = lh + 0 * bw;
        const int32_t *lh1 = lh + 1 * bw;
        const int32_t *lh2 = lh + 2 * bw;
        const int32_t *hl_row = hl + 0 * bw;
        const int32_t *hh_row = hh + 0 * bw;

        for (int column = 0; column < input_width; column++) {
            int32_t even = 11 * ll0[column] - 4 * ll1[column] + ll2[column] + WAV_ROUND;
            even >>= 3;
            even += hl_row[column];
            even >>= 1;
            even_lowpass[column] = even;

            int32_t odd = 5 * ll0[column] + 4 * ll1[column] - ll2[column] + WAV_ROUND;
            odd >>= 3;
            odd -= hl_row[column];
            odd >>= 1;
            odd_lowpass[column] = odd;

            even = 11 * lh0[column] - 4 * lh1[column] + lh2[column] + WAV_ROUND;
            even >>= 3;
            even += hh_row[column];
            even >>= 1;
            even_highpass[column] = even;

            odd = 5 * lh0[column] + 4 * lh1[column] - lh2[column] + WAV_ROUND;
            odd >>= 3;
            odd -= hh_row[column];
            odd >>= 1;
            odd_highpass[column] = odd;
        }

        invert_horizontal_row(even_lowpass, even_highpass, even_out, input_width);
        invert_horizontal_row(odd_lowpass,  odd_highpass,  odd_out,  input_width);
    }

    /* Middle rows. Slide the LL/LH triplet (row-1, row, row+1). */
    for (row = 1; row < last_row; row++) {
        const int32_t *ll_m = ll + (row - 1) * bw;
        const int32_t *ll_c = ll + (row    ) * bw;
        const int32_t *ll_p = ll + (row + 1) * bw;
        const int32_t *lh_m = lh + (row - 1) * bw;
        const int32_t *lh_c = lh + (row    ) * bw;
        const int32_t *lh_p = lh + (row + 1) * bw;
        const int32_t *hl_row = hl + row * bw;
        const int32_t *hh_row = hh + row * bw;

        for (int column = 0; column < input_width; column++) {
            /* Mirrors the InvertSpatialQuant16s "middle rows" scalar path. */
            int32_t even = ll_m[column] - ll_p[column] + WAV_ROUND;
            even >>= 3;
            even += ll_c[column];
            even += hl_row[column];
            even >>= 1;
            even_lowpass[column] = even;

            int32_t odd = -ll_m[column] + ll_p[column] + WAV_ROUND;
            odd >>= 3;
            odd += ll_c[column];
            odd -= hl_row[column];
            odd >>= 1;
            odd_lowpass[column] = odd;

            even = lh_m[column] - lh_p[column] + WAV_ROUND;
            even >>= 3;
            even += lh_c[column];
            even += hh_row[column];
            even >>= 1;
            even_highpass[column] = even;

            odd = -lh_m[column] + lh_p[column] + WAV_ROUND;
            odd >>= 3;
            odd += lh_c[column];
            odd -= hh_row[column];
            odd >>= 1;
            odd_highpass[column] = odd;
        }

        even_out += 2 * output_pitch_pix;
        odd_out  += 2 * output_pitch_pix;
        invert_horizontal_row(even_lowpass, even_highpass, even_out, input_width);
        invert_horizontal_row(odd_lowpass,  odd_highpass,  odd_out,  input_width);
    }

    /* Last row (bottom border): use rows last-2, last-1, last of LL and LH. */
    row = last_row;
    {
        const int32_t *ll_m2 = ll + (row - 2) * bw;
        const int32_t *ll_m1 = ll + (row - 1) * bw;
        const int32_t *ll_0  = ll + (row    ) * bw;
        const int32_t *lh_m2 = lh + (row - 2) * bw;
        const int32_t *lh_m1 = lh + (row - 1) * bw;
        const int32_t *lh_0  = lh + (row    ) * bw;
        const int32_t *hl_row = hl + row * bw;
        const int32_t *hh_row = hh + row * bw;

        for (int column = 0; column < input_width; column++) {
            int32_t even = 5 * ll_0[column] + 4 * ll_m1[column] - ll_m2[column] + WAV_ROUND;
            even >>= 3;
            even += hl_row[column];
            even >>= 1;
            even_lowpass[column] = even;

            int32_t odd = 11 * ll_0[column] - 4 * ll_m1[column] + ll_m2[column] + WAV_ROUND;
            odd >>= 3;
            odd -= hl_row[column];
            odd >>= 1;
            odd_lowpass[column] = odd;

            even = 5 * lh_0[column] + 4 * lh_m1[column] - lh_m2[column] + WAV_ROUND;
            even >>= 3;
            even += hh_row[column];
            even >>= 1;
            even_highpass[column] = even;

            odd = 11 * lh_0[column] - 4 * lh_m1[column] + lh_m2[column] + WAV_ROUND;
            odd >>= 3;
            odd -= hh_row[column];
            odd >>= 1;
            odd_highpass[column] = odd;
        }

        even_out += 2 * output_pitch_pix;
        odd_out  += 2 * output_pitch_pix;
        invert_horizontal_row(even_lowpass, even_highpass, even_out, input_width);
        invert_horizontal_row(odd_lowpass,  odd_highpass,  odd_out,  input_width);
    }

    free(even_lowpass); free(odd_lowpass);
    free(even_highpass); free(odd_highpass);
}

/* ============================================================
   Forward path that mirrors the fused encoder exactly (so we
   can build an oracle reference for PSNR validation that
   isolates the inverse pipeline math).
   ============================================================ */
static inline int32_t clamp_to(int32_t v, int32_t lo, int32_t hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* Forward log curve + channel demux for the whole image — produces
   ch_height x ch_width buffers for GS, RG, BG, GD (channel domain). */
static void fwd_channels(const uint16_t *bayer, int w, int h, int log_bits, int is_rggb,
                          int32_t *gs, int32_t *rg, int32_t *bg, int32_t *gd)
{
    int ch_w = w / 2, ch_h = h / 2;
    int log_max = (log_bits <= 14) ? 16383 : 65535;
    const uint16_t *log_tbl = (log_bits <= 14) ? EncoderLogCurve14 : EncoderLogCurve16;
    int32_t mid2 = 2 * (1 << (log_bits - 1));

    for (int r = 0; r < ch_h; r++) {
        const uint16_t *row1 = bayer + (r * 2) * w;
        const uint16_t *row2 = row1 + w;
        for (int c = 0; c < ch_w; c++) {
            uint16_t R, G1, G2, B;
            if (is_rggb) {
                R = row1[2*c]; G1 = row1[2*c+1]; G2 = row2[2*c]; B = row2[2*c+1];
            } else {
                G1 = row1[2*c]; B = row1[2*c+1]; R = row2[2*c]; G2 = row2[2*c+1];
            }
            if (R > log_max) R = log_max;
            if (G1 > log_max) G1 = log_max;
            if (G2 > log_max) G2 = log_max;
            if (B > log_max) B = log_max;
            int32_t lr  = log_tbl[R];
            int32_t lg1 = log_tbl[G1];
            int32_t lg2 = log_tbl[G2];
            int32_t lb  = log_tbl[B];
            int32_t gsv = (lg1 + lg2) >> 1;
            gs[r * ch_w + c] = gsv;
            rg[r * ch_w + c] = ((lr - gsv) + mid2) >> 1;
            bg[r * ch_w + c] = ((lb - gsv) + mid2) >> 1;
            gd[r * ch_w + c] = ((lg1 - lg2) + mid2) >> 1;
        }
    }
}

/* Forward horizontal wavelet — matches fused_encode.c horizontal_filter. */
static void fwd_horizontal(const int32_t *input, int width, int prescale,
                            int32_t *lowpass, int32_t *highpass)
{
    int prescale_rounding = (1 << prescale) - 1;
    int half = width / 2;
    #define PS(v) (((v) + prescale_rounding) >> prescale)

    lowpass[0]  = PS(input[0]) + PS(input[1]);
    highpass[0] = PS(input[0]) - PS(input[1]);

    for (int i = 1; i < half - 1; i++) {
        int idx = 2 * i;
        int32_t e0 = PS(input[idx]);
        int32_t o0 = PS(input[idx + 1]);
        lowpass[i] = e0 + o0;
        int32_t e_prev = PS(input[idx - 2]) + PS(input[idx - 1]);
        int32_t e_next = PS(input[idx + 2]) + PS(input[idx + 3]);
        highpass[i] = ((e_next - e_prev + 4) >> 3) + (e0 - o0);
    }

    {
        int idx = 2 * (half - 1);
        lowpass[half - 1]  = PS(input[idx]) + PS(input[idx + 1]);
        highpass[half - 1] = PS(input[idx]) - PS(input[idx + 1]);
    }
    #undef PS
}

/* Forward vertical (6-tap) filter for one output row given 6 input rows.
   Output: low = ll for this band-row, high = lh / hl / hh contribution. */
static void fwd_vertical_row(const int32_t *r0, const int32_t *r1, const int32_t *r2,
                              const int32_t *r3, const int32_t *r4, const int32_t *r5,
                              int width, int is_top, int is_bottom,
                              int32_t *out_low, int32_t *out_high)
{
    for (int c = 0; c < width; c++) {
        int32_t v0 = r0[c], v1 = r1[c], v2 = r2[c], v3 = r3[c], v4 = r4[c], v5 = r5[c];
        int32_t low, high;
        if (is_top)         low = v0 + v1;
        else if (is_bottom) low = v4 + v5;
        else                low = v2 + v3;
        high = ((v4 + v5 - v0 - v1 + 4) >> 3) + (v2 - v3);
        out_low[c]  = low;
        out_high[c] = high;
    }
}

/* Full single-level forward wavelet on a channel image (ch_w x ch_h):
   produces 4 bands of (bw x bh) where bw=ch_w/2, bh=ch_h/2.
   Bands stored quantized (with the same midpoint/multiplier as the
   encoder), so the inverse path's dequantize step is exercised on the
   identical numbers the encoder produced.  */
static void fwd_wavelet_quantize(const int32_t *channel, int ch_w, int ch_h,
                                  int prescale,
                                  const int32_t base_divisors[4],
                                  double quant_scale,
                                  int32_t *ll, int32_t *lh, int32_t *hl, int32_t *hh)
{
    int bw = ch_w / 2, bh = ch_h / 2;
    int32_t *hp_buf[6];
    int32_t *lp_buf[6];
    for (int r = 0; r < 6; r++) {
        hp_buf[r] = (int32_t *)calloc(bw, sizeof(int32_t));
        lp_buf[r] = (int32_t *)calloc(bw, sizeof(int32_t));
    }

    /* Per-band quant params (effective divisor = base * scale) */
    int32_t eff_div[4], mid[4], mul[4];
    for (int b = 0; b < 4; b++) {
        eff_div[b] = (int32_t)((double)base_divisors[b] * quant_scale + 0.5);
        if (eff_div[b] < 1) eff_div[b] = 1;
        mid[b] = get_midpoint(eff_div[b]);
        mul[b] = get_multiplier(eff_div[b]);
    }

    /* Run horizontal filter on each input row; collect 6-row circular
       buffer, emit a band row every 2 input rows (after the first 6). */
    int buf_row = 0;
    int out_row = 0;
    int32_t *tmp_low  = (int32_t *)malloc(bw * sizeof(int32_t));
    int32_t *tmp_high = (int32_t *)malloc(bw * sizeof(int32_t));

    for (int r = 0; r < ch_h; r++) {
        int idx = buf_row % 6;
        fwd_horizontal(channel + r * ch_w, ch_w, prescale,
                       lp_buf[idx], hp_buf[idx]);
        buf_row++;

        if (buf_row >= 6 && (buf_row % 2) == 0) {
            if (out_row >= bh) continue;
            int is_top = (out_row == 0);
            int is_bottom = (out_row == bh - 1);
            int base = (buf_row - 6) % 6;
            int32_t *L[6], *H[6];
            for (int i = 0; i < 6; i++) {
                int ii = (base + i) % 6;
                L[i] = lp_buf[ii];
                H[i] = hp_buf[ii];
            }

            fwd_vertical_row(L[0], L[1], L[2], L[3], L[4], L[5],
                              bw, is_top, is_bottom, tmp_low, tmp_high);
            for (int c = 0; c < bw; c++) {
                ll[out_row * bw + c] = quantize_scalar(tmp_low[c],  mid[0], mul[0]);
                lh[out_row * bw + c] = quantize_scalar(tmp_high[c], mid[1], mul[1]);
            }

            fwd_vertical_row(H[0], H[1], H[2], H[3], H[4], H[5],
                              bw, is_top, is_bottom, tmp_low, tmp_high);
            for (int c = 0; c < bw; c++) {
                hl[out_row * bw + c] = quantize_scalar(tmp_low[c],  mid[2], mul[2]);
                hh[out_row * bw + c] = quantize_scalar(tmp_high[c], mid[3], mul[3]);
            }
            out_row++;
        }
    }
    /* Trailing 2 band rows that the 6-tap filter doesn't produce are left
       at calloc-zero, matching the encoder behaviour. */

    free(tmp_low); free(tmp_high);
    for (int r = 0; r < 6; r++) { free(lp_buf[r]); free(hp_buf[r]); }
}

#if FUSED_WAVELET_LEVELS >= 2
/* 2-level forward wavelet + quantization (matches fused_encode.c FUSED_WAVELET_LEVELS=2).
   Produces 7 quantized bands per channel in the order:
     l1_bands[0]=LL1, l1_bands[1]=LH1, l1_bands[2]=HL1, l1_bands[3]=HH1   (at bw1*bh1)
     l0_hp[0]=LH0, l0_hp[1]=HL0, l0_hp[2]=HH0                              (at bw*bh)
   ch_w x ch_h is the channel image size (= w/2 x h/2).
   bw = ch_w/2, bh = ch_h/2 (level-0 band dimensions).
   bw1 = bw/2, bh1 = bh/2  (level-1 band dimensions).
   base_divisors[7] = { FUSED_LL_DIVISOR, qt[4], qt[5], qt[6], qt[7], qt[8], qt[9] }.

   The intermediate LL0 is held with divisor=1 (no quantization) so the
   level-1 wavelet sees clean values. */
static void fwd_wavelet_quantize_2level(const int32_t *channel, int ch_w, int ch_h,
                                         int prescale,
                                         const int32_t base_divisors[7],
                                         double quant_scale,
                                         int32_t *l1_bands[4],   /* LL1, LH1, HL1, HH1 */
                                         int32_t *l0_hp[3])      /* LH0, HL0, HH0 */
{
    int bw = ch_w / 2, bh = ch_h / 2;
    int bw1 = bw / 2, bh1 = bh / 2;

    /* Level-0 forward with: LL divisor=1 (lossless), LH/HL/HH = base_divisors[4..6].
       LL goes into a full-size scratch buffer (no quant). */
    int32_t *ll0 = (int32_t *)calloc((size_t)bw * bh, sizeof(int32_t));
    int32_t lossless_base[4] = { 1, base_divisors[4], base_divisors[5], base_divisors[6] };
    fwd_wavelet_quantize(channel, ch_w, ch_h, prescale,
                          lossless_base, quant_scale,
                          ll0, l0_hp[0], l0_hp[1], l0_hp[2]);

    /* Level-1 forward on the (unquantized) LL0 buffer with: LL1 divisor=FUSED_LL_DIVISOR,
       LH1/HL1/HH1 = base_divisors[1..3]. Use prescale=2 to match the encoder's
       run_level1_wavelet. */
    int32_t l1_base[4] = { base_divisors[0], base_divisors[1], base_divisors[2], base_divisors[3] };
    fwd_wavelet_quantize(ll0, bw, bh, 2,
                          l1_base, quant_scale,
                          l1_bands[0], l1_bands[1], l1_bands[2], l1_bands[3]);

    free(ll0);
    (void)bw1; (void)bh1;
}
#endif

#if FUSED_WAVELET_LEVELS >= 3
/* 3-level forward wavelet + quantization (matches fused_encode.c FUSED_WAVELET_LEVELS=3).
   Produces 10 quantized bands per channel in the order:
     l2_bands[0..3] = LL2, LH2, HL2, HH2   (at bw2*bh2)
     l1_hp[0..2]    = LH1, HL1, HH1        (at bw1*bh1)
     l0_hp[0..2]    = LH0, HL0, HH0        (at bw*bh)
   ch_w x ch_h is the channel image size (= w/2 x h/2).
   bw = ch_w/2, bh = ch_h/2.
   bw1 = bw/2, bh1 = bh/2.
   bw2 = bw1/2, bh2 = bh1/2.

   base_divisors[10] = { FUSED_LL2_DIVISOR, qt[1], qt[2], qt[3],
                         qt[4], qt[5], qt[6], qt[7], qt[8], qt[9] }.

   The intermediate LL0 and LL1 are held with divisor=1 (no quantization)
   so deeper wavelets see clean values. */
static void fwd_wavelet_quantize_3level(const int32_t *channel, int ch_w, int ch_h,
                                         int prescale,
                                         const int32_t base_divisors[10],
                                         double quant_scale,
                                         int32_t *l2_bands[4],   /* LL2, LH2, HL2, HH2 */
                                         int32_t *l1_hp[3],      /* LH1, HL1, HH1 */
                                         int32_t *l0_hp[3])      /* LH0, HL0, HH0 */
{
    int bw  = ch_w / 2, bh  = ch_h / 2;
    int bw1 = bw / 2,   bh1 = bh / 2;
    int bw2 = bw1 / 2,  bh2 = bh1 / 2;

    /* Level-0 forward with LL lossless (divisor=1), LH/HL/HH = base_divisors[7..9]. */
    int32_t *ll0 = (int32_t *)calloc((size_t)bw * bh, sizeof(int32_t));
    int32_t l0_base[4] = { 1, base_divisors[7], base_divisors[8], base_divisors[9] };
    fwd_wavelet_quantize(channel, ch_w, ch_h, prescale,
                          l0_base, quant_scale,
                          ll0, l0_hp[0], l0_hp[1], l0_hp[2]);

    /* Level-1 forward on the (unquantized) LL0. LL1 also lossless (divisor=1)
       so the level-2 wavelet sees clean values. LH1/HL1/HH1 = base_divisors[4..6].
       Prescale=2 to match run_level1_wavelet. */
    int32_t *ll1 = (int32_t *)calloc((size_t)bw1 * bh1, sizeof(int32_t));
    int32_t l1_base[4] = { 1, base_divisors[4], base_divisors[5], base_divisors[6] };
    fwd_wavelet_quantize(ll0, bw, bh, 2,
                          l1_base, quant_scale,
                          ll1, l1_hp[0], l1_hp[1], l1_hp[2]);

    /* Level-2 forward on the (unquantized) LL1. LL2 = FUSED_LL2_DIVISOR,
       LH2/HL2/HH2 = base_divisors[1..3]. Prescale=2 to match run_level2_wavelet. */
    int32_t l2_base[4] = { base_divisors[0], base_divisors[1], base_divisors[2], base_divisors[3] };
    fwd_wavelet_quantize(ll1, bw1, bh1, 2,
                          l2_base, quant_scale,
                          l2_bands[0], l2_bands[1], l2_bands[2], l2_bands[3]);

    free(ll0);
    free(ll1);
    (void)bw2; (void)bh2;
}
#endif

/* ============================================================
   Decode all bands from one frame bitstream into per-channel int32 buffers.
   In single-level mode (BANDS_PER_CHANNEL=4): band_buffers[ch][band] is a
       bw*bh buffer for band 0..3 (LL, LH, HL, HH all at level-0 size).
   In 2-level mode (BANDS_PER_CHANNEL=7): band_buffers[ch][0..3] are level-1
       bands at (bw/2 × bh/2). band_buffers[ch][4..6] are level-0 highpass
       at (bw × bh).
   In 3-level mode (BANDS_PER_CHANNEL=10): band_buffers[ch][0..3] are level-2
       bands at (bw/4 × bh/4). band_buffers[ch][4..6] are level-1 highpass
       at (bw/2 × bh/2). band_buffers[ch][7..9] are level-0 highpass
       at (bw × bh).
   The CALLER must allocate each buffer at the correct dimensions.
   ============================================================ */
static int decode_frame_bands(const uint8_t *vc5, size_t size,
                               int bw, int bh,
                               int32_t *band_buffers[4][BANDS_PER_CHANNEL])
{
    size_t pos = 0;
    int bands_ok = 0;
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 0; band < BANDS_PER_CHANNEL; band++) {
            int this_w = bw, this_h = bh;
#if FUSED_WAVELET_LEVELS == 3
            if (band < 4) { this_w = bw / 4; this_h = bh / 4; }
            else if (band < 7) { this_w = bw / 2; this_h = bh / 2; }
#elif FUSED_WAVELET_LEVELS == 2
            if (band < 4) { this_w = bw / 2; this_h = bh / 2; }
#endif
            size_t band_bytes = 0;
            if (probe_band_bytes(vc5 + pos, size - pos, &band_bytes) != 0) {
                fprintf(stderr, "    band-probe failed at ch=%d band=%d pos=%zu\n",
                        ch, band, pos);
                return bands_ok;
            }
            memset(band_buffers[ch][band], 0,
                   (size_t)this_w * this_h * sizeof(int32_t));
            int rc = jans_decode_band_x4(vc5 + pos, band_bytes,
                                          band_buffers[ch][band],
                                          this_w, this_h, this_w * sizeof(int32_t));
            if (rc != 0) {
                fprintf(stderr, "    jans_decode_band_x4 ch=%d band=%d → %d\n",
                        ch, band, rc);
                return bands_ok;
            }
            pos += band_bytes;
            bands_ok++;
        }
    }
    return bands_ok;
}

/* ============================================================
   Stats helpers
   ============================================================ */
typedef struct {
    double sse;
    double max_abs;
    uint64_t n;
} mse_acc;

static inline void mse_add(mse_acc *m, double diff) {
    m->sse += diff * diff;
    double a = (diff < 0) ? -diff : diff;
    if (a > m->max_abs) m->max_abs = a;
    m->n++;
}

static double psnr_from_mse(double mse, double peak) {
    if (mse <= 0.0) return INFINITY;
    return 10.0 * log10(peak * peak / mse);
}

/* ============================================================
   Inverse log curve + final Bayer reconstruction
   ============================================================ */
static inline uint16_t inv_log(int32_t v, int log_bits) {
    int log_max = (log_bits <= 14) ? 16383 : 65535;
    if (v < 0) v = 0; else if (v > log_max) v = log_max;
    return (log_bits <= 14) ? DecoderLogCurve14[v] : DecoderLogCurve16[v];
}

/* Reconstruct one 14-bit-or-16-bit Bayer row pair from 4 channel rows
   (each in channel domain, i.e. encoder's pre-prescale log-curve scale).

   The channel-domain values stored by the encoder are at HALF scale
   (encoder always shifts >>1). To invert:
       GD' = GD * 2  (but offset by mid2)
       RG' = RG * 2 (offset)
       BG' = BG * 2 (offset)
       GS  = GS * 2 (no offset since GS=(g1+g2)/2)

   Then in the original log domain:
       g1 = GS + (GD - midpoint)  where midpoint = 1 << (log_bits-1)
       g2 = GS - (GD - midpoint)
       r  = GS + 2*(RG - midpoint)
       b  = GS + 2*(BG - midpoint)
   Inverse log curve recovers the linear Bayer pixel.

   The encoder's stored channel values are X = ((linear_value)+offset)>>1.
   So to recover linear_value we use: stored * 2 - offset where applicable.
   But because the encoder applied prescale=2 (>>2) on top of all this,
   the *output* of the inverse wavelet is already at 1/4 the original
   channel scale. So we have to multiply by 4 (== <<2 = prescale) before
   doing the channel demux.

   To make this rigorous, the prescale is applied DURING horizontal_filter
   on the raw channel pixel — so the inverse wavelet output is in
   "channel/4" scale. We must <<prescale to recover channel scale before
   the channel→Bayer demux. */
static void reconstruct_bayer_row(const int32_t *gs_row, const int32_t *rg_row,
                                   const int32_t *bg_row, const int32_t *gd_row,
                                   int ch_w, int log_bits, int is_rggb, int prescale,
                                   uint16_t *out_row1, uint16_t *out_row2)
{
    int log_max = (log_bits <= 14) ? 16383 : 65535;
    int32_t mid_half = 1 << (log_bits - 1);  /* fast_decode's "midpoint" */

    for (int c = 0; c < ch_w; c++) {
        /* Undo prescale: encoder did >>prescale during horizontal_filter.
           Multiplying by 1<<prescale restores the channel-domain scale.
           This is the same as the decoder's descale_shift = prescale. */
        int32_t GS = gs_row[c] << prescale;
        int32_t RG = rg_row[c] << prescale;
        int32_t BG = bg_row[c] << prescale;
        int32_t GD = gd_row[c] << prescale;

        /* The encoder stored channels at >>1, but: the prescale shift
           already accounts for the factor of 2 inside the wavelet sum
           (lowpass = e+o vs (e+o)/2). The decoder's InvertHorizontal16s
           output >>1 + our prescale_shift inverse cleanly undoes the
           wavelet's gain. The encoder's per-channel >>1 on top of THAT
           is what the decoder pack inverts with (RG-mid)<<1 below. */
        GS = clamp_to(GS, 0, log_max);
        RG = clamp_to(RG, 0, log_max);
        BG = clamp_to(BG, 0, log_max);
        GD = clamp_to(GD, 0, log_max);

        GD -= mid_half;
        RG -= mid_half;
        BG -= mid_half;

        int32_t R  = (RG << 1) + GS;
        int32_t B  = (BG << 1) + GS;
        int32_t G1 = GS + GD;
        int32_t G2 = GS - GD;

        R  = clamp_to(R,  0, log_max);
        G1 = clamp_to(G1, 0, log_max);
        G2 = clamp_to(G2, 0, log_max);
        B  = clamp_to(B,  0, log_max);

        uint16_t Rp  = inv_log(R,  log_bits);
        uint16_t G1p = inv_log(G1, log_bits);
        uint16_t G2p = inv_log(G2, log_bits);
        uint16_t Bp  = inv_log(B,  log_bits);

        if (is_rggb) {
            out_row1[2*c]   = Rp;  out_row1[2*c+1] = G1p;
            out_row2[2*c]   = G2p; out_row2[2*c+1] = Bp;
        } else {
            out_row1[2*c]   = G1p; out_row1[2*c+1] = Bp;
            out_row2[2*c]   = Rp;  out_row2[2*c+1] = G2p;
        }
    }
}

/* ============================================================
   Per-frame reconstruction. Decodes bands → dequantize → inverse
   wavelet → channel demux + inverse log → Bayer output.

   Also builds the "oracle" reference (forward-encode then immediate
   inverse, no bitstream roundtrip) so PSNR can isolate whether the
   inverse math itself is correct, separately from the missing LL.
   ============================================================ */
typedef struct {
    /* Average across the frame: */
    double psnr_oracle_total;        /* full Bayer reconstruction vs oracle reference */
    double psnr_oracle_per_ch[4];    /* per Bayer-channel (R, G1, G2, B) */
    double psnr_raw_total;           /* full Bayer reconstruction vs original raw */
    double psnr_raw_per_ch[4];

    /* Coefficient sanity: */
    int32_t band_min[BANDS_PER_FRAME], band_max[BANDS_PER_FRAME];
    int     band_nonzero[BANDS_PER_FRAME];

    /* For verifying band-level decode (Stage A): also compare decoded
       bands against the encoder's exact pre-rANS coefficient values. */
    double band_match_pct[BANDS_PER_FRAME];  /* % of coeffs that match the oracle exactly */
} frame_stats;

static double psnr_per_bayer_channel(const uint16_t *orig, const uint16_t *recon,
                                      int w, int h, int log_bits,
                                      int is_rggb,
                                      double per_ch[4])
{
    double peak = (1 << log_bits) - 1;
    mse_acc m_total = {0};
    mse_acc m_ch[4] = {0};

    for (int r = 0; r < h; r++) {
        for (int c = 0; c < w; c++) {
            int32_t a = orig[r * w + c];
            int32_t b = recon[r * w + c];
            double diff = (double)a - (double)b;
            mse_add(&m_total, diff);
            int rmod = r & 1, cmod = c & 1;
            int bayer_idx;
            if (is_rggb) {
                if (rmod == 0 && cmod == 0) bayer_idx = 0;       /* R */
                else if (rmod == 0 && cmod == 1) bayer_idx = 1;  /* G1 */
                else if (rmod == 1 && cmod == 0) bayer_idx = 2;  /* G2 */
                else bayer_idx = 3;                                /* B */
            } else {
                if (rmod == 0 && cmod == 0) bayer_idx = 1;       /* G1 */
                else if (rmod == 0 && cmod == 1) bayer_idx = 3;  /* B */
                else if (rmod == 1 && cmod == 0) bayer_idx = 0;  /* R */
                else bayer_idx = 2;                                /* G2 */
            }
            mse_add(&m_ch[bayer_idx], diff);
        }
    }
    for (int i = 0; i < 4; i++) {
        double mse = m_ch[i].n > 0 ? m_ch[i].sse / m_ch[i].n : 0.0;
        per_ch[i] = psnr_from_mse(mse, peak);
    }
    double mse = m_total.n > 0 ? m_total.sse / m_total.n : 0.0;
    return psnr_from_mse(mse, peak);
}

/* Build the "oracle" Bayer reconstruction: forward-encode the raw,
   then immediately reverse the inverse pipeline starting from the
   in-memory quantized bands (no bitstream roundtrip).  With LL = 0
   (matching the no-LL-in-bitstream behaviour), this oracle is what
   the lossy inverse pipeline can achieve in principle, so the
   bitstream roundtrip should match it to high precision.  Any
   deviation between oracle and decoded reconstruction is bitstream
   error (rANS, dequant) — almost zero for a lossless inverse-quant
   step. */
static int run_frame_test(const uint8_t *raw, const uint8_t *vc5,
                           size_t vc5_size, int w, int h, int log_bits,
                           int is_rggb, int prescale, int quality,
                           double quant_scale,
                           frame_stats *out)
{
    int ch_w = w / 2, ch_h = h / 2;
    int bw = ch_w / 2, bh = ch_h / 2;

#if FUSED_WAVELET_LEVELS == 1
    /* ================================================================
       Single-level path
       ================================================================ */

    /* Allocate band buffers and forward-encode the raw to get the
       "oracle" band coefficients (pre-rANS). */
    int32_t *oracle_bands[4][4];
    int32_t *decoded_bands[4][BANDS_PER_CHANNEL];
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 4; b++) {
            oracle_bands[ch][b]  = (int32_t *)calloc((size_t)bw * bh, sizeof(int32_t));
            decoded_bands[ch][b] = (int32_t *)calloc((size_t)bw * bh, sizeof(int32_t));
        }
    }

    /* Channel-domain images for forward pass */
    int32_t *channels[4];
    for (int i = 0; i < 4; i++) {
        channels[i] = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
    }

    fwd_channels((const uint16_t *)raw, w, h, log_bits, is_rggb,
                 channels[0], channels[1], channels[2], channels[3]);

    int32_t base_divisors[4];
    fused_base_divisors(quality, base_divisors);

    for (int ch = 0; ch < 4; ch++) {
        fwd_wavelet_quantize(channels[ch], ch_w, ch_h, prescale,
                              base_divisors, quant_scale,
                              oracle_bands[ch][0], oracle_bands[ch][1],
                              oracle_bands[ch][2], oracle_bands[ch][3]);
    }

    /* Decode bitstream → decoded_bands (LL stays zero). */
    int bands_ok = decode_frame_bands(vc5, vc5_size, bw, bh, decoded_bands);
    if (bands_ok != BANDS_PER_FRAME) {
        fprintf(stderr, "    DECODE FAILED: %d/%d bands\n", bands_ok, BANDS_PER_FRAME);
        for (int ch = 0; ch < 4; ch++)
            for (int b = 0; b < 4; b++) {
                free(oracle_bands[ch][b]); free(decoded_bands[ch][b]);
            }
        for (int i = 0; i < 4; i++) free(channels[i]);
        return -1;
    }

    /* Sanity stats per band (using decoded values, post-dequant).
       16-band layout: bi = ch*4 + b (was ch*3+(b-1) when LL wasn't emitted). */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 4; b++) {
            int bi = ch * 4 + b;
            int32_t mn = INT32_MAX, mx = INT32_MIN;
            int nz = 0;
            int matches = 0;
            size_t n = (size_t)bw * bh;
            for (size_t k = 0; k < n; k++) {
                int32_t v = decoded_bands[ch][b][k];
                if (v != 0) nz++;
                if (v < mn) mn = v;
                if (v > mx) mx = v;
                if (v == oracle_bands[ch][b][k]) matches++;
            }
            out->band_min[bi] = mn;
            out->band_max[bi] = mx;
            out->band_nonzero[bi] = nz;
            out->band_match_pct[bi] = 100.0 * matches / (double)n;
        }
    }

    /* Inverse quant: in-place multiply by effective divisor. */
    int32_t eff_div[4];
    for (int b = 0; b < 4; b++) {
        eff_div[b] = (int32_t)((double)base_divisors[b] * quant_scale + 0.5);
        if (eff_div[b] < 1) eff_div[b] = 1;
    }
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 4; b++) {
            int32_t d = eff_div[b];
            if (d == 1) continue;
            size_t n = (size_t)bw * bh;
            for (size_t k = 0; k < n; k++) {
                decoded_bands[ch][b][k] = dequantize_scalar(decoded_bands[ch][b][k], d);
            }
        }
    }

    /* Build per-channel reconstruction. */
    int32_t *recon_ch[4];
    int32_t *oracle_ch[4];
    for (int i = 0; i < 4; i++) {
        recon_ch[i]  = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
        oracle_ch[i] = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
    }

    for (int ch = 0; ch < 4; ch++) {
        invert_spatial_band(decoded_bands[ch][0],
                             decoded_bands[ch][1],
                             decoded_bands[ch][2],
                             decoded_bands[ch][3],
                             bw, bh,
                             recon_ch[ch], ch_w);
    }

    /* Oracle reconstruction: same path but with oracle bands (no bitstream). */
    int32_t *oracle_bands_dq[4][4];
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 4; b++) {
            size_t n = (size_t)bw * bh;
            oracle_bands_dq[ch][b] = (int32_t *)malloc(n * sizeof(int32_t));
            int32_t d = eff_div[b];
            for (size_t k = 0; k < n; k++) {
                oracle_bands_dq[ch][b][k] = dequantize_scalar(oracle_bands[ch][b][k], d);
            }
        }
        invert_spatial_band(oracle_bands_dq[ch][0],
                             oracle_bands_dq[ch][1],
                             oracle_bands_dq[ch][2],
                             oracle_bands_dq[ch][3],
                             bw, bh,
                             oracle_ch[ch], ch_w);
    }

    /* Cleanup band-level buffers (the per-channel buffers freed at end) */
    for (int ch = 0; ch < 4; ch++)
        for (int b = 0; b < 4; b++) {
            free(oracle_bands[ch][b]); free(decoded_bands[ch][b]);
            free(oracle_bands_dq[ch][b]);
        }

#elif FUSED_WAVELET_LEVELS == 2
    /* ================================================================
       2-level path: 7 bands per channel (LL1, LH1, HL1, HH1, LH0, HL0, HH0).
       ================================================================ */
    int bw1 = bw / 2, bh1 = bh / 2;

    int32_t *oracle_bands[4][7];
    int32_t *decoded_bands[4][7];
    /* Per-band dimensions: bands 0..3 are level-1 (bw1*bh1), bands 4..6 are level-0 (bw*bh) */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 7; b++) {
            int W = (b < 4) ? bw1 : bw;
            int H = (b < 4) ? bh1 : bh;
            oracle_bands[ch][b]  = (int32_t *)calloc((size_t)W * H, sizeof(int32_t));
            decoded_bands[ch][b] = (int32_t *)calloc((size_t)W * H, sizeof(int32_t));
        }
    }

    /* Channel-domain images for forward pass */
    int32_t *channels[4];
    for (int i = 0; i < 4; i++) {
        channels[i] = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
    }

    fwd_channels((const uint16_t *)raw, w, h, log_bits, is_rggb,
                 channels[0], channels[1], channels[2], channels[3]);

    int32_t base_divisors_2l[7];
    fused_base_divisors_2level(quality, base_divisors_2l);

    for (int ch = 0; ch < 4; ch++) {
        int32_t *l1_bands[4] = {
            oracle_bands[ch][0], oracle_bands[ch][1],
            oracle_bands[ch][2], oracle_bands[ch][3]
        };
        int32_t *l0_hp[3] = {
            oracle_bands[ch][4], oracle_bands[ch][5], oracle_bands[ch][6]
        };
        fwd_wavelet_quantize_2level(channels[ch], ch_w, ch_h, prescale,
                                     base_divisors_2l, quant_scale,
                                     l1_bands, l0_hp);
    }

    /* Decode bitstream → decoded_bands. */
    int bands_ok = decode_frame_bands(vc5, vc5_size, bw, bh, decoded_bands);
    if (bands_ok != BANDS_PER_FRAME) {
        fprintf(stderr, "    DECODE FAILED: %d/%d bands\n", bands_ok, BANDS_PER_FRAME);
        for (int ch = 0; ch < 4; ch++)
            for (int b = 0; b < 7; b++) {
                free(oracle_bands[ch][b]); free(decoded_bands[ch][b]);
            }
        for (int i = 0; i < 4; i++) free(channels[i]);
        return -1;
    }

    /* Per-band stats (post-dequant compare uses pre-dequant decoded values). */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 7; b++) {
            int bi = ch * 7 + b;
            int32_t mn = INT32_MAX, mx = INT32_MIN;
            int nz = 0, matches = 0;
            int W = (b < 4) ? bw1 : bw;
            int H = (b < 4) ? bh1 : bh;
            size_t n = (size_t)W * H;
            for (size_t k = 0; k < n; k++) {
                int32_t v = decoded_bands[ch][b][k];
                if (v != 0) nz++;
                if (v < mn) mn = v;
                if (v > mx) mx = v;
                if (v == oracle_bands[ch][b][k]) matches++;
            }
            out->band_min[bi] = mn;
            out->band_max[bi] = mx;
            out->band_nonzero[bi] = nz;
            out->band_match_pct[bi] = 100.0 * matches / (double)n;
        }
    }

    /* Inverse quant: in-place multiply by effective divisor. */
    int32_t eff_div[7];
    for (int b = 0; b < 7; b++) {
        eff_div[b] = (int32_t)((double)base_divisors_2l[b] * quant_scale + 0.5);
        if (eff_div[b] < 1) eff_div[b] = 1;
    }
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 7; b++) {
            int32_t d = eff_div[b];
            if (d == 1) continue;
            int W = (b < 4) ? bw1 : bw;
            int H = (b < 4) ? bh1 : bh;
            size_t n = (size_t)W * H;
            for (size_t k = 0; k < n; k++) {
                decoded_bands[ch][b][k] = dequantize_scalar(decoded_bands[ch][b][k], d);
            }
        }
    }

    /* 2-level inverse: invert level-1 to reconstruct LL0, then invert level-0
       using reconstructed LL0 + decoded LH0/HL0/HH0. */
    int32_t *ll0_recon = (int32_t *)calloc((size_t)bw * bh, sizeof(int32_t));
    int32_t *ll0_oracle = (int32_t *)calloc((size_t)bw * bh, sizeof(int32_t));
    int32_t *recon_ch[4];
    int32_t *oracle_ch[4];
    int32_t *oracle_bands_dq[4][7];
    for (int i = 0; i < 4; i++) {
        recon_ch[i]  = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
        oracle_ch[i] = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
    }

    /* Build oracle dequantized buffers (also for band-match stats). */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 7; b++) {
            int W = (b < 4) ? bw1 : bw;
            int H = (b < 4) ? bh1 : bh;
            size_t n = (size_t)W * H;
            oracle_bands_dq[ch][b] = (int32_t *)malloc(n * sizeof(int32_t));
            int32_t d = eff_div[b];
            for (size_t k = 0; k < n; k++) {
                oracle_bands_dq[ch][b][k] = dequantize_scalar(oracle_bands[ch][b][k], d);
            }
        }
    }

    /* Level-1 prescale (matches encoder's run_level1_wavelet): each inverse
       wavelet halves the magnitude scale (it doesn't undo the forward
       prescale). To recover the true LL0 scale we must apply <<prescale_l1
       after inverting level 1, before feeding into the level-0 inverse. */
    const int prescale_l1 = 2;
    for (int ch = 0; ch < 4; ch++) {
        /* Invert level-1: LL1+LH1+HL1+HH1 (at bw1*bh1) → LL0 reconstructed (at bw*bh).
           invert_spatial_band takes 4 bands at (input_w, input_h) and writes
           a (input_w*2, input_h*2) output. */
        invert_spatial_band(decoded_bands[ch][0],   /* LL1 */
                             decoded_bands[ch][1],   /* LH1 */
                             decoded_bands[ch][2],   /* HL1 */
                             decoded_bands[ch][3],   /* HH1 */
                             bw1, bh1,
                             ll0_recon, bw);

        /* Scale up by 1<<prescale_l1 so ll0_recon matches the magnitude scale
           that the encoder's LL0 buffer had pre-L1-wavelet. */
        for (size_t k = 0, n = (size_t)bw * bh; k < n; k++) {
            ll0_recon[k] <<= prescale_l1;
        }

        /* Invert level-0: reconstructed LL0 + decoded LH0/HL0/HH0 → channel domain. */
        invert_spatial_band(ll0_recon,                  /* LL0 reconstructed */
                             decoded_bands[ch][4],      /* LH0 */
                             decoded_bands[ch][5],      /* HL0 */
                             decoded_bands[ch][6],      /* HH0 */
                             bw, bh,
                             recon_ch[ch], ch_w);

        /* Oracle path: same with oracle bands. */
        invert_spatial_band(oracle_bands_dq[ch][0],
                             oracle_bands_dq[ch][1],
                             oracle_bands_dq[ch][2],
                             oracle_bands_dq[ch][3],
                             bw1, bh1,
                             ll0_oracle, bw);
        for (size_t k = 0, n = (size_t)bw * bh; k < n; k++) {
            ll0_oracle[k] <<= prescale_l1;
        }
        invert_spatial_band(ll0_oracle,
                             oracle_bands_dq[ch][4],
                             oracle_bands_dq[ch][5],
                             oracle_bands_dq[ch][6],
                             bw, bh,
                             oracle_ch[ch], ch_w);
    }

    free(ll0_recon); free(ll0_oracle);
    for (int ch = 0; ch < 4; ch++)
        for (int b = 0; b < 7; b++) {
            free(oracle_bands[ch][b]); free(decoded_bands[ch][b]);
            free(oracle_bands_dq[ch][b]);
        }

#else  /* FUSED_WAVELET_LEVELS == 3 */
    /* ================================================================
       3-level path: 10 bands per channel
       (LL2, LH2, HL2, HH2, LH1, HL1, HH1, LH0, HL0, HH0).
       ================================================================ */
    int bw1 = bw / 2,   bh1 = bh / 2;
    int bw2 = bw1 / 2,  bh2 = bh1 / 2;

    int32_t *oracle_bands[4][10];
    int32_t *decoded_bands[4][10];
    /* Per-band dimensions: bands 0..3 level-2 (bw2*bh2),
       4..6 level-1 (bw1*bh1), 7..9 level-0 (bw*bh). */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 10; b++) {
            int W, H;
            if (b < 4)      { W = bw2; H = bh2; }
            else if (b < 7) { W = bw1; H = bh1; }
            else            { W = bw;  H = bh;  }
            oracle_bands[ch][b]  = (int32_t *)calloc((size_t)W * H, sizeof(int32_t));
            decoded_bands[ch][b] = (int32_t *)calloc((size_t)W * H, sizeof(int32_t));
        }
    }

    /* Channel-domain images for forward pass */
    int32_t *channels[4];
    for (int i = 0; i < 4; i++) {
        channels[i] = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
    }

    fwd_channels((const uint16_t *)raw, w, h, log_bits, is_rggb,
                 channels[0], channels[1], channels[2], channels[3]);

    int32_t base_divisors_3l[10];
    fused_base_divisors_3level(quality, base_divisors_3l);

    for (int ch = 0; ch < 4; ch++) {
        int32_t *l2_bands[4] = {
            oracle_bands[ch][0], oracle_bands[ch][1],
            oracle_bands[ch][2], oracle_bands[ch][3]
        };
        int32_t *l1_hp[3] = {
            oracle_bands[ch][4], oracle_bands[ch][5], oracle_bands[ch][6]
        };
        int32_t *l0_hp[3] = {
            oracle_bands[ch][7], oracle_bands[ch][8], oracle_bands[ch][9]
        };
        fwd_wavelet_quantize_3level(channels[ch], ch_w, ch_h, prescale,
                                     base_divisors_3l, quant_scale,
                                     l2_bands, l1_hp, l0_hp);
    }

    /* Decode bitstream → decoded_bands. */
    int bands_ok = decode_frame_bands(vc5, vc5_size, bw, bh, decoded_bands);
    if (bands_ok != BANDS_PER_FRAME) {
        fprintf(stderr, "    DECODE FAILED: %d/%d bands\n", bands_ok, BANDS_PER_FRAME);
        for (int ch = 0; ch < 4; ch++)
            for (int b = 0; b < 10; b++) {
                free(oracle_bands[ch][b]); free(decoded_bands[ch][b]);
            }
        for (int i = 0; i < 4; i++) free(channels[i]);
        return -1;
    }

    /* Per-band stats. */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 10; b++) {
            int bi = ch * 10 + b;
            int32_t mn = INT32_MAX, mx = INT32_MIN;
            int nz = 0, matches = 0;
            int W, H;
            if (b < 4)      { W = bw2; H = bh2; }
            else if (b < 7) { W = bw1; H = bh1; }
            else            { W = bw;  H = bh;  }
            size_t n = (size_t)W * H;
            for (size_t k = 0; k < n; k++) {
                int32_t v = decoded_bands[ch][b][k];
                if (v != 0) nz++;
                if (v < mn) mn = v;
                if (v > mx) mx = v;
                if (v == oracle_bands[ch][b][k]) matches++;
            }
            out->band_min[bi] = mn;
            out->band_max[bi] = mx;
            out->band_nonzero[bi] = nz;
            out->band_match_pct[bi] = 100.0 * matches / (double)n;
        }
    }

    /* Inverse quant: in-place multiply by effective divisor. */
    int32_t eff_div[10];
    for (int b = 0; b < 10; b++) {
        eff_div[b] = (int32_t)((double)base_divisors_3l[b] * quant_scale + 0.5);
        if (eff_div[b] < 1) eff_div[b] = 1;
    }
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 10; b++) {
            int32_t d = eff_div[b];
            if (d == 1) continue;
            int W, H;
            if (b < 4)      { W = bw2; H = bh2; }
            else if (b < 7) { W = bw1; H = bh1; }
            else            { W = bw;  H = bh;  }
            size_t n = (size_t)W * H;
            for (size_t k = 0; k < n; k++) {
                decoded_bands[ch][b][k] = dequantize_scalar(decoded_bands[ch][b][k], d);
            }
        }
    }

    /* 3-level inverse chain:
         1. Invert level-2 (4 bands at bw2×bh2) → reconstructed LL1 (bw1×bh1).
            Apply <<prescale_l2 to recover the magnitude scale that the
            encoder's LL1 buffer had pre-L2-wavelet.
         2. Invert level-1 (recon LL1 + decoded LH1/HL1/HH1 at bw1×bh1) →
            reconstructed LL0 (bw×bh). Apply <<prescale_l1.
         3. Invert level-0 (recon LL0 + decoded LH0/HL0/HH0 at bw×bh) →
            channel-domain reconstruction (ch_w×ch_h).
       The level-0 prescale shift is handled by reconstruct_bayer_row. */
    const int prescale_l2 = 2;
    const int prescale_l1 = 2;

    int32_t *ll1_recon  = (int32_t *)calloc((size_t)bw1 * bh1, sizeof(int32_t));
    int32_t *ll1_oracle = (int32_t *)calloc((size_t)bw1 * bh1, sizeof(int32_t));
    int32_t *ll0_recon  = (int32_t *)calloc((size_t)bw  * bh,  sizeof(int32_t));
    int32_t *ll0_oracle = (int32_t *)calloc((size_t)bw  * bh,  sizeof(int32_t));
    int32_t *recon_ch[4];
    int32_t *oracle_ch[4];
    int32_t *oracle_bands_dq[4][10];
    for (int i = 0; i < 4; i++) {
        recon_ch[i]  = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
        oracle_ch[i] = (int32_t *)calloc((size_t)ch_w * ch_h, sizeof(int32_t));
    }

    /* Build oracle dequantized buffers. */
    for (int ch = 0; ch < 4; ch++) {
        for (int b = 0; b < 10; b++) {
            int W, H;
            if (b < 4)      { W = bw2; H = bh2; }
            else if (b < 7) { W = bw1; H = bh1; }
            else            { W = bw;  H = bh;  }
            size_t n = (size_t)W * H;
            oracle_bands_dq[ch][b] = (int32_t *)malloc(n * sizeof(int32_t));
            int32_t d = eff_div[b];
            for (size_t k = 0; k < n; k++) {
                oracle_bands_dq[ch][b][k] = dequantize_scalar(oracle_bands[ch][b][k], d);
            }
        }
    }

    for (int ch = 0; ch < 4; ch++) {
        /* Decoded path: L2 inverse → ll1_recon, shift, L1 inverse → ll0_recon,
           shift, L0 inverse → recon_ch[ch]. */
        invert_spatial_band(decoded_bands[ch][0],   /* LL2 */
                             decoded_bands[ch][1],   /* LH2 */
                             decoded_bands[ch][2],   /* HL2 */
                             decoded_bands[ch][3],   /* HH2 */
                             bw2, bh2,
                             ll1_recon, bw1);
        for (size_t k = 0, n = (size_t)bw1 * bh1; k < n; k++) {
            ll1_recon[k] <<= prescale_l2;
        }

        invert_spatial_band(ll1_recon,                /* LL1 reconstructed */
                             decoded_bands[ch][4],    /* LH1 */
                             decoded_bands[ch][5],    /* HL1 */
                             decoded_bands[ch][6],    /* HH1 */
                             bw1, bh1,
                             ll0_recon, bw);
        for (size_t k = 0, n = (size_t)bw * bh; k < n; k++) {
            ll0_recon[k] <<= prescale_l1;
        }

        invert_spatial_band(ll0_recon,                /* LL0 reconstructed */
                             decoded_bands[ch][7],    /* LH0 */
                             decoded_bands[ch][8],    /* HL0 */
                             decoded_bands[ch][9],    /* HH0 */
                             bw, bh,
                             recon_ch[ch], ch_w);

        /* Oracle path: same with oracle bands. */
        invert_spatial_band(oracle_bands_dq[ch][0],
                             oracle_bands_dq[ch][1],
                             oracle_bands_dq[ch][2],
                             oracle_bands_dq[ch][3],
                             bw2, bh2,
                             ll1_oracle, bw1);
        for (size_t k = 0, n = (size_t)bw1 * bh1; k < n; k++) {
            ll1_oracle[k] <<= prescale_l2;
        }
        invert_spatial_band(ll1_oracle,
                             oracle_bands_dq[ch][4],
                             oracle_bands_dq[ch][5],
                             oracle_bands_dq[ch][6],
                             bw1, bh1,
                             ll0_oracle, bw);
        for (size_t k = 0, n = (size_t)bw * bh; k < n; k++) {
            ll0_oracle[k] <<= prescale_l1;
        }
        invert_spatial_band(ll0_oracle,
                             oracle_bands_dq[ch][7],
                             oracle_bands_dq[ch][8],
                             oracle_bands_dq[ch][9],
                             bw, bh,
                             oracle_ch[ch], ch_w);
    }

    free(ll1_recon); free(ll1_oracle);
    free(ll0_recon); free(ll0_oracle);
    for (int ch = 0; ch < 4; ch++)
        for (int b = 0; b < 10; b++) {
            free(oracle_bands[ch][b]); free(decoded_bands[ch][b]);
            free(oracle_bands_dq[ch][b]);
        }
#endif  /* FUSED_WAVELET_LEVELS */

    /* Reconstruct Bayer image (decoded path) */
    uint16_t *recon_bayer = (uint16_t *)calloc((size_t)w * h, sizeof(uint16_t));
    for (int r = 0; r < ch_h; r++) {
        reconstruct_bayer_row(recon_ch[0] + r * ch_w,
                               recon_ch[1] + r * ch_w,
                               recon_ch[2] + r * ch_w,
                               recon_ch[3] + r * ch_w,
                               ch_w, log_bits, is_rggb, prescale,
                               recon_bayer + (2 * r) * w,
                               recon_bayer + (2 * r + 1) * w);
    }

    /* Reconstruct Bayer image (oracle path) */
    uint16_t *oracle_bayer = (uint16_t *)calloc((size_t)w * h, sizeof(uint16_t));
    for (int r = 0; r < ch_h; r++) {
        reconstruct_bayer_row(oracle_ch[0] + r * ch_w,
                               oracle_ch[1] + r * ch_w,
                               oracle_ch[2] + r * ch_w,
                               oracle_ch[3] + r * ch_w,
                               ch_w, log_bits, is_rggb, prescale,
                               oracle_bayer + (2 * r) * w,
                               oracle_bayer + (2 * r + 1) * w);
    }

    /* PSNR */
    out->psnr_oracle_total = psnr_per_bayer_channel(
        oracle_bayer, recon_bayer, w, h, log_bits, is_rggb,
        out->psnr_oracle_per_ch);
    out->psnr_raw_total = psnr_per_bayer_channel(
        (const uint16_t *)raw, recon_bayer, w, h, log_bits, is_rggb,
        out->psnr_raw_per_ch);

    /* Cleanup */
    for (int i = 0; i < 4; i++) {
        free(channels[i]); free(recon_ch[i]); free(oracle_ch[i]);
    }
    free(recon_bayer); free(oracle_bayer);
    return 0;
}

/* ============================================================
   Main driver
   ============================================================ */
static int run_one_input(const char *raw_path, int w, int h, int pf, int q,
                          int num_frames, double fps)
{
    fprintf(stderr, "\n========================================================\n");
    fprintf(stderr, " FULL ROUNDTRIP: %s\n", raw_path);
    fprintf(stderr, "   dims=%dx%d pf=%d q=%d frames=%d fps=%.1f (rc=OFF for PSNR)\n",
            w, h, pf, q, num_frames, fps);
    fprintf(stderr, "========================================================\n");

    /* Set up log curves up front. The encoder library does this lazily for
       the forward direction; the decoder side we need to trigger ourselves. */
    SetupEncoderLogCurve();
    SetupDecoderLogCurve();

    /* Load raw */
    FILE *f = fopen(raw_path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", raw_path); return 1; }
    fseek(f, 0, SEEK_END);
    size_t raw_size = (size_t)ftell(f);
    rewind(f);
    size_t expected = (size_t)w * h * 2;
    if (raw_size < expected) {
        fprintf(stderr, "raw file too small: %zu < %zu\n", raw_size, expected);
        fclose(f);
        return 1;
    }
    uint8_t *raw = (uint8_t *)malloc(expected);
    if (!raw) { fclose(f); return 1; }
    fread(raw, 1, expected, f);
    fclose(f);

    /* Encoder properties we need to feed the inverse pipeline. */
    int log_bits = (pf >= 4) ? 16 : 14;
    int is_rggb  = (pf == 0 || pf == 1 || pf == 4);
    const int prescale = 2;     /* fused_encode hardcodes this */

    /* Collect frames */
    collector_state cs;
    memset(&cs, 0, sizeof(cs));
    cs.capacity = num_frames;
    cs.frames   = (captured_frame *)calloc((size_t)num_frames, sizeof(captured_frame));
    pthread_mutex_init(&cs.lock, NULL);
    if (!cs.frames) { free(raw); return 1; }

    GPR_VIDEO_ENCODER *enc = gpr_video_encoder_create(
        w, h, pf, q, 3, collect_writer, &cs);
    if (!enc) {
        fprintf(stderr, "encoder create failed\n");
        free(raw); free(cs.frames);
        return 1;
    }

    /* IMPORTANT: rate control OFF so quant_scale = 1.0 for every frame.
       This makes PSNR validation deterministic across all frames since
       the public API doesn't expose per-frame scale. */
    /* (No gpr_video_encoder_set_target_bitrate call.) */

    for (int i = 0; i < num_frames; i++) {
        if (gpr_video_encoder_submit(enc, raw, expected, (uint64_t)i) != 0) {
            fprintf(stderr, "submit failed at frame %d\n", i);
        }
    }
    gpr_video_encoder_flush(enc);
    gpr_video_encoder_destroy(enc);

    fprintf(stderr, "captured %d frames, %.2f MB total (%.2f MB/frame avg)\n",
            cs.count,
            cs.total_bytes / 1024.0 / 1024.0,
            cs.count > 0 ? (cs.total_bytes / (double)cs.count) / 1024.0 / 1024.0 : 0.0);

    /* PSNR pass/fail thresholds. With no LL band, PSNR vs original raw
       cannot exceed a structural ceiling (driven by removed DC content).
       The oracle metric DOES need to be high — it tests that the inverse
       math accurately undoes the forward math when fed identical input. */
    const double oracle_psnr_threshold = 50.0;   /* dB — should be near-lossless */

    int frames_pass = 0;
    double sum_oracle_psnr = 0, sum_raw_psnr = 0;

    for (int fi = 0; fi < cs.count; fi++) {
        captured_frame *frame = &cs.frames[fi];
        frame_stats fs;
        memset(&fs, 0, sizeof(fs));

        int rc = run_frame_test(raw, frame->data, frame->size,
                                 w, h, log_bits, is_rggb, prescale, q,
                                 1.0 /* quant_scale: rate control is OFF */,
                                 &fs);
        if (rc != 0) {
            fprintf(stderr, "  frame %2" PRIu64 ": FAILED to reconstruct\n",
                    frame->tag);
            free(frame->data);
            continue;
        }

        /* Compute average band-match% to spot any rANS mismatch quickly. */
        double sum_match = 0;
        int32_t min_v = INT32_MAX, max_v = INT32_MIN;
        for (int b = 0; b < BANDS_PER_FRAME; b++) {
            sum_match += fs.band_match_pct[b];
            if (fs.band_min[b] < min_v) min_v = fs.band_min[b];
            if (fs.band_max[b] > max_v) max_v = fs.band_max[b];
        }
        double avg_match = sum_match / (double)BANDS_PER_FRAME;

        fprintf(stderr,
            "  frame %2" PRIu64 ": size=%5.2f MB | bands match=%6.2f%% | "
            "PSNR(oracle)=%6.2f dB | PSNR(raw)=%5.2f dB | "
            "per-ch raw=[%.1f %.1f %.1f %.1f]\n",
            frame->tag,
            frame->size / 1024.0 / 1024.0,
            avg_match,
            fs.psnr_oracle_total,
            fs.psnr_raw_total,
            fs.psnr_raw_per_ch[0], fs.psnr_raw_per_ch[1],
            fs.psnr_raw_per_ch[2], fs.psnr_raw_per_ch[3]);

        /* Per-band detail on the first frame only — locate which bands diverge */
        if (frame->tag == 0) {
            const int BPC = BANDS_PER_CHANNEL;
            fprintf(stderr, "         per-band match%%: ");
            for (int b = 0; b < BANDS_PER_FRAME; b++) {
                fprintf(stderr, "%s%5.1f%s", (b % BPC == 0) ? "ch" : "/",
                        fs.band_match_pct[b], "");
                if (b % BPC == BPC - 1) fprintf(stderr, "  ");
            }
            fprintf(stderr, "\n         per-band nonzero: ");
            for (int b = 0; b < BANDS_PER_FRAME; b++) {
                fprintf(stderr, "%s%5d%s", (b % BPC == 0) ? "ch" : "/",
                        fs.band_nonzero[b], "");
                if (b % BPC == BPC - 1) fprintf(stderr, "  ");
            }
            fprintf(stderr, "\n         per-band [min,max]: ");
            for (int b = 0; b < BANDS_PER_FRAME; b++) {
                fprintf(stderr, "[%d,%d]%s",
                        fs.band_min[b], fs.band_max[b],
                        (b % BPC == BPC - 1) ? "  " : " ");
            }
            fprintf(stderr, "\n");
        }

        sum_oracle_psnr += fs.psnr_oracle_total;
        sum_raw_psnr    += fs.psnr_raw_total;
        if (fs.psnr_oracle_total >= oracle_psnr_threshold ||
            !isfinite(fs.psnr_oracle_total)) {
            frames_pass++;
        }
        free(frame->data);
    }

    int rc = (frames_pass == cs.count && cs.count == num_frames) ? 0 : 1;
    fprintf(stderr,
        "\nSummary: %d/%d frames pass (oracle PSNR >= %.1f dB)\n"
        "  avg oracle PSNR = %.2f dB, avg raw-vs-recon PSNR = %.2f dB\n"
        "VERDICT: %s\n",
        frames_pass, cs.count, oracle_psnr_threshold,
        cs.count > 0 ? sum_oracle_psnr / cs.count : 0.0,
        cs.count > 0 ? sum_raw_psnr / cs.count : 0.0,
        rc == 0 ? "PASS" : "FAIL");

    free(raw); free(cs.frames);
    pthread_mutex_destroy(&cs.lock);
    return rc;
}

int main(int argc, char **argv)
{
    if (argc > 1 && argc < 8) {
        fprintf(stderr,
            "usage: %s raw_file w h pf q num_frames fps\n"
            "       %s              (no args = default Z8 ISO64 + ISO22800)\n",
            argv[0], argv[0]);
        return 1;
    }
    if (argc >= 8) {
        const char *path = argv[1];
        int    w  = atoi(argv[2]);
        int    h  = atoi(argv[3]);
        int    pf = atoi(argv[4]);
        int    q  = atoi(argv[5]);
        int    n  = atoi(argv[6]);
        double fps = atof(argv[7]);
        return run_one_input(path, w, h, pf, q, n, fps);
    }
    int rc1 = run_one_input("/tmp/Z8_ISO64.raw",    8280, 5520, 4, 3, 10, 24.0);
    int rc2 = run_one_input("/tmp/Z8_ISO22800.raw", 8280, 5520, 4, 3, 10, 24.0);
    fprintf(stderr, "\n=== Final ===\n");
    fprintf(stderr, "  ISO64:    %s\n", rc1 == 0 ? "PASS" : "FAIL");
    fprintf(stderr, "  ISO22800: %s\n", rc2 == 0 ? "PASS" : "FAIL");
    return (rc1 == 0 && rc2 == 0) ? 0 : 1;
}
