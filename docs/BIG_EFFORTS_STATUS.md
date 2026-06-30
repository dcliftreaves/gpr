# Big Efforts Status

Last refreshed: 2026-06-30

This document maps the repo to the four large product efforts. It is a
planning/status document, not a replacement for the release evidence manifest.
If a metric here conflicts with a committed receipt, the receipt wins.
The generated audit dashboard for these same four pillars is tracked in
[`PRODUCT_PILLAR_SCORECARD.md`](PRODUCT_PILLAR_SCORECARD.md).

## Summary

| effort | done | current status | production interpretation |
|---|---:|---|---|
| Raw stills for 50 MP / 100 MP cameras | 90% | Strong, production-gated for the current tested Bayer surface, including all normal unpacked 2x2 Bayer phases in committed synthetic conformance, RGGB plus Mission 1 GBRG real-fixture coverage, and calibrated X2D/Z8 noise sidecars. | Good enough to present as a working stills product path, with explicit open work on real GRBG/BGGR fixtures and Mission/iPhone darkframe sidecars. |
| Raw video MVP for GoPro / Mission 1 | 80% | Strong prototype/Labs handoff, blocked on real camera closure. | Good enough for GoPro engineers to pick up and run; not done until real sensor/DMA/storage/display receipts exist. |
| Raw stills improvement / expensive SR | 60% | Partly done through 1x still CNN, reusable 4K/8K SR machinery, routed Mission/Z8/X2D still-SR specialists, full-frame receipts, rendered proxy review, X2D editor-openability plus metadata-transplant proof, X2D rawpy latitude diagnostics, structured HF residual target datasets, band diagnostics, raw-CFA expanded targets, no-REF HF residual probes including a matched dilated raw-CFA gate, calibrated noise-clean target sweep, raw-CFA residual alignment audit, trainable raw-CFA residual target NPZ, and the first true raw-CFA residual model receipts. | Not done until learned/modelled high-frequency texture restoration receipts pass; raw-CFA helps, the current local/dilated residual probes remain far below promotion, ISO 200 noise cleaning is too small to explain the gap, and the first raw-domain trainer narrows the blocker to X2D/domain generalization and low raw-residual recovery. |
| Raw video improvement / PSF-aware Bayer resize | 44% | Partly done through 4K cleanup, candidate-aware 8K SR, native high/low pair inventory, measurement plan, first native measurement run, and an explicit PSF gap closure plan. | Not done as a formal PSF/blur-calibrated resizing model until controlled high/low pairs produce a stable native kernel and PSF-conditioned gates pass. |

## 1. Raw Stills

Goal: best still images for modern 50 MP and 100 MP Bayer cameras, with
normal Bayer support, noise-aware compression, and texture/noise handled
without confusing signal for noise.

Current evidence:

- Three production STILL tiers pass the committed visual gate on 50 MP images:
  9.80 MB, 15.05 MB, and 27.17 MB mean size.
- Capability regression includes 12 MP, 23 MP, 50 MP Z8, and 100 MP-class X2D
  roundtrips.
