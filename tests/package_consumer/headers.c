/* Compile public headers as C without private headers or prerequisite includes. */
#if HAS_ENCODER
#include "vc5_encoder.h"
#endif
#if HAS_DECODER
#include "vc5_decoder.h"
#endif
#if HAS_SDK && !NATIVE_CLIENT
#include "gpr.h"
#endif
#if HAS_CAPTURE
#include "gpr_capture.h"
#include "gpr_gvid_reader.h"
#endif
#if HAS_PREVIEW
#include "gpr_preview.h"
#endif
int c_header_probe(void) {
#if HAS_SDK && !NATIVE_CLIENT
    gpr_parameters p;
    gpr_parameters_set_defaults(&p);
    gpr_parameters_destroy(&p,free);
    return 1;
#elif HAS_ENCODER
    vc5_encoder_parameters p;
    vc5_encoder_parameters_set_default(&p);
    return p.input_width > 0;
#elif HAS_DECODER
    vc5_decoder_parameters p;
    vc5_decoder_parameters_set_default(&p);
    return p.rgb_bits == 8 || p.rgb_bits == 16;
#else
    return 1;
#endif
}
