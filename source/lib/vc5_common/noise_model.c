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

    free(json);

    if (model->width > 0 && model->height > 0 && model->poly_order > 0)
        model->valid = 1;

    return model->valid ? 0 : -1;
}

/* Evaluate 2D polynomial at normalized coordinates */
static double eval_poly(const double *coeffs, int order, double x, double y)
{
    double result = 0;
    int idx = 0;
    for (int total = 0; total <= order; total++)
        for (int i = total; i >= 0; i--)
        {
            int j = total - i;
            result += coeffs[idx++] * pow(x, i) * pow(y, j);
        }
    return result;
}

double fpn_model_eval(const fpn_model *model, int row, int col)
{
    if (!model->valid) return 0.0;

    /* Determine Bayer channel: 0=R(even row, even col), 1=Gr, 2=Gb, 3=B */
    int ch = (row & 1) * 2 + (col & 1);

    /* Normalize coordinates to [-1, 1] using half-resolution grid */
    int half_w = model->width / 2;
    int half_h = model->height / 2;
    double x = (half_w > 1) ? (2.0 * (col / 2) / (half_w - 1)) - 1.0 : 0.0;
    double y = (half_h > 1) ? (2.0 * (row / 2) / (half_h - 1)) - 1.0 : 0.0;

    return eval_poly(model->poly_coeffs[ch], model->poly_order, x, y);
}

void fpn_subtract(const fpn_model *model, uint16_t *raw, int width, int height)
{
    if (!model->valid) return;

    for (int row = 0; row < height; row++)
    {
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

    for (int row = 0; row < height; row++)
    {
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
