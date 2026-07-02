# Production 100 Percent Burn-Down

Last refreshed: 2026-07-02

This is the short execution list. Work starts at the first local open gate and
only moves when the named receipt passes or the blocker receipt names the exact
reason it cannot pass.

## Gate Order

| order | gate | status | percent | exact next receipt |
|---:|---|---|---:|---|
| 1 | CI and repo hygiene | passing at last push; protect | 100 | Latest GitHub Actions run for `master` is green; local sensitive-content, manifest, artifact-hygiene, and diff checks pass before every push. |
| 2 | RAW video reconstruction | closed; protect | 100 | Existing 4K cleanup and 8K SR lock-ledger, dashboards, ProRes media, editable raw receipts, and manifest guards remain green. |
| 3 | RAW stills | open on darkframe provenance | 92 | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate with four same-camera/same-ISO no-scene-signal CFA frames each, then camera-noise sidecars pass strict provenance. |
| 4 | RAW video MVP | externally blocked on camera-role run | 80 | Real Mission 1 camera-role receipts from sensor/DMA or camera ring-buffer source, SD writer, rear display, valid `.gvid`, zero drops, memory, and 120+ sustained frames at the accepted 20+ fps floor. |
| 5 | Premium still/SR | open local blocker | 60 | A candidate-only no-REF model receipt clears 15% / 15% held-out MAE/RMSE, nonnegative worst-row MAE, 50 MP + 100 MP route coverage, editor/openability, timing/memory, exact-sidecar-only noise policy, and production submission validation. |

## Current First Local Gate

Gate 5 is the first open local gate because Gate 4 requires real Mission 1
camera-role access. The latest Gate 5 branch is closed as a failed smoke:

| branch | evidence | decision |
|---|---|---|
| frequency-pyramid source-evidence teacher | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_frequency_pyramid_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. X2D median MAE is barely positive but worst-row MAE is `-4.850145322879209%`; Z8 median MAE is `-8.809287941837436%` and worst-row MAE is `-67.44360239254922%`. |
| gated no-op residual source-evidence teacher | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gated_residual_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. Z8 damage is reduced to `-0.07770732977859413%` median MAE and `-0.9817010759922141%` worst-row MAE, but X2D worst-row MAE is `-17.16908196504484%`. |
| stricter gated identity probe | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gated_residual_identity_z8_smoke_20260702/train_receipt.json` | Not a launchable production branch. It nearly collapses to interpolation parity: X2D median/worst are `+0.00008488424079708562%` / `-0.011432486540108134%`; Z8 median/worst are `-0.0014934440317522601%` / `-0.011380055480565317%`. |
| masked-detail/no-op target objective | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_masked_detail_noop_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. X2D median/worst-row MAE is `-0.000016166284221217207%` / `-0.004217229249483704%`; Z8 median/worst-row MAE is `-0.0011404326756156245%` / `-0.009009865416027604%`. Same-camera scene smokes also stay negative, so this is an objective/gating failure rather than only a cross-camera split problem. |
| raw-CFA source-frequency target objective | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_sourcefreq_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. The absolute source-frequency target is the wrong objective scale: X2D median/worst-row raw MAE recovery is `-4968.130415027571%` / `-10524.379064644432%`; Z8 median/worst-row raw MAE recovery is `-502.5390630379172%` / `-966.3531327864554%`. |
| raw-CFA residual signal objective | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_residual_signal_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. Direct raw-CFA residual training is near parity on X2D but still regresses: X2D median/worst-row raw MAE recovery is `-0.15178115040635068%` / `-5.352462806764585%`; Z8 median/worst-row raw MAE recovery is `-5.108265406545033%` / `-178.9545417615565%`. This points to route-specific no-op/benefit gating or Z8 target conditioning, not another generic U-Net residual smoke. |
| raw-CFA candidate-HF no-op gate | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_candidate_hf_noop_smoke_gate_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. Candidate-only HF gating clips the Z8 low-HF tail to exact parity, but does not create positive learning: X2D median/worst-row raw MAE recovery is `-0.006290143931539378%` / `-0.23156087540736878%`; Z8 median/worst-row raw MAE recovery is `0.0%` / `0.0%`, below the `>0.001%` median floor. A frame-context diagnostic also failed X2D at `-0.01923371655785397%` median, so simple gate/context tuning is not enough. |
| target/degradation blocker receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_degradation_evidence_20260702/target_degradation_evidence.json` | Current local blocker is now explicit and machine-readable: long-run allowed is `false`; X2D candidate-HF no-op median/worst recovery is `-0.006290143931539378%` / `-0.23156087540736878%`; Z8 is safe but zero-benefit at `0.0%` / `0.0%`; frame-context X2D is worse at `-0.01923371655785397%`. This rules out simple no-op threshold tuning, simple frame-context conditioning, and another generic raw-CFA residual long run. |
| replacement target/source contract | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_replacement_target_source_contract_20260702/replacement_target_source_contract.json` | Ready for paired smoke preflight only. X2D has candidate-only source evidence at `4.821260781753699%` MAE / `11.520193787949786%` RMSE but a `3.4500243590744026x` holdout target-distribution mismatch; Z8 has only `0.649807764458084%` MAE source evidence despite `21.89973637064664%` RMSE recovery; calibrated target SNR is mixed signal/noise. The next candidate must use noise-aware or row-filtered residual targets, route-conditioned X2D sampling, changed Z8 degradation/source policy, candidate-only runtime inputs, and exact no-op behavior. |
| replacement-contract route-conditioned/noise-aware smoke | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate9_smoke_acceptance_20260702/smoke_gate_acceptance.json` | Blocked before long run. X2D median/worst raw MAE recovery is `-0.16833363636675505%` / `-6.051057523320477%`; Z8 median/worst raw MAE recovery is `-1.5863477181003771%` / `-55.716890568612115%`. This rules out the first replacement-contract U-Net route split with continuous SNR weighting and high-energy emphasis. |
| Gate 10 target/degradation decision | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate10_target_degradation_decision_20260702/gate10_target_degradation_decision.json` | Closed as `source_degradation_target_mismatch`. Gate 10 records X2D median/worst raw MAE recovery at `-0.16833363636675505%` / `-6.051057523320477%`, Z8 at `-1.5863477181003771%` / `-55.716890568612115%`, X2D target-distribution mismatch at `3.4500243590744026x`, and Z8 mostly noise-floor targets (`28/36`). It sets `paired_smoke_allowed=false` and allows only a degradation-source audit before the next candidate intake. |
| Gate 11 degradation-source audit | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_degradation_source_audit_20260702/degradation_source_audit.json` | Closed as `degradation_source_policy_ready_for_gate11_preflight`. It selects `route_isolated_teacher_then_router`: X2D may train on `70` signal/mixed rows with stratified target sampling and no-op fallback; Z8 must default no-op for noise-floor rows and cannot train positive residuals without a new source-evidence receipt. |
| current scoreboard | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_masked_detail_20260702/scoreboard.json` | 124 runtime-safe receipts, 0 promotable receipts, best runtime-safe row remains 4.03% MAE / 3.75% RMSE versus the 15% / 15% floor. |

## Next Unambiguous Step

Build `premium_still_sr_gate11_candidate_intake_<date>` from the route-isolated
teacher/router policy. Do not rerun source-frequency targets, generic full-crop
U-Net residual training, masked-detail thresholds, candidate-HF no-op threshold
tuning, simple frame-context conditioning, the Gate 9 route-conditioned/noise-
aware U-Net smoke, or the older clean-source residual families as production
work. The preflight must encode:

1. X2D training on signal/mixed rows only, with stratified target sampling and
   exact no-op fallback;
2. Z8 no-op for current noise-floor rows and no positive residual training
   unless a new source-evidence receipt passes;
3. candidate-only runtime inputs with no REF/source/JPEG image content.

Only after that Gate 11 preflight exists may paired X2D/Z8 smoke run. The smoke
must create a positive no-REF learning signal while preserving exact no-op
behavior for low-error tiles.

The candidate may advance only if all of these are true:

| requirement | pass rule |
|---|---|
| X2D smoke | median MAE improvement `> 0.001%`, worst-row MAE improvement `>= 0%`, and baseline beaten. |
| Z8 smoke | median MAE improvement `> 0.001%`, worst-row MAE improvement `>= 0%`, and baseline beaten. |
| Runtime inputs | `candidate_raw`, `camera_metadata`, and optional exact validated noise sidecar only. |
| Forbidden inputs | No REF, source RAW, source RGB, source HF, JPEG target, source residual noise, or gate metric at render time. |
| Long-run permission | `tools/check_premium_still_sr_smoke_gate_acceptance.py --require-pass` passes on the paired smoke receipts. |
| Production permission | The 15% / 15% promotion floor, nonnegative worst-row recovery, editor/openability, timing/memory, exact-sidecar-only noise policy, and `check_production_capture_submission.py` all pass. |

## Commands That Move The Gate

```bash
python3 tools/build_premium_still_sr_gate10_target_degradation_decision.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate10_target_degradation_decision_<date>

python3 tools/build_premium_still_sr_degradation_source_audit.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_degradation_source_audit_<date>

# Next tool to build: tools/build_premium_still_sr_gate11_candidate_preflight.py
# The preflight must emit:
# /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate11_candidate_intake_<date>/candidate_preflight.json
```

Gate 11 paired smoke commands are intentionally absent until the candidate
intake exists. If the preflight cannot encode the Gate 11 policy, it must
classify the failure as source/degradation mismatch, objective/gating failure,
model capacity, camera-conditioning gap, timing/memory infeasibility, or
noise-policy mismatch.
