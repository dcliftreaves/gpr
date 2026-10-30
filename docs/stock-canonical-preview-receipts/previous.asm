
/mnt/ssd/gpr_work/gpr_capture_pre_phase_20261030:     file format elf64-littleaarch64


Disassembly of section .text:

0000000000013500 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)>:
   13500:	a9ac7bfd 	stp	x29, x30, [sp, #-320]!
   13504:	910003fd 	mov	x29, sp
   13508:	a9046bf9 	stp	x25, x26, [sp, #64]
   1350c:	a90573fb 	stp	x27, x28, [sp, #80]
   13510:	f9400039 	ldr	x25, [x1]
   13514:	f940103a 	ldr	x26, [x1, #32]
   13518:	f940203b 	ldr	x27, [x1, #64]
   1351c:	6b0600bf 	cmp	w5, w6
   13520:	54002022 	b.cs	13924 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x424>  // b.hs, b.nlast
   13524:	aa0003e8 	mov	x8, x0
   13528:	aa0203ed 	mov	x13, x2
   1352c:	a90153f3 	stp	x19, x20, [sp, #16]
   13530:	510004d3 	sub	w19, w6, #0x1
   13534:	4b050273 	sub	w19, w19, w5
   13538:	b9402d02 	ldr	w2, [x8, #44]
   1353c:	529fe000 	mov	w0, #0xff00                	// #65280
   13540:	a9025bf5 	stp	x21, x22, [sp, #32]
   13544:	2a0503f5 	mov	w21, w5
   13548:	8b150273 	add	x19, x19, x21
   1354c:	a90363f7 	stp	x23, x24, [sp, #48]
   13550:	aa1503fc 	mov	x28, x21
   13554:	b000028b 	adrp	x11, 64000 <(anonymous namespace)::srgb_table()::table+0xf970>
   13558:	f9003bf3 	str	x19, [sp, #112]
   1355c:	72a8efe0 	movk	w0, #0x477f, lsl #16
   13560:	fd0033e8 	str	d8, [sp, #96]
   13564:	aa0103f8 	mov	x24, x1
   13568:	aa0303f6 	mov	x22, x3
   1356c:	aa0403f7 	mov	x23, x4
   13570:	911a416b 	add	x11, x11, #0x690
   13574:	2a1c03ee 	mov	w14, w28
   13578:	1e270004 	fmov	s4, w0
   1357c:	34001cc2 	cbz	w2, 13914 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x414>
   13580:	d37ef792 	lsl	x18, x28, #2
   13584:	9103010f 	add	x15, x8, #0xc0
   13588:	91036114 	add	x20, x8, #0xd8
   1358c:	910303e5 	add	x5, sp, #0xc0
   13590:	910403e9 	add	x9, sp, #0x100
   13594:	52800003 	mov	w3, #0x0                   	// #0
   13598:	5281ffec 	mov	w12, #0xfff                 	// #4095
   1359c:	1e2e1002 	fmov	s2, #1.000000000000000000e+00
   135a0:	1e2c1003 	fmov	s3, #5.000000000000000000e-01
   135a4:	d503201f 	nop
   135a8:	f94001e6 	ldr	x6, [x15]
   135ac:	2a0303e7 	mov	w7, w3
   135b0:	f9400280 	ldr	x0, [x20]
   135b4:	1100046a 	add	w10, w3, #0x1
   135b8:	b86778c4 	ldr	w4, [x6, x7, lsl #2]
   135bc:	b9403511 	ldr	w17, [x8, #52]
   135c0:	b8726800 	ldr	w0, [x0, x18]
   135c4:	2a0403f0 	mov	w16, w4
   135c8:	3942e101 	ldrb	w1, [x8, #184]
   135cc:	9bb14000 	umaddl	x0, w0, w17, x16
   135d0:	d37ff800 	lsl	x0, x0, #1
   135d4:	35000261 	cbnz	w1, 13620 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x120>
   135d8:	11001073 	add	w19, w3, #0x4
   135dc:	6b02027f 	cmp	w19, w2
   135e0:	54000208 	b.hi	13620 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x120>  // b.pmore
   135e4:	b86a58d1 	ldr	w17, [x6, w10, uxtw #2]
   135e8:	11000490 	add	w16, w4, #0x1
   135ec:	6b10023f 	cmp	w17, w16
   135f0:	54000181 	b.ne	13620 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x120>  // b.any
   135f4:	11000871 	add	w17, w3, #0x2
   135f8:	11000890 	add	w16, w4, #0x2
   135fc:	b87178d1 	ldr	w17, [x6, x17, lsl #2]
   13600:	6b10023f 	cmp	w17, w16
   13604:	540000e1 	b.ne	13620 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x120>  // b.any
   13608:	11000c70 	add	w16, w3, #0x3
   1360c:	11000c84 	add	w4, w4, #0x3
   13610:	b87078c6 	ldr	w6, [x6, x16, lsl #2]
   13614:	6b0400df 	cmp	w6, w4
   13618:	54001fe0 	b.eq	13a14 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x514>  // b.none
   1361c:	d503201f 	nop
   13620:	78e06b41 	ldrsh	w1, [x26, x0]
   13624:	2a0203e2 	mov	w2, w2
   13628:	78e06b26 	ldrsh	w6, [x25, x0]
   1362c:	51400821 	sub	w1, w1, #0x2, lsl #12
   13630:	78e06b60 	ldrsh	w0, [x27, x0]
   13634:	9b1c1c44 	madd	x4, x2, x28, x7
   13638:	bd40a506 	ldr	s6, [x8, #164]
   1363c:	0b0104c1 	add	w1, w6, w1, lsl #1
   13640:	51400800 	sub	w0, w0, #0x2, lsl #12
   13644:	13027cc2 	asr	w2, w6, #2
   13648:	13027c21 	asr	w1, w1, #2
   1364c:	0b0004c0 	add	w0, w6, w0, lsl #1
   13650:	7100003f 	cmp	w1, #0x0
   13654:	1a9fa021 	csel	w1, w1, wzr, ge	// ge = tcont
   13658:	13027c00 	asr	w0, w0, #2
   1365c:	713ffc3f 	cmp	w1, #0xfff
   13660:	1a8cd021 	csel	w1, w1, w12, le
   13664:	7100005f 	cmp	w2, #0x0
   13668:	1a9fa042 	csel	w2, w2, wzr, ge	// ge = tcont
   1366c:	713ffc5f 	cmp	w2, #0xfff
   13670:	1a8cd042 	csel	w2, w2, w12, le
   13674:	7100001f 	cmp	w0, #0x0
   13678:	1a9fa000 	csel	w0, w0, wzr, ge	// ge = tcont
   1367c:	7c61d961 	ldr	h1, [x11, w1, sxtw #1]
   13680:	713ffc1f 	cmp	w0, #0xfff
   13684:	1a8cd000 	csel	w0, w0, w12, le
   13688:	7c62d960 	ldr	h0, [x11, w2, sxtw #1]
   1368c:	5e21d821 	scvtf	s1, s1
   13690:	7c60d965 	ldr	h5, [x11, w0, sxtw #1]
   13694:	5e21d800 	scvtf	s0, s0
   13698:	a9508101 	ldp	x1, x0, [x8, #264]
   1369c:	1e261821 	fdiv	s1, s1, s6
   136a0:	5e21d8a5 	scvtf	s5, s5
   136a4:	1e261800 	fdiv	s0, s0, s6
   136a8:	1e2618a5 	fdiv	s5, s5, s6
   136ac:	eb00003f 	cmp	x1, x0
   136b0:	540019a0 	b.eq	139e4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4e4>  // b.none
   136b4:	4f03f607 	fmov	v7.4s, #1.000000000000000000e+00
   136b8:	d37cec84 	lsl	x4, x4, #4
   136bc:	3ce46826 	ldr	q6, [x1, x4]
   136c0:	ad081fe6 	stp	q6, q7, [sp, #256]
   136c4:	b940a900 	ldr	w0, [x8, #168]
   136c8:	2a0003e2 	mov	w2, w0
   136cc:	8b204901 	add	x1, x8, w0, uxtw #2
   136d0:	bd405027 	ldr	s7, [x1, #80]
   136d4:	bd409426 	ldr	s6, [x1, #148]
   136d8:	1e273821 	fsub	s1, s1, s7
   136dc:	1e260821 	fmul	s1, s1, s6
   136e0:	1e222030 	fcmpe	s1, s2
   136e4:	540014c4 	b.mi	1397c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x47c>  // b.first
   136e8:	1e2e1001 	fmov	s1, #1.000000000000000000e+00
   136ec:	bc627926 	ldr	s6, [x9, x2, lsl #2]
   136f0:	11001000 	add	w0, w0, #0x4
   136f4:	1e260821 	fmul	s1, s1, s6
   136f8:	bc607926 	ldr	s6, [x9, x0, lsl #2]
   136fc:	1e262030 	fcmpe	s1, s6
   13700:	540015e4 	b.mi	139bc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4bc>  // b.first
   13704:	b940ad00 	ldr	w0, [x8, #172]
   13708:	2a0003e2 	mov	w2, w0
   1370c:	8b204901 	add	x1, x8, w0, uxtw #2
   13710:	bd405021 	ldr	s1, [x1, #80]
   13714:	bd409427 	ldr	s7, [x1, #148]
   13718:	1e213801 	fsub	s1, s0, s1
   1371c:	1e270821 	fmul	s1, s1, s7
   13720:	1e222030 	fcmpe	s1, s2
   13724:	54001244 	b.mi	1396c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x46c>  // b.first
   13728:	1e2e1001 	fmov	s1, #1.000000000000000000e+00
   1372c:	bc627927 	ldr	s7, [x9, x2, lsl #2]
   13730:	11001000 	add	w0, w0, #0x4
   13734:	1e270821 	fmul	s1, s1, s7
   13738:	bc607927 	ldr	s7, [x9, x0, lsl #2]
   1373c:	1e272030 	fcmpe	s1, s7
   13740:	54001364 	b.mi	139ac <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4ac>  // b.first
   13744:	b940b100 	ldr	w0, [x8, #176]
   13748:	2a0003e2 	mov	w2, w0
   1374c:	8b204901 	add	x1, x8, w0, uxtw #2
   13750:	bd405030 	ldr	s16, [x1, #80]
   13754:	bd409421 	ldr	s1, [x1, #148]
   13758:	1e303800 	fsub	s0, s0, s16
   1375c:	1e210800 	fmul	s0, s0, s1
   13760:	1e222010 	fcmpe	s0, s2
   13764:	540011c4 	b.mi	1399c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x49c>  // b.first
   13768:	1e2e1000 	fmov	s0, #1.000000000000000000e+00
   1376c:	bc627921 	ldr	s1, [x9, x2, lsl #2]
   13770:	11001000 	add	w0, w0, #0x4
   13774:	1e210800 	fmul	s0, s0, s1
   13778:	bc607921 	ldr	s1, [x9, x0, lsl #2]
   1377c:	1e212010 	fcmpe	s0, s1
   13780:	540011a4 	b.mi	139b4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4b4>  // b.first
   13784:	b940b500 	ldr	w0, [x8, #180]
   13788:	1e272820 	fadd	s0, s1, s7
   1378c:	2a0003e2 	mov	w2, w0
   13790:	8b204901 	add	x1, x8, w0, uxtw #2
   13794:	1e230800 	fmul	s0, s0, s3
   13798:	bd405021 	ldr	s1, [x1, #80]
   1379c:	bd409427 	ldr	s7, [x1, #148]
   137a0:	1e2138a1 	fsub	s1, s5, s1
   137a4:	1e270821 	fmul	s1, s1, s7
   137a8:	1e222030 	fcmpe	s1, s2
   137ac:	54000f04 	b.mi	1398c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x48c>  // b.first
   137b0:	1e2e1001 	fmov	s1, #1.000000000000000000e+00
   137b4:	bc627925 	ldr	s5, [x9, x2, lsl #2]
   137b8:	11001000 	add	w0, w0, #0x4
   137bc:	1e250821 	fmul	s1, s1, s5
   137c0:	bc607927 	ldr	s7, [x9, x0, lsl #2]
   137c4:	1e272030 	fcmpe	s1, s7
   137c8:	540010a4 	b.mi	139dc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4dc>  // b.first
   137cc:	bd408501 	ldr	s1, [x8, #132]
   137d0:	1e2120d0 	fcmpe	s6, s1
   137d4:	5400100c 	b.gt	139d4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4d4>
   137d8:	bd408901 	ldr	s1, [x8, #136]
   137dc:	1e212010 	fcmpe	s0, s1
   137e0:	54000f6c 	b.gt	139cc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4cc>
   137e4:	bd408d01 	ldr	s1, [x8, #140]
   137e8:	1e2120f0 	fcmpe	s7, s1
   137ec:	54000ecc 	b.gt	139c4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x4c4>
   137f0:	2d4c0510 	ldp	s16, s1, [x8, #96]
   137f4:	bd406905 	ldr	s5, [x8, #104]
   137f8:	1e210801 	fmul	s1, s0, s1
   137fc:	1f060601 	fmadd	s1, s16, s6, s1
   13800:	1f0704a1 	fmadd	s1, s5, s7, s1
   13804:	1e222030 	fcmpe	s1, s2
   13808:	54000964 	b.mi	13934 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x434>  // b.first
   1380c:	1e2e1001 	fmov	s1, #1.000000000000000000e+00
   13810:	bd409105 	ldr	s5, [x8, #144]
   13814:	1e250821 	fmul	s1, s1, s5
   13818:	1e202038 	fcmpe	s1, #0.0
   1381c:	5400006c 	b.gt	13828 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x328>
   13820:	52800000 	mov	w0, #0x0                   	// #0
   13824:	14000007 	b	13840 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x340>
   13828:	1e222030 	fcmpe	s1, s2
   1382c:	52801fe0 	mov	w0, #0xff                  	// #255
   13830:	5400008a 	b.ge	13840 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x340>  // b.tcont
   13834:	1f040c21 	fmadd	s1, s1, s4, s3
   13838:	1e390020 	fcvtzu	w0, s1
   1383c:	386049a0 	ldrb	w0, [x13, w0, uxtw]
   13840:	2d4d8511 	ldp	s17, s1, [x8, #108]
   13844:	390303e0 	strb	w0, [sp, #192]
   13848:	bd407510 	ldr	s16, [x8, #116]
   1384c:	1e210801 	fmul	s1, s0, s1
   13850:	1f060621 	fmadd	s1, s17, s6, s1
   13854:	1f070601 	fmadd	s1, s16, s7, s1
   13858:	1e222030 	fcmpe	s1, s2
   1385c:	540007e4 	b.mi	13958 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x458>  // b.first
   13860:	1e2040a1 	fmov	s1, s5
   13864:	1e202038 	fcmpe	s1, #0.0
   13868:	5400006c 	b.gt	13874 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x374>
   1386c:	52800000 	mov	w0, #0x0                   	// #0
   13870:	14000007 	b	1388c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x38c>
   13874:	1e222030 	fcmpe	s1, s2
   13878:	52801fe0 	mov	w0, #0xff                  	// #255
   1387c:	5400008a 	b.ge	1388c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x38c>  // b.tcont
   13880:	1f040c21 	fmadd	s1, s1, s4, s3
   13884:	1e390020 	fcvtzu	w0, s1
   13888:	386049a0 	ldrb	w0, [x13, w0, uxtw]
   1388c:	2d4f4510 	ldp	s16, s17, [x8, #120]
   13890:	390307e0 	strb	w0, [sp, #193]
   13894:	bd408101 	ldr	s1, [x8, #128]
   13898:	1e310800 	fmul	s0, s0, s17
   1389c:	1f060200 	fmadd	s0, s16, s6, s0
   138a0:	1f070020 	fmadd	s0, s1, s7, s0
   138a4:	1e222010 	fcmpe	s0, s2
   138a8:	540004e4 	b.mi	13944 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x444>  // b.first
   138ac:	1e2020b8 	fcmpe	s5, #0.0
   138b0:	5400006c 	b.gt	138bc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3bc>
   138b4:	52800006 	mov	w6, #0x0                   	// #0
   138b8:	14000007 	b	138d4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3d4>
   138bc:	1e2220b0 	fcmpe	s5, s2
   138c0:	52801fe6 	mov	w6, #0xff                  	// #255
   138c4:	5400008a 	b.ge	138d4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3d4>  // b.tcont
   138c8:	1f040ca5 	fmadd	s5, s5, s4, s3
   138cc:	1e3900a0 	fcvtzu	w0, s5
   138d0:	386049a6 	ldrb	w6, [x13, w0, uxtw]
   138d4:	2a0e03e4 	mov	w4, w14
   138d8:	aa1703e2 	mov	x2, x23
   138dc:	aa1603e1 	mov	x1, x22
   138e0:	aa0803e0 	mov	x0, x8
   138e4:	39030be6 	strb	w6, [sp, #194]
   138e8:	97fffb22 	bl	12570 <(anonymous namespace)::display_pixel(gpr_preview_plan const*, unsigned char*, unsigned long, unsigned int, unsigned int, unsigned char const*)>
   138ec:	2a0a03e3 	mov	w3, w10
   138f0:	b9402d02 	ldr	w2, [x8, #44]
   138f4:	6b0a005f 	cmp	w2, w10
   138f8:	54ffe588 	b.hi	135a8 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0xa8>  // b.pmore
   138fc:	f9403be0 	ldr	x0, [sp, #112]
   13900:	eb1c001f 	cmp	x0, x28
   13904:	54000080 	b.eq	13914 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x414>  // b.none
   13908:	9100079c 	add	x28, x28, #0x1
   1390c:	2a1c03ee 	mov	w14, w28
   13910:	35ffe382 	cbnz	w2, 13580 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x80>
   13914:	a94153f3 	ldp	x19, x20, [sp, #16]
   13918:	a9425bf5 	ldp	x21, x22, [sp, #32]
   1391c:	a94363f7 	ldp	x23, x24, [sp, #48]
   13920:	fd4033e8 	ldr	d8, [sp, #96]
   13924:	a9446bf9 	ldp	x25, x26, [sp, #64]
   13928:	a94573fb 	ldp	x27, x28, [sp, #80]
   1392c:	a8d47bfd 	ldp	x29, x30, [sp], #320
   13930:	d65f03c0 	ret
   13934:	1e202038 	fcmpe	s1, #0.0
   13938:	0f000405 	movi	v5.2s, #0x0
   1393c:	1e25cc21 	fcsel	s1, s1, s5, gt
   13940:	17ffffb4 	b	13810 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x310>
   13944:	1e202018 	fcmpe	s0, #0.0
   13948:	5400004c 	b.gt	13950 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x450>
   1394c:	0f000400 	movi	v0.2s, #0x0
   13950:	1e2008a5 	fmul	s5, s5, s0
   13954:	17ffffd6 	b	138ac <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3ac>
   13958:	1e202038 	fcmpe	s1, #0.0
   1395c:	5400004c 	b.gt	13964 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x464>
   13960:	0f000401 	movi	v1.2s, #0x0
   13964:	1e2108a1 	fmul	s1, s5, s1
   13968:	17ffffbf 	b	13864 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x364>
   1396c:	1e202038 	fcmpe	s1, #0.0
   13970:	0f000407 	movi	v7.2s, #0x0
   13974:	1e27cc21 	fcsel	s1, s1, s7, gt
   13978:	17ffff6d 	b	1372c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x22c>
   1397c:	1e202038 	fcmpe	s1, #0.0
   13980:	0f000406 	movi	v6.2s, #0x0
   13984:	1e26cc21 	fcsel	s1, s1, s6, gt
   13988:	17ffff59 	b	136ec <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1ec>
   1398c:	1e202038 	fcmpe	s1, #0.0
   13990:	0f000405 	movi	v5.2s, #0x0
   13994:	1e25cc21 	fcsel	s1, s1, s5, gt
   13998:	17ffff87 	b	137b4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2b4>
   1399c:	1e202018 	fcmpe	s0, #0.0
   139a0:	0f000401 	movi	v1.2s, #0x0
   139a4:	1e21cc00 	fcsel	s0, s0, s1, gt
   139a8:	17ffff71 	b	1376c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x26c>
   139ac:	1e204027 	fmov	s7, s1
   139b0:	17ffff65 	b	13744 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x244>
   139b4:	1e204001 	fmov	s1, s0
   139b8:	17ffff73 	b	13784 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x284>
   139bc:	1e204026 	fmov	s6, s1
   139c0:	17ffff51 	b	13704 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x204>
   139c4:	1e204027 	fmov	s7, s1
   139c8:	17ffff8a 	b	137f0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2f0>
   139cc:	1e204020 	fmov	s0, s1
   139d0:	17ffff85 	b	137e4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2e4>
   139d4:	1e204026 	fmov	s6, s1
   139d8:	17ffff80 	b	137d8 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2d8>
   139dc:	1e204027 	fmov	s7, s1
   139e0:	17ffff7b 	b	137cc <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x2cc>
   139e4:	a94f0500 	ldp	x0, x1, [x8, #240]
   139e8:	eb01001f 	cmp	x0, x1
   139ec:	540000a0 	b.eq	13a00 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x500>  // b.none
   139f0:	8b041404 	add	x4, x0, x4, lsl #5
   139f4:	ad401c86 	ldp	q6, q7, [x4]
   139f8:	ad001d26 	stp	q6, q7, [x9]
   139fc:	17ffff32 	b	136c4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1c4>
   13a00:	f00000e0 	adrp	x0, 32000 <typeinfo name for std::thread::_State_impl<std::thread::_Invoker<std::tuple<void (std::__future_base::_Async_state_impl<std::thread::_Invoker<std::tuple<Output::coefficients(void*, unsigned long, unsigned long, vc5_preview_coefficients const*)::{lambda(unsigned int)#1}, int> >, _codec_error>::*)(), std::__future_base::_Async_state_impl<std::thread::_Invoker<std::tuple<Output::coefficients(void*, unsigned long, unsigned long, vc5_preview_coefficients const*)::{lambda(unsigned int)#1}, int> >, _codec_error>*> > >+0x40>
   13a04:	910e0000 	add	x0, x0, #0x380
   13a08:	ad401c06 	ldp	q6, q7, [x0]
   13a0c:	ad001d26 	stp	q6, q7, [x9]
   13a10:	17ffff2d 	b	136c4 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x1c4>
   13a14:	f9401304 	ldr	x4, [x24, #32]
   13a18:	1e2e1011 	fmov	s17, #1.000000000000000000e+00
   13a1c:	f9402302 	ldr	x2, [x24, #64]
   13a20:	4f012407 	movi	v7.4s, #0x20, lsl #8
   13a24:	fc606880 	ldr	d0, [x4, x0]
   13a28:	4f00c5e6 	movi	v6.4s, #0xf, msl #8
   13a2c:	bd40a510 	ldr	s16, [x8, #164]
   13a30:	fc606841 	ldr	d1, [x2, x0]
   13a34:	0f10a400 	sxtl	v0.4s, v0.4h
   13a38:	f9400302 	ldr	x2, [x24]
   13a3c:	0f10a421 	sxtl	v1.4s, v1.4h
   13a40:	6ea78400 	sub	v0.4s, v0.4s, v7.4s
   13a44:	1e301a31 	fdiv	s17, s17, s16
   13a48:	fc606845 	ldr	d5, [x2, x0]
   13a4c:	f9408504 	ldr	x4, [x8, #264]
   13a50:	6ea78421 	sub	v1.4s, v1.4s, v7.4s
   13a54:	4f215400 	shl	v0.4s, v0.4s, #1
   13a58:	0f10a4a8 	sxtl	v8.4s, v5.4h
   13a5c:	4f000407 	movi	v7.4s, #0x0
   13a60:	4f215421 	shl	v1.4s, v1.4s, #1
   13a64:	0e651000 	saddw	v0.4s, v0.4s, v5.4h
   13a68:	4f3e0505 	sshr	v5.4s, v8.4s, #2
   13a6c:	f9408906 	ldr	x6, [x8, #272]
   13a70:	4ea88421 	add	v1.4s, v1.4s, v8.4s
   13a74:	4f3e0400 	sshr	v0.4s, v0.4s, #2
   13a78:	4ea56cc5 	smin	v5.4s, v6.4s, v5.4s
   13a7c:	4f3e0421 	sshr	v1.4s, v1.4s, #2
   13a80:	4ea06cc0 	smin	v0.4s, v6.4s, v0.4s
   13a84:	4ea564e5 	smax	v5.4s, v7.4s, v5.4s
   13a88:	4ea16cc1 	smin	v1.4s, v6.4s, v1.4s
   13a8c:	4ea064e0 	smax	v0.4s, v7.4s, v0.4s
   13a90:	9e6600a0 	fmov	x0, d5
   13a94:	0e0c3cb1 	mov	w17, v5.s[1]
   13a98:	0e143cb0 	mov	w16, v5.s[2]
   13a9c:	4ea164e7 	smax	v7.4s, v7.4s, v1.4s
   13aa0:	9e660001 	fmov	x1, d0
   13aa4:	0e143c02 	mov	w2, v0.s[2]
   13aa8:	7c605966 	ldr	h6, [x11, w0, uxtw #1]
   13aac:	0e1c3ca0 	mov	w0, v5.s[3]
   13ab0:	7c715968 	ldr	h8, [x11, w17, uxtw #1]
   13ab4:	0e0c3c15 	mov	w21, v0.s[1]
   13ab8:	0e0c3cf1 	mov	w17, v7.s[1]
   13abc:	7c705974 	ldr	h20, [x11, w16, uxtw #1]
   13ac0:	7c615965 	ldr	h5, [x11, w1, uxtw #1]
   13ac4:	9e6600e1 	fmov	x1, d7
   13ac8:	7c625972 	ldr	h18, [x11, w2, uxtw #1]
   13acc:	0e143cf0 	mov	w16, v7.s[2]
   13ad0:	0e1c3c02 	mov	w2, v0.s[3]
   13ad4:	7c605970 	ldr	h16, [x11, w0, uxtw #1]
   13ad8:	7c755975 	ldr	h21, [x11, w21, uxtw #1]
   13adc:	0e1c3ce0 	mov	w0, v7.s[3]
   13ae0:	7c615961 	ldr	h1, [x11, w1, uxtw #1]
   13ae4:	6e060506 	mov	v6.h[1], v8.h[0]
   13ae8:	7c715973 	ldr	h19, [x11, w17, uxtw #1]
   13aec:	6e0606a5 	mov	v5.h[1], v21.h[0]
   13af0:	7c705968 	ldr	h8, [x11, w16, uxtw #1]
   13af4:	0ea11c20 	mov	v0.8b, v1.8b
   13af8:	7c625967 	ldr	h7, [x11, w2, uxtw #1]
   13afc:	6e0a0686 	mov	v6.h[2], v20.h[0]
   13b00:	7c605961 	ldr	h1, [x11, w0, uxtw #1]
   13b04:	6e0a0645 	mov	v5.h[2], v18.h[0]
   13b08:	6e060660 	mov	v0.h[1], v19.h[0]
   13b0c:	6e0e0606 	mov	v6.h[3], v16.h[0]
   13b10:	6e0e04e5 	mov	v5.h[3], v7.h[0]
   13b14:	6e0a0500 	mov	v0.h[2], v8.h[0]
   13b18:	2f10a4d0 	uxtl	v16.4s, v6.4h
   13b1c:	6e0e0420 	mov	v0.h[3], v1.h[0]
   13b20:	2f10a4a1 	uxtl	v1.4s, v5.4h
   13b24:	6e21da10 	ucvtf	v16.4s, v16.4s
   13b28:	2f10a400 	uxtl	v0.4s, v0.4h
   13b2c:	6e21d821 	ucvtf	v1.4s, v1.4s
   13b30:	4f919210 	fmul	v16.4s, v16.4s, v17.s[0]
   13b34:	6e21d800 	ucvtf	v0.4s, v0.4s
   13b38:	4f919033 	fmul	v19.4s, v1.4s, v17.s[0]
   13b3c:	4f919012 	fmul	v18.4s, v0.4s, v17.s[0]
   13b40:	eb06009f 	cmp	x4, x6
   13b44:	54001340 	b.eq	13dac <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x8ac>  // b.none
   13b48:	4f03f600 	fmov	v0.4s, #1.000000000000000000e+00
   13b4c:	b9402d00 	ldr	w0, [x8, #44]
   13b50:	9b1c1c00 	madd	x0, x0, x28, x7
   13b54:	8b001080 	add	x0, x4, x0, lsl #4
   13b58:	4c400814 	ld4	{v20.4s-v23.4s}, [x0]
   13b5c:	ad000120 	stp	q0, q0, [x9]
   13b60:	ad010120 	stp	q0, q0, [x9, #32]
   13b64:	ad0054b4 	stp	q20, q21, [x5]
   13b68:	ad015cb6 	stp	q22, q23, [x5, #32]
   13b6c:	b940b104 	ldr	w4, [x8, #176]
   13b70:	29551d02 	ldp	w2, w7, [x8, #168]
   13b74:	910223e1 	add	x1, sp, #0x88
   13b78:	8b040910 	add	x16, x8, x4, lsl #2
   13b7c:	d37cec84 	lsl	x4, x4, #4
   13b80:	4f03f607 	fmov	v7.4s, #1.000000000000000000e+00
   13b84:	910243f5 	add	x21, sp, #0x90
   13b88:	4f000406 	movi	v6.4s, #0x0
   13b8c:	8b070900 	add	x0, x8, x7, lsl #2
   13b90:	bd405200 	ldr	s0, [x16, #80]
   13b94:	d37cece7 	lsl	x7, x7, #4
   13b98:	bd409608 	ldr	s8, [x16, #148]
   13b9c:	bd405005 	ldr	s5, [x0, #80]
   13ba0:	4e040400 	dup	v0.4s, v0.s[0]
   13ba4:	bd409415 	ldr	s21, [x0, #148]
   13ba8:	8b020900 	add	x0, x8, x2, lsl #2
   13bac:	d37cec42 	lsl	x2, x2, #4
   13bb0:	4e0404a5 	dup	v5.4s, v5.s[0]
   13bb4:	3ce768b1 	ldr	q17, [x5, x7]
   13bb8:	bd405014 	ldr	s20, [x0, #80]
   13bbc:	4ea5d605 	fsub	v5.4s, v16.4s, v5.4s
   13bc0:	bd40941c 	ldr	s28, [x0, #148]
   13bc4:	4ea0d610 	fsub	v16.4s, v16.4s, v0.4s
   13bc8:	b940b500 	ldr	w0, [x8, #180]
   13bcc:	4e040694 	dup	v20.4s, v20.s[0]
   13bd0:	bd407100 	ldr	s0, [x8, #112]
   13bd4:	3ce7693b 	ldr	q27, [x9, x7]
   13bd8:	8b000910 	add	x16, x8, x0, lsl #2
   13bdc:	4f9590a5 	fmul	v5.4s, v5.4s, v21.s[0]
   13be0:	d37cec00 	lsl	x0, x0, #4
   13be4:	4f889210 	fmul	v16.4s, v16.4s, v8.s[0]
   13be8:	bd40521f 	ldr	s31, [x16, #80]
   13bec:	3ce468a8 	ldr	q8, [x5, x4]
   13bf0:	4ea5f4e5 	fmin	v5.4s, v7.4s, v5.4s
   13bf4:	bd40961d 	ldr	s29, [x16, #148]
   13bf8:	4eb0f4f0 	fmin	v16.4s, v7.4s, v16.4s
   13bfc:	4eb4d673 	fsub	v19.4s, v19.4s, v20.4s
   13c00:	bd407514 	ldr	s20, [x8, #116]
   13c04:	4e0407ff 	dup	v31.4s, v31.s[0]
   13c08:	4e25f4c5 	fmax	v5.4s, v6.4s, v5.4s
   13c0c:	4e30f4d0 	fmax	v16.4s, v6.4s, v16.4s
   13c10:	3ce4693e 	ldr	q30, [x9, x4]
   13c14:	6e31dca5 	fmul	v5.4s, v5.4s, v17.4s
   13c18:	6e28de10 	fmul	v16.4s, v16.4s, v8.4s
   13c1c:	4f9c9273 	fmul	v19.4s, v19.4s, v28.s[0]
   13c20:	4ebfd652 	fsub	v18.4s, v18.4s, v31.4s
   13c24:	4ea5f765 	fmin	v5.4s, v27.4s, v5.4s
   13c28:	4eb0f7db 	fmin	v27.4s, v30.4s, v16.4s
   13c2c:	4eb3f4f3 	fmin	v19.4s, v7.4s, v19.4s
   13c30:	4f9d9250 	fmul	v16.4s, v18.4s, v29.s[0]
   13c34:	3ce268bd 	ldr	q29, [x5, x2]
   13c38:	2d50e518 	ldp	s24, s25, [x8, #132]
   13c3c:	4e3bd4b2 	fadd	v18.4s, v5.4s, v27.4s
   13c40:	4e33f4d3 	fmax	v19.4s, v6.4s, v19.4s
   13c44:	4f03f405 	fmov	v5.4s, #5.000000000000000000e-01
   13c48:	4eb0f4f0 	fmin	v16.4s, v7.4s, v16.4s
   13c4c:	3ce068a8 	ldr	q8, [x5, x0]
   13c50:	3ce2693c 	ldr	q28, [x9, x2]
   13c54:	6e25de52 	fmul	v18.4s, v18.4s, v5.4s
   13c58:	4e30f4d0 	fmax	v16.4s, v6.4s, v16.4s
   13c5c:	4e040739 	dup	v25.4s, v25.s[0]
   13c60:	6e3dde73 	fmul	v19.4s, v19.4s, v29.4s
   13c64:	3ce0693b 	ldr	q27, [x9, x0]
   13c68:	f00000e0 	adrp	x0, 32000 <typeinfo name for std::thread::_State_impl<std::thread::_Invoker<std::tuple<void (std::__future_base::_Async_state_impl<std::thread::_Invoker<std::tuple<Output::coefficients(void*, unsigned long, unsigned long, vc5_preview_coefficients const*)::{lambda(unsigned int)#1}, int> >, _codec_error>::*)(), std::__future_base::_Async_state_impl<std::thread::_Invoker<std::tuple<Output::coefficients(void*, unsigned long, unsigned long, vc5_preview_coefficients const*)::{lambda(unsigned int)#1}, int> >, _codec_error>*> > >+0x40>
   13c6c:	2d4c0517 	ldp	s23, s1, [x8, #96]
   13c70:	2d51c51a 	ldp	s26, s17, [x8, #140]
   13c74:	4eb9f652 	fmin	v18.4s, v18.4s, v25.4s
   13c78:	6e28de10 	fmul	v16.4s, v16.4s, v8.4s
   13c7c:	4e040718 	dup	v24.4s, v24.s[0]
   13c80:	4eb3f793 	fmin	v19.4s, v28.4s, v19.4s
   13c84:	4e04075a 	dup	v26.4s, v26.s[0]
   13c88:	4f819241 	fmul	v1.4s, v18.4s, v1.s[0]
   13c8c:	2d4d5915 	ldp	s21, s22, [x8, #104]
   13c90:	4eb8f673 	fmin	v19.4s, v19.4s, v24.4s
   13c94:	4eb0f778 	fmin	v24.4s, v27.4s, v16.4s
   13c98:	4f809240 	fmul	v0.4s, v18.4s, v0.s[0]
   13c9c:	3dc36010 	ldr	q16, [x0, #3456]
   13ca0:	aa0b03e0 	mov	x0, x11
   13ca4:	4f971261 	fmla	v1.4s, v19.4s, v23.s[0]
   13ca8:	aa0903eb 	mov	x11, x9
   13cac:	4ebaf717 	fmin	v23.4s, v24.4s, v26.4s
   13cb0:	aa0d03e9 	mov	x9, x13
   13cb4:	4f961260 	fmla	v0.4s, v19.4s, v22.s[0]
   13cb8:	aa0003ed 	mov	x13, x0
   13cbc:	4f9512e1 	fmla	v1.4s, v23.4s, v21.s[0]
   13cc0:	4f9412e0 	fmla	v0.4s, v23.4s, v20.s[0]
   13cc4:	4ea51cb4 	mov	v20.16b, v5.16b
   13cc8:	4ea1f4e1 	fmin	v1.4s, v7.4s, v1.4s
   13ccc:	4ea0f4e0 	fmin	v0.4s, v7.4s, v0.4s
   13cd0:	4e21f4c1 	fmax	v1.4s, v6.4s, v1.4s
   13cd4:	4e20f4c0 	fmax	v0.4s, v6.4s, v0.4s
   13cd8:	4f919021 	fmul	v1.4s, v1.4s, v17.s[0]
   13cdc:	4f919000 	fmul	v0.4s, v0.4s, v17.s[0]
   13ce0:	4ea1f4e1 	fmin	v1.4s, v7.4s, v1.4s
   13ce4:	4ea0f4e0 	fmin	v0.4s, v7.4s, v0.4s
   13ce8:	4e21f4c1 	fmax	v1.4s, v6.4s, v1.4s
   13cec:	4e20f4c0 	fmax	v0.4s, v6.4s, v0.4s
   13cf0:	4e30cc34 	fmla	v20.4s, v1.4s, v16.4s
   13cf4:	4ea51ca1 	mov	v1.16b, v5.16b
   13cf8:	6ea1ba94 	fcvtzu	v20.4s, v20.4s
   13cfc:	4e30cc01 	fmla	v1.4s, v0.4s, v16.4s
   13d00:	6ea1b820 	fcvtzu	v0.4s, v1.4s
   13d04:	ad0483f4 	stp	q20, q0, [sp, #144]
   13d08:	bd408101 	ldr	s1, [x8, #128]
   13d0c:	2d4f0108 	ldp	s8, s0, [x8, #120]
   13d10:	f9003fe5 	str	x5, [sp, #120]
   13d14:	aa0103e5 	mov	x5, x1
   13d18:	4f809240 	fmul	v0.4s, v18.4s, v0.s[0]
   13d1c:	4f881260 	fmla	v0.4s, v19.4s, v8.s[0]
   13d20:	4f8112e0 	fmla	v0.4s, v23.4s, v1.s[0]
   13d24:	4ea0f4e0 	fmin	v0.4s, v7.4s, v0.4s
   13d28:	4e20f4c0 	fmax	v0.4s, v6.4s, v0.4s
   13d2c:	4f919000 	fmul	v0.4s, v0.4s, v17.s[0]
   13d30:	4ea0f4e7 	fmin	v7.4s, v7.4s, v0.4s
   13d34:	4e27f4c6 	fmax	v6.4s, v6.4s, v7.4s
   13d38:	4e30ccc5 	fmla	v5.4s, v6.4s, v16.4s
   13d3c:	6ea1b8a0 	fcvtzu	v0.4s, v5.4s
   13d40:	3d802fe0 	str	q0, [sp, #176]
   13d44:	b94002b0 	ldr	w16, [x21]
   13d48:	b94012a0 	ldr	w0, [x21, #16]
   13d4c:	2a0e03e4 	mov	w4, w14
   13d50:	b94022a7 	ldr	w7, [x21, #32]
   13d54:	aa1703e2 	mov	x2, x23
   13d58:	aa1603e1 	mov	x1, x22
   13d5c:	910012b5 	add	x21, x21, #0x4
   13d60:	38706931 	ldrb	w17, [x9, x16]
   13d64:	38606930 	ldrb	w16, [x9, x0]
   13d68:	aa0803e0 	mov	x0, x8
   13d6c:	38676927 	ldrb	w7, [x9, x7]
   13d70:	390223f1 	strb	w17, [sp, #136]
   13d74:	390227f0 	strb	w16, [sp, #137]
   13d78:	39022be7 	strb	w7, [sp, #138]
   13d7c:	97fff9fd 	bl	12570 <(anonymous namespace)::display_pixel(gpr_preview_plan const*, unsigned char*, unsigned long, unsigned int, unsigned int, unsigned char const*)>
   13d80:	2a0a03e3 	mov	w3, w10
   13d84:	6b0a027f 	cmp	w19, w10
   13d88:	54000060 	b.eq	13d94 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x894>  // b.none
   13d8c:	1100054a 	add	w10, w10, #0x1
   13d90:	17ffffed 	b	13d44 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x844>
   13d94:	aa0d03e0 	mov	x0, x13
   13d98:	aa0903ed 	mov	x13, x9
   13d9c:	f9403fe5 	ldr	x5, [sp, #120]
   13da0:	aa0b03e9 	mov	x9, x11
   13da4:	aa0003eb 	mov	x11, x0
   13da8:	17fffed2 	b	138f0 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x3f0>
   13dac:	a94f0102 	ldp	x2, x0, [x8, #240]
   13db0:	eb00005f 	cmp	x2, x0
   13db4:	54000280 	b.eq	13e04 <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x904>  // b.none
   13db8:	b9402d00 	ldr	w0, [x8, #44]
   13dbc:	9b1c1c00 	madd	x0, x0, x28, x7
   13dc0:	8b001440 	add	x0, x2, x0, lsl #5
   13dc4:	4cdf0814 	ld4	{v20.4s-v23.4s}, [x0], #64
   13dc8:	4c400818 	ld4	{v24.4s-v27.4s}, [x0]
   13dcc:	4e981a85 	uzp1	v5.4s, v20.4s, v24.4s
   13dd0:	4e985a81 	uzp2	v1.4s, v20.4s, v24.4s
   13dd4:	4e991aa0 	uzp1	v0.4s, v21.4s, v25.4s
   13dd8:	4e995aa7 	uzp2	v7.4s, v21.4s, v25.4s
   13ddc:	4e9a1ac6 	uzp1	v6.4s, v22.4s, v26.4s
   13de0:	ad0000a5 	stp	q5, q0, [x5]
   13de4:	4e9a5ac5 	uzp2	v5.4s, v22.4s, v26.4s
   13de8:	ad001d21 	stp	q1, q7, [x9]
   13dec:	4e9b5ae0 	uzp2	v0.4s, v23.4s, v27.4s
   13df0:	3d8008a6 	str	q6, [x5, #32]
   13df4:	4e9b1ae1 	uzp1	v1.4s, v23.4s, v27.4s
   13df8:	ad010125 	stp	q5, q0, [x9, #32]
   13dfc:	3d800ca1 	str	q1, [x5, #48]
   13e00:	17ffff5b 	b	13b6c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x66c>
   13e04:	4f03f600 	fmov	v0.4s, #1.000000000000000000e+00
   13e08:	ad0000a0 	stp	q0, q0, [x5]
   13e0c:	ad000120 	stp	q0, q0, [x9]
   13e10:	ad0100a0 	stp	q0, q0, [x5, #32]
   13e14:	ad010120 	stp	q0, q0, [x9, #32]
   13e18:	17ffff55 	b	13b6c <(anonymous namespace)::display_wavelet_rows(gpr_preview_plan const*, gpr_rgb_buffer const*, unsigned char const*, unsigned char*, unsigned long, unsigned int, unsigned int)+0x66c>
