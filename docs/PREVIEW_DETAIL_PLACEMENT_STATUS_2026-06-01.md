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
| Full-gate Lab-L residual CNN | `3b4a30d74a54cd90` | Trained with Charbonnier + MS-SSIM + LPIPS; 3/4 pass, but `Z8Z_6693` regresses vs unsharp s07. |
| Z8Z_6693-only Lab-L residual CNN | `ba742b469237dbab` | Diagnostic: even when trained only on the blocker, local L-only residuals do not clear `Z8Z_6693` and dE regresses on `Z8Z_0001`. |

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
narrowed further by the CNN probes:

| image | unsharp s07 LPIPS | full-gate L-CNN LPIPS | Z6693-only L-CNN LPIPS |
|---|---:|---:|---:|
| Z8Z_5323 | 0.1271 | 0.1390 | 0.1429 |
| Z8Z_6693 | 0.2242 | 0.2569 | 0.2584 |

The local Lab-L CNN can improve easy already-passing content, but it does not
place the missing texture on the `Z8Z_6693` blocker. Training only on
`Z8Z_6693` removes generalization pressure and still fails, which points away
from small local L-only capacity and toward one of:

- full-image/context target mismatch,
- teacher quality/target mismatch for hair/skin texture,
- loss objective still not aligned with the gate's LPIPS/MS-SSIM behavior, or
- codec/detail aliasing that the local L-only post-process cannot infer.

## Artifacts

- Full-gate linear detail sidecar:
  `models/luma_detail_linear_lab_sips_fullgate_v1.npz`
- Sidecar config/fit receipt:
  `models/luma_detail_linear_lab_sips_fullgate_v1.npz.json`
- Full-gate Lab-L CNN checkpoint:
  `models/luma_detail_cnn_lab_sips_unsharp_s07_fullgate_lpips_v1.pt`
- Z8Z_6693 diagnostic CNN checkpoint:
  `models/luma_detail_cnn_lab_sips_unsharp_s07_z6693_lpips_final_v1.pt`
- Temporary registry pipelines:
  `codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10_luma_linear_detail_v1+demosaic=sips_via_gpr_tools`
  `codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10_unsharp_s07_luma_detail_cnn_v1+demosaic=sips_via_gpr_tools`
  `codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10_unsharp_s07_luma_detail_cnn_z6693_v1+demosaic=sips_via_gpr_tools`
- Gate runs:
  `tests/quality_gates/runs/387888dda9016edf/run.json`
  `tests/quality_gates/runs/3b4a30d74a54cd90/run.json`
  `tests/quality_gates/runs/ba742b469237dbab/run.json`
- Diagnostic dashboard:
  `tests/quality_gates/runs/dashboard/detail_candidate_linear_v1.html`
  `tests/quality_gates/runs/dashboard/detail_candidate_luma_cnn_v1.html`
- Latest comparison dashboard:
  `tests/quality_gates/runs/dashboard/latest_preview_comparison.html`

## Next Work

Stop spending time on local Lab-L residual post-processes. The next credible
candidate needs either a larger teacher/detail target with full-image context,
or a codec-side/detail-aware path that prevents the `Z8Z_6693` texture aliasing
before the preview model sees it.