- A real X2D 100MP visual roundtrip audit now exists at
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html`.
  It records a 11,664 x 8,750 DNG to GPR to DNG path, three 100 percent crop
  panels, a 47 MB `.gpr`, 593 ms encode, 965 ms decode, and 49.21 dB
  full-image raw Bayer PSNR.
- The legacy stills SDK/CLI path now exposes RGGB, GBRG, GRBG, and BGGR at
  12/14/16 bits. `test_still_matrix.sh` covers the full normal unpacked Bayer
  phase set; `test_capabilities.py` includes alternate-phase capability rows.
- Fixture compatibility covers Mission 1 50 MP DNG, Mission 1 12 MP DNG,
  Mission 1 50 MP GPR, Nikon Z8 DNG, Hasselblad X2D DNG, iPhone CFA DNG,
  iPhone metadata roundtrip, and iPhone Linear Raw rejection.
- The real Bayer phase discovery at
  `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html`
  confirms that the broader local Mission 1, Z8, X2D, and iPhone CFA fixture
  pool contains 74 normal 2x2 Bayer DNGs: 70 RGGB and 4 Mission 1 GBRG. GRBG
  and BGGR remain synthetic-conformance coverage until real fixtures are added.
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
- The camera-noise coverage audit at
  `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/index.html`
  records six production-ready darkframe sidecars: X2D at ISO 64, 200, 800,
  3200, and 12800, plus Z8 at ISO 500. Mission 1 and iPhone have real fixtures
  but no production-ready darkframe sidecars yet.
- The Mission/iPhone darkframe candidate audit at
  `/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_20260630/index.html`
  scans 50 local DNG candidates. It parsed 49 Mission 1 CFA DNGs and found 9
  darkframe-like frames, but they are split across 8 ISO groups and no group
  has the required four-frame stack. The iPhone file in this scan is the known
  Linear Raw negative fixture, not a CFA darkframe source.
- The broader real-photo Bayer phase sample at
  `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_realphotos_sample_20260630/index.html`
  scans 350 iPhone/GoPro/Hassel real-photo DNGs with the batch metadata path.
  It finds 316 Apple iPhone 7 Plus RGGB CFA fixtures and 4 GoPro GBRG fixtures,
  but still no real GRBG or BGGR fixture.
- The broader real-photo darkframe-candidate sample at
  `/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_realphotos_sample_20260630/index.html`
  parses 320 files and finds one iPhone ISO1250 RGGB dark-looking four-frame
  candidate stack. The boosted contact sheet
  `/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_realphotos_sample_20260630/iphone_darkframe_like_contact_x16.jpg`
  shows visible scene content in part of that group, so the audit now keeps it
  candidate-only: `production_sidecar_ready=false`.
- The stills fixture gap plan at
  `/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_20260630/index.html`
  turns those receipts into the concrete closure list: add real GRBG and BGGR
  fixtures, add Mission 1 and iPhone darkframe stacks, and top up the current
  Mission 1 ISO232 RGGB darkframe-like group with two more matching frames.
- The raw-stills capture request at
  `/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_20260630/index.html`
  converts that closure list into handoff-ready sample requests and validation
  commands for the missing GRBG/BGGR fixtures plus Mission/iPhone darkframe
  stacks.

Boundaries:

- Current guarded Bayer surface is "normal unpacked 2x2 Bayer" for the legacy
  stills path, not every possible CFA or packed variant. FUSED/video is still
  scoped separately and remains RGGB/GBRG until its header contract is expanded.
  Real GRBG and BGGR camera fixtures should be added before claiming
  broad real-camera alternate-phase coverage.
- Nonzero camera-noise removal/addback is not promoted as a production stills
  claim yet. The safe current decision is: keep signal targets raw-like, use
  DNG NoiseProfile/ISO as conditioning metadata, and accept nonzero clean
  targets only after darkframes, flat-fields, frame stacks, or equivalent
  calibrated evidence prove the residual is noise rather than image detail.

Next production work:

1. Fulfill the raw-stills capture request: add real GRBG and BGGR camera
   fixtures to back the committed synthetic stills conformance cells.
2. Collect or locate Mission 1 and iPhone darkframe/frame-stack data from that
   request, then apply the camera/ISO noise-calibration sidecar flow. For Mission 1, start
   from the candidate audit: the lowest-lift current group is ISO232 RGGB,
   which has two darkframe-like candidates and needs two more matching frames
   before sidecar construction.
3. Re-run the raw-noise/signal audit before training any CNN on nonzero clean
   targets.

## 2. Raw Video MVP

Goal: a minimal viable raw-video path for a GoPro product.

Current evidence:

- `.gvid` stores real per-frame FUSED `.gpr` Bayer payloads. The project does
  not count wrapping already-compressed camera `.GPR` files as encode success.
- Mission 1 native 4096 x 3072 Bayer recompression clears the active 20 fps
  Pi 5 stand-in floor with zero drops and valid `.gvid` receipts.
- 1024 x 768 camera-back preview is decoded from the same 4K `.gvid` stream
  above 20 fps on the Pi 5 stand-in.
- The handoff bundle, GoPro intake audit, Labs runbooks, quick validation
  script, target closure package, `.gvid` conformance tests, and
  sanitizer-clean CI are in place. The intake audit verifies the bundle while
  keeping camera-production status false until real camera-role receipts exist.

Boundaries:

- Actual Mission 1 firmware readiness is still blocked on a camera-role run:
  real sensor/DMA or camera ring-buffer source, storage handoff, rear-display
  handoff, zero drops, valid `.gvid`, and timing receipt.
- Strict 24 fps is not production-proven for the current quality profile.
  The active floor is 20+ fps on the Pi 5 stand-in unless the product target is
  raised again.

Next production work:

1. Give GoPro engineers the handoff bundle and intake audit, then have them run
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
- `tools/cnn/audit_premium_still_sr_raw_cfa_residual.py` now compares rendered
  HF residual supervision with the actual editable raw target:
  source raw minus candidate raw, high-passed phase-by-phase without mixing CFA
  colors. The expanded 351-row audit reports median absolute rendered-to-raw
  residual correlation 0.691 and median best-phase correlation 0.922:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_audit_20260630/index.html`.
  This is strong enough to justify the next training pass using same-color raw
  residuals directly rather than continuing to optimize rendered-HF residuals
  as the primary target.
