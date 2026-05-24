// GPRCodec.m — thin wrapper around the GPR fused encoder + decoder.

#import "GPRCodec.h"

// External C symbols from libvc5_encoder.a / libvc5_decoder.a
typedef struct FUSED_ENCODER FUSED_ENCODER;
extern FUSED_ENCODER *gpr_encode_fused_create(int w, int h, int pf, int q);
extern int gpr_encode_fused_frame(FUSED_ENCODER *ctx, const uint8_t *raw,
                                   size_t sz, uint8_t **out, size_t *out_sz);
extern void gpr_encode_fused_destroy(FUSED_ENCODER *ctx);
extern int gpr_decode_fused(const uint8_t *enc, size_t enc_size,
                             uint16_t *bayer_out, size_t bayer_pitch_bytes,
                             int *out_width, int *out_height);

@implementation GPRCodec {
    FUSED_ENCODER *_ctx;
}

- (nullable instancetype)initWithWidth:(int)width
                                height:(int)height
                          pixelFormat:(int)pixelFormat
                              quality:(int)quality
{
    self = [super init];
    if (!self) return nil;
    _ctx = gpr_encode_fused_create(width, height, pixelFormat, quality);
    if (!_ctx) {
        fprintf(stderr, "GPRCodec: encoder create failed\n");
        return nil;
    }
    fprintf(stderr, "GPRCodec: %dx%d pf=%d q=%d\n", width, height, pixelFormat, quality);
    return self;
}

- (void)dealloc {
    if (_ctx) gpr_encode_fused_destroy(_ctx);
}

- (int)encodeRawBayer:(const uint16_t *)bayer
                bytes:(size_t)bytes
              vc5Out:(uint8_t **)vc5Out
             vc5Size:(size_t *)vc5Size
{
    return gpr_encode_fused_frame(_ctx, (const uint8_t *)bayer, bytes, vc5Out, vc5Size);
}

- (int)decode:(const uint8_t *)enc
         size:(size_t)size
     outBayer:(uint16_t *)outBayer
     outPitch:(size_t)outPitch
     outWidth:(int *)outWidth
    outHeight:(int *)outHeight
{
    return gpr_decode_fused(enc, size, outBayer, outPitch, outWidth, outHeight);
}

@end
