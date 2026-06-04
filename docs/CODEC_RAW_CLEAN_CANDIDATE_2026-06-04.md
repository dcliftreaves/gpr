# Codec Raw Clean Candidate

Date: 2026-06-04

This pass connects the validated raw clean targets to the actual preview codec
input path. It builds paired data from `ml2_q3_dec2` decoded Bayer crops to
full-resolution clean raw targets, then trains a small 2x raw model.

Artifacts:

- Paired NPZ:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_20260604/ml2_q3_dec2_raw_clean_pairs.npz`
- Paired NPZ receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_20260604/ml2_q3_dec2_raw_clean_pairs.npz.json`
- Best high-ISO checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/codec_raw_clean_sr_w64_accepted_only.pt`
- Dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dashboard_w64_accepted/codec_raw_clean_dashboard.html`

## Paired Data

`tools/cnn/build_codec_raw_clean_pairs.py` encodes and decodes each source DNG
with `ml2_q3_dec2`, then maps the full-resolution clean-target crop to the
corresponding half-resolution decoded Bayer crop.

Shapes:

- Codec input: `N x 4 x 128 x 128`.
- Clean raw target: `N x 4 x 256 x 256`.
- Exact residual and sigma target sidecars: `N x 4 x 256 x 256`.

Encode measurements from this run:

| Image | encoded bytes | encode ms |
| --- | ---: | ---: |
| `Z8Z_0001` | 1,751,835 | 8.80 |
| `Z8Z_0067` | 1,020,716 | 7.70 |
| `Z8Z_5323` | 2,658,567 | 11.20 |
| `Z8Z_6693` | 3,374,869 | 12.50 |

## Candidate

`tools/cnn/train_codec_raw_clean_sr.py` trains a small raw 2x model:

- Input: bilinear-upsampled codec CFA planes plus target sigma planes.
- Output: clean full-resolution CFA planes.
- Width: 64.
- Steps: 5000.
- Training set: accepted high-ISO targets only.

Result:

- Accepted high-ISO clean RMSE: 26.62 raw counts.
- Accepted high-ISO exact-addback RMSE: 26.62 raw counts.

Per accepted crop:

| Image | ISO | Crop | clean RMSE counts |
| --- | ---: | --- | ---: |
| `Z8Z_5323` | 5000 | `A_detail` | 23.74 |
| `Z8Z_5323` | 5000 | `B_center` | 27.76 |
| `Z8Z_5323` | 5000 | `C_lowerleft` | 16.88 |
| `Z8Z_6693` | 9000 | `A_detail` | 29.23 |
| `Z8Z_6693` | 9000 | `B_center` | 25.31 |
| `Z8Z_6693` | 9000 | `C_lowerleft` | 36.82 |

## Interpretation

- The codec-input path can learn the validated high-ISO clean targets; the
  accepted-only model reaches about the same high-ISO RMSE as the source-raw
  clean-target learner.
- This is not full-gate production yet. Because the checkpoint was trained only
  on accepted high-ISO targets, it is bad on rejected ISO 64 no-op crops.
- The production candidate should either train a mixed/gated model that learns
  no-op behavior on rejected low-ISO crops, or dispatch the noise-clean model
  only when the raw-noise contract accepts the target.

## Next

Train the same codec-input architecture with an explicit acceptance/noise-level
conditioning channel and a loss that includes rejected no-op crops without
letting them dilute the accepted high-ISO objective.
