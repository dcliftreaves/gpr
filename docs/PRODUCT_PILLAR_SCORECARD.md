# Product Pillar Scorecard

The product pillar scorecard is the top-level audit view for the four large
efforts currently driving the repo:

1. best RAW stills for 50 MP / 100 MP cameras,
2. GoPro / Mission 1 RAW video MVP,
3. premium spend-time-for-quality still/SR,
4. RAW video cleanup and reconstruction, with PSF/blur work tracked as optional
   next-generation research.

It is intentionally stricter than the README. The README can sell the project
clearly; this scorecard says what is proven, what is only proxy-proven, and
what still blocks a production claim.

Build it with:

```bash
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp \
  python3 tools/build_product_pillar_scorecard.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_ship_boundary_20260701
```

Current generated dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_ship_boundary_20260701/index.html`

Companion production burn-down dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/product_burndown_100_percent_queue_20260702/index.html`

The burn-down is the action view over the same machine-readable capture
requirements: it carries the requirement IDs, statuses, and validation commands
from [`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json),
then separates hardware integration, sample-acquisition, model-promotion, and
optional research requirement IDs. The generated dashboard also carries a
separate Research Parking Lot for PSF/SR follow-ups; those actions are retained
for traceability but excluded from production action counts and readiness percentages.
That distinction matters because the one Mission 1 camera-role
closure, real fixture/darkframe gaps, premium model-promotion gaps, and optional
PSF research are different kinds of evidence, not regressions of the locked
still, 4K cleanup, 8K SR, or Pi stand-in paths.
The committed sample/receipt contract is
[`PRODUCTION_CAPTURE_REQUIREMENTS.md`](PRODUCTION_CAPTURE_REQUIREMENTS.md) and
[`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json).

## Score Semantics

The percentages are production-readiness burn-down estimates. They are not
image-quality metrics and they are not regression signals for locked artifacts.
A locked path regresses only when its own committed gate, receipt, hash, or CI
guard fails. This matters because the approved 4K cleanup, offline 8K SR,
production STILL tiers, and Pi-stand-in raw-video/preview receipts can remain
locked while the overall readiness score stays below 100% because hardware,
fixture, noise-sidecar, or promotion evidence is still missing. PSF evidence is
kept as optional research for a future replacement, not a blocker for shipping
the approved current raw-video SR workflow.

The denominator is the shippable production suite: raw stills, raw video MVP,
premium still/SR, and approved raw-video reconstruction. Use
[`PRODUCT_LOCK_LEDGER.md`](PRODUCT_LOCK_LEDGER.md) to decide whether an
approved artifact regressed; use this scorecard and the burn-down dashboard to
decide what production evidence is still missing.

The generated scorecard now carries the exact lock-ledger path names and open
production gate names for each pillar. `tools/test/check_product_lock_ledger.py`
keeps the Markdown ledger, generated scorecard contract, and CI view from
drifting apart.

For raw-video SR specifically, the approved 4K cleanup and 8K reconstruction
path is frozen for release. It is reopened only by a committed gate/receipt/hash
or manual-review failure, or by a replacement that already beats the locked
baseline and emits the same `.gvid`, editable raw, ProRes, dashboard, and
receipt set. PSF-conditioned work remains optional research until then.

The generated scorecard enforces that boundary in structure: raw-video
production evidence lives under `evidence`, while PSF/blur references live under
`research_evidence`. Tests fail if PSF lineage drifts back into the locked
raw-video artifacts or the done/proven release evidence. That is the stop rule
against endless SR iteration: shipping work is judged against locked receipts,
and new SR research can only replace the release path after it beats those
receipts first.

Current interpretation:

