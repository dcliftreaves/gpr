/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "vc5_decoder.h"
#include "rgb.h"
#include "logcurve.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
static void check(bool b,const char *s) {if (!b) {std::fprintf(stderr,"%s\n",s);std::abort();}}
static std::vector<unsigned char> render(RGB_PARAMETERS p) {
    PIXEL gs[]={256,512,1024,1536,256,512,1024,1536};
    PIXEL rg[8],bg[8];std::fill(rg,rg+8,2048);std::fill(bg,bg+8,2048);
    RGB_IMAGE out={};gpr_allocator alloc={std::malloc,std::free};
    WaveletToCalibratedRGB(alloc,gs,rg,bg,4,2,4,&out,12,&p);
    check(out.buffer && out.size==size_t(4*2*3*(p.bits/8)),"render allocation/geometry");
    auto data=static_cast<unsigned char *>(out.buffer);
    std::vector<unsigned char> bytes(data,data+out.size);std::free(out.buffer);return bytes;
}
int main() {
    SetupDecoderLogCurve();
    RGB_PARAMETERS p;rgb_parameters_set_default(&p);
    p.white_balance_gain={1,0,1,0,1,0};
    auto eight=render(p);check(eight[0]<eight[3] && eight[3]<eight[6],"horizontal orientation");
    for (size_t i=0;i<eight.size();i+=3) check(eight[i]==eight[i+1] && eight[i+1]==eight[i+2],"neutral chromaticity");
    p.bits=16;auto sixteen=render(p);
    for (size_t i=0;i<eight.size();++i) {
        unsigned value=(unsigned(sixteen[2*i])<<8)|sixteen[2*i+1];
        check(std::abs(int(value)-int(eight[i])*257)<=258,"8/16 display-render agreement");
    }
    p.bits=8;p.black_level=65535;auto black=render(p);
    check(std::all_of(black.begin(),black.end(),[](unsigned char c){return c==0;}),"black subtraction");
    p.black_level=0;p.baseline_exposure=1;auto bright=render(p);
    for (size_t i=0;i<eight.size();++i) check(bright[i]>=eight[i],"exposure monotonicity");
    p.baseline_exposure=-1;auto dark=render(p);
    for (size_t i=0;i<eight.size();++i) check(dark[i]<=eight[i],"negative exposure monotonicity");
    // Different exposure LUTs must not race across simultaneous SDK decoders.
    std::thread a([&]{for(int i=0;i<30;++i){auto q=p;q.baseline_exposure=1;check(render(q)==bright,"concurrent bright LUT");}});
    std::thread b([&]{for(int i=0;i<30;++i)check(render(p)==dark,"concurrent dark LUT");});a.join();b.join();
    p.baseline_exposure=0;float gains[]={1,2,1,2};
    p.shading_map={{gains,gains,gains},2,2,0,0,1,1};auto shaded=render(p);
    for(size_t i=0;i<eight.size();++i)check(shaded[i]>=eight[i],"lens shading gain");
    p.shading_map={};gpr_buffer invalid={};gpr_rgb_buffer output={};vc5_decoder_parameters d={};
    vc5_decoder_parameters_set_default(&d);d.mem_alloc=std::malloc;d.mem_free=std::free;
    p.color_matrix[0][0]=NAN;
    check(vc5_decoder_process_calibrated(&d,&invalid,&p,&output)==CODEC_ERROR_BAD_ARGUMENT,"nonfinite matrix rejected");
    std::puts("PASS: calibrated orientation, neutral color, exposure, precision, shading, concurrent LUTs and input bounds");
}
