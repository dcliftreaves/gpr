# Video pipeline status — refreshed 2026-06-14

## Your design intent (restated)

> "For video I wanted to take a quality level that allowed us to hit
> 24 fps and could use a CNN to recover visual quality on the decoder side."

Three parts: **24 fps capture** (encode side, Pi 5 constrained),
**offline/review PREVIEW quality** (Mac desktop side), and a separate
**live/camera-back preview** path if interactive display is required.

## Current video pipelines

For the latest preview-video review bundle and SOTA-v2 ProRes evidence, see
`docs/PREVIEW_VIDEO_REVIEW_2026-06-04.md`. That document records the
2026-06-04 dashboard, ProRes review outputs, and the current distinction
between the raw 24 fps capture deliverable (`.gvid` carrying
`ml2_q3_dec2` frame payloads) and rendered preview outputs.

### A) Full-res VIDEO_FREEZE ship (desktop processing, not Pi capture)

| field | value |
|---|---|
| codec | `ml2_q3_l1x2` (multi-level FUSED, L1 ×2 cranked) |
| CNN | `bibo1x_ane_ml2_q3` (matched) |
| gate verdict | **PASS** (worst LPIPS 0.076 < 0.08 ceiling) |
| per-frame size | **7.81 MB** |
| at 24 fps | **187 MB/s sustained** |
| Pi 5 encode (legacy gpr_tools, post 2026-05-28 perf work) | **1.84 fps best** at q=3 full 50MP, **0.57 fps** pre-perf-work — NOT 24 fps capable either way |
| use case | desktop post-processing of full-res video |

This is the pipeline that PASSes the perceptual gate. It's the
correct ship for post-processed video on a Mac. It is **NOT** the
embedded-capture ship — Pi 5 can't encode this fast.

### B) Embedded half-res Pi-capture path (target blocker on latest strict run)

| field | value |
|---|---|
| codec | `ml2_q3_dec2` (multi-level FUSED, decimate=2 → half-res) |
| raw-video container | `.gvid` primary deliverable; MOV/GPR1 compatibility wrapper optional |
| live/camera-back PREVIEW | `2k_raw_0p5x_l2hh` selective-L2 HH production-bounded edge-safe display policy; older codec-only gate remains experimental |
| offline/review PREVIEW | `preview_q8_threeway_runtime_fullframe_v1` registered as external-receipt no-REF production path |
| offline/review entrypoint | `tools/cnn/render_preview_q8_threeway_runtime.py` |
| Pi 5 capture fps | Historical 2026-05-26 receipt: **24.93 fps median**. Latest strict 10 minute Labs receipt at commit `0dd6660`: **19.98 fps median**, 50.04 ms median, 66.01 ms p95, 14,400/14,400 frames, 0 drops, valid `.gvid`. Corrected pixel-format short direct `.gvid` probe at commit `e16357f`: **19.85 fps median**, 50.38 ms median, 57.23 ms p95, 120/120 frames, 0 drops, valid `.gvid`. Treat the current commit/path as blocked until the regression is narrowed or fixed. |
| per-frame size | **1.30 MB** at half-res |
| at 24 fps sustained | **31 MB/s** — well within USB SSD capability |
| offline/review PREVIEW quality | **PASS on current 28-image/84-row holdout** — worst LPIPS 0.1178, MS-SSIM 0.9548, Y-PSNR 30.87, dE2000 2.64 |
| offline/review PREVIEW speed | **13.65 s/image, 0.073 fps, 5.37 GB peak RSS** on the Mac/MPS receipt — not live/camera-back preview |

This remains the intended embedded capture architecture, but the latest strict
target-style receipt does not clear 24 fps. The codec-only PREVIEW route is the
fast live/camera-back path. The current q8 three-way CNN route closes the
no-REF full-frame PREVIEW quality gap for offline/review output, but it is much
too slow for live preview. Live/camera-back quality beyond codec-only remains a
separate future strategy.

The live/camera-back blocker is now bounded to exact outer-edge display
quality, not raw-target timing. The committed codec-only PREVIEW gate run
`b561d2e75801f0aa` passes 1/4 images and fails worst-case thresholds at LPIPS
0.3119, MS-SSIM 0.8617, Y-PSNR 24.04, and dE2000 3.56. The current 2K raw
timing path, `2k_raw_0p5x_l2hh`, clears Pi 5 timing at 29.85 fps median
and 37.1 ms p95. Its exact-edge rendered proxy remains 80/84, with four
LPIPS-only lower-right crops: `Z8Z_0002`, `Z8Z_0003`, `Z8Z_0009`, and
`Z8Z_0020`; MS-SSIM, Y-PSNR, and dE2000 remain passing on those rows. With a
16 px edge-safe display viewport, the same target passes 84/84 with worst LPIPS
0.1378, worst MS-SSIM 0.9787, worst Y-PSNR 37.60, and worst dE2000 1.37.
Production is therefore limited to that bounded edge-safe live display policy
unless exact outer-edge display becomes a requirement.

