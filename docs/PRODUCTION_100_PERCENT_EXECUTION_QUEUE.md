# Production 100 Percent Execution Queue

Last refreshed: 2026-07-03

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
4. Build the next Premium still/SR target-construction proposal and pass the
   Gate15 target-construction preflight. It must prove, before training, that
   X2D has enough candidate-only positive rows to clear the 1% smoke median
   floor and that Z8 can remain exact no-op unless it has positive source
   evidence.
5. Gate15 target construction and paired smoke are closed as a failed branch:
   X2D did not clear the 1% median MAE floor or 0.0% worst-row floor, while Z8
   exact-noop passed.
6. Gate16 learnability/objective revision is closed as a paired-smoke pass,
   then rejected as a production candidate by the all-target-row audit. X2D
   paired-smoke median/worst raw MAE recovery is 17.086680690440865% / 0.0%,
   but the 463-row audit records -0.12226915231999792% median MAE recovery,
   -0.1296250122706981% median RMSE recovery, and -9.625700832601128% worst
   MAE recovery on X2D/100 MP target rows. It also has no 50 MP rows and no
   full-frame evidence.
7. Gate17 replacement target construction is closed as a balanced target
   package: 576 50 MP rows and 576 100 MP rows, selected from the Gate14
   clean-source target surface, with no REF/source/JPEG render-time inputs.
8. Gate17 training/audit is closed as a rejected model branch. It used the
   balanced 576-row-per-class package but missed the floor on 1,152 rows:
   overall median MAE recovery `-0.23468499188533842%`, overall median RMSE
   recovery `0.34200684333480724%`, 100 MP worst MAE
   `-35.30304893327897%`, and 50 MP worst MAE `-2.259351982942634%`.
9. Gate18 candidate/objective revision is closed as a receipt: it names
   `premium_still_sr_gate18_tail_safe_context_objective_v1`, preserves the
   balanced Gate17 target surface, rejects unchanged Gate17 reruns, and emits
   exact train/audit commands.
10. Gate18 training/audit is closed as a rejected safety branch. It improves
   worst rows but collapses toward no-op: overall median MAE/RMSE `0.0%` /
   `0.0%`, 100 MP worst MAE `-0.0912221669777865%`, and 50 MP worst MAE
   `-0.0068758277986793615%`.
11. Gate19 positive-signal/source revision is closed as a rejected branch. The
   source-HF objective missed broad target-row quality with overall median
   MAE/RMSE `-14.17838003215098%` / `-13.181758464778333%`, 100 MP median
   MAE `-13.116189248074146%`, 50 MP median MAE
   `-15.64244661023621%`, and severe negative tails.
12. Gate17 scalar-direction calibration is closed as a rejection. Its best
   scalar is `0.025`, with only `0.017883242885033075%` overall median MAE
   recovery and a negative worst row, so scalar tuning cannot close the model
   floor.
13. Candidate-HF feature scaling is closed as a rejection. Its best scalar is
   `-0.025`, with `-0.004920370968732175%` overall median MAE recovery and a
   negative worst row, so stored candidate-HF is not a predictive replacement
   target.
14. Gate20 supervision/objective revision is closed as a local receipt. It
   names `premium_still_sr_gate20_rebuilt_supervision_v1` and requires rebuilt
   supervision targets before any new long train.
15. The first Gate20 rebuilt-supervision target generation is closed as a
   coverage blocker. The actual build created 351 rows: 108 50 MP rows and
   243 100 MP rows.
16. Gate20 X2D/100 MP source expansion is closed as an authorization receipt.
   The expanded manifest adds 29 audited X2D scene DNGs, the strict target
   rebuild created 1,593 rows, and coverage is now 594 50 MP rows plus 999
   100 MP rows. `gate20_training_authorized=true`.
17. Run Gate20 no-REF preflight, training, and
   broad target-row audit before any full 50 MP / 100 MP promotion receipt:
   15% / 15% held-out MAE/RMSE, nonnegative worst row, editor/openability,
   timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and
   production submission validation.
18. Close raw-stills noise by proving Mission 1 and iPhone true-dark provenance,
   then building strict camera-noise sidecars.
19. Close GoPro raw-video MVP only with a real Mission 1 camera-role run:
   sensor/DMA or camera ring-buffer source, SD writer, rear display, valid
   `.gvid`, zero drops, memory, 120+ sustained frames, 4096 x 3072 encode,
   1024 x 768 preview, and the accepted 20+ fps floor.

