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
| current scoreboard | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_frequency_pyramid_20260702/scoreboard.json` | 113 runtime-safe receipts, 0 promotable receipts, best runtime-safe row remains 4.03% MAE / 3.75% RMSE versus the 15% / 15% floor. |

## Next Unambiguous Step

Build a new Premium still/SR candidate preflight for a **no-op or
benefit-gated residual model**. The model must be candidate-only at runtime and
must learn when to leave low-error Z8/X2D tiles unchanged before it learns a
detail residual.

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

python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py \
  <exact X2D smoke command from candidate_preflight.json>

python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py \
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
