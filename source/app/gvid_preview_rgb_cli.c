/* .gvid -> Mission 1 1024x768 RGB24 preview frames.
   Usage:
     gvid_preview_rgb_cli in.gvid SENSOR_W SENSOR_H out_dir limit write_frames

   write_frames=1 writes frame_%06d.rgb. write_frames=0 measures only.
*/
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/types.h>

#define GVID_MAGIC 0x44495647u
#define FRAME_MAGIC 0x004D5246u

extern int gpr_decode_fused_ll_preview(const uint8_t *enc, size_t enc_size,
                                       uint16_t *bayer_out, size_t bayer_pitch_bytes,
                                       int *out_width, int *out_height);

typedef struct {
    double decode_ms;
    double isp_ms;
    double write_ms;
    double total_ms;
    uint32_t payload_size;
} Row;

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1.0e6;
}

static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t rd64(const uint8_t *p) {
    uint64_t lo = rd32(p);
    uint64_t hi = rd32(p + 4);
    return lo | (hi << 32);
}

static int percentile_u16_hist(const uint32_t hist[16384], uint32_t total, double frac) {
    uint32_t want = (uint32_t)((double)(total - 1) * frac + 0.5);
    uint32_t seen = 0;
    for (int i = 0; i < 16384; i++) {
        seen += hist[i];
        if (seen > want) return i;
    }
    return 16383;
}

static uint8_t clamp_u8(float v) {
    if (v <= 0.0f) return 0;
    if (v >= 255.0f) return 255;
    return (uint8_t)(v + 0.5f);
}

static int preview_isp_rgb24(const uint16_t *raw, int width, int height,
                             int pitch_pixels, uint8_t *rgb_out) {
    double r_sum = 0.0, g_sum = 0.0, b_sum = 0.0;
    uint32_t blocks = 0;
    for (int y = 0; y < height; y += 2) {
        const uint16_t *row0 = raw + (size_t)y * pitch_pixels;
        const uint16_t *row1 = row0 + pitch_pixels;
        for (int x = 0; x < width; x += 2) {
            r_sum += row0[x];
            g_sum += ((double)row0[x + 1] + (double)row1[x]) * 0.5;
            b_sum += row1[x + 1];
            blocks++;
        }
    }
    float r_gain = (float)((g_sum / blocks) / fmax(r_sum / blocks, 1.0));
    float b_gain = (float)((g_sum / blocks) / fmax(b_sum / blocks, 1.0));
    if (r_gain < 0.25f) r_gain = 0.25f;
    if (r_gain > 4.0f) r_gain = 4.0f;
    if (b_gain < 0.25f) b_gain = 0.25f;
    if (b_gain > 4.0f) b_gain = 4.0f;

    uint32_t hist[16384];
    memset(hist, 0, sizeof(hist));
    for (int y = 0; y < height; y += 2) {
        const uint16_t *row0 = raw + (size_t)y * pitch_pixels;
        const uint16_t *row1 = row0 + pitch_pixels;
        for (int x = 0; x < width; x += 2) {
            float r = row0[x] * r_gain;
            float g = ((float)row0[x + 1] + (float)row1[x]) * 0.5f;
            float b = row1[x + 1] * b_gain;
            int lum = (int)(0.2126f * r + 0.7152f * g + 0.0722f * b + 0.5f);
            if (lum < 0) lum = 0;
            if (lum > 16383) lum = 16383;
            hist[lum]++;
        }
    }

    int lo = percentile_u16_hist(hist, blocks, 0.008);
    int hi = percentile_u16_hist(hist, blocks, 0.998);
    if (hi <= lo + 64) {
        lo = 0;
        hi = 16383;
    }
    uint8_t lut[16384];
    float inv = 1.0f / (float)(hi - lo);
    for (int i = 0; i < 16384; i++) {
        float x = ((float)i - (float)lo) * inv;
        if (x < 0.0f) x = 0.0f;
        if (x > 1.0f) x = 1.0f;
        x = powf(x, 1.0f / 2.25f);
        float xp = powf(x, 1.18f);
        float yp = powf(1.0f - x, 1.18f);
        x = xp / (xp + yp + 1.0e-9f);
        lut[i] = clamp_u8(x * 255.0f);
    }

    for (int y = 0; y < height; y += 2) {
        const uint16_t *row0 = raw + (size_t)y * pitch_pixels;
        const uint16_t *row1 = row0 + pitch_pixels;
        uint8_t *out0 = rgb_out + (size_t)y * width * 3;
        uint8_t *out1 = out0 + (size_t)width * 3;
        for (int x = 0; x < width; x += 2) {
            int rv = (int)(row0[x] * r_gain + 0.5f);
            int gv = (int)(((float)row0[x + 1] + (float)row1[x]) * 0.5f + 0.5f);
            int bv = (int)(row1[x + 1] * b_gain + 0.5f);
            if (rv < 0) rv = 0; if (rv > 16383) rv = 16383;
            if (gv < 0) gv = 0; if (gv > 16383) gv = 16383;
            if (bv < 0) bv = 0; if (bv > 16383) bv = 16383;
            float r = lut[rv], g = lut[gv], b = lut[bv];
            float lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;
            r = lum + (r - lum) * 1.12f;
            g = lum + (g - lum) * 1.12f;
            b = lum + (b - lum) * 1.12f;
            uint8_t r8 = clamp_u8(r), g8 = clamp_u8(g), b8 = clamp_u8(b);
            size_t p = (size_t)x * 3;
            out0[p + 0] = r8; out0[p + 1] = g8; out0[p + 2] = b8;
            out0[p + 3] = r8; out0[p + 4] = g8; out0[p + 5] = b8;
            out1[p + 0] = r8; out1[p + 1] = g8; out1[p + 2] = b8;
            out1[p + 3] = r8; out1[p + 4] = g8; out1[p + 5] = b8;
        }
    }
    return 0;
}

