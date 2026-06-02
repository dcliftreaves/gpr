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
| Full-image L donor/blend oracle | `preview_luma_blend_oracle_1920` | Exploratory 1920-wide sweep; no fixed donor or pairwise blend passes all four images. |

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

A full-image Lab-L donor/blend oracle now rules out simple donor selection as
well. `tests/quality_gates/probe_preview_luma_blend_oracle.py` keeps the solved
Lab/SIPS a/b chroma path fixed and sweeps available L donors (`lab_sips`,
`s07`, `upresable`, `sl_dec2_y`, `bibo_cross`) plus pairwise blends. The
exploratory 1920-wide run
`tests/quality_gates/runs/dashboard/preview_luma_blend_oracle_1920.json`
produced no all-image PASS. The best global row,
`blend:sl_dec2_y:bibo_cross:a=0.25`, fails `Z8Z_0001` (`LPIPS=0.1657`,
`Y-PSNR=27.36`, `dE=3.25`). The strongest `Z8Z_6693` single-image donor is
`bibo_cross` (`LPIPS=0.1316`), but its MS-SSIM is only `0.8981`. That means the
missing blocker is not solved by choosing or blending existing L donors; it
needs a learned upstream/full-context detail-placement model or a better
teacher/detail source.

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
  `tests/quality_gates/runs/dashboard/preview_luma_blend_oracle_1920.html`
- Latest comparison dashboard:
  `tests/quality_gates/runs/dashboard/latest_preview_comparison.html`

## Next Work

Stop spending time on local Lab-L residual post-processes. The next credible
candidate needs either a larger teacher/detail target with full-image context,
or a codec-side/detail-aware path that prevents the `Z8Z_6693` texture aliasing
before the preview model sees it.

## Holdout Evaluation Policy

The four-image `tests/quality_gates/test_set.json` remains the ship gate:
per-image thresholds, worst image governs, and no averaging can convert a
frozen-gate failure into a ship claim.

For candidate ranking, use the 28-image informational PREVIEW breadth set:

```bash
python3 tests/quality_gates/run_gate.py PIPELINE_NAME \
  --test-set tests/quality_gates/preview_holdout_set.json
python3 tests/quality_gates/summarize_preview_holdout.py RUN_HASH [RUN_HASH...]
```

The holdout summary reports median, p95/p05 tails, worst image, and
per-stratum failures across smooth gradients, high-detail edges,
foliage/organic texture, saturated color, shadows, and same-session OOD
examples near the `Z8Z_6693` blocker. A production candidate should improve the
frozen blocker and should not trade it for a wider p95 tail on the holdout.
