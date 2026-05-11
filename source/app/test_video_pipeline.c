/* Video pipeline benchmark — producer → encoder → writer with ring buffers.
 *
 * Measures the wall-time difference between sequential (read → encode → write
 * per frame) and 3-stage pipelined operation.
 *
 * Storage speeds are configurable so we can simulate the embedded environment
 * (SD card vs internal eMMC vs NVMe). On M1 the in-memory "I/O" is too fast
 * for any pipeline win to show up — that's the point of the simulated delays.
 *
 * Build:
 *   clang -O2 -o /tmp/test_video_pipeline source/app/test_video_pipeline.c \
 *     build/source/lib/vc5_encoder/libvc5_encoder.a \
 *     build/source/lib/vc5_common/libvc5_common.a -lpthread
 *
 * Usage:
 *   test_video_pipeline raw_file width height read_ms write_ms n_frames
 *
 * Example (HERO10 23 MP, SD-card-like writes at 60 ms/frame):
 *   test_video_pipeline /tmp/hero10_test.raw 5568 4176 20 30 10
 *
 * Sample results on M1 (HERO10 23 MP, 10 frames):
 *   read=20 write=30:  seq 67 ms/frame, pipe 34 ms/frame → 1.98x speedup
 *   read=10 write=60:  seq 87 ms/frame, pipe 63 ms/frame → 1.38x speedup
 *   read=100 write=60: seq 178 ms/frame, pipe 109 ms/frame → 1.63x speedup
 *
 * Maximum pipeline speedup is bounded by the ratio of (sum of all stages)
 * to (slowest single stage). Best speedup happens when the three stages are
 * roughly equal — the realistic embedded scenario.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <pthread.h>
#include <mach/mach_time.h>

typedef struct FUSED_ENCODER FUSED_ENCODER;
extern FUSED_ENCODER *gpr_encode_fused_create(int w, int h, int pf, int q);
extern int gpr_encode_fused_frame(FUSED_ENCODER *ctx,
    const unsigned char *raw, size_t sz, unsigned char **out, size_t *out_sz);
extern void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);

static double _s = 0;
static double now_ms(void) {
    if (!_s) { mach_timebase_info_data_t i; mach_timebase_info(&i); _s=(double)i.numer/i.denom/1e6; }
    return mach_absolute_time() * _s;
}

/* Busy-wait the specified ms (avoids OS scheduler dithering at small intervals). */
static void delay_ms(double ms) {
    if (ms <= 0) return;
    double end = now_ms() + ms;
    while (now_ms() < end) { /* spin */ }
}

/* ============================================================
 * Ring buffer infrastructure — single producer / single consumer
 * ============================================================ */
typedef struct {
    void *items[8];      /* power of 2 */
    int head, tail;
    int mask;            /* size - 1 */
    pthread_mutex_t lock;
    pthread_cond_t  not_full, not_empty;
    int closed;
} RING;

static void ring_init(RING *r, int size) {
    r->head = r->tail = 0;
    r->mask = size - 1;
    r->closed = 0;
    pthread_mutex_init(&r->lock, NULL);
    pthread_cond_init(&r->not_full, NULL);
    pthread_cond_init(&r->not_empty, NULL);
}

static void ring_push(RING *r, void *item) {
    pthread_mutex_lock(&r->lock);
    while (((r->head + 1) & r->mask) == (r->tail & r->mask) && !r->closed) {
        pthread_cond_wait(&r->not_full, &r->lock);
    }
    r->items[r->head & r->mask] = item;
    r->head++;
    pthread_cond_signal(&r->not_empty);
    pthread_mutex_unlock(&r->lock);
}

static void *ring_pop(RING *r) {
    pthread_mutex_lock(&r->lock);
    while (r->head == r->tail && !r->closed) {
        pthread_cond_wait(&r->not_empty, &r->lock);
    }
    void *item = NULL;
    if (r->head != r->tail) {
        item = r->items[r->tail & r->mask];
        r->tail++;
        pthread_cond_signal(&r->not_full);
    }
    pthread_mutex_unlock(&r->lock);
    return item;
}

