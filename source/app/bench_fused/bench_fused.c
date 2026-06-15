/* Clean per-frame microbenchmark for the fused encoder.
 *
 * No producer/consumer threading, no memcpy per frame, no malloc churn.
 * Encodes the same raw buffer N times against a persistent encoder context
 * and reports min/p25/median/p75/max + fps.
 *
 * Usage: bench_clean <raw_file> <width> <height> <n_iters>
 *
 * The Bayer pattern defaults to pixel_format = 4 (RGGB16). Override with
 * GPR_BENCH_PIXEL_FORMAT=<0..5>.
 * To force quality, set FUSED_QUALITY=<0..11>.
 *
 * Companion to tools/pi_benchmark.sh (which sweeps env flags).
 */
#define _POSIX_C_SOURCE 200809L  /* snprintf, etc. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#include "gpr_video_format.h"

typedef struct FUSED_ENCODER FUSED_ENCODER;
extern FUSED_ENCODER *gpr_encode_fused_create(int w, int h, int pf, int q);
extern int gpr_encode_fused_frame(FUSED_ENCODER *ctx, const unsigned char *raw,
                                   size_t sz, unsigned char **out, size_t *out_sz);
extern void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);
extern void gpr_encode_fused_set_denoise(FUSED_ENCODER *ctx,
                                         double noise_scale,
                                         double noise_offset,
                                         double strength);

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1.0e6;
}

