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
6. Gate16 learnability/objective revision is closed as a paired-smoke pass:
   X2D median/worst raw MAE recovery is 17.086680690440865% / 0.0%, and Z8
   exact-noop passes at 0.0% / 0.0%.
7. Only after paired smoke passes, run the full 50 MP / 100 MP Premium still-SR
   promotion receipt: 15% / 15% held-out MAE/RMSE, nonnegative worst row,
   editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only
   noise policy, and production submission validation.
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
| 4 | Premium still/SR | A no-REF 50 MP / 100 MP premium still candidate passes the full promotion gate: 15% / 15% held-out MAE/RMSE floor, nonnegative worst row, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. | Run the full promotion-gate package for the accepted Gate16 candidate; do not reopen Gate14/Gate15 unless the full gate identifies a specific failed subcondition. |
| 5 | RAW video reconstruction | Approved 4K cleanup and 8K SR release receipts stay locked and green; replacement research ships only if it beats the locked artifact surface. | Protect only. PSF/blur is optional research, not a release blocker. |

The local priority order is fixed: **CI first, Gate16 full 50 MP / 100 MP
Premium still-SR promotion second, Mission/iPhone darkframe provenance third,
GoPro camera-role handoff fourth, locked raw-video reconstruction protection
fifth.**

| order | gate | status | exact next step | receipt that moves it |
|---:|---|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Keep GitHub Actions green for the latest `master` push and run the sensitive-content, manifest, artifact-hygiene, and diff checks before each push. | Latest `master` CI run passes. |
| 2 | RAW video reconstruction | closed/protect | Do not reopen approved 4K cleanup or 8K SR unless a locked receipt fails or a replacement already beats the locked artifact surface. | Product lock ledger, README pillar guard, and release manifest guard pass. |
| 3 | Premium still/SR Gate 14 intake | closed/local | Protect `premium_still_sr_gate14_candidate_intake_20260702`: selector sidecar, source-model mapping, feature schema, hashes, candidate-only runtime policy, and exact no-op fallback are persisted. | Gate 14 executable selector intake reproduces the Gate 13 pass using candidate-only runtime inputs and Z8 exact-noop. |
| 4 | Premium still/SR Gate 14 selector smoke | closed/local | Protect `premium_still_sr_gate14_selector_smoke_20260702`: the persisted sidecar runs through runtime feature recomputation, source/checkpoint hash checks, first-match routing, and intake replay comparison. | Selector smoke reproduces the X2D pass, preserves Z8 exact-noop, records model/checkpoint hashes, and uses no REF/source/JPEG/gate metric inputs. |
| 5 | Premium still/SR Gate14 floor-student launch packet | closed/local | Protect `premium_still_sr_gate14_floor_student_preflight_20260702` and `premium_still_sr_gate14_floor_student_launch_packet_20260702`: the next candidate named by the model-floor gap has a launchable preflight, paired X2D/Z8 smoke commands, exact no-op fallback, and no REF/source/JPEG render-time inputs. | `preflight_audit.json` says `launchable_preflight_passed` for `premium_still_sr_gate14_floor_student_v1`, with `1.0%` median MAE smoke floor and `0.0%` worst-row floor. |
| 6 | Premium still/SR promotion | open/local | Run the full promotion-gate package for `premium_still_sr_gate16_tail_safe_x2d_positive_z8_noop_v1`. Gate16 paired smoke passed: X2D median/worst raw MAE recovery was `17.086680690440865%` / `0.0%`; Z8 exact-noop passed at `0.0%` / `0.0%`; `long_run_allowed=true`. The next receipt must prove the 15% / 15% held-out MAE/RMSE floor, nonnegative worst row, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation on the full 50 MP / 100 MP gate. | `premium_still_sr_promotion_receipts` pass 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. |
| 7 | RAW stills noise sidecars | open/sample | Capture or prove Mission 1 and iPhone true darkframes with strict no-scene-signal provenance. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate, then camera-noise calibration sidecars pass `--require-source-provenance`. |
| 8 | Mission 1 raw-video MVP | blocked_external | GoPro/Mission 1 firmware owner runs the camera-role validation on real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Real camera-role receipts show valid `.gvid`, zero drops, 120+ sustained frames, memory, 4096 x 3072 source encode, 1024 x 768 preview, and 20+ fps floor. |

## Current Local Result

The current local state is Gate16 paired-smoke pass plus full-promotion open.
Do not spend another day on ambiguous "improve CNN" work; burn down these rows
in order:

1. Rebuild the strict promotion receipt rollup with the Gate16 smoke acceptance
   input and keep `paired_smoke_gate=true`.
2. Build the full Gate16 still-SR gate receipt with `--real-artifacts` for
   50 MP and 100 MP review media, editable DNG/GPR evidence, dashboard, and
   checkpoint hash `aeebad51bd54964b37c356457084197f6fadcad2b3df43cc44c6f8c3bdef6d1d`.
3. The full gate must record both `full_frame_gate_50mp_row_count > 0` and
   `full_frame_gate_100mp_row_count > 0`.
4. The full gate must record both `median_mae_reduction_pct_50mp >= 15.0` and
   `median_mae_reduction_pct_100mp >= 15.0`.
5. The full gate must record both worst-row MAE reductions as `>= 0.0` and
   `severe_worst_row_failures=false`.
6. The full gate must record actual render timings:
   `render_seconds_per_50mp_frame > 0`,
   `render_seconds_per_100mp_frame > 0`, and `peak_rss_gb > 0`.
7. The full gate must wire the exact-sidecar-only noise policy into the model
   receipt: `raw_noise_signal_audit_passed=true`,
   `exact_sidecars_only=true`, and `forbids_source_residual_noise=true`.
8. Run `tools/check_premium_still_sr_promotion_gate.py` against that full gate
   and require production-ready only after scoreboard, noise policy, full gate,
   and next-contract state agree.
9. Rebuild `tools/build_premium_still_sr_promotion_receipts.py`; the Premium
   still/SR row is complete only when it reports `done_step_count=9`,
   `completion_percent=100.0`, `production_ready=true`, and no blockers.

Current proof:

- Gate16 acceptance:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate16_tail_safe_smoke_acceptance_20260702/smoke_gate_acceptance.json`
- Gate16 X2D checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate16_x2d_tail_safe_0015_smoke_20260702/premium_still_sr_raw_cfa_residual.pt`
- Gate16-aware promotion rollup:
  `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_gate16_20260702/premium_still_sr_promotion_receipts.json`

The Gate16-aware rollup currently records `done_step_count=5`,
`total_step_count=9`, `completion_percent=55.6`, and
`first_open_step=model_promotion_floor`. The remaining blockers are
`model_promotion_floor_not_met`, `full_50mp_100mp_gate_missing`,
`timing_memory_missing`, `noise_policy_not_wired`, and
`production_submission_missing_or_failed`.
