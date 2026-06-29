# Big Efforts Status

Last refreshed: 2026-06-29

This document maps the repo to the four large product efforts. It is a
planning/status document, not a replacement for the release evidence manifest.
If a metric here conflicts with a committed receipt, the receipt wins.

## Summary

| effort | current status | production interpretation |
|---|---|---|
| Raw stills for 50 MP / 100 MP cameras | Strong, production-gated for the current tested Bayer surface, including all normal unpacked 2x2 Bayer phases in committed synthetic conformance. | Good enough to present as a working stills product path, with explicit open work on more real alternate-phase fixtures and camera-calibrated noise. |
| Raw video MVP for GoPro / Mission 1 | Strong prototype/Labs handoff, blocked on real camera closure. | Good enough for GoPro engineers to pick up and run; not done until real sensor/DMA/storage/display receipts exist. |
| Raw stills improvement / expensive SR | Partly done through 1x still CNN and reusable 4K/8K SR machinery. | Not done as a dedicated premium still-SR product gate. |
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
2. Build camera/ISO noise calibration from darkframes or frame stacks for Z8,
   X2D, Mission 1, and iPhone CFA where available.
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

Boundaries:

- The approved 8K SR path is a Mission/Z8 raw-video reconstruction path, not a
  dedicated general still-SR product for every 50 MP/100 MP camera.
- "Looks sharper" is not enough for a still-SR promotion. The output must keep
  raw-editor latitude, tone/color stability, worst-row visual quality, and
  camera-specific noise handling.

Next production work:

1. Define a still-SR gate separate from video SR: 50 MP and 100 MP fixtures,
   rendered dashboard, raw-domain metrics, and raw-editor latitude checks.
2. Train against high-quality still targets, with camera/ISO metadata and a
   noise policy that passes the raw-noise/signal audit.
3. Emit review TIFF/ProRes/contact sheets plus editable DNG/GPR receipts.

## 4. Raw Video Improvement / PSF-Aware Resize

Goal: understand and improve the point-spread/blur introduced when resizing or
reconstructing Bayer data, especially 12 MP or 4K capture feeding 4K cleanup
and 8K reconstruction.

Current evidence:

- Mission native12 4K cleanup is approved for offline/review scope.
- Candidate-aware 8K SR passes broad Mission42 and Z8 full-frame gates.
- Existing diagnostics already look at CFA raw error, rendered tone/green
  behavior, phase, edge alignment, gradient energy, and lower-right failures.

Boundaries:

- The current SR path is not a formal PSF-calibrated model. It is an approved
  empirical candidate with dashboards and receipts.
- Replacing it requires beating the current baseline on full-frame Mission and
  Z8 gates, not just lowering tile loss or improving a small crop.

Next production work:

1. Estimate the effective Bayer-domain PSF for the resize/capture path using
   real high-res-to-low-res pairs and sharp-edge/texture targets.
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
