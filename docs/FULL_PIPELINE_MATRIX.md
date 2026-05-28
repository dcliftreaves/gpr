# Full GPR pipeline matrix — 2026-05-28

All entries from `pipelines/registry.json` × `tests/quality_gates/runs/`.
Sorted within each mode by mean MB (smaller first).

## STILLS (legacy CineForm VC5 + matched CNN)

| q | codec | CNN | mean MB | worst LPIPS | worst MS-SSIM | worst Y-PSNR | verdict | ship role |
|---:|---|---|---:|---:|---:|---:|---|---|
| 0 | `gpr_tools_q0` | matched-q3 | 9.80 | 0.0314 | 0.9915 | 40.59 | **PASS** | experiment-still-q0-with-q3-trained-cnn |
| 1 | `gpr_tools_q1` | matched-q3 | 12.12 | 0.0183 | 0.9953 | 43.62 | **PASS** | experiment-still-q1-with-q3-trained-cnn |
| 2 | `gpr_tools_q2` | matched-q3 | 13.68 | 0.0180 | 0.9954 | 43.69 | **PASS** | experiment-still-q2-with-q3-trained-cnn |
| 3 | `gpr_tools_q3` | matched-q3 | 15.05 | 0.0155 | 0.9961 | 44.45 | **PASS** | ship-still-primary |
| 3 | `gpr_tools_q3` | bibo1x_ane_sl_q3 | 15.05 | 0.1015 | 0.9583 | 33.23 | **FAIL** | cross-pair-cheap-probe-legacy-codec-fused-trained-cnn |
| - | `gpr_tools_legacy` | none | 15.05 | 0.2583 | 0.9653 | 28.25 | **FAIL** | production-stills-gpr_tools |
| 8 | `gpr_tools_q8` | none | 27.17 | 0.0035 | 0.9989 | 51.89 | **PASS** | ship-still-archival-no-cnn |

STILL ceiling: LPIPS ≤ 0.05, MS-SSIM ≥ 0.99, Y-PSNR ≥ 35, ΔE ≤ 1.5

## VIDEO_FREEZE (multi-level FUSED + matched CNN)

