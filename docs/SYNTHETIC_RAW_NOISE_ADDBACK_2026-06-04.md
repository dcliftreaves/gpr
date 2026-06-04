# Synthetic Raw Noise Addback

Date: 2026-06-04

This pass creates the first synthetic replacement for the exact residual
sidecars. It is a diagnostic baseline, not final production grain.

Artifacts:

- Dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/synthetic_raw_noise_addback_20260604/synthetic_raw_noise_addback.html`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/synthetic_raw_noise_addback_20260604/synthetic_raw_noise_addback.json`
- Per-crop NPZ sidecars:
  `/Volumes/OWC_8TB/gpr_work/artifacts/synthetic_raw_noise_addback_20260604/<image>/<image>_<crop>_synthetic_addback.npz`

## Method

`tools/cnn/synthesize_raw_noise_addback.py` builds synthetic residuals from the
raw clean-target sidecars:

1. Draw same-plane Gaussian raw noise.
2. Scale by the DNG-derived per-pixel sigma map.
3. Apply the clean-target mask.
4. Dampen high-gradient same-plane regions.
5. Match the exact residual RMS per crop.
6. Clip to `+/-1.0 * sigma`.

## Accepted High-ISO Results

| Image | Crop | exact/sigma | synthetic/sigma | RMS ratio | synthetic lag | synthetic edge ratio | exact edge ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_5323` | `A_detail` | 0.238 | 0.238 | 0.998 | 0.008 | 0.345 | 0.600 |
| `Z8Z_5323` | `B_center` | 0.265 | 0.264 | 0.996 | 0.009 | 0.430 | 0.735 |
| `Z8Z_5323` | `C_lowerleft` | 0.237 | 0.236 | 0.997 | 0.010 | 0.523 | 0.821 |
| `Z8Z_6693` | `A_detail` | 0.224 | 0.224 | 0.999 | 0.008 | 0.689 | 0.839 |
| `Z8Z_6693` | `B_center` | 0.232 | 0.232 | 0.998 | 0.008 | 0.425 | 0.712 |
| `Z8Z_6693` | `C_lowerleft` | 0.243 | 0.242 | 0.997 | 0.009 | 0.498 | 0.795 |

## Interpretation

- The synthetic addback matches exact residual RMS closely.
- Same-plane lag is lower than exact residual lag, as expected for independent
  Gaussian noise.
- Edge energy is now bounded below the exact residual edge ratio on all
  accepted crops, because the generator explicitly dampens high-gradient
  regions. This is a guardrail, not proof that edge-region grain is
  production-correct.
- This is still not final production noise. It does not yet model darkframe
  fixed-pattern noise, row/column banding, PRNU, or temperature/exposure effects.

## Next

Use the per-crop NPZ sidecars in clean/addback scoring dashboards after exact
addback passes. The next quality step is to add camera-matched darkframe or
black-frame structure if Nikon Z8 calibration frames are found.
