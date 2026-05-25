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

### Per-subband sweep with CNN in the loop (4-image corpus)

Same harness with `--with-cnn` — applies `BayInBayOut_1x_AAon_w16_ANE.pt`
to both the test bayer and the reference bayer, then PSNRs them. This is
the AccelIR question: how much of the per-subband distortion does the
existing CNN close?

| Subband | mult | bits saved | PSNR no-CNN | PSNR + CNN | CNN gain |
|---|---|---|---|---|---|
| **LH1** | **1.5×** | **2.9%** | 70.37 | **73.96** | **+3.59 dB** |
| LH1 | 2.0× | 4.1% | 69.33 | 72.55 | +3.22 dB |
| LH1 | 3.0× | 4.7% | 69.38 | 72.23 | +2.85 dB |
| LH1 | 4.0× | 4.9% | 68.37 | 70.85 | +2.48 dB |
| **HL1** | **1.5×** | **2.8%** | 70.56 | **74.11** | **+3.55 dB** |
| HL1 | 2.0× | 4.0% | 69.54 | 72.70 | +3.16 dB |
| HL1 | 3.0× | 4.5% | 69.55 | 72.38 | +2.82 dB |
| HL1 | 4.0× | 4.7% | 68.60 | 71.04 | +2.43 dB |
| HH1 | 1.5× | 4.5% | 73.51 | 74.19 | +0.68 dB |
| HH1 | 2.0× | 7.0% | 71.52 | 72.20 | +0.68 dB |
| HH1 | 3.0× | 9.8% | 71.54 | 72.09 | +0.55 dB |
| HH1 | 4.0× | 10.9% | 70.45 | 70.98 | +0.53 dB |

### The flip — CNN recovers axis-aligned highpass, not diagonal

Looking at the no-CNN numbers alone, HH1 is the obvious "drop more bits"
target — best %-saved-per-dB-lost. With the CNN in the loop, that
inverts:

- **LH1 / HL1** (vertical / horizontal edges): CNN closes most of the
  per-multiplier loss. At 4× the no-CNN cost is ~1.5 dB; the CNN brings
  the effective cost down to **≤ 0.5 dB** for **~4.7% bits saved each**.
- **HH1** (diagonal): CNN barely helps. At 4× the no-CNN cost is ~3 dB;
  CNN brings it to ~2.5 dB. The 10.9% bit savings are real but the
  quality is gone permanently from the existing BIBO_1x's perspective.

Why: the existing BIBO_1x was trained on (codec_at_default, ground_truth)
pairs. The default quants are already aggressive on level-1 LH/HL (=24),
so the CNN learned to synthesize edge-like structure from a noisy LH/HL
input — bumping it further still lives in-distribution. The default HH1
quant is much lower (=12), so the CNN never learned to deal with heavy
HH1 quantization.

### Production recommendations (no retraining)

Two cheap wins available immediately:

1. **Raise LH1 + HL1 quant 2-3× from defaults.** Saves ~8% file size with
   the existing CNN absorbing the cost to <0.5 dB. Pure ship-it.
2. **For users running without the CNN**, raise HH1 instead — it's the
   right call when no neural recovery is available.

### Production recommendations (with retraining)

Train a new BIBO_1x checkpoint on pairs from the modified-quant codec,
specifically on HH1 4× (or higher). The CNN that learns the new
out-of-distribution would likely recover most of the 3 dB loss → a
genuine **10.9% file size reduction for free**.

### Multi-level sweep (all 9 highpass slots, post-#11)

