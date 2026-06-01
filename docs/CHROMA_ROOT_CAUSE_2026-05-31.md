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

## Next fix path

Do not promote `lab_chroma_corrector_w12_ep5`.

The next chroma experiment should be constrained so it cannot destroy safe
codec chroma:

1. Train a residual Lab a/b corrector around the codec/sips chroma baseline,
   not absolute a/b from a weak codec-only hint.
2. Use multi-image validation that includes OOD gate-like sources, not only
   `Z8Z_0067`.
3. Add a fallback clamp or blend: if predicted ab correlation/energy diverges
   from codec chroma, preserve codec chroma and only use the learned residual
   in low-risk regions.
4. Gate before registry promotion; only copy a checkpoint into `models/` after
   a full gate pass and worst-diff inspection.
