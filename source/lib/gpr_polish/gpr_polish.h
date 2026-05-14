/*
 * gpr_polish — optional decoder-side post-process that runs a small CNN
 * over decoded Bayer to clean up wavelet quantization artifacts.
 *
 * Designed for offline / batch use (e.g., a "develop" or "export" stage in
 * a video editor). On Apple silicon it runs through CoreML on the Neural
 * Engine at roughly 1 fps for a 50 MP frame. Not currently fast enough for
 * real-time 24 fps decode.
 *
 * The model is quality-conditioned: pass the original encode quality
 * (0..3) so the model knows which artifact pattern to attack.
 *
 * Threadsafe: a single gpr_polish_t is single-threaded; create multiple
 * for parallel frames.
 */

#ifndef GPR_POLISH_H
#define GPR_POLISH_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct gpr_polish_s gpr_polish_t;

/* Create a polish context. model_path may be NULL to use the bundled
   default model (TBD; currently must provide a CoreML .mlpackage path).
   Returns NULL on failure (model file not found, runtime unavailable). */
gpr_polish_t *gpr_polish_create(const char *model_path);

/* Free the context. */
void gpr_polish_destroy(gpr_polish_t *p);

/* Apply the polish to a Bayer plane in-place.
 *
 *   bayer:  uint16 Bayer plane (RGGB), values in [0, 16383] (14-bit).
 *   width:  pixel width (must be even).
 *   height: pixel height (must be even).
 *   stride: row stride in bytes (must be a multiple of 2).
 *   quality: encode quality (0..3) the bayer was decoded from.
 *
 * On success returns 0 and bayer is updated in-place. On failure returns
 * a negative errno-like code and bayer is unchanged.
 *
 * Implementation: tiles the frame, runs CoreML per tile, blends overlaps.
 */
int gpr_polish_apply(gpr_polish_t *p,
                     uint16_t *bayer,
                     int width, int height,
                     int stride_bytes,
                     int quality);

/* Returns true if the runtime is available on this platform.
 * (Currently true on macOS arm64 with CoreML 14+, false elsewhere.) */
bool gpr_polish_available(void);

/* Performance hint: returns an estimate of how many milliseconds the
 * apply() call will take for a frame of (width*height) Bayer pixels.
 * Returns negative if the model isn't loaded yet. */
double gpr_polish_estimate_ms(const gpr_polish_t *p, int width, int height);

#ifdef __cplusplus
}
#endif

#endif /* GPR_POLISH_H */
