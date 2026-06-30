# Product Pillar Scorecard

The product pillar scorecard is the top-level audit view for the four large
efforts currently driving the repo:

1. best RAW stills for 50 MP / 100 MP cameras,
2. GoPro / Mission 1 RAW video MVP,
3. premium spend-time-for-quality still/SR,
4. PSF-aware RAW video cleanup and reconstruction.

It is intentionally stricter than the README. The README can sell the project
clearly; this scorecard says what is proven, what is only proxy-proven, and
what still blocks a production claim.

Build it with:

```bash
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp \
python3 tools/build_product_pillar_scorecard.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_capture_requirements_20260630
```

Current generated dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_capture_requirements_20260630/index.html`

Companion production burn-down dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/product_burndown_20260630/index.html`

The burn-down is the action view: it separates hardware integration, sample
acquisition, and model-promotion work. That distinction matters because the one
Mission 1 camera-role closure, the real fixture/darkframe/PSF sample gaps, and
the premium/PSF model-promotion gaps are different kinds of open evidence, not
regressions of the locked still, 4K cleanup, 8K SR, or Pi stand-in paths.
The committed sample/receipt contract is
[`PRODUCTION_CAPTURE_REQUIREMENTS.md`](PRODUCTION_CAPTURE_REQUIREMENTS.md) and
[`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json).

## Score Semantics

The percentages are production-readiness burn-down estimates. They are not
image-quality metrics and they are not regression signals for locked artifacts.
A locked path regresses only when its own committed gate, receipt, hash, or CI
guard fails. This matters because the approved 4K cleanup, offline 8K SR,
production STILL tiers, and Pi-stand-in raw-video/preview receipts can remain
locked while the overall readiness score stays below 100% because hardware,
fixture, noise-sidecar, PSF, or promotion evidence is still missing.

The denominator is the full four-pillar production suite: raw stills, raw video
MVP, premium still/SR, and PSF-aware video/SR. Use
[`PRODUCT_LOCK_LEDGER.md`](PRODUCT_LOCK_LEDGER.md) to decide whether an
approved artifact regressed; use this scorecard and the burn-down dashboard to
decide what production evidence is still missing.

The generated scorecard now carries the exact lock-ledger path names and open
production gate names for each pillar. `tools/test/check_product_lock_ledger.py`
keeps the Markdown ledger, generated scorecard contract, and CI view from
drifting apart.

Current interpretation:

| pillar | current score | production reading |
|---|---:|---|
| Best RAW stills | 90% | Strong for the current tested Bayer surface, now including a real X2D 100MP visual roundtrip audit, real RGGB plus GoPro/Mission GBRG fixture coverage, and explicit camera-noise coverage; real GRBG/BGGR fixtures and Mission/iPhone darkframe sidecars are still open. |
| GoPro RAW video MVP | 80% | Pi 5 stand-in, handoff package, and GoPro intake audit are strong; real Mission 1 sensor/DMA/storage/display receipts are still required. |
| Premium still/SR | 60% | The expanded 13-scene / 351-row target set now has complete raw-CFA features, the raw-CFA gated model beats matched RGB ablations on expanded Z8/X2D holdouts, a matched dilated raw-CFA variant has been tested, calibrated noise-cleaning is bounded, and true source-minus-candidate same-color raw residual targets plus raw-domain trainers now exist; Z8 is mildly positive, but the hard X2D holdout is only barely positive after a wider/block17 pass and remains far from production-grade. |
| PSF-aware RAW video improvement | 44% | Current 4K cleanup and 8K SR baselines are useful, including continuous 8K no-CNN versus CNN ProRes review media for a whole-scene A/B; near-time native Mission 1 high/low candidates are indexed, the first native PSF measurement has executed, and a hash-strict capture request now spells out the controlled-pair capture and model-gate path. Formal native PSF/blur-aware replacement remains open because the available near-time pairs produce an unstable kernel. |

The current real X2D 100MP still audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html`.
It records a 11,664 x 8,750 DNG to GPR to DNG roundtrip, 100 percent crop
panels, and 49.21 dB full-image raw Bayer PSNR.

The current real Bayer phase discovery lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html`.
It scans canonical plus broader local Mission 1/Z8/X2D/iPhone DNG pools and
finds 74 normal 2x2 Bayer DNGs: 70 RGGB and 4 Mission 1 GBRG. GRBG and BGGR
remain covered by committed synthetic conformance until real camera fixtures are
added.

The current camera-noise coverage audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/index.html`.
It records six validated darkframe sidecars: X2D at ISO 64, 200, 800, 3200,
and 12800, plus Z8 at ISO 500. Mission 1 and iPhone have real fixtures but no
production-ready darkframe sidecars yet, so nonzero noise removal/addback is not
promoted for those cameras.

The current Mission/iPhone darkframe candidate audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_20260630/index.html`.
It finds 9 darkframe-like Mission 1 frames, but they are split across 8
camera/ISO/CFA groups and no group has the four-frame stack required for a
production sidecar. The iPhone row is the known Linear Raw negative fixture,
not a CFA darkframe source.

The broader real-photo sample lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_realphotos_sample_20260630/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_realphotos_sample_20260630/index.html`.
It adds real-photo iPhone RGGB evidence and finds one iPhone dark-looking
candidate stack, but the boosted contact sheet shows scene content in part of
that group. The audit therefore keeps `production_sidecar_ready=false`; Mission
1/iPhone production noise sidecars remain open.

The targeted GoPro/Mission DNG/GPR fixture scan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/index.html`.
It parses 3,000 local DNG/GPR files as normal Bayer: 2,892 GBRG and 108 RGGB.
It still finds no real GRBG or BGGR fixture, which keeps that work as sample
acquisition rather than parser work. The targeted Mission DNG darkframe scan at
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_targeted_dng_20260630/index.html`
finds 9 dark-like Mission frames, but no same-ISO four-frame production stack.

The current stills fixture gap plan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_20260630/index.html`.
It consolidates the phase/noise receipts into the concrete capture checklist:
real GRBG and BGGR fixtures, Mission 1 and iPhone darkframe stacks, and two
additional matching frames for the current Mission 1 ISO232 RGGB darkframe-like
group.

The raw-stills capture request lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_20260630/index.html`.
It converts that closure list into handoff-ready sample requests, validation
commands, and promotion criteria.
The same raw-stills blockers are pinned in the committed production capture
requirements as `real_grbg_fixture`, `real_bggr_fixture`,
`mission1_darkframe_stack`, and `iphone_cfa_darkframe_stack`.

The current GoPro Mission 1 intake audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260630/index.html`.
It verifies the portable firmware handoff bundle, required docs, 4096 x 3072
`.gvid` sample, quick-validation dry run, and stand-in encode/preview receipts.
It remains `camera_production_ready=false` until real Mission 1 sensor/DMA,
storage, and rear-display receipts replace the stand-in evidence.
That required camera-side proof is pinned as
`mission1_camera_role_receipts` in the committed production capture
requirements.

The current raw-video PSF/SR readiness audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630/index.html`.
It records that the current 4K cleanup and 8K SR baselines are approved for
their existing offline roles, but the PSF replacement is not production-ready
without native camera/display PSF evidence and a PSF-conditioned model gate.

The current standalone continuous-scene 8K no-CNN versus CNN review lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/`.
It contains separate 8280 x 5520 ProRes videos for the no-CNN Z8 baseline and
the retained 4K cleanup CNN Bayer plus approved 8K SR CNN path, with 24 matched
frames at 20 fps. This is the whole-video review evidence for the approved
baseline, not a dashboard, contact sheet, side-by-side review, or crop montage.

The current Mission 1 native high/low PSF candidate inventory lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630/index.html`.
It indexes near-time 8192 x 6144 and 4096 x 3072 Mission 1 captures as inputs
for the measured PSF pass. It is not a measured PSF receipt yet; alignment,
edge/texture mining, and a PSF-conditioned gate remain open.

The current Mission 1 native PSF measurement plan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630/index.html`.
It selects the best decoded native high/low pairs and defines the scene-vetting,
alignment, edge/texture mining, kernel-fitting, and promotion gates required
before the PSF-aware raw-video improvement pillar can replace the approved
4K/8K baselines.

The current Mission 1 native PSF measurement run lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/index.html`.
It executed the plan on the selected near-time pairs. Two of three pairs passed
scene/alignment vetting and provided 1,409 sharp-edge plus 1,381 texture-field
tiles, but the combined kernel was unstable and is not ready for model
conditioning.

The current Mission 1 native PSF corpus audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_corpus_audit_20260630/index.html`.
It hashes all four current near-time candidate pairs and records that zero are
strict controlled pairs: ISO/settings are not fixed enough, fixed
WB/lens/stabilization/sharpening metadata is absent, no negative controls are
marked, the existing measurement accepted only two pairs, and the kernel is
unstable. This proves the local corpus cannot close the PSF blocker without new
or newly located controlled captures.

The raw-video PSF controlled capture request lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_capture_request_20260630/index.html`.
It is the handoff for closing the measurement blocker: locked same-scene
8192 x 6144 and 4096 x 3072 Bayer pair stacks, source GPR/DNG hashes, decoded
little-endian uint16 Bayer hashes, fixed ISO/exposure/WB/lens/sharpening
settings, plus negative controls, with the exact validation commands required
to promote a stable native PSF kernel.
That controlled-pair blocker is pinned as `controlled_mission1_psf_pairs` in
the committed production capture requirements.

The current raw-video SR/detail candidate scoreboard lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_sr_candidate_scoreboard_20260630/index.html`.
It indexes 89 historical Mission/Z8 decision receipts and finds zero
current-scale promotion rows under the Mission42 plus Z8 all24 coverage rule.

The current premium still-SR experiment scoreboard lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260630/index.html`.
It ranks the available no-REF HF residual training receipts and currently
records zero promotable rows. The best single-scene row reaches 4.03 percent
held-out MAE recovery, while the best broad scene-held-out row remains 2.92
percent; both are diagnostic rather than production-ready.

The premium still-SR blocker audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_blocker_audit_20260630/index.html`.
It turns the current diagnostic failure into next-experiment requirements:
keep the expanded target coverage fixed, replace the weak rendered-context
learner with a stronger raw/CFA-aware or otherwise larger-context texture
model, keep calibrated noise/signal cleaning in the feature contract, and run a
full still/editor-latitude promotion gate.
The final still-SR promotion artifact set is pinned as
`premium_still_sr_promotion_receipts` in the committed production capture
requirements.

The premium still-SR target expansion plan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_expansion_plan_20260630/index.html`.
It selected six X2D 100MP and four Z8 50MP scenes with validated noise
sidecars, while explicitly deferring Mission 1 until same-camera noise sidecars
exist. The executed expanded build lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/expanded_target_build_receipt.json`;
the merged target contains 13 scenes and 351 rows. The expanded residual band
analysis lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/index.html`
and still shows the residual is fine-band dominated. The first expanded
training passes are intentionally not promoted: the weighted w96
render-context model was unstable, and the conservative w64 model landed near
zero held-out recovery.

The current raw-CFA smoke target and ablation receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_smoke_targets_20260630/2025_10_oct_austin_0626/hf_residual_targets.json`,
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_probe_model_20260630/train_receipt.json`,
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_ablation_rgb_model_20260630/train_receipt.json`.
The current raw-CFA gated architecture receipt lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_gated_probe_w48_1000_20260630/train_receipt.json`.
Together these prove the raw-CFA target/trainer path executes on a real X2D
scene: naive channel concatenation trails the matched RGB ablation, while the
explicit raw-CFA gated probe beats that ablation on +2 EV holdout recovery.
The expanded raw-CFA target rebuild lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/expanded_target_build_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json`.
It records complete raw-CFA feature coverage for all 351 rows / 13 scenes. The
expanded gated holdout receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_z8holdout_w48_1000_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_x2dholdout_w48_1000_20260630/train_receipt.json`.
They beat matched RGB ablations on held-out Z8 and X2D, but the best broad
holdout is still only about 2.92 percent median MAE recovery against the 15
percent promotion threshold.
The first matched dilated raw-CFA gated receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_z8holdout_matched_w48_1000_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_x2dholdout_matched_w48_1000_20260630/train_receipt.json`.
They improve the weak Z8 holdout from 1.04 to about 1.30 percent median MAE
recovery, but trail the X2D gated baseline at 2.86 versus 2.92 percent and
leave severe negative worst rows. That makes the simple dilated gate a useful
diagnostic, not the production path.
The current calibrated noise-clean sweep lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_clean_sweep_x2d_smoke_20260630/index.html`.
It shows the validated ISO 200 X2D noise floor is far below the current HF
residual: render gain 16 changes about 11.93 percent of pixels, but removes
only about 0.24 percent median residual energy. Noise cleaning remains a
guardrail, not the main explanation for the current still-SR blocker.

The current raw-CFA residual audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_audit_20260630/index.html`.
It compares rendered HF supervision against the editable raw target:
source raw minus candidate raw, high-passed without mixing CFA phases. Across
351 rows / 13 scenes, median absolute rendered-to-raw residual correlation is
0.691, median best-phase correlation is 0.922, and median raw-HF residual
magnitude is about 0.346x the rendered HF residual magnitude. That makes a
true same-color raw residual target the next training direction, with rendered
HF/editor-latitude kept as review and promotion metrics.

The current raw-CFA residual target build lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_20260630/index.html`.
It emits the trainable NPZ for that direction: `candidate_raw_cfa4`,
`candidate_raw_hf_cfa4`, `raw_hf_residual_cfa4`, `source_raw_hf_cfa4`, and
`render_hf_residual_y`. The NPZ covers the same 351 rows / 13 scenes, is
1.6 GB on the external artifact drive, and has SHA-256
`4c92f94e7505c09e2445df74e58d429460d31a199d61cf82b0299479a8c95ba4`.

The first raw-CFA residual model receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/train_receipt.json`.
They use candidate-only runtime inputs and four-plane raw residual output. The
Z8 scene holdout is mildly positive at about 0.50 percent median raw-residual
MAE recovery, but the X2D scene holdout remains negative at about -0.21
percent, so these receipts narrow the blocker rather than promoting a model.
The follow-up X2D receipts at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/train_receipt.json`,
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/train_receipt.json`,
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/train_receipt.json`
show that wider raw context barely clears zero at about 0.02 percent median
X2D recovery, while stored candidate-HF features and naive one-sigma noise
soft-thresholding do not fix the X2D blocker.

The generated JSON keeps `production_ready=false` until all four pillars have
direct evidence. This avoids promoting a proxy benchmark or diagnostic CNN as a
finished product result.
