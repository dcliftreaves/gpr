# Raw Clean REF Targets

Date: 2026-06-04

This pass turns the Z8 raw-noise analysis into auditable clean-signal training
targets. It works in linear raw CFA space, separates R/G1/G2/B before measuring
structure, and saves the exact removed residual as an addback sidecar.

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets.html`

JSON:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets.json`

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

The builder enforces the target contract by default. If a crop's candidate
residual fails the residual/sigma, lag, or edge-leakage checks, the residual is
rejected and the sidecar becomes a no-op target (`clean == raw`,
`exact_residual == 0`) for that crop.

## Full-Gate Metrics

Validation:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets_validation.json`

| Image | ISO | Crop | accepted | reason | residual/sigma | lag max abs | edge energy ratio |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| `Z8Z_0001` | 64 | `A_detail` | no | lag | 0.000 | 0.000 | 0.000 |
| `Z8Z_0001` | 64 | `B_center` | no | lag | 0.000 | 0.000 | 0.000 |
| `Z8Z_0001` | 64 | `C_lowerleft` | no | lag | 0.000 | 0.000 | 0.000 |
| `Z8Z_0067` | 64 | `A_detail` | no | lag | 0.000 | 0.000 | 0.000 |
| `Z8Z_0067` | 64 | `B_center` | no | lag | 0.000 | 0.000 | 0.000 |
| `Z8Z_0067` | 64 | `C_lowerleft` | no | lag | 0.000 | 0.000 | 0.000 |
| `Z8Z_5323` | 5000 | `A_detail` | yes | - | 0.238 | 0.092 | 0.600 |
| `Z8Z_5323` | 5000 | `B_center` | yes | - | 0.265 | 0.105 | 0.735 |
| `Z8Z_5323` | 5000 | `C_lowerleft` | yes | - | 0.237 | 0.085 | 0.821 |
| `Z8Z_6693` | 9000 | `A_detail` | yes | - | 0.224 | 0.152 | 0.839 |
| `Z8Z_6693` | 9000 | `B_center` | yes | - | 0.232 | 0.105 | 0.712 |
| `Z8Z_6693` | 9000 | `C_lowerleft` | yes | - | 0.243 | 0.107 | 0.795 |

Interpretation:

- The ISO 64 crops failed the lag criterion before enforcement, so they are
  rejected rather than denoised. This avoids training against structured
  low-ISO signal as if it were noise.
- The accepted ISO 5000/9000 residuals are intentionally sub-sigma: roughly
  0.224-0.265x the DNG-predicted raw noise floor by RMS, with per-pixel
  residual clipped to `1.0 * sigma`.
- Same-plane lag remains bounded on accepted targets: worst absolute lag is
  0.152.
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