static void ring_close(RING *r) {
    pthread_mutex_lock(&r->lock);
    r->closed = 1;
    pthread_cond_broadcast(&r->not_empty);
    pthread_cond_broadcast(&r->not_full);
    pthread_mutex_unlock(&r->lock);
}

/* ============================================================
 * Pipeline stages
 * ============================================================ */
typedef struct {
    const unsigned char *src_raw;
    size_t raw_size;
    int n_frames;
    double read_ms;
    double write_ms;
    RING *raw_ring;            /* producer → encoder */
    RING *enc_ring;            /* encoder → writer */
    FUSED_ENCODER *encoder;
    int w, h;
    /* Pool of pre-allocated raw-frame buffers to avoid alloc churn */
    unsigned char *raw_pool[8];
    int raw_pool_avail[8];
    pthread_mutex_t pool_lock;
    pthread_cond_t  pool_avail;
} PIPELINE;

static unsigned char *pool_take(PIPELINE *p) {
    pthread_mutex_lock(&p->pool_lock);
    while (1) {
        for (int i = 0; i < 8; i++) {
            if (p->raw_pool_avail[i]) {
                p->raw_pool_avail[i] = 0;
                unsigned char *buf = p->raw_pool[i];
                pthread_mutex_unlock(&p->pool_lock);
                return buf;
            }
        }
        pthread_cond_wait(&p->pool_avail, &p->pool_lock);
    }
}

static void pool_return(PIPELINE *p, unsigned char *buf) {
    pthread_mutex_lock(&p->pool_lock);
    for (int i = 0; i < 8; i++) {
        if (p->raw_pool[i] == buf) {
            p->raw_pool_avail[i] = 1;
            pthread_cond_signal(&p->pool_avail);
            break;
        }
    }
    pthread_mutex_unlock(&p->pool_lock);
}

static void *producer_thread(void *arg) {
    PIPELINE *p = (PIPELINE *)arg;
    for (int i = 0; i < p->n_frames; i++) {
        unsigned char *buf = pool_take(p);
        /* Simulate disk read: memcpy + configurable delay */
        memcpy(buf, p->src_raw, p->raw_size);
        delay_ms(p->read_ms);
        ring_push(p->raw_ring, buf);
    }
    ring_close(p->raw_ring);
    return NULL;
}

typedef struct {
    unsigned char *bytes;
    size_t size;
    unsigned char *raw_buf;  /* the raw buffer to return to pool when done */
} ENC_FRAME;

static void *encoder_thread(void *arg) {
    PIPELINE *p = (PIPELINE *)arg;
    for (int i = 0; i < p->n_frames; i++) {
        unsigned char *raw = (unsigned char *)ring_pop(p->raw_ring);
        if (!raw) break;
        unsigned char *out = NULL;
        size_t out_sz = 0;
        gpr_encode_fused_frame(p->encoder, raw, p->raw_size, &out, &out_sz);
        ENC_FRAME *ef = malloc(sizeof(*ef));
        ef->bytes = out;     /* points into encoder ctx (do NOT free) */
        ef->size = out_sz;
        ef->raw_buf = raw;
        ring_push(p->enc_ring, ef);
    }
    ring_close(p->enc_ring);
    return NULL;
}

static void *writer_thread(void *arg) {
    PIPELINE *p = (PIPELINE *)arg;
    static unsigned char sink[1024 * 1024 * 32];  /* 32 MB sink, large enough */
    for (int i = 0; i < p->n_frames; i++) {
        ENC_FRAME *ef = (ENC_FRAME *)ring_pop(p->enc_ring);
        if (!ef) break;
        size_t copy = ef->size > sizeof(sink) ? sizeof(sink) : ef->size;
        memcpy(sink, ef->bytes, copy);
        delay_ms(p->write_ms);
        pool_return(p, ef->raw_buf);
        free(ef);
    }
    return NULL;
}

/* ============================================================
 * Sequential reference (no pipelining)
 * ============================================================ */
