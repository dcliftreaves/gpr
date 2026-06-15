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
| Pi 5 embedded capture | BLOCKED on latest strict target receipt | Historical `ml2_q3_dec2` receipt reached 24.93 fps, but commit `0dd6660` strict 14,400-frame Labs run reaches 19.98 fps median with 0 drops and valid `.gvid`; the corrected pixel-format short probe reaches 19.85 fps; the best short luma-pair near miss reaches 23.54 fps and remains below target. Restore >= 24 fps before production claim. |
| UPRESABLE | PASS as editable raw | Half-res capture to full-res editable raw passes the UPRESABLE Bayer PSNR gate |
| `.gvid` | Primary raw-video container | Wraps per-frame FUSED `.gpr` payloads with metadata dispatch docs |
| MOV wrapper | Compatibility/export path | Available for GPR1/GPRr wrapper and downstream review/export tooling |
| ProRes review | Review artifact path | Generated from preview/review tools, not the primary raw deliverable |
| PREVIEW offline/review | PASS for q8 three-way runtime full-frame path | No-REF full-frame holdout passes 84/84 on the current receipt |
| PREVIEW live/camera-back | PASS for bounded 2K edge-safe display | 2K L2 HH clears Pi timing at 29.85 fps median / 37.1 ms p95; the 16 px edge-safe display policy passes 84/84 with worst LPIPS 0.1378. |
| 2K raw target | Pi live-capable raw path | Fast decode hits 37.59 fps median / 27.7 ms p95; selective L2 HH hits 29.85 fps median / 37.1 ms p95. |
| 4K raw target | Offline-only production classification | 43.7 fps median on Mac path; Pi decode-side is 6.3 fps and rendered-proxy LPIPS remains diagnostic only. |
| 8K raw target | Offline/review only | Current 2x raw reconstruction is about 2.7 fps on the local timing smoke. |

Source of truth:
[`release_evidence_manifest.json`](release_evidence_manifest.json),
[`SHIP_DECISION.md`](SHIP_DECISION.md),
[`VIDEO_STATUS.md`](VIDEO_STATUS.md),
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
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_labs_readiness.py
python3 tools/test/check_labs_target_receipts.py
python3 tools/verify_production_artifacts.py
python3 tools/verify_release_manifest_artifacts.py
python3 tools/live_preview_policy.py
python3 tools/test/test_raw_resolution_targets.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
bash tools/test/test_labs_bundle_verify.sh
bash tools/test/test_labs_target_bench_smoke.sh
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
python3 tools/verify_release_manifest_artifacts.py --strict
python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts
python3 tests/quality_gates/audit_production_readiness.py --strict
```

Run a quality gate for a registered pipeline:

```bash
python3 tests/quality_gates/run_gate.py \
  'codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools'
```
