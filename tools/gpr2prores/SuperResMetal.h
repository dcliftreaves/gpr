// SuperResMetal.h — MPSGraph + optional hand-rolled Metal NAFBlock super-res CNN.
//
// Drop-in replacement for SuperResCNN that uses MPSGraph (and optionally
// validated Metal kernels for the hot NAFBlocks at C=16/32/64) instead of
// CoreML's MLModel. The F backbone (variant=F, width=16, depth=3) is hard-
// coded; weights are loaded from a directory of fp16 .bin blobs produced by
// extract_F_weights.py.
//
// Input convention (Bayer):  (inW × inH) uint16 raw mosaic
// CNN input planes:          (1, 4, inH/2, inW/2) fp16 (R, Gr, Gb, B)
// CNN output (residual):     (1, 4, inH, inW) fp16
// Final out (after baseline + scale + clamp + re-bayer):  (outW × outH) uint16
//
// The class allocates persistent MTLBuffers for weights and feeds + receives
// fp16 tensors from MPSGraph using NHWC layout.

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(NSInteger, SuperResMetalBackend) {
    // All ops in MPSGraph (default). Most reliable.
    SuperResMetalBackendMPSGraph = 0,
    // Hybrid: MPSGraph for intro/down/up/middle/SR head; Metal kernels for
    // NAFBlocks at C=16/32/64 (uses validated kernels from dering_proto_v2).
    SuperResMetalBackendHybrid = 1,
};

@interface SuperResMetal : NSObject

// Loads weights from `weightsDir` (a directory containing intro_weight.bin etc.
// produced by extract_F_weights.py). The (inH, inW) are *padded* CNN plane dims
// — the network's spatial input — and must be multiples of 8.
- (nullable instancetype)initWithWeightsDir:(NSString *)weightsDir
                                     device:(id<MTLDevice>)device
                                  inPlaneH:(uint32_t)inPlaneH
                                  inPlaneW:(uint32_t)inPlaneW
                                    backend:(SuperResMetalBackend)backend;

// Same signature as SuperResCNN. inBayer is (inW * inH) uint16; outBayer
// (outW * outH) uint16. The CNN runs on inH/2 × inW/2 planes and produces
// outH × outW Bayer output (typically 2× the input).
// Returns 0 on success.
- (int)runOnBayer:(const uint16_t *)inBayer
            width:(uint32_t)inW height:(uint32_t)inH
         outBayer:(uint16_t *)outBayer
         outWidth:(uint32_t)outW
        outHeight:(uint32_t)outH
       blackLevel:(uint32_t)blackLevel
       whiteLevel:(uint32_t)whiteLevel;

@end

NS_ASSUME_NONNULL_END
