# Premium Still SR

The premium still-SR pillar is separate from the current video SR work. It is
allowed to spend much more time per image, but it must still preserve editable
raw behavior, tone/color stability, camera noise policy, and worst-row visual
quality.

## Receipt

Premium still-SR evidence is recorded as a `gpr.premium_still_sr_gate.v1` JSON
sidecar and validated by:

```sh
python3 tools/check_product_pillar_receipts.py path/to/premium_still_sr_gate_receipt.json
```

The receipt requires:

- candidate pipeline ID, checkpoint hash, and target role;
- fixture coverage for camera count, 50 MP-class count, 100 MP-class count,
  and CFA phases;
- editable DNG, editable GPR, review TIFF/ProRes, and dashboard artifact
  hashes;
- comparison against the current STILL q0/q3/q8 baseline;
- a noise policy with raw-noise/signal audit status.

## Skeleton Builder

The committed builder creates a CI-safe non-production receipt:

```sh
python3 tools/build_premium_still_sr_gate_receipt.py \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate_skeleton
```

This proves the gate contract and artifact hashing path. It does not promote a
model. `--production-ready` is refused unless `--real-artifacts` is also set,
and the receipt checker still requires real gate pass state, 50 MP fixtures,
100 MP fixtures, and a passing raw-noise/signal audit.

## Current-State Readiness Builder

The current-state builder audits the merged still baselines, 50 MP / 100 MP
capability evidence, reusable SR packaging artifacts, and X2D/Z8 camera-noise
sidecars:

```sh
python3 tools/build_premium_still_sr_readiness.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_readiness_20260630
```

It emits:

- `readiness.json` and `readiness.md`;
- `index.html` for review;
- a non-production `premium_still_sr_gate_receipt.json` that validates against
  the product-pillar checker.

This is the source of truth for the current gap: 50 MP / 100 MP still
roundtrips, current still baselines, reusable editable SR packaging, and
validated X2D/Z8 noise sidecars exist, but a dedicated premium still-SR
checkpoint, still-specific dashboard, and raw-editor latitude receipt do not.
The refreshed 2026-06-30 readiness audit also reads the latest X2D no-REF HF
residual probe. That probe uses source HF only at training time and no REF/HF
content at runtime, but the scene-held-out median recovery is still only about
2.56 percent MAE and 2.86 percent RMSE, so it remains diagnostic rather than
promotable.

## Experiment Scoreboard

The experiment scoreboard scans premium still-SR training receipts under the
external artifact root, ranks the candidates by held-out residual recovery, and
marks rows as promotable only when they clear the no-REF runtime policy and the
minimum held-out MAE/RMSE recovery thresholds:

```sh
python3 tools/build_premium_still_sr_experiment_scoreboard.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260630
```

Current scoreboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260630/index.html
```

This is a necessary promotion guard, not a full production gate. A future row
must still pass full-frame raw/editor-latitude review before the premium
still-SR pillar can move from diagnostic to production-ready.

## Blocker Audit

The blocker audit combines the experiment scoreboard, current readiness
receipt, merged X2D HF target receipt, and residual band analysis:

```sh
python3 tools/build_premium_still_sr_blocker_audit.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_blocker_audit_20260630
```

Current audit:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_blocker_audit_20260630/index.html
```

The current audit keeps production readiness false. It records zero promotable
rows, a best single-candidate holdout recovery of about 4.03 percent MAE, a
broader scene-held-out recovery of about 2.56 percent MAE, an expanded
13-scene / 351-row target set, and roughly 0.981x fine-band residual share. The
target coverage floor is now cleared. The next executable candidate should keep
that target set fixed and replace the weak rendered-context residual learner
with a stronger raw-domain/CFA-aware or otherwise larger-context texture model
before any promotion attempt.

## Target Expansion Plan

The target expansion planner turns the blocker audit into the next concrete
training input list:

```sh
python3 tools/build_premium_still_sr_target_expansion_plan.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_expansion_plan_20260630
```

Current plan:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_expansion_plan_20260630/index.html
```

It keeps the current 3-scene / 81-row X2D HF target receipt and selects 10 new
target scenes: six additional X2D 100MP scenes and four representative Z8 50MP
scenes, all with validated noise sidecars. Mission 1 has 84 eligible 50MP
fixtures in the routed manifest, but the plan defers them until validated
same-camera noise sidecars exist.

The generated command contract is intentionally executable with the current
tooling: per-scene target building uses `--noise-sidecar` and
`--include-raw-cfa-features`, and the training step now pairs a raw-CFA gated
probe with a matched RGB ablation. The raw-CFA gated probe is evidence only
until it beats the RGB ablation on the expanded target set and survives the
full still/editor-latitude gate.

## Expanded Target Build And Result

The target expansion has been executed:

```sh
python3 tools/cnn/build_premium_still_sr_expanded_hf_targets_from_plan.py \
  --plan /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_expansion_plan_20260630/target_expansion_plan.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630
```

Current receipts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/expanded_target_build_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/merged/merge_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/index.html
```

The merged target has 351 rows across 13 X2D/Z8 scenes. Median residual
absolute mean is about 0.00721 and median HF Y correlation is about 0.575. The
expanded band analysis still shows a fine-band residual share around 0.981x,
so the missing detail is not a coarse tone or low-frequency placement problem.

Two expanded rendered-context training passes have been run. The weighted w96
model was unstable, with strongly negative train and holdout MAE recovery. The
conservative w64 control was stable but landed near zero holdout recovery. That
rules out "just add target coverage to the current rendered-context learner" as
the next production path. The next pass should change the model/feature
contract, most likely toward raw/CFA-aware or larger-context texture modeling,
then re-run the full still-SR gate.

The expanded target has also been rebuilt with complete raw-CFA features:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/expanded_target_build_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json
```

That rebuild records 13 scenes, 351 rows, and
`raw_cfa_feature_complete=true`, with `candidate_raw_cfa4` present in the
merged NPZ for every row.

## Raw-CFA Feature Smoke

The target builder, merge tool, and trainer now support optional raw-CFA
feature planes:

- `tools/cnn/build_premium_still_sr_hf_residual_targets.py --include-raw-cfa-features`
  writes `candidate_raw_cfa4` into the target NPZ.
- `tools/cnn/merge_premium_still_sr_hf_residual_targets.py` preserves
  `candidate_raw_cfa4` only when every merged target source has those arrays,
  and otherwise records incomplete raw-CFA coverage.
- `tools/cnn/train_premium_still_sr_hf_residual.py --feature-mode rgb_multiscale_rawcfa_coord_luma_ev_noise_bright`
  refuses to run unless the target NPZ carries `candidate_raw_cfa4`.
- `tools/cnn/train_premium_still_sr_hf_residual.py --model-arch raw_cfa_gated --feature-mode rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright`
  splits rendered RGB/metadata features from raw phase-detail features, then
  uses the raw-CFA branch to gate the residual predictor. This is still a
  no-REF runtime path: candidate render/raw data and deterministic metadata are
  the only inference inputs.

The first real one-scene raw-CFA smoke target is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_smoke_targets_20260630/2025_10_oct_austin_0626/hf_residual_targets.json
```

It contains 27 X2D crops and stores:

```text
inputs:              27 x 768 x 768 x 3 float16
hf_residuals:        27 x 768 x 768 x 3 float16
source_hf_targets:   27 x 768 x 768 x 3 float16
candidate_raw_cfa4:  27 x 768 x 768 x 4 float16
```

The first raw-CFA w64/d6 probe is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_probe_model_20260630/train_receipt.json
```

It improves train median residual MAE by about 1.62 percent and +2 EV holdout
median residual MAE by about 0.24 percent. The matched RGB-only ablation is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_ablation_rgb_model_20260630/train_receipt.json
```

It improves train median residual MAE by about 1.62 percent and +2 EV holdout
median residual MAE by about 0.63 percent. That means the naive raw-CFA
channel-concat feature contract is not better than RGB rendered-context
features.

The next architecture pass adds an explicit raw-CFA gated branch:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rawcfa_gated_probe_w48_1000_20260630/train_receipt.json
```

That w48/d6/1000-step gated probe improves train median residual MAE by about
1.46 percent and +2 EV holdout median residual MAE by about 0.79 percent. It
clears the matched RGB ablation on the same smoke target, which justified the
expanded validation pass below.

The expanded validation pass now exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_z8holdout_w48_1000_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rgb_ablation_model_z8holdout_w48_1000_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_gated_model_x2dholdout_w48_1000_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rgb_ablation_model_x2dholdout_w48_1000_20260630/train_receipt.json
```

On held-out Z8, the raw-CFA gated model reaches about 1.04 percent median MAE
recovery versus 0.36 percent for the matched RGB ablation. On held-out X2D, it
reaches about 2.92 percent versus 2.42 percent. That proves the raw-CFA gated
direction generalizes beyond the smoke target, but it is still far from the
15 percent broad-holdout recovery threshold and still has negative worst rows.
The next model must add larger context and/or a better raw-domain target, then
run the full 50 MP / 100 MP still/editor-latitude promotion gate.

## Fixture Manifest Builder

Use the latest real-fixture compatibility receipt to build the first dedicated
50 MP / 100 MP still-SR input manifest:

```sh
python3 tools/build_premium_still_sr_fixture_manifest.py \
  --compat-receipt /Volumes/OWC_8TB/gpr_work/artifacts/real_fixture_compatibility/receipt_20260628T060625Z.txt \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_20260629
```

The manifest hashes the source DNG/GPR fixtures, classifies 50 MP / 100 MP
eligibility, and attaches available camera-noise sidecars. It is the input
contract for the next dedicated still-SR training/evaluation run.

## Pair Builder

The first dedicated candidate input set is built from that manifest:

```sh
python3 tools/cnn/build_premium_still_sr_pairs.py \
  --fixture-manifest /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_20260629/fixture_manifest.json \
  --out /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_20260629/premium_still_sr_pairs.npz \
  --work-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_20260629/work \
  --tiles-per-fixture 16 \
  --low-plane-tile 96 \
  --include-gpr
```

This reads real DNG/GPR sources through `gpr_tools`, normalizes each camera from
its black/saturation levels into the existing 14-bit CNN training range, and
emits 4-plane Bayer input/target tiles compatible with the current SR trainer.

The first generated pair set is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_20260629/premium_still_sr_pairs.npz
```

The first smoke checkpoint trained from it is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_smoke_20260629/premium_still_sr_smoke_w24_d4_120.pt
```

That smoke run proves the dedicated still-SR loop executes, but it is not a
production candidate: with X2D held out it improves RMSE by only about
0.0008 percent and still lacks full-dashboard, raw-editor latitude, and
worst-row visual receipts.

A larger 64-tile-per-fixture run also exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt
```

It found a small positive held-out X2D signal at step 400
(`0.15%` RMSE improvement, `0.04%` MAE improvement), then overfit/regressed by
step 1000. Treat that as evidence that the dedicated still-SR loop is alive,
not as production approval.

Build the current candidate metrics dashboard with:

```sh
python3 tools/build_premium_still_sr_candidate_dashboard.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_dashboard_20260629
```

The dashboard summarizes checkpoint hashes, pair hashes, best-step metrics, and
overfit/regression from the final eval. It is a raw-metric dashboard, not the
rendered visual/editor-latitude gate required for production promotion.

Build the current tile-level visual review dashboard with:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python \
  tools/build_premium_still_sr_visual_review.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_20260629 \
  --max-tiles 64 --review-rows 12
```

Current visual review:

`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_20260629/index.html`

The visual review emits baseline/model/target/error contact sheets for the X2D
holdout tiles. It is useful for spotting softness and tile artifacts, but it is
still not a raw-editor render or full-frame still promotion gate.

## Xlarge Diagnostic

The 2026-06-29 xlarge diagnostic increased the pair set to 1,024 tiles:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_xlarge_20260629/premium_still_sr_pairs_256t.npz
```

Whole-image X2D holdout stayed weak:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_xlarge_20260629/premium_still_sr_w48_d6_2000_x2dholdout.pt
best step 300: 0.09% RMSE improvement, 0.06% MAE improvement
```

Random tile holdout across the same fixture set improved substantially:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_xlarge_20260629/premium_still_sr_w48_d6_2400_randomholdout.pt
best step 2400: 12.74% RMSE improvement, 12.30% MAE improvement
```

Diagnostic dashboards:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_xlarge_dashboard_20260629/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_xlarge_random_20260629/index.html
```

Per-image random-holdout RMSE improvement:

| image | eval tiles | RMSE improvement | interpretation |
|---|---:|---:|---|
| Mission 1 50 MP DNG | 57 | 55.89% | model can learn this source distribution |
| Mission 1 50 MP GPR | 44 | 55.71% | model can learn this compressed source distribution |
| Nikon Z8 50 MP DNG | 51 | 19.81% | useful signal, but less dramatic |
| Hasselblad X2D 100 MP DNG | 52 | 2.36% | current blocker for broad 100 MP promotion |

Conclusion: the premium still-SR loop is capable of learning useful detail
priors, but the production blocker is now narrowed to X2D/generalization and
fixture diversity. The next candidate needs more 100 MP fixtures or
camera-specific specialization before it should be promoted.

## X2D Batch Diagnostic

Adobe DNG Converter can batch-convert Hasselblad `.fff` / `.3FR` sources for
this fixture path:

```sh
"/Applications/Adobe DNG Converter.app/Contents/MacOS/Adobe DNG Converter" \
  -c -d /Volumes/OWC_8TB/gpr_work/artifacts/x2d_dng_adobe_batch_20260629 \
  /path/to/source.fff
```

The 2026-06-29 X2D batch converted eight Hasselblad X2D 100C `.fff` files to
DNG and built an expanded 12-fixture manifest:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/x2d_dng_adobe_batch_20260629/conversion_manifest.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_x2d_batch_20260629/fixture_manifest.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_x2d_batch_20260629/premium_still_sr_pairs_x2d_batch_64t.npz
```

Results:

| holdout | checkpoint | best RMSE improvement | best MAE improvement | interpretation |
|---|---|---:|---:|---|
| original X2D fixture | `premium_still_sr_w48_d6_2000_origx2d_holdout.pt` | 0.30% | 0.19% | better than the previous 0.15% result, but still weak |
| new Austin X2D fixture 00 | `premium_still_sr_w48_d6_1600_austin00_holdout.pt` | 2.16% | 1.38% | added X2D diversity helps same-camera-class generalization |

Dashboards:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_x2d_batch_dashboard_20260629/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_x2d_batch_austin00_20260629/index.html
```

The generated raw-extract cache was removed after pair generation. Durable
artifacts kept: converted DNGs, conversion manifest, fixture manifest, pair
NPZ, checkpoints, training receipts, and dashboards.

## X2D Specialist Diagnostic

The first camera-specialist pass built an X2D-only 100 MP pair set from the
original X2D fixture plus the eight converted Austin X2D DNGs:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_x2d_only_20260629/fixture_manifest.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_x2d_only_20260629/premium_still_sr_pairs_x2d_only_128t.npz
```

The original X2D fixture remained the holdout. The X2D-only specialist improves
the hard holdout more than the mixed-camera X2D-batch model:

| candidate | training set | best RMSE improvement | best MAE improvement | interpretation |
|---|---|---:|---:|---|
| mixed-camera X2D batch | Mission 1 + Z8 + X2D | 0.30% | 0.19% | added 100 MP diversity helps, but mixed source training under-serves the hard X2D scene |
| X2D specialist, first pass | X2D only | 0.76% | 0.65% | camera-specialist direction is useful |
| X2D specialist, continued | X2D only | 1.08% | 1.18% | best current hard-X2D result, still not production-grade |

Specialist dashboards:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_x2d_specialist_dashboard_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_x2d_specialist_20260630/index.html
```

The specialist result supports a camera/source-aware router or separate
specialist checkpoints for premium still-SR. It does not yet satisfy
production promotion because the result is still tile-level, the improvement is
modest, and raw-editor latitude/full-frame still receipts are missing.

## Z8 Specialist Diagnostic

The Z8 specialist pass built a 24-fixture Nikon Z8 manifest from the existing
`barn_sky_dngs` fixture directory and trained with `z8_z8z_1349` held out:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_z8_batch_20260630/fixture_manifest.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_z8_batch_20260630/premium_still_sr_pairs_z8_batch_64t.npz
```

Results:

| candidate | holdout | best RMSE improvement | best MAE improvement | interpretation |
|---|---|---:|---:|---|
| Z8 specialist, first pass | `z8_z8z_1349` | 16.04% | 2.56% | strong Z8 route signal |
| Z8 specialist, continued | `z8_z8z_1349` | 25.52% | 4.28% | best current Z8 route candidate |

Dashboards:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_z8_specialist_dashboard_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_z8_specialist_20260630/index.html
```

The generated raw-extract cache was removed after pair generation. Durable
artifacts kept: manifest, pair NPZ, pair sidecar, checkpoints, training
receipts, and dashboards.

## Mission 1 Specialist Diagnostic

The Mission 1 specialist pass built a Mission-only manifest from real
8192 x 6144 Mission 1 DNG/GPR sources under
`/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/RawPics`. Smaller
23 MP and native 12 MP files were intentionally excluded from this premium
50 MP still-SR route.

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_mission1_batch_20260630/fixture_manifest.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_mission1_batch_20260630/premium_still_sr_pairs_mission1_batch_32t.npz
```

The pair set contains 84 fixtures, split as 42 DNG and 42 GPR sources, with
2,688 same-color Bayer SR tiles. The temporary raw-extract cache was removed
after pair generation; the durable pair artifact is about 583 MB.

Results:

| candidate | holdout | best RMSE improvement | best MAE improvement | interpretation |
|---|---|---:|---:|---|
| Mission 1 specialist | `mission1_gp017504_dng,mission1_gp017504_gpr` | 58.13% | 49.40% | strong route signal for both Mission DNG and GPR sources |

Dashboards:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_mission1_specialist_dashboard_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_visual_review_mission1_specialist_20260630/index.html
```

Full-frame follow-up:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_mission1_specialist_20260630/eval/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_mission1_specialist_20260630/eval/summary.json
```

The full-frame run generated normalized 4096 x 3072 low raws and 8192 x 6144
targets from the held-out GP017504 DNG/GPR sources, ran tiled inference with
512-plane-pixel tiles and 64-pixel overlap, and deleted the generated SR raws
after comparison. Both held-out frames improved over bilinear same-color
upsampling:

| scope | RMSE improvement | MAE improvement | gradient MAE improvement | Mac/MPS throughput with 8K raw write |
|---|---:|---:|---:|---:|
| GP017504 DNG/GPR full-frame median | 56.62% | 46.67% | 29.70% | 2.68 fps |

This closes the old Mission placeholder in the router plan and gives Mission 1
its first full-frame still-SR receipt. It is still not a production still-SR
promotion because X2D/Z8 need equivalent full-frame checks, and the whole
routed suite still needs rendered/editor-latitude review plus camera-noise
sidecar target construction.

## Router Plan

The router plan builder turns current specialist evidence into a metadata-only
contract:

```sh
python3 tools/build_premium_still_sr_router_plan.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --fixture-manifest /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fixture_manifest_routed_20260630/fixture_manifest.json \
  --receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_x2d_specialist_20260629/premium_still_sr_x2d_specialist_w48_d6_2400plus2400_origx2d_holdout.pt.json \
  --receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_z8_specialist_20260630/premium_still_sr_z8_specialist_w48_d6_2400plus2400_z8z1349_holdout.pt.json \
  --receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_mission1_specialist_20260630/premium_still_sr_mission1_specialist_w48_d6_2400_gp017504_holdout.pt.json \
  --candidate-alias candidate_0=x2d_specialist \
  --candidate-alias candidate_1=z8_specialist \
  --candidate-alias candidate_2=mission1_specialist \
  --route x2d:100mp:dng=x2d_specialist \
  --route z8:50mp:dng=z8_specialist \
  --route mission1:50mp:dng=mission1_specialist \
  --route mission1:50mp:gpr=mission1_specialist \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_router_plan_20260630
```

Current router plan:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_router_plan_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_router_plan_20260630/router_plan.json
```

Current routes:

| route | fixtures | candidate | status |
|---|---:|---|---|
| `x2d:100mp:dng` | 9 | `x2d_specialist` | best current X2D route, not production-ready |
| `mission1:50mp:dng` | 42 | `mission1_specialist` | strong Mission DNG route, not production-ready |
| `mission1:50mp:gpr` | 42 | `mission1_specialist` | strong Mission GPR route, not production-ready |
| `z8:50mp:dng` | 24 | `z8_specialist` | strong current Z8 route, not production-ready |

The router plan is deliberately `production_ready=false`. It exists so future
work can add real candidates route-by-route without ambiguity.

## Routed Full-Frame Sweep

After the Mission 1 full-frame follow-up, the same tiled full-frame evaluator
was run on the current Z8 and X2D specialist holdouts. Generated SR raws were
deleted after comparison; durable artifacts are the input sidecars, bench
receipts, compare receipts, contact sheets, summaries, and dashboards.

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_mission1_specialist_20260630/eval/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_z8_specialist_20260630/eval/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_fullframe_x2d_specialist_20260630/eval/index.html
```

| route | holdout | full-frame crop | RMSE improvement | MAE improvement | gradient MAE improvement | throughput with raw write |
|---|---|---:|---:|---:|---:|---:|
| `mission1:50mp:dng/gpr` | `GP017504` DNG/GPR | 8192 x 6144 | 56.62% | 46.67% | 29.70% | 2.68 fps |
| `z8:50mp:dng` | `Z8Z_1349` | 8280 x 5520 | 40.74% | 7.86% | 4.06% | 3.20 fps |
| `x2d:100mp:dng` | `2024_April_X2D_1742` | 11664 x 8748 | 1.03% | 1.20% | 1.06% | 1.55 fps |

The X2D source is 11664 x 8750; the full-frame check uses a two-row bottom
crop so every Bayer plane can be downsampled by an exact same-color 2x rule.
This is a full-gate crop, not a hidden resize.

Interpretation: the routed full-frame path is now executable for every current
specialist route. Mission 1 and Z8 are directionally strong. X2D remains the
limiting route; it is positive but weak, consistent with the earlier tile
diagnostics. Production promotion still requires rendered/editor-latitude
review and camera-noise sidecar target construction.

## Rendered / Latitude Proxy Review

`tools/build_premium_still_sr_rendered_review.py` builds the first routed
rendered-review dashboard from the full-frame summaries. It reruns each
specialist checkpoint in memory, renders upper-left, center, and lower-detail
Bayer crops through a simple OpenCV demosaic at -2/0/+2 EV, and scores display
MAE against the target render. It does not write generated SR raws.

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rendered_review_routed_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_rendered_review_routed_20260630/rendered_review.json
```

Result:

| rows | model better | model worse | median model-baseline display MAE | worst model-baseline display MAE |
|---:|---:|---:|---:|---:|
| 36 | 33 | 3 | -0.00018 | +0.00057 |

All three rendered proxy regressions are the X2D center crop under -2/0/+2 EV.
That narrows the current premium still-SR blocker to the X2D center-scene route
under exposure stress, not Mission 1 or Z8. This is still a proxy review:
production promotion needs raw-editor rendering/openability receipts and
camera-noise sidecar target construction.

## X2D Editor-Openability And Metadata Receipt

`tools/build_premium_still_sr_editor_receipt.py` wraps a retained SR-generation
bench receipt and the editable DNG/GPR packaging receipt into the still-SR
product vocabulary:

```sh
python3 tools/build_premium_still_sr_editor_receipt.py \
  --bench-receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/sr_gen/x2d_100mp_dng_premium_still_sr_x2d_specialist_w48_d6_2400plus2400_origx2d_holdout_sr8k_512_ov64_bench.json \
  --packaging-receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/x2d_scaled/packaging/packaging_receipt.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/editor_receipt_x2dscale_meta \
  --route x2d:100mp:dng \
  --camera "Hasselblad X2D 100C" \
  --source-frame 2024_April_X2D_1742 \
  --metadata-audit /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/x2d_scaled/metadata_transplant_v3/metadata_transplant_audit.json \
  --metadata-dng /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/x2d_scaled/metadata_transplant_v3/frame_000000_sr8k_x2d_meta.dng \
  --raw-black-level 4096 \
  --raw-white-level 59215 \
  --min-gpr-psnr-range-db 55
```

Current receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/editor_receipt_x2dscale_meta/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/editor_receipt_x2dscale_meta/editor_receipt.json
```

Result:

| route | dimensions | SR throughput with raw write | metadata DNG | SDK GPR readback | production state |
|---|---:|---:|---|---|---|
| `x2d:100mp:dng` | 11664 x 8748 | 1.50 fps | rawpy-openable, X2D code-value scale, source-camera metadata audit passes with allowed crop/precision exceptions | rawpy-openable via GPR-to-DNG, 57.49 dB across the X2D black-to-white range at q3 | not production-ready |

This closes the first editor-openability question for the hard X2D route. It
also proves a practical source-camera metadata transplant after rescaling the
SR raw back into X2D black/white code values. The receipt is intentionally
`production_ready=false` because it proves openability/export, not
exposure-stressed raw-editor latitude. The metadata audit allows the two-row
`ActiveArea` crop, `AsShotNeutral` numeric-format drift, and missing
recommended `OpcodeList2`; it does not allow missing required render tags.

## X2D Rawpy Latitude Review

`tools/build_premium_still_sr_latitude_review.py` renders the original X2D DNG
and the metadata-transplanted SR DNG through rawpy/LibRaw with camera WB/color
metadata, no auto-bright, AHD demosaic, and -2/0/+2 EV exposure shifts. This is
closer to a raw-editor receipt than the OpenCV Bayer proxy, but it is still an
automated review rather than Lightroom/ACR signoff.

```sh
python3 tools/build_premium_still_sr_latitude_review.py \
  --source-dng /Volumes/OWC_8TB/gpr_work/artifacts/fixtures/x2d_dngs/2024_April_X2D_1742.dng \
  --candidate-dng /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/x2d_scaled/metadata_transplant_v3/frame_000000_sr8k_x2d_meta.dng \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_synthetic_hf_20260630 \
  --crop-size 768 \
  --output-bps 16 \
  --contact-rows 9 \
  --allow-common-crop \
  --oracle-hf-addback \
  --synthetic-hf-addback \
  --synthetic-hf-sidecar /Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_sidecars_20260629/x2d/Hasselblad_X2D_100C_ISO12800_exp0.001_noise_calibration.json
```

Current dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_synthetic_hf_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_synthetic_hf_20260630/latitude_review.json
```

Result:

| rows | median display MAE | worst display MAE | median LF Y MAE | median HF Y MAE | median HF corr | synthetic-HF median MAE | source-HF oracle worst MAE | blocker |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 9 | 0.04281 | 0.09161 | 0.00546 | 0.02892 | 0.406 | 0.04293 | 0.01586 | +2 EV structured high-frequency texture/detail loss |

Interpretation: metadata/openability is no longer the X2D blocker.
Low-frequency tone is much closer than full-pixel error. In the +2 EV rows the
candidate retains only about 44-53 percent of the source high-frequency
luminance energy. Median HF correlation is only 0.406, with the worst +2 EV
rows around 0.398-0.483, so the candidate is not just under-amplified; much of
the source HF structure is not aligned. The optional source-HF oracle preserves
candidate low-frequency tone and injects source high-frequency content; it
drops worst +2 EV display MAE from 0.09161 to 0.01586 and worst +2 EV HF Y MAE
from 0.06095 to 0.00005. That oracle uses source content and is not a
production/no-REF render path.

The same dashboard now runs a production-safe synthetic-HF sweep seeded from
candidate/runtime metadata only. With the X2D ISO 12800 darkframe sidecar, the
normalized sigma is 0.00390 and the sweep tests 1x through 16x that scale. The
best random-HF rows slightly worsen median display MAE from 0.04281 to 0.04293
and worst display MAE from 0.09161 to 0.09167, leaving a median 0.03713 MAE
gap to the source-HF oracle. The production conclusion is therefore narrower:
the next pass needs structured texture/detail reconstruction or a still-SR
target/loss change, not simple noise addback.

### X2D Structured HF Residual Targets

`tools/cnn/build_premium_still_sr_hf_residual_targets.py` turns the X2D
latitude comparison into a supervised residual dataset for the next still-SR
training pass. It stores candidate rendered crops as inputs and
`source_hf - candidate_hf` as the target residual. The source DNG is used only
to build the training target; this artifact is not a runtime/no-REF render
path.

```sh
python3 tools/cnn/build_premium_still_sr_hf_residual_targets.py \
  --source-dng /Volumes/OWC_8TB/gpr_work/artifacts/fixtures/x2d_dngs/2024_April_X2D_1742.dng \
  --candidate-dng /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_editor_receipt_20260630/x2d_scaled/metadata_transplant_v3/frame_000000_sr8k_x2d_meta.dng \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630 \
  --crop-size 768 \
  --block 16 \
  --output-bps 16 \
  --contact-rows 9
```

Current dashboard and target NPZ:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/hf_residual_targets.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/hf_residual_targets.npz
```

Result:

| rows | median HF corr | median residual mean | max residual mean | median residual p95 | NPZ bytes |
|---:|---:|---:|---:|---:|---:|
| 9 | 0.406 | 0.04284 | 0.09168 | 0.10893 | 83,370,728 |

This is the first concrete target for the next production experiment: train a
structured residual/detail model that predicts this field from candidate/runtime
inputs, then rerun the rawpy latitude gate without source-HF at render time.

### X2D No-REF HF Residual Smoke Model

`tools/cnn/train_premium_still_sr_hf_residual.py` trains a bounded residual
predictor against the structured HF targets. The model is runtime-safe in the
narrow input sense: inference sees candidate rendered RGB, candidate high-pass,
and deterministic XY coordinates only. The source DNG contributes only to the
supervised target builder above.

```sh
python3 tools/cnn/train_premium_still_sr_hf_residual.py \
  --targets /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/hf_residual_targets.npz \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630 \
  --checkpoint-name x2d_hf_residual_w64_d6_s2000.pt \
  --steps 2000 \
  --batch-size 6 \
  --patch-size 192 \
  --width 64 \
  --depth 6 \
  --residual-scale 0.30 \
  --feature-mode rgb_hf_coord \
  --holdout-ev 2.0
```

Current smoke artifact:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630/x2d_hf_residual_w64_d6_s2000.pt
```

Result:

| split | baseline residual MAE median | model residual MAE median | residual MAE reduction median | checkpoint SHA-256 |
|---|---:|---:|---:|---|
| train EV -2/0 | 0.03002 | 0.02831 | 5.34% | `25dad7e865724cc00e9a9da40544a325f36d97952db952d1e920d3aab1d0ceff` |
| holdout EV +2 | 0.08659 | 0.08305 | 4.03% | `25dad7e865724cc00e9a9da40544a325f36d97952db952d1e920d3aab1d0ceff` |

This is progress but not a production result. The source-HF oracle still shows
that the missing +2 EV texture/detail is recoverable in principle; this no-REF
smoke model recovers only a small part of it. The next pass should test more
context-rich inputs or a lower/mid/high-frequency target split before spending
on a full still-SR promotion run.

### X2D HF Residual Band Analysis

`tools/cnn/analyze_premium_still_sr_hf_residual_bands.py` decomposes the
structured residual target by frequency band and brightness range. This is a
diagnostic only; the source-derived residual target is used to decide what a
future no-REF model must learn.

```sh
python3 tools/cnn/analyze_premium_still_sr_hf_residual_bands.py \
  --targets /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_20260630/hf_residual_targets.npz \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_20260630 \
  --fine-block 4 \
  --mid-block 16 \
  --coarse-block 64 \
  --contact-rows 9
```

Current diagnostic artifact:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_20260630/band_analysis.json
```

Result:

| metric | value |
|---|---:|
| median Y residual abs mean | 0.02892 |
| +2 EV median Y residual abs mean | 0.05983 |
| +2 EV median Y residual p95 | 0.15422 |
| median HF energy ratio | 0.467 |
| median fine-band share of residual abs | 0.980x |
| median mid-band share of residual abs | 0.204x |
| median coarse-band share of residual abs | 0.00003x |

The residual is not a coarse tone or alignment problem. It is dominated by
fine-band texture/noise/detail, with a meaningful but smaller mid-band term.
The error grows sharply at +2 EV and has brightness-range structure: +2 EV
bright pixels show much larger residuals than midtones, while the clipped
center row is a special case. The next model target should therefore be
exposure/brightness-aware fine texture restoration with validated camera-noise
conditioning, not another coarse color/tonemap or random-noise pass.

### Broader X2D HF Residual Grid

The first HF residual target set only had 9 rows: three crops at three EVs.
`tools/cnn/build_premium_still_sr_hf_residual_targets.py` now supports
deterministic grid crops and writes scene/source metadata into each row so
later training can hold out crops or whole source scenes.

Current broader target:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_grid5_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_targets_grid5_20260630/hf_residual_targets.npz
```

Result:

| target | rows | median HF correlation | median residual abs mean |
|---|---:|---:|---:|
| original named crops | 9 | 0.406 | 0.04284 |
| 5x5 grid across -2/0/+2 EV | 75 | 0.407 | 0.04456 |

The grid target does not change the diagnosis: the candidate still lacks
high-frequency X2D texture/detail under the rawpy latitude render, and that
gap is not explained by a single odd crop.

The matching no-REF center-grid holdout probe is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_grid5_centerholdout_w48_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_grid5_centerholdout_w48_20260630/train_receipt.json
```

| split | train rows | holdout rows | train median residual MAE reduction | holdout median residual MAE reduction | checkpoint SHA-256 |
|---|---:|---:|---:|---:|---|
| hold out `grid5_02_02` center crop across EVs | 72 | 3 | 1.65% | 1.69% | `f2a8a3dc4b6e0748b6bf403f83042291baf15ab78a6f3328a914bde3f080f20a` |

The broader band analysis is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_band_analysis_grid5_20260630/index.html
```

| metric | value |
|---|---:|
| median Y residual abs mean | 0.02772 |
| median fine-band share of residual abs | 0.969x |
| median mid-band share of residual abs | 0.253x |
| median coarse-band share of residual abs | 0.00003x |

This confirms the production blocker at broader coverage: the remaining X2D
gap is fine-band texture/noise/detail and scene generalization. The next target
expansion should combine multiple X2D scenes, validated X2D noise sidecars, and
scene-held-out evaluation before spending on a larger model.

### Multi-Scene X2D HF Residual Target

`tools/cnn/build_premium_still_sr_degraded_candidate_raw.py` now creates a
deterministic same-color box2 degraded raw from a source DNG, and
`tools/cnn/build_premium_still_sr_hf_residual_targets.py` can render that raw
through the source DNG metadata. This avoids requiring a packaged candidate
DNG for every training scene while preserving camera WB/color/tone behavior in
the target render. `tools/cnn/merge_premium_still_sr_hf_residual_targets.py`
then combines per-scene NPZ files into one training set.

