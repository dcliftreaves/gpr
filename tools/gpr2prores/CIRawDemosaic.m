// CIRawDemosaic.m — see header.
//
// Per-frame DNG synthesis used to dominate runtime: every frame built a fresh
// ~91 MB DNG NSData via CIDNGBuilder and handed it to
// [CIRAWFilter filterWithImageData:], which made Apple's DNG parser walk a
// fresh TIFF/IFD on every frame. On 50 MP Z8 frames that path measured
// ~55 ms/frame steady-state.
//
// New path uses [CIRAWFilter filterWithCVPixelBuffer:properties:]:
//
//   * Build one CVPixelBufferPool once at init, format
//     kCVPixelFormatType_14Bayer_<CFA> (IOSurface-backed, Metal-compatible).
//   * Build the metadata properties dict once at init by synthesizing one
//     minimal DNG (via CIDNGBuilder, all camera-profile tags inherited from
//     the template DNG) at the exact buffer dims, then parsing it through
//     ImageIO to obtain a CGImageSource-style properties dict. CIRAWFilter
//     accepts exactly this dict shape and uses it to pick a DNG decoder.
//   * Per frame: acquire a pooled buffer, memcpy bayer into it, hand to
//     CIRAWFilter, render. No DNG construction. No DNG parse.
//
// Measured drop on 50 MP Z8 codec-decimated bayer at UHD output:
//   ~55 ms → ~25 ms (~2.2×). Visual output matches the old path's
//   colorimetry; the new path tends to read slightly brighter because the
//   filter's exposure heuristics see the buffer at its actual bp16-class
//   format instead of a TIFF strip.
//
// Why a *synthesized* probe DNG for the properties dict instead of just
// reading the template file's properties directly?
//   1. NEF / .nef inputs return no kCGImagePropertyDNGDictionary at all
//      from ImageIO. CIRAWFilter then refuses to pick a decoder.
//   2. The template DNG's dims may not match our buffer's dims (we may be
//      consuming codec-decimated bayer at 2× smaller dims than the source).
//      CIRAWFilter cross-checks dims; a mismatch yields outputImage=nil and
//      supportedDecoderVersions={None}.
// Synthesizing a minimal DNG at our buffer's exact dims (while inheriting
// the template's color-science tags via CIDNGBuilder) gives a properties
// dict that is dimensionally consistent and contains a real DNG dict.

#import "CIRawDemosaic.h"
#import "CIDNGBuilder.h"

#import <CoreImage/CoreImage.h>
#import <CoreImage/CIRAWFilter.h>
#import <ImageIO/ImageIO.h>

@implementation CIRawDemosaic {
    id<MTLDevice>     _device;
    CIContext        *_ciContext;
    uint32_t          _outW, _outH;
    uint32_t          _sensorW, _sensorH;
    CGColorSpaceRef   _outCS;

    // Pool of 14Bayer<CFA> pixel buffers, sized to sensorW × sensorH.
    CVPixelBufferPoolRef _bayerPool;
    // Constant metadata dict passed to filterWithCVPixelBuffer:properties:
    // every frame. Same shape CGImageSourceCopyProperties returns for a DNG.
    NSDictionary     *_filterProperties;
}

// Pick the kCVPixelFormatType_14Bayer_* CFA constant matching our enum.
// DNGInfo->cfaPattern: 0=RGGB, 1=GBRG, 2=GRBG, 3=BGGR.
static OSType bayerFormatForCFA(uint32_t cfa) {
    switch (cfa) {
        case 0: return kCVPixelFormatType_14Bayer_RGGB;
        case 1: return kCVPixelFormatType_14Bayer_GBRG;
        case 2: return kCVPixelFormatType_14Bayer_GRBG;
        case 3: return kCVPixelFormatType_14Bayer_BGGR;
        default: return kCVPixelFormatType_14Bayer_RGGB;
    }
}

// Build the per-session properties dict. See file header for the rationale
// behind synthesizing a probe DNG at the buffer's exact dims.
static NSDictionary *buildFilterProperties(const DNGInfo *info,
                                            uint32_t sensorW,
                                            uint32_t sensorH,
                                            NSString *templateDngPath)
{
    NSDictionary *result = nil;
    CIDNGBuilder *probeBuilder = [[CIDNGBuilder alloc] initWithInfo:info
                                                              width:sensorW
                                                             height:sensorH
                                                    templateDngPath:templateDngPath];
    if (!probeBuilder) return nil;

    size_t bayerBytes = (size_t)sensorW * sensorH * 2;
    void *probeBayer = calloc(1, bayerBytes);
    NSData *probeDng = probeBayer ? [probeBuilder dngFromBayerBytes:probeBayer length:bayerBytes] : nil;
    free(probeBayer);
    if (!probeDng) return nil;

    CGImageSourceRef src = CGImageSourceCreateWithData((__bridge CFDataRef)probeDng, NULL);
    if (!src) return nil;
    NSDictionary *file = (__bridge_transfer NSDictionary *)CGImageSourceCopyProperties(src, NULL);
    NSDictionary *idx0 = (__bridge_transfer NSDictionary *)CGImageSourceCopyPropertiesAtIndex(src, 0, NULL);
    CFRelease(src);

    NSMutableDictionary *merged = [NSMutableDictionary dictionary];
    if (file) [merged addEntriesFromDictionary:file];
    if (idx0) {
        for (NSString *k in idx0) {
            if (!merged[k]) merged[k] = idx0[k];
        }
    }
    if (merged.count) result = merged;
    return result;
}

