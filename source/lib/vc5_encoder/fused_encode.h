/*! @file fused_encode.h
 *
 *  @brief Fused encoder: Bayer→Wavelet→Quantize→FreqCount in one streaming pass.
 *
 *  Replaces the 4-stage serial pipeline with a 2-pass fused design:
 *  Pass 1: Stream Bayer pixels through log curve → horizontal filter → vertical
 *          filter + quantize, counting ANS frequencies inline.
 *  Pass 2: rANS encode using pre-counted frequencies.
 *
 *  Eliminates 44MB of intermediate component arrays (for Z8 45MP).
 *  Designed for GoPro ARM (Cortex-A78), testable on Mac ARM64.
 *
 *  (C) Copyright 2018 GoPro Inc. Licensed under Apache-2.0 or MIT.
 */

#ifndef FUSED_ENCODE_H
#define FUSED_ENCODE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*!
    @brief Fused encode: raw Bayer pixels → VC5 bitstream.

    Two-pass design:
    Pass 1: Fused unpack→wavelet→quantize→frequency count (no intermediate arrays)
    Pass 2: rANS encode using counted frequencies

    @param raw_bayer    Raw Bayer pixel data (uint16_t interleaved)
    @param raw_size     Size of raw data in bytes
    @param width        Image width in pixels
    @param height       Image height in pixels
    @param pixel_format 0=RGGB12, 1=RGGB14, 2=GBRG12, 3=GBRG14, 4=RGGB16, 5=GBRG16
    @param quality      Quality preset (0-8, default 3 = Filmscan-1)
    @param vc5_out      Output: allocated VC5 bitstream (caller must free)
    @param vc5_size     Output: size of VC5 bitstream
    @return 0 on success, -1 on error
*/
int gpr_encode_fused(
    const uint8_t *raw_bayer,
    size_t raw_size,
    int width, int height,
    int pixel_format,
    int quality,
    uint8_t **vc5_out,
    size_t *vc5_size
);

#ifdef __cplusplus
}
#endif

#endif /* FUSED_ENCODE_H */
