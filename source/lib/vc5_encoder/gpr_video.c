/*! @file gpr_video.c
 *
 *  @brief Pipelined video encoder implementation.
 *  See gpr_video.h for design notes.
 *
 *  Supports two modes:
 *    encoder_count=1: legacy single-encoder pipeline (one input ring,
 *                     one encoder thread, one output ring, one writer).
 *    encoder_count=2: dual ping-pong pipeline. Two input rings (one per
 *                     encoder), two encoder threads each owning its own
 *                     FUSED_ENCODER context, a shared output ring with
 *                     tag-ordered consumption, and one writer thread that
 *                     emits frames strictly in frame_tag order.
 *
 *  Single-encoder mode is byte-identical to the prior behavior because
 *  it uses N=1 throughout: one input ring, one encoder, and the output
 *  ring with N=1 reduces to a plain FIFO (any inserted frame is already
 *  in tag order on entry).
 *
 *  (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#include "gpr_video.h"
#include "fused_encode.h"

#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <math.h>

#define VIDEO_MAX_RING_DEPTH 8
#define VIDEO_MAX_ENCODERS   2

typedef struct {
    uint8_t *raw;          /* owned, pre-allocated raw frame slot */
    size_t   raw_capacity;
    size_t   raw_size;     /* size of the frame in this slot */
    uint64_t frame_tag;
} input_slot;

/* Output slot: tag-keyed. The writer consumes by frame_tag in submission
   order, not by ring position, so out-of-order producer pushes (encoder
   B finishing before encoder A on an earlier tag) are reordered here. */
typedef struct {
    uint8_t *copy_buf;     /* owned, holds the copied bitstream */
    size_t   copy_capacity;
    size_t   vc5_size;     /* size of the copied bitstream */
    uint64_t frame_tag;
    int      valid;        /* 1 if this slot holds a completed frame */
} output_slot;

/* Per-encoder state (one input ring, one fused context, one thread). */
typedef struct encoder_state {
    int                idx;            /* 0 or 1 */
    struct GPR_VIDEO_ENCODER *parent;  /* back-pointer */

    /* Owned by the encoder thread once it boots. */
    FUSED_ENCODER     *fused_ctx;

    /* Adaptive bitrate state (encoder-thread-only access).
       Each encoder converges its own controller independently. */
    double rc_avg_bytes;
    double rc_scale;
    int    rc_frames_seen;

    /* Input ring slots. */
    input_slot      *in_slots;
    int              in_head;
    int              in_tail;
    int              in_count;
    pthread_mutex_t  in_lock;
    pthread_cond_t   in_not_full;
    pthread_cond_t   in_not_empty;

    pthread_t        thread;
} encoder_state;

struct GPR_VIDEO_ENCODER {
    int width, height;
    int pixel_format;
    int quality;
    int ring_depth;
    int encoder_count;

    /* Denoise config: applied uniformly to each encoder before its first
       frame. The encoder threads poll this once at startup. */
    int    denoise_set;
    double noise_scale, noise_offset, denoise_strength;

    /* Rate-control target shared by all encoders; each encoder runs its
       own controller against this target (per-frame budget). */
    double target_bytes_per_frame;

    /* Per-encoder state. We allocate up to encoder_count entries. */
    encoder_state encs[VIDEO_MAX_ENCODERS];

    /* Shared output ring. The producer-side index (`out_head`) is unused
       in tag-ordered mode; encoder threads search for any free slot
       (valid=0) and stamp it with the frame_tag. The writer scans for
       the slot whose frame_tag matches its expected sequence number. */
    output_slot     *out_slots;
    int              out_ring_size;
    int              out_count;        /* number of slots with valid=1 */
    uint64_t         writer_expected_tag;  /* next tag the writer will emit */
    pthread_mutex_t  out_lock;
    pthread_cond_t   out_not_full;
    pthread_cond_t   out_not_empty;

