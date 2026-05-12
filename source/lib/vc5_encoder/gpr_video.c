/*! @file gpr_video.c
 *
 *  @brief Pipelined video encoder implementation.
 *  See gpr_video.h for design notes.
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

typedef struct {
    uint8_t *raw;          /* owned, pre-allocated raw frame slot */
    size_t   raw_capacity;
    size_t   raw_size;     /* size of the frame in this slot */
    uint64_t frame_tag;
} input_slot;

typedef struct {
    uint8_t *vc5;          /* points into a per-slot encoded buffer */
    size_t   vc5_size;
    uint64_t frame_tag;
    /* The encoded bitstream lives in the fused encoder's persistent
       output buffer. We snapshot the pointer + size; the encoder owns
       the storage. To keep the writer thread from racing the next
       encode, we use a dedicated copy buffer per output slot. */
    uint8_t *copy_buf;     /* owned, holds the copied bitstream */
    size_t   copy_capacity;
} output_slot;

struct GPR_VIDEO_ENCODER {
    int width, height;
    int pixel_format;
    int quality;
    int ring_depth;

    /* Underlying fused encoder context (owned by encoder thread) */
    FUSED_ENCODER *fused_ctx;
    int denoise_set;
    double noise_scale, noise_offset, denoise_strength;

    /* Adaptive bitrate state (encoder-thread-only access).
       target_bytes_per_frame=0 means rate control disabled. */
    double target_bytes_per_frame;
    double rc_avg_bytes;        /* EMA of recent vc5 sizes */
    double rc_scale;            /* current quant scale to apply on next frame */
    int    rc_frames_seen;      /* warms the EMA */

    /* Input ring: caller produces, encoder consumes (SPSC) */
    input_slot  *in_slots;
    int          in_head;   /* next slot for producer to fill */
    int          in_tail;   /* next slot for consumer to read */
    int          in_count;  /* number of filled slots */
    pthread_mutex_t in_lock;
    pthread_cond_t  in_not_full;
    pthread_cond_t  in_not_empty;

    /* Output ring: encoder produces, writer consumes (SPSC) */
    output_slot *out_slots;
    int          out_head;
    int          out_tail;
    int          out_count;
    pthread_mutex_t out_lock;
    pthread_cond_t  out_not_full;
    pthread_cond_t  out_not_empty;

    /* Worker threads */
    pthread_t encoder_thread;
    pthread_t writer_thread;
    int threads_started;
    int stop_requested;

    /* Writer callback */
    gpr_video_writer_fn writer;
    void *writer_data;

    /* Stats (updated under their respective locks for the counters that
       can be racy, atomic increments where simpler) */
    gpr_video_stats stats;
};

static void *encoder_thread_fn(void *arg);
static void *writer_thread_fn(void *arg);

