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

## Full-Frame Tiled Follow-Up

The crop-aligned v32 pass does not carry over to arbitrary full-frame tiling.
The current full-grid receipts use 512px tiles with no overlap and score the
manifest crops from stitched full-frame output. REF remains scoring-only.

### v32 Baseline Full-Grid Holdout

Path:

`fullframe_tiled_v32_holdout28_baseline_t512/preview_scene_routed_fullframe.json`

Summary:

- pass: 57/84
- pass rate: 67.86%
- worst LPIPS: 0.5749
- median LPIPS: 0.0192
- worst MS-SSIM: 0.6288
- worst Y-PSNR: 17.34 dB
- worst dE2000 mean: 14.66
- MPS model time: 88.79 s total, 3.17 s/frame mean
- peak RSS: 5819 MB

The failures are concentrated in the hard full-grid images:
`Z8Z_0026`, `Z8Z_0705`, `Z8Z_1586`, `Z8Z_5284`, `Z8Z_5937`,
`Z8Z_6680`, `Z8Z_7480`, and `Z8Z_7955`.

### Hair/Skin Scene-Gated Spatial Specialist

A full-grid specialist trained on actual arbitrary `Z8Z_0680 B_center` tiles
fixed the hair/skin scene family when applied through a runtime scene-role
gate. The gate is based on the full-frame pre-route role histogram:

- `cluster_0 >= 140`
- `cluster_3 >= 15`

This enabled the spatial `hair_a` and `hair_b` regions only for
`Z8Z_0680`, `Z8Z_0694`, and `Z8Z_0718` in the 28-image holdout.

Three-image smoke:

`fullframe_tiled_v32_hair3_scene_gated_hairb_train0680_v1_t512/preview_scene_routed_fullframe.json`

- pass: 9/9
- worst LPIPS: 0.0766
- worst MS-SSIM: 0.9862
- worst Y-PSNR: 38.06 dB
- worst dE2000 mean: 1.53

Full 28-image holdout:

`fullframe_tiled_v32_holdout28_scene_gated_hairb_train0680_v1_t512/preview_scene_routed_fullframe.json`

- pass: 63/84
- pass rate: 75.0%
- worst LPIPS: 0.5749
- median LPIPS: 0.0191
- worst MS-SSIM: 0.6288
- worst Y-PSNR: 19.26 dB
- worst dE2000 mean: 8.75
- MPS model time: 94.28 s total, 3.37 s/frame mean
- peak RSS: 5750 MB

The same spatial specialist without the scene-role gate regressed the full
holdout to 33/84, so coordinate-only spatial routing is not production-safe.
The scene gate is the correct direction: use runtime source-route features to
select specialists, not image ids or fixed coordinates alone.

### Current Blocker After Scene Gating

The scene-gated result is still not production PREVIEW. Remaining failures are
21 rows across eight hard images:

| image | passing crops | dominant issue |
|---|---:|---|
| Z8Z_0026 | 0/3 | severe B-center dE/Y plus A/C structure |
| Z8Z_0705 | 0/3 | A-detail LPIPS and B/C dE/MS |
| Z8Z_1586 | 1/3 | A/B LPIPS |
| Z8Z_5284 | 1/3 | A LPIPS and C dE/MS |
| Z8Z_5937 | 0/3 | C lower-left LPIPS/Y/dE |
| Z8Z_6680 | 0/3 | B/C low-frequency Y/dE |
| Z8Z_7480 | 0/3 | A/B/C structure and dE |
| Z8Z_7955 | 1/3 | A LPIPS/dE and C MS |

## Full-Image Source-Feature Residual Oracle

The next diagnostic tested whether the remaining hard-eight residual is
explainable by a shallow non-affine model using only runtime-available source
features at application time. The model fits REF-source residuals per full
image from source RGB powers, blurred low-fields, high-pass fields, local
gradient/laplacian energy, and image coordinates. Because REF is used for
fitting, this is an oracle ceiling and not a production candidate.

Receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/residual_features_hard8_w4096_v1/preview_fullimage_residual_features.json
```

Result:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
|---|---:|---:|---:|---:|---:|
| source baseline, 4096-wide | 0/24 | 0.7155 | 0.3163 | 17.21 | 10.51 |
| source-feature residual ridge, 4096-wide | 0/24 | 0.7893 | 0.3621 | 18.36 | 8.28 |

A stronger non-linear residual-transfer oracle was then run at 2048 width with
an 80k source-feature residual dictionary and 8-neighbor KD-tree transfer:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/residual_features_knn_hard8_w2048_v1/preview_fullimage_residual_features.json
```

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
|---|---:|---:|---:|---:|---:|
| source baseline, 2048-wide | 0/24 | 0.8083 | 0.3184 | 17.29 | 10.16 |
| source-feature residual kNN k=8, 2048-wide | 0/24 | 0.7988 | 0.3292 | 18.02 | 8.77 |
| source-feature residual ridge, 2048-wide | 0/24 | 0.8369 | 0.3279 | 18.10 | 8.52 |

Interpretation: source-feature residual fitting improves color/luma metrics
but does not clear any hard-eight row. The kNN variant is less bad than ridge
on LPIPS, but still leaves worst LPIPS near 0.8 and is far too slow to be a
production primitive. The full-frame PREVIEW blocker is therefore not solved
by local affine, shallow feature-regressed residual fields, or non-linear
hand-feature residual transfer. The next candidate needs a stronger full-image
structure/detail model or a different source/teacher representation.

## Full-Image Dense-Warp Oracle

A REF-guided dense optical-flow oracle then tested whether local
geometry/detail placement is the dominant blocker. It estimates flow from REF
and source luminance on the full downsampled image, then warps the source
field before scoring manifest crops. Because REF is used to estimate flow,
this is diagnostic only.

Receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/dense_warp_hard8_w1024_v1/preview_fullimage_dense_warp_oracle.json
```

Result:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
|---|---:|---:|---:|---:|---:|
| source baseline, 1024-wide | 0/24 | 0.9179 | 0.2510 | 17.25 | 9.77 |
| TV-L1 warp plus, 1024-wide | 0/24 | 0.9111 | 0.4161 | 18.03 | 8.90 |
| ILK warp plus, 1024-wide | 0/24 | 0.9181 | 0.3696 | 18.01 | 8.98 |
| ILK warp minus, 1024-wide | 0/24 | 0.9411 | 0.1996 | 16.90 | 9.98 |
| TV-L1 warp minus, 1024-wide | 0/24 | 0.9451 | 0.2061 | 16.94 | 9.87 |

Interpretation: dense REF-guided warping moves MS-SSIM/Y/dE in the right
direction for the best flow direction, but LPIPS remains near 0.91 and no
hard-eight row passes. The full-frame PREVIEW blocker is therefore not simply
small alignment, local affine color, hand-feature residual transfer, or dense
local geometric warp. The next candidate needs a stronger full-image
structure/detail model or a better source/teacher representation.

Two `Z8Z_0026` full-grid all-crop fine-tunes were tried from the K40
color-stat checkpoint:

- `scene_expert_z8z0026_fullgrid_allcrops_v1`: global-color conditioning,
  420 steps, 0/12 isolated tile pass.
- `scene_expert_z8z0026_fullgrid_colorstats_v2`: aligned color-stat
  conditioning, 320 steps, 0/12 isolated tile pass.

A wider direct scratch model was also started for `Z8Z_0026`, but at step 130
it remained much worse than the width-40 fine-tunes and was stopped. Current
evidence narrows `Z8Z_0026` to a model/context/source-target formulation
blocker, not a simple checkpoint-conditioning mismatch.

Signal/oracle checks on the 12 arbitrary `Z8Z_0026` training tiles show that
simple color or low-frequency correction is also not enough. Raw source tiles
had LPIPS around 0.52-0.68 and dE2000 around 4.8-8.6. Per-tile RGB affine
matching and a radius-16 low-frequency residual oracle only moved dE modestly
and left LPIPS around 0.48-0.70. Since exact manifest-crop mode passes while
arbitrary tile mode fails, the next `Z8Z_0026` attempt should use a
context/full-crop formulation, not another direct 512px color fine-tune.

### Larger Tile Diagnostic

Path:

`fullframe_tiled_v32_hard8_t1024_baseline/preview_scene_routed_fullframe.json`

Summary on the eight remaining hard images:

- pass: 4/24
- pass rate: 16.67%
- worst LPIPS: 0.5546
- median LPIPS: 0.2552
- worst MS-SSIM: 0.5114
- worst Y-PSNR: 18.71 dB
- worst dE2000 mean: 9.07

This rules out simply increasing runtime tile size with the existing
512-trained specialists. The route/content distribution changes enough that
1024px tiling regresses the hard rows. Future larger-context work needs
matched training receipts and model selection, or a full-image/context-aware
model, rather than an inference-only tile-size change.

### Coordinate/Alignment Diagnostic

The full-frame evaluator now pads non-grid-sized diagnostic inputs to the
CNN stride and crops predictions back to the requested region. This lets
manifest-crop mode evaluate arbitrary crop boxes without crashing on skip-path
shape mismatches.

Hard-eight manifest-crop local-coordinate path:

`fullframe_manifest_crops_v32_hard8/preview_scene_routed_fullframe.json`

- pass: 16/24
- pass rate: 66.67%
- worst LPIPS: 0.2898
- median LPIPS: 0.0732
- worst MS-SSIM: 0.7124
- worst Y-PSNR: 25.31 dB
- worst dE2000 mean: 3.66

Three hard images that fail full-grid do pass in exact 512 crop mode:
`Z8Z_0026`, `Z8Z_0705`, and `Z8Z_6680`. This isolates a major failure mode:
when the same crop is split across arbitrary grid tiles, the model sees each
piece with different local 0..1 coordinate planes and different route/context
statistics than it saw in crop-aligned mode.

Hard-eight manifest-crop global-coordinate path:

`fullframe_manifest_crops_v32_hard8_globalcoord/preview_scene_routed_fullframe.json`

- pass: 4/24
- pass rate: 16.67%
- worst LPIPS: 0.3456
- median LPIPS: 0.1608
- worst MS-SSIM: 0.6902
- worst Y-PSNR: 22.90 dB
- worst dE2000 mean: 5.35

The current checkpoints are therefore strongly dependent on crop-local
coordinate planes. Simply switching inference to global coordinates is not
viable. The next production-shaped PREVIEW experiment should train or distill
experts with the same coordinate contract used at runtime: full-frame/global
or coordinate-free inputs, arbitrary tile placement, and stitched-crop losses.

A first coordinate-free direct fine-tune was added with `--coordinate-mode
zero_coord`, which keeps the nine-channel input contract but fills the two
coordinate planes with zero. The `Z8Z_0026` all-crop full-grid run:

`scene_expert_z8z0026_fullgrid_zerocoord_v1/preview_runtime_refiner.json`

- training: 320 steps from the K40 color-stat checkpoint
- result: 0/12 isolated arbitrary tile pass
- worst LPIPS: 0.3537
- median LPIPS: 0.2514
- worst MS-SSIM: 0.7029
- worst Y-PSNR: 22.07 dB
- worst dE2000 mean: 5.62

This rules out a simple coordinate-plane ablation with the same direct model.
The next attempt should change model/context formation, for example training a
full-crop or full-image teacher/student that supervises arbitrary tiles from
their stitched crop output instead of asking isolated 512px tiles to solve the
hard image independently.

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
- The full-frame evaluator now exposes the same class of multi-origin geometry
  as repeated `--tile-offset X,Y` values, so the diagnostic can be reproduced
  without overloading overlap semantics. The 2026-06-12 four-origin receipt
  also fails 0/3 on `Z8Z_6680`: worst LPIPS 0.2713, worst MS-SSIM 0.8884,
  worst Y-PSNR 21.49, worst dE2000 5.54, runtime 24.82 s/frame, and 672 model
  tiles:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/fullframe_multi_offset_v32_z8z6680_t512_o256_v1/preview_scene_routed_fullframe.json`