| pillar | current score | production reading |
|---|---:|---|
| Best RAW stills | 92% | Strong for the current tested Bayer surface, now including a real X2D 100MP visual roundtrip audit, real RGGB/GBRG/GRBG/BGGR fixture coverage, and explicit camera-noise coverage; Mission/iPhone darkframe sidecars are still open. |
| GoPro RAW video MVP | 80% | Pi 5 stand-in, handoff package, and GoPro intake audit are strong; real Mission 1 sensor/DMA/storage/display receipts are still required. |
| Premium still/SR | 60% | The expanded 13-scene / 351-row target set now has complete raw-CFA features, the deduplicated raw-supervision NPZ collapses it to 117 unique scene/crop raw-domain rows with zero raw conflicts, and RCAB/NAF/U-Net teacher receipts run on that target. Z8 is mildly positive, but X2D remains far below promotion: the raw-target distribution audit shows the hard X2D holdout has **3.45x** the X2D train-median target energy with **6/9** rows above train p90, the RCAB smoke is only **0.069%** median recovery on an 8-row X2D holdout, the scaled RCAB pass is only **0.034%** on a 24-row X2D holdout, the all-X2D-holdout NAF-style pass is **-0.059%** on a 24-row X2D holdout with a heavily regressed train split, the corrected X2D-scene NAF pass reaches only **0.107%** median MAE recovery and negative RMSE recovery, hard SNR filtering hurts versus unfiltered X2D-only **0.149%**, broad SNR weighting also hurts, and noise-floor-only downweighting only nudges the X2D-scene U-Net branch to **0.153%**. Scalar target-energy weighting regresses to **0.118%** or **0.133%**, Fourier/band-loss shaping regresses to **-0.386%** or **-0.139%**, candidate-HF target scaling reaches only **0.052%** or **-0.137%**, direct source-HF target prediction regresses to **-241.62%** without stored HF and **-862.69%** with stored HF, frame-context scalar conditioning reaches only **0.001%**, matched global-context trails at **0.149%**, fixed non-box PSF/CFA NAF trails at **0.130%**, stored candidate-HF regresses to **0.110%**, broader pyramid context trails at **0.131%**, same-scene candidate-signal and frequency-filter probes regress, nearest-neighbor retrieval regresses the hard X2D holdout, and candidate-only local/full-crop/global-context/masked-context statistics remain insufficient. The clean-signal target pass now removes calibrated noise-floor residuals and keeps 81 retained-signal rows, but the X2D candidate-only learnability audit is still **-4.325%** median MAE recovery and the bounded clean-signal U-Net is **-0.025%** on the X2D holdout. The broader t64 clean-source pair set now covers 4,800 tiles across Mission 1, Z8, and X2D, and the new Restormer-style trainer is runtime-safe, but it is not promotable: X2D smoke is only **+0.013%** median MAE recovery, Z8 smoke is **-0.072%**, and the longer Z8 run overfits train while regressing held-out MAE to **-5.06%**. The raw-target SNR/distribution/clean-target audits are useful, but binary row removal, simple row weighting, stored-HF, Fourier/band scalar loss shaping, candidate-side scalar output scaling, source-HF target replacement, frame-stat concatenation, fixed global PSF conditioning, clean-target gating alone, same-color pair training, and simple capacity increases are not enough; the next pass needs a materially different clean-source or CFA-aware teacher/data objective with camera conditioning, calibrated noise/degradation synthesis, row-level PSF conditioning, and learned multiscale texture priors. |
| RAW video reconstruction improvement | 100% | Current 4K cleanup and 8K SR baselines are approved for the offline/post workflow, including continuous 8K no-CNN versus CNN ProRes review media for whole-scene A/B, `.gvid` decode-to-SR, editable DNG/GPR packaging, 2K/8K ProRes review, Mission metadata-transplant receipts, 42-frame full-sequence `.gvid` packaging, objective visual-review, manual visual signoff, and release/registry receipts. The retained research lineage includes `psf_gradient_focus_from_detail_s400_fw6_gw12_s300` and `mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1`. Controlled high/low PSF pairs, native kernel measurement, and PSF-conditioned replacement training are preserved as optional research evidence, but no longer block shipping the approved current raw-video SR workflow. |

The current real X2D 100MP still audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html`.
It records a 11,664 x 8,750 DNG to GPR to DNG roundtrip, 100 percent crop
panels, and 49.21 dB full-image raw Bayer PSNR.

The canonical real Bayer phase discovery lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html`.
It scans canonical plus broader local Mission 1/Z8/X2D/iPhone DNG pools and
finds 74 normal 2x2 Bayer DNGs: 70 RGGB and 4 Mission 1 GBRG.

The current camera-noise coverage audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/index.html`.
It records six validated darkframe sidecars: X2D at ISO 64, 200, 800, 3200,
and 12800, plus Z8 at ISO 500. Mission 1 and iPhone have real fixtures but no
production-ready darkframe sidecars yet, so nonzero noise removal/addback is not
promoted for those cameras.

The raw-stills noise sidecar readiness receipt lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_stills_noise_sidecar_readiness_20260701/index.html`.
It rolls the coverage audit, runtime policy, darkframe candidate audit, fixture
gap plan, and capture request into the current product verdict: X2D and Z8 are
enabled for calibrated nonzero noise addback, while Mission 1 and iPhone remain
metadata-conditioning-only. The receipt records the two open requirement IDs:
`mission1_darkframe_stack` and `iphone_cfa_darkframe_stack`.

The current full-manifest Mission/iPhone darkframe candidate audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/index.html`.
It parses 1,997 of 2,000 bounded manifest rows, finds 59 dark-like frames, and
identifies four iPhone same-ISO candidate stacks. It still keeps
`production_sidecar_ready=false`
because candidate-discovery frames need confirmed no-scene-signal provenance
before they can become noise sidecars. Mission 1 remains the tighter sample gap:
the lowest-lift ISO232 RGGB group has two candidates and needs two more matching
frames.

The broader real-photo sample lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_realphotos_sample_20260630/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_realphotos_sample_20260630/index.html`.
It adds real-photo iPhone RGGB evidence and finds one iPhone dark-looking
candidate stack, but the boosted contact sheet shows scene content in part of
that group. The audit therefore keeps `production_sidecar_ready=false`; Mission
1/iPhone production noise sidecars remain open.

