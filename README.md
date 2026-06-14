# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)
[![STILL smallest](https://img.shields.io/badge/STILL%20smallest-9.80%20MB%20%2F%2050%20MP-2576c4?style=flat-square)](docs/SHIP_DECISION.md)
[![Pi 5 video](https://img.shields.io/badge/Pi%205%20capture-24.93%20fps%20%2F%2050%20MP-1a5fb4?style=flat-square)](docs/VIDEO_STATUS.md)
[![Spec](https://img.shields.io/badge/built%20on-SMPTE%20ST%202073%20(VC--5)-555?style=flat-square)](docs/SPEC.md)

GPR is an open raw Bayer media suite built around VC-5 wavelet coding,
matched decoder-side restoration, raw-video containers, and reproducible
quality gates. The repo is being productionized around one rule: every
shipping path must either pass its committed gate with receipts, or be clearly
marked experimental.

![GPR production status matrix](docs/img/readme_status_matrix.svg)

![GPR still and video pipeline flow](docs/img/readme_pipeline_flow.svg)

## Production Goal

Use this as the active engineering goal for the repo:

```text
Productionize GPR as a release-quality raw media suite across stills, video,
PREVIEW/live decode, UPRESABLE, .gvid/container outputs, editable raw outputs,
dashboards, CI, and target-platform performance.

Stop only when:
- CI is green on main/master after the final push.
- Every registered production path is passing its committed gate or explicitly
  marked experimental.
- PREVIEW/live decode has a no-REF runtime path, full-image validation,
  holdout coverage, dashboard evidence, and documented worst rows.
- Stills, VIDEO_FREEZE, UPRESABLE, .gvid, MOV wrapper, editable DNG/GPR, and
  ProRes review outputs have current receipts.
- Pi 5 / Mission 1 and Mac/M5 paths have timing, memory, and FPS receipts.
- 2K, 4K, and 8K raw targets are classified as live-capable,
  preview-capable, or offline-only.
- If production quality cannot be reached, the blocker is named with metrics,
  visuals, artifact paths, and the next experiment.
```

Artifacts and temporary outputs should live under
`/Volumes/OWC_8TB/gpr_work`, with `TMPDIR` pointed at the external drive for
large runs.

## Production Definition Of Done

A path is production only when the repo can prove all of these from committed
source plus indexed external receipts:

| requirement | proof required |
|---|---|
| Quality | A committed quality gate, dashboard, or manifest receipt covers the actual ship class and passes by worst-row thresholds, not just averages. |
| Runtime inputs | The runtime source policy is explicit. PREVIEW render paths must not use REF content for routing, conditioning, low-frequency fields, high-frequency detail, or output synthesis. |
| Output contract | The produced file is readable by the intended consumer: Bayer raw stays Bayer-decodable, `.gvid` frames carry valid metadata, wrappers round-trip, and review MOV/ProRes files inspect correctly. |
| Performance | Timing, FPS/throughput, and memory are measured on the intended target: Pi 5 / Mission 1 for embedded capture and Mac/M5 for offline render. |
| Reproducibility | Checkpoint hashes, sidecars, registry entries, scripts, dashboards, and artifact paths are listed in the release evidence manifest or linked docs. |
| Repo hygiene | CI passes, generated artifacts stay outside main, and release checks include artifact verification, sensitive-content guard, manifest validation, and production-readiness audit. |

If any row is missing, the path must be marked experimental, diagnostic, or
offline-only. Do not promote an intermediate improvement because it is visually
better; promote only when the evidence matches the intended production role.

## Readiness Snapshot

The current release state is intentionally split between shipped raw-media
paths and the bounded live display policy:

| bucket | status | production rule |
|---|---|---|
| Shipping raw media | Stills, VIDEO_FREEZE, UPRESABLE, `.gvid`, MOV wrapper, editable DNG/GPR, and ProRes review outputs have receipts and pass their committed checks. | Keep these paths gated by the registry, manifest, CI, and production-readiness audit. |
| Live-capable raw decode | 2K raw decode has Pi 5 timing receipts above 24 fps for both fast and selective-L2 HH modes. | Treat as raw decode/capture readiness, not as a full rendered PREVIEW quality pass. |
| Offline/review PREVIEW | q8 three-way no-REF full-frame runtime passes the current 84-row holdout. | Production for offline review only; current receipt is 13.65 s/image, 0.073 fps, 5.37 GB RSS. |
| Live/camera-back PREVIEW | PASS for bounded 2K display. The fast codec-only baseline fails the committed PREVIEW quality gate, but 2K selective-L2 HH with a 16 px edge-safe viewport passes the 84-row rendered proxy while clearing Pi 5 timing. | Ship only the bounded edge-safe display policy; exact-edge raw proxy caveats remain documented and are not promoted as full-frame rendered perfection. |
| 4K and 8K raw targets | Offline-only. 4K is strong as editable raw; 8K is review/offline reconstruction. | Keep classified offline until target-platform timing and rendered-quality evidence both support promotion. |

## Current Ship Matrix

| area | production status | current evidence |
|---|---|---|
| Stills | PASS: three tiers | 9.80 MB, 15.05 MB, and 27.17 MB per 50 MP frame all pass the STILL gate |
| VIDEO_FREEZE | PASS for desktop/post | `ml2_q3_l1x2` + matched CNN passes the VIDEO_FREEZE gate at 7.81 MB/frame |
| Pi 5 embedded capture | PASS for half-res raw capture | `ml2_q3_dec2` captures 50 MP source-derived frames at 24.93 fps sustained |
| UPRESABLE | PASS as editable raw | Half-res capture to full-res editable raw passes the UPRESABLE Bayer PSNR gate |
| `.gvid` | Primary raw-video container | Wraps per-frame FUSED `.gpr` payloads with metadata dispatch docs |
| MOV wrapper | Compatibility/export path | Available for GPR1/GPRr wrapper and downstream review/export tooling |
| ProRes review | Review artifact path | Generated from preview/review tools, not the primary raw deliverable |
| PREVIEW offline/review | PASS for q8 three-way runtime full-frame path | No-REF full-frame holdout passes 84/84 on the current receipt |
| PREVIEW live/camera-back | PASS for bounded 2K edge-safe display | Speed is not the blocker: 2K L2 HH clears Pi timing at 29.85 fps median / 37.1 ms p95. Exact-edge rendered proxy is 80/84, but the production live policy uses a 16 px edge-safe viewport that passes 84/84 with worst LPIPS 0.1378. The older codec-only PREVIEW gate run still fails quality at 1/4 images passing, worst LPIPS 0.3119 |
| 2K raw target | Pi live-capable raw path | Fast decode mode hits 37.59 fps median / 27.7 ms p95 on Pi 5; selective L2 HH hits 29.85 fps median / 37.1 ms p95, reaches 80/84 exact-edge proxy crops, and reaches 84/84 with the 16 px edge-safe display policy |
| 4K raw target | Offline-only production classification | 43.7 fps median on Mac path; matched main-corpus raw quality passes, but Pi decode-side is 6.3 fps and rendered-proxy LPIPS remains diagnostic only |
| 8K raw target | Offline/review only | Current 2x raw reconstruction is about 2.7 fps on the local timing smoke |

Source of truth:
[`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json),
[`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md),
[`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md),
[`docs/FULL_PIPELINE_MATRIX.md`](docs/FULL_PIPELINE_MATRIX.md), and
`tests/quality_gates/runs/`.

## Release Evidence

The repo keeps source, registry entries, small receipts, and verification code
in git. Heavy dashboards, videos, checkpoints, and rendered media stay under
`/Volumes/OWC_8TB/gpr_work/artifacts` and are indexed by
[`docs/release_evidence_manifest.json`](docs/release_evidence_manifest.json).
CI validates that the manifest still names the required production paths, raw
targets, platform receipts, and dashboard evidence.

CI-safe release checks run on hosted GitHub Actions and prove the source,
registry, manifest, hygiene, live-policy, and small container contracts. The
artifact verifier also runs in inventory mode in CI so resolver and registry
hashing code stay exercised even when private checkpoints are absent. The full
release-readiness command below verifies local 8TB-backed production artifacts
in strict mode and runs the strict production-readiness audit; those external
checks are required before claiming a release, but are intentionally not run on
hosted CI.

| evidence | status | what it proves |
|---|---|---|
| `preview_offline_review_q8_threeway` | current | no-REF full-frame PREVIEW review path passes 84/84 holdout rows |
| `preview_candidate_evidence_rank` | diagnostic | candidate ranking separates production-shaped evidence from crop-only and oracle rows |
| `preview_failure_mode_audit` | experimental-blocker | live/full-image detail-placement failures are documented rather than hidden by crop-only success |
| `preview_source_ref_policy_audit` | diagnostic | runtime source policy is scored against resolved true REF rows |
| `raw_2k_fast_visual_proxy` | diagnostic | fastest 2K Pi raw mode clears 24 fps and has a raw-domain quality receipt, but reaches only 56/84 rendered proxy rows |
| `raw_2k_l2hh_visual_proxy` | current | 2K selective-L2 HH raw target reaches 80/84 exact-edge rendered proxy rows while clearing Pi timing |
| `raw_2k_l2hh_edge_safe_visual_proxy` | current | 2K selective-L2 HH with the `preview_live_2k_l2hh_edge_safe` production 16 px edge-safe display viewport reaches 84/84 rendered proxy rows |
| `raw_4k_visual_proxy` | diagnostic | 4K raw target is strong as editable raw but rendered-proxy LPIPS remains a diagnostic issue |
| `preview_review_media` | current | ProRes review files exist for preview/timelapse inspection |
| `gvid_metadata_dispatch` | diagnostic | `.gvid` metadata dispatch and clean-target routing behavior have dashboard evidence |
| `noise_signal_audit` | diagnostic | X2D ISO-stratified noise/signal training targets are audited before model training |

The Pi-to-Mac UPRESABLE bench is indexed as stage receipts: Pi encode loop
6.08 fps including SSH overhead, USB transfer 501 MB/s, Mac offline upres
1.79 fps, and GPRaw pack 180.26 fps.

The quick release-readiness command is:

```bash
export GPR_EXTERNAL_ROOT=/Volumes/OWC_8TB/gpr_work
export GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp
export GATE_TMPDIR=/Volumes/OWC_8TB/gpr_work/gate_tmp

python3 tools/test/check_release_evidence_manifest.py
python3 tools/verify_production_artifacts.py
python3 tools/verify_production_artifacts.py --strict
python3 tools/live_preview_policy.py
python3 tools/test/test_raw_resolution_targets.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
python3 tests/quality_gates/check_registry_consistency.py
python3 tests/quality_gates/audit_ship_pipelines.py --strict
python3 tests/quality_gates/audit_production_readiness.py --strict
python3 tools/test/check_sensitive_content.py
python3 tools/test/check_sensitive_content.py --history
python3 tools/test/check_repo_artifact_hygiene.py
```

## Stills

The still pipeline uses the legacy `gpr_tools` encoder with either a matched
BIBO_1x decoder CNN or no CNN for the archival tier.

| tier | pipeline | mean size | verdict |
|---|---|---:|---|
| smallest | `gpr_tools_q0` + matched q3 CNN | 9.80 MB | PASS |
| primary | `gpr_tools_q3` + matched q3 CNN | 15.05 MB | PASS |
| archival | `gpr_tools_q8` + no CNN | 27.17 MB | PASS |

The gate is per-image worst-case, not an average: LPIPS <= 0.05,
MS-SSIM >= 0.99, Y-PSNR >= 35 dB, and dE2000 <= 1.5.

![Three STILL tiers, fine-detail crop](docs/img/still_three_tiers.png)

![Three STILL tiers animated](docs/img/q_levels_animated.gif)

## Video And Raw Targets

The production video split is explicit:

| use case | path | status |
|---|---|---|
| Desktop full-res video | `ml2_q3_l1x2` + matched CNN | PASS, 7.81 MB/frame |
| Embedded capture | `ml2_q3_dec2` half-res raw stream | PASS, 24.93 fps on Pi 5 |
| Offline/review PREVIEW | q8 three-way no-REF full-frame runtime | PASS on current holdout, too slow for live |
| Live/camera-back display | 2K selective-L2 HH edge-safe viewport | production-bounded: raw decode clears 24 fps and the 16 px edge-safe rendered proxy is 84/84; exact-edge raw proxy remains 80/84 and the older codec-only gate remains experimental |

Raw output targets from the 24 fps capture stream:

| target | dimensions | method | current classification |
|---|---:|---|---|
| `2k_raw_0p5x_fast` | 2070 x 1380 | direct half-res decode with L2 highpass dropped | live-capable Pi raw mode at 37.59 fps median / 27.7 ms p95; 56/84 rendered proxy rows |
| `2k_raw_0p5x_l2hh` | 2070 x 1380 | direct half-res decode with selective L2 HH restored | live-capable Pi quality mode at 29.85 fps median / 37.1 ms p95; matched-source raw quality passes, exact-edge rendered proxy is 80/84, and a 16 px edge-safe display viewport is 84/84 |
| `4k_raw_1x` | 4140 x 2760 | decoded Bayer from `ml2_q3_dec2` | offline-only production classification: Mac editable raw passes, Pi decode-side is not live, rendered-proxy LPIPS is diagnostic |
| `8k_raw_2x` | 8280 x 5520 | BIBO_2x Bayer super-resolution | offline/review only |

Latest raw-target receipts are summarized in
[`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md).

## PREVIEW Status

PREVIEW has two different meanings in this repo:

- **Offline/review PREVIEW**: a no-REF, full-frame q8 three-way runtime path
  used to create reviewable rendered output from raw captures. This path passes
  the current 28-image / 84-row holdout, but runs at offline speed.
- **Live/camera-back PREVIEW**: an interactive display path. This is not the
  same problem. The current q8 three-way route is an offline/review path and
  not a live/camera-back preview path. The current codec-only live baseline
  fails the committed PREVIEW gate at 1/4 images passing, worst LPIPS 0.3119,
  worst MS-SSIM 0.8617, worst Y-PSNR 24.04, and worst dE2000 3.56. The current
  2K selective-L2 HH live display path clears Pi timing and passes the
  rendered proxy dashboard when the display viewport excludes the outer 16 px
  edge. Exact-edge raw proxy remains documented at 80/84, so promotion is
  limited to the bounded edge-safe display policy.

The latest PREVIEW blocker is not chroma direction. The remaining production
question is whether live-speed source-derived detail placement can pass the
visual gate without REF content at render time. See
[`docs/PREVIEW_RUNTIME_POLICY_2026-06-06.md`](docs/PREVIEW_RUNTIME_POLICY_2026-06-06.md),
[`docs/PREVIEW_SCENE_ROUTED_PRODUCTION_PASS_2026-06-06.md`](docs/PREVIEW_SCENE_ROUTED_PRODUCTION_PASS_2026-06-06.md), and
[`docs/PREVIEW_CLEAN_SOURCE_BLOCKER_2026-06-07.md`](docs/PREVIEW_CLEAN_SOURCE_BLOCKER_2026-06-07.md).

## Build

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

The CI workflow builds on Linux and macOS, generates synthetic 50 MP fixtures,
runs the codec roundtrip tests, and executes focused Python checks. The local
build used for production-path work commonly lives in `build-local/`.

## Focused Checks

Run the public CI-safe release checks:

```bash
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/test/check_sensitive_content.py
python3 tools/test/check_sensitive_content.py --history
python3 tools/test/check_repo_artifact_hygiene.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/verify_production_artifacts.py
python3 tools/live_preview_policy.py
python3 tools/test/test_raw_resolution_targets.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
python3 tests/quality_gates/check_registry_consistency.py
python3 tests/quality_gates/audit_ship_pipelines.py --strict
```

Run the external-artifact release checks when `/Volumes/OWC_8TB/gpr_work` is
mounted:

```bash
export GPR_EXTERNAL_ROOT=/Volumes/OWC_8TB/gpr_work
export GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp
export GATE_TMPDIR=/Volumes/OWC_8TB/gpr_work/gate_tmp

python3 tools/verify_production_artifacts.py --strict
python3 tests/quality_gates/audit_production_readiness.py --strict
```

Run a quality gate for a registered pipeline:

```bash
python3 tests/quality_gates/run_gate.py \
  'codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools'
```

Reproduce the current 2K raw fast-path measurements with external-drive
artifacts:

```bash
export GPR_EXTERNAL_ROOT=/Volumes/OWC_8TB/gpr_work
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/cnn/evaluate_raw_resolution_targets.py \
  --runtime-2k-target \
  --target-2k 2k_raw_0p5x_l2hh
python3 tools/cnn/build_raw_resolution_visual_dashboard.py \
  --target 2k_raw_0p5x_l2hh \
  --limit 28 \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_resolution_targets_20260614/visual_2k_l2hh_28f_explicit
python3 tools/cnn/build_raw_resolution_visual_dashboard.py \
  --target 4k_raw_1x \
  --limit 28 \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_resolution_targets_20260614/visual_4k_28f
python3 tools/cnn/analyze_raw_resolution_visual_failures.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/raw_resolution_targets_20260614/visual_2k_l2hh_28f_explicit/raw_resolution_targets_visual_dashboard.json \
  --edge-probe \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/raw_resolution_targets_20260614_analysis/visual_2k_l2hh_28f_explicit/raw_resolution_visual_failure_analysis.json

build-local/bin/fused_decode_cli frame.gpr 8280 5520 frame_2k_fast.raw 2k_raw_0p5x_fast
build-local/bin/fused_decode_cli frame.gpr 8280 5520 frame_2k_l2hh.raw 2k_raw_0p5x_l2hh
```

On a Pi 5 target:

```bash
python3 tools/test/run_pi_raw_resolution_bench.py \
  --limit 120
```

## Repository Map

| path | purpose |
|---|---|
| `source/` | C codec, decoder, CLI, and test applications |
| `pipelines/registry.json` | Canonical codec/CNN/demosaic registry |
| `tests/quality_gates/` | Per-class quality gates, readiness audits, and run logs |
| `tools/cnn/` | CNN training, evaluation, rendering, and dashboard tools |
| `tools/gpraw/` | Container and wrapper tooling |
| `docs/` | Ship decisions, status notes, methodology, and experiment summaries |

Useful docs:

- [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) - current `.gvid` capture-to-ProRes walkthrough.
- [`docs/README.md`](docs/README.md) - full documentation index.
- [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) - feature and platform matrix.
- [`docs/SHIP_DECISION.md`](docs/SHIP_DECISION.md) - current shipping quality gates.
- [`docs/VIDEO_STATUS.md`](docs/VIDEO_STATUS.md) - capture, preview, and review status.
- [`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`](docs/RAW_RESOLUTION_TARGETS_2026-06-14.md) - 2K/4K/8K raw target ladder.
- [`docs/UPRESABLE_PIPELINE.md`](docs/UPRESABLE_PIPELINE.md) - half-res capture to editable full-res raw.
- [`docs/GVID_METADATA_DISPATCH_2026-06-04.md`](docs/GVID_METADATA_DISPATCH_2026-06-04.md) - `.gvid` metadata dispatch.
- [`docs/EXPERIMENT_ARCHIVE_2026-06-04.md`](docs/EXPERIMENT_ARCHIVE_2026-06-04.md) - old experiment summary without committing bulky artifacts.

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