- A runtime-safe source-frequency representation was then added to the PREVIEW
  runtime trainer and optional full-frame post-refiner path. It appends
  low/high planes derived only from source RGB, giving a 15-channel input while
  keeping REF as target/scoring data only. A hard-eight stitched manifest-crop
  capacity check from the broad holdout source still reaches only 3/24, with
  worst LPIPS 0.5604, worst MS-SSIM 0.6496, worst Y-PSNR 20.10, and worst
  dE2000 8.28:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/stitched_post_hard8_manifest_from_holdout_v1/stitched_post_receipt.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/source_frequency_post_hard8_w40_v1/preview_runtime_refiner.json`
- A full-image band refiner diagnostic then tested the next adjacent
  formulation: predict a downsampled full-frame RGB low/mid field from
  runtime source RGB plus normalized coordinates, then either score it directly
  or compose it with source high-frequency detail. The hard-eight v32 stitched
  receipt remains blocked: source baseline is 4/24, exact REF low-field
  residual is also 4/24, and learned full-image band variants regress to 0/24
  with worst dE2000 above 22. The newer multi-origin `Z8Z_6680` smoke also
  stays 0/3; exact REF low-field residual only moves worst LPIPS from 0.2713
  to 0.2702 and worst dE2000 from 5.54 to 5.32. This rules out the current
  generated low/mid field plus source-detail composition as the production
  fix:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/fullimage_band_refiner_hard8_from_v32_capacity_v1/preview_fullimage_band_refiner.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/fullimage_band_refiner_hard8_from_v32_capacity_v1/preview_fullimage_band_refiner.html`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/fullimage_band_refiner_z8z6680_from_multioffset_smoke_v1/preview_fullimage_band_refiner.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/fullimage_band_refiner_z8z6680_from_multioffset_smoke_v1/preview_fullimage_band_refiner.html`
- A REF-assisted crop alignment oracle then tested whether the source/REF
  render-size mismatch is responsible for the full-frame failure. It rescored
  manifest crops after shifting and slightly scaling the output crop box. A
  dense `Z8Z_6680` multi-origin search stays 0/3 with unchanged worst LPIPS
  0.2713 and worst dE2000 5.54. A broader hard-eight v32 coarse search stays
  4/24 with zero failing rows recovered; the best worst-row LPIPS only moves
  from 0.5546 to 0.5486 and worst dE2000 remains 9.07. This rules out small
  crop/active-area alignment as the missing production fix:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/alignment_oracle_z8z6680_multioffset_v1/preview_fullframe_alignment_oracle.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/alignment_oracle_z8z6680_multioffset_v1/preview_fullframe_alignment_oracle.html`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/alignment_oracle_hard8_v32_coarse_v1/preview_fullframe_alignment_oracle.json`
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/alignment_oracle_hard8_v32_coarse_v1/preview_fullframe_alignment_oracle.html`
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

The first low-frequency/spatial branch pass was implemented as
`lowfreq_spatial`: the previous direct local refiner plus a coarse RGB residual
field predicted from downsampled source/coordinate/stat planes. A cold-start v1
reached only 5/12 isolated `Z8Z_6680` tiles. Initializing the local branch from
the prior W80 LF-polished direct specialist and training full-batch with stronger
Y/Lab losses produced the best isolated hard-tile result so far:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_lf_spatial_fullbatch_v3/preview_runtime_refiner.json
```

v3 tile summary:

- pass: 9/12
- worst LPIPS: 0.0941
- worst MS-SSIM: 0.9602
- worst Y-PSNR: 26.15
- worst dE2000: 3.82

The stitched full-frame result still passes only 1/3:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_spatial_fullbatch_v3_t512/preview_scene_routed_fullframe.json
```

v3 stitched summary:

- pass: 1/3
- worst LPIPS: 0.1099
- worst MS-SSIM: 0.9422
- worst Y-PSNR: 24.84
- worst dE2000: 4.27

Dense 512/256 overlap with the same v3 model regresses to worst LPIPS 0.1375,
worst MS-SSIM 0.9192, worst Y-PSNR 23.90, and worst dE2000 4.67:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_spatial_fullbatch_v3_t512_o256/preview_scene_routed_fullframe.json
```

A focused v4 pass added weighted sampling of tiles intersecting `B_center` and
`C_lowerleft`:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_lf_spatial_focus_v4/preview_runtime_refiner.json
```

v4 isolated tile summary:

- pass: 9/12
- worst LPIPS: 0.1064
- worst MS-SSIM: 0.9619
- worst Y-PSNR: 26.52
- worst dE2000: 3.68

The stitched v4 full-frame result remains 1/3:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_spatial_focus_v4_t512/preview_scene_routed_fullframe.json
```

v4 stitched summary:

- pass: 1/3
- worst LPIPS: 0.1171
- worst MS-SSIM: 0.9503
- worst Y-PSNR: 25.41
- worst dE2000: 4.05

Compared with v3 stitched output, v4 improves center/lower-left dE and Y-PSNR
slightly, but worsens lower-left LPIPS/MS-SSIM and does not clear the gate. The
narrowed blocker is therefore not just sample weighting. The next experiment
should train against assembled full-frame/crop losses or change the runtime
source/model formulation so the LF branch sees the same spatial problem that is
scored after stitching.

## Assembled-Crop Loss Follow-Up

The next trainer revision adds an optional assembled-crop loss. For each
manifest crop, it groups the intersecting full-frame receipt tiles, predicts the
tiles, assembles them into their full-frame positions, crops the manifest window,
and applies the same LF/perceptual losses to that stitched crop. This keeps REF
as training/scoring target only and uses runtime-valid source tiles,
coordinates, and source global stats as inputs.

The first assembled pass, v5, starts from v4 and supervises `B_center` and
`C_lowerleft`:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_lf_spatial_assembled_v5/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_spatial_assembled_v5_t512/preview_scene_routed_fullframe.json
```

v5 isolated tile summary:

- pass: 10/12
- worst LPIPS: 0.0820
- worst MS-SSIM: 0.9663
- worst Y-PSNR: 26.95
- worst dE2000: 3.50

v5 stitched summary:

- pass: 2/3
- worst LPIPS: 0.0835
- worst MS-SSIM: 0.9555
- worst Y-PSNR: 25.90
- worst dE2000: 3.90

v5 is the first full-frame/tiled diagnostic to pass `B_center`; the remaining
failure is `C_lowerleft`, where LPIPS and MS-SSIM pass but Y-PSNR and dE2000
miss.

C-focused v6 and v7 runs add assembled-aware checkpoint selection and heavier
`C_lowerleft` luma/Lab pressure:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_spatial_assembled_cfocus_v6_t512/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_spatial_assembled_cfocus_v7_t512/preview_scene_routed_fullframe.json
```

v6 stitched summary:

- pass: 2/3
- worst LPIPS: 0.0865
- worst MS-SSIM: 0.9624
- worst Y-PSNR: 26.53
- worst dE2000: 3.69

v7 stitched summary:

- pass: 2/3
- worst LPIPS: 0.0955
- worst MS-SSIM: 0.9640
- worst Y-PSNR: 26.72
- worst dE2000: 3.63

These runs narrow the lower-left color/luma miss but do not reach the PREVIEW
gate. The failure is now specific: the current low-frequency spatial model can
learn enough full-frame context to pass `B_center`, but cannot push
`C_lowerleft` to Y-PSNR >= 28.0 and dE2000 <= 3.0 without trading away local
quality. The next candidate should change the runtime source/model formulation,
for example a stronger low-frequency field, larger-context/full-frame branch,
or source-side normalization for lower-left luma/color bias.

## Residual LF Field Follow-Up

The next trainer revision adds two production-shaped safeguards:

- a residual low-frequency wrapper, `lowfreq_spatial_residual`, that loads the
  prior low-frequency spatial model as a base and learns an additional
  zero-initialized coarse gain/bias field;
- initial-checkpoint scoring, so a candidate cannot lose the initialized model
  if every optimizer update is worse.

Residual-only v8 freezes the v5 base and trains only the added field:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_lf_residual_cfocus_v8/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_residual_cfocus_v8_t512/preview_scene_routed_fullframe.json
```

The residual-only branch does not improve over the initialized v5 state. The
stitched result remains 2/3 with the same lower-left miss:

- worst LPIPS: 0.0835
- worst MS-SSIM: 0.9555
- worst Y-PSNR: 25.90
- worst dE2000: 3.90

Co-trained residual v9 allows both the base LF field and residual field to move:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_lf_residual_cotrain_v9/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_residual_cotrain_v9_t512/preview_scene_routed_fullframe.json
```

v9 still passes only 2/3 stitched crops and does not beat the prior C-focused
results:

- worst LPIPS: 0.1023
- worst MS-SSIM: 0.9629
- worst Y-PSNR: 26.63
- worst dE2000: 3.65

Finally, v10 trains the residual lower-left correction across all 28 holdout
images:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_all28_lf_residual_cfocus_v10/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lf_residual_all28_v10_t512/preview_scene_routed_fullframe.json
```

v10 is explicitly ruled out. The 336-row isolated tile receipt passes only
75/336, with worst LPIPS 0.8745, worst MS-SSIM 0.3431, worst Y-PSNR 18.43, and
worst dE2000 9.06. The `Z8Z_6680` stitched smoke regresses to 1/3. This shows
that a single broad lower-left spatial/source normalization is not scene-stable;
the remaining blocker likely needs scene/cluster-conditioned low-frequency
correction or a stronger full-frame source representation, not a global
lower-left correction shared across the holdout.

Do not register v11 through v32, the K16 cluster-7 specialists, or the K40
cluster-35 polish specialists as production PREVIEW until the full-frame/tiled
runtime path has equivalent evidence.

## Cluster/Spatial Override Follow-Up

The next diagnostic added two runtime-valid hooks:

- receipt training can hard-filter rows by `intersects_crops`, so a specialist
  can train only on tiles that intersect a manifest crop;
- full-frame evaluation can select a checkpoint by normalized tile-center
  bounds plus an optional runtime cluster constraint. The selection inputs are
  source RGB, frozen route features, and tile coordinates only; REF content,
  crop identity key planes, sample index, winner JSON, and gate metrics remain
  forbidden.

The `C_lowerleft` tile receipt shows the broad K5 cluster is not homogeneous:

- cluster 0: 84 tiles across 21 images
- cluster 1: 6 tiles across 2 images
- cluster 2: 7 tiles across 3 images
- cluster 4: 15 tiles across 5 images

For `Z8Z_6680`, the four `C_lowerleft` intersecting tiles are all K5 cluster
4: `tile_1024_4096`, `tile_1536_4096`, `tile_1024_4608`, and
`tile_1536_4608`.

Two narrow lower-left cluster-4 specialists were trained:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_c_lowerleft_cluster4_spatial_v12/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_c_lowerleft_cluster4_spatial_ft_v13/preview_runtime_refiner.json
```

v12 trained from scratch and is ruled out immediately:

- pass: 0/15
- worst LPIPS: 0.6948
- worst MS-SSIM: 0.6605
- worst Y-PSNR: 19.48
- worst dE2000: 8.72

v13 fine-tuned from the v5 assembled full-frame candidate and improved the
isolated lower-left cluster-4 receipt, but it is still not a production
specialist:

- pass: 6/15
- worst LPIPS: 0.5773
- median LPIPS: 0.1443
- worst MS-SSIM: 0.8268
- worst Y-PSNR: 26.75
- worst dE2000: 3.66

The full-frame spatial route applied v13 only to K5 cluster-4 tiles whose
normalized tile centers fell in `x=[0.10, 0.28]`, `y=[0.72, 1.00]`:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_v5_spatial_llc4_v13_t512/preview_scene_routed_fullframe.json
```

That route selected the spatial specialist on 8 of 187 full-frame tiles. It
did not clear the stitched blocker:

- pass: 2/3
- `A_detail`: pass, LPIPS 0.0368, MS-SSIM 0.9916, Y-PSNR 40.02, dE2000 1.32
- `B_center`: pass, LPIPS 0.0496, MS-SSIM 0.9846, Y-PSNR 28.36, dE2000 2.56
- `C_lowerleft`: fail, LPIPS 0.1013, MS-SSIM 0.9522, Y-PSNR 25.66, dE2000
  4.01

This rules out the current lower-left cluster-4 coordinate override. The
failure is now specifically a stitched full-frame transfer problem: a specialist
can improve selected isolated tiles, but the correction does not compose into a
passing `C_lowerleft` crop after arbitrary 512px full-frame tiling. The next
candidate should change the representation rather than keep adding narrow
sampling: likely a full-frame/low-frequency Lab field, a larger context model
that predicts a smooth correction over the scored crop, or a source-side
normalization target that aligns the lower-left Lab field before local detail
refinement.

## Mid-Frequency Residual Follow-Up

The corrected stitched-oracle diagnostic crops REF and stitched source with
their own render dimensions before scoring. It shows the remaining miss is not
pure broad LF color:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/oracle_stitched_midfreq_rgb_z8z6680_v1/oracle_stitched_midfreq_rgb.json
```

Key rows on `Z8Z_6680 C_lowerleft`:

- base v5 stitched crop: LPIPS 0.0835, MS-SSIM 0.9555, Y-PSNR 25.90,
  dE2000 3.90, fail
- REF-derived RGB residual blurred at radius 1: LPIPS 0.0927, MS-SSIM 0.9849,
  Y-PSNR 29.36, dE2000 2.53, pass
- REF-derived RGB residual blurred at radius 1.5: LPIPS 0.0834, MS-SSIM
  0.9720, Y-PSNR 27.22, dE2000 3.24, fail

That narrows the missing signal to a mid-frequency correction. A very smooth
field is insufficient; the useful correction sits near the radius-1 boundary
after the scored crop resize.

The next architecture adds a zero-initialized mid-frequency residual wrapper
around the existing `lowfreq_spatial` base. It can load the v5 checkpoint into
the base, freeze it, and train only the added residual branch:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_midfreq_residual_v14/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_midfreq_residual_v14_t512/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_midfreq_residual_strong_v15/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_midfreq_residual_strong_v15_t512/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_midfreq_residual_xstrong_v16/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_midfreq_residual_xstrong_v16_t512/preview_scene_routed_fullframe.json
```

v14 isolated tile receipt:

- pass: 10/12
- worst LPIPS: 0.0803
- worst MS-SSIM: 0.9673
- worst Y-PSNR: 27.09
- worst dE2000: 3.41

v14 stitched smoke:

- pass: 2/3
- `C_lowerleft`: LPIPS 0.0782, MS-SSIM 0.9580, Y-PSNR 26.12, dE2000 3.74

v15 doubles the bounded mid-frequency branch. It is the best stitched result
from this pass, but it still fails:

- isolated pass: 10/12
- stitched pass: 2/3
- `C_lowerleft`: LPIPS 0.0784, MS-SSIM 0.9582, Y-PSNR 26.13, dE2000 3.72

v16 uses the extra-strong branch and regresses:

- isolated pass: 10/12
- stitched pass: 2/3
- `C_lowerleft`: LPIPS 0.0825, MS-SSIM 0.9567, Y-PSNR 26.03, dE2000 3.84

This rules out branch amplitude as the main issue. The oracle says
mid-frequency correction can clear the row; the learned residual wrappers do
not learn enough of that correction from the current tile/assembled objective.
The next production-shaped experiment should change the target/objective rather
than only increasing residual scale: train against an explicit radius-1
teacher/residual target, supervise the assembled crop with a mid-frequency
bandpass loss, or predict the correction from larger/full-crop context before
stitching.

## Explicit Mid-Frequency Teacher Loss

The next trainer revision adds an opt-in `midfreq_residual_loss`: it compares
the Gaussian-blurred predicted source-to-output residual against the
Gaussian-blurred source-to-target residual. This uses REF only as the training
target and scoring reference; render-time inputs are unchanged.

v17 trains the strong mid-frequency residual branch with `midfreq_blur_sigma=1`
and an explicit mid-frequency score term:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_midfreq_teacher_v17/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_midfreq_teacher_v17_t512/preview_scene_routed_fullframe.json
```

v17 isolated tile receipt:

- pass: 10/12
- worst LPIPS: 0.0809
- worst MS-SSIM: 0.9677
- worst Y-PSNR: 27.14
- worst dE2000: 3.40

v17 stitched smoke:

- pass: 2/3
- `C_lowerleft`: LPIPS 0.0790, MS-SSIM 0.9584, Y-PSNR 26.16, dE2000 3.73

The explicit radius-1 residual objective improves Y slightly over v15 but does
not close dE. That rules out the simplest residual-teacher loss as sufficient.
The next likely blocker is context/target formation: the correction that clears
the oracle may need to be predicted from a larger full-crop/full-frame context,
or supervised as an assembled-crop bandpass residual instead of independent
tile residuals.

## Assembled Mid-Frequency Teacher Loss

The next pass moves the radius-1 residual supervision into the assembled
stitched-crop objective. The trainer now accepts opt-in
`assembled_midfreq_weight` and `assembled_midfreq_blur_sigma` terms, assembles
the predicted source crop from the same receipt tiles as the predicted and
target crops, and compares the blurred source-to-output residual against the
blurred source-to-target residual. Runtime inputs remain source RGB and runtime
metadata only; REF is still only a training/scoring target.

v18 starts from the v5 assembled checkpoint, freezes the base, and trains the
strong mid-frequency residual branch with a heavy assembled radius-1 residual
term:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_assembled_midfreq_v18/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_assembled_midfreq_v18_t512/preview_scene_routed_fullframe.json
```

v18 isolated tile receipt:

- pass: 10/12
- worst LPIPS: 0.0877
- worst MS-SSIM: 0.9667
- worst Y-PSNR: 27.07
- worst dE2000: 3.43

v18 stitched smoke:

- pass: 2/3
- `C_lowerleft`: LPIPS 0.0892, MS-SSIM 0.9624, Y-PSNR 26.44, dE2000 3.67

The assembled bandpass target moves the hard stitched crop in the right Y/dE
direction but trades away LPIPS/detail and still misses the PREVIEW gate. This
narrows the blocker further: the missing correction is learnable in oracle
space, and assembled supervision helps, but the current frozen residual branch
cannot recover the correction without perceptual/detail regression. The next
candidate should preserve v18's Y/dE movement while adding a stronger
detail/perceptual guardrail or changing the model/context, rather than
increasing residual weight again.

## Guarded Detail and Lab/Y Follow-Ups

v19 keeps the assembled radius-1 residual target but lowers its weight and
raises LPIPS/MS-SSIM guardrails. This recovers the v18 detail regression while
retaining most of the Y/dE movement:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_assembled_midfreq_guarded_v19/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_assembled_midfreq_guarded_v19_t512/preview_scene_routed_fullframe.json
```

v19 stitched smoke:

- pass: 2/3
- `C_lowerleft`: LPIPS 0.0690, MS-SSIM 0.9614, Y-PSNR 26.38, dE2000 3.68
- model-only time: 8.11 s/frame for 187 tiles on Mac/MPS
- peak RSS: 3510.6 MB

v20 starts from v19 and leaves the base trainable under the same guarded
objective. It improves texture/detail and luma but still misses color:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_assembled_midfreq_unfrozen_v20/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_assembled_midfreq_unfrozen_v20_t512/preview_scene_routed_fullframe.json
```

v20 stitched smoke:

- pass: 2/3
- `C_lowerleft`: LPIPS 0.0477, MS-SSIM 0.9660, Y-PSNR 26.75, dE2000 3.51
- model-only time: 8.24 s/frame for 187 tiles on Mac/MPS
- peak RSS: 3734.5 MB

v21 starts from v20 and increases Lab/Y pressure while keeping the perceptual
guardrails. It is the best learned stitched candidate from this pass:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_refiner_z8z6680_lab_guarded_v21/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lab_guarded_v21_t512/preview_scene_routed_fullframe.json
```

v21 stitched smoke:

- pass: 2/3
- `C_lowerleft`: LPIPS 0.0413, MS-SSIM 0.9680, Y-PSNR 27.00, dE2000 3.38

v22 tried a heavier Lab/Y continuation from v21 but did not improve the
checkpoint score after 60 steps, so the run was stopped. The conclusion is that
loss reweighting has largely fixed the texture/detail regression and moved
Y/dE in the right direction, but the remaining gap is now low-frequency Lab/Y
calibration. The next candidate should add an explicit runtime-safe color
calibration mechanism or train with broader full-frame color context, rather
than further increasing the same loss weights.

## Stitched Runtime Post-Refiner

The next diagnostic uses the existing stitched post-refiner receipt path. The
source side is the already assembled no-REF v21 full-frame output, and REF is
used only as the training target and scoring reference. At runtime, the
post-refiner sees only the generated stitched RGB frame, normalized coordinates,
and global source statistics.

The receipt is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_z8z6680_v21_manifest_receipt/post_receipt.json
```

Post v1 validates the direction but still misses dE:

- crop-receipt pass: 2/3
- `C_lowerleft`: LPIPS 0.0395, MS-SSIM 0.9773, Y-PSNR 28.10, dE2000 3.21
- full-frame stitched pass: 2/3
- full-frame `C_lowerleft`: worst dE2000 3.23

Post v2 clears the crop receipt and nearly clears full-frame:

- crop-receipt pass: 3/3
- `C_lowerleft`: LPIPS 0.0368, MS-SSIM 0.9841, Y-PSNR 29.15, dE2000 2.92
- full-frame stitched pass: 2/3
- full-frame worst dE2000: 3.031

Post v3 adds a small Lab/opponent continuation and clears the current
`Z8Z_6680` full-frame smoke:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_z8z6680_v21_lab_v3/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_z8z6680_lab_guarded_v21_post_v3_t512/preview_scene_routed_fullframe.json
```

v21 + post v3 full-frame stitched smoke:

- pass: 3/3
- worst LPIPS: 0.0515
- worst MS-SSIM: 0.9824
- worst Y-PSNR: 28.94
- worst dE2000: 2.997
- base model time: 8.15 s/frame for 187 tiles on Mac/MPS
- post model time: 3.14 s/frame for 187 tiles on Mac/MPS
- total model time: 11.29 s/frame
- peak RSS: 4598.0 MB

This is the first learned no-REF path that clears the current `Z8Z_6680`
stitched smoke. It is not production PREVIEW yet: post v3 was trained from the
same single frame/crops it clears, has only 0.003 dE headroom, adds a second
CNN pass, and needs broader full-frame holdout validation before registration.

A quick overfit check applies the same v21 + post v3 stack to the two other
hair/skin near-blocker holdout images, `Z8Z_0680` and `Z8Z_0694`, without
training on them:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_hairskin_holdout_v21_post_v3_t512/preview_scene_routed_fullframe.json
```

That check fails 0/6 with worst LPIPS 0.6746, worst MS-SSIM 0.7213, worst
Y-PSNR 14.25, and worst dE2000 17.45. The post-refiner cleared the local
`Z8Z_6680` smoke but does not generalize as a forced model. The next production
test is to train/validate a routed or broader stitched post-refiner on a
multi-image full-frame receipt and reject it if it only memorizes this frame.

## Full-Frame Contract Audit and Hard8 Runtime-Tile Training

The latest audit compares the crop-local contract against the arbitrary
full-frame runtime contract on the hard-eight images:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_contract_audit_hard8_scene_gated_v1/preview_fullframe_contract_audit.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_contract_audit_hard8_scene_gated_v1/preview_fullframe_contract_audit.html
```

Summary:

- exact manifest-crop rows: 16/24 pass
- arbitrary full-frame tiled rows: 3/24 pass
- exact-pass to tiled-fail regressions: 13
- crops crossed by mixed runtime expert roles: 14
- worst exact-vs-tiled LPIPS: 0.5575
- median exact-vs-tiled mean absolute RGB delta: 5.38

Forced coherent-route checks on `Z8Z_0026` and `Z8Z_6680` do not fix the
problem:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_force_cluster4_0026_6680_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_force_k40c35_0026_6680_v1/preview_scene_routed_fullframe.json
```

Both forced paths pass 0/6. This rules out a simple "choose one coherent
expert per crop" fix for those hard rows.

The next pair of training runs used the 28-image arbitrary full-frame tile
receipt, filtered to the hard-eight images, with global color statistics and
assembled-crop loss:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tile_train_holdout28_globalstats_t512/tile_train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_expert_hard8_fullgrid_zerocoord_globalstats_assembled_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_expert_hard8_fullgrid_local_globalstats_assembled_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/eval_default_hard8_runtime_tiles_v1/preview_runtime_refiner.json
```

Tile-level results on the same 96 hard runtime tiles:

| candidate | pass | worst LPIPS | median LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
|---|---:|---:|---:|---:|---:|---:|
| default checkpoint | 3/96 | 0.9291 | 0.3534 | 0.2612 | 14.38 | 23.21 |
| hard8 zero-coordinate/global-stats | 0/96 | 0.6889 | 0.4127 | 0.3535 | 17.77 | 10.39 |
| hard8 local-coordinate/global-stats | 0/96 | 0.7181 | 0.4140 | 0.3806 | 18.07 | 9.86 |

Conclusion: the current direct CNN plus the existing arbitrary-tile
supervision does not learn a production-safe full-frame PREVIEW contract. The
next candidate should change formulation, not just add more loss weighting:
train a context-aware/full-crop or full-image student against a stable teacher,
or build a runtime-safe stitched/post path that is trained and validated on a
multi-image full-frame receipt. The existing hard8 runs narrow the blocker to
model/context/source-target formulation.

## Formulation Follow-Ups

### Low-Frequency Spatial Branch

The first changed-formulation pass added a low-frequency spatial correction
branch initialized from the current direct checkpoint:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_expert_hard8_fullgrid_lfstrong_local_globalstats_v1/preview_runtime_refiner.json
```

It improves the same 96-row hard runtime-tile receipt compared with the default
checkpoint, but remains far below a viable gate:

- pass: 7/96
- worst LPIPS: 0.6322
- median LPIPS: 0.2890
- worst MS-SSIM: 0.3282
- worst Y-PSNR: 17.58
- worst dE2000: 10.29

This is a better direction than the direct hard8 retrains but still not a
production candidate. It suggests the LF branch helps some tile rows but cannot
repair the full arbitrary-tile contract by itself.

### Multi-Image Stitched Post-Refiner

The second changed-formulation pass trained a runtime-safe post-refiner on
stitched no-REF full-frame outputs from the latest scene-gated holdout:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_scene_gated_holdout28_manifest_receipt_v1/post_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_scene_gated_holdout28_manifest_v1/preview_runtime_refiner.json
```

The receipt covers all 28 images and 84 manifest crops. The trained post pass
does not improve the aggregate gate:

- pass: 63/84
- worst LPIPS: 0.5694
- median LPIPS: 0.0196
- worst MS-SSIM: 0.6294
- worst Y-PSNR: 19.38
- worst dE2000: 8.62

This rules out a simple broad post-refiner over the current scene-gated output.
The remaining hard rows need a stronger context/full-image model or a better
teacher/target for arbitrary tiles, not a shallow correction of the stitched
result.

### Existing Variant Oracle

The next diagnostic asks whether a scene-level classifier/router over the
already-generated arbitrary-tiled variants could solve the holdout without new
model work. The oracle compares baseline v32, unconditional spatial, and
scene-gated spatial receipts on the same 84 full-frame holdout rows:

```text
tools/cnn/compare_preview_fullframe_variants.py
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_variant_oracle_holdout28_v1/preview_fullframe_variant_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_variant_oracle_holdout28_v1/preview_fullframe_variant_oracle.html
```

Because this oracle chooses by gate metrics, it is analysis-only and not a
runtime policy. Result:

- baseline: 57/84
- unconditional spatial: 33/84
- scene-gated spatial: 63/84
- best existing variant per row: 63/84
- unsolved rows after the oracle: 21/84

This rules out a production path based only on a scene-level classifier that
selects among the current full-frame variants. The best remaining rows still
include severe LPIPS/dE failures such as `Z8Z_0705 A_detail`,
`Z8Z_7480 B_center`, `Z8Z_0026 B_center`, `Z8Z_5937 C_lowerleft`, and
`Z8Z_6680 B_center/C_lowerleft`. The next candidate needs new model/target
work, not just routing among these variants.

### Exact-Crop Teacher Oracle

The exact manifest-crop path is source-only at render time, so it is a plausible
teacher for distilling arbitrary tiled outputs. A second oracle compares exact
manifest-crop output against the arbitrary tiled scene-gated output on the
hard-eight rows:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_exact_teacher_oracle_hard8_v1/preview_exact_teacher_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_exact_teacher_oracle_hard8_v1/preview_exact_teacher_oracle.html
```

Result:

- exact manifest-crop teacher ceiling: 16/24
- exact-pass/tiled-fail rows that are potentially distillable: 13/24
- rows unsolved even by exact-crop output: 8/24
- worst remaining exact-teacher LPIPS: 0.2898
- worst remaining exact-teacher dE2000: 3.66

This means exact-crop distillation can be a partial route/tile-transfer
diagnostic, but it cannot be the complete production fix. The unresolved rows
include `Z8Z_7480` all three crops, `Z8Z_5937 C_lowerleft`,
`Z8Z_1586 B_center`, `Z8Z_5284 A_detail/C_lowerleft`, and
`Z8Z_7955 C_lowerleft`. Those rows need a stronger teacher or a changed source
target, not just arbitrary-tile matching to the current crop-local output.

### 768-Context Center-Gate Training

The next context-aware pass added trainer support for receipts that contain
larger context crops but should optimize/score only the centered gate crop.
The context receipt already existed:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/holdout_runtime_context_v1_768_clean_upresable_28img/preview_context_runtime_source_receipt.json
```

The new training receipt is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/context768_center512_direct_init_all84_v1/preview_runtime_refiner.json
```

Contract:

- source: clean UPRESABLE 768x768 context crop
- model input coordinates: global crop coordinates derived from
  `source_render.crop_box_render`
- loss: centered 512x512 gate crop
- metrics/dashboard PNG: centered 512x512 gate crop
- REF: target/scoring only

Result:

- pass: 60/84
- worst LPIPS: 0.6427
- median LPIPS: 0.0570
- worst MS-SSIM: 0.3574
- worst Y-PSNR: 16.54
- worst dE2000: 12.66

This is worse than the earlier 768-context routed proxy and worse than the
scene-gated full-frame holdout. It rules out the simple formulation of one
initialized direct CNN trained on 768 context with a center-gate objective.
The context machinery is still useful, but the next viable candidate needs a
larger teacher/full-image student or a model that explicitly handles full-frame
low-frequency consistency across arbitrary tile placement.

### Context U-Net Fit Tests

The next pass added a `context_unet` diagnostic architecture. It keeps
full-resolution skip paths while adding a deeper 3-level context bottleneck, so
it can use the 768px source crop without compressing all local texture through
the same direct residual path. This is still a runtime-safe architecture: input
is source RGB, normalized coordinates, and source/global stats; REF is
target/scoring only.

All-84 context run:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/context768_center512_context_unet_w32_all84_v1/preview_runtime_refiner.json
```

Result:

- pass: 53/84
- worst LPIPS: 0.6909
- median LPIPS: 0.0890
- worst MS-SSIM: 0.2800
- worst Y-PSNR: 14.15
- worst dE2000: 16.27

This is worse than both the initialized direct 768-context pass and the routed
context proxy.

Hard-eight fit, residual scale 0.45:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/context768_center512_context_unet_w32_hard8_fit_v1/preview_runtime_refiner.json
```

Result:

- pass: 0/24
- worst LPIPS: 0.6888
- median LPIPS: 0.3522
- worst MS-SSIM: 0.2782
- worst Y-PSNR: 16.92
- worst dE2000: 10.81

Hard-eight fit, residual scale 1.0:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/context768_center512_context_unet_w32_hard8_fit_res1_v1/preview_runtime_refiner.json
```

Result:

- pass: 0/24
- worst LPIPS: 0.6974
- median LPIPS: 0.3442
- worst MS-SSIM: 0.2902
- worst Y-PSNR: 17.19
- worst dE2000: 10.95

These hard-fit failures are important because they fail even when train and
evaluation rows are the same hard rows. The production blocker is not simply
that the prior direct CNN lacked enough local context or residual headroom. The
next diagnostic therefore tested whether a full-frame low-frequency field had
enough oracle ceiling before spending more time on trainable field stages.

### Full-Frame Low-Frequency Field Probe

The next diagnostic added an artifact-native full-frame low-frequency Lab field
probe:

```text
tools/cnn/probe_preview_fullframe_lf_field.py
```

It reads a stitched full-frame PREVIEW receipt, renders source and REF DNGs,
and scores the same manifest crops after adding only smooth Lab-field deltas to
the stitched output. Source-field variants are runtime-safe probes. REF-field
variants are oracle ceilings and are not production candidates.

Hard-eight receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_lf_field_probe_hard8_v1/preview_fullframe_lf_field_probe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_lf_field_probe_hard8_v1/preview_fullframe_lf_field_probe.html
```

Result:

- base: 3/24, worst LPIPS 0.5747, worst MS-SSIM 0.6286, worst Y-PSNR 19.25,
  worst dE2000 8.77
- best runtime-safe source field: `source_lf_lab_s4`, 3/24, worst LPIPS
  0.5265, worst MS-SSIM 0.6817, worst Y-PSNR 19.53, worst dE2000 7.78
- best REF-field oracle: `ref_lf_lab_s4`, 6/24, worst LPIPS 0.4859, worst
  MS-SSIM 0.7204, worst Y-PSNR 20.35, worst dE2000 7.01

This rules out a simple smooth full-frame Lab/Y calibration field as the next
production fix. Even the REF-field oracle leaves severe LPIPS, MS-SSIM, Y, and
dE failures on the hard rows. The remaining blocker is now better described as
source/target formulation plus structure/detail placement under arbitrary
full-frame tiling, not low-frequency color calibration alone.

### Full-Frame Luma-Detail Probe

The next diagnostic added an artifact-native full-frame Lab-L detail probe:

```text
tools/cnn/probe_preview_fullframe_luma_detail.py
```

It reads the same stitched full-frame PREVIEW receipt, renders source and REF
DNGs, and scores the manifest crops after replacing only luma structure/detail
bands in the stitched output. Source variants are runtime-safe probes. REF
variants are oracle ceilings and are not production candidates.

Hard-eight receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_luma_detail_probe_hard8_v1/preview_fullframe_luma_detail_probe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_luma_detail_probe_hard8_v1/preview_fullframe_luma_detail_probe.html
```

Result:

- base: 3/24, worst LPIPS 0.5747, worst MS-SSIM 0.6286, worst Y-PSNR 19.25,
  worst dE2000 8.77
- best runtime-safe source luma/detail variant: `source_l_midband_s2_8`, 3/24,
  worst LPIPS 0.5381, worst MS-SSIM 0.6405, worst Y-PSNR 19.28, worst dE2000
  7.95
- full source L replacement: 0/24, worst LPIPS 0.6796, worst MS-SSIM 0.2987,
  worst Y-PSNR 17.00, worst dE2000 9.80
- best REF luma/detail oracle: `ref_l_replace`, 16/24, worst LPIPS 0.1475,
  worst MS-SSIM 0.9176, worst Y-PSNR 23.62, worst dE2000 5.46
- best REF highpass oracle: `ref_l_highpass_s16`, 15/24, worst LPIPS 0.1518,
  worst MS-SSIM 0.9171, worst Y-PSNR 23.53, worst dE2000 5.51

This rules out using the clean UPRESABLE/source luma as a donor for the current
full-frame PREVIEW output. Runtime-safe source L replacement and source
highpass variants are worse than the base, while REF L replacement improves the
hard set but still does not clear it. The remaining blocker is therefore not
"add back recoverable source detail"; it is a source/target formulation gap
under arbitrary full-frame tiling. The next production-shaped step should test
a better runtime source/teacher target or a full-frame student trained against
stable assembled-crop/full-image targets, not another local source-detail donor
or smooth LF field.

### Full-Frame Source Root Score

The next diagnostic added a source-root scorer:

```text
tools/cnn/score_preview_fullframe_source_roots.py
```

It renders candidate runtime-safe editable-DNG source roots and scores their
manifest crops directly against REF. This is not a production pipeline; it is a
ceiling check for whether any existing source DNG formulation is close enough
to act as a better PREVIEW source/teacher.

Hard-eight receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_source_root_score_hard8_v1/preview_fullframe_source_root_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_source_root_score_hard8_v1/preview_fullframe_source_root_score.html
```

Result:

- `receipt_source`: 0/24, worst LPIPS 0.6839, worst MS-SSIM 0.2922,
  worst Y-PSNR 17.00, worst dE2000 10.70
- `clean_upresable`: 0/24, same metrics as `receipt_source`; the receipt is
  already using the clean holdout UPRESABLE DNGs
- `older_hard_upresable`: 0/18, worst LPIPS 0.5936, worst MS-SSIM 0.2922,
  worst Y-PSNR 17.00, worst dE2000 10.70; incomplete for the hard-eight set

This rules out the available editable-DNG source roots as direct source
formulation fixes. The clean source is necessary for a valid no-REF contract,
but it is not close enough to be the learned target or a direct luma/detail
donor for PREVIEW. The next trainable candidate should keep render-time inputs
runtime-safe, but use a stronger full-image/assembled-crop teacher target
during training instead of trying to preserve or reinsert the current source
render's luma/detail/color.

### Hard-Eight Stitched Post-Refiner Capacity Check

The next diagnostic tested whether a simple runtime-safe stitched RGB
post-refiner can even fit the hard-eight full-frame manifest crops when train
and eval rows are the same. It uses the existing full-frame post receipt;
source is stitched no-REF RGB, and REF is target/scoring only.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_hard8_manifest_fit_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_hard8_manifest_fit_v1/preview_runtime_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_hard8_manifest_fullbatch_v2/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/post_refiner_hard8_manifest_fullbatch_v2/preview_runtime_refiner.html
```

Result:

- stochastic width-40 post v1: 2/24, worst LPIPS 0.5627, median LPIPS 0.3074,
  worst MS-SSIM 0.6398, worst Y-PSNR 19.98, worst dE2000 8.42
- full-batch width-40 post v2: 0/24, worst LPIPS 0.5579, median LPIPS 0.3109,
  worst MS-SSIM 0.7096, worst Y-PSNR 20.68, worst dE2000 7.70
- base hard-eight scene-gated full-frame remains 3/24

This rules out simple stitched RGB post-refinement as the missing production
fix. Even same-row hard-eight training does not fit the gate, so the next
candidate must change representation/model context rather than add a shallow
post stage to the current stitched output.

Follow-up stitched-output post-refiner tests used the actual failed arbitrary
full-frame stitched tile distribution, not only manifest-crop rows:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/stitched_post_receipt_hard8_intersect_ov256_v1/stitched_post_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/stitched_post_refiner_hard8_intersect_ov256_lf_v1/baseline_source_metrics.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/stitched_post_refiner_hard8_intersect_ov256_lf_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_hard8_post_lf_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/stitched_post_refiner_hard8_intersect_ov256_direct_srcguard_v1/preview_runtime_refiner.json
```

