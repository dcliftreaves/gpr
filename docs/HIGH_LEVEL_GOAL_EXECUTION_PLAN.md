# High-Level Goal Execution Plan

Last refreshed: 2026-06-30

This is the burndown plan for the four product pillars in the main README and
`BIG_EFFORTS_STATUS.md`. It is intentionally execution-focused: every item
should end in a committed test, receipt, dashboard, or explicit blocker.

## Definition Of Done

The project should not call the high-level goal complete until all four pillars
have production receipts:

1. Raw stills pass committed gates for the intended 50 MP / 100 MP camera
   surface, normal Bayer phases, bit depths, and camera-noise policy.
2. Raw video has a GoPro/Mission 1 MVP path with real Bayer `.gvid` capture,
   preview decode, recovery, timing, and storage receipts.
3. Offline premium still improvement has a dedicated still-SR gate and emits
   editable raw plus review artifacts that beat the current still baseline.
4. Raw video improvement has PSF/blur-aware 4K cleanup and 8K reconstruction
   evidence, not just crop-local CNN examples.

If a pillar cannot close, the blocker must be specific and evidenced: missing
camera access, CFA/metadata incompatibility, noise calibration uncertainty,
model capacity, PSF mismatch, throughput, memory, or storage.

## Current Burn-Down Order

### 1. Raw Stills Compatibility And Noise Policy

Immediate work:

- Keep all normal unpacked 2x2 Bayer still phases guarded. The legacy stills
  SDK/CLI path now exposes RGGB, GBRG, GRBG, and BGGR at 12/14/16 bits with
  matrix and capability coverage.
- Add real BGGR/GRBG camera fixtures as they become available so the current
  synthetic conformance cells are backed by real metadata and black-level
  examples.
- Use the committed camera-noise calibration sidecar builder for darkframe
  stacks. The schema is keyed by camera model, dimensions, ISO, bit depth,
  black level, white level, CFA phase, and darkframe/flatfield source hash.
  The lightweight guard is `tools/check_product_pillar_receipts.py` with
  schema `gpr.camera_noise_calibration.v1`; the builder is
  `tools/build_camera_noise_calibration.py`.
- Convert existing legacy darkframe-calibration artifacts with
  `tools/convert_darkframe_calibration_to_noise_sidecars.py` only when the
  selected source frames can be recovered and hashed. The first real converted
  receipts are under
  `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_sidecars_20260629/`.

Evidence required:

- `tools/test/test_still_matrix.sh` covers every normal unpacked Bayer phase.
- `tools/test/test_capabilities.py` emits capability rows for the promoted
  alternate phases.
- `docs/CAPABILITIES.md` is regenerated from an unfiltered run before a release
  claim is made.
- Noise removal/addback stays disabled as a production claim until calibrated
  darkframe/stack evidence proves the residual is noise rather than detail.
  The policy is documented in `docs/CAMERA_NOISE_CALIBRATION.md`.

### 2. Raw Video MVP For GoPro / Mission 1

Immediate work:

- Keep the current Pi 5 stand-in path clean: real decoded Bayer frames into
  `.gvid`, 1024 preview decode from the same stream, interrupted-tail recovery,
  and Lexar SILVER PLUS write-budget evidence.
- Avoid counting a wrapped original camera `.GPR` payload as a raw-video encode.
- Maintain GoPro employee handoff docs so a Mission 1 camera-role run can be
  executed without local project history.

Evidence required:

- A real Mission 1 sensor/DMA or camera-ring-buffer source receipt is required
  before this becomes firmware-ready.
- The accepted stand-in floor remains 20+ fps unless the product requirement is
  raised to strict 24 fps again.
- If strict 24 fps is required, optimization work should start from measured
  source, encode, write, preview, and buffer timings.

### 3. Premium Raw Still Improvement

Immediate work:

- Split still-SR from video-SR. It needs its own 50 MP / 100 MP still fixtures,
  rendered dashboard, raw-domain metrics, editor-latitude checks, and worst-row
  review. The lightweight guard is `gpr.premium_still_sr_gate.v1`; the
  CI-safe skeleton builder is `tools/build_premium_still_sr_gate_receipt.py`.
- Treat the current X2D editor-openability and rawpy latitude receipts as
  partial closure only: DNG/GPR open, export, source-camera metadata
  transplant, automated latitude evidence, and a source-HF oracle upper bound
  are proven. A calibrated no-REF random-HF sweep now shows simple stochastic
  noise addback is insufficient, and the first X2D structured HF residual
  target dataset has been materialized for supervised training. Production-safe
  structured high-frequency texture/detail restoration still needs to pass
  before promotion.
- Reuse the approved 4K/8K SR tooling only after the target is still-specific:
  high-quality still references, camera metadata, and noise policy included.
- Keep the output editable: DNG/GPR receipt first, review TIFF/ProRes/contact
  sheets second.

Evidence required:

- The still-SR candidate must beat the current STILL q0/q3/q8 baseline on the
  committed still gate, not just sharpen crops.
