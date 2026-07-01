# Workspace And Artifact Map

Last refreshed: 2026-07-01

This file records where the active production work lives on this workstation.
It is operational documentation, not a portable build requirement. The GitHub
repo remains the source of truth for committed code and docs; the 8TB drive
holds local worktrees, large generated artifacts, checkpoints, dashboards, and
temporary data that should not be committed.

## Active Checkouts

| purpose | location | notes |
|---|---|---|
| Main production branch | `/Volumes/OWC_8TB/gpr_work/worktrees/gpr_clean_sanitized_20260604` | Active `master` worktree tracking `origin/master`. Use this for current code, docs, tests, release manifests, and CI-linked commits. |
| GoPro Labs extension/API PR | `/Volumes/OWC_8TB/gpr_work/worktrees/gpr_labs_extension_api_pr` | Separate worktree for upstream-facing Labs/plugin API proposal work. Keep it separate from the main product branch unless intentionally merging a cleaned change. |

The historical path `/Users/dcliftreaves/Documents/Github/gpr` is not the
authoritative checkout for the current work. Use the 8TB worktree above unless
the branch has intentionally been moved.

## External Root

| path | role |
|---|---|
| `/Volumes/OWC_8TB/gpr_work` | Project external root for artifacts, models, data, temporary files, caches, build outputs, and worktrees. |
| `/Volumes/OWC_8TB/gpr_work/tmp` | Preferred `TMPDIR` / `GPR_TMPDIR` for local runs. Avoid writing large temporary data to the internal OS drive. |
| `/Volumes/OWC_8TB/gpr_work/artifacts` | Generated dashboards, receipts, review movies, manifests, and audit outputs. Large artifacts stay here, not in git. |
| `/Volumes/OWC_8TB/gpr_work/checkpoints` | Long-lived model checkpoints that are not committed. |
| `/Volumes/OWC_8TB/gpr_work/models` | Model-export staging and local model assets. |
| `/Volumes/OWC_8TB/gpr_work/venvs` | Local Python environments, including the ML environment used for CNN/audit work. |
| `/Volumes/OWC_8TB/gpr_work/cache`, `/Volumes/OWC_8TB/gpr_work/torch_cache`, `/Volumes/OWC_8TB/gpr_work/pip-cache`, `/Volumes/OWC_8TB/gpr_work/pip_cache`, `/Volumes/OWC_8TB/gpr_work/xdg_cache` | External-drive caches to avoid internal-drive churn. |

Recommended environment for heavy local work:

```bash
export GPR_EXTERNAL_ROOT=/Volumes/OWC_8TB/gpr_work
export GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp
```

For ML/CNN scripts, the current local environment is:

```bash
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python
```

## Large Source Data

| path | role |
|---|---|
| `/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs` | Consolidated Barnsky DNG source data. |
| `/Volumes/OWC_8TB/gpr_work/barnsky_full_gprs` | Consolidated Barnsky GPR source data. |
| `/Volumes/OWC_8TB/gpr_work/X2D_DarkFrames` | X2D darkframe source stacks used for camera-noise calibration. |
| `/Volumes/OWC_8TB/gpr_work/x2d_scene_dngs` | X2D scene DNGs used by still/SR and compatibility audits. |
| `/Volumes/OWC_8TB/gpr_work/codec_anchored_work` | Historical codec-anchored experiment data retained for spelunking/reference. |
| `/Volumes/OWC_8TB/gpr_work/external` | External dependencies or mirrored source data staged for local runs. |
| `/Volumes/OWC_8TB/gpr_work/pi-pre-wipe-2026-05-29` | Pi-side backup material from before the wipe. Treat as archival unless a receipt explicitly references it. |

## Current Evidence Starting Points