| order | goal | 100 percent condition | current next move |
|---:|---|---|---|
| 1 | CI and repo hygiene | Latest `master` commit has passing GitHub Actions, sensitive-content guard, artifact-hygiene guard, release-manifest guard, README guards, and clean diff checks. | Protect on every push. |
| 2 | Best RAW stills | 50 MP and 100 MP still tiers remain green, normal RGGB/GBRG/GRBG/BGGR Bayer support remains green, and Mission 1 plus iPhone camera-noise sidecars validate from strict true-dark provenance. | Capture/prove Mission 1 and iPhone true darkframes, then build strict sidecars. |
| 3 | GoPro RAW video MVP | Real Mission 1 camera-role source/storage/display receipts prove 4096 x 3072 Bayer `.gvid` encode, 1024 x 768 preview decode, valid container, zero drops, memory, and 120+ sustained frames at the accepted 20+ fps floor. | Hand GoPro/Mission 1 firmware owners the camera-role runbook; local Pi stand-ins cannot close this gate. |
| 4 | Premium still/SR | A no-REF 50 MP / 100 MP premium still candidate passes the full promotion gate: 15% / 15% held-out MAE/RMSE floor, nonnegative worst row, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. | Run the Gate20 rebuilt-supervision target commands, then require broad 50 MP / 100 MP target-row pass before full promotion. |
| 5 | RAW video reconstruction | Approved 4K cleanup and 8K SR release receipts stay locked and green; replacement research ships only if it beats the locked artifact surface. | Protect only. PSF/blur is optional research, not a release blocker. |

The local priority order is fixed: **CI first, Gate20 Premium still/SR
rebuilt-supervision targets second, Mission/iPhone darkframe provenance third,
GoPro camera-role handoff fourth, locked raw-video reconstruction protection
fifth.**

