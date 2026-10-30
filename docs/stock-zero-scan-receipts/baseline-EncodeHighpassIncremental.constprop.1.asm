
/mnt/ssd/gpr_work/stock-zero-scan-prototype-20261030/build-baseline/zero_scan_benchmark:     file format elf64-littleaarch64


Disassembly of section .init:

Disassembly of section .plt:

Disassembly of section .text:

0000000000005dd0 <EncodeHighpassIncremental.constprop.1>:
    5dd0:	a9bc7bfd 	stp	x29, x30, [sp, #-64]!
    5dd4:	52800404 	mov	w4, #0x20                  	// #32
    5dd8:	12003c63 	and	w3, w3, #0xffff
    5ddc:	910003fd 	mov	x29, sp
    5de0:	f940040f 	ldr	x15, [x0, #8]
    5de4:	a90153f3 	stp	x19, x20, [sp, #16]
    5de8:	b940100b 	ldr	w11, [x0, #16]
    5dec:	a9025bf5 	stp	x21, x22, [sp, #32]
    5df0:	52800007 	mov	w7, #0x0                   	// #0
    5df4:	a90363f7 	stp	x23, x24, [sp, #48]
    5df8:	f940102d 	ldr	x13, [x1, #32]
    5dfc:	39405006 	ldrb	w6, [x0, #20]
    5e00:	f94005ee 	ldr	x14, [x15, #8]
    5e04:	4b060084 	sub	w4, w4, w6
    5e08:	f9402df0 	ldr	x16, [x15, #88]
    5e0c:	9ac4256b 	lsr	x11, x11, x4
    5e10:	b94001b1 	ldr	w17, [x13]
    5e14:	8b1001ce 	add	x14, x14, x16
    5e18:	b4000045 	cbz	x5, 5e20 <EncodeHighpassIncremental.constprop.1+0x50>
    5e1c:	b94000a7 	ldr	w7, [x5]
    5e20:	8b23244a 	add	x10, x2, w3, uxth #1
    5e24:	aa0e03ec 	mov	x12, x14
    5e28:	52800009 	mov	w9, #0x0                   	// #0
    5e2c:	d37f7d24 	ubfiz	x4, x9, #1, #32
    5e30:	8b04005e 	add	x30, x2, x4
    5e34:	350006a7 	cbnz	w7, 5f08 <EncodeHighpassIncremental.constprop.1+0x138>
    5e38:	11001132 	add	w18, w9, #0x4
    5e3c:	6b03025f 	cmp	w18, w3
    5e40:	54000648 	b.hi	5f08 <EncodeHighpassIncremental.constprop.1+0x138>  // b.pmore
    5e44:	11000d28 	add	w8, w9, #0x3
    5e48:	78e87848 	ldrsh	w8, [x2, x8, lsl #1]
    5e4c:	340005e8 	cbz	w8, 5f08 <EncodeHighpassIncremental.constprop.1+0x138>
    5e50:	11000533 	add	w19, w9, #0x1
    5e54:	11000929 	add	w9, w9, #0x2
    5e58:	f9401434 	ldr	x20, [x1, #40]
    5e5c:	92403d08 	and	x8, x8, #0xffff
    5e60:	78646844 	ldrh	w4, [x2, x4]
    5e64:	78737855 	ldrh	w21, [x2, x19, lsl #1]
    5e68:	78697853 	ldrh	w19, [x2, x9, lsl #1]
    5e6c:	f8687a9e 	ldr	x30, [x20, x8, lsl #3]
    5e70:	f8757a95 	ldr	x21, [x20, x21, lsl #3]
    5e74:	92407fc9 	and	x9, x30, #0xffffffff
    5e78:	f8647a88 	ldr	x8, [x20, x4, lsl #3]
    5e7c:	d360ffde 	lsr	x30, x30, #32
    5e80:	f8737a93 	ldr	x19, [x20, x19, lsl #3]
    5e84:	d360feb7 	lsr	x23, x21, #32
    5e88:	d360fd04 	lsr	x4, x8, #32
    5e8c:	92407eb5 	and	x21, x21, #0xffffffff
    5e90:	0b0403d6 	add	w22, w30, w4
    5e94:	92407d08 	and	x8, x8, #0xffffffff
    5e98:	d360fe74 	lsr	x20, x19, #32
    5e9c:	92407e73 	and	x19, x19, #0xffffffff
    5ea0:	0b170298 	add	w24, w20, w23
    5ea4:	0b1802d6 	add	w22, w22, w24
    5ea8:	710082df 	cmp	w22, #0x20
    5eac:	54000728 	b.hi	5f90 <EncodeHighpassIncremental.constprop.1+0x1c0>  // b.pmore
    5eb0:	0b1403d4 	add	w20, w30, w20
    5eb4:	9ad72104 	lsl	x4, x8, x23
    5eb8:	aa150084 	orr	x4, x4, x21
    5ebc:	9ad6216b 	lsl	x11, x11, x22
    5ec0:	9ade2273 	lsl	x19, x19, x30
    5ec4:	0b1600c6 	add	w6, w6, w22
    5ec8:	aa090273 	orr	x19, x19, x9
    5ecc:	9ad42084 	lsl	x4, x4, x20
    5ed0:	aa0b0084 	orr	x4, x4, x11
    5ed4:	aa04026b 	orr	x11, x19, x4
    5ed8:	71007cdf 	cmp	w6, #0x1f
    5edc:	540000a9 	b.ls	5ef0 <EncodeHighpassIncremental.constprop.1+0x120>  // b.plast
    5ee0:	510080c6 	sub	w6, w6, #0x20
    5ee4:	9ac62564 	lsr	x4, x11, x6
    5ee8:	5ac00884 	rev	w4, w4
    5eec:	b8004584 	str	w4, [x12], #4
    5ef0:	6b03025f 	cmp	w18, w3
    5ef4:	540002e0 	b.eq	5f50 <EncodeHighpassIncremental.constprop.1+0x180>  // b.none
    5ef8:	2a1203e9 	mov	w9, w18
    5efc:	d37f7d24 	ubfiz	x4, x9, #1, #32
    5f00:	8b04005e 	add	x30, x2, x4
    5f04:	34fff9a7 	cbz	w7, 5e38 <EncodeHighpassIncremental.constprop.1+0x68>
    5f08:	aa1e03e4 	mov	x4, x30
    5f0c:	eb1e015f 	cmp	x10, x30
    5f10:	540000a1 	b.ne	5f24 <EncodeHighpassIncremental.constprop.1+0x154>  // b.any
    5f14:	14000006 	b	5f2c <EncodeHighpassIncremental.constprop.1+0x15c>
    5f18:	91000884 	add	x4, x4, #0x2
    5f1c:	eb04015f 	cmp	x10, x4
    5f20:	54000060 	b.eq	5f2c <EncodeHighpassIncremental.constprop.1+0x15c>  // b.none
    5f24:	79c00088 	ldrsh	w8, [x4]
    5f28:	34ffff88 	cbz	w8, 5f18 <EncodeHighpassIncremental.constprop.1+0x148>
    5f2c:	cb1e0084 	sub	x4, x4, x30
    5f30:	9341fc84 	asr	x4, x4, #1
    5f34:	0b040129 	add	w9, w9, w4
    5f38:	0b0400e7 	add	w7, w7, w4
    5f3c:	6b03013f 	cmp	w9, w3
    5f40:	540006a3 	b.cc	6014 <EncodeHighpassIncremental.constprop.1+0x244>  // b.lo, b.ul, b.last
    5f44:	6b03013f 	cmp	w9, w3
    5f48:	54fff721 	b.ne	5e2c <EncodeHighpassIncremental.constprop.1+0x5c>  // b.any
    5f4c:	d503201f 	nop
    5f50:	52800401 	mov	w1, #0x20                  	// #32
    5f54:	4b060021 	sub	w1, w1, w6
    5f58:	cb0e018c 	sub	x12, x12, x14
    5f5c:	39005006 	strb	w6, [x0, #20]
    5f60:	9ac12161 	lsl	x1, x11, x1
    5f64:	b9001001 	str	w1, [x0, #16]
    5f68:	8b10018c 	add	x12, x12, x16
    5f6c:	f9002dec 	str	x12, [x15, #88]
    5f70:	b4000045 	cbz	x5, 5f78 <EncodeHighpassIncremental.constprop.1+0x1a8>
    5f74:	b90000a7 	str	w7, [x5]
    5f78:	a94153f3 	ldp	x19, x20, [sp, #16]
    5f7c:	52800000 	mov	w0, #0x0                   	// #0
    5f80:	a9425bf5 	ldp	x21, x22, [sp, #32]
    5f84:	a94363f7 	ldp	x23, x24, [sp, #48]
    5f88:	a8c47bfd 	ldp	x29, x30, [sp], #64
    5f8c:	d65f03c0 	ret
    5f90:	0b0400c6 	add	w6, w6, w4
    5f94:	9ac42164 	lsl	x4, x11, x4
    5f98:	aa080084 	orr	x4, x4, x8
    5f9c:	71007cdf 	cmp	w6, #0x1f
    5fa0:	540000a9 	b.ls	5fb4 <EncodeHighpassIncremental.constprop.1+0x1e4>  // b.plast
    5fa4:	510080c6 	sub	w6, w6, #0x20
    5fa8:	9ac62488 	lsr	x8, x4, x6
    5fac:	5ac00908 	rev	w8, w8
    5fb0:	b8004588 	str	w8, [x12], #4
    5fb4:	0b1700c6 	add	w6, w6, w23
    5fb8:	9ad72084 	lsl	x4, x4, x23
    5fbc:	aa150084 	orr	x4, x4, x21
    5fc0:	71007cdf 	cmp	w6, #0x1f
    5fc4:	540000a9 	b.ls	5fd8 <EncodeHighpassIncremental.constprop.1+0x208>  // b.plast
    5fc8:	510080c6 	sub	w6, w6, #0x20
    5fcc:	9ac62488 	lsr	x8, x4, x6
    5fd0:	5ac00908 	rev	w8, w8
    5fd4:	b8004588 	str	w8, [x12], #4
    5fd8:	0b1400c6 	add	w6, w6, w20
    5fdc:	9ad42084 	lsl	x4, x4, x20
    5fe0:	aa130084 	orr	x4, x4, x19
    5fe4:	71007cdf 	cmp	w6, #0x1f
    5fe8:	540000a9 	b.ls	5ffc <EncodeHighpassIncremental.constprop.1+0x22c>  // b.plast
    5fec:	510080c6 	sub	w6, w6, #0x20
    5ff0:	9ac62488 	lsr	x8, x4, x6
    5ff4:	5ac00908 	rev	w8, w8
    5ff8:	b8004588 	str	w8, [x12], #4
    5ffc:	0b1e00c6 	add	w6, w6, w30
    6000:	9ade2084 	lsl	x4, x4, x30
    6004:	aa09008b 	orr	x11, x4, x9
    6008:	71007cdf 	cmp	w6, #0x1f
    600c:	54fff729 	b.ls	5ef0 <EncodeHighpassIncremental.constprop.1+0x120>  // b.plast
    6010:	17ffffb4 	b	5ee0 <EncodeHighpassIncremental.constprop.1+0x110>
    6014:	34000347 	cbz	w7, 607c <EncodeHighpassIncremental.constprop.1+0x2ac>
    6018:	71002cff 	cmp	w7, #0xb
    601c:	54000309 	b.ls	607c <EncodeHighpassIncremental.constprop.1+0x2ac>  // b.plast
    6020:	51000632 	sub	w18, w17, #0x1
    6024:	52800194 	mov	w20, #0xc                   	// #12
    6028:	d2800093 	mov	x19, #0x4                   	// #4
    602c:	14000003 	b	6038 <EncodeHighpassIncremental.constprop.1+0x268>
    6030:	71002cff 	cmp	w7, #0xb
    6034:	54000249 	b.ls	607c <EncodeHighpassIncremental.constprop.1+0x2ac>  // b.plast
    6038:	6b1200ff 	cmp	w7, w18
    603c:	1a92d0e4 	csel	w4, w7, w18, le
    6040:	9bb44c84 	umaddl	x4, w4, w20, x19
    6044:	8b0401a8 	add	x8, x13, x4
    6048:	386469a4 	ldrb	w4, [x13, x4]
    604c:	2940f908 	ldp	w8, w30, [x8, #4]
    6050:	0b0400c6 	add	w6, w6, w4
    6054:	9ac42164 	lsl	x4, x11, x4
    6058:	aa0403cb 	orr	x11, x30, x4
    605c:	71007cdf 	cmp	w6, #0x1f
    6060:	540000a9 	b.ls	6074 <EncodeHighpassIncremental.constprop.1+0x2a4>  // b.plast
    6064:	510080c6 	sub	w6, w6, #0x20
    6068:	9ac62564 	lsr	x4, x11, x6
    606c:	5ac00884 	rev	w4, w4
    6070:	b8004584 	str	w4, [x12], #4
    6074:	6b0800e7 	subs	w7, w7, w8
    6078:	54fffdc1 	b.ne	6030 <EncodeHighpassIncremental.constprop.1+0x260>  // b.any
    607c:	f9401424 	ldr	x4, [x1, #40]
    6080:	11000532 	add	w18, w9, #0x1
    6084:	78695848 	ldrh	w8, [x2, w9, uxtw #1]
    6088:	f8687888 	ldr	x8, [x4, x8, lsl #3]
    608c:	d360fd09 	lsr	x9, x8, #32
    6090:	0b0900e4 	add	w4, w7, w9
    6094:	7100809f 	cmp	w4, #0x20
    6098:	54000149 	b.ls	60c0 <EncodeHighpassIncremental.constprop.1+0x2f0>  // b.plast
    609c:	0b0700c6 	add	w6, w6, w7
    60a0:	2a0903e4 	mov	w4, w9
    60a4:	9ac7216b 	lsl	x11, x11, x7
    60a8:	71007cdf 	cmp	w6, #0x1f
    60ac:	540000a9 	b.ls	60c0 <EncodeHighpassIncremental.constprop.1+0x2f0>  // b.plast
    60b0:	510080c6 	sub	w6, w6, #0x20
    60b4:	9ac62567 	lsr	x7, x11, x6
    60b8:	5ac008e7 	rev	w7, w7
    60bc:	b8004587 	str	w7, [x12], #4
    60c0:	92407d08 	and	x8, x8, #0xffffffff
    60c4:	0b0400c6 	add	w6, w6, w4
    60c8:	9ac42164 	lsl	x4, x11, x4
    60cc:	aa04010b 	orr	x11, x8, x4
    60d0:	71007cdf 	cmp	w6, #0x1f
    60d4:	54000109 	b.ls	60f4 <EncodeHighpassIncremental.constprop.1+0x324>  // b.plast
    60d8:	510080c6 	sub	w6, w6, #0x20
    60dc:	2a1203e9 	mov	w9, w18
    60e0:	52800007 	mov	w7, #0x0                   	// #0
    60e4:	9ac62564 	lsr	x4, x11, x6
    60e8:	5ac00884 	rev	w4, w4
    60ec:	b8004584 	str	w4, [x12], #4
    60f0:	17ffff95 	b	5f44 <EncodeHighpassIncremental.constprop.1+0x174>
    60f4:	2a1203e9 	mov	w9, w18
    60f8:	52800007 	mov	w7, #0x0                   	// #0
    60fc:	17ffff92 	b	5f44 <EncodeHighpassIncremental.constprop.1+0x174>

Disassembly of section .fini:
