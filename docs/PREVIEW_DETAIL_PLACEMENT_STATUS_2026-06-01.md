# PREVIEW Detail Placement Status - 2026-06-01

Objective: preserve the Lab SIPS color guardrail and move the remaining PREVIEW
blocker, which is full-image luma/detail placement on `Z8Z_5323` and
`Z8Z_6693`.

## Current Baseline

`codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10+demosaic=sips_via_gpr_tools`

Run `5e7d52579ffb2d3e` keeps dE2000 mean under the PREVIEW threshold on all
four gate images. The remaining failures are detail metrics:

| image | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean | verdict |
|---|---:|---:|---:|---:|---|
| Z8Z_0001 | 0.1159 | 0.9627 | 30.35 | 2.97 | PASS |
| Z8Z_0067 | 0.0499 | 0.9888 | 41.02 | 1.01 | PASS |
| Z8Z_5323 | 0.1806 | 0.9594 | 35.06 | 1.58 | FAIL LPIPS |
| Z8Z_6693 | 0.3096 | 0.9348 | 32.74 | 2.09 | FAIL LPIPS/MS-SSIM |

## Candidates Tested

| candidate | run | result |
|---|---|---|
| Lab SIPS + unsharp s05 | `d96fb7cb66c53d56` | 3/4 images pass; `Z8Z_6693` still fails LPIPS/MS-SSIM. |
| Lab SIPS + unsharp s07 | `1f1ef2ee138c51c3` | Best simple detail candidate; `Z8Z_5323` passes, `Z8Z_6693` fails. |
| Lab SIPS + unsharp s10 | `87ad3539b3650eab` | Improves `Z8Z_6693` LPIPS but narrowly regresses `Z8Z_0001` dE. |
| BIDO blend distill | `8d4f8aa3eb81a99d` | Reject; regresses detail and dE guardrail. |
| Full-gate linear Lab-L detail sidecar | `387888dda9016edf` | Reject; improves Y-PSNR but badly regresses LPIPS. |

## Root Cause Narrowing

The latest full-gate-trained sidecar was fit from full-resolution
REF/PIPELINE pairs in `5e7d52579ffb2d3e`. It is constrained to Lab L only and
cannot alter chroma or memorize coordinates. Its training MSE improved, and
gate Y-PSNR improved on all images, but LPIPS got worse:

| image | baseline LPIPS | linear-detail LPIPS | baseline Y-PSNR | linear-detail Y-PSNR |
|---|---:|---:|---:|---:|
| Z8Z_5323 | 0.1806 | 0.2984 | 35.06 | 35.50 |
| Z8Z_6693 | 0.3096 | 0.4757 | 32.74 | 33.12 |

This rules out "more L2 luma correction" as the solution. The failure is now
narrowed to the loss/objective and target mismatch: the gate needs
perceptual/full-image texture placement, while the successful color baseline
and the linear detail fit optimize local numeric error. The useful direction is
a full-image/crop perceptual distillation target, not more global sharpening or
L2 high-pass regression.

## Artifacts

- Full-gate linear detail sidecar:
  `models/luma_detail_linear_lab_sips_fullgate_v1.npz`
- Sidecar config/fit receipt:
  `models/luma_detail_linear_lab_sips_fullgate_v1.npz.json`
- Temporary registry pipeline:
  `codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10_luma_linear_detail_v1+demosaic=sips_via_gpr_tools`
- Gate run:
  `tests/quality_gates/runs/387888dda9016edf/run.json`
- Diagnostic dashboard:
  `tests/quality_gates/runs/dashboard/detail_candidate_linear_v1.html`
- Latest comparison dashboard:
  `tests/quality_gates/runs/dashboard/latest_preview_comparison.html`

## Next Work

Train a perceptual detail-placement candidate against full-gate crops/full
images with LPIPS/MS-SSIM-aware loss, using the Lab SIPS chroma path as a
fixed color guardrail. Do not use L2-only Lab-L sidecars as the main path.
