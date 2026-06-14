# Production Artifacts

Production checkpoints and generated media artifacts live outside the source
tree. Keep main small and reproducible: source, registry metadata, test
receipts, and docs are committed; heavyweight model binaries and dashboards are
external artifacts with hashes.

## External root

Default local root:

```bash
/Volumes/OWC_8TB/gpr_work
```

Use the helper before training, gates, or artifact-heavy smoke tests:

```bash
source tools/dev/external_drive_env.sh
```

Important paths:

| variable | default | purpose |
|---|---|---|
| `GPR_MODEL_ROOT` | `/Volumes/OWC_8TB/gpr_work/models` | production checkpoints referenced by `pipelines/registry.json` |
| `GPR_CHECKPOINT_ROOT` | `/Volumes/OWC_8TB/gpr_work/checkpoints` | training checkpoints and candidates |
| `GPR_ARTIFACT_ROOT` | `/Volumes/OWC_8TB/gpr_work/artifacts` | dashboards, videos, generated reports |
| `TMPDIR` | `/Volumes/OWC_8TB/gpr_work/tmp` | Python/tool temporary files |
| `GATE_TMPDIR` | `/Volumes/OWC_8TB/gpr_work/gate_tmp` | quality-gate scratch |

## Required Registry Artifacts

Release mode verifies every checkpoint field referenced by
`pipelines/registry.json`, not just the three core shipping model files. This
keeps experimental, diagnostic, and guardrail registry entries reproducible
while they remain registered. The current strict artifact inventory is:

| CNN id | field | registry path | sha256 |
|---|---|---|---|
| `bibo1x_ane_gpr_tools_q3` | `ckpt_path` | `models/BayInBayOut_1x_AAon_w16_ANE_gpr_tools_q3.pt` | `df22af432710bddabd223047c2db2d0edf2808dd17c4341694a974e045ec87cd` |
| `bibo1x_ane_ml2_q3` | `ckpt_path` | `models/BayInBayOut_1x_AAon_w16_ANE_ML2_q3.pt` | `7fac7c28f13830c716fede8c9caf129fc7d949151508b70530449f13151fade9` |
| `bibo2x_ane_ml2_q3_dec2_diverse` | `ckpt_path` | `models/BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt` | `bd3636d2c026639e3d8c9636de491c662fe05e67bdaa4451061901b47b37659b` |
| `bido4x_ane_ml2_q3_dec2_lpips_detail_lumagrad_w001` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/checkpoints/bido_target_detail_20260605/bido_4x_lpips005_detail_lumagrad_w001.pt` | `e538ad8d3d2f464beeb311484a84caebc1e4ec6c754bd94027b5a5933f861132` |
| `bido4x_w32_ml2_q3_dec2_hardtail_t192_lpips005_lumagrad0005` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/checkpoints/bido_full_context_20260605/bido_4x_w32_hardtail_t192_lpips005_lumagrad0005_z6693holdout.pt` | `8fa6d260a0e2bb8b03e98fa8b09496811e1d297cbb3443d621f514ec8060cc6f` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_expanded` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/codec_raw_signal_sr_w64_iso_expanded_84crops.pt` | `376f1fa52989c62076684ffa39fedbf7a469b8bf7ab3e934a9260100d5dc328c` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_expanded_runtime_sigma_probe` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_expanded_20260605/codec_raw_signal_sr_w64_iso_expanded_84crops.pt` | `376f1fa52989c62076684ffa39fedbf7a469b8bf7ab3e934a9260100d5dc328c` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_runtime_sigma_84crops` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_runtime_sigma_20260605/codec_raw_signal_sr_w64_iso_runtime_sigma_84crops.pt` | `fb6e37a1e15ed297d47878b6144bebcbf5ed0ee675bfe5a141da401e5c497aeb` |
| `codec_raw_signal_sr_ml2_q3_dec2_w64_iso_only_84crops` | `ckpt_path` | `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_train_iso_only_20260605/codec_raw_signal_sr_w64_iso_only_84crops.pt` | `7de6e691813e39ae2d9d3ce1a0ed1682a90b2d702c0cb3ac6af2d01f1e9445cf` |
| `lab_chroma_corrector_w12_sips_residual_ab8_sub10` | `ckpt_y` | `/Volumes/OWC_8TB/gpr_work/cnn/F_ane_no_sr_w16_y_multival_hf05_grad02_sub4.pt` | `e7f5add8b7a3b4ed04f87417f7026b3d5a01ccfc0ee3eb403e4f8ced3eab661e` |
| `lab_chroma_corrector_w12_sips_residual_ab8_sub10` | `ckpt_chroma` | `/Volumes/OWC_8TB/gpr_work/cnn/F_ane_chroma_corrector_w12_sips_residual_ab8_sub10.pt` | `cbb6bde6f0bdb36eb50f202f2031fec2447fea12379125211475b0e886ff4677` |

