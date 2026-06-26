# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)
[![STILL smallest](https://img.shields.io/badge/STILL%20smallest-9.80%20MB%20%2F%2050%20MP-2576c4?style=flat-square)](docs/SHIP_DECISION.md)
[![Mission preview](https://img.shields.io/badge/Mission%20preview-25.85%20fps%20Pi%205-2e7d32?style=flat-square)](docs/VIDEO_STATUS.md)
[![12MP Mission 1](https://img.shields.io/badge/12MP%20Mission%201-24.32%20fps%20stand--in%2C%20handoff%20open-d9822b?style=flat-square)](docs/VIDEO_STATUS.md)
[![Spec](https://img.shields.io/badge/built%20on-SMPTE%20ST%202073%20(VC--5)-555?style=flat-square)](docs/SPEC.md)

## Open Raw Video For Action Cameras

**8-bit JPEG size. 16-bit RAW quality. Editable Bayer video.**

GPR is an open raw Bayer media suite for stills, camera-class raw video,
camera-back preview, offline reconstruction, and review renders. It takes
sensor Bayer frames into compact `.gvid` streams, previews them at display
resolution, restores 4K/8K detail with decoder-side CNNs, and exports ProRes
review media while preserving an editable raw source.

![GPR raw-video showcase: 4K Bayer .gvid, live preview, native 12MP crops, and 8K SR review](docs/img/readme_showcase.webp)

| capture | camera preview | detail restore | review/export |
|---|---|---|---|
| 4096 x 3072 Bayer into `.gvid`, above the active 20 fps Pi 5 stand-in floor | 1024 x 768 full-frame preview from the same 4K `.gvid`, above 20 fps | 4K cleanup and offline 8K SR from raw Bayer sources | 4K and 8K ProRes review outputs from `.gvid` receipts |

The current evidence covers the prototype loop end to end: true Bayer
recompression into `.gvid`, camera-back preview decode from that stream, 4K
cleanup, offline 8K SR, editable DNG/GPR packaging, ProRes review, and release
receipts. The remaining production step is intentionally narrow: run the same
closure path from the actual Mission 1 sensor/DMA, SD writer, and rear display
instead of the Pi stand-in.

![Raw Bayer timelapse decoded through the GPR preview path](docs/img/readme_z8_timelapse_1024.webp)

> Raw Bayer timelapse frames rendered through the current preview path. Large
> review movies, dashboards, checkpoints, and receipts stay outside git under
> `/Volumes/OWC_8TB/gpr_work/artifacts`; compact media in `docs/img/` keeps the
> README reviewable.

![GPR video comparison poster](docs/img/readme_preview_codec_vs_sota.png)

## At A Glance

| result | current evidence |
|---|---|
| Compact 50 MP RAW stills | Three production STILL tiers average **9.80 MB**, **15.05 MB**, and **27.17 MB** per frame while passing the committed visual gate. |
| 1x decoder CNN restoration | The current still/video 1x CNN checkpoints remain gate-passing; no retrain is needed for the production STILL and VIDEO_FREEZE paths. |
| Raw video container | `.gvid` stores per-frame FUSED `.gpr` payloads with metadata dispatch, validation, and interrupted-tail recovery checks. |
| 12MP Mission 1 candidate | Native 4096 x 3072 Bayer recompression passes the active **20+ fps** Pi stand-in floor with valid `.gvid`, zero drops, and recovery receipts; strict 24 fps remains open. |
| Mission 1 preview target | 4096 x 3072 `.gvid` decodes to 1024 x 768 RGB preview above **20 fps** on the Pi 5 stand-in. |
| 2x / 8K reconstruction | Candidate-aware Mission native12-to-8K SR is **offline/review only** today; broad Mission42 and Z8 full-frame gates are positive, with `.gvid` decode-to-SR, 8K `.gvid`, and 8K ProRes receipts. |
| 4K rendered detail research | Bayer-output / RGB-supervised cleanup improves all 42 Mission frames against high-res-derived 4K RGB and CFA targets, and feeds the current candidate-aware 8K SR path. |

![Native 12MP encode speed evidence](docs/img/readme_native12_fps_plot.svg)

## Stills Performance And CNN Latitude

The stills path is not just smaller files. It is a production-gated raw-photo
pipeline with measured encode/decode receipts, three quality tiers, and a
matched 1x CNN that lets lower-bitrate files land in the same visual gate.

| still path | measured performance | quality/compression result |
|---|---|---|
| 12 MP still roundtrip | 4032 x 3024 rggb12 q3 encodes in **32.4 ms** and decodes in **52.7 ms** in the committed capability run. | Output is **4.72% of 16-bit raw size** with 43.31 dB Bayer PSNR, exceeding the locked criteria. |
| 50 MP still roundtrip | 8280 x 5520 rggb14 q3 encodes in **133.5 ms** and decodes in **243.2 ms** in the committed capability run. Pi-side 50 MP still encode is documented at **1.84 fps best** after the parallel DNG-read performance work. | Output is **6.78% of 16-bit raw size** with 53.85 dB Bayer PSNR, exceeding the locked criteria. |
| STILL smallest | `gpr_tools_q0` plus the matched q3 BIBO_1x CNN averages **9.80 MB** on 50 MP images. | Worst LPIPS is **0.031**, passing the STILL visual gate while landing 35% smaller than primary. |
| STILL primary | `gpr_tools_q3` plus the matched q3 BIBO_1x CNN averages **15.05 MB** on 50 MP images. | Worst LPIPS is **0.016**; this is the general-purpose visual-lossless still tier. |
| STILL archival | `gpr_tools_q8` needs no CNN and averages **27.17 MB** on 50 MP images. | Worst LPIPS is **0.004**; this is the tighter, larger-file tier. |

The key result is latitude: the same matched q3 BIBO_1x CNN supports both the
primary q3 tier and the smaller q0 tier, so a user can trade file size against
headroom without leaving the committed stills gate. At archival q8, the codec
is already tight enough that CNN restoration is not required. The current
source-of-truth tables are [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md)
and [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

## What It Enables

| capability | current evidence |
|---|---|
| Compact raw stills | Three STILL tiers pass the committed gate: **9.80 MB**, **15.05 MB**, and **27.17 MB** mean size per 50 MP frame. |
| Raw video streams | `.gvid` wraps per-frame FUSED `.gpr` payloads with metadata dispatch, validation, and interrupted-tail recovery checks. |
| Desktop-quality video/post | VIDEO_FREEZE passes the video gate with matched decoder CNN restoration for desktop/post workflows. |
| Review media | `.gvid` can feed MOV/GPR wrappers and ProRes review outputs for visual inspection. |
| Live camera-back preview | 4096 x 3072 `.gvid` decodes to 1024 x 768 RGB preview above 20 fps on the Pi 5 stand-in; Mission 1 display handoff remains the blocker. |
| 12MP Mission 1 candidate | Native 12MP true Bayer recompression passes the active 20+ fps Pi stand-in floor; strict 24 fps and actual camera handoff are still open. |
| 8K reconstruction | Mission 1 / Z8 12MP-to-8K SR has offline/Mac evidence, 8K `.gvid` packaging receipts, and `.gvid` to 8K ProRes review receipts. |

![GPR still and video pipeline flow](docs/img/readme_pipeline_flow.svg)

## Visual Evidence

The repo keeps small preview assets in `docs/img/` and indexes full dashboards,
videos, and receipts under `/Volumes/OWC_8TB/gpr_work/artifacts`.

![Three STILL tiers, fine-detail crop](docs/img/still_three_tiers.png)

![CNN and SR improvement plot](docs/img/readme_cnn_sr_plot.svg)

![Mission native12 100 percent crop sheet](docs/img/readme_mission1_native12_100pct.png)

![Mission native12 2x SR contact sheet](docs/img/readme_mission1_2x_sr_contact.png)

## Status At A Glance

| path | role | status |
|---|---|---|
| **STILL smallest / primary / archival** | Compressed raw photos | **Production-gated.** All three tiers pass the STILL gate; FUSED-stills paths are retired. |
| **VIDEO_FREEZE** | Full-res desktop/post raw video | **Production-gated.** Passes the committed VIDEO_FREEZE gate; not an embedded 24 fps capture path. |
| **`.gvid`** | Primary raw-video container | **Ready for prototype workflows.** Container, metadata dispatch, recovery, and validation tooling exist. |
| **MOV / ProRes** | Compatibility and review | **Receipted review/export path.** ProRes outputs are review media, not the primary raw deliverable. |
| **UPRESABLE** | Half-res capture to editable full-res raw | **Production-gated as editable raw.** Uses Bayer PSNR gates; rendered appearance is for review, not final grading. |
| **PREVIEW offline/review** | Full-frame no-REF render | **Production-gated for offline review.** Current q8 three-way path passes the 84-row holdout but is slow; this is not a live/camera-back preview path. |
| **PREVIEW live/camera-back** | 1024 x 768 display preview | **Pi stand-in target passes.** Current Mission 1 `.gvid` preview decode/render receipts are above 20 fps; exact camera UI integration remains a firmware handoff task. |
| **Mission 1 native 12MP** | True Bayer camera candidate | **20+ fps proxy passes; strict 24 fps not proven.** The best all-42 numbered-list receipt records 24.32 fps whole-run wall and 25.29 fps loop median on the Pi stand-in; the selected 1,440-frame aggregate closure rerun records 20.50 fps wall and 21.52 fps median. Camera handoff is still open. |
| **4K raw target** | Editable raw output | **Offline-only.** Strong raw-domain evidence, but not a Pi live decode path. |
| **8K SR target** | Offline reconstruction / review | **Offline-only.** Candidate-aware SR is positive on Mission42 and Z8 broad gates; 8K `.gvid` packaging and `.gvid` to 8K ProRes review are receipted. |

## Mission 1 Numbered List

This branch is organized around the four production paths requested for the
Mission 1 workstream. The important boundary is that every path starts from raw
Bayer frames and a real `.gvid` stream. The branch does not count wrapped
camera `.GPR` payloads, JPEG-derived ProRes, crop-only previews, or the older
`2k_raw_0p5x_l2hh` experiment as satisfying these four items.

| # | requested path | evidence on this branch | done definition | remaining gap |
|---:|---|---|---|---|
| 1 | `RAW 4K Bayer -> .gvid 4K Bayer` at `20 fps+` on Pi 5 | 1,440-frame aggregate Pi stand-in closure run: 4096 x 3072 Bayer, zero drops, valid `.gvid`, 20.50 fps whole-run wall, 21.52 fps median loop timing, and Lexar SILVER PLUS write-budget pass. The firmware-facing `gpr_labs_encoder` shim is committed and covered by `test_labs_encoder_api`. | A camera-side encoder can ingest 4K Bayer frames, recompress them into `.gvid`, write them without drops, and clear the active 20 fps floor. | Real Mission 1 sensor/DMA/storage handoff receipt. The same receipt must come from the actual Mission 1 sensor/DMA or camera ring-buffer source and storage handoff, not the Pi file-backed stand-in. |
| 2 | `.gvid 4K Bayer -> Mission screen preview` at `20 fps+` | 1,440-frame aggregate Pi stand-in preview: the same 4096 x 3072 `.gvid` decodes to full-frame 1024 x 768 RGB at 24.20 fps whole-run wall and 43.86 fps median decode-plus-target. | The camera-back preview path decodes the 4K Bayer `.gvid`, renders a full-frame screen-resolution view, and clears 20 fps. | Real Mission 1 UI/display receipt. The Mission 1 rear-display/UI path still needs a real camera receipt with the display handoff and visual check marked executed. |
| 3 | `.gvid 4K Bayer -> 4K CNN .gvid` and `.gvid 4K Bayer -> 8K SR .gvid` | 4K cleanup passes the high-res-derived RGB/CFA target guard and 4K cleanup production signoff. Candidate-aware 8K SR has broad Mission42 and Z8 gates, 8K `.gvid` packaging, editable DNG/GPR packaging, Mission metadata receipts, visual review, and offline registry scope. | Desktop/post can take the 4K raw `.gvid`, run the CNN cleanup/SR path, and emit editable 4K or 8K Bayer `.gvid` artifacts with receipts. | This is intentionally offline/post today. It is not claimed as a live camera path, and visual review still matters before treating a given SR checkpoint as final. |
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

Machine-readable status and closure steps live in
[`docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md`](docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md).

The production log and full evidence matrix live in
[`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md). The current Mission 1
capture, preview, and SR snapshot is summarized in
[`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md).

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
`/Volumes/OWC_8TB/gpr_work/artifacts`. The committed manifest indexes the
current evidence so strict local checks can verify it.

| media family | where to start |
|---|---|
| Release evidence manifest | [`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json) |
| Production artifact layout and hashes | [`docs/PRODUCTION_ARTIFACTS.md`](docs/PRODUCTION_ARTIFACTS.md) |
| Mission 1 numbered-list burndown | [`docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md`](docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md) |
| Still/video ship decisions | [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md) |
| Video, preview, and Mission 1 status | [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md) |
| Raw 2K / 4K / 8K ladder | [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md) |
| UPRESABLE editable raw workflow | [`docs/UPRESABLE_PIPELINE.md`](docs/UPRESABLE_PIPELINE.md) |
| Stills REF / codec-only / CNN dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/visual_compare_20260525_final/index.html` |
| Still 1x / video 1x / Mission 2x CNN dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_1x2x_review_20260618/index.html` |
| 12MP Mission 1 100% crop dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_current_review_100pct_dashboard_20260618/index.html` |
| Curated before/after ProRes review folder | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_prores_before_after_20260619/` |
| Original PREVIEW ProRes review folder | `/Volumes/OWC_8TB/gpr_work/artifacts/preview_review_20260604/` |
| Mission native12-to-8K ProRes review folder | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_q3_20260619/` |
| Mission 4K RGB/CFA target CNN dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_rgb_cfa_target_gate_wb_review/index.html` |
| Mission 4K CNN tone/green-bias audit | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_tone_audit_20260625/index.html` |
| Mission 4K CNN `.gvid` packaging receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_gvid_packaging_q8/labs_target_bench.json` |
| Mission 4K CNN `.gvid` to ProRes review | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_prores_review/` |
| Mission candidate-aware 8K SR broad dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_broad_fullframe/index.html` |
| Z8 candidate-aware 8K SR broad dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/z8_all24_fullframe/index.html` |
| Mission candidate-aware 8K `.gvid` to ProRes review | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_to_prores_42f_after_bounds_fix/mission42_8k_sr_gvid_42f_no_cnn_20p_prores.mov` |
| Mission candidate-aware 8K `.gvid` packaging receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_packaging_q3_after_bounds_fix/receipt.json` |
| Mission candidate-aware 8K `.gvid` to ProRes receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_4kcnn_8k_sr_gvid_to_prores_42f_after_bounds_fix/receipt.json` |

![GPR production status matrix](docs/img/readme_status_matrix.svg)

## Raw Output Ladder

| target | dimensions | classification | current result |
|---|---:|---|---|
| `mission1_preview_1024` | 1024 x 768 RGB from 4096 x 3072 `.gvid` | Pi stand-in preview timing pass; camera UI pending | Best receipt is 25.85 fps whole-run wall including extract process and 36.23 fps median decode-plus-target; selected 1,440-frame aggregate closure rerun is 24.20 fps wall and 43.86 fps median decode-plus-target. |
| `4k_raw_1x` | 4096 x 3072 Mission / 4140 x 2760 Z8 | editable 4K Bayer output | Mission 1 native12 capture/recompression clears the active 20+ fps Pi stand-in floor; 4K CNN detail cleanup and ProRes review are offline/post paths. |
| `8k_raw_2x` | 8192 x 6144 Mission / 8280 x 5520 Z8 | offline/review only | Candidate-aware CNN SR is positive in broad full-frame gates; current SR throughput is about 1 fps on Mac/MPS. 42-frame 8192 x 6144 `.gvid` packaging and `.gvid` to 8K ProRes review are receipted. |

Details: [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md).
That historical target ladder still tracks `2k_raw_0p5x_l2hh`; the current
Mission 1 camera-back path above is the simpler 1024 x 768 preview target.

## Mission 1 Reality Check

The native 12MP work is intentionally labeled tightly:

- It is true Bayer recompression, not wrapping pre-compressed camera `.GPR`
  payloads and calling that encode performance.
- Current quality-preserving profiles pass the active 20+ fps Pi stand-in
  floor across real Mission 1 12MP images. The best all-42 numbered-list
  receipt records 24.32 fps whole-run wall and 25.29 fps loop median; a fresh
  selected 1,440-frame aggregate closure rerun records 20.50 fps wall and 21.52 fps
  median.
- Strict 24 fps is not production-proven yet on the Pi stand-in path.
- Firmware readiness still requires actual camera sensor/DMA/storage handoff
  receipts, not just file-backed bench runs.

See [`docs/LABS_READINESS_REVIEW.md`](docs/LABS_READINESS_REVIEW.md) and
[`docs/LABS_MISSION1_RUNBOOK.md`](docs/LABS_MISSION1_RUNBOOK.md) for the
handoff contract.

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
| `camera_handoff_receipt.json` | `target.role=camera`, `raw_source_kind=sensor_dma_capture` or `camera_ring_buffer`, sensor/DMA handoff executed, storage handoff executed, zero drops, valid `.gvid`, and `20+ fps` timing |
| `preview_ui_receipt.json` | `target.role=camera`, UI path executed, full-frame 1024 x 768 preview, no drops, visual display check, and `20+ fps` timing |
| `mission1_camera_closure_run.json` | the target preflight, encode, and preview receipts belong to the same camera closure package; production requires all three to be ready and aggregate-consistent |
| `closure_package.json` | the final package retains SHA-pinned target preflight, camera handoff, and preview UI receipt summaries before production promotion |

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
