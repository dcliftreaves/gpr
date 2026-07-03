# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)
[![RAW stills](https://img.shields.io/badge/50MP%20RAW-9.80%20MB%20tier-2576c4?style=flat-square)](docs/SHIP_DECISION.md)
[![Mission preview](https://img.shields.io/badge/Mission%20preview-25.85%20fps%20Pi%205-2e7d32?style=flat-square)](docs/VIDEO_STATUS.md)
[![Spec](https://img.shields.io/badge/built%20on-SMPTE%20ST%202073%20(VC--5)-555?style=flat-square)](docs/SPEC.md)

## Open RAW Stills And Video For Action Cameras

**8-bit JPEG size. 16-bit RAW quality. Editable Bayer stills and video.**

GPR keeps the sensor data alive. It turns compact action-camera captures into
editable RAW stills, RAW video streams, camera-back preview, and offline 4K/8K
reconstruction without making JPEG the master.

![GPR raw capture suite: RAW stills, 4K Bayer .gvid, preview decode, and 8K SR review](docs/img/readme_showcase.webp)

GPR started as a practical still-photo problem: RAW files should stay editable,
but they should not have to move through the world as giant assets. The same
idea became a video pipeline. The working rule is: record Bayer, keep it small, preview from the same raw stream,
and spend desktop compute later when it visibly improves the image.

## What It Enables

| path | result |
|---|---|
| **RAW stills** | 50 MP and 100 MP-class editable Bayer photos at JPEG-like sizes. |
| **RAW video MVP** | 4K Bayer frames recompressed into `.gvid`, with camera-back preview from the same stream. |
| **Premium still/SR** | A slow offline still path for maximum quality, currently gated until a better no-REF model wins. |
| **Video reconstruction** | Approved 4K cleanup and 8K SR for desktop/post, with editable raw plus ProRes review media. |

The pipeline has one rule: the editable Bayer stream is the source of truth.
Stills, preview, `.gvid`, and ProRes review media all branch from raw sensor
data, so the fast camera path can stay simple while slower reconstruction stays
optional.

![GPR still and video pipeline flow](docs/img/readme_pipeline_flow.svg)

The readiness view separates what is already proven from what still needs a
camera-side or model-promotion receipt. It is a product boundary, not a running
experiment log.

![GPR four-pillar production readiness](docs/img/readme_status_matrix.svg)

## Image Proof

The small assets below are committed so the repo can be understood without
opening a dashboard server. Full receipts, hashes, dashboards, and videos live
in the linked evidence docs.

Stills came first. The target is simple to explain but hard to do well: make
large 50 MP and 100 MP-class Bayer captures small enough to treat like everyday
files while preserving 16-bit RAW editability and visual headroom.

![Three STILL tiers, fine-detail crop](docs/img/still_three_tiers.png)

Video made the same constraint harder. The raw stream has to be compact enough
to write continuously and direct enough to preview without a separate JPEG-first
path. This timelapse shows the preview side of that same raw-stream idea.

![Raw Bayer timelapse decoded through the GPR preview path](docs/img/readme_z8_timelapse_1024.webp)

The Mission native12 crop sheet is the camera MVP at 100% scale: real Bayer
dimensions, codec receipts, and visible crop evidence instead of a wrapper
around existing JPEG/GPR payloads.

![Mission native12 100 percent crop sheet](docs/img/readme_mission1_native12_100pct.png)

Offline reconstruction is where compute is allowed to be expensive. The 2x
contact sheet shows the post path improving review output while keeping the
editable raw/video source separate from the rendered media.

![Mission native12 2x SR contact sheet](docs/img/readme_mission1_2x_sr_contact.png)

## Performance Snapshot

| product path | current result | boundary |
|---|---|---|
| **50 MP stills** | Three visual-gated tiers average **9.80 MB**, **15.05 MB**, and **27.17 MB**. | Mission 1 and iPhone strict-provenance darkframe sidecars still need closure before broad noise addback is claimed. |
| **100 MP stills** | X2D 100 MP DNG roundtrips through editable GPR with normal Bayer handling. | Keep fixture coverage and editor-openability checks green. |
| **4K RAW video** | 4096 x 3072 Bayer `.gvid` clears the accepted **20+ fps** Pi 5 stand-in floor with zero drops. | Actual Mission 1 sensor/DMA, SD writer, and rear-display receipts are still required. |
| **Camera preview** | The same 4K `.gvid` previews full-frame at 1024 x 768 above **20 fps** on the Pi 5 stand-in. | Real camera UI/display handoff is the remaining proof. |
| **4K/8K reconstruction** | Offline 4K cleanup and 8K SR are approved for desktop/post review and editable raw outputs. | PSF/blur work is optional replacement research, not a release blocker. |

The performance claim matters because raw video is only useful when capture does
not miss frames. These numbers anchor the Pi 5 stand-in path, while the docs
keep the real Mission 1 sensor/DMA and SD-writer handoff open until GoPro-side
receipts exist.

![Native 12MP encode speed evidence](docs/img/readme_native12_fps_plot.svg)

CNNs and SR are quality levers, not the camera capture mechanism. The camera
path stands on Bayer plus `.gvid`; models can improve stills or reconstruction
when the workflow can afford the extra time.

![CNN and SR improvement plot](docs/img/readme_cnn_sr_plot.svg)

## Capabilities

GPR is organized around four product outcomes:

1. **1. Best RAW stills**: compact, editable RAW photos for 50 MP and 100 MP
   cameras, including normal RGGB/GBRG/GRBG/BGGR Bayer support.
2. **2. GoPro RAW video MVP**: 4K Bayer to `.gvid` at camera-relevant speed, plus
   preview from that same stream.
3. **3. Premium still/SR**: an expensive still-improvement lane. The current CNNs
   are not promoted; the next model must beat the no-REF 50 MP / 100 MP gate.
4. **4. RAW video reconstruction**: approved offline 4K cleanup and 8K SR for
   post-production workflows.

Current four-pillar completion is **83%**. That number is a production-readiness
burn-down, not an image-quality score and not a regression signal for locked
artifacts.

## Traceability

Detailed engineering receipts live here:

PREVIEW offline/review and PREVIEW live/camera-back are tracked separately;
offline/review PREVIEW is not a live/camera-back preview path.

| question | source |
|---|---|
| What is ready, what is open, and why? | [`docs/PRODUCT_PILLAR_SCORECARD.md`](docs/PRODUCT_PILLAR_SCORECARD.md), [`docs/GOAL_CLOSURE_MATRIX.md`](docs/GOAL_CLOSURE_MATRIX.md) |
| What exactly must happen to reach 100%? | [`docs/PRODUCTION_100_PERCENT_PLAN.md`](docs/PRODUCTION_100_PERCENT_PLAN.md), [`docs/PRODUCTION_100_PERCENT_EXECUTION_QUEUE.md`](docs/PRODUCTION_100_PERCENT_EXECUTION_QUEUE.md) |
| What proves the stills path? | [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md), [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md), [`docs/CAMERA_NOISE_CALIBRATION.md`](docs/CAMERA_NOISE_CALIBRATION.md) |
| What proves the Mission 1 raw-video path? | [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md), [`docs/GOPRO_MISSION1_QUICK_VALIDATION.md`](docs/GOPRO_MISSION1_QUICK_VALIDATION.md), [`docs/LABS_INTAKE.md`](docs/LABS_INTAKE.md) |
| What proves or blocks CNN/SR work? | [`docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md`](docs/MISSION1_CNN_NEXT_STEPS_2026-06-28.md), [`docs/PREMIUM_STILL_SR.md`](docs/PREMIUM_STILL_SR.md), [`docs/PREMIUM_STILL_SR_FIRST_HOUR.md`](docs/PREMIUM_STILL_SR_FIRST_HOUR.md) |
| Where are the large dashboards and videos? | [`docs/PRODUCTION_ARTIFACTS.md`](docs/PRODUCTION_ARTIFACTS.md), [`docs/WORKSPACE_AND_ARTIFACT_MAP.md`](docs/WORKSPACE_AND_ARTIFACT_MAP.md), [`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json) |
| What productization contracts must stay green? | [`docs/PRODUCTIZATION_CONTRACTS.md`](docs/PRODUCTIZATION_CONTRACTS.md), [`docs/PRODUCTION_CAPTURE_REQUIREMENTS.md`](docs/PRODUCTION_CAPTURE_REQUIREMENTS.md), [`docs/RELEASE_ARTIFACTS.md`](docs/RELEASE_ARTIFACTS.md), [`docs/GVID_CONFORMANCE.md`](docs/GVID_CONFORMANCE.md), [`docs/CNN_PRODUCT_SCORECARD_2026-06-29.md`](docs/CNN_PRODUCT_SCORECARD_2026-06-29.md) |

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
python3 tools/test/check_readme_product_pillars.py
python3 tools/test/check_product_burndown_contract.py
python3 tools/test/check_release_evidence_manifest.py
python3 tests/quality_gates/check_registry_consistency.py
python3 tests/quality_gates/audit_ship_pipelines.py --strict
```

Walk the raw-video path:

```bash
python3 tools/gvid_pack.py /clip/gpr_dir clip.gvid \
  --width 4096 \
  --height 3072 \
  --fps 24 \
  --quality 8 \
  --pixel-format 1 \
  --payload-kind fused_gpr

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
| `pipelines/registry.json` | Codec, CNN, demosaic, and production-role registry |
| `tests/quality_gates/` | Quality gates, readiness audits, and run logs |
| `tools/cnn/` | CNN training, evaluation, rendering, dashboards, and SR tools |
| `tools/gpr2prores/` | Mac review path, Metal CNN path, demosaic, and ProRes muxing |
| `tools/gpraw/` | MOV/GPR wrapper tooling |
| `tools/` | `.gvid`, Mission 1, Labs, artifact, and release verification tools |
| `docs/` | Runbooks, status docs, methodology, and evidence indexes |

## Engineering Rules

- Shipping claims require reproducible receipts and passing gates.
- Runtime preview must not use REF content.
- Large artifacts belong under `/Volumes/OWC_8TB/gpr_work`, not in git.
- Camera-ready claims require target-hardware evidence; Pi/userland stand-ins
  stay labeled as stand-ins.

## License

Dual licensed under Apache-2.0 or MIT. See [`LICENSE.txt`](LICENSE.txt).

## Trademarks

Product names and file-format names belong to their respective owners. This
project uses descriptive compatibility terms only.
