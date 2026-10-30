                if (length <= 32) {
                    uint64_t bits01=((uint64_t)(uint32_t)c0<<n1)|(uint32_t)c1;
                    uint64_t bits23=((uint64_t)(uint32_t)c2<<n3)|(uint32_t)c3;
                    uint64_t bits=(bits01<<(n2+n3))|bits23;
                    accumulator=(accumulator<<length)|bits;
                    occupied+=length;
                    if (occupied>=32) {
                        occupied-=32;
                        write_bits(&stream_buffer,(uint32_t)(accumulator>>occupied));
                        stream_buffer+=4;
                    }
                } else if (length <= 64) {
                    uint64_t bits01=((uint64_t)(uint32_t)c0<<n1)|(uint32_t)c1;
                    uint64_t bits23=((uint64_t)(uint32_t)c2<<n3)|(uint32_t)c3;
                    uint64_t bits=(bits01<<(n2+n3))|bits23;
                    unsigned rest=occupied+length-32;
                    write_bits(&stream_buffer,(uint32_t)((accumulator<<(32-occupied))|(rest==64 ? UINT64_C(0):(bits>>rest))));
                    stream_buffer+=4;
                    if (rest>=32) {
                        rest-=32;
                        write_bits(&stream_buffer,(uint32_t)(bits>>rest));
                        stream_buffer+=4;
                    }
                    accumulator=bits;
                    occupied=rest;
                } else {
