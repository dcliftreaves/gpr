/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_preview_srgb.hpp"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <future>
#include <stdexcept>
static void check(bool b,const char *m){if(!b)throw std::runtime_error(m);}
int main(int argc,char **argv){try{
 auto first=std::async(std::launch::async,[]{return gpr_preview_detail::srgb_table();});
 auto *table=gpr_preview_detail::srgb_table();check(first.get()==table,"first-use table identity");check(reinterpret_cast<uintptr_t>(table)%128==0,"table alignment");
 unsigned transitions=0;
 for(unsigned i=0;i<65536;++i){double x=double(i)/65535;double encoded=x<=.0031308?12.92*x:1.055*std::pow(x,1.0/2.4)-.055;auto expected=uint8_t(std::floor(encoded*255+.5));check(gpr_preview_detail::srgb_lookup(table,i)==expected,"packed gamma differs from legacy formula");if(i&&gpr_preview_detail::srgb_lookup(table,i)!=gpr_preview_detail::srgb_lookup(table,i-1))++transitions;}
 if(argc==2){std::ofstream file(argv[1],std::ios::binary);check(bool(file),"table output");for(unsigned i=0;i<4096;++i){char b[2]={char(table[i]&255),char(table[i]>>8)};file.write(b,2);}}
 std::printf("{\"inputs_exact\":65536,\"table_bytes\":8192,\"alignment\":128,\"transitions\":%u}\n",transitions);return 0;
}catch(const std::exception &e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