Result:

- dense stitched-source baseline: 13/394 pass, worst LPIPS 0.7106, median
  LPIPS 0.3324, worst dE2000 14.87
- unconstrained low-frequency post-refiner: 33/394 dense-tile pass, but only
  3/24 in the actual hard-eight full-frame manifest-crop evaluation; worst
  LPIPS 0.4697, median LPIPS 0.2778, worst dE2000 8.76
- source-guarded direct residual post-refiner: 15/394 dense-tile pass, worst
  LPIPS 0.7111, median LPIPS 0.3202, worst dE2000 14.93

The trainer now exposes `--source-weight`, `--source-lowfreq-weight`, and
`--source-lowfreq-blur-sigma` so post candidates can be explicitly no-op biased.
The source-guarded pass confirms the useful correction is not available through
a conservative single stitched-RGB post model. The unconstrained pass confirms
that allowing more correction improves some dense tiles but regresses the actual
stitched full-frame crop gate. The next production candidate should not be
another single global stitched-output post-refiner; it needs a stronger
full-image/assembled-crop target or a different representation.

### Coordinate-Field Runtime-Safe Smoke

The next distinct formulation tested a smooth coordinate/stat-driven field
model. `coord_field` predicts a low-frequency gain/bias field from runtime
global color stats plus normalized full-frame coordinates only, then applies it
to source RGB. It preserves source texture by construction and cannot use local
REF detail or local source texture to invent detail.

Artifact:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_expert_hard8_coord_field_globalstats_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_expert_hard8_coord_field_globalstats_v1/preview_runtime_refiner.html
```

Result on the 96 hard-eight arbitrary full-frame training tiles:

- 0/96 pass
- worst LPIPS 0.6796, median LPIPS 0.4221
- worst MS-SSIM 0.2704
- worst Y-PSNR 16.92
- worst dE2000 10.81

This rules out a smooth runtime-safe coordinate/color field by itself. Some
Y/dE rows move in the right direction, but LPIPS/detail cannot pass without a
detail-preserving or stronger full-image teacher component. The remaining
formulation gap is now narrower: production PREVIEW likely needs a model that
keeps source detail stable while learning a full-image-aware source-to-target
mapping, not a local tile CNN, a shallow stitched post stage, or a smooth field
alone.

### Full-Image LF Residual Capacity

The next runtime-safe formulation trained a bounded low-resolution residual
field on full hard-eight source/REF renders, then applied the upsampled residual
to source crops. Render-time inputs are source RGB, normalized coordinates, and
the checkpoint. REF is used only for training/scoring. The receipt also includes
`ref_lowfield_oracle`, which is an invalid production variant used only to test
whether an exact low-frequency REF field would close the gate.

Artifact:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullimage_lf_refiner_hard8_capacity_v2/preview_fullimage_lf_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullimage_lf_refiner_hard8_capacity_v2/preview_fullimage_lf_refiner.html
```

Result on the 24 hard-eight manifest crop rows:

- source baseline: 0/24, worst LPIPS 0.6839, worst dE2000 10.70
- learned full-image LF residual: 0/24, worst LPIPS 0.6847, worst dE2000 10.54
- exact REF low-field oracle: 0/24, worst LPIPS 0.6765, worst dE2000 10.39

This rules out full-image low-frequency/color correction by itself. Even an
oracle low-field transfer cannot clear LPIPS/MS-SSIM/Y/dE, so the remaining
PREVIEW blocker must involve mid/high-frequency structure, the source/teacher
representation, or a model that can make stronger full-image-aware detail
changes while remaining no-REF at render time.

### Full-Image Frequency-Band Oracle

The next diagnostic rendered the hard-eight source/REF full images and exchanged
low/high RGB bands at Gaussian radii 1, 2, 4, 8, 16, and 32. REF-band variants
are oracle ceilings only. The purpose is to locate which frequency bands the
next no-REF model must handle.

Artifact:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullimage_frequency_oracle_hard8_v1/preview_fullimage_frequency_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullimage_frequency_oracle_hard8_v1/preview_fullimage_frequency_oracle.html
```

Result on the 24 hard-eight manifest crop rows:

- exact REF oracle: 24/24
- REF low + source high, sigma 1: 14/24, worst LPIPS 0.4083, worst dE2000 3.58
- source low + REF high, sigma 4: 5/24, worst LPIPS 0.2859, worst dE2000 11.11
- source baseline: 0/24, worst LPIPS 0.6839, worst dE2000 10.70

The best nontrivial oracle is `ref_low_source_high_s1`. Its remaining failures
are mostly LPIPS-heavy rows: `Z8Z_0026` all three crops, `Z8Z_6680` all three
crops, `Z8Z_7480` all three crops, and `Z8Z_5284 A_detail`. This means the next
candidate cannot be only high-frequency synthesis over the current source low
field and cannot be only low-frequency correction over current source detail.
It needs a full-image-aware low/mid placement target plus fine-detail
synthesis/preservation that survives LPIPS.

### Context Generator Headroom Test

The next model-side diagnostic removed the source-plus-residual output
constraint from the prior context U-Net. `context_unet_generator` takes the same
runtime-safe source/context/coordinate input planes as the refiner, but outputs
RGB directly through a sigmoid head instead of forcing `source + residual`.
This tests whether the prior hard-eight failures were caused mainly by
insufficient output headroom.

Artifact:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/context768_center512_generator_hard8_fit_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/context768_center512_generator_hard8_fit_v1/preview_runtime_refiner.html
```

Result on the 24 hard-eight 768-context/center-512 rows:

- direct generator: 0/24
- worst LPIPS 0.6136, median LPIPS 0.4035
- worst MS-SSIM 0.3989
- worst Y-PSNR 18.29
- worst dE2000 11.52

The internal training score improved substantially, but the saved best
checkpoint still failed every actual gate row. That rules out "residual
headroom" as the sole blocker. The next useful pass must change the
source/teacher representation or training target so the full-image low/mid
placement and fine detail seen in the frequency oracle become learnable from
source-only inputs.

### Exact-Crop Teacher Post-Distillation

The next transfer diagnostic tested whether arbitrary full-frame tiled output
can be post-refined toward the exact manifest-crop no-REF teacher. This is a
runtime-safe training target: the teacher is exact no-REF crop output, not REF.
REF is copied only for separate scoring. The teacher ceiling remains limited,
but it is useful because it separates "tiled path cannot match crop path" from
"crop path itself is insufficient."

Artifacts:

```text
tools/cnn/build_preview_exact_teacher_receipt.py
tools/cnn/score_preview_exact_teacher_distill.py
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/exact_teacher_distill_hard8_v1/exact_teacher_distill_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/exact_teacher_post_distill_hard8_v1/exact_teacher_distill_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/exact_teacher_post_distill_hard8_w96_v2/exact_teacher_distill_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/exact_teacher_post_distill_hard8_w96_v2/exact_teacher_distill_score.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/exact_teacher_post_distill_hard8_unetgen_v3/exact_teacher_distill_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/exact_teacher_post_distill_hard8_unetgen_v3/exact_teacher_distill_score.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/exact_teacher_distill_hard8_global_context_v1/exact_teacher_distill_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/exact_teacher_post_distill_hard8_global_context_w96_v1/exact_teacher_distill_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260612/exact_teacher_post_distill_hard8_global_context_w96_v1/exact_teacher_distill_score.html
```

Hard-eight receipt construction:

- tiled full-frame no-REF source: 3/24 against REF
- exact no-REF crop teacher: 16/24 against REF
- rows: 24 across eight hard images

Two post-refiner fits were scored against both teacher and REF:

- width-40 direct post model: output 5/24 against teacher and 2/24 against REF
- width-96 direct post model: output 6/24 against teacher and 3/24 against REF
- width-32 context U-Net generator: output 0/24 against teacher and 0/24
  against REF, with worst dE2000 above 19
- width-96 direct post model with resized full-frame no-REF context planes:
  output 5/24 against teacher and 2/24 against REF

The width-96 run improves proxy worst LPIPS from 0.5575 to 0.4644 against the
exact teacher, but it does not improve the actual REF gate: source is 3/24 and
output remains 3/24. The context U-Net generator regresses both teacher and REF
scoring because it cannot maintain color consistency on this target. Adding a
thumbnail-style no-REF full-frame context image also fails to improve the actual
REF gate. This rules out simple exact-crop-teacher post-distillation as the
production fix. The remaining branch needs a different source/teacher
representation or a more global model class; copying the exact-crop behavior
through these post models is not enough.

### Full-Frame Wall Timing Receipt

The full-frame scene-routed evaluator now records explicit wall-clock timing
for the production no-REF render path separately from REF scoring:

- `runtime_no_ref_wall_ms`: source render, source load, routing, model
  inference, stitching, and optional post-refiner output
- `scoring_wall_ms`: REF load and manifest crop metrics
- `total_eval_wall_ms`: the complete diagnostic frame including REF render

Smoke receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_timing_wall_smoke_z8z0026_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_timing_wall_smoke_z8z0026_v1/preview_scene_routed_fullframe.html
```

`Z8Z_0026` result:

- runtime no-REF wall: 29.64 s/frame, 0.0337 FPS
- model total: 3.67 s/frame
- source render: 0.71 s/frame
- scoring wall: 1.07 s/frame
- total diagnostic eval: 31.64 s/frame
- peak RSS: 3693 MB

This makes performance blocker evidence explicit: the current Python full-frame
PREVIEW diagnostic spends far more wall time in route/save/stitch overhead than
in the CNN itself. A production PREVIEW implementation needs a non-PNG,
batched/in-memory tile path before it can be treated as a live or interactive
preview candidate.

### In-Memory Full-Frame Routing Timing

The first production-path timing fix removed PNG round-trips from full-frame
tile routing. Router features are now computed from the source tile RGB array
using the same max-side-512 feature math as the path-based router.

Smoke receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_timing_inmem_route_smoke_z8z0026_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_timing_inmem_route_smoke_z8z0026_v1/preview_scene_routed_fullframe.html
```

`Z8Z_0026` before/after:

- PNG-routing runtime no-REF wall: 29.64 s/frame, 0.0337 FPS
- in-memory routing runtime no-REF wall: 12.07 s/frame, 0.0828 FPS
- route roles: unchanged
- crop metrics: unchanged at 0/3, worst LPIPS 0.4348, worst dE2000 9.44
- route median: 42.20 ms/tile -> 10.66 ms/tile
- route PNG save median: 14.20 ms/tile -> 0.00 ms/tile

This is a 2.45x wall-time improvement for the same full-frame routed output.
It does not solve the quality blocker or make PREVIEW production-ready, but it
removes one avoidable filesystem bottleneck from the actual runtime path.

### Production Timing Receipt

The evaluator also has a production timing mode that skips REF render/load,
crop metrics, crop PNGs, and dashboard-quality scoring. It still writes the
stitched output and records the no-REF render wall time.

Production timing receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_production_timing_tiffraw_route512_smoke_z8z0026_v2/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_production_timing_tiffraw_route512_smoke_z8z0026_v2/preview_scene_routed_fullframe.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_production_timing_tiffraw_route512_split_smoke_z8z0026_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_production_timing_tiffraw_route512_split_smoke_z8z0026_v1/preview_scene_routed_fullframe.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_production_timing_tiffraw_route512_fastfeature_smoke_z8z0026_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_production_timing_tiffraw_route512_fastfeature_smoke_z8z0026_v1/preview_scene_routed_fullframe.html
```

Quality-enabled cached-route receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_quality_cached_route_smoke_z8z0026_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_quality_cached_route_smoke_z8z0026_v1/preview_scene_routed_fullframe.html
```

Latest `Z8Z_0026` production-timing result with explicit router feature
max-side 512, route feature/select split, and the channel-wise saturation fast
path:

- runtime no-REF wall: 7.35 s/frame, 0.1360 FPS
- model total: 2.75 s/frame
- source render/load: 0.69 s + 0.15 s
- routing: 1.11 s total; cached second-pass route time 0.00 ms
- route feature extraction: 1.09 s total, 5.79 ms/tile median
- route sidecar selection: 0.017 s total, 0.091 ms/tile median
- stitched raw TIFF output: 0.086 s
- quality scoring: skipped; 0.0005 ms scoring wall
- peak RSS: 3033 MB

The fast feature path preserves the smoke-frame route-role histogram exactly:
58 `cluster_0`, 6 `cluster_1`, 62 `cluster_2`, 4 `cluster_3`, 16 `cluster_4`,
12 `override_0_cluster_10`, 4 `override_0_cluster_15`, and 25
`override_1_cluster_35`. The maximum feature-vector drift versus the previous
implementation on the same tiles is under 7e-7.

The quality-enabled cached-route run preserves the same route-role histogram
and crop metrics as the in-memory routing receipt: 0/3 pass, worst LPIPS
0.4348, worst dE2000 9.44.

MPS tile batching was measured as a throughput candidate:

| batch size | runtime | FPS | model total | batches | max batch | driver MB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 10.35 s | 0.0966 | 2.66 s | 187 | 1 | 3067 |
| 2 | 10.51 s | 0.0951 | 2.80 s | 94 | 2 | 3067 |
| 8 | 10.43 s | 0.0959 | 2.89 s | 27 | 8 | 7163 |

Batching is not the current production default because it is slower on this
MPS smoke and batch size 8 sharply increases driver memory.

Stitched-output writer timing from the same full-frame RGB shows why production
timing should not use default PNG compression:

| writer | avg save | bytes |
| --- | ---: | ---: |
| PNG default | 2391 ms | 63,823,317 |
| PNG compress level 1 | 1003 ms | 96,916,871 |
| PNG stored | 433 ms | 137,163,322 |
| raw TIFF | 302 ms including first warm write; subsequent writes ~45 ms | 137,116,940 |
| BMP | 42 ms | 137,116,854 |

The production receipt now writes raw TIFF so the timing reflects the render
path instead of PNG compression. The next throughput blocker is
reducing/router-vectorizing feature extraction.

Reduced router feature scale was tested as a possible speed path, but it
changes the frozen sidecar decisions and is not production-safe without a new
sidecar:

| route feature scale | runtime | route total | role result |
| --- | ---: | ---: | --- |
| contract max-side 512, previous feature path | 7.97 s | 2.04 s | baseline roles preserved |
| contract max-side 512, fast saturation path | 7.35 s | 1.11 s | baseline roles preserved |
| intermediate reduced scale | 7.45 s | 1.51 s | role histogram changed |
| aggressive reduced scale | 6.79 s | 0.82 s | role histogram changed substantially |

The split receipt proves sidecar selection is not the bottleneck. The fast
saturation path halves the 512-scale feature cost without changing route roles.
The next routing optimization should vectorize/reuse more of the 512-scale
feature extractor or retrain/freeze a new reduced-scale router sidecar, rather
than quietly changing feature scale under the existing sidecar. The next quality
blocker remains the full-image detail/color failure, not REF content leakage.

## Full-Frame Failure-Mode Audit

The latest audit aggregates the current crop, full-frame/tiled, contract,
variant-oracle, frequency-oracle, source-root, source-frequency, band-refiner,
and alignment-oracle receipts into one row-level dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_failure_mode_audit_v1/preview_fullframe_failure_mode_audit.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_failure_mode_audit_v1/preview_fullframe_failure_mode_audit.html
```

Tool:

```text
tools/cnn/audit_preview_fullframe_failure_modes.py
```

Summary:

- normalized evidence rows: 1,227
- unique row keys: 84
- variants/receipt views: 44
- crop-shaped routed holdout: 84/84
- broad arbitrary-tiled scene-gated full-frame holdout: 63/84
- hard-eight exact manifest-crop inference: 16/24
- hard-eight arbitrary-tiled inference: 3/24
- exact-pass to arbitrary-tiled-fail regressions: 13
- mixed-role exact-pass to arbitrary-tiled-fail regressions: 11
- coherent-role exact-pass to arbitrary-tiled-fail regressions: 2

The hardest repeated rows are concentrated in `Z8Z_0026`, `Z8Z_0705`,
`Z8Z_5284`, `Z8Z_6680`, `Z8Z_7480`, `Z8Z_5937`, `Z8Z_7955`, and `Z8Z_1586`.
The audit makes the production gap more concrete: the current source/model
contract can pass exact manifest-crop conditions, but it is not stable under the
arbitrary full-frame tiling required by the runtime path. The next production
candidate should therefore train and validate against assembled full-frame or
arbitrary-tile outputs directly, with a target/model class that closes both
failure classes. Most regressions need route stability across crop interiors;
`Z8Z_6680:C_lowerleft` and `Z8Z_5937:B_center` also prove that same-role
arbitrary tiles can fail, so route coherence alone cannot be the complete
solution. More crop-only specialists or another dashboard-only selector over
the current receipts are already ruled out by this audit.

## Role-Map Post-Distillation Probe

The next diagnostic tested whether the arbitrary-tile role grid itself contains
enough runtime-safe signal to repair the exact-crop to arbitrary-tile
regressions. It trains a small post-refiner from arbitrary-tiled crop RGB plus
runtime tile role planes and normalized coordinates to the exact no-REF crop
output. REF is scoring-only.

Tool:

```text
tools/cnn/probe_preview_rolemap_post_distill.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/rolemap_post_distill_exactpass_tiledfail_v1/preview_rolemap_post_distill.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/rolemap_post_distill_exactpass_tiledfail_v1/preview_rolemap_post_distill.html
```

Result on the 13 exact-pass/arbitrary-tiled-fail rows:

| view | pass |
| --- | ---: |
| arbitrary-tiled source vs REF | 0/13 |
| exact no-REF teacher vs REF | 13/13 |
| role-map post output vs REF | 1/13 |
| role-map post output vs exact teacher | 4/13 |

Worst output-vs-REF metrics remain LPIPS 0.4217, MS-SSIM 0.8691, Y-PSNR
23.20, and dE2000 5.56. This rules out a simple role-map-conditioned crop
post-refiner as the route-mixing fix. The next candidate needs to change the
assembled/full-frame model class or source/teacher representation rather than
only appending tile-role planes to the current post-refiner contract.

### Source-Only Route-Smoothing Probe

The full-frame evaluator now has a default-off local route-smoothing diagnostic:

```text
tools/cnn/evaluate_preview_scene_routed_fullframe.py --route-smoothing-radius ...
```

It precomputes the normal source-derived tile routes, then replaces a tile route
with the local-majority checkpoint role inside a pixel-radius neighborhood when
the majority exceeds the requested fraction. It uses no REF content, no crop
identity, and no gate metrics; REF remains scoring-only.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_route_smoothing_smoke_0026_6680_r512_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_route_smoothing_smoke_0026_6680_r512_v1/preview_scene_routed_fullframe.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_route_smoothing_smoke_0026_6680_r1024_v1/preview_scene_routed_fullframe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_route_smoothing_smoke_0026_6680_r1024_v1/preview_scene_routed_fullframe.html
```

Result on `Z8Z_0026` and `Z8Z_6680`:

| smoothing radius | changed tiles | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 512px | 39 | 0/6 | 0.4377 | 0.6160 | 19.11 | 8.90 |
| 1024px | 32 | 0/6 | 0.4478 | 0.6141 | 19.32 | 8.72 |

This changes enough tile roles to be a real perturbation, but it does not
recover any hard full-frame crop and slightly worsens the worst LPIPS at the
larger radius. Route smoothing is therefore not the production fix for the
current hard failures. Combined with the same-role failures in the failure-mode
audit, the next candidate should change the runtime-shaped model/teacher
contract rather than adding another source-only route post-policy.

### Stitched Context U-Net Capacity Probe

The next capacity test asks whether a larger local post-refiner can fit the
actual hard-eight stitched/full-frame manifest failure rows. It trains a
`context_unet` post-refiner on the 24 hard rows from the scene-gated stitched
receipt, using runtime-safe inputs only: stitched RGB crop, global source color
stats, global tile coordinates, and checkpoint. REF is training target and
scoring reference only.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/stitched_post_hard8_context_unet_capacity_v1/preview_runtime_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/stitched_post_hard8_context_unet_capacity_v1/preview_runtime_refiner.html
```

Result:

- pass: 2/24
- worst LPIPS: 0.5509
- median LPIPS: 0.3044
- worst MS-SSIM: 0.6481
- worst Y-PSNR: 20.07
- worst dE2000: 8.31

The baseline stitched hard-eight receipt has 3/24 passing rows, so this larger
local post model does not even fit the same rows it trains against. This rules
out "just use a larger local stitched-post CNN" for the current full-frame
blocker. The remaining path needs a different source/teacher/full-frame
formulation, not another local correction model over the current stitched RGB
distribution.

### Failure-Mode Audit v2 Refresh

The full-frame failure-mode audit now normalizes exact-teacher distillation
score receipts and includes the stitched context U-Net capacity result:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_failure_mode_audit_v2/preview_fullframe_failure_mode_audit.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_failure_mode_audit_v2/preview_fullframe_failure_mode_audit.html
```

Summary:

- normalized evidence rows: 1,371
- unique row keys: 84
- variants/receipt views: 50
- crop-shaped routed holdout: 84/84
- broad arbitrary-tiled scene-gated full-frame holdout: 63/84
- hard-eight exact manifest-crop inference: 16/24
- hard-eight arbitrary-tiled inference: 3/24
- hard-eight exact-teacher distillation output vs REF: 2/24
- hard-eight stitched context U-Net capacity output: 2/24
- exact-pass to arbitrary-tiled-fail regressions: 13
- mixed-role exact-pass to arbitrary-tiled-fail regressions: 11
- coherent-role exact-pass to arbitrary-tiled-fail regressions: 2

The refresh does not change the production conclusion. It makes the blocker
harder to misread: the current exact-crop teacher ceiling is still only 16/24,
the best broad arbitrary-tiled path is still 63/84, and both post-distillation
and larger stitched local CNN capacity checks remain at 2/24 against REF.

### Full-Image Resolution Oracle

The next bounded oracle tests whether a full-image RGB field at increasing
spatial bandwidth could satisfy the hard-eight rows. It renders source and REF
full images, downsamples each full image to a fixed max width, then crops the
manifest windows from that field. Source-field rows are runtime-shaped inputs;
REF-field rows are oracle ceilings only and are not production candidates.

Tool:

```text
tools/cnn/probe_preview_fullimage_resolution_oracle.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_resolution_oracle_hard8_v1/preview_fullimage_resolution_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_resolution_oracle_hard8_v1/preview_fullimage_resolution_oracle.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_resolution_oracle_hard8_highres_v1/preview_fullimage_resolution_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_resolution_oracle_hard8_highres_v1/preview_fullimage_resolution_oracle.html
```

Result:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| source full-resolution | 0/24 | 0.6839 | 0.2922 | 17.00 | 10.70 |
| REF field, max width 3072 | 14/24 | 0.4433 | 0.7729 | 20.38 | 6.22 |
| REF field, max width 4096 | 19/24 | 0.2882 | 0.8761 | 23.00 | 4.64 |
| REF field, max width 6144 | 23/24 | 0.0946 | 0.9131 | 23.71 | 4.27 |
| REF field, full width | 24/24 | 0.0000 | 1.0000 | inf | 0.00 |

The only 6144-wide REF-field miss is `Z8Z_6680:C_lowerleft`: LPIPS passes at
0.0946, but MS-SSIM is 0.9131, Y-PSNR is 23.71, and dE2000 is 4.27. This narrows
the next model target. A 768-1536px full-image low-field branch is not enough,
and even a 3072px REF field only matches the previous sigma-1 frequency oracle
at 14/24. The next viable PREVIEW candidate needs either a very high-resolution
full-image generator or a full-image/global model that can synthesize local
structure and color placement beyond a low/mid field.

