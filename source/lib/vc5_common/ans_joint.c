/*! @file ans_joint.c
 *  @brief Joint RLV ANS coder — single symbol per coefficient.
 */

#include "ans_joint.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#define RANS_BYTE_L (1u << 23)

/* Run class encoding: class → (min_run, extra_bits)
   Class 0: run=0 (0 bits)      Class 4: run=4-7 (2 bits)
   Class 1: run=1 (0 bits)      Class 5: run=8-15 (3 bits)
   Class 2: run=2 (0 bits)      Class 6: run=16-31 (4 bits)
   Class 3: run=3 (0 bits)      Class 7: run=32-287 (8 bits) */
/* Contiguous exponentially spaced run classes — no gaps */
static const int run_class_min[JANS_RUN_CLASSES] = {0, 1, 2, 3, 4,  8, 16, 32,  64,  128};
static const int run_class_bits[JANS_RUN_CLASSES] = {0, 0, 0, 0, 2,  3,  4,  5,   6,    7};

static int run_to_class(int run, int *residual) {
    for (int c = JANS_RUN_CLASSES - 1; c >= 0; c--) {
        if (run >= run_class_min[c]) {
            *residual = run - run_class_min[c];
            return c;
        }
    }
    *residual = run;
    return 0;
}

static int class_to_run(int cls, int residual) {
    return run_class_min[cls] + residual;
}

/* Mag class encoding: class → (min_mag, extra_bits)
   Class 0: mag=0 (sentinel)     Class 8: mag=8-15 (3 bits)
   Class 1: mag=1 (0 bits)       Class 9: mag=16-31 (4 bits)
   Class 2: mag=2 (0 bits)       Class 10: mag=32-63 (5 bits)
   Class 3: mag=3 (0 bits)       Class 11: mag=64-127 (6 bits)
   Class 4: mag=4 (0 bits)       Class 12: mag=128-255 (7 bits)
   Class 5: mag=5 (0 bits)       Class 13: mag=256-511 (8 bits)
   Class 6: mag=6 (0 bits)       Class 14: mag=512-1023 (9 bits)
   Class 7: mag=7 (0 bits)       Class 15: mag=1024+ (10 bits) */
static const int mag_class_min[JANS_MAG_CLASSES] = {0,1,2,3,4,5,6,7,8,16,32,64,128,256,512,1024};
static const int mag_class_bits[JANS_MAG_CLASSES] = {0,0,0,0,0,0,0,0,3,4,5,6,7,8,9,10};

static int mag_to_class(int mag, int *residual) {
    for (int c = JANS_MAG_CLASSES - 1; c >= 0; c--) {
        if (mag >= mag_class_min[c]) {
            *residual = mag - mag_class_min[c];
            return c;
        }
    }
    *residual = mag;
    return 0;
}

static int class_to_mag(int cls, int residual) {
    return mag_class_min[cls] + residual;
}

/* --- rANS core --- */

static inline void rans_enc_put(uint32_t *state, uint8_t **pptr,
                                uint32_t start, uint32_t freq) {
    uint32_t x = *state;
    uint32_t x_max = ((RANS_BYTE_L >> JANS_TABLE_BITS) << 8) * freq;
    while (x >= x_max) { *(*pptr)++ = (uint8_t)(x & 0xFF); x >>= 8; }
    *state = ((x / freq) << JANS_TABLE_BITS) + (x % freq) + start;
}

static inline int rans_dec_renorm(uint32_t *state, const uint8_t **pptr,
                                  const uint8_t *end) {
    while (*state < RANS_BYTE_L) {
        if (*pptr >= end) return -1;
        *state = (*state << 8) | **pptr;
        (*pptr)++;
    }
    return 0;
}

/* --- Bit buffer for residual bits --- */
typedef struct {
    uint8_t *buf;
    size_t   capacity;
    size_t   byte_pos;
    int      bit_pos;  /* bits written in current byte (0-7) */
} BITBUF;

static void bitbuf_init(BITBUF *bb, uint8_t *buf, size_t cap) {
    bb->buf = buf; bb->capacity = cap; bb->byte_pos = 0; bb->bit_pos = 0;
    if (buf) memset(buf, 0, cap);
}

