/* Private handoff proof: same-process concurrent callers and capacity fallback. */
#include "vc5_encoder.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr,"handoff concurrent line %d: %s\n",__LINE__,#x); abort(); } } while(0)
#define CASES 49
static struct {
    vc5_encoder_parameters parameters;
    gpr_buffer input, expected;
} cases[CASES];
static void *run(void *argument) {
    unsigned worker=(unsigned)(uintptr_t)argument;
    for (unsigned repeat=0; repeat<4; ++repeat)
        for (unsigned i=worker;i<CASES;i+=4) {
            gpr_buffer result={0};
            REQUIRE(vc5_encoder_process(&cases[i].parameters,&cases[i].input,&result,NULL)==CODEC_ERROR_OKAY);
            REQUIRE(result.size==cases[i].expected.size && !memcmp(result.buffer,cases[i].expected.buffer,result.size));
            free(result.buffer);
        }
    return NULL;
}
int main(void) {
    const VC5_ENCODER_PIXEL_FORMAT formats[4][3]={
        {VC5_ENCODER_PIXEL_FORMAT_RGGB_12,VC5_ENCODER_PIXEL_FORMAT_RGGB_14,VC5_ENCODER_PIXEL_FORMAT_RGGB_16},
        {VC5_ENCODER_PIXEL_FORMAT_GBRG_12,VC5_ENCODER_PIXEL_FORMAT_GBRG_14,VC5_ENCODER_PIXEL_FORMAT_GBRG_16},
        {VC5_ENCODER_PIXEL_FORMAT_GRBG_12,VC5_ENCODER_PIXEL_FORMAT_GRBG_14,VC5_ENCODER_PIXEL_FORMAT_GRBG_16},
        {VC5_ENCODER_PIXEL_FORMAT_BGGR_12,VC5_ENCODER_PIXEL_FORMAT_BGGR_14,VC5_ENCODER_PIXEL_FORMAT_BGGR_16}};
    setenv("GPR_STREAM_UNPACK","1",1);setenv("GPR_BAND_STREAM","1",1);
    setenv("GPR_COMPACT_BANDS","1",1);setenv("GPR_DIRECT_BANDS","1",1);setenv("GPR_CHANNEL_ASM","1",1);
    unsetenv("GPR_ENTROPY_HANDOFF");unsetenv("GPR_HANDOFF_NO_THREADS");
    for (unsigned i=0;i<CASES;++i) {
        unsigned phase=(i/12)%4,depth=(i/4)%3,quality=i%2 ? 5:0;
        unsigned width=i==48 ? 32768 : i%4<2 ? 50:130;
        unsigned height=i==48 ? 48 : i%4<2 ? 50:98;
        vc5_encoder_parameters *p=&cases[i].parameters;vc5_encoder_parameters_set_default(p);
        p->input_width=width;p->input_height=height;p->input_pitch=width*2;p->pixel_format=formats[phase][depth];p->quality_setting=(VC5_ENCODER_QUALITY_SETTING)quality;
        cases[i].input.size=(size_t)width*height*2;cases[i].input.buffer=malloc(cases[i].input.size);REQUIRE(cases[i].input.buffer);
        uint16_t *raw=cases[i].input.buffer;uint32_t random=i+17;
        for (unsigned x=0;x<width*height;++x) {random=random*1664525u+1013904223u;raw[x]=(random>>16)&((1u<<(12+2*depth))-1);}
        REQUIRE(vc5_encoder_process(p,&cases[i].input,&cases[i].expected,NULL)==CODEC_ERROR_OKAY);
    }
    setenv("GPR_ENTROPY_HANDOFF","1",1);
    for (unsigned fallback=0;fallback<2;++fallback) {
        if (fallback) setenv("GPR_HANDOFF_NO_THREADS","1",1);
        pthread_t workers[4];
        for (unsigned i=0;i<4;++i) REQUIRE(!pthread_create(&workers[i],NULL,run,(void *)(uintptr_t)i));
        for (unsigned i=0;i<4;++i) REQUIRE(!pthread_join(workers[i],NULL));
    }
    for (unsigned i=0;i<CASES;++i) {free(cases[i].input.buffer);free(cases[i].expected.buffer);}
    puts("PASS: 49 disabled references, 392 exact enabled encodes across four simultaneous callers, helpers and no-created-thread fallback, including >1MiB ring capacity fallback");
    return 0;
}
