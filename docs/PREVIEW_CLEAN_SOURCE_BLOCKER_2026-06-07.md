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

### v26: Hierarchical K12 Override

Path:

`scene_routed_holdout_v26_k12_c11_override/preview_scene_routed_holdout.json`

Summary:

- pass: 80/84
- pass rate: 95.24%
- worst LPIPS: 0.0595
- median LPIPS: 0.0068
- worst MS-SSIM: 0.9159
- worst Y-PSNR: 27.41 dB
- worst dE2000 mean: 4.03

This pass kept the K5/v24 route intact and added a secondary K12 source-feature
router only as an explicit override for K12 cluster 11. That cluster contains
only `Z8Z_7480 B_center`; its specialist cleared the row with LPIPS 0.0296,
MS-SSIM 0.9642, Y-PSNR 33.31 dB, and dE2000 1.81. This is still diagnostic:
the override is too narrow to register as production without a broader
generalization check.

### v28: K16 Structure Override

Path:

`scene_routed_holdout_v28_k16_c10v3_c15_override/preview_scene_routed_holdout.json`

Summary:

- pass: 82/84
- pass rate: 97.62%
- worst LPIPS: 0.0498
- median LPIPS: 0.0068
- worst MS-SSIM: 0.9642
- worst Y-PSNR: 27.41 dB
- worst dE2000 mean: 4.03

At this stage, this was the best diagnostic route. It keeps the K5 route intact and
uses a K16 source-feature override for two narrow structure cases:

- K16 cluster 10 uses `scene_expert_k16_cluster10_ms_content_v3`, which
  cleared `Z8Z_7480 A_detail` and `Z8Z_7480 C_lowerleft` while preserving
  its two passing neighbors.
- K16 cluster 15 maps the prior `Z8Z_7480 B_center` specialist through the
  same K16 sidecar.

The route is still not production PREVIEW. It fails two high-texture
cluster-4 color/luma rows, and the remaining miss is now dE/Y rather than
LPIPS or structure.

## Remaining Failures

v28 full routed diagnostic failures before the v32 stacked route:

| image | crop | cluster | conditioning | LPIPS | MS-SSIM | Y-PSNR | dE2000 |
|---|---|---:|---|---:|---:|---:|---:|
| Z8Z_0026 | B_center | 4 | content_stats | 0.0234 | 0.9781 | 29.53 | 3.66 |
| Z8Z_6680 | C_lowerleft | 4 | content_stats | 0.0183 | 0.9763 | 27.41 | 4.03 |

v29 cluster-4 LF/Y/Lab fine-tune, evaluated on the same 84-row holdout, stayed
at 82/84. It improved the remaining rows but did not clear them:

| image | crop | route | LPIPS | MS-SSIM | Y-PSNR | dE2000 |
|---|---|---|---:|---:|---:|---:|
| Z8Z_0026 | B_center | K5 cluster 4 | 0.0390 | 0.9774 | 29.89 | 3.47 |
| Z8Z_6680 | C_lowerleft | K5 cluster 4 | 0.0280 | 0.9750 | 27.80 | 3.85 |

The best tighter K40 cluster-35 Lab polish isolated the remaining problem to
one dE miss:

| image | crop | route | LPIPS | MS-SSIM | Y-PSNR | dE2000 | PREVIEW |
|---|---|---|---:|---:|---:|---:|---|
| Z8Z_0026 | B_center | K40 cluster 35 | 0.0793 | 0.9814 | 30.72 | 2.87 | pass |
| Z8Z_0026 | C_lowerleft | K40 cluster 35 | 0.0761 | 0.9799 | 33.88 | 2.07 | pass |
| Z8Z_6680 | C_lowerleft | K40 cluster 35 | 0.0512 | 0.9807 | 28.88 | 3.13 | fail |

