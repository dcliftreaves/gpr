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
7. Build the next Premium still/SR candidate and target package. It must pass a
   broad target-row audit before any full 50 MP / 100 MP promotion receipt:
   15% / 15% held-out MAE/RMSE, nonnegative worst row, editor/openability,
   timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and
   production submission validation.
8. Close raw-stills noise by proving Mission 1 and iPhone true-dark provenance,
   then building strict camera-noise sidecars.
9. Close GoPro raw-video MVP only with a real Mission 1 camera-role run:
   sensor/DMA or camera ring-buffer source, SD writer, rear display, valid
   `.gvid`, zero drops, memory, 120+ sustained frames, 4096 x 3072 encode,
   1024 x 768 preview, and the accepted 20+ fps floor.

| order | goal | 100 percent condition | current next move |
|---:|---|---|---|
| 1 | CI and repo hygiene | Latest `master` commit has passing GitHub Actions, sensitive-content guard, artifact-hygiene guard, release-manifest guard, README guards, and clean diff checks. | Protect on every push. |
| 2 | Best RAW stills | 50 MP and 100 MP still tiers remain green, normal RGGB/GBRG/GRBG/BGGR Bayer support remains green, and Mission 1 plus iPhone camera-noise sidecars validate from strict true-dark provenance. | Capture/prove Mission 1 and iPhone true darkframes, then build strict sidecars. |
| 3 | GoPro RAW video MVP | Real Mission 1 camera-role source/storage/display receipts prove 4096 x 3072 Bayer `.gvid` encode, 1024 x 768 preview decode, valid container, zero drops, memory, and 120+ sustained frames at the accepted 20+ fps floor. | Hand GoPro/Mission 1 firmware owners the camera-role runbook; local Pi stand-ins cannot close this gate. |
| 4 | Premium still/SR | A no-REF 50 MP / 100 MP premium still candidate passes the full promotion gate: 15% / 15% held-out MAE/RMSE floor, nonnegative worst row, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. | Build a replacement for the rejected Gate16 candidate. It must first pass broad target-row coverage with both 50 MP and 100 MP evidence, then the full promotion gate. |
| 5 | RAW video reconstruction | Approved 4K cleanup and 8K SR release receipts stay locked and green; replacement research ships only if it beats the locked artifact surface. | Protect only. PSF/blur is optional research, not a release blocker. |

The local priority order is fixed: **CI first, Premium still/SR replacement
candidate and target package second, Mission/iPhone darkframe provenance third,
GoPro camera-role handoff fourth, locked raw-video reconstruction protection
fifth.**

| order | gate | status | exact next step | receipt that moves it |
|---:|---|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Keep GitHub Actions green for the latest `master` push and run the sensitive-content, manifest, artifact-hygiene, and diff checks before each push. | Latest `master` CI run passes. |
| 2 | RAW video reconstruction | closed/protect | Do not reopen approved 4K cleanup or 8K SR unless a locked receipt fails or a replacement already beats the locked artifact surface. | Product lock ledger, README pillar guard, and release manifest guard pass. |
| 3 | Premium still/SR Gate 14 intake | closed/local | Protect `premium_still_sr_gate14_candidate_intake_20260702`: selector sidecar, source-model mapping, feature schema, hashes, candidate-only runtime policy, and exact no-op fallback are persisted. | Gate 14 executable selector intake reproduces the Gate 13 pass using candidate-only runtime inputs and Z8 exact-noop. |
| 4 | Premium still/SR Gate 14 selector smoke | closed/local | Protect `premium_still_sr_gate14_selector_smoke_20260702`: the persisted sidecar runs through runtime feature recomputation, source/checkpoint hash checks, first-match routing, and intake replay comparison. | Selector smoke reproduces the X2D pass, preserves Z8 exact-noop, records model/checkpoint hashes, and uses no REF/source/JPEG/gate metric inputs. |
| 5 | Premium still/SR Gate14 floor-student launch packet | closed/local | Protect `premium_still_sr_gate14_floor_student_preflight_20260702` and `premium_still_sr_gate14_floor_student_launch_packet_20260702`: the next candidate named by the model-floor gap has a launchable preflight, paired X2D/Z8 smoke commands, exact no-op fallback, and no REF/source/JPEG render-time inputs. | `preflight_audit.json` says `launchable_preflight_passed` for `premium_still_sr_gate14_floor_student_v1`, with `1.0%` median MAE smoke floor and `0.0%` worst-row floor. |
| 6 | Premium still/SR replacement candidate | open/local | Do not rerun `premium_still_sr_gate16_tail_safe_x2d_positive_z8_noop_v1` as the production candidate. Its all-target-row audit records `target_row_count=463`, only `100mp` rows, `row_scope=target_row_tile`, median MAE/RMSE recovery of `-0.12226915231999792%` / `-0.1296250122706981%`, and worst MAE recovery of `-9.625700832601128%`. Build the replacement target package with both 50 MP and 100 MP rows and require broad target-row pass before full promotion. | New target-row audit passes broad 50 MP / 100 MP coverage, then `premium_still_sr_promotion_receipts` pass 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. |
| 7 | RAW stills noise sidecars | open/sample | Capture or prove Mission 1 and iPhone true darkframes with strict no-scene-signal provenance. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate, then camera-noise calibration sidecars pass `--require-source-provenance`. |
| 8 | Mission 1 raw-video MVP | blocked_external | GoPro/Mission 1 firmware owner runs the camera-role validation on real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Real camera-role receipts show valid `.gvid`, zero drops, 120+ sustained frames, memory, 4096 x 3072 source encode, 1024 x 768 preview, and 20+ fps floor. |