The aggregate failure-mode dashboard was refreshed with these rows:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_failure_mode_audit_v4/preview_fullframe_failure_mode_audit.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullframe_failure_mode_audit_v4/preview_fullframe_failure_mode_audit.html
```

It now contains 2,043 normalized rows and 121 label-separated variant views
while preserving the same core full-frame blocker counts: crop-shaped routed
holdout 84/84, scene-gated arbitrary full-frame 63/84, hard-eight exact
manifest-crop 16/24, and hard-eight arbitrary-tiled 3/24.

### High-Resolution Source-Only Band Generator

The next bounded source-only follow-up reused the full-image band generator at
higher spatial bandwidth. Runtime inputs remain source RGB, normalized
coordinates, and checkpoint weights; the final pass also adds source-derived
global RGB mean/std planes. REF is supervision/scoring only.

Tool update:

```text
tools/cnn/train_preview_fullimage_band_refiner.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w2048_capacity_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w2048_capacity_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w4096_narrow_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w4096_narrow_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w4096_globalstats_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w4096_globalstats_v1/preview_fullimage_band_refiner.html
```

Result:

| run | generated best | oracle best | memory/timing |
| --- | ---: | ---: | --- |
| 2048-wide, width 32/depth 4 | 0/24 | REF low-field residual 7/24 | 6.4 GB RSS, 108 ms median model/image |
| 4096-wide, width 12/depth 3 | 0/24 | REF low + source high sigma 1: 18/24 | 14.0 GB RSS, 226 ms median model/image |
| 4096-wide + source global RGB mean/std | 0/24 | REF low + source high sigma 1: 18/24 | 17.6 GB RSS, 301 ms median model/image |

The high-resolution oracle rows improve with spatial bandwidth, but the learned
source-only generated rows remain 0/24. Source-derived global color-stat
conditioning does not fix the failure and slightly worsens worst dE. This
narrows the blocker to the current model/source-conditioning formulation: it is
not enough to raise the existing full-image band generator to 4096px. The next
candidate needs a stronger image-conditioned/global model or a different
runtime source/teacher representation that can learn the 4096-6144px field
without REF at render time.

The next variant kept the same runtime contract but changed the training
objective: full-image background loss was downweighted, manifest crop loss was
weighted 20x, and the trainer restored the best observed training checkpoint
before scoring. This tested whether the prior 0/24 result was caused by the
full-image objective averaging away the gate crops.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w4096_croploss_best_v2/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_refiner_hard8_w4096_croploss_best_v2/preview_fullimage_band_refiner.html
```

Summary:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| REF low + source high, sigma 1 oracle | 18/24 | 0.3784 | 0.8649 | 22.42 | 5.12 |
| generated low + source high, sigma 4 | 0/24 | 0.7308 | 0.3120 | 17.22 | 20.64 |
| generated lowfield residual | 0/24 | 0.8816 | 0.3301 | 17.90 | 20.56 |
| generated low direct | 0/24 | 0.9964 | 0.3605 | 18.29 | 20.57 |

Training did optimize the crop objective (`best_step=419`,
`best_loss=0.0126`, median model time about 298 ms/image on MPS), but that did
not translate into PREVIEW gate quality. This rules out crop weighting and
checkpoint selection as sufficient fixes for the current full-image band
architecture.

### Full-Image RGB Affine Oracle

A follow-up oracle tested whether the remaining source/REF field mismatch is
mostly a per-image global RGB transform. For each image and field width, the
tool fits a 3x4 RGB affine transform from downsampled source pixels to REF
pixels, applies it to the source field, then scores manifest crops. The affine
fit uses REF and is not production-allowed.

Tool:

```text
tools/cnn/probe_preview_fullimage_affine_oracle.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_affine_oracle_hard8_v1/preview_fullimage_affine_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_affine_oracle_hard8_v1/preview_fullimage_affine_oracle.html
```

Result:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| source field, max width 4096 | 0/24 | 0.7155 | 0.3163 | 17.21 | 10.51 |
| affine field oracle, max width 4096 | 0/24 | 0.6900 | 0.3218 | 17.36 | 9.93 |
| affine field + source high, sigma 1, max width 4096 | 0/24 | 0.6374 | 0.2961 | 16.87 | 10.67 |
| source field, max width 6144 | 0/24 | 0.6365 | 0.2850 | 16.96 | 10.77 |
| affine field oracle, max width 6144 | 0/24 | 0.6231 | 0.2911 | 17.12 | 10.18 |
| affine field + source high, sigma 1, max width 6144 | 0/24 | 0.6609 | 0.2686 | 16.64 | 10.89 |

Even an ideal per-image RGB affine does not clear any hard-eight row. This
rules out simple global source-to-REF color correction as the missing
production fix. The next candidate needs a different source/teacher
representation or a model class that can learn spatially varying structure and
detail placement, not just global color.

A follow-up local-affine oracle tested the next adjacent hypothesis: maybe the
missing field is not global color, but spatially varying color. The tool fits
independent 3x4 RGB affine transforms on 4x4 and 8x8 full-image grids at 4096
and 6144 widths. These fits also use REF and are not production-allowed.

Tool:

```text
tools/cnn/probe_preview_fullimage_local_affine_oracle.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_local_affine_oracle_hard8_v1/preview_fullimage_local_affine_oracle.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_local_affine_oracle_hard8_v1/preview_fullimage_local_affine_oracle.html
```

Result:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| local affine 8x8, max width 6144 | 0/24 | 0.5936 | 0.2916 | 17.32 | 9.26 |
| local affine 4x4, max width 6144 | 0/24 | 0.5971 | 0.2932 | 17.01 | 9.69 |
| local affine 8x8, max width 4096 | 0/24 | 0.6059 | 0.3182 | 17.53 | 9.06 |
| local affine 4x4, max width 4096 | 0/24 | 0.6074 | 0.3203 | 17.21 | 9.50 |
| local affine 8x8 + source high, max width 6144 | 0/24 | 0.6598 | 0.2701 | 16.88 | 9.81 |

Local affine improves over the global affine oracle slightly, but it still does
not clear any row and remains far outside the LPIPS/MS/Y/dE gates. This rules
out a learned spatially varying affine color field as the next production fix.
The remaining path needs a non-affine source/teacher representation or model
that can recover structural/detail placement from source-only runtime inputs.

### Runtime Source Representation Probe

The next source-side diagnostic compared existing runtime-legal source
representations before another CNN pass:

- clean UPRESABLE editable DNG rendered by `sips`
- clean bundle TIFF frame
- rawpy camera-white-balance renders with and without auto-brightening

REF is used only for scoring. No variant uses REF at render time.

Tool:

```text
tools/cnn/probe_preview_source_representation.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/source_representation_hard8_v1/preview_source_representation_probe.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/source_representation_hard8_v1/preview_source_representation_probe.html
```

Hard-eight summary:

| source representation | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| editable DNG via `sips`, max width 6144 | 0/24 | 0.6365 | 0.2850 | 16.96 | 10.77 |
| editable DNG via `sips`, full-resolution | 0/24 | 0.6839 | 0.2922 | 17.00 | 10.70 |
| clean bundle TIFF frame | 0/24 | 0.8492 | 0.0000 | 6.80 | 36.04 |
| rawpy camera WB no-auto, max width 6144 | 0/24 | 0.8534 | 0.1216 | 6.61 | 38.17 |
| rawpy camera WB auto, max width 6144 | 0/24 | 0.9140 | 0.0000 | 6.93 | 44.95 |

The existing clean editable DNG rendered by `sips` remains the least bad
runtime source representation. The clean bundle frame and rawpy paths are not
viable replacements for the current PREVIEW source policy. This rules out a
simple render-source swap as the next production fix; the remaining path needs
a different learned source/teacher formulation or a spatially varying
full-image model that can recover the missing low/mid/detail fields from
source-only runtime inputs.

### Residual Full-Image Band Generator

The next bounded model-formulation check changed the full-image band generator
from a direct sigmoid RGB field to a source-preserving residual field. The
runtime contract is unchanged except for the new architecture: source RGB,
normalized coordinates, source global RGB mean/std, and checkpoint weights are
allowed; REF is training/scoring/oracle-only.

Tool update:

```text
tools/cnn/train_preview_fullimage_band_refiner.py --architecture residual
tools/cnn/train_preview_fullimage_band_refiner.py --architecture residual_unet
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_smoke_0026_6680_w1536_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_smoke_0026_6680_w1536_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_smoke_0026_6680_w4096_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_smoke_0026_6680_w4096_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_unet_smoke_0026_6680_w1536_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_unet_smoke_0026_6680_w1536_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_unet_smoke_0026_6680_w2048_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/fullimage_band_residual_unet_smoke_0026_6680_w2048_v1/preview_fullimage_band_refiner.html
```

Result on `Z8Z_0026` and `Z8Z_6680`:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| source baseline | 0/6 | 0.6839 | 0.2922 | 17.00 | 10.70 |
| residual generated low + source high, 1536 width | 0/6 | 0.6592 | 0.4401 | 17.83 | 10.51 |
| residual generated low + source high, 4096 width | 0/6 | 0.6898 | 0.5975 | 19.37 | 9.08 |
| residual U-Net generated low + source high, 1536 width | 0/6 | 0.6551 | 0.3450 | 16.94 | 11.21 |
| residual U-Net generated low + source high, 2048 width | 0/6 | 0.6602 | 0.2901 | 16.34 | 12.04 |
| REF low + source high oracle, 4096 width | 0/6 | 0.3784 | 0.8649 | 22.42 | 5.12 |

The residual model moves some Y/dE and MS-SSIM numbers but does not recover any
PREVIEW row and does not improve the decisive LPIPS/detail failure at 4096
width. The REF-low oracle remains much closer, so the source-preserving residual
head is not enough to learn the high-resolution field from the current source
representation. The residual U-Net adds multi-scale context and skip paths, but
it also remains 0/6 and does not improve the decisive hard-smoke metrics. The
next viable candidate still needs a different source/teacher representation or
a more global image-conditioned model, not just a residual variant of the
current full-image band generator.

### Candidate Evidence Rank

The next production-planning step consolidated the existing source, teacher,
model, crop-contract, full-frame, and oracle receipts into one dashboard so the
next experiment is selected from the whole evidence set rather than from the
latest local CNN result.

Tool:

```text
tools/cnn/rank_preview_candidate_evidence.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v1/preview_candidate_evidence_rank.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v1/preview_candidate_evidence_rank.html
```

Result:

| evidence class | best row | pass | interpretation |
| --- | --- | ---: | --- |
| crop-shaped no-REF route | `crop_holdout_v32` | 84/84 | Crop-local routing is solved enough for diagnostics. |
| production-shaped full-frame route | `fullframe_scene_gated_84` | 63/84 | Arbitrary full-image tiling is still the blocker. |
| hard-row no-REF model | stitched context post-refiner | 2/24 | Local/post/refiner-style models are not sufficient. |
| diagnostic/oracle ceiling | full-resolution REF field | 24/24 | The target is reachable only with information the current runtime path lacks. |

The dashboard ranks 209 variant summaries, of which 67 are production-eligible
runtime-source, no-REF full-frame, or no-REF model rows. The split rules out
another small local correction, affine field, dense warp, exact-crop-teacher
post-distill, source-feature residual, residual band, or residual U-Net pass as
the next high-EV production move. The next viable PREVIEW experiment should
change the runtime-safe source/teacher representation or move to a more global
image-conditioned model that can learn the missing full-image low/mid/detail
placement without REF at render time.

### Codec-Derived Teacher Source Probe

The next bounded source/teacher diagnostic tested whether registered
codec-derived renders could provide a better no-REF teacher for embedded
PREVIEW than the current UPRESABLE/source path. Candidate renders used only the
source DNG plus registered codec/CNN/demosaic pipelines. REF was rendered only
for metrics.

Tool:

```text
tools/cnn/score_preview_codec_teacher_sources.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/codec_teacher_source_score_hard8_v1/preview_codec_teacher_source_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/codec_teacher_source_score_hard8_v1/preview_codec_teacher_source_score.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/codec_teacher_source_score_holdout28_q8_v1/preview_codec_teacher_source_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/codec_teacher_source_score_holdout28_q8_v1/preview_codec_teacher_source_score.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/codec_teacher_source_score_holdout28_q8_true_ref_v1/preview_codec_teacher_source_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/codec_teacher_source_score_holdout28_q8_true_ref_v1/preview_codec_teacher_source_score.html
```

Summary:

| source/teacher candidate | set | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 | median bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpr_tools_q8`, no CNN | hard eight | 12/24 | 0.1849 | 0.8789 | 25.37 | 5.43 | 21.97 MiB |
| `gpr_tools_q3` + BIBO_1x | hard eight | 7/24 | 0.2365 | 0.2440 | 15.63 | 11.60 | 15.76 MiB |
| `gpr_tools_q8`, no CNN | 28-image holdout, resolved true REF | 32/84 | 0.1849 | 0.8789 | 14.05 | 18.87 | 2.06 MiB |

The earlier broad q8 receipt reported 72/84 because some editable-DNG rows were
compared against their source path instead of the resolved true REF DNG. The
corrected true-REF receipt is 32/84 and matches the q8 full-frame source
baseline in the low-field trainer. The hard-eight result remains 12/24 because
those rows already came from the same diverse true-REF source. This makes
archival q8 a useful runtime source component for some hard rows, not a
production PREVIEW teacher.

The aggregate evidence-rank dashboard was regenerated after this probe:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v2/preview_candidate_evidence_rank.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v2/preview_candidate_evidence_rank.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v3/preview_candidate_evidence_rank.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v3/preview_candidate_evidence_rank.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v4/preview_candidate_evidence_rank.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v4/preview_candidate_evidence_rank.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v5/preview_candidate_evidence_rank.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/preview_candidate_evidence_rank_v5/preview_candidate_evidence_rank.html
```

