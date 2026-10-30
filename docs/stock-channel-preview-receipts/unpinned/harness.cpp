// Isolated whole-encode + exact three-plane reconstruction comparison.
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
#include <stdexcept>
#include <vector>
struct Arena {
 std::vector<unsigned char> storage; size_t used=0,peak=0;
 explicit Arena(size_t n):storage(n,0){}
 void *alloc(size_t n){if(n>SIZE_MAX-63)return nullptr;size_t count=(n+63)&~size_t(63);if(count>storage.size()-used)return nullptr;void*p=storage.data()+used;used+=count;if(used>peak)peak=used;return p;}
};
thread_local Arena *current=nullptr;
static void *allocate(size_t n){return current?current->alloc(n):nullptr;}
static void release(void*){}
struct Context {
 std::array<Arena,3> scratch{{Arena(16u<<20),Arena(16u<<20),Arena(16u<<20)}};
 gpr_rgb_buffer planes[3]={{}}; int errors[3]={0,0,0}; unsigned calls[3]={0,0,0};double channel_s[3]={0,0,0};
 void reconstruct(unsigned c,const vc5_preview_coefficients *view) noexcept {
  auto *previous=current;current=&scratch[c];scratch[c].used=0;
  auto start=std::chrono::steady_clock::now();
  errors[c]=vc5_decoder_reconstruct_preview_channel(view,c,allocate,release,&planes[c]);
  channel_s[c]=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();++calls[c];current=previous;
 }
};
static void each(void *u,unsigned c,const vc5_preview_coefficients *v){static_cast<Context*>(u)->reconstruct(c,v);}
static void all(void *u,const vc5_preview_coefficients *v){
 auto *c=static_cast<Context*>(u);
 try {auto a=std::async(std::launch::async,[&]{c->reconstruct(1,v);});auto b=std::async(std::launch::async,[&]{c->reconstruct(2,v);});c->reconstruct(0,v);a.get();b.get();}
 catch(...){c->errors[0]=-1;}
}
int main(int argc,char **argv){
 if(argc!=4){std::fprintf(stderr,"usage: harness raw baseline|channel iterations\n");return 2;}
 std::ifstream file(argv[1],std::ios::binary);std::vector<unsigned char>raw((std::istreambuf_iterator<char>(file)),{});
 if(raw.size()!=4096u*3072u*2u)return 3;
 bool early=!std::strcmp(argv[2],"channel");if(!early&&std::strcmp(argv[2],"baseline"))return 4;
 int runs=std::atoi(argv[3]);if(runs<1||runs>1000)return 5;
 Arena encoder(256u<<20);Context context;
 vc5_encoder_parameters p;vc5_encoder_parameters_set_default(&p);p.input_width=4096;p.input_height=3072;p.input_pitch=8192;p.pixel_format=VC5_ENCODER_PIXEL_FORMAT_RGGB_14;p.quality_setting=VC5_ENCODER_QUALITY_SETTING_FS1;p.mem_alloc=allocate;p.mem_free=release;
 gpr_buffer input={raw.data(),raw.size()};
 std::vector<unsigned char>payload_ref;std::array<std::vector<unsigned char>,3>plane_ref;
 for(int i=0;i<runs;++i){
  encoder.used=0;current=&encoder;gpr_buffer output={};
  for(unsigned c=0;c<3;++c){context.planes[c]={};context.errors[c]=0;context.calls[c]=0;}
  auto start=std::chrono::steady_clock::now();
  auto error=early?vc5_encoder_process_with_channel_preview(&p,&input,&output,nullptr,each,&context):vc5_encoder_process_with_preview(&p,&input,&output,nullptr,all,&context);
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  if(error||!output.buffer||!output.size)return 6;
  for(unsigned c=0;c<3;++c)if(context.errors[c]||context.calls[c]!=1||context.planes[c].width!=1024||context.planes[c].height!=768)return 7;
  if(i==0){payload_ref.assign((unsigned char*)output.buffer,(unsigned char*)output.buffer+output.size);for(unsigned c=0;c<3;++c)plane_ref[c].assign((unsigned char*)context.planes[c].buffer,(unsigned char*)context.planes[c].buffer+context.planes[c].size);}
  else {if(payload_ref.size()!=output.size||std::memcmp(payload_ref.data(),output.buffer,output.size))return 8;for(unsigned c=0;c<3;++c)if(plane_ref[c].size()!=context.planes[c].size||std::memcmp(plane_ref[c].data(),context.planes[c].buffer,context.planes[c].size))return 9;}
  std::printf("{\"iteration\":%d,\"wall_s\":%.9f,\"channel_s\":[%.9f,%.9f,%.9f],\"encoder_peak\":%zu,\"preview_peak\":[%zu,%zu,%zu]}\n",i,seconds,context.channel_s[0],context.channel_s[1],context.channel_s[2],encoder.peak,context.scratch[0].peak,context.scratch[1].peak,context.scratch[2].peak);std::fflush(stdout);
 }
 // Explicit sidecars let the parent independently compare both modes.
 std::ofstream payload(std::string(argv[2])+".vc5",std::ios::binary);payload.write((char*)payload_ref.data(),payload_ref.size());
 for(unsigned c=0;c<3;++c){std::ofstream plane(std::string(argv[2])+"-"+std::to_string(c)+".plane",std::ios::binary);plane.write((char*)plane_ref[c].data(),plane_ref[c].size());}
 return 0;
}