    /* Worker thread for the writer. */
    pthread_t writer_thread;
    int threads_started;
    int stop_requested;

    /* Writer callback */
    gpr_video_writer_fn writer;
    void *writer_data;

    /* Stats. Some counters are bumped without locks (racy by 1-2 events). */
    gpr_video_stats stats;
};

static void *encoder_thread_fn(void *arg);
static void *writer_thread_fn(void *arg);

GPR_VIDEO_ENCODER *gpr_video_encoder_create_dual(
    int width, int height,
    int pixel_format, int quality,
    int ring_depth, int encoder_count,
    gpr_video_writer_fn writer, void *user_data)
{
    if (width <= 0 || height <= 0 || ring_depth < 1 || !writer) return NULL;
    if (encoder_count < 1) encoder_count = 1;
    if (encoder_count > VIDEO_MAX_ENCODERS) encoder_count = VIDEO_MAX_ENCODERS;
    if (ring_depth > VIDEO_MAX_RING_DEPTH) ring_depth = VIDEO_MAX_RING_DEPTH;

    GPR_VIDEO_ENCODER *ctx = (GPR_VIDEO_ENCODER *)calloc(1, sizeof(*ctx));
    if (!ctx) return NULL;

    ctx->width = width;
    ctx->height = height;
    ctx->pixel_format = pixel_format;
    ctx->quality = quality;
    ctx->ring_depth = ring_depth;
    ctx->encoder_count = encoder_count;
    ctx->writer = writer;
    ctx->writer_data = user_data;
    ctx->writer_expected_tag = 0;

    /* Output ring is shared. Size it to fit all in-flight frames from
       every encoder so a slow writer cannot deadlock the encoders. */
    ctx->out_ring_size = ring_depth * encoder_count;
    if (ctx->out_ring_size < 2) ctx->out_ring_size = 2;

    pthread_mutex_init(&ctx->out_lock, NULL);
    pthread_cond_init(&ctx->out_not_full, NULL);
    pthread_cond_init(&ctx->out_not_empty, NULL);

    size_t raw_size = (size_t)width * (size_t)height * 2;  /* 16-bit Bayer */
    size_t vc5_capacity = raw_size / 2;

    /* Output slots. */
    ctx->out_slots = (output_slot *)calloc(ctx->out_ring_size, sizeof(output_slot));
    if (!ctx->out_slots) goto fail;
    for (int i = 0; i < ctx->out_ring_size; i++) {
        ctx->out_slots[i].copy_buf = (uint8_t *)malloc(vc5_capacity);
        if (!ctx->out_slots[i].copy_buf) goto fail;
        ctx->out_slots[i].copy_capacity = vc5_capacity;
        ctx->out_slots[i].valid = 0;
    }

    /* Per-encoder input ring + state. */
    for (int e = 0; e < encoder_count; e++) {
        encoder_state *es = &ctx->encs[e];
        es->idx = e;
        es->parent = ctx;
        es->rc_scale = 1.0;
        es->rc_avg_bytes = 0.0;
        es->rc_frames_seen = 0;

        pthread_mutex_init(&es->in_lock, NULL);
        pthread_cond_init(&es->in_not_full, NULL);
        pthread_cond_init(&es->in_not_empty, NULL);

        es->in_slots = (input_slot *)calloc(ring_depth, sizeof(input_slot));
        if (!es->in_slots) goto fail;
        for (int i = 0; i < ring_depth; i++) {
            es->in_slots[i].raw = (uint8_t *)malloc(raw_size);
            if (!es->in_slots[i].raw) goto fail;
            es->in_slots[i].raw_capacity = raw_size;
        }
    }

    /* Start encoder threads, then writer. */
    int started = 0;
    for (int e = 0; e < encoder_count; e++) {
        if (pthread_create(&ctx->encs[e].thread, NULL, encoder_thread_fn, &ctx->encs[e]) != 0) {
            /* Roll back: signal stop on the ones already started, join, fail. */
            ctx->stop_requested = 1;
            for (int j = 0; j < started; j++) {
                pthread_mutex_lock(&ctx->encs[j].in_lock);
                pthread_cond_broadcast(&ctx->encs[j].in_not_empty);
                pthread_mutex_unlock(&ctx->encs[j].in_lock);
                pthread_join(ctx->encs[j].thread, NULL);
            }
            goto fail;
        }
        started++;
    }
    if (pthread_create(&ctx->writer_thread, NULL, writer_thread_fn, ctx) != 0) {
        ctx->stop_requested = 1;
        for (int e = 0; e < encoder_count; e++) {
            pthread_mutex_lock(&ctx->encs[e].in_lock);
            pthread_cond_broadcast(&ctx->encs[e].in_not_empty);
            pthread_mutex_unlock(&ctx->encs[e].in_lock);
            pthread_join(ctx->encs[e].thread, NULL);
        }
        goto fail;
    }
    ctx->threads_started = 1;
    return ctx;

fail:
    gpr_video_encoder_destroy(ctx);
    return NULL;
}

