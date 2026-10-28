/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_preview.h"
#include "gpr_gvid_reader.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
static void check(bool value,const char *why) { if (!value) throw std::runtime_error(why); }
static std::vector<uint8_t> file(const std::string &path) {
    std::ifstream in(path,std::ios::binary|std::ios::ate); check(bool(in),"fixture missing");
    std::vector<uint8_t> out(size_t(in.tellg())); in.seekg(0);
    check(bool(in.read(reinterpret_cast<char *>(out.data()),out.size())),"fixture read"); return out;
}
struct Memory {
    const std::vector<uint8_t> &data;
    size_t pos=0,chunk=13,fail=SIZE_MAX;
    explicit Memory(const std::vector<uint8_t> &d) : data(d) {}
    static ptrdiff_t read(void *user,uint8_t *out,size_t n) {
        auto &m=*static_cast<Memory *>(user);
        if (m.pos>=m.fail) return -1;
        size_t bytes=std::min({n,m.chunk,m.data.size()-m.pos,m.fail-m.pos});
        if (bytes) std::memcpy(out,m.data.data()+m.pos,bytes);
        m.pos+=bytes; return ptrdiff_t(bytes);
    }
};
static int parse(Memory &input,unsigned *count=nullptr) {
    gpr_gvid_reader *r=nullptr;
    int error=gpr_gvid_reader_create(Memory::read,&input,0,&r);
    if (error) return error;
    unsigned frames=0; gpr_gvid_frame_view frame={};
    while ((error=gpr_gvid_reader_next(r,&frame))==GPR_GVID_FRAME) {
        check(frame.index==frames,"reader index"); ++frames;
    }
    if (error==GPR_GVID_DONE) check(gpr_gvid_reader_end_verified(r)==1,"reader finalization");
    check(gpr_gvid_reader_next(r,&frame)==error,"reader error not sticky");
    gpr_gvid_reader_close(r); if (count) *count=frames; return error;
}
static void reader_tests(const std::string &root) {
    auto data=file(root+"/container-v3.gvid");
    for (size_t chunk:{size_t(1),size_t(7),size_t(13),size_t(4096)}) {
        Memory in(data); in.chunk=chunk; unsigned frames=0;
        check(parse(in,&frames)==GPR_GVID_DONE && frames==2,"independent container fixture");
    }
    for (size_t i=0;i<data.size();++i) {
        std::vector<uint8_t> truncated(data.begin(),data.begin()+i); Memory in(truncated);
        check(parse(in)<0,"truncated recording accepted");
        auto corrupt=data; corrupt[i]^=1; Memory bad(corrupt);
        check(parse(bad)<0,"corrupt recording accepted");
    }
    for (size_t i:{size_t(0),size_t(40),size_t(85),data.size()}) {
        Memory in(data); in.fail=i; check(parse(in)==GPR_GVID_IO,"I/O failure hidden");
    }
    auto trailing=data; trailing.push_back(0); Memory in(trailing); check(parse(in)<0,"trailing bytes accepted");
    gpr_gvid_reader *reader=nullptr; Memory capped(data);
    check(!gpr_gvid_reader_create(Memory::read,&capped,4,&reader),"limit create");
    gpr_gvid_frame_view out={}; check(gpr_gvid_reader_next(reader,&out)==GPR_GVID_LIMIT,"payload limit ignored");
    gpr_gvid_reader_close(reader);
}
static void render(const std::string &root,unsigned width,unsigned scale,bool unaligned) {
    std::string name=std::to_string(width)+"x96-q3";
    auto payload=file(root+"/"+name+".vc5"),expected=file(root+"/"+name+"-s"+std::to_string(scale)+".rgb");
    std::vector<uint8_t> scratch;
    const uint8_t *source=payload.data();
    if (unaligned) { scratch.resize(payload.size()+1); std::copy(payload.begin(),payload.end(),scratch.begin()+1); source=scratch.data()+1; }
    gpr_gvid_config cfg={width,96,30,1,3,14,{'R','G','G','B'}};
    gpr_preview_options options={}; gpr_preview_options_default(&options); options.downsample=scale;
    gpr_preview_info info={}; check(!gpr_preview_dimensions(&cfg,&options,&info),"dimensions");
    check(info.width==(width+scale-1)/scale && info.height==(96+scale-1)/scale,"full-frame dimensions");
    check(expected.size()==info.row_bytes*info.height,"reference dimensions");
    size_t pitch=info.row_bytes+11,needed=(info.height-1)*pitch+info.row_bytes;
    std::vector<uint8_t> rgb(pitch*info.height+32,0xcd);
    check(gpr_preview_render(&cfg,&options,source,payload.size(),rgb.data()+16,needed-1,pitch,&info)==GPR_PREVIEW_CAPACITY,"small output accepted");
    check(std::all_of(rgb.begin(),rgb.end(),[](uint8_t p){ return p==0xcd; }),"error modified output");
    check(!gpr_preview_render(&cfg,&options,source,payload.size(),rgb.data()+16,needed,pitch,&info),"render failed");
    for (size_t y=0;y<info.height;++y) {
        check(!std::memcmp(rgb.data()+16+y*pitch,expected.data()+y*info.row_bytes,info.row_bytes),"preview differs from independent stock RGB");
        for (size_t x=info.row_bytes;x<pitch;++x) check(rgb[16+y*pitch+x]==0xcd,"display padding overwritten");
    }
    for (size_t i=0;i<16;++i) check(rgb[i]==0xcd && rgb[rgb.size()-1-i]==0xcd,"display canary overwritten");
    // Reject bad geometry/profile before invoking the historical decoder.
    cfg.width+=8;
    std::vector<uint8_t> large(1024*1024,0xcd);
    check(gpr_preview_render(&cfg,&options,source,payload.size(),large.data(),large.size(),4096,&info)==GPR_PREVIEW_PAYLOAD,"wrong payload geometry accepted");
}
static void invalid_preview(const std::string &root) {
    auto payload=file(root+"/128x96-q3.vc5");
    gpr_gvid_config cfg={128,96,30,1,3,14,{'R','G','G','B'}};
    gpr_preview_options options={}; gpr_preview_options_default(&options); gpr_preview_info info={};
    std::vector<uint8_t> rgb(32*24*3,0xcd);
    for (size_t n=0;n<payload.size();++n)
        check(gpr_preview_render(&cfg,&options,payload.data(),n,rgb.data(),rgb.size(),96,&info)==GPR_PREVIEW_PAYLOAD,"truncated VC5 accepted");
    auto bad=payload; bad[11]^=1;
    check(gpr_preview_render(&cfg,&options,bad.data(),bad.size(),rgb.data(),rgb.size(),96,&info)==GPR_PREVIEW_PAYLOAD,"changed VC5 width accepted");
    options.gain_pow2_den[0]=32;
    check(gpr_preview_dimensions(&cfg,&options,&info)==GPR_PREVIEW_INVALID,"unsafe gain shift accepted");
    check(std::all_of(rgb.begin(),rgb.end(),[](uint8_t p){ return p==0xcd; }),"invalid input modified RGB");
}
int main(int argc,char **argv) {
    try {
        check(argc==2,"fixture directory required"); std::string root=argv[1]; reader_tests(root);
        // Begin concurrent renders cold, exercising curve/prefix initialization.
        bool okay[2]={true,true}; std::thread threads[2];
        for (unsigned i=0;i<2;++i) threads[i]=std::thread([&,i]{ try { render(root,128,4,i!=0); } catch (...) { okay[i]=false; } });
        for (auto &t:threads) t.join(); check(okay[0] && okay[1],"concurrent render");
        for (unsigned width:{128u,72u}) for (unsigned scale:{4u,8u,16u}) for (bool unaligned:{false,true}) render(root,width,scale,unaligned);
        invalid_preview(root);
        std::cout<<"PASS: independent stock RGB, full-frame reductions, pitched display, unaligned input, concurrent render, bounded native reader and corruption/EOF rejection\n";
        return 0;
    } catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
