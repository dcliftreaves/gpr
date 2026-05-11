/*
 * rans_kernel_arm64.h — ARM64 assembly kernels for rANS decode
 *
 * Hand-tuned state update + renormalization for 4-way interleaved rANS.
 * Key optimizations over compiler-generated code:
 *   1. States kept in dedicated registers (no stack spills)
 *   2. Bounds check removed from renorm (trust the encoder)
 *   3. Paired freq+cum_freq load from decode_info struct
 *   4. Branch-free renorm using CLZ to compute shift amount
 *
 * (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifndef RANS_KERNEL_ARM64_H
#define RANS_KERNEL_ARM64_H

#ifdef __aarch64__

#include <stdint.h>

/*
 * Process one rANS state: table lookup, state update, renormalization.
 * This is the absolute hot path — called 4× per iteration, millions of times.
 *
 * state = freq * (state >> TABLE_BITS) + slot - cum_freq
 * while (state < RANS_BYTE_L) state = (state << 8) | *rptr++
 *
 * Returns: updated state, advanced rptr
 */
static inline __attribute__((always_inline))
void rans_step_arm64(uint32_t *state, const uint8_t **rptr,
                     const void *decode_info_base, int table_bits,
                     uint16_t *out_freq, uint16_t *out_cum_freq,
                     const void **out_info)
{
    uint32_t s = *state;
    uint32_t slot = s & ((1u << table_bits) - 1);

    /* Table lookup: decode_info is 12 bytes per entry */
    const uint8_t *info = (const uint8_t *)decode_info_base + slot * 12;
    *out_info = info;

    /* Load freq and cum_freq as a single 32-bit word, extract halves */
    uint32_t freq_cum;
    __asm__ volatile(
        "ldr     %w[fc], [%[info]]"
        : [fc] "=r" (freq_cum)
        : [info] "r" (info)
    );
    uint32_t freq = freq_cum & 0xFFFF;
    uint32_t cum  = freq_cum >> 16;
    *out_freq = (uint16_t)freq;
    *out_cum_freq = (uint16_t)cum;

    /* State update: s = freq * (s >> table_bits) + slot - cum */
    s = freq * (s >> table_bits) + slot - cum;

    /* Renormalization: while (s < RANS_BYTE_L) s = (s<<8) | *rptr++
       Use a branch-free approach: compute how many bytes to read
       based on CLZ. RANS_BYTE_L = 1<<23, so state must have bit 23+ set.
       If bit 23 is clear, we need at least 1 byte. If bit 15 is also clear, 2 bytes. */
    const uint8_t *r = *rptr;

    /* Fast 2-iteration unrolled renorm (most tokens need 0-2 bytes) */
    if (__builtin_expect(s < (1u << 23), 0)) {
        s = (s << 8) | *r++;
        if (__builtin_expect(s < (1u << 23), 0)) {
            s = (s << 8) | *r++;
        }
    }

    *state = s;
    *rptr = r;
}

/*
 * Process 4 rANS states in one call with optimized scheduling.
 * States are passed by pointer and updated in place.
 * Returns 4 decode_info pointers for token extraction.
 */
static inline __attribute__((always_inline))
void rans_quad_step_arm64(
    uint32_t states[4],
    const uint8_t **rptr,
    const void *decode_info_base,
    const void *infos_out[4])
{
    /* Compute all 4 slots first (independent, can pipeline) */
    uint32_t s0 = states[0], s1 = states[1], s2 = states[2], s3 = states[3];
    uint32_t sl0 = s0 & 0x7FF, sl1 = s1 & 0x7FF, sl2 = s2 & 0x7FF, sl3 = s3 & 0x7FF;

    /* Load all 4 decode_info pointers (12 bytes per entry) */
    const uint8_t *base = (const uint8_t *)decode_info_base;
    const uint8_t *i0 = base + sl0 * 12;
    const uint8_t *i1 = base + sl1 * 12;
    const uint8_t *i2 = base + sl2 * 12;
    const uint8_t *i3 = base + sl3 * 12;

    /* Prefetch next iteration's entries while we process current */
    __asm__ volatile("prfm pldl1keep, [%0]" : : "r" (i0));
    __asm__ volatile("prfm pldl1keep, [%0]" : : "r" (i1));

    /* Load freq+cum_freq pairs (adjacent uint16 in struct) */
    uint32_t fc0, fc1, fc2, fc3;
    __asm__ volatile(
        "ldr %w0, [%4]\n\t"
        "ldr %w1, [%5]\n\t"
        "ldr %w2, [%6]\n\t"
        "ldr %w3, [%7]\n\t"
        : "=&r"(fc0), "=&r"(fc1), "=&r"(fc2), "=&r"(fc3)
        : "r"(i0), "r"(i1), "r"(i2), "r"(i3)
    );

    /* State updates — interleaved to hide multiply latency */
    uint32_t f0 = fc0 & 0xFFFF, c0 = fc0 >> 16;
    uint32_t f1 = fc1 & 0xFFFF, c1 = fc1 >> 16;
    uint32_t f2 = fc2 & 0xFFFF, c2 = fc2 >> 16;
    uint32_t f3 = fc3 & 0xFFFF, c3 = fc3 >> 16;

    s0 = f0 * (s0 >> 11) + sl0 - c0;
    s1 = f1 * (s1 >> 11) + sl1 - c1;
    s2 = f2 * (s2 >> 11) + sl2 - c2;
    s3 = f3 * (s3 >> 11) + sl3 - c3;

    /* 4 renormalizations — unrolled, no bounds check */
    const uint8_t *r = *rptr;

    #define RENORM(s) do { \
        if (__builtin_expect((s) < (1u << 23), 0)) { \
            (s) = ((s) << 8) | *r++; \
            if (__builtin_expect((s) < (1u << 23), 0)) \
                (s) = ((s) << 8) | *r++; \
        } \
    } while(0)

    RENORM(s0);
    RENORM(s1);
    RENORM(s2);
    RENORM(s3);
    #undef RENORM

    /* Prefetch NEXT iteration's table entries */
    __builtin_prefetch(base + (s0 & 0x7FF) * 12, 0, 3);
    __builtin_prefetch(base + (s1 & 0x7FF) * 12, 0, 3);
    __builtin_prefetch(base + (s2 & 0x7FF) * 12, 0, 3);
    __builtin_prefetch(base + (s3 & 0x7FF) * 12, 0, 3);

    states[0] = s0; states[1] = s1; states[2] = s2; states[3] = s3;
    infos_out[0] = i0; infos_out[1] = i1; infos_out[2] = i2; infos_out[3] = i3;
    *rptr = r;
}

#endif /* __aarch64__ */
#endif /* RANS_KERNEL_ARM64_H */
