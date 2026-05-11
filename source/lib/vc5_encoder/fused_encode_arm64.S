/*
 * fused_encode_arm64.S — ARM64 assembly for fused encoder hot loops
 *
 * Targets:
 *   - Mac ARM64 (Apple Silicon) as fast iteration testbed
 *   - GoPro GP3 (Cortex-A78) as production target
 *   - Raspberry Pi 5 (Cortex-A76) as intermediate dev platform
 *
 * Hot loops covered (in priority order):
 *   1. fused_unpack_row_neon    — Bayer→GS,RG,BG,GD with log curve
 *   2. fused_horizontal_neon    — wavelet horizontal filter
 *   3. fused_vertical_quant_neon — wavelet vertical + quantize (fused)
 *   4. fused_freq_count_neon    — frequency counting (run, mag classes)
 *
 * Register conventions (ARM64 AAPCS64):
 *   x0-x7: argument registers, caller-saved
 *   x8: indirect result, caller-saved
 *   x9-x15: caller-saved scratch
 *   x16-x17: intra-procedure-call scratch
 *   x18: platform register (avoid on Apple Silicon)
 *   x19-x28: callee-saved (must preserve)
 *   x29 (fp), x30 (lr): frame pointer, link register
 *   v0-v7: argument vector registers, caller-saved
 *   v8-v15: callee-saved (must preserve, but only lower 64 bits)
 *   v16-v31: caller-saved scratch
 *
 * (C) Copyright 2026 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifdef __aarch64__

/* ================================================================
 * Function: fused_unpack_row_neon_asm
 *
 * Bayer → GS, RG, BG, GD with log curve, NEON 4-wide.
 *
 * void fused_unpack_row_neon_asm(
 *     const uint16_t *row1,    // x0: input Bayer row 1
 *     const uint16_t *row2,    // x1: input Bayer row 2
 *     const uint16_t *log_tbl, // x2: log curve LUT (16384 or 65536 entries)
 *     int32_t *out_gs,         // x3: GS output
 *     int32_t *out_rg,         // x4: RG output
 *     int32_t *out_bg,         // x5: BG output
 *     int32_t *out_gd,         // x6: GD output
 *     int ch_width,            // w7: output channel width (in pixels)
 *     int log_max,             // [sp+0]: max log curve input
 *     int mid2,                // [sp+8]: 2 * midpoint (e.g., 16384 for 14-bit)
 *     int is_rggb              // [sp+16]: 1=RGGB, 0=GBRG
 * );
 *
 * Inner loop (per 4 output pixels):
 *   1. Load 8 Bayer pixels from each row (16 total)
 *   2. Clamp to log_max
 *   3. 16 scalar LUT lookups (interleaved with NEON setup)
 *   4. NEON 4-wide: vgs = (vg1 + vg2) >> 1
 *   5. NEON: vgd = ((vg1 - vg2) + vmid2) >> 1
 *   6. NEON: vrg = ((vr - vgs) + vmid2) >> 1
 *   7. NEON: vbg = ((vb - vgs) + vmid2) >> 1
 *   8. Store 4 × 4 × int32 outputs
 *
 * Critical path: LUT lookup (~4 cycles) → NEON load → arithmetic chain (3 cycles)
 * Throughput: ~6 cycles per 4 pixels at IPC=3 (constrained by LUT)
 *
 * STUB: returns -1, falls back to C. Full implementation pending.
 */
.text
.globl _fused_unpack_row_neon_asm
.p2align 4

_fused_unpack_row_neon_asm:
    /* Stub — returns -1 to signal C fallback.
     * Full implementation will be added incrementally:
     *   Phase 1: Inner loop skeleton with NEON loads/stores
     *   Phase 2: Add LUT lookup chain
     *   Phase 3: Software pipeline LUT loads with NEON compute
     *   Phase 4: Unroll 8-wide for better pipeline utilization
     */
    mov w0, #-1
    ret


/* ================================================================
 * Function: fused_horizontal_neon_asm
 *
 * Horizontal wavelet filter, NEON 4-wide.
 *
 * void fused_horizontal_neon_asm(
 *     const int32_t *input,  // x0: input row (channel data)
 *     int32_t *lowpass,      // x1: lowpass output
 *     int32_t *highpass,     // x2: highpass output
 *     int width,             // w3: input width
 *     int prescale           // w4: prescale shift (0, 2, or 3)
 * );
 *
 * Filter math (per output pair i):
 *   lowpass[i]  = PS(in[2i]) + PS(in[2i+1])
 *   highpass[i] = ((PS(in[2i+2]+in[2i+3]) - PS(in[2i-2]+in[2i-1]) + 4) >> 3)
 *               + (PS(in[2i]) - PS(in[2i+1]))
 *
 * where PS(v) = (v + prescale_rounding) >> prescale
 *
 * NEON strategy (4 outputs per iteration):
 *   - Load 12 inputs covering [2i-2 .. 2i+9]
 *   - Apply prescale (vadd round, vshl by -prescale)
 *   - Use vuzpq to extract even/odd samples
 *   - Compute lowpass = evens + odds (single VADD)
 *   - Compute prev_sum and next_sum via paired evens/odds + VADD
 *   - Compute highpass = ((next - prev + 4) >> 3) + (even - odd)
 *
 * STUB: returns -1, falls back to C.
 */
.globl _fused_horizontal_neon_asm
.p2align 4

_fused_horizontal_neon_asm:
    mov w0, #-1
    ret


/* ================================================================
 * Function: fused_vertical_quant_neon_asm
 *
 * Vertical wavelet filter + fused quantization, NEON 4-wide.
 *
 * void fused_vertical_quant_neon_asm(
 *     int32_t *rows[6],      // x0: array of 6 row pointers
 *     int32_t *out_lo,       // x1: lowpass+quant output (LL or HL band)
 *     int32_t *out_hi,       // x2: highpass+quant output (LH or HH band)
 *     int width,             // w3: band width
 *     int32_t mid_lo,        // w4: lowpass midpoint
 *     int32_t mul_lo,        // w5: lowpass multiplier
 *     int32_t mid_hi,        // w6: highpass midpoint
 *     int32_t mul_hi         // w7: highpass multiplier
 * );
 *
 * Vertical filter (middle rows):
 *   low  = r2 + r3
 *   high = ((r4 + r5 - r0 - r1 + 4) >> 3) + (r2 - r3)
 *
 * Quantize (per coefficient):
 *   abs_val = |v|
 *   q = ((abs_val + midpoint) * multiplier) >> 16
 *   result = (v < 0) ? -q : q
 *
 * NEON strategy (4 outputs per iteration):
 *   - 6 row loads (24 NEON registers worth — needs careful scheduling)
 *   - 6-tap filter math (mostly vadd/vsub, 1 vshr)
 *   - VMULL for 32×32→64 multiply in quantize
 *   - VBSL for sign restoration
 *
 * Register pressure: ~20 NEON regs at peak. Use 4-wide on Cortex-A78.
 *
 * STUB: returns -1, falls back to C.
 */
.globl _fused_vertical_quant_neon_asm
.p2align 4

_fused_vertical_quant_neon_asm:
    mov w0, #-1
    ret

#endif /* __aarch64__ */
