/*
 * gpr_polish — CoreML-backed Bayer polish implementation.
 *
 * Objective-C++ so we can call CoreML from C-only callers via the gpr_polish.h
 * C interface. Compiled only on Apple platforms; the build system should
 * substitute a stub on non-Apple targets so callers can compile uniformly.
 *
 * Tile pipeline:
 *   - input: uint16 Bayer (H, W), 14-bit values
 *   - per tile (256x256 Bayer = 128x128 unshuffled 4ch):
 *       1. pixel-unshuffle to (4, 128, 128) float32 in [0, 1]
 *       2. build one-hot quality plane (4, 128, 128)
 *       3. run CoreML model -> (4, 128, 128) cleaned float32
 *       4. pixel-shuffle back to (256, 256) uint16
 *   - tile overlap with cosine blend to hide seams
 */

#include "gpr_polish.h"

#import <Foundation/Foundation.h>
#import <CoreML/CoreML.h>

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define TILE_BAYER 256          /* Bayer pixels per tile side */
#define TILE_UN    128          /* unshuffled pixels per tile side */
#define OVERLAP_BAYER 32        /* Bayer pixels of overlap */
#define STRIDE_BAYER (TILE_BAYER - OVERLAP_BAYER)

struct gpr_polish_s {
    MLModel *model;             /* CoreML model, retained */
    NSString *model_path;
};

static const float NORM = 1.0f / 16383.0f;  /* 14-bit -> [0,1] */
static const float DENORM = 16383.0f;

gpr_polish_t *gpr_polish_create(const char *model_path)
{
    if (!model_path) return NULL;
    NSError *err = nil;
    NSString *path = [NSString stringWithUTF8String:model_path];
    NSURL *url = [NSURL fileURLWithPath:path];

    /* Compile the .mlpackage if needed (CoreML expects .mlmodelc). */
    NSURL *compiled = url;
    if (![path hasSuffix:@".mlmodelc"]) {
        compiled = [MLModel compileModelAtURL:url error:&err];
        if (err) {
            NSLog(@"gpr_polish: compile failed: %@", err);
            return NULL;
        }
    }

    MLModelConfiguration *cfg = [MLModelConfiguration new];
    cfg.computeUnits = MLComputeUnitsAll;  /* ANE + GPU + CPU */
    MLModel *m = [MLModel modelWithContentsOfURL:compiled configuration:cfg error:&err];
    if (err) {
        NSLog(@"gpr_polish: model load failed: %@", err);
        return NULL;
    }

    gpr_polish_t *p = (gpr_polish_t *)calloc(1, sizeof(*p));
    p->model = m;
    p->model_path = path;
    return p;
}

void gpr_polish_destroy(gpr_polish_t *p)
{
    if (!p) return;
    p->model = nil;
    p->model_path = nil;
    free(p);
}

bool gpr_polish_available(void)
{
#if __has_include(<CoreML/CoreML.h>)
    return true;
#else
    return false;
#endif
}

double gpr_polish_estimate_ms(const gpr_polish_t *p, int width, int height)
{
    if (!p || !p->model) return -1.0;
    /* Empirical from M-series ANE: ~1.3 ms per 256x256 tile.
       Tile count = ceil(width/STRIDE) * ceil(height/STRIDE). */
    int tiles_x = (width + STRIDE_BAYER - 1) / STRIDE_BAYER;
    int tiles_y = (height + STRIDE_BAYER - 1) / STRIDE_BAYER;
    int total_tiles = tiles_x * tiles_y;
    return total_tiles * 1.3;
}

/* Pixel unshuffle: (256, 256) uint16 Bayer in [0, 16383] -> (4, 128, 128) float32 in [0, 1]
 *   plane 0: R  (y even, x even)
 *   plane 1: G1 (y even, x odd)
 *   plane 2: G2 (y odd,  x even)
 *   plane 3: B  (y odd,  x odd)
 */
