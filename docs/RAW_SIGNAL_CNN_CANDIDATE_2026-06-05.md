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
- Registered gate run:
  `/Volumes/OWC_8TB/gpr_work/worktrees/gpr_clean_sanitized_20260604/tests/quality_gates/runs/1bd6fcf9583a44fa/run.json`

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

## Registered Source-Sigma Gate Run

Temporary registered pipeline:

```text
codec=ml2_q3_dec2+cnn=codec_raw_signal_sr_ml2_q3_dec2_w64_iso_expanded+demosaic=sips_via_gpr_tools
```

Frozen gate run:

```text
run_hash=1bd6fcf9583a44fa
ship_class=UPRESABLE
verdict=PASS
```

Per-image gate metrics:

| image | Bayer PSNR final | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_0001` | 47.44 | 0.0761 | 0.9877 | 37.83 | 1.80 |
| `Z8Z_0067` | 58.43 | 0.0618 | 0.9922 | 47.42 | 0.83 |
| `Z8Z_5323` | 58.04 | 0.0174 | 0.9960 | 47.16 | 0.86 |
| `Z8Z_6693` | 55.27 | 0.0244 | 0.9943 | 45.23 | 1.11 |

UPRESABLE gates enforce Bayer PSNR final; rendered metrics are informational
for editable raw, but they are listed here to make color/detail regressions
visible.

This receipt is an analysis result, not a deployable production path: the model
conditions on a sigma map derived from the source DNG raw signal. A decoder does
not have that source raw; it has codec output plus DNG metadata.

## Runtime-Sigma Probe

Production-valid sigma conditioning was tested with a separate registered probe:

```text
codec=ml2_q3_dec2+cnn=codec_raw_signal_sr_ml2_q3_dec2_w64_iso_expanded_runtime_sigma_probe+demosaic=sips_via_gpr_tools
```

The probe computes the DNG NoiseProfile sigma map from decoded/upscaled codec
raw instead of source raw.

Frozen gate run:

```text
run_hash=aa32c2c5d52eb753
ship_class=UPRESABLE
verdict=PASS
```

The raw Bayer gate still passes, but the rendered blockers regress sharply:

| image | source-sigma LPIPS | runtime-sigma LPIPS | source MS-SSIM | runtime MS-SSIM | source Bayer PSNR | runtime Bayer PSNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_0001` | 0.0761 | 0.2814 | 0.9877 | 0.8849 | 47.44 | 37.64 |
| `Z8Z_0067` | 0.0618 | 0.0832 | 0.9922 | 0.9867 | 58.43 | 50.66 |
| `Z8Z_5323` | 0.0174 | 0.3333 | 0.9960 | 0.9229 | 58.04 | 42.42 |
| `Z8Z_6693` | 0.0244 | 0.4417 | 0.9943 | 0.8916 | 55.27 | 39.47 |

Conclusion: the current checkpoint is not production-ready. The failure is now
narrowed to a conditioning mismatch: training used source-derived sigma, while
deployment must use codec-derived or metadata-only sigma. The next candidate
must be retrained or distilled with runtime-available sigma conditioning, or the
sigma channels must be removed.

## Runtime-Sigma Retrain

A follow-up retrain used the same expanded 84-crop set but rebuilt the pair
sigma channels from decoded/upscaled codec raw:

- Runtime-sigma pairs:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_pairs_runtime_sigma_20260605/ml2_q3_dec2_raw_signal_pairs_runtime_sigma_84crops.npz`
- Checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_runtime_sigma_20260605/codec_raw_signal_sr_w64_iso_runtime_sigma_84crops.pt`
- Checkpoint SHA-256:
  `fb6e37a1e15ed297d47878b6144bebcbf5ed0ee675bfe5a141da401e5c497aeb`
- Model dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_runtime_sigma_20260605/dashboard_w64_iso_runtime_sigma_84crops/codec_raw_clean_dashboard.html`
- Dispatch dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_runtime_sigma_20260605/dispatch_policy_w64_iso_runtime_sigma_84crops/raw_signal_dispatch_policy.html`

Training summary on the 84-crop pair set:

| mode | mean raw target RMSE | accepted raw target RMSE | note |
| --- | ---: | ---: | --- |
| bilinear bypass | 218.05 counts | 225.28 counts | baseline |
| runtime-sigma model | 191.36 counts | 204.87 counts | weak gain |
| dispatch policy | 191.32 counts | n/a | ISO >= 100 or HF RMS >= 1.741; 1 regression |

Registered retrain gate run:

```text
pipeline=codec=ml2_q3_dec2+cnn=codec_raw_signal_sr_ml2_q3_dec2_w64_iso_runtime_sigma_84crops+demosaic=sips_via_gpr_tools
run_hash=042cc4bdcf4dfe35
ship_class=UPRESABLE
verdict=PASS
```

The raw Bayer gate still passes, but rendered quality remains unusable:

| image | source-sigma LPIPS | runtime-sigma probe LPIPS | runtime-sigma retrain LPIPS | retrain MS-SSIM | retrain Bayer PSNR |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_0001` | 0.0761 | 0.2814 | 0.3015 | 0.9136 | 38.80 |
| `Z8Z_0067` | 0.0618 | 0.0832 | 0.0881 | 0.9887 | 51.63 |
| `Z8Z_5323` | 0.0174 | 0.3333 | 0.4251 | 0.9400 | 43.62 |
| `Z8Z_6693` | 0.0244 | 0.4417 | 0.6393 | 0.9170 | 39.46 |

Conclusion: retraining the same small crop model with runtime sigma does not
solve full-image texture/detail placement. The next candidate should either
remove sigma channels entirely or use a larger/full-context teacher objective;
the current architecture/input contract should not be promoted.

## No-Sigma Retrain

A follow-up retrain removed sigma maps from the model input entirely. The
candidate uses only decoded/upscaled codec raw plus one ISO conditioning plane,
so it has no dependency on source-derived or codec-derived sigma maps.

- Checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_iso_only_20260605/codec_raw_signal_sr_w64_iso_only_84crops.pt`
- Checkpoint SHA-256:
  `7de6e691813e39ae2d9d3ce1a0ed1682a90b2d702c0cb3ac6af2d01f1e9445cf`
- Model dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_iso_only_20260605/dashboard_w64_iso_only_84crops/codec_raw_clean_dashboard.html`
- Dispatch dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_iso_only_20260605/dispatch_policy_w64_iso_only_84crops/raw_signal_dispatch_policy.html`

Training summary on the expanded 84-crop pair set:

| mode | mean raw target RMSE | accepted raw target RMSE | note |
| --- | ---: | ---: | --- |
| bilinear bypass | 218.05 counts | 225.28 counts | baseline |
| no-sigma model | 190.84 counts | 204.76 counts | weak crop gain |
| dispatch policy | 190.84 counts | n/a | ISO >= 100 or HF RMS >= 1.741; 1 regression |

Registered no-sigma gate run:

```text
pipeline=codec=ml2_q3_dec2+cnn=codec_raw_signal_sr_ml2_q3_dec2_w64_iso_only_84crops+demosaic=sips_via_gpr_tools
run_hash=4f8231e47309d668
ship_class=UPRESABLE
verdict=PASS
```

The raw Bayer gate still passes, but rendered quality is essentially unchanged
from the runtime-sigma retrain:

| image | source-sigma LPIPS | runtime-sigma retrain LPIPS | no-sigma LPIPS | no-sigma MS-SSIM | no-sigma Bayer PSNR |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_0001` | 0.0761 | 0.3015 | 0.3062 | 0.9131 | 38.78 |
| `Z8Z_0067` | 0.0618 | 0.0881 | 0.0887 | 0.9888 | 51.68 |
| `Z8Z_5323` | 0.0174 | 0.4251 | 0.4246 | 0.9424 | 43.10 |
| `Z8Z_6693` | 0.0244 | 0.6393 | 0.6503 | 0.9199 | 40.04 |

Conclusion: removing sigma channels does not solve the blocker. The failure is
now narrowed away from sigma conditioning alone. The next candidate should stop
retraining this small crop-RMSE model and move to a larger/full-context or
teacher-distilled objective that directly optimizes full-image detail placement.

## Runtime

The 2026-06-05 rerun of `1bd6fcf9583a44fa` records per-image stage timings
in `run.json`. Measurements were taken on the local Apple Silicon gate host
with `GATE_MAX_WORKERS=1`; scratch was on `/Volumes/OWC_8TB/gpr_work/gate_tmp`.

| metric | mean | min | max |
| --- | ---: | ---: | ---: |
| codec encode/decode | 10.45 ms | 7.60 ms | 13.90 ms |
| raw-signal CNN apply | 1614.21 ms | 993.71 ms | 2199.74 ms |
| codec + CNN restore | 1624.66 ms | 1001.31 ms | 2209.04 ms |
| model inference only | 512.67 ms | 166.50 ms | 675.14 ms |
| demosaic/render | 13905.78 ms | 12079.64 ms | 15113.63 ms |
| metrics | 3971.57 ms | 3733.54 ms | 4517.58 ms |
| full gate image path | 25538.89 ms | 22129.59 ms | 26989.18 ms |

Dispatch statistics over the four gate images:

| metric | mean | min | max |
| --- | ---: | ---: | ---: |
| tiles total | 187.00 | 187 | 187 |
| tiles using model | 134.75 | 32 | 187 |
| tiles bypassed | 52.25 | 0 | 155 |

Interpretation: the codec stage remains preview-speed, but the current Python
tiled PyTorch raw-signal CNN restore path is an offline/desktop candidate only.
The full gate path additionally includes validation-only render and metric
work. Promotion to a live/preview path requires a compiled restore backend and a
separate target benchmark on that backend. The runtime-sigma and no-sigma
retries show that performance optimization is secondary until the full-image
detail-placement objective is fixed.

## Remaining Work

This is a registered raw-domain candidate, but it is not production-ready until:

- full rendered quality gates are run against the current display-space
  baseline;
- LPIPS, MS-SSIM, luma/detail, crop-level texture placement, and worst-image
  visual inspection are compared;
- the candidate is retrained or distilled with a larger/full-context objective;
  both runtime-available sigma conditioning and no-sigma conditioning failed
  this requirement with the current small crop model;
- the raw-signal CNN is compiled or otherwise optimized, then decode + model +
  encode timing is remeasured on the intended preview path;
- the checkpoint hash, sidecar config, gate receipt, and timing receipt are kept
  with the candidate artifacts.
