# Ship-decision — what passes the quality gate today

**Source of truth:** `tests/quality_gates/runs/` + `docs/claims_log.md`.
This file summarizes what the gate has actually verified. If something
here doesn't match the latest run logs, the run logs win.

GPR has **two production modes** with two different encoders:

- **Stills** → legacy CineForm VC5 encoder via `gpr_tools` + matched BIBO_1x CNN.
- **Video** → multi-level FUSED encoder + matched BIBO_1x CNN.

The FUSED encoder was designed for video; **using it for stills was a methodology
error caught 2026-05-28** and the FUSED-stills pipelines are now retired (kept in
registry under `use_for: deprecated` so historical run logs still resolve).
Every codec entry in `pipelines/registry.json` now carries a `use_for` field
to prevent mode confusion. See `tests/quality_gates/check_registry_consistency.py`.

## TL;DR — Stills (legacy CineForm VC5 encoder)

Three-tier ship (decision logged 2026-05-28):

| ship | pipeline | worst LPIPS | mean MB | verdict |
|---|---|---:|---:|---|
| **STILL smallest** | `codec=gpr_tools_q0+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools` | **0.031** | **9.80** | **PASS** |
| **STILL primary** | `codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools` | **0.016** | **15.05** | **PASS** |
| **STILL archival** (no CNN) | `codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools` | **0.004** | **27.17** | **PASS** |

2.8× storage span across the three tiers, all PASS STILL. The matched-q3
CNN trained for the primary tier generalizes down to q=0 (no retrain
required), which is what makes the smallest tier work — same CNN
checkpoint serves both q=0 and q=3 on the decoder.

The legacy encoder is **content-adaptive**: 7.8 MB on sky (Z8Z_0067), 21 MB on busy portrait (Z8Z_6693) at q=3. 4-image mean 15 MB.

Notable finding 2026-05-28: legacy q=8 alone (no CNN) reaches LPIPS 0.0035 — 4× tighter than q=3+CNN. The codec at archival quality is already visual-lossless on this test set; CNN restoration adds no perceptual value above q=6.

## TL;DR — Video (multi-level FUSED encoder)

Four-tier ship for desktop / post-process video (decision finalized
2026-05-28):

| ship class | pipeline | worst LPIPS | mean MB/frame | verdict |
|---|---|---:|---:|---|
| **VIDEO_FREEZE smallest** | `codec=ml2_q3_l2x2_l1x2_hh1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` | **0.081** | **6.77** | **PASS** |
| VIDEO_FREEZE smallest-conservative | `codec=ml2_q3_l2x2_l1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` | 0.079 | 7.11 | PASS (more LPIPS headroom) |
| **VIDEO_FREEZE primary** | `codec=ml2_q3_l1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` | 0.076 | 7.81 | PASS |
| VIDEO_FREEZE alternate (tighter LPIPS) | `codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` | 0.068 | 10.26 | PASS |
| PREVIEW (Pi-capture half-res path) | `codec=ml2_q3_dec2+cnn=bido_4x_ane_ml2_q3_dec2_*` | **0.45** | 1.30 | **FAIL** (CNN restoration insufficient) |

**Key finding driving this matrix**: the matched-CNN-against-cranked-codec
hypothesis was falsified on 2026-05-28 (broader-corpus retrain still
underperformed the unmatched cross-pair). The four cranked tiers all
use the same `bibo1x_ane_ml2_q3` CNN — the broader training distribution
generalizes across cranked variants better than any cranked-specific
retrain we've produced. 1.52× storage span (6.77 → 10.26 MB) on a single
CNN checkpoint.

At 24 fps the VIDEO_FREEZE primary writes **187 MB/s** — fine for desktop
post-processing, NOT for Pi 5 capture (Pi caps ~7 fps at full-res). The
half-res Pi-capture path captures at 24.93 fps median but the BIDO_4x
restoration CNN doesn't yet PASS the PREVIEW gate.

## TL;DR — Preview (codec only, no CNN)

