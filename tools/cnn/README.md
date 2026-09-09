# CNN runtime tools

This directory supports registered still restoration, offline 4K cleanup,
offline 8K SR, editable raw packaging, and PREVIEW review rendering. Live
raw4K capture and full-frame 1024 preview on Pi are native paths outside this
directory. Registry scope and ship status remain authoritative; retaining a
candidate does not promote it.

## Entry points and dependencies

- `render_gvid_sr_receipt.py`: .gvid to 8K Bayer; uses
  `bench_mission1_sr_8k.py` and model definitions in `train_mission1_sr.py`.
- `train_bayer_rgb_target_cleanup.py apply`: registered 4K Bayer cleanup.
  The historical filename is retained for registry compatibility; training
  commands have been removed.
- `upresable_pipeline.py`, `preview_timelapse_fast.py`, and
  `preview_timelapse_fast_sota.py`: editable raw/timelapse rendering.
- `render_preview_q8_threeway_runtime.py`: registered offline PREVIEW;
  depends on `evaluate_preview_q8_threeway_runtime_fullframe.py`,
  `evaluate_preview_q8_crop_fullframe.py`,
  `evaluate_preview_scene_routed_fullframe.py`,
  `evaluate_preview_scene_routed.py`, `evaluate_preview_runtime_policy.py`,
  and `build_preview_holdout_runtime_receipt.py`.
- PREVIEW support libraries: `build_preview_scene_router_audit.py`,
  `score_preview_q8_hard_router_union.py`,
  `score_preview_q8_threeway_router_union.py`,
  `train_display_rgb_direct_nonref.py`, and
  `train_preview_fullimage_band_refiner.py`. These retain inference,
  feature/routing, and model helpers; their experiment CLIs are archived.
- Sidecar encoding/decoding: `pack_bayer_detail_residual_sidecar.py`,
  `bayer_detail_residual.py`, and
  `bench_bayer_detail_residual_sidecar_native.py`.
- Offline receipts: `package_mission1_sr_receipt.py`,
  `package_mission1_sr_sequence_receipt.py`,
  `compare_mission1_sr_fullframe.py`, and `decide_mission1_sr_promotion.py`.
- Gate/model support: `model.py`, `analyze_dng_noise_profile.py`,
  `train_codec_raw_clean_sr.py`, `run_lab_chroma_corrector.py`, and
  `bench_raw_resolution_targets.py`. Historical analysis/training filenames
  retain only helpers required by registered gates and raw-resolution tests.

Outside this directory, retain `tools/gvid_metadata.py`,
`tools/gvid_pack.py`, `tools/test/metrics.py`, and the PREVIEW holdout
manifest. Native decoder/encoder tools, `gpr_tools`, `gpr2prores`, and
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

## Archive

Research trainers, oracle/reference-transfer commands, dashboards, probes,
target builders, and iteration runners are archived at
`archive/research-and-integration-2026-09-09`
(`3d675ef95d2e1470af0a60abb81994eb09bb5aa6`).
Inspect any original file without restoring it:

```sh
git show archive/research-and-integration-2026-09-09:tools/cnn/train_mission1_sr.py
```
