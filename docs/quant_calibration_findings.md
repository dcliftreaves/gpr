# Quant calibration — initial rate-distortion sweep

First-pass measurement for task #158 (CNN-aware per-subband quant
calibration, AccelIR style). Sweeps the codec's built-in quality
presets across a Z8 50 MP DNG corpus and records (bits, bayer-PSNR)
per (image, quality). This is the rate-distortion curve the
per-subband sweep needs to beat.

Harness: `tools/test/quant_calibration.py`.

## Findings — 2026-05-24, M3 Max, barn_sky 4-image corpus

Mean over 4 Z8 50 MP `Z8Z_133*.dng` source frames:

| quality | kB/frame | ratio vs DNG | bayer PSNR |
|---|---|---|---|
| 0 (Low) | 3 674 | 0.103 | 49.72 dB |
| 1 (Medium) | 5 002 | 0.141 | 50.61 dB |
| 2 (High) | 8 363 | 0.235 | 52.46 dB |
| **3 (Filmscan-1 default)** | **10 003** | **0.281** | **53.55 dB** |
| 4 (Filmscan-X) | 11 497 | 0.323 | 54.62 dB |
| **5 (Filmscan-2)** | **14 284** | **0.402** | **57.17 dB ← PEAK** |
| 6 (Filmscan-3) | 16 220 | 0.456 | 54.38 dB ↓ |
| 7 (Filmscan-4) | 16 447 | 0.463 | 49.63 dB ↓↓ |
| 8 (Filmscan-5) | 16 732 | 0.471 | 49.64 dB |

## What this means

**The useful operating range is q=0..5.** Beyond q=5 the codec
allocates more bits but quality regresses. The drop from 57.17 dB
(q=5) to ~49.6 dB (q=7,8) at 50 MP smells like a coefficient
overflow that triggers when quants get small enough.

This matches a long-standing "Q8 overflow" note in working memory.
The most likely culprit: LL3 coefficient magnitudes for 14-bit
input under the smallest-quant presets exceed the rANS class-15
ceiling (±2047) and get clipped. The `FUSED_LL3_EXTRA_DIVISOR = 16`
in `source/lib/vc5_decoder/fused_decode.c` is the existing
mitigation; it likely needs to scale with the chosen quant.

## Implication for #158 (CNN-aware per-subband calibration)

- The "rate budget" for per-subband sweeps should be anchored at
  q=3 (the default) and q=5 (the empirical quality peak), not at
  the nominal q=8 ceiling.
- Bit savings target: going from q=5 to q=3 saves ~4.3 MB/frame
  for a ~3.6 dB quality drop. If a CNN closes 2+ dB of that gap
  on real content, we get a clear win.
- Next experiment (waiting on per-subband env-var override in
  encoder + decoder): sweep one subband slot at a time, holding
  others at q=3 defaults. The subbands the CNN closes "for free"
  become the ones we crank up in production.

## Reproducing

```
python3 tools/test/quant_calibration.py \
    --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/barn_sky_dngs \
    --max-images 4 \
    --qualities 0,1,2,3,4,5,6,7,8 \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration
```

CSV per-(image, quality) is written to `<out-dir>/calibration.csv`.
Add `--with-cnn` for CNN-corrected PSNR (slower; uses BIBO_1x
mpsgraph by default).
