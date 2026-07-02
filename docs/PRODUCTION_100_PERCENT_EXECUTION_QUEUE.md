# Production 100 Percent Execution Queue

Last refreshed: 2026-07-02

This file is the short, unambiguous execution contract. Start at the first row
whose status is not `closed` or `blocked_external`. Work on a row counts only
when the named receipt exists, validates, and is linked from
`release_evidence_manifest.json`.

| order | gate | status | exact next step | receipt that moves it |
|---:|---|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Keep GitHub Actions green for the latest `master` push and run the sensitive-content, manifest, artifact-hygiene, and diff checks before each push. | Latest `master` CI run passes. |
| 2 | RAW video reconstruction | closed/protect | Do not reopen approved 4K cleanup or 8K SR unless a locked receipt fails or a replacement already beats the locked artifact surface. | Product lock ledger, README pillar guard, and release manifest guard pass. |
| 3 | Premium still/SR Gate 14 | open/local | Build `premium_still_sr_gate14_candidate_intake_<date>` from the Gate 13 multi-source selector result. Persist the selector sidecar, source-model mapping, feature schema, hashes, and exact no-op fallback. | Gate 14 executable selector intake reproduces the Gate 13 pass using candidate-only runtime inputs and Z8 exact-noop. |
| 4 | Premium still/SR promotion | open/local after Gate 14 | Run the executable selector smoke and then the full 50 MP / 100 MP promotion gate. | `premium_still_sr_promotion_receipts` pass 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, editor/openability, timing/memory, checkpoint hashes, and exact-sidecar-only noise policy. |
| 5 | RAW stills noise sidecars | open/sample | Capture or prove Mission 1 and iPhone true darkframes with strict no-scene-signal provenance. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate, then camera-noise calibration sidecars pass `--require-source-provenance`. |
| 6 | Mission 1 raw-video MVP | blocked_external | GoPro/Mission 1 firmware owner runs the camera-role validation on real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Real camera-role receipts show valid `.gvid`, zero drops, 120+ sustained frames, memory, 4096 x 3072 source encode, 1024 x 768 preview, and 20+ fps floor. |

## Current Local Result

Gate 13 source/objective revision passed as a source-selection preflight, not as
production. The receipt is:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate13_source_or_objective_revision_20260702/source_or_objective_revision.json`

The pass means this:

- A single X2D source was not separable per scene, but a multi-source
  candidate-only selector has enough measured upper-bound capacity.
- The selector upper bound uses 12 compatible X2D source receipts, 78 runtime
  features, and 10,199 safe source/predicate selectors.
- It clears both X2D scenes with zero negative selected rows:
  `x2d_2025_austin_06` median MAE `8.022846730221168%`, worst `0.0%`;
  `x2d_2025_austin_07` median MAE `0.07380457072746566%`, worst `0.0%`.
- Z8 remains exact no-op at `0.0%` median and `0.0%` worst-row MAE.

The next step is therefore not another broad CNN run. It is Gate 14: turn the
multi-source selector upper bound into an executable sidecar and prove the
actual selector reproduces the receipt without REF, source RAW/RGB/HF, JPEG, or
gate metrics at render time.
