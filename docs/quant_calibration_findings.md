# Quant calibration — initial rate-distortion sweep

First-pass measurement for task #158 (CNN-aware per-subband quant
calibration, AccelIR style). Sweeps the codec's built-in quality
presets across a Z8 50 MP DNG corpus and records (bits, bayer-PSNR)
per (image, quality). This is the rate-distortion curve the
per-subband sweep needs to beat.

Harness: `tools/test/quant_calibration.py`.

## Findings — 2026-05-24, M3 Max, barn_sky 4-image corpus

Mean over 4 Z8 50 MP `Z8Z_133*.dng` source frames (Release build,
peak=16383 for 14-bit data):

| quality | kB/frame | ratio vs DNG | bayer PSNR |
|---|---|---|---|
| 0 (Low) | 3 674 | 0.103 | 61.77 dB |
| 1 (Medium) | 5 002 | 0.141 | 62.66 dB |
| 2 (High) | 8 363 | 0.235 | 64.51 dB |
| **3 (Filmscan-1 default)** | **10 003** | **0.281** | **65.59 dB** |
| 4 (Filmscan-X) | 11 497 | 0.323 | 66.67 dB |
| **5 (Filmscan-2)** | **14 284** | **0.402** | **69.21 dB ← PEAK** |
| 6 (Filmscan-3) | 16 220 | 0.456 | 66.42 dB ↓ |
| 7 (Filmscan-4) | 16 447 | 0.463 | 61.67 dB ↓↓ |
| 8 (Filmscan-5) | 16 732 | 0.471 | 61.68 dB |

## What this means

**The useful operating range is q=0..5.** Beyond q=5 the codec
allocates more bits but quality regresses. The drop from 69.21 dB
(q=5) to 61.7 dB (q=7,8) at 50 MP costs 7.5 dB while spending an
extra ~2.4 MB/frame. This regression reproduces identically on
master `b53ce2b` and on the `fix/half-res-fused-playback` branch,
so it was introduced before PR #7 / the FUSED rewrite. Filed as
task #159 for separate investigation.

Suspected cause: legacy encoder's smaller `quality_tables[8]`
divisors produce post-quant coefficient magnitudes that exceed an
int16 or rANS class-15 ceiling somewhere and saturate. Not yet
proven; full bisection is blocked because the older-than-Z8-support
commits can't encode the test corpus.

## Implication for #158 (CNN-aware per-subband calibration)

- The "rate budget" for per-subband sweeps should be anchored at
  q=3 (the default, 65.59 dB / 10 MB) and q=5 (the empirical
  quality peak, 69.21 dB / 14.3 MB), not the nominal q=8 ceiling.
- Bit savings target: going from q=5 to q=3 saves ~4.3 MB/frame
  for a ~3.6 dB quality drop. If a CNN closes 2+ dB of that gap
  on real content, we get a clear win.
- Next experiment (waiting on per-subband env-var override in
  encoder + decoder): sweep one subband slot at a time, holding
  others at q=3 defaults. The subbands the CNN closes "for free"
  become the ones we crank up in production.

## Build prerequisite

These numbers require a **Release** build (`-O2`). A `-O0` build —
which happens if CMake was run without `-DCMAKE_BUILD_TYPE=…`
before commit `aed6e37` made Release the default — shows ~12 dB
lower PSNR across the board AND ~6× slower decode. If you see
~53 dB at q=3 instead of ~66 dB, you're on an unoptimized build.

## Reproducing

```
cmake -B build-local                  # picks Release by default since aed6e37
cmake --build build-local --target gpr_tools -j 8
python3 tools/test/quant_calibration.py \
    --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/barn_sky_dngs \
    --max-images 4 \
    --qualities 0,1,2,3,4,5,6,7,8 \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration
```

CSV per-(image, quality) is written to `<out-dir>/calibration.csv`.
Add `--with-cnn` for CNN-corrected PSNR (slower; uses BIBO_1x
mpsgraph by default).
