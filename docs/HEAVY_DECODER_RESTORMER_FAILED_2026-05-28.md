# Heavy-decoder VIDEO_FREEZE tier — Restormer post-RGB FAILED

**Date:** 2026-05-28
**Branch:** fix/multilevel-cascade-regression
**Hypothesis:** A 26M-param transformer trained on real-noise denoising
(Restormer real_denoising.pth) applied as a post-decode RGB filter could
recover what a 315K-param matched BIBO_1x cannot, unlocking aggressive
cranked-codec tiers below the 6.77 MB current smallest ship.

## Result: all three test pipelines FAIL, by wide margins

VIDEO_FREEZE thresholds (per-image worst-case): LPIPS ≤0.085, MS-SSIM ≥0.965,
Y-PSNR ≥32 dB, ΔE2000 ≤2.0.

| Pipeline | run_hash | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst ΔE | verdict |
|---|---|---|---|---|---|---|
| `codec=ml2_q3_l2x2_l1x4+cnn=restormer_real_denoising_post+demosaic=sips_via_gpr_tools` | `5508eae0328a3492` | 0.229 | 0.913 | 26.16 | 2.47 | FAIL |
| `codec=ml2_q3_l2x2_l1x2_hh1x4+cnn=restormer_real_denoising_post+demosaic=sips_via_gpr_tools` | `baa1d069683f4958` | 0.229 | 0.913 | 26.18 | 2.53 | FAIL |
| `codec=ml2_q3_l2x2_l1x4_hh1x4+cnn=restormer_real_denoising_post+demosaic=sips_via_gpr_tools` | `8377593ac1edaaf5` | 0.229 | 0.913 | 26.18 | 2.45 | FAIL |

Worst image is the same (Z8Z_0001, dark detailed rocks) across all three
runs with near-identical metrics, indicating the failure is dominated by
Restormer's behavior on that content — not by which codec was used.

## Visual-diff observation (Read-tool inspection)

I opened all three worst-image visual diffs via the Read tool. In each one
the PIPELINE crop shows the dark rocks and fine surface texture aggressively
smoothed and color-washed, while REF preserves crisp grain and shadow
detail. The same blurring is visible across the three runs regardless of
codec aggression. Restormer is over-denoising legitimate high-frequency
photographic content because the real_denoising prior expects much higher
input noise than the codec leaves behind.

(6-word concrete-noun sentence per CLAUDE.md ship-claim discipline:
"Restormer washed dark rocks and smoothed fine grain detail.")

## Why this happened

Restormer's real_denoising weight was trained on SIDD/DND-style sensor
noise: spatially uncorrelated, Poisson-Gaussian-mixture, magnitude ~1-5%
of signal. Codec artifacts are structurally different:

- Spatially correlated (cross-hatch from wavelet quant)
- Concentrated in mid frequencies (HH/HL/LH bands)
- Low magnitude relative to content variance
- Edge-aligned (not signal-independent)

A model that learned "remove i.i.d. high-spatial-freq noise from RGB" will
take legitimate fine texture as noise and erase it, while the structured
codec artifacts (which look unlike training-distribution noise) pass
through. Net result: worse than codec-alone on detail content, marginally
better only on Z8Z_0067 (smooth gradient sky).

## What this falsifies

- The "heavy CNN class beats small matched CNN" hypothesis as
  written. Adding model capacity does not help when the model is
  trained on the wrong noise distribution.
- The premise that "cranked-codec output is essentially extra noise on
  the clean render." It isn't: it's structured wavelet quantization
  artifacts that no real-noise prior is going to recognize.

## What's still open

- **Heavy CNN trained against codec output** (not real noise): the
  Phase B BIDO distillation work (`bido_4x_ane_ml2_q3_dec2_distill`,
  registered earlier) is the conceptually correct version of this
  experiment — a heavy teacher's targets fine-tuned a lighter student
  against codec output. Not the same as running the teacher live.
- **Restormer fine-tuned on (codec_rgb, clean_rgb) pairs**: would
  almost certainly do better than zero-shot, but requires training
  effort and the resulting model still wouldn't be "real-time" — and
  if the task is "spend training compute to make a heavy decoder
  work," the BIBO_w24 matched retrain (task (a)) is the cheaper bet.
- **Task (a) — BIBO_w24 matched retrain** against `ml2_q3_l2x2_l1x4`:
  still the open lever. Scheduled to start once M5 finishes its
  in-flight BIDO_w24 training.

## Decision

Drop Restormer-as-decoder. No further investment. The three failed
pipelines stay in the registry as `experiment-heavy-decoder-restormer-*`
entries so the negative result is reproducible from registry alone.
