# Release Readiness

This is the production log for GPR. The top-level README stays media-focused;
this document holds the release goal, evidence matrix, and commands required
before claiming a production release.

## Production Goal

Productionize GPR as a release-quality raw media suite across stills, video,
PREVIEW/live decode, UPRESABLE, `.gvid`/container outputs, editable raw
outputs, dashboards, CI, and target-platform performance.

Stop only when:

- CI is green on `main`/`master` after the final push.
- Every registered production path is passing its committed gate or explicitly
  marked experimental.
- PREVIEW/live decode has a no-REF runtime path, full-image validation,
  holdout coverage, dashboard evidence, and documented worst rows.
- Stills, VIDEO_FREEZE, UPRESABLE, `.gvid`, MOV wrapper, editable DNG/GPR, and
  ProRes review outputs have current receipts.
- Pi 5 / Mission 1 and Mac/M5 paths have timing, memory, and FPS receipts.
- 2K, 4K, and 8K raw targets are classified as live-capable,
  preview-capable, or offline-only.
- If production quality cannot be reached, the blocker is named with metrics,
  visuals, artifact paths, and the next experiment.

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

| bucket | status | production rule |
|---|---|---|
| Shipping raw media | Stills, VIDEO_FREEZE, UPRESABLE, `.gvid`, MOV wrapper, editable DNG/GPR, and ProRes review outputs have receipts and pass their committed checks. | Keep these paths gated by the registry, manifest, hosted CI-safe checks, local strict artifact verification, and production-readiness audit. |
| Live-capable raw decode | 2K raw decode has Pi 5 timing receipts above 24 fps for both fast and selective-L2 HH modes. | Treat as raw decode/capture readiness, not as a full rendered PREVIEW quality pass. |
| Offline/review PREVIEW | q8 three-way no-REF full-frame runtime passes the current 84-row holdout. | Production for offline review only; current receipt is 13.65 s/image, 0.073 fps, 5.37 GB RSS. |
| Live/camera-back PREVIEW | PASS for bounded 2K display. The fast codec-only baseline fails the committed PREVIEW quality gate, but 2K selective-L2 HH with a 16 px edge-safe viewport passes the 84-row rendered proxy while clearing Pi 5 timing. | Ship only the bounded edge-safe display policy; exact-edge raw proxy caveats remain documented and are not promoted as full-frame rendered perfection. |
| 4K raw-video target | PASS on the Pi 5 stand-in for the accepted 20+ fps floor: true 4096 x 3072 Bayer frames recompress into `.gvid`, validate, recover interrupted tails, and preview from the same stream. | Firmware readiness still requires the real Mission 1 sensor/DMA or camera ring-buffer source, SD writer, and rear-display handoff receipts. Strict 24 fps is stretch performance research unless the product bar is raised again. |
| 8K raw reconstruction target | Offline/post only. The approved 8K SR path has `.gvid`, editable raw, ProRes, objective review, manual signoff, and release receipts. | Do not promote to live/camera use without new target-platform timing and quality evidence. |

## Open Production Blockers

These are the remaining items that prevent a broader production claim:

| blocker | current evidence | next proof needed |
|---|---|---|
| Mission 1 firmware readiness | Pi 5 stand-in receipts prove valid `.gvid`, zero drops, interrupted-tail recovery, storage-budget fit, 20+ fps native 12MP true-Bayer recompression, and 1024 x 768 preview from the same stream. | Actual Mission 1 sensor/DMA or camera ring-buffer source, SD writer, rear-display handoff, zero drops, valid `.gvid`, and 20+ fps camera-role timing receipts. |
| Mission 1 and iPhone noise sidecars | X2D and Z8 have validated camera-noise sidecars. Mission 1 and iPhone have candidate dark-like stacks, but not strict-provenance production sidecars. | Same-camera, same-ISO no-scene-signal darkframe stacks with source hashes, extraction receipts, `gpr.camera_noise_calibration.v1` sidecars, and raw-noise/signal audit pass. |
| Premium still-SR promotion | The raw-CFA target set, editable raw packaging, X2D/Z8/Mission specialists, and many diagnostic CNN receipts exist, but the best X2D recovery remains far below the 50 MP / 100 MP still-SR promotion gate. | A candidate-only runtime model that clears the dedicated still-SR gate for both 50 MP and 100 MP rows, emits editable DNG/GPR plus review media, records timing/RSS, and proves exact-sidecar-only noise policy. |
| Optional stretch work, not release blockers | Strict 24 fps native12 timing, 8K live-camera SR, and PSF-conditioned video/SR replacement all have useful research receipts and rejection evidence. | Keep them out of the release blocker list unless the product target is raised or a replacement already beats the locked baseline with the full receipt set. |

