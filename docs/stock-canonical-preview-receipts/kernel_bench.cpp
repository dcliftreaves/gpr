/* SPDX-License-Identifier: Apache-2.0 OR MIT */
// Diagnostic: fixed 12 MP RGGB14 -> 1024x768 calibrated display. Decode/setup
// and RGB CRC are excluded from render timing; no encoding, queue or storage.
#include "gpr_preview.h"
#include "vc5_decoder.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>
#include <zlib.h>
static std::vector<uint8_t> read(const char *path) {
    std::ifstream input(path,std::ios::binary|std::ios::ate);
    if (!input || input.tellg()<=0 || input.tellg()>128*1024*1024) throw std::runtime_error("invalid input size");
    std::vector<uint8_t> bytes(size_t(input.tellg()));input.seekg(0);
    if (!input.read(reinterpret_cast<char *>(bytes.data()),bytes.size())) throw std::runtime_error("input read failed");
    return bytes;
}
struct Source {
    gpr_preview_plan *plan=nullptr;
    std::vector<int16_t> samples[3];
    gpr_preview_wavelet_planes planes={};
    uint32_t crc=0;
    ~Source(){gpr_preview_plan_destroy(plan);}
};
int main(int argc,char **argv) {
    try {
        if (argc!=6) throw std::runtime_error("usage: kernel_bench iterations profile0 payload0 profile1 payload1");
        unsigned iterations=unsigned(std::stoul(argv[1]));
        if (!iterations || iterations>10000) throw std::runtime_error("invalid iterations");
        Source sources[2];gpr_gvid_config video={4096,3072,20,1,3,14,{'R','G','G','B'}};
        for (unsigned i=0;i<2;++i) {
            auto profile=read(argv[2+i*2]),payload=read(argv[3+i*2]);
            if (gpr_preview_plan_from_profile(&video,profile.data(),profile.size(),&sources[i].plan)) throw std::runtime_error("profile rejected");
            vc5_decoder_parameters decoder={};vc5_decoder_parameters_set_default(&decoder);
            decoder.mem_alloc=std::malloc;decoder.mem_free=std::free;
            decoder.rgb_bits=16;decoder.rgb_resolution=GPR_RGB_RESOLUTION_QUARTER;
            gpr_buffer compressed={payload.data(),payload.size()};
            for (unsigned c=0;c<3;++c) {
                gpr_rgb_buffer plane={};
                if (vc5_decoder_process_wavelet_channel(&decoder,&compressed,c,&plane)) throw std::runtime_error("decode failed");
                std::unique_ptr<void,decltype(&std::free)> owned(plane.buffer,std::free);
                if (plane.width!=1024 || plane.height!=768) throw std::runtime_error("unexpected geometry");
                sources[i].samples[c].assign(static_cast<int16_t *>(plane.buffer),static_cast<int16_t *>(plane.buffer)+plane.size/2);
                sources[i].planes.width=plane.width;sources[i].planes.height=plane.height;
                sources[i].planes.samples[c]=sources[i].samples[c].data();sources[i].planes.sample_count[c]=plane.size/2;
            }
        }
        std::vector<uint8_t> rgb(1024*768*3);std::vector<double> timings;
        for (unsigned iteration=0;iteration<iterations;++iteration) for (auto &source:sources) {
            gpr_preview_info info={};auto begin=std::chrono::steady_clock::now();
            int error=gpr_preview_plan_render_wavelets(source.plan,&source.planes,rgb.data(),rgb.size(),1024*3,&info);
            double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
            if (error || info.width!=1024 || info.height!=768) throw std::runtime_error("render failed");
            uint32_t crc=uint32_t(crc32(0,rgb.data(),rgb.size()));
            if (iteration && crc!=source.crc) throw std::runtime_error("pixels changed across repeats");
            source.crc=crc;timings.push_back(ms);
        }
        std::sort(timings.begin(),timings.end());
        std::cout<<"{\"renders\":"<<timings.size()<<",\"median_ms\":"<<timings[timings.size()/2]
            <<",\"p95_ms\":"<<timings[size_t((timings.size()-1)*.95)]<<",\"source_rgb_crc32\":["
            <<sources[0].crc<<','<<sources[1].crc<<"]}\n";
        return 0;
    }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