- `tools/cnn/build_premium_still_sr_raw_cfa_residual_targets.py` now builds
  that training input. The full expanded target build lives at
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_20260630/index.html`
  and writes a 1.6 GB NPZ with candidate raw-CFA, candidate raw-HF, source
  raw-HF, rendered-HF luma review, and source-minus-candidate same-color raw-HF
  residual arrays for 351 rows / 13 scenes.
- `tools/cnn/train_premium_still_sr_raw_cfa_residual.py` now trains a
  four-plane raw residual model against that NPZ using candidate-only runtime
  inputs. The stabilized w32/2000-step receipts are diagnostic: held-out Z8 is
  mildly positive at about 0.50 percent median raw-residual MAE recovery, but
  held-out X2D remains negative at about -0.21 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/index.html`,
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/index.html`.
  A wider/block17 X2D pass reaches only about 0.02 percent median holdout
  recovery, while the stored candidate-HF feature probe and one-sigma
  noise-soft-threshold target remain negative. Those receipts narrow the
  blocker to X2D/domain generalization and recovery strength, not target
  availability, stored-HF feature mismatch, or a naive noise subtraction:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/index.html`,
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/index.html`,
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/index.html`.
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
- `tools/build_premium_still_sr_latitude_review.py` now emits a rawpy/LibRaw
  latitude dashboard that renders the original X2D DNG and the
  metadata-transplanted SR DNG with camera WB/color metadata at -2/0/+2 EV.
  The 2026-06-30 X2D run has 9 crop/EV rows, median display MAE 0.04281,
  median Y MAE 0.02909, median low-frequency Y MAE 0.00546, and median
  high-frequency Y MAE 0.02892. The worst rows are all +2 EV, with worst
  display MAE 0.09161, worst low-frequency Y MAE 0.01657, and worst
  high-frequency Y MAE 0.06095. The candidate carries only about 44-53 percent
  of the source high-frequency luminance energy in the +2 EV rows, with median
  HF correlation 0.406 and worst-row correlations around 0.398-0.483:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_synthetic_hf_20260630/index.html`.
- The same latitude review includes a source-HF oracle diagnostic. It preserves
  candidate low-frequency tone but injects source high-frequency content, so it
  is diagnostic only and cannot be used as a production/no-REF render path.
  With that oracle, worst +2 EV display MAE drops from 0.09161 to 0.01586 and
  worst +2 EV HF Y MAE drops from 0.06095 to 0.00005. This proves the next
  production experiment should synthesize or restore camera texture/noise,
  rather than chase broad tone mapping.
- A follow-up no-REF synthetic-HF sweep uses the X2D ISO 12800 darkframe
  sidecar to derive a normalized sigma of 0.00390 and tries deterministic
  generated high-frequency texture from candidate/runtime metadata only:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_synthetic_hf_20260630/index.html`.
  The best calibrated random-HF rows slightly worsen median display MAE
  from 0.04281 to 0.04293 and worst MAE from 0.09161 to 0.09167, while the
  median gap to the source-HF oracle remains 0.03713. That narrows the
  committed blocker to structured texture/detail reconstruction, not simple
  stochastic noise addback. The low HF correlation means the next training pass
  should learn a residual/detail field from high-quality still targets, not
  simply increase output HF amplitude.
