#define _POSIX_C_SOURCE 200809L
#include "functions.inc"
static void die(const char *s){fprintf(stderr,"%s\n",s);exit(1);}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static uint8_t outputs[2][131072];
static unsigned encode(int kind,PIXEL *data,unsigned width,unsigned height,unsigned pitch,int incremental){
 STREAM byte_stream;BITSTREAM bits;
 if(CreateStreamBuffer(&byte_stream,outputs[kind],sizeof(outputs[kind]))||InitBitstream(&bits)||AttachBitstream(&bits,&byte_stream))die("stream");
 uint32_t pending=0;CODEC_ERROR error;
 if(incremental){
  for(unsigned y=0;y<height;y++){
   error=kind?pair_incremental(&bits,&encoder_codeset_17,data+y*pitch,width,1,pitch*2,&pending,false):baseline_incremental(&bits,&encoder_codeset_17,data+y*pitch,width,1,pitch*2,&pending,false);
   if(error)die("incremental encode");
  }
  error=kind?pair_incremental(&bits,&encoder_codeset_17,NULL,width,0,pitch*2,&pending,true):baseline_incremental(&bits,&encoder_codeset_17,NULL,width,0,pitch*2,&pending,true);
 }else error=kind?pair_incremental(&bits,&encoder_codeset_17,data,width,height,pitch*2,NULL,true):baseline_incremental(&bits,&encoder_codeset_17,data,width,height,pitch*2,NULL,true);
 if(error||FlushBitstream(&bits))die("encode");return byte_stream.byte_count;
}
int main(void){
 gpr_allocator allocator={malloc,free};if(PrepareCodebooks(&allocator,&encoder_codeset_17))die("codebook");
 uint64_t *codes=malloc((65536+256)*sizeof(uint64_t));if(!codes)die("malloc");
 memcpy(codes,encoder_codeset_17.signed_codes,65536*sizeof(uint64_t));free((void*)encoder_codeset_17.signed_codes);encoder_codeset_17.signed_codes=codes;
 for(unsigned key=0;key<256;key++){
  int a=key&15,b=key>>4;if(a&8)a-=16;if(b&8)b-=16;uint64_t c0=codes[(uint16_t)a],c1=codes[(uint16_t)b];
  unsigned n0=c0>>32,n1=c1>>32;codes[65536+key]=(n0+n1<=32)?((uint64_t)(n0+n1)<<32)|(uint32_t)(((uint64_t)(uint32_t)c0<<n1)|(uint32_t)c1):0;
 }
 PIXEL data[4096];unsigned checks=0;uint32_t random=1;
 for(unsigned width=1;width<=257;width++)for(unsigned pattern=0;pattern<5;pattern++){
  unsigned pitch=width+3,height=3;
  for(unsigned i=0;i<pitch*height;i++){
   random=random*1664525+1013904223;
   data[i]=pattern==0?0:pattern==1?(int)(random%16)-8:pattern==2?(i%23==22?7:0):pattern==3?(i%3==0?8:i%3==1?-9:0):(int16_t)(random>>16);
  }
  for(unsigned inc=0;inc<2;inc++){
   unsigned a=encode(0,data,width,height,pitch,inc),b=encode(1,data,width,height,pitch,inc);
   if(a!=b||memcmp(outputs[0],outputs[1],a))die("byte mismatch");checks++;
  }
 }
 /* Exhaust the four signed-nibble lanes' range check separately. */
 for(unsigned v=0;v<65536;v++)for(unsigned lane=0;lane<4;lane++){
  uint64_t p=(uint64_t)v<<(lane*16),s=p&UINT64_C(0x0008000800080008);
  int accepted=(p&UINT64_C(0xfff8fff8fff8fff8))==(s<<13)-s;
  int value=(int16_t)v;if(accepted!=(value>=-8&&value<=7))die("range test");
 }
 printf("{\"exact_stream_cases\":%u,\"range_cases\":262144,\"runs\":[",checks);
 int order[]={0,1,1,0,1,0,0,1};
 for(unsigned r=0;r<8;r++){
  unsigned kind=order[r];
  for(unsigned i=0;i<4096;i++){random=random*1664525+1013904223;data[i]=(int)(random%16)-8;}
  double start=now();unsigned long bytes=0;
  for(unsigned repeat=0;repeat<50000;repeat++){
   bytes+=encode(kind,data,1024,3,1027,1);
  }
  printf("%s{\"kind\":\"%s\",\"elapsed_s\":%.9f,\"streams\":50000,\"output_bytes\":%lu}",r?",":"",kind?"pair":"baseline",now()-start,bytes);fflush(stdout);
 }
 printf("]}\n");ReleaseCodebooks(&allocator,&encoder_codeset_17);return 0;
}
