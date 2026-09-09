# Mission 1 Codec/CNN Risk Boundary - 2026-06-18

This note defines the boundary between codec correctness work and CNN/SR
recovery work for the Mission 1 native 12MP path.

## Current Baseline

- Registered 12MP codec profile: `mission1_native12_t233`.
- Registered 8K SR profile:
  `mission1_native12_8k_sr_all24_holdout5_v1`.
- Registered offline-review pipeline candidate:
  `codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_all24_holdout5_v1+demosaic=sips_via_gpr_tools`.
- T236 is quality/storage-boundary evidence, not the registered production
  codec.
- T356/T468 are rejected speed-tier evidence until their raw quality failures
  are resolved.

## Risk Classes

| issue class | production risk | CNN/SR policy |
|---|---|---|
| Entropy symbol inefficiency | Larger payloads and lower FPS, but decoded Bayer remains correct. | CNN not required; solve in entropy coding or scheduling. |
| Frequency/count overflow | Invalid stream state or decoder-specific behavior. | CNN cannot waive this. Add codec invariants and roundtrip tests. |
| Magnitude or symbol range clipping | Raw pixel corruption, jagged Bayer, or irreversible edge loss. | CNN cannot waive this. The codec path is not production-valid. |
| Controlled quantization or threshold loss | Valid decoded Bayer with intentional quality loss. | CNN/SR may be used if full-image worst-row metrics and visual review pass. |
| Rejected speed-tier signal loss | Smaller/faster payload but visibly degraded Bayer. | Research only; do not register as production to recover with CNN later. |

## Production Rule

The codec must decode to valid Bayer before any CNN is considered. CNN/SR is
allowed only as visual recovery or upscaling for an already valid decoded raw
path. It is not allowed to hide invalid bitstreams, clipped coefficients,
broken symbol ranges, wrong metadata, or Bayer images that fail the raw quality
gate.

## Current Interpretation

The registered T233 codec path remains the conservative capture baseline
because it has passing quality dashboards and target-platform timing receipts
above the accepted 20 fps Pi stand-in floor. The SR registry entries are
offline/review candidates, not live camera paths. The T233 guardrail-light
checkpoint is registered only in that offline 12MP-to-8K scope because it keeps
the production capture codec boundary, passed the Mission and regenerated Z8
guardrails for the earlier frozen SR pair/codec artifact contract, and has
runtime plus q3 packaging receipts. It is not yet production-closed for the
current corrected codec/source contract. The harder focused T233 checkpoint
improves the Mission hard rows but is held for registry review because it does
not clear the regenerated Z8 guardrail. A guarded focus continuation was also
rejected because it stayed below guardrail-light on Mission and Z8 worst-row
metrics. T236 is
useful because it narrows the strict-24 gap to a target-platform handoff margin,
but its SR variants currently regress worst-row broad-holdout detail metrics.
A mixed Mission+Z8 guarded probe from guardrail-light was run next; it found no
promotion candidate. A first partial probe was rejected for incomplete baseline
holdout coverage. A follow-up full-coverage evaluation across all 8 Mission
frames and all 5 regenerated Z8 guardrail frames confirmed the failure mode:
the step-200 checkpoint slightly improved the Mission worst-row RMSE floor but
missed the Mission median floor and regressed Z8 RMSE/PSNR, while the best tile
checkpoint preserved Z8 slightly but still missed the Mission RMSE floors.
A smaller resblock pixel-shuffle architecture was then tested as a guarded
full-coverage probe. Random residual initialization was rejected because it
damaged the output before training recovered. The trainer now zero-initializes
new residual SR heads so from-scratch candidates start as the bilinear baseline.
The corrected zero-init resblock probe is faster than the registered offline
SR checkpoint and learns a small positive lift over bilinear, but it is still
far below guardrail-light on Mission and regenerated Z8 floors, so it is also
rejected and not registered. A production-sized zero-init resblock follow-up
(`w48`, depth 6, Charbonnier, 800 steps) confirmed the same boundary at full
coverage: the best candidate improved over bilinear only modestly (Mission
RMSE median +4.84%, regenerated Z8 RMSE median +2.18%) while remaining far
below guardrail-light (Mission RMSE median -44.97 points, Mission RMSE floor
-35.34 points, regenerated Z8 RMSE floor -23.70 points versus guardrail-light).
It was also slower than guardrail-light on the offline SR path, so it is
rejected and not registered.
A weight-space interpolation probe between guardrail-light and focus-hardrows
was also rejected. Alpha 0.25, 0.50, and 0.75 candidates were evaluated on
the full 8-image Mission broad holdout and 5-image regenerated Z8 guardrail.
They nudged the Mission worst-row RMSE floor up by 0.10 to 0.26 points, but
each regressed Mission median RMSE and the Z8 guardrail, so guardrail-light
remains the registered offline SR candidate.

