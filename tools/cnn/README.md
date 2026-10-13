# CNN runtime tools

This directory supports registered still restoration, offline 4K cleanup,
offline 8K SR, editable raw packaging, and PREVIEW review rendering. Live
raw4K capture and full-frame 1024 preview on Pi are native paths outside this
directory. Registry scope and ship status remain authoritative; retaining a
candidate does not promote it.

## Entry points and dependencies

- `render_gvid_sr_receipt.py`: .gvid to 8K Bayer; uses
  `mission1_sr_runtime.py` and model definitions in `mission1_sr_models.py`.
  `bench_mission1_sr_8k.py` uses the same runtime for timing receipts; it is
  not a production inference dependency or a quality gate.
- `train_bayer_rgb_target_cleanup.py apply`: registered, visually signed-off
  4K Bayer cleanup; registry scope remains offline review-only.
- `upresable_pipeline.py`, `preview_timelapse_fast.py`, and
  `preview_timelapse_fast_sota.py`: editable raw/timelapse rendering.
- `render_preview_q8_threeway_runtime.py`: registered offline PREVIEW;
  depends on `evaluate_preview_q8_threeway_runtime_fullframe.py`,
  `evaluate_preview_q8_crop_fullframe.py`,
  `evaluate_preview_scene_routed_fullframe.py`,
  `evaluate_preview_scene_routed.py`, `evaluate_preview_runtime_policy.py`,
  and `build_preview_holdout_runtime_receipt.py`.
- PREVIEW support libraries: `preview_scene_features.py`,
  `score_preview_q8_hard_router_union.py`,
  `score_preview_q8_threeway_router_union.py`,
  `preview_rgb_models.py`, and
  `preview_input_features.py`: inference, feature/routing,
  and model helpers.
- Sidecar encoding/decoding: `pack_bayer_detail_residual_sidecar.py` and
  `bayer_detail_residual.py`.
- Offline packaging: `package_mission1_sr_receipt.py` and
  `package_mission1_sr_sequence_receipt.py`.
- Model support: `model.py` and the model definitions used by the entry
  points above.
- Shared visual metrics: `tools/cnn/metrics.py`.

The runtime-only model/feature libraries use runtime names; their former
`train_*`/audit module paths are not compatibility APIs. Architecture classes,
checkpoint config dispatch, state-dict keys, and PREVIEW quality thresholds
are unchanged. Retained architecture branches support existing checkpoint
configs; their presence does not approve additional models. The registered
`train_bayer_rgb_target_cleanup.py apply` CLI retains its registry path.

The approved offline-production 8K model is
`mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1`. Model names, codec
pairings, and review-only scope are documented in
[Reconstruction](../../docs/RECONSTRUCTION.md#approval-boundary).

Outside this directory, retain `tools/gvid_metadata.py`,
`tools/gvid_pack.py`, and the PREVIEW manifest
`pipelines/preview_holdout_set.json`. Native decoder/encoder tools, `gpr_tools`, `gpr2prores`, and
`gpr_mov_tool` provide capture, raw packaging, and ProRes integration.
The ProRes Makefile has no Python training dependency; its weight exporters
use `model.py`. Python dependencies are listed in `requirements.txt`;
rendering also uses macOS `sips`, FFmpeg, and DNG metadata extraction uses
ExifTool.

## Portable artifacts

`runtime_paths.py` resolves default data/output paths under
`GPR_EXTERNAL_ROOT`, falling back to the repository root. Relative external
roots are repository-relative. Existing CLI paths and model-specific
environment overrides remain available. Registry artifact paths are relative
to the repository or configured external root; checkpoint hashes, pipeline
identities, and gate baselines are preserved.

Set `GPR_EXTERNAL_ROOT` before invoking renderers to relocate default source,
checkpoint, and receipt trees. UPRESABLE also supports `GPR_MODEL_ROOT`,
and `GPR_BIBO2X_CKPT`.
Sequence packaging requires an explicit `--meta-dng`.

## Historical evidence

[Pinned runtime and research history](https://github.com/dcliftreaves/gpr/tree/f13dbe95d3e97c400e8d493ba178dbb037ff3c96/tools/cnn)
is separate from production dependencies. Historical gate identities remain
lookup-compatible; retaining an identity does not promote its model.
