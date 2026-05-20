/*! @file fused_decode.c
 *
 *  @brief Implementation of the fused decoder.
 *
 *  See fused_decode.h for the contract. The flow:
 *    1. Parse FUSED_HEADER and band-size table.
 *    2. rANS-decode all 40 bands (4 channels × 10 slots) via
 *       jans_decode_band_x4.
 *    3. Per channel: inverse wavelet at level 3, then 2, then 1.
 *       Level 1 uses InvertSpatialQuantDescale16s with descale=1 to
 *       undo the encoder's prescale=2. Levels 2/3 use the plain
 *       InvertSpatialQuant16s (no descale).
 *    4. Reverse the GS/RG/BG/GD color transform per pixel:
 *         R  = (RG-midpoint)<<1 + GS
 *         B  = (BG-midpoint)<<1 + GS
 *         G1 = GS + (GD-midpoint)
 *         G2 = GS - (GD-midpoint)
 *       Clamp to [0, log_max], apply DecoderLogCurve, shift to the
 *       caller's output bit depth, and write to the RGGB/GBRG Bayer
 *       pattern.
 */

#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L  /* needed for CLOCK_MONOTONIC on Pi gcc */
#endif

#include "headers.h"
#include "ans_joint.h"
#include "fused_decode.h"
#include "../vc5_encoder/fused_encode.h"  /* FUSED_HEADER, FUSED_MAGIC */
#include "logcurve.h"
#include "inverse.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>

/* GPR_DECODE_TIMING=1 prints per-stage decoder timing. */
static double _decode_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1.0e6;
}

/* Mirror of the encoder's quality_tables (private to fused_encode.c).
   Keep these in sync if they change. */
static const QUANT FUSED_QUALITY_TABLES[9][10] = {
    {1, 24, 24, 12, 64, 64, 48, 512, 512, 768},
    {1, 24, 24, 12, 48, 48, 32, 256, 256, 384},
    {1, 24, 24, 12, 32, 32, 24, 128, 128, 192},
    {1, 24, 24, 12, 24, 24, 12,  96,  96, 144},  /* default FS1 */
    {1, 24, 24, 12, 24, 24, 12,  64,  64,  96},
    {1, 24, 24, 12, 24, 24, 12,  32,  32,  48},
    {1, 12, 12,  6, 12, 12,  6,  16,  16,  24},
    {1,  6,  6,  4, 12, 12,  6,  16,  16,  24},
    {1,  4,  4,  2, 10, 10,  6,  16,  16,  24},
};

/* Allocator wrapper for the decoder primitives. They expect a
   gpr_allocator* — provide one backed by libc malloc. */
static void *fd_alloc(size_t n) { return malloc(n); }
static void  fd_free(void *p)   { free(p); }

/* Worker for parallel per-channel inverse wavelet in the single-level+LL
   decode path. Each task owns its 4 bands + output channel buffer. */
typedef struct {
    PIXEL *ll, *lh, *hl, *hh;
    PIXEL *out_channel;
    int bw, bh, ch_w, ch_h;
    QUANT *q;
    CODEC_ERROR err;
} FUSED_INV_TASK;

/* Per-strip color transform task. Each thread handles a contiguous slice
   of channel rows and writes the corresponding Bayer rows. */
typedef struct {
    int y_start, y_end;             /* channel row range [y_start, y_end) */
    int ch_w, ch_h;
    int log_max, midpoint, shift, is_rggb;
    const uint16_t *log_table;
    const PIXEL *gs_row, *rg_row, *bg_row, *gd_row;  /* base of channels */
    uint8_t *bayer_out;
    size_t bayer_pitch_bytes;
} FUSED_COLOR_TASK;

