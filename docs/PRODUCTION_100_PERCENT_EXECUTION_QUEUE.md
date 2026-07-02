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

## Unambiguous Execution Steps

Work from this list in order. Do not skip to a later item unless the earlier
item is `closed` or `blocked_external`.

1. Keep CI green on every pushed `master` commit.
2. Keep approved raw-video reconstruction locked; do not reopen 4K cleanup or
   8K SR unless a locked receipt fails or a replacement already beats the
   locked proof surface.
3. For Premium still/SR, stop threshold tuning. The objective-gate audit proves
   the current failed objectives do not contain enough positive candidate-only
   rows for a runtime gate to rescue them.
4. Build the next Premium still/SR target-construction preflight. It must prove,
   before training, that X2D has enough candidate-only positive rows to clear
   the 1% smoke median floor and that Z8 can remain exact no-op unless it has
   positive source evidence.
5. Only after that preflight passes, run paired X2D/Z8 smokes. A long run is
   allowed only if the paired smoke clears the 1% median MAE floor and 0.0%
   worst-row floor.
6. Only after paired smoke passes, run the full 50 MP / 100 MP Premium still-SR
   promotion receipt: 15% / 15% held-out MAE/RMSE, nonnegative worst row,
   editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only
   noise policy, and production submission validation.
7. Close raw-stills noise by proving Mission 1 and iPhone true-dark provenance,
   then building strict camera-noise sidecars.
8. Close GoPro raw-video MVP only with a real Mission 1 camera-role run:
   sensor/DMA or camera ring-buffer source, SD writer, rear display, valid
   `.gvid`, zero drops, memory, 120+ sustained frames, 4096 x 3072 encode,
   1024 x 768 preview, and the accepted 20+ fps floor.

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
| 6 | Premium still/SR promotion | open/local | Revise Gate14 target construction before any long run. The objective-gate audit proves the current high-pass residual U-Net, direct clean-source 2x objective, and source-HF/stored-HF objective cannot be rescued by candidate-only threshold gating: direct-clean has 0 positive-floor rows where 33 are needed on both X2D/Z8, source-HF has 2/17 on X2D and 0/17 on Z8. The next preflight must create enough candidate-only positive rows for X2D while keeping Z8 exact no-op unless positive source evidence exists. | `premium_still_sr_promotion_receipts` pass 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. |
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

The first direct clean-source 2x objective revision has now been tested and is
also blocked before long training:

- X2D direct-clean 2x smoke:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_direct_clean2x_x2d_smoke_20260702/train_receipt.json`
  with holdout median/worst MAE recovery `0.0014214634577010441%` /
  `-0.003295453099076983%`, checkpoint
  `45f7020d08ccf57a77fb741b09221d1d03ac32590dd82945990bdfdda0f98d49`.
- Z8 direct-clean 2x smoke:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_direct_clean2x_z8_smoke_20260702/train_receipt.json`
  with holdout median/worst MAE recovery `-0.002131528550201698%` /
  `-0.01173024558700332%`, checkpoint
  `d42c5b332f1d73a545cb729c8f151b48dc3fc07835db19735b9a416756baf37a`.

That rules out the simple direct clean-source 2x replacement as the production
objective. The next local Gate A action is a stronger target/objective revision:
combine source-HF or direct-clean supervision with exact-sidecar-only noise
gating and candidate-only no-op behavior, then re-run the paired X2D/Z8 smoke.

The first source-HF/stored-HF revision has also been tested and is blocked
before long training:

- X2D source-HF/stored-HF smoke:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_sourcehf_storedhf_x2d_smoke_20260702/train_receipt.json`
  with holdout median/worst raw MAE recovery `0.0%` /
  `-72.74350477685562%`, checkpoint
  `ba2d2ec480e753764f136d53a075f86eaae796435ed6867651d15dd14190dc65`.
- Z8 source-HF/stored-HF smoke:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_sourcehf_storedhf_z8_smoke_20260702/train_receipt.json`
  with holdout median/worst raw MAE recovery `0.0%` / `0.0%`, checkpoint
  `e340f5fac100446dd26763e13336eb01a18bbb7fa72622706ef2608e55890f74`.

That rules out this source-HF configuration: the candidate-HF no-op gate
protects Z8 but collapses the median to no-op and leaves an unacceptable X2D
tail. The next objective revision must change gate construction and target
selection, not just rerun source-HF with the same no-op threshold.

The Gate14 objective-gate audit then checked whether threshold gating could
rescue either the direct-clean 2x or source-HF/stored-HF failures:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_objective_gate_audit_20260702/objective_gate_audit.json`

It records `verdict=blocked_before_gate_construction`,
`blocker_classification=insufficient_positive_signal`,
`gate_rescue_possible=false`, and `oracle_positive_signal_possible=false`.
The audit is stronger than a threshold-search miss: even an oracle positive/no-op
upper bound cannot clear the 1% median smoke floor on the current outputs. The
next local step is therefore a target-construction preflight that proves enough
positive candidate-only rows exist before any paired smoke or long training.