static void bitbuf_write(BITBUF *bb, uint32_t value, int bits) {
    for (int i = 0; i < bits; i++) {
        if (bb->byte_pos < bb->capacity) {
            bb->buf[bb->byte_pos] |= ((value >> i) & 1) << bb->bit_pos;
            bb->bit_pos++;
            if (bb->bit_pos >= 8) { bb->bit_pos = 0; bb->byte_pos++; }
        }
    }
}

static size_t bitbuf_size(const BITBUF *bb) {
    return bb->byte_pos + (bb->bit_pos > 0 ? 1 : 0);
}

static uint32_t bitbuf_read(const uint8_t *buf, size_t buf_size,
                            size_t *byte_pos, int *bit_pos, int bits) {
    uint32_t value = 0;
    for (int i = 0; i < bits; i++) {
        if (*byte_pos < buf_size) {
            value |= ((buf[*byte_pos] >> *bit_pos) & 1) << i;
            (*bit_pos)++;
            if (*bit_pos >= 8) { *bit_pos = 0; (*byte_pos)++; }
        }
    }
    return value;
}

/* --- Normalize and build tables --- */

static void normalize_freq(uint16_t *freq, int n) {
    uint32_t total = 0;
    for (int i = 0; i < n; i++) total += freq[i];
    if (total == 0) { freq[0] = JANS_TABLE_SIZE; return; }
    uint32_t scaled_total = 0;
    uint16_t scaled[JANS_NUM_SYMBOLS + 1];
    for (int i = 0; i < n; i++) {
        if (freq[i] > 0) {
            uint32_t s = (uint32_t)freq[i] * JANS_TABLE_SIZE / total;
            if (s == 0) s = 1;
            scaled[i] = (uint16_t)s;
        } else scaled[i] = 0;
        scaled_total += scaled[i];
    }
    int32_t diff = (int32_t)JANS_TABLE_SIZE - (int32_t)scaled_total;
    int max_idx = 0;
    for (int i = 1; i < n; i++) if (scaled[i] > scaled[max_idx]) max_idx = i;
    scaled[max_idx] = (uint16_t)((int32_t)scaled[max_idx] + diff);
    memcpy(freq, scaled, n * sizeof(uint16_t));
}

static void build_tables(JANS_TABLE *t, int n) {
    t->cum_freq[0] = 0;
    for (int i = 1; i < n; i++) t->cum_freq[i] = t->cum_freq[i-1] + t->freq[i-1];
    int sym = 0;
    for (int i = 0; i < JANS_TABLE_SIZE; i++) {
        while (sym < n-1 && i >= t->cum_freq[sym] + t->freq[sym]) sym++;
        t->decode_sym[i] = (uint16_t)sym;
    }
}

/* --- Encode --- */