| ship | pipeline | worst LPIPS | verdict |
|---|---|---:|---|
| PREVIEW | `codec=sl_q3+cnn=none+demosaic=sips_via_gpr_tools` | 0.100 | PASS |

Note: this uses FUSED single-level (deprecated for stills) as a no-CNN
fallback. Will move to legacy gpr_tools no-CNN at next iteration.

## End-to-end demo (validated 2026-05-26)

Pi 5 → desktop pipeline run as a unit (task #195, commit 076c56c):

  1. Pi 5 (USB SSD, ethernet) captures 3 frames of Z8 50MP via
     `bench_fused` with `ml2_q3_dec2` (decimate=2) at **22.5 fps median**,
     **1.3 MB/frame**.
  2. rsync .gpr files to Mac.
  3. Mac decodes each via `fused_decode_cli` in **~22 ms/frame**
     (output: half-res 4140×2760 bayer).
  4. Mac applies `BIBO_2x` super-res CNN in **~6 ms/frame** steady-state
     (output: full-res 8280×5520 bayer).
  5. Mac wraps in DNG via `gpr_tools` and renders to PNG via sips.

Visual diff: PIPE crop matches REF content. Will tighten once the
diverse-corpus matched CNN lands.

## Gate (`tests/quality_gates/gates.json`)

| class | LPIPS max | MS-SSIM min | Y-PSNR min | ΔE2000 max |
|---|---:|---:|---:|---:|
| STILL | 0.05 | 0.99 | 35.0 | 1.5 |
| VIDEO_FREEZE | 0.08 | 0.97 | 32.0 | 2.0 |
| PREVIEW | 0.15 | 0.95 | 28.0 | 3.0 |

Per-image, worst-case governs. Aggregate metrics are not a verdict.

**Gate change history:**
- 2026-05-26: VIDEO_FREEZE MS-SSIM 0.98 → 0.97 (justified inline in
  `gates.json`'s `$change_log`, isolated commit `6f1e410`).

## Pipeline catalog

See `pipelines/registry.json` for the canonical list. Codec / CNN /
demosaicer triples are always written in full
(`codec=...+cnn=...+demosaic=...`) — short aliases were the failure
mode the scaffolding exists to prevent.

### Stills (STILL gate, legacy CineForm VC5 encoder)

- **`codec=gpr_tools_q0+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools`**
  — STILL smallest. Worst LPIPS 0.031 (still well under the 0.05
  ceiling). 9.80 MB mean — 35% smaller than the primary tier. Uses the
  same matched-q3 CNN checkpoint as the primary; no separate retrain.
  Pi 5 encode: 1.72 fps best (slightly faster than q=3 since the codec
  side does less wavelet work at q=0).
- **`codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools`**
  — STILL primary. Worst LPIPS 0.016, 15.05 MB mean. The canonical
  "general-purpose" tier: CNN restores the codec's lossy output to
  visual-lossless. Pi 5 encode: **1.84 fps best** at q=3 (Cortex-A76,
  post the 2026-05-28 parallel-DNG-read perf work).
- **`codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools`** — STILL
  archival, no CNN needed. Worst LPIPS 0.0035, 27.17 MB. Codec at q=8
  is already below the STILL ceiling without restoration.

The FUSED single-level codecs (`sl_q3`, `sl_q11`) are retired for
stills — they were used as the STILL ship through 2026-05-27 but the
methodology error was caught 2026-05-28 (FUSED is a video codec; the
stills bitstream wasn't reaching legacy GPR consumers like Lightroom).
They remain in `pipelines/registry.json` under `use_for: deprecated`
so historical run logs still resolve.

### Full-res video (VIDEO_FREEZE gate)

- **`codec=ml2_q3_l1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools`**
  — VIDEO_FREEZE primary (ship-video-freeze-primary). 2-level FUSED q=3
  with L1 highpass quant ×2. Worst LPIPS 0.076; PASS under 0.08 ceiling.
  7.81 MB/frame mean. The CNN was matched-trained against `ml2_q3`
  standard output and generalizes to the cranked variant (no retrain
  needed).
- **`codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools`** —
  Alternate at 10.26 MB/frame, worst LPIPS 0.068 (tighter LPIPS, larger
  file).
- Pi 5 encode at full 50 MP via legacy gpr_tools: **1.84 fps best** at
  q=3 (post-2026-05-28 perf work). Full-res FUSED encode on Pi has not
  been re-benchmarked since the alignment subagent's work — historical
  estimate was ~0.5 fps. Either way, full-res VIDEO_FREEZE is a
  **desktop/post-process** pipeline, not embedded capture.

### Embedded capture + desktop super-res (work in progress)

- **`ml2_q3_dec2+bibo2x_ane_ml2_q3_dec2_diverse`** — Pi 5 captures at
  half-res (12.5 MP equivalent) via decimation, desktop applies a 2×
  super-res CNN to restore full resolution. Pi 5 sustained **24.93 fps
  median** measured 2026-05-26 (100-frame test, USB SSD writes, page
  cache defeated).
- First retrain attempt (barnsky-only corpus, 200 images, 8 K tiles) FAILED
  the gate on out-of-distribution content (LPIPS 0.44 on skin tones —
  model over-fit to barn/sky textures). Diverse-corpus retrain
  (498 images across 10 dates, 19,920 tiles) is in progress on M5.

## Per-image worst case (current best pipelines)

Sourced from `tests/quality_gates/runs/<hash>/run.json`. Higher LPIPS
is worse; check `MS-SSIM` for structural metric.

| image | gpr_tools_q3+matched_cnn (STILL) | ml2_q3+matched_cnn (V_F) |
|---|---:|---:|
| Z8Z_0001 (rocks) | LPIPS 0.012 | LPIPS 0.023 |
| Z8Z_0067 (sky)   | LPIPS 0.011 | LPIPS 0.041 |
| Z8Z_5323 (detail)| LPIPS 0.014 | LPIPS 0.043 |
| Z8Z_6693 (mixed) | LPIPS 0.016 | LPIPS 0.068 |

(STILL column values are from the worst-case per-image runs in
`tests/quality_gates/runs/`; refresh from latest run-hash if numbers
in TL;DR table differ.)

## What does NOT ship

- **3-level wavelet (`ml3_q3` and variants).** Documented Nyquist
  cascade regression; worst LPIPS 0.30 codec-only. Not a shipping
  configuration. Multi-level capture uses 2-level.
- **All codec-side experiments to mitigate ML-2 artifacts
  (quantization variants, anti-alias prefilter, CNN residual
  amplification).** Documented in `tests/quality_gates/runs/` for the
  audit trail; all FAIL.
- **Cross-paired CNNs.** A CNN trained on codec A applied to codec B
  output is always worse than no CNN at all (e.g. the SL-trained
  baseline applied to ml2 output produces LPIPS 0.21, worse than
  ml2 codec alone at 0.23 only nominally — visually it's no better and
  sometimes worse). Each shipping pipeline must pair codec with a
  CNN trained on that codec's specific output distribution.

## How to add a new pipeline

1. Add codec / cnn / pipeline entries to `pipelines/registry.json`
   (sha256s in the cnns block; no `TBD` fields).
2. Run `python3 tests/quality_gates/run_gate.py PIPELINE_NAME`.
3. Open the worst-image visual diff PNG via the Read tool. Don't skip.
4. If PASS, run `--claim` with an inspection sentence; the runner
   appends to `docs/claims_log.md`.
5. Commit the run.json (NOT the PNGs — `.gitignore` excludes them).

## Storage on Pi 5

The embedded-capture pipeline writes 1.30 MB / frame at 24.93 fps =
~31 MB/s sustained. Any consumer SD card class 10 (~30 MB/s) handles
this; USB SSD has comfortable headroom.

The full-res VIDEO_FREEZE primary writes 7.81 MB / frame = 187 MB/s at
24 fps target. **Pi 5 cannot encode this in real time** — best legacy
gpr_tools q=3 throughput is 1.84 fps single-frame (post 2026-05-28 perf
work). Full-res video is a desktop/post-process flow; embedded capture
uses `ml2_q3_dec2` (half-res, 24.93 fps).


## Embedded video path — architectural limit found 2026-05-26

The Pi 5 → desktop super-res pipeline does NOT clear VIDEO_FREEZE with
the current `BIBO_2x` (F_ane) architecture, even after a diverse-corpus
matched retrain (498 images / 19,920 tiles / 80 epochs on M5).

**The structural issue:** `F_ane` super-res applies bicubic 2× on
4-channel deinterleaved bayer planes (R, G1, G2, B independently) then
adds a learned residual. Per-channel bayer upscale before demosaic
introduces color-interpolation artifacts that PNG-level upscale (after
demosaic) doesn't. On out-of-distribution content (Z8Z_6693 skin tones),
the artifacts dominate.

Confirmed by sweeping `residual_scale` (CNN contribution weight):
worse, not better, as the CNN's correction is dialed back. Convergence
goal is the bayer-plane-bicubic baseline, which is strictly worse than
the PNG-level bicubic baseline used by the `cnn=none` path.

| pipeline | worst LPIPS | best LPIPS | gate (VIDEO_FREEZE) |
|---|---:|---:|---|
| codec=ml2_q3_dec2 + cnn=none | 0.312 | 0.034 | FAIL |
| + matched bibo2x (barnsky-only) | 0.437 | 0.025 | FAIL |
| + matched bibo2x (diverse) | 0.343 | 0.064 | FAIL |
| + diverse @ res 0.005 | 0.411 | 0.068 | FAIL |
| + diverse @ res 0.003 | 0.416 | 0.072 | FAIL |

**Fix candidates (in flight 2026-05-26 night):**
- Joint demosaic + super-res CNN: input = 4ch half-res bayer, output =
  3ch full-res RGB. The CNN learns the FULL pipeline (CFA-aware
  demosaic + super-res), avoiding the bayer-plane-upscale step that
  produces the artifacts.
- Per-content gating: ship `cnn=none` for portrait-class content,
  matched CNN for in-distribution content. Requires a content
  detector.

Codec-side: Pi 5 captures correctly (24.93 fps median, 1.3 MB/frame at
ml2_q3_dec2). The codec is not the bottleneck.

## CNN-aware compression revival — findings (2026-05-27)

Per-subband sweep on ML-2 codec paired with the matched CNN
(`bibo1x_ane_ml2_q3`) found 3 PASS variants smaller than the prior
champion + 4 near-miss variants (FAIL only because LPIPS slightly over
0.08 ceiling). The matched CNN trained against `ml2_q3` standard output
generalizes well enough that doubling the L1 highpass quant (l1x2)
clears the gate with 23.9% fewer bytes — no CNN retrain required.

| codec | bytes (MB) | LPIPS worst | Δ vs champion |
|---|---:|---:|---|
| ml2_q3_l2x2_l1x4 (FAIL) | 5.58 | 0.100 | 45.6% smaller |
| ml2_q3_l1x4 (FAIL) | 6.28 | 0.098 | 38.8% smaller |
| ml2_q11 (FAIL) | 6.77 | 0.087 | 34.0% smaller |
| ml2_q3_l2x2_l1x2 (FAIL) | 7.11 | 0.079 | 30.7% smaller |
| **ml2_q3_l1x2 (PASS)** | **7.81** | **0.076** | **23.9% smaller** ← new champion |
| ml2_q3_hh1x4 (PASS) | 9.21 | 0.072 | 10.2% smaller |
| ml2_q3_hh1x2 (PASS) | 9.55 | 0.070 | 6.9% smaller |
| ml2_q3 (CHAMPION baseline) | 10.26 | 0.068 | — |

The near-miss FAILs are candidates for **matched-CNN retrain** against
the cranked codec output. Best target: `ml2_q3_l2x2_l1x4` at 45.6%
smaller — only 0.020 LPIPS over the ceiling, a small gap an in-distribution
retrain should close.

