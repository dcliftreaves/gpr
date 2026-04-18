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

/*! Simple xorshift32 PRNG for reproducible noise generation */
static uint32_t xorshift32(uint32_t *state)
{
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

/*! Convert uniform uint32 to approximate Gaussian via Box-Muller-like transform.
    Uses the simple (u1 + u2 + ... + u12 - 6) / 12 approximation (CLT). */
static double prng_gaussian(uint32_t *state)
{
    double sum = 0.0;
    for (int i = 0; i < 12; i++)
        sum += (double)xorshift32(state) / 4294967296.0;
    return sum - 6.0;
}

void AddNoiseFromModel(PIXEL *data, DIMENSION width, DIMENSION height,
                       DIMENSION pitch, double sigma, uint32_t seed, int band_id)
{
    if (sigma <= 0.0) return;

    /* Mix seed with band_id for unique noise per band */
    uint32_t state = seed ^ ((uint32_t)band_id * 2654435761u);
    if (state == 0) state = 1;

    int pitch_pixels = pitch / sizeof(PIXEL);
    int32_t isigma = (int32_t)(sigma + 0.5);
    if (isigma <= 0) return;

    for (int row = 0; row < height; row++)
    {
        PIXEL *row_ptr = data + row * pitch_pixels;
        for (int col = 0; col < width; col++)
        {
            double noise = prng_gaussian(&state) * sigma;
            row_ptr[col] += (int32_t)(noise + (noise >= 0 ? 0.5 : -0.5));
        }
    }
}

void AnscombeForward(COMPONENT_VALUE *data, DIMENSION width, DIMENSION height,
                     size_t pitch, double alpha, double sigma_sq)
{
    if (alpha <= 0.0) return;

    double inv_alpha = 2.0 / alpha;
    double offset = 3.0 / 8.0 * alpha * alpha + sigma_sq;
    int pitch_elems = (int)(pitch / sizeof(COMPONENT_VALUE));

    for (int row = 0; row < height; row++)
    {
        COMPONENT_VALUE *row_ptr = data + row * pitch_elems;
        for (int col = 0; col < width; col++)
        {
            double x = (double)row_ptr[col];
            double arg = alpha * x + offset;
            double stabilized = (arg > 0.0) ? inv_alpha * sqrt(arg) : 0.0;
            row_ptr[col] = (COMPONENT_VALUE)(stabilized + 0.5);
        }
    }
}

void AnscombeInverse(COMPONENT_VALUE *data, DIMENSION width, DIMENSION height,
                     size_t pitch, double alpha, double sigma_sq)
{
    if (alpha <= 0.0) return;

    double half_alpha = alpha / 2.0;
    double offset = 3.0 / 8.0 * alpha * alpha + sigma_sq;
    int pitch_elems = (int)(pitch / sizeof(COMPONENT_VALUE));

    for (int row = 0; row < height; row++)
    {
        COMPONENT_VALUE *row_ptr = data + row * pitch_elems;
        for (int col = 0; col < width; col++)
        {
            double d = (double)row_ptr[col];
            /* Exact unbiased inverse (asymptotic): x = (d/c)^2 - offset/alpha
               where c = 2/alpha, so (d/c)^2 = (d*alpha/2)^2 = d^2*alpha^2/4
               Then x = d^2*alpha/4 - 3/8*alpha - sigma^2/alpha
               With bias correction: subtract 1/(4*alpha) per Makitalo & Foi (2011) */
            double val = half_alpha * d;
            val = val * val;                     /* (alpha*d/2)^2 */
            val = (val - offset) / alpha;        /* invert: x = ((c*d)^2 - offset) / alpha */
            val -= 1.0 / (4.0 * alpha);          /* bias correction */
            row_ptr[col] = (COMPONENT_VALUE)(val + 0.5);
        }
    }
}
