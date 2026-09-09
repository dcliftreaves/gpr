/*
 * GPR (GoPro RAW / fused-VC5) video decoder for libavcodec.
 *
 * Copyright (c) 2026 Happy.
 *
 * This file is part of FFmpeg (out-of-tree patch — installed into
 * libavcodec/gpr.c by tools/gpraw_codec/install_patch.sh).
 *
 * FFmpeg is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */

/**
 * @file
 * GPR fused-format decoder. One AVPacket == one self-contained GPR frame
 * (FUSED_HEADER + band manifest + rANS bands). This decoder is a thin
 * wrapper around libvc5_decoder's gpr_decode_fused(): we hand it the
 * packet bytes and it writes a 16-bit Bayer plane.
 *
 * Output pixel format: AV_PIX_FMT_BAYER_RGGB16LE or
 * AV_PIX_FMT_BAYER_GBRG16LE depending on the FUSED_HEADER.is_rggb flag.
 * (FFmpeg's two BAYER pixel formats use bit-packed 16-bit single-plane
 * layout — the same shape gpr_decode_fused writes.)
 *
 * Stream identification: codec_tag 'GPRr' (little-endian uint32 spelling
 * G, P, R, r), mapped in libavformat/isom_tags.c.
 */

/* FUSED_HEADER layout (must mirror source/lib/vc5_encoder/fused_encode.h).
 * All fields are little-endian uint32_t. We re-state them here so this
 * file has no source-tree include path dependency beyond libvc5_decoder.a. */
#define GPR_FUSED_MAGIC      0x44535546u   /* 'FUSD' LE                 */
#define GPR_FUSED_HDR_SIZE   52u           /* 13 × uint32_t             */
#define GPR_FUSED_OFF_MAGIC   0
#define GPR_FUSED_OFF_VER     4
#define GPR_FUSED_OFF_WIDTH   8
#define GPR_FUSED_OFF_HEIGHT 12
#define GPR_FUSED_OFF_PIXFMT 16
#define GPR_FUSED_OFF_QUAL   20
#define GPR_FUSED_OFF_RGGB   24
#define GPR_FUSED_OFF_LOGB   28
#define GPR_FUSED_OFF_PRES   32
#define GPR_FUSED_OFF_MULTI  36
#define GPR_FUSED_OFF_BANDS  40
#define GPR_FUSED_OFF_DECIM  44

#include "libavutil/avassert.h"
#include "libavutil/common.h"
#include "libavutil/imgutils.h"
#include "libavutil/intreadwrite.h"
#include "libavutil/mem.h"

#include "avcodec.h"
#include "codec_internal.h"
#include "decode.h"

/* External decoder API from libvc5_decoder. We deliberately forward-declare
   here rather than including fused_decode.h so this file stays inside the
   FFmpeg source tree without an include-path entanglement. */
int gpr_decode_fused(const uint8_t *enc, size_t enc_size,
                     uint16_t *bayer_out, size_t bayer_pitch_bytes,
                     int *out_width, int *out_height);

typedef struct GPRContext {
    AVClass *class;
    /* Decoded dimensions latched on first frame, validated thereafter. */
    int latched_width;
    int latched_height;
} GPRContext;

static av_cold int gpr_dec_init(AVCodecContext *avctx)
{
    GPRContext *s = avctx->priv_data;
    s->latched_width  = 0;
    s->latched_height = 0;

    /* The MOV demuxer will have set avctx->width/height from the stream
       sample description. If they are zero (some old containers) we will
       latch them from the first frame's GPR header.

       The CFA pattern (RGGB vs GBRG) is also frame-level — we default to
       RGGB and override on the first frame if the header says GBRG. */
    avctx->pix_fmt = AV_PIX_FMT_BAYER_RGGB16LE;
    return 0;
}

static av_cold int gpr_dec_close(AVCodecContext *avctx)
{
    return 0;
}

