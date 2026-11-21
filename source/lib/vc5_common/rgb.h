/* Adapted from Adeel Abbas, gopro/gpr PR #68, revision 1a65057d. */
/*! @file rgb.h
 *
 *  @brief Handles conversion of wavelet to rgb format
 *
 *  @version 1.0.0
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

#ifndef RGB_H
#define RGB_H

#include "types.h"
#include "pixel.h"
#include "image.h"
#include "gpr_rgb_buffer.h"

#include "gpr_rgb_render.h"

#ifdef __cplusplus
extern "C" {
#endif

    void rgb_parameters_set_default( RGB_PARAMETERS* rgb_params );

    void WaveletToCalibratedRGB( gpr_allocator allocator, PIXEL* GS_src, PIXEL* RG_src, PIXEL* BG_src, DIMENSION src_width, DIMENSION src_height, DIMENSION src_pitch,
                       RGB_IMAGE *dst_image, int input_precision_bits, const RGB_PARAMETERS* rgb_params );

#ifdef __cplusplus
}
#endif

#endif // RGB_H
