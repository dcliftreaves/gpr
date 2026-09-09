// GPRawReader.m — Objective-C façade over tools/gpraw/include/gpraw.h.
//
// Build: this needs the gpraw object file (build/gpraw.o) and the FFmpeg
// link flags. The gpr2prores Makefile currently does not pull libavformat
// in; integrating this file therefore requires adding:
//
//     CFLAGS  += `pkg-config --cflags libavformat libavutil`
//     LDFLAGS += `pkg-config --libs   libavformat libavutil`
//     OBJS    += GPRawReader.o ../gpraw/build/gpraw.o
//
// to the gpr2prores Makefile and re-running. Until then this file is built
// only as part of standalone validation. The header is unconditional so
// the rest of the pipeline can reference the API.

#import "GPRawReader.h"
#import "../gpraw/include/gpraw.h"

// Inline the FUSED_HEADER parse — same logic as GPRFileReader so we don't
// pull in fused_encode.h here.
static uint32_t le32_at(const uint8_t *p, size_t off) {
    return  (uint32_t)p[off+0]
         | ((uint32_t)p[off+1] << 8)
         | ((uint32_t)p[off+2] << 16)
         | ((uint32_t)p[off+3] << 24);
}

static BOOL parse_fused_header(const uint8_t *bytes, size_t len, GPRFileInfo *info) {
    if (!bytes || len < 48) return NO;
    if (le32_at(bytes, 0) != 0x44535546u) return NO;     // 'FUSD'
    info->encWidth    = le32_at(bytes,  8);
    info->encHeight   = le32_at(bytes, 12);
    info->pixelFormat = le32_at(bytes, 16);
    uint32_t dec      = le32_at(bytes, 44);
    info->decimate    = (dec < 2) ? 1 : dec;
    info->decWidth    = info->encWidth  / info->decimate;
    info->decHeight   = info->encHeight / info->decimate;
    return YES;
}

@implementation GPRawReader {
    GPRaw_Reader *_reader;
    GPRaw_Metadata _meta;
    NSInteger _frameCount;
    NSInteger _width;
    NSInteger _height;
    double    _fps;
    NSString *_codecVersion;
    NSString *_cfaPattern;
    NSString *_encoderSettings;
    NSInteger _quality;
    NSInteger _bitDepth;
    NSInteger _blackLevel;
    NSInteger _whiteLevel;
}

- (nullable instancetype)initWithPath:(NSString *)path {
    self = [super init];
    if (!self) return nil;

    _reader = gpraw_reader_open([path UTF8String]);
    if (!_reader) return nil;

    int w = 0, h = 0, fnum = 0, fden = 1;
    int64_t nf = 0;
    gpraw_reader_get_video_info(_reader, &w, &h, &fnum, &fden, &nf);
    _width = w; _height = h;
    _fps = fden > 0 ? (double)fnum / (double)fden : 0.0;
    _frameCount = (NSInteger)nf;

    GPRaw_Metadata m;
    if (gpraw_reader_get_metadata(_reader, &m) == 0) {
        _meta = m;
        _codecVersion    = m.codec_version    ? @(m.codec_version)    : nil;
        _cfaPattern      = m.cfa_pattern      ? @(m.cfa_pattern)      : nil;
        _encoderSettings = m.encoder_settings ? @(m.encoder_settings) : nil;
        _quality         = m.quality;
        _bitDepth        = m.bit_depth;
        _blackLevel      = m.black_level;
        _whiteLevel      = m.white_level;
    }
    return self;
}

- (NSInteger)frameCount    { return _frameCount; }
- (NSInteger)width         { return _width; }
- (NSInteger)height        { return _height; }
- (double)fps              { return _fps; }
- (NSString *)codecVersion { return _codecVersion; }
- (NSString *)cfaPattern   { return _cfaPattern; }
- (NSInteger)quality       { return _quality; }
- (NSInteger)bitDepth      { return _bitDepth; }
- (NSInteger)blackLevel    { return _blackLevel; }
- (NSInteger)whiteLevel    { return _whiteLevel; }
- (NSString *)encoderSettings { return _encoderSettings; }

- (nullable NSData *)nextEncodedFrameInto:(GPRFileInfo *)info {
    if (!_reader) return nil;
    const uint8_t *bytes = NULL;
    size_t n = 0;
    int64_t ts = 0;
    int rc = gpraw_reader_next_frame(_reader, &bytes, &n, &ts);
    if (rc != 0 || !bytes || n == 0) return nil;
    if (info) parse_fused_header(bytes, n, info);
    // No-copy NSData: bytes are valid until the next call. Callers that
    // want to retain them must -copy explicitly. Most of the pipeline
    // consumes them in the same iteration so we can avoid the alloc.
    return [NSData dataWithBytesNoCopy:(void *)bytes length:n freeWhenDone:NO];
}

- (void)close {
    if (_reader) { gpraw_reader_close(_reader); _reader = NULL; }
}

- (void)dealloc {
    [self close];
}

@end
