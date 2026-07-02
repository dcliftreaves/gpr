# Premium Still-SR First-Hour Promotion Checklist

This is the shortest path for deciding whether a new premium still-SR model is
worth a full production promotion attempt. It is deliberately stricter than a
sharp-looking crop. The current lane is active and diagnostic, but not
production-promoted.

## Decision In One Page

| question | current answer |
|---|---|
| Is premium still-SR shippable today? | No. The infrastructure exists, but current no-REF models do not clear the 50 MP / 100 MP still-SR promotion gate. |
| What is the current scorecard state? | **82** runtime-safe training receipts, **0** promotable rows, and best runtime-safe recovery of **4.03%** MAE / **3.75%** RMSE against the **15% / 15%** promotion floor. |
| What must a new candidate prove first? | Candidate-only runtime inputs, positive held-out recovery, 50 MP and 100 MP full-frame gates, editor-latitude review, worst-row review, editable raw outputs, timing, memory, and exact-sidecar-only noise policy. |
| What is forbidden at render time? | REF/source/JPEG image content, source residual noise, hidden source-HF targets, or any noise addback not tied to a validated exact camera/ISO sidecar. |
| What should happen before another long CNN run? | Build a small candidate and reject it early unless it improves held-out X2D and Z8 evidence with runtime-safe inputs. |

## First-Hour Steps

1. Read the promotion boundary, not just the training notes:

   ```sh
   sed -n '1,180p' docs/PREMIUM_STILL_SR.md
   sed -n '1,120p' docs/PRODUCTION_CAPTURE_REQUIREMENTS.md
   ```

2. Regenerate or inspect the current promotion gate:

   ```sh
   python3 tools/check_premium_still_sr_promotion_gate.py \
     --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_gate_<date> \
     --require-promotion-safe
   ```

   The expected current state is `promotion_safe=true` and
   `production_ready=false`. That means it is safe to keep experimenting, not
   safe to claim a premium still-SR product.

3. Build the fixture manifest and confirm the candidate has both 50 MP and
   100 MP evidence:

   ```sh
   python3 tools/build_premium_still_sr_fixture_manifest.py \
     --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_<date>
   ```

4. Before training long, run a short candidate through a held-out gate and
   write a receipt with:

   | field | requirement |
   |---|---|
   | checkpoint/config | SHA-256 hash and training config |
   | target hash | immutable target dataset hash |
   | runtime inputs | `candidate_raw`, camera metadata, and optional validated exact noise sidecars only |
   | forbidden inputs | no REF/source/JPEG content at render time |
   | holdouts | 50 MP and 100 MP full-frame row counts |
   | metrics | median MAE/RMSE reduction and worst-row MAE reduction |
   | review | worst-row dashboard and raw-editor latitude review |
   | outputs | editable DNG/GPR receipts and review TIFF/ProRes hashes where applicable |
   | performance | seconds per 50 MP frame, seconds per 100 MP frame, and peak RSS |
   | noise policy | exact-sidecar-only addback; source residual noise forbidden |

   The production form of `tools/build_premium_still_sr_gate_receipt.py` now
   refuses to write `production_ready=true` unless real editable DNG/GPR,
   review media, dashboard paths, no-REF runtime flags, 50 MP / 100 MP rows,
   positive median reductions, nonnegative worst-row reductions, timing/memory,
   and exact-sidecar-only noise policy are supplied. Use the full command shape
   in [`PREMIUM_STILL_SR.md`](PREMIUM_STILL_SR.md) only after a candidate has
   real artifacts.

5. Rebuild the scoreboard and reject the candidate if it cannot beat the
   promotion floor:

   ```sh
   python3 tools/build_premium_still_sr_experiment_scoreboard.py \
     --external-root /Volumes/OWC_8TB/gpr_work \
     --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_<date>
   ```

6. Submit only candidates that survive the scoreboard to the full production
   capture checker:

   ```sh
   python3 tools/build_production_capture_submission_template.py \
     --output /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/submission_template.json

   python3 tools/check_production_capture_submission.py <submission.json> \
     --json-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/audit.json \
     --html-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/index.html
   ```

## Promotion Requirements

| requirement | closure signal |
|---|---|
| candidate-only runtime | `runtime_inputs` includes `candidate_raw` and camera metadata, and excludes REF/source/JPEG image content |
| 50 MP gate | at least one full-frame 50 MP row, positive median MAE reduction, nonnegative worst-row MAE reduction |
| 100 MP gate | at least one full-frame 100 MP row, positive median MAE reduction, nonnegative worst-row MAE reduction |
| quality review | no severe worst-row visual failures and editor-latitude review passes |
| raw output | editable DNG/GPR receipts exist and openability is proven |
| performance | seconds/frame and peak RSS recorded for the offline render path |
| noise policy | only exact validated sidecars may drive nonzero noise removal/addback; source residual noise is forbidden |
| final registration | checkpoint hash, config hash, gate receipt, dashboard, and artifact hashes are recorded before any production claim |

## What Does Not Count

| shortcut | why it is insufficient |
|---|---|
| Looks sharper in one crop | The gate is full-frame, worst-row, and editor-latitude based. |
| Positive train split only | Current evidence already shows train improvement can fail scene-held-out X2D. |
| More time on the rejected 12k-step teacher | The 12k-step X2D scene-holdout run regressed; repeating the same objective is not a promotion path. |
| Clean target alone | The clean-signal U-Net smoke still regressed X2D; the next pass needs materially different supervision or runtime signal. |
| Runtime REF/source/HF leakage | It violates the no-REF production contract even if metrics improve. |
| Noise synthesized without exact sidecars | It violates the camera-noise policy and can hide source-noise leakage. |

## Current Evidence To Inspect

| evidence | path |
|---|---|
| Product promotion boundary | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_gate_20260702/index.html` |
| Experiment scoreboard | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260701/index.html` |
| Current next-experiment contract | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702/index.html` |
| Clean-source pair audit | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702/index.html` |
| X2D routed holdout rejection | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702/index.html` |
| Z8 routed holdout rejection | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702/index.html` |
| Clean-signal target dashboard | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_signal_targets_20260702/index.html` |
| Clean-signal U-Net rejection | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_signal_model_x2dsceneholdout_unet_w32_700_20260702/index.html` |

## Source Of Truth

| topic | document |
|---|---|
| Premium still-SR gate contract | [`PREMIUM_STILL_SR.md`](PREMIUM_STILL_SR.md) |
| Open production requirement | [`PRODUCTION_CAPTURE_REQUIREMENTS.md`](PRODUCTION_CAPTURE_REQUIREMENTS.md) and [`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json) |
| Locked paths versus open gates | [`PRODUCT_LOCK_LEDGER.md`](PRODUCT_LOCK_LEDGER.md) |
| Camera-noise policy | [`CAMERA_NOISE_CALIBRATION.md`](CAMERA_NOISE_CALIBRATION.md) |
