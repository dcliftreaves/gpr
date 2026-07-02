# Production 100 Percent Execution Queue

Last refreshed: 2026-07-02

This file is the short, unambiguous execution contract. Start at the first row
whose status is not `closed` or `blocked_external`. Work on a row counts only
when the named receipt exists, validates, and is linked from
`release_evidence_manifest.json` or `PRODUCTION_ARTIFACTS.md`.

## 100 Percent Definition

The project is 100 percent production-ready only when every row below is closed
by the named evidence. No dashboard, model checkpoint, local timing run, or
visual review can substitute for the receipt named in the `receipt that moves
it` column.

| order | goal | 100 percent condition | current next move |
|---:|---|---|---|
| 1 | CI and repo hygiene | Latest `master` commit has passing GitHub Actions, sensitive-content guard, artifact-hygiene guard, release-manifest guard, README guards, and clean diff checks. | Protect on every push. |
| 2 | Best RAW stills | 50 MP and 100 MP still tiers remain green, normal RGGB/GBRG/GRBG/BGGR Bayer support remains green, and Mission 1 plus iPhone camera-noise sidecars validate from strict true-dark provenance. | Capture/prove Mission 1 and iPhone true darkframes, then build strict sidecars. |
| 3 | GoPro RAW video MVP | Real Mission 1 camera-role source/storage/display receipts prove 4096 x 3072 Bayer `.gvid` encode, 1024 x 768 preview decode, valid container, zero drops, memory, and 120+ sustained frames at the accepted 20+ fps floor. | Hand GoPro/Mission 1 firmware owners the camera-role runbook; local Pi stand-ins cannot close this gate. |
| 4 | Premium still/SR | A no-REF 50 MP / 100 MP premium still candidate passes the full promotion gate: 15% / 15% held-out MAE/RMSE floor, nonnegative worst row, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. | Revise the Gate14 floor-student target/objective before any long run. |
| 5 | RAW video reconstruction | Approved 4K cleanup and 8K SR release receipts stay locked and green; replacement research ships only if it beats the locked artifact surface. | Protect only. PSF/blur is optional research, not a release blocker. |

The local priority order is fixed: **CI first, Premium still/SR target/objective
revision second, Mission/iPhone darkframe provenance third, GoPro camera-role
handoff fourth, locked raw-video reconstruction protection fifth.**

| order | gate | status | exact next step | receipt that moves it |
|---:|---|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Keep GitHub Actions green for the latest `master` push and run the sensitive-content, manifest, artifact-hygiene, and diff checks before each push. | Latest `master` CI run passes. |
| 2 | RAW video reconstruction | closed/protect | Do not reopen approved 4K cleanup or 8K SR unless a locked receipt fails or a replacement already beats the locked artifact surface. | Product lock ledger, README pillar guard, and release manifest guard pass. |
| 3 | Premium still/SR Gate 14 intake | closed/local | Protect `premium_still_sr_gate14_candidate_intake_20260702`: selector sidecar, source-model mapping, feature schema, hashes, candidate-only runtime policy, and exact no-op fallback are persisted. | Gate 14 executable selector intake reproduces the Gate 13 pass using candidate-only runtime inputs and Z8 exact-noop. |
| 4 | Premium still/SR Gate 14 selector smoke | closed/local | Protect `premium_still_sr_gate14_selector_smoke_20260702`: the persisted sidecar runs through runtime feature recomputation, source/checkpoint hash checks, first-match routing, and intake replay comparison. | Selector smoke reproduces the X2D pass, preserves Z8 exact-noop, records model/checkpoint hashes, and uses no REF/source/JPEG/gate metric inputs. |
| 5 | Premium still/SR Gate14 floor-student launch packet | closed/local | Protect `premium_still_sr_gate14_floor_student_preflight_20260702` and `premium_still_sr_gate14_floor_student_launch_packet_20260702`: the next candidate named by the model-floor gap has a launchable preflight, paired X2D/Z8 smoke commands, exact no-op fallback, and no REF/source/JPEG render-time inputs. | `preflight_audit.json` says `launchable_preflight_passed` for `premium_still_sr_gate14_floor_student_v1`, with `1.0%` median MAE smoke floor and `0.0%` worst-row floor. |
| 6 | Premium still/SR promotion | open/local | Revise the Gate14 floor-student target/objective after the paired smokes blocked the long run: the X2D/Z8 target dataset now exists, but the current high-pass residual U-Net clears neither the 1% median smoke floor nor the no-op-off ablation. | `premium_still_sr_promotion_receipts` pass 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. |
| 7 | RAW stills noise sidecars | open/sample | Capture or prove Mission 1 and iPhone true darkframes with strict no-scene-signal provenance. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate, then camera-noise calibration sidecars pass `--require-source-provenance`. |
| 8 | Mission 1 raw-video MVP | blocked_external | GoPro/Mission 1 firmware owner runs the camera-role validation on real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Real camera-role receipts show valid `.gvid`, zero drops, 120+ sustained frames, memory, 4096 x 3072 source encode, 1024 x 768 preview, and 20+ fps floor. |

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

The current strict promotion receipt is:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_20260702/premium_still_sr_promotion_receipts.json`

It records `completion_percent=50.0`, `done_step_count=4`, and
`first_open_step=model_promotion_floor`. The blocker classes are
`model_promotion_floor_not_met`, `full_50mp_100mp_gate_missing`,
`timing_memory_missing`, `noise_policy_not_wired`, and
`production_submission_missing_or_failed`.

The current model-floor receipt is:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_model_floor_gap_20260702/model_floor_gap.json`

It records the exact first blocker: best runtime-safe MAE/RMSE are
`4.031355420019811%` / `3.753504206299621%` versus the `15% / 15%` floor, and
Gate 14 selector global median MAE is `0.2506229397841941%`. The next candidate
contract is `premium_still_sr_gate14_floor_student_v1`, not another Gate 14
replay or rejected single-source branch.

That candidate now has a launchable intake packet:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_launch_packet_20260702/launch_packet.json`

The preflight verdict is `launchable_preflight_passed`, with two required smoke
commands: X2D and Z8. The launch packet requests
`premium_still_sr_gate14_floor_student_targets_20260702/gate14_floor_student_targets.npz`
before those smokes. Do not run another Gate 14 selector replay as a substitute
for the student target builder.

The target-builder has now run and passed:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_targets_20260702/gate14_floor_student_targets.json`

It built `2112` X2D/Z8 target rows from the Gate14 clean-source pair surface:
`576` X2D rows and `1536` Z8 rows.

The paired smoke commands also ran:

- X2D smoke receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_x2d_smoke_20260702/train_receipt.json`
  with holdout median MAE recovery `0.0%` and worst-row recovery
  `-0.0009948811042696764%`.
- Z8 smoke receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_z8_smoke_20260702/train_receipt.json`
  with holdout median MAE recovery `0.0%` and worst-row recovery `0.0%`.
- Smoke acceptance:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json`
  verdict `blocked_before_long_run`.

No-op-off ablations did not fix the blocker: X2D median was
`-0.0008484692747994224%`; Z8 median was `0.00019770163681548142%`.
The next action is therefore a target/objective revision, not a longer run:
try a stronger source-HF or direct clean-source 2x objective and wire strict
noise sidecars before reattempting paired smokes.
