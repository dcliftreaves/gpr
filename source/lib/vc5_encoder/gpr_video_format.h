/*! @file gpr_video_format.h
 *
 *  @brief Container format for GPR raw video streams.
 *
 *  Wraps a sequence of fused-encoder bitstreams with a clip header
 *  (target bitrate, denoise state, encoding parameters) and per-frame
 *  headers (length + tag), so downstream decoders can:
 *   - know the clip's target rate without measuring
 *   - reject incompatible decoder versions
 *   - seek through frames without parsing bitstream content
 *
 *  Wire format (little-endian, packed):
 *
 *      Clip header (32 bytes, written once at stream start):
 *          [0..3]   magic     = 'GVID' (0x44, 0x49, 0x56, 0x47 on disk)
 *          [4]      version   = 1
 *          [5]      flags     bit 0 = rate_control_enabled
 *                             bit 1 = denoise_enabled
 *                             bits 2-7 = reserved (must be 0)
 *          [6..7]   pixel_format (0..5; see fused_encode.h)
 *          [8..9]   quality      (0..8 base preset)
 *          [10..11] reserved2 (must be 0)
 *          [12..15] width
 *          [16..19] height
 *          [20..23] fps_x1000   (24.0 fps stored as 24000)
 *          [24..27] target_kbps (0 if rate control disabled; otherwise
 *                                target * 8 * 1024 / 1000 from MB/s)
 *          [28..31] frame_count_hint (0 if unknown at start)
 *
 *      Frame header (16 bytes, written before each frame's bitstream):
 *          [0..3]   magic     = 'FRM\0' (0x46, 0x52, 0x4D, 0x00 on disk)
 *          [4..7]   payload_size (bitstream length in bytes)
 *          [8..15]  frame_tag (caller's tag from submit, e.g. PTS)
 *
 *      Then payload_size bytes of fused-encoder bitstream.
 *      Repeat frame-header + bitstream for each frame.
 *
 *  No clip trailer — readers detect EOF naturally.
 *
 *  (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifndef GPR_VIDEO_FORMAT_H
#define GPR_VIDEO_FORMAT_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GPR_VIDEO_CLIP_MAGIC    0x44495647u   /* 'GVID' LE */
#define GPR_VIDEO_FRAME_MAGIC   0x004D5246u   /* 'FRM\0' LE */
#define GPR_VIDEO_FORMAT_VERSION 1

#define GPR_VIDEO_FLAG_RATE_CONTROL  0x01
#define GPR_VIDEO_FLAG_DENOISE       0x02

#define GPR_VIDEO_CLIP_HEADER_SIZE  32
#define GPR_VIDEO_FRAME_HEADER_SIZE 16

typedef struct {
    uint32_t magic;
    uint8_t  version;
    uint8_t  flags;
    uint16_t pixel_format;
    uint16_t quality;
    uint16_t reserved2;
    uint32_t width;
    uint32_t height;
    uint32_t fps_x1000;
    uint32_t target_kbps;
    uint32_t frame_count_hint;
} gpr_video_clip_header;

typedef struct {
    uint32_t magic;
    uint32_t payload_size;
    uint64_t frame_tag;
} gpr_video_frame_header;

/*! @brief Encode a clip header into a 32-byte buffer.
    @return GPR_VIDEO_CLIP_HEADER_SIZE on success, -1 on error. */
int gpr_video_write_clip_header(uint8_t *buf, size_t buf_size,
                                 int width, int height,
                                 int pixel_format, int quality,
                                 double fps, double target_MBps,
                                 int denoise_enabled,
                                 uint32_t frame_count_hint);

/*! @brief Encode a frame header into a 16-byte buffer.
    @return GPR_VIDEO_FRAME_HEADER_SIZE on success, -1 on error. */
int gpr_video_write_frame_header(uint8_t *buf, size_t buf_size,
                                  size_t payload_size,
                                  uint64_t frame_tag);

/*! @brief Parse a clip header. Validates magic and version.
    @return 0 on success, -1 on malformed/incompatible header. */
int gpr_video_read_clip_header(const uint8_t *buf, size_t buf_size,
                                gpr_video_clip_header *out);

/*! @brief Parse a frame header. Validates magic.
    @return 0 on success, -1 on malformed header. */
int gpr_video_read_frame_header(const uint8_t *buf, size_t buf_size,
                                 gpr_video_frame_header *out);

#ifdef __cplusplus
}
#endif

#endif /* GPR_VIDEO_FORMAT_H */
