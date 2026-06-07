# PREVIEW Clean Source Blocker - 2026-06-07

## Scope

This audit reran the routed PREVIEW candidate after replacing stale
UPRESABLE editable-DNG sources with clean artifacts generated from the
holdout manifest inputs.

Artifact root:

`/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606`

Clean UPRESABLE source root:

`/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607`

## Source Fix

The previous holdout used stale editable DNGs for some `Z8Z_*` ids. For
example, generated files named `Z8Z_0026.dng` and `Z8Z_0705.dng` carried
capture metadata that did not match the corresponding REF files. This made
the severe PREVIEW failures look like CNN failures when the source artifact
itself was wrong.

Regenerated clean UPRESABLE outputs:

- 28 editable DNGs
- `.gvid`: `upresable_timelapse.gvid`
- MOV wrapper: `upresable_timelapse.gpr1.mov`
- Mac MPS receipt: BIBO_2x around 385-393 ms/frame, full-res encode around
  215-217 ms/frame, DNG export around 1.3-1.7 s/frame

Clean receipt:

`holdout_runtime_crops_v8_clean_upresable_28img/preview_holdout_runtime_source_receipt.json`

Summary:

- 28/28 images present
- 84/84 crop rows
- 0 missing

## Best Routed Results

### v11: Clean Structure Experts

Path:

`scene_routed_holdout_v11_clean_structure_c2c4/preview_scene_routed_holdout.json`

Summary:

- pass: 76/84
- pass rate: 90.48%
- worst LPIPS: 0.1725
- median LPIPS: 0.0088
- worst MS-SSIM: 0.8168
- worst Y-PSNR: 24.27 dB
- worst dE2000 mean: 5.83
- M5 model median: 9.16 ms/crop
- M5 peak RSS: 933 MB

### v12: Mixed Content-Stats Experts

Path:

`scene_routed_holdout_v12_mixed_contentstats_c2c4/preview_scene_routed_holdout.json`

Summary:

- pass: 76/84
- pass rate: 90.48%
- worst LPIPS: 0.1725
- median LPIPS: 0.0088
- worst MS-SSIM: 0.8168
- worst Y-PSNR: 25.01 dB
- worst dE2000 mean: 5.51
- M5 model median: 9.15 ms/crop
- M5 peak RSS: 924 MB

The mixed-conditioning path improved some Y/dE values but did not improve
aggregate pass rate.

### v13: Gate-Space Luma/Opponent Loss

Path:

`scene_routed_holdout_v13_gate_luma_c1c2c4/preview_scene_routed_holdout.json`

Summary:

- pass: 76/84
- pass rate: 90.48%
- worst LPIPS: 0.1645
- median LPIPS: 0.0082
- worst MS-SSIM: 0.8437
- worst Y-PSNR: 26.17 dB
- worst dE2000 mean: 4.78

This pass added differentiable BT.709 luma and RGB-opponent losses to the
runtime PREVIEW trainer and selected checkpoints using those gate-space
proxies. It improved the failure rows again, but did not clear additional
rows.

## Remaining Failures

v13 failures:

| image | crop | cluster | conditioning | LPIPS | MS-SSIM | Y-PSNR | dE2000 |
|---|---|---:|---|---:|---:|---:|---:|
| Z8Z_0026 | A_detail | 2 | content_stats | 0.0583 | 0.9640 | 29.40 | 3.18 |
| Z8Z_0026 | B_center | 4 | content_stats | 0.0879 | 0.9683 | 28.56 | 4.21 |
| Z8Z_0026 | C_lowerleft | 4 | content_stats | 0.0837 | 0.9643 | 31.63 | 3.04 |
| Z8Z_6680 | B_center | 2 | content_stats | 0.0482 | 0.9821 | 27.93 | 3.58 |
| Z8Z_6680 | C_lowerleft | 4 | content_stats | 0.0616 | 0.9619 | 26.17 | 4.78 |
| Z8Z_7480 | A_detail | 1 | zero | 0.1645 | 0.8437 | 29.71 | 2.86 |
| Z8Z_7480 | B_center | 4 | content_stats | 0.1141 | 0.9338 | 32.40 | 2.06 |
| Z8Z_7480 | C_lowerleft | 4 | content_stats | 0.1040 | 0.9163 | 31.33 | 2.51 |

## Ruled Out

- Stale source identity was a real blocker and is fixed by the v8 clean
  UPRESABLE receipt.
- Simple global or per-cluster affine RGB correction did not change pass
  rate; it stayed at 76/84.
- Content-stat conditioning for clusters 2 and 4 improved some Y/dE values
  but did not change pass rate.
- A width-80 cluster-4 expert trained from scratch remained far worse than
  the width-40 expert by step 300 and was stopped.
- Gate-space luma/opponent loss improved the same hard rows but held pass
  rate at 76/84.
- A stronger color/luma-weighted cluster-4 pass worsened LPIPS headroom and
  still held pass rate at 4/9 for that cluster.
- A 768-pixel context-crop cluster-4 expert remained far behind the 512-crop
  expert by step 300 and was stopped; simple larger-context retraining did
  not solve the blocker.

## Current Blocker

The remaining failures are not caused by REF leakage, stale source files, or
a simple fixed color transform. They are concentrated in hard source/target
rows where the clean UPRESABLE source starts far outside the PREVIEW gate and
the current crop-local expert improves LPIPS substantially but under-corrects
low-frequency luma/color and local structure.

Most likely next causes to test:

- full-image context may still be required, but it likely needs a real
  full-frame/tiled render path rather than naive 768-crop retraining;
- the UPRESABLE source target is not aligned enough with REF for these scenes;
- the current model can improve gate-space luma/color but lacks enough
  structure/detail correction for the remaining rows;
- a stronger teacher/full-image target is needed for `Z8Z_0026`, `Z8Z_6680`,
  and `Z8Z_7480`.

Do not register v11, v12, or v13 as production PREVIEW. They are diagnostic
candidates only.