| codec | CNN | mean MB | worst LPIPS | worst MS-SSIM | worst Y-PSNR | verdict | ship role |
|---|---|---:|---:|---:|---:|---|---|
| `ml2_q3_dec2` | bibo2x_ane_hh1x4 | 2.20 | 0.2858 | 0.9158 | 26.26 | **FAIL** | ml2-halfres-plus-cranked-superres-cnn |
| `ml2_q3_dec2` | bibo2x_ane_ml2_q3_dec2 | 2.20 | 0.4370 | 0.9110 | 31.92 | **FAIL** | alternate-embedded-bibo2x-matched-narrow |
| `ml2_q3_dec2` | bibo2x_ane_ml2_q3_dec2_diverse | 2.20 | 0.3433 | 0.9445 | 33.37 | **FAIL** | alternate-embedded-bibo2x-matched-diverse |
| `ml2_q3_dec2` | bibo2x_ane_ml2_q3_dec2_diverse_reshalf | 2.20 | 0.4107 | 0.9208 | 28.61 | **FAIL** | exp-cnn-residual-half |
| `ml2_q3_dec2` | bibo2x_ane_ml2_q3_dec2_diverse_resthird | 2.20 | 0.4157 | 0.9013 | 26.73 | **FAIL** | exp-cnn-residual-third |
| `ml2_q3_dec2` | bibo2x_ane_sl_q3 | 2.20 | 0.2530 | 0.8971 | 25.63 | **FAIL** | alternate-embedded-bibo2x-cross |
| `ml2_q3_dec2` | bido_4x_ane_ml2_q3_dec2_lpips | 2.20 | 0.4516 | 0.9262 | 29.25 | **FAIL** | embedded-preview-bido-lpips-finetune |
| `ml2_q3_dec2` | bido_4x_ane_ml2_q3_dec2_wider | 2.20 | 0.6419 | 0.9289 | 29.29 | **FAIL** | experiment-embedded-bido-wider |
| `ml2_q3_dec2` | none | 2.20 | 0.3119 | 0.8617 | 24.04 | **FAIL** | embedded-preview-ml2-no-cnn |
| `ml2_q11` | matched-ml2 | 6.77 | 0.0869 | 0.9709 | 35.88 | **FAIL** | cnnaware-ml2-q11-with-matched-cnn |
| `ml2_q11` | bibo1x_ane_sl_q3 | 6.77 | 0.1681 | 0.9520 | 30.38 | **FAIL** | ml2-cranked |
| `ml2_q3_l2x2_l1x2` | matched-ml2 | 7.11 | 0.0794 | 0.9689 | 35.59 | **PASS** | cnnaware-ml2-crank-l2x2_l1x2-with-matched-cnn |
| `ml2_q3_l1x2_hh1x4` | matched-ml2 | 7.47 | 0.0773 | 0.9695 | 35.42 | **PASS** | cnnaware-ml2-l1x2_hh1x4-matched-cnn |
| `ml2_q3_l1x2` | matched-ml2 | 7.81 | 0.0760 | 0.9710 | 35.81 | **PASS** | ship-video-freeze-primary |
| `ml2_q3_hh1x8` | matched-ml2 | 9.20 | 0.0724 | 0.9719 | 35.89 | **PASS** | cnnaware-ml2-hh1x8-matched-cnn |
| `ml2_q3_hh1x4` | matched-ml2 | 9.21 | 0.0723 | 0.9719 | 35.92 | **PASS** | cnnaware-ml2-crank-hh1x4-with-matched-cnn |
| `ml2_q3_hh1x2` | matched-ml2 | 9.55 | 0.0702 | 0.9736 | 36.40 | **PASS** | cnnaware-ml2-crank-hh1x2-with-matched-cnn |
| `ml2_q3` | bibo1x_ane_hh1x4 | 10.26 | 0.1996 | 0.9591 | 29.55 | **FAIL** | ml2-with-hh1x4-cnn |
| `ml2_q3` | bibo1x_ane_l1l2x4 | 10.26 | 0.3137 | 0.9364 | 27.95 | **FAIL** | ml2-with-l1l2x4-cnn |
| `ml2_q3` | matched-ml2 | 10.26 | 0.0683 | 0.9746 | 36.71 | **PASS** | ship-video-freeze-alternate-tighter-lpips |
| `ml2_q3` | bibo1x_ane_ml2_q3_msssim | 10.26 | 0.0847 | 0.9662 | 35.79 | **FAIL** | exp-E15-retrain-msssim-aware |
| `ml2_q3` | bibo1x_ane_sl_q3 | 10.26 | 0.2118 | 0.9513 | 29.08 | **FAIL** | ml2-with-mismatched-sl-cnn |
| `ml2_q3` | bibo1x_ane_sl_q3_strong10 | 10.26 | 0.9234 | 0.4308 | 16.86 | **FAIL** | exp-E8-cnn-strong-10x |
| `ml2_q3` | bibo1x_ane_sl_q3_strong5 | 10.26 | 0.7894 | 0.6310 | 20.88 | **FAIL** | exp-E7-cnn-strong-5x |
| `ml2_q3` | none | 10.26 | 0.2305 | 0.9166 | 28.19 | **FAIL** | ml2-baseline |

VIDEO_FREEZE ceiling (relaxed 2026-05-27): LPIPS ≤ 0.085, MS-SSIM ≥ 0.965, Y-PSNR ≥ 32, ΔE ≤ 2.0

PREVIEW ceiling: LPIPS ≤ 0.15, MS-SSIM ≥ 0.95, Y-PSNR ≥ 28, ΔE ≤ 3.0

## Pi 5 encode timing (legacy gpr_tools, single-thread, Z8Z_0067 50MP, best of 3)

| q | encode ms | bytes (MB) | single-frame fps |
|---:|---:|---:|---:|
| 0 | 1639 | 3.22 | 0.61 |
| 1 | 1661 | 3.75 | 0.60 |
| 2 | 1706 | 5.88 | 0.59 |
| 3 | 1756 | 7.81 | 0.57 |
| 4 | 1822 | 9.79 | 0.55 |
| 5 | 1929 | 13.35 | 0.52 |
| 6 | 1980 | 16.15 | 0.51 |
| 7 | 1973 | 16.15 | 0.51 |
| 8 | 1972 | 16.18 | 0.51 |

## Embedded video capture (Pi 5 sustained)

| pipeline | sustained fps | per-frame MB | per-second MB | restoration |
|---|---:|---:|---:|---|
| `ml2_q3_dec2` (half-res capture) | 24.93 | 1.30 | 31 | needs BIDO Phase B |
| `ml2_q3_l1x2` (full-res via ml2) | 0.51 (Pi 5 too slow) | 7.81 | 187 | desktop ship (Mac decoder + matched CNN) |
