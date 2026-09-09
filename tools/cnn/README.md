# CNN tools for GPR

This directory keeps the CNN code that is still part of the current GPR
feature surface:

- 1x Bayer restoration for production stills and VIDEO_FREEZE.
- 4K Mission 1 cleanup against high-resolution-derived RGB/CFA targets.
- Offline Mission 1/Z8 4K-to-8K SR review paths.
- Premium still-SR raw-CFA residual teachers, including the current
  shifted-window attention teacher path for expensive still improvement.
- UPRESABLE half-resolution-to-editable-raw reconstruction.
- PREVIEW and release-audit utilities that are still referenced by gates.

Old raw-clean, Restormer, display-HF, and one-off PREVIEW probe scripts were
removed from `master`. Recover them from the archive branches listed in
`docs/EXPERIMENT_ARCHIVE_2026-06-04.md` if that research resumes.

## Model code

`model.py` contains the compact Bayer-in/Bayer-out CNN families used by the
registry:

- `BIBO_1x`: 1x Bayer restoration for stills and VIDEO_FREEZE.
- `BIBO_2x`: 2x Bayer reconstruction for UPRESABLE and related paths.
- Mission 1 SR variants used by the offline 8K review experiments.

Checkpoint binaries are production artifacts, not source files. Canonical
checkpoint names and sha256 hashes live in `pipelines/registry.json` and
`docs/PRODUCTION_ARTIFACTS.md`. Install them under `$GPR_MODEL_ROOT`, defaulting
to `/Volumes/OWC_8TB/gpr_work/models`, then verify with:

```bash
python3 tools/verify_production_artifacts.py --strict
```

## Current tool groups

| role | representative tools |
|---|---|
| General 1x training | `train.py`, `model.py` |
| 4K Mission 1 cleanup | `train_bayer_rgb_target_cleanup.py`, `build_4k_rgb_downsample_target_dashboard.py`, `build_mission1_4k_visual_signoff.py` |
| 8K SR training/evaluation | `train_mission1_sr.py`, `build_mission1_sr_pairs.py`, `run_mission1_sr_fullframe_broad_eval.py`, `render_gvid_sr_receipt.py` |
| Premium still-SR raw-CFA teachers | `train_premium_still_sr_raw_cfa_residual.py`, `build_premium_still_sr_raw_cfa_residual_targets.py`, `deduplicate_premium_still_sr_raw_targets.py` |
| Raw target and preview audits | `evaluate_raw_resolution_targets.py`, `render_preview_q8_threeway_runtime.py`, `evaluate_preview_q8_threeway_runtime_fullframe.py` |
| Release receipts | `decide_mission1_sr_promotion.py`, `run_mission1_sr_guarded_experiment.py`, `package_mission1_sr_receipt.py` |

Do not swap checkpoints across codec families just because dimensions match.
Every checkpoint is calibrated to a specific codec/CNN/demosaic registry entry
and must clear the relevant gate before being described as production-ready.

## Related docs

- `docs/VIDEO_STATUS.md`
- `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`
- `docs/MISSION1_SR_PRODUCTION_STATUS_2026-06-18.md`
- `docs/PRODUCTION_ARTIFACTS.md`
- `docs/EXPERIMENT_ARCHIVE_2026-06-04.md`
