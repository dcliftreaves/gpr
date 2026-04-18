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

/*! Quickselect partition with median-of-three pivot for O(N) median finding */
static int partition(int32_t *arr, int lo, int hi)
{
    /* Median-of-three pivot to avoid O(N²) on sorted data */
    int mid = lo + (hi - lo) / 2;
    if (arr[lo] > arr[mid]) { int32_t t = arr[lo]; arr[lo] = arr[mid]; arr[mid] = t; }
    if (arr[lo] > arr[hi])  { int32_t t = arr[lo]; arr[lo] = arr[hi]; arr[hi] = t; }
    if (arr[mid] > arr[hi]) { int32_t t = arr[mid]; arr[mid] = arr[hi]; arr[hi] = t; }
    /* Swap median to hi-1 position as pivot */
    { int32_t t = arr[mid]; arr[mid] = arr[hi]; arr[hi] = t; }

    int32_t pivot = arr[hi];
    int i = lo;
    for (int j = lo; j < hi; j++)
    {
        if (arr[j] <= pivot)
        {
            int32_t t = arr[i]; arr[i] = arr[j]; arr[j] = t;
            i++;
        }
    }
    { int32_t t = arr[i]; arr[i] = arr[hi]; arr[hi] = t; }
    return i;
}

/*! O(N) average-case median via quickselect */
static int32_t quickselect_median(int32_t *arr, int n)
{
    int k = n / 2;
    int lo = 0, hi = n - 1;
    while (lo < hi)
    {
        int p = partition(arr, lo, hi);
        if (p == k) return arr[k];
        else if (p < k) lo = p + 1;
        else hi = p - 1;
    }
    return arr[lo];
}

/*! Maximum samples for MAD estimation (limits memory and compute).
    10K samples gives excellent statistical accuracy for median estimation. */
#define MAX_MAD_SAMPLES 10000

double EstimateNoiseSigma(const PIXEL *data, DIMENSION width,
                          DIMENSION height, DIMENSION pitch)
{
    int total = (int)width * (int)height;
    if (total <= 0) return 0.0;

    /* Subsample for large bands to keep MAD estimation fast */
    int step = 1;
    int count = total;
    if (total > MAX_MAD_SAMPLES)
    {
        step = total / MAX_MAD_SAMPLES;
        count = MAX_MAD_SAMPLES;
    }

    int32_t *abs_vals = (int32_t *)malloc(count * sizeof(int32_t));
    if (abs_vals == NULL) return 0.0;

    int pitch_pixels = pitch / sizeof(PIXEL);
    int idx = 0;
    int sample_idx = 0;

    for (int row = 0; row < (int)height && idx < count; row++)
    {
        const PIXEL *row_ptr = data + row * pitch_pixels;
        for (int col = 0; col < (int)width && idx < count; col++)
        {
            if (sample_idx % step == 0)
            {
                int32_t v = row_ptr[col];
                abs_vals[idx++] = (v < 0) ? -v : v;
            }
            sample_idx++;
        }
    }

    double median = (double)quickselect_median(abs_vals, idx);
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
    double global_sigma;

    /* Prefer calibrated noise model when DNG NoiseProfile is available */
    if (noise_scale > 0.0)
    {
        global_sigma = CalibratedNoiseSigma(finest->data[LL_BAND],
                                            finest->width, finest->height,
                                            finest->pitch,
                                            noise_scale, noise_offset);
    }
    else
    {
        /* Fallback: estimate from finest HH band using MAD */
        global_sigma = EstimateNoiseSigma(finest->data[HH_BAND],
                                          finest->width, finest->height,
                                          finest->pitch);
    }

    if (global_sigma <= 0.0) return 0.0;

    /* Per-band adaptive thresholding: estimate sigma individually per band
       for more accurate noise separation. Use global sigma as fallback. */
    for (int level = 0; level < MAX_WAVELET_COUNT; level++)
    {
        WAVELET *wavelet = transform->wavelet[level];
        int N = (int)wavelet->width * (int)wavelet->height;
        if (N <= 0) continue;

        for (int band = LH_BAND; band <= HH_BAND; band++)
        {
            /* Estimate per-band sigma using MAD (more accurate than global) */
            double band_sigma = EstimateNoiseSigma(wavelet->data[band],
                                                    wavelet->width,
                                                    wavelet->height,
                                                    wavelet->pitch);

            /* Use per-band estimate if reasonable, else fall back to global scaled */
            if (band_sigma <= 0.0)
                band_sigma = global_sigma * level_scale[level];

            double T = band_sigma * sqrt(2.0 * log((double)N)) * strength;

            SoftThresholdBand(wavelet->data[band],
                              wavelet->width, wavelet->height,
                              wavelet->pitch, T);
        }
    }

    return global_sigma;
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
