/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#ifndef GPR_PREVIEW_H
#define GPR_PREVIEW_H
#include "gpr_gvid.h"
#ifdef __cplusplus
extern "C" {
#endif
enum { GPR_PREVIEW_OK=0,GPR_PREVIEW_INVALID=-1,GPR_PREVIEW_CAPACITY=-2,
       GPR_PREVIEW_PAYLOAD=-3,GPR_PREVIEW_CODEC=-4,GPR_PREVIEW_NOMEM=-5 };
typedef struct {
    uint32_t downsample; /* 4, 8 or 16 Bayer samples per RGB sample axis. */
    uint32_t gain_num[3],gain_pow2_den[3]; /* R,G,B gain = num / 2^den. */
} gpr_preview_options;
typedef struct { uint32_t width,height; size_t row_bytes; } gpr_preview_info;
void gpr_preview_options_default(gpr_preview_options *out);
int gpr_preview_dimensions(const gpr_gvid_config *video,const gpr_preview_options *options,gpr_preview_info *out);
/* Render the complete wavelet-scaled frame to caller-owned RGB24 rows. No CNN,
 * crop or full-resolution RAW intermediate. Display buffers remain caller
 * owned; padding bytes are not modified. Options/default gains are explicit,
 * not camera-calibrated ISP/color science. 4-byte-unaligned payloads are copied
 * to aligned scratch. The fast path accepts the stock SDK's four-channel,
 * three-level RAW profile and checks dimensions/framing before decoding. */
int gpr_preview_render(const gpr_gvid_config *video,const gpr_preview_options *options,
    const uint8_t *payload,size_t payload_size,uint8_t *rgb,size_t capacity,size_t pitch,gpr_preview_info *out);
#ifdef __cplusplus
}
#endif
#endif
