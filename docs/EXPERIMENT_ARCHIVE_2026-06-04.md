# Experiment Archive - 2026-06-04

The production integration branch intentionally excludes generated artifacts,
checkpoint sweeps, and one-off experiment dashboards from `master`.

The full exploratory branch is preserved at:

```text
archive/multilevel-cascade-experiments-20260604
```

Additional cleanup history is preserved in:

```text
production/cnn-video-readme-20260619
dev/production-status-20260608
```

Those branches keep the broad investigation history from PR #32 and later
production-integration work, including:

- model checkpoint sweeps under `models/`;
- generated gate run receipts under `tests/quality_gates/runs/`;
- generated dashboard HTML/JSON outputs;
- exploratory CNN scripts for chroma, luma/detail, wavelet, guided-filter,
  Restormer, and hardtail candidate studies;
- session plans and intermediate writeups that were useful during research but
  are not production documentation.

The slim production branch keeps only the code, tests, and curated docs needed
to build, validate, and operate the current GPR/GVID paths. New large media,
dashboards, checkpoints, and scratch artifacts should remain on the external
work drive or a dedicated leaf branch unless they are required by CI or by a
small reproducible fixture.

Current external artifact root:

```text
/Volumes/OWC_8TB/gpr_work/artifacts
```

Current external scratch root:

```text
/Volumes/OWC_8TB/gpr_work/tmp
```

## Docs removed from master

These notes were useful during research, but are now superseded by the current
README, release readiness docs, video status, numbered-list burndown, and
release evidence manifest. Use the branches above or git history before the
cleanup commit if a future agent needs to inspect them.

| removed doc | why it is not in mainline docs |
|---|---|
| `docs/AUTONOMOUS_RUN_2026-05-25.md` | Session roll-up; the current docs index and git history are the durable record. |
| `docs/session_2026-05-25_progress.md` | Session transcript; superseded by current release and capability docs. |
| `docs/BIDO_DISTILLATION_PLAN.md` | Old BIDO/PREVIEW training worklog; current SR status lives in `VIDEO_STATUS.md`, `RAW_RESOLUTION_TARGETS_2026-06-14.md`, and the manifest. |
| `docs/CODEC_RAW_CLEAN_CANDIDATE_2026-06-04.md` | Dated raw-clean candidate writeup; superseded by the raw-noise audit and current production path docs. |
| `docs/CODEC_RAW_CLEAN_DISPATCH_2026-06-04.md` | Dated dispatch worklog; current `.gvid` metadata and render evidence are in the manifest-linked docs. |
| `docs/DARKFRAME_CALIBRATION_2026-06-05.md` | One-off corpus scan; not part of the current release contract. |
| `docs/GVID_SOURCE_METADATA_2026-06-04.md` | Early source-side metadata sidecar note; current metadata dispatch evidence is in `GVID_METADATA_DISPATCH_2026-06-04.md`. |
| `docs/LABS_FIRMWARE_REVIEW_BURNDOWN_GOAL.md` | Intermediate goal statement; current Labs readiness docs and runbook are authoritative. |
| `docs/NOISE_PROFILE_ANALYSIS_2026-06-04.md` | One-off Z8 noise-profile inspection; superseded by `RAW_NOISE_SIGNAL_AUDIT_2026-06-05.md`. |
| `docs/PREVIEW_HOLDOUT_RAW_CLEAN_AUDIT_2026-06-04.md` | Informational breadth audit; current PREVIEW evidence is manifest-indexed. |
| `docs/PREVIEW_RUNTIME_POLICY_2026-06-06.md` | Dated PREVIEW routing receipt; current live preview policy is `tools/live_preview_policy.py` plus `RAW_RESOLUTION_TARGETS_2026-06-14.md`. |
| `docs/PREVIEW_SCENE_ROUTED_PRODUCTION_PASS_2026-06-06.md` | Dated scene-routed receipt; superseded by current PREVIEW status and release evidence. |
| `docs/PREVIEW_SCENE_ROUTER_RESEARCH_2026-06-06.md` | Research note; useful context, not production documentation. |
| `docs/PRODUCTION_PR_SLICE_2026-06-18.md` | PR-shaping note; main now carries only the cleaned production surface. |
| `docs/RAW_CLEAN_CNN_CANDIDATE_2026-06-04.md` | Early raw-clean CNN candidate; superseded by current raw-signal and production docs. |
| `docs/RAW_CLEAN_REF_TARGETS_2026-06-04.md` | Early raw clean target builder note; superseded by current raw-noise audit. |
| `docs/RAW_CLEAN_RUNTIME_GATE_2026-06-04.md` | Dated runtime-gate note; no longer a current ship gate. |
| `docs/SYNTHETIC_RAW_NOISE_ADDBACK_2026-06-04.md` | Diagnostic noise-addback baseline; not part of the current production path. |

## Tools removed from master

These one-off tools had no current tests, docs, manifest entries, or import
paths after the docs cleanup. They remain recoverable from the archive branches
above if darkframe/noise-addback research resumes.

| removed tool | archived purpose |
|---|---|
| `tools/cnn/calibrate_darkframes.py` | Z8/X2D darkframe discovery and calibration probe. |
| `tools/cnn/synthesize_raw_noise_addback.py` | Synthetic raw residual addback diagnostic for early raw-clean targets. |

The 2026-06-26 cleanup also removed old raw-clean, Restormer, display-HF, and
PREVIEW-probe utility scripts that had no current tests, docs, manifest entries,
or live import paths. Recover them from the archive branches above if that
research line resumes.

## Additional research docs removed from master

| removed doc | why it is not in mainline docs |
|---|---|
| `docs/ANE_TRAINING_RESULTS.md` | M5 training roll-up; current checkpoint status lives in `PRODUCTION_ARTIFACTS.md` and `pipelines/registry.json`. |
| `docs/RESEARCH_VSR_AND_ANE.md` | Literature survey; not part of the current implementation surface. |
| `docs/shadow_highlight_recovery_research.md` | Tonemapping research note; superseded by current Mission 1 status and dashboards. |
| `docs/perf_findings_20260525.md` | Early performance findings; current performance evidence lives in `CAPABILITIES.md`, `LABS_TARGET_BENCH.md`, and `VIDEO_STATUS.md`. |
| `docs/rc-limited-quality.md` | Old rate-control quality note; current still/video gates are in `SHIP_DECISION.md`. |
| `docs/followups.md` | Parking-lot list; current open items are in release readiness and Mission 1 burndown docs. |
| `docs/RELEASE_NOTES_v2.1.md` | Historical release note with stale research pointers. |

## 2026-06-25 Raw-Match And Alignment Probes

The Mission 1 JPEG/DNG tone-matching and alignment probes were useful for
finding the display-look boundary, but they are not part of the production
camera path. They have been preserved outside the production branch at:

```text
/Volumes/OWC_8TB/gpr_work/experiment_archive/raw_match_alignment_20260625
```

That archive includes the Adobe/rawpy matching probes, local-tone and residual
fit tools, alignment sweep scripts, full-frame TIFF target notes, and related
one-off dashboards. The production branch keeps the current `.gvid`, preview,
4K cleanup, 8K SR, ProRes, readiness, and closure-receipt tooling.
