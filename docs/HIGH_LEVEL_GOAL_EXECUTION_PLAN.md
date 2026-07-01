# High-Level Goal Execution Plan

Last refreshed: 2026-07-01

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

## Execution Split

The high-level goal has two different kinds of remaining work. Keep them
separate so hardware/sample acquisition blockers do not stall local model and
productization work.

Can advance locally without new captures:

- Premium still-SR: keep the expanded raw-CFA target fixed and test stronger
  candidate-only raw-domain/detail models or losses against the same 50 MP /
  100 MP still/editor gates. The current evidence says the blocker is X2D
  raw-detail recovery strength and missing full-image/structured context, not
  simple camera-domain filtering. The raw target duplicate audit shows the
  nominal 351-row target collapses to 117 unique scene/crop raw rows across EV
  variants, so the next local model pass should deduplicate raw supervision
  and use rendered EV rows only for review/tone gates. The architecture should
  move away from another small local U-Net and toward a CFA-aware restoration
  teacher with camera/noise/PSF conditioning, progressive patch sizing, and
  spatial plus Fourier losses before distilling to a smaller student.
- Raw-video PSF/SR: use the current modeled-resize/detail-budget receipts to
  build PSF-conditioned ablations, but keep them non-production until controlled
  native high/low pairs produce a stable kernel. Any replacement still has to
  beat the locked 4K cleanup and 8K SR baselines on Mission42 and Z8 all24.
- README/release hygiene: keep the four pillars, lock ledger, scorecard,
  release manifest, artifact guards, and continuous review media aligned with
  the evidence that actually exists.

Requires new hardware or new samples before it can close:

- Mission 1 raw-video MVP production closure: real sensor/DMA or camera
  ring-buffer source, SD writer, rear-display/UI handoff, zero drops, valid
  `.gvid`, and timing receipts from `target_role=camera`.
- Mission 1 and iPhone nonzero noise addback: same-camera, same-ISO darkframe
  stacks with source hashes and validated `gpr.camera_noise_calibration.v1`
  sidecars.
- Native PSF promotion: controlled same-scene Mission 1 high/low Bayer pair
  stacks with source hashes, decoded Bayer hashes, fixed settings, and negative
  controls.

The next local work should therefore default to premium still-SR and
PSF-conditioned ablations unless new Mission 1 hardware receipts or missing
fixtures have arrived.

## Current Burn-Down Order

### 1. Raw Stills Compatibility And Noise Policy

Immediate work:

- Keep all normal unpacked 2x2 Bayer still phases guarded. The legacy stills
  SDK/CLI path now exposes RGGB, GBRG, GRBG, and BGGR at 12/14/16 bits with
  matrix and capability coverage.
- Keep real RGGB/GBRG/GRBG/BGGR still fixture coverage linked to the broad
  GoPro/Mission and old-photo phase scans so synthetic conformance cells stay
  backed by real metadata and black-level examples.
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
- Use the current raw-video PSF gap plan as the closure checklist for this
  pillar:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gap_plan_20260630/index.html`.
  It records the current accepted-pair count, tile support, kernel-stability
  result, required hash-strict controlled-pair capture, and promotion receipts.
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

1. Apply the noise-calibration sidecar flow to real Mission 1 and iPhone
   darkframe/frame-stack artifacts where available. The current lowest-lift
   Mission candidate is `GoPro|MISSION 1|ISO232|RGGB`, which already has two
   darkframe-like frames and needs two more matching frames for a production
   stack candidate. The iPhone ISO1250 RGGB candidate set already has enough
   dark-like frames, but it still needs no-scene-signal provenance before it can
   be promoted. The current full-manifest pass raises that iPhone ISO1250 RGGB
   candidate set to 27 dark-like frames. The current stills fixture gap plan is
   `/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/index.html`;
   the handoff-ready raw-stills capture request is
   `/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_noise_fullmanifest_20260701/index.html`.
2. Continue premium still-SR from the current raw-CFA residual blocker, not
   older rendered-HF targets. The latest candidate-only raw-domain trainer is
   mildly positive on held-out Z8 at about 0.50 percent median raw-residual MAE
   recovery, but the hard X2D holdout remains far below promotion: the best
   diagnostic early-selected U-Net reaches about 0.13 percent median recovery,
   the best known X2D row is about 0.16 percent, same-scene candidate-signal
   regresses by about -3.67 percent, and a per-CFA-plane frequency filter
   regresses by about -4.29 percent. The raw target duplicate audit also shows
   that the 351 rendered EV rows are only 117 unique raw scene/crop rows. The
   next model work should therefore first deduplicate raw-domain rows, then
   train a literature-aligned CFA-aware teacher, such as a NAFNet/RCAB or
   Restormer-like restoration model, with camera/noise/PSF conditioning,
   progressive patch sizes, and spatial plus Fourier losses. Distill to a
   smaller candidate-only runtime student only after the teacher clears the
   50 MP / 100 MP still/editor-latitude gates.
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
   That gated raw/CFA architecture has now been scaled to a complete raw-CFA
   expanded target under
   `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/`.
   It beats matched RGB ablations on both held-out Z8 and held-out X2D, with
   the best broad scene holdout at 2.92 percent median MAE recovery. A matched
   dilated raw-CFA gated variant improves the weaker Z8 holdout from 1.04 to
   about 1.30 percent, but trails the X2D gated baseline at 2.86 versus 2.92
   percent and leaves severe negative worst rows. A calibrated X2D ISO 200
   noise-clean sweep now shows gain 16 changes about 11.93 percent of pixels
   but removes only about 0.24 percent median residual energy. The next pass
   should therefore move beyond the current rendered-residual target to a
   stronger raw-domain signal/detail target and model, with calibrated
   noise-cleaning kept as a guardrail rather than the main fix.
4. Replace the still-SR skeleton with a production candidate receipt only after
   the routed 50 MP and 100 MP candidates pass those editor and worst-row gates.
5. Follow the raw-video PSF gap plan:
   `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gap_plan_20260630/index.html`.
   The current native measurement has enough tile support but only 2 accepted
   pairs and an unstable fitted kernel. The next PSF commit should add
   controlled same-scene Mission 1 high/low pairs with source hashes, decoded
   Bayer hashes, fixed settings, and negative controls, or document that the
   available local corpus cannot supply them before training the
   PSF-conditioned SR experiment.
6. Gate a PSF-conditioned 4K/8K video SR candidate only against the locked
   Mission42 and Z8 all24 baselines. If it does not beat the current 4K cleanup
   and 8K SR paths, keep the approved baselines and record whether the blocker
   is native PSF estimation, loss/objective design, model capacity, codec/detail
   aliasing, or missing controlled-pair evidence.
7. Re-run the README/media/release guards and open a focused PR for each small
   reviewable slice.
