// CIRawDemosaic.m — see header.

#import "CIRawDemosaic.h"
#import "CIDNGBuilder.h"

#import <CoreImage/CoreImage.h>
#import <CoreImage/CIRAWFilter.h>

@implementation CIRawDemosaic {
    id<MTLDevice>     _device;
    CIContext        *_ciContext;
    CIDNGBuilder     *_builder;
    uint32_t          _outW, _outH;
    uint32_t          _sensorW, _sensorH;
    CGColorSpaceRef   _outCS;
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

    _builder = [[CIDNGBuilder alloc] initWithInfo:info
                                            width:sensorW
                                           height:sensorH
                                  templateDngPath:templateDngPath];
    if (!_builder) return nil;

    // Metal-backed CIContext shares textures with our pipeline.
    _ciContext = [CIContext contextWithMTLDevice:device options:@{
        kCIContextCacheIntermediates: @NO,
    }];
    if (!_ciContext) {
        fprintf(stderr, "CIRawDemosaic: failed to create Metal CIContext\n");
        return nil;
    }
    fprintf(stderr, "CIRawDemosaic: ready (%ux%u → %ux%u UHD via CIRAWFilter)\n",
            sensorW, sensorH, outW, outH);

    _outCS = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    return self;
}

- (void)dealloc {
    if (_outCS) CGColorSpaceRelease(_outCS);
}

- (void)encode:(nullable id<MTLCommandBuffer>)cb
         bayer:(const uint16_t *)bayer
         width:(uint32_t)w
        height:(uint32_t)h
outPixelBuffer:(CVPixelBufferRef)pb
{
    (void)cb;  // We use CIContext-driven Metal submissions, not the caller's cb.

    if (w != _sensorW || h != _sensorH) {
        fprintf(stderr, "CIRawDemosaic: bayer dims %ux%u differ from configured %ux%u\n",
                w, h, _sensorW, _sensorH);
        return;
    }

    size_t bayerBytes = (size_t)w * h * 2;
    NSData *dng = [_builder dngFromBayerBytes:bayer length:bayerBytes];
    if (!dng) {
        fprintf(stderr, "CIRawDemosaic: builder returned nil\n");
        return;
    }
    // Set GPR2PRORES_DUMP_CIDNG=/some/path.dng to dump the first synth DNG.
    static int _dumped = 0;
    if (!_dumped) {
        _dumped = 1;
        const char *dumpPath = getenv("GPR2PRORES_DUMP_CIDNG");
        if (dumpPath) {
            [dng writeToFile:@(dumpPath) atomically:NO];
            fprintf(stderr, "CIRawDemosaic: dumped first synth DNG to %s (%lu bytes)\n",
                    dumpPath, (unsigned long)dng.length);
        }
    }

    // Compute inputScaleFactor so the rendered output approximately matches
    // (_outW, _outH). CIRAWFilter scales with inputScaleFactor relative to
    // native dims. Use width-based ratio.
    CGFloat scale = (CGFloat)_outW / (CGFloat)w;
    if (scale <= 0) scale = 1.0;

    CIRAWFilter *raw = [CIRAWFilter filterWithImageData:dng
                                         identifierHint:@"com.adobe.raw-image"];
    if (!raw) {
        // Try alternative identifier hint
        raw = [CIRAWFilter filterWithImageData:dng identifierHint:@"public.tiff"];
    }
    if (!raw) {
        fprintf(stderr, "CIRawDemosaic: CIRAWFilter filterWithImageData returned nil\n");
        return;
    }

    // Configure for fast path: draft mode, no denoise/sharpen.
    raw.scaleFactor = scale;
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
        return;
    }

    // Compose to exactly (outW, outH): translate to origin then crop / scale.
    CGRect extent = image.extent;
    // If extent is larger or smaller, fit width and crop (preserving aspect),
    // then translate top-left to (0,0).
    CGAffineTransform xform = CGAffineTransformMakeTranslation(-extent.origin.x, -extent.origin.y);
    CIImage *moved = [image imageByApplyingTransform:xform];

    // If dims don't match exactly, scale to match outW preserving aspect, then crop centered.
    CGRect movedExtent = moved.extent;
    CGFloat sx = (CGFloat)_outW / movedExtent.size.width;
    CGFloat sy = (CGFloat)_outH / movedExtent.size.height;
    // Use the larger scale to cover, then crop. Or simpler: scale to fit width
    // exactly; let height crop naturally to _outH from the centre.
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

    // Render directly into the caller's CVPixelBuffer (IOSurface-backed).
    [_ciContext render:cropped
        toCVPixelBuffer:pb
                 bounds:CGRectMake(0, 0, _outW, _outH)
             colorSpace:_outCS];
}

@end
