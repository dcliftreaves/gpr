# Codec Raw Clean Dispatch Candidate

Date: 2026-06-04

This pass follows the preview-holdout finding that raw noise removal must be
noise-level/acceptance gated, not always-on. It compares two `ml2_q3_dec2`
codec-input clean-target models and a virtual sidecar-label dispatch policy.

Artifacts:

- All-target checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/codec_raw_clean_sr_w64_all_targets.pt`
- All-target dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dashboard_w64_all_targets/codec_raw_clean_dashboard.html`
- Dispatch comparison dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dispatch_comparison_w64/codec_raw_clean_dispatch_dashboard.html`
- Dispatch comparison JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dispatch_comparison_w64/codec_raw_clean_dispatch_dashboard.json`

## Trainer Fix

`tools/cnn/train_codec_raw_clean_sr.py` now scores checkpoints by the correct
objective:

- `--accepted-only`: optimize accepted-crop clean RMSE.
- all-target training: optimize all-row clean RMSE.

The previous all-target run was accidentally scored by accepted-crop RMSE
because accepted rows existed. The corrected all-target checkpoint saves at the
best all-row score.

## Full-Gate Raw Metrics

The comparison uses the existing 12-pair full-gate codec-input dataset:

`/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_20260604/ml2_q3_dec2_raw_clean_pairs.npz`

| Candidate | All mean RMSE | Accepted mean RMSE | Rejected mean RMSE |
| --- | ---: | ---: | ---: |
| accepted-only model | 72.38 | 26.62 | 118.15 |
| all-target model | 41.96 | 33.93 | 49.99 |
| oracle dispatch | 38.31 | 26.62 | 49.99 |

The dispatch policy is:

- accepted crops use the accepted-only high-ISO model;
- rejected/no-op crops use the all-target model.

This is an oracle comparison because it uses sidecar acceptance labels. It is
not yet a runtime classifier for arbitrary video frames.

## Interpretation

The dispatch result is the best current raw-domain candidate:

- it keeps the accepted-only model's high-ISO performance;
- it avoids the accepted-only model's low-ISO/rejected-crop failure;
- it improves the all-target model by using the specialized high-ISO model only
  where the clean-target sidecar says removal is safe.

This does not yet satisfy final production criteria. The next required step is
to replace the sidecar oracle with a runtime acceptance/noise-level gate that
can be computed from source/decoded raw data, then run the rendered quality
gate and timing path.
