# Raw Clean REF Targets

Date: 2026-06-04

This pass turns the Z8 raw-noise analysis into auditable clean-signal training
targets. It works in linear raw CFA space, separates R/G1/G2/B before measuring
structure, and saves the exact removed residual as an addback sidecar.

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_20260604/raw_clean_ref_targets.html`

JSON:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_20260604/raw_clean_ref_targets.json`

## Method

For each selected gate crop:

1. Read DNG `NoiseProfile`, `BlackLevel`, `WhiteLevel`, `CFAPattern`,
   `CFAPlaneColor`, ISO, make, and model.
2. Build a per-pixel raw sigma map in raw counts.
3. Deinterleave the crop into same-CFA planes.
4. Create a candidate residual with conservative per-plane BayesShrink.
5. Keep only residual energy that is weakly supported by same-plane edge,
   cross-scale wavelet, and local-coherence structure.
6. Clip the final residual to `+/-1.0 * sigma` per pixel.
7. Save `raw`, `clean`, `exact_residual`, `sigma`, and `mask` arrays in NPZ
   sidecars. `clean + exact_residual` reconstructs `raw` within float precision.

This is intentionally not a perceptual denoiser. It is a training-target builder
that removes statistically defensible sensor noise while leaving structured
texture guarded.

## Metrics

| Image | ISO | Crop | sigma rms | residual/sigma | flat residual/sigma | kept candidate energy | lag max abs | edge energy ratio |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_5323` | 5000 | `A_detail` | 110.4 | 0.238 | 0.271 | 0.086 | 0.092 | 0.600 |
| `Z8Z_5323` | 5000 | `B_center` | 100.9 | 0.265 | 0.307 | 0.119 | 0.105 | 0.735 |
| `Z8Z_5323` | 5000 | `C_lowerleft` | 59.2 | 0.237 | 0.289 | 0.105 | 0.085 | 0.821 |
| `Z8Z_6693` | 9000 | `A_detail` | 138.7 | 0.224 | 0.276 | 0.157 | 0.152 | 0.839 |
| `Z8Z_6693` | 9000 | `B_center` | 113.4 | 0.232 | 0.271 | 0.088 | 0.105 | 0.712 |
| `Z8Z_6693` | 9000 | `C_lowerleft` | 160.0 | 0.243 | 0.287 | 0.098 | 0.107 | 0.795 |

Interpretation:

- The removed residual is intentionally sub-sigma: roughly 0.225-0.266x the
  DNG-predicted raw noise floor by RMS, with per-pixel residual clipped to
  `1.0 * sigma`.
- Same-plane lag remains bounded: worst absolute lag is 0.152.
- Edge removal is biased away from structure: edge/non-edge energy ratio stays
  below 1.0 on all six crops.
- The exact residual sidecar reconstructs the original raw crop with maximum
  float error of 0.000122 raw counts.

## Next Training Step

Use these NPZ sidecars to build the next CNN target:

- train signal placement against `clean`;
- condition the model on `sigma` or ISO/noise-profile channels;
- score both `candidate_clean` versus `clean` and
  `candidate_clean + exact_residual` versus `raw`;
- only after exact-addback scoring works, replace `exact_residual` with
  synthetic ISO-aware Bayer/wavelet noise.
