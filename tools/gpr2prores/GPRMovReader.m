// GPRMovReader.m — libavformat-backed MOV reader for GPR-frame streams.

#import "GPRMovReader.h"
#import "DNGExif.h"

#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>

#define GPR_FOURCC  MKTAG('G','P','R','1')
#define TMCD_FOURCC MKTAG('t','m','c','d')

@implementation GPRMovReader {
    AVFormatContext *_fmtCtx;
    int _vstreamIdx;
    int _astreamIdx;
    int _tstreamIdx;
    // EXIF sidecar (sibling .exif file): one length-prefixed GEXF blob per frame.
    NSData *_exifSidecar;
    size_t _exifSidecarOff;
    int _exifFrameIdx;
}

- (nullable instancetype)initWithPath:(NSString *)path info:(GPRMovInfo *)info {
    self = [super init];
    if (!self) return nil;
    const char *cpath = [path UTF8String];
    _vstreamIdx = _astreamIdx = _tstreamIdx = -1;

    if (avformat_open_input(&_fmtCtx, cpath, NULL, NULL) < 0) {
        fprintf(stderr, "GPRMovReader: open %s failed\n", cpath);
        return nil;
    }
    if (avformat_find_stream_info(_fmtCtx, NULL) < 0) {
        avformat_close_input(&_fmtCtx);
        return nil;
    }
    for (unsigned i = 0; i < _fmtCtx->nb_streams; i++) {
        AVStream *s = _fmtCtx->streams[i];
        uint32_t tag = s->codecpar->codec_tag;
        if (tag == GPR_FOURCC) _vstreamIdx = (int)i;
        else if (tag == TMCD_FOURCC) _tstreamIdx = (int)i;
        else if (s->codecpar->codec_type == AVMEDIA_TYPE_AUDIO) _astreamIdx = (int)i;
    }
    if (_vstreamIdx < 0) {
        fprintf(stderr, "GPRMovReader: no GPR1-tagged stream in %s\n", cpath);
        avformat_close_input(&_fmtCtx);
        return nil;
    }

    // Try to load the EXIF sidecar (<path>.exif).
    NSString *exifPath = [path stringByAppendingPathExtension:@"exif"];
    BOOL hasExif = NO;
    if ([[NSFileManager defaultManager] fileExistsAtPath:exifPath]) {
        _exifSidecar = [NSData dataWithContentsOfFile:exifPath options:NSDataReadingMappedAlways error:nil];
        if (_exifSidecar.length >= 4 && memcmp(_exifSidecar.bytes, "GEX0", 4) == 0) {
            _exifSidecarOff = 4;
            _exifFrameIdx = 0;
            hasExif = YES;
        } else {
            _exifSidecar = nil;
        }
    }

    AVStream *vs = _fmtCtx->streams[_vstreamIdx];
    if (info) {
        memset(info, 0, sizeof(*info));
        info->width     = (uint32_t)vs->codecpar->width;
        info->height    = (uint32_t)vs->codecpar->height;
        // r_frame_rate is the real rate from sample table; fall back to avg.
        AVRational fr = vs->r_frame_rate.num ? vs->r_frame_rate : vs->avg_frame_rate;
        if (fr.den > 0 && fr.num > 0 && fr.num / fr.den > 0 && fr.num / fr.den <= 240) {
            info->fps = fr.num / fr.den;
        } else {
            info->fps = 24;
        }
        info->numFrames = vs->nb_frames;
        info->hasAudio    = (_astreamIdx >= 0);
        info->hasTimecode = (_tstreamIdx >= 0);
        info->hasExif     = hasExif;
        if (_tstreamIdx >= 0) {
            AVDictionaryEntry *tcent =
                av_dict_get(_fmtCtx->streams[_tstreamIdx]->metadata, "timecode", NULL, 0);
            if (tcent && tcent->value) {
                strncpy(info->timecodeStart, tcent->value, sizeof(info->timecodeStart) - 1);
            }
        }
    }
    fprintf(stderr, "GPRMovReader: %s opened, video=%d audio=%d tmcd=%d exif=%s (%dx%d)\n",
            cpath, _vstreamIdx, _astreamIdx, _tstreamIdx, hasExif ? "sidecar" : "no",
            vs->codecpar->width, vs->codecpar->height);
    return self;
}

- (void)dealloc {
    if (_fmtCtx) avformat_close_input(&_fmtCtx);
}

- (nullable DNGExifInfo *)nextExifFromSidecar {
    if (!_exifSidecar) return nil;
    if (_exifSidecarOff + 4 > _exifSidecar.length) return nil;
    const uint8_t *p = _exifSidecar.bytes;
    uint32_t L = *(const uint32_t *)(p + _exifSidecarOff);
    _exifSidecarOff += 4;
    if (_exifSidecarOff + L > _exifSidecar.length) return nil;
    NSData *blob = [NSData dataWithBytesNoCopy:(void *)(p + _exifSidecarOff)
                                       length:L
                                 freeWhenDone:NO];
    _exifSidecarOff += L;
    _exifFrameIdx++;
    return [DNGExif deserialize:blob];
}

- (nullable NSData *)nextFrame {
    return [self nextFrameWithExif:NULL];
}

- (nullable NSData *)nextFrameWithExif:(DNGExifInfo * _Nullable * _Nullable)outExif {
    if (!_fmtCtx) return nil;
    if (outExif) *outExif = nil;
    AVPacket *pkt = av_packet_alloc();
    if (!pkt) return nil;
    while (av_read_frame(_fmtCtx, pkt) >= 0) {
        if (pkt->stream_index == _vstreamIdx) {
            NSData *d = [NSData dataWithBytes:pkt->data length:(NSUInteger)pkt->size];
            av_packet_unref(pkt);
            av_packet_free(&pkt);
            if (outExif) *outExif = [self nextExifFromSidecar];
            return d;
        } else {
            // Audio / timecode / other — skip silently (preserved on disk).
            av_packet_unref(pkt);
        }
    }
    av_packet_free(&pkt);
    return nil;
}

- (void)close {
    if (_fmtCtx) {
        avformat_close_input(&_fmtCtx);
        _fmtCtx = NULL;
    }
}

@end
