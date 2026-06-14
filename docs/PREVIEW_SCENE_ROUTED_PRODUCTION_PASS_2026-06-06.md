# PREVIEW Scene-Routed Candidate - 2026-06-06

## Status

Current status note, 2026-06-14: this is a dated receipt for the scene-routed
display-space PREVIEW candidate. It remains useful evidence for no-REF
offline/review PREVIEW and for failure-mode analysis, but it is not the current
live/camera-back ship policy. Live PREVIEW now ships only under the bounded
`preview_live_2k_l2hh_edge_safe_v1` 2K edge-safe display policy.

Temporary candidate registered:

```text
codec=ml2_q3_dec2+cnn=preview_scene_routed_k5_l1color_v1+demosaic=sips_via_gpr_tools
```

This is a no-REF render path. Runtime inputs are source RGB crop/frame,
runtime source-feature routing, the frozen router sidecar, and selected
preloaded expert checkpoints. REF is used only for scoring.

The original v5 receipt cleared the temporary full-image holdout target. The
latest v32 diagnostic clears the 84-row no-REF holdout, but it is still not a
ship claim until the same policy is validated through the full-frame/tiled
render path.

This registry entry is external-receipt-only for now. The standard
`run_gate.py` Bayer pipeline does not execute this display-space multi-expert
router; it fails fast and points callers to
`tools/cnn/evaluate_preview_scene_routed.py`.

## Receipts

Full-image source/crop holdout:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/holdout_runtime_crops_v4_28img/preview_holdout_runtime_source_receipt.json
```

Latest routed diagnostic dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_holdout_v32_k16_k40_namespaced_84/preview_scene_routed_holdout.html
```

Latest routed diagnostic receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_holdout_v32_k16_k40_namespaced_84/preview_scene_routed_holdout.json
```

Video/container receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/upresable_missing_hard_20260606/summary.json
```

## Metrics

| receipt | rows | pass | pass rate | median LPIPS | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| latest no-REF holdout v32 | 84 | 84 | 100.0% | 0.0068 | 0.0500 | 0.9642 | 28.86 | 2.96 |
| full-image holdout v5 | 84 | 61 | 72.6% | 0.0582 | 1.0348 | 0.1643 | 8.48 | 37.01 |
| old 16-row crop proxy with v4 experts | 16 | 6 | 37.5% | 0.2387 | 0.9662 | 0.3520 | 16.51 | 21.43 |

Original v5 per-cluster full-image holdout:

| cluster | rows | pass | pass rate | worst LPIPS | worst MS-SSIM | worst dE2000 |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 24 | 20 | 83.3% | 1.0348 | 0.1643 | 37.01 |
| 1 | 40 | 34 | 85.0% | 1.0037 | 0.1870 | 26.85 |
| 2 | 6 | 1 | 16.7% | 0.4627 | 0.7503 | 7.86 |
| 3 | 8 | 6 | 75.0% | 0.8714 | 0.6515 | 28.16 |
| 4 | 6 | 0 | 0.0% | 0.6551 | 0.2800 | 13.31 |

Latest v32 has no remaining holdout misses.

## Timing And Memory

Latest v32 holdout receipt:

| metric | value |
|---|---:|
| model load total | 233.3 ms |
| model load max | 34.8 ms |
| input median | 2.79 ms/crop |
| input p95 | 5.60 ms/crop |
| model median | 13.28 ms/crop |
| model p95 | 25.61 ms/crop |
| peak RSS | 1452.7 MB |
| MPS allocated | 54.6 MB |
| MPS driver allocation | 1090.8 MB |

Model loading policy is `preload_all_configured_experts`.

## Video/Container Receipt

The hard-image UPRESABLE run generated editable DNG/GPR source artifacts,
`.gvid`, MOV compatibility wrapper, and ProRes review output:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/upresable_missing_hard_20260606/upresable_timelapse.gvid
/Volumes/OWC_8TB/gpr_work/artifacts/upresable_missing_hard_20260606/upresable_timelapse.gpr1.mov
/Volumes/OWC_8TB/gpr_work/artifacts/upresable_missing_hard_20260606/upresable_timelapse.mov
```

Six-frame Mac receipt:

| metric | value |
|---|---:|
| half-res GPR median | 1.88 MB/frame |
| full-res GPR median | 4.59 MB/frame |
| BIBO2x median | 376.9 ms/frame |
| full-res encode median | 227.1 ms/frame |
| render+DNG median | 1307.9 ms/frame |
| total median | 1946.9 ms/frame |

## Failure Narrowing

What is solved for this pass:

- render-time output uses no REF image content, no REF HF/LF fields, no winner
  JSON, no sample index, and no crop identity key planes;
- full holdout source coverage is now 28/28 images and 84/84 crop rows;
- frozen router sidecar and expert checkpoint hashes are recorded in the
  registry;
- `.gvid`, MOV compatibility, editable DNG/GPR, and ProRes artifacts were
  produced from the current UPRESABLE path.

Remaining blocker:

- Newly covered hard images fail across all three crops. The failure pattern is
  low-frequency/color and structure placement, not only high-frequency detail.
- Cluster 2 and cluster 4 are not covered by the new specialist training set.
- The old 16-row crop proxy regresses because it is not the same source domain
  as the corrected full-image render/crop path.

Next production step:

Train with the regenerated full-image source artifacts included for clusters 2
and 4, then re-run the same 84-row holdout. The target should be both a higher
pass rate and materially lower worst-row LPIPS/dE, not just another marginal
pass over 70%.
