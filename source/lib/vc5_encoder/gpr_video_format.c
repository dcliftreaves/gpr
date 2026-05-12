/*! @file gpr_video_format.c
 *
 *  @brief Container format for GPR raw video — header (de)serialization.
 *
 *  See gpr_video_format.h for the wire format.
 *
 *  (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#include "gpr_video_format.h"
#include <string.h>

static void write_u32_le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v       & 0xff);
    p[1] = (uint8_t)((v >>  8) & 0xff);
    p[2] = (uint8_t)((v >> 16) & 0xff);
    p[3] = (uint8_t)((v >> 24) & 0xff);
}

static void write_u16_le(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)(v       & 0xff);
    p[1] = (uint8_t)((v >> 8) & 0xff);
}

static uint32_t read_u32_le(const uint8_t *p) {
    return ((uint32_t)p[0])
         | ((uint32_t)p[1] <<  8)
         | ((uint32_t)p[2] << 16)
         | ((uint32_t)p[3] << 24);
}

static uint16_t read_u16_le(const uint8_t *p) {
    return (uint16_t)(((uint16_t)p[0]) | ((uint16_t)p[1] << 8));
}

static uint64_t read_u64_le(const uint8_t *p) {
    return ((uint64_t)read_u32_le(p))
         | ((uint64_t)read_u32_le(p + 4) << 32);
}

static void write_u64_le(uint8_t *p, uint64_t v) {
    write_u32_le(p,     (uint32_t)(v        & 0xffffffffu));
    write_u32_le(p + 4, (uint32_t)((v >> 32) & 0xffffffffu));
}

int gpr_video_write_clip_header(uint8_t *buf, size_t buf_size,
                                 int width, int height,
                                 int pixel_format, int quality,
                                 double fps, double target_MBps,
                                 int denoise_enabled,
                                 uint32_t frame_count_hint)
{
    if (!buf || buf_size < GPR_VIDEO_CLIP_HEADER_SIZE) return -1;
    if (width <= 0 || height <= 0 || pixel_format < 0 || pixel_format > 5) return -1;
    if (quality < 0 || quality > 8) return -1;
    if (fps <= 0.0) return -1;

    uint8_t flags = 0;
    if (target_MBps > 0.0) flags |= GPR_VIDEO_FLAG_RATE_CONTROL;
    if (denoise_enabled) flags |= GPR_VIDEO_FLAG_DENOISE;

    /* target_MBps × 8 × 1024 ≈ kbps; storing in 32-bit kbps gives finer
       resolution than MB/s for modest targets, and accommodates up to
       ~4 TB/s of headroom for futures we don't have today. */
    uint32_t target_kbps = (target_MBps > 0.0)
        ? (uint32_t)(target_MBps * 8.0 * 1024.0 + 0.5)
        : 0u;
    uint32_t fps_x1000 = (uint32_t)(fps * 1000.0 + 0.5);

    write_u32_le(buf +  0, GPR_VIDEO_CLIP_MAGIC);
    buf[4] = GPR_VIDEO_FORMAT_VERSION;
    buf[5] = flags;
    write_u16_le(buf +  6, (uint16_t)pixel_format);
    write_u16_le(buf +  8, (uint16_t)quality);
    write_u16_le(buf + 10, 0);                              /* reserved */
    write_u32_le(buf + 12, (uint32_t)width);
    write_u32_le(buf + 16, (uint32_t)height);
    write_u32_le(buf + 20, fps_x1000);
    write_u32_le(buf + 24, target_kbps);
    write_u32_le(buf + 28, frame_count_hint);
    return GPR_VIDEO_CLIP_HEADER_SIZE;
}

int gpr_video_write_frame_header(uint8_t *buf, size_t buf_size,
                                  size_t payload_size,
                                  uint64_t frame_tag)
{
    if (!buf || buf_size < GPR_VIDEO_FRAME_HEADER_SIZE) return -1;
    if (payload_size > 0xffffffffu) return -1;
    write_u32_le(buf + 0, GPR_VIDEO_FRAME_MAGIC);
    write_u32_le(buf + 4, (uint32_t)payload_size);
    write_u64_le(buf + 8, frame_tag);
    return GPR_VIDEO_FRAME_HEADER_SIZE;
}

int gpr_video_read_clip_header(const uint8_t *buf, size_t buf_size,
                                gpr_video_clip_header *out)
{
    if (!buf || !out || buf_size < GPR_VIDEO_CLIP_HEADER_SIZE) return -1;
    uint32_t magic = read_u32_le(buf + 0);
    uint8_t version = buf[4];
    if (magic != GPR_VIDEO_CLIP_MAGIC) return -1;
    if (version != GPR_VIDEO_FORMAT_VERSION) return -1;
    out->magic = magic;
    out->version = version;
    out->flags = buf[5];
    out->pixel_format = read_u16_le(buf + 6);
    out->quality = read_u16_le(buf + 8);
    out->reserved2 = read_u16_le(buf + 10);
    out->width = read_u32_le(buf + 12);
    out->height = read_u32_le(buf + 16);
    out->fps_x1000 = read_u32_le(buf + 20);
    out->target_kbps = read_u32_le(buf + 24);
    out->frame_count_hint = read_u32_le(buf + 28);
    return 0;
}

int gpr_video_read_frame_header(const uint8_t *buf, size_t buf_size,
                                 gpr_video_frame_header *out)
{
    if (!buf || !out || buf_size < GPR_VIDEO_FRAME_HEADER_SIZE) return -1;
    uint32_t magic = read_u32_le(buf + 0);
    if (magic != GPR_VIDEO_FRAME_MAGIC) return -1;
    out->magic = magic;
    out->payload_size = read_u32_le(buf + 4);
    out->frame_tag = read_u64_le(buf + 8);
    return 0;
}