| order | gate | status | exact next step | receipt that moves it |
|---:|---|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Keep GitHub Actions green for the latest `master` push and run the sensitive-content, manifest, artifact-hygiene, and diff checks before each push. | Latest `master` CI run passes. |
| 2 | RAW video reconstruction | closed/protect | Do not reopen approved 4K cleanup or 8K SR unless a locked receipt fails or a replacement already beats the locked artifact surface. | Product lock ledger, README pillar guard, and release manifest guard pass. |
| 3 | Premium still/SR Gate 14 intake | closed/local | Protect `premium_still_sr_gate14_candidate_intake_20260702`: selector sidecar, source-model mapping, feature schema, hashes, candidate-only runtime policy, and exact no-op fallback are persisted. | Gate 14 executable selector intake reproduces the Gate 13 pass using candidate-only runtime inputs and Z8 exact-noop. |
| 4 | Premium still/SR Gate 14 selector smoke | closed/local | Protect `premium_still_sr_gate14_selector_smoke_20260702`: the persisted sidecar runs through runtime feature recomputation, source/checkpoint hash checks, first-match routing, and intake replay comparison. | Selector smoke reproduces the X2D pass, preserves Z8 exact-noop, records model/checkpoint hashes, and uses no REF/source/JPEG/gate metric inputs. |
| 5 | Premium still/SR Gate14 floor-student launch packet | closed/local | Protect `premium_still_sr_gate14_floor_student_preflight_20260702` and `premium_still_sr_gate14_floor_student_launch_packet_20260702`: the next candidate named by the model-floor gap has a launchable preflight, paired X2D/Z8 smoke commands, exact no-op fallback, and no REF/source/JPEG render-time inputs. | `preflight_audit.json` says `launchable_preflight_passed` for `premium_still_sr_gate14_floor_student_v1`, with `1.0%` median MAE smoke floor and `0.0%` worst-row floor. |
| 6 | Premium still/SR Gate17 target package | closed/local | Protect `premium_still_sr_gate17_replacement_targets_20260702`: the package selects 576 50 MP rows and 576 100 MP rows from the Gate14 clean-source target surface, rejects exact-noop camera-class coverage as a production substitute, and emits the next training/audit commands. | `gate17_replacement_targets.json` records `paired_smoke_ready=true`, `selected_class_counts={'50mp': 576, '100mp': 576}`, candidate-only runtime policy, and no production claim. |
| 7 | Premium still/SR Gate17 training/audit | closed/rejected | Protect `premium_still_sr_gate17_balanced_smoke_train_20260702` and `premium_still_sr_gate17_balanced_target_row_audit_20260702` as rejection evidence. Do not rerun the same training command as the production path. | Audit records 1,152 balanced rows, target-row/tile scope, `production_ready=false`, median MAE/RMSE below floor, and negative worst rows on both classes. |
| 8 | Premium still/SR Gate18 candidate/objective revision | closed/local | Protect `premium_still_sr_gate18_candidate_objective_revision_20260703`: it names the changed objective and exact next commands. | `gate18_candidate_objective_revision.json` records no-REF candidate-only runtime policy, Gate17 rejection metrics, and `premium_still_sr_gate18_tail_safe_context_objective_v1`. |
| 9 | Premium still/SR Gate18 training/audit | closed/rejected | Protect `premium_still_sr_gate18_tail_safe_context_train_20260703` and `premium_still_sr_gate18_tail_safe_context_target_row_audit_20260703` as rejection evidence. | Audit records broad 50 MP / 100 MP coverage, improved tail safety, `production_ready=false`, and no positive median recovery. |
| 10 | Premium still/SR Gate19 positive-signal/source revision | closed/rejected | Protect `premium_still_sr_gate19_source_hf_positive_signal_train_20260703` and its broad audit as rejection evidence. | Audit records broad 50 MP / 100 MP coverage, `production_ready=false`, negative median MAE/RMSE, and severe negative tails. |
| 11 | Premium still/SR direction calibration | closed/rejected | Protect `premium_still_sr_gate17_direction_calibration_audit_20260703` as evidence that scalar tuning does not close the model floor. | Best scalar is `0.025`, with `0.017883242885033075%` median MAE recovery and a negative worst row. |
| 12 | Premium still/SR candidate-HF feature audit | closed/rejected | Protect `premium_still_sr_candidate_hf_feature_audit_20260703` as evidence that stored candidate-HF scalar transforms are not predictive. | Best alpha is `-0.025`, median MAE recovery is `-0.004920370968732175%`, and `next_decision=candidate_hf_feature_not_predictive_change_supervision`. |
| 13 | Premium still/SR Gate20 supervision/objective revision | closed/local | Protect `premium_still_sr_gate20_supervision_objective_revision_20260703`: it rejects Gate17/Gate18/Gate19/scalar/candidate-HF reruns and names the rebuilt-supervision target commands. | `gate20_supervision_objective_revision.json` records candidate-only runtime policy, exact prior rejection hashes, `first_open_step=gate20_rebuild_supervision_targets`, and `premium_still_sr_gate20_rebuilt_supervision_v1`. |
| 14 | Premium still/SR Gate20 first rebuilt supervision targets | closed/blocked | Protect `premium_still_sr_gate20_rebuilt_supervision_targets_20260703`, strict plan, and `premium_still_sr_gate20_target_coverage_audit_20260703` as target-construction evidence. | Actual rebuilt targets have 351 rows: 108 50 MP and 243 100 MP. Strict planner reaches 594 50 MP rows but only 243 100 MP rows; `gate20_training_authorized=false`. |
| 15 | Premium still/SR Gate20 expanded X2D target package | closed/local | Protect `premium_still_sr_x2d_manifest_expansion_gate20_20260703`, `premium_still_sr_gate20_strict_expanded_x2d_plan_20260703`, `premium_still_sr_gate20_expanded_x2d_targets_20260703`, and `premium_still_sr_gate20_target_coverage_audit_expanded_x2d_20260703`. | Expanded rebuilt targets have 1,593 rows: 594 50 MP and 999 100 MP. Both row floors and the total floor pass; `gate20_training_authorized=true`. |
| 16 | Premium still/SR Gate20 train/audit | open/local | Run no-REF/candidate-only preflight, Gate20 training, broad target-row audit, and the full 50 MP / 100 MP promotion receipt. | Median MAE/RMSE recovery clears 15% / 15%, worst-row MAE is nonnegative, timing/memory/checkpoint hashes are recorded, editor/openability passes, exact-sidecar-only noise policy passes, and production submission validates. |
| 17 | RAW stills noise sidecars | open/sample | Capture or prove Mission 1 and iPhone true darkframes with strict no-scene-signal provenance. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate, then camera-noise calibration sidecars pass `--require-source-provenance`. |
| 18 | Mission 1 raw-video MVP | blocked_external | GoPro/Mission 1 firmware owner runs the camera-role validation on real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Real camera-role receipts show valid `.gvid`, zero drops, 120+ sustained frames, memory, 4096 x 3072 source encode, 1024 x 768 preview, and 20+ fps floor. |

## Current Local Result

The current local state is Gate16 paired-smoke pass, Gate16 all-target-row
rejection, Gate17 balanced target-package construction, Gate17 training/audit
rejection, Gate18 candidate/objective revision, Gate18 training/audit
rejection, Gate19 source-HF rejection, Gate17 scalar-calibration rejection,
candidate-HF feature rejection, Gate20 supervision/objective revision, and
Gate20 expanded X2D target coverage authorization.
Do not spend
another day on ambiguous "improve CNN" work; burn down these rows in order:

1. Run Gate20 train and
   `tools/build_premium_still_sr_gate16_target_row_audit.py`
   or its
   successor on the replacement. It must record both `50mp` and `100mp`
   row counts, median MAE/RMSE recovery `>= 15.0`, and worst-row MAE recovery
   `>= 0.0` before a full promotion run is allowed.