- (nullable instancetype)initWithDevice:(id<MTLDevice>)device
                            sensorWidth:(uint32_t)sensorW
                           sensorHeight:(uint32_t)sensorH
                              outWidth:(uint32_t)outW
                             outHeight:(uint32_t)outH
                                   info:(const DNGInfo *)info
                         templateDngPath:(nullable NSString *)templateDngPath
{
    self = [super init];
    if (!self) return nil;
    _device = device;
    _sensorW = sensorW;
    _sensorH = sensorH;
    _outW = outW;
    _outH = outH;

    // Verify the API path exists on this OS. CIRAWFilter
    // +filterWithCVPixelBuffer:properties: is macOS 12 / iOS 15.
    if (![CIRAWFilter respondsToSelector:@selector(filterWithCVPixelBuffer:properties:)]) {
        fprintf(stderr, "CIRawDemosaic: filterWithCVPixelBuffer:properties: unavailable on this OS\n");
        return nil;
    }

    // Metal-backed CIContext shares textures with our pipeline.
    _ciContext = [CIContext contextWithMTLDevice:device options:@{
        kCIContextCacheIntermediates: @NO,
    }];
    if (!_ciContext) {
        fprintf(stderr, "CIRawDemosaic: failed to create Metal CIContext\n");
        return nil;
    }

    _outCS = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);

    _filterProperties = buildFilterProperties(info, sensorW, sensorH, templateDngPath);
    if (!_filterProperties) {
        fprintf(stderr, "CIRawDemosaic: failed to build filter properties from template %s\n",
                templateDngPath ? [templateDngPath UTF8String] : "(nil)");
        return nil;
    }
    // Sanity check: the dict should include a TIFF dict and a DNG dict.
    if (!_filterProperties[(NSString *)kCGImagePropertyDNGDictionary]) {
        fprintf(stderr, "CIRawDemosaic: WARNING - properties dict has no DNG entry; "
                "CIRAWFilter is likely to reject the buffer\n");
    }

    // Build a CVPixelBufferPool of 14Bayer<CFA> sized to our buffer dims.
    // The 14Bayer formats are the CFA-bearing format that CIRAWFilter's
    // CV-pixel-buffer ingest path consumes; the format-fourcc carries the
    // CFA pattern and CIRAWFilter combines that with the properties dict
    // to select its DNG decoder.
    OSType bayerFormat = bayerFormatForCFA(info->cfaPattern);
    NSDictionary *pixelAttrs = @{
        (NSString *)kCVPixelBufferPixelFormatTypeKey: @(bayerFormat),
        (NSString *)kCVPixelBufferWidthKey: @(sensorW),
        (NSString *)kCVPixelBufferHeightKey: @(sensorH),
        (NSString *)kCVPixelBufferIOSurfacePropertiesKey: @{},
        (NSString *)kCVPixelBufferMetalCompatibilityKey: @YES,
    };
    NSDictionary *poolAttrs = @{
        (NSString *)kCVPixelBufferPoolMinimumBufferCountKey: @(2),
    };
    CVReturn r = CVPixelBufferPoolCreate(NULL,
                                          (__bridge CFDictionaryRef)poolAttrs,
                                          (__bridge CFDictionaryRef)pixelAttrs,
                                          &_bayerPool);
    if (r != kCVReturnSuccess || !_bayerPool) {
        fprintf(stderr, "CIRawDemosaic: CVPixelBufferPoolCreate failed (r=%d)\n", r);
        return nil;
    }

    fprintf(stderr,
            "CIRawDemosaic: ready (%ux%u → %ux%u via filterWithCVPixelBuffer, "
            "fmt='%c%c%c%c' cfa=%u black=%u white=%u)\n",
            sensorW, sensorH, outW, outH,
            (char)((bayerFormat >> 24) & 0xff), (char)((bayerFormat >> 16) & 0xff),
            (char)((bayerFormat >> 8) & 0xff),  (char)(bayerFormat & 0xff),
            info->cfaPattern, info->blackLevel, info->whiteLevel);

    return self;
}

