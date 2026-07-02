# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)
[![STILL smallest](https://img.shields.io/badge/STILL%20smallest-9.80%20MB%20%2F%2050%20MP-2576c4?style=flat-square)](docs/SHIP_DECISION.md)
[![Mission preview](https://img.shields.io/badge/Mission%20preview-25.85%20fps%20Pi%205-2e7d32?style=flat-square)](docs/VIDEO_STATUS.md)
[![12MP Mission 1](https://img.shields.io/badge/12MP%20Mission%201-20%2B%20fps%20stand--in%2C%20camera%20handoff%20open-d9822b?style=flat-square)](docs/VIDEO_STATUS.md)
[![Spec](https://img.shields.io/badge/built%20on-SMPTE%20ST%202073%20(VC--5)-555?style=flat-square)](docs/SPEC.md)

## Open Raw Video For Action Cameras

**8-bit JPEG size. 16-bit RAW quality. Editable Bayer video.**

GPR is an open raw Bayer media suite for stills, camera-class raw video,
camera-back preview, offline reconstruction, and review renders. The core
promise is simple: keep the sensor data editable, make it small enough to move,
and spend compute later only when it buys visible quality.

The prototype path for GoPro-class raw video is now concrete. Sensor Bayer
frames are recompressed into compact `.gvid` streams, that same stream drives a
camera-back preview, desktop tools can restore 4K/8K detail with decoder-side
CNNs, and ProRes review media can be exported without replacing the editable raw
source.

![GPR raw-video showcase: 4K Bayer .gvid, live preview, native 12MP crops, and 8K SR review](docs/img/readme_showcase.webp)

![GPR four-pillar production readiness](docs/img/readme_status_matrix.svg)

## What Ships From The Same Raw Stream

| output | why it matters |
|---|---|
| **Compact RAW stills** | 50 MP and 100 MP-class Bayer photos stay editable while landing near JPEG-sized file budgets. |
| **Camera RAW video** | 4096 x 3072 Bayer frames become `.gvid` streams that are small enough for the accepted Pi 5 / Mission 1 stand-in write path. |
| **Camera-back preview** | The same `.gvid` stream decodes to a full-frame 1024 x 768 preview instead of maintaining a separate preview-only codec. |
| **Desktop reconstruction** | 4K cleanup and 8K SR run offline, where extra compute can buy detail without slowing capture. |
| **Review media** | ProRes and dashboard outputs exist for inspection, but the editable Bayer `.gvid` / DNG / GPR artifacts remain the product source. |

## Product Status In One Screen

Current four-pillar completion is **83%**. This is a production-readiness
burn-down, not an image-quality score, and not a regression signal for locked
artifacts. The product line is deliberately plain: **capture editable Bayer,
keep it small, preview from the same raw stream, then spend desktop compute only
when it visibly improves the result.**

| product pillar | done | what is ready now | still blocking 100% |
|---|---:|---|---|
| **Best RAW stills** | **92%** | 50 MP tiers at **9.80 MB**, **15.05 MB**, and **27.17 MB**; X2D 100 MP roundtrip; 12/14/16-bit support; real RGGB/GBRG/GRBG/BGGR coverage; X2D/Z8 noise sidecars. | Mission 1 and iPhone strict-provenance darkframe sidecars before broad nonzero noise addback is claimed. |
| **GoPro RAW video MVP** | **80%** | True 4096 x 3072 Bayer frames recompress into `.gvid` above the accepted **20+ fps** Pi 5 stand-in floor, and the same stream previews full-frame at 1024 x 768 above **20 fps**. | Real Mission 1 sensor/DMA or camera-ring-buffer source, SD writer, rear-display handoff, zero drops, valid `.gvid`, 120+ sustained frames, and timing receipts from the camera role. |
| **Premium still/SR** | **60%** | Raw-CFA targets, routed specialists, editor-openability, model-promotion tooling, and the 95-receipt experiment scoreboard exist. | A no-REF 50 MP / 100 MP candidate must beat the current still baseline and pass worst-row, editor-latitude, timing, memory, and exact-sidecar-only noise-policy gates. |
| **RAW video reconstruction improvement** | **100%** | Approved offline/post 4K cleanup and 8K SR emit `.gvid`, editable raw, standalone no-CNN/CNN ProRes review movies, objective review, and manual signoff receipts. | No release blocker. PSF/blur modeling is parked as optional replacement research. |

The denominator is the shippable production suite: **1. Best RAW stills**,
**2. GoPro RAW video MVP**, **3. Premium still/SR**, and
**4. Raw video reconstruction improvement**. PSF-aware video/SR remains optional research
for a future replacement, not a blocker for the approved current release path.

Current action stack:

| lane | action now | do not do |
|---|---|---|
| **Ship/protect** | Keep the locked still tiers, Pi-stand-in `.gvid` encode/preview, and approved 4K/8K reconstruction receipts green. | Do not reopen approved raw-video SR just because another model idea exists. |
| **External closure** | Hand GoPro the Mission 1 camera-role validation package, and capture Mission/iPhone darkframes with strict source provenance. | Do not count Pi stand-ins, wrapped camera `.GPR` files, JPEG-derived media, or unproven dark-like scene frames as production closure. |
| **Local model work** | Advance only premium still-SR candidates that satisfy the no-REF 50 MP / 100 MP promotion preflight in [`docs/PREMIUM_STILL_SR_FIRST_HOUR.md`](docs/PREMIUM_STILL_SR_FIRST_HOUR.md). | Do not rerun rejected local-CNN, clean-source residual, or scalar-loss variants as primary production attempts. |

## The Four Product Bets

GPR is not one codec demo. The repo is organized around four product outcomes
with locked proof surfaces, clear production boundaries, and explicit next
receipts.

| product bet | user-facing offer | current ship boundary |
|---|---|---|
| **1. Better RAW stills** | 50 MP and 100 MP-class editable Bayer photos at 8-bit JPEG size and 16-bit RAW quality, with normal CFA support and a path toward camera-noise-aware compression. | Ship the current 50 MP tiers and normal-Bayer support. Do not claim broad Mission/iPhone nonzero noise addback until strict-provenance darkframes exist. |
| **2. GoPro RAW video MVP** | A GoPro-class raw-video stream: 4K Bayer frames into `.gvid`, decoded from the same stream for camera-back preview, then handed to desktop tools for post. | Ship as a Labs-ready handoff package from Pi 5 stand-in evidence; actual Mission 1 firmware readiness still needs camera-role receipts with 120+ sustained frames. |
| **3. Premium still improvement** | A slow offline still path that can spend serious compute on raw-CFA restoration, editor latitude, and texture recovery. | Do not promote current CNNs. Premium still-SR remains open until the no-REF 50 MP / 100 MP promotion gate passes. |
| **4. RAW video reconstruction** | Approved 4K cleanup and offline 8K reconstruction for desktop/post, with editable `.gvid`/DNG/GPR outputs and ProRes review media. | Ship the approved offline/post path now. Reopen only if its locked gate/receipt/hash/manual review fails, or if a replacement beats it with the same `.gvid`, editable raw, ProRes, dashboard, timing, memory, and hash evidence. |

## What Is Locked

| locked path | proof | real next action |
|---|---|---|
| **50 MP RAW still tiers** | Three editable Bayer tiers pass the committed visual gate at **9.80 MB**, **15.05 MB**, and **27.17 MB** mean size. | Capture Mission/iPhone strict-provenance darkframes and build production noise sidecars. |
| **4K `.gvid` capture prototype** | 4096 x 3072 Bayer `.gvid` clears the accepted **20 fps** Pi 5 stand-in floor with zero drops, recovery, metadata dispatch, and Lexar write-budget receipts. | Run the same closure package on the actual Mission 1 sensor/DMA, storage, and rear-display paths. |
| **1024 camera-back preview** | The same 4K `.gvid` decodes to a full-frame 1024 x 768 preview above **20 fps** on the Pi 5 stand-in. | Prove the Mission 1 rear-display/UI handoff. |
| **Offline 4K cleanup and 8K SR** | Approved CNN paths emit editable 4K/8K Bayer `.gvid` plus ProRes review media for desktop/post workflows. | Keep locked. PSF-conditioned replacement work is optional research, not a release blocker. |

The SR shipping rule is narrow by design: the approved raw-video 4K cleanup and
8K SR workflow is a ship/no-ship decision, and it is currently **ship** for
offline/post. New SR research can replace it only after it beats the locked
baseline on the existing gate and emits the same `.gvid`, editable raw, ProRes,
dashboard, and receipt set. Otherwise SR iteration is research, not a reason to
delay the current workflow. The only open SR model-promotion lane is premium
still-SR, which has its own 50 MP / 100 MP gate.

Premium still-SR promotion is intentionally stricter than "looks sharper." A
candidate must submit `runtime_inputs` with `candidate_raw` and camera metadata,
exclude REF/source/JPEG content at render time, report 50 MP and 100 MP gate row
counts, show positive median MAE reduction with nonnegative worst-row MAE
reduction, record seconds/frame and peak RSS, and prove exact-sidecar-only noise
policy. The current scoreboard is deliberately not promotable: **95** runtime-safe
still-SR receipts, **0** promotable rows, best older runtime-safe row at **4.03%**
held-out MAE recovery / **3.75%** held-out RMSE recovery against the **15% / 15%**
promotion floor, and newer clean-source Restormer pair plus degradation/objective
receipts that still fail the joint X2D/Z8 holdout gate.

## Evidence Map

| question | source of truth |
|---|---|
| What is done, percent-wise, across the four pillars? | [`docs/PRODUCT_PILLAR_SCORECARD.md`](docs/PRODUCT_PILLAR_SCORECARD.md) and `/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_ship_boundary_20260701/index.html` |
| What exact evidence would make the active high-level goal complete? | [`docs/GOAL_CLOSURE_MATRIX.md`](docs/GOAL_CLOSURE_MATRIX.md) maps locked proof, open gates, next useful action, and non-claims. |
| Which outputs are locked, and what would count as a real regression? | [`docs/PRODUCT_LOCK_LEDGER.md`](docs/PRODUCT_LOCK_LEDGER.md) |
| Where are worktrees, TMPDIR, dashboards, videos, checkpoints, and receipts? | [`docs/WORKSPACE_AND_ARTIFACT_MAP.md`](docs/WORKSPACE_AND_ARTIFACT_MAP.md), [`docs/PRODUCTION_ARTIFACTS.md`](docs/PRODUCTION_ARTIFACTS.md), and [`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json) |
| What work remains before calling the whole suite production-ready? | [`docs/BIG_EFFORTS_STATUS.md`](docs/BIG_EFFORTS_STATUS.md), [`docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md`](docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md), [`docs/PRODUCTION_CAPTURE_REQUIREMENTS.md`](docs/PRODUCTION_CAPTURE_REQUIREMENTS.md), and [`docs/PRODUCTION_CAPTURE_REQUIREMENTS.json`](docs/PRODUCTION_CAPTURE_REQUIREMENTS.json) |
| What proves the stills path? | [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md), [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md), [`docs/CAMERA_NOISE_CALIBRATION.md`](docs/CAMERA_NOISE_CALIBRATION.md), and [`docs/RAW_STILLS_NOISE_FIRST_HOUR.md`](docs/RAW_STILLS_NOISE_FIRST_HOUR.md) |
| What proves the GoPro/Mission raw-video path? | [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md), [`docs/GOPRO_MISSION1_QUICK_VALIDATION.md`](docs/GOPRO_MISSION1_QUICK_VALIDATION.md), [`docs/GOPRO_LABS_FIRST_HOUR.md`](docs/GOPRO_LABS_FIRST_HOUR.md), and [`docs/LABS_INTAKE.md`](docs/LABS_INTAKE.md) |
| What proves or blocks premium still/SR? | [`docs/PREMIUM_STILL_SR.md`](docs/PREMIUM_STILL_SR.md), [`docs/PREMIUM_STILL_SR_FIRST_HOUR.md`](docs/PREMIUM_STILL_SR_FIRST_HOUR.md), and the 95-receipt scoreboard at `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_restormer_degrade_t64_20260702/index.html` |
| What proves optional PSF video/SR research? | [`docs/BAYER_RESIZE_PSF.md`](docs/BAYER_RESIZE_PSF.md), the PSF research dashboards, and `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_next_experiment_contract_20260701/index.html` |
| What should a GoPro/Labs engineer run first? | [`docs/GOPRO_LABS_FIRST_HOUR.md`](docs/GOPRO_LABS_FIRST_HOUR.md) gives the one-page camera-role closure checklist and the shortcuts that do not count as Mission 1 firmware evidence. |

## Visual Proof

Small preview assets stay in git; full dashboards, review movies, checkpoints,
and receipts stay on the 8TB artifact root.

![Raw Bayer timelapse decoded through the GPR preview path](docs/img/readme_z8_timelapse_1024.webp)

![GPR video comparison poster](docs/img/readme_preview_codec_vs_sota.png)

## Current Evidence Snapshot

| lane | proof now | open edge |
|---|---|---|
| **Compact stills** | Three 50 MP STILL tiers average **9.80 MB**, **15.05 MB**, and **27.17 MB** while passing the committed visual gate. | Mission/iPhone darkframes need strict source provenance before broad nonzero noise addback is promoted. |
| **Camera-class raw video** | Native 4096 x 3072 Bayer recompression clears the accepted **20+ fps** Pi 5 stand-in floor with valid `.gvid`, zero drops, recovery, metadata, and Lexar write-budget receipts. | Real Mission 1 sensor/DMA, storage, and display receipts are still required. |
| **Camera-back preview** | The same 4K `.gvid` decodes to full-frame 1024 x 768 RGB above **20 fps** on the Pi 5 stand-in. | Mission 1 rear-display/UI handoff remains unproven. |
| **Offline reconstruction** | Approved 4K cleanup and candidate-aware 8K SR emit editable `.gvid` plus ProRes review media. | PSF-conditioned replacements are research until they beat the locked baseline. |
| **Review/export scopes** | MOV / ProRes review outputs, PREVIEW offline/review, and PREVIEW live/camera-back are each tracked separately. | PREVIEW offline/review is not a live/camera-back preview path, and ProRes is not the primary raw deliverable. |
| **Premium still/SR** | 95 runtime-safe experiment receipts, raw-CFA targets, routed specialists, and promotion tooling exist. | Current candidates are not promotable; the next pass needs a clean-signal raw objective with calibrated noise addback. |

![Native 12MP encode speed evidence](docs/img/readme_native12_fps_plot.svg)

## Stills Performance And CNN Latitude

The stills path is not just smaller files. It is a production-gated raw-photo
pipeline with measured encode/decode receipts, three quality tiers, and a
matched 1x CNN that lets lower-bitrate files land in the same visual gate.

| still path | measured performance | quality/compression result |
|---|---|---|
| 12 MP still roundtrip | 4032 x 3024 rggb12 q3 encodes in **32.4 ms** and decodes in **52.7 ms** in the committed capability run. | Output is **4.72% of 16-bit raw size** with 43.31 dB Bayer PSNR, exceeding the locked criteria. |
| 50 MP still roundtrip | 8280 x 5520 rggb14 q3 encodes in **133.5 ms** and decodes in **243.2 ms** in the committed capability run. Pi-side 50 MP still encode is documented at **1.84 fps best** after the parallel DNG-read performance work. | Output is **6.78% of 16-bit raw size** with 53.85 dB Bayer PSNR, exceeding the locked criteria. |
| 100 MP X2D visual roundtrip | The real X2D 11,664 x 8,750 DNG fixture roundtrips DNG to GPR to DNG in the local audit with **593 ms** encode and **965 ms** decode. | The `.gpr` is **47 MB**, full-image raw Bayer PSNR is **49.21 dB**, and the dashboard includes 100% upper-left, center, and lower-right crop panels. |
| Real Bayer phase inventory | Canonical and broader local Mission 1, Z8, X2D, iPhone CFA, and old-photo fixtures parse as normal 2x2 Bayer. | Combined scans now cover real **RGGB + GBRG + GRBG + BGGR** fixtures, so broad normal-Bayer phase coverage is closed for the stills path. |
| Camera-noise coverage | Validated darkframe sidecars cover X2D at ISO **64/200/800/3200/12800** and Z8 at ISO **500**. The full-manifest Mission/iPhone audit parses **1,997 / 2,000** rows and finds **59** dark-like frames. | Mission 1 still needs a confirmed 4-frame same-ISO dark stack; iPhone has ISO1250 RGGB dark-like candidates but needs no-scene-signal provenance before nonzero noise removal/addback can be promoted. |
| Targeted real-fixture search | The current 3,000-file GoPro/Mission DNG/GPR scan parsed every file as normal Bayer: **2,892 GBRG** and **108 RGGB**. A broad old-photo scan adds **818** parsed normal Bayer rows, including **120 GRBG** Nikon D200 and **80 BGGR** Nikon D70 fixtures. | This closes real normal-Bayer phase coverage and leaves Mission/iPhone darkframe sidecars as the raw-stills sample/provenance gaps. |
| Stills fixture closure plan | The current gap plan turns the fixture/noise receipts into a capture checklist. | Mission ISO232 RGGB has **2** dark-like candidates and needs **2** more matching frames; iPhone ISO1250 RGGB has **27** dark-like candidates but needs true-dark provenance or recapture. |
| STILL smallest | `gpr_tools_q0` plus the matched q3 BIBO_1x CNN averages **9.80 MB** on 50 MP images. | Worst LPIPS is **0.031**, passing the STILL visual gate while landing 35% smaller than primary. |
| STILL primary | `gpr_tools_q3` plus the matched q3 BIBO_1x CNN averages **15.05 MB** on 50 MP images. | Worst LPIPS is **0.016**; this is the general-purpose visual-lossless still tier. |
| STILL archival | `gpr_tools_q8` needs no CNN and averages **27.17 MB** on 50 MP images. | Worst LPIPS is **0.004**; this is the tighter, larger-file tier. |

The key result is latitude: the same matched q3 BIBO_1x CNN supports both the
primary q3 tier and the smaller q0 tier, so a user can trade file size against
headroom without leaving the committed stills gate. At archival q8, the codec
is already tight enough that CNN restoration is not required. The current
source-of-truth tables are [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md)
and [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

![GPR still and video pipeline flow](docs/img/readme_pipeline_flow.svg)

## Visual Evidence

The repo keeps small preview assets in `docs/img/` and indexes full dashboards,
videos, and receipts under `/Volumes/OWC_8TB/gpr_work/artifacts`.

![Three STILL tiers, fine-detail crop](docs/img/still_three_tiers.png)

![CNN and SR improvement plot](docs/img/readme_cnn_sr_plot.svg)

![Mission native12 100 percent crop sheet](docs/img/readme_mission1_native12_100pct.png)

![Mission native12 2x SR contact sheet](docs/img/readme_mission1_2x_sr_contact.png)

## Mission 1 Numbered List

This branch is organized around the four production paths requested for the
Mission 1 workstream. The important boundary is that every path starts from raw
Bayer frames and a real `.gvid` stream. The branch does not count wrapped
camera `.GPR` payloads, JPEG-derived ProRes, or crop-only previews as
satisfying these four items.

| # | requested path | evidence on this branch | done definition | remaining gap |
|---:|---|---|---|---|
| 1 | `RAW 4K Bayer -> .gvid 4K Bayer` at `20 fps+` on Pi 5 | 1,440-frame aggregate Pi stand-in closure run: 4096 x 3072 Bayer, zero drops, valid `.gvid`, 20.50 fps whole-run wall, 21.52 fps median loop timing, and Lexar SILVER PLUS write-budget pass. The production `bench_fused` mmap-ring ready-only source receipt replays actual GP017602 raw through the FLL2 profile at 19.99 fps over 1,440 frames, with 45.67 ms median encode+write and valid `.gvid`. The firmware-facing `gpr_labs_encoder` shim is committed and covered by `test_labs_encoder_api`. | A camera-side encoder can ingest 4K Bayer frames, recompress them into `.gvid`, write them without drops, and clear the active 20 fps floor when source buffers are DMA-like rather than CPU-copied. | Real Mission 1 sensor/DMA/storage handoff receipt. The same receipt must come from the actual Mission 1 sensor/DMA or camera ring-buffer source and storage handoff, not the Pi stand-in. |
| 2 | `.gvid 4K Bayer -> Mission screen preview` at `20 fps+` | 1,440-frame aggregate Pi stand-in preview: the same 4096 x 3072 `.gvid` decodes to full-frame 1024 x 768 RGB at 24.20 fps whole-run wall and 43.86 fps median decode-plus-target. | The camera-back preview path decodes the 4K Bayer `.gvid`, renders a full-frame screen-resolution view, and clears 20 fps. | Real Mission 1 UI/display receipt. The Mission 1 rear-display/UI path still needs a real camera receipt with the display handoff and visual check marked executed. |
| 3 | `.gvid 4K Bayer -> 4K CNN .gvid` and `.gvid 4K Bayer -> 8K SR .gvid` | 4K cleanup passes the high-res-derived RGB/CFA target guard and 4K cleanup production signoff. Candidate-aware 8K SR has broad Mission42 and Z8 gates, 8K `.gvid` packaging, editable DNG/GPR packaging, Mission metadata receipts, objective visual review, manual signoff, and offline registry scope. | Desktop/post can take the 4K raw `.gvid`, run the CNN cleanup/SR path, and emit editable 4K or 8K Bayer `.gvid` artifacts with receipts. | This is intentionally offline/post today. It is not claimed as a live camera path or as a PSF-conditioned replacement until controlled native PSF evidence lands. |
| 4 | `.gvid 4K/8K Bayer -> ProRes 4K/8K` | 4K CNN `.gvid` to ProRes review and candidate-aware 8K `.gvid` to 8K ProRes review receipts are indexed in the release manifest. | Review media can be generated from the raw `.gvid` outputs for inspection and comparison without replacing the raw deliverable. | No current blocker for review/export; ProRes remains a review artifact, not the primary raw-video container. |

The last production promotion step is a real-camera closure run. The manual
target workflow now emits `target_preflight_receipt.json`,
`labs_target_bench.json`, `camera_handoff_receipt.json`,
`preview_decode_1024x768/receipt.json`, `preview_ui_receipt.json`, and
`mission1_camera_closure_run.json`. The aggregate closure validator proves the
target bench, handoff, and preview receipts agree on the same `.gvid`, frame
count, dimensions, pixel format, source provenance, and drop state. The
production gate remains blocked until those receipts come from a
`target_role=camera` run with real sensor/DMA, storage handoff, UI path, and
visual display checks marked executed.

For GoPro firmware/Labs evaluation, the shortest target-side path is
`python3 tools/run_gopro_mission1_quick_validation.py`; the full command,
inputs, receipts, and failure handling are in
[`docs/GOPRO_MISSION1_QUICK_VALIDATION.md`](docs/GOPRO_MISSION1_QUICK_VALIDATION.md).
The portable reviewer package is built with
`python3 tools/build_gopro_mission1_handoff_bundle.py`.
The GoPro intake audit verifies that package and keeps camera-production status
false until real Mission 1 sensor/DMA, storage, and rear-display receipts exist:
`/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html`.

For deterministic rehearsal before that handoff, `tools/mission1_dma_source_sim.py`
creates a separate-process FIFO producer/consumer that mimics a sensor
DMA/ring-buffer cadence. Its receipt captures inter-frame timing, producer
backpressure, consumer wait, complete-frame delivery, and hash consistency. Use
it to replay measured Mission 1 delay profiles on the Pi 5; it is explicitly
non-production evidence and does not replace the real sensor/DMA, storage, or
display receipts.
`tools/mission1_stream_source_encoder.py` extends that rehearsal by feeding the
deterministic FIFO source into the firmware-facing Labs encoder shim and
validating the resulting `.gvid`.

Machine-readable status and closure steps live in
[`docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md`](docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md).

The production log and full evidence matrix live in
[`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md). The current Mission 1
capture, preview, and SR snapshot is summarized in
[`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md).
The remaining productization contracts for release bundles, Labs/plugin
handoff, `.gvid` conformance, and CNN governance are tracked in
[`docs/PRODUCTIZATION_CONTRACTS.md`](docs/PRODUCTIZATION_CONTRACTS.md),
[`docs/RELEASE_ARTIFACTS.md`](docs/RELEASE_ARTIFACTS.md), and
[`docs/GVID_CONFORMANCE.md`](docs/GVID_CONFORMANCE.md).
The exact real samples and hardware receipts still needed to finish the four
pillars are pinned in
[`docs/PRODUCTION_CAPTURE_REQUIREMENTS.md`](docs/PRODUCTION_CAPTURE_REQUIREMENTS.md).

## Quality Model

GPR promotes a path only when the evidence matches the intended use. Stills,
VIDEO_FREEZE, PREVIEW, UPRESABLE, live 2K display, containers, and platform
performance each have different gates because they serve different workflows.

| gate family | what it protects |
|---|---|
| Worst-row visual gates | LPIPS, MS-SSIM, Y-PSNR, and dE2000 thresholds for rendered still/video/PREVIEW outputs. |
| Raw-domain gates | Bayer PSNR, MAE, p99 error, bit depth, pixel format, and Bayer decodability. |
| Runtime source policy | PREVIEW render paths must not use REF content at render time. |
| Container receipts | `.gvid`, MOV/GPR, DNG/GPR, metadata, frame count, and recovery validation. |
| Target-platform receipts | Pi 5 / Mission 1 capture timing, Mac/M-series render timing, memory, drops, and write budgets. |

Worst images matter more than averages. A path with a good mean and bad tail is
not promoted.

## Media And Dashboards

Large dashboards, videos, checkpoints, and generated media stay outside git in
`/Volumes/OWC_8TB/gpr_work/artifacts`. The README keeps only compact media and
links to source-of-truth indexes so the public page does not become an artifact
catalog.

| media family | where to start |
|---|---|
| Release bundle and artifact hashes | [`docs/RELEASE_ARTIFACTS.md`](docs/RELEASE_ARTIFACTS.md), [`docs/PRODUCTION_ARTIFACTS.md`](docs/PRODUCTION_ARTIFACTS.md), and [`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json) |
| Four-pillar status and remaining work | [`docs/PRODUCT_PILLAR_SCORECARD.md`](docs/PRODUCT_PILLAR_SCORECARD.md), [`docs/BIG_EFFORTS_STATUS.md`](docs/BIG_EFFORTS_STATUS.md), and [`docs/GOAL_CLOSURE_MATRIX.md`](docs/GOAL_CLOSURE_MATRIX.md) |
| CNN readiness and locked reconstruction evidence | [`docs/CNN_PRODUCT_SCORECARD_2026-06-29.md`](docs/CNN_PRODUCT_SCORECARD_2026-06-29.md), [`docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md`](docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md), and [`docs/MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md`](docs/MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md) |
| Mission 1 raw-video and preview handoff | [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md), [`docs/GOPRO_MISSION1_QUICK_VALIDATION.md`](docs/GOPRO_MISSION1_QUICK_VALIDATION.md), [`docs/LABS_INTAKE.md`](docs/LABS_INTAKE.md), and `/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html` |
| Raw stills, noise, and fixture coverage | [`docs/CAMERA_NOISE_CALIBRATION.md`](docs/CAMERA_NOISE_CALIBRATION.md), [`docs/RAW_STILLS_NOISE_FIRST_HOUR.md`](docs/RAW_STILLS_NOISE_FIRST_HOUR.md), [`docs/LOCAL_FIXTURE_COMPATIBILITY.md`](docs/LOCAL_FIXTURE_COMPATIBILITY.md), and `/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/index.html` |
| Premium still/SR and optional PSF research | [`docs/PREMIUM_STILL_SR.md`](docs/PREMIUM_STILL_SR.md), [`docs/PREMIUM_STILL_SR_FIRST_HOUR.md`](docs/PREMIUM_STILL_SR_FIRST_HOUR.md), [`docs/BAYER_RESIZE_PSF.md`](docs/BAYER_RESIZE_PSF.md), and `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_restormer_degrade_t64_20260702/index.html` |
| Approved 8K video CNN/SR A/B review | Z8 no-CNN/CNN ProRes movies live under `/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/`; Mission 1 broad and strict sequential scenes live under `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/` and `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/`. |

## Raw Output Ladder

| target | dimensions | classification | current result |
|---|---:|---|---|
| `mission1_preview_1024` | 1024 x 768 RGB from 4096 x 3072 `.gvid` | Pi stand-in preview timing pass; camera UI pending | Best receipt is 25.85 fps whole-run wall including extract process and 36.23 fps median decode-plus-target; selected 1,440-frame aggregate closure rerun is 24.20 fps wall and 43.86 fps median decode-plus-target. |
| `mission1_native12_4k_gvid` | 4096 x 3072 Bayer `.gvid` | camera MVP stand-in; real camera handoff pending | Selected 1,440-frame Pi stand-in closure run clears the active 20 fps floor at 20.50 fps wall / 21.52 fps median, with zero drops, valid `.gvid`, and Lexar SILVER PLUS budget pass. |
| `preview_offline_review_q8_threeway` | full-frame review render | PREVIEW offline/review; not a live/camera-back preview path | Current q8 three-way path passes the 84-row holdout but is slow and scoped to offline review. |
| `4k_raw_1x` | 4096 x 3072 Mission / 4140 x 2760 Z8 | editable 4K Bayer output for offline/post | Strong raw-domain evidence for 4K raw output, 4K CNN detail cleanup, and ProRes review. This is separate from the live Mission 1 camera MVP target above. |
| `8k_raw_2x` | 8192 x 6144 Mission / 8280 x 5520 Z8 | offline-production for post/reconstruction; not a live-camera path | Candidate-aware CNN SR is positive in broad full-frame gates; current SR throughput is about 1 fps on Mac/MPS. 42-frame 8192 x 6144 `.gvid` packaging and `.gvid` to 8K ProRes review are receipted. |

Details: [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md).
The current Mission 1 camera-back path is the simple 1024 x 768 full-frame
preview target from the same 4K `.gvid`.

## Final Camera Closure

The remaining production step is not another proxy benchmark. It is a
camera-role closure run that proves the same 4K Bayer `.gvid` encode and
1024 x 768 preview paths from the actual Mission 1 frame source, storage
writer, and rear display.

Start with the host-to-target dry run:

```bash
python3 tools/run_mission1_remote_closure_package.py \
  --dry-run \
  --camera-ready \
  --summary-json /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json
```

When the camera frame source, SD writer, and rear-display path are wired, remove
`--dry-run`. The production receipts are:

| receipt | proves |
|---|---|
| `target_preflight_receipt.json` | `target.role=camera`, target paths/binaries/storage are ready, concrete frame-source/storage/display labels are recorded, and `target_preflight_ready=true` plus `camera_closure_possible=true` after the real camera frame source, storage path, and display path have been asserted |
| `camera_handoff_receipt.json` | `target.role=camera`, `raw_source_kind=sensor_dma_capture` or `camera_ring_buffer`, sensor/DMA handoff executed, storage handoff executed, zero drops, valid `.gvid`, 120+ sustained frames, and `20+ fps` timing |
| `preview_ui_receipt.json` | `target.role=camera`, UI path executed, full-frame 1024 x 768 preview, 120+ sustained frames, no drops, visual display check, and `20+ fps` timing |
| `mission1_camera_closure_run.json` | the target preflight, encode, and preview receipts belong to the same camera closure package; production requires all three to be ready and aggregate-consistent |
| `closure_package.json` | the final package retains SHA-pinned target preflight, camera handoff, and preview UI receipt summaries before production promotion |

To simulate camera-source timing deterministically before that run:

```bash
python3 tools/mission1_dma_source_sim.py \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_dma_source_sim/current/receipt.json \
  --work-dir /Volumes/OWC_8TB/gpr_work/tmp/mission1_dma_source_sim \
  --source-width 4096 \
  --source-height 3072 \
  --frames 240 \
  --target-fps 20 \
  --delay-pattern-ms 0,0.5,0,1.0
```

That receipt should be compared with real Mission 1 source timing once sensor
handoff is available. It remains a profiling/replay tool, not a production
promotion artifact.

To feed the deterministic source into the real Labs encoder shim:

```bash
python3 tools/mission1_stream_source_encoder.py \
  --bench build-local/bin/labs_encoder_bench_cli \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_stream_source_encoder/current/receipt.json \
  --work-dir /Volumes/OWC_8TB/gpr_work/tmp/mission1_stream_source_encoder \
  --source-width 4096 \
  --source-height 3072 \
  --frames 120 \
  --target-fps 20 \
  --quality 8 \
  --pixel-format 1
```

This is still stand-in evidence. It verifies deterministic source cadence plus
encoder/container behavior, not real Mission 1 camera handoff.

Run the production gate after collecting those receipts:

```bash
python3 tools/mission1_numbered_list_readiness.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --require-production
```

## Quick Start

Build the codec and tools:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

Run CI-safe release checks:

```bash
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/test/check_sensitive_content.py
python3 tools/test/check_repo_artifact_hygiene.py
python3 tools/test/check_readme_media.py
python3 tools/test/test_check_readme_media.py
python3 tools/test/check_readme_product_pillars.py
python3 tools/test/test_check_readme_product_pillars.py
python3 tools/test/check_product_burndown_contract.py
python3 tools/test/test_check_product_burndown_contract.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_labs_readiness.py
python3 tools/test/test_mission1_numbered_list_readiness.py
python3 tools/test/test_mission1_numbered_list_closure_plan.py
python3 tools/test/test_build_mission1_8k_sr_visual_review.py
python3 tools/test/test_mission1_camera_dispatch_inputs.py
python3 tools/test/test_mission1_camera_closure_package.py
python3 tools/test/test_mission1_camera_hardware_audit.py
python3 tools/test/test_mission1_camera_source_probe.py
python3 tools/test/test_mission1_camera_target_preflight.py
python3 tools/test/test_collect_mission1_target_closure.py
python3 tools/test/test_run_mission1_target_closure_package.py
python3 tools/test/test_run_mission1_remote_closure_package.py
python3 tools/test/test_run_mission1_camera_closure.py
python3 tools/test/test_mission1_camera_closure_run.py
python3 tools/test/test_raw_resolution_targets.py
python3 tools/test/test_verify_release_manifest_artifacts.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
bash tools/test/test_labs_camera_handoff_receipt.sh
cmake --build build --target test_labs_encoder_api
build/bin/test_labs_encoder_api
BUILD_DIR=build bash tools/test/test_labs_encoder_bench_cli.sh
python3 tests/quality_gates/check_registry_consistency.py
python3 tests/quality_gates/audit_ship_pipelines.py --strict
```

Run strict external-artifact checks when the 8TB work drive is mounted:

```bash
export GPR_EXTERNAL_ROOT=/Volumes/OWC_8TB/gpr_work
export GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp
export GATE_TMPDIR=/Volumes/OWC_8TB/gpr_work/gate_tmp

python3 tools/verify_production_artifacts.py --strict
python3 tools/verify_release_manifest_artifacts.py --strict --summary
python3 tools/mission1_numbered_list_readiness.py --external-root "$GPR_EXTERNAL_ROOT"
python3 tools/check_mission1_camera_closure_package.py "$GPR_EXTERNAL_ROOT/artifacts/mission1_camera_closure_package_20260625/closure_package.json"
python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts
python3 tests/quality_gates/audit_production_readiness.py --strict
```

Walk the raw-video path:

```bash
# Pack a directory of per-frame .gpr payloads.
python3 tools/gvid_pack.py /clip/gpr_dir clip.gvid \
  --width 4096 \
  --height 3072 \
  --fps 24 \
  --quality 8 \
  --pixel-format 1 \
  --payload-kind fused_gpr

# Convert .gvid to ProRes review media on macOS.
./tools/gpr2prores/gpr2prores \
  --meta-dng /path/to/source_metadata.dng \
  --ckpt /path/to/metal_weights_dir \
  --cnn-backend metal \
  --demosaic core-image \
  clip.gvid review.mov
```

Full walkthrough: [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md).

## Repository Map

| path | purpose |
|---|---|
| `source/` | C codec, decoder, CLI, and test applications |
| `pipelines/registry.json` | Canonical codec/CNN/demosaic registry and production roles |
| `tests/quality_gates/` | Quality gates, readiness audits, and run logs |
| `tools/cnn/` | CNN training, evaluation, rendering, dashboards, and SR tools |
| `tools/gpr2prores/` | Mac review path, Metal CNN path, demosaic, and ProRes muxing |
| `tools/gpraw/` | MOV/GPR wrapper tooling |
| `tools/` | `.gvid`, Mission 1, Labs, artifact, and release verification tools |
| `docs/` | Status docs, methodology, runbooks, and evidence indexes |

## Documentation

| doc | purpose |
|---|---|
| [`docs/README.md`](docs/README.md) | Documentation index |
| [`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md) | Production goal, current matrix, and release checks |
| [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) | `.gvid` capture-to-ProRes walkthrough |
| [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md) | Current ship classes and quality-gate receipts |
| [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md) | Capture, PREVIEW, video, and review status |
| [`docs/LABS_READINESS_REVIEW.md`](docs/LABS_READINESS_REVIEW.md) | Labs readiness and Mission 1 handoff review |
| [`docs/GOPRO_MISSION1_QUICK_VALIDATION.md`](docs/GOPRO_MISSION1_QUICK_VALIDATION.md) | Minimal camera-side validation path and non-camera fallback plan |
| [`docs/MISSION1_STREAM_SOURCE_TIMING_2026-06-28.md`](docs/MISSION1_STREAM_SOURCE_TIMING_2026-06-28.md) | Pi stream-source-to-encoder timing results and next production gap |
| [`docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md`](docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md) | Current 4K cleanup / 8K SR CNN status and next actions |
| [`docs/PRODUCTIZATION_CONTRACTS.md`](docs/PRODUCTIZATION_CONTRACTS.md) | Release bundle, Labs handoff, `.gvid`, and CNN governance checklist |
| [`docs/PRODUCTION_CAPTURE_REQUIREMENTS.md`](docs/PRODUCTION_CAPTURE_REQUIREMENTS.md) | Exact release-blocking darkframes, camera receipts, model-promotion receipts, and optional PSF research pairs |
| [`docs/RELEASE_ARTIFACTS.md`](docs/RELEASE_ARTIFACTS.md) | GitHub release bundle contents, checksums, and upload flow |
| [`docs/GVID_CONFORMANCE.md`](docs/GVID_CONFORMANCE.md) | `.gvid` wire-contract and malformed-stream conformance suite |
| [`docs/PRODUCTION_ARTIFACTS.md`](docs/PRODUCTION_ARTIFACTS.md) | External model/artifact layout and hashes |

## Engineering Rules

- Shipping claims require committed registry entries, reproducible receipts,
  and passing gates.
- Runtime PREVIEW must not use REF content for routing, conditioning,
  low-frequency fields, high-frequency detail, or output synthesis.
- Large artifacts belong under `/Volumes/OWC_8TB/gpr_work`, not in the repo.
- Experimental paths stay documented but do not become production paths until
  evidence supports the intended role.
- A camera-ready claim requires target-hardware evidence. Pi/userland stand-ins
  are labeled as stand-ins.

## License

Dual licensed under Apache-2.0 or MIT. See [`LICENSE.txt`](LICENSE.txt).

## Trademarks

Product names and file-format names belong to their respective owners. This
project uses descriptive compatibility terms only.
