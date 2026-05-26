# 2026-05-25: FUSED multi-level visual-quality regression — what we got wrong

**Read this before reading SHIP_DECISION.md, methodology_cnn_aware_quant.md,
or any of the cranked-quant docs from the PR #16..#28 window.** Those
documents were written against the broken codec path and overstate the
file-size savings while understating the visual cost.

## Update 2026-05-25 (late evening) — 2-level wavelet restored

The original 3-level cascade regression is real and intrinsic (Nyquist
aliasing through L3 at small scales). The fix landed not as "make 3-level
match single-level" but as **restore the 2-level wavelet path** (`fa9f328`
production code, was removed in `5045828`). 2-level avoids the deepest
cascade.

| mode | Z8 50MP file | Z8 50MP bayer-PSNR | Δ vs SL |
|---|---:|---:|---:|
| single-level q=3 | 23.9 MB | 46.73 | — |
| **ML-2 q=3** | **5.6 MB** | **43.28** | **-3.45** |
| ML-3 q=3 (still broken) | 3.0 MB | 40.55 | -6.18 |

ML-2 q=11 actually improves bayer-PSNR by +0.81 dB on Z8 (quantization
acts as a denoiser) at 4.4 MB. See commits `5e1e7ae`, `56a96ae` on
`fix/multilevel-cascade-regression` for the full restoration.

**Shipping plan (revised):**
- Stills: single-level FUSED q=3 (default)
- Video: ML-2 (`FUSED_WAVELET_LEVELS=2`)
- ML-3: not shipping; cascade regression remains

The "10 dB regression" applies specifically to ML-3 vs SL. ML-2 vs SL
is -3 to -4 dB, and ML-2 vs ML-3 is +2 to +5 dB (always better).

## TL;DR

- **FUSED multi-level wavelet has a ~10 dB PSNR regression vs single-level
  FUSED on the same input.** It produces visible cross-hatch artifacts on
  natural images, primarily on the green channels of the demosaiced output.
- The bug has been present since at least PR #7 (b53ce2b). It is not in
  the per-band quantization (set every band's quant to 1 → still 10 dB
  worse). The cascade math (forward `prescale=2` at every level, inverse
  `descale=2` at every level) appears self-consistent on DC and gradient
  signals; the divergence shows up on sinusoidal / oscillating content,
  most pronounced at mid frequencies (corresponds to the L2 wavelet band).
- The cranked-quant work in PR #20..#28 (q=11 preset, q=12 candidate,
  AccelIR-style per-subband calibration) was measured ON the broken
  multi-level path. The reported 22% file-size savings ratio dropped to
  16% when re-measured on single-level. The 69% savings of multi-level
  baseline over single-level was paid for in 10 dB of visual quality.
- The bayer-PSNR-only methodology hid this for the entire PR #7..#31
  cycle. PSNR-on-bayer was 40+ dB while visual quality was visibly
  degraded. New `tools/test/metrics.py` adds Y-PSNR / MS-SSIM / LPIPS /
  ΔE2000 on demosaiced RGB to prevent the next instance of this.

## Corrected numbers (single-level, full-res FUSED q=3)

File sizes on 4 Z8 50MP test DNGs:

| config | avg KB | savings vs single q=3 |
|---|---:|---:|
| baseline q=3 single-level | 27,867 | — |
| baseline q=3 multi-level (BROKEN) | 8,548 | +69.3% — but 10 dB worse PSNR |
| HH cranked ×2 | 26,395 | +5.3% |
| HH cranked ×4 | 25,426 | +8.8% |
| LH/HL/HH cranked ×4 | 23,309 | +16.4% |
| LH/HL/HH cranked ×8 | 20,555 | +26.2% |

Visual quality metric (vs sips REF on the same gpr_tools-written DNG path):

| Z8 image | mode | Y-PSNR | MS-SSIM | LPIPS | ΔE2000 |
|---|---|---:|---:|---:|---:|
| Z8Z_0001 | q=3 single | 33.53 dB | 0.983 | 0.243 | 1.27 |
| Z8Z_0001 | q=3 multi | 23.84 dB | 0.803 | 0.384 | 3.74 |
| Z8Z_0067 | q=3 single | 46.84 dB | 0.994 | 0.038 | 0.66 |
| Z8Z_0067 | q=3 multi | 44.38 dB | 0.982 | 0.270 | 1.08 |
| Z8Z_5323 | q=3 single | 32.98 dB | 0.938 | 0.115 | 1.57 |
| Z8Z_5323 | q=3 multi | 30.34 dB | 0.841 | 0.204 | 2.26 |
| Z8Z_6693 | q=3 single | 29.53 dB | 0.890 | 0.177 | 2.32 |
| Z8Z_6693 | q=3 multi | 28.01 dB | 0.778 | 0.209 | 2.94 |

Multi-level loses on every metric on every image.

## What the cranked-quant docs got wrong

`docs/SHIP_DECISION.md` Option B's "22% file size savings" was measured
on multi-level. Re-measured on single-level: that same crank pattern
(`L1+L2 cranked ×2`) saves about 8-16%, not 22%. The CNN retraining
(BayInBayOut_1x_AAon_w16_ANE_L1L2x4.pt) was trained on multi-level
outputs and is not directly applicable to single-level codec outputs.

`docs/methodology_cnn_aware_quant.md` describes per-subband calibration
with PSNR-on-bayer as the headline metric. The methodology is sound;
the specific quant-table calibrations need to be re-measured with
visual metrics on the corrected codec path.

`docs/quant_calibration_findings.md` per-subband sweep numbers all need
re-validation on single-level.

## Implications for shipping

