# Quant calibration — rate-distortion findings

Empirical measurement for task #158 (CNN-aware per-subband quant
calibration, AccelIR style). Two complementary sweeps:

1. **Quality preset sweep** — codec's nine built-in `q=0..8` presets.
   Establishes the rate-distortion baseline the per-subband sweep must beat.
2. **Per-subband sweep** — `GPR_QUANT_OVERRIDE` lets us crank one
   subband's quant divisor independently. Identifies which subbands
   the codec can afford to throw away bits in.

Harness: `tools/test/quant_calibration.py` (modes `presets` / `per-subband`).

## Findings — 2026-05-24, M3 Max, barn_sky 4-image Z8 50 MP corpus

### Preset sweep (mean across corpus, Release build, peak=16383)

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

**The useful operating range is q=0..5** — beyond q=5 the codec spends
more bits for worse quality. Filed as task #159 for separate investigation
(suspected coefficient saturation when divisors get small).

### Per-subband sweep (half-res single-level + LL, mean across 2 Z8 frames)

Reference: encode at `q=3` defaults (no override). Each row is a single
slot of the level-1 quant table multiplied by N. PSNR vs the same-image
default-encode in bayer domain.

| Subband | mult | quant | KB/frame | bits saved | PSNR vs ref |
|---|---|---|---|---|---|
| ref (no override) | — | LH=24 HL=24 HH=12 | **4 526** | — | — |
| LH1 (vertical edges) | 1.5× | 36 | 4 395 | 2.9% | 70.4 dB |
| LH1 | 2.0× | 48 | 4 341 | 4.1% | 69.3 dB |
| LH1 | 4.0× | 96 | 4 306 | 4.9% | 68.4 dB |
| HL1 (horizontal edges) | 1.5× | 36 | 4 399 | 2.8% | 70.6 dB |
| HL1 | 2.0× | 48 | 4 347 | 4.0% | 69.5 dB |
| HL1 | 4.0× | 96 | 4 315 | 4.7% | 68.6 dB |
| **HH1 (diagonal)** | **1.5×** | **18** | **4 322** | **4.5%** | **73.5 dB** |
| **HH1** | **2.0×** | **24** | **4 211** | **7.0%** | **71.5 dB** |
| **HH1** | **3.0×** | **36** | **4 085** | **9.8%** | **71.5 dB** |
| **HH1** | **4.0×** | **48** | **4 032** | **10.9%** | **70.5 dB** |

### What this means

**HH1 (diagonal high-frequency) is the cheapest subband to drop bits in.**
At 4× multiplier, HH1 saves **10.9% of file size for only ~3 dB cost**
relative to the default-encode reference — over **2× the bits per dB**
that LH1 or HL1 give.

Why: diagonal edges in real raw Bayer are rare compared to vertical/
horizontal ones, so the encoder spends few bits there to begin with —
zeroing more of them removes redundancy that wasn't carrying signal.

**Recommended next step**: raise the default HH1 quant from 12 (q=3
default) to 36 (3× mult), saving ~10% of bitstream size with <2 dB
local PSNR cost. Even bigger savings are likely available once we
measure CNN recovery (see below).

## What's still pending in this thread

- **CNN-recovery sweep**. The current per-subband PSNR is bayer-domain,
  no CNN. The AccelIR question is "of the dB lost per subband bump, how
  much does a CNN trained on (codec_at_mult_x, codec_at_default) pairs
  give back". If HH1 4× loses ~3 dB but the CNN restores 2 dB, it's
  effectively free; if it restores 0 dB, the 10.9% is the real ceiling.
  The harness's `render_via_gpr2prores` path was inconclusive at first
  pass (PSNR floored at 26.77 dB due to demosaic-mismatch noise dominating).
  Next: apply the PyTorch BIBO_1x model directly to the half-res decoded
  bayer and compare bayer-domain, matching `test_cnn_regression.py`'s
  methodology.

- **Train a CNN on the more-aggressive HH1 quant.** Existing BIBO_1x was
  trained against the q=3 default codec output. To recover the additional
  HH1 loss, retrain on pairs from the modified-quant codec.

- **Sweep the other subbands** (LL2/HL2/HH2 = level 2, slots 4/5/6).
  Those slots aren't used in single-level + LL mode — need multi-level
  FUSED encoder which currently hardcodes `decimate=0` (see #157 follow-up).

## Build prerequisite

Numbers require a **Release** build (`-O2`). A `-O0` build shows ~12 dB
lower PSNR across the board AND ~6× slower decode (Agent B's commit
`aed6e37` defaults Release if no build type is specified).

## Reproducing

Build the test_fused_roundtrip helper (used by per-subband mode):

```
clang -O2 -I source/lib/vc5_decoder -I source/lib/vc5_encoder \
    source/app/test_fused_decode_roundtrip.c \
    build-local/source/lib/vc5_decoder/libvc5_decoder.a \
    build-local/source/lib/vc5_encoder/libvc5_encoder.a \
    build-local/source/lib/vc5_common/libvc5_common.a \
    build-local/source/lib/common/libcommon.a \
    -lpthread -lm -o build-local/bin/test_fused_roundtrip
```

Then run the sweep:

```
# Quality-preset baseline (gpr_tools legacy encoder)
python3 tools/test/quant_calibration.py --mode presets \
    --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/barn_sky_dngs \
    --max-images 4 --qualities 0,1,2,3,4,5,6,7,8 \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration

# Per-subband sweep (FUSED encoder + half-res + GPR_QUANT_OVERRIDE)
python3 tools/test/quant_calibration.py --mode per-subband \
    --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/barn_sky_dngs \
    --max-images 4 --slots 1,2,3 --multipliers 1.0,1.5,2.0,3.0,4.0 \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration
```

CSV outputs are written to `<out-dir>/calibration.csv` and
`<out-dir>/per_subband_sweep.csv`.