The targeted GoPro/Mission DNG/GPR fixture scan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/index.html`.
It parses 3,000 local DNG/GPR files as normal Bayer: 2,892 GBRG and 108 RGGB.
The broad old-photo scan at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_photos_20260701/index.html`
adds 818 parsed normal Bayer rows: 618 RGGB, 120 GRBG, and 80 BGGR. Combined
with the GoPro/Mission scan, real RGGB/GBRG/GRBG/BGGR coverage is closed for
the stills path. The targeted Mission DNG darkframe scan at
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_targeted_dng_20260630/index.html`
finds 9 dark-like Mission frames, but no same-ISO four-frame production stack.

The bounded source-root Bayer phase scan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_source_roots_20260630/index.html`.
It uses per-root limits and exiftool timeouts to avoid broad-tree stalls, sees
1,279 files across source roots, and parses 710 normal Bayer rows: 460 RGGB and
250 GBRG. The later broad old-photo scan closes the missing GRBG/BGGR evidence.

The current stills fixture gap plan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/index.html`.
It consolidates the phase/noise receipts into the concrete capture checklist:
Mission 1 and iPhone darkframe stacks, including two additional matching Mission
ISO232 RGGB frames and provenance validation for the 27-frame iPhone ISO1250
RGGB dark-like candidate stack.

The raw-stills capture request lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_strict_provenance_20260701/index.html`.
It converts that closure list into handoff-ready sample requests, validation
commands, and promotion criteria.
The same raw-stills blockers are pinned in the committed production capture
requirements as `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack`.

The current GoPro Mission 1 intake audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html`.
It verifies the portable firmware handoff bundle, required docs, 4096 x 3072
`.gvid` sample, quick-validation dry run, and stand-in encode/preview receipts.
It remains `camera_production_ready=false` until real Mission 1 sensor/DMA,
storage, and rear-display receipts replace the stand-in evidence.
That required camera-side proof is pinned as
`mission1_camera_role_receipts` in the committed production capture
requirements.

The current raw-video PSF/SR readiness audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630/index.html`.
It records that the current 4K cleanup and 8K SR baselines are approved for
their existing offline roles, but the PSF replacement is not production-ready
without native camera/display PSF evidence and a PSF-conditioned model gate.

The current Z8 standalone continuous-scene 8K no-CNN versus CNN review lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/`.
It contains separate 8280 x 5520 ProRes videos for the no-CNN Z8 baseline and
the retained 4K cleanup CNN Bayer plus approved 8K SR CNN path, with 24 matched
frames at 20 fps. This is the whole-video review evidence for the approved
baseline, not a dashboard, contact sheet, side-by-side review, or crop montage.

The current Mission 1 broad 8K no-CNN versus CNN review lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/`.
It contains separate 8192 x 6144 ProRes videos for 42 Mission 1 raw-video
frames at 20 fps: a no-CNN 4096 x 3072 raw Bayer baseline display-upscaled
with Lanczos, and the approved 4K cleanup plus 8K SR CNN raw Bayer render.
This is the broad whole-video Mission 1 review pair; it is not the side-by-side
movie in that folder.

The stricter Mission 1 sequential-scene 8K no-CNN versus CNN review lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/`.
It contains separate 8192 x 6144 ProRes videos for 12 sequential Mission 1
frames at 20 fps: a no-CNN 4096 x 3072 raw Bayer baseline display-upscaled
with Lanczos, and the approved 4K cleanup plus 8K SR CNN raw Bayer render.

The current Mission 1 native high/low PSF candidate inventory lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630/index.html`.
It indexes near-time 8192 x 6144 and 4096 x 3072 Mission 1 captures as inputs
for the measured PSF pass. It is not a measured PSF receipt yet; alignment,
edge/texture mining, and a PSF-conditioned gate remain optional research.

The current Mission 1 native PSF measurement plan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630/index.html`.
It selects the best decoded native high/low pairs and defines the scene-vetting,
alignment, edge/texture mining, kernel-fitting, and promotion gates required
before a future PSF-conditioned model can replace the approved 4K/8K baselines.

The current Mission 1 native PSF measurement run lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/index.html`.
It executed the plan on the selected near-time pairs. Two of three pairs passed
scene/alignment vetting and provided 1,409 sharp-edge plus 1,381 texture-field
tiles, but the combined kernel was unstable and is not ready for model
conditioning.

The current Mission 1 native PSF kernel-stability audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_kernel_stability_audit_20260630/index.html`.
It records that the blocker is kernel disagreement, not just one missing pair:
2 accepted pairs, max normalized-weight std 0.809 against a 0.10 gate, one
accepted pair with invalid negative weights, and one low-correlation diagnostic
pair. This kernel must not condition a replacement model.

The current Mission 1 native PSF corpus audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_corpus_audit_20260630/index.html`.
It hashes all four current near-time candidate pairs and records that zero are
strict controlled pairs: ISO/settings are not fixed enough, fixed
WB/lens/stabilization/sharpening metadata is absent, no negative controls are
marked, the existing measurement accepted only two pairs, and the kernel is
unstable. This proves the local corpus cannot close the PSF replacement
research gap without new or newly located controlled captures for a future
PSF-conditioned replacement.

