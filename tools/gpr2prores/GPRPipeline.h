// GPRPipeline.h — the top-level pipeline class.
//
// Two input modes:
//   - DNG mode: encodes + decodes through the fused codec per frame
//     (acquisition-time / single-pass benchmarking).
//   - GPR mode: reads pre-encoded .gpr files and runs decode only
//     (playback workflow). Color/black/white/wb metadata comes from a
//     companion DNG passed as metaDngPath.

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface GPRPipeline : NSObject

// firstFrame: path to the first input frame (.dng or .gpr).
// metaDngPath: when firstFrame is .gpr, the DNG to pull color/black/white/wb
//   metadata from. When firstFrame is .dng this may be nil.
// cnnBackend: "coreml" (default), "mpsgraph", or "metal".
// When "mpsgraph"/"metal", ckptPath is interpreted as a directory of fp16 weight
// blobs (see extract_F_weights.py). When "coreml" it's the mlpackage path.
- (nullable instancetype)initWithFirstFrame:(NSString *)firstFrame
                                metaDngPath:(nullable NSString *)metaDngPath
                                   ckptPath:(NSString *)ckptPath
                                    outPath:(NSString *)outPath
                                        fps:(int)fps
                                       aaOn:(BOOL)aaOn
                                      noCNN:(BOOL)noCNN
                                    noCodec:(BOOL)noCodec
                                     timing:(BOOL)timing
                                 cnnBackend:(NSString *)cnnBackend;

- (int)runFrames:(NSArray<NSString *> *)framePaths;

@end

NS_ASSUME_NONNULL_END
