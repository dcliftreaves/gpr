# PREVIEW restoration — per-channel CNN decomposition (path-2 plan)

**Date:** 2026-05-29
**Status:** PLAN — supersedes the "distill the blend into one CNN" path-2 sketch
**Context:** Path-1 LAB-swap blend (commit `f27ea3f`) confirmed that BIDO's luma
+ BIBO's chroma improves LPIPS on 3 of 4 gate images and improves ΔE p95
across the board. But the blend still FAILs PREVIEW on the hard images
because BIBO's chroma (trained against SL codec, cross-paired) isn't a
clean match to ml2_q3_dec2.

The next architectural pivot: **train per-channel models in LAB or YCbCr
space, sized differently per channel, recombined at output**. Originally
prompted by user observation that the matched BIDO has *good luminance*
but only chroma is broken.

## Why per-channel decomposition is the right move

Three independent reasons converge:

1. **L1-on-RGB has no chroma-aware penalty.** A 5-unit shift in R looks
   identical to a 5-unit shift in G to RGB-L1, but they have completely
   different perceptual color impact (ΔE2000). Joint demosaic CNNs
   trained on L1-RGB consistently drift chroma; the path-1 LAB-swap
   experiment proved this empirically.
2. **Channels have different signal statistics.** Luminance is
   high-frequency, edge-dominated, sharpness-critical. Chroma is
   low-frequency, smooth, magnitude-dominated. A single network has to
   compromise; separate networks can specialize.
3. **Smaller networks per channel can total fewer params than one big
   network.** The user's intuition: 3 small CNNs running sequentially
   can match a single large one in capacity while peaking at lower
   memory and being independently tunable.

## Three architectural variants

Listed in increasing complexity. Recommend starting at #1.

### Variant A — Three independent per-channel CNNs (the user's proposal)

```
Bayer (4ch half-res)
   │
   ├── Y_CNN   (F_ane_no_sr_w16,  ~315K params)  → Y  channel (full-res)
   ├── Cb_CNN  (F_ane_no_sr_w8,    ~80K params)  → Cb channel (full-res)
   └── Cr_CNN  (F_ane_no_sr_w8,    ~80K params)  → Cr channel (full-res)

Recombine: YCbCr → RGB via standard ITU-R BT.601 / BT.709 matrix.
```

**Param count:** ~475K total. **2.3× smaller than BIDO w24** (722K) and
**62% smaller than w32** (1.27M). Sequential inference uses peak memory
equal to the largest model (~315K params).

**Why YCbCr not LAB:**
- YCbCr conversion is a fixed linear matrix (cheap, exact).
- LAB requires sRGB → linear → XYZ → LAB (3 stages, non-linear).
- LAB IS more perceptual, but the network can learn perceptual
  weighting via its loss, not the colorspace.
- BT.709 is the standard for video pipelines (Pi 5 → desktop).

**Per-channel losses:**

| channel | loss | reasoning |
|---|---|---|
| Y | multi-scale L1 + LPIPS-alex γ=0.10 | sharpness-focused, matches current BIDO recipe |
| Cb, Cr | L1 + Charbonnier (robust) | chroma-fidelity-focused, no perceptual term needed (chroma is smooth) |

**Why no LPIPS on chroma:** AlexNet was trained on luminance-dominated
ImageNet; LPIPS-alex doesn't carry perceptual color information.
Spending compute on it for chroma channels is pure overhead.

### Variant B — Shared backbone, three output heads

```
Bayer (4ch half-res)
   │
   ▼
Shared backbone  (F_ane stem, ~200K params)
   │
   ├── Y head    (~50K params)  → Y  (full-res)
   ├── Cb head   (~25K params)  → Cb (full-res)
   └── Cr head   (~25K params)  → Cr (full-res)
```

**Param count:** ~300K total. **Less than variant A**, single forward pass.

**Pros:** Shared early features (Bayer decimation artifacts are
channel-agnostic — edges and structural priors transfer); single inference.

**Cons:** Loses the "independently tunable" property; if Y loss drives
the shared backbone in a direction that hurts chroma, hard to fix.

### Variant C — Two-CNN: luma + joint chroma

```
Bayer (4ch half-res)
   │
   ├── Y_CNN   (F_ane_no_sr_w16, ~315K params) → Y  (full-res)
   └── CbCr_CNN (F_ane_no_sr_w8,  ~80K params) → Cb,Cr 2-channel output
```

**Param count:** ~395K total. Two forward passes.

**Why:** Cb and Cr are correlated in natural images (skin tones, sky,
foliage all live on smooth curves in the Cb/Cr plane). A joint CbCr
network can exploit that correlation; truly independent Cb-vs-Cr
networks can't.

## Recommendation — Start with Variant A, then converge

