# Video pipeline status — refreshed 2026-06-25

## Your design intent (restated)

> "For video I wanted to take a quality level that allowed us to hit
> 24 fps and could use a CNN to recover visual quality on the decoder side."

Three parts: **camera capture** (encode side, with Pi 5 as a conservative
stand-in proxy), **camera-back preview** from the same raw-video stream, and
**offline/review reconstruction** for 4K cleanup, 8K SR, and ProRes review.

The active Mission 1 target now uses native 4096 x 3072 Bayer `.gvid` as the
capture stream and decodes that stream to 1024 x 768 RGB for camera-back
preview. Older half-res/2K sections below are retained as historical context,
not the current numbered-list success definition.

## Current video pipelines

## 2026-06-25 Mission 1 Numbered-List Snapshot

The current active Mission 1 evidence is summarized by
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_numbered_list_readiness_20260625/readiness.json`
and generated with:

```bash
python3 tools/mission1_numbered_list_readiness.py \
  --external-root /Volumes/OWC_8TB/gpr_work
```

Current status is `evidence_passes_with_production_blockers`:

- 4K Bayer `.gvid` on the Pi 5 stand-in: 420 frames, 4096 x 3072, zero drops,
  24.32 fps whole-run wall, 25.29 fps loop median, and Lexar SILVER PLUS
  write-budget pass.
- Selected aggregate Pi stand-in closure rerun on 2026-06-25: 1,440 frames,
  4096 x 3072, zero drops, valid `.gvid`, 20.50 fps whole-run wall,
  21.52 fps median loop timing, and Lexar SILVER PLUS write-budget pass.
- Camera-back preview: 4096 x 3072 `.gvid` to 1024 x 768 RGB, 420 frames,
  25.85 fps whole-run wall including extract process, and 36.23 fps median
  decode-plus-target timing.
- Selected aggregate preview rerun from the same `.gvid`: 24.20 fps whole-run
  wall including extract/process and 43.86 fps median decode-plus-target
  timing.
- Refreshed aggregate closure receipt:
  `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/mission1_camera_closure_run.json`
  records `aggregate_consistency_ready=true`, proving the target bench,
  handoff, and preview UI receipts agree on `.gvid` identity, dimensions,
  frame count, pixel format, source provenance, and drop state.
- 4K cleanup CNN: rendered/tone review artifacts exist, the intended high-res
  CFA raw guard passes, 4K `.gvid` packaging is receipted, and the production
  signoff receipt validates for offline/post scope. The older clean-low Bayer
  comparison is retained as a diagnostic because this branch targets the
  high-resolution-derived CFA objective.
- 8K SR: broad Mission42/Z8 quality gates, 8K `.gvid`, decode-to-SR timing,
  editable DNG/GPR packaging, Mission metadata transplant, visual review,
  production promotion, and ProRes receipts exist. This is an offline/post
  output path at current throughput, not a live camera path.

Camera firmware readiness still requires actual Mission 1 sensor/DMA input,
camera UI preview integration, and camera storage handoff receipts. Older
strict-24 and half-res sections below remain historical context rather than the
current numbered-list success definition.

A real non-dry camera-ready closure launch was attempted against
`192.168.16.67` after the target package was synced. It stopped before encode
or preview because the required hardware audit found no camera sensor
enumerated by rpicam/libcamera/V4L. The blocked receipts are indexed under
`artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/`.

For the older preview-video review bundle and SOTA-v2 ProRes evidence, see
`docs/PREVIEW_VIDEO_REVIEW_2026-06-04.md`. That document records the
2026-06-04 dashboard, ProRes review outputs, and the former distinction between
the half-res raw capture deliverable and rendered preview outputs. The current
Mission 1 numbered-list target is native 4096 x 3072 Bayer `.gvid` capture plus
1024 x 768 preview from that same stream.

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

### B) Embedded half-res Pi-capture path (proxy-acceptable, camera receipt pending)

| field | value |
|---|---|
| codec | `ml2_q3_dec2` (multi-level FUSED, decimate=2 → half-res) |
| raw-video container | `.gvid` primary deliverable; MOV/GPR1 compatibility wrapper optional |
| live/camera-back PREVIEW | historical half-res/2K policy; the current Mission 1 numbered-list preview is 4096 x 3072 `.gvid` to 1024 x 768 RGB from the native12 stream |
| offline/review PREVIEW | `preview_q8_threeway_runtime_fullframe_v1` registered as external-receipt no-REF production path |
| offline/review entrypoint | `tools/cnn/render_preview_q8_threeway_runtime.py` |
| Pi 5 capture fps | Historical 2026-05-26 receipt: **24.93 fps median**. Latest strict 10 minute Labs receipt at commit `0dd6660`: **19.98 fps median**, 50.04 ms median, 66.01 ms p95, 14,400/14,400 frames, 0 drops, valid `.gvid`; treat this as acceptable conservative 20 fps proxy evidence for camera integration. Corrected pixel-format short direct `.gvid` probe at commit `e16357f`: **19.85 fps median**, 50.38 ms median, 57.23 ms p95, 120/120 frames, 0 drops, valid `.gvid`. Hardened native 12MP Mission 1 true-Bayer probe: **22.99 fps median / 22.40 fps wall**, 120/120 frames, 0 drops, valid `.gvid`, storage-budget pass; strict 24 fps still fails. Actual Mission 1 24 fps capture remains unproven. |
| per-frame size | **1.30 MB** at half-res |
| at 24 fps sustained | **31 MB/s** — well within USB SSD capability |
| offline/review PREVIEW quality | **PASS on current 28-image/84-row holdout** — worst LPIPS 0.1178, MS-SSIM 0.9548, Y-PSNR 30.87, dE2000 2.64 |
| offline/review PREVIEW speed | **13.65 s/image, 0.073 fps, 5.37 GB peak RSS** on the Mac/MPS receipt — not live/camera-back preview |

This remains useful historical evidence for half-res capture and offline
PREVIEW research. It is no longer the active Mission 1 numbered-list target.
The current camera-back preview proof decodes the native 4096 x 3072 `.gvid`
stream to 1024 x 768 RGB above the accepted 20 fps floor. The q8 three-way CNN
route closes the no-REF full-frame PREVIEW quality gap for offline/review
output, but it is much too slow for live preview.

Treat any proxy path as blocked for direct firmware readiness until actual
Mission 1 camera receipts prove sensor/DMA input, SD-card handoff, and rear
display presentation. The Pi result is proxy-acceptable only.
For current target-bench receipts, direct firmware readiness requires both
median frame timing and whole-run wall throughput to clear target FPS.

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

### C) Native 12MP Mission 1 Bayer recompression candidate

| field | value |
|---|---|
| profile | `mission1_native12_fll2_t233_avg7555_fast_pinp2_20fps_v1` |
| profile helper | `tools/mission1_native12_fll2_t2_profile.py` |
| codec | single-level fused q8, exact predictive LL sideband (`FLL2`) with avg predictor + tuned Rice, hard per-band highpass dead-zones LH/HL/HH=2/3/3, byte-exact prescale-2 reference-horizontal NEON |
| source | native Mission 1 4096 x 3072 Bayer, pixel format 1 (`RGGB14`) |
| target | 20+ fps Pi 5 / Mission 1 stand-in, conservative Lexar SILVER PLUS 128GB-1TB 205/150 write budget with 0.90 margin |
| quality evidence | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_fll2_T2_native12_quality_20260617/summary.json`; exploratory strict-24 quality/storage boundary dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_t236_ch2lh3_quality_dashboard_20260618/summary.json` |
| Pi evidence | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_prescale2_refh_neon_native12_1440f_20fps_20260617/summary.json`; current-code phase probe: `/Volumes/OWC_8TB/gpr_work/artifacts/current_probe_t233_GP017602_pi_20260618/` |
| status | passes active 20+ fps stand-in floor; T233 remains the registered production profile; T236 is exploratory strict-24 storage-boundary evidence; actual sensor/DMA camera handoff pending; strict 24 fps timing remains open for the quality profile |

