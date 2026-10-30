
/mnt/ssd/gpr_work/stock-zero-scan-prototype-20261030/build-word/zero_scan_benchmark:     file format elf64-littleaarch64


Disassembly of section .init:

Disassembly of section .plt:

Disassembly of section .text:

0000000000005dd0 <EncodeHighpassIncremental.constprop.1>:
    5dd0:	a9bb7bfd 	stp	x29, x30, [sp, #-80]!
    5dd4:	52800404 	mov	w4, #0x20                  	// #32
    5dd8:	12003c63 	and	w3, w3, #0xffff
    5ddc:	910003fd 	mov	x29, sp
    5de0:	f9400410 	ldr	x16, [x0, #8]
    5de4:	a90153f3 	stp	x19, x20, [sp, #16]
    5de8:	b940100b 	ldr	w11, [x0, #16]
    5dec:	f940102d 	ldr	x13, [x1, #32]
    5df0:	a9025bf5 	stp	x21, x22, [sp, #32]
    5df4:	52800007 	mov	w7, #0x0                   	// #0
    5df8:	f940060f 	ldr	x15, [x16, #8]
    5dfc:	a90363f7 	stp	x23, x24, [sp, #48]
    5e00:	b94001b2 	ldr	w18, [x13]
    5e04:	f9402e11 	ldr	x17, [x16, #88]
    5e08:	f90023f9 	str	x25, [sp, #64]
    5e0c:	39405006 	ldrb	w6, [x0, #20]
    5e10:	8b1101ef 	add	x15, x15, x17
    5e14:	4b060084 	sub	w4, w4, w6
    5e18:	9ac4256b 	lsr	x11, x11, x4
    5e1c:	b4000045 	cbz	x5, 5e24 <EncodeHighpassIncremental.constprop.1+0x54>
    5e20:	b94000a7 	ldr	w7, [x5]
    5e24:	d37f3c6e 	ubfiz	x14, x3, #1, #16
    5e28:	aa0f03ec 	mov	x12, x15
    5e2c:	8b0e0048 	add	x8, x2, x14
    5e30:	5280000a 	mov	w10, #0x0                   	// #0
    5e34:	d37f7d44 	ubfiz	x4, x10, #1, #32
    5e38:	8b040053 	add	x19, x2, x4
    5e3c:	350006a7 	cbnz	w7, 5f10 <EncodeHighpassIncremental.constprop.1+0x140>
    5e40:	1100115e 	add	w30, w10, #0x4
    5e44:	6b0303df 	cmp	w30, w3
    5e48:	54000648 	b.hi	5f10 <EncodeHighpassIncremental.constprop.1+0x140>  // b.pmore
    5e4c:	11000d49 	add	w9, w10, #0x3
    5e50:	78e97849 	ldrsh	w9, [x2, x9, lsl #1]
    5e54:	340005e9 	cbz	w9, 5f10 <EncodeHighpassIncremental.constprop.1+0x140>
    5e58:	11000553 	add	w19, w10, #0x1
    5e5c:	1100094a 	add	w10, w10, #0x2
    5e60:	f9401435 	ldr	x21, [x1, #40]
    5e64:	92403d29 	and	x9, x9, #0xffff
    5e68:	78646844 	ldrh	w4, [x2, x4]
    5e6c:	78737856 	ldrh	w22, [x2, x19, lsl #1]
    5e70:	786a7854 	ldrh	w20, [x2, x10, lsl #1]
    5e74:	f8697ab3 	ldr	x19, [x21, x9, lsl #3]
    5e78:	f8767ab6 	ldr	x22, [x21, x22, lsl #3]
    5e7c:	92407e6a 	and	x10, x19, #0xffffffff
    5e80:	f8647aa9 	ldr	x9, [x21, x4, lsl #3]
    5e84:	d360fe73 	lsr	x19, x19, #32
    5e88:	f8747ab4 	ldr	x20, [x21, x20, lsl #3]
    5e8c:	d360fed7 	lsr	x23, x22, #32
    5e90:	d360fd24 	lsr	x4, x9, #32
    5e94:	92407ed6 	and	x22, x22, #0xffffffff
    5e98:	0b040278 	add	w24, w19, w4
    5e9c:	92407d29 	and	x9, x9, #0xffffffff
    5ea0:	d360fe95 	lsr	x21, x20, #32
    5ea4:	92407e94 	and	x20, x20, #0xffffffff
    5ea8:	0b1702b9 	add	w25, w21, w23
    5eac:	0b190318 	add	w24, w24, w25
    5eb0:	7100831f 	cmp	w24, #0x20
    5eb4:	54000888 	b.hi	5fc4 <EncodeHighpassIncremental.constprop.1+0x1f4>  // b.pmore
    5eb8:	0b150275 	add	w21, w19, w21
    5ebc:	9ad72124 	lsl	x4, x9, x23
    5ec0:	aa160084 	orr	x4, x4, x22
    5ec4:	9ad8216b 	lsl	x11, x11, x24
    5ec8:	9ad32294 	lsl	x20, x20, x19
    5ecc:	0b1800c6 	add	w6, w6, w24
    5ed0:	aa0a0294 	orr	x20, x20, x10
    5ed4:	9ad52084 	lsl	x4, x4, x21
    5ed8:	aa0b0084 	orr	x4, x4, x11
    5edc:	aa04028b 	orr	x11, x20, x4
    5ee0:	71007cdf 	cmp	w6, #0x1f
    5ee4:	540000a9 	b.ls	5ef8 <EncodeHighpassIncremental.constprop.1+0x128>  // b.plast
    5ee8:	510080c6 	sub	w6, w6, #0x20
    5eec:	9ac62564 	lsr	x4, x11, x6
    5ef0:	5ac00884 	rev	w4, w4
    5ef4:	b8004584 	str	w4, [x12], #4
    5ef8:	6b0303df 	cmp	w30, w3
    5efc:	54000420 	b.eq	5f80 <EncodeHighpassIncremental.constprop.1+0x1b0>  // b.none
    5f00:	2a1e03ea 	mov	w10, w30
    5f04:	d37f7d44 	ubfiz	x4, x10, #1, #32
    5f08:	8b040053 	add	x19, x2, x4
    5f0c:	34fff9a7 	cbz	w7, 5e40 <EncodeHighpassIncremental.constprop.1+0x70>
    5f10:	cb0401c4 	sub	x4, x14, x4
    5f14:	f100189f 	cmp	x4, #0x6
    5f18:	aa1303e4 	mov	x4, x19
    5f1c:	540000cc 	b.gt	5f34 <EncodeHighpassIncremental.constprop.1+0x164>
    5f20:	1400000d 	b	5f54 <EncodeHighpassIncremental.constprop.1+0x184>
    5f24:	91002084 	add	x4, x4, #0x8
    5f28:	cb040109 	sub	x9, x8, x4
    5f2c:	f100193f 	cmp	x9, #0x6
    5f30:	5400012d 	b.le	5f54 <EncodeHighpassIncremental.constprop.1+0x184>
    5f34:	f9400089 	ldr	x9, [x4]
    5f38:	b4ffff69 	cbz	x9, 5f24 <EncodeHighpassIncremental.constprop.1+0x154>
    5f3c:	eb04011f 	cmp	x8, x4
    5f40:	540000e0 	b.eq	5f5c <EncodeHighpassIncremental.constprop.1+0x18c>  // b.none
    5f44:	d503201f 	nop
    5f48:	79c00089 	ldrsh	w9, [x4]
    5f4c:	35000089 	cbnz	w9, 5f5c <EncodeHighpassIncremental.constprop.1+0x18c>
    5f50:	91000884 	add	x4, x4, #0x2
    5f54:	eb04011f 	cmp	x8, x4
    5f58:	54ffff81 	b.ne	5f48 <EncodeHighpassIncremental.constprop.1+0x178>  // b.any
    5f5c:	cb130084 	sub	x4, x4, x19
    5f60:	9341fc84 	asr	x4, x4, #1
    5f64:	0b04014a 	add	w10, w10, w4
    5f68:	0b0400e7 	add	w7, w7, w4
    5f6c:	6b03015f 	cmp	w10, w3
    5f70:	540006c3 	b.cc	6048 <EncodeHighpassIncremental.constprop.1+0x278>  // b.lo, b.ul, b.last
    5f74:	6b03015f 	cmp	w10, w3
    5f78:	54fff5e1 	b.ne	5e34 <EncodeHighpassIncremental.constprop.1+0x64>  // b.any
    5f7c:	d503201f 	nop
    5f80:	52800401 	mov	w1, #0x20                  	// #32
    5f84:	4b060021 	sub	w1, w1, w6
    5f88:	cb0f018c 	sub	x12, x12, x15
    5f8c:	39005006 	strb	w6, [x0, #20]
    5f90:	9ac12161 	lsl	x1, x11, x1
    5f94:	b9001001 	str	w1, [x0, #16]
    5f98:	8b11018c 	add	x12, x12, x17
    5f9c:	f9002e0c 	str	x12, [x16, #88]
    5fa0:	b4000045 	cbz	x5, 5fa8 <EncodeHighpassIncremental.constprop.1+0x1d8>
    5fa4:	b90000a7 	str	w7, [x5]
    5fa8:	a94153f3 	ldp	x19, x20, [sp, #16]
    5fac:	52800000 	mov	w0, #0x0                   	// #0
    5fb0:	a9425bf5 	ldp	x21, x22, [sp, #32]
    5fb4:	a94363f7 	ldp	x23, x24, [sp, #48]
    5fb8:	f94023f9 	ldr	x25, [sp, #64]
    5fbc:	a8c57bfd 	ldp	x29, x30, [sp], #80
    5fc0:	d65f03c0 	ret
    5fc4:	0b0400c6 	add	w6, w6, w4
    5fc8:	9ac42164 	lsl	x4, x11, x4
    5fcc:	aa090084 	orr	x4, x4, x9
    5fd0:	71007cdf 	cmp	w6, #0x1f
    5fd4:	540000a9 	b.ls	5fe8 <EncodeHighpassIncremental.constprop.1+0x218>  // b.plast
    5fd8:	510080c6 	sub	w6, w6, #0x20
    5fdc:	9ac62489 	lsr	x9, x4, x6
    5fe0:	5ac00929 	rev	w9, w9
    5fe4:	b8004589 	str	w9, [x12], #4
    5fe8:	0b1700c6 	add	w6, w6, w23
    5fec:	9ad72084 	lsl	x4, x4, x23
    5ff0:	aa160084 	orr	x4, x4, x22
    5ff4:	71007cdf 	cmp	w6, #0x1f
    5ff8:	540000a9 	b.ls	600c <EncodeHighpassIncremental.constprop.1+0x23c>  // b.plast
    5ffc:	510080c6 	sub	w6, w6, #0x20
    6000:	9ac62489 	lsr	x9, x4, x6
    6004:	5ac00929 	rev	w9, w9
    6008:	b8004589 	str	w9, [x12], #4
    600c:	0b1500c6 	add	w6, w6, w21
    6010:	9ad52084 	lsl	x4, x4, x21
    6014:	aa140084 	orr	x4, x4, x20
    6018:	71007cdf 	cmp	w6, #0x1f
    601c:	540000a9 	b.ls	6030 <EncodeHighpassIncremental.constprop.1+0x260>  // b.plast
    6020:	510080c6 	sub	w6, w6, #0x20
    6024:	9ac62489 	lsr	x9, x4, x6
    6028:	5ac00929 	rev	w9, w9
    602c:	b8004589 	str	w9, [x12], #4
    6030:	0b1300c6 	add	w6, w6, w19
    6034:	9ad32084 	lsl	x4, x4, x19
    6038:	aa0a008b 	orr	x11, x4, x10
    603c:	71007cdf 	cmp	w6, #0x1f
    6040:	54fff5c9 	b.ls	5ef8 <EncodeHighpassIncremental.constprop.1+0x128>  // b.plast
    6044:	17ffffa9 	b	5ee8 <EncodeHighpassIncremental.constprop.1+0x118>
    6048:	34000347 	cbz	w7, 60b0 <EncodeHighpassIncremental.constprop.1+0x2e0>
    604c:	71002cff 	cmp	w7, #0xb
    6050:	54000309 	b.ls	60b0 <EncodeHighpassIncremental.constprop.1+0x2e0>  // b.plast
    6054:	5100065e 	sub	w30, w18, #0x1
    6058:	52800195 	mov	w21, #0xc                   	// #12
    605c:	d2800094 	mov	x20, #0x4                   	// #4
    6060:	14000003 	b	606c <EncodeHighpassIncremental.constprop.1+0x29c>
    6064:	71002cff 	cmp	w7, #0xb
    6068:	54000249 	b.ls	60b0 <EncodeHighpassIncremental.constprop.1+0x2e0>  // b.plast
    606c:	6b1e00ff 	cmp	w7, w30
    6070:	1a9ed0e4 	csel	w4, w7, w30, le
    6074:	9bb55084 	umaddl	x4, w4, w21, x20
    6078:	8b0401a9 	add	x9, x13, x4
    607c:	386469a4 	ldrb	w4, [x13, x4]
    6080:	2940cd29 	ldp	w9, w19, [x9, #4]
    6084:	0b0400c6 	add	w6, w6, w4
    6088:	9ac42164 	lsl	x4, x11, x4
    608c:	aa04026b 	orr	x11, x19, x4
    6090:	71007cdf 	cmp	w6, #0x1f
    6094:	540000a9 	b.ls	60a8 <EncodeHighpassIncremental.constprop.1+0x2d8>  // b.plast
    6098:	510080c6 	sub	w6, w6, #0x20
    609c:	9ac62564 	lsr	x4, x11, x6
    60a0:	5ac00884 	rev	w4, w4
    60a4:	b8004584 	str	w4, [x12], #4
    60a8:	6b0900e7 	subs	w7, w7, w9
    60ac:	54fffdc1 	b.ne	6064 <EncodeHighpassIncremental.constprop.1+0x294>  // b.any
    60b0:	f9401424 	ldr	x4, [x1, #40]
    60b4:	11000553 	add	w19, w10, #0x1
    60b8:	786a5849 	ldrh	w9, [x2, w10, uxtw #1]
    60bc:	f8697889 	ldr	x9, [x4, x9, lsl #3]
    60c0:	d360fd2a 	lsr	x10, x9, #32
    60c4:	0b0a00e4 	add	w4, w7, w10
    60c8:	7100809f 	cmp	w4, #0x20
    60cc:	54000149 	b.ls	60f4 <EncodeHighpassIncremental.constprop.1+0x324>  // b.plast
    60d0:	0b0700c6 	add	w6, w6, w7
    60d4:	2a0a03e4 	mov	w4, w10
    60d8:	9ac7216b 	lsl	x11, x11, x7
    60dc:	71007cdf 	cmp	w6, #0x1f
    60e0:	540000a9 	b.ls	60f4 <EncodeHighpassIncremental.constprop.1+0x324>  // b.plast
    60e4:	510080c6 	sub	w6, w6, #0x20
    60e8:	9ac62567 	lsr	x7, x11, x6
    60ec:	5ac008e7 	rev	w7, w7
    60f0:	b8004587 	str	w7, [x12], #4
    60f4:	92407d29 	and	x9, x9, #0xffffffff
    60f8:	0b0400c6 	add	w6, w6, w4
    60fc:	9ac42164 	lsl	x4, x11, x4
    6100:	aa04012b 	orr	x11, x9, x4
    6104:	71007cdf 	cmp	w6, #0x1f
    6108:	54000109 	b.ls	6128 <EncodeHighpassIncremental.constprop.1+0x358>  // b.plast
    610c:	510080c6 	sub	w6, w6, #0x20
    6110:	2a1303ea 	mov	w10, w19
    6114:	52800007 	mov	w7, #0x0                   	// #0
    6118:	9ac62564 	lsr	x4, x11, x6
    611c:	5ac00884 	rev	w4, w4
    6120:	b8004584 	str	w4, [x12], #4
    6124:	17ffff94 	b	5f74 <EncodeHighpassIncremental.constprop.1+0x1a4>
    6128:	2a1303ea 	mov	w10, w19
    612c:	52800007 	mov	w7, #0x0                   	// #0
    6130:	17ffff91 	b	5f74 <EncodeHighpassIncremental.constprop.1+0x1a4>

Disassembly of section .fini:
