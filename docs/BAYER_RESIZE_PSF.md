# Bayer Resize PSF

The raw-video improvement pillar is about understanding the blur introduced
when Bayer data is resized or reconstructed. The current 4K cleanup and 8K SR
paths are approved empirical baselines, but they are not yet formal
PSF-calibrated models.

## Receipt

PSF evidence is recorded as a `gpr.bayer_resize_psf_receipt.v1` JSON sidecar
and validated by:

```sh
python3 tools/check_product_pillar_receipts.py path/to/bayer_resize_psf_receipt.json
```

Production promotion requires real Mission and Z8 full-frame evidence, not just
a synthetic or crop-local measurement. The receipt must include sharp-edge
evidence, texture-field evidence, gate results, raw/editable outputs, ProRes
review media, and timing/memory artifacts.

## Synthetic Builder

The committed builder creates a small non-production receipt that exercises the
contract without private data:

```sh
python3 tools/build_bayer_resize_psf_receipt.py \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/psf_synthetic_smoke \
  --resize-factor 2 --cfa-phase RGGB --cfa-phase GBRG
```

It generates synthetic sharp-edge and texture fixtures, applies a box
downsample/nearest-upsample path, estimates edge-spread width, writes artifact
hashes, and marks `production_ready=false`. This is useful for CI and tool
stability. It is not enough to replace the current SR baseline.

## Real-Pair Builder

The pair-derived builder consumes the premium still-SR pair NPZ layout and fits
the same-color 2x Bayer resize kernel that maps high-resolution target planes
to low-resolution input planes. It also measures the 2x repeat residual budget
so the video-SR work can distinguish broad deblur from same-cell detail
reconstruction:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python \
  tools/build_bayer_resize_psf_from_pairs.py \
  --pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629
```

Current receipt:

`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629/bayer_resize_psf_receipt.json`

Current dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629/index.html`

The 2026-06-29 run uses 256 Mission 1, Z8, and X2D real-fixture tiles. The
global fit converges to normalized weights very close to `[0.25, 0.25, 0.25,
0.25]`, selects `same_color_box2` as the best candidate, and reports about
0.30 RMSE on the normalized 14-bit training scale. This confirms the current
pair target is internally consistent with a same-color 2x2 box resize model.

Refreshed 2026-06-30 xlarge receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/bayer_resize_psf_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/index.html
```

That run uses 1,024 real-fixture tiles and keeps the same conclusion: fitted
normalized weights are `[0.25000165, 0.25000245, 0.25000036, 0.24999554]`,
`same_color_box2` remains the best kernel, and fit RMSE is `0.30044` on the
14-bit training scale. The new detail budget shows the 2x repeat residual is
almost entirely same-cell fine detail:

| metric | value |
|---|---:|
| residual abs mean, 14-bit scale | 67.88974 |
| residual RMSE, 14-bit scale | 165.42555 |
| fine share of residual abs | 0.99999x |
| mid share of residual abs | 0.00347x |
| coarse share of residual abs | 0.00187x |
| residual / target same-cell detail ratio | 1.00001x |

Interpretation: for the modeled 4K-to-8K pair target, the effective PSF is a
2x2 box, and the missing signal is not a broad low-frequency blur field. It is
same-cell Bayer fine detail that must be reconstructed by the offline SR model
or supplied by a better native capture target.

It is still non-production evidence. The current pair generator creates the
low-resolution side by downsampling extracted high-resolution raw, so this does
not yet measure native sensor, camera ISP, DMA, display, or storage blur.

## Known-Kernel Fitter Validation

The known-kernel validation proves the fitter can recover a deliberately
non-box same-color 2x Bayer kernel, rather than only rediscovering the current
pair-builder's 2x2 average:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python3 \
  tools/build_bayer_resize_psf_known_kernel_validation.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_known_kernel_validation_20260701
```

Current dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_known_kernel_validation_20260701/index.html`

Current result: the fixture target is `[0.52, 0.23, 0.17, 0.08]`, and the
fitter recovers normalized weights within `1.1e-8` RMSE. The mismatched
negative control is rejected with about `9064` RMSE on the 14-bit scale. This
narrows the current native Mission 1 blocker: the measurement code can recover
a known kernel, so the unstable local native kernel is more likely caused by
the uncontrolled near-time source pairs than by an inability to fit a kernel.

This is still not production evidence. Controlled native Mission 1 high/low
pairs, decoded Bayer hashes, fixed settings, and negative controls are still
required before a PSF-conditioned model can replace the approved 4K/8K
baselines.

## Readiness Audit

The current PSF/SR readiness audit is generated by:

```sh
python3 tools/build_raw_video_psf_audit.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630
```

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630/index.html`

The audit intentionally keeps this pillar non-production at 44 percent. It
records that the approved 4K cleanup and 8K SR baselines are ready for their
current offline roles, and that near-time native Mission 1 high/low candidates
exist, while the native PSF replacement remains open because there is no
measured camera/display PSF receipt and no PSF-conditioned model has beaten the
current Mission42 and Z8 baselines.

Whole-video review evidence is intentionally kept separate from dashboards.
The Z8 A/B lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/`
and contains two standalone 8280 x 5520 ProRes movies: a no-CNN raw Bayer
baseline and the retained 4K cleanup plus approved 8K SR CNN path. The Mission
1 broad A/B lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/`
and contains two standalone 8192 x 6144 ProRes movies over 42 raw-video
frames: a no-CNN 4096 x 3072 raw Bayer baseline upscaled to 8K and the
approved 4K cleanup plus 8K SR CNN render. The stricter Mission 1 scene A/B
lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/`
and contains two standalone 8192 x 6144 ProRes movies over the sequential
`GP017497` through `GP017508` scene: a no-CNN 4096 x 3072 raw Bayer baseline
upscaled to 8K and the approved 4K cleanup plus 8K SR CNN render. These are
baseline review artifacts, not proof that the PSF-conditioned replacement is
complete.

The native Mission 1 high/low candidate inventory is generated by:

```sh
python3 tools/build_mission1_native_psf_pair_inventory.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630
```

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_pair_inventory_20260630/index.html`

The measurement plan converts that inventory into the next executable protocol:

```sh
python3 tools/build_mission1_native_psf_measurement_plan.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630
```

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630/index.html`

The plan selects the best decoded native high/low pairs, hashes the input
receipts, and spells out the required alignment, scene vetting, edge/texture
tile mining, Bayer/RGB kernel fitting, and gate promotion steps. It is still
not a measured PSF receipt; production remains blocked until a measured kernel
and PSF-conditioned 4K/8K model gate exist.

The first native measurement run executes that plan:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python \
  tools/build_mission1_native_psf_measurement.py \
  --measurement-plan /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_plan_20260630/measurement_plan.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630
```

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/index.html`

Current result: the run executed alignment, scene vetting, edge/texture mining,
and Bayer-plane kernel fitting on the selected Mission 1 pairs. It accepted 2
of 3 pairs, found 1,409 sharp-edge tiles and 1,381 texture-field tiles, but
rejected the measured kernel as unstable. That narrows the next data need:
controlled same-scene high/low pairs, not more fitting on the current near-time
pair set.

The kernel-stability audit makes that rejection explicit:

```sh
python3 tools/build_mission1_native_psf_kernel_stability_audit.py \
  --measurement /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/native_psf_measurement.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_kernel_stability_audit_20260630
```

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_kernel_stability_audit_20260630/index.html`

Current result: the dominant blocker is kernel disagreement, not just missing
one more pair. The current near-time measurement has 2 accepted pairs, max
normalized-weight std `0.809` against a `0.10` gate, one accepted pair with
invalid negative weights (`GP017602 -> GP017600`), and one low-correlation
diagnostic pair (`GP017601 -> GP017600`). This means the current native kernel
must not be used to condition a replacement model.

The controlled capture request now also requires production provenance for
each candidate pair: original high/low GPR/DNG paths with SHA-256 source
hashes, decoded little-endian uint16 Bayer paths with byte counts and hashes,
fixed camera settings across each pair, extraction receipts or camera-firmware
decode receipts, and negative controls that are expected to fail alignment or
scene vetting. This keeps PSF conditioning from being trained on cropped,
tone-mapped, demosaiced, moved-camera, or otherwise ambiguous data.

The current local-corpus audit is generated by:

```sh
python3 tools/build_mission1_native_psf_corpus_audit.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_corpus_audit_20260630 \
  --hash-files
```

Dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_corpus_audit_20260630/index.html`

It hashes the four current near-time Mission 1 candidate pairs and finds zero
strict controlled pairs. The files are useful diagnostics, but they do not
close production PSF: ISO/settings are not fixed tightly enough, fixed
WB/lens/stabilization/sharpening metadata is absent, no negative controls are
marked, the existing measurement accepted only two pairs, and the kernel is
unstable.

## SR/Detail Candidate Scoreboard

The candidate scoreboard scans historical Mission/Z8 SR and detail decision
receipts, extracts baseline-vs-candidate holdout deltas, and requires
Mission42 plus Z8 all24-scale coverage before a row can count as a current
promotion candidate:

```sh
python3 tools/build_raw_video_sr_candidate_scoreboard.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_video_sr_candidate_scoreboard_psf_detail_20260701
```

Current scoreboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_sr_candidate_scoreboard_psf_detail_20260701/index.html
```

The current run indexes 90 decision receipts and finds zero current-scale
promotion rows. It now has one PSF-detail-ready row from the metric-bearing
rerun: the current candidate improves median same-cell detail by 2.004 points
on Mission42 and 0.302 points on Z8, but still regresses Mission gradient floor
versus the approved baseline. It therefore does not replace the approved 4K/8K
baselines.

The Mission gradient/detail blocker audit lives at:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_gradient_detail_blocker_audit_20260701/index.html
```

It confirms that the current candidate has five Mission rows that regress both
gradient and same-cell Bayer detail relative to the approved baseline:
`GP017346`, `GP017600`, `GP017347`, `GP017348`, and `GP017359`. The next local
candidate should preserve the current median same-cell detail gains while
adding a hard-row gradient/detail floor objective or sampler around those rows.

## Detail Metric Audit

The current PSF-conditioned replacement gate needs detail metrics that match
the modeled-PSF finding: the missing 4K-to-8K signal is mostly same-cell Bayer
fine detail. The audit is generated by:

```sh
python3 tools/build_raw_video_psf_detail_metric_audit.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --created-utc 2026-07-01T01:23:45Z \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_detail_metric_audit_20260701
```

Current dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_detail_metric_audit_20260701/index.html
```

Initial result: coverage was present for the selected Mission42 and Z8 all24
baseline/candidate summaries, but all four historical summaries were missing
the required same-cell detail fields:

- `same_cell_detail_mae_improvement_pct`
- `same_cell_fine_detail_mae_improvement_pct`
- `cfa_plane_detail_mae_improvement_pct`

The resulting status is
`blocked_missing_same_cell_detail_metrics`. The next implementation step is to
emit these metrics from the full-frame Mission/Z8 summary builders, then
re-run the SR/detail scoreboard before training or promoting a PSF-conditioned
replacement.

That implementation pass is now complete for the current best baseline and
candidate summaries. The metric-bearing full-frame rerun lives at:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/
```

The rerun preserves four summary receipts:

| summary | images | same-cell detail median | same-cell fine median | CFA-plane detail median |
|---|---:|---:|---:|---:|
| Mission42 baseline | 42 | 26.091% | 22.100% | 26.091% |
| Mission42 candidate | 42 | 28.095% | 23.397% | 28.095% |
| Z8 baseline | 24 | 3.214% | 2.347% | 3.214% |
| Z8 candidate | 24 | 3.516% | 2.552% | 3.516% |

The matching metric audit is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_detail_metric_audit_rerun_20260701/index.html
```

It records `ready_summary_count=4`, `missing_summary_count=0`, and
`psf_detail_gate_ready=true`. This closes the missing-metric blocker only. It
does not promote a PSF-conditioned replacement because the controlled native
PSF kernel and PSF-conditioned model gate are still open.

## Next-Experiment Contract

The next-experiment contract is generated by:

```sh
python3 tools/build_raw_video_psf_next_experiment_contract.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --created-utc 2026-07-01T00:29:21Z \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_next_experiment_contract_20260701
```

Current dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_next_experiment_contract_20260701/index.html
```

The contract records the current actionable split:

- local modeled-PSF ablations are allowed and should start from the
  `same_color_box2` detail-budget receipt;
- those ablations are non-production until controlled native high/low pairs
  produce a stable kernel;
- the current native Mission 1 kernel must not condition a production model
  because it has only 2 accepted pairs, max normalized-weight std `0.809`,
  and one accepted pair with invalid negative weights;
- the SR/detail scoreboard has 89 historical decision receipts and zero rows
  promotable under the Mission42 plus Z8 all24 coverage rule.

The recommended first local track is a modeled-PSF same-cell fine-detail
ablation. Promotion still requires Mission42 and Z8 all24 gate improvement,
standalone scene-video review, `.gvid`, editable DNG/GPR, ProRes, timing,
memory, config, dashboard, and artifact-hash receipts.

## Production Path

The next real pass should move beyond modeled pairs into native capture and
display evidence:

1. Estimate effective Bayer-domain PSF from true high-res / native-low-res
   Mission 1 and Z8 captures, with sharp edges and texture fields.
2. Train or tune 4K cleanup and 8K SR with CFA-aware targets, PSF-conditioned
   losses, and explicit fine-detail reconstruction metrics.
3. Promote only if Mission42 and Z8 all24 gates improve and the output has
   `.gvid`, editable DNG/GPR, ProRes, timing, memory, and hash receipts.
