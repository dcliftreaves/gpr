/*! @file test_preview_decode.c
 *
 *  @brief Standalone LL2-only preview decoder for the GPR raw video codec.
 *
 *  This binary deliberately contains NO inverse wavelet code. It:
 *    1. Encodes a single frame at quality 3 via gpr_encode_fused_frame.
 *    2. Walks the per-frame bitstream and decodes ONLY the LL2 band of
 *       each channel (the first band per channel in 3-level layout).
 *       Bands 1..9 (LH2/HL2/HH2/LH1/HL1/HH1/LH0/HL0/HH0) are skipped
 *       physically — their bytes are advanced past with probe_band_bytes
 *       but jans_decode_band_x4 is never called on them.
 *    3. Dequantizes LL2 with FUSED_LL2_DIVISOR=64.
 *    4. Feeds the 4 LL2 channel buffers (GS/RG/BG/GD at bw2 x bh2)
 *       directly to reconstruct_bayer_row — no inverse wavelet at all.
 *       The LL2 band values, post-dequant, are at the *same* magnitude
 *       scale as the encoder's channel domain (3 levels of forward
 *       horizontal_filter use prescale=2 each which cancels the gain
 *       of each level's e+o sums). So prescale=0 in reconstruct_bayer_row.
 *    5. Writes the resulting Bayer image at LL2 resolution
 *       (2*bw2) x (2*bh2) = 1034 x 690 as a 16-bit big-endian PGM.
 *
 *  By construction the decoder's output is bounded to ≤ 1.5K horizontal
 *  pixels — there is no path in this binary to produce anything larger.
 *
 *  Build:
 *    clang -O2 -o /tmp/test_preview_decode source/app/test_preview_decode.c \
 *      build/source/lib/vc5_encoder/libvc5_encoder.a \
 *      build/source/lib/vc5_common/libvc5_common.a \
 *      -lpthread -lm
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <inttypes.h>

#include "../lib/vc5_encoder/fused_encode.h"

/* -- External symbols from libvc5_common -- */
extern int  jans_decode_band_x4(const uint8_t *in_buf, size_t in_size,
                                int32_t *data, int width, int height, int pitch);
extern void SetupEncoderLogCurve(void);
extern void SetupDecoderLogCurve(void);
extern uint16_t DecoderLogCurve14[];
extern uint16_t DecoderLogCurve16[];

#define BANDS_PER_CHANNEL  10   /* 3-level layout: LL2,LH2,HL2,HH2,LH1,HL1,HH1,LH0,HL0,HH0 */
#define FUSED_LL2_DIVISOR  64

/* ============================================================
   Bitstream framing probe (copied verbatim from
   test_video_full_roundtrip.c probe_band_bytes).
   Returns the number of bytes consumed by one logical band in
   `*consumed`. We need this to skip past bands 1..9 without
   actually decoding them.
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
   Quant helpers (copied verbatim from test_video_full_roundtrip.c).
   ============================================================ */