- (void)dealloc {
    if (_outCS) CGColorSpaceRelease(_outCS);
    if (_bayerPool) {
        CVPixelBufferPoolRelease(_bayerPool);
        _bayerPool = NULL;
    }
}

- (void)encode:(nullable id<MTLCommandBuffer>)cb
         bayer:(const uint16_t *)bayer
         width:(uint32_t)w
        height:(uint32_t)h
outPixelBuffer:(CVPixelBufferRef)pb
{
    (void)cb;  // CIContext drives its own Metal submissions.

    if (w != _sensorW || h != _sensorH) {
        fprintf(stderr, "CIRawDemosaic: bayer dims %ux%u differ from configured %ux%u\n",
                w, h, _sensorW, _sensorH);
        return;
    }

    // 1) Pull a pooled Bayer buffer.
    CVPixelBufferRef bayerPB = NULL;
    CVReturn r = CVPixelBufferPoolCreatePixelBuffer(NULL, _bayerPool, &bayerPB);
    if (r != kCVReturnSuccess || !bayerPB) {
        fprintf(stderr, "CIRawDemosaic: pool alloc failed (r=%d)\n", r);
        return;
    }

    // 2) Copy the bayer plane in (single-plane, 16 bits/pixel).
    CVPixelBufferLockBaseAddress(bayerPB, 0);
    uint8_t *dst = (uint8_t *)CVPixelBufferGetBaseAddress(bayerPB);
    size_t dstStride = CVPixelBufferGetBytesPerRow(bayerPB);
    size_t srcStride = (size_t)w * 2;
    if (dstStride == srcStride) {
        memcpy(dst, bayer, (size_t)h * srcStride);
    } else {
        for (uint32_t y = 0; y < h; y++) {
            memcpy(dst + (size_t)y * dstStride,
                   ((const uint8_t *)bayer) + (size_t)y * srcStride,
                   srcStride);
        }
    }
    CVPixelBufferUnlockBaseAddress(bayerPB, 0);

    // 3) Hand to CIRAWFilter. No DNG construction, no DNG parse.
    CIRAWFilter *raw = [CIRAWFilter filterWithCVPixelBuffer:bayerPB
                                                 properties:_filterProperties];
    if (!raw) {
        fprintf(stderr, "CIRawDemosaic: filterWithCVPixelBuffer returned nil\n");
        CVPixelBufferRelease(bayerPB);
        return;
    }

    // Fast-path settings: draft mode, no denoise/sharpen/etc.
    CGFloat scale = (CGFloat)_outW / (CGFloat)w;
    if (scale <= 0 || scale > 1.0) scale = 1.0;  // CIRAWFilter clamps to (0,1]
    raw.scaleFactor = (float)scale;
    raw.draftModeEnabled = YES;
    raw.luminanceNoiseReductionAmount = 0.0f;
    raw.colorNoiseReductionAmount = 0.0f;
    raw.sharpnessAmount = 0.0f;
    raw.detailAmount = 0.0f;
    raw.moireReductionAmount = 0.0f;
    raw.localToneMapAmount = 0.0f;

    CIImage *image = raw.outputImage;
    if (!image) {
        fprintf(stderr, "CIRawDemosaic: outputImage nil\n");
        CVPixelBufferRelease(bayerPB);
        return;
    }

    // 4) Translate to origin, then scale-to-fit + center-crop to (outW, outH).
    CGRect extent = image.extent;
    CGAffineTransform xform = CGAffineTransformMakeTranslation(-extent.origin.x, -extent.origin.y);
    CIImage *moved = [image imageByApplyingTransform:xform];

    CGRect movedExtent = moved.extent;
    CGFloat sx = (CGFloat)_outW / movedExtent.size.width;
    CGFloat sy = (CGFloat)_outH / movedExtent.size.height;
    CGFloat finalScale = MAX(sx, sy);
    CIImage *scaled = moved;
    if (fabs(finalScale - 1.0) > 1e-4) {
        scaled = [moved imageByApplyingTransform:CGAffineTransformMakeScale(finalScale, finalScale)];
    }
    CGRect scaledExtent = scaled.extent;
    CGFloat cropX = (scaledExtent.size.width  - (CGFloat)_outW) * 0.5;
    CGFloat cropY = (scaledExtent.size.height - (CGFloat)_outH) * 0.5;
    CIImage *cropped = [scaled imageByApplyingTransform:CGAffineTransformMakeTranslation(-cropX, -cropY)];
    cropped = [cropped imageByCroppingToRect:CGRectMake(0, 0, _outW, _outH)];

    // 5) Render directly into the caller's CVPixelBuffer (IOSurface-backed).
    [_ciContext render:cropped
        toCVPixelBuffer:pb
                 bounds:CGRectMake(0, 0, _outW, _outH)
             colorSpace:_outCS];

    CVPixelBufferRelease(bayerPB);
}

@end