The production branch should stay narrow: keep reusable source, tests, registry
metadata, release checks, and concise evidence docs in main; keep generated
dashboards, videos, checkpoints, rejected-probe transcripts, and bulky worklogs
external or on a leaf branch. The current branch is clean and CI-backed; do not
re-expand it with bulky historical artifacts.

## Verification Refresh - 2026-06-18

Current local verification was rerun with large scratch and artifacts on
`/Volumes/OWC_8TB/gpr_work`.

Update on 2026-07-01:

- GitHub CI is green on `master` for commit `4e0b62f` after the SR shipping
  boundary refresh:
  `https://github.com/dcliftreaves/gpr/actions/runs/28527832547`.
- The public README, product-pillar scorecard, lock ledger, and release
  evidence manifest now agree that the current raw-video 4K cleanup and 8K SR
  paths are locked for offline/post shipment. PSF/blur work is optional
  replacement research, not a release blocker.
- Production capture submission tooling now separates release-blocking
  requirements from closed fixture rows and optional PSF research. A
  release-only submission must close Mission 1 darkframes, iPhone CFA
  darkframes, Mission 1 camera-role receipts, and premium still-SR promotion;
  omitted optional PSF rows are skipped.
- The branch is clean after the latest push; generated dashboards, videos, and
  checkpoints remain external under `/Volumes/OWC_8TB/gpr_work/artifacts`.

Update on 2026-06-25:

- Release manifest artifact verification was clean in strict summary mode: 134
  indexed artifacts, 374 production-artifact hash rows, 0 failures.
- README media, release-evidence manifest, repo artifact hygiene, sensitive
  content, Labs readiness, Labs target receipts, registry consistency, strict
  production-artifact verification, production-readiness audit, live-preview
  policy, raw-resolution target tests, Bayer-resample tests, and the Mission 1
  closure-package tests passed from the production branch.
- The Mission 1 numbered-list production audit intentionally exits with
  `evidence_passes_with_production_blockers`: items 3 and 4 are production
  ready for offline/post scope, while items 1 and 2 remain blocked by the real
  Mission 1 sensor/DMA/storage handoff receipt and the real Mission 1
  rear-display preview UI receipt.
- The current camera-role target preflight records concrete frame-source,
  storage, and display labels, and still refuses promotion until those labels
  are backed by real camera execution rather than stand-in paths.
- The refreshed sensor-ring preflight additionally proves the current Pi target
  does not expose `/dev/mission1/sensor_dma_ring`; final camera closure needs a
  real Mission 1 frame-source endpoint before the handoff and preview receipts
  can be produced.
- A real non-dry camera-ready closure launch was attempted after the target
  closure package was synced. It passed dispatch validation, failed the
  required hardware audit because no camera sensor is enumerated by
  rpicam/libcamera/V4L, and copied back the early failure receipts under
  `artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/`.

Update on 2026-06-19:

- `cmake --build build-local -j4` completed from the current production-slice
  worktree.
- Native codec smoke checks passed with external temp:
  `test_fused_band_roundtrip`, `test_fused_roundtrip` with `GPR_INCLUDE_LL=1`
  and `FUSED_INLINE_TOKENIZE=0`, `test_video_pipeline_sim_portable`,
  `test_jans_inline_tail_flush`, `ans_test`, native detail-residual sidecar,
  detail-residual benchmark regression, and raw `.gpr` roundtrip.
- The hosted CI Python dependency set stays limited to `numpy` and `rawpy`;
  OpenCV-dependent SR diagnostics remain local/leaf-branch tools unless they
  are promoted into the release check set.
- Strict registry/artifact/readiness checks were rerun after the q4/t2
  interpolation decision was added to the audit evidence.

Passing checks:

- Full still matrix: `0 failure(s)` across 1024-square, 12MP, 23MP, 50MP Z8,
  and 100MP X2D cases.
- C/C++ rebuild: `cmake --build build-local` completed after recompiling the
  changed codec and tool sources.
- CI-safe release guards: sensitive-content including history, repo artifact
  hygiene, release manifest, Labs readiness, Labs target receipts, production
  artifact inventory, release manifest artifact inventory, live preview policy,
  raw resolution targets, Bayer resample, `.gvid` pack/metadata, Labs bundle,
  Labs target bench smoke, native12 SR8K readiness, native12 frontier summary,
  native12 write-contention summary, Mission 1 SR codec-profile wiring,
  registry consistency, and ship-pipeline audit.
