/*
 * test_gpr_polish — smoke test for the CoreML-backed polish library.
 *
 * Behavior:
 *   - asserts gpr_polish_available() is true on Apple builds.
 *   - asserts gpr_polish_create(NULL) returns NULL (graceful).
 *   - if argv[1] is supplied (path to a .mlpackage or .mlmodelc), also runs
 *     a full apply() against a deterministic synthetic Bayer tile and
 *     verifies output is finite and in-range.
 *
 * The model-path arg is optional so CI can exercise the load-paths even
 * when no model is shipped. The encoder API integration (gpr_video_encoder
 * --polish flag) is tested separately once it lands.
 */

#include "gpr_polish.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int test_available_and_null(void)
{
    if (!gpr_polish_available()) {
        fprintf(stderr, "FAIL: gpr_polish_available() returned false on this build\n");
        return 1;
    }
    if (gpr_polish_create(NULL) != NULL) {
        fprintf(stderr, "FAIL: gpr_polish_create(NULL) did not return NULL\n");
        return 1;
    }
    printf("OK: available() && create(NULL) graceful\n");
    return 0;
}

static int test_apply(const char *model_path)
{
    gpr_polish_t *p = gpr_polish_create(model_path);
    if (!p) {
        fprintf(stderr, "FAIL: gpr_polish_create(\"%s\") returned NULL\n", model_path);
        return 1;
    }

    const int W = 512, H = 512;
    uint16_t *bayer = (uint16_t *)malloc((size_t)W * H * sizeof(uint16_t));
    if (!bayer) { gpr_polish_destroy(p); return 1; }

    /* Deterministic ramp — easy to eyeball, not all the same value. */
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            uint32_t v = (uint32_t)((y * 17u + x * 31u) & 0x3FFF); /* 14-bit */
            bayer[y * W + x] = (uint16_t)v;
        }
    }

    double est = gpr_polish_estimate_ms(p, W, H);
    printf("estimate_ms(%dx%d) = %.1f\n", W, H, est);

    int rc = gpr_polish_apply(p, bayer, W, H, W * 2, /*quality=*/3);
    if (rc != 0) {
        fprintf(stderr, "FAIL: gpr_polish_apply rc=%d\n", rc);
        free(bayer); gpr_polish_destroy(p); return 1;
    }

    /* Verify output is in 14-bit range and not all-zero. */
    uint32_t sum = 0;
    uint16_t maxv = 0;
    for (int i = 0; i < W * H; i++) {
        if (bayer[i] > 16383) {
            fprintf(stderr, "FAIL: out-of-range value %u at index %d\n", bayer[i], i);
            free(bayer); gpr_polish_destroy(p); return 1;
        }
        sum += bayer[i];
        if (bayer[i] > maxv) maxv = bayer[i];
    }
    if (sum == 0 || maxv == 0) {
        fprintf(stderr, "FAIL: output looks all-zero (sum=%u max=%u)\n", sum, maxv);
        free(bayer); gpr_polish_destroy(p); return 1;
    }
    printf("OK: apply() finished, sum=%u max=%u mean=%.1f\n",
           sum, maxv, sum / (double)(W * H));

    free(bayer);
    gpr_polish_destroy(p);
    return 0;
}

int main(int argc, char **argv)
{
    if (test_available_and_null()) return 1;

    if (argc >= 2) {
        printf("running apply() test with model: %s\n", argv[1]);
        if (test_apply(argv[1])) return 1;
    } else {
        printf("skipping apply() test (no model path given)\n");
    }
    printf("PASS\n");
    return 0;
}
