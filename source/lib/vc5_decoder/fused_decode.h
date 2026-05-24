/*! @file fused_decode.h
 *
 *  @brief Decoder for the fused encoder's self-describing wrapper format.
 *
 *  Pairs with the encoder in vc5_encoder/fused_encode.{c,h}. Reads the
 *  FUSED_HEADER + band manifest, decodes each rANS band stream via
 *  jans_decode_band_x4, inverse-quantizes and inverse-transforms 3
 *  levels of wavelet per channel, reverses the 4-channel color
 *  transform, applies the inverse log curve, and packs the result
 *  back into an RGGB / GBRG Bayer plane.
 *
 *  Only multi-level streams have enough information to reconstruct;
 *  single-level streams have no preserved lowpass and so cannot be
 *  decoded (the function returns -ENOTSUP in that case).
 */
#ifndef FUSED_DECODE_H
#define FUSED_DECODE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Decode a fused-encoder wrapped output back to a Bayer plane.
   enc/enc_size:   the wrapper format produced by gpr_encode_fused().
   bayer_out:      caller-allocated uint16 buffer of size
                   width * height * 2 bytes.
   bayer_pitch:    row stride in bytes (typically width * 2).
   out_width/out_height: returned via pointers (== header.width/height).
   Returns 0 on success, negative errno-like on failure. */
int gpr_decode_fused(const uint8_t *enc, size_t enc_size,
                     uint16_t *bayer_out, size_t bayer_pitch_bytes,
                     int *out_width, int *out_height);

#ifdef __cplusplus
}
#endif

#endif /* FUSED_DECODE_H */