static int gpr_dec_decode(AVCodecContext *avctx, AVFrame *frame,
                          int *got_frame, AVPacket *avpkt)
{
    GPRContext *s = avctx->priv_data;
    int width = 0, height = 0;
    int ret;

    *got_frame = 0;

    if (!avpkt->data || (unsigned)avpkt->size < GPR_FUSED_HDR_SIZE) {
        av_log(avctx, AV_LOG_ERROR, "gpr: packet too small (%d bytes)\n",
               avpkt ? avpkt->size : 0);
        return AVERROR_INVALIDDATA;
    }

    /* Validate magic + peek width/height/CFA from the FUSED_HEADER. */
    if (AV_RL32(avpkt->data + GPR_FUSED_OFF_MAGIC) != GPR_FUSED_MAGIC) {
        av_log(avctx, AV_LOG_ERROR,
               "gpr: bad magic 0x%08x (expected 0x%08x)\n",
               AV_RL32(avpkt->data + GPR_FUSED_OFF_MAGIC), GPR_FUSED_MAGIC);
        return AVERROR_INVALIDDATA;
    }

    width  = (int)AV_RL32(avpkt->data + GPR_FUSED_OFF_WIDTH);
    height = (int)AV_RL32(avpkt->data + GPR_FUSED_OFF_HEIGHT);
    uint32_t is_rggb = AV_RL32(avpkt->data + GPR_FUSED_OFF_RGGB);
    uint32_t decim   = AV_RL32(avpkt->data + GPR_FUSED_OFF_DECIM);
    if (decim > 1) {
        /* Channel-space decimation halves the visible dimensions. */
        width  /= decim;
        height /= decim;
    }
    enum AVPixelFormat want_fmt = is_rggb ? AV_PIX_FMT_BAYER_RGGB16LE
                                          : AV_PIX_FMT_BAYER_GBRG16LE;
    if (avctx->pix_fmt != want_fmt) {
        avctx->pix_fmt = want_fmt;
    }

    if (width <= 0 || height <= 0 || width > 16384 || height > 16384) {
        av_log(avctx, AV_LOG_ERROR,
               "gpr: implausible dimensions from header: %dx%d\n",
               width, height);
        return AVERROR_INVALIDDATA;
    }

    /* On the very first frame, propagate dimensions to avctx so downstream
       filters / muxers see them even if the container forgot to set them. */
    if (!s->latched_width) {
        s->latched_width  = width;
        s->latched_height = height;
        if (avctx->width  <= 0) avctx->width  = width;
        if (avctx->height <= 0) avctx->height = height;
    } else if (width != s->latched_width || height != s->latched_height) {
        av_log(avctx, AV_LOG_ERROR,
               "gpr: dimension change mid-stream not supported "
               "(%dx%d -> %dx%d)\n",
               s->latched_width, s->latched_height, width, height);
        return AVERROR_INVALIDDATA;
    }

    /* Allocate the output frame. Bayer 16-bit is one component per sample,
       so linesize[0] = width * 2 bytes. */
    if ((ret = ff_get_buffer(avctx, frame, 0)) < 0)
        return ret;

    /* Hand the packet straight to the GPR decoder. It writes directly
       into the AVFrame data buffer at our requested stride. */
    int decoded_w = 0, decoded_h = 0;
    ret = gpr_decode_fused(avpkt->data, (size_t)avpkt->size,
                           (uint16_t *)frame->data[0],
                           (size_t)frame->linesize[0],
                           &decoded_w, &decoded_h);
    if (ret < 0) {
        av_log(avctx, AV_LOG_ERROR,
               "gpr: gpr_decode_fused failed: %d\n", ret);
        return AVERROR_INVALIDDATA;
    }
    if (decoded_w != width || decoded_h != height) {
        av_log(avctx, AV_LOG_ERROR,
               "gpr: header/decode dim mismatch %dx%d vs %dx%d\n",
               width, height, decoded_w, decoded_h);
        return AVERROR_INVALIDDATA;
    }

    frame->pict_type = AV_PICTURE_TYPE_I;     /* every GPR frame is intra */
    frame->flags    |= AV_FRAME_FLAG_KEY;
    frame->pts       = avpkt->pts;
    *got_frame = 1;
    return avpkt->size;
}

const FFCodec ff_gpr_decoder = {
    .p.name           = "gpr",
    CODEC_LONG_NAME("GoPro RAW (fused VC-5)"),
    .p.type           = AVMEDIA_TYPE_VIDEO,
    .p.id             = AV_CODEC_ID_GPR,
    .priv_data_size   = sizeof(GPRContext),
    .init             = gpr_dec_init,
    .close            = gpr_dec_close,
    FF_CODEC_DECODE_CB(gpr_dec_decode),
    .p.capabilities   = AV_CODEC_CAP_DR1,
    .caps_internal    = FF_CODEC_CAP_INIT_CLEANUP,
};