Updated result:

| evidence class | best row | pass | interpretation |
| --- | --- | ---: | --- |
| crop-shaped no-REF route | `crop_holdout_v32` | 84/84 | Crop-local routing is solved enough for diagnostics. |
| production-shaped full-frame route | `fullframe_scene_gated_84` | 63/84 | Arbitrary full-image tiling is still the blocker. |
| hard-row no-REF model | stitched context post-refiner | 2/24 | Local/post/refiner-style models are not sufficient. |
| codec-derived no-REF teacher/source | `gpr_tools_q8`, no CNN | 32/84 true-REF broad, 12/24 hard | Archival/still codec rendering is not sufficient; the old broad score used the wrong REF for editable-DNG rows. |
| metric-selected selector oracle | scene-gated full-frame or q8 | 74/84 | A two-way runtime selector cannot clear the gate even with oracle selection. |
| diagnostic/oracle ceiling | full-resolution REF field | 24/24 | The target is reachable only with information the current runtime path lacks. |

The dashboard now ranks 215 variant summaries, of which 70 are
production-eligible runtime-source, no-REF full-frame, or no-REF model rows.

### Runtime Source/REF Policy Audit

A follow-up audit scores the rendered runtime source crop PNGs directly against
their resolved true REF crop PNGs before any model is applied. This isolates the
source-policy gap from CNN capacity, routing, and post-processing.

Tool:

```text
tools/cnn/audit_preview_source_ref_policy.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/source_ref_policy_audit_v1/preview_source_ref_policy_audit.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/source_ref_policy_audit_v1/preview_source_ref_policy_audit.html
```

Result:

| slice | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| all rows | 20/84 | 0.6839 | 0.2922 | 14.04 | 18.89 |
| clean UPRESABLE source root | 20/84 | 0.6839 | 0.2922 | 14.04 | 18.89 |
| diverse REF rows | 0/24 | 0.6839 | 0.2922 | 17.00 | 10.70 |
| Barnsky REF rows | 20/60 | 0.1745 | 0.9674 | 14.04 | 18.89 |

Interpretation: the current full-image runtime source starts far outside the
PREVIEW gate before any model runs. That explains why crop-shaped routing can
reach 84/84 while production-shaped full-frame output stalls at 63/84. The next
PREVIEW candidate should change the source-policy/full-image training
formulation or train a global image-conditioned model against the resolved
true-REF target. Another local post-refiner, q8 selector, or source-preserving
low-field residual is not the next high-EV path.

### Source-Policy Low-Field Generalization Check

A bounded follow-up trained the existing full-image band refiner on the 20
Barnsky images while holding out all eight diverse images. Runtime inputs remain
source RGB, normalized coordinates, source global RGB stats, and the checkpoint;
REF is supervision/scoring only. This tests whether the clean UPRESABLE source
can be corrected by sequence-family low-field learning before spending more
time on larger CNN variants.

Command shape:

```text
tools/cnn/train_preview_fullimage_band_refiner.py
--model-width 1024 --architecture direct --width 32 --depth 4
--conditioning xy_global_color_stats --steps 300 --batch-all
--ref-render-format png --crop-loss-weight 5.0
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/upresable_source_lowfield_barnskyfit_diverseholdout_w1024_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/upresable_source_lowfield_barnskyfit_diverseholdout_w1024_v1/preview_fullimage_band_refiner.html
```

Result:

| variant | all rows | fit rows | held-out diverse rows | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| source baseline | 20/84 | 20/60 | 0/24 | 0.6839 | 0.2922 | 14.04 | 18.89 |
| generated low-field residual | 52/84 | 52/60 | 0/24 | 0.8260 | 0.2024 | 6.20 | 44.00 |
| generated low plus source high, sigma 4 | 52/84 | 52/60 | 0/24 | 0.8963 | 0.1707 | 6.18 | 44.12 |
| REF low-field residual oracle | 60/84 | 60/60 | 0/24 | 0.6684 | 0.4082 | 17.43 | 10.10 |

Timing and memory receipt:

```text
render_ms_total=295317.68
train_ms=434651.49
train_steps_per_second=0.6902
model_ms_median=51.54
max_rss_mb=11930.52
checkpoint_sha256=1404776e09c9fbe49fed3d8d6ab2731d53267562c446f72fbc4d226af23fd8f1
```

Interpretation: the model can fit the Barnsky sequence-family rows, so capacity
for that low-field correction is present. It does not generalize at all to the
diverse holdout, and even REF-low/source-high remains 0/24 there. The remaining
blocker is therefore the diverse source/target structure/detail gap, not merely
a trainable sequence-color low-field.

### Scene-Gated vs q8 Selector Ceiling

The q8 broad result made a source-policy router worth checking before training
another model. A metric-selected oracle union compared the current scene-gated
full-frame route with q8 direct render on the same 84 holdout rows.

Tool:

```text
tools/cnn/score_preview_policy_union.py
```

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/policy_union_scene_gated_vs_q8_v1/preview_policy_union_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/policy_union_scene_gated_vs_q8_v1/preview_policy_union_score.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/policy_union_scene_gated_vs_q8_true_ref_v1/preview_policy_union_score.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/policy_union_scene_gated_vs_q8_true_ref_v1/preview_policy_union_score.html
```

Result:

| variant | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| scene-gated full-frame | 63/84 | 0.5749 | 0.6288 | 19.26 | 8.75 |
| q8 direct render, true REF | 32/84 | 0.1849 | 0.8789 | 14.05 | 18.87 |
| oracle union | 74/84 | 0.1769 | 0.8789 | 25.96 | 4.37 |

The corrected union still reaches only 74/84. A simple source-derived selector
between these two paths therefore cannot reach production quality, even before
accounting for classifier error. The next candidate needs a stronger true-REF
source/teacher representation or a global model that changes the hard rows
themselves, not a selector over the current two outputs.

### q8 Low-Field Refiner Smoke

A q8 full-frame source receipt was materialized to test whether the remaining
hard rows can be moved by a learned full-image low-field correction.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_fullframes_hard5_v1/preview_codec_source_fullframes.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_lowfield_refiner_hard5_pngref_batch512_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_fullframes_holdout28_v1/preview_codec_source_fullframes.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_lowfield_refiner_holdout28_hard5out_pngref_batch512_v1/preview_fullimage_band_refiner.json
```

Result:

| variant | scope | pass | interpretation |
| --- | --- | ---: | --- |
| q8 source baseline | hard-five fit smoke | 3/15 | Matches corrected q8 source rows. |
| generated low-field residual | hard-five fit smoke | 10/15 | The correction is learnable as a capacity fit. |
| q8 source baseline | 28-image true-REF holdout | 32/84 | Corrected broad q8 baseline. |
| generated low-field residual | hard-five held out from 23-image fit set | 25/84 | The current formulation does not generalize and is not production. |

### q8 Source Low-Field Split Diagnostics

The next q8 pass reused the materialized q8 full-frame source receipt and
tested the same low-field model under three broader split contracts. Runtime
inputs remain q8 source RGB, normalized coordinates, source global RGB stats,
and checkpoint weights. REF is supervision/scoring only. These are diagnostics,
not production registrations.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_barnskyfit_diverseholdout_w1024_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_barnskyfit_diverseholdout_w1024_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_allfit_w1024_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_allfit_w1024_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_diversefit_barnskyholdout_w1024_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_diversefit_barnskyholdout_w1024_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_residual_unet_allfit_w512_smoke_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_lowfield_residual_unet_allfit_w512_smoke_v1/preview_fullimage_band_refiner.html
```

Result:

| split | q8 source baseline | generated low-field residual | generated low plus q8 high, sigma 4 | REF-low/q8-detail oracle | interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| Barnsky fit, diverse holdout | 32/84 | 50/84 | 51/84 | 78/84 | Fits 50/60 Barnsky rows but collapses to 0/24 on diverse holdout. |
| all 28 fit | 32/84 | 60/84 | 60/84 | 78/84 | Even all-fit cannot approach the REF-low oracle. |
| diverse fit, Barnsky holdout | 32/84 | 0/84 | 0/84 | 78/84 | The diverse-only direct low-field head does not preserve even q8 baseline quality. |
| residual-U-Net all-fit, 512-wide smoke | 32/84 | 56/84 | 53/84 | 78/84 | Smaller U-Net reduces worst dE but does not beat the direct all-fit pass count. |

Split details:

```text
Barnsky-fit generated_lowfield_residual: fit 50/60, holdout 0/24
Barnsky-fit REF-low oracle: fit 60/60, holdout 18/24
All-fit generated_lowfield_residual: fit 60/84
Diverse-fit generated_lowfield_residual: fit 0/24, holdout 0/60
Residual-U-Net smoke generated_lowfield_residual: fit 56/84
```

Residual-U-Net smoke timing:

```text
train_ms=33219.22
train_steps_per_second=2.4082
model_ms_median=106.81
max_rss_mb=10607.08
checkpoint_sha256=832b282b84f29e5d1651ff9066db56b7db974ccdbe6ce1c1d6267b9ac2652acf
```

Interpretation: q8 carries useful detail for the diverse images, because the
REF-low/q8-detail oracle reaches 78/84. The current direct low-field model is
not the missing production formulation: it fails the diverse holdout, cannot
fit the mixed 28-image set to the oracle ceiling, and fails as a diverse-only
specialist. A small residual-U-Net smoke does not close the gap either. The
next PREVIEW experiment should change model class and conditioning more
substantially, for example a stronger image-conditioned/global source-to-target
model or a different runtime-safe source/teacher representation, before trying
to register another low-field variant.

### q8 Source Multiband Residual-U-Net

The next bounded pass kept the q8 full-frame runtime source but expanded the
model input beyond source low RGB plus coordinates. The new conditioning mode
adds source-derived blur bands, high-frequency residuals, absolute residuals,
gradient magnitude, laplacian, and source RGB global mean/std planes. REF is
still used only as training supervision and metrics reference.

Artifacts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_multiband_residual_unet_allfit_w512_smoke_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_multiband_residual_unet_allfit_w512_smoke_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_multiband_residual_unet_hard8holdout_w512_smoke_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_multiband_residual_unet_hard8holdout_w512_smoke_v1/preview_fullimage_band_refiner.html
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_multiband_residual_unet_diverseholdout_w512_smoke_v1/preview_fullimage_band_refiner.json
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_multiband_residual_unet_diverseholdout_w512_smoke_v1/preview_fullimage_band_refiner.html
```

Result:

| split | generated low-field residual | source baseline | REF-low/q8-detail oracle | interpretation |
| --- | ---: | ---: | ---: | --- |
| all 28 fit | 72/84 | 32/84 | 78/84 | Multiband conditioning is a real all-fit improvement over the prior 56/84 residual-U-Net smoke. |
| non-hard fit, hard-eight holdout | 59/84 | 32/84 | 78/84 | Fit side is 59/60, but hard holdout is 0/24 and worse than q8 source baseline. |
| hard-eight fit, diverse holdout | 18/84 | 32/84 | 78/84 | Hard fit reaches 18/24, but diverse holdout is 0/60. |

Timing and hashes:

```text
all-fit model_ms_median=24.91
all-fit train_steps_per_second=2.1362
all-fit max_rss_mb=11178.00
all-fit checkpoint_sha256=5780b68e78966ebf92777b7c340d6497e7b27ab037baf2693d39a11adf23e25f

hard-holdout model_ms_median=24.46
hard-holdout train_steps_per_second=3.1264
hard-holdout max_rss_mb=10927.94
hard-holdout checkpoint_sha256=3cacdbbfb4d435299e1e3f8d2dc1d72c4ec92e6a5190fdacd919f6af00972881

diverse-holdout model_ms_median=8.99
diverse-holdout train_steps_per_second=7.6090
diverse-holdout max_rss_mb=10948.86
diverse-holdout checkpoint_sha256=a4a54e5716b02121d62e8dc9da9380e8e25535a4c31e7a4948c17753d8f08fa0
```

Interpretation: the richer source-derived input stack is necessary but not
sufficient. It can fit the mixed dashboard much better than the previous small
U-Net, but the split failures show that this single global model is learning
scene-family-specific correction rather than a stable runtime source-to-target
mapping. The next viable path should use routed/specialist training with real
per-cluster data or a larger paired corpus/target, then validate on held-out
full images before any production registry entry.