The deterministic known-kernel PSF validation lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_known_kernel_validation_20260701/index.html`.
It recovers the non-box `[0.52, 0.23, 0.17, 0.08]` same-color 2x Bayer kernel
within **1.1e-8** normalized-weight RMSE and rejects the mismatched negative
control with about **9064** RMSE on the 14-bit scale. This strengthens the
measurement-tooling evidence only; it does not close the controlled native
Mission 1 PSF replacement research gap.
It does not block the approved current 4K cleanup and 8K reconstruction
workflow.

The raw-video PSF controlled capture request lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_capture_request_20260630/index.html`.
It is the handoff for closing the measurement blocker: locked same-scene
8192 x 6144 and 4096 x 3072 Bayer pair stacks, source GPR/DNG hashes, decoded
little-endian uint16 Bayer hashes, exact dimensions and byte counts,
extraction/settings/measurement receipt hashes, fixed
ISO/exposure/WB/lens/sharpening settings, plus negative controls with explicit
rejection reasons, with the exact validation commands required to promote a
stable native PSF kernel.
That controlled-pair request is pinned as optional research under
`controlled_mission1_psf_pairs` in the committed production capture
requirements.

The current raw-video SR/detail candidate scoreboard lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_sr_candidate_scoreboard_psf_detail_20260701/index.html`.
It indexes 90 Mission/Z8 decision receipts and finds zero current-scale
promotion rows under the Mission42 plus Z8 all24 coverage rule. One row is
PSF-detail-ready and PSF-detail-OK: the current metric-bearing candidate
improves median same-cell detail by **2.004** points on Mission42 and
**0.302** points on Z8. It still does not promote because `mission_ok=false`
from the Mission gradient-floor regression.

The Mission gradient/detail blocker audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gradient_detail_blocker_audit_20260701/index.html`.
It narrows the current failure to five Mission rows that regress both gradient
and same-cell Bayer detail: `GP017346`, `GP017600`, `GP017347`, `GP017348`,
and `GP017359`. The next candidate should target those rows without giving up
the current positive Mission/Z8 median same-cell detail deltas.

The current raw-video PSF detail-metric audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_detail_metric_audit_rerun_20260701/index.html`.
The first audit confirmed that Mission42 and Z8 all24 baseline/candidate
summaries were available but missing same-cell Bayer fine-detail metrics. The
rerun closes that metric blocker: all four selected summaries now include
`same_cell_detail_mae_improvement_pct`,
`same_cell_fine_detail_mae_improvement_pct`, and
`cfa_plane_detail_mae_improvement_pct`. The current candidate improves median
same-cell detail from **26.091%** to **28.095%** on Mission42 and from
**3.214%** to **3.516%** on Z8. That is still diagnostic evidence, not a
PSF-conditioned replacement claim.

The current raw-video PSF next-experiment contract lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_next_experiment_contract_20260701/index.html`.
It makes modeled-PSF same-cell fine-detail ablations the recommended local
track, while explicitly forbidding production promotion from the current
unstable native Mission 1 kernel or partial historical SR rows.

The current premium still-SR experiment scoreboard lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_teacher_first_smoke_20260702/index.html`.
It now ranks 97 runtime-safe rendered-HF, raw-CFA residual, clean-signal, and
clean-source pair training receipts and records zero promotable rows. The best
older runtime-safe row reaches 4.03 percent held-out MAE recovery and 3.75
percent held-out RMSE recovery against the 15 percent / 15 percent promotion
threshold, while the newest clean-source Restormer pair rows remain far below
promotion. The degradation/objective ablation with Charbonnier, Laplacian, RAW
noise, gain jitter, and blur reaches only 0.0048 percent X2D MAE recovery and
regresses Z8 by -0.3973 percent MAE. Both branches are diagnostic rather than
production-ready.
The full 12k-step X2D scene-holdout window-attention teacher run is now one of
those diagnostic rows: it trains slightly positive at 0.804 percent median raw
MAE recovery, but the 9-row X2D scene holdout is negative at -0.030 percent MAE
and -0.098 percent RMSE after 31,155.66 seconds. That narrows the blocker: the
current full-crop PSF/CFA window-attention objective is not the missing
promotion lever.

The premium still-SR blocker audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_blocker_audit_20260630/index.html`.
It turns the current diagnostic failure into next-experiment requirements:
keep the expanded target coverage fixed, replace the weak rendered-context
learner with a stronger raw/CFA-aware or otherwise larger-context texture
model, keep calibrated noise/signal cleaning in the feature contract, and run a
full still/editor-latitude promotion gate.