Artifact receipts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_holdout_v29_c4_lfy_lab_score_84/preview_scene_routed_holdout.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_expert_k40_cluster35_lab_polish_v5/preview_runtime_refiner.json
```

### v32: Stacked K16/K40 Runtime Route

Path:

`scene_routed_holdout_v32_k16_k40_namespaced_84/preview_scene_routed_holdout.json`

Summary:

- pass: 84/84
- pass rate: 100.0%
- worst LPIPS: 0.0500
- median LPIPS: 0.0068
- worst MS-SSIM: 0.9642
- worst Y-PSNR: 28.86 dB
- worst dE2000 mean: 2.96

This pass added `color_stats` conditioning, trained a K40 cluster-35
low-frequency color specialist, and fixed the routed evaluator so multiple
override sidecars are namespaced by sidecar index. The namespacing matters:
without it, K40 cluster IDs collided with K16 cluster IDs and incorrectly
selected the wrong checkpoint on passing rows.

v32 is the first broad no-REF PREVIEW holdout where every row passes the
committed PREVIEW gates. Runtime inputs remain source RGB, frozen source
feature routers, and selected checkpoints. REF is used only for training and
scoring.

### Channel Oracle

After CI was restored on `master`, a repeatable channel oracle was added at:

`tests/quality_gates/probe_preview_channel_oracle.py`

It was run on the current hard cluster-35 rows:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/preview_channel_oracle_v1/preview_channel_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/preview_channel_oracle_v1/preview_channel_oracle.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/preview_channel_oracle_v1/k40_cluster35_lab_offset_oracle.json
```

Key findings:

- For `Z8Z_6680 C_lowerleft`, K40-v5 has enough structure and Y headroom:
  LPIPS 0.0512, MS-SSIM 0.9807, Y-PSNR 28.88, but dE2000 3.13 fails the
  3.0 PREVIEW ceiling.
- Replacing only K40-v5 Lab a/b with REF a/b clears that row:
  LPIPS 0.0475, MS-SSIM 0.9825, Y-PSNR 28.84, dE2000 2.04. This is oracle
  evidence only; REF channels are not allowed at render time.
- Replacing only K40-v5 Lab L with REF L also clears it:
  LPIPS 0.0082, MS-SSIM 0.9979, Y-PSNR 52.88, dE2000 1.99. This confirms the
  remaining gap is not texture placement.
- Replacing K40-v5 Lab L with the clean UPRESABLE source L fails badly:
  LPIPS 0.5527, MS-SSIM 0.2998, Y-PSNR 17.00, dE2000 9.33.
- A fixed Lab a/b offset does not clear the K40 cluster. The best coarse
  offsets still leave `Z8Z_6680 C_lowerleft` above the dE ceiling and begin
  to consume `Z8Z_0026 B_center` headroom.

This narrows the next experiment further: a deployable fix needs a runtime
source/teacher that predicts scene-specific low-frequency Lab color, not a
constant cluster offset and not another texture/detail pass.

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
- A fixed Lab a/b offset oracle on the K40 cluster-35 polish does not clear
  the remaining `Z8Z_6680 C_lowerleft` dE miss.
- Structure-heavy fine-tunes improved worst LPIPS from 0.1645 to 0.0567 and
  cleared one cluster-4 row, but did not solve the remaining dE/Y/MS rows.
- Lab loss fixed cluster 2 completely, but repeated Lab/Y and MS-SSIM passes
  on cluster 4 are still stuck at 5/9 isolated pass rate.
- A full K12 route regressed to 72/84 because mixed K12 clusters forced one
  checkpoint where the previous K5 route used different experts.
- A hierarchical K12 cluster-11 override cleared `Z8Z_7480 B_center` and raised
  the route to 80/84 without regressions.
- K8/K12 cluster-10 style specialists for `Z8Z_0026`/`Z8Z_6680` high-texture
  rows regressed `Z8Z_6680 B_center`, which already passes under the cluster-2
  polished expert.
- A K16 cluster-10 MS/content-stat specialist cleared the remaining
  `Z8Z_7480` structure rows and raised the route to 82/84, but does not touch
  the two cluster-4 color/luma failures.
