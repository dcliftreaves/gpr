# Production PR Slice - 2026-06-18

This branch contains production code, receipts, and a large amount of
experiment history. The mergeable PR should be smaller than the working branch:
ship the reusable code, release gates, and evidence contracts, but keep bulky
worklogs, failed experiment transcripts, and exploratory one-off diagnostics in
external artifacts or a leaf branch.

Default rule: main gets only files that are needed to build, verify, reproduce,
or honestly document a production or explicitly registered offline path. A tool
that helped discover the path is not automatically part of the production PR.

## Keep In Main

These changes directly support the production objective and should stay in the
mainline PR.

| area | keep |
|---|---|
| Container and metadata | `.gvid` metadata validation, packing/dispatch, `gpr2prores` `.gvid` input, camera-handoff receipt tooling |
| Target benchmarking | `run_labs_target_bench.py`, Labs target workflow inputs, storage target fields, timing/detail parsing, receipt checks |
| Native 12MP codec path | Mission 1 FLL2/T233 profile tooling, true-Bayer quality dashboards, write-contention summary tooling, current accepted encoder fixes |
| Bayer resampling | CFA-preserving 50MP-to-12MP helpers and tests |
| 8K SR | Mission 1 native12 SR train/eval/render/package tools needed by committed registry entries, offline-only production scope guards, and small CI regressions for the SR evidence contract |
| Detail residual prototype | Native Bayer detail-residual sidecar prototype and regression test only if it remains referenced by the release readiness audit or a production blocker |
| CI guards | sensitive-content, artifact hygiene, release manifest, registry consistency, Labs readiness, target receipt, and SR frontier checks |
| High-level docs | README, release readiness, video status, Labs readiness, production artifacts, capability/status docs |

## Keep As External Evidence

These are valuable but should remain under `/Volumes/OWC_8TB/gpr_work/artifacts`
or in an experiment branch, referenced by hash from the main repo.

| evidence class | reason |
|---|---|
| Raw dashboards and media | Too large/noisy for main; referenced by manifest and artifact hashes |
| Long production status transcripts | Useful audit trail, but too broad for a focused PR |
| Failed performance probes | Preserve summary/hash only unless the probe became a reusable release check |
| Rejected CNN checkpoints and rejected checkpoint blends | Keep external; record decision and metrics in docs/registry only |
| Source corpus scans | Keep inventory and paths, not copied media |
| Exploratory CNN diagnostics | Keep in a leaf branch unless the diagnostic is directly invoked by CI, a strict audit, or a reproducibility manifest |

Archived leaf-branch docs moved out of the repo working tree:

| archived doc | sha256 |
|---|---|
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/production_pr_leaf_docs_20260618/MISSION1_12MP_PERFORMANCE_ARCHITECTURE.md` | `1b0a212fb68db23d998e83b5006128dd479b82690c0b0f673b0b172853b786e6` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/production_pr_leaf_docs_20260618/MISSION1_CAMERA_RAW_RENDERING_REQUIREMENTS.md` | `6d4893e383f65867746d44a256859c79e332d5e8f1e3fb0ec330a9693c513166` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/production_pr_leaf_docs_20260618/MISSION1_NATIVE12_STATUS_2026-06-16.md` | `9f7af0aa110644f3345777fa7de15c0e1f0ac877d535f23b2b987238845e6305` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/production_pr_leaf_docs_20260618/MISSION1_PRODUCTION_STATUS_2026-06-18.md` | `a73a105da01ccc65e2fe960a41ef2c102c99b9752b4308660cdcece9c37e1ac7` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/production_pr_leaf_docs_20260618/MISSION1_TRUE_BAYER_12MP_RECOMPRESSION_GOAL.md` | `bddaa296dffb9791e2f19366715ab65bb6ec2018eda919ad5a3b64934104db6c` |

## Current Product Boundary

- Stills: gate-passing; no current retrain needed for 1x still/video CNNs.
- Native 12MP Mission 1: quality-preserving true-Bayer path clears the 20+ fps
  Pi stand-in floor; strict 24 fps and actual camera handoff remain open.
- 8K SR: registered as offline/review candidate only. Older raw-target smoke
  receipts are roughly 2.7 fps; the current q4/t2 sidecar-aware `.gvid`
  decode+SR+write receipt is about 1.16 fps and must not be described as
  live-camera upscaling.
- PREVIEW: 2K edge-safe display path is live-capable; q8 full-frame routing is
  offline/review only.
- 50MP-to-12MP: use the CFA-preserving resampler for synthetic 12MP Bayer
  training/eval inputs; do not replace native 12MP capture when the sensor can
  provide native 4096 x 3072 raw.

## CI Surface

Keep the GitHub Actions surface intentionally small:

| workflow | trigger | role |
|---|---|---|
| `ci.yml` | `master` push and PR | hosted source/build/test gate |
| `labs-target.yml` | manual only | self-hosted Pi 5 / Mission 1 stand-in evidence |
| `release.yml` | version tags and manual | release tarball packaging |
| `sanitizers.yml` | scheduled and manual | slower ASan/UBSan/TSan coverage |
| `windows-test.yml` | manual only | Windows compatibility smoke |

Do not add more always-on PR workflows unless they replace an existing lane.
Target hardware, external dashboards, and private media evidence belong in
manual/self-hosted lanes or local strict checks.

## Svelte Main PR Cut

Use this as the review target before opening or updating the production PR.

| class | action for main PR |
|---|---|
| Build/runtime codec changes | Keep only if covered by CMake, codec smoke tests, `.gvid` tests, or target-bench receipts. |
| Mission 1 native12 scripts | Keep profile, frontier, strict-gap, write-contention, true-Bayer recompression, metadata, and handoff tooling that is referenced by release checks or docs. |
| SR production contract | Keep the registry entry, train/eval/render/package scripts, frontier summary, promotion decision logic, and tests that prove registered offline SR paths remain reproducible and correctly labeled. |
| SR research probes | Defer green-phase oracles, error-decomposition probes, sidecar retargeting experiments, phase/detail oracles, and rejected interpolation helpers unless a committed checker calls them. Summarize their conclusions in `MISSION1_SR_PRODUCTION_STATUS_2026-06-18.md` instead. |
| Dashboards/media/checkpoints | Keep out of git. Reference artifact path and sha256 from `PRODUCTION_ARTIFACTS.md`, `release_evidence_manifest.json`, or the status doc. |
| Long worklogs | Keep out of README and mainline docs unless condensed into a status table, blocker row, or reproducibility receipt. |

Practical first PR target:

1. Code that builds the current codec/container/runtime paths.
2. Tests and CI guards that run on hosted CI or strict local release checks.
3. Registry, manifest, and docs that prevent overclaiming: 12MP Mission 1 is
   20+ fps proxy / strict 24 open, and 8K SR is offline/review only.
4. No generated media, raw outputs, checkpoints, dashboards, or experiment logs.

## Current Untracked File Disposition

These files were still untracked when this slice note was written. The intent
is to keep small, reusable production/reproducibility code in main and keep
bulky outputs or run transcripts out of main.

| path | disposition |
|---|---|
| `docs/MISSION1_CODEC_CNN_RISK_BOUNDARY_2026-06-18.md` | keep: production boundary between codec validity and CNN/SR recovery |
| `docs/MISSION1_SR_PRODUCTION_STATUS_2026-06-18.md` | keep: current 12MP-to-8K SR frontier, rejected-probe receipts, and next-experiment boundary |
| `docs/PRODUCTION_PR_SLICE_2026-06-18.md` | keep: PR-surface and archive policy |
| `source/app/jans_coeff_bench.c` | keep: native12 tokenizer microbench required by readiness audit |
| `source/app/bayer_detail_residual_sidecar.c` | keep: native same-color Bayer detail-residual sidecar prototype for timing/byte-exact decode evidence |
| `tools/analyze_fused_coeff_roundtrip.py` | keep: codec-debug support for coefficient/payload invariants |
| `tools/analyze_fused_payload.py` | keep: codec-debug support; has regression coverage |
| `tools/bayer_resample.py` | keep: CFA-preserving 50MP-to-12MP training/eval input generator |
| `tools/extract_gvid_frame.py` | keep: lightweight `.gvid` inspection utility |
| `tools/mission1_camera_raw_metadata_audit.py` | keep: Mission 1 raw metadata/rendering evidence helper |
| `tools/mission1_native12_fll2_t2_profile.py` | keep: registered 20+ fps Mission 1 native12 profile contract |
| `tools/mission1_native12_frontier_summary.py` | keep: native12 codec frontier evidence summary required by readiness audit |
| `tools/mission1_native12_quality_dashboard.py` | keep: native12 review dashboard generator |
| `tools/mission1_native12_sr_frontier_summary.py` | keep: 8K SR frontier evidence summary required by readiness audit |
| `tools/mission1_strict24_gap_report.py` | keep: compact strict-24 loop/wall gap report required by readiness audit |
| `tools/mission1_true_bayer_recompression_matrix.py` | keep: native/raw recompression matrix helper |
| `tools/mission1_write_contention_summary.py` | keep: write-contention evidence summary required by readiness audit |
| `tools/cnn/*.py` | mixed: keep only production-contract train/eval/render/package/frontier/promotion tools in the first PR; defer one-off probes and rejected-experiment helpers to a leaf branch unless a strict checker requires them |
| `tools/test/test_analyze_fused_payload.sh` | keep: codec-debug regression |
| `tools/test/test_bayer_resample.py` | keep: CFA-resampler regression |
| `tools/test/test_gpr_tools_raw_gpr_roundtrip.sh` | keep: raw `.gpr` roundtrip regression |
| `tools/test/test_mission1_metadata_repack.sh` | keep: Mission 1 metadata/repack regression |
| `tools/test/test_mission1_native12_fll2_t2_profile.sh` | keep: native12 profile contract regression |
| `tools/test/test_mission1_native12_frontier_summary.py` | keep: native12 frontier summary regression required by readiness audit |
| `tools/test/test_mission1_native12_sr_frontier_summary.py` | keep: SR frontier summary regression required by readiness audit |
| `tools/test/test_mission1_strict24_gap_report.py` | keep: strict-24 gap report regression required by readiness audit |
| `tools/test/test_mission1_sr_pair_codec_profiles.py` | keep: SR training-pair codec profile regression |
| `tools/test/test_mission1_write_contention_summary.py` | keep: write-contention summary regression required by readiness audit |
| `tools/test/test_native12_sr8k_readiness_audit.py` | keep: native12 SR8K readiness-audit regression |
| `tools/test/test_render_gvid_sr_registry.sh` | keep: `.gvid` to SR registry/render regression |
| `tools/test/test_analyze_mission1_sr_codec_sensitivity.py` | keep: codec-sensitivity analyzer regression |
| `tools/test/test_analyze_mission1_sr_phase_reconstruction.py` | keep: same-color Bayer phase-reconstruction analyzer regression |
| `tools/test/test_apply_bayer_detail_shrink_raw.py` | keep: deterministic cleanup regression |
| `tools/test/test_apply_bayer_detail_residual_oracle_raw.py` | keep: codec-side same-color detail-residual oracle regression |
| `tools/test/test_analyze_bayer_detail_residual_budget.py` | keep: broad same-color detail-residual budget regression |
| `tools/test/test_apply_bayer_phase_oracle_raw.py` | keep: same-color Bayer detail-content oracle regression |
| `tools/test/test_pack_bayer_detail_residual_sidecar.py` | keep: same-color detail-residual sidecar pack/unpack regression |
| `tools/test/test_bayer_detail_residual_sidecar_native.sh` | keep: native detail-residual sidecar regression |
| `tools/test/test_bench_bayer_detail_residual_sidecar_native.py` | keep: native sidecar thread-benchmark summary regression |
| `tools/test/test_apply_bayer_unsharp_raw.py` | keep: deterministic unsharp regression |
| `tools/test/test_build_mission1_sr_coverage_manifest.py` | keep: full-frame SR coverage-manifest regression |
| `tools/test/test_mine_mission1_sr_hard_tiles.py` | keep: gate/codec-sensitive hard-tile miner regression |
| `tools/test/test_plan_mission1_sr_gate_iteration.py` | keep: full-frame gate-driven SR iteration planner regression |
| `tools/test/test_scan_mission1_sr_fullframe_checkpoints.py` | keep: full-frame checkpoint scanner regression |
| `tools/test/test_select_mission1_sr_gate_candidate.py` | keep: gate-candidate selector regression |
| `tools/test/test_train_bayer_low_cleanup.py` | keep: same-color Bayer cleanup detail-loss regression |
| `tools/test/test_train_mission1_sr_expand.py` | keep: SR trainer architecture/scope/plane-weight/phase-loss regression |
| `tools/test/test_verify_production_artifacts.py` | keep: production-artifact verifier regression |

Deferred SR diagnostics archived outside the main PR:

| archived file | sha256 |
|---|---|
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/deferred_sr_diagnostics_20260619/analyze_mission1_sr_error_decomposition.py` | `1e54cbcb3fa0e7996f2b60594b17d4cf17cce1d12afc5d063a103bdc2bd24834` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/deferred_sr_diagnostics_20260619/probe_mission1_sr_green_phase_oracle.py` | `5b945f1a4eb0bae4d00d141d68c555d4d73b13a94d4087ee926ecc62280aaaff` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/deferred_sr_diagnostics_20260619/retarget_mission1_sr_pair_inputs.py` | `c66ff938cd645b0bcd6c1c719612758166bcd6302524405e672961aeba19980f` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/deferred_sr_diagnostics_20260619/test_analyze_mission1_sr_error_decomposition.py` | `3d342831ff1685c822ca63e777d39909f3fdb9ad828c0625beb13e3f3d07e5f8` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/deferred_sr_diagnostics_20260619/test_probe_mission1_sr_green_phase_oracle.py` | `09e7c3790cc54f2b1f9d43ad1efd88f50d9c13f69b214a906a37065670fcd859` |
| `/Volumes/OWC_8TB/gpr_work/artifacts/repo_archives/deferred_sr_diagnostics_20260619/test_retarget_mission1_sr_pair_inputs.py` | `fc88e78894afb97c72bbf45a1417df148f4013166b3acb72e8e809c0f3bf7559` |

## Merge Checklist

1. Keep all code required by strict readiness checks.
2. Add only keep-listed source/test/doc files that are required by build, CI,
   registry, manifest, or strict release checks.
3. Remove, unstage, or move experiment-only worklogs and one-off diagnostics
   from the main PR unless a strict checker depends on them.
4. Ensure every external artifact referenced by `docs/release_evidence_manifest.json`,
   `pipelines/registry.json`, or `docs/PRODUCTION_ARTIFACTS.md` verifies by hash.
5. Keep `production_scope: offline_review_only` on every Mission 1 native12 8K
   SR pipeline until live timing evidence exists.
6. Keep Mission 1 camera readiness blocked until a target-hardware
   sensor/DMA/storage receipt exists.
7. Run:

```bash
python3 tools/test/check_sensitive_content.py
python3 tools/test/check_labs_readiness.py
python3 tools/test/check_release_evidence_manifest.py
python3 tests/quality_gates/check_registry_consistency.py
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp /Users/dcliftreaves/anaconda3/envs/py3_10/bin/python tests/quality_gates/check_registry_consistency.py --strict-artifacts
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp /Users/dcliftreaves/anaconda3/envs/py3_10/bin/python tools/verify_release_manifest_artifacts.py --strict
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp /Users/dcliftreaves/anaconda3/envs/py3_10/bin/python tools/verify_production_artifacts.py --strict
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp /Users/dcliftreaves/anaconda3/envs/py3_10/bin/python tests/quality_gates/audit_production_readiness.py --strict
git diff --check
```

`check_release_evidence_manifest.py` also validates that every repo path named
by `release_checks`, `ci_checks`, or `blocked_release_checks` exists and is
tracked. This catches clean-checkout failures where CI references a local
diagnostic that was not included in the PR.
