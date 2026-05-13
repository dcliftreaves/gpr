/*
 * fused_encode_arm64.S — ARM64 assembly for fused encoder hot loops
 *
 * Implemented:
 *   1. fused_unpack_row_rggb_asm  — Bayer→GS,RG,BG,GD for RGGB pattern
 *   2. fused_unpack_row_gbrg_asm  — same but for GBRG pattern
 *
 * Approach (per output lane):
 *   - 4 ldrh from the Bayer rows (post-increment).
 *   - 4 cmp/csel for branchless clip to log_max.
 *   - 4 ldrh-with-shifted-index for the LUT lookups.
 *   - All arithmetic (gs, gd, rg, bg) in GPRs — scalar add/sub/asr are
 *     1-cycle dual-issue ops on M1 and don't compete with the NEON ports.
 *   - 4 single-word stores per lane to the four output channels.
 *
 * Honest disclaimer (M1 measurement, May 2026):
 *   The compiler's NEON-intrinsics lowering (umov+ldrh chain + 32 lane
 *   inserts to rebuild NEON regs) is already very close to optimal on
 *   Apple M1.  Producer-unpack pass measures ~6.0 ms with C-intrinsics,
 *   ~6.0 ms with this asm — no significant win on M1.  The asm is kept
 *   because it is expected to win 10-20% on Cortex-A78 where the NEON
 *   port pressure is higher (4-wide retire vs M1's 8-wide).
 *
 * Register conventions (ARM64 AAPCS64):
 *   x0..x7   argument registers
 *   x9..x15  caller-saved scratch
 *   x16,x17  intra-procedure scratch
 *   x19..x28 callee-saved (must preserve)
 *   x29 fp, x30 lr
 *
 * (C) Copyright 2026 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifdef __aarch64__

/* macOS uses leading underscore on symbol names; Linux/ELF does not. */
#if defined(__APPLE__)
#  define CNAME(name) _##name
#else
#  define CNAME(name) name
#endif

.text

/* ----------------------------------------------------------------
 * int fused_unpack_row_rggb_asm(
 *     const uint16_t *row1,    // x0  — RGGB: [R G1 R G1 ...]
 *     const uint16_t *row2,    // x1  —       [G2 B G2 B ...]
 *     const uint16_t *log_tbl, // x2
 *     int32_t *out_gs,         // x3
 *     int32_t *out_rg,         // x4
 *     int32_t *out_bg,         // x5
 *     int32_t *out_gd,         // x6
 *     int ch_width,            // w7
 *     int log_max,             // [sp+0]  (Apple: 4B slot; Linux: 8B slot)
 *     int mid2                 // [sp+8]  (Apple: at +4)
 * );
 * Returns: number of columns processed (multiple of 8).
 * ---------------------------------------------------------------- */

