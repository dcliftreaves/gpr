/* test_roundtrip.c — end-to-end validation for the FFmpeg GPR decoder.
 *
 *   1. Synthesizes a deterministic 1920x1080 Bayer (16-bit) test pattern.
 *   2. Encodes 50 copies as fused-GPR frames into a .gpraw MOV container.
 *   3. Decodes each frame via gpraw_reader + gpr_decode_fused (reference).
 *   4. Decodes each frame via libavcodec using AV_CODEC_ID_GPR (under test).
 *   5. Asserts byte-equal output between (3) and (4).
 *
 * Built and run by test_roundtrip.sh — links against:
 *   - gpr libs (vc5_decoder, vc5_common, common, vc5_encoder)
 *   - gpraw lib (writer side)
 *   - the patched FFmpeg in /tmp/ffmpeg_gpr (libavformat + libavcodec)
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/avutil.h>
#include <libavutil/imgutils.h>

#include "fused_decode.h"

/* MOV codec_tag 'GPRr' little-endian. */
#define GPRAW_CODEC_TAG (((uint32_t)'G') | ((uint32_t)'P' << 8) | \
                         ((uint32_t)'R' << 16) | ((uint32_t)'r' << 24))

/* Encoder C entry points (no public header, link by name). */
typedef struct FUSED_ENCODER FUSED_ENCODER;
extern FUSED_ENCODER *gpr_encode_fused_create(int w, int h, int pf, int q);
extern int gpr_encode_fused_frame(FUSED_ENCODER *ctx, const unsigned char *raw,
                                  size_t sz, unsigned char **out, size_t *out_sz);
extern void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);

#define W 1920
#define H 1080
#define N_FRAMES 50

static void make_test_bayer(uint16_t *p, int seed) {
    /* Deterministic pseudo-random gradient that varies by frame index.
       The pattern is RGGB-tiled so the encoder treats it as legitimate. */
    uint32_t x = (uint32_t)seed * 2654435761u + 1u;
    for (int y = 0; y < H; y++) {
        for (int xc = 0; xc < W; xc++) {
            uint16_t v;
            int is_g = ((xc ^ y) & 1);
            x = x * 1103515245u + 12345u;
            int noise = (int)((x >> 16) & 0x1FF);
            if (is_g) {
                v = (uint16_t)(2048 + (y * 2) + noise);
            } else if ((y & 1) == 0) {           /* R */
                v = (uint16_t)(1500 + xc / 2 + noise);
            } else {                              /* B */
                v = (uint16_t)(2500 + xc / 3 + noise);
            }
            if (v > 14000) v = 14000;             /* keep < white_level */
            p[y * W + xc] = v;
        }
    }
}

/* Minimal .gpraw writer. Mirrors tools/gpraw/src/gpraw.c but compiled
   against the patched FFmpeg so codec_id=AV_CODEC_ID_GPR is recognized. */
