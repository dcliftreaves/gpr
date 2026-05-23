// GPRFileReader.m — read encoded .gpr files (FUSED format).
//
// We use mmap'd-backed NSData so the OS handles paging; for ~3.5 MB files
// on NVMe this resolves to ~1-2 ms of effective wall-clock per frame. The
// file is not modified, so NSDataReadingMappedAlways is the right policy.

#import "GPRFileReader.h"

// Field offsets in the FUSED_HEADER (see fused_encode.h). Keep these in sync.
//   magic=0 version=4 width=8 height=12 pixel_format=16 quality=20 is_rggb=24
//   log_bits=28 prescale=32 multi_level=36 num_bands=40 decimate=44
static uint32_t le32_at(const uint8_t *p, size_t off) {
    return  (uint32_t)p[off+0]
         | ((uint32_t)p[off+1] << 8)
         | ((uint32_t)p[off+2] << 16)
         | ((uint32_t)p[off+3] << 24);
}

static BOOL parse_header_bytes(const uint8_t *bytes, size_t len, GPRFileInfo *info) {
    if (!bytes || len < 48) return NO;
    uint32_t magic = le32_at(bytes, 0);
    if (magic != 0x44535546u) {
        fprintf(stderr, "GPRFileReader: bad magic 0x%08x (expected 'FUSD')\n", magic);
        return NO;
    }
    info->encWidth    = le32_at(bytes,  8);
    info->encHeight   = le32_at(bytes, 12);
    info->pixelFormat = le32_at(bytes, 16);
    uint32_t dec      = le32_at(bytes, 44);
    info->decimate    = (dec < 2) ? 1 : dec;
    info->decWidth    = info->encWidth  / info->decimate;
    info->decHeight   = info->encHeight / info->decimate;
    return YES;
}

@implementation GPRFileReader

+ (nullable NSData *)readEncodedFromPath:(NSString *)path info:(GPRFileInfo *)info {
    NSError *err = nil;
    NSData *data = [NSData dataWithContentsOfFile:path
                                          options:NSDataReadingMappedAlways
                                            error:&err];
    if (!data) {
        fprintf(stderr, "GPRFileReader: open %s failed: %s\n",
                [path UTF8String],
                err ? [[err localizedDescription] UTF8String] : "?");
        return nil;
    }
    if (!parse_header_bytes(data.bytes, data.length, info)) {
        fprintf(stderr, "GPRFileReader: bad FUSED header in %s\n", [path UTF8String]);
        return nil;
    }
    return data;
}

+ (BOOL)readHeaderFromPath:(NSString *)path info:(GPRFileInfo *)info {
    NSFileHandle *fh = [NSFileHandle fileHandleForReadingAtPath:path];
    if (!fh) return NO;
    NSData *hdr = [fh readDataOfLength:48];
    [fh closeFile];
    return parse_header_bytes(hdr.bytes, hdr.length, info);
}

@end