Current multi-scene target:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/merged/merge_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/merged/hf_residual_targets_merged.npz
```

Scenes:

| scene | ISO | noise sidecar status | rows |
|---|---:|---|---:|
| `x2d_1742_iso12800` | 12800 | exact X2D ISO 12800 sidecar | 27 |
| `x2d_austin0150_iso3200` | 3200 | exact X2D ISO 3200 sidecar | 27 |
| `x2d_austin0181_iso6400` | 6400 | bracketed by X2D ISO 3200 and 12800 sidecars | 27 |

Merged result:

| rows | scenes | median HF correlation | median residual abs mean |
|---:|---:|---:|---:|
| 81 | 3 | 0.465 | 0.03005 |

Scene-held-out no-REF probes:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_w48_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_w48_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/train_receipt.json
```

| model | holdout scene | train median residual MAE reduction | holdout median residual MAE reduction | checkpoint SHA-256 |
|---|---|---:|---:|---|
| w48 crop-local RGB/HF | `x2d_austin0181_iso6400` | 2.21% | 1.46% | `b1f0af31f5a5f8017fa6218592b35cc06dd8c159074ea993b1cdda7a5a84eba2` |
| w64 multiscale + ISO/noise sidecar scalars | `x2d_austin0181_iso6400` | 3.29% | 2.26% | `c945b24315047592963f3a1dbdf4e1f4722afa732e6821caa9eb24cdee34d4ef` |
| w96 multiscale + ISO/noise sidecar scalars | `x2d_austin0181_iso6400` | 3.69% | 2.56% | `b3cfc2687a4fe7e66eedb57c7f82352f9804712dc68cc8699461d474390c84c9` |

Merged band analysis:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_multiscene_hf_residual_band_analysis_20260630/index.html
```

| metric | value |
|---|---:|
| median Y residual abs mean | 0.01894 |
| median Y residual p95 abs | 0.04723 |
| median HF energy ratio | 0.579 |
| median fine-band share of residual abs | 0.971x |
| median mid-band share of residual abs | 0.244x |
| median coarse-band share of residual abs | 0.00003x |

These are positive scene-held-out X2D HF target results, but still far below a
production still-SR promotion threshold. The evidence now rules out the
single-image target and simple scalar conditioning as the main blockers:
multiscale candidate features plus validated ISO/noise sidecar scalars improve
holdout recovery from 1.46 percent to 2.56 percent, but the model still
recovers only a small part of the fine texture/detail gap. The next serious
pass should move from display-space crop-local residual learning to a
larger-context, noise-conditioned, raw-domain target/model, then rerun the
rawpy latitude gate.

### Exposure/Brightness-Aware Residual Controls

`tools/cnn/train_premium_still_sr_hf_residual.py` now supports EV/brightness
features, multiscale high-pass features, and optional ISO/noise sidecar scalar
planes. These modes remain no-REF at inference: they use candidate RGB,
candidate high-pass, candidate luma/brightness buckets, deterministic render
EV, deterministic coordinates, and camera/ISO noise sidecar metadata.

The first control pass shows that those features alone do not solve the X2D
texture/detail blocker:

| run | split | train median residual MAE reduction | holdout median residual MAE reduction | dashboard |
|---|---|---:|---:|---|
| baseline w64/d6 | train EV -2/0, hold out +2 EV | 5.34% | 4.03% | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_w64_20260630/index.html` |
| EV/brightness weighted | train EV -2/0, hold out +2 EV | 4.57% | 3.39% | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_evbright_w64_20260630/index.html` |
| EV/brightness weighted | train upper-left/lower-detail, hold out center crop | 5.57% | -1.56% | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_evbright_cropholdout_w64_20260630/index.html` |
| EV/brightness unweighted | train upper-left/lower-detail, hold out center crop | 6.28% | 0.54% | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_hf_residual_model_evbright_unweighted_cropholdout_w64_20260630/index.html` |

The weighted objective over-focuses the tiny named-crop set and hurts spatial
holdout. The unweighted crop-holdout control is barely positive. The 75-row
grid target above is the next production-aligned baseline: it gives broader
coverage, but still only recovers 1.69 percent on the center-grid holdout.
Promotion now needs multi-scene/full-frame X2D target diversity with validated
ISO/noise sidecars, not another scalar EV/brightness-only control.

## Production Path

The next real pass should use 50 MP and 100 MP still fixtures, including X2D
and Z8 where available:

1. Train or tune camera/source specialists against high-quality still targets,
   not video crops.
2. Add a deterministic router based on source metadata and/or safe raw-domain
   features, with a default shared model only where specialists do not help.
3. Condition on validated camera-noise sidecars for the relevant camera/ISO
   class.
4. Emit editable DNG/GPR plus review TIFF/ProRes/contact sheets.
5. Promote only if the candidate beats the current still tiers on raw-domain
   metrics, rendered visual gates, editor-latitude checks, and worst-image
   review.