static int build_gpraw(const char *path) {
    FUSED_ENCODER *enc = gpr_encode_fused_create(W, H, /*pf=*/1, /*q=*/3);
    if (!enc) { fprintf(stderr, "encoder create failed\n"); return -1; }

    AVFormatContext *oc = NULL;
    int rc = avformat_alloc_output_context2(&oc, NULL, "mov", path);
    if (rc < 0 || !oc) { fprintf(stderr, "alloc_output_context2 failed\n"); return -1; }
    AVStream *vs = avformat_new_stream(oc, NULL);
    AVCodecParameters *p = vs->codecpar;
    p->codec_type = AVMEDIA_TYPE_VIDEO;
    p->codec_id   = AV_CODEC_ID_GPR;
    p->codec_tag  = GPRAW_CODEC_TAG;
    p->width      = W;
    p->height     = H;
    p->format     = AV_PIX_FMT_NONE;
    vs->time_base = (AVRational){1, 24};
    vs->avg_frame_rate = (AVRational){24, 1};
    vs->r_frame_rate   = (AVRational){24, 1};

    if (!(oc->oformat->flags & AVFMT_NOFILE)) {
        rc = avio_open(&oc->pb, path, AVIO_FLAG_WRITE);
        if (rc < 0) { fprintf(stderr, "avio_open failed\n"); return -1; }
    }
    rc = avformat_write_header(oc, NULL);
    if (rc < 0) {
        char errbuf[AV_ERROR_MAX_STRING_SIZE] = {0};
        av_strerror(rc, errbuf, sizeof errbuf);
        fprintf(stderr, "write_header: %s\n", errbuf);
        return -1;
    }

    uint16_t *bayer = malloc((size_t)W * H * 2);
    for (int i = 0; i < N_FRAMES; i++) {
        make_test_bayer(bayer, i);
        unsigned char *out = NULL; size_t out_sz = 0;
        rc = gpr_encode_fused_frame(enc, (const unsigned char *)bayer,
                                    (size_t)W * H * 2, &out, &out_sz);
        if (rc != 0 || !out || out_sz == 0) {
            fprintf(stderr, "encode frame %d failed\n", i); return -1;
        }
        AVPacket *pkt = av_packet_alloc();
        av_new_packet(pkt, (int)out_sz);
        memcpy(pkt->data, out, out_sz);
        pkt->stream_index = vs->index;
        pkt->pts = pkt->dts = i;
        pkt->duration = 1;
        pkt->flags = AV_PKT_FLAG_KEY;
        rc = av_write_frame(oc, pkt);
        av_packet_free(&pkt);
        if (rc < 0) { fprintf(stderr, "write_frame %d failed\n", i); return -1; }
    }
    av_write_trailer(oc);
    avio_closep(&oc->pb);
    avformat_free_context(oc);
    free(bayer);
    gpr_encode_fused_destroy(enc);
    return 0;
}

static int decode_via_libavcodec(const char *path,
                                 uint16_t **frames_out, int *nframes_out) {
    AVFormatContext *ic = NULL;
    if (avformat_open_input(&ic, path, NULL, NULL) < 0) return -1;
    if (avformat_find_stream_info(ic, NULL) < 0) { avformat_close_input(&ic); return -2; }

    int vidx = -1;
    for (unsigned i = 0; i < ic->nb_streams; i++)
        if (ic->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            vidx = (int)i; break;
        }
    if (vidx < 0) { avformat_close_input(&ic); return -3; }

    const AVCodec *codec = avcodec_find_decoder(ic->streams[vidx]->codecpar->codec_id);
    if (!codec) {
        char tag[5] = {0};
        memcpy(tag, &ic->streams[vidx]->codecpar->codec_tag, 4);
        fprintf(stderr, "no decoder for codec_id=%d codec_tag='%s'\n",
                ic->streams[vidx]->codecpar->codec_id, tag);
        avformat_close_input(&ic); return -4;
    }
    fprintf(stderr, "libavcodec decoder selected: %s (%s)\n",
            codec->name, codec->long_name);

    AVCodecContext *avctx = avcodec_alloc_context3(codec);
    avcodec_parameters_to_context(avctx, ic->streams[vidx]->codecpar);
    if (avcodec_open2(avctx, codec, NULL) < 0) {
        avformat_close_input(&ic); avcodec_free_context(&avctx); return -5;
    }

    AVPacket *pkt   = av_packet_alloc();
    AVFrame  *frame = av_frame_alloc();
    uint16_t *out   = malloc((size_t)W * H * 2 * (size_t)N_FRAMES);
    int n = 0;
    while (av_read_frame(ic, pkt) >= 0) {
        if (pkt->stream_index != vidx) { av_packet_unref(pkt); continue; }
        if (avcodec_send_packet(avctx, pkt) < 0) {
            av_packet_unref(pkt); break;
        }
        while (avcodec_receive_frame(avctx, frame) == 0) {
            if (n >= N_FRAMES) break;
            /* Copy contiguous (linesize may include padding). */
            for (int y = 0; y < H; y++)
                memcpy(out + (size_t)n * W * H + (size_t)y * W,
                       frame->data[0] + (size_t)y * frame->linesize[0],
                       (size_t)W * 2);
            av_frame_unref(frame);
            n++;
        }
        av_packet_unref(pkt);
    }
    /* Flush. */
    avcodec_send_packet(avctx, NULL);
    while (avcodec_receive_frame(avctx, frame) == 0 && n < N_FRAMES) {
        for (int y = 0; y < H; y++)
            memcpy(out + (size_t)n * W * H + (size_t)y * W,
                   frame->data[0] + (size_t)y * frame->linesize[0],
                   (size_t)W * 2);
        av_frame_unref(frame);
        n++;
    }
    av_frame_free(&frame);
    av_packet_free(&pkt);
    avcodec_free_context(&avctx);
    avformat_close_input(&ic);

    *frames_out = out;
    *nframes_out = n;
    return 0;
}

