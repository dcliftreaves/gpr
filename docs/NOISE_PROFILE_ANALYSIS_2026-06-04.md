# Z8 Raw Noise Profile Analysis

Date: 2026-06-04

This pass re-checks the noise/signal separation on the ISO-sensitive Z8 gate
blockers using raw-domain camera metadata instead of rendered Lab-L heuristics.

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/noise_profile_analysis_20260604/noise_profile_analysis.html`

JSON:

`/Volumes/OWC_8TB/gpr_work/artifacts/noise_profile_analysis_20260604/noise_profile_analysis.json`

## Inputs

The two inspected frames are from `tests/quality_gates/test_set.json`:

| Image | ISO | DNG path |
| --- | ---: | --- |
| `Z8Z_5323` | 5000 | `/Volumes/OWC_8TB/gpr_work/artifacts/visual_compare_20260525/source_dngs/Z8Z_5323.dng` |
| `Z8Z_6693` | 9000 | `/Volumes/OWC_8TB/gpr_work/artifacts/visual_compare_20260525/source_dngs/Z8Z_6693.dng` |

The DNGs carry `NoiseProfile`, `BlackLevel`, and `WhiteLevel` tags. The
measured black/white range is 1008 to 15892, so one normalized DNG unit maps to
14884 raw counts.

## Result

The DNG profile predicts an ISO-dependent raw noise floor that is much larger
than the rendered-domain `noise_signal_classifier` proxy implied:

| Image | ISO | Crop | sigma rms counts | flat HF / sigma | removed / sigma | lag1 mean x/y | lag1 max abs x/y | edge energy ratio |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_5323` | 5000 | `A_detail` | 110.4 | 0.94 | 0.81 | -0.06 / -0.05 | 0.08 / 0.06 | 0.93 |
| `Z8Z_5323` | 5000 | `B_center` | 100.9 | 0.95 | 0.77 | -0.09 / -0.08 | 0.09 / 0.10 | 1.12 |
| `Z8Z_5323` | 5000 | `C_lowerleft` | 59.2 | 0.91 | 0.73 | -0.07 / -0.06 | 0.08 / 0.07 | 1.19 |
| `Z8Z_6693` | 9000 | `A_detail` | 138.7 | 0.98 | 0.57 | -0.05 / -0.13 | 0.05 / 0.16 | 1.05 |
| `Z8Z_6693` | 9000 | `B_center` | 113.4 | 0.96 | 0.79 | -0.08 / -0.09 | 0.09 / 0.11 | 1.06 |
| `Z8Z_6693` | 9000 | `C_lowerleft` | 160.0 | 0.99 | 0.78 | -0.08 / -0.09 | 0.10 / 0.12 | 1.13 |

Interpretation:

- The validation metrics are computed per CFA plane, then aggregated. This avoids
  treating Bayer color alternation as high-frequency detail.
- The conservative raw denoise removes less than one predicted sigma of energy.
- The removed residual is close to white but mildly anti-correlated, with mean
  lag-1 correlation around -0.05 to -0.13 and worst per-plane absolute lag
  around 0.16.
- Edge removal is not strongly concentrated on structure: edge/non-edge energy
  ratio is roughly 0.93-1.19.
- Flat-region same-plane high-frequency energy is 0.91-0.99x the predicted
  camera-noise floor. In flat areas, the finest raw-domain HF is therefore
  largely consistent with stochastic sensor noise. The guardrail is that this
  only applies to same-plane flat regions; structured regions still need
  edge/cross-scale protection.

## Relation To The Prior Classifier

`tests/quality_gates/runs/dashboard/noise_signal_classifier.html` classified
rendered Lab-L finest-wavelet energy using structure support. That guard was
useful for proving that full finest-band removal destroys signal, but it is not
an ISO-aware camera-noise estimator.

For the two high-ISO blockers, the prior JSON reported tiny rendered-domain
predicted noise RMS values:

| Image | ISO | prior predicted noise rms | prior removed energy frac |
| --- | ---: | ---: | ---: |
| `Z8Z_5323` | 5000 | 0.027965 | 0.000292 |
| `Z8Z_6693` | 9000 | 0.044798 | 0.000385 |

That explains the mismatch in visual review: it was mostly preserving the
finest Lab-L band, not analytically estimating the camera noise floor from ISO
and raw signal level.

## Darkframes

The consolidated 8TB tree has `/Volumes/OWC_8TB/gpr_work/X2D_DarkFrames`, but
those files are Hasselblad X2D `.fff` frames. They are useful for building a
camera-agnostic darkframe calibration path, but they do not directly calibrate
Nikon Z8 frames. No obvious Nikon/Z8 darkframe directory or darkframe filenames
were found in the consolidated tree.

## Production Direction

The next CNN pass should not train against noisy REF as the direct target.
Instead:

1. Use the DNG `NoiseProfile` and ISO as the raw-domain noise model.
2. Build a clean target by removing only same-plane sub-sigma residual energy
   in flat/support-limited regions that passes the raw-domain checks above.
3. Train or fine-tune the detail model against the cleaned signal target.
4. Add noise back for evaluation using the exact REF residual first, then
   replace it with synthetic ISO-aware Bayer/wavelet noise.
5. Make the candidate explicitly ISO-aware, either by adding ISO/noise-profile
   conditioning channels or by feeding a per-pixel sigma map.

Stop criteria for this subproblem:

- A cleaned-signal target exists for every gate crop/image used for training.
- Removed residual RMS is at or below the DNG-predicted sigma, per-plane lag-1
  correlation remains low, and edge energy ratio stays close to one.
- Candidate evaluation reports both clean-target scores and exact-noise-addback
  scores.
- The dashboard shows raw, cleaned, removed residual, sigma map, candidate,
  exact-noise-addback, and synthetic-noise-addback at 100% crop scale.
