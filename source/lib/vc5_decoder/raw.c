/*! @file raw.c
 *
 *  @brief Definition of routines for packing a row of pixels into a RAW image.
 *
 *  (C) Copyright 2018 GoPro Inc (http://gopro.com/).
 *
 *  Licensed under either:
 *  - Apache License, Version 2.0, http://www.apache.org/licenses/LICENSE-2.0
 *  - MIT license, http://opensource.org/licenses/MIT
 *  at your option.
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

#include "headers.h"
#include <stdlib.h>

static int gpr_optical_restore_mode(void)
{
    const char *env = getenv("GPR_OPTICAL_RESTORE");
    if (env == NULL || env[0] == '\0' || env[0] == '0')
    {
        return 0;
    }
    return atoi(env);
}

static inline int32_t i32_abs(int32_t v)
{
    return v < 0 ? -v : v;
}

static inline int32_t i32_min(int32_t a, int32_t b)
{
    return a < b ? a : b;
}

static inline int32_t i32_max(int32_t a, int32_t b)
{
    return a > b ? a : b;
}

/*!
	@brief Pack the component arrays into an output image
	
	The inverse component transform for Bayer images (VC-5 Part 3)
	is applied to the component arrays before combining the values
	into a packed image.
 */
CODEC_ERROR PackComponentsToRAW(const UNPACKED_IMAGE *image,
                                PIXEL *output_buffer, size_t output_pitch,
                                DIMENSION width, DIMENSION height,
                                ENABLED_PARTS enabled_parts, uint16_t output_bit_depth, PIXEL_FORMAT output_format )
{
    // Define pointers to the rows for each input component
    COMPONENT_VALUE *GS_input_buffer;
    COMPONENT_VALUE *RG_input_buffer;
    COMPONENT_VALUE *BG_input_buffer;
    COMPONENT_VALUE *GD_input_buffer;
    
    // Define pointers to the rows for each output component
    uint16_t *output_row1_ptr;
    uint16_t *output_row2_ptr;
    
    //size_t input_quarter_pitch;
    size_t output_half_pitch;
    
    int row;
    
    GS_input_buffer = image->component_array_list[0].data;
    RG_input_buffer = image->component_array_list[1].data;
    BG_input_buffer = image->component_array_list[2].data;
    GD_input_buffer = image->component_array_list[3].data;
    
    // Compute the distance between the half rows in the Bayer grid
    output_half_pitch = output_pitch / 2;
    const int optical_restore = gpr_optical_restore_mode();
    const int32_t half_h = (int32_t)(height > 1 ? height / 2 : 1);
    const int32_t half_w = (int32_t)(width > 1 ? width / 2 : 1);
    
    for (row = 0; row < height; row++)
    {
        COMPONENT_VALUE *GS_input_row_ptr = (COMPONENT_VALUE *)((uintptr_t)GS_input_buffer + row * image->component_array_list[0].pitch);
        COMPONENT_VALUE *RG_input_row_ptr = (COMPONENT_VALUE *)((uintptr_t)RG_input_buffer + row * image->component_array_list[1].pitch);
        COMPONENT_VALUE *BG_input_row_ptr = (COMPONENT_VALUE *)((uintptr_t)BG_input_buffer + row * image->component_array_list[2].pitch);
        COMPONENT_VALUE *GD_input_row_ptr = (COMPONENT_VALUE *)((uintptr_t)GD_input_buffer + row * image->component_array_list[3].pitch);
        
        uint8_t *output_row_ptr = (uint8_t *)output_buffer + row * output_pitch;
        
        const int32_t midpoint = 2048;
        
        int column;
        
        output_row1_ptr = (uint16_t *)output_row_ptr;
        output_row2_ptr = (uint16_t *)(output_row_ptr + output_half_pitch);

        if (output_format == PIXEL_FORMAT_RAW_RGGB_14 && output_bit_depth == 14)
        {
            if (optical_restore > 0 && row > 0 && row + 1 < height && width > 2)
            {
                const size_t gs_pitch = image->component_array_list[0].pitch;
                const size_t rg_pitch = image->component_array_list[1].pitch;
                const size_t bg_pitch = image->component_array_list[2].pitch;
                const COMPONENT_VALUE *GS_prev_ptr = (const COMPONENT_VALUE *)((uintptr_t)GS_input_row_ptr - gs_pitch);
                const COMPONENT_VALUE *GS_next_ptr = (const COMPONENT_VALUE *)((uintptr_t)GS_input_row_ptr + gs_pitch);
                const COMPONENT_VALUE *RG_prev_ptr = (const COMPONENT_VALUE *)((uintptr_t)RG_input_row_ptr - rg_pitch);
                const COMPONENT_VALUE *RG_next_ptr = (const COMPONENT_VALUE *)((uintptr_t)RG_input_row_ptr + rg_pitch);
                const COMPONENT_VALUE *BG_prev_ptr = (const COMPONENT_VALUE *)((uintptr_t)BG_input_row_ptr - bg_pitch);
                const COMPONENT_VALUE *BG_next_ptr = (const COMPONENT_VALUE *)((uintptr_t)BG_input_row_ptr + bg_pitch);

                const int32_t ny_q8 = ((row - half_h) * 256) / half_h;
                const int32_t ny2_q8 = (ny_q8 * ny_q8) >> 8;

                // Estimate per-row horizontal banding offset on GD from edge samples
                const int32_t row_gd_bias = ((GD_input_row_ptr[0] - midpoint) + (GD_input_row_ptr[width - 1] - midpoint)) / 4;

                for (column = 0; column < width; column++)
                {
                    int32_t GS = GS_input_row_ptr[column];
                    int32_t RG = RG_input_row_ptr[column] - midpoint;
                    int32_t BG = BG_input_row_ptr[column] - midpoint;
                    int32_t GD = GD_input_row_ptr[column] - midpoint - row_gd_bias;

                    if (column > 0 && column + 1 < width)
                    {
                        const int32_t nx_q8 = ((column - half_w) * 256) / half_w;
                        const int32_t r2_q8 = (nx_q8 * nx_q8 + ny2_q8 * 256) >> 9; // normalized r^2 in [0..256]

                        // 1. Load 3x3 variance-stabilized luminance neighborhood (in 12-bit VC-5 log space)
                        const int32_t tl = GS_prev_ptr[column - 1], tc = GS_prev_ptr[column], tr = GS_prev_ptr[column + 1];
                        const int32_t ml = GS_input_row_ptr[column - 1], mc = GS, mr = GS_input_row_ptr[column + 1];
                        const int32_t bl = GS_next_ptr[column - 1], bc = GS_next_ptr[column], br = GS_next_ptr[column + 1];

                        const int32_t gs_avg = (tl + tc + tr + ml + mc + mr + bl + bc + br + 4) / 9;
                        const int32_t min_t = i32_min(tl, i32_min(tc, tr));
                        const int32_t min_m = i32_min(ml, i32_min(mc, mr));
                        const int32_t min_b = i32_min(bl, i32_min(bc, br));
                        const int32_t gs_min = i32_min(min_t, i32_min(min_m, min_b));

                        const int32_t max_t = i32_max(tl, i32_max(tc, tr));
                        const int32_t max_m = i32_max(ml, i32_max(mc, mr));
                        const int32_t max_b = i32_max(bl, i32_max(bc, br));
                        const int32_t gs_max = i32_max(max_t, i32_max(max_m, max_b));
                        const int32_t local_span = gs_max - gs_min;

                        // 2. Anisotropic directional coherence vs 0D spotty shot noise in 12-bit log space
                        // Coherent 1D strokes have consistent directional gradient across the 3x3 window,
                        // whereas 0D spotty noise fluctuates randomly around gs_avg.
                        const int32_t gx = (tr + 2 * mr + br) - (tl + 2 * ml + bl); // 3x3 Sobel X (4x scale)
                        const int32_t gy = (bl + 2 * bc + br) - (tl + 2 * tc + tr); // 3x3 Sobel Y (4x scale)
                        const int32_t sobel_mag = (i32_abs(gx) + i32_abs(gy)) >> 2;

                        // Empirical noise threshold in 12-bit companded Sobel space (~38..50 log counts)
                        const int32_t tau_noise = 40 + ((r2_q8 * 14) >> 8);
                        if (sobel_mag <= tau_noise)
                        {
                            // Flat isotropic region: suppress 0D spotty shot noise via 3x3 VST mean
                            GS = gs_avg;
                        }
                        else
                        {
                            // Coherent 1D stroke ("Write it", "S") or strong edge ("ee"):
                            // Smoothly ramp PSF deconvolution gain above tau_noise + anti-ringing clamp
                            const int32_t weight_q4 = i32_min(16, ((sobel_mag - tau_noise) * 16) / 36);
                            const int32_t psf_gain_q4 = 11 + ((r2_q8 * 8) >> 8); // 0.68x center -> 1.18x corner
                            const int32_t detail = mc - gs_avg;
                            const int32_t boosted = mc + (((detail * psf_gain_q4) >> 4) * weight_q4 >> 4);
                            const int32_t blended_base = (mc * weight_q4 + gs_avg * (16 - weight_q4)) >> 4;
                            const int32_t target_gs = (weight_q4 >= 12) ? boosted : ((boosted * weight_q4 + blended_base * (16 - weight_q4)) >> 4);
                            // Shan et al. (2008) local monotonicity envelope: zero Gibbs ringing!
                            GS = i32_min(gs_max, i32_max(gs_min, target_gs));
                        }

                        // 3. Hot-pixel / RTS impulse clamp + radial CRA & shot-noise soft-coring on GD (C_G)
                        const int32_t abs_gd = i32_abs(GD);
                        const int32_t tau_gd = 14 + ((r2_q8 * 14) >> 8);
                        if (abs_gd > local_span + 36)
                        {
                            // Single-photosite thermal hot pixel / RTS blinker
                            GD = 0;
                        }
                        else if (abs_gd <= tau_gd)
                        {
                            GD = 0;
                        }
                        else
                        {
                            GD = (GD > 0) ? (GD - tau_gd) : (GD + tau_gd);
                        }

                        // 4. Sub-pixel Radial Lateral Chromatic Aberration (LCA) alignment + 5-tap chroma filter
                        const int32_t grad_r = (nx_q8 * gx + ny_q8 * gy) >> 11;
                        const int32_t lca_shift = (grad_r * r2_q8) >> 10;
                        const int32_t rg_med = (RG * 4 + (RG_input_row_ptr[column - 1] - midpoint) + (RG_input_row_ptr[column + 1] - midpoint) + (RG_prev_ptr[column] - midpoint) + (RG_next_ptr[column] - midpoint)) >> 3;
                        const int32_t bg_med = (BG * 4 + (BG_input_row_ptr[column - 1] - midpoint) + (BG_input_row_ptr[column + 1] - midpoint) + (BG_prev_ptr[column] - midpoint) + (BG_next_ptr[column] - midpoint)) >> 3;
                        RG = rg_med - lca_shift;
                        BG = bg_med + lca_shift;
                    }

                    int32_t R  = clamp_uint(RG * 2 + GS, 12);
                    int32_t B  = clamp_uint(BG * 2 + GS, 12);
                    int32_t G1 = clamp_uint(GS + GD,     12);
                    int32_t G2 = clamp_uint(GS - GD,     12);

                    output_row1_ptr[2 * column + 0] = (uint16_t)(DecoderLogCurve[R]  >> 2);
                    output_row1_ptr[2 * column + 1] = (uint16_t)(DecoderLogCurve[G1] >> 2);
                    output_row2_ptr[2 * column + 0] = (uint16_t)(DecoderLogCurve[G2] >> 2);
                    output_row2_ptr[2 * column + 1] = (uint16_t)(DecoderLogCurve[B]  >> 2);
                }
                continue;
            }

            for (column = 0; column < width; column++)
            {
                int32_t GS = GS_input_row_ptr[column];
                int32_t RG = RG_input_row_ptr[column] - midpoint;
                int32_t BG = BG_input_row_ptr[column] - midpoint;
                int32_t GD = GD_input_row_ptr[column] - midpoint;

                int32_t R  = clamp_uint(RG * 2 + GS, 12);
                int32_t B  = clamp_uint(BG * 2 + GS, 12);
                int32_t G1 = clamp_uint(GS + GD,     12);
                int32_t G2 = clamp_uint(GS - GD,     12);

                output_row1_ptr[2 * column + 0] = (uint16_t)(DecoderLogCurve[R]  >> 2);
                output_row1_ptr[2 * column + 1] = (uint16_t)(DecoderLogCurve[G1] >> 2);
                output_row2_ptr[2 * column + 0] = (uint16_t)(DecoderLogCurve[G2] >> 2);
                output_row2_ptr[2 * column + 1] = (uint16_t)(DecoderLogCurve[B]  >> 2);
            }
            continue;
        }
        
        // Pack the rows of Bayer components into the BYR4 pattern
        for (column = 0; column < width; column++)
        {
            int32_t GS, RG, BG, GD;
            int32_t R, G1, G2, B;
            
            GS = GS_input_row_ptr[column];
            RG = RG_input_row_ptr[column];
            BG = BG_input_row_ptr[column];
            GD = GD_input_row_ptr[column];
            
            // Convert unsigned values to signed values
            GD -= midpoint;
            RG -= midpoint;
            BG -= midpoint;
            
            // Differences may be negative; signed left shift is undefined in C.
            R = RG * 2 + GS;
            B = BG * 2 + GS;
            G1 = GS + GD;
            G2 = GS - GD;
            
            R  = clamp_uint(R,  12);
            G1 = clamp_uint(G1, 12);
            G2 = clamp_uint(G2, 12);
            B  = clamp_uint(B,  12);
            
            // Apply inverse protune log curve
            R  = DecoderLogCurve[R];
            B  = DecoderLogCurve[B];
            G1 = DecoderLogCurve[G1];
            G2 = DecoderLogCurve[G2];

            R   >>= (16 - output_bit_depth);
            B   >>= (16 - output_bit_depth);
            G1  >>= (16 - output_bit_depth);
            G2  >>= (16 - output_bit_depth);
            
            switch (output_format)
            {
                case PIXEL_FORMAT_RAW_RGGB_12:
                case PIXEL_FORMAT_RAW_RGGB_14:
                case PIXEL_FORMAT_RAW_RGGB_16:
                    output_row1_ptr[2 * column + 0] = (uint16_t)R;
                    output_row1_ptr[2 * column + 1] = (uint16_t)G1;
                    output_row2_ptr[2 * column + 0] = (uint16_t)G2;
                    output_row2_ptr[2 * column + 1] = (uint16_t)B;
                    break;
                    
                case PIXEL_FORMAT_RAW_GBRG_12:
                case PIXEL_FORMAT_RAW_GBRG_14:
                case PIXEL_FORMAT_RAW_GBRG_16:
                    output_row1_ptr[2 * column + 0] = (uint16_t)G1;
                    output_row1_ptr[2 * column + 1] = (uint16_t)B;
                    output_row2_ptr[2 * column + 0] = (uint16_t)R;
                    output_row2_ptr[2 * column + 1] = (uint16_t)G2;
                    break;
                    
                case PIXEL_FORMAT_RAW_GRBG_12:
                case PIXEL_FORMAT_RAW_GRBG_14:
                case PIXEL_FORMAT_RAW_GRBG_16:
                    output_row1_ptr[2 * column + 0] = (uint16_t)G1;
                    output_row1_ptr[2 * column + 1] = (uint16_t)R;
                    output_row2_ptr[2 * column + 0] = (uint16_t)B;
                    output_row2_ptr[2 * column + 1] = (uint16_t)G2;
                    break;
                case PIXEL_FORMAT_RAW_BGGR_12:
                case PIXEL_FORMAT_RAW_BGGR_14:
                case PIXEL_FORMAT_RAW_BGGR_16:
                    output_row1_ptr[2 * column + 0] = (uint16_t)B;
                    output_row1_ptr[2 * column + 1] = (uint16_t)G1;
                    output_row2_ptr[2 * column + 0] = (uint16_t)G2;
                    output_row2_ptr[2 * column + 1] = (uint16_t)R;
                    break;
                default:
                    assert(0);
                    break;
            }
        }
    }
    
    return CODEC_ERROR_OKAY;
}
