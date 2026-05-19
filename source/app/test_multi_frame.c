/* test_multi_frame — encode → decode N raw frames through the fused codec,
 * write the decoded Bayer + a quick-and-dirty demosaiced PPM per frame, and
 * print per-frame encode/decode timings.
 *
 * The PPM is for sanity (looks roughly like the scene), NOT for visualization
 * quality. For correct color/gamma rendering use tools/render_compare.py on
 * the saved .raw files, which feeds them through rawpy/libraw with the source
 * DNG's white balance + color matrix + gamma. Rolling a demosaic by hand
 * always looks broken — don't trust the .ppm output for quality judgments.
 *
 * Honors the same env flags as bench_fused:
 *   GPR_INCLUDE_LL=1         single-level + LL band (decodable)
 *   GPR_ROW_DECIMATE=2       2x row decimation (channel-space)
 *   GPR_COL_DECIMATE=2       2x col decimation (channel-space)
 *   GPR_DROP_HIGHPASS=1      LL-only output (skips highpass tokenize)
 *
 * Build (Pi or any aarch64 with the encoder/decoder built):
 *   gcc -O2 source/app/test_multi_frame.c \
 *       build/source/lib/vc5_decoder/libvc5_decoder.a \
 *       build/source/lib/vc5_encoder/libvc5_encoder.a \
 *       build/source/lib/vc5_common/libvc5_common.a \
 *       build/source/lib/common/libcommon.a \
 *       -lpthread -lm -o /tmp/multi_frame
 *
 * Usage:
 *   multi_frame W H out_prefix raw1 [raw2 ...]
 *   GPR_INCLUDE_LL=1 GPR_ROW_DECIMATE=2 GPR_COL_DECIMATE=2 \
 *       multi_frame 8280 5520 /tmp/out/f frame1.raw frame2.raw ...
 *
 * Driven end-to-end by tools/run_codec_movie.sh which handles DNG→raw on
 * the local side, ssh's the raws over, runs this tool, and renders the
 * output through rawpy back on the local side.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

typedef struct FUSED_ENCODER FUSED_ENCODER;
extern FUSED_ENCODER *gpr_encode_fused_create(int w, int h, int pf, int q);
extern int gpr_encode_fused_frame(FUSED_ENCODER *ctx, const unsigned char *raw, size_t sz,
                                   unsigned char **out, size_t *out_sz);
extern void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);
extern int gpr_decode_fused(const unsigned char *enc, size_t enc_size,
                             uint16_t *bayer_out, size_t bayer_pitch_bytes,
                             int *out_width, int *out_height);

static double now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1.0e6;
}

static void demosaic_to_ppm(const uint16_t *bayer, int W, int H,
                            int gain, const char *path)
{
    int ow = W / 2, oh = H / 2;
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fprintf(f, "P6\n%d %d\n65535\n", ow, oh);
    uint8_t *row = malloc((size_t)ow * 6);
    for (int yo = 0; yo < oh; yo++) {
        const uint16_t *r1 = bayer + (size_t)(yo * 2) * W;
        const uint16_t *r2 = bayer + (size_t)(yo * 2 + 1) * W;
        for (int xo = 0; xo < ow; xo++) {
            int xi = xo * 2;
            uint32_t r  = r1[xi];
            uint32_t g1 = r1[xi + 1];
            uint32_t g2 = r2[xi];
            uint32_t b  = r2[xi + 1];
            uint32_t g  = (g1 + g2) >> 1;
            uint32_t rr = r * gain; if (rr > 65535) rr = 65535;
            uint32_t gg = g * gain; if (gg > 65535) gg = 65535;
            uint32_t bb = b * gain; if (bb > 65535) bb = 65535;
            row[xo * 6 + 0] = (rr >> 8) & 0xff; row[xo * 6 + 1] = rr & 0xff;
            row[xo * 6 + 2] = (gg >> 8) & 0xff; row[xo * 6 + 3] = gg & 0xff;
            row[xo * 6 + 4] = (bb >> 8) & 0xff; row[xo * 6 + 5] = bb & 0xff;
        }
        fwrite(row, 1, (size_t)ow * 6, f);
    }
    free(row);
    fclose(f);
}

int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr, "usage: %s W H out_prefix raw1 [raw2 ...]\n", argv[0]);
        return 1;
    }
    int W = atoi(argv[1]), H = atoi(argv[2]);
    const char *prefix = argv[3];
    int nframes = argc - 4;
    size_t in_sz = (size_t)W * H * 2;

    FUSED_ENCODER *enc = gpr_encode_fused_create(W, H, 1, 3);
    if (!enc) { fprintf(stderr, "encoder create fail\n"); return 1; }

    uint16_t *raw = malloc(in_sz);
    uint16_t *dec = calloc(1, in_sz);  /* worst case full res */

    /* Warm-up using first frame */
    {
        FILE *f = fopen(argv[4], "rb");
        fread(raw, 1, in_sz, f); fclose(f);
        unsigned char *out = NULL; size_t out_sz = 0;
        gpr_encode_fused_frame(enc, (unsigned char *)raw, in_sz, &out, &out_sz);
        gpr_encode_fused_frame(enc, (unsigned char *)raw, in_sz, &out, &out_sz);
    }

    fprintf(stderr, "# frame  src                   enc_ms  dec_ms  bytes      dw x dh\n");
    for (int i = 0; i < nframes; i++) {
        const char *src_path = argv[4 + i];
        FILE *f = fopen(src_path, "rb");
        if (!f || fread(raw, 1, in_sz, f) != in_sz) {
            fprintf(stderr, "skip %s\n", src_path); continue;
        }
        fclose(f);

        double t0 = now_ms();
        unsigned char *out = NULL; size_t out_sz = 0;
        gpr_encode_fused_frame(enc, (unsigned char *)raw, in_sz, &out, &out_sz);
        double t1 = now_ms();
        int dw, dh;
        /* First call to discover output dims (decoder writes nothing safe if
           the output is smaller than the buffer with a too-wide pitch). */
        int drc = gpr_decode_fused(out, out_sz, dec, (size_t)W * 2, &dw, &dh);
        if (drc == 0 && (dw != W || dh != H)) {
            /* Re-decode with tight pitch matching the actual output dims. */
            memset(dec, 0, in_sz);
            drc = gpr_decode_fused(out, out_sz, dec, (size_t)dw * 2, &dw, &dh);
        }
        double t2 = now_ms();
        if (drc != 0) { fprintf(stderr, "frame %d DECODE rc=%d\n", i, drc); continue; }

        const char *name = strrchr(src_path, '/'); name = name ? name + 1 : src_path;
        fprintf(stderr, "# %3d    %-22s %6.1f  %6.1f  %-9zu  %4d x %4d\n",
                i, name, t1 - t0, t2 - t1, out_sz, dw, dh);

        /* Write decoded raw (LE u16) and demosaiced PPM */
        char path[512];
        snprintf(path, sizeof(path), "%s_%03d.raw", prefix, i);
        FILE *g = fopen(path, "wb");
        if (g) { fwrite(dec, 2, (size_t)dw * dh, g); fclose(g); }
        snprintf(path, sizeof(path), "%s_%03d.ppm", prefix, i);
        demosaic_to_ppm(dec, dw, dh, 4, path);
    }

    gpr_encode_fused_destroy(enc);
    free(raw); free(dec);
    return 0;
}
