/*! @file noise_model.c
 *
 *  @brief Fixed-pattern noise model implementation.
 *
 *  (C) Copyright 2018 GoPro Inc (http://gopro.com/).
 *  Licensed under Apache-2.0 or MIT at your option.
 */

#include "noise_model.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

void fpn_model_init(fpn_model *model)
{
    memset(model, 0, sizeof(fpn_model));
    for (int ch = 0; ch < 4; ch++)
    {
        model->row_offsets[ch] = NULL;
        model->col_offsets[ch] = NULL;
    }
    model->precomputed_map = NULL;
}

void fpn_model_free(fpn_model *model)
{
    for (int ch = 0; ch < 4; ch++)
    {
        free(model->row_offsets[ch]);
        free(model->col_offsets[ch]);
        model->row_offsets[ch] = NULL;
        model->col_offsets[ch] = NULL;
    }
    free(model->precomputed_map);
    model->precomputed_map = NULL;
}

/*! Precompute the full-resolution FPN map for fast subtraction/addition.
    Evaluates polynomial + row/col offsets once per pixel at load time. */
static void fpn_precompute(fpn_model *model)
{
    if (!model->valid || model->width <= 0 || model->height <= 0) return;

    size_t npixels = (size_t)model->width * model->height;
    model->precomputed_map = (int16_t *)calloc(npixels, sizeof(int16_t));
    if (!model->precomputed_map) return;

    for (int row = 0; row < model->height; row++)
    {
        for (int col = 0; col < model->width; col++)
        {
            double fpn = fpn_model_eval(model, row, col);
            int32_t rounded = (int32_t)(fpn + (fpn >= 0 ? 0.5 : -0.5));
            if (rounded > 32767) rounded = 32767;
            if (rounded < -32768) rounded = -32768;
            model->precomputed_map[row * model->width + col] = (int16_t)rounded;
        }
    }
}

/* Simple JSON number array parser (no external dependency) */
static int parse_double_array(const char *json, const char *key, double *out, int max_count)
{
    char search[128];
    snprintf(search, sizeof(search), "\"%s\"", key);
    const char *p = strstr(json, search);
    if (!p) return 0;

    p = strchr(p, '[');
    if (!p) return 0;
    p++;

    int count = 0;
    while (count < max_count)
    {
        char *end;
        double val = strtod(p, &end);
        if (end == p) break;
        out[count++] = val;
        p = end;
        while (*p == ' ' || *p == ',') p++;
        if (*p == ']') break;
    }
    return count;
}

static int parse_uint32(const char *json, const char *key, uint32_t *out)
{
    char search[128];
    snprintf(search, sizeof(search), "\"%s\":", key);
    const char *p = strstr(json, search);
    if (!p) return 0;
    p += strlen(search);
    while (*p == ' ') p++;
    *out = (uint32_t)strtoul(p, NULL, 10);
    return 1;
}

static int parse_int(const char *json, const char *key, int *out)
{
    char search[128];
    snprintf(search, sizeof(search), "\"%s\":", key);
    const char *p = strstr(json, search);
    if (!p) return 0;
    p += strlen(search);
    while (*p == ' ') p++;
    *out = (int)strtol(p, NULL, 10);
    return 1;
}

int fpn_model_load(fpn_model *model, const char *json_path)
{
    fpn_model_init(model);

    FILE *f = fopen(json_path, "r");
    if (!f) return -1;

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    char *json = (char *)malloc(size + 1);
    if (!json) { fclose(f); return -1; }
    fread(json, 1, size, f);
    json[size] = '\0';
    fclose(f);

    parse_int(json, "width", &model->width);
    parse_int(json, "height", &model->height);
    parse_int(json, "fpn_poly_order", &model->poly_order);
    parse_uint32(json, "fpn_seed", &model->seed);

    parse_double_array(json, "channel_means", model->channel_means, 4);
    parse_double_array(json, "residual_sigma", model->residual_sigma, 4);
    parse_double_array(json, "fpn_poly_R", model->poly_coeffs[0], FPN_MAX_POLY_TERMS);
    parse_double_array(json, "fpn_poly_Gr", model->poly_coeffs[1], FPN_MAX_POLY_TERMS);
    parse_double_array(json, "fpn_poly_Gb", model->poly_coeffs[2], FPN_MAX_POLY_TERMS);
    parse_double_array(json, "fpn_poly_B", model->poly_coeffs[3], FPN_MAX_POLY_TERMS);

    /* Load row/column offsets if present (before freeing json!) */
    int half_h = model->height / 2;
    int half_w = model->width / 2;
    const char *row_keys[] = {"row_offsets_R", "row_offsets_Gr", "row_offsets_Gb", "row_offsets_B"};
    const char *col_keys[] = {"col_offsets_R", "col_offsets_Gr", "col_offsets_Gb", "col_offsets_B"};
    int has_rc = 0;

    for (int ch = 0; ch < 4; ch++)
    {
        if (strstr(json, row_keys[ch]) != NULL && half_h > 0)
        {
            model->row_offsets[ch] = (double *)calloc(half_h, sizeof(double));
            if (model->row_offsets[ch])
            {
                int n = parse_double_array(json, row_keys[ch], model->row_offsets[ch], half_h);
                if (n > 0) has_rc = 1;
            }
        }
        if (strstr(json, col_keys[ch]) != NULL && half_w > 0)
        {
            model->col_offsets[ch] = (double *)calloc(half_w, sizeof(double));
            if (model->col_offsets[ch])
            {
                int n = parse_double_array(json, col_keys[ch], model->col_offsets[ch], half_w);
                if (n > 0) has_rc = 1;
            }
        }
    }
    model->has_row_col_offsets = has_rc;
    model->half_rows = half_h;
    model->half_cols = half_w;

    free(json);

    if (model->width > 0 && model->height > 0 && model->poly_order > 0)
        model->valid = 1;

    /* Precompute the full-resolution FPN map for fast per-image subtraction */
    if (model->valid)
        fpn_precompute(model);

    return model->valid ? 0 : -1;
}