GPR_VIDEO_ENCODER *gpr_video_encoder_create(
    int width, int height,
    int pixel_format, int quality,
    int ring_depth,
    gpr_video_writer_fn writer, void *user_data)
{
    if (width <= 0 || height <= 0 || ring_depth < 1 || !writer) return NULL;
    if (ring_depth > VIDEO_MAX_RING_DEPTH) ring_depth = VIDEO_MAX_RING_DEPTH;

    GPR_VIDEO_ENCODER *ctx = (GPR_VIDEO_ENCODER *)calloc(1, sizeof(*ctx));
    if (!ctx) return NULL;

    ctx->width = width;
    ctx->height = height;
    ctx->pixel_format = pixel_format;
    ctx->quality = quality;
    ctx->ring_depth = ring_depth;
    ctx->writer = writer;
    ctx->writer_data = user_data;

    /* The fused encoder will be created inside the encoder thread because
       it owns FUSED_THREADS / FUSED_INLINE_TOKENIZE env interpretation. */
    pthread_mutex_init(&ctx->in_lock, NULL);
    pthread_cond_init(&ctx->in_not_full, NULL);
    pthread_cond_init(&ctx->in_not_empty, NULL);
    pthread_mutex_init(&ctx->out_lock, NULL);
    pthread_cond_init(&ctx->out_not_full, NULL);
    pthread_cond_init(&ctx->out_not_empty, NULL);

    /* Allocate input ring slots: each holds a full raw frame (~100 MB at 50 MP). */
    size_t raw_size = (size_t)width * (size_t)height * 2;  /* 16-bit Bayer */
    ctx->in_slots = (input_slot *)calloc(ring_depth, sizeof(input_slot));
    if (!ctx->in_slots) goto fail;
    for (int i = 0; i < ring_depth; i++) {
        ctx->in_slots[i].raw = (uint8_t *)malloc(raw_size);
        if (!ctx->in_slots[i].raw) goto fail;
        ctx->in_slots[i].raw_capacity = raw_size;
    }

    /* Allocate output ring slots. Bitstream size is bounded by the fused
       encoder's worst-case (about 30% of raw). Pre-allocate at half-of-raw
       to be safe. */
    size_t vc5_capacity = raw_size / 2;
    ctx->out_slots = (output_slot *)calloc(ring_depth, sizeof(output_slot));
    if (!ctx->out_slots) goto fail;
    for (int i = 0; i < ring_depth; i++) {
        ctx->out_slots[i].copy_buf = (uint8_t *)malloc(vc5_capacity);
        if (!ctx->out_slots[i].copy_buf) goto fail;
        ctx->out_slots[i].copy_capacity = vc5_capacity;
    }

    /* Start worker threads. */
    if (pthread_create(&ctx->encoder_thread, NULL, encoder_thread_fn, ctx) != 0)
        goto fail;
    if (pthread_create(&ctx->writer_thread, NULL, writer_thread_fn, ctx) != 0) {
        ctx->stop_requested = 1;
        pthread_cond_broadcast(&ctx->in_not_empty);
        pthread_join(ctx->encoder_thread, NULL);
        goto fail;
    }
    ctx->threads_started = 1;

    return ctx;

fail:
    gpr_video_encoder_destroy(ctx);
    return NULL;
}

void gpr_video_encoder_set_denoise(GPR_VIDEO_ENCODER *ctx,
                                    double noise_scale,
                                    double noise_offset,
                                    double strength)
{
    if (!ctx) return;
    /* Stored on the context; encoder thread will apply on its fused context.
       The encoder thread polls this once before the first frame. */
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
    ctx->rc_scale = 1.0;
    ctx->rc_avg_bytes = 0.0;
    ctx->rc_frames_seen = 0;
}

int gpr_video_encoder_submit(GPR_VIDEO_ENCODER *ctx,
                              const uint8_t *raw_bayer, size_t raw_size,
                              uint64_t frame_tag)
{
    if (!ctx || !raw_bayer) return -1;

    pthread_mutex_lock(&ctx->in_lock);
    int waited = 0;
    while (ctx->in_count >= ctx->ring_depth && !ctx->stop_requested) {
        waited = 1;
        pthread_cond_wait(&ctx->in_not_full, &ctx->in_lock);
    }
    if (ctx->stop_requested) {
        pthread_mutex_unlock(&ctx->in_lock);
        return -1;
    }
    if (waited) ctx->stats.submit_waited++;

    input_slot *slot = &ctx->in_slots[ctx->in_head];
    if (raw_size > slot->raw_capacity) raw_size = slot->raw_capacity;
    memcpy(slot->raw, raw_bayer, raw_size);
    slot->raw_size = raw_size;
    slot->frame_tag = frame_tag;

    ctx->in_head = (ctx->in_head + 1) % ctx->ring_depth;
    ctx->in_count++;
    ctx->stats.frames_submitted++;
    pthread_cond_signal(&ctx->in_not_empty);
    pthread_mutex_unlock(&ctx->in_lock);
    return 0;
}