static inline int32_t get_midpoint(int divisor) {
    return (divisor > 1) ? (divisor >> 1) - 1 : 0;
}
static inline int32_t get_multiplier(int divisor) {
    return (divisor > 0) ? ((1 << 16) / divisor) : 0;
}
static inline int32_t dequantize_scalar(int32_t q, int32_t divisor) {
    return q * divisor;
}
static inline int32_t clamp_to(int32_t v, int32_t lo, int32_t hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* ============================================================
   Inverse log curve + Bayer reconstruction (copied verbatim from
   test_video_full_roundtrip.c). Takes channel-domain rows and
   produces 2 raw Bayer rows.
   ============================================================ */
static inline uint16_t inv_log(int32_t v, int log_bits) {
    int log_max = (log_bits <= 14) ? 16383 : 65535;
    if (v < 0) v = 0; else if (v > log_max) v = log_max;
    return (log_bits <= 14) ? DecoderLogCurve14[v] : DecoderLogCurve16[v];
}

static void reconstruct_bayer_row(const int32_t *gs_row, const int32_t *rg_row,
                                   const int32_t *bg_row, const int32_t *gd_row,
                                   int ch_w, int log_bits, int is_rggb, int prescale,
                                   uint16_t *out_row1, uint16_t *out_row2)
{
    int log_max = (log_bits <= 14) ? 16383 : 65535;
    int32_t mid_half = 1 << (log_bits - 1);

    for (int c = 0; c < ch_w; c++) {
        int32_t GS = gs_row[c] << prescale;
        int32_t RG = rg_row[c] << prescale;
        int32_t BG = bg_row[c] << prescale;
        int32_t GD = gd_row[c] << prescale;

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
   Decode ONLY the LL2 band of each of the 4 channels. Skip
   bands 1..9 by advancing past their bytes without calling
   jans_decode_band_x4. The point: this binary cannot produce
   anything but a 2*bw2 x 2*bh2 image.
   ============================================================ */
static int decode_ll2_only(const uint8_t *vc5, size_t size,
                            int bw2, int bh2,
                            int32_t *ll2[4])
{
    size_t pos = 0;
    int ll2_ok = 0;
    for (int ch = 0; ch < 4; ch++) {
        for (int band = 0; band < BANDS_PER_CHANNEL; band++) {
            size_t band_bytes = 0;
            if (probe_band_bytes(vc5 + pos, size - pos, &band_bytes) != 0) {
                fprintf(stderr, "band-probe failed at ch=%d band=%d pos=%zu\n",
                        ch, band, pos);
                return ll2_ok;
            }
            if (band == 0) {
                /* This is LL2 for this channel — decode it. */
                memset(ll2[ch], 0, (size_t)bw2 * bh2 * sizeof(int32_t));
                int rc = jans_decode_band_x4(vc5 + pos, band_bytes,
                                              ll2[ch], bw2, bh2,
                                              bw2 * (int)sizeof(int32_t));
                if (rc != 0) {
                    fprintf(stderr, "jans_decode_band_x4 ch=%d LL2 → %d\n", ch, rc);
                    return ll2_ok;
                }
                ll2_ok++;
            }
            /* For bands 1..9 we PHYSICALLY skip — no decode call. */
            pos += band_bytes;
        }
    }
    return ll2_ok;
}

/* ============================================================
   Compute pixel stats for the preview image (uint16 values).
   ============================================================ */
typedef struct {
    uint16_t min, max;
    double   mean;
    uint16_t median;
} pix_stats;

static int u16_cmp(const void *a, const void *b) {
    uint16_t va = *(const uint16_t *)a, vb = *(const uint16_t *)b;
    return (va > vb) - (va < vb);
}

static void compute_stats(const uint16_t *img, size_t n, pix_stats *s)
{
    uint16_t mn = 0xFFFF, mx = 0;
    double sum = 0;
    for (size_t i = 0; i < n; i++) {
        uint16_t v = img[i];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
        sum += v;
    }
    s->min = mn;
    s->max = mx;
    s->mean = sum / (double)n;

    /* Median via copy+sort. n ~ 700K → ~1.4 MB, fine. */
    uint16_t *copy = (uint16_t *)malloc(n * sizeof(uint16_t));
    memcpy(copy, img, n * sizeof(uint16_t));
    qsort(copy, n, sizeof(uint16_t), u16_cmp);
    s->median = copy[n / 2];
    free(copy);
}

/* ============================================================
   Write a 16-bit big-endian PGM.
   ============================================================ */
static int write_pgm16(const char *path, const uint16_t *img, int w, int h)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    fprintf(f, "P5\n%d %d\n65535\n", w, h);
    /* Convert host endianness to big-endian per byte for portability. */
    size_t n = (size_t)w * h;
    uint8_t *be = (uint8_t *)malloc(n * 2);
    if (!be) { fclose(f); return -1; }
    for (size_t i = 0; i < n; i++) {
        uint16_t v = img[i];
        be[2*i]   = (uint8_t)(v >> 8);
        be[2*i+1] = (uint8_t)(v & 0xFF);
    }
    size_t wr = fwrite(be, 1, n * 2, f);
    free(be);
    fclose(f);
    return wr == n * 2 ? 0 : -1;
}

/* ============================================================
   Time helpers
   ============================================================ */
static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

int main(int argc, char **argv)
{
    (void)argc; (void)argv;

    /* Z8 ISO64 raw input. */
    const char *raw_path = "/tmp/Z8_ISO64.raw";
    const int w = 8280, h = 5520;
    const int pixel_format = 4;        /* RGGB16, but real data is 14-bit-in-16 */
    const int quality      = 3;

    /* Derived dimensions */
    const int ch_w = w / 2;
    const int ch_h = h / 2;
    const int bw   = ch_w / 2;
    const int bh   = ch_h / 2;
    const int bw1  = bw / 2;
    const int bh1  = bh / 2;
    const int bw2  = bw1 / 2;
    const int bh2  = bh1 / 2;
    const int out_w = bw2 * 2;     /* 1034 */
    const int out_h = bh2 * 2;     /* 690 */

    /* log_bits matches test_video_full_roundtrip.c: pf>=4 → 16. */
    const int log_bits = (pixel_format >= 4) ? 16 : 14;
    const int is_rggb  = (pixel_format == 0 || pixel_format == 1 || pixel_format == 4);

    fprintf(stderr,
            "preview decoder: input=%s\n"
            "  in=%dx%d ch=%dx%d bw2=%d bh2=%d out=%dx%d log_bits=%d\n",
            raw_path, w, h, ch_w, ch_h, bw2, bh2, out_w, out_h, log_bits);

    /* Init decoder log curves (encoder is set up lazily by its own library). */
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
    if (fread(raw, 1, expected, f) != expected) {
        fprintf(stderr, "raw read short\n"); fclose(f); free(raw); return 1;
    }
    fclose(f);

    /* ===== Stage 1: Encode one frame ===== */
    FUSED_ENCODER *enc = gpr_encode_fused_create(w, h, pixel_format, quality);
    if (!enc) { fprintf(stderr, "encoder create failed\n"); free(raw); return 1; }

    uint8_t *vc5 = NULL;
    size_t   vc5_size = 0;
    double t0 = now_ms();
    int rc = gpr_encode_fused_frame(enc, raw, expected, &vc5, &vc5_size);
    double t_encode = now_ms() - t0;
    if (rc != 0) {
        fprintf(stderr, "encode failed rc=%d\n", rc);
        gpr_encode_fused_destroy(enc);
        free(raw);
        return 1;
    }
    fprintf(stderr, "encoded: %.2f MB in %.1f ms\n",
            vc5_size / 1024.0 / 1024.0, t_encode);

    /* Make a private copy of the bitstream (encoder buffer is reused on next call). */
    uint8_t *vc5_copy = (uint8_t *)malloc(vc5_size);
    memcpy(vc5_copy, vc5, vc5_size);
    /* enc is no longer needed; destroy now to free the encoder's buffers. */
    gpr_encode_fused_destroy(enc);

    /* ===== Stage 2: Walk frame, decode LL2 only ===== */
    int32_t *ll2[4];
    for (int i = 0; i < 4; i++) {
        ll2[i] = (int32_t *)calloc((size_t)bw2 * bh2, sizeof(int32_t));
        if (!ll2[i]) {
            fprintf(stderr, "ll2 alloc failed\n");
            return 1;
        }
    }

    double t1 = now_ms();
    int ll2_count = decode_ll2_only(vc5_copy, vc5_size, bw2, bh2, ll2);
    if (ll2_count != 4) {
        fprintf(stderr, "expected 4 LL2 bands, got %d\n", ll2_count);
        for (int i = 0; i < 4; i++) free(ll2[i]);
        free(vc5_copy); free(raw);
        return 1;
    }

    /* Inverse quant LL2 with FUSED_LL2_DIVISOR. The encoder used base_divisor
       = FUSED_LL2_DIVISOR with the standard get_midpoint/get_multiplier. The
       inverse is simply value * divisor. */
    {
        int32_t d = FUSED_LL2_DIVISOR;
        size_t n = (size_t)bw2 * bh2;
        for (int ch = 0; ch < 4; ch++) {
            for (size_t k = 0; k < n; k++) {
                ll2[ch][k] = dequantize_scalar(ll2[ch][k], d);
            }
        }
    }
    /* Suppress unused-warning for the symmetric helpers; they're kept here so
       this file is a self-contained reference for the dequant math even
       though we don't run forward quant in the preview decoder. */
    (void)get_midpoint; (void)get_multiplier;
    double t_preview = now_ms() - t1;

    /* ===== Stage 3: NO inverse wavelet — treat LL2 as channel domain
       and call reconstruct_bayer_row directly.

       Why prescale=0:
       Each forward wavelet level applies a horizontal prescale of 2
       (PS(x)=x>>2). Each level then sums pairs in both horizontal
       (lowpass = e+o) and vertical directions, giving a net gain of
       2*2 / 2^2 = 1× per level. So the LL2 buffer's post-dequant
       values live at the SAME magnitude scale as the encoder's
       original channel-domain buffer. reconstruct_bayer_row's
       prescale argument applies an additional <<prescale to the
       channel value; with the LL2 values already in channel scale,
       we want no further shift → prescale=0.

       (Empirically: prescale=2 in the full decoder is correct for the
       *fully inverse-wavelet'd* channel image because each inverse
       wavelet level halves the magnitude scale. Here we have zero
       inverse wavelet levels, so we want zero extra shift.)  */
    const int prescale_for_recon = 0;

    double t2 = now_ms();
    uint16_t *preview = (uint16_t *)calloc((size_t)out_w * out_h, sizeof(uint16_t));
    if (!preview) {
        fprintf(stderr, "preview alloc failed\n");
        return 1;
    }

    /* Empirical sweep of prescale ∈ {0, 2, 4, 6} on Z8 ISO64 RGGB16 (pf=4):
         prescale=0 → min=0 max=9703 mean=1782 median=1527
         prescale=2 → min=0 max=65535 mean=50076 median=65535 (clipped)
         prescale=4 → min=0 max=65535 mean=50275 median=65535 (clipped)
         prescale=6 → min=0 max=65535 mean=50275 median=65535 (clipped)
       Conclusion: prescale=0 is the only non-clipping value. This matches
       the theory: each forward wavelet level applies horizontal prescale=2
       which is exactly cancelled by the level's e+o summing in both axes
       (gain = 2*2 / 2^2 = 1×). So LL2 post-dequant lives at the same scale
       as the encoder's channel-domain buffer, and any additional <<prescale
       in reconstruct_bayer_row pushes the value into the log curve's
       saturated tail. The mean of 1782 / median 1527 is what a normally-
       exposed 14-bit-RGGB-in-16-bit-log-curve round-trip produces: the
       input pixels are <= 16383 out of 65535, and the 16-bit log curve
       compresses those further into the bottom quarter of [0, 65535]. */
    {
        for (int ps = 0; ps <= 6; ps += 2) {
            uint16_t *tmp = (uint16_t *)calloc((size_t)out_w * out_h, sizeof(uint16_t));
            for (int r = 0; r < bh2; r++) {
                reconstruct_bayer_row(ll2[0] + r * bw2,
                                       ll2[1] + r * bw2,
                                       ll2[2] + r * bw2,
                                       ll2[3] + r * bw2,
                                       bw2, log_bits, is_rggb, ps,
                                       tmp + (2 * r) * out_w,
                                       tmp + (2 * r + 1) * out_w);
            }
            pix_stats sps;
            compute_stats(tmp, (size_t)out_w * out_h, &sps);
            fprintf(stderr,
                "  prescale=%d → min=%u max=%u mean=%.1f median=%u%s\n",
                ps, sps.min, sps.max, sps.mean, sps.median,
                ps == prescale_for_recon ? "  <-- USED" : "");
            free(tmp);
        }
    }

    /* Each row pair of preview is produced from one row of the 4 LL2 buffers.
       LL2 is bw2 columns wide → reconstruct_bayer_row emits 2*bw2 = out_w
       columns into two Bayer rows. Total bh2 row-pairs → out_h rows. */
    for (int r = 0; r < bh2; r++) {
        reconstruct_bayer_row(ll2[0] + r * bw2,
                               ll2[1] + r * bw2,
                               ll2[2] + r * bw2,
                               ll2[3] + r * bw2,
                               bw2, log_bits, is_rggb, prescale_for_recon,
                               preview + (2 * r) * out_w,
                               preview + (2 * r + 1) * out_w);
    }

    if (write_pgm16("/tmp/preview_ll2.pgm", preview, out_w, out_h) != 0) {
        fprintf(stderr, "PGM write failed\n");
        return 1;
    }
    double t_write = now_ms() - t2;

    /* ===== Validation: pixel stats ===== */
    pix_stats s;
    compute_stats(preview, (size_t)out_w * out_h, &s);

    fprintf(stderr,
        "\nDECODE STAGES: encode=%.1fms preview=%.1fms write=%.1fms\n",
        t_encode, t_preview, t_write);

    printf("PIXEL STATS: min=%u max=%u mean=%.1f median=%u\n",
           s.min, s.max, s.mean, s.median);
    printf("OUTPUT DIMS: %d x %d\n", out_w, out_h);
    printf("OUTPUT FILE: /tmp/preview_ll2.pgm\n");
    printf("LL2 BANDS DECODED: %d/4 (bands 1..9 physically skipped)\n", ll2_count);
    printf("DECODE STAGES: encode=%.1fms preview=%.1fms write=%.1fms\n",
           t_encode, t_preview, t_write);

    /* Pass condition: dims correct, all 4 LL2 bands decoded, mean in a
       sensible range for a 14-bit-in-16-bit raw exposed normally. */
    int dims_ok = (out_w == 1034 && out_h == 690);
    int range_ok = (s.mean > 1000.0 && s.mean < 50000.0 &&
                    s.min < s.max);
    int pass = dims_ok && range_ok && ll2_count == 4;
    if (pass) {
        printf("VERDICT: PASS — produced %dx%d preview from LL2 only "
               "(no inverse wavelet, no bands 1..9 decoded)\n", out_w, out_h);
    } else {
        printf("VERDICT: FAIL — dims_ok=%d range_ok=%d ll2_count=%d\n",
               dims_ok, range_ok, ll2_count);
    }

    /* Cleanup */
    free(preview);
    for (int i = 0; i < 4; i++) free(ll2[i]);
    free(vc5_copy);
    free(raw);
    return pass ? 0 : 1;
}