Inline jANS frequency accounting now uses the existing saturating increment
helper instead of raw `uint16_t` increments. The T236 GP017602 hard-frame
receipt records a smaller payload and valid `.gvid`, but still fails strict
24 fps. This keeps the remaining timing gap in the codec/handoff bucket, not
the CNN/SR bucket. A follow-up stripe retune on the accepted saturation binary
found `FUSED_STRIPE_ROWS=264` fastest in the 120-frame sweep, but it still
missed strict 24 at 44.005 ms median and 22.29 fps wall, so stripe shape is
not the closure path. A byte-identical jANS tokenizer lane-extract probe was
also rejected: replacing scalar reloads after the NEON nonzero check with
`vgetq_lane_s32` preserved the short `.gvid` hash but regressed the 120-frame
target A/B by 0.64 ms median on average. A later byte-identical FLL2 LL
bitwriter change is accepted as a timing improvement: the 240-frame same-session
comparison improves from 43.64 ms median / 21.80 fps wall to 42.77 ms median /
23.11 fps wall, narrowing but not closing the strict-24 gap.

The inline jANS scalar-tail path now has a focused regression test:
`source/app/test_jans_inline_tail_flush.c`. It covers high-magnitude residuals
with more than one pending byte at finalization across single-blob,
immediate-stripe, and deferred-stripe modes. The Pi sanity receipt at
`/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_tail_flush_sanity_GP017602_30f_20260618/summary.json`
accepts the change as a correctness fix: the `.gvid` remains valid with zero
drops and storage pass, payload rises only 0.048 KiB/frame, and strict 24 fps
is still open.

## Current SR Frontier

The registered offline 12MP-to-8K SR path remains useful for review outputs
under its earlier frozen artifact contract, and the later candidates are
bounded by Mission-vs-Z8 tradeoffs:

| candidate | Mission RMSE min / median | Mission PSNR14 min | fps with write median | status |
|---|---:|---:|---:|---|
| `mission1_native12_8k_sr_all24_holdout5_v1` | 34.00% / 47.63% | 47.88 dB | 2.65 | registered offline baseline |
| `mission1_native12_8k_sr_focus_hardrows_2500_v1` | 37.69% / 49.24% | 47.90 dB | 2.61 | review candidate; improves Mission hard rows but held behind guardrail review |
| `mission1_native12_8k_sr_guardrail_light_w15_800_v1` | 37.38% / 49.80% | 48.02 dB | 2.63 | registered offline candidate with refreshed packaging |
| `mission1_native12_t236_gw08` | 26.97% / 54.91% | 46.94 dB | 2.54 | rejected: worst-row regression |

The next CNN training pass should not start from a blank architecture unless it
has an explicit reason. The current best launch point is the T233 focused or
guardrail-light checkpoint, with a promotion rule that requires both:

- Mission broad-holdout worst-row and median floors improve over the registered
  candidate.
- Regenerated Z8 guardrail RMSE/PSNR floors do not regress.

If a candidate cannot satisfy both, keep it as a leaf experiment and do not
change the production registry.

A 2026-06-18 refresh against the current corrected codec/source contract found
that the existing guardrail-light checkpoint is not production-closed for the
current path. The old SR lows are bit-exact to the legacy OpenCV
GaussianBlur(sigma=0.85) plus INTER_AREA same-CFA-plane downsampler. The
refreshed production pair builder now uses `tools/bayer_resample.py`, so clean
12MP lows changed before codec encoding. Recompressing the old legacy lows
through the current corrected codec recovered `GP017349` to the RMSE floor but
`GP017346` still missed MAE and gradient floors. Treat this as a
training/eval-generator contract drift plus current-codec mismatch, not proof
that the jANS residual-tail fix alone broke SR quality. The next promotable SR
pass must freeze one pair generator contract, rebuild Mission+Z8 pairs with the
exact current codec binary/profile, and retrain or fine-tune before registry
promotion.