- `tools/cnn/build_premium_still_sr_hf_residual_targets.py` now materializes
  that next supervised target: candidate rendered crops plus
  `source_hf - candidate_hf` residuals. The current X2D artifact has 9 crop/EV
  rows, median HF correlation 0.406, median residual absolute mean 0.04284,
  max residual absolute mean 0.09168, median residual p95 0.10893, and an
  83.4 MB compressed NPZ with artifact hash:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/index.html`.
  This target uses source HF for supervision only and is explicitly not a
  runtime/no-REF render path.
- `tools/cnn/train_premium_still_sr_hf_residual.py` now runs the first no-REF
  residual learner against that target. The current X2D w64/d6/2000-step smoke
  model uses candidate RGB, candidate high-pass, and deterministic XY only at
  inference. It improves train median residual MAE by 5.34 percent and +2 EV
  holdout median residual MAE by 4.03 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630/index.html`.
  This is not enough for production promotion; it narrows the next experiment
  to richer full-frame context, metadata/ISO-aware features, or a different
  LF/mid/HF target split rather than more random-HF addback.
- `tools/build_premium_still_sr_experiment_scoreboard.py` now ranks the
  premium still-SR training receipts and applies the no-REF runtime promotion
  guard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260630/index.html`.
  The current scoreboard finds 10 candidate receipts and zero promotable rows.
  The best single-scene no-REF row reaches 4.03 percent held-out MAE recovery;
  the broader multi-scene/noise-conditioned row remains 2.56 percent. This
  confirms the current 50 percent pillar score is still appropriate.
- `tools/cnn/analyze_premium_still_sr_hf_residual_bands.py` decomposes the X2D
  residual target by frequency and brightness. The current dashboard shows
  median Y residual absolute mean 0.02892, +2 EV median 0.05983, +2 EV p95
  0.15422, median HF energy ratio 0.467, fine-band residual share 0.980x,
  mid-band share 0.204x, and effectively zero coarse-band share:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_20260630/index.html`.
  This narrows the production blocker further: the missing X2D +2 EV detail is
  fine-band, brightness/exposure-conditioned texture/noise/detail. The next
  candidate should be fine-texture/noise-aware and exposure-conditioned before
  any full rawpy latitude promotion run.
- The exposure/brightness-aware residual trainer controls do not yet generalize
  well enough for promotion. A weighted EV/brightness model drops +2 EV holdout
  improvement from 4.03 percent to 3.39 percent. On a center-crop holdout split,
  the weighted model regresses by -1.56 percent and the unweighted
  EV/brightness model improves only 0.54 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_evbright_unweighted_cropholdout_w64_20260630/index.html`.
  This points to insufficient target diversity/full-frame context, not just
  missing scalar EV or brightness features.
- The HF residual target builder now supports deterministic grid crops with
  scene/source metadata. The first broader X2D grid target has 75 rows, median
  HF correlation 0.407, and median residual absolute mean 0.04456:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_grid5_20260630/index.html`.
  A no-REF w48/d5 probe holding out the center grid crop across EVs improves
  train median residual MAE by 1.65 percent and holdout by 1.69 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_grid5_centerholdout_w48_20260630/index.html`.
  The matching band analysis shows median fine-band residual share 0.969x,
  mid-band share 0.253x, and essentially zero coarse-band share:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_grid5_20260630/index.html`.
  This is better coverage, not production promotion; the next target needs
  multiple X2D scenes plus validated camera-noise sidecars.
