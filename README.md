# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)
[![STILL smallest](https://img.shields.io/badge/STILL%20smallest-9.80%20MB%20%2F%2050%20MP-2576c4?style=flat-square)](docs/SHIP_DECISION.md)
[![2K live decode](https://img.shields.io/badge/2K%20live%20decode-29.85%20fps%20Pi%205-2e7d32?style=flat-square)](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md)
[![12MP Mission 1](https://img.shields.io/badge/12MP%20Mission%201-20%2B%20fps%20proxy%2C%2024%20open-d9822b?style=flat-square)](docs/VIDEO_STATUS.md)
[![Spec](https://img.shields.io/badge/built%20on-SMPTE%20ST%202073%20(VC--5)-555?style=flat-square)](docs/SPEC.md)

## Open Raw Video For Action Cameras

**8-bit JPEG size. 16-bit RAW quality. Raw video that stays editable.**

GPR is an open raw Bayer media suite for stills, raw video, review renders,
and editable camera-original workflows. It combines VC-5 wavelet coding,
decoder-side restoration, `.gvid` raw-video streams, MOV/ProRes review tools,
and reproducible quality gates.

For camera-lab work, it is a prototype path for raw-video capture, review, and
editable exports: compact raw media, visually checked decoder restoration, and
explicit proof for every performance and quality claim.

![GPR video comparison poster](docs/img/readme_preview_codec_vs_sota.png)

## At A Glance

| result | current evidence |
|---|---|
| Compact 50 MP RAW stills | Three production STILL tiers average **9.80 MB**, **15.05 MB**, and **27.17 MB** per frame while passing the committed visual gate. |
| 1x decoder CNN restoration | The current still/video 1x CNN checkpoints remain gate-passing; no retrain is needed for the production STILL and VIDEO_FREEZE paths. |
| Raw video container | `.gvid` stores per-frame FUSED `.gpr` payloads with metadata dispatch, validation, and interrupted-tail recovery checks. |
| 12MP Mission 1 candidate | Native 4096 x 3072 Bayer recompression passes the active **20+ fps** Pi stand-in floor with valid `.gvid`, zero drops, and recovery receipts; strict 24 fps remains open. |
| 2K live preview target | Bounded 2K selective-L2 HH display policy clears Pi 5 timing and passes the edge-safe display proxy gate. |
| 2x / 8K reconstruction | Mission native12-to-8K SR is **offline/review only** today; it has dashboards, checkpoint receipts, `.gvid` decode-to-SR receipts, and ProRes review media. |

![Native 12MP encode speed evidence](docs/img/readme_native12_fps_plot.svg)

## What It Enables

| capability | current evidence |
|---|---|
| Compact raw stills | Three STILL tiers pass the committed gate: **9.80 MB**, **15.05 MB**, and **27.17 MB** mean size per 50 MP frame. |
| Raw video streams | `.gvid` wraps per-frame FUSED `.gpr` payloads with metadata dispatch, validation, and interrupted-tail recovery checks. |
| Desktop-quality video/post | VIDEO_FREEZE passes the video gate with matched decoder CNN restoration for desktop/post workflows. |
| Review media | `.gvid` can feed MOV/GPR wrappers and ProRes review outputs for visual inspection. |
| Live camera-back preview | The bounded 2K selective-L2 HH path clears Pi 5 timing and passes the edge-safe display proxy gate. |
| 12MP Mission 1 candidate | Native 12MP true Bayer recompression passes the active 20+ fps Pi stand-in floor; strict 24 fps and actual camera handoff are still open. |
| 8K reconstruction | Mission 1 / Z8 12MP-to-8K SR has offline/Mac evidence, packaging receipts, and ProRes review receipts; it is not a live/camera path. |

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
| **PREVIEW live/camera-back** | Bounded display preview | **Production-gated only for the 2K edge-safe viewport.** Exact outer-edge display remains diagnostic. |
| **Mission 1 native 12MP** | True Bayer camera candidate | **20+ fps proxy passes; strict 24 fps not proven.** Current hard receipts are around 22-23 fps on Pi stand-in. |
| **4K raw target** | Editable raw output | **Offline-only.** Strong raw-domain evidence, but not a Pi live decode path. |
| **8K SR target** | Offline reconstruction / review | **Offline-only.** Registered checkpoint and receipts exist; current speed is Mac/offline, not live. |

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

![GPR production status matrix](docs/img/readme_status_matrix.svg)

## Raw Output Ladder

| target | dimensions | classification | current result |
|---|---:|---|---|
| `2k_raw_0p5x_fast` | 2070 x 1380 | live-capable raw decode | 37.59 fps median on Pi 5; fastest raw target, rendered proxy is diagnostic. |
| `2k_raw_0p5x_l2hh` | 2070 x 1380 | live-capable bounded PREVIEW | 29.85 fps median on Pi 5; 84/84 rendered rows pass with the 16 px edge-safe viewport. |
| `4k_raw_1x` | 4140 x 2760 | offline-only | Strong editable raw evidence; Pi decode-side timing is not live. |
| `8k_raw_2x` | 8280 x 5520 | offline/review only | CNN SR path has registered receipts and review packaging; current throughput is offline. |

Details: [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md).

## Mission 1 Reality Check

The native 12MP work is intentionally labeled tightly:

- It is true Bayer recompression, not wrapping pre-compressed camera `.GPR`
  payloads and calling that encode performance.
- Current quality-preserving profiles pass the active 20+ fps Pi stand-in
  floor across real Mission 1 12MP images.
- Strict 24 fps is not production-proven yet on the Pi stand-in path.
- Firmware readiness still requires actual camera sensor/DMA/storage handoff
  receipts, not just file-backed bench runs.

See [`docs/LABS_READINESS_REVIEW.md`](docs/LABS_READINESS_REVIEW.md) and
[`docs/LABS_MISSION1_RUNBOOK.md`](docs/LABS_MISSION1_RUNBOOK.md) for the
handoff contract.

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
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_labs_readiness.py
python3 tools/test/test_raw_resolution_targets.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
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
python3 tools/verify_release_manifest_artifacts.py --strict
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
