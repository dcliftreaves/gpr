/* Clean per-frame microbenchmark for the fused encoder.
 *
 * No producer/consumer threading, no memcpy per frame, no malloc churn.
 * Encodes the same raw buffer N times against a persistent encoder context
 * and reports min/p25/median/p75/max + fps.
 *
 * Usage: bench_clean <raw_file> <width> <height> <n_iters>
 *
 * The Bayer pattern defaults to pixel_format = 4 (RGGB16). Override with
 * GPR_BENCH_PIXEL_FORMAT=<0..5>.
 * To force quality, set FUSED_QUALITY=<0..11>.
 *
 * Companion to tools/pi_benchmark.sh (which sweeps env flags).
 */
#if !defined(__APPLE__)
#  ifndef _GNU_SOURCE
#  define _GNU_SOURCE 1
#  endif
#endif
#define _POSIX_C_SOURCE 200809L  /* snprintf, etc. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#if !defined(_WIN32)
#include <fcntl.h>
#include <dirent.h>
#include <pthread.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>
#if defined(__linux__)
#include <sched.h>
#endif
#if defined(__linux__) && !defined(SYNC_FILE_RANGE_WRITE)
#define SYNC_FILE_RANGE_WRITE 1
#endif
#if defined(__linux__)
extern long syscall(long number, ...);
#endif
#endif

#include "gpr_video_format.h"

typedef struct FUSED_ENCODER FUSED_ENCODER;
extern FUSED_ENCODER *gpr_encode_fused_create(int w, int h, int pf, int q);
extern int gpr_encode_fused_frame(FUSED_ENCODER *ctx, const unsigned char *raw,
                                   size_t sz, unsigned char **out, size_t *out_sz);
extern int gpr_encode_fused_frame_scatter(FUSED_ENCODER *ctx,
                                   const unsigned char *raw, size_t sz,
                                   const unsigned char ***parts,
                                   const size_t **part_sizes,
                                   int *part_count,
                                   size_t *out_sz);
extern void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);
extern void gpr_encode_fused_set_denoise(FUSED_ENCODER *ctx,
                                         double noise_scale,
                                         double noise_offset,
                                         double strength);

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1.0e6;
}

static int cmp_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

static void print_phase_summary(const char *name, const double *values, int n) {
    if (!values || n <= 0) return;
    double *sorted = (double *)malloc((size_t)n * sizeof(double));
    if (!sorted) return;
    memcpy(sorted, values, (size_t)n * sizeof(double));
    qsort(sorted, (size_t)n, sizeof(double), cmp_double);
    double sum = 0.0;
    double sum_sq = 0.0;
    for (int i = 0; i < n; i++) {
        sum += sorted[i];
        sum_sq += sorted[i] * sorted[i];
    }
    double mean = sum / n;
    double var = sum_sq / n - mean * mean;
    int p25 = n / 4;
    int p50 = n / 2;
    int p75 = (3 * n) / 4;
    int p95 = (int)((double)(n - 1) * 0.95 + 0.5);
    int p99 = (int)((double)(n - 1) * 0.99 + 0.5);
    if (p95 < 0) p95 = 0; if (p95 >= n) p95 = n - 1;
    if (p99 < 0) p99 = 0; if (p99 >= n) p99 = n - 1;
    fprintf(stderr,
        "# bench_phase_ms %s n=%d mean=%.3f stddev=%.3f min=%.3f p25=%.3f median=%.3f p75=%.3f p95=%.3f p99=%.3f max=%.3f\n",
        name, n, mean, var > 0 ? __builtin_sqrt(var) : 0.0,
        sorted[0], sorted[p25], sorted[p50], sorted[p75],
        sorted[p95], sorted[p99], sorted[n - 1]);
    free(sorted);
}

typedef struct RAW_CORPUS {
    unsigned char **frames;
    char **names;
    int count;
    size_t frame_size;
} RAW_CORPUS;

static int cmp_string_ptr(const void *a, const void *b) {
    const char *sa = *(const char * const *)a;
    const char *sb = *(const char * const *)b;
    return strcmp(sa, sb);
}

static int has_raw_suffix(const char *name) {
    size_t n = strlen(name);
    return n >= 4 && strcmp(name + n - 4, ".raw") == 0;
}

static int path_is_dir(const char *path) {
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

static void raw_corpus_free(RAW_CORPUS *c) {
    if (!c) return;
    if (c->frames) {
        for (int i = 0; i < c->count; i++) free(c->frames[i]);
    }
    if (c->names) {
        for (int i = 0; i < c->count; i++) free(c->names[i]);
    }
    free(c->frames);
    free(c->names);
    c->frames = NULL;
    c->names = NULL;
    c->count = 0;
}

static int read_exact_file(const char *path, unsigned char *dst, size_t sz) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    size_t got = fread(dst, 1, sz, f);
    int extra = fgetc(f);
    fclose(f);
    return (got == sz && extra == EOF) ? 0 : -1;
}

