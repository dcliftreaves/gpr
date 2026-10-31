// Isolated production codec modes; no runtime changes or acceptance timing.
#include "vc5_encoder.h"
#include "vc5_decoder.h"
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <future>
#include <iterator>
#include <vector>
struct Arena {
 std::vector<unsigned char> bytes;size_t used=0,peak=0;
 explicit Arena(size_t n):bytes(n,0){}
 void *alloc(size_t n){if(n>SIZE_MAX-63)return nullptr;size_t count=(n+63)&~size_t(63);if(count>bytes.size()-used)return nullptr;void *p=bytes.data()+used;used+=count;if(used>peak)peak=used;return p;}
};
static thread_local Arena *current=nullptr;
static void *allocate(size_t n){return current?current->alloc(n):nullptr;}
static void release(void*){}
struct Context {
 std::array<Arena,3> scratch{{Arena(1024u*768u*16u+(1u<<20)),Arena(1024u*768u*16u+(1u<<20)),Arena(1024u*768u*16u+(1u<<20))}};
 gpr_rgb_buffer planes[3]={{}};int error[3]={};unsigned calls=0;double callback_s=0;volatile int sample=0;
 void reconstruct(unsigned channel,const vc5_preview_coefficients *view) {
  Arena *previous=current;current=&scratch[channel];scratch[channel].used=0;
  error[channel]=vc5_decoder_reconstruct_preview_channel(view,channel,allocate,release,&planes[channel]);current=previous;
 }
};
static void retain(void *user,const vc5_preview_coefficients *view) {
 Context *c=static_cast<Context*>(user);++c->calls;
 // Observe retained data without running reconstruction or scanning full planes.
 for(unsigned channel=0;channel<3;++channel)for(unsigned level=0;level<2;++level)
  for(unsigned band=level?0:1;band<4;++band)c->sample+=view->channels[channel][level].bands[band][0];
}
static void reconstruct(void *user,const vc5_preview_coefficients *view) {
 Context *c=static_cast<Context*>(user);++c->calls;
 auto start=std::chrono::steady_clock::now();
 try {auto a=std::async(std::launch::async,[&]{c->reconstruct(1,view);});auto b=std::async(std::launch::async,[&]{c->reconstruct(2,view);});c->reconstruct(0,view);a.get();b.get();}
 catch(...){c->error[0]=-1;}
 c->callback_s=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
}
static std::vector<unsigned char> read(const char *name) {std::ifstream f(name,std::ios::binary);return std::vector<unsigned char>((std::istreambuf_iterator<char>(f)),{});}
int main(int argc,char **argv) {
 if(argc!=3)return 2;auto raw=read(argv[1]),reference=read(argv[2]);
 if(raw.size()!=4096u*3072u*2u||reference.empty())return 3;
 std::array<std::vector<unsigned char>,3> expected;
 vc5_decoder_parameters dp;vc5_decoder_parameters_set_default(&dp);dp.mem_alloc=std::malloc;dp.mem_free=std::free;dp.rgb_bits=16;dp.rgb_resolution=GPR_RGB_RESOLUTION_QUARTER;
 gpr_buffer stock={reference.data(),reference.size()};
 for(unsigned channel=0;channel<3;++channel){gpr_rgb_buffer plane={};if(vc5_decoder_process_wavelet_channel(&dp,&stock,channel,&plane))return 4;expected[channel].assign(static_cast<unsigned char*>(plane.buffer),static_cast<unsigned char*>(plane.buffer)+plane.size);std::free(plane.buffer);}
 Arena encoder(192u<<20);Context context;
 vc5_encoder_parameters p;vc5_encoder_parameters_set_default(&p);p.input_width=4096;p.input_height=3072;p.input_pitch=8192;p.pixel_format=VC5_ENCODER_PIXEL_FORMAT_RGGB_14;p.quality_setting=VC5_ENCODER_QUALITY_SETTING_FS1;p.mem_alloc=allocate;p.mem_free=release;
 gpr_buffer input={raw.data(),raw.size()};
 const unsigned modes[12]={0,1,2,2,1,0,1,0,2,0,2,1};const char *names[3]={"none","retain","reconstruct"};
 for(unsigned block=0;block<12;++block)for(unsigned iteration=0;iteration<16;++iteration){
  unsigned mode=modes[block];encoder.used=0;current=&encoder;gpr_buffer output={};context.calls=0;context.callback_s=0;
  for(unsigned c=0;c<3;++c){context.planes[c]={};context.error[c]=0;}
  auto start=std::chrono::steady_clock::now();
  CODEC_ERROR error=vc5_encoder_process_with_preview(&p,&input,&output,nullptr,mode==0?nullptr:mode==1?retain:reconstruct,&context);
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  if(error||output.size!=reference.size()||std::memcmp(output.buffer,reference.data(),reference.size())||context.calls!=(mode?1u:0u))return 5;
  if(mode==2)for(unsigned c=0;c<3;++c)if(context.error[c]||context.planes[c].size!=expected[c].size()||std::memcmp(context.planes[c].buffer,expected[c].data(),expected[c].size()))return 6;
  std::printf("{\"event\":\"iteration\",\"block\":%u,\"mode\":\"%s\",\"iteration\":%u,\"warmup\":%s,\"wall_s\":%.9f,\"callback_s\":%.9f,\"encoder_used\":%zu,\"all_payloads_exact_independent_stock\":true,\"planes_exact_independent_decode\":%s}\n",block,names[mode],iteration,iteration==0?"true":"false",seconds,context.callback_s,encoder.used,mode==2?"true":"null");std::fflush(stdout);
 }
 return 0;
}