## Pi 5 encode characteristics (real measurements)

From `docs/STILLS_PI5_TIMING.md` — single-image full-res 50MP encode
times (legacy gpr_tools q-levels, post 2026-05-28 parallel-DNG-read
perf work; comparable to FUSED order of magnitude):

| q | encode ms | fps single-image |
|---:|---:|---:|
| 3 |  544 | **1.84** |
| 8 |  704 | 1.42 |

(Pre-perf-work baseline was 1.76 s / 0.57 fps at q=3 — 2.89× speedup
from commits 79403fb + ec1cb2c, which targeted the Adobe DNG SDK input
decode rather than the VC5 codec itself.)

For video you need either:
- Half-res capture restored to >= 24 fps on the strict target receipt, or
- A faster encoder. The parallel-DNG-read win above doesn't help the
  pure-encode hot path; further encoder speedup would have to come from
  cache-line alignment / NEON / multi-threading wins on the VC5 codec
  itself. The 2026-05-28 alignment subagent work targets exactly this.

## Decision framework

| What you want | Which pipeline |
|---|---|
| Highest-quality video at any size, desktop | **A** (full-res VIDEO_FREEZE) |
| Embedded Pi-camera capture at 24 fps | **B** (half-res `.gvid`; container/recovery work, capture throughput is currently blocked below 24 fps) |
| Offline/review preview from B's captures | **B** with q8 three-way PREVIEW candidate (quality passes; 0.073 fps) |
| Live/camera-back preview from B's captures | **B** with the bounded `2k_raw_0p5x_l2hh` edge-safe display policy; exact-edge display remains diagnostic |

## Per-frame numbers on Z8 50MP — for budgeting

| pipeline | per-frame MB | per-second-at-24fps MB |
|---|---:|---:|
| A: ml2_q3_l1x2 + matched CNN | 7.81 | 187 |
| A: ml2_q3 + matched CNN (alternate) | 10.26 | 246 |
| B: ml2_q3_dec2 (Pi capture) | 1.30 | **31** |

## Raw output target ladder

`ml2_q3_dec2` can feed three raw output sizes while preserving Bayer data:

| target | dimensions | method | current status |
|---|---:|---|---|
| 2K / 0.5x | 2070 x 1380 | `2k_raw_0p5x_fast` drops L2 highpass; `2k_raw_0p5x_l2hh` restores selective L2 HH | live-capable raw target. Fast mode: 26.6 ms median, 27.7 ms p95, 37.59 fps median. Selective L2 HH: 33.5 ms median, 37.1 ms p95, 29.85 fps median; matched-source raw quality 55.60 dB mean PSNR; exact-edge rendered proxy 80/84, 16 px edge-safe display proxy 84/84 |
| 4K / 1x | 4140 x 2760 | direct decoded Bayer | offline-only production classification. Mac editable raw: 22.9 ms median, 43.7 fps median. Pi decode-side: 159.6 ms median, 6.3 fps median. Rendered proxy: 55/84 diagnostic under PREVIEW LPIPS |
| 8K / 2x | 8280 x 5520 | BIBO_2x Bayer super-resolution | offline/review only at current speed |

Details and receipts are in `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`.

## Open work for video

1. **Live PREVIEW exact-edge closure** — the production live/camera-back path
   is now bounded to the `preview_live_2k_l2hh_edge_safe_v1` policy: 2K
   selective L2 HH, no REF content, and a 16 px edge-safe display viewport.
   It clears Pi 5 timing and passes 84/84 rendered proxy rows. Exact-edge
   display remains 80/84 with four near-threshold LPIPS rows; closing those
   rows is the remaining quality improvement if full outer-edge display is
   required. The older codec-only live PREVIEW baseline remains experimental
   because the committed gate run is 1/4 images passing.
2. **Codec perf** — 2026-05-28 landed three Pi 5 wins:
   (a) parallel DNG SDK input decode (2.89× on legacy stills, commits
   `79403fb` + `ec1cb2c`);
   (b) FUSED Pass 2 worker-pool dispatch on narrow hosts (6.6% on Pi 5
   half-res video capture, 17% on Pass 2 alone, commit `c1eabc6`).
   Encoder cache-line alignment attack (proposed for hot scratch) was
   measured at ≤2% delta on both Pi 5 and Mac — below ship bar, did
   not land. The Pi 5 stills encoder hot path now needs wavelet /
   quantizer inner-loop work to win further (not plumbing).
3. **Legacy gpr_tools for video** (open question) — if the legacy
   encoder is more efficient than FUSED for stills, the same question
   applies for video. Would need a video-domain matched CNN retrain.
   Comparable to today's stills work.
