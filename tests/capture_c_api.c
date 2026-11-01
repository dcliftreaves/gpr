/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#include "gpr_capture.h"
#include "gpr_gvid_reader.h"
#include <string.h>
static unsigned writes;
struct header_source {const uint8_t *bytes;size_t size,offset;};
static ptrdiff_t read_header_bytes(void *user,uint8_t *bytes,size_t size) {
    struct header_source *source=(struct header_source *)user;
    size_t n=source->size-source->offset;
    if (n>size) n=size;
    memcpy(bytes,source->bytes+source->offset,n);source->offset+=n;
    return (ptrdiff_t)n;
}
static int unexpected_write(void *user,const uint8_t *bytes,size_t size) {
    (void)user;(void)bytes;(void)size;++writes;return 0;
}

static uint32_t slow_crc(uint32_t crc,const uint8_t *p,size_t n) {
    crc ^= UINT32_MAX;
    while (n--) {
        crc ^= *p++;
        for (unsigned bit=0;bit<8;++bit) crc=(crc>>1) ^ ((crc&1) ? 0xedb88320u : 0);
    }
    return crc ^ UINT32_MAX;
}

int main(void) {
    gpr_capture *capture=(gpr_capture *)(uintptr_t)1;
    if (gpr_capture_create(NULL,NULL,&capture)!=GPR_CAPTURE_INVALID || capture!=NULL) return 1;
    if (gpr_capture_create_with_observer(NULL,NULL,NULL,NULL,&capture)!=GPR_CAPTURE_INVALID || capture!=NULL) return 9;
    if (gpr_capture_create_with_encoder_preview(NULL,NULL,NULL,NULL,NULL,NULL,&capture)!=GPR_CAPTURE_INVALID || capture!=NULL) return 10;
    if (gpr_capture_create_with_encoder_rows(NULL,NULL,NULL,NULL,NULL,NULL,&capture)!=GPR_CAPTURE_INVALID || capture!=NULL) return 11;
    if (gpr_capture_flush(NULL)!=GPR_CAPTURE_INVALID || gpr_capture_finish(NULL)!=GPR_CAPTURE_INVALID) return 2;
    if (gpr_capture_get_stats(NULL,NULL)!=GPR_CAPTURE_INVALID) return 3;
    if (gpr_gvid_crc32(0,"123456789",9)!=0xcbf43926u) return 4;
    {
        uint8_t header[64];
        gpr_gvid_config video={11664,8750,1,1,3,16,{'R','G','G','B'}};
        if (gpr_gvid_write_header(header,&video,NULL,0)) return 12;
        {
            struct header_source source={header,sizeof header,0};
            gpr_gvid_reader *reader=NULL;gpr_gvid_stream_info info;
            if (gpr_gvid_reader_create(read_header_bytes,&source,0,&reader)) return 17;
            if (gpr_gvid_reader_info(reader,&info) || info.video.width!=11664 || info.video.height!=8750) return 18;
            gpr_gvid_reader_close(reader);
            /* v2 keeps its old geometry limits even with the v3 extension. */
            header[4]=2;header[36]=14;header[40]=32;memset(header+44,0,20);source.offset=0;
            if (gpr_gvid_reader_create(read_header_bytes,&source,0,&reader)!=GPR_GVID_INVALID || reader) return 19;
        }
        video.width=16384;video.height=8192;
        if (gpr_gvid_write_header(header,&video,NULL,0)) return 13;
        video.height=8194;
        if (!gpr_gvid_write_header(header,&video,NULL,0)) return 14;
        video.width=11665;video.height=8750;
        if (!gpr_gvid_write_header(header,&video,NULL,0)) return 15;
        video.width=16386;video.height=48;
        if (!gpr_gvid_write_header(header,&video,NULL,0)) return 16;
    }
    {
        gpr_capture_config config={0};gpr_capture_callbacks callbacks={unexpected_write,0,0};
        config.video=(gpr_gvid_config){128,96,30,1,3,14,{'R','G','G','B'}};
        config.stride_bytes=256;config.max_inflight=1;
        for (unsigned dimension=8;dimension<48;dimension+=8) {
            config.video.width=dimension;
            if (gpr_capture_create(&config,&callbacks,&capture)!=GPR_CAPTURE_INVALID || capture) return 6;
            config.video.width=128;config.video.height=dimension;
            if (gpr_capture_create(&config,&callbacks,&capture)!=GPR_CAPTURE_INVALID || capture) return 7;
            config.video.height=96;
        }
        if (writes) return 8;
    }
    uint8_t data[1040];
    for (size_t i=0;i<sizeof data;++i) data[i]=(uint8_t)(i*13+7);
    for (unsigned offset=0;offset<8;++offset) for (size_t n=0;n<=1024;++n) {
        uint32_t seed=(uint32_t)(n*171871u);
        if (gpr_gvid_crc32(seed,data+offset,n)!=slow_crc(seed,data+offset,n)) return 5;
    }
    gpr_capture_cancel(NULL); gpr_capture_destroy(NULL);
    return 0;
}
