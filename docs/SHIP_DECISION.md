# Ship-decision artifact — corrected after 2026-05-25 evening

## TL;DR (updated)

The shipping pipeline is **single-level FUSED q=3 + baseline BIBO_1x CNN.**

Re-measured against single-level with the new visual-metric stack:

| metric | q=3 alone | q=3 + CNN | q=11 + CNN |
|---|---:|---:|---:|
| bayer-PSNR (4-img mean) | 40–61 dB | 57–66 dB | 54–63 dB (~-2 dB vs q=3+CNN) |
| Y-PSNR (Z8 50MP → UHD) | 30–47 dB | 45–51 dB | 42–48 dB |
| MS-SSIM | 0.89–0.99 | 0.997+ | 0.993+ |
| LPIPS (AlexNet) | 0.04–0.28 | 0.01–0.03 | 0.02–0.16 |
| ΔE2000 (Lab) | 0.5–2.3 | 0.5–1.1 | 0.5–1.2 |
| file size vs q=3 | — | — | -12% to -19% (avg ~17%) |

Single-level q=3 + baseline CNN is perceptually indistinguishable from
REF on the 4-image Z8 test set (LPIPS 0.01–0.03).

q=11 (which now cranks single-level slots 1/2/3 as well as multi-level
slots 7/8/9) saves 12–19% (avg ~17%) at the cost of ~2 dB bayer-PSNR and
a small but measurable LPIPS bump (still well under "visibly different"
threshold of ~0.15 on most content).

## Pre-release exploration framing applies

(See `memory/project_strategic_framing.md`.) This is a contribution
candidate for GoPro's OSS codec — open-source, non-commercial, with the
restricted-rights window in mind.

## What ships now

1. **Single-level FUSED q=3** is the default codec configuration. It's
   already the default of `gpr_encode_fused_create()` — `FUSED_MULTI_LEVEL`
   defaults to 0. Files are larger than multi-level was claiming, but
   the quality is real.
2. **Baseline BIBO_1x CNN** lives at `models/BayInBayOut_1x_AAon_w16_ANE.pt`.
   Applied to decoded bayer, gives +4 to +17 dB.
3. **q=11 "turn it up to 11" CNN-aware preset** is now slot-aware: cranks
   both single-level (slots 1/2/3) and multi-level (slots 7/8/9) so it
   gives savings regardless of codec mode. 18% smaller files at
   indistinguishable-to-CNN quality.
4. **Visual metric stack** at `tools/test/metrics.py` for any future
   ship/no-ship call.

## Aggressive single-level cranks

How far can single-level alone get on file size? Tested with Z8Z_5323
(high-detail scene, hardest to compress):

| crank | KB | savings | quality risk |
|---|---:|---:|---|
| q=3 baseline | 35,910 | — | reference |
| HH×4 (= q=11) | 28,915 | 19.5% | imperceptible w/ CNN |
| HH×8 | 24,749 | 31.1% | small visible degradation |
| HH×16 | 18,828 | 47.6% | visible artifacts, CNN may not fully recover |
| HH×32 | 15,843 | 55.9% | clearly degraded |

The CNN was trained on HH×4 distribution; HH×16+ is out-of-distribution
and the CNN won't help much. A retrained CNN at HH×16 would change this.

## What does NOT ship yet (blocked on task #172)

1. **Multi-level wavelet path**, including the file-size-density benefits
   it was buying for the video codec. Files at single-level are 3.3×
   bigger than broken-multi-level was producing.
2. **q=12 / cranked-L1+L2 preset.** Was measured on multi-level. Re-do
   on fixed multi-level once available.
3. **Retrained CNN checkpoints** (HH1×4, L1L2×4). Trained on multi-level
   outputs, calibrated to the broken artifact distribution.

## Pi 5 24 fps × 50 MP video viability

- **Storage budget at single-level + q=11**: ~14.8 MB/frame avg.
  - UHS-I microSD (~33 MB/s sustained): 2 fps. Not enough.
  - UHS-II V90 (~90 MB/s): 6 fps. Not enough.
  - USB-C SATA SSD (~400 MB/s): 27 fps. **PLAUSIBLE.**
  - USB-C NVMe (~800 MB/s): 54 fps. Comfortable.
- **Encoder throughput at single-level**: ~60-80 ms/frame on M1, likely
  ~120-240 ms/frame on Pi 5 (NEON A78). Need ≤41.7 ms/frame. **Off by
  3-6×.** Multi-level on M1 was 43-83 ms/frame (less data to entropy-code).
- **Bottom line**: single-level + USB SSD might hit ~6-8 fps on Pi 5,
  not 24 fps. Multi-level fix unblocks both halves (smaller files +
  faster encode).

## What changed in the codec from "as originally intended"

- `tools/test/metrics.py` is the new primary quality gate. Bayer-PSNR
  alone hid the multi-level regression for the entire PR #7..#28 cycle
  — it stays as a sanity-check helper, not the headline.
- The vertical filter top/bottom rows now use legacy-style 6-tap
  boundary coefficients (was the FUSED middle-row formula at boundaries
  — small correctness improvement, no measurable PSNR delta).
- `q=11 quality_tables[11]` slot 1/2/3 are now cranked alongside 7/8/9.
  The bitstream format is unchanged; only the quant table entries differ.
- `FUSED_INVERSE_DESCALE` and `FUSED_L2_L3_PRESCALE` env vars are
  in-place as debug knobs for the eventual multi-level fix work.

## Tests

```
$ ./tools/test/test_still_matrix.sh       # 15/15 PASS
$ python3 tools/test/test_capabilities.py  # 16/16 PASS (14 EXCEEDED, 2 MET)
$ python3 tools/test/test_multilevel_regression.py  # FAILS (until #172)
```

## Memory and follow-ups

- `memory/project_multilevel_regression.md` — codec-internal note on
  what's broken.
- `memory/project_deployment_targets_split.md` — embedded (codec only)
  vs desktop (codec + CNN) deployment legs.
- `memory/project_codec_cnn_co_design.md` — codec + CNN are one system.

Next concrete piece of work: task #172 (multi-level cascade fix). Best
attempted with the visual-metric stack as the ship/no-ship gate.