The current premium still-SR signal-objective gate lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_signal_objective_gate_20260701/index.html`.
It superseded the earlier transformer-teacher contract and led to the
clean-signal target/U-Net rejection. The first audits are negative on the
legacy raw residual objective: X2D is -1.238 percent median MAE recovery and Z8
is -2.632 percent. The bounded clean-signal U-Net then still regressed the X2D
holdout at -0.025 percent median MAE recovery, so the current next pass moves
off residual-cleaning and onto self-supervised clean-source RAW SR.
The current next-experiment contract lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702/index.html`.
It requires low/high same-color Bayer pairs from real high-quality 50 MP /
100 MP sources, a clean-source teacher that beats same-color interpolation on
held-out X2D/Z8 images, and candidate-only distillation only after that teacher
gate passes.
The first dedicated clean-source pair model smoke now lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_source_pair_model_smoke_20260702/index.html`.
It proves the new `tools/cnn/train_premium_still_sr_clean_source_pairs.py`
trainer/evaluator path runs, but it is diagnostic-only: with `x2d_100mp_dng`
held out, median MAE gain is -0.087 percent and median RMSE gain is -0.049
percent versus nearest same-color 2x.
The broader routed clean-source pair set now lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702/index.html`.
It covers 75 images and 1200 tiles across Mission 1, Z8, and X2D with a
nearest same-color 2x median MAE of 12.40 and RMSE of 23.10. The matching
1500-step X2D and Z8 holdout model receipts are both rejection evidence:
training improves by 14.54 percent and 12.86 percent median MAE respectively,
but held-out X2D regresses by -5.07 percent and held-out Z8 regresses by -4.82
percent median MAE.
A bounded NAF-like residual pixelshuffle plus gradient/detail-loss probe is
also rejected on those routed clean-source pairs: the 500-step X2D holdout is
about -0.35 percent median MAE and -0.36 percent RMSE versus interpolation,
and the matched Z8 holdout regresses by about -10.09 percent median MAE.
The expanded t64 clean-source pair audit now covers 4,800 tiles across Mission
1, Z8, and X2D with a nearest same-color 2x median MAE of 12.68 and RMSE of
23.96. The first `restormer_pixelshuffle` smoke receipts remain runtime-safe
but not promotable: X2D is only +0.013 percent median MAE recovery, Z8 is
-0.072 percent, and a longer Z8 run improves train MAE by 23.13 percent while
regressing held-out Z8 MAE to -5.06 percent. That rules out more steps on the
same Restormer/same-color pair objective as the next primary move.
The premium still-SR noise-policy gate now lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_policy_gate_20260702/index.html`.
It confirms the clean-signal target has 117/117 calibrated noise sidecars and
forbids source raw, REF/JPEG content, and exact source-noise addback at render
time, but it keeps the current clean-signal U-Net, routed pixelshuffle, and
routed NAF/detail model receipts blocked because none clear the 15 percent /
15 percent holdout MAE/RMSE floors.
The rejected relaunch guard now lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rejected_relaunch_guard_20260702/index.html`.
It blocks `teacher_first_fullframe_raw_sr_smoke_v1` before a long run because
that candidate id and the X2D/Z8 smoke output directories are already tied to
committed rejection receipts. The next local Gate A move must use a materially
different candidate id, evidence path, and X2D/Z8 smoke plan.
The superseded transformer-teacher contract remains archived at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_next_experiment_contract_transformer_teacher_20260701/index.html`.
The trainer now has PSF/kernel-conditioned `_psf` feature modes that can consume
row metadata, explicit four-weight kernels, or a `gpr.bayer_resize_psf_receipt.v1`
without adding source/REF content at runtime. That opens the intended
PSF/camera-aware experiment path, but it is not a promoted still-SR model. The
trainer now also has `model_arch=window_attention_teacher`, a shifted-window
attention plus overlap-convolution raw-CFA teacher path. Its first bounded
real-target smoke receipt lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/index.html`
and proves executable PSF+CFA-conditioned path coverage on the canonical
117-row deduplicated target without REF/source/JPEG runtime inputs. It is not a
promotion run: the bounded 2-row X2D holdout median raw MAE recovery is about
0.142 percent, far below the 15 percent promotion gate.
The trainer now also exposes explicit overlapped-tile final evaluation and seam
diagnostics through `--eval-overlap` and `--seam-check-width`. The first
real-target overlap smoke receipt lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/index.html`.
It uses the same canonical deduplicated target with 64 px overlap and 8 px seam
bands. The bounded X2D holdout median raw MAE recovery is about 0.448 percent,
with overlap-vs-plain median MAE around 1.65e-5 and seam-band delta around
7.04e-5. This is validation machinery and seam-risk evidence, not promotion.

The first two X2D scene-holdout PSF probes are now recorded: a local noise-floor
U-Net with near-box PSF planes reaches about 0.106 percent median exact raw MAE
recovery versus the non-PSF 0.153 percent baseline, and a full-crop raw-context
PSF U-Net reaches about 0.064 percent. The current blocker is therefore not
"missing PSF plumbing"; it is missing per-row/per-camera PSF variation or a
stronger teacher/objective. The PSF metadata gap audit at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_psf_metadata_gap_20260701/index.html`
records 117 rows, 13 scenes, inferred 81 X2D and 36 Z8 rows, **0/117** rows
with row-level PSF metadata, **0** unique row kernels, a near-box global PSF,
and `another_psf_cnn_run_justified=false`.
The PSF sidecar contract at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_psf_sidecar_contract_20260701/index.html`
now makes that gap executable for the trainer via `--psf-sidecar`. It is still
blocker evidence rather than promotion evidence: **0/117** rows have
camera-specific PSF assignments, **117/117** rows use the global fallback, all
rows are near-box, and only **1** unique kernel exists.
The final still-SR promotion artifact set is pinned as
`premium_still_sr_promotion_receipts` in the committed production capture
requirements.

The premium still-SR target expansion plan lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_expansion_plan_20260630/index.html`.
It selected six X2D 100MP and four Z8 50MP scenes with validated noise
sidecars, while explicitly deferring Mission 1 until same-camera noise sidecars
exist. The executed expanded build lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/expanded_target_build_receipt.json`;
the merged target contains 13 scenes and 351 rows. The expanded residual band
analysis lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/index.html`
and still shows the residual is fine-band dominated. The first expanded
training passes are intentionally not promoted: the weighted w96
render-context model was unstable, and the conservative w64 model landed near
zero held-out recovery.

