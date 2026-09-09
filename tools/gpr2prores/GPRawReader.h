// GPRawReader.h — Objective-C wrapper around the gpraw C library for
// streaming GPR-encoded frames out of a GPRaw .mov container.
//
// This is the symmetric counterpart to GPRFileReader (which reads one .gpr
// file at a time). The pipeline can switch between them at frame-iteration
// time:
//
//     GPRFileReader   — reads N independent .gpr files from a directory
//     GPRawReader     — reads N frames from a single .mov GPRaw container
//
// Internally this wraps gpraw_reader_* from tools/gpraw. The MOV layer is
// opaque about the GPR bitstream — the bytes returned here are exactly
// what gpr_encode_fused_frame emitted (FUSED_HEADER + bands), so the
// downstream decode + CNN + demosaic stages stay identical.

#import <Foundation/Foundation.h>
#import "GPRFileReader.h"   // for GPRFileInfo

NS_ASSUME_NONNULL_BEGIN

@interface GPRawReader : NSObject

// Open a .mov GPRaw container. Returns nil on failure.
- (nullable instancetype)initWithPath:(NSString *)path;

// Total frames in the container (from MOV nb_frames; may be 0 for some
// streams — fall back to streaming until -nextEncodedFrame: returns NO).
@property (nonatomic, readonly) NSInteger frameCount;

// Output bayer dimensions (decimated half-res target) declared in the
// MOV video sample description. Match what the decoder will produce.
@property (nonatomic, readonly) NSInteger width;
@property (nonatomic, readonly) NSInteger height;
@property (nonatomic, readonly) double    fps;

// Track-level metadata as strings (nil if absent). Strings remain valid
// until -close.
@property (nonatomic, readonly, nullable) NSString *codecVersion;
@property (nonatomic, readonly, nullable) NSString *cfaPattern;
@property (nonatomic, readonly) NSInteger quality;
@property (nonatomic, readonly) NSInteger bitDepth;
@property (nonatomic, readonly) NSInteger blackLevel;
@property (nonatomic, readonly) NSInteger whiteLevel;
@property (nonatomic, readonly, nullable) NSString *encoderSettings;

// Stream the next frame. Returns nil at EOF or on error.
// The returned NSData is backed by demuxer-owned memory that is reused on
// the next call — copy it before invoking -nextEncodedFrame: again.
// On success, *info is filled in from the frame's FUSED_HEADER bytes.
- (nullable NSData *)nextEncodedFrameInto:(GPRFileInfo *)info;

// Release the underlying demuxer. Safe to call multiple times.
- (void)close;

@end

NS_ASSUME_NONNULL_END