| question | start here |
|---|---|
| What is locked, what is open, and what regresses? | `docs/PRODUCT_LOCK_LEDGER.md` |
| What percentage done are the four product pillars? | `docs/PRODUCT_PILLAR_SCORECARD.md`, `/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_ship_boundary_20260701/index.html`, and the release-blocker burn-down at `/Volumes/OWC_8TB/gpr_work/artifacts/product_burndown_ship_boundary_20260701/index.html` |
| What is the broad four-effort status? | `docs/BIG_EFFORTS_STATUS.md` |
| What exact samples/receipts are still required? | `docs/PRODUCTION_CAPTURE_REQUIREMENTS.md` and `docs/PRODUCTION_CAPTURE_REQUIREMENTS.json` |
| What release artifacts are indexed and hash-checked? | `docs/RELEASE_ARTIFACTS.md`, `docs/release_evidence_manifest.json`, and `docs/PRODUCTION_ARTIFACTS.md` |
| What proves stills compression/quality? | `docs/SHIP_DECISION.md`, `docs/CAPABILITIES.md`, and `/Volumes/OWC_8TB/gpr_work/artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html` |
| What proves the GoPro/Mission raw-video MVP proxy? | `docs/VIDEO_STATUS.md`, `docs/GOPRO_MISSION1_QUICK_VALIDATION.md`, and `/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html` |
| What proves the camera-back preview proxy? | `docs/VIDEO_STATUS.md` and the Mission 1 numbered-list burndown in `docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md` |
| What proves the approved 8K SR review path? | The standalone ProRes movies under `/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/`, `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/`, and `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/`. |
| What proves or blocks premium still-SR? | `docs/PREMIUM_STILL_SR.md`, `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_gap_20260701/index.html`, and `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_next_experiment_contract_transformer_teacher_20260701/index.html` |
| What tracks optional PSF-aware video/SR research? | `docs/BAYER_RESIZE_PSF.md`, `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_kernel_stability_audit_20260630/index.html`, and `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_capture_request_20260630/index.html` |

## Current Local Work Queue

The active production burn-down has four release-blocking open requirement IDs.
Three have work that can continue without a Mission 1 development kit; one
requires a real camera-role run. PSF-aware video/SR is intentionally not in this
queue; it is optional research unless it later beats the locked 4K/8K baseline
with the full receipt surface.

| priority | work | local status |
|---|---|---|
| 1 | Premium still-SR promotion | Local model-promotion work can continue from the raw-CFA residual target and blocker dashboards. The current blocker is X2D/domain-general raw-detail recovery strength, not missing tooling. |
| 2 | Mission 1 / iPhone noise sidecars | Local audits and sidecar builders are ready; Mission needs two more matching ISO232 RGGB darkframes, and iPhone needs confirmed no-scene provenance or recapture. |
| 3 | Mission 1 raw-video MVP closure | Blocked on real Mission 1 sensor/DMA or camera-ring-buffer, SD writer, and rear-display receipts. Pi 5 stand-in receipts remain proxy evidence only. |

## Current Whole-Video Review Artifacts

These are standalone continuous review movies, not dashboard/contact-sheet
videos.

| review | no-CNN | CNN |
|---|---|---|
| Z8 8K, 24 matched frames at 20 fps | `/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/z8_24f_true_no_cnn_4k_raw_lanczos_to_8k_20p_prores.mov` | `/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/z8_24f_with_4k_cleanup_and_8k_sr_cnn_20p_prores.mov` |
| Mission 1 broad 8K, 42 frames at 20 fps | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/mission42_true_no_cnn_4k_raw_lanczos_to_8k_42f_20p_prores.mov` | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/mission42_with_4k_cleanup_and_8k_sr_cnn_42f_20p_prores.mov` |
| Mission 1 sequential scene GP017497 through GP017508, 12 frames at 20 fps | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/GP017497_508_true_no_cnn_8k_12f_20p_prores.mov` | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/GP017497_508_with_4k_cleanup_8k_sr_cnn_12f_20p_prores.mov` |

## Cleanup Rule

Generated artifacts should either be:

1. referenced by a committed manifest, dashboard index, scorecard, or status
   doc;
2. retained under an explicit experiment/archive directory; or
3. deleted after the run if they are temporary and not needed for review.

Small docs and receipts belong in git only when they are source-of-truth
contracts. Large videos, generated dashboards, NPZ files, checkpoints, frame
dumps, and temporary build products belong under `/Volumes/OWC_8TB/gpr_work`.
