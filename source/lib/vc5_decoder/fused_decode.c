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

#include "headers.h"
#include "ans_joint.h"
#include "fused_decode.h"
#include "../vc5_encoder/fused_encode.h"  /* FUSED_HEADER, FUSED_MAGIC */
#include "logcurve.h"
#include "inverse.h"

#include <stdlib.h>
#include <string.h>

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
    if (!hdr.multi_level) return -5;  /* single-level can't be reconstructed (no LL) */
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