.globl CNAME(fused_unpack_row_rggb_asm)
.p2align 4
CNAME(fused_unpack_row_rggb_asm):
    stp     x29, x30, [sp, #-32]!
    mov     x29, sp
    stp     x19, x20, [sp, #16]

    /* Apple/Linux differ on packing of fixed-int stack args.  Apple packs
       4-byte ints into 4-byte slots; Linux uses 8-byte slots. */
#if defined(__APPLE__)
    ldr     w19, [sp, #32]               /* log_max */
    ldr     w20, [sp, #36]               /* mid2    */
#else
    ldr     w19, [sp, #32]
    ldr     w20, [sp, #40]
#endif

    /* Round-down ch_width to multiple of 8. */
    and     w17, w7, #~7
    cbz     w17, .Lrggb_done

    mov     w8, wzr
.Lrggb_iter:
    mov     w16, #8                      /* lane counter */
.Lrggb_lane:
    ldrh    w9,  [x0], #2                /* R   */
    ldrh    w10, [x0], #2                /* G1  */
    ldrh    w11, [x1], #2                /* G2  */
    ldrh    w12, [x1], #2                /* B   */
    /* Branchless clip to log_max. */
    cmp     w9,  w19
    csel    w9,  w19, w9,  hi
    cmp     w10, w19
    csel    w10, w19, w10, hi
    cmp     w11, w19
    csel    w11, w19, w11, hi
    cmp     w12, w19
    csel    w12, w19, w12, hi
    /* LUT lookups (each LUT entry is uint16_t = 2 bytes; index << 1). */
    ldrh    w9,  [x2, w9,  uxtw #1]      /* r   */
    ldrh    w10, [x2, w10, uxtw #1]      /* g1  */
    ldrh    w11, [x2, w11, uxtw #1]      /* g2  */
    ldrh    w12, [x2, w12, uxtw #1]      /* b   */
    /* Compute outputs. */
    add     w13, w10, w11                /* g1+g2 */
    asr     w13, w13, #1                 /* gs */
    sub     w14, w10, w11
    add     w14, w14, w20
    asr     w14, w14, #1                 /* gd */
    sub     w15, w9, w13
    add     w15, w15, w20
    asr     w15, w15, #1                 /* rg */
    sub     w9, w12, w13
    add     w9, w9, w20
    asr     w9, w9, #1                   /* bg */
    /* Stores. */
    str     w13, [x3], #4
    str     w15, [x4], #4
    str     w9,  [x5], #4
    str     w14, [x6], #4

    subs    w16, w16, #1
    b.ne    .Lrggb_lane

    add     w8, w8, #8
    cmp     w8, w17
    b.lt    .Lrggb_iter

.Lrggb_done:
    mov     w0, w17
    ldp     x19, x20, [sp, #16]
    ldp     x29, x30, [sp], #32
    ret


/* ----------------------------------------------------------------
 * GBRG: row1 = [G1 B G1 B ...], row2 = [R G2 R G2 ...].
 * Same signature as rggb. */

.globl CNAME(fused_unpack_row_gbrg_asm)
.p2align 4
CNAME(fused_unpack_row_gbrg_asm):
    stp     x29, x30, [sp, #-32]!
    mov     x29, sp
    stp     x19, x20, [sp, #16]

#if defined(__APPLE__)
    ldr     w19, [sp, #32]
    ldr     w20, [sp, #36]
#else
    ldr     w19, [sp, #32]
    ldr     w20, [sp, #40]
#endif

    and     w17, w7, #~7
    cbz     w17, .Lgbrg_done

    mov     w8, wzr
.Lgbrg_iter:
    mov     w16, #8
.Lgbrg_lane:
    ldrh    w10, [x0], #2                /* G1 */
    ldrh    w12, [x0], #2                /* B  */
    ldrh    w9,  [x1], #2                /* R  */
    ldrh    w11, [x1], #2                /* G2 */
    cmp     w9,  w19
    csel    w9,  w19, w9,  hi
    cmp     w10, w19
    csel    w10, w19, w10, hi
    cmp     w11, w19
    csel    w11, w19, w11, hi
    cmp     w12, w19
    csel    w12, w19, w12, hi
    ldrh    w9,  [x2, w9,  uxtw #1]
    ldrh    w10, [x2, w10, uxtw #1]
    ldrh    w11, [x2, w11, uxtw #1]
    ldrh    w12, [x2, w12, uxtw #1]
    add     w13, w10, w11
    asr     w13, w13, #1
    sub     w14, w10, w11
    add     w14, w14, w20
    asr     w14, w14, #1
    sub     w15, w9, w13
    add     w15, w15, w20
    asr     w15, w15, #1
    sub     w9, w12, w13
    add     w9, w9, w20
    asr     w9, w9, #1
    str     w13, [x3], #4
    str     w15, [x4], #4
    str     w9,  [x5], #4
    str     w14, [x6], #4

    subs    w16, w16, #1
    b.ne    .Lgbrg_lane

    add     w8, w8, #8
    cmp     w8, w17
    b.lt    .Lgbrg_iter

.Lgbrg_done:
    mov     w0, w17
    ldp     x19, x20, [sp, #16]
    ldp     x29, x30, [sp], #32
    ret

#endif /* __aarch64__ */
