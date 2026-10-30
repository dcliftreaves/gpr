/* Independent prefix-count and guarded-boundary proof; no encoder dependencies. */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
typedef int16_t PIXEL;
#include "../source/lib/vc5_encoder/zero_scan.h"
#define CHECK(x) do {if (!(x)) {fprintf(stderr,"zero scan proof line %d\n",__LINE__);exit(1);}} while(0)
static uint64_t cases;
static void prove(PIXEL *data,unsigned count,unsigned expected) {
    const PIXEL *end=data+count;
    CHECK(FindFirstNonzero(data,end)==data+expected);
    ++cases;
}
int main(void) {
    PIXEL storage[192];
    /* Every alignment modulo 128, every short length and possible first position. */
    for (unsigned offset=0;offset<64;++offset) for (unsigned count=0;count<=65;++count) {
        PIXEL *data=storage+offset;
        memset(data,0,count*2);prove(data,count,count);
        for (unsigned first=0;first<count;++first) {data[first]=-32768;prove(data,count,first);data[first]=0;}
    }
    /* Every nonzero 16-bit representation in every vector lane. */
    for (unsigned lane=0;lane<8;++lane) for (unsigned value=1;value<65536;++value) {
        memset(storage,0,32);storage[lane]=(PIXEL)value;prove(storage,16,lane);
    }
    size_t page=(size_t)sysconf(_SC_PAGESIZE);
    uint8_t *pages=mmap(NULL,page*3,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);CHECK(pages!=MAP_FAILED);
    CHECK(!mprotect(pages+page,page,PROT_READ|PROT_WRITE));
    for (unsigned count=0;count<=128;++count) {
        PIXEL *data=(PIXEL *)(pages+page*2-count*2);memset(data,0,count*2);prove(data,count,count);
        for (unsigned first=0;first<count;++first) {data[first]=1;prove(data,count,first);data[first]=0;}
        data=(PIXEL *)(pages+page);memset(data,0,count*2);prove(data,count,count);
    }
    CHECK(!munmap(pages,page*3));
    printf("{\"variant\":%d,\"cases\":%llu,\"all_prefixes_exact\":true,\"guard_pages\":true}\n",GPR_ZERO_SCAN,(unsigned long long)cases);
    return 0;
}