/* Demux raw packets and run gpr_decode_fused directly (reference). */
static int decode_via_direct(const char *path,
                             uint16_t **frames_out, int *nframes_out) {
    AVFormatContext *ic = NULL;
    if (avformat_open_input(&ic, path, NULL, NULL) < 0) return -1;
    if (avformat_find_stream_info(ic, NULL) < 0) { avformat_close_input(&ic); return -2; }
    int vidx = -1;
    for (unsigned i = 0; i < ic->nb_streams; i++)
        if (ic->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO)
            { vidx = (int)i; break; }
    if (vidx < 0) { avformat_close_input(&ic); return -3; }
    uint16_t *out = malloc((size_t)W * H * 2 * (size_t)N_FRAMES);
    AVPacket *pkt = av_packet_alloc();
    int n = 0;
    while (av_read_frame(ic, pkt) >= 0 && n < N_FRAMES) {
        if (pkt->stream_index == vidx) {
            int dw = 0, dh = 0;
            int rc = gpr_decode_fused(pkt->data, (size_t)pkt->size,
                                      out + (size_t)n * W * H,
                                      (size_t)W * 2, &dw, &dh);
            if (rc != 0) {
                fprintf(stderr, "direct decode frame %d failed (rc=%d)\n", n, rc);
                av_packet_free(&pkt); avformat_close_input(&ic);
                free(out); return -4;
            }
            n++;
        }
        av_packet_unref(pkt);
    }
    av_packet_free(&pkt);
    avformat_close_input(&ic);
    *frames_out = out;
    *nframes_out = n;
    return 0;
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "/tmp/gpraw_roundtrip.gpraw";

    fprintf(stderr, "[1/4] building %s\n", path);
    if (build_gpraw(path) != 0) return 1;

    fprintf(stderr, "[2/4] decoding via gpr_decode_fused (reference)\n");
    uint16_t *ref = NULL; int ref_n = 0;
    if (decode_via_direct(path, &ref, &ref_n) != 0) return 1;
    fprintf(stderr, "  got %d frames\n", ref_n);

    fprintf(stderr, "[3/4] decoding via libavcodec (under test)\n");
    uint16_t *uut = NULL; int uut_n = 0;
    if (decode_via_libavcodec(path, &uut, &uut_n) != 0) return 1;
    fprintf(stderr, "  got %d frames\n", uut_n);

    fprintf(stderr, "[4/4] comparing\n");
    if (ref_n != uut_n) {
        fprintf(stderr, "FAIL: frame count mismatch ref=%d uut=%d\n", ref_n, uut_n);
        return 2;
    }
    int mismatch = 0;
    for (int i = 0; i < ref_n; i++) {
        if (memcmp(ref + (size_t)i * W * H, uut + (size_t)i * W * H,
                   (size_t)W * H * 2) != 0) {
            /* find first differing pixel */
            for (int p = 0; p < W * H; p++) {
                if (ref[(size_t)i * W * H + p] != uut[(size_t)i * W * H + p]) {
                    fprintf(stderr,
                            "FAIL frame %d pix %d: ref=%u uut=%u\n",
                            i, p, ref[(size_t)i*W*H + p],
                            uut[(size_t)i*W*H + p]);
                    break;
                }
            }
            mismatch++;
        }
    }
    if (mismatch) {
        fprintf(stderr, "FAIL: %d / %d frames differ\n", mismatch, ref_n);
        return 3;
    }
    fprintf(stderr, "PASS: %d frames byte-identical\n", ref_n);
    free(ref); free(uut);
    return 0;
}
