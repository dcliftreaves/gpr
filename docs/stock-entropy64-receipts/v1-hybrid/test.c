#define _POSIX_C_SOURCE 200809L
#include "functions.inc"
static void die(const char *s){fprintf(stderr,"%s\n",s);exit(1);}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
#define CAPACITY 32768
static uint8_t outputs[2][CAPACITY+32];
static unsigned encode(int kind,PIXEL *data,unsigned width,unsigned height,unsigned pitch,int incremental,unsigned prefix){
 STREAM byte_stream;BITSTREAM bits;memset(outputs[kind],0xa5,sizeof(outputs[kind]));
 if(CreateStreamBuffer(&byte_stream,outputs[kind]+16,CAPACITY)||InitBitstream(&bits)||AttachBitstream(&bits,&byte_stream))die("stream");
 bits.count=prefix;bits.buffer=prefix?(UINT32_C(0xfedcba98)<<(32-prefix)):0;
 uint32_t pending=0;CODEC_ERROR error;
 if(incremental){
  for(unsigned y=0;y<height;y++){
   error=kind?candidate_incremental(&bits,&encoder_codeset_17,data+y*pitch,width,1,pitch*2,&pending,false):baseline_incremental(&bits,&encoder_codeset_17,data+y*pitch,width,1,pitch*2,&pending,false);
   if(error)die("incremental encode");
  }
  error=kind?candidate_incremental(&bits,&encoder_codeset_17,NULL,width,0,pitch*2,&pending,true):baseline_incremental(&bits,&encoder_codeset_17,NULL,width,0,pitch*2,&pending,true);
 }else error=kind?candidate_incremental(&bits,&encoder_codeset_17,data,width,height,pitch*2,NULL,true):baseline_incremental(&bits,&encoder_codeset_17,data,width,height,pitch*2,NULL,true);
 if(error||FlushBitstream(&bits)||byte_stream.byte_count>CAPACITY)die("encode");
 for(unsigned i=0;i<16;i++)if(outputs[kind][i]!=0xa5||outputs[kind][CAPACITY+16+i]!=0xa5)die("output canary");
 return byte_stream.byte_count;
}
static uint32_t random_state=1;
static uint32_t rnd(void){random_state=random_state*1664525u+1013904223u;return random_state;}
static uint64_t mask(unsigned n){return n==64?UINT64_MAX:n?((UINT64_C(1)<<n)-1):0;}
static unsigned reservoir_oracle(void){
 unsigned checks=0;
 for(unsigned occupied=0;occupied<32;occupied++)for(unsigned length=1;length<=64;length++)for(unsigned repeat=0;repeat<257;repeat++){
  uint64_t accumulator=((uint64_t)rnd()<<32)|rnd(),bits=(((uint64_t)rnd()<<32)|rnd())&mask(length);
  unsigned total=occupied+length,remaining=total,count=0;uint32_t actual[2]={0,0},expected[2]={0,0};uint64_t residual;
  if(total>=32){unsigned rest=total-32;actual[count++]=(uint32_t)((accumulator<<(32-occupied))|(bits>>rest));if(rest>=32){rest-=32;actual[count++]=(uint32_t)(bits>>rest);}remaining=rest;residual=bits;}
  else {residual=(accumulator<<length)|bits;remaining=total;}
  __uint128_t reference=((__uint128_t)(accumulator&mask(occupied))<<length)|bits;unsigned ref_remaining=total,ref_count=0;
  while(ref_remaining>=32){ref_remaining-=32;expected[ref_count++]=(uint32_t)(reference>>ref_remaining);}
  if(count!=ref_count||remaining!=ref_remaining||memcmp(actual,expected,sizeof(actual))||(residual&mask(remaining))!=(uint64_t)(reference&mask(ref_remaining)))die("128-bit reservoir oracle mismatch");checks++;
 }
 return checks;
}
static void fill(PIXEL *data,unsigned count,unsigned pattern,unsigned seed){
 random_state=seed;
 for(unsigned i=0;i<count;i++){
  uint32_t r=rnd();
  data[i]=pattern==0?0:pattern==1?(int)(r%16)-8:pattern==2?(i%23==22?7:0):pattern==3?(int)(r%128)-64:pattern==4?(int)(r%2048)-1024:pattern==5?(i%3==0?INT16_MIN:i%3==1?INT16_MAX:0):(int16_t)(r>>16);
 }
}
int main(int argc,char **argv){
 gpr_allocator allocator={malloc,free};if(PrepareCodebooks(&allocator,&encoder_codeset_17))die("codebook");
 for(unsigned i=0;i<65536;i++){unsigned n=encoder_codeset_17.signed_codes[i]>>32;if(n<1||n>32)die("code length outside proof contract");}
 unsigned states=reservoir_oracle();PIXEL data[4096];unsigned checks=0;
 for(unsigned width=1;width<=257;width++)for(unsigned pattern=0;pattern<7;pattern++){
  unsigned pitch=width+3,height=3;fill(data,pitch*height,pattern,17+width+pattern);
  for(unsigned inc=0;inc<2;inc++)for(unsigned prefix=0;prefix<32;prefix++){
   unsigned a=encode(0,data,width,height,pitch,inc,prefix),b=encode(1,data,width,height,pitch,inc,prefix);
   if(a!=b||memcmp(outputs[0]+16,outputs[1]+16,a))die("byte mismatch");checks++;
  }
 }
 printf("{\"reservoir_states\":%u,\"exact_stream_cases\":%u,\"canaries_passed\":true,\"runs\":[",states,checks);fflush(stdout);
 if(argc==2&&!strcmp(argv[1],"--bench")){
  int order[]={0,1,1,0,1,0,0,1};unsigned patterns[]={1,3,4,6};
  for(unsigned pattern=0;pattern<4;pattern++)for(unsigned run=0;run<8;run++){
   unsigned kind=order[run];fill(data,4096,patterns[pattern],101+patterns[pattern]);
   double start=now();unsigned long bytes=0;
   for(unsigned repeat=0;repeat<10000;repeat++)bytes+=encode(kind,data,1024,3,1027,1,repeat%32);
   printf("%s{\"pattern\":%u,\"kind\":\"%s\",\"elapsed_s\":%.9f,\"streams\":10000,\"output_bytes\":%lu}",pattern||run?",":"",patterns[pattern],kind?"candidate":"baseline",now()-start,bytes);fflush(stdout);
  }
 }
 printf("]}\n");ReleaseCodebooks(&allocator,&encoder_codeset_17);return 0;
}
