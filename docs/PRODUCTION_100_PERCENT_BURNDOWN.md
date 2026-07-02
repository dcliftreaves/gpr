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
| current scoreboard | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_masked_detail_20260702/scoreboard.json` | 124 runtime-safe receipts, 0 promotable receipts, best runtime-safe row remains 4.03% MAE / 3.75% RMSE versus the 15% / 15% floor. |

## Next Unambiguous Step

Build a new Premium still/SR target/degradation evidence receipt that fixes the
**raw-CFA objective failure mode just evidenced**. Do not rerun
source-frequency targets, generic full-crop U-Net residual training,
masked-detail thresholds, candidate-HF no-op threshold tuning, or the older
clean-source residual families as production work. The next candidate must be
one of:

1. a new target/degradation source receipt showing that the current raw-CFA
   residual targets are mismatched to the candidate render path, with a
   proposed replacement objective;
2. a materially different route-conditioning candidate, not just frame-context
   plus the existing no-op gate, that proves the `Z8Z_1353` and X2D parity
   failures are not target/degradation mismatch before mixing routes;
3. a teacher/objective that creates a positive no-REF signal on both X2D and
   Z8 while preserving exact no-op behavior for low-error tiles.

It must create a positive no-REF learning signal while preserving exact no-op
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
python3 tools/build_premium_still_sr_candidate_preflight_template.py \
  --template <new_gated_residual_template> \
  --candidate-id <new_candidate_id> \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_preflight>/candidate_preflight.json

python3 tools/check_premium_still_sr_candidate_preflight.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_preflight>/candidate_preflight.json \
  --json-out /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_preflight>/preflight_audit.json \
  --html-out /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_preflight>/index.html \
  --require-launchable

/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python tools/cnn/train_premium_still_sr_raw_cfa_residual.py \
  <exact X2D smoke command from candidate_preflight.json>

/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python tools/cnn/train_premium_still_sr_raw_cfa_residual.py \
  <exact Z8 smoke command from candidate_preflight.json>

python3 tools/check_premium_still_sr_smoke_gate_acceptance.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_preflight>/candidate_preflight.json \
  --json-out /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_smoke_gate>/smoke_gate_acceptance.json \
  --html-out /Volumes/OWC_8TB/gpr_work/artifacts/<candidate_smoke_gate>/index.html \
  --require-pass
```

If this fails, the blocker receipt must classify the failure as one of:
source/degradation mismatch, objective/gating failure, model capacity,
camera-conditioning gap, timing/memory infeasibility, or noise-policy mismatch.
Then start the next candidate from that classification, not from visual taste.
