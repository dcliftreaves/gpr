# High-Level Goal Execution Plan

Last refreshed: 2026-06-29

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
- Reuse the approved 4K/8K SR tooling only after the target is still-specific:
  high-quality still references, camera metadata, and noise policy included.
- Keep the output editable: DNG/GPR receipt first, review TIFF/ProRes/contact
  sheets second.

Evidence required:

- The still-SR candidate must beat the current STILL q0/q3/q8 baseline on the
  committed still gate, not just sharpen crops.
- 50 MP and 100 MP camera classes both need receipts before the claim is broad.
- Any nonzero denoise target must pass the raw-noise/signal audit first.

### 4. PSF-Aware Raw Video Improvement

Immediate work:

- Estimate the Bayer-domain PSF introduced by camera downsample, resize, and
  reconstruction using high-res/low-res pairs, sharp edges, and texture fields.
  The lightweight guard is `gpr.bayer_resize_psf_receipt.v1`; the synthetic
  non-production contract builder is `tools/build_bayer_resize_psf_receipt.py`.
- Train or tune 4K cleanup and 8K SR with CFA-aware targets and PSF-conditioned
  losses.
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
3. Replace the still-SR skeleton with a real candidate receipt from 50 MP and
   100 MP still fixtures.
4. Apply the PSF receipt path to real Mission/Z8 high-res-to-low-res pairs and
   use it to drive the next PSF-conditioned SR experiment.
5. Re-run the README/media/release guards and open a focused PR for each small
   reviewable slice.
