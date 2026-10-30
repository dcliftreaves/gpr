/* Private experiment: frame-scoped bounded stage-0 entropy handoff. */
#define HANDOFF_SLOTS 4
#define HANDOFF_ROWS 32

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    PIXEL *storage;
    size_t pitch;
    unsigned width, height, published, pending_jobs;
    unsigned read_sequence[3];
    unsigned state[3][HANDOFF_SLOTS]; /* 0 free, 1 producer-owned, 2 ready, 3 busy */
    unsigned rows[HANDOFF_SLOTS];
    unsigned busy[3], cursor, done;
    unsigned completed_by[4];
    BITSTREAM *stream[3];
    uint32_t *zero_pending[3];
    ENCODER_CODESET *codeset;
    CODEC_ERROR error;
} ENTROPY_HANDOFF;

static __thread ENTROPY_HANDOFF *active_entropy_handoff;

static PIXEL *HandoffBuffer(ENTROPY_HANDOFF *h, unsigned band, unsigned slot)
{
    return (PIXEL *)((uint8_t *)h->storage +
        ((size_t)band * HANDOFF_SLOTS + slot) * HANDOFF_ROWS * h->pitch);
}

/* Each band has at most one consumer; its row order and zero state span chunks. */
static int HandoffHelp(ENTROPY_HANDOFF *h, unsigned worker, int wait)
{
    unsigned band = 0, slot = 0, rows = 0;
    pthread_mutex_lock(&h->mutex);
    for (;;) {
        int found = 0;
        for (unsigned i=0; i<3; ++i) {
            band = (h->cursor+i)%3;
            slot = h->read_sequence[band]%HANDOFF_SLOTS;
            if (!h->busy[band] && h->state[band][slot] == 2) {
                h->busy[band] = 1;
                h->state[band][slot] = 3;
                rows = h->rows[slot];
                h->cursor = (band+1)%3;
                found = 1;
                break;
            }
        }
        if (found) break;
        if (!wait || (h->done && !h->pending_jobs)) {
            pthread_mutex_unlock(&h->mutex);
            return 0;
        }
        pthread_cond_wait(&h->changed, &h->mutex);
    }
    pthread_mutex_unlock(&h->mutex);
    CODEC_ERROR error = EncodeHighpassIncremental(h->stream[band], h->codeset,
        HandoffBuffer(h,band,slot), h->width, rows, h->pitch,
        h->zero_pending[band], false);
    pthread_mutex_lock(&h->mutex);
    if (error != CODEC_ERROR_OKAY && h->error == CODEC_ERROR_OKAY) h->error = error;
    h->busy[band] = 0;
    h->state[band][slot] = 0;
    h->read_sequence[band]++;
    h->pending_jobs--;
    h->completed_by[worker]++;
    pthread_cond_broadcast(&h->changed);
    pthread_mutex_unlock(&h->mutex);
    return 1;
}

static unsigned HandoffReserve(ENTROPY_HANDOFF *h)
{
    unsigned slot = h->published%HANDOFF_SLOTS;
    for (;;) {
        pthread_mutex_lock(&h->mutex);
        if (!h->state[0][slot] && !h->state[1][slot] && !h->state[2][slot]) {
            for (unsigned band=0; band<3; ++band) h->state[band][slot]=1;
            pthread_mutex_unlock(&h->mutex);
            return slot;
        }
        pthread_mutex_unlock(&h->mutex);
        if (!HandoffHelp(h,0,0)) {
            pthread_mutex_lock(&h->mutex);
            /* Recheck after locking: a helper may have completed before this lock. */
            if (h->state[0][slot] || h->state[1][slot] || h->state[2][slot])
                pthread_cond_wait(&h->changed,&h->mutex);
            pthread_mutex_unlock(&h->mutex);
        }
    }
}

static void HandoffPublish(ENTROPY_HANDOFF *h, unsigned rows)
{
    pthread_mutex_lock(&h->mutex);
    unsigned slot = h->published%HANDOFF_SLOTS;
    h->rows[slot] = rows;
    for (unsigned band=0; band<3; ++band) {
        assert(h->state[band][slot] == 1);
        h->state[band][slot] = 2;
    }
    h->published++;
    h->pending_jobs += 3;
    pthread_cond_broadcast(&h->changed);
    pthread_mutex_unlock(&h->mutex);
}

static void HandoffFinish(ENTROPY_HANDOFF *h)
{
    pthread_mutex_lock(&h->mutex);
    h->done = 1;
    pthread_cond_broadcast(&h->changed);
    pthread_mutex_unlock(&h->mutex);
    while (HandoffHelp(h,0,1)) {}
}

static int HandoffInit(ENTROPY_HANDOFF *h, ENCODER *encoder, unsigned width, unsigned height)
{
    memset(h,0,sizeof(*h));
    h->width = width;
    h->height = height;
    h->pitch = ((size_t)width*sizeof(PIXEL)+63)&~(size_t)63;
    size_t bytes = h->pitch*HANDOFF_SLOTS*HANDOFF_ROWS*3;
    if (!width || !height || bytes > 1024*1024) return 0;
    h->storage = gpr_aligned_alloc(encoder->allocator,bytes);
    if (!h->storage) return 0;
    if (pthread_mutex_init(&h->mutex,NULL)) {
        gpr_aligned_free(encoder->allocator,h->storage);
        h->storage=NULL;
        return 0;
    }
    if (pthread_cond_init(&h->changed,NULL)) {
        pthread_mutex_destroy(&h->mutex);
        gpr_aligned_free(encoder->allocator,h->storage);
        h->storage=NULL;
        return 0;
    }
    return 1;
}

static void HandoffDestroy(ENTROPY_HANDOFF *h, ENCODER *encoder)
{
    pthread_cond_destroy(&h->changed);
    pthread_mutex_destroy(&h->mutex);
    gpr_aligned_free(encoder->allocator,h->storage);
}