static void *encoder_thread_fn(void *arg)
{
    GPR_VIDEO_ENCODER *ctx = (GPR_VIDEO_ENCODER *)arg;

    /* Create the fused encoder inside this thread so any thread-local state
       lives where it'll be used. */
    FUSED_ENCODER *fused = gpr_encode_fused_create(ctx->width, ctx->height,
                                                    ctx->pixel_format, ctx->quality);
    if (!fused) {
        ctx->stop_requested = 1;
        pthread_cond_broadcast(&ctx->in_not_full);
        pthread_cond_broadcast(&ctx->out_not_empty);
        return NULL;
    }
    if (ctx->denoise_set) {
        gpr_encode_fused_set_denoise(fused, ctx->noise_scale, ctx->noise_offset,
                                      ctx->denoise_strength);
    }
    ctx->fused_ctx = fused;

    for (;;) {
        /* Pop a frame from input ring. */
        pthread_mutex_lock(&ctx->in_lock);
        while (ctx->in_count == 0 && !ctx->stop_requested) {
            pthread_cond_wait(&ctx->in_not_empty, &ctx->in_lock);
        }
        if (ctx->in_count == 0 && ctx->stop_requested) {
            pthread_mutex_unlock(&ctx->in_lock);
            break;
        }
        input_slot *in = &ctx->in_slots[ctx->in_tail];
        /* Keep the slot reserved while we encode (we hold ownership of in->raw
           via the tail pointer). Don't advance tail until encoding is done. */
        pthread_mutex_unlock(&ctx->in_lock);

        /* Apply adaptive bitrate scale (if enabled) before encoding. */
        if (ctx->target_bytes_per_frame > 0.0) {
            gpr_encode_fused_set_quant_scale(fused, ctx->rc_scale);
        }

        /* Encode (this is where the fused encoder runs its 4 internal threads). */
        uint8_t *vc5_out = NULL;
        size_t vc5_size = 0;
        int rc = gpr_encode_fused_frame(fused, in->raw, in->raw_size, &vc5_out, &vc5_size);

        /* Update rate controller. Smooth output size with an EMA, then
           adjust the scale toward the target. Use sqrt(error) so we move
           gently — frame sizes for noisy content can swing wide. */
        if (ctx->target_bytes_per_frame > 0.0 && rc == 0 && vc5_size > 0) {
            const double alpha = 0.7;       /* EMA weight on history */
            if (ctx->rc_frames_seen == 0) ctx->rc_avg_bytes = (double)vc5_size;
            else ctx->rc_avg_bytes = ctx->rc_avg_bytes * alpha + (double)vc5_size * (1.0 - alpha);
            ctx->rc_frames_seen++;

            double err = ctx->rc_avg_bytes / ctx->target_bytes_per_frame;
            /* sqrt damps overshoot; clamp the multiplicative step too */
            double step = sqrt(err);
            if (step < 0.85) step = 0.85;
            if (step > 1.20) step = 1.20;
            double new_scale = ctx->rc_scale * step;
            if (new_scale < 0.25) new_scale = 0.25;
            if (new_scale > 16.0) new_scale = 16.0;
            ctx->rc_scale = new_scale;
        }

        if (rc == 0 && vc5_out && vc5_size > 0) {
            /* Push to output ring, copying the bitstream into the slot
               (so the fused encoder's persistent buffer is free to be
               reused for the next frame immediately). */
            pthread_mutex_lock(&ctx->out_lock);
            int waited = 0;
            while (ctx->out_count >= ctx->ring_depth && !ctx->stop_requested) {
                waited = 1;
                pthread_cond_wait(&ctx->out_not_full, &ctx->out_lock);
            }
            if (ctx->stop_requested) {
                pthread_mutex_unlock(&ctx->out_lock);
                break;
            }
            if (waited) ctx->stats.encoder_waited++;

            output_slot *out = &ctx->out_slots[ctx->out_head];
            size_t copy_size = (vc5_size <= out->copy_capacity) ? vc5_size : out->copy_capacity;
            memcpy(out->copy_buf, vc5_out, copy_size);
            out->vc5 = out->copy_buf;
            out->vc5_size = copy_size;
            out->frame_tag = in->frame_tag;

            ctx->out_head = (ctx->out_head + 1) % ctx->ring_depth;
            ctx->out_count++;
            ctx->stats.frames_encoded++;
            pthread_cond_signal(&ctx->out_not_empty);
            pthread_mutex_unlock(&ctx->out_lock);
        }

        /* Release the input slot now. */
        pthread_mutex_lock(&ctx->in_lock);
        ctx->in_tail = (ctx->in_tail + 1) % ctx->ring_depth;
        ctx->in_count--;
        pthread_cond_signal(&ctx->in_not_full);
        pthread_mutex_unlock(&ctx->in_lock);
    }

    /* Wake the writer in case it's waiting */
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
        int waited = 0;
        while (ctx->out_count == 0 && !ctx->stop_requested) {
            waited = 1;
            pthread_cond_wait(&ctx->out_not_empty, &ctx->out_lock);
        }
        if (ctx->out_count == 0 && ctx->stop_requested) {
            pthread_mutex_unlock(&ctx->out_lock);
            break;
        }
        if (waited) ctx->stats.writer_waited++;
        output_slot *out = &ctx->out_slots[ctx->out_tail];
        /* Hold reference, release lock around the writer callback (writer
           may be slow — must not block encoder pushing into other slots). */
        const uint8_t *vc5 = out->vc5;
        size_t vc5_size = out->vc5_size;
        uint64_t tag = out->frame_tag;
        pthread_mutex_unlock(&ctx->out_lock);

        int rc = ctx->writer(ctx->writer_data, vc5, vc5_size, tag);
        if (rc != 0) {
            ctx->stats.writer_errors++;
        }

        pthread_mutex_lock(&ctx->out_lock);
        ctx->out_tail = (ctx->out_tail + 1) % ctx->ring_depth;
        ctx->out_count--;
        ctx->stats.frames_written++;
        pthread_cond_signal(&ctx->out_not_full);
        pthread_mutex_unlock(&ctx->out_lock);
    }
    return NULL;
}