Install the portable model-root artifacts as:

```bash
$GPR_MODEL_ROOT/
  BayInBayOut_1x_AAon_w16_ANE_gpr_tools_q3.pt
  BayInBayOut_1x_AAon_w16_ANE_ML2_q3.pt
  BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt
```

The verifier also checks a repo-local `models/` directory for developer
overrides, but production setup should use `GPR_MODEL_ROOT`.

## Verify

Inventory mode, suitable for CI:

```bash
python3 tools/verify_production_artifacts.py
python3 tests/quality_gates/check_registry_consistency.py
```

Release mode:

```bash
python3 tools/verify_production_artifacts.py --strict
python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts
python3 tests/quality_gates/audit_ship_pipelines.py --strict
python3 tests/quality_gates/audit_production_readiness.py --strict
```

`audit_ship_pipelines.py` is the narrow committed-run check for registry roles
tagged `ship-*`. `audit_production_readiness.py --strict` is the broader
release checklist: stills, video quality, PREVIEW/non-REF receipts, noise/signal
guards, UPRESABLE, `.gvid`, MOV compatibility, Pi 5 / Mission 1 setup, and
platform speed receipts. `tools/test/check_release_evidence_manifest.py`
validates the compact release manifest at
`docs/release_evidence_manifest.json`.

The current offline/review PREVIEW production path is
`preview_q8_threeway_runtime_fullframe_v1`. It is a no-REF, full-frame q8
three-way runtime route with an external receipt under
`artifacts/preview_runtime_policy_20260613/q8_threeway_runtime_full_holdout_v1/`.
That receipt reports 84/84 rows passing on the 28-image holdout, weighted
runtime of 13.65 seconds per image, 0.073 fps, and 5.37 GB peak RSS. It is not
the live/camera-back path; live PREVIEW remains a separate speed/quality
problem documented in `docs/VIDEO_STATUS.md`.

## Runtime resolution

Registry checkpoint paths are portable relative paths such as
`models/name.pt`. Runtime tools resolve them in this order:

1. absolute path, if the registry entry is absolute;
2. repo-local path, for developer overrides;
3. `GPR_MODEL_ROOT` and `GPR_CHECKPOINT_ROOT`;
4. `GPR_EXTERNAL_ROOT/models` and `GPR_EXTERNAL_ROOT/checkpoints`;
5. `/Volumes/OWC_8TB/gpr_work/models` and `/Volumes/OWC_8TB/gpr_work/checkpoints`.

Missing artifacts are warnings in inventory mode and hard failures in strict
release mode.

## What stays off main

- `.pt`, `.pth`, `.mlpackage`, and intermediate training checkpoints;
- full dashboards with generated image/video payloads;
- ProRes/MOV/GVID review outputs;
- large training tiles and corpus extracts.

Commit only the registry hash, training sidecar summary, quality-gate receipt,
and compact documentation needed to reproduce the artifact.