static int cmp_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

static double median_of(const Row *rows, int n, int field) {
    double *vals = (double *)malloc((size_t)n * sizeof(double));
    for (int i = 0; i < n; i++) {
        vals[i] = field == 0 ? rows[i].decode_ms : field == 1 ? rows[i].isp_ms :
                  field == 2 ? rows[i].write_ms : rows[i].total_ms;
    }
    qsort(vals, (size_t)n, sizeof(double), cmp_double);
    double med = (n & 1) ? vals[n / 2] : (vals[n / 2 - 1] + vals[n / 2]) * 0.5;
    free(vals);
    return med;
}

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr, "usage: %s in.gvid SENSOR_W SENSOR_H out_dir limit write_frames\n", argv[0]);
        return 1;
    }
    const char *gvid_path = argv[1];
    int sensor_w = atoi(argv[2]);
    int sensor_h = atoi(argv[3]);
    const char *out_dir = argv[4];
    int limit = atoi(argv[5]);
    int write_frames = atoi(argv[6]);
    int preview_w = sensor_w / 4;
    int preview_h = sensor_h / 4;

    mkdir(out_dir, 0775);
    char frames_dir[1024];
    snprintf(frames_dir, sizeof(frames_dir), "%s/frames_rgb", out_dir);
    if (write_frames) mkdir(frames_dir, 0775);

    FILE *in = fopen(gvid_path, "rb");
    if (!in) { perror("open gvid"); return 2; }
    uint8_t hdr[32];
    if (fread(hdr, 1, sizeof(hdr), in) != sizeof(hdr) || rd32(hdr) != GVID_MAGIC) {
        fprintf(stderr, "bad gvid header\n");
        fclose(in);
        return 3;
    }
    uint32_t frame_hint = rd32(hdr + 28);
    if (limit <= 0 || (frame_hint && (uint32_t)limit > frame_hint)) limit = (int)frame_hint;
    if (limit <= 0) limit = 1000000;

    uint16_t *bayer = (uint16_t *)malloc((size_t)preview_w * preview_h * sizeof(uint16_t));
    uint8_t *rgb = (uint8_t *)malloc((size_t)preview_w * preview_h * 3);
    uint8_t *payload = NULL;
    size_t payload_cap = 0;
    Row *rows = (Row *)calloc((size_t)limit, sizeof(Row));
    if (!bayer || !rgb || !rows) return 4;

    int count = 0;
    for (; count < limit; count++) {
        uint8_t fh[16];
        if (fread(fh, 1, sizeof(fh), in) != sizeof(fh)) break;
        if (rd32(fh) != FRAME_MAGIC) { fprintf(stderr, "bad frame magic\n"); break; }
        uint32_t payload_size = rd32(fh + 4);
        (void)rd64(fh + 8);
        if (payload_size > payload_cap) {
            uint8_t *np = (uint8_t *)realloc(payload, payload_size);
            if (!np) return 5;
            payload = np;
            payload_cap = payload_size;
        }
        if (fread(payload, 1, payload_size, in) != payload_size) break;

        double t0 = now_ms();
        int ow = 0, oh = 0;
        int rc = gpr_decode_fused_ll_preview(payload, payload_size, bayer,
                                             (size_t)preview_w * sizeof(uint16_t), &ow, &oh);
        double t1 = now_ms();
        if (rc != 0 || ow != preview_w || oh != preview_h) {
            fprintf(stderr, "decode failed frame=%d rc=%d dims=%dx%d\n", count, rc, ow, oh);
            break;
        }
        rc = preview_isp_rgb24(bayer, preview_w, preview_h, preview_w, rgb);
        double t2 = now_ms();
        if (rc != 0) break;
        if (write_frames) {
            char path[1200];
            snprintf(path, sizeof(path), "%s/frame_%06d.rgb", frames_dir, count);
            FILE *out = fopen(path, "wb");
            if (!out) return 6;
            fwrite(rgb, 1, (size_t)preview_w * preview_h * 3, out);
            fclose(out);
        }
        double t3 = now_ms();
        rows[count].decode_ms = t1 - t0;
        rows[count].isp_ms = t2 - t1;
        rows[count].write_ms = t3 - t2;
        rows[count].total_ms = t3 - t0;
        rows[count].payload_size = payload_size;
        if ((count + 1) % 50 == 0) fprintf(stderr, "%d frames\n", count + 1);
    }
    fclose(in);

    char receipt_path[1024];
    snprintf(receipt_path, sizeof(receipt_path), "%s/receipt.json", out_dir);
    FILE *receipt = fopen(receipt_path, "w");
    if (receipt) {
        double dec_med = median_of(rows, count, 0);
        double isp_med = median_of(rows, count, 1);
        double wr_med = median_of(rows, count, 2);
        double total_med = median_of(rows, count, 3);
        fprintf(receipt,
                "{\n"
                "  \"schema\": \"gvid_preview_rgb_cli.v1\",\n"
                "  \"gvid\": \"%s\",\n"
                "  \"frames\": %d,\n"
                "  \"width\": %d,\n"
                "  \"height\": %d,\n"
                "  \"write_frames\": %d,\n"
                "  \"summary\": {\n"
                "    \"decode_ms_median\": %.3f,\n"
                "    \"isp_ms_median\": %.3f,\n"
                "    \"write_ms_median\": %.3f,\n"
                "    \"total_ms_median\": %.3f,\n"
                "    \"total_fps_median\": %.3f\n"
                "  }\n"
                "}\n",
                gvid_path, count, preview_w, preview_h, write_frames,
                dec_med, isp_med, wr_med, total_med, total_med > 0.0 ? 1000.0 / total_med : 0.0);
        fclose(receipt);
        fprintf(stderr, "receipt %s\n", receipt_path);
    }

    free(rows);
    free(payload);
    free(rgb);
    free(bayer);
    return count > 0 ? 0 : 7;
}
