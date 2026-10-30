/* Private standalone benchmark; every output is compared to independent bytes. */
#define _POSIX_C_SOURCE 200809L
#include "vc5_encoder.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr,"handoff benchmark line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static double now(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
int main(int argc,char **argv) {
    REQUIRE(argc==5);unsigned repeats=(unsigned)atoi(argv[4]);REQUIRE(repeats>0 && repeats<=1000);
    FILE *f=fopen(argv[1],"rb");REQUIRE(f);size_t rawsize=4096ul*3072*2;uint16_t *raw=malloc(rawsize);REQUIRE(raw && fread(raw,1,rawsize,f)==rawsize && fgetc(f)==EOF);REQUIRE(!fclose(f));
    f=fopen(argv[2],"rb");REQUIRE(f && !fseek(f,0,SEEK_END));long bytes=ftell(f);REQUIRE(bytes>0 && !fseek(f,0,SEEK_SET));uint8_t *reference=malloc((size_t)bytes);REQUIRE(reference && fread(reference,1,bytes,f)==(size_t)bytes);REQUIRE(!fclose(f));
    setenv("GPR_STREAM_UNPACK","1",1);setenv("GPR_BAND_STREAM","1",1);setenv("GPR_COMPACT_BANDS","1",1);setenv("GPR_DIRECT_BANDS","1",1);setenv("GPR_CHANNEL_ASM","1",1);setenv("GPR_PIN_CHANNELS","1",1);
    if (atoi(argv[3])) setenv("GPR_ENTROPY_HANDOFF","1",1);else unsetenv("GPR_ENTROPY_HANDOFF");
    vc5_encoder_parameters p;vc5_encoder_parameters_set_default(&p);p.input_width=4096;p.input_height=3072;p.input_pitch=4096*2;p.pixel_format=VC5_ENCODER_PIXEL_FORMAT_RGGB_14;p.quality_setting=(VC5_ENCODER_QUALITY_SETTING)3;
    gpr_buffer input={raw,rawsize};
    for (unsigned i=0;i<repeats;++i) {
        gpr_buffer output={0};double begin=now();CODEC_ERROR error=vc5_encoder_process(&p,&input,&output,NULL);double end=now();
        REQUIRE(error==CODEC_ERROR_OKAY && output.size==(size_t)bytes && !memcmp(output.buffer,reference,output.size));
        printf("{\"index\":%u,\"encode_ms\":%.9f,\"payload_exact\":true,\"payload_bytes\":%zu}\n",i,(end-begin)*1000,output.size);free(output.buffer);
    }
    free(raw);free(reference);return 0;
}
