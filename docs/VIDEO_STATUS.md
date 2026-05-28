# Video pipeline status — 2026-05-28

## Your design intent (restated)

> "For video I wanted to take a quality level that allowed us to hit
> 24 fps and could use a CNN to recover visual quality on the decoder side."

Two parts: **24 fps capture** (encode side, Pi 5 constrained) and
**CNN-restored quality on decode** (Mac desktop side).

## Current video pipelines

### A) Full-res VIDEO_FREEZE ship (desktop processing, not Pi capture)

| field | value |
|---|---|
| codec | `ml2_q3_l1x2` (multi-level FUSED, L1 ×2 cranked) |
| CNN | `bibo1x_ane_ml2_q3` (matched) |
| gate verdict | **PASS** (worst LPIPS 0.076 < 0.08 ceiling) |
| per-frame size | **7.81 MB** |
| at 24 fps | **187 MB/s sustained** |
| Pi 5 encode | **~0.5 fps** at full 50MP — NOT 24 fps capable |
| use case | desktop post-processing of full-res video |

This is the pipeline that PASSes the perceptual gate. It's the
correct ship for post-processed video on a Mac. It is **NOT** the
embedded-capture ship — Pi 5 can't encode this fast.

### B) Embedded half-res Pi-capture path (24 fps capable, restoration gap)

| field | value |
|---|---|
| codec | `ml2_q3_dec2` (multi-level FUSED, decimate=2 → half-res) |
| restoration CNN | `bido_4x_ane_ml2_q3_dec2_*` (joint demosaic+SR, 4× spatial) |
| Pi 5 capture fps | **24.93 fps median** (verified 2026-05-26, 100-frame bench, USB SSD writes, page cache defeated) |
| per-frame size | **1.30 MB** at half-res |
| at 24 fps sustained | **31 MB/s** — well within USB SSD capability |
| gate verdict for restoration | **FAIL** — worst LPIPS 0.45 on OOD images (the BIDO CNN doesn't yet restore well enough for visual-lossless playback) |

**This is the actual 24 fps capture pipeline you asked for.** The
encode side works. The CNN-restoration side is the open gap. Phase B
of `BIDO_DISTILLATION_PLAN.md` (Restormer-teacher distillation) is the
plan to close that.

## Pi 5 encode characteristics (real measurements)

From `docs/STILLS_PI5_TIMING.md` — single-image full-res 50MP encode
times (legacy gpr_tools q-levels, comparable to FUSED order of
magnitude):

| q | encode ms | fps single-image |
|---:|---:|---:|
| 3 | 1756 | 0.57 |
| 8 | 1972 | 0.51 |

For video you need either:
- Half-res capture (achieves 24.93 fps, you have this), or
- A faster encoder (the perf-subagent work in progress targets this)

## Decision framework

| What you want | Which pipeline |
|---|---|
| Highest-quality video at any size, desktop | **A** (full-res VIDEO_FREEZE) |
| Embedded Pi-camera capture at 24 fps | **B** (half-res, CNN still needs work) |
| Desktop preview from B's captures | **B** with BIDO Phase B (planned, not yet shipped) |

## Per-frame numbers on Z8 50MP — for budgeting

| pipeline | per-frame MB | per-second-at-24fps MB |
|---|---:|---:|
| A: ml2_q3_l1x2 + matched CNN | 7.81 | 187 |
| A: ml2_q3 + matched CNN (alternate) | 10.26 | 246 |
| B: ml2_q3_dec2 (Pi capture) | 1.30 | **31** |

## Open work for video

1. **BIDO Phase B (Restormer distillation)** — close the OOD gap on the
   embedded preview path. Plan exists. ~6 hours on M5.
2. **Codec perf** — the perf subagent is working on legacy encoder
   speedup; if it produces a 2-3× win, Pi 5 might be able to hit
   higher resolutions / fps. Re-measure when that lands.
3. **Legacy gpr_tools for video** (open question) — if the legacy
   encoder is more efficient than FUSED for stills, the same question
   applies for video. Would need a video-domain matched CNN retrain.
   Comparable to today's stills work.
