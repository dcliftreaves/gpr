/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_preview_queue.h"
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <future>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>
static void check(bool b,const char *why){if(!b)throw std::runtime_error(why);}
struct Sink {
 std::mutex mutex;std::condition_variable changed;bool entered=false,allowed=false;
 std::vector<uint32_t> pixels,payloads;
 static int display(void *u,const gpr_preview_frame_view *v){
  auto &s=*static_cast<Sink*>(u);std::unique_lock<std::mutex> lock(s.mutex);
  s.pixels.push_back(gpr_gvid_crc32(0,v->rgb,v->size_bytes));s.payloads.push_back(v->payload_crc32);s.entered=true;s.changed.notify_all();
  s.changed.wait(lock,[&]{return s.allowed;});return 0;
 }
 void wait(){std::unique_lock<std::mutex> lock(mutex);check(changed.wait_for(lock,std::chrono::seconds(5),[&]{return entered;}),"sink entry timeout");}
 void unblock(){std::lock_guard<std::mutex>lock(mutex);allowed=true;changed.notify_all();}
};
using Plan=std::unique_ptr<gpr_preview_plan,decltype(&gpr_preview_plan_destroy)>;
using Queue=std::unique_ptr<gpr_preview_queue,decltype(&gpr_preview_queue_destroy)>;
static void run(unsigned width,unsigned height,size_t spare,bool cancel){
 gpr_gvid_config config={width,height,20,1,3,14,{'R','G','G','B'}};gpr_preview_calibration calibration={};gpr_preview_calibration_identity(&config,&calibration);if(width==56||width==136)calibration.crop[2]=float(width-6);
 gpr_preview_plan *created=nullptr;check(!gpr_preview_plan_create(&config,&calibration,&created),"plan creation");Plan plan(created,gpr_preview_plan_destroy);gpr_preview_info info={};check(!gpr_preview_plan_info(plan.get(),&info),"plan info");
 size_t count=size_t((width+3)/4)*((height+3)/4),bytes=count*6;std::vector<int16_t> samples[3];gpr_preview_wavelet_planes planes={};planes.width=(width+3)/4;planes.height=(height+3)/4;
 for(unsigned c=0;c<3;++c){samples[c].resize(count);planes.samples[c]=samples[c].data();planes.sample_count[c]=count;}
 auto fill=[&](unsigned seed){for(size_t i=0;i<count;++i){samples[0][i]=int16_t(2048+(i+seed*17)%8000);samples[1][i]=int16_t(8192+int((i*3+seed)%500)-250);samples[2][i]=int16_t(8192+int((i*7+seed*11)%700)-350);}};
 std::vector<uint8_t> rgb(info.row_bytes*info.height);auto expected=[&]{gpr_preview_info result={};check(!gpr_preview_plan_render_wavelets(plan.get(),&planes,rgb.data(),rgb.size(),info.row_bytes,&result),"independent direct render");return gpr_gvid_crc32(0,rgb.data(),rgb.size());};
 Sink sink;gpr_preview_queue_config qc={bytes+spare,rgb.size(),Sink::display,&sink};gpr_preview_queue *q=nullptr;check(!gpr_preview_queue_create(&qc,&q),"queue creation");Queue queue(q,gpr_preview_queue_destroy);
 // Always unblock before destruction, including assertion/error exits.
 struct Unblock {Sink &sink;~Unblock(){sink.unblock();}} unblock{sink};
 auto bad=planes;--bad.sample_count[2];check(gpr_preview_queue_offer_wavelets(q,plan.get(),0,100,&bad,11)==GPR_PREVIEW_INVALID,"short plane acceptance");
 fill(1);uint32_t first=expected();check(!gpr_preview_queue_offer_wavelets(q,plan.get(),0,100,&planes,11),"first offer");sink.wait();
 fill(2);uint32_t second=expected();check(!gpr_preview_queue_offer_wavelets(q,plan.get(),1,101,&planes,22),"pending offer");
 for(auto &v:samples){std::fill(v.begin(),v.end(),-123);v.clear();v.shrink_to_fit();}
 gpr_preview_queue_stats stats={};check(!gpr_preview_queue_get_stats(q,&stats),"stats");check(stats.offered==2&&stats.inflight==2&&stats.payload_peak_bytes<=2*qc.max_payload_bytes,"payload memory bound");
 if(cancel)gpr_preview_queue_cancel(q);sink.unblock();check(!gpr_preview_queue_finish(q),"finish");check(!gpr_preview_queue_get_stats(q,&stats),"final stats");check(!stats.inflight&&!stats.error,"final ownership");
 if(cancel){check(sink.pixels==std::vector<uint32_t>{first}&&stats.discarded==1,"cancel pending wavelet");}
 else {check(sink.pixels==std::vector<uint32_t>({first,second}),"copied plane pixels");check(sink.payloads==std::vector<uint32_t>({11,22})&&stats.rendered==2,"frame CRC binding");}
}
int main(){try{
 for(auto size: {48u,56u,128u,136u})for(size_t spare:{size_t(0),size_t(255),size_t(256),size_t(510),size_t(512)})run(size,size==136?104:size,spare,false);
 run(56,56,512,true);run(128,96,512,true);
 std::cout<<"PASS: copied wavelet planes, independent RGB/count/CRC bindings, cropped tails and unaligned packed rows, tight/spare bounds, pending ownership and cancellation\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
