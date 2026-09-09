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

The first open sub-receipt is Gate18 candidate/objective revision. Gate17 target
construction is useful and closed; the first Gate17 trained checkpoint is
rejected by the broad audit and must not be rerun unchanged as the production
path.

Current closed/rejected evidence:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_balanced_smoke_train_20260702/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_balanced_target_row_audit_20260702/gate16_target_row_audit.json
```

Gate17 audit summary:

```text
target rows: 1152 total, 576 50 MP, 576 100 MP
overall median MAE / RMSE recovery: -0.23468499188533842% / 0.34200684333480724%
100 MP median MAE / RMSE recovery: -0.20590927436038237% / -0.20105907022904856%
50 MP median MAE / RMSE recovery: -0.23798252847127244% / 0.8416423186511623%
100 MP / 50 MP worst MAE recovery: -35.30304893327897% / -2.259351982942634%
verdict: rejected before full-frame promotion
```

Gate18 candidate/objective revision and train/audit are now built from this
failure. Gate18 is safer than Gate17, but it collapses toward no-op and remains
far below the 15% / 15% promotion floor. The first open local row is now Gate19:
recover positive signal while preserving the Gate18 tail safety.

## 100 Percent Ladder

Move rows in this exact order. Do not skip a row because a later dashboard
looks better.

| order | row | receipt | pass condition |
|---:|---|---|---|
| 1 | Gate17 target construction | `premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.json` plus NPZ | Closed: 1152 balanced rows, 576 50 MP and 576 100 MP, candidate-only runtime policy, no REF/source/JPEG. |
| 2 | Gate17 baseline train/audit | `premium_still_sr_gate17_balanced_target_row_audit_20260702/gate16_target_row_audit.json` | Closed/rejected: broad target-row audit ran and records negative median MAE plus negative worst rows. |
| 3 | Gate18 candidate/objective revision | `premium_still_sr_gate18_candidate_objective_revision_20260703/gate18_candidate_objective_revision.json` | Closed: names `premium_still_sr_gate18_tail_safe_context_objective_v1`, rejects unchanged Gate17 reruns, includes exact training/audit commands, and keeps no-REF candidate-only runtime inputs. |
| 4 | Gate18 broad target-row audit | `premium_still_sr_gate18_tail_safe_context_target_row_audit_20260703/gate16_target_row_audit.json` | Closed/rejected: broad 50 MP / 100 MP coverage, safer worst rows, but no positive median recovery. |
| 5 | Gate19 positive-signal/source revision | `premium_still_sr_gate19_positive_signal_source_revision_<date>/gate19_positive_signal_source_revision.json` | Names how positive signal is recovered without REF/source/JPEG runtime content and without reopening Gate17 tail failures. |
| 6 | Gate19 broad target-row audit | `premium_still_sr_gate19_target_row_audit_<date>/gate16_target_row_audit.json` | 50 MP and 100 MP target rows clear `15% / 15%` median MAE/RMSE recovery and nonnegative worst-row MAE. |
| 7 | Full promotion gate | `premium_still_sr_promotion_gate_<date>/promotion_gate.json` | 50 MP and 100 MP full-frame rows clear the same floors, editor/openability, exact-sidecar-only noise policy, and no REF/source/JPEG render-time inputs. |
| 8 | Timing and memory | timing/memory receipt referenced by the promotion gate | Actual render path reports seconds per 50 MP frame, seconds per 100 MP frame, and peak RSS. |
| 9 | Production submission | production capture/submission receipt | Checkpoint hash, sidecar/training config, dashboard, promotion gate, timing/memory, editable DNG/GPR, and noise-policy evidence all validate. |
| 10 | CI and docs | latest pushed `master` GitHub Actions run | CI passes after docs/manifests/artifact hashes are updated; sensitive-content and artifact-hygiene guards pass locally. |

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
env TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp \
  /Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/build_premium_still_sr_gate17_replacement_targets.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_replacement_targets_20260702

env TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp \
  /Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/build_premium_still_sr_gate16_target_row_audit.py \
  --candidate-id premium_still_sr_gate17_balanced_50mp_100mp_v1 \
  --train-receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_balanced_smoke_train_20260702/train_receipt.json \
  --targets /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.npz \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate17_balanced_target_row_audit_20260702

# Next local production work:
# 1. Build Gate19 positive-signal/source revision from:
#    /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate18_tail_safe_context_target_row_audit_20260703/gate16_target_row_audit.json
# 2. Train only the command named by that Gate19 revision receipt.
# 3. Run the broad 50 MP / 100 MP target-row audit before any full promotion gate.

python3 tools/test/check_production_capture_requirements.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_sensitive_content.py
```

Do not move to Mission/iPhone darkframes until this row has either a production
receipt or a specific machine-readable blocker receipt.
