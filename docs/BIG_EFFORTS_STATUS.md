# Big Efforts Status

Last refreshed: 2026-06-30

This document maps the repo to the four large product efforts. It is a
planning/status document, not a replacement for the release evidence manifest.
If a metric here conflicts with a committed receipt, the receipt wins.

## Summary

| effort | current status | production interpretation |
|---|---|---|
| Raw stills for 50 MP / 100 MP cameras | Strong, production-gated for the current tested Bayer surface, including all normal unpacked 2x2 Bayer phases in committed synthetic conformance. | Good enough to present as a working stills product path, with explicit open work on more real alternate-phase fixtures and camera-calibrated noise. |
| Raw video MVP for GoPro / Mission 1 | Strong prototype/Labs handoff, blocked on real camera closure. | Good enough for GoPro engineers to pick up and run; not done until real sensor/DMA/storage/display receipts exist. |
| Raw stills improvement / expensive SR | Partly done through 1x still CNN, reusable 4K/8K SR machinery, routed Mission/Z8/X2D still-SR specialists, full-frame receipts, rendered proxy review, and X2D editor-openability plus metadata-transplant proof. | Not done until full raw-editor latitude, X2D exposure-stress, and noise-aware target receipts pass. |
| Raw video improvement / PSF-aware Bayer resize | Partly done through 4K cleanup and candidate-aware 8K SR. | Not done as a formal PSF/blur-calibrated resizing model. |

## 1. Raw Stills

Goal: best still images for modern 50 MP and 100 MP Bayer cameras, with
normal Bayer support, noise-aware compression, and texture/noise handled
without confusing signal for noise.

Current evidence:

- Three production STILL tiers pass the committed visual gate on 50 MP images:
  9.80 MB, 15.05 MB, and 27.17 MB mean size.
- Capability regression includes 12 MP, 23 MP, 50 MP Z8, and 100 MP-class X2D
  roundtrips.
- The legacy stills SDK/CLI path now exposes RGGB, GBRG, GRBG, and BGGR at
  12/14/16 bits. `test_still_matrix.sh` covers the full normal unpacked Bayer
  phase set; `test_capabilities.py` includes alternate-phase capability rows.
- Fixture compatibility covers Mission 1 50 MP DNG, Mission 1 12 MP DNG,
  Mission 1 50 MP GPR, Nikon Z8 DNG, Hasselblad X2D DNG, iPhone CFA DNG,
  iPhone metadata roundtrip, and iPhone Linear Raw rejection.
- The CLI exposes DNG NoiseProfile-aware denoise/noise replacement plumbing,
  but the current raw-noise audit forbids treating the old single-frame REF
  residual as pure removable noise.
- `tools/build_camera_noise_calibration.py` now emits a validated
  `gpr.camera_noise_calibration.v1` sidecar from raw darkframe stacks. This is
  the production rail for future noise-aware compression and CNN targets.
- `tools/convert_darkframe_calibration_to_noise_sidecars.py` converted the real
  X2D and Z8 darkframe calibration artifacts into v1 sidecars with selected
  source-frame manifests and SHA-256 hashes:
  `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_sidecars_20260629/`.

Boundaries:

- Current guarded Bayer surface is "normal unpacked 2x2 Bayer" for the legacy
  stills path, not every possible CFA or packed variant. FUSED/video is still
  scoped separately and remains RGGB/GBRG until its header contract is expanded.
  More real BGGR/GRBG camera fixtures should be added before claiming broad
  real-camera alternate-phase coverage.
- Nonzero camera-noise removal/addback is not promoted as a production stills
  claim yet. The safe current decision is: keep signal targets raw-like, use
  DNG NoiseProfile/ISO as conditioning metadata, and accept nonzero clean
  targets only after darkframes, flat-fields, frame stacks, or equivalent
  calibrated evidence prove the residual is noise rather than image detail.

Next production work:

1. Add real BGGR and GRBG camera fixtures to back the committed synthetic
   stills conformance cells.
2. Apply the camera/ISO noise-calibration sidecar flow to Mission 1 and iPhone
   darkframes/frame stacks where available.
