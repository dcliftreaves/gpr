// GPRMovReader.h — libavformat-backed MOV reader for GPR-frame streams.
//
// Opens a MOV with a GPR1-tagged stream (produced by GPRMovWriter) and
// yields per-frame encoded bytes via -nextFrame:. Companion streams
// (tmcd, GEXF, audio) are exposed via dedicated accessors.

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@class DNGExifInfo;

typedef struct {
    uint32_t width;
    uint32_t height;
    int      fps;
    int64_t  numFrames;  // may be 0 if unknown; rely on -nextFrame: returning nil
    BOOL     hasAudio;
    BOOL     hasTimecode;
    BOOL     hasExif;
    char     timecodeStart[32];   // "HH:MM:SS:FF" or empty
} GPRMovInfo;

@interface GPRMovReader : NSObject

- (nullable instancetype)initWithPath:(NSString *)path info:(GPRMovInfo *)info;

// Returns NSData wrapping the next video frame's encoded bytes, or nil at EOF.
// If `outExif` is non-NULL, fills with the per-frame EXIF for that frame index
// (or nil if no sidecar is present).
- (nullable NSData *)nextFrameWithExif:(DNGExifInfo * _Nullable * _Nullable)outExif;

// Convenience: video only.
- (nullable NSData *)nextFrame;

- (void)close;

@end

NS_ASSUME_NONNULL_END
