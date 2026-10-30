/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_preview_queue.h"
#include "vc5_decoder.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <vector>
static void check(bool b,const char *m){if(!b)throw std::runtime_error(m);}
static std::vector<uint8_t> read(const char *p){std::ifstream f(p,std::ios::binary);check(bool(f),"input open");return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)),{});}
struct Sink {uint32_t expected,payload;uint64_t render_ns=0,index=0;
 static int display(void *u,const gpr_preview_frame_view *f){auto &s=*static_cast<Sink*>(u);if(gpr_gvid_crc32(0,f->rgb,f->size_bytes)!=s.expected||f->payload_crc32!=s.payload)return 1;s.render_ns=f->render_ns;s.index=f->index;return 0;}
};
int main(int argc,char **argv){try{
 check(argc==5,"usage: benchmark payload profile expected_rgb_crc iterations");auto bytes=read(argv[1]),profile=read(argv[2]);unsigned runs=unsigned(std::strtoul(argv[4],nullptr,10));check(runs>0&&runs<10000,"iterations");
 gpr_gvid_config video={4096,3072,20,1,3,14,{'R','G','G','B'}};gpr_preview_plan *p=nullptr;check(!gpr_preview_plan_from_profile(&video,profile.data(),profile.size(),&p),"profile parse");std::unique_ptr<gpr_preview_plan,decltype(&gpr_preview_plan_destroy)>plan(p,gpr_preview_plan_destroy);gpr_preview_info info={};check(!gpr_preview_plan_info(p,&info),"profile info");
 vc5_decoder_parameters decoder;vc5_decoder_parameters_set_default(&decoder);decoder.mem_alloc=std::malloc;decoder.mem_free=std::free;decoder.pixel_format=VC5_DECODER_PIXEL_FORMAT_RGGB_14;decoder.rgb_bits=16;decoder.rgb_resolution=GPR_RGB_RESOLUTION_QUARTER;
 gpr_buffer input={bytes.data(),bytes.size()};gpr_rgb_buffer decoded[3]={{}};
 struct FreePlanes {gpr_rgb_buffer *p;~FreePlanes(){for(unsigned c=0;c<3;++c)std::free(p[c].buffer);}} free_planes{decoded};
 gpr_preview_wavelet_planes planes={};
 for(unsigned c=0;c<3;++c){check(vc5_decoder_process_wavelet_channel(&decoder,&input,c,&decoded[c])==CODEC_ERROR_OKAY,"decode plane");planes.width=decoded[c].width;planes.height=decoded[c].height;planes.samples[c]=(int16_t*)decoded[c].buffer;planes.sample_count[c]=decoded[c].size/2;}
 Sink sink={uint32_t(std::strtoul(argv[3],nullptr,10)),gpr_gvid_crc32(0,bytes.data(),bytes.size())};gpr_preview_queue_config cfg={size_t(video.width)*video.height*3+1024*1024,info.row_bytes*info.height,Sink::display,&sink,1};gpr_preview_queue *q=nullptr;check(!gpr_preview_queue_create(&cfg,&q),"queue create");std::unique_ptr<gpr_preview_queue,decltype(&gpr_preview_queue_destroy)>queue(q,gpr_preview_queue_destroy);
 for(unsigned i=0;i<runs;++i){auto start=std::chrono::steady_clock::now();check(!gpr_preview_queue_offer_wavelets(q,p,i,i+1,&planes,sink.payload),"offer planes");check(!gpr_preview_queue_flush(q),"flush planes");auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();check(sink.index==i,"delivered index");std::printf("{\"iteration\":%u,\"render_ns\":%llu,\"cycle_ns\":%lld,\"rgb_crc32\":%u}\n",i,(unsigned long long)sink.render_ns,(long long)ns,sink.expected);}
 check(!gpr_preview_queue_finish(q),"finish");gpr_preview_queue_stats stats={};check(!gpr_preview_queue_get_stats(q,&stats)&&stats.rendered==runs&&!stats.discarded&&!stats.inflight&&stats.payload_peak_bytes<=2*cfg.max_payload_bytes,"final queue accounting");return 0;
}catch(const std::exception &e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
