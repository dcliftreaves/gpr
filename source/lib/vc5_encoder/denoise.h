/*! @file denoise.h
 *
 *  @brief Wavelet-domain noise estimation and soft thresholding for compression.
 *
 *  Reduces entropy in highpass wavelet bands by removing coefficients below
 *  the noise floor.  Uses sensor-calibrated noise parameters (DNG NoiseProfile)
 *  when available, falling back to robust MAD estimation from image data.
 *
 *  References:
 *    Donoho & Johnstone (1994) - "Ideal spatial adaptation by wavelet shrinkage"
 *    Goesele & Heidrich (2001) - "Entropy-Based Dark Frame Subtraction"
 *
 *  (C) Copyright 2018 GoPro Inc (http://gopro.com/).
 *
 *  Licensed under either:
 *  - Apache License, Version 2.0, http://www.apache.org/licenses/LICENSE-2.0
 *  - MIT license, http://opensource.org/licenses/MIT
 *  at your option.
 */

#ifndef DENOISE_H
#define DENOISE_H

#include "common.h"

#ifdef __cplusplus
extern "C" {
#endif

/*!
    @brief Denoise all highpass bands of one channel's wavelet transform

    Estimates noise sigma (from calibration or MAD fallback), then applies
    soft thresholding to all 9 highpass subbands (LH/HL/HH × 3 levels).
    The lowpass band is never modified.

    @param transform        Channel's wavelet transform (modified in-place)
    @param strength         User threshold multiplier (0.0–1.0, default 1.0)
    @param noise_scale      DNG NoiseProfile scale (0 = use MAD fallback)
    @param noise_offset     DNG NoiseProfile offset
    @return                 Estimated noise sigma for this channel
*/
double DenoiseTransform(TRANSFORM *transform, double strength,
                        double noise_scale, double noise_offset);

/*!
    @brief Estimate noise sigma from HH band using MAD (fallback)

    Robust estimator: sigma = median(|coefficients|) / 0.6745

    @param data     Band coefficient data
    @param width    Band width in pixels
    @param height   Band height in rows
    @param pitch    Row stride in bytes
    @return         Estimated noise sigma
*/
double EstimateNoiseSigma(const PIXEL *data, DIMENSION width,
                          DIMENSION height, DIMENSION pitch);

/*!
    @brief Compute noise sigma from calibrated Poisson-Gaussian model

    Uses the DNG NoiseProfile parameters with the lowpass band mean
    as the signal level: sigma = sqrt(noise_scale * mean + noise_offset)

    @param lowpass_data     Lowpass band data (signal reference)
    @param width            Band width
    @param height           Band height
    @param pitch            Row stride in bytes
    @param noise_scale      DNG NoiseProfile scale parameter
    @param noise_offset     DNG NoiseProfile offset parameter
    @return                 Calibrated noise sigma
*/
double CalibratedNoiseSigma(const PIXEL *lowpass_data, DIMENSION width,
                            DIMENSION height, DIMENSION pitch,
                            double noise_scale, double noise_offset);

/*!
    @brief Apply soft thresholding to a wavelet band in-place

    |c| <= T  →  0
    |c| >  T  →  sign(c) * (|c| - T)

    @param data         Band data (modified in-place)
    @param width        Band width
    @param height       Band height
    @param pitch        Row stride in bytes
    @param threshold    Absolute threshold value
*/
void SoftThresholdBand(PIXEL *data, DIMENSION width, DIMENSION height,
                       DIMENSION pitch, double threshold);

#ifdef __cplusplus
}
#endif

#endif /* DENOISE_H */