Variant A is the user's idea, is the simplest, exposes the per-channel
tuning we want, and has clear param-budget headroom. If it works,
variants B and C are optimization paths after the architecture is
proven.

## Concrete first run

```
Models in tools/cnn/model.py:
  - F_ane_no_sr_w16_y    (matches existing F_ane_no_sr_w16 output spec but 1ch)
  - F_ane_no_sr_w8_chroma (new, narrower variant of F_ane_no_sr, 1ch output)

Training scripts:
  - train.py --variant F_ane_no_sr_w16_y --output-channel Y --loss-domain ycbcr
  - train.py --variant F_ane_no_sr_w8_chroma --output-channel Cb --loss-domain ycbcr
  - train.py --variant F_ane_no_sr_w8_chroma --output-channel Cr --loss-domain ycbcr

Dataset: existing tiles_ml2_q3_dec2_dmsr_gate.npz (the matched corpus).
At training time, convert tgt_rgb → YCbCr, slice the channel the CNN
is training on.

Loss:
  Y: multiscale_l1(pred_Y, tgt_Y) + 0.10 * lpips_alex(pred_Y → broadcast 3ch, tgt_Y → broadcast 3ch)
  Cb/Cr: l1(pred, tgt) + 0.10 * charbonnier(pred, tgt)

Training time: ~3 hr per channel on M5 MPS (≈ existing BIDO time / 1.5
because each is 1-channel out, smaller network).

Total wall: ~9 hr for all three on a single M5, or ~3 hr if we train
them in parallel on different machines (M3 Max + M5).

Inference: 3 sequential forward passes on M3 Max MPS, recombine via
BT.709 inverse. Estimated total decode time per frame: ~30-50 ms (vs
~12-15 ms for single BIDO).
```

## Decision rules

- All three channels train successfully → gate the combined output.
- Y-CNN converges, chroma CNNs don't → fall back to Variant C (joint
  chroma) so they can share statistics.
- Anything PASSes PREVIEW → promote as `ship-preview-embedded-channel-decomp`.
- Nothing PASSes → the architecture-family ceiling is real even at
  decomposed scale; the strategic call is to ship `cnn=none + bicubic`
  and accept the LPIPS 0.31 floor.

## Why this might still fail (honest pre-mortem)

1. **Y-CNN converges, chroma drifts on OOD.** The OOD content (Z8Z_6693
   hair) has chroma the chroma-CNNs can't match because they've never
   seen similar skin/hair tones in training. The corpus expansion via
   ood_dngs_2025-04-20 + brightness-balance correction would need to
   ship in parallel for the chroma channels to have the right priors.
2. **YCbCr conversion is not the right perceptual space.** ΔE2000 is
   defined in LAB. We may need to train in LAB after all, just paying
   the more expensive forward conversion. Variant A in LAB instead of
   YCbCr is a one-line change.
3. **The Bayer-to-chroma signal is structurally weak.** Half-res Bayer
   has 1/8 chroma samples vs full-res RGB target. The chroma CNN might
   not have enough input signal to recover the missing color
   information, regardless of param count. If so, the only fix is
   either (a) higher-resolution capture (defeats the dec2 point) or (b)
   spatial chroma upsampling from neighboring captured pixels (which
   requires multi-frame context).
4. **The L1 vs Charbonnier vs ΔE choice for chroma still has unknowns.**
   We haven't ablated yet.

## Other directions NOT taken (and why)

- **Distill the blend into one CNN.** Drops the per-channel architectural
  insight; we'd be training one model to mimic the blend, which trains
  the same RGB-domain optimization problem we already know fails.
  Rejected.
- **Direct LAB training of existing BIDO.** Cheaper (no arch change) but
  doesn't address the architectural coupling. Could be a B-side
  ablation; not the headline experiment.
- **Multi-frame temporal context.** Real-RawVSR's approach. Out of scope
  for embedded preview (no temporal buffer on the capture side).
- **Diffusion / iterative refinement at decode time.** Real-ESRGAN-like.
  Compute-prohibitive even on M5; not the embedded preview compute budget.

## What ships if all of this fails

`cnn=none + bicubic` at worst LPIPS 0.31 on Z8Z_6693, packaged as a
**"PREVIEW lite"** tier with the honest statement that the half-res
capture's restoration ceiling is in research, not engineering. The
24.93 fps Pi 5 capture still works; only the preview-quality CNN is
gated by architecture R&D.

## Wall-budget summary

| step | time | gate? |
|---|---|---|
| Variant A: 3 channel CNNs trained sequentially on M5 | ~9 hr | yes (after each cohort) |
| OR parallel on M5 + M3 Max | ~3 hr | yes |
| Combined inference pipeline integration | ~1-2 hr | manual |
| Gate run + ship-claim preflight | ~10 min | yes |
| **Variant B/C if Variant A inconclusive** | ~3-6 hr more | yes |
