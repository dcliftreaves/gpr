// GPRCodec.h — wraps the fused encoder + decoder (reusable context).

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface GPRCodec : NSObject

- (nullable instancetype)initWithWidth:(int)width
                                height:(int)height
                          pixelFormat:(int)pixelFormat
                              quality:(int)quality;

// Encode one frame. Returns 0 on success; vc5_out/vc5_size point into the
// context-owned output buffer (do NOT free).
- (int)encodeRawBayer:(const uint16_t *)bayer
                bytes:(size_t)bytes
              vc5Out:(uint8_t **)vc5Out
             vc5Size:(size_t *)vc5Size;

// Decode an encoded blob. outBayer must hold at least
// (out_width * out_height * 2) bytes worth of uint16. outPitch is in bytes.
- (int)decode:(const uint8_t *)enc
         size:(size_t)size
     outBayer:(uint16_t *)outBayer
     outPitch:(size_t)outPitch
     outWidth:(int *)outWidth
    outHeight:(int *)outHeight;

@end

NS_ASSUME_NONNULL_END