- The X2D HF target path now also supports candidate raw renders through the
  source DNG metadata, plus deterministic same-color box2 degraded candidate
  raws and target NPZ merging. The first multi-scene X2D target has 81 rows
  across ISO 12800, ISO 3200, and ISO 6400 scenes, with exact sidecars for
  ISO 12800/3200 and bracket sidecars for ISO 6400:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/merged/merge_receipt.json`.
  A scene-held-out no-REF w48/d5 probe improves train median residual MAE by
  2.21 percent and held-out `x2d_austin0181_iso6400` by 1.46 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_w48_20260630/index.html`.
  Adding multiscale candidate high-pass features plus validated ISO/noise
  sidecar scalar planes improves the same scene holdout to 2.56 percent with a
  w96/d8 model:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/index.html`.
  The merged band analysis still shows median fine-band residual share 0.971x:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_band_analysis_20260630/index.html`.
  This confirms the blocker is no longer just a single-image target issue or
  missing scalar noise metadata; the production path needs a stronger
  larger-context raw-domain/noise-conditioned texture model.
- The target expansion pass has now been executed. The executor built the 10
  newly selected X2D/Z8 scenes, merged them with the existing target sources,
  and produced a 13-scene / 351-row HF residual target set:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/expanded_target_build_receipt.json`,
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/merged/merge_receipt.json`.
  The expanded band analysis still shows median fine-band residual share about
  0.981x:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/index.html`.
  Two expanded rendered-context training passes were run and rejected: the
  weighted w96 model was unstable, and the conservative w64 model landed near
  zero held-out recovery. This moves the blocker from target coverage to the
  model/feature contract; the next production pass should be raw/CFA-aware or
  otherwise larger-context texture modeling.
- Raw-CFA feature plumbing now exists. The target builder can write
  `candidate_raw_cfa4`, the merge tool records whether raw-CFA feature coverage
  is complete, and the trainer has a guarded
  `rgb_multiscale_rawcfa_coord_luma_ev_noise_bright` feature mode plus an
  explicit raw-CFA gated architecture for phase-detail features. The first real
  one-scene X2D target has 27 rows with 768 x 768 x 4 raw-CFA feature planes:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_smoke_targets_20260630/2025_10_oct_austin_0626/hf_residual_targets.json`.
  A w64/d6 raw-CFA probe improves +2 EV holdout residual MAE by only about
  0.24 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_probe_model_20260630/train_receipt.json`.
  The matched RGB-only ablation improves the same holdout by about 0.63
  percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_ablation_rgb_model_20260630/train_receipt.json`.
  The raw-CFA gated w48/d6/1000-step probe improves the same holdout by about
  0.79 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_gated_probe_w48_1000_20260630/train_receipt.json`.
  This proves the raw-CFA path runs and that a gated raw branch is more
  promising than naive channel concatenation.
- Expanded raw-CFA target coverage is now complete. The rebuilt target records
  351 rows across 13 X2D/Z8 scenes with `raw_cfa_feature_complete=true`:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json`.
  On held-out Z8, the raw-CFA gated model improves median residual MAE by about
  1.04 percent versus 0.36 percent for the matched RGB ablation:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_z8holdout_w48_1000_20260630/train_receipt.json`.
  On held-out X2D, it improves about 2.92 percent versus 2.42 percent:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_x2dholdout_w48_1000_20260630/train_receipt.json`.
  A matched dilated raw-CFA gated variant also exists:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_z8holdout_matched_w48_1000_20260630/train_receipt.json`
  and
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_x2dholdout_matched_w48_1000_20260630/train_receipt.json`.
  It improves the weak Z8 holdout from 1.04 to about 1.30 percent median MAE
  recovery, but trails the X2D baseline at 2.86 versus 2.92 percent and leaves
  severe negative worst rows. This moves the blocker from raw-CFA
  plumbing/coverage to target/model design: simple dilated context is not
  enough, and the next pass needs a stronger raw-domain/noise-cleaned target
  and model.