- K16 cluster 7, K24 cluster 21, and K40 cluster 35 color/luma specialists all
  failed isolated checks for the remaining `Z8Z_0026`/`Z8Z_6680` rows. The
  newer K40 cluster-35 Lab polish cleared `Z8Z_0026 B_center` but still left
  `Z8Z_6680 C_lowerleft` at dE2000 3.13 against a 3.0 PREVIEW ceiling.

## Current Blocker

The 84-row no-REF crop/full-gate holdout is now clear under v32. The remaining
blocker is deployment proof, not another crop-level color pass:

- run the same stacked-router policy through the full-frame/tiled render path;
- fix arbitrary tile context/routing; the first full-frame tiled smoke fails
  0/3 on `Z8Z_6680`;
- capture encode/decode/model timing and memory for the actual render path;
- only then consider registry promotion.

Full-frame/tiled smoke receipts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_smoke_z8z6680/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_smoke_z8z6680_t512/preview_scene_routed_fullframe.json
```

The 768/128-overlap tiled run scores 0/3 on `Z8Z_6680`: worst LPIPS 0.4103,
worst MS-SSIM 0.7062, worst Y-PSNR 19.04, and worst dE2000 8.05. The
512/no-overlap run also scores 0/3: worst LPIPS 0.3612, worst MS-SSIM 0.7958,
worst Y-PSNR 19.72, and worst dE2000 6.96. Matching the nominal crop size is
therefore insufficient; the failure is arbitrary tile placement/context plus
tile-level route selection.

Follow-up full-frame diagnostics narrowed this further:

- Exact manifest-crop full-frame mode passes 3/3 on `Z8Z_6680`, proving the
  DNG render, crop extraction, checkpoints, and scoring path are consistent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_manifest_crops_v32_z8z6680/preview_scene_routed_fullframe.json`
- High-overlap v32 tiling still fails 0/3, so overlap alone is not the fix:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_smoke_z8z6680_t1024_o768/preview_scene_routed_fullframe.json`
- A reproducible 336-row full-frame tile receipt across the 28-image holdout
  shows the source/REF tile gap is hard before the CNN: raw UPRESABLE source
  tiles pass only 80/336, and the hard diverse images pass 0/12 each before
  refinement:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_train_holdout28_intersect_t512/tile_train_receipt.json`
- A broad global-coordinate tile refiner improves the tile receipt to 272/336
  but still leaves severe cluster-2/cluster-4 failures:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_holdout28_globalcoord_v1/preview_runtime_refiner.json`
- A wider `Z8Z_6680` specialist proves the texture component is learnable on
  the hardest tiles, but LF/luma/color consistency remains the blocker. The
  LF-polished specialist reaches 8/12 on isolated `Z8Z_6680` tiles, then only
  1/3 on stitched full-frame crops:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_globalcoord_w80_lfpolish_v2/preview_runtime_refiner.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_globalcoord_w80_lfpolish_v2_t512/preview_scene_routed_fullframe.json`

The evidenced blocker is now specific: the current local-tile CNN family can
learn detail placement on isolated hard tiles, but it does not maintain
low-frequency luma/color consistency across arbitrary stitched full-frame tiles
from the current UPRESABLE source. The next production candidate should use a
full-frame or larger-context objective, a stronger model with explicit
low-frequency/global color handling, or an upstream source policy that reduces
the source/REF tile mismatch before PREVIEW refinement.

Additional follow-up diagnostics ruled out several simpler fixes:

- `global_color_stats` conditioning, using only full-frame source RGB stats at
  render time, reaches 271/336 on the 28-image tile receipt and 0/3 on the
  stitched `Z8Z_6680` full-frame crop receipt. Full-frame scalar color context
  alone is not enough:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_holdout28_globalcolor_v1/preview_runtime_refiner.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_holdout28_globalcolor_v1_z8z6680_t512/preview_scene_routed_fullframe.json`
- A REF-fit LF affine oracle on the best W80 LF-polished stitched output stays
  at 1/3, even with per-crop affine fits. The remaining misses are not a simple
  RGB gain/bias problem:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/lf_affine_oracle_z8z6680_w80_lfpolish_v2/lf_affine_oracle.json`
