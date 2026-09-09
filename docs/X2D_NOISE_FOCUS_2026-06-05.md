# X2D Noise Focus

Date: 2026-06-05

This pass pivots the noise/signal work to Hasselblad X2D because we have both
scene raws and darkframes for that camera.

## Source Material

- Project notes pointed to `/Volumes/Photos/DavidsPics/Hassel` and
  `/Users/dcliftreaves/Pictures/hassel/`.
- The mounted photo volume is available as `/Volumes/photos/DavidsPics/Hassel`.
- X2D darkframes are in `/Volumes/OWC_8TB/gpr_work/X2D_DarkFrames`.

Inventory:

- `/Volumes/photos/DavidsPics/Hassel`: 16,127 raw/DNG candidates.
- 2024/2025 X2D `.fff` metadata inventory: 3,195 X2D 100C scene raws.
- X2D scene ISO counts: ISO64=438, ISO100=346, ISO200=229, ISO400=504,
  ISO800=280, ISO1600=232, ISO3200=343, ISO6400=394, ISO12800=429.
- X2D darkframes: ISO64=187, ISO200=100, ISO800=100, ISO3200=50,
  ISO12800=50.

## Adobe DNG Conversion

Adobe DNG Converter is installed at:

`/Applications/Adobe DNG Converter.app/Contents/MacOS/Adobe DNG Converter`

Converted representative scene DNGs are staged outside the repo:

`/Volumes/OWC_8TB/gpr_work/x2d_scene_dngs/adobe_20260605`

The matched-ISO set currently contains one scene each at ISO 64, 200, 800,
3200, and 12800, plus an ISO 6400 smoke-test scene.

## Artifacts

- Darkframe calibration dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_calibration_x2d_full_20260605/darkframe_calibration.html`
- Matched-ISO scene noise dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/noise_profile_analysis_adobe_matched_iso/noise_profile_analysis.html`
- Matched-ISO test set:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/x2d_adobe_matched_iso_test_set.json`
- 2024/2025 X2D metadata inventory:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_hassel_2024_2025_fff_metadata_20260605.json`

## Findings

The raw-domain analyzer now accepts X2D DNGs with three-value `BlackLevel`
metadata. X2D uses per-color black levels in some converted DNGs; the analyzer
maps them to R/G/B with both green CFA sites sharing the green value.

Darkframe calibration measured the expected ISO scaling. Temporal RMS by CFA
site is roughly 17 counts at ISO800, 64-67 counts at ISO3200, and 230-243
counts at ISO12800.

Matched-ISO scene analysis shows the noise-removal target becomes more credible
at higher ISO:

| ISO | Avg sigma RMS | Avg flat HF/sigma | Avg removed/sigma | Max lag |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 87.76 | 2.628 | 0.435 | 0.363 |
| 200 | 142.21 | 1.851 | 0.492 | 0.368 |
| 800 | 168.79 | 1.024 | 0.677 | 0.246 |
| 3200 | 497.04 | 1.033 | 0.491 | 0.213 |
| 6400 | 704.37 | 0.938 | 0.623 | 0.169 |
| 12800 | 1010.69 | 0.929 | 0.779 | 0.066 |

Interpretation:

- ISO 800 and above are close enough to the DNG-predicted noise floor to support
  meaningful raw-clean/noise-addback experiments.
- ISO 64 and 200 still show more structure risk, so low-ISO clean targets should
  stay conservative unless additional flat-field or frame-stack evidence proves
  the residual is camera noise.
- The next CNN target pass should be ISO-aware: learn signal/detail placement
  from the scene target, then add camera noise back as a rendering layer rather
  than asking the CNN to synthesize exact sensor noise.

## ISO 200+ Control Pass

Follow-up artifacts:

- ISO 200+ target dashboard with `--min-noise-iso 800`:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/raw_clean_targets_iso200plus_min800_v2/raw_clean_ref_targets.html`
- ISO 200+ audit dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/raw_noise_signal_audit_iso200plus_min800_v2/raw_noise_signal_audit.html`
- ISO 1600/3200 diagnostic dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/noise_profile_analysis_iso1600_3200_focus/noise_profile_analysis.html`

Policy:

- ISO 200 and 400 are exact raw-preserving controls.
- ISO 800 and above may generate a nonzero residual, but only if the residual
  passes the full noise/signal audit.
- If a residual is too correlated with image gradients, it is forced to an
  exact no-op sidecar before training.

Result:

| ISO | Crops | Forced controls | Contract no-op | Nonzero targets | Audit |
| ---: | ---: | ---: | ---: | ---: | --- |
| 200 | 3 | 3 | 0 | 0 | pass |
| 400 | 3 | 3 | 0 | 0 | pass |
| 800 | 3 | 0 | 3 | 0 | pass |
| 1600 | 3 | 0 | 2 | 1 | pass |
| 3200 | 3 | 0 | 3 | 0 | pass |
| 6400 | 3 | 0 | 3 | 0 | pass |
| 12800 | 3 | 0 | 2 | 1 | pass |

The ISO 1600/3200 diagnostic dashboard is the right place to visually inspect
why noise removal matters. It shows about 0.5-0.8 sigma of removable
high-frequency content in the less-destructive analyzer. The production target
builder is stricter: it keeps only residuals that pass lag, edge, and gradient
correlation checks, because those sidecars become CNN training targets.

## Next Work

## Expanded ISO-Stratified Pass

Follow-up artifacts:

- Selection manifest:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/x2d_iso_stratified_21_fff_selection.json`
- Converted DNG manifest:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/x2d_iso_stratified_21_test_set.json`
- Target dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/raw_clean_targets_iso_stratified_21_min800/raw_clean_ref_targets.html`
- Audit dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605/raw_noise_signal_audit_iso_stratified_21_min800/raw_noise_signal_audit.html`

The expanded pass uses 21 X2D scenes: three each at ISO 200, 400, 800, 1600,
3200, 6400, and 12800. Each scene contributes three 1024x1024 crops.

Result:

| ISO | Crops | Forced controls | Contract no-op | Nonzero targets | Audit |
| ---: | ---: | ---: | ---: | ---: | --- |
| 200 | 9 | 9 | 0 | 0 | pass |
| 400 | 9 | 9 | 0 | 0 | pass |
| 800 | 9 | 0 | 8 | 1 | pass |
| 1600 | 9 | 0 | 9 | 0 | pass |
| 3200 | 9 | 0 | 5 | 4 | pass |
| 6400 | 9 | 0 | 8 | 1 | pass |
| 12800 | 9 | 0 | 7 | 2 | pass |

All 63 audit rows pass. Every low-ISO control is an exact no-op. The surviving
high-ISO residuals are tiny, with max residual/sigma RMS below 0.004. This is
the intended production-safe behavior: remove only residuals that are strongly
noise-like, preserve signal by default, and keep exact residual sidecars only
for analysis/addback.

## Next Work

1. Use the expanded X2D pass as the noise/signal guardrail, not as the main CNN
   objective. The production target should still learn raw signal/detail
   placement.
2. Train or distill the next candidate with larger/full-image context or a
   teacher objective; the small crop-RMSE model has already failed rendered
   detail placement.
3. Add synthetic ISO-aware noise rendering as a separate output layer after the
   signal model. Exact residual addback remains an evaluation receipt, not a
   training target.
4. Re-run full gates and timing only after the detail-placement candidate
   improves rendered LPIPS/MS-SSIM and crop-level texture placement.