3. Re-run the raw-noise/signal audit before training any CNN on nonzero clean
   targets.
4. Add a 100 MP real-fixture visual dashboard, not just synthetic capability
   timing/PSNR.

## 2. Raw Video MVP

Goal: a minimal viable raw-video path for a GoPro product.

Current evidence:

- `.gvid` stores real per-frame FUSED `.gpr` Bayer payloads. The project does
  not count wrapping already-compressed camera `.GPR` files as encode success.
- Mission 1 native 4096 x 3072 Bayer recompression clears the active 20 fps
  Pi 5 stand-in floor with zero drops and valid `.gvid` receipts.
- 1024 x 768 camera-back preview is decoded from the same 4K `.gvid` stream
  above 20 fps on the Pi 5 stand-in.
- The handoff bundle, Labs runbooks, quick validation script, target closure
  package, `.gvid` conformance tests, and sanitizer-clean CI are in place.

Boundaries:

- Actual Mission 1 firmware readiness is still blocked on a camera-role run:
  real sensor/DMA or camera ring-buffer source, storage handoff, rear-display
  handoff, zero drops, valid `.gvid`, and timing receipt.
- Strict 24 fps is not production-proven for the current quality profile.
  The active floor is 20+ fps on the Pi 5 stand-in unless the product target is
  raised again.

Next production work:

1. Give GoPro engineers the handoff bundle and have them run
   `tools/run_gopro_mission1_quick_validation.py` on real Mission 1 hardware.
2. Compare camera-role source timing against the FIFO/DMA simulator receipts.
3. If strict 24 fps is required, optimize encode/write overlap or the FLL2
   quality profile only after real camera source timing is known.

## 3. Raw Stills Improvement / Expensive SR

Goal: an offline path that can spend substantial time to produce the best
possible still, including 50 MP and 100 MP outputs where high-quality SR is
worth minutes rather than milliseconds.

Current evidence:

- The matched still 1x CNN lets the q0 and q3 still tiers pass the visual gate.
- The 4K cleanup and 8K SR tooling proves the repo can train, register, gate,
  package, and review offline CNN outputs.
- The current 8K SR path has Mission42 and Z8 broad full-frame evidence, 8K
  `.gvid` packaging, editable DNG/GPR packaging, metadata receipts, and ProRes
  review artifacts.
- `tools/build_premium_still_sr_gate_receipt.py` now emits a
  `gpr.premium_still_sr_gate.v1` skeleton receipt with editable raw, review
  media, and dashboard artifact hashes. It is deliberately non-production until
  real 50 MP / 100 MP fixtures and gate metrics are supplied.
- `tools/build_premium_still_sr_readiness.py` now emits a current-state
  readiness report and a validating non-production gate receipt from the merged
  baselines, 50 MP / 100 MP capability rows, reusable SR packaging evidence,
  and X2D/Z8 noise sidecars.
- `tools/build_premium_still_sr_fixture_manifest.py` turns the latest real
  fixture compatibility receipt into a hashed 50 MP / 100 MP still-SR manifest
  with available noise-sidecar references.
- `tools/cnn/build_premium_still_sr_pairs.py` converts that manifest into
  same-color 2x Bayer SR tile pairs using `gpr_tools` extraction and per-camera
  black/saturation normalization.
- The first dedicated still-SR smoke checkpoint trains from those pairs and
  proves the loop executes, but it is not production-grade: X2D holdout RMSE
  improvement is only about 0.0008 percent and full visual/editor-latitude
  receipts are still missing.
- A larger 64-tile-per-fixture still-SR run peaks at about 0.15 percent held-out
  X2D RMSE improvement at step 400, then overfits/regresses by step 1000. This
  is a positive signal, not a production checkpoint.
- `tools/build_premium_still_sr_candidate_dashboard.py` emits the current
  still-SR candidate metric dashboard, including pair/checkpoint hashes,
  best-step metrics, and final-step regression.
