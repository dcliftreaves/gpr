# Preview Holdout Raw Clean Audit

Date: 2026-06-04

This pass expands the raw clean-target and synthetic addback checks from the
four-image frozen gate to the 28-image informational preview holdout. This is
not a ship-gate claim; it is a breadth audit for the noise/signal separation
logic before more CNN work.

Artifacts:

- Clean-target dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_preview_holdout_20260604/raw_clean_ref_targets.html`
- Clean-target JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_preview_holdout_20260604/raw_clean_ref_targets.json`
- Clean-target validation:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_preview_holdout_20260604/raw_clean_ref_targets_validation.json`
- Synthetic addback dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/synthetic_raw_noise_addback_preview_holdout_20260604/synthetic_raw_noise_addback.html`
- Synthetic addback JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/synthetic_raw_noise_addback_preview_holdout_20260604/synthetic_raw_noise_addback.json`

## Reader Fixes

The holdout pass found two DNG-reader compatibility issues:

- Some TIFF pages expose `page.pages` as `None`, not an empty iterable.
- Some DNGs store a single two-value `NoiseProfile` pair instead of three
  RGB pairs. The reader now treats a two-value profile as a shared
  scale/offset variance pair for all CFA planes.

Both fixes are in `tools/cnn/analyze_dng_noise_profile.py`.

## Clean-Target Result

Holdout scope:

- 28 images.
- 3 fixed crops per image.
- 84 raw clean-target sidecars.

Validation:

- Sidecar contract validation: 84 pass / 0 fail.
- Accepted residual crops: 6.
- Rejected/no-op crops: 78.
- Rejection causes before contract enforcement: `lag` on 78 crops and
  `edge_ratio` on 61 crops.

Acceptance by ISO:

| ISO | Crops | Accepted |
| ---: | ---: | ---: |
| 64 | 63 | 0 |
| 72 | 6 | 0 |
| 450 | 3 | 0 |
| 500 | 6 | 1 |
| 4000 | 3 | 2 |
| 25600 | 3 | 3 |

Accepted-crop guardrails:

- Mean residual/sigma RMS: 0.2335.
- Max accepted edge removed-energy ratio: 0.9456.
- Max accepted lag: 0.1817.

Interpretation: the current cleaner behaves as a conservative high-ISO/noise
dispatch. It does not remove low-ISO fine structure from the preview holdout;
those crops become explicit no-op targets.

## Synthetic Addback Result

Synthetic addback scope:

- 84 per-crop NPZ sidecars.
- Max reconstruction error for `clean + synthetic_residual == synthetic_addback`: 0.0.

Accepted-crop addback metrics:

- Mean synthetic/exact residual RMS ratio: 0.9979.
- Min/max synthetic/exact residual RMS ratio: 0.9975 / 0.9988.
- Max synthetic edge ratio: 0.6536.
- Max exact edge ratio: 0.9456.
- Max synthetic same-plane lag: 0.0115.

Accepted rows:

| Image | Crop | ISO | RMS ratio | Synthetic edge ratio |
| --- | --- | ---: | ---: | ---: |
| `Z8Z_1586` | `C_lowerleft` | 500 | 0.9983 | 0.336 |
| `Z8Z_5937` | `A_detail` | 4000 | 0.9976 | 0.565 |
| `Z8Z_5937` | `C_lowerleft` | 4000 | 0.9976 | 0.630 |
| `Z8Z_7480` | `A_detail` | 25600 | 0.9975 | 0.438 |
| `Z8Z_7480` | `B_center` | 25600 | 0.9988 | 0.654 |
| `Z8Z_7480` | `C_lowerleft` | 25600 | 0.9976 | 0.400 |

## Production Implication

Do not train a single always-on denoising/restoration model against these
targets. The data says the next production candidate needs explicit
noise-level or acceptance dispatch:

- low ISO and unsafe structure-heavy crops should be no-op for the noise
  removal branch;
- high ISO accepted crops can use clean-target training plus synthetic addback;
- any visual comparison that uses clean targets must add exact residuals back
  for equivalence scoring, then separately evaluate synthetic addback.

The next CNN path should therefore be gated/conditioned, not a blanket
cleaning model.