void gpr_video_encoder_flush(GPR_VIDEO_ENCODER *ctx)
{
    if (!ctx) return;
    /* Wait for input ring + output ring to drain. */
    pthread_mutex_lock(&ctx->in_lock);
    while (ctx->in_count > 0) {
        pthread_mutex_unlock(&ctx->in_lock);
        /* yield-style: spin via condvar on out_lock change */
        pthread_mutex_lock(&ctx->out_lock);
        if (ctx->out_count > 0)
            pthread_cond_wait(&ctx->out_not_full, &ctx->out_lock);
        pthread_mutex_unlock(&ctx->out_lock);
        pthread_mutex_lock(&ctx->in_lock);
    }
    pthread_mutex_unlock(&ctx->in_lock);

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
        pthread_mutex_lock(&ctx->in_lock);
        ctx->stop_requested = 1;
        pthread_cond_broadcast(&ctx->in_not_empty);
        pthread_cond_broadcast(&ctx->in_not_full);
        pthread_mutex_unlock(&ctx->in_lock);
        pthread_mutex_lock(&ctx->out_lock);
        pthread_cond_broadcast(&ctx->out_not_empty);
        pthread_cond_broadcast(&ctx->out_not_full);
        pthread_mutex_unlock(&ctx->out_lock);
        pthread_join(ctx->encoder_thread, NULL);
        pthread_join(ctx->writer_thread, NULL);
    }
    if (ctx->fused_ctx) gpr_encode_fused_destroy(ctx->fused_ctx);
    if (ctx->in_slots) {
        for (int i = 0; i < ctx->ring_depth; i++) {
            if (ctx->in_slots[i].raw) free(ctx->in_slots[i].raw);
        }
        free(ctx->in_slots);
    }
    if (ctx->out_slots) {
        for (int i = 0; i < ctx->ring_depth; i++) {
            if (ctx->out_slots[i].copy_buf) free(ctx->out_slots[i].copy_buf);
        }
        free(ctx->out_slots);
    }
    pthread_mutex_destroy(&ctx->in_lock);
    pthread_cond_destroy(&ctx->in_not_full);
    pthread_cond_destroy(&ctx->in_not_empty);
    pthread_mutex_destroy(&ctx->out_lock);
    pthread_cond_destroy(&ctx->out_not_full);
    pthread_cond_destroy(&ctx->out_not_empty);
    free(ctx);
}

void gpr_video_encoder_get_stats(const GPR_VIDEO_ENCODER *ctx,
                                  gpr_video_stats *out)
{
    if (!ctx || !out) return;
    /* Snapshot — counters are 64-bit so they're aligned-load-atomic on aarch64. */
    *out = ctx->stats;
}
