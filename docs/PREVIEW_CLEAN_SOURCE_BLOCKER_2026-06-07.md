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

### v20: Lab-Tuned Clusters 2/4 + Structure-Tuned Cluster 1

Path:

`scene_routed_holdout_v20_c1struct_c2c4lab/preview_scene_routed_holdout.json`

Summary:

- pass: 78/84
- pass rate: 92.86%
- worst LPIPS: 0.0567
- median LPIPS: 0.0068
- worst MS-SSIM: 0.8945
- worst Y-PSNR: 27.02 dB
- worst dE2000 mean: 4.23

This pass added differentiable Lab loss to the runtime PREVIEW trainer.
Cluster 2 improved from 7/9 to 8/9 and cluster 4 improved dE/Y headroom, but
the cluster-4 `Z8Z_7480` rows remained MS-SSIM limited.

### v22: Cluster 2 Lab Polish

Path:

`scene_routed_holdout_v22_c2polish_c4laby/preview_scene_routed_holdout.json`

Summary:

- pass: 79/84
- pass rate: 94.05%
- worst LPIPS: 0.0567
- median LPIPS: 0.0068
- worst MS-SSIM: 0.8945
- worst Y-PSNR: 27.32 dB
- worst dE2000 mean: 4.05

This pass polished cluster 2 with stronger Lab/Y scoring. Cluster 2 reached
9/9 isolated pass rate, clearing `Z8Z_6680 B_center` with dE2000 2.96.

### v24: Cluster 1/4 MS Polish

Path:

`scene_routed_holdout_v24_c1ms_c2polish_c4ms/preview_scene_routed_holdout.json`

Summary:

- pass: 79/84
- pass rate: 94.05%
- worst LPIPS: 0.0595
- median LPIPS: 0.0068
- worst MS-SSIM: 0.9159
- worst Y-PSNR: 27.41 dB
- worst dE2000 mean: 4.03

This is the current best diagnostic route by severe-failure profile. It keeps
the v22 pass count, improves worst MS-SSIM from 0.8945 to 0.9159, and improves
worst dE2000 from 4.05 to 4.03. It still fails the PREVIEW gate and must not
be registered as production.

## Remaining Failures

v24 failures:

| image | crop | cluster | conditioning | LPIPS | MS-SSIM | Y-PSNR | dE2000 |
|---|---|---:|---|---:|---:|---:|---:|
| Z8Z_0026 | B_center | 4 | content_stats | 0.0234 | 0.9781 | 29.53 | 3.66 |
| Z8Z_6680 | C_lowerleft | 4 | content_stats | 0.0183 | 0.9763 | 27.41 | 4.03 |
| Z8Z_7480 | A_detail | 1 | zero | 0.0595 | 0.9159 | 30.28 | 2.77 |
| Z8Z_7480 | B_center | 4 | content_stats | 0.0354 | 0.9485 | 32.52 | 1.98 |
| Z8Z_7480 | C_lowerleft | 4 | content_stats | 0.0341 | 0.9421 | 31.62 | 2.36 |

## Ruled Out

- Stale source identity was a real blocker and is fixed by the v8 clean
  UPRESABLE receipt.
- Simple global or per-cluster affine RGB correction did not change pass
  rate; it stayed at 76/84.
- Content-stat conditioning for clusters 2 and 4 improved some Y/dE values
  but did not change pass rate.
- Running the v13 ensemble on 768-pixel context crops and scoring the center
  512 region regressed to 73/84 with row clusters fixed and 72/84 with
  sidecar rerouting; the current crop-trained experts do not tolerate larger
  context windows.
- Source pass-through for clusters 1/2/4 regressed badly; the clean
  UPRESABLE source alone is far outside the PREVIEW gate for these clusters.
- A width-80 cluster-4 expert trained from scratch remained far worse than
  the width-40 expert by step 200 and was stopped.
- Gate-space luma/opponent loss improved the same hard rows but held pass
  rate at 76/84.
- A stronger color/luma-weighted cluster-4 pass worsened LPIPS headroom and
  still held pass rate at 4/9 for that cluster.
- A 768-pixel context-crop cluster-4 expert remained far behind the 512-crop
  expert by step 300 and was stopped; simple larger-context retraining did
  not solve the blocker.
- Fixed per-cluster RGB affine and per-row RGB affine oracles did not clear
  the remaining rows. Per-row affine reached only 77/84, so the gap is not a
  simple global color transform.
- Structure-heavy fine-tunes improved worst LPIPS from 0.1645 to 0.0567 and
  cleared one cluster-4 row, but did not solve the remaining dE/Y/MS rows.
- Lab loss fixed cluster 2 completely, but repeated Lab/Y and MS-SSIM passes
  on cluster 4 are still stuck at 5/9 isolated pass rate.

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

Do not register v11 through v24 as production PREVIEW. They are diagnostic
candidates only.