- Strict external-artifact checks with the 8TB work drive mounted:
  `verify_production_artifacts.py --strict`,
  `verify_release_manifest_artifacts.py --strict --summary`,
  `check_registry_consistency.py --strict-artifacts`, and
  `audit_production_readiness.py --strict`.
- Mission 1/SR source smokes: FLL2 T233 profile, fused payload analysis,
  raw-to-GPR roundtrip, Mission 1 metadata repack, and registry-driven
  `.gvid` to 8K SR render smoke.
- Bayer resample contract: exact same-plane area reference, shared
  `gaussian_area` production mode, CFA phase, G1/G2 separation, geometry
  rejection, and CLI mode handling.

Current interpretation:

- Stills have no current regression in the full synthetic matrix.
- Native 12MP Mission 1 true-Bayer recompression is production-bounded to the
  accepted 20+ fps Pi stand-in floor. The selected aggregate closure rerun
  records 20.50 fps wall and 21.52 fps median for 1,440 frames; an older
  all-42 numbered-list receipt records 24.32 fps whole-run wall and 25.29 fps
  loop median on the Pi stand-in. Strict 24 fps remains optional performance
  research unless the product target is raised again.
- 50MP-to-12MP Bayer training/recompression inputs use the shared
  CFA-preserving `gaussian_area` resampler: each Bayer color plane is
  anti-aliased and downsampled independently, so RGGB phase, green-plane
  separation, and raw bit-depth are preserved.
- 8K SR is offline/post evidence, not a live-camera path. Registry,
  checkpoint, Z8/Mission holdouts, `.gvid` decode-to-SR, editable DNG/GPR,
  ProRes review, metadata repack, visual-review, manual signoff, and
  production-promotion receipts pass for the approved path.
- Final camera firmware readiness still requires real Mission 1 sensor/DMA and
  camera-storage handoff evidence.
- Codec/CNN boundary: symbol/range issues remain codec correctness guardrails,
  while CNN/SR is used only for valid-codec visual recovery. See
  [`MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md`](MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md).

## Current Ship Matrix

| area | production status | current evidence |
|---|---|---|
| Stills | PASS: three tiers | 9.80 MB, 15.05 MB, and 27.17 MB per 50 MP frame all pass the STILL gate |
| VIDEO_FREEZE | PASS for desktop/post | `ml2_q3_l1x2` + matched CNN passes the VIDEO_FREEZE gate at 7.81 MB/frame |
| Pi 5 embedded capture | proxy-pass / firmware-blocked | Native 4096 x 3072 true-Bayer recompression passes the active 20+ fps Pi stand-in floor with valid `.gvid`, zero drops, interrupted-tail recovery, and Lexar write-budget evidence. The selected aggregate closure rerun records 20.50 fps wall and 21.52 fps median over 1,440 frames; an older all-42 numbered-list receipt records 24.32 fps whole-run wall and 25.29 fps loop median. Actual Mission 1 firmware readiness still requires a target-hardware camera-role receipt. |
| UPRESABLE | PASS as editable raw | Half-res capture to full-res editable raw passes the UPRESABLE Bayer PSNR gate |
| `.gvid` | Primary raw-video container | Wraps per-frame FUSED `.gpr` payloads with metadata dispatch docs |
| MOV wrapper | Compatibility/export path | Available for GPR1/GPRr wrapper and downstream review/export tooling |
| ProRes review | Review artifact path | Generated from preview/review tools, not the primary raw deliverable |
| PREVIEW offline/review | PASS for q8 three-way runtime full-frame path | No-REF full-frame holdout passes 84/84 on the current receipt |
| PREVIEW live/camera-back | PASS for `preview_live_mission1_1024` Pi stand-in display | The current 4K `.gvid` decodes to a full-frame 1024 x 768 RGB preview at 24.20 fps whole-run wall and 43.86 fps median decode-plus-target on the Pi stand-in; real Mission 1 UI/display handoff is still required. |
| 2K raw target | Pi live-capable raw path | Fast decode hits 37.59 fps median / 27.7 ms p95; selective L2 HH hits 29.85 fps median / 37.1 ms p95. |
| 4K raw target | Offline-only production classification | 43.7 fps median on Mac path; Pi decode-side is 6.3 fps and rendered-proxy LPIPS remains diagnostic only. |
| 8K raw target | Offline/review only | Current 2x raw reconstruction is about 2.7 fps on the local timing smoke. |

Source of truth:
[`release_evidence_manifest.json`](release_evidence_manifest.json),
[`SHIP_DECISION.md`](SHIP_DECISION.md),
[`VIDEO_STATUS.md`](VIDEO_STATUS.md),
[`MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md`](MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md),
[`FULL_PIPELINE_MATRIX.md`](FULL_PIPELINE_MATRIX.md), and
`../tests/quality_gates/runs/`.