GPR_VIDEO_ENCODER *gpr_video_encoder_create(
    int width, int height,
    int pixel_format, int quality,
    int ring_depth,
    gpr_video_writer_fn writer, void *user_data)
{
    return gpr_video_encoder_create_dual(width, height, pixel_format, quality,
                                          ring_depth, 1, writer, user_data);
}

void gpr_video_encoder_set_denoise(GPR_VIDEO_ENCODER *ctx,
                                    double noise_scale,
                                    double noise_offset,
                                    double strength)
{
    if (!ctx) return;
    /* Stored on the context; encoder thread will apply on its fused context.
       Each encoder thread polls this once before processing its first frame. */
    ctx->noise_scale = noise_scale;
    ctx->noise_offset = noise_offset;
    ctx->denoise_strength = strength;
    ctx->denoise_set = 1;
}

void gpr_video_encoder_set_target_bitrate(GPR_VIDEO_ENCODER *ctx,
                                           double target_MBps, double fps)
{
    if (!ctx) return;
    if (target_MBps <= 0.0 || fps <= 0.0) {
        ctx->target_bytes_per_frame = 0.0;   /* disable */
        return;
    }
    ctx->target_bytes_per_frame = target_MBps * 1024.0 * 1024.0 / fps;
    for (int e = 0; e < ctx->encoder_count; e++) {
        ctx->encs[e].rc_scale = 1.0;
        ctx->encs[e].rc_avg_bytes = 0.0;
        ctx->encs[e].rc_frames_seen = 0;
    }
}

int gpr_video_encoder_submit(GPR_VIDEO_ENCODER *ctx,
                              const uint8_t *raw_bayer, size_t raw_size,
                              uint64_t frame_tag)
{
    if (!ctx || !raw_bayer) return -1;

    /* Pick encoder by tag. With encoder_count=1 this always lands on 0,
       preserving original behavior. */
    int target = (int)(frame_tag % (uint64_t)ctx->encoder_count);
    encoder_state *es = &ctx->encs[target];

    pthread_mutex_lock(&es->in_lock);
    int waited = 0;
    while (es->in_count >= ctx->ring_depth && !ctx->stop_requested) {
        waited = 1;
        pthread_cond_wait(&es->in_not_full, &es->in_lock);
    }
    if (ctx->stop_requested) {
        pthread_mutex_unlock(&es->in_lock);
        return -1;
    }
    if (waited) ctx->stats.submit_waited++;

    input_slot *slot = &es->in_slots[es->in_head];
    if (raw_size > slot->raw_capacity) raw_size = slot->raw_capacity;
    memcpy(slot->raw, raw_bayer, raw_size);
    slot->raw_size = raw_size;
    slot->frame_tag = frame_tag;

    es->in_head = (es->in_head + 1) % ctx->ring_depth;
    es->in_count++;
    ctx->stats.frames_submitted++;
    pthread_cond_signal(&es->in_not_empty);
    pthread_mutex_unlock(&es->in_lock);
    return 0;
}

