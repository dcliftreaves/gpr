/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#ifndef GPR_PREVIEW_SRGB_HPP
#define GPR_PREVIEW_SRGB_HPP
#include <cmath>
#include <cstdint>
#include <mutex>
#include <stdexcept>
namespace gpr_preview_detail {
using srgb_entry=uint16_t;
inline uint8_t srgb_reference(unsigned i) {
    double x=double(i)/65535;
    double y=x<=.0031308 ? 12.92*x:1.055*std::pow(x,1.0/2.4)-.055;
    return uint8_t(std::floor(y*255+.5));
}
inline const srgb_entry *srgb_table() {
    alignas(128) static srgb_entry table[4096];
    static std::once_flag once;
    std::call_once(once,[]{
        for (unsigned block=0;block<4096;++block) {
            unsigned first=block*16,base=srgb_reference(first),last=srgb_reference(first+15),cutoff=16;
            if (last!=base) {
                if (last!=base+1) throw std::logic_error("sRGB block exceeds packed representation");
                unsigned low=1,high=15;
                while (low<high) {
                    unsigned mid=low+(high-low)/2;
                    if (srgb_reference(first+mid)==base) low=mid+1;else high=mid;
                }
                cutoff=low;
            }
            table[block]=srgb_entry(base|(cutoff<<8));
        }
    });
    return table;
}
inline uint8_t srgb_lookup(const srgb_entry *table,unsigned index) {
    unsigned word=table[index>>4];
    return uint8_t((word&255)+unsigned((index&15)>=(word>>8)));
}
}
#endif