static void unshuffle_tile(const uint16_t *bayer, int stride_pixels,
                           float *out)
{
    /* out has layout (4, 128, 128) contiguous */
    const int H = TILE_UN, W = TILE_UN;
    for (int y = 0; y < H; y++) {
        const uint16_t *r_row1 = bayer + (2*y)     * stride_pixels;
        const uint16_t *r_row2 = bayer + (2*y + 1) * stride_pixels;
        float *p0 = out + 0 * H * W + y * W;
        float *p1 = out + 1 * H * W + y * W;
        float *p2 = out + 2 * H * W + y * W;
        float *p3 = out + 3 * H * W + y * W;
        for (int x = 0; x < W; x++) {
            p0[x] = r_row1[2*x]     * NORM;
            p1[x] = r_row1[2*x + 1] * NORM;
            p2[x] = r_row2[2*x]     * NORM;
            p3[x] = r_row2[2*x + 1] * NORM;
        }
    }
}

/* Inverse of unshuffle. Caller provides write-back stride. */
static void shuffle_tile(const float *in,
                         uint16_t *bayer, int stride_pixels)
{
    const int H = TILE_UN, W = TILE_UN;
    for (int y = 0; y < H; y++) {
        const float *p0 = in + 0 * H * W + y * W;
        const float *p1 = in + 1 * H * W + y * W;
        const float *p2 = in + 2 * H * W + y * W;
        const float *p3 = in + 3 * H * W + y * W;
        uint16_t *r1 = bayer + (2*y)     * stride_pixels;
        uint16_t *r2 = bayer + (2*y + 1) * stride_pixels;
        for (int x = 0; x < W; x++) {
            float v0 = p0[x] * DENORM; if (v0 < 0) v0 = 0; if (v0 > 16383) v0 = 16383;
            float v1 = p1[x] * DENORM; if (v1 < 0) v1 = 0; if (v1 > 16383) v1 = 16383;
            float v2 = p2[x] * DENORM; if (v2 < 0) v2 = 0; if (v2 > 16383) v2 = 16383;
            float v3 = p3[x] * DENORM; if (v3 < 0) v3 = 0; if (v3 > 16383) v3 = 16383;
            r1[2*x]     = (uint16_t)(v0 + 0.5f);
            r1[2*x + 1] = (uint16_t)(v1 + 0.5f);
            r2[2*x]     = (uint16_t)(v2 + 0.5f);
            r2[2*x + 1] = (uint16_t)(v3 + 0.5f);
        }
    }
}