static int raw_corpus_load(const char *path, size_t frame_size, RAW_CORPUS *out) {
    memset(out, 0, sizeof(*out));
    out->frame_size = frame_size;
    if (!path_is_dir(path)) {
        out->frames = (unsigned char **)calloc(1, sizeof(unsigned char *));
        out->names = (char **)calloc(1, sizeof(char *));
        if (!out->frames || !out->names) return -1;
        out->frames[0] = (unsigned char *)malloc(frame_size);
        out->names[0] = strdup(path);
        if (!out->frames[0] || !out->names[0]) return -1;
        if (read_exact_file(path, out->frames[0], frame_size) != 0) return -1;
        out->count = 1;
        return 0;
    }

    DIR *dir = opendir(path);
    if (!dir) return -1;
    int cap = 64;
    int count = 0;
    char **names = (char **)calloc((size_t)cap, sizeof(char *));
    if (!names) {
        closedir(dir);
        return -1;
    }
    struct dirent *ent = NULL;
    while ((ent = readdir(dir)) != NULL) {
        if (!has_raw_suffix(ent->d_name)) continue;
        if (count == cap) {
            cap *= 2;
            char **next = (char **)realloc(names, (size_t)cap * sizeof(char *));
            if (!next) {
                closedir(dir);
                for (int i = 0; i < count; i++) free(names[i]);
                free(names);
                return -1;
            }
            names = next;
        }
        names[count] = strdup(ent->d_name);
        if (!names[count]) {
            closedir(dir);
            for (int i = 0; i < count; i++) free(names[i]);
            free(names);
            return -1;
        }
        count++;
    }
    closedir(dir);
    if (count <= 0) {
        free(names);
        return -1;
    }
    qsort(names, (size_t)count, sizeof(char *), cmp_string_ptr);

    out->frames = (unsigned char **)calloc((size_t)count, sizeof(unsigned char *));
    out->names = (char **)calloc((size_t)count, sizeof(char *));
    if (!out->frames || !out->names) {
        for (int i = 0; i < count; i++) free(names[i]);
        free(names);
        return -1;
    }
    for (int i = 0; i < count; i++) {
        char fullpath[2048];
        snprintf(fullpath, sizeof(fullpath), "%s/%s", path, names[i]);
        out->frames[i] = (unsigned char *)malloc(frame_size);
        out->names[i] = names[i];
        if (!out->frames[i] || read_exact_file(fullpath, out->frames[i], frame_size) != 0) {
            free(names);
            return -1;
        }
        out->count++;
    }
    free(names);
    return 0;
}

#if !defined(_WIN32)
static int write_all_fd(int fd, const void *data, size_t size) {
    const unsigned char *p = (const unsigned char *)data;
    while (size > 0) {
        ssize_t n = write(fd, p, size);
        if (n <= 0) return -1;
        p += (size_t)n;
        size -= (size_t)n;
    }
    return 0;
}

static int writev_all2(int fd,
                       const void *a, size_t a_size,
                       const void *b, size_t b_size) {
    struct iovec iov[2];
    iov[0].iov_base = (void *)a;
    iov[0].iov_len = a_size;
    iov[1].iov_base = (void *)b;
    iov[1].iov_len = b_size;
    int iovcnt = 2;
    while (iovcnt > 0) {
        ssize_t n = writev(fd, iov, iovcnt);
        if (n <= 0) return -1;
        size_t done = (size_t)n;
        while (iovcnt > 0 && done >= iov[0].iov_len) {
            done -= iov[0].iov_len;
            iov[0] = iov[1];
            iovcnt--;
        }
        if (iovcnt > 0 && done > 0) {
            iov[0].iov_base = (unsigned char *)iov[0].iov_base + done;
            iov[0].iov_len -= done;
        }
    }
    return 0;
}

static int writev_all_many(int fd, const struct iovec *iov_in, int iovcnt) {
    struct iovec iov[32];
    if (iovcnt < 1 || iovcnt > (int)(sizeof(iov) / sizeof(iov[0]))) return -1;
    memcpy(iov, iov_in, (size_t)iovcnt * sizeof(iov[0]));
    int first = 0;
    while (first < iovcnt) {
        ssize_t n = writev(fd, iov + first, iovcnt - first);
        if (n <= 0) return -1;
        size_t done = (size_t)n;
        while (first < iovcnt && done >= iov[first].iov_len) {
            done -= iov[first].iov_len;
            first++;
        }
        if (first < iovcnt && done > 0) {
            iov[first].iov_base = (unsigned char *)iov[first].iov_base + done;
            iov[first].iov_len -= done;
        }
    }
    return 0;
}

static void maybe_start_writeback(int fd, off_t offset, off_t size, int enabled) {
    if (!enabled || fd < 0 || size <= 0) return;
#if defined(__linux__) && defined(SYS_sync_file_range) && defined(SYNC_FILE_RANGE_WRITE)
    (void)syscall(SYS_sync_file_range, fd, offset, size, SYNC_FILE_RANGE_WRITE);
#else
    (void)fd;
    (void)offset;
    (void)size;
#endif
}

typedef struct {
    unsigned char *data;
    size_t size;
    uint64_t tag;
} ASYNC_GVID_FRAME;

typedef struct {
    FILE *fp;
    ASYNC_GVID_FRAME *queue;
    int cap;
    int head;
    int tail;
    int count;
    int closed;
    int error;
    pthread_mutex_t lock;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
    pthread_t thread;
} ASYNC_GVID_WRITER;

static void async_gvid_set_error(ASYNC_GVID_WRITER *w) {
    pthread_mutex_lock(&w->lock);
    w->error = 1;
    pthread_cond_broadcast(&w->not_empty);
    pthread_cond_broadcast(&w->not_full);
    pthread_mutex_unlock(&w->lock);
}

static void *async_gvid_thread(void *arg) {
    ASYNC_GVID_WRITER *w = (ASYNC_GVID_WRITER *)arg;
    for (;;) {
        pthread_mutex_lock(&w->lock);
        while (w->count == 0 && !w->closed && !w->error) {
            pthread_cond_wait(&w->not_empty, &w->lock);
        }
        if (w->count == 0 && (w->closed || w->error)) {
            pthread_mutex_unlock(&w->lock);
            break;
        }
        ASYNC_GVID_FRAME frame = w->queue[w->head];
        w->queue[w->head].data = NULL;
        w->queue[w->head].size = 0;
        w->head = (w->head + 1) % w->cap;
        w->count--;
        int already_failed = w->error;
        pthread_cond_signal(&w->not_full);
        pthread_mutex_unlock(&w->lock);

        if (!already_failed) {
            uint8_t frame_header[GPR_VIDEO_FRAME_HEADER_SIZE];
            int n_frame = gpr_video_write_frame_header(
                frame_header, sizeof(frame_header), frame.size, frame.tag);
            if (n_frame != GPR_VIDEO_FRAME_HEADER_SIZE ||
                fwrite(frame_header, 1, sizeof(frame_header), w->fp) != sizeof(frame_header) ||
                fwrite(frame.data, 1, frame.size, w->fp) != frame.size) {
                async_gvid_set_error(w);
            }
        }
        free(frame.data);
    }
    return NULL;
}