static void *encoder_thread_fn(void *arg)
{
    encoder_state *es = (encoder_state *)arg;
    GPR_VIDEO_ENCODER *ctx = es->parent;

    /* Create the fused encoder inside this thread so any thread-local
       state lives where it'll be used. */
    FUSED_ENCODER *fused = gpr_encode_fused_create(ctx->width, ctx->height,
                                                    ctx->pixel_format, ctx->quality);
    if (!fused) {
        ctx->stop_requested = 1;
        pthread_mutex_lock(&es->in_lock);
        pthread_cond_broadcast(&es->in_not_full);
        pthread_mutex_unlock(&es->in_lock);
        pthread_mutex_lock(&ctx->out_lock);
        pthread_cond_broadcast(&ctx->out_not_empty);
        pthread_mutex_unlock(&ctx->out_lock);
        return NULL;
    }
    if (ctx->denoise_set) {
        gpr_encode_fused_set_denoise(fused, ctx->noise_scale, ctx->noise_offset,
                                      ctx->denoise_strength);
    }
    es->fused_ctx = fused;

    for (;;) {
        /* Pop a frame from this encoder's input ring. */
        pthread_mutex_lock(&es->in_lock);
        while (es->in_count == 0 && !ctx->stop_requested) {
            pthread_cond_wait(&es->in_not_empty, &es->in_lock);
        }
        if (es->in_count == 0 && ctx->stop_requested) {
            pthread_mutex_unlock(&es->in_lock);
            break;
        }
        input_slot *in = &es->in_slots[es->in_tail];
        /* Keep slot reserved while encoding; don't advance tail until done. */
        pthread_mutex_unlock(&es->in_lock);

        /* Apply adaptive bitrate scale (per-encoder controller). */
        if (ctx->target_bytes_per_frame > 0.0) {
            gpr_encode_fused_set_quant_scale(fused, es->rc_scale);
        }

        /* Encode. */
        uint8_t *vc5_out = NULL;
        size_t vc5_size = 0;
        int rc = gpr_encode_fused_frame(fused, in->raw, in->raw_size,
                                         &vc5_out, &vc5_size);

        /* Update this encoder's rate controller. */
        if (ctx->target_bytes_per_frame > 0.0 && rc == 0 && vc5_size > 0) {
            const double alpha = 0.7;
            if (es->rc_frames_seen == 0) es->rc_avg_bytes = (double)vc5_size;
            else es->rc_avg_bytes = es->rc_avg_bytes * alpha + (double)vc5_size * (1.0 - alpha);
            es->rc_frames_seen++;

            double err = es->rc_avg_bytes / ctx->target_bytes_per_frame;
            double step = sqrt(err);
            if (step < 0.85) step = 0.85;
            if (step > 1.20) step = 1.20;
            double new_scale = es->rc_scale * step;
            if (new_scale < 0.25) new_scale = 0.25;
            if (new_scale > 16.0) new_scale = 16.0;
            es->rc_scale = new_scale;
        }

        if (rc == 0 && vc5_out && vc5_size > 0) {
            /* Push to shared output ring: find an empty slot. The ring
               is sized to ring_depth*encoder_count so a fully-loaded
               pipeline always has room. If full (writer behind), wait. */
            pthread_mutex_lock(&ctx->out_lock);
            int waited = 0;
            while (ctx->out_count >= ctx->out_ring_size && !ctx->stop_requested) {
                waited = 1;
                pthread_cond_wait(&ctx->out_not_full, &ctx->out_lock);
            }
            if (ctx->stop_requested) {
                pthread_mutex_unlock(&ctx->out_lock);
                break;
            }
            if (waited) ctx->stats.encoder_waited++;

            /* Linear scan for an empty slot. With small ring sizes
               (typically 4-8), this is faster than maintaining a
               free-list and keeps the critical section tiny. */
            int found = -1;
            for (int i = 0; i < ctx->out_ring_size; i++) {
                if (!ctx->out_slots[i].valid) { found = i; break; }
            }
            /* By invariant (out_count < out_ring_size), `found` is always >= 0. */
            output_slot *out = &ctx->out_slots[found];
            size_t copy_size = (vc5_size <= out->copy_capacity) ? vc5_size : out->copy_capacity;
            memcpy(out->copy_buf, vc5_out, copy_size);
            out->vc5_size = copy_size;
            out->frame_tag = in->frame_tag;
            out->valid = 1;
            ctx->out_count++;
            ctx->stats.frames_encoded++;
            /* Broadcast: in tag-ordered mode, only the writer waiting on
               a specific tag should wake — signal is enough since there
               is exactly one writer, but broadcast is harmless and safe
               against future multi-writer changes. */
            pthread_cond_signal(&ctx->out_not_empty);
            pthread_mutex_unlock(&ctx->out_lock);
        }

        /* Release the input slot. */
        pthread_mutex_lock(&es->in_lock);
        es->in_tail = (es->in_tail + 1) % ctx->ring_depth;
        es->in_count--;
        pthread_cond_signal(&es->in_not_full);
        pthread_mutex_unlock(&es->in_lock);
    }

    /* Wake the writer in case it's waiting. */
    pthread_mutex_lock(&ctx->out_lock);
    pthread_cond_broadcast(&ctx->out_not_empty);
    pthread_mutex_unlock(&ctx->out_lock);

    return NULL;
}