static void *fused_color_runner(void *arg) {
    FUSED_COLOR_TASK *t = (FUSED_COLOR_TASK *)arg;
    int log_max = t->log_max, midpoint = t->midpoint, shift = t->shift;
    const uint16_t *log_table = t->log_table;
    int ch_w = t->ch_w;
    for (int y = t->y_start; y < t->y_end; y++) {
        const PIXEL *gs_row = t->gs_row + (size_t)y * ch_w;
        const PIXEL *rg_row = t->rg_row + (size_t)y * ch_w;
        const PIXEL *bg_row = t->bg_row + (size_t)y * ch_w;
        const PIXEL *gd_row = t->gd_row + (size_t)y * ch_w;
        uint8_t *r1b = t->bayer_out + (size_t)(2*y) * t->bayer_pitch_bytes;
        uint8_t *r2b = t->bayer_out + (size_t)(2*y + 1) * t->bayer_pitch_bytes;
        uint16_t *bayer_row1 = (uint16_t *)r1b;
        uint16_t *bayer_row2 = (uint16_t *)r2b;

        for (int x = 0; x < ch_w; x++) {
            int gs = gs_row[x], rg = rg_row[x], bg = bg_row[x], gd = gd_row[x];
            if (gs < 0) gs = 0; if (gs > log_max) gs = log_max;
            if (rg < 0) rg = 0; if (rg > log_max) rg = log_max;
            if (bg < 0) bg = 0; if (bg > log_max) bg = log_max;
            if (gd < 0) gd = 0; if (gd > log_max) gd = log_max;
            rg -= midpoint; bg -= midpoint; gd -= midpoint;
            int r  = (rg << 1) + gs;
            int b  = (bg << 1) + gs;
            int g1 = gs + gd;
            int g2 = gs - gd;
            if (r  < 0) r  = 0; if (r  > log_max) r  = log_max;
            if (g1 < 0) g1 = 0; if (g1 > log_max) g1 = log_max;
            if (g2 < 0) g2 = 0; if (g2 > log_max) g2 = log_max;
            if (b  < 0) b  = 0; if (b  > log_max) b  = log_max;
            int r_lin  = log_table[r]  >> shift;
            int g1_lin = log_table[g1] >> shift;
            int g2_lin = log_table[g2] >> shift;
            int b_lin  = log_table[b]  >> shift;
            if (t->is_rggb) {
                bayer_row1[2*x]   = (uint16_t)r_lin;
                bayer_row1[2*x+1] = (uint16_t)g1_lin;
                bayer_row2[2*x]   = (uint16_t)g2_lin;
                bayer_row2[2*x+1] = (uint16_t)b_lin;
            } else {
                bayer_row1[2*x]   = (uint16_t)g1_lin;
                bayer_row1[2*x+1] = (uint16_t)b_lin;
                bayer_row2[2*x]   = (uint16_t)r_lin;
                bayer_row2[2*x+1] = (uint16_t)g2_lin;
            }
        }
    }
    return NULL;
}

/* Per-channel band decode task. 4 of these — each decodes a channel's
   4 bands sequentially in one thread. 16-thread per-band variant was
   tested: did NOT help (rANS decode has memory bandwidth + libc malloc
   contention; more threads beyond core count = diminishing returns). */
typedef struct {
    const uint8_t *enc_start;
    const uint32_t *band_sizes;     /* 4 sizes */
    PIXEL *out[4];
    int bw, bh;
} FUSED_BAND_TASK;

static void *fused_band_decode_runner(void *arg) {
    FUSED_BAND_TASK *t = (FUSED_BAND_TASK *)arg;
    size_t off = 0;
    for (int s = 0; s < 4; s++) {
        uint32_t sz = t->band_sizes[s];
        if (sz < 64) {
            memset(t->out[s], 0, (size_t)t->bw * t->bh * sizeof(PIXEL));
        } else {
            int drc = jans_decode_band_x4(t->enc_start + off, sz, t->out[s],
                                          t->bw, t->bh, t->bw * (int)sizeof(PIXEL));
            if (drc != 0) memset(t->out[s], 0, (size_t)t->bw * t->bh * sizeof(PIXEL));
        }
        off += sz;
    }
    return NULL;
}

static void *fused_inv_wavelet_runner(void *arg) {
    FUSED_INV_TASK *t = (FUSED_INV_TASK *)arg;
    gpr_allocator alloc = { fd_alloc, fd_free };
    t->err = InvertSpatialQuantDescale16s(&alloc,
        t->ll, t->bw * (int)sizeof(PIXEL),
        t->lh, t->bw * (int)sizeof(PIXEL),
        t->hl, t->bw * (int)sizeof(PIXEL),
        t->hh, t->bw * (int)sizeof(PIXEL),
        t->out_channel, t->ch_w * (int)sizeof(PIXEL),
        (DIMENSION)t->bw, (DIMENSION)t->bh,
        (DIMENSION)t->ch_w, (DIMENSION)t->ch_h,
        /*descale=*/2, t->q);
    return NULL;
}