int jans_encode_band(uint8_t *out_buf, size_t out_capacity,
                     const int32_t *data, int width, int height, int pitch) {
    int pitch_elems = pitch / sizeof(int32_t);
    size_t pixels = (size_t)width * (size_t)height;
    if (pixels > (size_t)(INT32_MAX / 2)) return -1;

    /* Collect tokens + residual bits */
    size_t max_tokens = pixels + height + 16;
    uint16_t *tokens = (uint16_t *)malloc(max_tokens * sizeof(uint16_t));
    if (!tokens) return -1;

    /* Bit buffer for residuals (run_extra + mag_extra + sign) */
    size_t resid_cap = pixels * 2; /* generous upper bound */
    uint8_t *resid_buf = (uint8_t *)malloc(resid_cap);
    if (!resid_buf) { free(tokens); return -1; }

    BITBUF bb;
    bitbuf_init(&bb, resid_buf, resid_cap);

    JANS_TABLE table;
    memset(&table, 0, sizeof(table));
    int token_count = 0;

    for (int row = 0; row < height; row++) {
        const int32_t *rowptr = data + row * pitch_elems;
        int run = 0;
        for (int col = 0; col < width; col++) {
            int32_t val = rowptr[col];
            if (val == 0) { run++; continue; }

            int32_t mag = (val < 0) ? -val : val;

            /* Emit long runs as run-only tokens (mag_class=0) */
            while (run >= 256) {
                int rr; int rc = run_to_class(255, &rr);
                int sym = rc * JANS_MAG_CLASSES + 0;
                table.freq[sym]++;
                tokens[token_count++] = (uint16_t)sym;
                bitbuf_write(&bb, rr, run_class_bits[rc]);
                run -= 255;
            }

            int run_resid, mag_resid;
            int rc = run_to_class(run, &run_resid);
            int mc = mag_to_class(mag, &mag_resid);

            int sym = rc * JANS_MAG_CLASSES + mc;
            table.freq[sym]++;
            tokens[token_count++] = (uint16_t)sym;

            /* Write residual bits: run extra, mag extra, sign */
            bitbuf_write(&bb, run_resid, run_class_bits[rc]);
            bitbuf_write(&bb, mag_resid, mag_class_bits[mc]);
            if (mc > 0) /* sign bit for nonzero magnitude */
                bitbuf_write(&bb, (val < 0) ? 1 : 0, 1);

            run = 0;
        }
        /* Trailing zeros: run-only token */
        if (run > 0) {
            while (run > 0) {
                int actual = (run > 255) ? 255 : run;
                int rr; int rc = run_to_class(actual, &rr);
                int sym = rc * JANS_MAG_CLASSES + 0;
                table.freq[sym]++;
                tokens[token_count++] = (uint16_t)sym;
                bitbuf_write(&bb, rr, run_class_bits[rc]);
                run -= actual;
            }
        }
    }

    size_t resid_size = bitbuf_size(&bb);

    /* Normalize and build ANS table */
    normalize_freq(table.freq, JANS_NUM_SYMBOLS);
    build_tables(&table, JANS_NUM_SYMBOLS);
    table.initialized = 1;

    /* rANS encode tokens in reverse */
    size_t rans_cap = pixels * 2 + 4096;
    uint8_t *rans_buf = (uint8_t *)malloc(rans_cap);
    if (!rans_buf) { free(tokens); free(resid_buf); return -1; }

    uint8_t *rans_ptr = rans_buf;
    uint32_t state = RANS_BYTE_L;

    for (int i = token_count - 1; i >= 0; i--) {
        int sym = tokens[i];
        rans_enc_put(&state, &rans_ptr,
                     table.cum_freq[sym], table.freq[sym]);
    }
    *rans_ptr++ = (uint8_t)(state >> 0);
    *rans_ptr++ = (uint8_t)(state >> 8);
    *rans_ptr++ = (uint8_t)(state >> 16);
    *rans_ptr++ = (uint8_t)(state >> 24);

    size_t rans_size = rans_ptr - rans_buf;

    /* Reverse rANS buffer */
    for (size_t i = 0; i < rans_size / 2; i++) {
        uint8_t t = rans_buf[i]; rans_buf[i] = rans_buf[rans_size-1-i];
        rans_buf[rans_size-1-i] = t;
    }

    free(tokens);

    /* Serialize frequency table */
    uint8_t freq_buf[JANS_NUM_SYMBOLS * 2];
    for (int i = 0; i < JANS_NUM_SYMBOLS; i++) {
        freq_buf[i*2] = (uint8_t)(table.freq[i] >> 8);
        freq_buf[i*2+1] = (uint8_t)(table.freq[i]);
    }
    int freq_size = JANS_NUM_SYMBOLS * 2;

    /* Pack: [token_count:4][freq_size:4][rans_size:4][resid_size:4]
             [freq_data][rans_data][resid_data] */
    size_t total = 16 + freq_size + rans_size + resid_size;
    if (total > out_capacity) { free(rans_buf); free(resid_buf); return -1; }

    uint8_t *p = out_buf;
    *p++ = (token_count>>24)&0xFF; *p++ = (token_count>>16)&0xFF;
    *p++ = (token_count>>8)&0xFF;  *p++ = token_count&0xFF;
    *p++ = (freq_size>>24)&0xFF;   *p++ = (freq_size>>16)&0xFF;
    *p++ = (freq_size>>8)&0xFF;    *p++ = freq_size&0xFF;
    *p++ = (rans_size>>24)&0xFF;   *p++ = (rans_size>>16)&0xFF;
    *p++ = (rans_size>>8)&0xFF;    *p++ = rans_size&0xFF;
    *p++ = (resid_size>>24)&0xFF;  *p++ = (resid_size>>16)&0xFF;
    *p++ = (resid_size>>8)&0xFF;   *p++ = resid_size&0xFF;
    memcpy(p, freq_buf, freq_size); p += freq_size;
    memcpy(p, rans_buf, rans_size); p += rans_size;
    memcpy(p, resid_buf, resid_size);

    free(rans_buf);
    free(resid_buf);
    return (int)total;
}

