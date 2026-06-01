# Chroma root cause notes — 2026-05-31

## Current finding

The PREVIEW chroma failure is not a simple BT.709 matrix/sign bug. The latest
Lab-corrector experiment confirms the failure is model/input-distribution
generalization:

- Training sidecar rebuilt successfully:
  `/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_dmsr_gate_chroma.npz`
- Lab chroma checkpoint trained from that sidecar:
  `/Volumes/OWC_8TB/gpr_cnn/F_ane_chroma_corrector_w12.pt`
- Best saved epoch: 5
- Checkpoint sha256:
  `cab3cebf7753d8e27fef4c476003d5f7526bb0f6aae62717804571a3391508b2`
- Tile validation improved from `val_dE_proxy=32.223` to `2.358`, but full
  gate failed.

## Failed gate receipt

Pipeline tested locally:

`codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_ep5+demosaic=sips_via_gpr_tools`

Run hash: `c9bbe8390032412a`

Worst image: `Z8Z_6693`

Worst visual diff inspected: gray fabric shifted yellow/green; brown fabric
became purple/desaturated and visibly softer.

| image | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean | verdict |
|---|---:|---:|---:|---:|---|
| Z8Z_0001 | 0.1643 | 0.9521 | 30.58 | 6.02 | FAIL |
| Z8Z_0067 | 0.0761 | 0.9790 | 40.99 | 2.53 | PASS |
| Z8Z_5323 | 0.3466 | 0.9321 | 34.94 | 6.59 | FAIL |
| Z8Z_6693 | 0.5528 | 0.9136 | 32.75 | 5.22 | FAIL |

## Diagnostic evidence

Compared with the existing YCbCr decomp failure, the Lab corrector reduces
some errors on the validation-like image but introduces larger OOD chroma bias.

Worst OOD image `Z8Z_6693`:

| run | dE95 | L MAE | ab MAE | ab95 | hue95 | ab bias | ab corr | chrHF |
|---|---:|---:|---:|---:|---:|---|---|---:|
| Lab corrector ep5 | 10.81 | 3.12 | 4.23 | 12.66 | 69.7 | -0.01, -5.26 | +0.907, -0.494 | 0.56 |
| YCbCr decomp | 9.70 | 3.08 | 4.08 | 9.16 | 31.9 | +0.48, -5.82 | +0.782, +0.886 | 0.30 |
| codec none | 7.42 | 3.50 | 0.93 | 3.88 | 7.7 | +0.24, -0.24 | +0.965, +0.914 | 0.20 |
| UPRESABLE BIBO2x | 5.75 | 2.70 | 0.73 | 2.97 | 5.1 | +0.01, -0.02 | +0.978, +0.947 | 0.11 |

The strong negative Lab-b correlation on `Z8Z_6693` is the key signal: the
Lab corrector is not merely smoothing or globally tinting; it is predicting the
wrong b-channel direction on OOD content.

## Root-cause conclusion

The current Lab-corrector setup overfits a narrow validation distribution and
uses an insufficient runtime chroma hint:

1. Validation is only `Z8Z_0067`, which is the one full-gate image that passes.
2. The sidecar's `a_naive_half` / `b_naive_half` are codec-only Lab hints from
   deinterleaved Bayer planes, not the actual gpr_tools/sips display-space
   chroma path. That hint is too weak or biased for OOD fabric/skin/studio
   content.
3. The model predicts absolute Lab a/b. When it misses, it can invert the
   b-channel relationship instead of falling back to the safer codec chroma.

## Residual codec-baseline follow-up

Do not promote `lab_chroma_corrector_w12_ep5`.

The first follow-up residual experiment used the codec-only Lab a/b estimate as
the residual baseline:

- Checkpoint:
  `/Volumes/OWC_8TB/gpr_cnn/F_ane_chroma_corrector_w12_residual_ab8_sub10.pt`
- Checkpoint sha256:
  `f4bc680e3d47cdb4c5cd4d9047c5a8c676a816105a796b436b175153b0ea5253`
- Training mode: codec Lab a/b baseline plus bounded `+/-8` Lab-unit residual
- Validation sources: `Z8Z_0067`, `div_Z8Z_5271`, `div_Z8Z_6477`,
  `div_Z8Z_7424`
