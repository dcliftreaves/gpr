# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)
[![STILL smallest](https://img.shields.io/badge/STILL%20smallest-9.80%20MB%20%2F%2050%20MP-2576c4?style=flat-square)](docs/SHIP_DECISION.md)
[![Pi 5 video](https://img.shields.io/badge/Pi%205%20capture-blocked%2019.98%20fps%20%2F%2024%20target-b04a1d?style=flat-square)](docs/VIDEO_STATUS.md)
[![Spec](https://img.shields.io/badge/built%20on-SMPTE%20ST%202073%20(VC--5)-555?style=flat-square)](docs/SPEC.md)

GPR is an open raw Bayer media suite for stills, raw video, review renders, and
editable camera-original workflows. It combines VC-5 wavelet coding, matched
decoder-side restoration, `.gvid` raw-video streams, MOV/ProRes review tooling,
and reproducible quality gates.

![GPR still and video pipeline flow](docs/img/readme_pipeline_flow.svg)

## Why It Exists

GPR is built for raw capture workflows that need three things at once:

| need | what GPR provides |
|---|---|
| Small raw files | Wavelet-coded Bayer frames with production-gated still and video tiers. |
| Real media outputs | `.gpr`, `.gvid`, MOV compatibility wrappers, editable DNG/GPR exports, and ProRes review files. |
| Measured deployment paths | Pi 5 capture/decode receipts, Mac/M5 offline render receipts, and CI-backed reproducibility checks. |

The project treats visual quality, decode speed, memory, and file compatibility
as one system. Shipping claims are backed by registry entries, quality receipts,
dashboards, and target-platform timing in
[`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md).

## Media Paths

![GPR production status matrix](docs/img/readme_status_matrix.svg)

| path | role | current state |
|---|---|---|
| Stills | Compressed raw photos | Three production tiers pass the STILL gate at 9.80 MB, 15.05 MB, and 27.17 MB per 50 MP frame. |
| VIDEO_FREEZE | Full-res raw video/post | Production-gated desktop/post paths with matched decoder CNN restoration. |
| Pi 5 capture | Embedded raw stream | Latest strict 14,400-frame Labs receipt validates `.gvid` and recovery with 0 drops, but is blocked at 19.98 fps median versus the 24 fps target. |
| PREVIEW offline/review | Full-frame review render | q8 three-way no-REF runtime path passes the current 84-row holdout; offline speed only. This is not a live/camera-back preview path. |
| PREVIEW live/camera-back | Bounded display | 2K selective-L2 HH edge-safe viewport clears Pi timing and rendered proxy gates. |
| UPRESABLE | Half-res capture to full-res raw | Produces editable full-res raw with ProRes and container review outputs. |
| `.gvid` | Raw-video container | Wraps per-frame FUSED `.gpr` payloads with metadata dispatch. |
| MOV / ProRes | Review and compatibility | MOV wrapper and ProRes review outputs are covered by artifact receipts. |

## Visual Quality

The still gate is worst-row based: LPIPS <= 0.05, MS-SSIM >= 0.99,
Y-PSNR >= 35 dB, and dE2000 <= 1.5. Video and PREVIEW use their own committed
thresholds and ship classes.

![Three STILL tiers, fine-detail crop](docs/img/still_three_tiers.png)

## Raw Targets

| target | dimensions | classification | evidence summary |
|---|---:|---|---|
| `2k_raw_0p5x_fast` | 2070 x 1380 | live-capable raw decode | 37.59 fps median / 27.7 ms p95 on Pi 5; rendered proxy remains diagnostic. |
| `2k_raw_0p5x_l2hh` | 2070 x 1380 | live-capable bounded PREVIEW | 29.85 fps median / 37.1 ms p95 on Pi 5; 84/84 rendered proxy rows with 16 px edge-safe viewport. |
| `4k_raw_1x` | 4140 x 2760 | offline-only | Mac editable raw path is fast enough for offline work; Pi decode-side is not live. |
| `8k_raw_2x` | 8280 x 5520 | offline/review only | BIBO_2x Bayer reconstruction is about 2.7 fps on the local timing smoke. |

Details: [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md)
and [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md).

## Review Media

Heavy rendered media stays outside git under
`/Volumes/OWC_8TB/gpr_work/artifacts`. The release manifest indexes the current
dashboards, videos, and receipts so local strict checks can verify them.

| artifact family | examples |
|---|---|
| PREVIEW dashboards | q8 three-way full-frame holdout, candidate evidence rank, source/REF policy audit. |
| ProRes review | codec-only, SOTA-v2, codec-vs-SOTA split, and UPRESABLE timelapse MOVs. |
| Raw containers | `.gvid` timelapse stream and GPR1 MOV compatibility wrapper. |
| Editable exports | DNG and GPR export directories from the UPRESABLE hard-tail media receipt. |

Start with [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for the
capture-to-ProRes walkthrough and
[`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json)
for the indexed artifact list.

## Quick Start

Build the codec and tools:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

Run the public CI-safe checks:

```bash
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/test/check_sensitive_content.py
python3 tools/test/check_sensitive_content.py --history
python3 tools/test/check_repo_artifact_hygiene.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/verify_production_artifacts.py
python3 tools/verify_release_manifest_artifacts.py
python3 tools/live_preview_policy.py
python3 tools/test/test_raw_resolution_targets.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
python3 tests/quality_gates/check_registry_consistency.py
python3 tests/quality_gates/audit_ship_pipelines.py --strict
```

Run strict local release checks when the external artifact drive is mounted:

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

## Docs

| doc | purpose |
|---|---|
| [`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md) | Production goal, release checks, evidence matrix, and strict verification flow. |
| [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) | `.gvid` capture-to-ProRes walkthrough. |
| [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md) | Current production ship classes and quality-gate receipts. |
| [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md) | Capture, PREVIEW, video, and review status. |
| [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md) | 2K/4K/8K raw target ladder. |
| [`docs/UPRESABLE_PIPELINE.md`](docs/UPRESABLE_PIPELINE.md) | Half-res capture to editable full-res raw. |
| [`docs/PRODUCTION_ARTIFACTS.md`](docs/PRODUCTION_ARTIFACTS.md) | External model/artifact layout and hashes. |
| [`docs/README.md`](docs/README.md) | Full documentation index. |

## Repository Map

| path | purpose |
|---|---|
| `source/` | C codec, decoder, CLI, and test applications |
| `pipelines/registry.json` | Canonical codec/CNN/demosaic registry |
| `tests/quality_gates/` | Per-class quality gates, readiness audits, and run logs |
| `tools/cnn/` | CNN training, evaluation, rendering, and dashboard tools |
| `tools/gpr2prores/` | Mac playback path, Metal CNN path, and ProRes muxer |
| `tools/gpraw/` | Container and wrapper tooling |
| `docs/` | Ship decisions, status notes, methodology, and experiment summaries |

## Engineering Rules

- Shipping claims require committed registry entries, reproducible receipts,
  and a passing gate.
- Worst-image rows matter more than aggregate averages.
- Runtime PREVIEW must not use REF content at route time or render time.
- Large artifacts belong under `/Volumes/OWC_8TB/gpr_work`, not in the repo.
- Experimental paths stay documented, but they do not become production paths
  until evidence supports the claim.

## License

Dual licensed under Apache-2.0 or MIT. See [`LICENSE`](LICENSE).

## Trademarks

Product names and file-format names belong to their respective owners. This
project uses descriptive compatibility terms only.