/* --- Decode --- */

int jans_decode_band(const uint8_t *in_buf, size_t in_size,
                     int32_t *data, int width, int height, int pitch) {
    if (in_size < 16) return -1;
    int pitch_elems = pitch / sizeof(int32_t);

    const uint8_t *p = in_buf;
    int token_count = (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]; p += 4;
    int freq_size   = (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]; p += 4;
    int rans_size   = (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]; p += 4;
    int resid_size  = (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]; p += 4;

    if (token_count < 0 || freq_size < 0 || rans_size < 4 || resid_size < 0) return -1;
    if ((size_t)16 + freq_size + rans_size + resid_size > in_size) return -1;

    /* Deserialize frequency table */
    const uint8_t *freq_data = p; p += freq_size;
    JANS_TABLE table;
    memset(&table, 0, sizeof(table));
    for (int i = 0; i < JANS_NUM_SYMBOLS && i*2+1 < freq_size; i++)
        table.freq[i] = ((uint16_t)freq_data[i*2] << 8) | freq_data[i*2+1];
    normalize_freq(table.freq, JANS_NUM_SYMBOLS);
    build_tables(&table, JANS_NUM_SYMBOLS);

    const uint8_t *rans_data = p; p += rans_size;
    const uint8_t *rans_end = rans_data + rans_size;
    const uint8_t *resid_data = p;

    /* Init rANS */
    uint32_t state = ((uint32_t)rans_data[0]<<24) | ((uint32_t)rans_data[1]<<16) |
                     ((uint32_t)rans_data[2]<<8) | (uint32_t)rans_data[3];
    const uint8_t *rptr = rans_data + 4;

    /* Clear output */
    for (int row = 0; row < height; row++)
        memset(data + row * pitch_elems, 0, width * sizeof(int32_t));

    size_t resid_byte = 0;
    int resid_bit = 0;
    int row = 0, col = 0;

    for (int t = 0; t < token_count && row < height; t++) {
        /* Decode token */
        uint32_t slot = state & (JANS_TABLE_SIZE - 1);
        int sym = table.decode_sym[slot];
        uint16_t freq = table.freq[sym];
        state = freq * (state >> JANS_TABLE_BITS) + slot - table.cum_freq[sym];
        if (rans_dec_renorm(&state, &rptr, rans_end) != 0) return -1;

        int rc = sym / JANS_MAG_CLASSES;
        int mc = sym % JANS_MAG_CLASSES;

        /* Read run residual bits */
        int run_resid = bitbuf_read(resid_data, resid_size, &resid_byte, &resid_bit,
                                    run_class_bits[rc]);
        int run = class_to_run(rc, run_resid);

        /* Apply zeros */
        col += run;
        while (col >= width) { col -= width; row++; }

        if (mc > 0 && row < height) {
            /* Read magnitude residual bits */
            int mag_resid = bitbuf_read(resid_data, resid_size, &resid_byte, &resid_bit,
                                        mag_class_bits[mc]);
            int mag = class_to_mag(mc, mag_resid);

            /* Read sign bit */
            int sign = bitbuf_read(resid_data, resid_size, &resid_byte, &resid_bit, 1);

            if (col < width)
                data[row * pitch_elems + col] = sign ? -mag : mag;
            col++;
            if (col >= width) { row++; col = 0; }
        }
    }

    return 0;
}