- Best tile validation: epoch 17, `val_dE_proxy=8.467`
- Full-gate run: `0c8974e88d94e710`
- Full-gate verdict: FAIL

| image | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean | verdict |
|---|---:|---:|---:|---:|---|
| Z8Z_0001 | 0.1647 | 0.9521 | 30.61 | 6.08 | FAIL |
| Z8Z_0067 | 0.0812 | 0.9837 | 41.50 | 3.04 | FAIL |
| Z8Z_5323 | 0.2980 | 0.9437 | 35.12 | 6.10 | FAIL |
| Z8Z_6693 | 0.5755 | 0.9138 | 32.68 | 6.22 | FAIL |

The residual model partially fixes the absolute model's worst `Z8Z_6693`
b-channel inversion (`abCorr_b` improved from `-0.494` to `+0.210`), but it
still destroys safe codec chroma in too many places. On `Z8Z_0067`, dE mean
regressed from `2.53` with the absolute Lab model to `3.04`; on `Z8Z_6693`,
ab MAE improved from `4.23` to `2.55`, but LPIPS and dE still fail badly.

This narrows the root cause further: a residual connection is necessary but
not sufficient while the baseline hint is still the codec-only Lab estimate.
The model needs the actual display-space codec/sips chroma baseline or a
runtime guard that can preserve the existing `cnn=none` chroma when the learned
residual lowers channel correlation.

## Display-space baseline result

The next experiment used the actual decoded codec raw rendered through
`gpr_tools` + `sips` as the Lab a/b residual baseline. This tests the original
root-cause hypothesis directly: the learned model was anchored to the wrong
runtime chroma hint.

- Sidecar:
  `/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_dmsr_gate_chroma_sips.npz`
- Sidecar build coverage: `498/498` sources rendered and filled
- Sidecar size: `1556.4 MiB`
- Checkpoint:
  `/Volumes/OWC_8TB/gpr_cnn/F_ane_chroma_corrector_w12_sips_residual_ab8_sub10.pt`
- Checkpoint sha256:
  `cbb6bde6f0bdb36eb50f202f2031fec2447fea12379125211475b0e886ff4677`
- Y checkpoint sha256:
  `44caeef760bd3c4ff00e017c3dca24bef694928199035e3284f6cd742fb19b45`
- Training mode: display-space `demosaic_sips` Lab a/b baseline plus bounded
  `+/-8` Lab-unit residual
- Validation sources: `Z8Z_0067`, `div_Z8Z_5271`, `div_Z8Z_6477`,
  `div_Z8Z_7424`
- Best tile validation: epoch 10, `val_dE_proxy=2.511`
- Full-gate run: `5e7d52579ffb2d3e`
- Full-gate verdict: FAIL

| image | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean | verdict |
|---|---:|---:|---:|---:|---|
| Z8Z_0001 | 0.1159 | 0.9627 | 30.35 | 2.97 | PASS |
| Z8Z_0067 | 0.0499 | 0.9888 | 41.02 | 1.01 | PASS |
| Z8Z_5323 | 0.1806 | 0.9594 | 35.06 | 1.58 | FAIL |
| Z8Z_6693 | 0.3096 | 0.9348 | 32.74 | 2.09 | FAIL |

The important change is that dE2000 mean now passes for every gate image. The
worst-diff inspection for `Z8Z_6693` no longer shows the prior purple/yellow
OOD chroma inversion; the visible failure is fabric/texture smoothing and
detail loss.

Worst OOD image `Z8Z_6693`, display-space residual versus prior candidates:

| run | dE95 | L MAE | ab MAE | ab95 | hue95 | ab bias | ab corr | chrHF |
|---|---:|---:|---:|---:|---:|---|---|---:|
| Lab sips residual | 6.38 | 3.12 | 0.88 | 3.50 | 6.3 | +0.04, +0.48 | +0.971, +0.932 | 0.10 |
| Lab corrector ep5 | 10.81 | 3.12 | 4.23 | 12.66 | 69.7 | -0.01, -5.26 | +0.907, -0.494 | 0.56 |
| Codec-only residual | 8.62 | 3.12 | 2.55 | 8.53 | 16.5 | +0.46, +0.42 | +0.837, +0.210 | 0.80 |
| YCbCr decomp | 9.70 | 3.08 | 4.08 | 9.16 | 31.9 | +0.48, -5.82 | +0.782, +0.886 | 0.30 |
| codec none | 7.42 | 3.50 | 0.93 | 3.88 | 7.7 | +0.24, -0.24 | +0.965, +0.914 | 0.20 |
| UPRESABLE BIBO2x | 5.75 | 2.70 | 0.73 | 2.97 | 5.1 | +0.01, -0.02 | +0.978, +0.947 | 0.11 |

