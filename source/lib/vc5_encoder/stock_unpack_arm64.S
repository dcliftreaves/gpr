/* Exact stock Bayer/log transform, with independent LUT loads feeding NEON
 * registers directly instead of a scalar scratch array on the stack. */
#if defined(__APPLE__)
#define SYM(x) _##x
#else
#define SYM(x) x
.section .note.GNU-stack,"",%progbits
#endif
.text
.p2align 4
.globl SYM(gpr_stock_unpack14_row)
SYM(gpr_stock_unpack14_row):
    ldr w8, [sp]
    cbz w7, 3f
    movi v7.8h, #0x10, lsl #8
1:
    /* Each group makes eight unrelated lookups available to the scheduler.
     * Only caller-saved integer/vector registers are used. */
    .macro GATHER off, lane0, lane1
    ldr w9, [x0, #\off]
    ldr w11, [x0, #(\off + 4)]
    ldr w13, [x1, #\off]
    ldr w15, [x1, #(\off + 4)]
    ubfx w10, w9, #18, #14
    ubfx w12, w11, #18, #14
    ubfx w14, w13, #18, #14
    ubfx w16, w15, #18, #14
    ubfx w9, w9, #2, #14
    ubfx w11, w11, #2, #14
    ubfx w13, w13, #2, #14
    ubfx w15, w15, #2, #14
    ldrh w9, [x2, w9, uxtw #1]
    ldrh w10, [x2, w10, uxtw #1]
    ldrh w11, [x2, w11, uxtw #1]
    ldrh w12, [x2, w12, uxtw #1]
    ldrh w13, [x2, w13, uxtw #1]
    ldrh w14, [x2, w14, uxtw #1]
    ldrh w15, [x2, w15, uxtw #1]
    ldrh w16, [x2, w16, uxtw #1]
    orr w9, w9, w11, lsl #16
    orr w10, w10, w12, lsl #16
    orr w13, w13, w15, lsl #16
    orr w14, w14, w16, lsl #16
    ins v0.s[(\lane0 / 2)], w9
    ins v1.s[(\lane0 / 2)], w10
    ins v2.s[(\lane0 / 2)], w13
    ins v3.s[(\lane0 / 2)], w14
    .endm
    GATHER 0, 0, 1
    GATHER 8, 2, 3
    GATHER 16, 4, 5
    GATHER 24, 6, 7
    cbnz w8, 2f
    /* GBRG -> R,G1,G2,B without changing the stock green-difference sign. */
    mov v4.16b, v0.16b
    mov v0.16b, v2.16b
    mov v2.16b, v3.16b
    mov v3.16b, v1.16b
    mov v1.16b, v4.16b
2:
    shadd v4.8h, v1.8h, v2.8h
    sub v5.8h, v1.8h, v2.8h
    shadd v5.8h, v5.8h, v7.8h
    sub v6.8h, v7.8h, v4.8h
    shadd v0.8h, v0.8h, v6.8h
    shadd v3.8h, v3.8h, v6.8h
    str q4, [x3], #16
    str q0, [x4], #16
    str q3, [x5], #16
    str q5, [x6], #16
    add x0, x0, #32
    add x1, x1, #32
    subs w7, w7, #8
    b.ne 1b
3:
    ret