2. Build the full 50 MP / 100 MP still-SR gate receipt with `--real-artifacts`
   for review media, editable DNG/GPR evidence, dashboard, checkpoint hash,
   actual render timings, and peak RSS.
3. The full gate must record both `full_frame_gate_50mp_row_count > 0` and
   `full_frame_gate_100mp_row_count > 0`.
5. The full gate must record both `median_mae_reduction_pct_50mp >= 15.0` and
   `median_mae_reduction_pct_100mp >= 15.0`.
6. The full gate must record both worst-row MAE reductions as `>= 0.0` and
   `severe_worst_row_failures=false`.
7. The full gate must wire the exact-sidecar-only noise policy into the model
   receipt: `raw_noise_signal_audit_passed=true`,
   `exact_sidecars_only=true`, and `forbids_source_residual_noise=true`.
8. Rebuild `tools/build_premium_still_sr_promotion_receipts.py`; the Premium
   still/SR row is complete only when it reports `done_step_count=9`,
   `completion_percent=100.0`, `production_ready=true`, and no blockers.

Current proof:

- Gate16 acceptance:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate16_tail_safe_smoke_acceptance_20260702/smoke_gate_acceptance.json`
- Gate16 X2D checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate16_x2d_tail_safe_0015_smoke_20260702/premium_still_sr_raw_cfa_residual.pt`
- Gate16 full-promotion launch packet:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate16_promotion_launch_packet_20260702/gate16_promotion_launch_packet.json`
- Gate16 all-target-row rejection audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate16_target_row_audit_20260702/gate16_target_row_audit.json`
- Gate17 balanced replacement target package:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.json`
- Gate17 rejected training receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_balanced_smoke_train_20260702/train_receipt.json`
- Gate17 rejected broad target-row audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_balanced_target_row_audit_20260702/gate16_target_row_audit.json`
- Gate18 candidate/objective revision:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate18_candidate_objective_revision_20260703/gate18_candidate_objective_revision.json`
- Gate18 rejected broad target-row audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate18_tail_safe_context_target_row_audit_20260703/gate16_target_row_audit.json`
- Gate16-aware promotion rollup:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_gate16_20260702/premium_still_sr_promotion_receipts.json`
- Candidate-HF feature rejection:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_hf_feature_audit_20260703/candidate_hf_feature_audit.json`
- Gate20 supervision/objective revision:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate20_supervision_objective_revision_20260703/gate20_supervision_objective_revision.json`

The Gate16-aware rollup currently records `done_step_count=5`,
`total_step_count=9`, `completion_percent=55.6`, and
`first_open_step=model_promotion_floor`. The Gate16 target-row audit narrows
that blocker: the smoke pass did not generalize across the current target set.
The audit records `row_scope=target_row_tile`, `target_row_count=463`, only
`100mp` rows, median MAE/RMSE recovery of `-0.12226915231999792%` /
`-0.1296250122706981%`, and worst MAE recovery of
`-9.625700832601128%`. Gate17 closes replacement target construction by
materializing `1152` balanced target rows: `576` 50 MP and `576` 100 MP. The
first Gate17 training/audit then rejects the unmodified raw-CFA residual
candidate: overall median MAE recovery `-0.23468499188533842%`, overall median
RMSE recovery `0.34200684333480724%`, 100 MP median MAE/RMSE
`-0.20590927436038237%` / `-0.20105907022904856%`, 50 MP median MAE/RMSE
`-0.23798252847127244%` / `0.8416423186511623%`, 100 MP worst MAE
`-35.30304893327897%`, and 50 MP worst MAE `-2.259351982942634%`. Gate18
collapses toward no-op, Gate19 source-HF direct prediction has negative median
recovery and severe tails, Gate17 scalar calibration cannot close the floor,
and candidate-HF feature scaling is not predictive. The remaining blockers are
Gate20 rebuilt-supervision targets, broad target-row audit pass, full 50 MP /
100 MP gate rows, timing/memory, exact noise-policy wiring, and production
submission.

The Gate16 launch packet recorded `ready_to_launch_full_gate=true`, but the
later all-target-row audit supersedes that launch state. Older route-readiness
metrics cannot close this gate, and Gate16 itself no longer qualifies for a
full promotion attempt. Gate17 is now the replacement target package and a
rejected baseline model. Gate18 revision/training/audit now shows that
tail-safe context training collapses toward no-op. Gate19 source-HF training,
Gate17 scalar calibration, and candidate-HF feature scaling now prove the next
attempt must rebuild supervision rather than use direct source-HF prediction,
scalar output tuning, or stored candidate-HF feature scaling. Gate20 may train
only after the rebuilt-supervision target receipt passes no-REF/candidate-only
preflight.