- 50 MP and 100 MP camera classes both need receipts before the claim is broad.
- Openability and metadata transplant are not enough for promotion. The routed
  still-SR suite still needs passing editor exposure-stress, rendered visual,
  and worst-row receipts.
- Any nonzero denoise target must pass the raw-noise/signal audit first.

### 4. PSF-Aware Raw Video Improvement

Immediate work:

- Estimate the Bayer-domain PSF introduced by camera downsample, resize, and
  reconstruction using high-res/low-res pairs, sharp edges, and texture fields.
  The lightweight guard is `gpr.bayer_resize_psf_receipt.v1`; the synthetic
  non-production contract builder is `tools/build_bayer_resize_psf_receipt.py`,
  and the real-pair modeled-resize builder is
  `tools/build_bayer_resize_psf_from_pairs.py`. The current xlarge pair receipt
  confirms the modeled target is a 2x2 same-color Bayer box and that the
  4K-to-8K residual is almost entirely same-cell fine detail:
  `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/`.
- Train or tune 4K cleanup and 8K SR with CFA-aware targets and PSF-conditioned
  losses, including explicit same-cell fine-detail reconstruction metrics.
- Keep dashboards honest: full-frame Mission and Z8 rows, rendered crops,
  raw-domain metrics, lower-right/worst-row inspection, and metadata receipts.

Evidence required:

- A replacement must beat the current approved 4K cleanup / 8K SR baseline on
  Mission42 and Z8 all24 gates.
- The result must emit `.gvid`, editable DNG/GPR, ProRes review, timing, memory,
  and artifact-hash receipts.
- If the PSF model does not improve the baseline, document whether the blocker
  is PSF estimation, target mismatch, loss objective, model capacity, or codec
  aliasing.
  The policy is documented in `docs/BAYER_RESIZE_PSF.md`.

## Near-Term Commit Targets

1. Add real BGGR/GRBG fixture coverage when a representative camera sample is
   available.
2. Apply the noise-calibration sidecar flow to real Mission 1 and iPhone
   darkframe/frame-stack artifacts where available.
3. Replace the X2D source-HF oracle with a production-safe structured
   texture/detail path. It should preserve the now-measured low-frequency tone
   path, restore high-frequency luminance energy under +2 EV, and prove it
   without using REF/source content at render time. Calibrated random-HF
   addback is now ruled out as a sufficient fix. The structured HF residual
   dataset is available under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/`,
   and the first no-REF smoke model is under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630/`.
   Its +2 EV holdout residual MAE reduction is only 4.03 percent, so the next
   pass added exposure/brightness-conditioned controls and a broader X2D grid
   target instead of promoting the model.
   The supporting band analysis is under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_20260630/`
   and shows the blocker is fine-band, not coarse tone. The first
   EV/brightness-aware residual controls are still weak; the best crop-holdout
   control improves only 0.54 percent. The broader 75-row grid target is under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_grid5_20260630/`;
   it confirms median HF correlation 0.407 and the center-grid holdout model
   recovers only 1.69 percent residual MAE. The next commit target should
   expand from one X2D scene to multiple X2D scenes/full-frame tiles with
   validated camera-noise sidecars before another larger model run. The first
   multi-scene version is now under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/`;
   it covers 81 rows across three X2D scenes and the first scene-held-out model
   recovers only 1.46 percent residual MAE. A follow-up multiscale model with
   validated ISO/noise sidecar scalar planes improves that same scene holdout
   to 2.56 percent:
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/`.
   That is useful progress, but still too weak for promotion. The planned
   expanded target has now been built under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/`;
   it merges 13 X2D/Z8 scenes and 351 rows. The expanded residual band analysis
   under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/`
   still shows about 0.981x fine-band residual share. Two expanded
   rendered-context training passes were intentionally not promoted: the
   weighted w96 model was unstable, and the conservative w64 model was stable
   but near zero held-out recovery. The next commit target should keep this
   expanded target fixed while changing the learner/feature contract, most
   likely to raw-domain/CFA-aware or otherwise larger-context texture
   restoration, before another promotion attempt. Raw-CFA target/trainer
   plumbing now exists and has one-scene X2D receipts under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_smoke_targets_20260630/`,
   but the first naive raw-CFA channel-concat probe improves +2 EV holdout by
   only 0.24 percent, versus 0.63 percent for the matched RGB ablation. The
   follow-up raw-CFA gated architecture reaches 0.79 percent on the same
   smoke holdout:
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_gated_probe_w48_1000_20260630/`.
   The next pass should therefore scale that gated raw/CFA architecture to the
   expanded target set instead of simply concatenating raw planes into the
   current CNN.
4. Replace the still-SR skeleton with a production candidate receipt only after
   the routed 50 MP and 100 MP candidates pass those editor and worst-row gates.
5. Extend the pair-derived PSF receipt path to native camera/display evidence
   and use it to drive the next PSF-conditioned SR experiment.
6. Re-run the README/media/release guards and open a focused PR for each small
   reviewable slice.