static int async_gvid_start(ASYNC_GVID_WRITER *w, FILE *fp, int cap) {
    memset(w, 0, sizeof(*w));
    if (cap < 1) cap = 1;
    if (cap > 16) cap = 16;
    w->fp = fp;
    w->cap = cap;
    w->queue = (ASYNC_GVID_FRAME *)calloc((size_t)cap, sizeof(*w->queue));
    if (!w->queue) return -1;
    if (pthread_mutex_init(&w->lock, NULL) != 0) return -1;
    if (pthread_cond_init(&w->not_empty, NULL) != 0) return -1;
    if (pthread_cond_init(&w->not_full, NULL) != 0) return -1;
    if (pthread_create(&w->thread, NULL, async_gvid_thread, w) != 0) return -1;
    return 0;
}

static int async_gvid_submit(ASYNC_GVID_WRITER *w,
                             const unsigned char *data, size_t size,
                             uint64_t tag) {
    unsigned char *copy = (unsigned char *)malloc(size);
    if (!copy) return -1;
    memcpy(copy, data, size);

    pthread_mutex_lock(&w->lock);
    while (w->count == w->cap && !w->error) {
        pthread_cond_wait(&w->not_full, &w->lock);
    }
    if (w->error) {
        pthread_mutex_unlock(&w->lock);
        free(copy);
        return -1;
    }
    w->queue[w->tail] = (ASYNC_GVID_FRAME){ copy, size, tag };
    w->tail = (w->tail + 1) % w->cap;
    w->count++;
    pthread_cond_signal(&w->not_empty);
    pthread_mutex_unlock(&w->lock);
    return 0;
}

static int async_gvid_submit_take(ASYNC_GVID_WRITER *w,
                                  unsigned char *data, size_t size,
                                  uint64_t tag) {
    if (!data || size == 0) return -1;

    pthread_mutex_lock(&w->lock);
    while (w->count == w->cap && !w->error) {
        pthread_cond_wait(&w->not_full, &w->lock);
    }
    if (w->error) {
        pthread_mutex_unlock(&w->lock);
        free(data);
        return -1;
    }
    w->queue[w->tail] = (ASYNC_GVID_FRAME){ data, size, tag };
    w->tail = (w->tail + 1) % w->cap;
    w->count++;
    pthread_cond_signal(&w->not_empty);
    pthread_mutex_unlock(&w->lock);
    return 0;
}

static int async_gvid_stop(ASYNC_GVID_WRITER *w) {
    pthread_mutex_lock(&w->lock);
    w->closed = 1;
    pthread_cond_broadcast(&w->not_empty);
    pthread_mutex_unlock(&w->lock);
    pthread_join(w->thread, NULL);
    int error = w->error;
    for (int i = 0; i < w->cap; i++) {
        free(w->queue[i].data);
    }
    free(w->queue);
    pthread_cond_destroy(&w->not_empty);
    pthread_cond_destroy(&w->not_full);
    pthread_mutex_destroy(&w->lock);
    return error ? -1 : 0;
}

typedef struct {
    int fd;
    int writer_core;
    pthread_mutex_t lock;
    pthread_cond_t has_work;
    pthread_cond_t idle;
    pthread_t thread;
    int busy;
    int closed;
    int error;
    uint8_t frame_header[GPR_VIDEO_FRAME_HEADER_SIZE];
    struct iovec iov[32];
    int iovcnt;
} SCATTER_PINGPONG_WRITER;

static int bench_env_int(const char *name, int fallback) {
    const char *env = getenv(name);
    if (!env || !*env) return fallback;
    char *end = NULL;
    long value = strtol(env, &end, 10);
    if (end == env) return fallback;
    return (int)value;
}

static void bench_pin_writer_thread(int core) {
#if defined(__linux__)
    if (core < 0) return;
    int n = (int)sysconf(_SC_NPROCESSORS_ONLN);
    if (n <= 0) n = 4;
    cpu_set_t mask;
    CPU_ZERO(&mask);
    CPU_SET(core % n, &mask);
    (void)pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask);
#else
    (void)core;
#endif
}

static void scatter_pingpong_set_error(SCATTER_PINGPONG_WRITER *w) {
    pthread_mutex_lock(&w->lock);
    w->error = 1;
    pthread_cond_broadcast(&w->has_work);
    pthread_cond_broadcast(&w->idle);
    pthread_mutex_unlock(&w->lock);
}

static void *scatter_pingpong_thread(void *arg) {
    SCATTER_PINGPONG_WRITER *w = (SCATTER_PINGPONG_WRITER *)arg;
    bench_pin_writer_thread(w->writer_core);
    for (;;) {
        struct iovec iov[32];
        int iovcnt = 0;
        pthread_mutex_lock(&w->lock);
        while (!w->busy && !w->closed && !w->error) {
            pthread_cond_wait(&w->has_work, &w->lock);
        }
        if (!w->busy && (w->closed || w->error)) {
            pthread_mutex_unlock(&w->lock);
            break;
        }
        iovcnt = w->iovcnt;
        if (iovcnt > 0 && iovcnt <= (int)(sizeof(iov) / sizeof(iov[0]))) {
            memcpy(iov, w->iov, (size_t)iovcnt * sizeof(iov[0]));
        } else {
            w->error = 1;
        }
        pthread_mutex_unlock(&w->lock);

        if (iovcnt <= 0 || iovcnt > (int)(sizeof(iov) / sizeof(iov[0])) ||
            writev_all_many(w->fd, iov, iovcnt) != 0) {
            scatter_pingpong_set_error(w);
        }

        pthread_mutex_lock(&w->lock);
        w->busy = 0;
        pthread_cond_broadcast(&w->idle);
        pthread_mutex_unlock(&w->lock);
    }
    return NULL;
}