Root cause is now narrowed:

1. The original chroma inversion was caused by anchoring the learned a/b model
   to a codec-only Bayer Lab hint that did not match runtime display-space
   chroma.
2. The display-space baseline fixes the color direction and lowers ab error to
   roughly the safe codec/UPRESABLE range.
3. The remaining PREVIEW failure is not primarily chroma. It is luma/detail
   preservation: `Z8Z_5323` fails only LPIPS, and `Z8Z_6693` fails LPIPS plus
   MS-SSIM while dE passes.

## Luma/detail diagnostic

`tests/quality_gates/diagnose_luma_detail.py` compares saved gate detail crops
for the remaining hard images. It writes:
`tests/quality_gates/runs/dashboard/luma_detail_diagnostic.html`.

| image | run | LPIPS | MS-SSIM | crop L-SSIM | L-PSNR | high-pass ratio | high-pass corr | gradient ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Z8Z_5323 | Lab sips residual | 0.1806 | 0.9594 | 0.5826 | 30.85 | 0.438 | 0.011 | 0.445 |
| Z8Z_6693 | Lab sips residual | 0.3096 | 0.9348 | 0.4370 | 28.03 | 0.401 | 0.018 | 0.414 |
| Z8Z_5323 | ml2_dec2 no CNN | 0.2358 | 0.9063 | 0.5369 | 29.93 | 0.403 | 0.030 | 0.550 |
| Z8Z_6693 | ml2_dec2 no CNN | 0.2362 | 0.8617 | 0.3905 | 26.90 | 0.396 | 0.039 | 0.542 |
| Z8Z_5323 | UPRESABLE BIBO2x | 0.2027 | 0.9685 | 0.6396 | 32.11 | 0.213 | 0.154 | 0.249 |
| Z8Z_6693 | UPRESABLE BIBO2x | 0.3433 | 0.9445 | 0.4999 | 29.14 | 0.206 | 0.166 | 0.248 |

The display-space residual candidate improves dE and luma PSNR versus
`cnn=none`, but the crop high-pass correlation remains nearly zero. That means
the candidate is not just low-pass smoothing; it is synthesizing or relocating
texture differently enough to hurt perceptual metrics. UPRESABLE has lower
high-pass magnitude but meaningfully higher high-pass correlation, which is why
the next PREVIEW fix should preserve/borrow detail placement rather than simply
increase sharpening gain.

## Implementation status

- Sidecar builder support for display-space baseline exists behind
  `build_chroma_corrector_sidecar.py --baseline-mode demosaic_sips`.
- Gate/runtime support exists behind registry CNN field
  `"chroma_baseline": "demosaic_sips"`.
- Smoke check rendered the `Z8Z_0067` baseline from full codec raw plus source
  DNG metadata and executed a small residual-checkpoint inference with a
  display-space baseline input.
- Full display-space sidecar build, training, and full gate are complete. The
  candidate is intentionally not registered for promotion because the gate
  still fails on LPIPS/MS-SSIM.

## Next fix path

Do not promote any Lab chroma checkpoint yet. The next production fix should
preserve the display-space chroma baseline and attack the remaining preview
detail loss:

1. Keep display-space `demosaic_sips` chroma as the baseline for any PREVIEW
   chroma work.
2. Use `diagnose_luma_detail.py` as the regression harness for `Z8Z_5323` and
   `Z8Z_6693` while developing the next preview detail path.
3. Prototype a guarded blend that preserves baseline luma/detail in high-risk
   textured regions while using the learned model only where it improves dE
   without lowering LPIPS/MS-SSIM.
4. Gate before registry promotion; only copy a checkpoint into `models/` after
   a full gate pass and worst-diff inspection.
