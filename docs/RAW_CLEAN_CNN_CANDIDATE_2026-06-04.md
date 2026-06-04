# Raw Clean CNN Candidate

Date: 2026-06-04

This is the first consumer of the raw clean REF sidecars. It is deliberately a
small raw-space candidate, not yet a registered production pipeline.

Artifacts:

- Checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_train_20260604/raw_clean_ref_cnn_w24.pt`
- Training sidecar:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_train_20260604/raw_clean_ref_cnn_w24.pt.json`
- Dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_train_20260604/dashboard/raw_clean_model_dashboard.html`

## Setup

Training input:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets.json`

Model:

- 8 input channels: four raw CFA planes plus four sigma planes.
- 4 output channels: cleaned CFA planes.
- Small width-24 CNN.
- Trained for 1000 steps on the 12 full-gate sidecars.

The ISO 64 sidecars are no-op targets because their candidate residuals failed
the lag contract. The ISO 5000/9000 sidecars carry accepted exact residuals.

## Result

Best checkpoint:

- Accepted high-ISO clean RMSE: 26.80 raw counts.
- Accepted high-ISO exact-addback RMSE: 26.80 raw counts.
- All-target clean RMSE: 15.19 raw counts.
- Rejected no-op target RMSE: 3.58 raw counts.
- Best score: 0.000755 L1 in normalized raw space.

Per-crop clean RMSE:

| Image | ISO | Crop | accepted target | clean RMSE counts |
| --- | ---: | --- | --- | ---: |
| `Z8Z_0001` | 64 | `A_detail` | no | 3.42 |
| `Z8Z_0001` | 64 | `B_center` | no | 3.72 |
| `Z8Z_0001` | 64 | `C_lowerleft` | no | 3.36 |
| `Z8Z_0067` | 64 | `A_detail` | no | 3.72 |
| `Z8Z_0067` | 64 | `B_center` | no | 3.89 |
| `Z8Z_0067` | 64 | `C_lowerleft` | no | 3.39 |
| `Z8Z_5323` | 5000 | `A_detail` | yes | 25.87 |
| `Z8Z_5323` | 5000 | `B_center` | yes | 26.36 |
| `Z8Z_5323` | 5000 | `C_lowerleft` | yes | 14.02 |
| `Z8Z_6693` | 9000 | `A_detail` | yes | 30.54 |
| `Z8Z_6693` | 9000 | `B_center` | yes | 25.88 |
| `Z8Z_6693` | 9000 | `C_lowerleft` | yes | 38.11 |

Interpretation:

- The sidecar target path is now consumable by a sigma-aware raw CNN.
- The meaningful score for denoising is the accepted high-ISO score, not the
  all-target mean. The all-target mean is diluted by rejected ISO 64 no-op
  targets.
- Exact-addback scoring is wired: `model_clean + exact_residual` is scored
  against original raw, and currently equals clean-target error because the
  sidecar residual exactly reconstructs raw.
- This is not yet a production detail-placement candidate. It only proves the
  clean-target/addback training contract and gives a small baseline for the next
  model.

## Next

The next production-relevant candidate should train from codec-decoded raw input
to these clean raw targets, then evaluate exact-addback against original raw.
Only after that should synthetic ISO-aware noise replace `exact_residual`.
