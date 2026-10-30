
/mnt/ssd/gpr_work/stock-raw-media-runtime/build-runtime/gpr_capture_app:     file format elf64-littleaarch64


Disassembly of section .text:

0000000000013470 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)>:
   13470:	a9b37bfd 	stp	x29, x30, [sp, #-208]!
   13474:	910003fd 	mov	x29, sp
   13478:	a9025bf5 	stp	x21, x22, [sp, #32]
   1347c:	a90363f7 	stp	x23, x24, [sp, #48]
   13480:	f9400035 	ldr	x21, [x1]
   13484:	f9401036 	ldr	x22, [x1, #32]
   13488:	f9402037 	ldr	x23, [x1, #64]
   1348c:	6b0600bf 	cmp	w5, w6
   13490:	54001d22 	b.cs	13834 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3c4>  // b.hs, b.nlast
   13494:	aa0003e8 	mov	x8, x0
   13498:	aa0203eb 	mov	x11, x2
   1349c:	510004d8 	sub	w24, w6, #0x1
   134a0:	a90153f3 	stp	x19, x20, [sp, #16]
   134a4:	2a0503ec 	mov	w12, w5
   134a8:	b9402d02 	ldr	w2, [x8, #44]
   134ac:	4b050318 	sub	w24, w24, w5
   134b0:	a9046bf9 	stp	x25, x26, [sp, #64]
   134b4:	529fe000 	mov	w0, #0xff00                	// #65280
   134b8:	b000028a 	adrp	x10, 64000 <(anonymous namespace)::srgb_table()::table+0xf970>
   134bc:	a90573fb 	stp	x27, x28, [sp, #80]
   134c0:	72a8efe0 	movk	w0, #0x477f, lsl #16
   134c4:	aa0103f9 	mov	x25, x1
   134c8:	6d0627e8 	stp	d8, d9, [sp, #96]
   134cc:	aa0303ee 	mov	x14, x3
   134d0:	aa0403ef 	mov	x15, x4
   134d4:	6d072fea 	stp	d10, d11, [sp, #112]
   134d8:	8b0c0318 	add	x24, x24, x12
   134dc:	911a414a 	add	x10, x10, #0x690
   134e0:	fd0043ec 	str	d12, [sp, #128]
   134e4:	2a0c03ed 	mov	w13, w12
   134e8:	1e270004 	fmov	s4, w0
   134ec:	34001982 	cbz	w2, 1381c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3ac>
   134f0:	d37ef594 	lsl	x20, x12, #2
   134f4:	9102c113 	add	x19, x8, #0xb0
   134f8:	91032112 	add	x18, x8, #0xc8
   134fc:	910263e5 	add	x5, sp, #0x98
   13500:	52800003 	mov	w3, #0x0                   	// #0
   13504:	5281fffa 	mov	w26, #0xfff                 	// #4095
   13508:	1e2e1003 	fmov	s3, #1.000000000000000000e+00
   1350c:	d503201f 	nop
   13510:	f9400264 	ldr	x4, [x19]
   13514:	2a0303e7 	mov	w7, w3
   13518:	f9400246 	ldr	x6, [x18]
   1351c:	11000469 	add	w9, w3, #0x1
   13520:	b8677881 	ldr	w1, [x4, x7, lsl #2]
   13524:	b9403500 	ldr	w0, [x8, #52]
   13528:	b87468d1 	ldr	w17, [x6, x20]
   1352c:	2a0103f0 	mov	w16, w1
   13530:	3942a106 	ldrb	w6, [x8, #168]
   13534:	9bb14000 	umaddl	x0, w0, w17, x16
   13538:	d37ff800 	lsl	x0, x0, #1
   1353c:	35000266 	cbnz	w6, 13588 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x118>
   13540:	1100107b 	add	w27, w3, #0x4
   13544:	6b02037f 	cmp	w27, w2
   13548:	54000208 	b.hi	13588 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x118>  // b.pmore
   1354c:	b8695890 	ldr	w16, [x4, w9, uxtw #2]
   13550:	11000426 	add	w6, w1, #0x1
   13554:	6b06021f 	cmp	w16, w6
   13558:	54000181 	b.ne	13588 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x118>  // b.any
   1355c:	11000870 	add	w16, w3, #0x2
   13560:	11000826 	add	w6, w1, #0x2
   13564:	b8707890 	ldr	w16, [x4, x16, lsl #2]
   13568:	6b06021f 	cmp	w16, w6
   1356c:	540000e1 	b.ne	13588 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x118>  // b.any
   13570:	11000c66 	add	w6, w3, #0x3
   13574:	11000c21 	add	w1, w1, #0x3
   13578:	b8667884 	ldr	w4, [x4, x6, lsl #2]
   1357c:	6b01009f 	cmp	w4, w1
   13580:	54001fc0 	b.eq	13978 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x508>  // b.none
   13584:	d503201f 	nop
   13588:	78e06ac1 	ldrsh	w1, [x22, x0]
   1358c:	2a0203e2 	mov	w2, w2
   13590:	78e06aa4 	ldrsh	w4, [x21, x0]
   13594:	51400821 	sub	w1, w1, #0x2, lsl #12
   13598:	78e06ae0 	ldrsh	w0, [x23, x0]
   1359c:	9b0c1c46 	madd	x6, x2, x12, x7
   135a0:	bd40a500 	ldr	s0, [x8, #164]
   135a4:	0b010481 	add	w1, w4, w1, lsl #1
   135a8:	51400800 	sub	w0, w0, #0x2, lsl #12
   135ac:	13027c82 	asr	w2, w4, #2
   135b0:	13027c21 	asr	w1, w1, #2
   135b4:	0b000480 	add	w0, w4, w0, lsl #1
   135b8:	7100003f 	cmp	w1, #0x0
   135bc:	1a9fa021 	csel	w1, w1, wzr, ge	// ge = tcont
   135c0:	13027c00 	asr	w0, w0, #2
   135c4:	713ffc3f 	cmp	w1, #0xfff
   135c8:	1a9ad021 	csel	w1, w1, w26, le
   135cc:	7100005f 	cmp	w2, #0x0
   135d0:	1a9fa042 	csel	w2, w2, wzr, ge	// ge = tcont
   135d4:	713ffc5f 	cmp	w2, #0xfff
   135d8:	1a9ad042 	csel	w2, w2, w26, le
   135dc:	7100001f 	cmp	w0, #0x0
   135e0:	1a9fa000 	csel	w0, w0, wzr, ge	// ge = tcont
   135e4:	7c61d942 	ldr	h2, [x10, w1, sxtw #1]
   135e8:	713ffc1f 	cmp	w0, #0xfff
   135ec:	1a9ad000 	csel	w0, w0, w26, le
   135f0:	7c62d941 	ldr	h1, [x10, w2, sxtw #1]
   135f4:	5e21d842 	scvtf	s2, s2
   135f8:	7c60d945 	ldr	h5, [x10, w0, sxtw #1]
   135fc:	5e21d821 	scvtf	s1, s1
   13600:	a94f8101 	ldp	x1, x0, [x8, #248]
   13604:	1e201842 	fdiv	s2, s2, s0
   13608:	5e21d8a5 	scvtf	s5, s5
   1360c:	1e201821 	fdiv	s1, s1, s0
   13610:	1e2018a5 	fdiv	s5, s5, s0
   13614:	eb00003f 	cmp	x1, x0
   13618:	540017e0 	b.eq	13914 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4a4>  // b.none
   1361c:	d37cecc2 	lsl	x2, x6, #4
   13620:	1e2e1007 	fmov	s7, #1.000000000000000000e+00
   13624:	8b020020 	add	x0, x1, x2
   13628:	1e2040f4 	fmov	s20, s7
   1362c:	1e2040e0 	fmov	s0, s7
   13630:	1e2040e6 	fmov	s6, s7
   13634:	bc626833 	ldr	s19, [x1, x2]
   13638:	2d40c412 	ldp	s18, s17, [x0, #4]
   1363c:	bd400c10 	ldr	s16, [x0, #12]
   13640:	bd405116 	ldr	s22, [x8, #80]
   13644:	bd409515 	ldr	s21, [x8, #148]
   13648:	1e363842 	fsub	s2, s2, s22
   1364c:	1e350842 	fmul	s2, s2, s21
   13650:	1e232050 	fcmpe	s2, s3
   13654:	54001264 	b.mi	138a0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x430>  // b.first
   13658:	1e272270 	fcmpe	s19, s7
   1365c:	54001484 	b.mi	138ec <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x47c>  // b.first
   13660:	bd405502 	ldr	s2, [x8, #84]
   13664:	bd409913 	ldr	s19, [x8, #152]
   13668:	1e223822 	fsub	s2, s1, s2
   1366c:	1e330842 	fmul	s2, s2, s19
   13670:	1e232050 	fcmpe	s2, s3
   13674:	54001044 	b.mi	1387c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x40c>  // b.first
   13678:	1e342250 	fcmpe	s18, s20
   1367c:	54001304 	b.mi	138dc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x46c>  // b.first
   13680:	bd405912 	ldr	s18, [x8, #88]
   13684:	bd409d02 	ldr	s2, [x8, #156]
   13688:	1e323821 	fsub	s1, s1, s18
   1368c:	1e220821 	fmul	s1, s1, s2
   13690:	1e232030 	fcmpe	s1, s3
   13694:	540011a4 	b.mi	138c8 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x458>  // b.first
   13698:	1e312010 	fcmpe	s0, s17
   1369c:	5400124c 	b.gt	138e4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x474>
   136a0:	bd405d01 	ldr	s1, [x8, #92]
   136a4:	1e342800 	fadd	s0, s0, s20
   136a8:	bd40a102 	ldr	s2, [x8, #160]
   136ac:	1e2c1011 	fmov	s17, #5.000000000000000000e-01
   136b0:	1e2138a1 	fsub	s1, s5, s1
   136b4:	1e310800 	fmul	s0, s0, s17
   136b8:	1e220821 	fmul	s1, s1, s2
   136bc:	1e232030 	fcmpe	s1, s3
   136c0:	54000fa4 	b.mi	138b4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x444>  // b.first
   136c4:	1e262210 	fcmpe	s16, s6
   136c8:	54001224 	b.mi	1390c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x49c>  // b.first
   136cc:	bd408501 	ldr	s1, [x8, #132]
   136d0:	1e2120f0 	fcmpe	s7, s1
   136d4:	5400118c 	b.gt	13904 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x494>
   136d8:	bd408901 	ldr	s1, [x8, #136]
   136dc:	1e212010 	fcmpe	s0, s1
   136e0:	540010ec 	b.gt	138fc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x48c>
   136e4:	bd408d01 	ldr	s1, [x8, #140]
   136e8:	1e2120d0 	fcmpe	s6, s1
   136ec:	5400104c 	b.gt	138f4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x484>
   136f0:	2d4c0505 	ldp	s5, s1, [x8, #96]
   136f4:	bd406902 	ldr	s2, [x8, #104]
   136f8:	1e210801 	fmul	s1, s0, s1
   136fc:	1f0704a1 	fmadd	s1, s5, s7, s1
   13700:	1f060441 	fmadd	s1, s2, s6, s1
   13704:	1e232030 	fcmpe	s1, s3
   13708:	540009e4 	b.mi	13844 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3d4>  // b.first
   1370c:	1e2e1001 	fmov	s1, #1.000000000000000000e+00
   13710:	bd409102 	ldr	s2, [x8, #144]
   13714:	1e220821 	fmul	s1, s1, s2
   13718:	1e202038 	fcmpe	s1, #0.0
   1371c:	5400006c 	b.gt	13728 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2b8>
   13720:	52800000 	mov	w0, #0x0                   	// #0
   13724:	14000008 	b	13744 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2d4>
   13728:	1e232030 	fcmpe	s1, s3
   1372c:	52801fe0 	mov	w0, #0xff                  	// #255
   13730:	540000aa 	b.ge	13744 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2d4>  // b.tcont
   13734:	1e2c1005 	fmov	s5, #5.000000000000000000e-01
   13738:	1f041421 	fmadd	s1, s1, s4, s5
   1373c:	1e390020 	fcvtzu	w0, s1
   13740:	38604960 	ldrb	w0, [x11, w0, uxtw]
   13744:	2d4d8510 	ldp	s16, s1, [x8, #108]
   13748:	390263e0 	strb	w0, [sp, #152]
   1374c:	bd407505 	ldr	s5, [x8, #116]
   13750:	1e210801 	fmul	s1, s0, s1
   13754:	1f070601 	fmadd	s1, s16, s7, s1
   13758:	1f0604a1 	fmadd	s1, s5, s6, s1
   1375c:	1e232030 	fcmpe	s1, s3
   13760:	54000844 	b.mi	13868 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3f8>  // b.first
   13764:	1e204041 	fmov	s1, s2
   13768:	1e202038 	fcmpe	s1, #0.0
   1376c:	5400006c 	b.gt	13778 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x308>
   13770:	52800000 	mov	w0, #0x0                   	// #0
   13774:	14000008 	b	13794 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x324>
   13778:	1e232030 	fcmpe	s1, s3
   1377c:	52801fe0 	mov	w0, #0xff                  	// #255
   13780:	540000aa 	b.ge	13794 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x324>  // b.tcont
   13784:	1e2c1005 	fmov	s5, #5.000000000000000000e-01
   13788:	1f041421 	fmadd	s1, s1, s4, s5
   1378c:	1e390020 	fcvtzu	w0, s1
   13790:	38604960 	ldrb	w0, [x11, w0, uxtw]
   13794:	2d4f4105 	ldp	s5, s16, [x8, #120]
   13798:	390267e0 	strb	w0, [sp, #153]
   1379c:	bd408101 	ldr	s1, [x8, #128]
   137a0:	1e300800 	fmul	s0, s0, s16
   137a4:	1f0700a0 	fmadd	s0, s5, s7, s0
   137a8:	1f060020 	fmadd	s0, s1, s6, s0
   137ac:	1e232010 	fcmpe	s0, s3
   137b0:	54000524 	b.mi	13854 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3e4>  // b.first
   137b4:	1e202058 	fcmpe	s2, #0.0
   137b8:	5400006c 	b.gt	137c4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x354>
   137bc:	52800006 	mov	w6, #0x0                   	// #0
   137c0:	14000008 	b	137e0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x370>
   137c4:	1e232050 	fcmpe	s2, s3
   137c8:	52801fe6 	mov	w6, #0xff                  	// #255
   137cc:	540000aa 	b.ge	137e0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x370>  // b.tcont
   137d0:	1e2c1000 	fmov	s0, #5.000000000000000000e-01
   137d4:	1f040040 	fmadd	s0, s2, s4, s0
   137d8:	1e390000 	fcvtzu	w0, s0
   137dc:	38604966 	ldrb	w6, [x11, w0, uxtw]
   137e0:	2a0d03e4 	mov	w4, w13
   137e4:	aa0f03e2 	mov	x2, x15
   137e8:	aa0e03e1 	mov	x1, x14
   137ec:	aa0803e0 	mov	x0, x8
   137f0:	39026be6 	strb	w6, [sp, #154]
   137f4:	97fffb5f 	bl	12570 <(anonymous namespace)::display_pixel(gpr_preview_plan const*, unsigned char*, unsigned long, unsigned int, unsigned int, unsigned char const*)>
   137f8:	2a0903e3 	mov	w3, w9
   137fc:	b9402d02 	ldr	w2, [x8, #44]
   13800:	6b09005f 	cmp	w2, w9
   13804:	54ffe868 	b.hi	13510 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0xa0>  // b.pmore
   13808:	eb18019f 	cmp	x12, x24
   1380c:	54000080 	b.eq	1381c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3ac>  // b.none
   13810:	9100058c 	add	x12, x12, #0x1
   13814:	2a0c03ed 	mov	w13, w12
   13818:	35ffe6c2 	cbnz	w2, 134f0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x80>
   1381c:	a94153f3 	ldp	x19, x20, [sp, #16]
   13820:	a9446bf9 	ldp	x25, x26, [sp, #64]
   13824:	a94573fb 	ldp	x27, x28, [sp, #80]
   13828:	6d4627e8 	ldp	d8, d9, [sp, #96]
   1382c:	6d472fea 	ldp	d10, d11, [sp, #112]
   13830:	fd4043ec 	ldr	d12, [sp, #128]
   13834:	a9425bf5 	ldp	x21, x22, [sp, #32]
   13838:	a94363f7 	ldp	x23, x24, [sp, #48]
   1383c:	a8cd7bfd 	ldp	x29, x30, [sp], #208
   13840:	d65f03c0 	ret
   13844:	1e202038 	fcmpe	s1, #0.0
   13848:	0f000402 	movi	v2.2s, #0x0
   1384c:	1e22cc21 	fcsel	s1, s1, s2, gt
   13850:	17ffffb0 	b	13710 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2a0>
   13854:	1e202018 	fcmpe	s0, #0.0
   13858:	5400004c 	b.gt	13860 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3f0>
   1385c:	0f000400 	movi	v0.2s, #0x0
   13860:	1e200842 	fmul	s2, s2, s0
   13864:	17ffffd4 	b	137b4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x344>
   13868:	1e202038 	fcmpe	s1, #0.0
   1386c:	5400004c 	b.gt	13874 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x404>
   13870:	0f000401 	movi	v1.2s, #0x0
   13874:	1e210841 	fmul	s1, s2, s1
   13878:	17ffffbc 	b	13768 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2f8>
   1387c:	1e202058 	fcmpe	s2, #0.0
   13880:	5400004c 	b.gt	13888 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x418>
   13884:	0f000402 	movi	v2.2s, #0x0
   13888:	1e220a52 	fmul	s18, s18, s2
   1388c:	17ffff7b 	b	13678 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x208>
   13890:	1e204213 	fmov	s19, s16
   13894:	1e204207 	fmov	s7, s16
   13898:	1e204211 	fmov	s17, s16
   1389c:	1e204206 	fmov	s6, s16
   138a0:	1e202058 	fcmpe	s2, #0.0
   138a4:	5400004c 	b.gt	138ac <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x43c>
   138a8:	0f000402 	movi	v2.2s, #0x0
   138ac:	1e220a73 	fmul	s19, s19, s2
   138b0:	17ffff6a 	b	13658 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1e8>
   138b4:	1e202038 	fcmpe	s1, #0.0
   138b8:	5400004c 	b.gt	138c0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x450>
   138bc:	0f000401 	movi	v1.2s, #0x0
   138c0:	1e210a10 	fmul	s16, s16, s1
   138c4:	17ffff80 	b	136c4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x254>
   138c8:	1e202038 	fcmpe	s1, #0.0
   138cc:	5400004c 	b.gt	138d4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x464>
   138d0:	0f000401 	movi	v1.2s, #0x0
   138d4:	1e210a31 	fmul	s17, s17, s1
   138d8:	17ffff70 	b	13698 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x228>
   138dc:	1e204254 	fmov	s20, s18
   138e0:	17ffff68 	b	13680 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x210>
   138e4:	1e204220 	fmov	s0, s17
   138e8:	17ffff6e 	b	136a0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x230>
   138ec:	1e204267 	fmov	s7, s19
   138f0:	17ffff5c 	b	13660 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1f0>
   138f4:	1e204026 	fmov	s6, s1
   138f8:	17ffff7e 	b	136f0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x280>
   138fc:	1e204020 	fmov	s0, s1
   13900:	17ffff79 	b	136e4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x274>
   13904:	1e204027 	fmov	s7, s1
   13908:	17ffff74 	b	136d8 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x268>
   1390c:	1e204206 	fmov	s6, s16
   13910:	17ffff6f 	b	136cc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x25c>
   13914:	a94e0500 	ldp	x0, x1, [x8, #224]
   13918:	eb01001f 	cmp	x0, x1
   1391c:	54000120 	b.eq	13940 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4d0>  // b.none
   13920:	8b061400 	add	x0, x0, x6, lsl #5
   13924:	ad401800 	ldp	q0, q6, [x0]
   13928:	ad051be0 	stp	q0, q6, [sp, #160]
   1392c:	2d544bf3 	ldp	s19, s18, [sp, #160]
   13930:	2d5543f1 	ldp	s17, s16, [sp, #168]
   13934:	2d5653e7 	ldp	s7, s20, [sp, #176]
   13938:	2d571be0 	ldp	s0, s6, [sp, #184]
   1393c:	17ffff41 	b	13640 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1d0>
   13940:	bd405106 	ldr	s6, [x8, #80]
   13944:	1e2e1010 	fmov	s16, #1.000000000000000000e+00
   13948:	bd409500 	ldr	s0, [x8, #148]
   1394c:	1e204212 	fmov	s18, s16
   13950:	1e204214 	fmov	s20, s16
   13954:	1e263842 	fsub	s2, s2, s6
   13958:	1e200842 	fmul	s2, s2, s0
   1395c:	1e204200 	fmov	s0, s16
   13960:	1e302050 	fcmpe	s2, s16
   13964:	54fff964 	b.mi	13890 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x420>  // b.first
   13968:	1e204211 	fmov	s17, s16
   1396c:	1e204206 	fmov	s6, s16
   13970:	1e204207 	fmov	s7, s16
   13974:	17ffff3b 	b	13660 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1f0>
   13978:	f9401322 	ldr	x2, [x25, #32]
   1397c:	1e2e1007 	fmov	s7, #1.000000000000000000e+00
   13980:	f9402321 	ldr	x1, [x25, #64]
   13984:	4f012405 	movi	v5.4s, #0x20, lsl #8
   13988:	fc606840 	ldr	d0, [x2, x0]
   1398c:	4f00c5e2 	movi	v2.4s, #0xf, msl #8
   13990:	bd40a509 	ldr	s9, [x8, #164]
   13994:	fc606821 	ldr	d1, [x1, x0]
   13998:	0f10a400 	sxtl	v0.4s, v0.4h
   1399c:	f9400321 	ldr	x1, [x25]
   139a0:	0f10a421 	sxtl	v1.4s, v1.4h
   139a4:	6ea58400 	sub	v0.4s, v0.4s, v5.4s
   139a8:	1e2918e7 	fdiv	s7, s7, s9
   139ac:	fc606826 	ldr	d6, [x1, x0]
   139b0:	f9407d02 	ldr	x2, [x8, #248]
   139b4:	0f10a4c8 	sxtl	v8.4s, v6.4h
   139b8:	4f215400 	shl	v0.4s, v0.4s, #1
   139bc:	6ea58421 	sub	v1.4s, v1.4s, v5.4s
   139c0:	4f000405 	movi	v5.4s, #0x0
   139c4:	f9408104 	ldr	x4, [x8, #256]
   139c8:	0e661000 	saddw	v0.4s, v0.4s, v6.4h
   139cc:	4f3e0506 	sshr	v6.4s, v8.4s, #2
   139d0:	4f215421 	shl	v1.4s, v1.4s, #1
   139d4:	4f3e0400 	sshr	v0.4s, v0.4s, #2
   139d8:	4ea66c46 	smin	v6.4s, v2.4s, v6.4s
   139dc:	4ea88421 	add	v1.4s, v1.4s, v8.4s
   139e0:	4ea06c40 	smin	v0.4s, v2.4s, v0.4s
   139e4:	4ea664a6 	smax	v6.4s, v5.4s, v6.4s
   139e8:	4f3e0421 	sshr	v1.4s, v1.4s, #2
   139ec:	4ea064a0 	smax	v0.4s, v5.4s, v0.4s
   139f0:	9e6600c0 	fmov	x0, d6
   139f4:	0e143cc6 	mov	w6, v6.s[2]
   139f8:	4ea16c41 	smin	v1.4s, v2.4s, v1.4s
   139fc:	0e1c3cc1 	mov	w1, v6.s[3]
   13a00:	9e660010 	fmov	x16, d0
   13a04:	0e0c3c1c 	mov	w28, v0.s[1]
   13a08:	7c605942 	ldr	h2, [x10, w0, uxtw #1]
   13a0c:	0e0c3cc0 	mov	w0, v6.s[1]
   13a10:	4ea164a5 	smax	v5.4s, v5.4s, v1.4s
   13a14:	7c66594b 	ldr	h11, [x10, w6, uxtw #1]
   13a18:	0e143c11 	mov	w17, v0.s[2]
   13a1c:	7c705941 	ldr	h1, [x10, w16, uxtw #1]
   13a20:	7c7c5949 	ldr	h9, [x10, w28, uxtw #1]
   13a24:	7c605946 	ldr	h6, [x10, w0, uxtw #1]
   13a28:	0e0c3cb0 	mov	w16, v5.s[1]
   13a2c:	0e1c3c00 	mov	w0, v0.s[3]
   13a30:	9e6600be 	fmov	x30, d5
   13a34:	0e143ca6 	mov	w6, v5.s[2]
   13a38:	6e060521 	mov	v1.h[1], v9.h[0]
   13a3c:	6e0604c2 	mov	v2.h[1], v6.h[0]
   13a40:	7c71594a 	ldr	h10, [x10, w17, uxtw #1]
   13a44:	7c615949 	ldr	h9, [x10, w1, uxtw #1]
   13a48:	7c7e5940 	ldr	h0, [x10, w30, uxtw #1]
   13a4c:	7c605946 	ldr	h6, [x10, w0, uxtw #1]
   13a50:	0e1c3ca0 	mov	w0, v5.s[3]
   13a54:	7c705945 	ldr	h5, [x10, w16, uxtw #1]
   13a58:	6e0a0541 	mov	v1.h[2], v10.h[0]
   13a5c:	7c665948 	ldr	h8, [x10, w6, uxtw #1]
   13a60:	6e0a0562 	mov	v2.h[2], v11.h[0]
   13a64:	6e0604a0 	mov	v0.h[1], v5.h[0]
   13a68:	7c605945 	ldr	h5, [x10, w0, uxtw #1]
   13a6c:	6e0e04c1 	mov	v1.h[3], v6.h[0]
   13a70:	6e0e0522 	mov	v2.h[3], v9.h[0]
   13a74:	6e0a0500 	mov	v0.h[2], v8.h[0]
   13a78:	2f10a421 	uxtl	v1.4s, v1.4h
   13a7c:	2f10a442 	uxtl	v2.4s, v2.4h
   13a80:	6e0e04a0 	mov	v0.h[3], v5.h[0]
   13a84:	6e21d821 	ucvtf	v1.4s, v1.4s
   13a88:	6e21d842 	ucvtf	v2.4s, v2.4s
   13a8c:	2f10a400 	uxtl	v0.4s, v0.4h
   13a90:	4f87902a 	fmul	v10.4s, v1.4s, v7.s[0]
   13a94:	4f879042 	fmul	v2.4s, v2.4s, v7.s[0]
   13a98:	6e21d800 	ucvtf	v0.4s, v0.4s
   13a9c:	4f879009 	fmul	v9.4s, v0.4s, v7.s[0]
   13aa0:	eb04005f 	cmp	x2, x4
   13aa4:	54000f40 	b.eq	13c8c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x81c>  // b.none
   13aa8:	4f03f611 	fmov	v17.4s, #1.000000000000000000e+00
   13aac:	b9402d00 	ldr	w0, [x8, #44]
   13ab0:	4eb11e3e 	mov	v30.16b, v17.16b
   13ab4:	9b0c1c00 	madd	x0, x0, x12, x7
   13ab8:	4eb11e20 	mov	v0.16b, v17.16b
   13abc:	4eb11e33 	mov	v19.16b, v17.16b
   13ac0:	8b001040 	add	x0, x2, x0, lsl #4
   13ac4:	4c400814 	ld4	{v20.4s-v23.4s}, [x0]
   13ac8:	4eb41e9d 	mov	v29.16b, v20.16b
   13acc:	4eb51ea8 	mov	v8.16b, v21.16b
   13ad0:	4eb61edf 	mov	v31.16b, v22.16b
   13ad4:	4eb71efc 	mov	v28.16b, v23.16b
   13ad8:	2d4a4114 	ldp	s20, s16, [x8, #80]
   13adc:	f00000e0 	adrp	x0, 32000 <typeinfo name for std::__future_base::_Task_setter<std::unique_ptr<std::__future_base::_Result<_codec_error>, std::__future_base::_Result_base::_Deleter>, std::thread::_Invoker<std::tuple<Output::coefficients(void*, unsigned long, unsigned long, vc5_preview_coefficients const*)::{lambda(unsigned int)#1}, int> >, _codec_error>+0x48>
   13ae0:	2d4b4901 	ldp	s1, s18, [x8, #88]
   13ae4:	910283fc 	add	x28, sp, #0xa0
   13ae8:	4e040610 	dup	v16.4s, v16.s[0]
   13aec:	bd408d1b 	ldr	s27, [x8, #140]
   13af0:	2d52d90c 	ldp	s12, s22, [x8, #148]
   13af4:	4e040421 	dup	v1.4s, v1.s[0]
   13af8:	bd406119 	ldr	s25, [x8, #96]
   13afc:	2d53ad15 	ldp	s21, s11, [x8, #156]
   13b00:	4eb0d450 	fsub	v16.4s, v2.4s, v16.4s
   13b04:	bd406d18 	ldr	s24, [x8, #108]
   13b08:	4ea1d446 	fsub	v6.4s, v2.4s, v1.4s
   13b0c:	4f03f607 	fmov	v7.4s, #1.000000000000000000e+00
   13b10:	4e040694 	dup	v20.4s, v20.s[0]
   13b14:	4f969210 	fmul	v16.4s, v16.4s, v22.s[0]
   13b18:	4f9590c6 	fmul	v6.4s, v6.4s, v21.s[0]
   13b1c:	4f000405 	movi	v5.4s, #0x0
   13b20:	4e040652 	dup	v18.4s, v18.s[0]
   13b24:	4eb4d54a 	fsub	v10.4s, v10.4s, v20.4s
   13b28:	4ea6f4e6 	fmin	v6.4s, v7.4s, v6.4s
   13b2c:	4eb0f4f0 	fmin	v16.4s, v7.4s, v16.4s
   13b30:	4eb2d529 	fsub	v9.4s, v9.4s, v18.4s
   13b34:	bd409112 	ldr	s18, [x8, #144]
   13b38:	4f8c914a 	fmul	v10.4s, v10.4s, v12.s[0]
   13b3c:	4e26f4ac 	fmax	v12.4s, v5.4s, v6.4s
   13b40:	4e30f4b0 	fmax	v16.4s, v5.4s, v16.4s
   13b44:	4f8b9129 	fmul	v9.4s, v9.4s, v11.s[0]
   13b48:	4eaaf4ea 	fmin	v10.4s, v7.4s, v10.4s
   13b4c:	6e2cdfff 	fmul	v31.4s, v31.4s, v12.4s
   13b50:	6e30dd0b 	fmul	v11.4s, v8.4s, v16.4s
   13b54:	4f03f406 	fmov	v6.4s, #5.000000000000000000e-01
   13b58:	4e2af4b0 	fmax	v16.4s, v5.4s, v10.4s
   13b5c:	4ebff7de 	fmin	v30.4s, v30.4s, v31.4s
   13b60:	4eabf400 	fmin	v0.4s, v0.4s, v11.4s
   13b64:	4ea9f4e8 	fmin	v8.4s, v7.4s, v9.4s
   13b68:	bd408909 	ldr	s9, [x8, #136]
   13b6c:	2d502914 	ldp	s20, s10, [x8, #128]
   13b70:	4e3ed400 	fadd	v0.4s, v0.4s, v30.4s
   13b74:	6e30dfbd 	fmul	v29.4s, v29.4s, v16.4s
   13b78:	4e28f4a8 	fmax	v8.4s, v5.4s, v8.4s
   13b7c:	4e040529 	dup	v9.4s, v9.s[0]
   13b80:	6e26dc00 	fmul	v0.4s, v0.4s, v6.4s
   13b84:	2d4cd902 	ldp	s2, s22, [x8, #100]
   13b88:	2d4e5501 	ldp	s1, s21, [x8, #112]
   13b8c:	2d4f6917 	ldp	s23, s26, [x8, #120]
   13b90:	4ea9f400 	fmin	v0.4s, v0.4s, v9.4s
   13b94:	4ebdf673 	fmin	v19.4s, v19.4s, v29.4s
   13b98:	6e28df9c 	fmul	v28.4s, v28.4s, v8.4s
   13b9c:	4e04054a 	dup	v10.4s, v10.s[0]
   13ba0:	4f829002 	fmul	v2.4s, v0.4s, v2.s[0]
   13ba4:	4f819001 	fmul	v1.4s, v0.4s, v1.s[0]
   13ba8:	4ebcf630 	fmin	v16.4s, v17.4s, v28.4s
   13bac:	4eaaf673 	fmin	v19.4s, v19.4s, v10.4s
   13bb0:	4e04077b 	dup	v27.4s, v27.s[0]
   13bb4:	4f9a9000 	fmul	v0.4s, v0.4s, v26.s[0]
   13bb8:	3dc32411 	ldr	q17, [x0, #3216]
   13bbc:	4ebbf610 	fmin	v16.4s, v16.4s, v27.4s
   13bc0:	4f991262 	fmla	v2.4s, v19.4s, v25.s[0]
   13bc4:	4f981261 	fmla	v1.4s, v19.4s, v24.s[0]
   13bc8:	4f971260 	fmla	v0.4s, v19.4s, v23.s[0]
   13bcc:	4f961202 	fmla	v2.4s, v16.4s, v22.s[0]
   13bd0:	4f951201 	fmla	v1.4s, v16.4s, v21.s[0]
   13bd4:	4f941200 	fmla	v0.4s, v16.4s, v20.s[0]
   13bd8:	4ea2f4e2 	fmin	v2.4s, v7.4s, v2.4s
   13bdc:	4ea1f4e1 	fmin	v1.4s, v7.4s, v1.4s
   13be0:	4ea0f4e0 	fmin	v0.4s, v7.4s, v0.4s
   13be4:	4e22f4a2 	fmax	v2.4s, v5.4s, v2.4s
   13be8:	4e21f4a1 	fmax	v1.4s, v5.4s, v1.4s
   13bec:	4e20f4a0 	fmax	v0.4s, v5.4s, v0.4s
   13bf0:	4f929042 	fmul	v2.4s, v2.4s, v18.s[0]
   13bf4:	4f929021 	fmul	v1.4s, v1.4s, v18.s[0]
   13bf8:	4f929000 	fmul	v0.4s, v0.4s, v18.s[0]
   13bfc:	4ea2f4e2 	fmin	v2.4s, v7.4s, v2.4s
   13c00:	4ea1f4e1 	fmin	v1.4s, v7.4s, v1.4s
   13c04:	4ea0f4e7 	fmin	v7.4s, v7.4s, v0.4s
   13c08:	4e22f4a2 	fmax	v2.4s, v5.4s, v2.4s
   13c0c:	4e21f4a0 	fmax	v0.4s, v5.4s, v1.4s
   13c10:	4e27f4a5 	fmax	v5.4s, v5.4s, v7.4s
   13c14:	4ea61cc1 	mov	v1.16b, v6.16b
   13c18:	4ea61cc7 	mov	v7.16b, v6.16b
   13c1c:	4e31cca6 	fmla	v6.4s, v5.4s, v17.4s
   13c20:	4e31cc01 	fmla	v1.4s, v0.4s, v17.4s
   13c24:	4e31cc47 	fmla	v7.4s, v2.4s, v17.4s
   13c28:	6ea1b8c0 	fcvtzu	v0.4s, v6.4s
   13c2c:	6ea1b821 	fcvtzu	v1.4s, v1.4s
   13c30:	6ea1b8e2 	fcvtzu	v2.4s, v7.4s
   13c34:	3d8033e0 	str	q0, [sp, #192]
   13c38:	ad0507e2 	stp	q2, q1, [sp, #160]
   13c3c:	b9400380 	ldr	w0, [x28]
   13c40:	b9401387 	ldr	w7, [x28, #16]
   13c44:	2a0d03e4 	mov	w4, w13
   13c48:	b9402386 	ldr	w6, [x28, #32]
   13c4c:	aa0f03e2 	mov	x2, x15
   13c50:	aa0e03e1 	mov	x1, x14
   13c54:	9100139c 	add	x28, x28, #0x4
   13c58:	38606970 	ldrb	w16, [x11, x0]
   13c5c:	aa0803e0 	mov	x0, x8
   13c60:	38676967 	ldrb	w7, [x11, x7]
   13c64:	38666966 	ldrb	w6, [x11, x6]
   13c68:	390263f0 	strb	w16, [sp, #152]
   13c6c:	390267e7 	strb	w7, [sp, #153]
   13c70:	39026be6 	strb	w6, [sp, #154]
   13c74:	97fffa3f 	bl	12570 <(anonymous namespace)::display_pixel(gpr_preview_plan const*, unsigned char*, unsigned long, unsigned int, unsigned int, unsigned char const*)>
   13c78:	2a0903e3 	mov	w3, w9
   13c7c:	6b09037f 	cmp	w27, w9
   13c80:	54ffdbe0 	b.eq	137fc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x38c>  // b.none
   13c84:	11000529 	add	w9, w9, #0x1
   13c88:	17ffffed 	b	13c3c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x7cc>
   13c8c:	a94e0101 	ldp	x1, x0, [x8, #224]
   13c90:	eb00003f 	cmp	x1, x0
   13c94:	540001e0 	b.eq	13cd0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x860>  // b.none
   13c98:	b9402d00 	ldr	w0, [x8, #44]
   13c9c:	9b0c1c00 	madd	x0, x0, x12, x7
   13ca0:	8b001420 	add	x0, x1, x0, lsl #5
   13ca4:	4cdf0814 	ld4	{v20.4s-v23.4s}, [x0], #64
   13ca8:	4c400818 	ld4	{v24.4s-v27.4s}, [x0]
   13cac:	4e981a9d 	uzp1	v29.4s, v20.4s, v24.4s
   13cb0:	4e985a93 	uzp2	v19.4s, v20.4s, v24.4s
   13cb4:	4e991aa8 	uzp1	v8.4s, v21.4s, v25.4s
   13cb8:	4e995aa0 	uzp2	v0.4s, v21.4s, v25.4s
   13cbc:	4e9a1adf 	uzp1	v31.4s, v22.4s, v26.4s
   13cc0:	4e9a5ade 	uzp2	v30.4s, v22.4s, v26.4s
   13cc4:	4e9b1afc 	uzp1	v28.4s, v23.4s, v27.4s
   13cc8:	4e9b5af1 	uzp2	v17.4s, v23.4s, v27.4s
   13ccc:	17ffff83 	b	13ad8 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x668>
   13cd0:	4f03f611 	fmov	v17.4s, #1.000000000000000000e+00
   13cd4:	4eb11e3e 	mov	v30.16b, v17.16b
   13cd8:	4eb11e20 	mov	v0.16b, v17.16b
   13cdc:	4eb11e33 	mov	v19.16b, v17.16b
   13ce0:	4eb11e3c 	mov	v28.16b, v17.16b
   13ce4:	4eb11e3f 	mov	v31.16b, v17.16b
   13ce8:	4eb11e28 	mov	v8.16b, v17.16b
   13cec:	4eb11e3d 	mov	v29.16b, v17.16b
   13cf0:	17ffff7a 	b	13ad8 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x668>