static int scatter_pingpong_start(SCATTER_PINGPONG_WRITER *w, int fd, int writer_core) {
    memset(w, 0, sizeof(*w));
    w->fd = fd;
    w->writer_core = writer_core;
    if (pthread_mutex_init(&w->lock, NULL) != 0) return -1;
    if (pthread_cond_init(&w->has_work, NULL) != 0) return -1;
    if (pthread_cond_init(&w->idle, NULL) != 0) return -1;
    if (pthread_create(&w->thread, NULL, scatter_pingpong_thread, w) != 0) return -1;
    return 0;
}

static int scatter_pingpong_submit(SCATTER_PINGPONG_WRITER *w,
                                   const struct iovec *iov,
                                   int iovcnt) {
    if (!iov || iovcnt <= 0 || iovcnt > (int)(sizeof(w->iov) / sizeof(w->iov[0]))) {
        return -1;
    }
    pthread_mutex_lock(&w->lock);
    while (w->busy && !w->error) {
        pthread_cond_wait(&w->idle, &w->lock);
    }
    if (w->error) {
        pthread_mutex_unlock(&w->lock);
        return -1;
    }
    memcpy(w->iov, iov, (size_t)iovcnt * sizeof(iov[0]));
    if (w->iov[0].iov_len == sizeof(w->frame_header)) {
        memcpy(w->frame_header, w->iov[0].iov_base, sizeof(w->frame_header));
        w->iov[0].iov_base = w->frame_header;
    }
    w->iovcnt = iovcnt;
    w->busy = 1;
    pthread_cond_signal(&w->has_work);
    pthread_mutex_unlock(&w->lock);
    return 0;
}

static int scatter_pingpong_stop(SCATTER_PINGPONG_WRITER *w) {
    pthread_mutex_lock(&w->lock);
    while (w->busy && !w->error) {
        pthread_cond_wait(&w->idle, &w->lock);
    }
    w->closed = 1;
    pthread_cond_broadcast(&w->has_work);
    pthread_mutex_unlock(&w->lock);
    pthread_join(w->thread, NULL);
    int error = w->error;
    pthread_cond_destroy(&w->idle);
    pthread_cond_destroy(&w->has_work);
    pthread_mutex_destroy(&w->lock);
    return error ? -1 : 0;
}
#endif

int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s raw w h n\n", argv[0]); return 1; }
    const char *path = argv[1];
    int w = atoi(argv[2]), h = atoi(argv[3]), n = atoi(argv[4]);
    size_t sz = (size_t)w * h * 2;
    RAW_CORPUS corpus;
    if (raw_corpus_load(path, sz, &corpus) != 0 || corpus.count <= 0) {
        fprintf(stderr, "read fail: %s\n", path);
        raw_corpus_free(&corpus);
        return 1;
    }
    fprintf(stderr, "# raw_corpus path=%s frames=%d frame_bytes=%zu\n", path, corpus.count, sz);

    /* Pre-fault the raw input so the first read isn't paying for it. */
    volatile uint32_t sink = 0;
    for (int fidx = 0; fidx < corpus.count; fidx++)
        for (size_t i = 0; i < sz; i += 4096) sink += corpus.frames[fidx][i];
    (void)sink;

    int quality = 3;
    {
        const char *q_env = getenv("FUSED_QUALITY");
        if (q_env && *q_env) {
            char *end = NULL;
            long q = strtol(q_env, &end, 10);
            if (end != q_env && q >= 0 && q <= 11) {
                quality = (int)q;
            } else {
                fprintf(stderr, "invalid FUSED_QUALITY=%s (expected 0..11)\n", q_env);
                return 1;
            }
        }
    }
    int bench_pixel_format = 4;
    double gvid_fps = 24.0;
    {
        const char *pf_env = getenv("GPR_BENCH_PIXEL_FORMAT");
        if (pf_env && *pf_env) {
            char *end = NULL;
            long pf = strtol(pf_env, &end, 10);
            if (end != pf_env && pf >= 0 && pf <= 5) {
                bench_pixel_format = (int)pf;
            } else {
                fprintf(stderr, "invalid GPR_BENCH_PIXEL_FORMAT=%s (expected 0..5)\n", pf_env);
                return 1;
            }
        }
    }
    {
        const char *fps_env = getenv("GPR_BENCH_GVID_FPS");
        if (fps_env && *fps_env) {
            char *end = NULL;
            double fps = strtod(fps_env, &end);
            if (end != fps_env && fps > 0.0) {
                gvid_fps = fps;
            } else {
                fprintf(stderr, "invalid GPR_BENCH_GVID_FPS=%s (expected positive fps)\n", fps_env);
                return 1;
            }
        }
    }

    FUSED_ENCODER *enc = gpr_encode_fused_create(w, h, bench_pixel_format, quality);
    if (!enc) { fprintf(stderr, "create fail\n"); return 1; }

    const char *scatter_env = getenv("GPR_BENCH_GVID_SCATTER");
    int gvid_scatter = (scatter_env && *scatter_env == '1') ? 1 : 0;
    const char *coalesce_prefix_env = getenv("GPR_BENCH_GVID_COALESCE_PREFIX");
    int gvid_coalesce_prefix = (coalesce_prefix_env && *coalesce_prefix_env == '1') ? 1 : 0;
    const char *pingpong_env = getenv("GPR_BENCH_GVID_PINGPONG");
    int gvid_pingpong = (pingpong_env && *pingpong_env == '1') ? 1 : 0;
    FUSED_ENCODER *enc_pingpong = NULL;

    /* Optional BayesShrink wavelet-domain denoise — set GPR_BENCH_DENOISE=<strength>
       (typically 0.5–1.0). Requires FUSED_INLINE_TOKENIZE=0 (split mode) — the
       encoder rejects the call otherwise. Set GPR_BENCH_NOISE_SCALE / OFFSET
       to pass calibrated NoiseProfile (default 0 = use MAD estimate). */
    {
        const char *e = getenv("GPR_BENCH_DENOISE");
        if (e && *e) {
            double strength = atof(e);
            const char *ns_env = getenv("GPR_BENCH_NOISE_SCALE");
            const char *no_env = getenv("GPR_BENCH_NOISE_OFFSET");
            double ns = ns_env ? atof(ns_env) : 0.0;
            double no = no_env ? atof(no_env) : 0.0;
            fprintf(stderr, "# denoise: strength=%.2f scale=%g offset=%g\n",
                    strength, ns, no);
            gpr_encode_fused_set_denoise(enc, ns, no, strength);
        }
    }
    if (gvid_pingpong) {
        if (!gvid_scatter) {
            fprintf(stderr, "GPR_BENCH_GVID_PINGPONG requires GPR_BENCH_GVID_SCATTER=1\n");
            gpr_encode_fused_destroy(enc);
            return 1;
        }
        enc_pingpong = gpr_encode_fused_create(w, h, bench_pixel_format, quality);
        if (!enc_pingpong) {
            fprintf(stderr, "create pingpong encoder fail\n");
            gpr_encode_fused_destroy(enc);
            return 1;
        }
        const char *e = getenv("GPR_BENCH_DENOISE");
        if (e && *e) {
            double strength = atof(e);
            const char *ns_env = getenv("GPR_BENCH_NOISE_SCALE");
            const char *no_env = getenv("GPR_BENCH_NOISE_OFFSET");
            double ns = ns_env ? atof(ns_env) : 0.0;
            double no = no_env ? atof(no_env) : 0.0;
            gpr_encode_fused_set_denoise(enc_pingpong, ns, no, strength);
        }
    }

    /* 2 warm-up frames not counted */
    for (int i = 0; i < 2; i++) {
        const unsigned char *raw = corpus.frames[i % corpus.count];
        unsigned char *out = NULL; size_t out_sz = 0;
        if (gvid_scatter) {
            const unsigned char **parts = NULL;
            const size_t *part_sizes = NULL;
            int part_count = 0;
            gpr_encode_fused_frame_scatter((enc_pingpong && (i & 1)) ? enc_pingpong : enc,
                                           raw, sz,
                                           &parts, &part_sizes, &part_count,
                                           &out_sz);
        } else {
            gpr_encode_fused_frame(enc, raw, sz, &out, &out_sz);
        }
    }

    /* Optional output dump for byte-identity testing: write the first frame's
       encoded bytes to GPR_BENCH_DUMP path, then continue benchmarking.

       Optional sustained-write benchmarking: set GPR_BENCH_WRITE_ALL=<dir>
       to write every encoded frame as frame_NNNN.gpr inside <dir>. Frame
       times then include the fwrite, which is the right measurement for
       "can this hardware actually capture at 24 fps to this storage?"
       Use a path that bypasses tmpfs (e.g. /mnt/ssd, not /tmp) and run
       n ≥ 10 × fps_target so the kernel page cache is exhausted (see
       feedback_honest_capture_bench: short runs are misleading).

       Optional direct-container benchmarking: set GPR_BENCH_GVID=<path> to
       write a strict .gvid stream sequentially as frames are encoded. This is
       closer to the camera/container path than GPR_BENCH_WRITE_ALL because it
       avoids per-frame open/close and the post-run pack step.

       If multiple output env vars are set, GPR_BENCH_DUMP still gets the first
       frame for byte-identity tests, GPR_BENCH_WRITE_ALL writes ALL frames to
       its own directory, and GPR_BENCH_GVID appends ALL frames to one stream. */
    const char *dump_path = getenv("GPR_BENCH_DUMP");
    const char *write_all_dir = getenv("GPR_BENCH_WRITE_ALL");
    const char *gvid_path = getenv("GPR_BENCH_GVID");
    const char *async_gvid_env = getenv("GPR_BENCH_ASYNC_GVID");
    int async_gvid = (async_gvid_env && *async_gvid_env == '1') ? 1 : 0;
    const char *writev_env = getenv("GPR_BENCH_GVID_WRITEV");
    int gvid_writev = (writev_env && *writev_env == '1') ? 1 : 0;
    if (gvid_scatter && !async_gvid) gvid_writev = 1;
    const char *sync_range_env = getenv("GPR_BENCH_GVID_SYNC_RANGE");
    int gvid_sync_range = (sync_range_env && *sync_range_env == '1') ? 1 : 0;
    int async_queue_cap = 4;
    {
        const char *queue_env = getenv("GPR_BENCH_ASYNC_QUEUE");
        if (queue_env && *queue_env) {
            int v = atoi(queue_env);
            if (v >= 1 && v <= 16) async_queue_cap = v;
        }
    }
    if (write_all_dir && *write_all_dir) {
        /* mkdir -p best effort; ignore errors (caller is responsible) */
        char mkdir_cmd[1024];
        snprintf(mkdir_cmd, sizeof(mkdir_cmd), "mkdir -p '%s'", write_all_dir);
        (void)!system(mkdir_cmd);
        fprintf(stderr, "# GPR_BENCH_WRITE_ALL=%s — frame times will include fwrite\n",
                write_all_dir);
    }
    FILE *gvid_fp = NULL;
#if !defined(_WIN32)
    int gvid_fd = -1;
    off_t gvid_offset = 0;
#endif
#if !defined(_WIN32)
    ASYNC_GVID_WRITER async_writer;
    int async_writer_started = 0;
    SCATTER_PINGPONG_WRITER pingpong_writer;
    int pingpong_writer_started = 0;
#endif
    if (gvid_path && *gvid_path) {
        if (async_gvid && gvid_writev) {
            fprintf(stderr, "GPR_BENCH_ASYNC_GVID and GPR_BENCH_GVID_WRITEV are mutually exclusive\n");
            return 1;
        }
        if (gvid_pingpong && !gvid_scatter) {
            fprintf(stderr, "GPR_BENCH_GVID_PINGPONG requires GPR_BENCH_GVID_SCATTER=1\n");
            return 1;
        }
        if (gvid_coalesce_prefix && !gvid_scatter) {
            fprintf(stderr, "GPR_BENCH_GVID_COALESCE_PREFIX requires GPR_BENCH_GVID_SCATTER=1\n");
            return 1;
        }
#if !defined(_WIN32)
        if (gvid_writev) {
            gvid_fd = open(gvid_path, O_CREAT | O_TRUNC | O_WRONLY, 0666);
            if (gvid_fd < 0) {
                fprintf(stderr, "open GPR_BENCH_GVID=%s failed\n", gvid_path);
                return 1;
            }
        } else
#endif
        {
            gvid_fp = fopen(gvid_path, "wb");
        }
        if (!gvid_fp
#if !defined(_WIN32)
            && gvid_fd < 0
#endif
        ) {
            fprintf(stderr, "open GPR_BENCH_GVID=%s failed\n", gvid_path);
            return 1;
        }
        uint8_t clip_header[GPR_VIDEO_CLIP_HEADER_SIZE];
        int n_header = gpr_video_write_clip_header(
            clip_header, sizeof(clip_header),
            w, h, bench_pixel_format, quality, gvid_fps,
            /*target_MBps=*/0.0, /*denoise_enabled=*/0,
            (uint32_t)n);
        int header_ok = (n_header == GPR_VIDEO_CLIP_HEADER_SIZE);
#if !defined(_WIN32)
        if (header_ok && gvid_fd >= 0) {
            header_ok = (write_all_fd(gvid_fd, clip_header, sizeof(clip_header)) == 0);
        } else
#endif
        if (header_ok) {
            header_ok = (fwrite(clip_header, 1, sizeof(clip_header), gvid_fp) == sizeof(clip_header));
        }
        if (!header_ok) {
            fprintf(stderr, "write GPR_BENCH_GVID clip header failed\n");
#if !defined(_WIN32)
            if (gvid_fd >= 0) close(gvid_fd);
#endif
            if (gvid_fp) fclose(gvid_fp);
            return 1;
        }
#if !defined(_WIN32)
        gvid_offset = (off_t)sizeof(clip_header);
#endif
        fprintf(stderr, "# GPR_BENCH_GVID=%s - frame times will include sequential .gvid %s\n",
                gvid_path, (gvid_scatter && gvid_pingpong) ? "scatter-pingpong-writev" : (gvid_scatter ? "scatter-writev" : (gvid_writev ? "writev" : "fwrite")));
        if (gvid_sync_range) {
            fprintf(stderr, "# GPR_BENCH_GVID_SYNC_RANGE=1 - start async kernel writeback after each direct .gvid frame\n");
        }
        if (gvid_pingpong) {
#if defined(_WIN32)
            fprintf(stderr, "GPR_BENCH_GVID_PINGPONG is not supported on this platform\n");
            if (gvid_fp) fclose(gvid_fp);
            return 1;
#else
            int writer_core = bench_env_int("GPR_BENCH_GVID_WRITER_CORE", -1);
            if (gvid_fd < 0 || scatter_pingpong_start(&pingpong_writer, gvid_fd, writer_core) != 0) {
                fprintf(stderr, "start scatter pingpong .gvid writer failed\n");
                if (gvid_fd >= 0) close(gvid_fd);
                if (gvid_fp) fclose(gvid_fp);
                return 1;
            }
            pingpong_writer_started = 1;
            fprintf(stderr, "# GPR_BENCH_GVID_PINGPONG=1 - frame times include encode plus writer backpressure, final drain reported separately\n");
            if (writer_core >= 0) {
                fprintf(stderr, "# GPR_BENCH_GVID_WRITER_CORE=%d - pin pingpong writer thread\n", writer_core);
            }
#endif
        }
        if (async_gvid) {
#if defined(_WIN32)
            fprintf(stderr, "GPR_BENCH_ASYNC_GVID is not supported on this platform\n");
            fclose(gvid_fp);
            return 1;
#else
            if (async_gvid_start(&async_writer, gvid_fp, async_queue_cap) != 0) {
                fprintf(stderr, "start async .gvid writer failed\n");
                fclose(gvid_fp);
                return 1;
            }
            async_writer_started = 1;
            fprintf(stderr, "# GPR_BENCH_ASYNC_GVID=1 queue=%d - frame times include copy/enqueue/backpressure%s\n",
                    async_queue_cap,
                    gvid_scatter ? " from scatter parts" : "");
#endif
        }
    }
    double *times = malloc((size_t)n * sizeof(double));
    double *encode_times = malloc((size_t)n * sizeof(double));
    double *write_times = malloc((size_t)n * sizeof(double));
    double *payload_kib = malloc((size_t)n * sizeof(double));
    if (!times || !encode_times || !write_times || !payload_kib) {
        fprintf(stderr, "timing allocation fail\n");
        free(times); free(encode_times); free(write_times); free(payload_kib);
        if (gvid_fp) fclose(gvid_fp);
        gpr_encode_fused_destroy(enc);
        return 1;
    }
    for (int i = 0; i < n; i++) {
        const unsigned char *raw = corpus.frames[i % corpus.count];
        double t0 = now_ms();
        unsigned char *out = NULL; size_t out_sz = 0;
        const unsigned char **parts = NULL;
        const size_t *part_sizes = NULL;
        int part_count = 0;
        int encode_rc = 0;
        if (gvid_scatter) {
            FUSED_ENCODER *frame_enc = (enc_pingpong && (i & 1)) ? enc_pingpong : enc;
            encode_rc = gpr_encode_fused_frame_scatter(frame_enc, raw, sz,
                                                       &parts, &part_sizes, &part_count,
                                                       &out_sz);
        } else {
            encode_rc = gpr_encode_fused_frame(enc, raw, sz, &out, &out_sz);
        }
        if (encode_rc != 0 || out_sz == 0 || (gvid_scatter && part_count <= 0)) {
            fprintf(stderr,
                    "encode failed frame=%d rc=%d out_sz=%zu scatter=%d parts=%d\n",
                    i, encode_rc, out_sz, gvid_scatter, part_count);
            if (gvid_fp) fclose(gvid_fp);
#if !defined(_WIN32)
            if (gvid_fd >= 0) close(gvid_fd);
#endif
            gpr_encode_fused_destroy(enc);
            if (enc_pingpong) gpr_encode_fused_destroy(enc_pingpong);
            raw_corpus_free(&corpus);
            free(times);
            free(encode_times);
            free(write_times);
            free(payload_kib);
            return 1;
        }
        double t_encode = now_ms();
        if (
#if !defined(_WIN32)
            (gvid_fd >= 0 || gvid_fp) &&
#else
            gvid_fp &&
#endif
            (gvid_scatter || out) && out_sz > 0) {
#if !defined(_WIN32)
            if (async_writer_started) {
                int async_rc = 0;
                if (gvid_scatter) {
                    if (!parts || !part_sizes || part_count <= 0 || part_count > 30) {
                        fprintf(stderr, "scatter async GPR_BENCH_GVID frame %d invalid chunks\n", i);
                        return 1;
                    }
                    unsigned char *payload = (unsigned char *)malloc(out_sz);
                    if (!payload) {
                        fprintf(stderr, "scatter async GPR_BENCH_GVID frame %d malloc failed\n", i);
                        return 1;
                    }
                    size_t pos = 0;
                    for (int p = 0; p < part_count; p++) {
                        if (part_sizes[p] > out_sz - pos) {
                            free(payload);
                            fprintf(stderr, "scatter async GPR_BENCH_GVID frame %d chunk overflow\n", i);
                            return 1;
                        }
                        memcpy(payload + pos, parts[p], part_sizes[p]);
                        pos += part_sizes[p];
                    }
                    if (pos != out_sz) {
                        free(payload);
                        fprintf(stderr, "scatter async GPR_BENCH_GVID frame %d size mismatch\n", i);
                        return 1;
                    }
                    async_rc = async_gvid_submit_take(&async_writer, payload, out_sz, (uint64_t)i);
                } else {
                    async_rc = async_gvid_submit(&async_writer, out, out_sz, (uint64_t)i);
                }
                if (async_rc != 0) {
                    fprintf(stderr, "async write GPR_BENCH_GVID frame %d failed\n", i);
                    return 1;
                }
            } else if (gvid_scatter && gvid_fd >= 0) {
                off_t frame_start = gvid_offset;
                uint8_t frame_header[GPR_VIDEO_FRAME_HEADER_SIZE];
                int n_frame = gpr_video_write_frame_header(
                    frame_header, sizeof(frame_header), out_sz, (uint64_t)i);
                if (n_frame != GPR_VIDEO_FRAME_HEADER_SIZE ||
                    !parts || !part_sizes || part_count <= 0 || part_count > 30) {
                    fprintf(stderr, "scatter GPR_BENCH_GVID frame %d invalid chunks\n", i);
                    close(gvid_fd);
                    return 1;
                }
                struct iovec iov[32];
                uint8_t coalesced_prefix[512];
                int iovcnt = 0;
                int first_part = 0;
                if (gvid_coalesce_prefix) {
                    size_t prefix_len = sizeof(frame_header) + part_sizes[0];
                    if (prefix_len > sizeof(coalesced_prefix)) {
                        fprintf(stderr, "scatter GPR_BENCH_GVID frame %d prefix too large for coalescing\n", i);
                        close(gvid_fd);
                        return 1;
                    }
                    memcpy(coalesced_prefix, frame_header, sizeof(frame_header));
                    memcpy(coalesced_prefix + sizeof(frame_header), parts[0], part_sizes[0]);
                    iov[iovcnt].iov_base = coalesced_prefix;
                    iov[iovcnt].iov_len = prefix_len;
                    iovcnt++;
                    first_part = 1;
                } else {
                    iov[iovcnt].iov_base = frame_header;
                    iov[iovcnt].iov_len = sizeof(frame_header);
                    iovcnt++;
                }
                for (int p = first_part; p < part_count; p++) {
                    iov[iovcnt].iov_base = (void *)parts[p];
                    iov[iovcnt].iov_len = part_sizes[p];
                    iovcnt++;
                }
                int write_rc = 0;
                if (pingpong_writer_started) {
                    write_rc = scatter_pingpong_submit(&pingpong_writer, iov, iovcnt);
                } else {
                    write_rc = writev_all_many(gvid_fd, iov, iovcnt);
                }
                if (write_rc != 0) {
                    fprintf(stderr, "scatter writev GPR_BENCH_GVID frame %d failed\n", i);
                    close(gvid_fd);
                    return 1;
                }
                gvid_offset += (off_t)sizeof(frame_header) + (off_t)out_sz;
                if (!pingpong_writer_started) {
                    maybe_start_writeback(gvid_fd, frame_start, gvid_offset - frame_start, gvid_sync_range);
                }
            } else if (gvid_fd >= 0) {
                off_t frame_start = gvid_offset;
                uint8_t frame_header[GPR_VIDEO_FRAME_HEADER_SIZE];
                int n_frame = gpr_video_write_frame_header(
                    frame_header, sizeof(frame_header), out_sz, (uint64_t)i);
                if (n_frame != GPR_VIDEO_FRAME_HEADER_SIZE ||
                    writev_all2(gvid_fd, frame_header, sizeof(frame_header), out, out_sz) != 0) {
                    fprintf(stderr, "writev GPR_BENCH_GVID frame %d failed\n", i);
                    close(gvid_fd);
                    return 1;
                }
                gvid_offset += (off_t)sizeof(frame_header) + (off_t)out_sz;
                maybe_start_writeback(gvid_fd, frame_start, gvid_offset - frame_start, gvid_sync_range);
            } else
#endif
            {
            uint8_t frame_header[GPR_VIDEO_FRAME_HEADER_SIZE];
            int n_frame = gpr_video_write_frame_header(
                frame_header, sizeof(frame_header), out_sz, (uint64_t)i);
            if (n_frame != GPR_VIDEO_FRAME_HEADER_SIZE ||
                fwrite(frame_header, 1, sizeof(frame_header), gvid_fp) != sizeof(frame_header) ||
                fwrite(out, 1, out_sz, gvid_fp) != out_sz) {
                fprintf(stderr, "write GPR_BENCH_GVID frame %d failed\n", i);
                fclose(gvid_fp);
                return 1;
            }
            }
        }
        if (write_all_dir && *write_all_dir && out && out_sz > 0) {
            char path[1280];
            snprintf(path, sizeof(path), "%s/frame_%04d.gpr", write_all_dir, i);
            FILE *wf = fopen(path, "wb");
            if (wf) {
                if (gvid_scatter && parts && part_sizes) {
                    for (int p = 0; p < part_count; p++) fwrite(parts[p], 1, part_sizes[p], wf);
                } else {
                    fwrite(out, 1, out_sz, wf);
                }
                fclose(wf);
            }
        }
        double t1 = now_ms();
        times[i] = t1 - t0;
        encode_times[i] = t_encode - t0;
        write_times[i] = t1 - t_encode;
        payload_kib[i] = (double)out_sz / 1024.0;
        if (i == 0 && dump_path && out_sz > 0) {
            FILE *df = fopen(dump_path, "wb");
            if (df) {
                if (gvid_scatter && parts && part_sizes) {
                    for (int p = 0; p < part_count; p++) fwrite(parts[p], 1, part_sizes[p], df);
                } else {
                    fwrite(out, 1, out_sz, df);
                }
                fclose(df);
            }
            fprintf(stderr, "# dumped frame 0 (%zu bytes) to %s\n", out_sz, dump_path);
        }
    }
    printf("# frame_ms\n");
    for (int i = 0; i < n; i++) printf("%.2f\n", times[i]);

    /* Sort to find quartiles */
    for (int i = 0; i < n; i++)
        for (int j = i+1; j < n; j++)
            if (times[j] < times[i]) { double t = times[i]; times[i] = times[j]; times[j] = t; }
    double sum = 0, sum_sq = 0;
    for (int i = 0; i < n; i++) { sum += times[i]; sum_sq += times[i]*times[i]; }
    double mean = sum / n;
    double var = sum_sq / n - mean * mean;
    fprintf(stderr,
        "# n=%d  mean=%.2f  stddev=%.2f  min=%.2f  p25=%.2f  median=%.2f  p75=%.2f  max=%.2f\n",
        n, mean, var > 0 ? __builtin_sqrt(var) : 0,
        times[0], times[n/4], times[n/2], times[3*n/4], times[n-1]);
    fprintf(stderr,
        "# fps_mean=%.2f  fps_median=%.2f  fps_p25(fast)=%.2f\n",
        1000.0/mean, 1000.0/times[n/2], 1000.0/times[n/4]);
    print_phase_summary("encode", encode_times, n);
    print_phase_summary("write", write_times, n);
    print_phase_summary("total", times, n);
    print_phase_summary("payload_kib", payload_kib, n);

    double async_drain_ms = 0.0;
