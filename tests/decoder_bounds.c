/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "vc5_decoder.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRE(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
static unsigned allocations;
static void *deny(size_t size) { (void)size; ++allocations; return NULL; }
static unsigned fail_at,live;
static void *count_alloc(size_t size) {
    void *p;
    ++allocations;if (allocations==fail_at) return NULL;
    p=malloc(size);if (p) ++live;return p;
}
static void count_free(void *p) { if (p) {REQUIRE(live);--live;free(p);} }
static unsigned char *fixture(const char *path,size_t *size) {
    FILE *f=fopen(path,"rb");unsigned char *data;long n;
    REQUIRE(f && !fseek(f,0,SEEK_END));n=ftell(f);REQUIRE(n>=64 && !fseek(f,0,SEEK_SET));
    data=(unsigned char *)malloc((size_t)n);REQUIRE(data && fread(data,1,(size_t)n,f)==(size_t)n && !fclose(f));
    *size=(size_t)n;return data;
}
static void rejected(vc5_decoder_parameters p,gpr_buffer source,gpr_buffer *raw,gpr_rgb_buffer *rgb) {
    p.mem_alloc=deny;allocations=0;
    REQUIRE(vc5_decoder_process(&p,&source,raw,rgb)!=CODEC_ERROR_OKAY);
    REQUIRE(!allocations);
    if (raw) REQUIRE(!raw->buffer && !raw->size);
    if (rgb) REQUIRE(!rgb->buffer && !rgb->size);
}
int main(int argc,char **argv) {
    size_t size;unsigned char *data;gpr_buffer source,raw={0};gpr_rgb_buffer rgb={0};
    vc5_decoder_parameters p,q;
    REQUIRE(argc==2);data=fixture(argv[1],&size);source.buffer=data;source.size=size;
    vc5_decoder_parameters_set_default(&p);p.mem_alloc=malloc;p.mem_free=free;
    REQUIRE(vc5_decoder_process(NULL,&source,&raw,NULL)==CODEC_ERROR_NULLPTR);
    REQUIRE(vc5_decoder_process(&p,NULL,&raw,NULL)==CODEC_ERROR_NULLPTR);
    REQUIRE(vc5_decoder_process(&p,&source,NULL,NULL)==CODEC_ERROR_NULLPTR);
    REQUIRE(vc5_decoder_process(&p,&source,&source,NULL)==CODEC_ERROR_BAD_ARGUMENT);
    REQUIRE(vc5_decoder_process(&p,&source,(gpr_buffer *)&p,NULL)==CODEC_ERROR_BAD_ARGUMENT);
    REQUIRE(vc5_decoder_process(&p,&source,NULL,(gpr_rgb_buffer *)&source)==CODEC_ERROR_BAD_ARGUMENT);
    REQUIRE(vc5_decoder_process(&p,&source,&raw,&rgb)==CODEC_ERROR_BAD_ARGUMENT);
    REQUIRE(!raw.buffer && !rgb.buffer);
    q=p;q.mem_alloc=NULL;REQUIRE(vc5_decoder_process(&q,&source,&raw,NULL)==CODEC_ERROR_BAD_ARGUMENT);
    q=p;q.mem_free=NULL;REQUIRE(vc5_decoder_process(&q,&source,&raw,NULL)==CODEC_ERROR_BAD_ARGUMENT);
    source.buffer=NULL;rejected(p,source,&raw,NULL);source.buffer=data;
    source.size=63;rejected(p,source,&raw,NULL);
    source.size=size-1;rejected(p,source,&raw,NULL);source.size=size;
    data[0]^=1;rejected(p,source,&raw,NULL);data[0]^=1;
    q=p;q.rgb_resolution=GPR_RGB_RESOLUTION_FULL;rejected(q,source,NULL,&rgb);
    q=p;q.rgb_resolution=GPR_RGB_RESOLUTION_NONE;rejected(q,source,NULL,&rgb);
    q=p;q.rgb_bits=7;rejected(q,source,NULL,&rgb);
    q=p;q.rgb_bits=8;q.rgb_gain.r_gain_num=0;rejected(q,source,NULL,&rgb);
    q=p;q.rgb_bits=8;q.rgb_gain.g_gain_num=1025;rejected(q,source,NULL,&rgb);
    q=p;q.rgb_bits=8;q.rgb_gain.b_gain_pow2_den=-1;rejected(q,source,NULL,&rgb);
    q=p;q.rgb_bits=8;q.rgb_gain.r_gain_pow2_den=17;rejected(q,source,NULL,&rgb);
    REQUIRE(vc5_decoder_process(&p,&source,&raw,NULL)==CODEC_ERROR_OKAY);
    REQUIRE(raw.buffer && raw.size==128*96*2);free(raw.buffer);raw.buffer=NULL;raw.size=0;
    p.rgb_bits=16;REQUIRE(vc5_decoder_process(&p,&source,NULL,&rgb)==CODEC_ERROR_OKAY);
    REQUIRE(rgb.buffer && rgb.size==32*24*6 && rgb.width==32 && rgb.height==24);
    free(rgb.buffer);rgb.buffer=NULL;rgb.size=0;
    q=p;q.mem_alloc=deny;allocations=0;
    REQUIRE(vc5_decoder_process(&q,&source,&raw,NULL)==CODEC_ERROR_OUTOFMEMORY);
    REQUIRE(allocations && !raw.buffer && !raw.size);
    q=p;q.mem_alloc=count_alloc;q.mem_free=count_free;fail_at=0;allocations=live=0;
    REQUIRE(vc5_decoder_process(&q,&source,&raw,NULL)==CODEC_ERROR_OKAY);
    REQUIRE(raw.buffer && live);count_free(raw.buffer);raw.buffer=NULL;raw.size=0;REQUIRE(!live);
    {
        unsigned total=allocations,index;
        for (index=1;index<=total;++index) {
            allocations=live=0;fail_at=index;
            REQUIRE(vc5_decoder_process(&q,&source,&raw,NULL)==CODEC_ERROR_OUTOFMEMORY);
            REQUIRE(!raw.buffer && !raw.size && !live);
        }
        fprintf(stdout,"RAW decoder allocation-failure positions: %u\n",total);
    }
    fail_at=0;allocations=live=0;
    REQUIRE(vc5_decoder_process(&q,&source,NULL,&rgb)==CODEC_ERROR_OKAY);
    REQUIRE(rgb.buffer && live);count_free(rgb.buffer);rgb.buffer=NULL;rgb.size=0;REQUIRE(!live);
    {
        unsigned total=allocations,index;
        for (index=1;index<=total;++index) {
            allocations=live=0;fail_at=index;
            REQUIRE(vc5_decoder_process(&q,&source,NULL,&rgb)==CODEC_ERROR_OUTOFMEMORY);
            REQUIRE(!rgb.buffer && !rgb.size && !live);
        }
        fprintf(stdout,"RGB decoder allocation-failure positions: %u\n",total);
    }
    free(data);
    puts("PASS: decoder argument boundary and stock RAW/RGB fixture");return 0;
}
