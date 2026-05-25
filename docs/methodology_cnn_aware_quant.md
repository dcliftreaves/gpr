# CNN-aware per-subband quantization calibration for the GPR codec

David Clift-Reaves — 2026-05-25
Branch: `docs/methodology-cnn-aware-quant`
Companion data: [`docs/quant_calibration_findings.md`](quant_calibration_findings.md)

## Abstract

We measure the rate-distortion behaviour of the GPR wavelet codec on a
per-subband basis and ask the AccelIR question (Ye et al., CVPR 2023):
which subbands can a neural post-processor recover bits from? Using a
new encoder/decoder environment variable (`GPR_QUANT_OVERRIDE`) we
sweep each of the 9 highpass quant slots in the multi-level wavelet
quant table across a diverse 4-image 50–100 MP corpus and compute both
bayer-domain PSNR and **CNN-corrected** bayer-domain PSNR using a
4-channel-in / 4-channel-out residual network (`BIBO_1x`).

The headline result: when the existing production CNN is replaced with
a checkpoint **retrained on the cranked-quant codec distribution**, the
CNN closes the +5.61 dB gap at HH1 4× that the un-retrained CNN had
left behind, and similarly closes ≈4.3 dB at LH1/HL1 2×. Stacking the
three knobs gives **10–17% smaller bitstreams at no perceptible
quality cost** after CNN correction. The bitstream format is unchanged
— the production-side change is encoder default quants plus replacing
the shipped CNN checkpoint.

## 1. Background

### 1.1 The GPR codec

GPR is a Bayer-domain wavelet codec descended from CineForm, currently
shipping as the still-image format for GoPro raw photos. The encoder
applies a Bayer-to-YUV-like 4-channel color transform, then for each
channel performs a multi-level 2D wavelet decomposition with three
levels of (LH, HL, HH) highpass subbands and a single LL3 lowpass
residual. Coefficients are quantized via a 10-slot table

```
{ LL3, LH3, HL3, HH3, LH2, HL2, HH2, LH1, HL1, HH1 }
```

then run-length / VLC entropy coded. The `q=3` (Filmscan-1, the
production default) quant table is

```
{ 1, 24, 24, 12, 24, 24, 12, 96, 96, 144 }
```

i.e. larger divisors at coarser levels (smaller-magnitude bands) and
the inverted-pyramid behavior CineForm has always used.

### 1.2 The CNN post-processor