## Release Evidence

The repo keeps source, registry entries, small receipts, and verification code
in git. Heavy dashboards, videos, checkpoints, and rendered media stay under
`/Volumes/OWC_8TB/gpr_work/artifacts` and are indexed by
[`release_evidence_manifest.json`](release_evidence_manifest.json). CI
validates that the manifest still names the required production paths, raw
targets, platform receipts, and dashboard evidence.

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

## Focused Checks

Run the public CI-safe release checks:

```bash
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/test/check_sensitive_content.py
python3 tools/test/check_sensitive_content.py --history
python3 tools/test/check_repo_artifact_hygiene.py
python3 tools/test/check_readme_media.py
python3 tools/test/test_check_readme_media.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_labs_readiness.py
python3 tools/test/test_mission1_numbered_list_readiness.py
python3 tools/test/test_mission1_numbered_list_closure_plan.py
python3 tools/test/test_mission1_8k_sr_production_promotion.py
python3 tools/test/test_check_mission1_cnn_closure.py
python3 tools/check_mission1_cnn_closure.py
python3 tools/check_mission1_cnn_closure.py --strict-artifacts
python3 tools/test/test_build_mission1_8k_sr_visual_review.py
python3 tools/test/test_build_mission1_8k_sr_visual_signoff.py
python3 tools/test/test_build_cnn_product_scorecard.py
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
python3 tools/test/check_labs_target_receipts.py
python3 tools/verify_production_artifacts.py
python3 tools/test/test_verify_production_artifacts.py
python3 tools/verify_release_manifest_artifacts.py --summary
python3 tools/test/test_verify_release_manifest_artifacts.py
python3 tools/live_preview_policy.py
python3 tools/test/test_raw_resolution_targets.py
python3 tools/test/test_bayer_resample.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
bash tools/test/test_labs_bundle_verify.sh
bash tools/test/test_labs_target_bench_smoke.sh
bash tools/test/test_labs_encoder_bench_cli.sh
bash tools/test/test_labs_camera_handoff_receipt.sh
bash tools/test/test_labs_preview_ui_receipt.sh
bash tools/test/test_build_labs_preview_ui_receipt.sh
bash tools/test/test_mission1_4k_cleanup_signoff_receipt.sh
bash tools/test/test_build_mission1_4k_cleanup_signoff_receipt.sh
python3 tools/test/test_native12_sr8k_readiness_audit.py
python3 tools/test/test_mission1_sr_production_gap_report.py
python3 tools/test/test_decide_mission1_sr_promotion.py
python3 tools/test/test_run_mission1_sr_guarded_experiment.py
python3 tools/test/test_mission1_native12_sr_frontier_summary.py
python3 tools/test/test_mission1_native12_frontier_summary.py
python3 tools/test/test_mission1_write_contention_summary.py
python3 tools/test/test_mission1_strict24_gap_report.py
python3 tools/test/test_mission1_strict24_probe_matrix_summary.py
python3 tools/test/test_mission1_sr_pair_codec_profiles.py
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
python3 tools/verify_release_manifest_artifacts.py --strict --summary
python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts
python3 tests/quality_gates/audit_production_readiness.py --strict
```

Run the Mission 1 numbered-list production-promotion gate only when the team is
ready to claim all four requested paths are production-ready:

```bash
python3 tools/mission1_numbered_list_readiness.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --require-production
```

This command is expected to fail until the camera hardware audit enumerates a
real camera source, the camera-role target preflight reports
`target_preflight_ready=true` and `camera_closure_possible=true`, records
concrete non-stand-in frame-source/storage/display labels, and actual camera
handoff plus actual preview UI receipts are present. The 4K cleanup production
signoff and 8K offline-production promotion receipts are already present.

One-line form for manifest checks:
`python3 tools/mission1_numbered_list_readiness.py --external-root /Volumes/OWC_8TB/gpr_work --require-production`

Run the strict Mission 1 stretch-performance check only when deciding whether
to raise the native 12MP path above the accepted 20+ fps floor:

```bash
python3 tests/quality_gates/audit_production_readiness.py --strict --require-mission1-strict24
```

This check is intentionally not part of the current release blocker list.
Treat it as optional performance research unless the product target is raised
again. The current raw-video MVP claim is bounded to the proven 20+ fps Pi
stand-in scope plus the still-open real Mission 1 camera-role receipt.

Run a quality gate for a registered pipeline:

```bash
python3 tests/quality_gates/run_gate.py \
  'codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools'
```
