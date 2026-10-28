/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_preview.h"
#include "vc5_decoder.h"
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>

namespace {
unsigned be16(const uint8_t *p) { return unsigned(p[0])*256+p[1]; }
bool stock_payload(const gpr_gvid_config &v,const uint8_t *p,size_t size) {
    if (!p || size<64 || size%4 || size>size_t(v.width)*v.height*3+1024*1024 || std::memcmp(p,"VC-5",4)) return false;
    size_t offset=4,ends[16]; unsigned depth=0,mask=0,channel=0,band=0,precision=16,count[4]={};
    while (offset<size) {
        while (depth && offset==ends[depth-1]) --depth;
        size_t end=depth ? ends[depth-1]:size;
        if (offset>end || end-offset<4) return false;
        unsigned word=be16(p+offset),value=be16(p+offset+2);
        int signed_tag=word<32768 ? int(word):int(word)-65536;
        unsigned tag=unsigned(signed_tag<0 ? -signed_tag:signed_tag); offset+=4;
        if (tag&0x6000) {
            size_t words=value+((tag&0x2000) ? size_t(tag&255)<<16:0);
            if (words>(end-offset)/4) return false;
            size_t next=offset+words*4;
            unsigned kind=tag&0xff00;
            if (kind==0x6000) {
                if (mask!=255 || band!=count[channel] || band>=10 || !words) return false;
                if (!band) {
                    size_t bits=size_t((v.width+15)/16)*((v.height+15)/16)*precision;
                    if (words!=(bits+31)/32) return false;
                }
                ++count[channel]; ++band; offset=next;
            } else if (kind==0x2000 || kind==0x2100 || kind==0x2400 || kind==0x2500 || kind==0x2600 || kind==0x2700) {
                if (depth==16 || !words) return false;
                ends[depth++]=next;
            } else {
                if (signed_tag>=0 || tag!=0x4004 || words!=9) return false;
                offset=next;
            }
            continue;
        }
        switch (tag) {
            case 12: if (value!=4) return false; mask|=1; break;
            case 20: if (value!=v.width) return false; mask|=2; break;
            case 21: if (value!=v.height) return false; mask|=4; break;
            case 84: if (value!=4) return false; mask|=8; break;
            case 106: if (value!=2) return false; mask|=16; break;
            case 107: if (value!=2) return false; mask|=32; break;
            case 108: if (value!=1) return false; mask|=64; break;
            case 102: if (value!=12) return false; mask|=128; break;
            case 101: if (value!=12) return false; break;
            case 14: if (value!=10) return false; break;
            case 62: if (value>=4) return false; channel=value; band=count[channel]; break;
            case 48: if (value!=count[channel] || value>=10) return false; band=value; break;
            case 35: if (value<1 || value>16) return false; precision=value; break;
            case 53: if (value>32767) return false; break;
            case 109: if (value!=0 && value!=0x2800) return false; break;
            default: return false;
        }
    }
    while (depth && offset==ends[depth-1]) --depth;
    return !depth && mask==255 && count[0]==10 && count[1]==10 && count[2]==10 && count[3]==10;
}
// The historical decoder has early error returns. Track frame allocations so
// wrapper failures also reclaim resources that did not reach its normal exit.
struct Allocations {
    std::map<void *,size_t> pointers;
    ~Allocations() { for (const auto &p:pointers) std::free(p.first); }
};
thread_local Allocations *active=nullptr;
void *allocate(size_t size) noexcept {
    void *p=std::malloc(size); if (!p) return nullptr;
    try { active->pointers.emplace(p,size); } catch (...) { std::free(p); return nullptr; }
    return p;
}
void release(void *p) {
    if (!p) return;
    auto found=active->pointers.find(p);
    if (found!=active->pointers.end()) { std::free(p); active->pointers.erase(found); }
}
}
extern "C" void gpr_preview_options_default(gpr_preview_options *out) {
    if (out) {
        *out={}; out->downsample=4;
        gpr_rgb_gain gain; gpr_rgb_gain_set_defaults(&gain);
        out->gain_num[0]=gain.r_gain_num; out->gain_pow2_den[0]=gain.r_gain_pow2_den;
        out->gain_num[1]=gain.g_gain_num; out->gain_pow2_den[1]=gain.g_gain_pow2_den;
        out->gain_num[2]=gain.b_gain_num; out->gain_pow2_den[2]=gain.b_gain_pow2_den;
    }
}
extern "C" int gpr_preview_dimensions(const gpr_gvid_config *v,const gpr_preview_options *o,gpr_preview_info *out) {
    uint8_t check[64];
    if (!v || !o || !out || gpr_gvid_write_header(check,v,nullptr,0) ||
        (o->downsample!=4 && o->downsample!=8 && o->downsample!=16)) return GPR_PREVIEW_INVALID;
    for (unsigned i=0;i<3;++i) if (!o->gain_num[i] || o->gain_num[i]>1024 || o->gain_pow2_den[i]>16) return GPR_PREVIEW_INVALID;
    out->width=(v->width+o->downsample-1)/o->downsample;
    out->height=(v->height+o->downsample-1)/o->downsample;
    out->row_bytes=size_t(out->width)*3; return 0;
}
extern "C" int gpr_preview_render(const gpr_gvid_config *v,const gpr_preview_options *o,
    const uint8_t *payload,size_t size,uint8_t *rgb,size_t capacity,size_t pitch,gpr_preview_info *out) {
    gpr_preview_info dimensions={};
    if (!out || !rgb || gpr_preview_dimensions(v,o,&dimensions)) return GPR_PREVIEW_INVALID;
    if (pitch<dimensions.row_bytes || pitch>SIZE_MAX/dimensions.height ||
        capacity<(dimensions.height-1)*pitch+dimensions.row_bytes) return GPR_PREVIEW_CAPACITY;
    if (!stock_payload(*v,payload,size)) return GPR_PREVIEW_PAYLOAD;
    try {
        std::vector<uint8_t> aligned;
        if (reinterpret_cast<uintptr_t>(payload)%4) { aligned.assign(payload,payload+size); payload=aligned.data(); }
        Allocations allocation; auto previous=active; active=&allocation;
        struct Restore { Allocations *old; ~Restore() { active=old; } } restore{previous};
        vc5_decoder_parameters parameters={}; vc5_decoder_parameters_set_default(&parameters);
        parameters.mem_alloc=allocate; parameters.mem_free=release;
        bool gbrg=!std::memcmp(v->cfa,"GBRG",4);
        parameters.pixel_format=gbrg ? (v->sample_bits==14 ? VC5_DECODER_PIXEL_FORMAT_GBRG_14:VC5_DECODER_PIXEL_FORMAT_GBRG_12)
            : (v->sample_bits==14 ? VC5_DECODER_PIXEL_FORMAT_RGGB_14:VC5_DECODER_PIXEL_FORMAT_RGGB_12);
        parameters.rgb_resolution=o->downsample==4 ? GPR_RGB_RESOLUTION_QUARTER:
            (o->downsample==8 ? GPR_RGB_RESOLUTION_EIGHTH:GPR_RGB_RESOLUTION_SIXTEENTH);
        parameters.rgb_bits=8;
        parameters.rgb_gain={int(o->gain_num[0]),int(o->gain_pow2_den[0]),int(o->gain_num[1]),
            int(o->gain_pow2_den[1]),int(o->gain_num[2]),int(o->gain_pow2_den[2])};
        gpr_buffer input={const_cast<uint8_t *>(payload),size}; gpr_rgb_buffer decoded={};
        CODEC_ERROR error=vc5_decoder_process(&parameters,&input,nullptr,&decoded);
        if (error || !decoded.buffer || decoded.width!=dimensions.width || decoded.height!=dimensions.height ||
            decoded.size!=dimensions.row_bytes*dimensions.height) return GPR_PREVIEW_CODEC;
        for (size_t y=0;y<dimensions.height;++y)
            std::memcpy(rgb+y*pitch,static_cast<uint8_t *>(decoded.buffer)+y*dimensions.row_bytes,dimensions.row_bytes);
        release(decoded.buffer); *out=dimensions; return 0;
    } catch (...) { return GPR_PREVIEW_NOMEM; }
}