- **q=11 / q=12 presets** as specified target multi-level slot mapping
  (slots 7/8/9 in the quality table). They're a no-op in single-level
  mode (where slots 1/2/3 are the active highpass). Until multi-level
  is fixed OR the presets are re-mapped to single-level slots, they
  shouldn't ship.
- **q=3 default**: ship single-level. Files are 3.3× bigger than the
  broken-multi-level "baseline" but the quality is real and recoverable
  later when multi-level is fixed.
- **The cranked-quant CNN checkpoints** (HH1×4, L1L2×4) are calibrated
  to multi-level artifact distribution. Don't ship them with single-level
  output — they may add artifacts rather than remove them.
- **Pi 5 / camera storage budget**: the 24 fps × 50 MP × microSD plan
  assumed multi-level compression. Single-level files are 3.3× larger;
  the budget needs to be rerun against UHS-II V90 or similar. Multi-level
  fix is on the critical path for the video deployment.

## What changed in code

- `tools/test/metrics.py` — new module, Y-PSNR/MS-SSIM/LPIPS/ΔE2000.
- `source/lib/vc5_decoder/fused_decode.c` — `FUSED_INVERSE_DESCALE` env
  hook to allow experimental descale sweeps without rebuild. No-op at
  defaults.

## Root-cause finding (post-investigation)

The multi-level regression has TWO interacting causes:

**1. Nyquist aliasing through the cascade.** Reproducible with horizontal
stripes:

```
period   8 px: SL=44.4 dB  ML=21.2 dB  (-23 dB)
period  16 px: SL=32.5 dB  ML=20.8 dB  (-12 dB)
period  32 px: SL=35.6 dB  ML=29.8 dB  (-6 dB)
period  64 px: SL=38.7 dB  ML=30.1 dB  (-9 dB)
period 256 px: SL=45.1 dB  ML=36.7 dB  (-8 dB)
```

Any frequency content that lands near L2 or L3 Nyquist degrades.

**2. Double-rounding in `horizontal_filter`.** The FUSED `horizontal_filter`
prescale pattern differs from legacy `FilterHorizontalRow`:

- legacy: `lowpass[i] = (input[2i] + input[2i+1] + rounding) >> prescale`  (single divide)
- FUSED:  `lowpass[i] = PS(input[2i]) + PS(input[2i+1])`  (two divides)

For prescale=2: legacy adds 0.75 ADU bias to `(e+o)`; FUSED adds 1.5 ADU.
The bias compounds across the 3-level cascade. The NEON SIMD path also
uses the suboptimal pattern. Single-level only invokes one wavelet level
so the bias is small (1.5 ADU vs source magnitude in thousands).

**Fix approach** (not done in this run — substantial change):
- Rewrite `horizontal_filter` to use `sum-then-prescale` (matches legacy
  `FilterHorizontalRow`).
- Update both scalar and NEON paths in fused_encode.c.
- Verify single-level PSNR doesn't regress.
- Potentially also pre-filter LL1 with anti-aliasing before L2 forward to
  address the Nyquist issue separately.

## What's pending

- Task #172: fix the multi-level inverse cascade bug (root cause now
  identified; fix pending separate PR).
- Task #170: integrate visual metrics into test_capabilities.py CI.
- Walk back the cranked-quant claims in SHIP_DECISION.md and
  methodology_cnn_aware_quant.md (this file is the holding pen).

## Memory entries (local — do not commit)

- `project_multilevel_regression.md`
- `feedback_visual_metric_stack.md`
- `feedback_self_check_outputs.md`

## Visual rig

`/Volumes/OWC_8TB/gpr_artifacts/visual_compare_20260525_metrics/index.html`
shows the side-by-side with metric tables. Single-level vs multi-level
vs cranked variants on 4 source DNGs.

## Critical update — CNN works great at single-level

Tested baseline BIBO_1x CNN against single-level codec output:

| image | codec-only bayer-PSNR | +CNN bayer-PSNR | CNN gain |
|---|---:|---:|---:|
| Z8Z_0001 | 46.75 | 61.86 | +15.11 dB |
| Z8Z_0067 | 61.43 | 65.64 | +4.21 dB |
| Z8Z_5323 | 43.27 | 60.54 | +17.27 dB |
| Z8Z_6693 | 39.80 | 57.29 | +17.49 dB |

For comparison, the same CNN on multi-level output gave only +0.3 to
+4.6 dB. **The CNN works fine — multi-level was killing it.**

Single-level + CNN visual metrics (vs REF):

| image | Y-PSNR | MS-SSIM | LPIPS | ΔE2000 |
|---|---:|---:|---:|---:|
| Z8Z_0001 | 47.87 | 0.9975 | 0.0147 | 0.57 |
| Z8Z_0067 | 50.54 | 0.9970 | 0.0319 | 0.51 |
| Z8Z_5323 | 45.98 | 0.9973 | 0.0114 | 0.89 |
| Z8Z_6693 | 42.82 | 0.9968 | 0.0140 | 1.06 |

Perceptually identical to REF. **This is the "amazing q=3 CNN" output.**

Cranked variants + CNN also work well:

| crank | Y-PSNR (vs REF) | LPIPS | file-size savings |
|---|---:|---:|---:|
| no crank | 47-50 | 0.01-0.03 | 0 |
| HH×4 + CNN | 45-49 | 0.02-0.09 | 8.8% |
| LH/HL/HH×4 + CNN | 42-49 | 0.02-0.16 | 16.4% |

Cranked-quant savings hold at single-level. The methodology is sound.

Final visual rig: `/Volumes/OWC_8TB/gpr_artifacts/visual_compare_20260525_final/index.html`

