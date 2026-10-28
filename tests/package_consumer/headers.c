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
#include "gpr_preview_queue.h"
static int c_display(void *user,const gpr_preview_frame_view *frame) { (void)user;(void)frame;return 0; }
#endif
int c_header_probe(void) {
#if HAS_PREVIEW
    gpr_gvid_config video={128,96,30,1,3,14,{'R','G','G','B'}};
    gpr_preview_calibration calibration;
    gpr_preview_plan *plan=0;
    gpr_preview_info info;
    gpr_preview_calibration_identity(&video,&calibration);
    if (gpr_preview_plan_create(&video,&calibration,&plan)) return 0;
    if (gpr_preview_plan_info(plan,&info) || info.width!=32 || info.height!=24) {
        gpr_preview_plan_destroy(plan);return 0;
    }
    gpr_preview_plan_destroy(plan);
    {
        gpr_preview_queue_config config={1,1,c_display,0};gpr_preview_queue *queue=0;
        if (gpr_preview_queue_create(&config,&queue)) return 0;
        if (gpr_preview_queue_finish(queue)) {gpr_preview_queue_destroy(queue);return 0;}
        gpr_preview_queue_destroy(queue);
    }
#endif
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
