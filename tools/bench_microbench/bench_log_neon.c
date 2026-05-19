/* Standalone microbenchmark: NEON float-domain log10 vs scalar LUT for the
   GPR encoder log curve. Tests:
     - Speed (cycles per element)
     - Byte identity vs LUT reference

   Encoder log curve formula (14->14 bit):
     y = floor(16383 * log10(1 + 112*x/16383) / log10(113)),  x in [0, 16383]
*/
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <arm_neon.h>

#define N_INPUT  (16384)              /* one full curve worth */
#define N_ITER_HOT  (16 * 1024)       /* repeated lookups */

/* Build the reference LUT (matches logcurve.c exactly). */
static void build_lut(uint16_t *table) {
    const double denom = log10(113.0);
    const double max_in = 16383.0;
    const double max_out = 16383.0;
    for (int i = 0; i <= 16383; i++) {
        const double norm = (i / max_in) * 112.0 + 1.0;
        const double output = max_out * (log10(norm) / denom);
        table[i] = (uint16_t)output;   /* C truncation, matches encoder */
    }
}

/* Scalar LUT lookup baseline. */
static __attribute__((noinline)) void run_scalar_lut(
    const uint16_t *lut, const uint16_t *in, uint16_t *out, int n)
{
    for (int i = 0; i < n; i++) out[i] = lut[in[i] & 0x3FFF];
}

