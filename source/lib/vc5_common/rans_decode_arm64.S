/*
 * rans_decode_arm64.S — ARM64 assembly for the rANS Pass 1 inner loop
 *
 * Processes 4 interleaved rANS states per iteration, extracting
 * (run, value) pairs into SoA arrays. This replaces the C hot loop
 * in jans_decode_band_x4.
 *
 * Register allocation:
 *   x0  = decode_info table base
 *   x1  = rptr (rANS byte stream pointer)
 *   x2  = rans_end
 *   x3  = resid_data
 *   x4  = resid_size
 *   x5  = runs output pointer
 *   x6  = values output pointer
 *   x7  = token_count
 *   w8-w11 = states[0-3]
 *   x12 = resid_byte_pos (passed by reference)
 *   x13 = resid_bit_pos (passed by reference)
 *
 * Returns: pair_count (number of tokens decoded) in w0
 *
 * (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifdef __aarch64__

/* Constants */
.equ TABLE_BITS, 12
.equ TABLE_SIZE, (1 << TABLE_BITS)
.equ TABLE_MASK, (TABLE_SIZE - 1)
.equ RANS_BYTE_L, (1 << 23)
.equ DECODE_INFO_SIZE, 12

.text
.global _rans_pass1_arm64
.p2align 4

/*
 * int rans_pass1_arm64(
 *     const void *decode_info_base,  // x0: &table.decode_info[0]
 *     const uint8_t **rptr_ptr,      // x1: &rptr (updated on return)
 *     const uint8_t *rans_end,       // x2
 *     const uint8_t *resid_data,     // x3
 *     size_t resid_size,             // x4
 *     uint16_t *runs,                // x5
 *     int32_t *values,               // x6
 *     int token_count,               // w7
 *     uint32_t states[4],            // [sp+0]: states array (read/write)
 *     size_t *resid_byte,            // [sp+8]: byte position (read/write)
 *     int *resid_bit                 // [sp+16]: bit position (read/write)
 * );
 *
 * This function is called from C to replace the Pass 1 hot loop.
 * For now, this is a STUB that returns -1 to fall back to C.
 * The actual assembly implementation will be added incrementally.
 */
_rans_pass1_arm64:
    /* Stub: return -1 to signal "use C fallback" */
    mov w0, #-1
    ret

#endif /* __aarch64__ */
