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

## Required models

The registry currently ships these checkpoint artifacts:

| CNN id | filename | sha256 |
|---|---|---|
| `bibo1x_ane_gpr_tools_q3` | `BayInBayOut_1x_AAon_w16_ANE_gpr_tools_q3.pt` | `df22af432710bddabd223047c2db2d0edf2808dd17c4341694a974e045ec87cd` |
| `bibo1x_ane_ml2_q3` | `BayInBayOut_1x_AAon_w16_ANE_ML2_q3.pt` | `7fac7c28f13830c716fede8c9caf129fc7d949151508b70530449f13151fade9` |
| `bibo2x_ane_ml2_q3_dec2_diverse` | `BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt` | `bd3636d2c026639e3d8c9636de491c662fe05e67bdaa4451061901b47b37659b` |

Install them as:

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
platform speed receipts. It expects external receipts under `GPR_ARTIFACT_ROOT`,
including the direct-RGB non-REF PREVIEW diagnostic dashboard, checkpoint hash,
and the deterministic runtime PREVIEW policy receipt. As of 2026-06-06, the
temporary scene-routed PREVIEW candidate clears the full-image 28-image holdout
target at 61/84 rows, with frozen router sidecar, expert checkpoint hashes,
timing/memory receipts, and `.gvid`/ProRes evidence. It is not a ship claim
because worst-row failures remain severe; see
`docs/PREVIEW_SCENE_ROUTED_PRODUCTION_PASS_2026-06-06.md`.

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