- A calibrated noise-clean target sweep now exists at
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_clean_sweep_x2d_smoke_20260630/index.html`.
  It uses the X2D raw-CFA smoke target and validated ISO 200 X2D sidecar. Gain
  16 changes about 11.93 percent of pixels but removes only about 0.24 percent
  median residual energy, so sensor-noise removal is a guardrail rather than
  the main still-SR blocker on that scene.
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
- Current evidence points to the rendered-context model/feature contract as the
  premium still-SR blocker, rather than target coverage or a broken training
  loop.
- The first raw-CFA path is plumbing/evidence, not promotion. It must beat the
  RGB ablation and then pass full 50 MP / 100 MP still/editor gates before it
  changes product readiness.
- Added X2D diversity improves same-camera-class generalization, but the
  original X2D scene remains a hard outlier. That points to target/loss or
  scene-specialist work before premium still-SR can be promoted.
- The specialist results support a camera/source-aware router or separate
  specialist checkpoints. Every current route now has a first full-frame
  check and rendered proxy review, and X2D has editor-openability,
  source-camera metadata proof, and rawpy latitude evidence. X2D remains weak,
  and the routed suite still lacks a passing full raw-editor latitude gate.
- The router plan is a contract for future routing, not a production registry.
  X2D, Z8, and Mission 1 now have candidate specialists, but all still lack
  production full-frame/editor-latitude gates.

Next production work:

1. Replace the source-HF oracle with a production-safe learned/modelled
   texture path. Calibrated random-HF addback does not close the X2D +2 EV
   gap, so the next pass should train against the structured HF residual target
   dataset or change the still-SR target/loss. The current LF tone error is
   much smaller than the HF error, and HF correlation is only about 0.406
   median, so the next pass should not chase generic tone mapping or simple HF
   gain first.
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
- The refreshed 2026-06-30 xlarge pair receipt covers 1,024 real-fixture tiles
  and adds a residual/detail budget:
  `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/index.html`.
  The fitted normalized weights are `[0.25000165, 0.25000245, 0.25000036,
  0.24999554]`, fit RMSE is 0.30044 on the 14-bit training scale, and the
  repeat-to-target residual is 0.99999x fine-band share. This means the modeled
  video-SR gap is same-cell Bayer fine-detail reconstruction, not broad coarse
  deblur.
- The raw-video PSF/SR readiness audit separates the approved 4K/8K baselines
  from the unfinished native PSF replacement claim:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630/index.html`.
- The Mission 1 native high/low candidate inventory indexes near-time
  8192 x 6144 and 4096 x 3072 capture candidates for the measured PSF pass:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630/index.html`.
- The Mission 1 native PSF measurement plan selects the best decoded pairs and
  defines scene vetting, alignment, edge/texture mining, native kernel fitting,
  and promotion gates:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630/index.html`.
- The first Mission 1 native PSF measurement run executes that plan:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/index.html`.
  It accepted 2 of 3 selected near-time pairs and found strong tile support
  (1,409 sharp-edge tiles and 1,381 texture-field tiles), but rejected the
  combined kernel as unstable.
- The raw-video PSF gap closure plan turns that failed native measurement into
  the concrete closure list:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gap_plan_20260630/index.html`.
  It preserves the approved 4K/8K baselines, records the accepted-pair and
  kernel-stability blockers, and requires controlled same-scene pairs before a
  PSF-conditioned model can be promoted.
- The raw-video SR/detail candidate scoreboard indexes 89 historical
  Mission/Z8 decision receipts and finds zero current-scale promotion rows
  under the Mission42 plus Z8 all24 coverage rule:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_sr_candidate_scoreboard_20260630/index.html`.

Boundaries:

- The current SR path is not a formal PSF-calibrated model. It is an approved
  empirical candidate with dashboards and receipts.
- The pair-derived PSF receipt validates the current modeled resize target and
  detail budget. It does not measure native camera sensor/DMA/display PSF
  because the low side of the pair is generated from the high-resolution raw
  extraction.
- The native high/low inventory, plan, and first measurement run are still not
  enough for production. The current near-time pairs do not provide three
  accepted same-scene pairs or a stable measured kernel.
- Replacing it requires beating the current baseline on full-frame Mission and
  Z8 gates, not just lowering tile loss or improving a small crop.

Next production work:

1. Follow the raw-video PSF gap closure plan: capture or locate controlled
   same-scene Mission 1 high/low pairs, then re-run the native PSF measurement
   until at least three pairs pass scene vetting and the fitted kernel is
   stable.
2. Train with CFA-aware high-res RGB/downsample targets, PSF-conditioned
   losses, and explicit same-cell fine-detail reconstruction metrics.
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