/* Single-level + LL decode path (hdr.num_bands == 16, hdr.multi_level == 0).
   Band layout per channel (4 slots):
     0 = LL1   (bw × bh)
     1 = LH1   (bw × bh)
     2 = HL1   (bw × bh)
     3 = HH1   (bw × bh)
   Channels: GS=0, RG=1, BG=2, GD=3.

   Handles optional channel-space decimation via hdr.decimate: when set
   to 2, the encoded bands represent a (hdr.width/2 × hdr.height/2) Bayer
   image. Output bayer dims are adjusted accordingly. */
static int decode_fused_single_level_ll(const FUSED_HEADER *hdr,
                                        const uint8_t *enc, size_t enc_size,
                                        uint16_t *bayer_out, size_t bayer_pitch_bytes,
                                        int *out_width, int *out_height);

int gpr_decode_fused(const uint8_t *enc, size_t enc_size,
                     uint16_t *bayer_out, size_t bayer_pitch_bytes,
                     int *out_width, int *out_height)
{
    if (!enc || !bayer_out) return -1;
    if (enc_size < sizeof(FUSED_HEADER)) return -2;

    FUSED_HEADER hdr;
    memcpy(&hdr, enc, sizeof(hdr));
    if (hdr.magic != FUSED_MAGIC) return -3;
    if (hdr.version != FUSED_VERSION) return -4;
    /* Route single-level-with-LL files to the 16-band path. */
    if (!hdr.multi_level && hdr.num_bands == 16) {
        return decode_fused_single_level_ll(&hdr, enc, enc_size,
                                            bayer_out, bayer_pitch_bytes,
                                            out_width, out_height);
    }
    if (!hdr.multi_level) return -5;  /* single-level-without-LL: not decodable */
    if (hdr.num_bands != 40) return -6;
    if (hdr.quality >= 9) return -7;

    if (out_width)  *out_width  = (int)hdr.width;
    if (out_height) *out_height = (int)hdr.height;

    SetupDecoderLogCurve();

    /* Band-size table */
    size_t off = sizeof(FUSED_HEADER);
    uint32_t band_sizes[40];
    memcpy(band_sizes, enc + off, sizeof(band_sizes));
    off += sizeof(band_sizes);

    /* Dimensions per level — ceil at each step to match the encoder's
       odd-width handling (otherwise odd intermediate widths drop the
       last column on the way down the pyramid). */
    int ch_w = (int)hdr.width  / 2;
    int ch_h = (int)hdr.height / 2;
    int bw1  = ch_w / 2, bh1 = ch_h / 2;
    int bw2  = (bw1 + 1) / 2, bh2 = (bh1 + 1) / 2;
    int bw3  = (bw2 + 1) / 2, bh3 = (bh2 + 1) / 2;

    /* Slot widths/heights — matches encoder write order:
         0..2 = LH1/HL1/HH1   (bw1×bh1)
         3..5 = LH2/HL2/HH2   (bw2×bh2)
         6..8 = LH3/HL3/HH3   (bw3×bh3)
         9    = LL3           (bw3×bh3)  */
    const int slot_w[10] = { bw1, bw1, bw1, bw2, bw2, bw2, bw3, bw3, bw3, bw3 };
    const int slot_h[10] = { bh1, bh1, bh1, bh2, bh2, bh2, bh3, bh3, bh3, bh3 };

    /* Decode all 40 bands into per-channel, per-slot int32 buffers. */
    PIXEL *bands[4][10];
    for (int ch = 0; ch < 4; ch++)
        for (int s = 0; s < 10; s++)
            bands[ch][s] = NULL;

    int band_idx = 0;
    int rc = 0;
    for (int ch = 0; ch < 4 && rc == 0; ch++) {
        for (int s = 0; s < 10 && rc == 0; s++) {
            int bw = slot_w[s], bh = slot_h[s];
            uint32_t sz = band_sizes[band_idx];
            if (off + sz > enc_size) { rc = -10; break; }
            bands[ch][s] = (PIXEL *)malloc((size_t)bw * bh * sizeof(PIXEL));
            if (!bands[ch][s]) { rc = -11; break; }
            int drc = jans_decode_band_x4(enc + off, sz,
                                           bands[ch][s], bw, bh,
                                           bw * (int)sizeof(PIXEL));
            if (drc != 0) { rc = -12; break; }
            off += sz;
            band_idx++;
        }
    }

    /* Per-channel inverse wavelet: level 3 → level 2 → level 1. */
    gpr_allocator alloc = { fd_alloc, fd_free };
    PIXEL *channels[4] = { NULL, NULL, NULL, NULL };

    if (rc == 0) {
        const QUANT *qt = FUSED_QUALITY_TABLES[hdr.quality];
        /* The decoder's DequantizeBandRow16s interprets a positive QUANT as
           "VC5 companded + quantized" (apply UncompandedValueFast then
           multiply by quant). The fused encoder doesn't compand, so we use
           the negative-quant convention to tell DequantizeBandRow16s to
           just multiply by |q| without uncompanding. */
        /* Level-3 quant: {LL3=qt[0], LH3=qt[1], HL3=qt[2], HH3=qt[3]} */
        QUANT q_l3[4] = { -qt[0], -qt[1], -qt[2], -qt[3] };
        /* Level-2 quant: {LL=1 (intermediate, not encoded), LH2=qt[4], HL2=qt[5], HH2=qt[6]} */
        QUANT q_l2[4] = { -1, -qt[4], -qt[5], -qt[6] };
        /* Level-1 quant: {LL=1 (intermediate), LH1=qt[7], HL1=qt[8], HH1=qt[9]} */
        QUANT q_l1[4] = { -1, -qt[7], -qt[8], -qt[9] };

        /* Manually dequantize LL3 (the inverse function only dequantizes
           LH/HL/HH; LL gets passed straight through). Encoder used
           qt[0] * FUSED_LL3_EXTRA_DIVISOR to keep LL3 mag under rANS's
           class-15 ceiling. */
        #define FUSED_LL3_EXTRA_DIVISOR 16
        int ll3_dequant = qt[0] * FUSED_LL3_EXTRA_DIVISOR;
        for (int ch = 0; ch < 4; ch++) {
            PIXEL *p = bands[ch][9];
            if (!p) continue;
            size_t n = (size_t)bw3 * bh3;
            for (size_t i = 0; i < n; i++) p[i] *= ll3_dequant;
        }

        for (int ch = 0; ch < 4 && rc == 0; ch++) {
            /* Every level used the encoder's prescale=2, so every inverse
               level uses descale=2 (which the primitive maps to an internal
               <<1 on horizontal output to restore magnitude). */

            /* Level 3 inverse: bands[ch][9] = LL3, [6/7/8] = LH3/HL3/HH3 → LL2 */
            PIXEL *ll2 = (PIXEL *)malloc((size_t)bw2 * bh2 * sizeof(PIXEL));
            if (!ll2) { rc = -20; break; }
            CODEC_ERROR e = InvertSpatialQuantDescale16s(&alloc,
                bands[ch][9], bw3 * (int)sizeof(PIXEL),
                bands[ch][6], bw3 * (int)sizeof(PIXEL),
                bands[ch][7], bw3 * (int)sizeof(PIXEL),
                bands[ch][8], bw3 * (int)sizeof(PIXEL),
                ll2, bw2 * (int)sizeof(PIXEL),
                (DIMENSION)bw3, (DIMENSION)bh3,
                (DIMENSION)bw2, (DIMENSION)bh2,
                /*descale=*/2, q_l3);
            if (e != CODEC_ERROR_OKAY) { free(ll2); rc = -21; break; }

            /* Level 2 inverse: ll2 + LH2/HL2/HH2 → LL1 */
            PIXEL *ll1 = (PIXEL *)malloc((size_t)bw1 * bh1 * sizeof(PIXEL));
            if (!ll1) { free(ll2); rc = -22; break; }
            e = InvertSpatialQuantDescale16s(&alloc,
                ll2,          bw2 * (int)sizeof(PIXEL),
                bands[ch][3], bw2 * (int)sizeof(PIXEL),
                bands[ch][4], bw2 * (int)sizeof(PIXEL),
                bands[ch][5], bw2 * (int)sizeof(PIXEL),
                ll1, bw1 * (int)sizeof(PIXEL),
                (DIMENSION)bw2, (DIMENSION)bh2,
                (DIMENSION)bw1, (DIMENSION)bh1,
                /*descale=*/2, q_l2);
            free(ll2);
            if (e != CODEC_ERROR_OKAY) { free(ll1); rc = -23; break; }

            /* Level 1 inverse: ll1 + LH1/HL1/HH1 → channel */
            channels[ch] = (PIXEL *)malloc((size_t)ch_w * ch_h * sizeof(PIXEL));
            if (!channels[ch]) { free(ll1); rc = -24; break; }
            e = InvertSpatialQuantDescale16s(&alloc,
                ll1,          bw1 * (int)sizeof(PIXEL),
                bands[ch][0], bw1 * (int)sizeof(PIXEL),
                bands[ch][1], bw1 * (int)sizeof(PIXEL),
                bands[ch][2], bw1 * (int)sizeof(PIXEL),
                channels[ch], ch_w * (int)sizeof(PIXEL),
                (DIMENSION)bw1, (DIMENSION)bh1,
                (DIMENSION)ch_w, (DIMENSION)ch_h,
                /*descale=*/2, q_l1);
            free(ll1);
            if (e != CODEC_ERROR_OKAY) { rc = -25; break; }
        }
    }

    /* Free band buffers; we've consumed them into the channel planes. */
    for (int ch = 0; ch < 4; ch++)
        for (int s = 0; s < 10; s++)
            if (bands[ch][s]) free(bands[ch][s]);

    /* Reverse the GS/RG/BG/GD color transform and apply the inverse
       log curve. Output bit-depth: match log_bits (12, 14, or 16). */
    if (rc == 0) {
        int log_max  = (1 << (int)hdr.log_bits) - 1;
        int midpoint = 1 << ((int)hdr.log_bits - 1);
        const uint16_t *log_table =
            (hdr.log_bits <= 14) ? DecoderLogCurve14 : DecoderLogCurve16;
        int output_bit_depth = (int)hdr.log_bits;
        int shift = 16 - output_bit_depth;
        int is_rggb = (int)hdr.is_rggb;

        for (int y = 0; y < ch_h; y++) {
            const PIXEL *gs_row = channels[0] + (size_t)y * ch_w;
            const PIXEL *rg_row = channels[1] + (size_t)y * ch_w;
            const PIXEL *bg_row = channels[2] + (size_t)y * ch_w;
            const PIXEL *gd_row = channels[3] + (size_t)y * ch_w;
            uint8_t *r1_bytes = (uint8_t *)bayer_out + (size_t)(2*y)     * bayer_pitch_bytes;
            uint8_t *r2_bytes = (uint8_t *)bayer_out + (size_t)(2*y + 1) * bayer_pitch_bytes;
            uint16_t *bayer_row1 = (uint16_t *)r1_bytes;
            uint16_t *bayer_row2 = (uint16_t *)r2_bytes;

            for (int x = 0; x < ch_w; x++) {
                int gs = gs_row[x];
                int rg = rg_row[x];
                int bg = bg_row[x];
                int gd = gd_row[x];

                /* Clamp inputs */
                if (gs < 0) gs = 0; if (gs > log_max) gs = log_max;
                if (rg < 0) rg = 0; if (rg > log_max) rg = log_max;
                if (bg < 0) bg = 0; if (bg > log_max) bg = log_max;
                if (gd < 0) gd = 0; if (gd > log_max) gd = log_max;

                /* Subtract midpoint, then invert color transform */
                rg -= midpoint;
                bg -= midpoint;
                gd -= midpoint;

                int r  = (rg << 1) + gs;
                int b  = (bg << 1) + gs;
                int g1 = gs + gd;
                int g2 = gs - gd;

                if (r  < 0) r  = 0; if (r  > log_max) r  = log_max;
                if (g1 < 0) g1 = 0; if (g1 > log_max) g1 = log_max;
                if (g2 < 0) g2 = 0; if (g2 > log_max) g2 = log_max;
                if (b  < 0) b  = 0; if (b  > log_max) b  = log_max;

                /* Inverse log curve → output bit depth */
                int r_lin  = log_table[r]  >> shift;
                int g1_lin = log_table[g1] >> shift;
                int g2_lin = log_table[g2] >> shift;
                int b_lin  = log_table[b]  >> shift;

                if (is_rggb) {
                    bayer_row1[2*x]   = (uint16_t)r_lin;
                    bayer_row1[2*x+1] = (uint16_t)g1_lin;
                    bayer_row2[2*x]   = (uint16_t)g2_lin;
                    bayer_row2[2*x+1] = (uint16_t)b_lin;
                } else {
                    /* GBRG */
                    bayer_row1[2*x]   = (uint16_t)g1_lin;
                    bayer_row1[2*x+1] = (uint16_t)b_lin;
                    bayer_row2[2*x]   = (uint16_t)r_lin;
                    bayer_row2[2*x+1] = (uint16_t)g2_lin;
                }
            }
        }
    }

    for (int ch = 0; ch < 4; ch++)
        if (channels[ch]) free(channels[ch]);

    return rc;
}

