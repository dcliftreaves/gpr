# Raw Signal CNN Candidate

Date: 2026-06-05

This pass moves the codec CNN target away from denoised REF residuals and onto
source Bayer signal/detail reconstruction. The noise audit showed that nonzero
REF denoise residuals can be signal-correlated, so the production-safe target
for this pass is `target_raw_planes`, with noise synthesis/addback left as a
separate render/evaluation layer.

## Artifacts

- Expanded manifest:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_signal_expanded_manifest_20260605/expanded_raw_signal_test_set_28img.json`
- Strict sidecars:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_expanded_noise_only_20260605/raw_clean_ref_targets.json`
- Sidecar dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_expanded_noise_only_20260605/raw_clean_ref_targets.html`
- Sidecar validation:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_expanded_noise_only_20260605/raw_clean_ref_targets_validation.json`
- Signal audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_noise_signal_audit_expanded_noise_only_20260605/raw_noise_signal_audit.html`
- Codec/source pairs:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_pairs_expanded_20260605/ml2_q3_dec2_raw_signal_pairs_expanded_84crops.npz`
- Checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/codec_raw_signal_sr_w64_iso_expanded_84crops.pt`
- Model dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/dashboard_w64_iso_expanded_84crops/codec_raw_clean_dashboard.html`
- Dispatch dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/dispatch_policy_w64_iso_expanded_84crops/raw_signal_dispatch_policy.html`

## Data

The expanded manifest contains 28 full-resolution DNGs and 84 fixed-coordinate
crops. ISO coverage:

| ISO | images |
| ---: | ---: |
| 64 | 7 |
| 200 | 2 |
| 500 | 3 |
| 560 | 1 |
| 640 | 1 |
| 5000 | 2 |
| 7200 | 1 |
| 9000 | 1 |
| 11400 | 1 |
| 25600 | 9 |

The strict sidecar validator passed all 84 crops. The stricter signal audit
flagged several nonzero residuals as signal-correlated; those residuals must
not be used as a denoise target. This candidate trains against raw signal only.

## Candidate

Training command shape:

```bash
python3 tools/cnn/train_codec_raw_clean_sr.py \
  --pairs /Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_pairs_expanded_20260605/ml2_q3_dec2_raw_signal_pairs_expanded_84crops.npz \
  --out /Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/codec_raw_signal_sr_w64_iso_expanded_84crops.pt \
  --steps 6000 --batch 8 --crop 128 --width 64 \
  --conditioning iso --target-mode raw_signal
```

Result on the 84-crop expanded set:

| mode | mean raw target RMSE | max raw target RMSE | rows regressed vs bilinear |
| --- | ---: | ---: | ---: |
| model only | 54.56 counts | 216.92 counts | 11 |
| bilinear bypass only | 218.05 counts | 847.44 counts | n/a |
| dispatch policy | 54.17 counts | 216.92 counts | 0 |

Best dispatch policy from the sweep:

```text
use model if ISO >= 100 or decoded HF RMS >= 1.741 raw counts
otherwise bypass to bilinear
```

This preserves the model gains on all ISO >= 200 crops and bypasses low-ISO
low-texture crops where the model can slightly over-correct.

Gate-image raw-domain averages:

| image | policy RMSE | bilinear RMSE | selected behavior |
| --- | ---: | ---: | --- |
| `Z8Z_0001` | 35.68 | 144.92 | model on detail crops, bypass on low-texture crop |
| `Z8Z_0067` | 15.72 | 15.72 | bypass all smooth crops |
| `Z8Z_5323` | 23.49 | 119.57 | model all crops |
| `Z8Z_6693` | 33.51 | 172.22 | model all crops |

## Remaining Work

This is a strong raw-domain candidate, but it is not production-ready until:

- the dispatch policy is wired into a temporary registered pipeline;
- full rendered quality gates are run against the current display-space
  baseline;
- LPIPS, MS-SSIM, luma/detail, crop-level texture placement, and worst-image
  visual inspection are compared;
- decode + model + encode timing is measured on the intended preview path;
- the checkpoint hash and sidecar config are recorded as production artifacts.