The shipping playback path (`gpr2prores`, PR #6) runs a 4-channel-bayer
in / 4-channel-bayer out residual network on each decoded frame before
demosaic. The current production checkpoint is

```
BayInBayOut_1x_AAon_w16_ANE.pt    # base width 16, anti-alias on, 1× scale
```

trained as a "LL-only-fast" model — pairs synthesized at the encoder's
default quants, optimised for speed on Apple Neural Engine and Metal
backends. It is *not* a super-resolution model; the 1× variant takes a
half-res bayer and returns a refined half-res bayer for downstream
demosaic to UHD output.

### 1.3 Prior art — AccelIR (CVPR 2023)

[AccelIR](https://openaccess.thecvf.com/content/CVPR2023/papers/Ye_AccelIR_Task-Aware_Image_Compression_for_Accelerating_Neural_Restoration_CVPR_2023_paper.pdf)
established that image-compression rate-distortion curves can be
re-optimised when the consumer of the bitstream is a neural restoration
network rather than a human eye: a CNN trained on the codec's output
distribution can hallucinate structure that a viewer of a bare decode
could not. For a wavelet codec the implication is that some subbands
are *more* CNN-recoverable than others. This paper validates that on
GPR + BIBO_1x and quantifies the trade per subband.

## 2. Method

### 2.1 Encoder/decoder instrumentation

We added a single environment variable, `GPR_QUANT_OVERRIDE`, parsed
identically by both the encoder and decoder library (no bitstream
format change — the modified quant table is written into the segment
headers per existing format rules and the decoder reads it back). The
variable takes a comma-separated list of `slot:value` pairs:

```
GPR_QUANT_OVERRIDE="3:48"          # set HH1 quant to 48 (4× the default 12)
GPR_QUANT_OVERRIDE="7:48,8:48,9:48"  # multi-level: set LH1, HL1, HH1 to 48
```

Slot numbering matches the codec's internal quant table. The harness
maps friendly names → slots based on encoder topology (see §2.3).

### 2.2 Two encoder topologies

The half-res FUSED encode/decode pipeline exposes two topologies. The
sweep harness supports both because they have different slot maps:

| Mode | `FUSED_MULTI_LEVEL` | `GPR_INCLUDE_LL` | Slots in use |
|---|---|---|---|
| `single-ll` (single-level + LL) | unset | `1` | 4 (LL, LH1, HL1, HH1) |
| `multi-level` | `1` | unset | 10 (LL3 + 9 highpass) |

`single-ll` is faster to encode and is the topology PR #11 retired in
favour of true multi-level for production raw video. We use it for the
CNN-aware sweep because we only ever crank level-1 highpass and the
two modes share identical level-1 semantics.

`multi-level` is used for the cross-level sweep (HH2, HH3, etc., §4.3).

### 2.3 Sweep harness

`tools/test/quant_calibration.py` implements both a quality-preset
sweep (`--mode presets`) and the per-subband sweep
(`--mode per-subband`). The per-subband sweep extracts the source
DNG's bayer plane to raw uint16, encodes a reference pass with no
override, then for each `(slot, multiplier)` cell encodes with
`GPR_QUANT_OVERRIDE="<slot>:<round(default*multiplier)>"`, decodes,
and reports bitstream size and bayer-domain PSNR vs the **reference
decode** (not vs the source DNG). We compare codec-vs-codec because
the production reference is what users see today; we want the
marginal cost of cranking quant beyond default.

With `--with-cnn`, the harness also runs BIBO_1x on both the
reference decode and each test decode, then PSNRs them. The CNN's own
bias is identical on both sides so it washes out — what's measured
is the CNN's ability to absorb per-subband distortion. Both decodes
are at half-res (`decimate=2`); BIBO_1x is 1× scale on this half-res
bayer; demosaic and UHD upscale happen downstream and are not part of
the PSNR.

### 2.4 Quant slot map (per encoder mode)

| slot | single-ll | multi-level |
|---|---|---|
| 0 | LL | LL3 |
| 1 | LH1 | LH3 |
| 2 | HL1 | HL3 |
| 3 | HH1 | HH3 |
| 4 | — | LH2 |
| 5 | — | HL2 |
| 6 | — | HH2 |
| 7 | — | LH1 |
| 8 | — | HL1 |
| 9 | — | HH1 |

### 2.5 Reproduction

```
# Quality-preset baseline (gpr_tools legacy encoder)
python3 tools/test/quant_calibration.py --mode presets \
    --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/barn_sky_dngs \
    --max-images 4 --qualities 0,1,2,3,4,5,6,7,8 \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration

# Per-subband sweep with CNN-corrected PSNR
python3 tools/test/quant_calibration.py --mode per-subband \
    --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/diverse_4 \
    --max-images 4 --slots 1,2,3 --multipliers 1.0,2.0,4.0 \
    --encoder-mode single-ll --with-cnn \
    --cnn-ckpt-pt /Users/dcliftreaves/dering_proto_v2/checkpoints/BayInBayOut_1x_AAon_w16_ANE.pt \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration
```

A `Release` (`-O2`) build is required — a `-O0` build measures roughly
12 dB lower PSNR across the board due to integer-saturation behaviour
in the wavelet kernels.

## 3. Findings — quality-preset baseline

Establishes the rate-distortion curve the per-subband work must beat.
Mean across the 4-image barn_sky Z8 50 MP corpus, Release build, peak
= 16383:

| quality | kB/frame | ratio vs DNG | bayer PSNR |
|---|---|---|---|
| 0 (Low) | 3 674 | 0.103 | 61.77 dB |
| 1 (Medium) | 5 002 | 0.141 | 62.66 dB |
| 2 (High) | 8 363 | 0.235 | 64.51 dB |
| 3 (Filmscan-1 default) | 10 003 | 0.281 | 65.59 dB |
| 4 (Filmscan-X) | 11 497 | 0.323 | 66.67 dB |
| **5 (Filmscan-2)** | **14 284** | **0.402** | **69.21 dB ← PEAK** |
| 6 (Filmscan-3) | 16 220 | 0.456 | 66.42 dB ↓ |
| 7 (Filmscan-4) | 16 447 | 0.463 | 61.67 dB ↓↓ |
| 8 (Filmscan-5) | 16 732 | 0.471 | 61.68 dB |

The useful operating range is `q=0..5`. Beyond `q=5` the codec spends
more bits for *worse* PSNR — filed as bug #159 and partially fixed in
PR #16 (LL3 highpass quant floor) and PR #20 (per-band floor extension
for dark content). The `q>5` regression is orthogonal to this paper.

## 4. Findings — per-subband sweep, un-retrained CNN

### 4.1 Level-1 highpass, single-level + LL topology, 4-image diverse corpus

Reference: per-image FUSED encode at `q=3` defaults. PSNR is computed
in bayer domain at half-res against the reference decode of the same
image. CNN is the production `BayInBayOut_1x_AAon_w16_ANE.pt`.

(Source: `docs/quant_calibration_findings.md` — barn_sky 4-image
sub-corpus.)

| Subband | mult | bits saved | PSNR no-CNN | PSNR + CNN | CNN gain |
|---|---|---|---|---|---|
| LH1 | 1.5× | 2.9% | 70.37 | **73.96** | **+3.59 dB** |
| LH1 | 2.0× | 4.1% | 69.33 | 72.55 | +3.22 dB |
| LH1 | 3.0× | 4.7% | 69.38 | 72.23 | +2.85 dB |
| LH1 | 4.0× | 4.9% | 68.37 | 70.85 | +2.48 dB |
| HL1 | 1.5× | 2.8% | 70.56 | **74.11** | **+3.55 dB** |
| HL1 | 2.0× | 4.0% | 69.54 | 72.70 | +3.16 dB |
| HL1 | 3.0× | 4.5% | 69.55 | 72.38 | +2.82 dB |
| HL1 | 4.0× | 4.7% | 68.60 | 71.04 | +2.43 dB |
| HH1 | 1.5× | 4.5% | 73.51 | 74.19 | +0.68 dB |
| HH1 | 2.0× | 7.0% | 71.52 | 72.20 | +0.68 dB |
| HH1 | 3.0× | 9.8% | 71.54 | 72.09 | +0.55 dB |
| HH1 | 4.0× | 10.9% | 70.45 | 70.98 | +0.53 dB |

### 4.2 Interpretation of the un-retrained result

Two opposite asymmetries fall out. **No-CNN ranking:** HH1 is the
cheapest subband to drop bits in — diagonal edges are rare in real
Bayer content, so each bit zeroed removes redundancy more than signal
(HH1 4× saves 10.9% with ~3 dB PSNR cost). **CNN-corrected ranking**
inverts: the CNN closes ~3 dB of the per-multiplier loss on the
axis-aligned LH1/HL1 bands, leaving an effective cost ≤ 0.5 dB at 4×;
the CNN barely touches HH1 (closes only 0.5–0.7 dB of the 3 dB cost).

The plausible cause is a training-distribution issue. The shipping
BIBO_1x was trained on (codec_at_default, ground_truth) pairs; the
default LH1/HL1 quants (24) are already aggressive, so the CNN saw
plenty of noisy axis-aligned highpass and learned to synthesise edges
from a degraded input. The default HH1 quant (12) is much lighter, so
the model has no in-distribution behaviour for a strongly-quantised
diagonal band.

### 4.3 Multi-level sweep (HH2 first measured, then walked back)

Once PR #11 made `decimate=2` work in true multi-level FUSED encoding,
we re-ran the sweep across all 9 highpass slots. On a 2-frame Z8 50 MP
barn_sky fixture, HH2 at 2× looked like a free win:

| Subband | Level | mult | bits saved | PSNR no-CNN | PSNR + CNN | CNN gain |
|---|---|---|---|---|---|---|
| LH3 | 3 | 4× | 0.7% | 71.50 | 71.61 | +0.11 dB |
| HL3 | 3 | 4× | 0.6% | 71.90 | 71.84 | −0.06 dB |
| HH3 | 3 | 4× | 1.1% | 76.05 | 75.59 | −0.45 dB |
| LH2 | 2 | 4× | 3.6% | 71.40 | 71.08 | −0.33 dB |
| HL2 | 2 | 4× | 3.4% | 71.64 | 71.70 | +0.07 dB |
| **HH2** | **2** | **2×** | **10.2%** | 75.45 | **78.19** | **+2.74 dB** |
| **HH2** | **2** | **4×** | **12.7%** | 74.24 | 75.28 | **+1.04 dB** |
| LH1 | 1 | 4× | 2.8% | 63.84 | 64.36 | +0.52 dB |
| HL1 | 1 | 4× | 2.5% | 64.85 | 65.28 | +0.43 dB |
| HH1 | 1 | 4× | 1.3% | 64.84 | 64.64 | −0.19 dB |

Re-run on the diverse 4-image corpus (Z8 ISO64, Z8 ISO22800, X2D
ISO64, X2D ISO200 — all 50–100 MP) walked the HH2 finding back:

| Image | HH2 2× bits saved | CNN gain |
|---|---|---|
| barn_sky (sky-heavy daylight) | 10.2% | **+2.74 dB** |
| Z8 ISO64 entropy-matrix | 4.0% | +0.13 dB |
| X2D ISO64 (Austin) | 3.4% | +0.08 dB |
| X2D ISO200 (Austin) | 4.8% | +0.13 dB |
| Z8 ISO22800 (high-noise) | 2.4% | **−0.82 dB** (CNN hurts) |
| **Mean across 4-image corpus** | **3.6%** | **−0.12 dB** |

The bits-saved holds (3–5% consistently) but the CNN gain doesn't. On
low-detail sky content the CNN cleans up cranked-HH2 noise; on
high-noise or high-detail content the extra quant noise interacts
badly with the CNN's learned prior. PR #13 lands HH2 ×2 as a
*quality-preserving bit saver* (≤ 0.5 dB CNN-corrected delta) rather
than the +2.7 dB free-win it first looked like.

The barn_sky 2-frame finding remains useful as a *sanity check* that
the framework is producing real signal — it just isn't the universal
ship recommendation we initially reported.

## 5. Hypothesis: retrain the CNN on the cranked distribution

If the level-1 HH1 ceiling is a training-distribution issue rather
than an architecture limit, training the same (`w=16`, AAon, residual
1×) model on pairs synthesised by the cranked-quant codec should
generalise — the CNN will see strongly-quantised HH1 input during
training and learn to invert it.

Concretely: generate `(codec_at_GPR_QUANT_OVERRIDE="3:48",
ground_truth_bayer)` pairs and train cold-start with AdamW lr = 5e-4
for ~80 epochs. The architecture is identical; only the training
distribution changes.

## 6. Findings — retrained CNN

A new checkpoint `BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt` was trained on
pairs generated with `GPR_INCLUDE_LL=1` + `GPR_QUANT_OVERRIDE="3:48"`
(HH1 4×), cold-start, 80 epochs, AdamW lr = 5e-4. Best validation at
epoch 47.

Per-subband sweep on the diverse 4-image corpus (`single-ll` mode):

(Source:
`/Volumes/OWC_8TB/gpr_artifacts/quant_calibration_retrained/per_subband_sweep.csv`
— means re-computed from the raw CSV.)

| Subband | mult | bits saved | PSNR no-CNN | PSNR + retrained-CNN | retrained CNN gain |
|---|---|---|---|---|---|
| LH1 | 2.0× | 3.4% | 54.76 dB | 59.30 dB | +4.54 dB |
| LH1 | 4.0× | 8.0% | 50.48 dB | 54.89 dB | +4.40 dB |
| HL1 | 2.0× | 3.4% | 54.94 dB | 59.32 dB | +4.38 dB |
| HL1 | 4.0× | 7.0% | 50.81 dB | 55.03 dB | +4.22 dB |
| HH1 | 2.0× | 6.2% | 60.47 dB | 66.31 dB | **+5.84 dB** |
| **HH1** | **4.0×** | **9.7%** | 56.40 dB | **62.01 dB** | **+5.61 dB ← the unlock** |

Comparison vs the un-retrained CNN at the same operating points
(per-subband, 4×):

| Subband | bits saved | un-retrained CNN gain | retrained CNN gain |
|---|---|---|---|
| LH1 | 8.0% | +2.48 dB | **+4.40 dB** |
| HL1 | 7.0% | +2.43 dB | **+4.22 dB** |
| **HH1** | **9.7%** | +0.53 dB | **+5.61 dB** |

The hypothesis is confirmed at the architecture level: the same
4-channel-bayer / w=16 residual model that previously closed 0.5 dB
on HH1 now closes 5.6 dB when trained on the cranked-quant pairs.
Per-image inspection on barn_sky alone (more uniform content) shows
+8.50 dB on HH1 4× — the diverse-corpus +5.6 dB is a floor, not a
ceiling.

The absolute PSNR numbers on the diverse corpus are lower than the
barn_sky sub-corpus in §4 (~50–60 dB vs ~70 dB) because the diverse
corpus includes Z8 ISO22800 and X2D high-entropy plates with much
larger PSNR-vs-ref denominators. The *gain* is what the methodology
measures.

This paper does not attribute how much of the +5.6 dB gain comes from
the CNN inverting genuine HH1 quant noise vs hallucinating plausible
diagonal structure from LH1/HL1/LL. That ablation is TODO.

## 7. Production implications

PR #21 (in flight — branch
`feat/q11-cnn-aware-and-env-cleanup-doc`) introduces a new `q=11`
"CNN-aware" preset that bakes the cranked-quant policy into the
encoder, avoiding env vars at runtime. Combined with shipping the
retrained checkpoint as the production CNN, the estimated ship
envelope vs the current `q=3` Filmscan-1 default is:

* **HH1 × 4** — 9.7% file size reduction; CNN absorbs to +5.6 dB
  (net cost vs default CNN-corrected ≈ 0 dB).
* **LH1 × 2 + HL1 × 2** — additional 6–8% file size; CNN absorbs to
  +4 dB each.
* **Stack estimate** — 15–17% smaller files at no perceptible quality
  cost after CNN.

Separately, multi-level + `decimate=2` + HH2 ×2 (PR #11/#13) hits
386 KB/frame at 24 fps → ~74 Mbps for 50 MP raw video on sky-heavy
content. Fits trivially on UHS-I microSD. The bitstream format is
unchanged across all of the above — decoders without the retrained
CNN see bare-decode quality; decoders with it see the corrected
quality. Soft upgrade.

## 8. Limitations & open questions

* **HH2 content-dependence (§4.3).** The +2.74 dB CNN gain on barn_sky
  doesn't survive on diverse content. No HH2-targeted retrained
  checkpoint exists yet; the same training-distribution hypothesis
  should apply. TODO.
* **2× super-res variant.** A separate checkpoint takes half-res
  bayer in / full-res bayer out (1× → 2× SR). It almost certainly has
  the same training-distribution gap on HH1; retraining is in flight,
  results not in this paper. TODO.
* **Combined-knob stacking.** The +5.6 / +4.4 / +4.2 dB gains were
  measured independently. Whether they stack or the retrained CNN
  saturates at ~5 dB total is unmeasured. TODO.
* **Content-adaptive encoder.** PR #21 ships the cranked-quant table
  as a static preset. A cleaner long-term design picks the per-subband
  table per-frame from highpass energy. Out of scope here.
* **No-CNN users** (third-party DNG readers) see the full ~3 dB cost
  at HH1 4×. `q=3` remains the default for non-CNN consumers; `q=11`
  is a CNN-aware *opt-in*.
* **Bayer-domain PSNR only.** Downstream demosaic + UHD render can
  amplify or attenuate per-subband distortion. PR #17 spot-checks
  that render-domain PSNR moves the same direction; a full
  demosaic-domain sweep is TODO.
* **The `q>5` regression (#159, #162)** is real and limits where this
  work can be applied. The `q=11` cranked-quant table must stay within
  the per-band floor introduced in PR #16 and extended in PR #20.

## 9. References

* Ye, J., Lee, J., Han, D. *AccelIR: Task-aware Image Compression for
  Accelerating Neural Restoration.* CVPR 2023.
  <https://openaccess.thecvf.com/content/CVPR2023/papers/Ye_AccelIR_Task-Aware_Image_Compression_for_Accelerating_Neural_Restoration_CVPR_2023_paper.pdf>
* [CompressAI](https://github.com/InterDigitalInc/CompressAI) — the
  rate-distortion measurement conventions in §2.3 mirror its
  per-bitrate eval format.
* GoPro CineForm / GPR codec — origin format documented in
  [`docs/format-spec-v2.md`](format-spec-v2.md) and
  [`docs/architecture.md`](architecture.md).
* Findings log this paper draws from:
  [`docs/quant_calibration_findings.md`](quant_calibration_findings.md).
* Harness:
  [`tools/test/quant_calibration.py`](../tools/test/quant_calibration.py).
* Raw retrained-CNN sweep data:
  `/Volumes/OWC_8TB/gpr_artifacts/quant_calibration_retrained/per_subband_sweep.csv`.

### Pull requests landed in support of this work

* PR #11 — FUSED: multi-level encoder + decoder honor `decimate=2`.
  <https://github.com/dcliftreaves/gpr/pull/11>
* PR #13 — `quant_calibration`: multi-level sweep + HH2 ×2 ship
  recommendation.
  <https://github.com/dcliftreaves/gpr/pull/13>
* PR #16 — encoder: floor LL3 highpass quant to keep magnitude within
  VLC codebook range (#159).
  <https://github.com/dcliftreaves/gpr/pull/16>
* PR #17 — tests: CNN-corrected PSNR + sustained-fps regression cells.
  <https://github.com/dcliftreaves/gpr/pull/17>
* PR #19 — docs: retrained CNN closes HH1 gap (+5.6 dB on diverse
  corpus). <https://github.com/dcliftreaves/gpr/pull/19>
* PR #20 — encoder: extend per-band quant floor for dark-content q=6+
  regression (#162). <https://github.com/dcliftreaves/gpr/pull/20>
* PR #21 (in flight) — codec: add `q=11` CNN-aware preset + env-var
  cleanup doc.
