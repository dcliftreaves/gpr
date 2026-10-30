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

/* Channel-row kernel: row1,row2,table,out,width,channel in x0..x5. */
.p2align 4
.globl SYM(gpr_stock_unpack14_channel)
SYM(gpr_stock_unpack14_channel):
    cbz w4, 9f
    movi v3.4h, #0x10, lsl #8
    cmp w5, #1
    b.eq 6f
    cmp w5, #2
    b.eq 7f
    cmp w5, #3
    b.eq 8f
5:
    .macro CHANNEL_FOUR kind
    /* Four Bayer quads: two paired 64-bit loads replace four W pairs.
     * All green indices are extracted before reusing packed source registers. */
    ldp x6,x7,[x0]
    ldp x8,x9,[x1]
    ubfx x10,x6,#18,#14
    ubfx x11,x6,#50,#14
    ubfx x12,x7,#18,#14
    ubfx x13,x7,#50,#14
    ubfx x14,x8,#2,#14
    ubfx x15,x8,#34,#14
    ubfx x16,x9,#2,#14
    ubfx x17,x9,#34,#14
    .if \kind == 1
    ubfx x8,x6,#2,#14
    ubfx x9,x6,#34,#14
    ubfx x6,x7,#2,#14
    ubfx x7,x7,#34,#14
    .elseif \kind == 2
    ubfx x6,x8,#18,#14
    ubfx x7,x8,#50,#14
    ubfx x8,x9,#18,#14
    ubfx x9,x9,#50,#14
    .endif
    ldrh w10,[x2,w10,uxtw #1]
    ldrh w11,[x2,w11,uxtw #1]
    ldrh w12,[x2,w12,uxtw #1]
    ldrh w13,[x2,w13,uxtw #1]
    ldrh w14,[x2,w14,uxtw #1]
    ldrh w15,[x2,w15,uxtw #1]
    ldrh w16,[x2,w16,uxtw #1]
    ldrh w17,[x2,w17,uxtw #1]
    .if \kind == 1 || \kind == 2
    ldrh w6,[x2,w6,uxtw #1]
    ldrh w7,[x2,w7,uxtw #1]
    ldrh w8,[x2,w8,uxtw #1]
    ldrh w9,[x2,w9,uxtw #1]
    .endif
    orr w10,w10,w11,lsl #16
    orr w12,w12,w13,lsl #16
    orr w14,w14,w15,lsl #16
    orr w16,w16,w17,lsl #16
    fmov s0,w10
    fmov s1,w14
    ins v0.s[1],w12
    ins v1.s[1],w16
    .if \kind == 3
    sub v0.4h,v0.4h,v1.4h
    shadd v0.4h,v0.4h,v3.4h
    .else
    shadd v0.4h,v0.4h,v1.4h
    .if \kind == 1 || \kind == 2
    .if \kind == 1
    orr w8,w8,w9,lsl #16
    orr w6,w6,w7,lsl #16
    fmov s2,w8
    ins v2.s[1],w6
    .else
    orr w6,w6,w7,lsl #16
    orr w8,w8,w9,lsl #16
    fmov s2,w6
    ins v2.s[1],w8
    .endif
    sub v0.4h,v3.4h,v0.4h
    shadd v0.4h,v2.4h,v0.4h
    .endif
    .endif
    str d0,[x3],#8
    add x0,x0,#16
    add x1,x1,#16
    subs w4,w4,#4
    .endm
    CHANNEL_FOUR 0
    b.ne 5b
    ret
6:
    CHANNEL_FOUR 1
    b.ne 6b
    ret
7:
    CHANNEL_FOUR 2
    b.ne 7b
    ret
8:
    CHANNEL_FOUR 3
    b.ne 8b
9:
    ret
