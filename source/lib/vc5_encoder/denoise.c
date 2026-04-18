/*! @file denoise.c
 *
 *  @brief Wavelet-domain noise estimation and soft thresholding.
 *
 *  (C) Copyright 2018 GoPro Inc (http://gopro.com/).
 *
 *  Licensed under either:
 *  - Apache License, Version 2.0, http://www.apache.org/licenses/LICENSE-2.0
 *  - MIT license, http://opensource.org/licenses/MIT
 *  at your option.
 */

#include "headers.h"
#include "denoise.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

/*! MAD-to-sigma normalization: 1 / 0.6745 (Donoho & Johnstone) */
#define MAD_SIGMA_FACTOR 1.4826

/*! Noise energy scaling per wavelet level (halves at each coarser scale) */
static const double level_scale[MAX_WAVELET_COUNT] = {1.0, 0.5, 0.25};

static int compare_int32(const void *a, const void *b)
{
    int32_t va = *(const int32_t *)a;
    int32_t vb = *(const int32_t *)b;
    return (va > vb) - (va < vb);
}

double EstimateNoiseSigma(const PIXEL *data, DIMENSION width,
                          DIMENSION height, DIMENSION pitch)
{
    int count = (int)width * (int)height;
    if (count <= 0) return 0.0;

    int32_t *abs_vals = (int32_t *)malloc(count * sizeof(int32_t));
    if (abs_vals == NULL) return 0.0;

    int pitch_pixels = pitch / sizeof(PIXEL);
    int idx = 0;

    for (int row = 0; row < height; row++)
    {
        const PIXEL *row_ptr = data + row * pitch_pixels;
        for (int col = 0; col < width; col++)
        {
            int32_t v = row_ptr[col];
            abs_vals[idx++] = (v < 0) ? -v : v;
        }
    }

    qsort(abs_vals, count, sizeof(int32_t), compare_int32);

    double median;
    if (count % 2 == 0)
        median = (abs_vals[count / 2 - 1] + abs_vals[count / 2]) / 2.0;
    else
        median = abs_vals[count / 2];

    free(abs_vals);

    return median * MAD_SIGMA_FACTOR;
}

double CalibratedNoiseSigma(const PIXEL *lowpass_data, DIMENSION width,
                            DIMENSION height, DIMENSION pitch,
                            double noise_scale, double noise_offset)
{
    int count = (int)width * (int)height;
    if (count <= 0) return 0.0;

    int pitch_pixels = pitch / sizeof(PIXEL);
    double sum = 0.0;

    for (int row = 0; row < height; row++)
    {
        const PIXEL *row_ptr = lowpass_data + row * pitch_pixels;
        for (int col = 0; col < width; col++)
            sum += (double)row_ptr[col];
    }

    double mean_signal = sum / count;
    double variance = noise_scale * mean_signal + noise_offset;

    return (variance > 0.0) ? sqrt(variance) : 0.0;
}

void SoftThresholdBand(PIXEL *data, DIMENSION width, DIMENSION height,
                       DIMENSION pitch, double threshold)
{
    int32_t T = (int32_t)(threshold + 0.5);
    if (T <= 0) return;

    int pitch_pixels = pitch / sizeof(PIXEL);

    for (int row = 0; row < height; row++)
    {
        PIXEL *row_ptr = data + row * pitch_pixels;
        for (int col = 0; col < width; col++)
        {
            int32_t val = row_ptr[col];
            int32_t abs_val = (val < 0) ? -val : val;

            if (abs_val <= T)
            {
                row_ptr[col] = 0;
            }
            else
            {
                int32_t shrunk = abs_val - T;
                row_ptr[col] = (val > 0) ? shrunk : -shrunk;
            }
        }
    }
}

double DenoiseTransform(TRANSFORM *transform, double strength,
                        double noise_scale, double noise_offset)
{
    if (strength <= 0.0) return 0.0;

    WAVELET *finest = transform->wavelet[0];
    double sigma;

    /* Prefer calibrated noise model when DNG NoiseProfile is available */
    if (noise_scale > 0.0)
    {
        sigma = CalibratedNoiseSigma(finest->data[LL_BAND],
                                     finest->width, finest->height,
                                     finest->pitch,
                                     noise_scale, noise_offset);
    }
    else
    {
        /* Fallback: estimate from finest HH band using MAD */
        sigma = EstimateNoiseSigma(finest->data[HH_BAND],
                                   finest->width, finest->height,
                                   finest->pitch);
    }

    if (sigma <= 0.0) return 0.0;

    /* Soft-threshold all highpass bands at all wavelet levels */
    for (int level = 0; level < MAX_WAVELET_COUNT; level++)
    {
        WAVELET *wavelet = transform->wavelet[level];
        int N = (int)wavelet->width * (int)wavelet->height;

        double T_base = sigma * sqrt(2.0 * log((double)N));
        double T = T_base * level_scale[level] * strength;

        /* Threshold LH, HL, HH bands — never touch LL */
        for (int band = LH_BAND; band <= HH_BAND; band++)
        {
            SoftThresholdBand(wavelet->data[band],
                              wavelet->width, wavelet->height,
                              wavelet->pitch, T);
        }
    }

    return sigma;
}