/* ============================================================
   Single-level + LL decode path
   ============================================================ */
static int decode_fused_single_level_ll(const FUSED_HEADER *hdr,
                                        const uint8_t *enc, size_t enc_size,
                                        uint16_t *bayer_out, size_t bayer_pitch_bytes,
                                        int *out_width, int *out_height)
{
    if (hdr->quality >= 9) return -7;

    /* When channel-space decimation was applied, the encoded bands
       represent a (hdr.width/dec × hdr.height/dec) Bayer-equivalent image.
       The output Bayer is at those reduced dims. */
    int dec = (hdr->decimate == 2) ? 2 : 1;
    int bayer_w = (int)hdr->width  / dec;
    int bayer_h = (int)hdr->height / dec;
    int ch_w = bayer_w / 2;
    int ch_h = bayer_h / 2;
    int bw = ch_w / 2;
    int bh = ch_h / 2;

    if (out_width)  *out_width  = bayer_w;
    if (out_height) *out_height = bayer_h;

    SetupDecoderLogCurve();

    size_t off = sizeof(FUSED_HEADER);
    if (off + 16 * sizeof(uint32_t) > enc_size) return -8;
    uint32_t band_sizes[16];
    memcpy(band_sizes, enc + off, sizeof(band_sizes));
    off += sizeof(band_sizes);

    /* Decode all 16 bands: 4 channels × {LL, LH, HL, HH}. */
    PIXEL *bands[4][4];
    for (int ch = 0; ch < 4; ch++)
        for (int s = 0; s < 4; s++)
            bands[ch][s] = NULL;

    int rc = 0;
    int band_idx = 0;
    int dbg_timing = 0;
    {
        const char *e = getenv("GPR_DECODE_TIMING");
        if (e && *e == '1') dbg_timing = 1;
    }
    /* GPR_DECODE_LL_ONLY=1: discard HP bands at decode (treat as zero),
       producing the same output as encoding with GPR_DROP_HIGHPASS=1, but
       from a full LL+HP-encoded stream. This lets a single archived stream
       serve two consumers: a fast streaming decoder that drops HP for
       speed, and a quality decoder that consumes the HP for full fidelity
       (with optional CNN polish layered on the LL-only output). */
    int ll_only_decode = 0;
    {
        const char *e = getenv("GPR_DECODE_LL_ONLY");
        if (e && *e == '1') ll_only_decode = 1;
    }
    double dt0 = _decode_ms();
    /* Pre-allocate buffers + compute per-channel offsets, then dispatch
       4 threads (one per channel × 4 bands each). When ll_only_decode is
       set, we still allocate HP band buffers but zero them and skip the
       rANS decode for the HP slots (their offsets are still consumed
       so the byte cursor walks past them). */
    FUSED_BAND_TASK bt[4];
    size_t band_off = off;
    for (int ch = 0; ch < 4 && rc == 0; ch++) {
        bt[ch].enc_start = enc + band_off;
        bt[ch].band_sizes = &band_sizes[ch * 4];
        bt[ch].bw = bw;
        bt[ch].bh = bh;
        for (int s = 0; s < 4; s++) {
            bands[ch][s] = (PIXEL *)malloc((size_t)bw * bh * sizeof(PIXEL));
            if (!bands[ch][s]) { rc = -11; break; }
            bt[ch].out[s] = bands[ch][s];
            uint32_t sz = band_sizes[ch * 4 + s];
            if (band_off + sz > enc_size) { rc = -10; break; }
            band_off += sz;
            /* When ll_only_decode is set, zero the HP band buffers and
               trigger the existing "sz < 64 → memset" fast path in the
               band runner by zeroing the size locally. We do this AFTER
               offset accumulation so the byte cursor walks the real
               sizes correctly. */
        }
    }
    /* If LL-only decode requested, point the runner at a zeroed-size
       table per channel so HP bands are memset to zero, not rANS-decoded. */
    static uint32_t zero_sizes[4][4];
    if (ll_only_decode && rc == 0) {
        for (int ch = 0; ch < 4; ch++) {
            zero_sizes[ch][0] = band_sizes[ch * 4 + 0];  /* keep LL */
            zero_sizes[ch][1] = 0;   /* triggers memset fast path */
            zero_sizes[ch][2] = 0;
            zero_sizes[ch][3] = 0;
            bt[ch].band_sizes = zero_sizes[ch];
        }
    }
    if (rc == 0) {
        pthread_t bth[4]; int bcr[4] = {0};
        for (int ch = 0; ch < 4; ch++) {
            bcr[ch] = (pthread_create(&bth[ch], NULL,
                       fused_band_decode_runner, &bt[ch]) == 0);
            if (!bcr[ch]) fused_band_decode_runner(&bt[ch]);
        }
        for (int ch = 0; ch < 4; ch++) {
            if (bcr[ch]) pthread_join(bth[ch], NULL);
        }
    }
    off = band_off;
    (void)band_idx;

    double dt_band = _decode_ms() - dt0;
    if (dbg_timing) fprintf(stderr, "  decode band_decode: %.1f ms\n", dt_band);
    double dt_wav0 = _decode_ms();

    PIXEL *channels[4] = { NULL, NULL, NULL, NULL };

    if (rc == 0) {
        const QUANT *qt = FUSED_QUALITY_TABLES[hdr->quality];
        QUANT q_l1[4] = { -qt[0], -qt[1], -qt[2], -qt[3] };

        /* The encoder divides single-level LL by 16× the natural quant to
           keep magnitudes under the rANS class-15 ceiling (matches the
           multi-level LL3 trick). Pre-multiply LL bands to undo that. */
        const int ll_extra = 16;
        const int ll_dequant = qt[0] * ll_extra;
        for (int ch = 0; ch < 4; ch++) {
            PIXEL *p = bands[ch][0];
            if (!p) continue;
            size_t n = (size_t)bw * bh;
            for (size_t i = 0; i < n; i++) p[i] *= ll_dequant;
        }

        const char *dbg = getenv("FUSED_DECODE_DEBUG");
        if (dbg && *dbg == '1') {
            for (int ch = 0; ch < 4; ch++) {
                for (int s = 0; s < 4; s++) {
                    PIXEL *p = bands[ch][s];
                    long mn = 1<<30, mx = -(1<<30); long long sum = 0;
                    long n = (long)bw * bh;
                    for (long i = 0; i < n; i++) {
                        if (p[i] < mn) mn = p[i];
                        if (p[i] > mx) mx = p[i];
                        sum += p[i];
                    }
                    fprintf(stderr, "  ch%d band%d (%s): min=%ld max=%ld mean=%.1f\n",
                            ch, s, s==0?"LL":s==1?"LH":s==2?"HL":"HH",
                            mn, mx, (double)sum/n);
                }
            }
        }

        /* Parallel inverse wavelet: 4 channels, 4 threads on Pi 5's 4 cores.
           Each channel's inverse is independent — own band buffers, own
           output channel. InvertSpatialQuantDescale16s uses the allocator
           which wraps libc malloc (thread-safe). Expected ~3-4× wall
           reduction on this stage. */
        FUSED_INV_TASK tasks[4];
        pthread_t threads[4];
        int created[4] = {0};
        for (int ch = 0; ch < 4 && rc == 0; ch++) {
            channels[ch] = (PIXEL *)malloc((size_t)ch_w * ch_h * sizeof(PIXEL));
            if (!channels[ch]) { rc = -24; break; }
            tasks[ch].ll = bands[ch][0];
            tasks[ch].lh = bands[ch][1];
            tasks[ch].hl = bands[ch][2];
            tasks[ch].hh = bands[ch][3];
            tasks[ch].out_channel = channels[ch];
            tasks[ch].bw = bw;
            tasks[ch].bh = bh;
            tasks[ch].ch_w = ch_w;
            tasks[ch].ch_h = ch_h;
            tasks[ch].q = q_l1;
            tasks[ch].err = CODEC_ERROR_OKAY;
        }
        if (rc == 0) {
            for (int ch = 0; ch < 4; ch++) {
                created[ch] = (pthread_create(&threads[ch], NULL,
                    fused_inv_wavelet_runner, &tasks[ch]) == 0);
                if (!created[ch]) fused_inv_wavelet_runner(&tasks[ch]);
            }
            for (int ch = 0; ch < 4; ch++) {
                if (created[ch]) pthread_join(threads[ch], NULL);
                if (tasks[ch].err != CODEC_ERROR_OKAY) rc = -25;
            }
        }
    }

    double dt_wav = _decode_ms() - dt_wav0;
    if (dbg_timing) fprintf(stderr, "  decode wavelet inv: %.1f ms\n", dt_wav);
    double dt_color0_sl = _decode_ms();

    for (int ch = 0; ch < 4; ch++)
        for (int s = 0; s < 4; s++)
            if (bands[ch][s]) free(bands[ch][s]);

    /* Parallel color transform: split channel rows across 4 threads. Each
       row is independent — output Bayer rows for row y are at 2y, 2y+1. */
    if (rc == 0) {
        int log_max  = (1 << (int)hdr->log_bits) - 1;
        int midpoint = 1 << ((int)hdr->log_bits - 1);
        const uint16_t *log_table =
            (hdr->log_bits <= 14) ? DecoderLogCurve14 : DecoderLogCurve16;
        int output_bit_depth = (int)hdr->log_bits;
        int shift = 16 - output_bit_depth;
        int is_rggb = (int)hdr->is_rggb;

        FUSED_COLOR_TASK ct[4];
        pthread_t cth[4]; int ccr[4] = {0};
        for (int i = 0; i < 4; i++) {
            ct[i].y_start = (ch_h * i) / 4;
            ct[i].y_end   = (ch_h * (i + 1)) / 4;
            ct[i].ch_w = ch_w;
            ct[i].ch_h = ch_h;
            ct[i].log_max = log_max;
            ct[i].midpoint = midpoint;
            ct[i].shift = shift;
            ct[i].is_rggb = is_rggb;
            ct[i].log_table = log_table;
            ct[i].gs_row = channels[0];
            ct[i].rg_row = channels[1];
            ct[i].bg_row = channels[2];
            ct[i].gd_row = channels[3];
            ct[i].bayer_out = (uint8_t *)bayer_out;
            ct[i].bayer_pitch_bytes = bayer_pitch_bytes;
            ccr[i] = (pthread_create(&cth[i], NULL,
                                     fused_color_runner, &ct[i]) == 0);
            if (!ccr[i]) fused_color_runner(&ct[i]);
        }
        for (int i = 0; i < 4; i++) {
            if (ccr[i]) pthread_join(cth[i], NULL);
        }
    }

    for (int ch = 0; ch < 4; ch++)
        if (channels[ch]) free(channels[ch]);

    if (dbg_timing) fprintf(stderr, "  decode color_xform: %.1f ms\n",
                            _decode_ms() - dt_color0_sl);
    return rc;
}
