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
| 3 | Premium still/SR Gate 14 intake | closed/local | Protect `premium_still_sr_gate14_candidate_intake_20260702`: selector sidecar, source-model mapping, feature schema, hashes, candidate-only runtime policy, and exact no-op fallback are persisted. | Gate 14 executable selector intake reproduces the Gate 13 pass using candidate-only runtime inputs and Z8 exact-noop. |
| 4 | Premium still/SR Gate 14 selector smoke | closed/local | Protect `premium_still_sr_gate14_selector_smoke_20260702`: the persisted sidecar runs through runtime feature recomputation, source/checkpoint hash checks, first-match routing, and intake replay comparison. | Selector smoke reproduces the X2D pass, preserves Z8 exact-noop, records model/checkpoint hashes, and uses no REF/source/JPEG/gate metric inputs. |
| 5 | Premium still/SR promotion | open/local | Run the full 50 MP / 100 MP promotion gate now that selector smoke passes. | `premium_still_sr_promotion_receipts` pass 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, editor/openability, timing/memory, checkpoint hashes, and exact-sidecar-only noise policy. |
| 6 | RAW stills noise sidecars | open/sample | Capture or prove Mission 1 and iPhone true darkframes with strict no-scene-signal provenance. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate, then camera-noise calibration sidecars pass `--require-source-provenance`. |
| 7 | Mission 1 raw-video MVP | blocked_external | GoPro/Mission 1 firmware owner runs the camera-role validation on real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Real camera-role receipts show valid `.gvid`, zero drops, 120+ sustained frames, memory, 4096 x 3072 source encode, 1024 x 768 preview, and 20+ fps floor. |

## Current Local Result

Gate 14 selector smoke passed as executable-selector runtime smoke, not as
production. The receipt is:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_selector_smoke_20260702/selector_smoke.json`

The pass means this:

- The Gate 13 upper bound is now persisted and smoke-tested as a deterministic
  seven-rule first-match selector sidecar with six source mappings and 78
  candidate-only runtime features.
- It clears both X2D scenes with zero negative selected rows through the runtime
  selector smoke: `x2d_2025_austin_06` median MAE `0.329828330762138%`, worst `0.0%`;
  `x2d_2025_austin_07` median MAE `0.02786331921791634%`, worst `0.0%`.
- Z8 remains exact no-op at `0.0%` median and `0.0%` worst-row MAE.
- Source receipts and checkpoints are readable and hash-stable; source model
  failure count is `0`.
- `promotion_gate_allowed=true`; `long_run_allowed=false`.

The next step is therefore not another broad CNN run or another selector pass.
It is the full 50 MP / 100 MP Premium still-SR promotion validation with
nonnegative worst-row recovery, timing/memory, editor/openability, exact
sidecar-only noise policy, and production submission validation.