/* NEON float-domain log10 via bitcast-exponent-mantissa + polynomial.
   Computes: y = 16383 * log10(1 + 112*x/16383) / log10(113)
   for x in [0, 16383].

   Strategy:
     1) v = 1 + 112*x/16383   (in [1, 113])
     2) log10(v) via float ops
     3) y = 16383 * log10(v) / log10(113)

   log10(v) using log2 trick:
     log2(v) = e + log2(1+m)   where v = 2^e * (1+m), m in [0,1)
     log10(v) = log2(v) / log2(10) = log2(v) * 0.301029996

   For log2(1+m), use Cephes-style polynomial fit on m, with sqrt(2)
   normalization for better accuracy: if m >= sqrt(2)-1, use m' = (m-1)/2
   to keep working in a smaller range.
*/
static __attribute__((noinline)) void run_neon_log(
    const uint16_t *in, uint16_t *out, int n)
{
    /* Constants for log10(1 + 112*x/16383) / log10(113) * 16383 */
    const float32x4_t v_one          = vdupq_n_f32(1.0f);
    const float32x4_t v_scale_in     = vdupq_n_f32(112.0f / 16383.0f);
    /* 16383 / log10(113) = 16383 / 2.053078443 = 7980.18... */
    const float32x4_t v_outscale     = vdupq_n_f32(16383.0f / 2.053078443f);
    /* log2(e) for natural→log2 conversion... we use log10 directly */
    /* log10(2) = 0.301029996 */
    const float32x4_t v_log10_2      = vdupq_n_f32(0.30102999566f);
    /* Polynomial coefficients for log10(1+m) where m in [-0.5, 0.5]
       (after sqrt(2) normalization). Higher-degree minimax for log10. */
    /* For log2(1+m) we use a 6th-degree minimax over m in [-0.5, 0.5]:
       coefs from a remez run. For simplicity here, use:
         log2(1+m) ~ m/ln(2) * (1 - m/2 + m^2/3 - m^3/4 + m^4/5 - m^5/6 + m^6/7)
       i.e. ln(1+m)/ln(2). Series truncated. */
    /* We'll do log(1+m) Taylor then *log10(e). log10(e) = 0.43429448 */
    const float32x4_t v_log10_e      = vdupq_n_f32(0.43429448190f);

    for (int i = 0; i < n; i += 4) {
        /* Load 4 u16, widen to u32, then to f32. */
        uint16x4_t vu16 = vld1_u16(&in[i]);
        uint32x4_t vu32 = vmovl_u16(vu16);
        float32x4_t vx  = vcvtq_f32_u32(vu32);

        /* v = 1 + 112*x/16383, range [1, 113] */
        float32x4_t vv = vfmaq_f32(v_one, vx, v_scale_in);

        /* Extract exponent & mantissa via bitcast.
           IEEE 754: bits 30:23 = biased exponent (127 = 2^0), bits 22:0 = mantissa */
        int32x4_t vbits = vreinterpretq_s32_f32(vv);
        /* mantissa: clear sign+exponent, set exponent to 127 -> v in [1,2) */
        int32x4_t vmant_bits = vorrq_s32(
            vandq_s32(vbits, vdupq_n_s32(0x007FFFFF)),
            vdupq_n_s32(0x3F800000));
        float32x4_t vm = vreinterpretq_f32_s32(vmant_bits);
        /* exponent: shift right 23, subtract bias 127 */
        int32x4_t ve_i = vsubq_s32(vshrq_n_s32(vbits, 23), vdupq_n_s32(127));
        float32x4_t ve = vcvtq_f32_s32(ve_i);

        /* Cephes sqrt(2) normalization:
           if vm > sqrt(2) (~1.41421356), then vm /= 2, ve += 1
           This keeps log argument in [sqrt(2)/2, sqrt(2)]. */
        float32x4_t v_sqrt2 = vdupq_n_f32(1.41421356f);
        uint32x4_t vmask = vcgtq_f32(vm, v_sqrt2);
        float32x4_t vm_half = vmulq_f32(vm, vdupq_n_f32(0.5f));
        vm = vbslq_f32(vmask, vm_half, vm);
        ve = vaddq_f32(ve, vbslq_f32(vmask, vdupq_n_f32(1.0f), vdupq_n_f32(0.0f)));

        /* x = vm - 1, now in [-0.293, 0.414] approx */
        float32x4_t vt = vsubq_f32(vm, v_one);

        /* log(1+x) polynomial. Use a deg-7 Horner scheme.
           For small x: ln(1+x) ≈ x - x^2/2 + x^3/3 - x^4/4 + x^5/5 - x^6/6 + x^7/7 */
        const float32x4_t c1 = vdupq_n_f32( 1.0f);
        const float32x4_t c2 = vdupq_n_f32(-0.5f);
        const float32x4_t c3 = vdupq_n_f32( 0.33333333f);
        const float32x4_t c4 = vdupq_n_f32(-0.25f);
        const float32x4_t c5 = vdupq_n_f32( 0.2f);
        const float32x4_t c6 = vdupq_n_f32(-0.16666667f);
        const float32x4_t c7 = vdupq_n_f32( 0.14285714f);

        /* Horner: ln(1+x) = x * (c1 + x*(c2 + x*(c3 + x*(c4 + x*(c5 + x*(c6 + x*c7)))))) */
        float32x4_t p = c7;
        p = vfmaq_f32(c6, p, vt);
        p = vfmaq_f32(c5, p, vt);
        p = vfmaq_f32(c4, p, vt);
        p = vfmaq_f32(c3, p, vt);
        p = vfmaq_f32(c2, p, vt);
        p = vfmaq_f32(c1, p, vt);
        float32x4_t vln_1px = vmulq_f32(p, vt);

        /* log10(v) = ve * log10(2) + log10(1+t) = ve*log10(2) + ln(1+t)*log10(e) */
        float32x4_t vlog10v = vfmaq_f32(vmulq_f32(ve, v_log10_2), vln_1px, v_log10_e);

        /* y = log10(v) * (16383/log10(113)) */
        float32x4_t vy = vmulq_f32(vlog10v, v_outscale);

        /* Truncate toward zero (matches encoder's (uint16_t)cast). */
        int32x4_t vy_i = vcvtq_s32_f32(vy);
        /* Clamp to [0, 16383] just in case */
        vy_i = vmaxq_s32(vy_i, vdupq_n_s32(0));
        vy_i = vminq_s32(vy_i, vdupq_n_s32(16383));
        uint16x4_t vy_u16 = vmovn_u32(vreinterpretq_u32_s32(vy_i));
        vst1_u16(&out[i], vy_u16);
    }
}

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(void) {
    static uint16_t lut[16384];
    static uint16_t in[N_INPUT];
    static uint16_t out_scalar[N_INPUT];
    static uint16_t out_neon[N_INPUT];

    build_lut(lut);

    /* Fill input with pseudo-uniform distribution 0..16383 */
    srand(42);
    for (int i = 0; i < N_INPUT; i++) in[i] = (uint16_t)(rand() & 0x3FFF);

    /* Sanity / accuracy: compare on the full 0..16383 sweep */
    static uint16_t sweep[N_INPUT];
    static uint16_t sweep_lut[N_INPUT];
    static uint16_t sweep_neon[N_INPUT];
    for (int i = 0; i < N_INPUT; i++) sweep[i] = (uint16_t)i;
    run_scalar_lut(lut, sweep, sweep_lut, N_INPUT);
    run_neon_log(sweep, sweep_neon, N_INPUT);

    int mismatches = 0;
    int max_abs_err = 0;
    long sum_abs_err = 0;
    int first_mismatch[5] = {-1,-1,-1,-1,-1};
    int fm_idx = 0;
    for (int i = 0; i < N_INPUT; i++) {
        int diff = (int)sweep_neon[i] - (int)sweep_lut[i];
        if (diff != 0) {
            mismatches++;
            int absd = diff < 0 ? -diff : diff;
            if (absd > max_abs_err) max_abs_err = absd;
            sum_abs_err += absd;
            if (fm_idx < 5) first_mismatch[fm_idx++] = i;
        }
    }
    printf("=== Accuracy (sweep 0..16383) ===\n");
    printf("mismatches: %d / 16384 (%.2f%%)\n", mismatches, 100.0*mismatches/16384);
    printf("max abs err: %d\n", max_abs_err);
    printf("mean abs err: %.3f\n", mismatches ? (double)sum_abs_err/mismatches : 0.0);
    printf("first mismatches at idx:");
    for (int j = 0; j < fm_idx; j++) {
        int i = first_mismatch[j];
        printf(" %d(lut=%u,neon=%u)", i, sweep_lut[i], sweep_neon[i]);
    }
    printf("\n\n");

    /* Hot-loop timing: run each routine many times to get cycle estimate */
    const int n_iter = 4096;

    /* Scalar LUT */
    double t0 = now_sec();
    for (int it = 0; it < n_iter; it++) {
        run_scalar_lut(lut, in, out_scalar, N_INPUT);
    }
    double dt_scalar = now_sec() - t0;

    /* NEON float-log */
    t0 = now_sec();
    for (int it = 0; it < n_iter; it++) {
        run_neon_log(in, out_neon, N_INPUT);
    }
    double dt_neon = now_sec() - t0;

    double total_elems = (double)n_iter * N_INPUT;
    /* Pi 5 nominal 2.4 GHz */
    double cyc_scalar = (dt_scalar / total_elems) * 2.4e9;
    double cyc_neon   = (dt_neon   / total_elems) * 2.4e9;

    printf("=== Timing (%d iters * %d elems = %.0f total) ===\n",
           n_iter, N_INPUT, total_elems);
    printf("scalar LUT: %.3f sec, %.2f cyc/elem (@ 2.4 GHz)\n",
           dt_scalar, cyc_scalar);
    printf("NEON log10: %.3f sec, %.2f cyc/elem (@ 2.4 GHz)\n",
           dt_neon, cyc_neon);
    printf("speedup (LUT/NEON): %.2fx %s\n",
           dt_scalar / dt_neon, dt_neon < dt_scalar ? "(NEON faster)" : "(LUT faster)");

    /* Project savings: at 50 MP single still, LUT cost is ~21 ms.
       Scale that to NEON. */
    double scale = dt_neon / dt_scalar;
    printf("\n=== Projection for 50 MP single still ===\n");
    printf("Scalar LUT path measured at ~21 ms total.\n");
    printf("NEON would take ~%.1f ms (= 21 * %.3f).\n", 21.0 * scale, scale);

    return 0;
}