The current raw-CFA smoke target and ablation receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_smoke_targets_20260630/2025_10_oct_austin_0626/hf_residual_targets.json`,
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_probe_model_20260630/train_receipt.json`,
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_ablation_rgb_model_20260630/train_receipt.json`.
The current raw-CFA gated architecture receipt lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_gated_probe_w48_1000_20260630/train_receipt.json`.
Together these prove the raw-CFA target/trainer path executes on a real X2D
scene: naive channel concatenation trails the matched RGB ablation, while the
explicit raw-CFA gated probe beats that ablation on +2 EV holdout recovery.
The expanded raw-CFA target rebuild lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/expanded_target_build_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json`.
It records complete raw-CFA feature coverage for all 351 rows / 13 scenes. The
expanded gated holdout receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_z8holdout_w48_1000_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_x2dholdout_w48_1000_20260630/train_receipt.json`.
They beat matched RGB ablations on held-out Z8 and X2D, but the best broad
holdout is still only about 2.92 percent median MAE recovery against the 15
percent promotion threshold.
The first matched dilated raw-CFA gated receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_z8holdout_matched_w48_1000_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_x2dholdout_matched_w48_1000_20260630/train_receipt.json`.
They improve the weak Z8 holdout from 1.04 to about 1.30 percent median MAE
recovery, but trail the X2D gated baseline at 2.86 versus 2.92 percent and
leave severe negative worst rows. That makes the simple dilated gate a useful
diagnostic, not the production path.
The current calibrated noise-clean sweep lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_clean_sweep_x2d_smoke_20260630/index.html`.
It shows the validated ISO 200 X2D noise floor is far below the current HF
residual: render gain 16 changes about 11.93 percent of pixels, but removes
only about 0.24 percent median residual energy. Noise cleaning remains a
guardrail, not the main explanation for the current still-SR blocker.

The current raw-CFA residual audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_audit_20260630/index.html`.
It compares rendered HF supervision against the editable raw target:
source raw minus candidate raw, high-passed without mixing CFA phases. Across
351 rows / 13 scenes, median absolute rendered-to-raw residual correlation is
0.691, median best-phase correlation is 0.922, and median raw-HF residual
magnitude is about 0.346x the rendered HF residual magnitude. That makes a
true same-color raw residual target the next training direction, with rendered
HF/editor-latitude kept as review and promotion metrics.

The current raw-CFA residual target build lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/index.html`.
It emits the trainable NPZ for that direction: `candidate_raw_cfa4`,
`candidate_raw_hf_cfa4`, `raw_hf_residual_cfa4`, `source_raw_hf_cfa4`, and
`render_hf_residual_y`. The NPZ covers the same 351 rows / 13 scenes, is
1.6 GB on the external artifact drive, has SHA-256
`06fa4b4efdc04b946a596d6907f79d590b62c0969716f903f3edcbd6be9a3488`,
and records known crop-local CFA phase for all 351 rows.