- An opt-in dilated-context refiner trained on the hard `Z8Z_6680` 512px tiles
  reaches only 2/12 isolated tiles and 0/3 stitched crops, worse than the
  direct W80 specialist:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_dilated_context_v1/preview_runtime_refiner.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_dilated_context_v1_t512/preview_scene_routed_fullframe.json`
- Training directly on 1024px source/REF tiles with 512px stride also fails
  0/26 on isolated `Z8Z_6680` tiles, so simply increasing tile size without a
  better objective is not enough:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_direct_t1024_o512_v1/preview_runtime_refiner.json`
- A four-row failure-only LF polish fixes one targeted tile but regresses the
  all-12 `Z8Z_6680` tile set from 8/12 to 4/12. Local failure polishing is not
  stable enough to use as a production recipe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_w80_failure_polish_v3_eval12/preview_runtime_refiner.json`
- A stitched-output post-refiner trained on the actual failed full-frame crop
  outputs improves isolated crop LPIPS/MS-SSIM, but still passes only 1/3 on
  the training crops and transfers to 0/3 when applied over the full stitched
  frame. Training the same post-refiner on 12 arbitrary stitched full-frame
  tiles also fails 0/12 isolated tiles. This rules out a small post-correction
  CNN as the immediate fix for the current v32 full-grid path:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_post_refiner_z8z6680_v1/preview_runtime_refiner.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_post_refiner_z8z6680_v1_t512/preview_scene_routed_fullframe.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_post_tile_refiner_z8z6680_t512_v1/preview_runtime_refiner.json`
- Padded-context inference, where each 512px output tile is routed and run
  with 256px of surrounding source context and then cropped back to the tile,
  also fails 0/3 and regresses worst LPIPS to 0.4586. Larger local context by
  itself is not enough:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_contextpad256_z8z6680_t512/preview_scene_routed_fullframe.json`
- Dense 512px sliding-window tiling with 256px overlap improves the smoke but
  still fails 0/3. Worst LPIPS improves from 0.3612 to 0.2713, worst MS-SSIM
  from 0.7958 to 0.8884, worst Y-PSNR from 19.72 to 21.49, and worst dE2000
  from 6.96 to 5.54. It also raises model time from 3.74 s/frame to 14.01
  s/frame on the Mac/MPS diagnostic path:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_dense512_o256_z8z6680/preview_scene_routed_fullframe.json`
- Overlap-save stitching with the same dense 512/256 geometry and a 128px
  valid margin regresses the dense result to worst LPIPS 0.2895, worst MS-SSIM
  0.8660, worst Y-PSNR 20.65, and worst dE2000 6.10. Discarding tile borders is
  not the missing production fix:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_dense512_o256_valid128_z8z6680/preview_scene_routed_fullframe.json`
- Route-context-only inference, where each tile is routed using a 256px padded
  source window but the CNN still receives the original 512px tile, also
  regresses to worst LPIPS 0.4001. Local route padding is not a stable way to
  recover crop-equivalent routing:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_dense512_o256_routepad256_z8z6680/preview_scene_routed_fullframe.json`

The route audit on `Z8Z_6680` now separates two causes. `A_detail` and
`B_center` pass in crop mode but receive mixed experts when covered by
arbitrary full-frame tiles. `C_lowerleft` receives the expected K40 cluster-35
expert in all four intersecting tiles but still fails, which means the blocker
is both route stability and model/source mismatch under arbitrary tile context.

The next candidate should not be another scalar-conditioning or local-polish
variant. Dense tiling helps but remains far outside the gate and too expensive
for production, while overlap-save and route-context-only variants regress. The
next candidate should be a stronger full-image model with an explicit
low-frequency/spatial field branch supervised on assembled full-frame crops and
arbitrary full-frame tiles.

Do not register v11 through v32, the K16 cluster-7 specialists, or the K40
cluster-35 polish specialists as production PREVIEW until the full-frame/tiled
runtime path has equivalent evidence.