That follow-up current-contract rebuild was started the same day. The new
Mission42 and Z8-all24 pair corpora now record the shared CFA resampler hash,
coeff-tool hash, and sanitized codec env contract. Fine-tunes from
guardrail-light improved the current-codec Mission hard rows, and hardfocus
128-tile training pushed `GP017346` to 63.43% RMSE improvement and `GP017349`
to 29.95% RMSE improvement, but it overfit the Mission hard frames and regressed
the regenerated Z8 guardrail to roughly 39% RMSE / 5% MAE / 1% gradient floors.
A balanced 128-tile follow-up trained on Mission hard frames plus Z8 train19
recovered Z8 holdout RMSE to roughly 45% improvement and PSNR14 to roughly
54 dB, but it still missed Mission full-frame detail floors. `GP017346`
remained below the MAE and gradient floors, `GP017349` remained just below the
30% RMSE floor, and `GP017347`/`GP017600` remained below the broad-holdout
gradient floor. A residual-scale sweep from that checkpoint was also rejected:
larger residual scales reduced Mission MAE/gradient and eventually damaged
both Mission and Z8 metrics, so the blocker is not a simple residual amplitude
knob. No current-contract SR checkpoint is promoted from this pass. The
remaining SR blocker is full-image detail/gradient placement under the current
model/loss/data-balance contract, not invalid codec output.

A hard full-frame tile-mining pass was then added to target the actual Mission
dashboard failures. The miner scores deinterleaved CFA-plane tiles by
model-vs-target gradient error weighted by target detail, and the pair builder
can now consume those tiles through a manifest. A first hard4-only finetune
from the balanced checkpoint improved `GP017347` and `GP017600` detail metrics
and slightly improved `GP017346`, but it regressed `GP017349` and the Z8
holdout. It is rejected and not registered. The next SR experiment should merge
hard-mined tiles with the balanced Mission42+Z8 corpus and select checkpoints
with full-frame Mission+Z8 guardrails rather than hard-only tile validation.

That mixed hard-tile plus balanced-corpus run is the best current-contract
candidate from this sequence, but it is also rejected. The step-1600 snapshot
improves Z8 guardrail RMSE versus the balanced checkpoint and gets `GP017347`
over the gradient floor, while avoiding the hard-only Z8 collapse. It still
misses production: `GP017346` remains below MAE/gradient floors, `GP017349`
remains just below the 30% RMSE floor, and `GP017600` remains below the
gradient floor. A stronger phase-2 detail-loss continuation regressed the
tradeoff. The next pass needs gate-aligned full-frame checkpoint selection and
possibly a targeted edge/detail residual path; tile validation is no longer a
reliable selection proxy for these failures.

## Evidence Pointers

- Current 100% review dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_current_review_100pct_dashboard_20260618/index.html`
- SR frontier summary:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_sr_frontier_summary_20260618/summary.json`
- Registered T233 8K SR broad dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_sr_all24_holdout8_fullframe_20260618/index.html`
- Focused T233 hard-row SR dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_sr_t233_focus_hardrows_fullframe_holdout8_20260618/index.html`
- Rejected guarded-focus continuation:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_t233_guarded_focus_w8_600_decision_20260618/decision.json`
- Rejected mixed Mission+Z8 guarded probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_guarded_mixed_probe_20260618/guarded_experiment_summary.json`
- Full-coverage rejected mixed Mission+Z8 guarded probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_guarded_mixed_probe_20260618/guarded_experiment_fullcoverage_summary.json`
- Rejected random-start resblock SR guarded probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_resblock_probe_20260618/guarded_experiment_summary.json`
- Rejected zero-init resblock SR guarded probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_resblock_zeroinit_probe_20260618/guarded_experiment_summary.json`
- Rejected production-sized zero-init resblock SR guarded probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_resblock_zeroinit_w48_800_probe_20260618/guarded_experiment_summary.json`
- Rejected light-focus checkpoint interpolation probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_interp_light_focus_probe_20260618/summary.json`
- T236 gradient-weight SR dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_sr_t236_gw08_holdout8_fullframe_20260618/index.html`
- Current-codec SR refresh probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_tailflush_refresh_GP017346_GP017349_20260618/summary.json`
- Current-contract SR retrain summary:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_current_contract_summary_20260618/summary.json`
- Balanced current-contract SR dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_current_contract_balanced128_train_20260618/mission_key8_fullframe/index.html`
- Balanced current-contract Z8 guardrail dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_current_contract_balanced128_train_20260618/z8_holdout5_fullframe/index.html`
- Rejected residual-scale sweep:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_current_contract_residual_scale_probe_20260618`
- Rejected hard-tile mining finetune:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hard_tile_mining_20260618/summary.json`
- Rejected mixed hard-tile plus balanced-corpus finetune:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_mixed_hard_balanced_20260618/summary.json`
- Rejected post-saturation stripe sweep:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/summary.json`
- Rejected jANS lane-extract tokenizer probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/summary.json`
- Accepted LL bitwriter32 timing probe:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_probe_GP017602_20260618/summary.json`