The first raw-CFA residual model receipts live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/train_receipt.json`.
They use candidate-only runtime inputs and four-plane raw residual output. The
Z8 scene holdout is mildly positive at about 0.50 percent median raw-residual
MAE recovery, but the X2D scene holdout remains negative at about -0.21
percent, so these receipts narrow the blocker rather than promoting a model.
The follow-up X2D receipts at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/train_receipt.json`,
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/train_receipt.json`,
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/train_receipt.json`,
plus the larger-patch high-residual-weighted probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w48_1600_abs6_patch256_20260630/train_receipt.json`,
the first pooled raw-context probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_context_w40_1800_20260630/train_receipt.json`,
the combined stored-HF plus pooled-context probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextstoredhf_w40_1800_20260630/train_receipt.json`,
the multiscale band-loss objective probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_bandloss_w40_1800_20260630/train_receipt.json`
and the X2D-only train-domain probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_x2donly_w48_2200_20260630/train_receipt.json`,
the camera-balanced sampler at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_camera_balanced_w48_2200_20260630/train_receipt.json`,
the context-padding probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextpad32_w48_1200_20260630/train_receipt.json`,
and the small U-Net/multiscale architecture probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_20260630/train_receipt.json`,
plus the frame-context U-Net probes at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_framectx_unet_w32_1200_20260630/train_receipt.json`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_framectx_unet_w32_1200_20260630/train_receipt.json`
show that wider raw context barely clears zero at about 0.02 percent median
X2D recovery, while stored candidate-HF features and naive one-sigma noise
soft-thresholding do not fix the X2D blocker; the larger-patch/stronger-local
loss pass regresses the hard X2D holdout to about -0.65 percent median MAE
recovery, the pooled-context feature pass remains negative at about -0.33
percent, the combined stored-HF/context feature pass regresses to about -0.43
percent, the band-loss objective pass regresses to about -0.54 percent, the
X2D-only split remains negative at about -0.15 percent, camera-balanced
sampling remains negative at about -0.45 percent, and context padding remains
negative at about -0.16 percent. The small U-Net/multiscale probe is the first
raw-domain branch to move the X2D holdout directionally positive at about
0.10 percent median MAE recovery. A diagnostic early-selection variant saves
the best holdout-probe checkpoint and raises that branch to about 0.13 percent,
but that is still below the best 0.16 percent X2D smoke row and far below
promotion. A same-scene center-crop candidate-signal audit still regresses the
hard X2D center rows by about -3.67 percent median MAE, so low-order candidate
features are not enough even when neighboring crops from the same scene are
available. A per-CFA-plane frequency filter from candidate HF to the raw
residual also regresses that split by about -4.29 percent median MAE, so the
missing detail is not a simple frequency response of candidate HF.
The raw target duplicate audit records 351 rows but only 117 unique scene/crop
raw-domain rows; raw arrays are identical across -2/0/+2 EV while rendered
review residuals vary. Raw-CFA training should now use the deduplicated target
and report unique raw supervision separately from rendered review rows.
The deduplicated raw-supervision NPZ is now materialized at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/index.html`.
It collapses the target to 117 raw rows with zero raw conflicts, preserves
rendered EV review rows in metadata, keeps the trainer-facing array names for
the next teacher pass, and carries 117/117 known CFA phase labels.
The raw-target SNR audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_target_snr_audit_20260701/index.html`.
It compares all 117 deduplicated rows with calibrated camera-noise sidecars:
X2D is mostly signal-dominated, with 59/81 rows above the noise floor and about
5.34x median target RMSE/noise sigma, while Z8 is mostly noise-floor/mixed,
with 28/36 rows at the noise floor and about 0.48x median target RMSE/noise
sigma. The next teacher should therefore use noise-aware row
weighting/filtering or camera-specific target treatment instead of one
unweighted residual objective across both cameras.
The raw-target distribution audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_distribution_audit_20260701/index.html`.
It records the current X2D scene mismatch: the hard
`2024_April_X2D_1742` holdout has 3.45x the X2D train-median target residual
energy and 6 of 9 rows above the train p90, even though it is not above the
training maximum.
The target-energy weighting controls live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/index.html`.
They show scalar row weighting does not close the distribution mismatch:
high-energy emphasis reaches about 0.118 percent and inverse-energy weighting
reaches about 0.133 percent median MAE recovery, both below the 0.153 percent
noise-floor-only U-Net branch.
The Fourier/band-loss objective controls live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/index.html`.
They show direct spatial/Fourier scalar loss shaping regresses the hard X2D
scene holdout to about -0.386 percent and -0.139 percent median MAE recovery.
The candidate-HF target-scale controls live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/index.html`.
They are runtime-safe candidate-only output-normalization controls, but full
strength reaches only about 0.052 percent median MAE recovery and half strength
regresses to about -0.137 percent.
The first deduped-target RCAB teacher smoke run lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/index.html`.
It uses residual channel attention, stored candidate HF, multiscale band loss,
and Fourier magnitude loss. It proves the trainer path, but remains
non-production with only about 0.069 percent median raw MAE recovery on an
8-row X2D holdout.
The scaled deduped-target RCAB teacher run lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/index.html`.
It is a rejection receipt: width 32, depth 6, 700 steps, scene-balanced
sampling, 256 px patches, multiscale band loss, and Fourier magnitude loss
reach only about 0.034 percent median raw MAE recovery on a 24-row X2D holdout,
while train rows regress by about -3.45 percent median.
The simple NAF-style teacher run lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/index.html`.
It is also a rejection receipt: SimpleGate/attention blocks with width 32,
depth 6, 700 steps, scene-balanced sampling, 256 px patches, multiscale band
loss, and Fourier magnitude loss reach about -0.059 percent median raw MAE
recovery on a 24-row X2D holdout, best holdout-probe selection happens at step
1 with only about 0.081 percent median recovery, and train rows regress by
about -101.16 percent median. This rules out simple NAF-style scale-up as the
next primary path.
The corrected-distribution X2D-scene NAF run lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/index.html`.
It trains only on X2D rows while holding out `2024_April_X2D_1742`. That fixes
the worst train/holdout distribution mismatch, but still reaches only about
0.107 percent median raw MAE recovery on the 9-row X2D scene holdout, keeps
holdout RMSE recovery negative, and selects step 1 as best. This confirms
distribution matters but does not promote the NAF branch.
The matched X2D-scene U-Net SNR-filter batch lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/index.html`,
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/index.html`,
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/index.html`.
It shows the SNR result should become weighting/conditioning, not hard row
removal: signal-only training reaches about 0.112 percent median MAE recovery,
signal-or-mixed reaches about 0.119 percent, and unfiltered X2D-only reaches
about 0.149 percent on the same 9-row X2D scene holdout.
The matched X2D-scene U-Net SNR-weighted batch lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/index.html`,
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/index.html`,
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/index.html`.
It shows broad weighting is not enough: signal-emphasis reaches about
0.135 percent, continuous-SNR reaches about 0.129 percent, and noise-floor-only
downweighting reaches about 0.153 percent median MAE recovery while RMSE
remains negative.
The CFA-aware target control and matched CFA-conditioned U-Net live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_target_control_unet_w32_1200_20260701/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_matched_unet_w32_1200_20260701/index.html`.
The control reproduces the 0.153 percent baseline on the regenerated
CFA-aware target, while simple CFA one-hot conditioning drops to about 0.100
percent median MAE recovery.
The stored-HF/noise-floor U-Net and pyramid/noise-floor U-Net controls live at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/index.html`
and
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/index.html`.
They reject two obvious follow-ups: stored candidate-HF reaches about
0.110 percent median MAE recovery and broader pyramid context reaches about
0.131 percent, both below the small noise-floor-weighted U-Net.
Adding absolute crop-position, camera one-hot, and full-crop candidate raw/HF
scalar context to that U-Net lands at about 0.09 percent on X2D and about
0.19 percent on Z8, below the existing Z8 raw-CFA baseline. The bounded
full-crop U-Net sample-mode probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_unet_w16_160_20260630/train_receipt.json`
trains on whole target crops and is runtime-safe, but it reaches only about
0.06 percent median MAE recovery on the hard X2D scene and regresses the train
split. The bounded full-crop stored-HF/context U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_contextstoredhf_unet_w24_360_20260630/train_receipt.json`
adds candidate-only stored-HF plus pooled candidate context, but reaches only
about 0.02 percent median MAE recovery and about 0.001 percent RMSE recovery
on the same hard X2D holdout. The bounded full-crop spectral-loss U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_spectral_unet_w24_420_20260630/train_receipt.json`
adds global FFT-magnitude residual loss, but reaches only about 0.03 percent
median MAE recovery while regressing the train split. The larger full-crop
raw-context U-Net at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_fullcrop_rawcontext_unet_w32_900_20260630/train_receipt.json`
uses scene-balanced full-crop samples and pooled candidate context, but still
reaches only about 0.056 percent median MAE recovery and about 0.005 percent
median RMSE recovery. The deeper gated pyramid U-Net at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_pyramid_rawcontext_w24_700_20260630/train_receipt.json`
adds a third encoder scale and channel gates, but reaches only about 0.031
percent median MAE recovery and about 0.003 percent median RMSE recovery. The
bounded global-context U-Net at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_globalctx_unet_w24_500_20260630/train_receipt.json`
adds a downsampled full-crop feature-map branch and scene-balanced full-crop
training, but reaches only about 0.0166 percent median MAE recovery and about
0.0015 percent median RMSE recovery.
The masked-context global-context U-Net at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_maskedctx_globalctx_w24_420_20260630/train_receipt.json`
randomly hides candidate detail blocks during training, but reaches only about
0.0025 percent median MAE recovery and slightly negative RMSE recovery.
A matched global-context U-Net on the current X2D-scene/noise-floor baseline
then reaches about 0.149 percent median MAE recovery and about -0.0049 percent
median RMSE recovery at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/train_receipt.json`,
which is still below the 0.153 percent small U-Net branch on MAE.
A non-box PSF/CFA NAF diagnostic at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/train_receipt.json`
uses explicit known-kernel weights `[0.52, 0.23, 0.17, 0.08]` and reaches about
0.130 percent median MAE recovery and about 0.0025 percent median RMSE
recovery. It confirms fixed global PSF conditioning is not enough; real
row-level PSF/camera variation is still required for this pillar.

A non-parametric patch-dictionary probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_patch_dictionary_x2dholdout_20260630/patch_dictionary_probe.json`
tests whether the missing residual can be recovered by nearest-neighbor
retrieval over current candidate raw/HF patch statistics. It also fails:
median raw-residual MAE recovery is about -0.80 percent and median RMSE
recovery is about -0.72 percent on the hard X2D holdout. The next model needs
a different runtime signal, a materially different target/objective, or a
stronger learned detail prior, not another local loss-weight/patch-size pass,
simple context-plane concatenation, combined local-feature concatenation,
simple band-loss reweighting, camera-domain filtering, camera-balanced
sampling, 32px context padding, a small U-Net alone, frame-context scalar
planes alone, bounded full-crop sampling alone, bounded stored-HF/full-crop
context alone, bounded full-crop spectral loss alone, a deeper pyramid over the
same runtime features, or simple nearest-neighbor residual transfer.

The generated JSON keeps `production_ready=false` until all four pillars have
direct evidence. This avoids promoting a proxy benchmark or diagnostic CNN as a
finished product result.
