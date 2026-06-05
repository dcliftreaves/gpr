# Raw Noise/Signal Audit

Date: 2026-06-05

This pass tightened the rule for separating removable sensor noise from signal
before using raw-clean targets for CNN training.

Artifacts:

- Strict target dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_noise_only_20260605/raw_clean_ref_targets.html`
- Strict target JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_noise_only_20260605/raw_clean_ref_targets.json`
- Noise/signal audit dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_noise_signal_audit_noise_only_20260605/raw_noise_signal_audit.html`
- Noise/signal audit JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_noise_signal_audit_noise_only_20260605/raw_noise_signal_audit.json`

## What Changed

`tools/cnn/build_raw_clean_ref_targets.py` now applies two extra guardrails
after the initial conservative residual estimate:

1. Whiten the residual by the DNG sigma map and regress out predictable
   components from lowpass signal, gradient support, finest wavelet detail, and
   coarser wavelet detail.
2. Apply a final flat-region gate after decorrelation so residual amplitude is
   not concentrated around edges.

`tools/cnn/audit_raw_noise_signal_separation.py` is a new pre-training audit.
It checks exact addback, residual/sigma, max residual/sigma, lag, edge leakage,
clean correlation, gradient correlation, spectral flatness, PSD peaks, and
low-frequency energy.

## Result

The older nonzero high-ISO residuals were sub-sigma and spectrally broad, but
they still carried strong correlation with same-plane high-frequency image
content. After highpass decorrelation and flat-region suppression, all gate
crops pass the audit only as effective no-ops:

| Image set | Rows | Pass | Fail | Effective no-op |
| --- | ---: | ---: | ---: | ---: |
| Full gate crops | 12 | 12 | 0 | 12 |

Residual/sigma range in the strict target set:

- minimum: `0.0000`
- maximum: `0.0186`

Interpretation: with the current single-frame Z8 REF evidence, any meaningful
REF denoise target is too entangled with real image detail. The production-safe
training target is therefore `clean ~= raw`, with exact addback retained as a
contract but not used as a meaningful residual.

## Production Decision

Do not train the next CNN against the earlier nonzero raw-clean residuals as
though they are pure camera noise. For the next model pass:

- train signal/detail placement against the raw target or a better teacher;
- keep DNG `NoiseProfile`/ISO as conditioning metadata;
- use synthetic or calibrated camera noise only as an output rendering/addback
  layer after signal reconstruction;
- require this audit to pass before any future clean-target sidecar is accepted
  as nonzero noise removal.

To produce nonzero clean targets safely, we need better evidence than a single
noisy REF frame: matched darkframes/blackframes for the same camera path,
frame stacks, or a controlled flat-field calibration set at the relevant ISOs.