- `tools/build_premium_still_sr_visual_review.py` emits the current tile-level
  visual review dashboard with baseline/model/target/error contact sheets for
  the X2D holdout:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_20260629/index.html`.
- The xlarge 1,024-tile diagnostic narrowed the blocker. Whole-image X2D
  holdout remains weak at about 0.09 percent RMSE improvement, but random
  tile holdout improves about 12.74 percent overall. Per-image random holdout
  improves Mission 1 by about 56 percent, Z8 by about 20 percent, and X2D by
  about 2.36 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_xlarge_dashboard_20260629/index.html`.
- Eight additional Hasselblad X2D 100C `.fff` files were converted to DNG with
  Adobe DNG Converter and added as 100 MP fixtures. With those fixtures, the
  original X2D holdout improves about 0.30 percent RMSE, and a held-out Austin
  X2D scene improves about 2.16 percent RMSE:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_x2d_batch_dashboard_20260629/index.html`.
- An X2D-only specialist trained on the 100 MP fixtures improves the hard
  original-X2D holdout to about 1.08 percent RMSE and 1.18 percent MAE, beating
  the mixed-camera X2D-batch candidate on the same holdout:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_x2d_specialist_dashboard_20260630/index.html`.
- A Mission 1-only specialist trained on 84 real 8192 x 6144 Mission DNG/GPR
  fixtures improves the held-out `mission1_gp017504_dng,gpr` tiles by about
  58.13 percent RMSE and 49.40 percent MAE:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_mission1_specialist_dashboard_20260630/index.html`.
- The same Mission 1 specialist has a first full-frame held-out GP017504
  DNG/GPR receipt. It improves over bilinear same-color upsampling by about
  56.62 percent RMSE, 46.67 percent MAE, and 29.70 percent gradient MAE, with
  Mac/MPS tiled inference plus 8192 x 6144 raw write at about 2.68 fps:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_mission1_specialist_20260630/eval/index.html`.
- The routed full-frame sweep now covers every current specialist route. Z8
  `Z8Z_1349` improves by about 40.74 percent RMSE, 7.86 percent MAE, and
  4.06 percent gradient MAE at about 3.20 fps with raw write. X2D
  `2024_April_X2D_1742` uses a 11664 x 8748 full-gate crop and improves by
  about 1.03 percent RMSE, 1.20 percent MAE, and 1.06 percent gradient MAE at
  about 1.55 fps with raw write:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_z8_specialist_20260630/eval/index.html`,
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_x2d_specialist_20260630/eval/index.html`.
- The first routed rendered/editor-latitude proxy review covers Mission 1,
  Z8, and X2D crops at -2/0/+2 EV. The model improves 33 of 36 crop/EV rows;
  the three regressions are all X2D center-crop rows under exposure stress:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rendered_review_routed_20260630/index.html`.
- The first X2D 100 MP editor-openability receipt rescales the 11664 x 8748
  still-SR output back into X2D code values, packages it as editable DNG/GPR,
  and verifies a source-camera metadata transplant. The transplanted DNG opens
  with rawpy, has no missing required render tags, and only allows the expected
  two-row `ActiveArea` crop, `AsShotNeutral` formatting, and missing
  recommended `OpcodeList2`. The q3 GPR readback opens through GPR-to-DNG and
  scores 57.49 dB across the X2D black-to-white range:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/editor_receipt_x2dscale_meta/index.html`.
- `tools/build_premium_still_sr_router_plan.py` now emits a metadata-only
  routed specialist plan. The current plan maps `x2d:100mp:dng` to the X2D
  specialist, `z8:50mp:dng` to the Z8 specialist, and both
  `mission1:50mp:dng` and `mission1:50mp:gpr` to the Mission 1 specialist:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_router_plan_20260630/index.html`.
- A Z8-only specialist trained on 24 Z8 DNG fixtures improves the held-out
  `z8_z8z_1349` fixture by about 25.52 percent RMSE and 4.28 percent MAE:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_z8_specialist_dashboard_20260630/index.html`.

Boundaries:

- The approved 8K SR path is a Mission/Z8 raw-video reconstruction path, not a
  dedicated general still-SR product for every 50 MP/100 MP camera.
- "Looks sharper" is not enough for a still-SR promotion. The output must keep
  raw-editor latitude, tone/color stability, worst-row visual quality, and
  camera-specific noise handling.