/* Evaluate 2D polynomial at normalized coordinates using precomputed powers */
static double eval_poly(const double *coeffs, int order, double x, double y)
{
    /* Precompute powers: avoids 60 pow() calls per pixel */
    double xp[FPN_MAX_POLY_ORDER + 1], yp[FPN_MAX_POLY_ORDER + 1];
    xp[0] = 1.0; yp[0] = 1.0;
    for (int k = 1; k <= order; k++)
    {
        xp[k] = xp[k-1] * x;
        yp[k] = yp[k-1] * y;
    }

    double result = 0;
    int idx = 0;
    for (int total = 0; total <= order; total++)
        for (int i = total; i >= 0; i--)
            result += coeffs[idx++] * xp[i] * yp[total - i];
    return result;
}

double fpn_model_eval(const fpn_model *model, int row, int col)
{
    if (!model->valid) return 0.0;

    /* Determine Bayer channel: 0=R(even row, even col), 1=Gr, 2=Gb, 3=B */
    int ch = (row & 1) * 2 + (col & 1);
    int hr = row / 2, hc = col / 2;

    /* Normalize coordinates to [-1, 1] using half-resolution grid */
    int half_w = model->width / 2;
    int half_h = model->height / 2;
    double x = (half_w > 1) ? (2.0 * hc / (half_w - 1)) - 1.0 : 0.0;
    double y = (half_h > 1) ? (2.0 * hr / (half_h - 1)) - 1.0 : 0.0;

    double fpn = eval_poly(model->poly_coeffs[ch], model->poly_order, x, y);

    /* Add row/column banding offsets if available */
    if (model->has_row_col_offsets)
    {
        if (model->row_offsets[ch] && hr < model->half_rows)
            fpn += model->row_offsets[ch][hr];
        if (model->col_offsets[ch] && hc < model->half_cols)
            fpn += model->col_offsets[ch][hc];
    }

    return fpn;
}

void fpn_subtract(const fpn_model *model, uint16_t *raw, int width, int height)
{
    if (!model->valid) return;

    if (model->precomputed_map && width == model->width && height == model->height)
    {
        /* Fast path: use precomputed int16 map */
        size_t npixels = (size_t)width * height;
        for (size_t i = 0; i < npixels; i++)
        {
            int32_t corrected = (int32_t)raw[i] - (int32_t)model->precomputed_map[i];
            if (corrected < 0) corrected = 0;
            if (corrected > 65535) corrected = 65535;
            raw[i] = (uint16_t)corrected;
        }
    }
    else
    {
        /* Slow path: evaluate polynomial per pixel */
        for (int row = 0; row < height; row++)
            for (int col = 0; col < width; col++)
            {
                double fpn = fpn_model_eval(model, row, col);
                int32_t corrected = (int32_t)raw[row * width + col] - (int32_t)(fpn + 0.5);
                if (corrected < 0) corrected = 0;
                if (corrected > 65535) corrected = 65535;
                raw[row * width + col] = (uint16_t)corrected;
            }
    }
}

void fpn_add_back(const fpn_model *model, uint16_t *raw, int width, int height)
{
    if (!model->valid) return;

    if (model->precomputed_map && width == model->width && height == model->height)
    {
        /* Fast path: use precomputed int16 map */
        size_t npixels = (size_t)width * height;
        for (size_t i = 0; i < npixels; i++)
        {
            int32_t restored = (int32_t)raw[i] + (int32_t)model->precomputed_map[i];
            if (restored < 0) restored = 0;
            if (restored > 65535) restored = 65535;
            raw[i] = (uint16_t)restored;
        }
    }
    else
    {
        /* Slow path: evaluate polynomial per pixel */
        for (int row = 0; row < height; row++)
            for (int col = 0; col < width; col++)
            {
                double fpn = fpn_model_eval(model, row, col);
                int32_t restored = (int32_t)raw[row * width + col] + (int32_t)(fpn + 0.5);
                if (restored < 0) restored = 0;
                if (restored > 65535) restored = 65535;
                raw[row * width + col] = (uint16_t)restored;
            }
    }
}
