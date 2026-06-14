/* Standalone .gpr (FUSED bitstream) -> raw bayer decoder.
   For the Pi-capture -> desktop-CNN ship-readiness demo.
   Usage: fused_decode_cli in.gpr SENSOR_W SENSOR_H out.raw [4k_raw_1x|2k_raw_0p5x]
*/
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

extern int gpr_decode_fused(const uint8_t *enc, size_t enc_size,
                            uint16_t *bayer_out, size_t bayer_pitch_bytes,
                            int *out_width, int *out_height);
extern int gpr_decode_fused_halfres(const uint8_t *enc, size_t enc_size,
                                    uint16_t *bayer_out, size_t bayer_pitch_bytes,
                                    int *out_width, int *out_height);

static double now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1.0e6;
}

static uint16_t avg4_u16(uint16_t a, uint16_t b, uint16_t c, uint16_t d) {
    return (uint16_t)(((uint32_t)a + (uint32_t)b + (uint32_t)c + (uint32_t)d + 2u) >> 2);
}

static int downsample_bayer_0p5x_cfa(const uint16_t *src, int src_w, int src_h,
                                     int src_pitch_pixels, uint16_t *dst,
                                     int *dst_w, int *dst_h) {
    if (!src || !dst || !dst_w || !dst_h) return -1;
    if ((src_w % 4) != 0 || (src_h % 4) != 0) return -2;

    int out_w = src_w / 2;
    int out_h = src_h / 2;
    for (int y = 0; y < out_h; y++) {
        int phase_y = y & 1;
        int plane_y = y >> 1;
        int sy0 = phase_y + plane_y * 4;
        int sy1 = sy0 + 2;
        const uint16_t *row0 = src + (size_t)sy0 * src_pitch_pixels;
        const uint16_t *row1 = src + (size_t)sy1 * src_pitch_pixels;
        uint16_t *out_row = dst + (size_t)y * out_w;
        for (int x = 0; x < out_w; x++) {
            int phase_x = x & 1;
            int plane_x = x >> 1;
            int sx0 = phase_x + plane_x * 4;
            int sx1 = sx0 + 2;
            out_row[x] = avg4_u16(row0[sx0], row0[sx1], row1[sx0], row1[sx1]);
        }
    }
    *dst_w = out_w;
    *dst_h = out_h;
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr, "usage: %s in.gpr SENSOR_W SENSOR_H out.raw [4k_raw_1x|2k_raw_0p5x]\n", argv[0]);
        return 1;
    }
    const char *target = (argc >= 6) ? argv[5] : "4k_raw_1x";
    int target_2k = strcmp(target, "2k_raw_0p5x") == 0;
    if (!target_2k && strcmp(target, "4k_raw_1x") != 0) {
        fprintf(stderr, "unknown target '%s' (expected 4k_raw_1x or 2k_raw_0p5x)\n", target);
        return 1;
    }
    int sw = atoi(argv[2]), sh = atoi(argv[3]);
    FILE *f = fopen(argv[1], "rb"); if (!f) { perror("open in"); return 1; }
    fseek(f, 0, SEEK_END); size_t sz = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *enc = malloc(sz);
    if (fread(enc, 1, sz, f) != sz) { fprintf(stderr, "read fail\n"); free(enc); fclose(f); return 1; }
    fclose(f);
    /* Allocate at sensor dims; decoder may emit half-res for decimated capture
       — still fits in this buffer. Bayer pitch = full sensor width. */
    uint16_t *bayer = (uint16_t *)calloc((size_t)sw * sh, sizeof(uint16_t));
    if (!bayer) { fprintf(stderr, "alloc fail\n"); return 1; }
    int ow = 0, oh = 0;
    double t0 = now_ms();
    int rc = target_2k
        ? gpr_decode_fused_halfres(enc, sz, bayer, (size_t)sw * sizeof(uint16_t), &ow, &oh)
        : gpr_decode_fused(enc, sz, bayer, (size_t)sw * sizeof(uint16_t), &ow, &oh);
    double t = now_ms() - t0;
    if (rc != 0) { fprintf(stderr, "decode failed rc=%d\n", rc); free(bayer); free(enc); return 2; }
    fprintf(stderr, "DECODE: %dx%d in %.1f ms (sensor %dx%d, in %zu bytes)\n",
            ow, oh, t, sw, sh, sz);

    uint16_t *out_bayer = bayer;
    int out_w = ow, out_h = oh, out_pitch = sw;
    double target_ms = 0.0;
    if (target_2k && (ow != sw / 4 || oh != sh / 4)) {
        out_w = ow / 2;
        out_h = oh / 2;
        out_pitch = out_w;
        out_bayer = (uint16_t *)malloc((size_t)out_w * out_h * sizeof(uint16_t));
        if (!out_bayer) { fprintf(stderr, "target alloc fail\n"); free(bayer); free(enc); return 1; }
        double td0 = now_ms();
        int trc = downsample_bayer_0p5x_cfa(bayer, ow, oh, sw, out_bayer, &out_w, &out_h);
        target_ms = now_ms() - td0;
        if (trc != 0) {
            fprintf(stderr, "target downsample failed rc=%d\n", trc);
            free(out_bayer); free(bayer); free(enc);
            return 3;
        }
        fprintf(stderr, "TARGET: %s %dx%d in %.1f ms\n", target, out_w, out_h, target_ms);
    } else {
        fprintf(stderr, "TARGET: %s %dx%d in %.1f ms\n", target, out_w, out_h, target_ms);
    }

    /* Write only the target rect (handle pitch != width for direct decode). */
    FILE *fo = fopen(argv[4], "wb");
    if (!fo) {
        perror("open out");
        if (out_bayer != bayer) free(out_bayer);
        free(bayer); free(enc);
        return 1;
    }
    for (int y = 0; y < out_h; y++) {
        fwrite(out_bayer + (size_t)y * out_pitch, sizeof(uint16_t), out_w, fo);
    }
    fclose(fo);
    if (out_bayer != bayer) free(out_bayer);
    free(bayer); free(enc);
    return 0;
}