- The current visual review is tile-level Bayer-plane RGB only. It is useful
  for softness/artifact inspection, but it is not a full-frame raw-editor
  latitude receipt.
- Current evidence points to X2D/generalization and fixture diversity as the
  premium still-SR blocker, rather than a broken training loop.
- Added X2D diversity improves same-camera-class generalization, but the
  original X2D scene remains a hard outlier. That points to target/loss or
  scene-specialist work before premium still-SR can be promoted.
- The specialist results support a camera/source-aware router or separate
  specialist checkpoints. Every current route now has a first full-frame
  check and rendered proxy review, and X2D has editor-openability plus
  source-camera metadata proof. X2D remains weak, and the routed suite still
  lacks full raw-editor latitude receipts.
- The router plan is a contract for future routing, not a production registry.
  X2D, Z8, and Mission 1 now have candidate specialists, but all still lack
  production full-frame/editor-latitude gates.

Next production work:

1. Convert the X2D openability/metadata receipt into full raw-editor latitude
   receipts, starting with the X2D center-crop exposure-stress blocker.
2. Train against high-quality still targets, with camera/ISO metadata and a
   noise policy that passes the raw-noise/signal audit.
3. Add full-frame still visual dashboards, raw-domain metrics, and raw-editor
   latitude checks for each routed candidate.
4. Emit review TIFF/ProRes/contact sheets plus editable DNG/GPR receipts.

## 4. Raw Video Improvement / PSF-Aware Resize

Goal: understand and improve the point-spread/blur introduced when resizing or
reconstructing Bayer data, especially 12 MP or 4K capture feeding 4K cleanup
and 8K reconstruction.

Current evidence:

- Mission native12 4K cleanup is approved for offline/review scope.
- Candidate-aware 8K SR passes broad Mission42 and Z8 full-frame gates.
- Existing diagnostics already look at CFA raw error, rendered tone/green
  behavior, phase, edge alignment, gradient energy, and lower-right failures.
- `tools/build_bayer_resize_psf_receipt.py` now emits a synthetic
  non-production `gpr.bayer_resize_psf_receipt.v1` receipt. This keeps the PSF
  evidence contract executable.
- `tools/build_bayer_resize_psf_from_pairs.py` now emits a pair-derived
  non-production PSF receipt from the real premium still-SR Mission 1, Z8, and
  X2D tile pairs. The 2026-06-29 run confirms the modeled same-color 2x target
  is effectively a 2x2 box kernel, with fitted weights near 0.25 each:
  `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629/index.html`.

Boundaries:

- The current SR path is not a formal PSF-calibrated model. It is an approved
  empirical candidate with dashboards and receipts.
- The pair-derived PSF receipt validates the current modeled resize target. It
  does not measure native camera sensor/DMA/display PSF because the low side of
  the pair is generated from the high-resolution raw extraction.
- Replacing it requires beating the current baseline on full-frame Mission and
  Z8 gates, not just lowering tile loss or improving a small crop.

Next production work:

1. Replace modeled-pair PSF evidence with native capture/display PSF
   measurements from real high-res-to-native-low-res Mission/Z8 pairs and
   sharp-edge/texture targets.
2. Train with CFA-aware high-res RGB/downsample targets and PSF-conditioned
   losses.
3. Promote only if Mission42 and Z8 all24 gates improve, worst rows are clean,
   and `.gvid`, editable DNG/GPR, ProRes, timing, and memory receipts exist.

## Quick Answer

We are not done with all four big efforts.

What is done enough to show externally:

- stills compression tiers and current 50 MP production still path,
- `.gvid` raw-video prototype/Labs handoff,
- Mission 1 20+ fps Pi stand-in raw-video MVP,
- 1024 preview from the same `.gvid`,
- current offline 4K cleanup and 8K SR baselines.

What remains:

- real Mission 1 camera-role validation,
- broader Bayer phase coverage,
- calibrated camera-noise removal/addback,
- dedicated premium still-SR product gates,
- formal PSF/blur-aware video SR replacement work.
