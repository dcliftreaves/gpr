/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
static void check(bool yes,const char *why) { if (!yes) throw std::runtime_error(why); }
struct Buffer {
    gpr_buffer value={};
    ~Buffer() { std::free(value.buffer); }
};
static void write(const char *path,const gpr_buffer &b) {
    std::ofstream out(path,std::ios::binary);
    check(bool(out.write(static_cast<const char *>(b.buffer),b.size)),"output write");
}
int main(int argc,char **argv) {
    try {
        check(argc==5,"format fixture.vc5 output.gpr output.dng");
        const unsigned bits[]={12,12,14,12,12,16,16,14,12,14,16,12,14,16};
        unsigned index=unsigned(std::atoi(argv[1])); check(index<14,"format index");
        std::ifstream in(argv[2],std::ios::binary);
        std::vector<char> bytes((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
        check(!bytes.empty(),"fixture read"); gpr_buffer input={bytes.data(),bytes.size()};
        gpr_allocator allocator={std::malloc,std::free};
        gpr_parameters p; gpr_parameters_set_defaults(&p);
        p.input_width=128; p.input_height=96;
        // Decode produces tightly packed words, independent of this source pitch.
        p.input_pitch=128*2+16;
        p.tuning_info.pixel_format=static_cast<GPR_PIXEL_FORMAT>(index);
        auto &white=p.tuning_info.dgain_saturation_level;
        white.level_red=white.level_green_even=white.level_green_odd=white.level_blue=(1u<<bits[index])-1;
        p.tuning_info.static_black_level={16,17,18,19};
        Buffer gpr,dng,extracted,gpr_raw,dng_raw;
        check(gpr_convert_vc5_to_gpr(&allocator,&p,&input,&gpr.value),"VC5 to GPR");
        check(gpr_convert_gpr_to_vc5(&allocator,&gpr.value,&extracted.value),"GPR to VC5");
        check(extracted.value.size==bytes.size() && !std::memcmp(extracted.value.buffer,bytes.data(),bytes.size()),"payload changed");
        check(gpr_convert_vc5_to_dng(&allocator,&p,&input,&dng.value),"VC5 to DNG");
        check(gpr_convert_gpr_to_raw(&allocator,&gpr.value,&gpr_raw.value),"GPR to raw");
        check(gpr_convert_dng_to_raw(&allocator,&dng.value,&dng_raw.value),"DNG to raw");
        check(gpr_raw.value.size==128*96*2 && dng_raw.value.size==gpr_raw.value.size &&
              !std::memcmp(gpr_raw.value.buffer,dng_raw.value.buffer,gpr_raw.value.size),"wrapper decoded pixels differ");
        Buffer fresh_vc5,fresh_gpr,fresh_extracted;
        check(gpr_convert_dng_to_vc5(&allocator,&dng.value,&fresh_vc5.value),"DNG to VC5");
        p.input_pitch=128*2;
        // Decoded DNG contains unpacked words, including for originally packed input.
        if (index==1) p.tuning_info.pixel_format=PIXEL_FORMAT_RGGB_12;
        if (index==4) p.tuning_info.pixel_format=PIXEL_FORMAT_GBRG_12;
        check(gpr_convert_raw_to_gpr(&allocator,&p,&dng_raw.value,&fresh_gpr.value),"fresh raw to GPR");
        check(gpr_convert_gpr_to_vc5(&allocator,&fresh_gpr.value,&fresh_extracted.value),"fresh GPR to VC5");
        check(fresh_vc5.value.size>4 && fresh_vc5.value.size==fresh_extracted.value.size &&
              !std::memcmp(fresh_vc5.value.buffer,fresh_extracted.value.buffer,fresh_vc5.value.size),"DNG to VC5 differs from fresh stock encode");
        gpr_buffer short_raw=dng_raw.value; --short_raw.size;
        Buffer rejected;
        check(!gpr_convert_raw_to_dng(&allocator,&p,&short_raw,&rejected.value) && !rejected.value.buffer,"short raw input accepted");
        write(argv[3],gpr.value); write(argv[4],dng.value);
        gpr_parameters_destroy(&p,std::free);
        std::cout<<"PASS: SDK payload wrapping and plain DNG, format "<<index<<'\n';
    } catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