int gpr_polish_apply(gpr_polish_t *p,
                     uint16_t *bayer,
                     int width, int height,
                     int stride_bytes,
                     int quality)
{
    if (!p || !p->model || !bayer) return -1;
    if (width % 2 || height % 2) return -2;
    if (quality < 0 || quality > 3) return -3;
    int stride_pixels = stride_bytes / 2;

    @autoreleasepool {
        /* Allocate workspace: one tile of input float32 + output float32. */
        size_t plane_size = TILE_UN * TILE_UN;
        size_t tile_floats = 4 * plane_size;

        /* Pre-build the quality plane (one-hot) — same for every tile. */
        NSArray *q_shape = @[@1, @4, @TILE_UN, @TILE_UN];
        NSError *err = nil;
        MLMultiArray *q_plane = [[MLMultiArray alloc] initWithShape:q_shape
                                                            dataType:MLMultiArrayDataTypeFloat32
                                                               error:&err];
        if (err) return -10;
        float *q_data = (float *)q_plane.dataPointer;
        memset(q_data, 0, tile_floats * sizeof(float));
        /* Set channel `quality` to 1.0 everywhere. */
        float *q_ch = q_data + quality * plane_size;
        for (size_t i = 0; i < plane_size; i++) q_ch[i] = 1.0f;

        /* Bayer input/output MLMultiArrays. */
        NSArray *shape = @[@1, @4, @TILE_UN, @TILE_UN];
        MLMultiArray *in_arr = [[MLMultiArray alloc] initWithShape:shape
                                                          dataType:MLMultiArrayDataTypeFloat32
                                                             error:&err];
        if (err) return -11;

        /* Compute tile positions. Bayer-aligned (even offsets). */
        int tiles_y = (height + STRIDE_BAYER - 1) / STRIDE_BAYER;
        int tiles_x = (width  + STRIDE_BAYER - 1) / STRIDE_BAYER;
        /* Edge tiles snap to width-TILE_BAYER / height-TILE_BAYER. */
        int *ys = (int *)malloc(sizeof(int) * tiles_y);
        int *xs = (int *)malloc(sizeof(int) * tiles_x);
        for (int i = 0; i < tiles_y; i++) {
            ys[i] = (i * STRIDE_BAYER) & ~1;
            if (ys[i] + TILE_BAYER > height) ys[i] = (height - TILE_BAYER) & ~1;
        }
        for (int i = 0; i < tiles_x; i++) {
            xs[i] = (i * STRIDE_BAYER) & ~1;
            if (xs[i] + TILE_BAYER > width) xs[i] = (width - TILE_BAYER) & ~1;
        }

        /* Output accumulator (float). We'll average overlapping tiles with unit weights. */
        float *acc = (float *)calloc((size_t)width * height, sizeof(float) * 4);
        float *cnt = (float *)calloc((size_t)width * height, sizeof(float));
        if (!acc || !cnt) { free(acc); free(cnt); free(ys); free(xs); return -12; }

        for (int iy = 0; iy < tiles_y; iy++) {
            for (int ix = 0; ix < tiles_x; ix++) {
                int y0 = ys[iy], x0 = xs[ix];

                /* Unshuffle this tile into in_arr. */
                unshuffle_tile(bayer + y0 * stride_pixels + x0,
                                stride_pixels,
                                (float *)in_arr.dataPointer);

                /* Run CoreML. */
                MLFeatureValue *bayer_fv = [MLFeatureValue featureValueWithMultiArray:in_arr];
                MLFeatureValue *q_fv = [MLFeatureValue featureValueWithMultiArray:q_plane];
                NSDictionary *features = @{@"bayer": bayer_fv, @"q_plane": q_fv};
                MLDictionaryFeatureProvider *prov = [[MLDictionaryFeatureProvider alloc]
                                                      initWithDictionary:features error:&err];
                if (err) {
                    free(acc); free(cnt); free(ys); free(xs);
                    return -20;
                }
                id<MLFeatureProvider> out = [p->model predictionFromFeatures:prov error:&err];
                if (err) {
                    free(acc); free(cnt); free(ys); free(xs);
                    return -21;
                }
                MLMultiArray *out_arr = [[out featureValueForName:@"cleaned"] multiArrayValue];
                const float *out_data = (const float *)out_arr.dataPointer;

                /* Shuffle output back into a temporary Bayer tile, then accumulate. */
                /* Direct write into accumulator: for each pixel in tile, add to acc[y, x].
                   But output is in unshuffled layout; we shuffle then accumulate. */
                uint16_t tile_out[TILE_BAYER * TILE_BAYER];
                /* Use a temporary stride of TILE_BAYER for the tile-local write. */
                shuffle_tile(out_data, tile_out, TILE_BAYER);
                for (int dy = 0; dy < TILE_BAYER; dy++) {
                    for (int dx = 0; dx < TILE_BAYER; dx++) {
                        int gy = y0 + dy, gx = x0 + dx;
                        if (gy >= height || gx >= width) continue;
                        size_t idx = (size_t)gy * width + gx;
                        acc[idx] += (float)tile_out[dy * TILE_BAYER + dx];
                        cnt[idx] += 1.0f;
                    }
                }
            }
        }

        /* Average and write back into bayer. */
        for (int y = 0; y < height; y++) {
            uint16_t *row = bayer + y * stride_pixels;
            for (int x = 0; x < width; x++) {
                size_t idx = (size_t)y * width + x;
                float c = cnt[idx];
                if (c > 0) {
                    float v = acc[idx] / c;
                    if (v < 0) v = 0;
                    if (v > 16383) v = 16383;
                    row[x] = (uint16_t)(v + 0.5f);
                }
            }
        }

        free(acc); free(cnt); free(ys); free(xs);
    }
    return 0;
}