static void *writer_thread_fn(void *arg)
{
    GPR_VIDEO_ENCODER *ctx = (GPR_VIDEO_ENCODER *)arg;

    for (;;) {
        pthread_mutex_lock(&ctx->out_lock);
        /* Look for the slot matching writer_expected_tag. If none, wait. */
        int waited = 0;
        int found;
        for (;;) {
            found = -1;
            for (int i = 0; i < ctx->out_ring_size; i++) {
                if (ctx->out_slots[i].valid &&
                    ctx->out_slots[i].frame_tag == ctx->writer_expected_tag) {
                    found = i;
                    break;
                }
            }
            if (found >= 0) break;
            if (ctx->stop_requested && ctx->out_count == 0) {
                pthread_mutex_unlock(&ctx->out_lock);
                return NULL;
            }
            waited = 1;
            pthread_cond_wait(&ctx->out_not_empty, &ctx->out_lock);
        }
        if (waited) ctx->stats.writer_waited++;

        output_slot *out = &ctx->out_slots[found];
        const uint8_t *vc5 = out->copy_buf;
        size_t vc5_size = out->vc5_size;
        uint64_t tag = out->frame_tag;
        /* Release lock around the writer callback (writer may be slow). The
           slot stays marked valid=1 with this tag, but no encoder will look
           at it (they pick free slots), and no other writer will look at
           it (single writer thread). */
        pthread_mutex_unlock(&ctx->out_lock);

        int rc = ctx->writer(ctx->writer_data, vc5, vc5_size, tag);
        if (rc != 0) {
            ctx->stats.writer_errors++;
        }

        pthread_mutex_lock(&ctx->out_lock);
        out->valid = 0;
        ctx->out_count--;
        ctx->writer_expected_tag++;
        ctx->stats.frames_written++;
        pthread_cond_broadcast(&ctx->out_not_full);
        pthread_mutex_unlock(&ctx->out_lock);
    }
    return NULL;
}