static double run_sequential(PIPELINE *p) {
    static unsigned char sink[1024 * 1024 * 32];
    unsigned char *raw = malloc(p->raw_size);
    double t0 = now_ms();
    for (int i = 0; i < p->n_frames; i++) {
        memcpy(raw, p->src_raw, p->raw_size);
        delay_ms(p->read_ms);
        unsigned char *out = NULL; size_t out_sz = 0;
        gpr_encode_fused_frame(p->encoder, raw, p->raw_size, &out, &out_sz);
        size_t copy = out_sz > sizeof(sink) ? sizeof(sink) : out_sz;
        memcpy(sink, out, copy);
        delay_ms(p->write_ms);
    }
    double t1 = now_ms();
    free(raw);
    return t1 - t0;
}

/* ============================================================
 * Pipelined run (3 threads)
 * ============================================================ */
static double run_pipelined(PIPELINE *p) {
    /* Init pool */
    for (int i = 0; i < 8; i++) {
        p->raw_pool[i] = malloc(p->raw_size);
        p->raw_pool_avail[i] = 1;
    }
    pthread_mutex_init(&p->pool_lock, NULL);
    pthread_cond_init(&p->pool_avail, NULL);

    RING raw_ring, enc_ring;
    ring_init(&raw_ring, 8);
    ring_init(&enc_ring, 8);
    p->raw_ring = &raw_ring;
    p->enc_ring = &enc_ring;

    pthread_t prod, enc, wri;
    double t0 = now_ms();
    pthread_create(&prod, NULL, producer_thread, p);
    pthread_create(&enc,  NULL, encoder_thread,  p);
    pthread_create(&wri,  NULL, writer_thread,   p);
    pthread_join(prod, NULL);
    pthread_join(enc,  NULL);
    pthread_join(wri,  NULL);
    double t1 = now_ms();

    for (int i = 0; i < 8; i++) free(p->raw_pool[i]);
    return t1 - t0;
}

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr, "usage: %s raw_file W H read_ms write_ms n_frames\n", argv[0]);
        return 1;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("fopen"); return 1; }
    fseek(f, 0, SEEK_END); size_t sz = ftell(f); rewind(f);
    unsigned char *src = malloc(sz);
    fread(src, 1, sz, f); fclose(f);
    int w = atoi(argv[2]), h = atoi(argv[3]);
    double read_ms = atof(argv[4]), write_ms = atof(argv[5]);
    int n_frames = atoi(argv[6]);

    PIPELINE p;
    memset(&p, 0, sizeof(p));
    p.src_raw = src;
    p.raw_size = sz;
    p.n_frames = n_frames;
    p.read_ms = read_ms;
    p.write_ms = write_ms;
    p.w = w; p.h = h;
    p.encoder = gpr_encode_fused_create(w, h, 1, 3);
    if (!p.encoder) { fprintf(stderr, "encoder create failed\n"); return 1; }

    fprintf(stderr, "Config: %dx%d, %d frames, read=%.1fms, write=%.1fms\n",
            w, h, n_frames, read_ms, write_ms);
    fprintf(stderr, "Raw size: %.1f MB, sim total I/O = %.1f ms/frame\n\n",
            sz / 1024.0 / 1024.0, read_ms + write_ms);

    /* Warm */
    {
        unsigned char *out = NULL; size_t os = 0;
        gpr_encode_fused_frame(p.encoder, src, sz, &out, &os);
    }

    double seq_ms = run_sequential(&p);
    fprintf(stderr, "Sequential:  %.1f ms total  →  %.2f ms/frame  →  %.1f fps\n",
            seq_ms, seq_ms / n_frames, 1000.0 * n_frames / seq_ms);

    double par_ms = run_pipelined(&p);
    fprintf(stderr, "Pipelined:   %.1f ms total  →  %.2f ms/frame  →  %.1f fps\n",
            par_ms, par_ms / n_frames, 1000.0 * n_frames / par_ms);

    double speedup = seq_ms / par_ms;
    fprintf(stderr, "Speedup:     %.2fx  (saves %.1f ms/frame)\n",
            speedup, (seq_ms - par_ms) / n_frames);

    gpr_encode_fused_destroy(p.encoder);
    free(src);
    return 0;
}
