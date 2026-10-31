#include "../source/lib/vc5_encoder/headers.h"
#include "vc5_encoder.h"
#include "vc5_decoder.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define REQUIRE(x) do{if(!(x)){std::fprintf(stderr,"stream inverse line %d: %s\n",__LINE__,#x);std::exit(1);}}while(0)
#include "wavelet_row_collector.hpp"
struct Rows {
 std::array<int16_t,1025> cubic;
 std::array<RowChannel,3> channels;
 Rows(unsigned w,unsigned h):channels{{RowChannel(w,h,cubic.data()),RowChannel(w,h,cubic.data()),RowChannel(w,h,cubic.data())}}{REQUIRE(!ComputeCubicTable(cubic.data(),1025,255));}
 static void accept(void *user,const vc5_preview_row *row){REQUIRE(row&&row->channel<3);static_cast<Rows*>(user)->channels[row->channel].accept(*row);}
};
static void run(unsigned w,unsigned h,unsigned phase,unsigned depth,unsigned quality){
 const PIXEL_FORMAT formats[4][3]={
 {PIXEL_FORMAT_RAW_RGGB_12,PIXEL_FORMAT_RAW_RGGB_14,PIXEL_FORMAT_RAW_RGGB_16},
 {PIXEL_FORMAT_RAW_GBRG_12,PIXEL_FORMAT_RAW_GBRG_14,PIXEL_FORMAT_RAW_GBRG_16},
 {PIXEL_FORMAT_RAW_GRBG_12,PIXEL_FORMAT_RAW_GRBG_14,PIXEL_FORMAT_RAW_GRBG_16},
 {PIXEL_FORMAT_RAW_BGGR_12,PIXEL_FORMAT_RAW_BGGR_14,PIXEL_FORMAT_RAW_BGGR_16}};
 const VC5_ENCODER_PIXEL_FORMAT public_formats[4][3]={
 {VC5_ENCODER_PIXEL_FORMAT_RGGB_12,VC5_ENCODER_PIXEL_FORMAT_RGGB_14,VC5_ENCODER_PIXEL_FORMAT_RGGB_16},
 {VC5_ENCODER_PIXEL_FORMAT_GBRG_12,VC5_ENCODER_PIXEL_FORMAT_GBRG_14,VC5_ENCODER_PIXEL_FORMAT_GBRG_16},
 {VC5_ENCODER_PIXEL_FORMAT_GRBG_12,VC5_ENCODER_PIXEL_FORMAT_GRBG_14,VC5_ENCODER_PIXEL_FORMAT_GRBG_16},
 {VC5_ENCODER_PIXEL_FORMAT_BGGR_12,VC5_ENCODER_PIXEL_FORMAT_BGGR_14,VC5_ENCODER_PIXEL_FORMAT_BGGR_16}};
 const QUANT tables[6][10]={{1,24,24,12,64,64,48,512,512,768},{1,24,24,12,48,48,32,256,256,384},
 {1,24,24,12,32,32,24,128,128,192},{1,24,24,12,24,24,12,96,96,144},
 {1,24,24,12,24,24,12,64,64,96},{1,24,24,12,24,24,12,32,32,48}};
 std::vector<uint16_t> raw(size_t(w)*h);uint32_t random=71;unsigned bits=12+2*depth;
 for(auto &v:raw){random=random*1664525u+1013904223u;v=uint16_t((random>>16)&((1u<<bits)-1));}
 vc5_encoder_parameters ep;vc5_encoder_parameters_set_default(&ep);ep.input_width=w;ep.input_height=h;ep.input_pitch=w*2;ep.pixel_format=public_formats[phase][depth];ep.quality_setting=(VC5_ENCODER_QUALITY_SETTING)quality;
 gpr_buffer input={raw.data(),raw.size()*2},reference={};unsetenv("GPR_PIPELINE_WAVELETS");REQUIRE(!vc5_encoder_process(&ep,&input,&reference,nullptr));
 ENCODER_PARAMETERS p;InitEncoderParameters(&p);p.encoded.format=IMAGE_FORMAT_RAW;p.allocator.Alloc=malloc;p.allocator.Free=free;std::memcpy(p.quant_table,tables[quality],sizeof(p.quant_table));
 IMAGE image={};image.buffer=raw.data();image.width=w;image.height=h;image.pitch=w*2;image.size=input.size;image.format=formats[phase][depth];p.input.width=w;p.input.height=h;p.input.format=image.format;
 Rows rows(w,h);p.preview_row_observer=Rows::accept;p.preview_row_user=&rows;
 std::vector<uint8_t> bytes(input.size+input.size/2+(1<<20));STREAM stream;REQUIRE(!CreateStreamBuffer(&stream,bytes.data(),bytes.size()));REQUIRE(!EncodeImage(&image,&stream,nullptr,&p));
 REQUIRE(reference.size==stream.byte_count&&!std::memcmp(reference.buffer,bytes.data(),reference.size));
 vc5_decoder_parameters dp;vc5_decoder_parameters_set_default(&dp);dp.mem_alloc=malloc;dp.mem_free=free;dp.rgb_bits=16;dp.rgb_resolution=GPR_RGB_RESOLUTION_QUARTER;
 for(unsigned c=0;c<3;++c){auto &out=rows.channels[c];REQUIRE(out.complete());gpr_rgb_buffer plane={};REQUIRE(!vc5_decoder_process_wavelet_channel(&dp,&reference,c,&plane));REQUIRE(plane.width==out.width&&plane.height==out.height&&plane.size==out.plane.size()*2&&!std::memcmp(plane.buffer,out.plane.data(),plane.size));free(plane.buffer);}
 free(reference.buffer);
}
int main(){const unsigned widths[5]={48,50,130,192,206},heights[5]={48,50,98,128,150};unsigned cases=0;
 for(unsigned shape=0;shape<5;++shape)for(unsigned phase=0;phase<4;++phase)for(unsigned depth=0;depth<3;++depth)for(unsigned q=0;q<6;++q){run(widths[shape],heights[shape],phase,depth,q);++cases;}
 for(unsigned h=48;h<=320;h+=2){run(130,h,0,1,3);++cases;}
 std::printf("{\"cases\":%u,\"payloads_exact_stock\":true,\"streaming_planes_exact_independent_decode\":true,\"bounded_rings\":true}\n",cases);
}
