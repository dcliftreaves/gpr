/* Standalone .gpr (FUSED bitstream) → raw bayer decoder.
   For the Pi-capture → desktop-CNN ship-readiness demo.
   Usage: fused_decode_cli in.gpr SENSOR_W SENSOR_H out.raw
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

static double now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1.0e6;
}

int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s in.gpr SENSOR_W SENSOR_H out.raw\n", argv[0]); return 1; }
    int sw = atoi(argv[2]), sh = atoi(argv[3]);
    FILE *f = fopen(argv[1], "rb"); if (!f) { perror("open in"); return 1; }
    fseek(f, 0, SEEK_END); size_t sz = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *enc = malloc(sz);
    if (fread(enc, 1, sz, f) != sz) { fprintf(stderr, "read fail\n"); return 1; }
    fclose(f);
    /* Allocate at sensor dims; decoder may emit half-res for decimated capture
       — still fits in this buffer. Bayer pitch = full sensor width. */
    uint16_t *bayer = (uint16_t *)calloc((size_t)sw * sh, sizeof(uint16_t));
    if (!bayer) { fprintf(stderr, "alloc fail\n"); return 1; }
    int ow = 0, oh = 0;
    double t0 = now_ms();
    int rc = gpr_decode_fused(enc, sz, bayer, (size_t)sw * sizeof(uint16_t), &ow, &oh);
    double t = now_ms() - t0;
    if (rc != 0) { fprintf(stderr, "decode failed rc=%d\n", rc); return 2; }
    fprintf(stderr, "DECODE: %dx%d in %.1f ms (sensor %dx%d, in %zu bytes)\n",
            ow, oh, t, sw, sh, sz);
    /* Write only the actual decoded rect (handle pitch != ow when ow < sw). */
    FILE *fo = fopen(argv[4], "wb"); if (!fo) { perror("open out"); return 1; }
    for (int y = 0; y < oh; y++) {
        fwrite(bayer + (size_t)y * sw, sizeof(uint16_t), ow, fo);
    }
    fclose(fo);
    free(bayer); free(enc);
    return 0;
}