int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s raw w h n\n", argv[0]); return 1; }
    const char *path = argv[1];
    int w = atoi(argv[2]), h = atoi(argv[3]), n = atoi(argv[4]);
    size_t sz = (size_t)w * h * 2;
    unsigned char *raw = malloc(sz);
    FILE *f = fopen(path, "rb");
    if (!f || fread(raw, 1, sz, f) != sz) { fprintf(stderr, "read fail\n"); return 1; }
    fclose(f);

    /* Pre-fault the raw input so the first read isn't paying for it. */
    volatile uint32_t sink = 0;
    for (size_t i = 0; i < sz; i += 4096) sink += raw[i];
    (void)sink;

    int quality = 3;
    {
        const char *q_env = getenv("FUSED_QUALITY");
        if (q_env && *q_env) {
            char *end = NULL;
            long q = strtol(q_env, &end, 10);
            if (end != q_env && q >= 0 && q <= 11) {
                quality = (int)q;
            } else {
                fprintf(stderr, "invalid FUSED_QUALITY=%s (expected 0..11)\n", q_env);
                return 1;
            }
        }
    }
    int bench_pixel_format = 4;
    {
        const char *pf_env = getenv("GPR_BENCH_PIXEL_FORMAT");
        if (pf_env && *pf_env) {
            char *end = NULL;
            long pf = strtol(pf_env, &end, 10);
            if (end != pf_env && pf >= 0 && pf <= 5) {
                bench_pixel_format = (int)pf;
            } else {
                fprintf(stderr, "invalid GPR_BENCH_PIXEL_FORMAT=%s (expected 0..5)\n", pf_env);
                return 1;
            }
        }
    }

    FUSED_ENCODER *enc = gpr_encode_fused_create(w, h, bench_pixel_format, quality);
    if (!enc) { fprintf(stderr, "create fail\n"); return 1; }

    /* Optional BayesShrink wavelet-domain denoise — set GPR_BENCH_DENOISE=<strength>
       (typically 0.5–1.0). Requires FUSED_INLINE_TOKENIZE=0 (split mode) — the
       encoder rejects the call otherwise. Set GPR_BENCH_NOISE_SCALE / OFFSET
       to pass calibrated NoiseProfile (default 0 = use MAD estimate). */
    {
        const char *e = getenv("GPR_BENCH_DENOISE");
        if (e && *e) {
            double strength = atof(e);
            const char *ns_env = getenv("GPR_BENCH_NOISE_SCALE");
            const char *no_env = getenv("GPR_BENCH_NOISE_OFFSET");
            double ns = ns_env ? atof(ns_env) : 0.0;
            double no = no_env ? atof(no_env) : 0.0;
            fprintf(stderr, "# denoise: strength=%.2f scale=%g offset=%g\n",
                    strength, ns, no);
            gpr_encode_fused_set_denoise(enc, ns, no, strength);
        }
    }

    /* 2 warm-up frames not counted */
    for (int i = 0; i < 2; i++) {
        unsigned char *out = NULL; size_t out_sz = 0;
        gpr_encode_fused_frame(enc, raw, sz, &out, &out_sz);
    }

    /* Optional output dump for byte-identity testing: write the first frame's
       encoded bytes to GPR_BENCH_DUMP path, then continue benchmarking.

       Optional sustained-write benchmarking: set GPR_BENCH_WRITE_ALL=<dir>
       to write every encoded frame as frame_NNNN.gpr inside <dir>. Frame
       times then include the fwrite, which is the right measurement for
       "can this hardware actually capture at 24 fps to this storage?"
       Use a path that bypasses tmpfs (e.g. /mnt/ssd, not /tmp) and run
       n ≥ 10 × fps_target so the kernel page cache is exhausted (see
       feedback_honest_capture_bench: short runs are misleading).

       Optional direct-container benchmarking: set GPR_BENCH_GVID=<path> to
       write a strict .gvid stream sequentially as frames are encoded. This is
       closer to the camera/container path than GPR_BENCH_WRITE_ALL because it
       avoids per-frame open/close and the post-run pack step.

       If multiple output env vars are set, GPR_BENCH_DUMP still gets the first
       frame for byte-identity tests, GPR_BENCH_WRITE_ALL writes ALL frames to
       its own directory, and GPR_BENCH_GVID appends ALL frames to one stream. */
    const char *dump_path = getenv("GPR_BENCH_DUMP");
    const char *write_all_dir = getenv("GPR_BENCH_WRITE_ALL");
    const char *gvid_path = getenv("GPR_BENCH_GVID");
    if (write_all_dir && *write_all_dir) {
        /* mkdir -p best effort; ignore errors (caller is responsible) */
        char mkdir_cmd[1024];
        snprintf(mkdir_cmd, sizeof(mkdir_cmd), "mkdir -p '%s'", write_all_dir);
        (void)!system(mkdir_cmd);
        fprintf(stderr, "# GPR_BENCH_WRITE_ALL=%s — frame times will include fwrite\n",
                write_all_dir);
    }
    FILE *gvid_fp = NULL;
    if (gvid_path && *gvid_path) {
        gvid_fp = fopen(gvid_path, "wb");
        if (!gvid_fp) {
            fprintf(stderr, "open GPR_BENCH_GVID=%s failed\n", gvid_path);
            return 1;
        }
        uint8_t clip_header[GPR_VIDEO_CLIP_HEADER_SIZE];
        int n_header = gpr_video_write_clip_header(
            clip_header, sizeof(clip_header),
            w, h, bench_pixel_format, quality, 24.0,
            /*target_MBps=*/0.0, /*denoise_enabled=*/0,
            (uint32_t)n);
        if (n_header != GPR_VIDEO_CLIP_HEADER_SIZE ||
            fwrite(clip_header, 1, sizeof(clip_header), gvid_fp) != sizeof(clip_header)) {
            fprintf(stderr, "write GPR_BENCH_GVID clip header failed\n");
            fclose(gvid_fp);
            return 1;
        }
        fprintf(stderr, "# GPR_BENCH_GVID=%s - frame times will include sequential .gvid fwrite\n",
                gvid_path);
    }
    double *times = malloc((size_t)n * sizeof(double));
    for (int i = 0; i < n; i++) {
        double t0 = now_ms();
        unsigned char *out = NULL; size_t out_sz = 0;
        gpr_encode_fused_frame(enc, raw, sz, &out, &out_sz);
        if (gvid_fp && out && out_sz > 0) {
            uint8_t frame_header[GPR_VIDEO_FRAME_HEADER_SIZE];
            int n_frame = gpr_video_write_frame_header(
                frame_header, sizeof(frame_header), out_sz, (uint64_t)i);
            if (n_frame != GPR_VIDEO_FRAME_HEADER_SIZE ||
                fwrite(frame_header, 1, sizeof(frame_header), gvid_fp) != sizeof(frame_header) ||
                fwrite(out, 1, out_sz, gvid_fp) != out_sz) {
                fprintf(stderr, "write GPR_BENCH_GVID frame %d failed\n", i);
                fclose(gvid_fp);
                return 1;
            }
        }
        if (write_all_dir && *write_all_dir && out && out_sz > 0) {
            char path[1280];
            snprintf(path, sizeof(path), "%s/frame_%04d.gpr", write_all_dir, i);
            FILE *wf = fopen(path, "wb");
            if (wf) {
                fwrite(out, 1, out_sz, wf);
                fclose(wf);
            }
        }
        double t1 = now_ms();
        times[i] = t1 - t0;
        if (i == 0 && dump_path && out && out_sz > 0) {
            FILE *df = fopen(dump_path, "wb");
            if (df) { fwrite(out, 1, out_sz, df); fclose(df); }
            fprintf(stderr, "# dumped frame 0 (%zu bytes) to %s\n", out_sz, dump_path);
        }
    }
    printf("# frame_ms\n");
    for (int i = 0; i < n; i++) printf("%.2f\n", times[i]);

    /* Sort to find quartiles */
    for (int i = 0; i < n; i++)
        for (int j = i+1; j < n; j++)
            if (times[j] < times[i]) { double t = times[i]; times[i] = times[j]; times[j] = t; }
    double sum = 0, sum_sq = 0;
    for (int i = 0; i < n; i++) { sum += times[i]; sum_sq += times[i]*times[i]; }
    double mean = sum / n;
    double var = sum_sq / n - mean * mean;
    fprintf(stderr,
        "# n=%d  mean=%.2f  stddev=%.2f  min=%.2f  p25=%.2f  median=%.2f  p75=%.2f  max=%.2f\n",
        n, mean, var > 0 ? __builtin_sqrt(var) : 0,
        times[0], times[n/4], times[n/2], times[3*n/4], times[n-1]);
    fprintf(stderr,
        "# fps_mean=%.2f  fps_median=%.2f  fps_p25(fast)=%.2f\n",
        1000.0/mean, 1000.0/times[n/2], 1000.0/times[n/4]);

    if (gvid_fp) {
        fflush(gvid_fp);
        fclose(gvid_fp);
    }
    gpr_encode_fused_destroy(enc);
    return 0;
}