void gpr_video_encoder_flush(GPR_VIDEO_ENCODER *ctx)
{
    if (!ctx) return;
    /* Wait for all per-encoder input rings to drain, then for the output
       ring to drain. We poll with a short condition wait on out_not_full
       (which fires every time the writer completes a frame). */
    for (;;) {
        int any_pending = 0;
        for (int e = 0; e < ctx->encoder_count; e++) {
            pthread_mutex_lock(&ctx->encs[e].in_lock);
            if (ctx->encs[e].in_count > 0) any_pending = 1;
            pthread_mutex_unlock(&ctx->encs[e].in_lock);
        }
        if (!any_pending) break;
        pthread_mutex_lock(&ctx->out_lock);
        /* Wait for any forward progress; out_not_full is signaled on writer
           completion. If the writer is idle and output is empty, the
           encoder is the active stage — yield briefly. */
        if (ctx->out_count > 0) {
            pthread_cond_wait(&ctx->out_not_full, &ctx->out_lock);
            pthread_mutex_unlock(&ctx->out_lock);
        } else {
            pthread_mutex_unlock(&ctx->out_lock);
            /* Encoder is mid-frame with empty output; sleep a tick.
               This matches the prior single-encoder code's behavior. */
            struct timespec ts = { 0, 1 * 1000 * 1000 };  /* 1 ms */
            nanosleep(&ts, NULL);
        }
    }

    pthread_mutex_lock(&ctx->out_lock);
    while (ctx->out_count > 0) {
        pthread_cond_wait(&ctx->out_not_full, &ctx->out_lock);
    }
    pthread_mutex_unlock(&ctx->out_lock);
}

void gpr_video_encoder_destroy(GPR_VIDEO_ENCODER *ctx)
{
    if (!ctx) return;
    if (ctx->threads_started) {
        gpr_video_encoder_flush(ctx);
        ctx->stop_requested = 1;
        for (int e = 0; e < ctx->encoder_count; e++) {
            pthread_mutex_lock(&ctx->encs[e].in_lock);
            pthread_cond_broadcast(&ctx->encs[e].in_not_empty);
            pthread_cond_broadcast(&ctx->encs[e].in_not_full);
            pthread_mutex_unlock(&ctx->encs[e].in_lock);
        }
        pthread_mutex_lock(&ctx->out_lock);
        pthread_cond_broadcast(&ctx->out_not_empty);
        pthread_cond_broadcast(&ctx->out_not_full);
        pthread_mutex_unlock(&ctx->out_lock);
        for (int e = 0; e < ctx->encoder_count; e++) {
            pthread_join(ctx->encs[e].thread, NULL);
        }
        pthread_join(ctx->writer_thread, NULL);
    }
    for (int e = 0; e < ctx->encoder_count; e++) {
        if (ctx->encs[e].fused_ctx) gpr_encode_fused_destroy(ctx->encs[e].fused_ctx);
        if (ctx->encs[e].in_slots) {
            for (int i = 0; i < ctx->ring_depth; i++) {
                if (ctx->encs[e].in_slots[i].raw) free(ctx->encs[e].in_slots[i].raw);
            }
            free(ctx->encs[e].in_slots);
        }
        pthread_mutex_destroy(&ctx->encs[e].in_lock);
        pthread_cond_destroy(&ctx->encs[e].in_not_full);
        pthread_cond_destroy(&ctx->encs[e].in_not_empty);
    }
    if (ctx->out_slots) {
        for (int i = 0; i < ctx->out_ring_size; i++) {
            if (ctx->out_slots[i].copy_buf) free(ctx->out_slots[i].copy_buf);
        }
        free(ctx->out_slots);
    }
    pthread_mutex_destroy(&ctx->out_lock);
    pthread_cond_destroy(&ctx->out_not_full);
    pthread_cond_destroy(&ctx->out_not_empty);
    free(ctx);
}

void gpr_video_encoder_get_stats(const GPR_VIDEO_ENCODER *ctx,
                                  gpr_video_stats *out)
{
    if (!ctx || !out) return;
    *out = ctx->stats;
}