Sustained 1,440-frame Pi receipts:

| image | median fps | median ms | MiB/frame | required write at 20 fps |
|---|---:|---:|---:|---:|
| GP017601 | 23.13 | 43.23 | 5.218 MiB | 109.4 MB/s |
| GP017602 | 22.70 | 44.05 | 5.313 MiB | 111.4 MB/s |
| GP017603 | 24.35 | 41.06 | 4.960 MiB | 104.0 MB/s |

All three receipts pass valid `.gvid`, zero drops, interrupted-tail recovery,
and storage target checks. This is true Bayer recompression, not camera `.GPR`
payload wrapping.

The hard frame, `GP017602`, records current sustained strict-24 encode median
40.72 ms and write median 3.56 ms in
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_prescale2_refh_neon_GP017602_1440f_24fps_20260617/labs_target_bench.json`.
Strict 24 fps therefore remains a total-frame/write-overlap blocker, not a
storage-size blocker.

Current-code 2026-06-18 Pi phase probe on GP017602 confirms the same practical
split for the registered T233 profile. SSD-backed direct `.gvid` capture
records 48.10 ms median total, 44.33 ms encode, and 3.81 ms write. Reading the
raw fixture from SSD while writing the `.gvid` stream to the Pi root SD card
records 48.70 ms median total, 44.76 ms encode, and 3.93 ms write, still
passing the accepted 20 fps floor. A matching scatter encode-only run records
44.38 ms median, or about 22.5 fps, so strict 24 fps cannot be reached by
storage work alone for this quality profile.

Latest 2026-06-18 boundary check: exploratory T236 (`LH=2,HL=3,HH=6,CH2_LH=3`,
FLL2 avg `6,6,5,6`) passes the three-image quality floor and fits strict-24
storage, but does not replace the registered T233 production profile. Fresh Pi
isolation shows this is not a visual-quality blocker: T236 encode-only clears
strict 24 fps at 38.870 ms median, while the best real-write `.gvid` probe is
42.503 ms total / 23.53 fps with 38.664 ms encode and 3.764 ms write. The
stronger source-provenance sustained receipt records 43.49 ms total / 23.00 fps
median over 240 frames, with 22.46 fps wall throughput, valid `.gvid`, no
drops, interruption recovery, source digest, and storage-budget pass. The remaining miss is
target-platform encode/write handoff margin. T468
(`LH=4,HL=6,HH=8,CH2_LH=4`) passes a hardened 120-frame Pi receipt at 27.74
wall fps, but fails raw quality and is not the production profile.

Codec/CNN policy: CNN recovery is valid only for decoded-valid codec outputs.
It cannot waive symbol/range clipping, invalid bitstreams, or raw quality
collapse. The current boundary note is
[`MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md`](MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md).

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

For video you need:
- Pi 5 stand-in evidence at roughly 20 fps for Labs integration, which the
  native 12MP FLL2 T2 receipts now provide, and
- Mission 1 hardware sensor/DMA evidence before firmware readiness can be
  claimed. If strict 24 fps remains a requirement, FLL2 T2 still needs
  additional highpass/rate optimization.

If the camera path misses 24 fps, the next options are a faster encoder or a
capture-side algorithm change. The parallel-DNG-read win above doesn't help the
  pure-encode hot path; further encoder speedup would have to come from
  cache-line alignment / NEON / multi-threading wins on the VC5 codec
  itself. The 2026-05-28 alignment subagent work targets exactly this.

## Decision framework

| What you want | Which pipeline |
|---|---|
| Highest-quality video at any size, desktop | **A** (full-res VIDEO_FREEZE) |
| Embedded Pi-camera native 12MP capture at 20+ fps | **C** (FLL2 T2 native Bayer recompression; Pi stand-in receipts pass, actual sensor/DMA camera receipt pending) |
| Embedded Pi-camera capture at strict 24 fps | **C** remains open; native12 FLL2 T2 needs more rate/throughput margin if strict 24 fps becomes the bar again |
| Offline/review preview from B's captures | **B** with q8 three-way PREVIEW candidate (quality passes; 0.073 fps) |
| Live/camera-back preview for current Mission 1 path | **C** native12 `.gvid` decoded to 1024 x 768 RGB; Pi stand-in passes above 20 fps, actual camera UI receipt pending |

## Per-frame numbers on Z8 50MP — for budgeting

| pipeline | per-frame MB | per-second-at-24fps MB |
|---|---:|---:|
| A: ml2_q3_l1x2 + matched CNN | 7.81 | 187 |
| A: ml2_q3 + matched CNN (alternate) | 10.26 | 246 |
| B: ml2_q3_dec2 (Pi capture) | 1.30 | **31** |
| C: native12 FLL2 T2 (GP017602) | 5.80 MiB | 146 MB/s at 24 fps; 122 MB/s at 20 fps |

## Raw output target ladder

`ml2_q3_dec2` can feed three raw output sizes while preserving Bayer data:

| target | dimensions | method | current status |
|---|---:|---|---|
| 2K / 0.5x | 2070 x 1380 | `2k_raw_0p5x_fast` drops L2 highpass; `2k_raw_0p5x_l2hh` restores selective L2 HH | live-capable raw target. Fast mode: 26.6 ms median, 27.7 ms p95, 37.59 fps median. Selective L2 HH: 33.5 ms median, 37.1 ms p95, 29.85 fps median; matched-source raw quality 55.60 dB mean PSNR; exact-edge rendered proxy 80/84, 16 px edge-safe display proxy 84/84 |
| 4K / 1x | 4140 x 2760 | direct decoded Bayer | offline-only production classification. Mac editable raw: 22.9 ms median, 43.7 fps median. Pi decode-side: 159.6 ms median, 6.3 fps median. Rendered proxy: 55/84 diagnostic under PREVIEW LPIPS |
| 8K / 2x | 8280 x 5520 | BIBO_2x Bayer super-resolution | offline/review only at current speed |

Details and receipts are in `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`.

## Open work for video

1. **Mission 1 camera closure** — the current production blocker is not another
   proxy benchmark. The next production receipt must come from a camera-role
   run that proves native12 `.gvid` encode from the real sensor/DMA source,
   storage handoff, and 1024 x 768 rear-display preview. The latest source
   probe still shows `/dev/mission1/sensor_dma_ring` missing on the target.
   The latest discovery receipt also records candidate V4L/media nodes
   (`pispbe-input`, `pispbe-output*`, `pispbe-config`, `/dev/media*`), DRM
   display nodes, and the mounted `/mnt/ssd` ext4 path, but these are
   handoff-discovery clues rather than validated raw Bayer frame sources.
   `rpicam-hello --list-cameras` and `libcamera-hello --list-cameras` both
   report `No cameras available!`, so the current camera-side blocker is sensor
   enumeration/handoff rather than storage or missing target tooling. The
   structured hardware audit records `hardware_ready_for_camera_source=false`
   and zero sensor-like V4L nodes.
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