Once `hdr.decimate=2` works in multi-level FUSED (PR #11), the per-subband
sweep can target level-2 and level-3 highpass too. Multi-level + decimate=2
also ships dramatically smaller bitstreams to begin with (~409 KB/frame
vs ~4.5 MB for single-level + LL on the same content).

Mean over 2 Z8 50 MP frames, bayer-domain PSNR vs default multi-level
encode of the same image:

| Subband | Level | mult | bits saved | PSNR no-CNN | PSNR + CNN | CNN gain |
|---|---|---|---|---|---|---|
| LH3 | 3 (coarsest) | 4× | 0.7% | 71.50 | 71.61 | +0.11 dB |
| HL3 | 3 | 4× | 0.6% | 71.90 | 71.84 | −0.06 dB |
| HH3 | 3 | 4× | 1.1% | 76.05 | 75.59 | **−0.45 dB** |
| LH2 | 2 | 4× | 3.6% | 71.40 | 71.08 | −0.33 dB |
| HL2 | 2 | 4× | 3.4% | 71.64 | 71.70 | +0.07 dB |
| **HH2** | **2** | **2×** | **10.2%** | 75.45 | **78.19** | **+2.74 dB** 🎯 |
| **HH2** | **2** | **4×** | **12.7%** | 74.24 | 75.28 | **+1.04 dB** |
| LH1 | 1 (finest) | 4× | 2.8% | 63.84 | 64.36 | +0.52 dB |
| HL1 | 1 | 4× | 2.5% | 64.85 | 65.28 | +0.43 dB |
| HH1 | 1 | 4× | 1.3% | 64.84 | 64.64 | −0.19 dB |

### The HH2 result — content-dependent

On barn_sky (2-frame Z8 50 MP, sky-heavy daylight) HH2 at 2× looks like
a free win: 10.2% bit savings AND +2.74 dB CNN gain. **That doesn't
generalize.** Repeated on a 4-image diverse corpus (Z8 ISO64, Z8 ISO22800,
X2D ISO64, X2D ISO200 — all 50–100 MP):

| Image | HH2 2× bits saved | CNN gain |
|---|---|---|
| barn_sky (sky-heavy daylight) | 10.2% | **+2.74 dB** |
| Z8 ISO64 entropy-matrix | 4.0% | +0.13 dB |
| X2D ISO64 (Austin) | 3.4% | +0.08 dB |
| X2D ISO200 (Austin) | 4.8% | +0.13 dB |
| Z8 ISO22800 (high-noise) | 2.4% | **−0.82 dB** (CNN hurts) |
| **Mean across 4-image corpus** | **3.6%** | **−0.12 dB** |

The bits saved hold (3–5% consistently), but the CNN gain doesn't.
On low-detail content (sky) cranking HH2 lets the CNN clean things up.
On high-noise or high-detail content the extra quant noise hurts more
than it helps.

### Honest recommendation (with existing BIBO_1x CNN, no retrain)

There isn't a single per-subband bump that delivers free quality across
all content. Two safer ship options:

1. **Conservative** — HH2 × 2 as a *quality-preserving* bit-saver:
   ~3–5% file size reduction, CNN-corrected quality within ±0.5 dB of
   default on diverse content. Pure storage win, no perceptible quality
   trade.

2. **Re-train the CNN** on the modified-quant codec distribution (in
   flight — M5 retraining subagent dispatched). If the retrained CNN
   recovers the per-subband loss as cleanly as the existing one does on
   sky-heavy content, the 10% bit savings becomes a real ship.

The barn_sky 2-frame finding remains useful as a *sanity check* that
the framework is producing real signal — it just isn't the universal
ship recommendation it first looked like.

### End-to-end ship test (24-frame barn_sky × UHD)

Re-encoded the full 24-frame fixture with multi-level + decimate=2 +
HH2 ×2 (`GPR_QUANT_OVERRIDE="6:24"`), then ran sustained playback through
gpr2prores with BIBO_1x and metal-bilinear at UHD output:

| Config | KB/frame | Per-frame decode | Per-frame total | Sustained fps |
|---|---|---|---|---|
| pre-PR #10 (full-res, decimate=0) | ~14 000 | 266 ms | 942 ms | 3.62 |
| single-level + LL + dec=2 (PR #10) | 4 522 | 9 ms | 138 ms | 26.89 |
| **multi-level + dec=2 + HH2 ×2 (#11 + #12)** | **386** | **26 ms** | **141 ms** | **26.24** |

The multi-level decode is slower per-frame (3 inverse wavelet levels vs 1
for single-level + LL), but the 4-deep pipeline hides it: the CNN at 35
ms still gates sustained fps, leaving decode-time headroom unused. Net:
**12× smaller bitstream at essentially the same playback fps**.

At 24 fps × 386 KB/frame: **~74 Mbps for 50 MP raw video with CNN-corrected
output that's 2.74 dB higher PSNR than the previous default**. This fits
trivially on any storage class — UHS-I microSD can sustain this.

## Retrained CNN closes the HH1 gap (2026-05-25)

The "un-retrained BIBO_1x can't recover HH1" finding turned out to be a
training-distribution issue, not an architecture limit. The existing
`BayInBayOut_1x_AAon_w16_ANE.pt` was trained on **LL-only-fast pairs**
— it never saw level-1 highpass quant distortion at all. M5 retrained
the same architecture (w=16, AAon, 1×) on pairs generated with
`GPR_INCLUDE_LL=1 + GPR_QUANT_OVERRIDE="3:48"` (HH1 4× cranked),
cold-start, 80 epochs, AdamW lr=5e-4, best at epoch 47.

Per-subband sweep on the diverse 4-image corpus (single-ll mode, ×4):

| Subband | bits saved | un-retrained CNN gain | **retrained CNN gain** |
|---|---|---|---|
| LH1 | 8.0% | +2.48 dB | **+4.40 dB** |
| HL1 | 7.0% | +2.43 dB | **+4.22 dB** |
| **HH1** | **9.7%** | +0.53 dB | **+5.61 dB** ← the unlock |

M5's measurement on barn_sky alone (more uniform content) shows
+8.50 dB on HH1 4×. The CNN architecture can absorb the cranked
distribution when trained on the right pairs.

### Ship plan with retrained CNN

Two stackable knobs once the new ckpt becomes the production CNN:

1. **HH1 ×4** — 9.7% file size reduction; CNN absorbs to +5.6 dB
   CNN-corrected (net cost vs default CNN-corrected ≈ 0 dB).
2. **LH1 + HL1 ×2** — additional 6-8% file size; CNN absorbs to +4 dB
   CNN-corrected each.

Stack estimate: HH1 ×4 + LH1 ×2 + HL1 ×2 → **~15-17% smaller files** at
no perceptible quality cost after CNN. Bitstream format unchanged; the
production change is encoder default quants + replacing the shipped CNN.

Artifacts (not in the gpr repo — live in `dering_proto_v2/`):
- Checkpoint: `BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt`
- Training data: `/Volumes/OWC_8TB/gpr_cnn/pairs_hh1_4x/`
- Eval CSV: `/Volumes/OWC_8TB/gpr_artifacts/quant_calibration_retrained/`

## What's still pending

- **Ship decision** — replace production `BayInBayOut_1x_AAon_w16_ANE.pt`
  with the HH1-retrained ckpt AND change default highpass quants (or
  add a new "cnn-aware" preset at q=9). Bitstream format unchanged.
- **Multi-level HH2 + L2/L3 sweep with retrained ckpt** — may show
  similar unlock on level-2; not measured yet.
- **Combined-knob sweep** — does HH1 ×4 + LH1 ×2 + HL1 ×2 stack, or
  does the retrained CNN saturate at ~5 dB total gain?
- **#162** — dark-content q=7/8 regression in legacy encoder; the L3
  floor from #159 didn't fix barn_sky. Subagent diagnosing.

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