## Current Local Result

The current local state is Gate16 paired-smoke pass, followed by Gate16
all-target-row rejection. Do not spend another day on ambiguous "improve CNN"
work; burn down these rows in order:

1. Build a replacement target package that contains both 50 MP and 100 MP
   rows, records target/source provenance, and marks whether each row is
   target-row/tile scope or true full-frame scope.
2. Train or select a replacement candidate whose runtime inputs remain
   candidate-only: `candidate_raw` plus camera metadata/sidecars, with no
   REF/source/JPEG render-time content.
3. Run `tools/build_premium_still_sr_gate16_target_row_audit.py` or its
   successor on the replacement. It must record both `50mp` and `100mp`
   row counts, median MAE/RMSE recovery `>= 15.0`, and worst-row MAE recovery
   `>= 0.0` before a full promotion run is allowed.
4. Build the full 50 MP / 100 MP still-SR gate receipt with `--real-artifacts`
   for review media, editable DNG/GPR evidence, dashboard, checkpoint hash,
   actual render timings, and peak RSS.
5. The full gate must record both `full_frame_gate_50mp_row_count > 0` and
   `full_frame_gate_100mp_row_count > 0`.
6. The full gate must record both `median_mae_reduction_pct_50mp >= 15.0` and
   `median_mae_reduction_pct_100mp >= 15.0`.
7. The full gate must record both worst-row MAE reductions as `>= 0.0` and
   `severe_worst_row_failures=false`.
8. The full gate must wire the exact-sidecar-only noise policy into the model
   receipt: `raw_noise_signal_audit_passed=true`,
   `exact_sidecars_only=true`, and `forbids_source_residual_noise=true`.
9. Rebuild `tools/build_premium_still_sr_promotion_receipts.py`; the Premium
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
- Gate16-aware promotion rollup:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_gate16_20260702/premium_still_sr_promotion_receipts.json`

The Gate16-aware rollup currently records `done_step_count=5`,
`total_step_count=9`, `completion_percent=55.6`, and
`first_open_step=model_promotion_floor`. The Gate16 target-row audit narrows
that blocker: the smoke pass did not generalize across the current target set.
The audit records `row_scope=target_row_tile`, `target_row_count=463`, only
`100mp` rows, median MAE/RMSE recovery of `-0.12226915231999792%` /
`-0.1296250122706981%`, and worst MAE recovery of
`-9.625700832601128%`. The remaining blockers are replacement target
construction, full 50 MP / 100 MP gate rows, timing/memory, exact noise-policy
wiring, and production submission.

The Gate16 launch packet recorded `ready_to_launch_full_gate=true`, but the
later all-target-row audit supersedes that launch state. Older route-readiness
metrics cannot close this gate, and Gate16 itself no longer qualifies for a
full promotion attempt. The next run must therefore build a replacement
candidate with broad 50 MP / 100 MP target-row evidence before full-frame
inference and timing.
