# Darkframe Calibration Pass

Date: 2026-06-05

This pass adds a raw-domain darkframe discovery and calibration tool, then uses
it to search the consolidated 8TB project data for Z8 darkframes.

## Tool

`tools/cnn/calibrate_darkframes.py`

The tool reads raw files with `rawpy`, reads metadata with `exiftool`, samples
each CFA site relative to its black level, and writes small JSON/HTML/PNG
receipts outside the repo by default.

It reports:

- candidate darkframe detection from raw signal above black;
- per-camera/ISO/exposure grouping;
- per-CFA-site mean residual, robust sigma, hot-pixel fraction, temporal noise,
  row/column fixed-pattern structure, and spatial fixed-pattern RMS;
- small signed residual and temporal-noise mosaics.

## Artifacts

Z8 corpus scan:

`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_discovery_z8_barnsky_20260605/darkframe_calibration.html`

`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_discovery_z8_barnsky_20260605/darkframe_calibration.json`

X2D smoke test:

`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_calibration_smoke_x2d_20260605/darkframe_calibration.html`

`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_calibration_smoke_x2d_20260605/darkframe_calibration.json`

## Z8 Result

The search found Z8 darkframes mixed into:

`/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs`

Summary:

| Source | Files scanned | Dark candidates | Camera | ISO | Exposure |
| --- | ---: | ---: | --- | ---: | ---: |
| `barnsky_full_dngs` | 2658 | 646 | Nikon Z 8 | 500 | 30 s |

The best candidates have whole-frame sampled signal close to black:

| Example | ISO | Exposure | p50 above black | p95 above black | p99 above black |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Z8Z_1474.dng` | 500 | 30 s | 51.0 | 130.8 | 179.9 |
| `Z8Z_1475.dng` | 500 | 30 s | 50.0 | 130.8 | 180.0 |
| `Z8Z_1480.dng` | 500 | 30 s | 51.0 | 132.0 | 186.9 |

The first 32 candidates calibrate as:

| CFA site | mean residual | spatial FPN RMS | temporal RMS | temporal p95 |
| --- | ---: | ---: | ---: | ---: |
| R00 | 51.51 | 298.71 | 16.34 | 29.88 |
| G01 | 80.97 | 299.83 | 24.08 | 51.00 |
| G10 | 80.82 | 298.47 | 23.85 | 50.49 |
| B11 | 46.73 | 131.99 | 17.74 | 35.36 |

Interpretation:

- These are real Z8 darkframes and are useful for dark-current, hot-pixel, and
  fixed-pattern calibration.
- They are not matched to the current high-ISO gate blockers
  (`Z8Z_5323` ISO 5000 and `Z8Z_6693` ISO 9000).
- The high-ISO gate frames should still use the DNG `NoiseProfile` for
  shot/read-noise scale unless matched high-ISO darkframes or blackframe stacks
  are found.
- The ISO-500 darkframes can still be used as a fixed-pattern/hot-pixel prior
  and as a validation dataset for synthetic noise/addback tooling.

## X2D Smoke Test

The X2D darkframe directory also calibrates correctly:

| Source | Files scanned | Dark candidates | Camera | ISO | Exposure |
| --- | ---: | ---: | --- | ---: | ---: |
| `X2D_DarkFrames` smoke subset | 2 | 2 | Hasselblad X2D 100C | 64 | 0.001 s |

Per-site temporal RMS on the two-frame smoke subset is roughly 2.5-2.9 raw
counts, confirming the tool handles non-DNG raw formats readable by `rawpy`.

## Production Decision

The next CNN pass should not train a denoised target from a single noisy REF.
The safer recipe is now:

1. Keep the signal target as raw/teacher signal unless a clean target passes the
   raw noise/signal audit.
2. Condition the model or post-render path on DNG `NoiseProfile`/ISO.
3. Use the discovered Z8 darkframes for hot-pixel and fixed-pattern priors.
4. Add back either exact REF residuals for equivalence diagnostics or synthetic
   ISO-aware Bayer/wavelet noise for final output.
5. Do not accept a nonzero clean-target residual unless it is sub-sigma,
   weakly correlated with signal structure, and supported by matched calibration
   data.
