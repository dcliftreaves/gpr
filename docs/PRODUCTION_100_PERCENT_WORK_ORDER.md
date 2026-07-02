# Production 100 Percent Work Order

Last refreshed: 2026-07-02

This is the unambiguous work order. Work counts only when it creates or
validates the named receipt. A dashboard, note, training log, or visual review
does not move the project unless it is referenced by that receipt.

## Stop Rule

Continue from the first open local row. Stop only when one of these is true:

1. The row's receipt exists, validates, is linked from the release evidence or
   production artifact docs, and CI is green after push.
2. The row is proven externally blocked, with the blocking condition recorded in
   the row's receipt.
3. CI fails, in which case fixing CI becomes the only active row.

## Ordered Rows

| order | row | status | done means |
|---:|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Latest pushed `master` GitHub Actions run passes; sensitive-content, artifact-hygiene, README, manifest, and product-lock guards pass locally before push. |
| 2 | RAW video reconstruction | closed/protect | Approved 4K cleanup and 8K SR receipts stay locked and green. Do not reopen for PSF research or dashboard cosmetics. |
| 3 | Premium still/SR Gate 14 selector | closed/protect | Gate 14 sidecar reloads, recomputes candidate-only runtime features, verifies source/checkpoint hashes, routes deterministically, and matches intake. |
| 4 | Premium still/SR promotion | open/local | `premium_still_sr_promotion_receipts` proves 50 MP and 100 MP no-REF quality, nonnegative worst rows, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. |
| 5 | RAW stills noise sidecars | open/sample | Mission 1 and iPhone each have four strict-provenance true darkframes and production-ready camera-noise sidecars. |
| 6 | Mission 1 raw-video camera role | blocked/external | GoPro/Mission 1 firmware owner runs real sensor/DMA or camera ring-buffer source, SD writer, rear display, valid `.gvid`, zero drops, memory, and 120+ sustained frames at the accepted 20+ fps floor. |

## Current First Open Row

The first open local row is **Premium still/SR promotion**.

The next exact receipt is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_20260702/premium_still_sr_promotion_receipts.json
```

The first open sub-receipt is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_model_floor_gap_20260702/model_floor_gap.json
```

It defines the next candidate contract as
`premium_still_sr_gate14_floor_student_v1`: distill or replace the Gate 14
routed selector/source evidence with a true candidate-only student or measured
high/low raw source evidence before any long run.

The candidate preflight and launch packet now exist:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/candidate_preflight.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/preflight_audit.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_launch_packet_20260702/launch_packet.json
```

They pass the preflight checker as launchable intake artifacts only. They do
not claim production readiness.

The target-builder audit now exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_targets_20260702/gate14_floor_student_targets.json
```

It blocks the smoke run with
`blocker_classification=gate14_raw_target_identity_missing`: the current
Gate14 pair surface has `4800` tiles and the current raw-CFA target set has
`117` rows, but direct row identity overlap is `0`. Do not train the floor
student from the unrelated raw-CFA target set.

## 100 Percent Ladder

Move rows in this exact order. Do not skip a row because a later dashboard
looks better.

| order | row | receipt | pass condition |
|---:|---|---|---|
| 1 | Gate14 floor-student preflight | `premium_still_sr_gate14_floor_student_preflight_20260702/preflight_audit.json` | `launchable_preflight_passed`, candidate id `premium_still_sr_gate14_floor_student_v1`, no REF/source/JPEG render-time inputs, X2D+Z8 smokes required, median MAE recovery floor `1.0%`, worst-row floor `0.0%`. |
| 2 | Gate14 floor-student target builder | `premium_still_sr_gate14_floor_student_targets_20260702/gate14_floor_student_targets.json` plus `gate14_floor_student_targets.npz` only if passed | Builds candidate-only student targets from Gate 14 pseudo-label/source selection and selector sidecar hashes; no production renderer uses Gate 14 output directly. Current result is blocked because direct row identity overlap is `0`. |
| 3 | Paired smoke gates | `premium_still_sr_gate14_floor_student_x2d_smoke_20260702/train_receipt.json` and `premium_still_sr_gate14_floor_student_z8_smoke_20260702/train_receipt.json` | Both holdouts beat same-color Bayer interpolation by at least `1.0%` median MAE recovery and `0.0%` worst-row recovery; checkpoint and training-config hashes are recorded. |
| 4 | Smoke acceptance | `premium_still_sr_gate14_floor_student_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | X2D and Z8 smoke receipts meet the preflight acceptance contract. If either fails, record the blocker class and return to target construction, not selector replay. |
| 5 | Full promotion gate | `premium_still_sr_promotion_gate_<date>/promotion_gate.json` | 50 MP and 100 MP full-frame rows clear `15% / 15%` median MAE/RMSE recovery, nonnegative worst rows, editor/openability, exact-sidecar-only noise policy, and no REF/source/JPEG render-time inputs. |
| 6 | Timing and memory | timing/memory receipt referenced by the promotion gate | Actual render path reports seconds per 50 MP frame, seconds per 100 MP frame, and peak RSS. |
| 7 | Production submission | production capture/submission receipt | Checkpoint hash, sidecar/training config, dashboard, promotion gate, timing/memory, editable DNG/GPR, and noise-policy evidence all validate. |
| 8 | CI and docs | latest pushed `master` GitHub Actions run | CI passes after docs/manifests/artifact hashes are updated; sensitive-content and artifact-hygiene guards pass locally. |

That receipt may say production is still blocked, but it must classify the
blocker. Acceptable blocker classes are:

- `model_promotion_floor_not_met`
- `full_50mp_100mp_gate_missing`
- `worst_row_tail_regression`
- `editor_openability_missing`
- `timing_memory_missing`
- `checkpoint_or_sidecar_drift`
- `noise_policy_not_wired`
- `production_submission_missing_or_failed`
- `external_mission1_camera_role_access`

## Commands For The Current Row

```bash
python3 tools/build_premium_still_sr_promotion_receipts.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_20260702

python3 tools/build_premium_still_sr_model_floor_gap.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_model_floor_gap_20260702

python3 tools/build_premium_still_sr_candidate_preflight_template.py \
  --template gate14_floor_student \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/candidate_preflight.json

python3 tools/check_premium_still_sr_candidate_preflight.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/candidate_preflight.json \
  --json-out /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/preflight_audit.json \
  --html-out /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/index.html \
  --require-launchable

python3 tools/build_premium_still_sr_launch_packet.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_launch_packet_20260702 \
  --manifest /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_preflight_20260702/candidate_preflight.json \
  --require-launchable

/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/build_premium_still_sr_gate14_floor_student_targets.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate14_floor_student_targets_20260702

python3 tools/check_premium_still_sr_promotion_gate.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_gate_current_20260702

python3 tools/test/check_production_capture_requirements.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_sensitive_content.py
```

Do not move to Mission/iPhone darkframes until this row has either a production
receipt or a specific machine-readable blocker receipt.