#if !defined(_WIN32)
    if (pingpong_writer_started) {
        double td0 = now_ms();
        if (scatter_pingpong_stop(&pingpong_writer) != 0) {
            fprintf(stderr, "scatter pingpong .gvid writer failed\n");
            if (gvid_fd >= 0) close(gvid_fd);
            return 1;
        }
        async_drain_ms = now_ms() - td0;
        print_phase_summary("pingpong_drain", &async_drain_ms, 1);
    }
    if (async_writer_started) {
        double td0 = now_ms();
        if (async_gvid_stop(&async_writer) != 0) {
            fprintf(stderr, "async .gvid writer failed\n");
            fclose(gvid_fp);
            return 1;
        }
        async_drain_ms = now_ms() - td0;
        print_phase_summary("async_drain", &async_drain_ms, 1);
    }
#endif
    if (gvid_fp) {
        fflush(gvid_fp);
        fclose(gvid_fp);
    }
#if !defined(_WIN32)
    if (gvid_fd >= 0) {
        close(gvid_fd);
    }
#endif
    free(times);
    free(encode_times);
    free(write_times);
    free(payload_kib);
    raw_corpus_free(&corpus);
    if (enc_pingpong) gpr_encode_fused_destroy(enc_pingpong);
    gpr_encode_fused_destroy(enc);
    return 0;
}
