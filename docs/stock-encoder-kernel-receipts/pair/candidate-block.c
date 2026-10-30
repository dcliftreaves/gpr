                /* Exact signed-nibble range test for all four lanes. */
                uint64_t packed;memcpy(&packed,rowptr+index,sizeof(packed));
                uint64_t sign=packed & UINT64_C(0x0008000800080008);
                if ((packed & UINT64_C(0xfff8fff8fff8fff8)) == (sign<<13)-sign) {
                    unsigned a=(packed&15)|((packed>>12)&240);
                    unsigned b=((packed>>32)&15)|((packed>>44)&240);
                    uint64_t p0=codeset->signed_codes[65536+a],p1=codeset->signed_codes[65536+b];
                    unsigned n0=p0>>32,n1=p1>>32,length=n0+n1;
                    if (n0 && n1 && length<=32) {
                        uint64_t bits=((uint64_t)(uint32_t)p0<<n1)|(uint32_t)p1;
                        accumulator=(accumulator<<length)|bits;occupied+=length;
                        if (occupied>=32) {occupied-=32;write_bits(&stream_buffer,(uint32_t)(accumulator>>occupied));stream_buffer+=4;}
                        index+=4;if (index==width) break;continue;
                    }
                }
