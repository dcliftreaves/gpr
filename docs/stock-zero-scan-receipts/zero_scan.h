/* Private zero-run scanner experiment. Endpoints are in the same PIXEL array. */
#ifndef GPR_ZERO_SCAN
#define GPR_ZERO_SCAN 0
#endif
#if GPR_ZERO_SCAN == 2 && defined(__aarch64__)
#include <arm_neon.h>
#endif
static inline const PIXEL *FindFirstNonzero(const PIXEL *start, const PIXEL *end)
{
#if GPR_ZERO_SCAN == 1
    while (end-start >= 4) {
        uint64_t word;
        memcpy(&word,start,sizeof(word));
        if (word) break;
        start+=4;
    }
#elif GPR_ZERO_SCAN == 2 && defined(__aarch64__)
    while (end-start >= 8) {
        uint16x8_t values=vld1q_u16((const uint16_t *)start);
        if (vmaxvq_u16(values)) break;
        start+=8;
    }
#endif
    while (start!=end && *start==0) ++start;
    return start;
}
