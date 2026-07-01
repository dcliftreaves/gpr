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
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260701
```

Current scoreboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_20260701/index.html
```

The current scoreboard scans **80** premium still-SR training receipts across
the older rendered-HF and newer raw-CFA residual schemas. All 80 rows are
runtime-safe, but **0** are promotable. The best runtime-safe row reaches only
**4.03%** held-out MAE recovery and **3.75%** held-out RMSE recovery against a
15% / 15% promotion threshold. This is a necessary promotion guard, not a full
production gate. A future row must still pass full-frame raw/editor-latitude
review before the premium still-SR pillar can move from diagnostic to
production-ready.

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

## Raw-CFA Residual Target And Model Probe

The raw-domain target builder now converts the expanded raw-CFA feature set
into direct source-minus-candidate same-color raw residual supervision:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/raw_cfa_residual_targets.npz
```

The NPZ covers the same 351 rows / 13 scenes and stores
`candidate_raw_cfa4`, `candidate_raw_hf_cfa4`, `raw_hf_residual_cfa4`,
`source_raw_hf_cfa4`, and `render_hf_residual_y`. It is the correct target for
editable raw restoration because the model output is a four-plane CFA residual,
not a rendered RGB texture patch. The refreshed CFA-aware build also resolves
crop-local Bayer phase from source DNG `raw_pattern` plus `crop_xy` parity:
351/351 rows have known phase labels, with 270 `RGGB` rows and 81 `GBRG`
rows.

The target now has a duplicate-row audit:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_target_duplicate_audit_20260701/index.html
```

It records 351 target rows but only 117 unique scene/crop raw-domain rows. For
all 117 scene/crop groups, `candidate_raw_cfa4`, `candidate_raw_hf_cfa4`,
`raw_hf_residual_cfa4`, and `source_raw_hf_cfa4` are identical across the
-2/0/+2 EV rows, while `render_hf_residual_y` varies across every group. The
EV rows are therefore useful rendered review/tone rows, but they are not
independent raw-CFA supervision. Raw-domain training receipts should therefore
report unique scene/crop counts separately from rendered review rows and use
the deduplicated target below for new teacher/student runs.

The deduplicated raw-supervision target is now materialized:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/raw_cfa_residual_targets_dedup.npz
```

It keeps the trainer-facing array names (`candidate_raw_cfa4`,
`candidate_raw_hf_cfa4`, `raw_hf_residual_cfa4`, `source_raw_hf_cfa4`, and
`render_hf_residual_y`) but collapses the target from 351 source rows to 117
unique raw rows with zero raw conflicts. The rendered EV rows are averaged into
one review plane and preserved in metadata under
`raw_deduplicated_review_rows`; they should not be counted as independent raw
supervision.

The current deduplicated CFA-aware target has 117 unique raw rows, 0 raw
conflicts, and 117/117 known crop-local CFA labels: 90 `RGGB` rows and 27
`GBRG` rows. New mixed-normal-Bayer premium still-SR runs should use this
artifact or a newer target with the same `cfa_phase` metadata contract.

## PSF-Conditioned Trainer Path

The raw-CFA residual trainer now has explicit PSF/kernel conditioning feature
modes for the next premium still-SR pass:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python3 \
  tools/cnn/train_premium_still_sr_raw_cfa_residual.py \
  --targets /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/raw_cfa_residual_targets_dedup.npz \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_window_attention_teacher_<date> \
  --model-arch window_attention_teacher \
  --feature-mode raw_multiscale_storedhf_coord_ev_noise_psf_cfa \
  --psf-receipt /Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_known_kernel_validation_20260701/bayer_resize_psf_receipt.json \
  --sample-mode full_crop \
  --holdout-camera x2d
```

The `_psf` modes add scalar planes derived from a
`gpr.bayer_resize_psf_receipt.v1` or explicit four-value
`--psf-kernel-weight` values. They do not add REF, source raw, source HF, or
JPEG target content at runtime. The default kernel is the neutral
`[0.25, 0.25, 0.25, 0.25]` box, so existing non-PSF feature modes remain
behavior-compatible.

The trainer also has additive `_cfa` feature-mode variants for mixed normal
Bayer target sets, including `raw_multiscale_coord_ev_noise_cfa`,
`raw_context_coord_ev_noise_cfa`, and `raw_context_coord_ev_noise_psf_cfa`.
Those variants append RGGB/GBRG/GRBG/BGGR/unknown one-hot metadata from target
rows (`cfa_phase`, `cfa_pattern`, `bayer_phase`, or `bayer_pattern`) while
leaving older feature modes behavior-compatible. The current CFA-aware
deduplicated target resolves all 117 rows from DNG metadata and crop parity, so
`_cfa` training no longer collapses the expanded X2D/Z8 target set to
`unknown`.

Two first PSF-conditioned probes have now been run against the deduplicated
X2D scene holdout:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_psf_noisefloor_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fullcrop_rawcontext_psf_unet_w32_900_20260701/index.html
```

The local noise-floor U-Net plus PSF planes reaches **0.106%** median exact raw
MAE recovery on the 9-row X2D scene holdout, below the prior non-PSF
noise-floor branch at **0.153%**, though its median raw residual RMSE recovery
turns slightly positive. The full-crop raw-context PSF U-Net reaches
**0.064%**, barely above the older non-PSF full-crop raw-context branch at
**0.056%** and still far below the promotion threshold.

This is useful evidence, not a promotion. The available PSF receipt is an
almost-neutral same-color box kernel
`[0.25000165, 0.25000245, 0.25000036, 0.24999554]`, and the deduplicated rows
do not carry per-row PSF metadata. A single near-box kernel is therefore not
enough runtime information to solve the hard X2D detail-placement miss. The
next PSF-aware still-SR pass should only be treated as materially new if it adds
real per-camera/per-resize PSF variation, or if it changes the teacher/objective
enough to beat the current **0.153%** X2D scene-holdout baseline.

The row-level PSF sidecar contract now turns that blocker into an executable
trainer input:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python3 \
  tools/build_premium_still_sr_psf_sidecar_contract.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_psf_sidecar_contract_20260701
```

Current sidecar contract:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_psf_sidecar_contract_20260701/index.html
```

It emits `gpr.premium_still_sr_psf_sidecar.v1` rows keyed by stable target-row
hashes and `gpr.premium_still_sr_psf_sidecar_contract.v1` readiness metadata.
The trainer consumes it with `--psf-sidecar`; direct row metadata still wins,
the sidecar beats global fallback weights, and global `--psf-receipt` /
`--psf-kernel-weight` remains only the compatibility fallback. The current
117-row artifact is deliberately **not ready** for PSF-conditioned promotion:
0 rows have camera-specific PSF assignments, 117 rows use the global default
near-box receipt, all 117 rows are near-box, and only 1 unique kernel exists.

The PSF metadata gap audit makes that decision explicit:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python3 \
  tools/build_premium_still_sr_psf_metadata_gap.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_psf_metadata_gap_20260701
```

Current audit:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_psf_metadata_gap_20260701/index.html
```

It records 117 deduplicated raw target rows across 13 scenes, with inferred
coverage of 81 X2D rows and 36 Z8 rows, but **0/117** rows carry row-level PSF
metadata and **0** unique row kernels exist. The global PSF is near-box
(`max_abs_delta_from_box=4.46e-06`), and the best PSF probe reaches
**0.106%** median exact raw MAE recovery versus the non-PSF **0.153%**
baseline. Its verdict is therefore
`another_psf_cnn_run_justified=false` until row-level camera/PSF variation is
added; otherwise the next still-SR effort should move to a stronger
camera/noise-aware teacher objective rather than repeat global PSF planes.

## Research Alignment For The Next CNN Pass

The current local U-Net/raw-residual experiments are intentionally diagnostic,
but they are not aligned with the stronger RAW SR literature. The next
architecture pass should be rebuilt around these points:

The generated next-experiment contract now carries this research basis as
machine-readable `research_basis` rows and converts it into the minimum viable
model requirements:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_next_experiment_contract_transformer_teacher_20260701/index.html
```

The same contract now includes an executable next-pass plan. It pins raw-domain
training to the deduplicated 117-row raw-CFA residual NPZ, reserves the full
351-row / EV target for rendered tone and latitude review, and emits
copy-pasteable smoke, X2D holdout, and Z8 holdout commands for the
`window_attention_teacher` branch. The planned full pass uses
`raw_multiscale_coord_ev_noise_psf_cfa`, the row-level PSF sidecar, full-crop
scene-balanced training, overlap/seam evaluation, and the no-REF/no-source
runtime policy. It is still diagnostic until the generated receipts clear the
X2D and Z8 gates and are followed by editable DNG/GPR, rendered-latitude,
timing, memory, scoreboard, and premium gate receipts.

- Use packed Bayer / CFA-aware preprocessing and preserve sensor-specific black
  level, CFA phase, and exposure metadata. RMFA-Net explicitly calls out black
  level, CFA handling, exposure/tone, and local/global feature separation as
  neural-ISP concerns: https://arxiv.org/html/2406.11469v1.
- Normalize or explicitly encode Bayer phase before mixing camera families.
  BayerUnify-style raw denoising work treats heterogeneous Bayer patterns as a
  first-order training problem rather than a cosmetic metadata detail:
  https://openaccess.thecvf.com/content_CVPRW_2019/papers/NTIRE/Liu_Learning_Raw_Image_Denoising_With_Bayer_Pattern_Unification_and_Bayer_CVPRW_2019_paper.pdf.
- Treat RAW restoration, denoising, demosaicing, and SR as a joint or
  end-to-end problem when the output is rendered/reviewed. JDN DMSR uses
  residual channel-attention blocks for joint denoising, demosaicing, and SR,
  and reports better results than sequential solutions:
  https://openaccess.thecvf.com/content/CVPR2021/papers/Xing_End-to-End_Learning_for_Joint_Image_Demosaicing_Denoising_and_Super-Resolution_CVPR_2021_paper.pdf.
- Model realistic RAW noise/degradation in the raw domain. The pipeline study
  "Rethinking Learning-based Demosaicing, Denoising, and Super-Resolution"
  emphasizes Poisson-Gaussian raw noise and direct raw denoising:
  https://ar5iv.labs.arxiv.org/html/1905.02538.
- Treat blur/resize as part of the forward model. The NTIRE 2024 RAW SR survey
  frames RAW 2x SR as Bayer upscaling under unknown noise and blur, and
  physics-informed PSF work points toward calibrated blur estimation rather
  than unconditioned texture hallucination:
  https://arxiv.org/html/2404.16223v1 and
  https://arxiv.org/html/2502.11382v1.
- Use stronger high-resolution restoration backbones or a teacher/student
  strategy rather than small local U-Nets. The NTIRE 2024 RAW SR survey reports
  top approaches using NAFNet teachers, progressive patch-size finetuning,
  spatial + Fourier losses, and spatial/frequency branches:
  https://arxiv.org/html/2404.16223v1. The refreshed contract also points the
  next primary pass toward SwinIR/HAT/RBSFormer-style shifted-window,
  hybrid-attention, or RAW-SR transformer teachers, or a Restormer-style
  high-resolution teacher, with overlapped-tile/full-image validation before
  any student distillation.
- Preserve Bayer geometry during augmentation and validation. The next pass
  should use Bayer-preserving flips/rotations or canonical phase remapping and
  should fail early if CFA phase metadata is wrong after augmentation.
- Make the first ablations architecture/data-contract tests, not another
  scalar-loss sweep: window-attention teacher versus the current noise-floor
  U-Net, with/without CFA phase conditioning, with/without validated noise
  sidecar conditioning, with/without modeled PSF sidecar, crop-only versus
  overlapped/full-image evaluation, and student distillation only after the
  teacher clears both camera holdouts.
- If multiple frames exist, burst RAW SR literature treats single-image SR as
  severely ill-posed and uses alignment/aggregation over raw bursts:
  https://openaccess.thecvf.com/content/ICCV2021/papers/Lecouat_Lucas-Kanade_Reloaded_End-to-End_Super-Resolution_From_Raw_Image_Bursts_ICCV_2021_paper.pdf.

For this repo, that means the next premium still-SR candidate should not be
another small raw-residual learner over the current duplicated rows, and the
new source-HF rejection receipts show it also should not ask the small U-Net to
predict full source HF directly. It should start from the deduplicated
raw-domain target, then train a CFA-aware window-attention or high-resolution
restoration teacher on unique raw rows with explicit Bayer phase handling,
camera/noise/PSF conditioning, progressive patch sizing, spatial/frequency
objectives, and rendered review gates. The raw-CFA trainer now exposes this
path as `model_arch=window_attention_teacher`, which uses alternating
shifted-window self-attention, overlap convolution, and a downsampled full-crop
context branch while preserving the candidate-only runtime input policy. A
smaller student can be distilled later only if the teacher clears the X2D/Z8
raw and rendered gates without full-image/tile-overlap artifacts.

The first real-target window-attention smoke receipt exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/train_receipt.json
```

It uses `model_arch=window_attention_teacher` with
`raw_multiscale_storedhf_coord_ev_noise_psf_cfa` on the canonical 117-row
deduplicated raw-CFA target, a known-kernel PSF receipt, CFA phase conditioning,
2 training steps, and bounded 2-row train / 2-row X2D holdout evaluation. It is
only executable path evidence: the bounded holdout median raw MAE recovery is
about **0.142%**, far below the promotion gate and not comparable to a full
teacher run. Its value is that the next contracted architecture can now run on
the real target without REF/source/JPEG runtime inputs.

The trainer now also supports explicit overlapped-tile final evaluation and
seam diagnostics:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python \
  tools/cnn/train_premium_still_sr_raw_cfa_residual.py \
  --targets /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/raw_cfa_residual_targets_dedup.npz \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_window_attention_overlap_eval_<date> \
  --model-arch window_attention_teacher \
  --feature-mode raw_multiscale_storedhf_coord_ev_noise_psf_cfa \
  --psf-receipt /Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_known_kernel_validation_20260701/bayer_resize_psf_receipt.json \
  --eval-tile 256 \
  --eval-overlap 64 \
  --seam-check-width 8
```

The first real-target overlap/seam smoke receipt exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/train_receipt.json
```

It uses 64 px overlap and 8 px seam bands on bounded 2-row train / 2-row X2D
holdout evaluation. The bounded X2D holdout median raw MAE recovery is about
**0.448%**, with overlap-vs-plain median MAE around **1.65e-5** and seam-band
delta around **7.04e-5**. This is validation machinery and seam-risk evidence,
not a production still-SR model.

The first RCAB-style teacher smoke run exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/train_receipt.json
```

It trains `model_arch=rcab_teacher` against the deduplicated 117-row target
with `raw_multiscale_storedhf_coord_ev_noise`, multiscale band loss, and
Fourier magnitude loss. It is a 30-step path proof, not a promotion run:
8-row X2D holdout median raw MAE recovery is only about **0.069%**, and the
receipt remains `training_probe_not_registered_production_algorithm`.

A scaled RCAB teacher pass also exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/train_receipt.json
```

It uses width 32, depth 6, 700 steps, scene-balanced sampling, 256 px patches,
multiscale band loss, and Fourier magnitude loss on the same deduplicated
target. It is also a rejection receipt, not a promotion receipt: 24-row X2D
holdout median raw MAE recovery is only about **0.034%**, best holdout probe
selection occurs at step 1, and the train split regresses by about **-3.45%**
median. Simple RCAB scaling is therefore not enough by itself; the next pass
needs a materially stronger teacher/data objective, not just more steps on this
configuration.

A first NAFNet-style teacher pass also exists:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/train_receipt.json
```

It uses `model_arch=naf_teacher` with SimpleGate/attention blocks, width 32,
depth 6, 700 steps, scene-balanced sampling, 256 px patches, multiscale band
loss, and Fourier magnitude loss on the same deduplicated target. This is also
a rejection receipt: the 24-row X2D holdout median raw MAE recovery is about
**-0.059%**, the train split regresses by about **-101.16%** median, and the
best holdout probe occurs at step 1 with only about **0.081%** median recovery.
Simple NAF-style architecture support is therefore not enough by itself; the
blocker is now more likely the target/objective/teacher construction than
another small RCAB/NAF scale-up.

After the SNR audit below, a corrected-distribution NAF probe trained only on
X2D rows while holding out the `2024_April_X2D_1742` scene:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/train_receipt.json
```

This fixes the worst train-distribution mistake from the all-X2D-holdout NAF
run, but it still is not a promotion candidate: the 9-row X2D scene holdout
median raw MAE recovery is only about **0.107%**, holdout RMSE recovery remains
negative at about **-0.128%**, train rows regress by about **-0.493%** median,
and best holdout selection again happens at step 1. The conclusion is narrower
than the first NAF failure: train/holdout camera distribution matters, but
simple NAF-style scale-up with this objective still trails the weak
early-selected U-Net branch and is far below the still-SR gate.

The first SNR-filtered U-Net probe batch then tested the SNR audit as a
training-control hypothesis on the same held-out X2D scene:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/index.html
```

All three use `model_arch=unet`, X2D-only training, the deduplicated raw target,
and the same 9-row `2024_April_X2D_1742` holdout. Hard filtering is not the
answer: `signal_dominated` training reaches about **0.112%** holdout median raw
MAE recovery, `signal_or_mixed` reaches about **0.119%**, and unfiltered
X2D-only training reaches about **0.149%**. The SNR audit is therefore useful
for diagnosis and future weighting, but dropping noise-floor rows outright
hurts this small X2D target. The next objective should use camera/SNR-aware
loss weighting or multitask uncertainty rather than binary row removal.

The first matched SNR-weighted U-Net probe batch then tested that next
hypothesis without removing rows:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/index.html
```

Broad weighting still trails the unfiltered branch: `signal_emphasis` reaches
about **0.135%** holdout median raw MAE recovery and `continuous_snr` reaches
about **0.129%**. The only positive control is narrow
`noise_floor_downweight`, which reaches about **0.153%** on the same 9-row X2D
scene holdout. That is a useful direction signal, but not a promotion result:
RMSE remains negative and the gain is too small to change the blocker. The next
teacher should keep the noise-floor downweight as a conservative training
prior, then move to a stronger CFA-aware objective with camera/PSF conditioning
and spatial plus Fourier losses.

Two immediate follow-up controls tested whether the weak branch was missing
candidate-side HF input or simple context capacity:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/index.html
```

Both are rejection evidence. Adding stored `candidate_raw_hf_cfa4` to the same
noise-floor-weighted U-Net regresses the held-out X2D scene to about
**0.110%** median raw MAE recovery. A broader pyramid U-Net without stored HF
also trails the small U-Net baseline at about **0.131%**. This narrows the
blocker further: the current candidate-only HF/context statistics and simple
capacity increase are not enough; the next pass needs a different raw-detail
teacher/target treatment, not another stored-HF or pyramid repeat.

A raw-target SNR audit now compares the deduplicated raw-CFA residual target to
the calibrated camera noise sidecars:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_target_snr_audit_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_target_snr_audit_20260701/raw_target_snr_audit.json
```

All 117 deduplicated rows have sidecar coverage. The result is mixed by camera:
X2D is mostly signal-dominated, with 59/81 rows classified as above the noise
floor and a median target RMSE/noise-sigma ratio of about **5.34x**; Z8 is
mostly noise-floor/mixed, with 28/36 rows at the noise floor and a median
target RMSE/noise-sigma ratio of about **0.48x**. Overall counts are 59
signal-dominated, 39 noise-floor, and 19 mixed rows. The next teacher should
therefore not use a single unweighted residual objective across both cameras:
use noise-aware row weighting/filtering or camera-specific target treatment
before another architecture scale-up.

A target-distribution audit now quantifies the X2D scene mismatch directly:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_distribution_audit_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_distribution_audit_20260701/target_distribution_audit.json
```

The hard `2024_April_X2D_1742` holdout is not outside the training maximum,
but it is a high-energy split: median target absolute residual is about
**3.45x** the X2D train median, and **6/9** holdout rows are above the train
p90. That explains why the small U-Net can move MAE only slightly while many
candidate-only feature/capacity variants regress. The next teacher should
either normalize or model this scene-energy/domain shift explicitly, add more
matched high-energy X2D raw targets, or change the target construction so the
held-out residual is not treated as a generic row from the same distribution.

A CFA-aware target control and a matched CFA-conditioned U-Net then tested the
new crop-local CFA metadata directly:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_target_control_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_cfa_matched_unet_w32_1200_20260701/index.html
```

The non-CFA control exactly reproduces the matched **0.153%** median raw MAE
recovery on the regenerated CFA-aware target, so the target rebuild did not
change the baseline arrays. Adding simple CFA one-hot planes is still positive
but worse at about **0.100%** median raw MAE recovery. CFA metadata remains
important for normal-Bayer compatibility, but this simple one-hot conditioning
should not be repeated as the primary still-SR quality path.

A matched global-context U-Net then tested whether the older small
global-context probe was underpowered rather than the wrong direction:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/index.html
```

It uses the same X2D scene holdout, regenerated deduplicated CFA-aware target,
train-camera filter, noise-floor weighting, seed, and bounded eval as the
**0.153%** U-Net baseline. The best probe checkpoint lands at **0.149%**
median raw MAE recovery and **-0.0049%** median RMSE recovery. That improves
RMSE versus the 0.153% noise-floor baseline but trails it on MAE, so simple
global-context branch scale-up is recorded as a rejection, not a promotion.

A non-box PSF/CFA NAF diagnostic then tested whether a known asymmetric 2x
kernel signal plus CFA metadata changes the X2D result:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/index.html
```

It uses the known-kernel validation weights `[0.52, 0.23, 0.17, 0.08]` as an
explicit global PSF conditioning signal, not as a production sidecar. The best
probe checkpoint lands at **0.130%** median raw MAE recovery and **0.0025%**
median RMSE recovery. That beats the corrected X2D-scene NAF rejection but
still trails the **0.153%** small U-Net branch, so the actionable conclusion is
not "use a fixed synthetic PSF"; it is that real row-level PSF/camera variation
is still needed before PSF conditioning can be expected to move the pillar.

Two direct target-energy weighting controls then tested whether simple
train-time row weighting closes that mismatch:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/index.html
```

Both trail the small noise-floor-only U-Net baseline: high-energy emphasis
reaches about **0.118%** holdout median raw MAE recovery and inverse-energy
normalization reaches about **0.133%**, versus **0.153%** for the current best
small U-Net branch. The distribution audit is still the right blocker, but it
cannot be fixed by a scalar row-weighting policy alone.

A matched Fourier/band-loss objective control then tested whether adding
explicit multiscale residual-band consistency and FFT-magnitude loss to the
same X2D-scene U-Net would improve detail placement:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/index.html
```

Both regress the hard X2D scene holdout. The heavier objective reaches about
**-0.386%** median raw MAE recovery, and the lighter objective reaches about
**-0.139%**, versus **0.153%** for the noise-floor-only U-Net. The next pass
should change target construction, input context, or teacher capacity, not add
another scalar spatial/Fourier loss term to the current small U-Net.

Candidate-HF target scaling then tested whether the model should learn a
normalized residual and rescale output from runtime-safe candidate high-frequency
energy:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/index.html
```

The policy is runtime-safe because it uses candidate raw-HF energy only, but it
also trails the current baseline. Full-strength scaling reaches about
**0.052%** median raw MAE recovery, and half-strength scaling regresses to about
**-0.137%**, versus **0.153%** for the noise-floor-only U-Net. The hard X2D
scene mismatch is therefore not solved by scalar target-energy weights,
spatial/Fourier scalar losses, or candidate-HF scalar output normalization.

A non-scalar target-representation control then tested whether the model should
predict source raw HF directly and convert that prediction back to residual
space using runtime candidate HF:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200_20260701/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200_20260701/index.html
```

Both are strong rejections. Predicting full source HF without stored candidate
HF regresses the hard X2D holdout to about **-241.62%** median raw MAE recovery;
adding stored candidate HF as an input regresses further to about **-862.69%**.
That narrows the failure: the current U-Net cannot be rescued by replacing the
residual target with full-HF reconstruction, even when candidate HF is exposed.
The next pass should keep residual-space scoring and move to a stronger
CFA-aware teacher/objective with camera/noise/PSF conditioning or a learned
multiscale prior, rather than asking the small U-Net to synthesize all source
HF directly.

A matched frame-context control then tested whether the current best
noise-floor U-Net branch improves when it receives runtime-safe crop position,
camera one-hot, full-crop raw statistics, and candidate-HF statistics:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_framectx_noisefloor_unet_w32_1200_20260701/index.html
```

It also rejects the current small-U-Net direction. The hard X2D scene holdout
reaches only **0.001%** median raw MAE recovery and **-0.068%** median raw
RMSE recovery, versus **0.153%** MAE for the matched noise-floor baseline.
That rules out simple scalar frame/camera/crop-stat concatenation as the
missing ingredient for this branch.

The first raw-CFA residual trainer is:

```text
tools/cnn/train_premium_still_sr_raw_cfa_residual.py
```

Runtime inputs are candidate-only: candidate raw CFA planes, candidate
same-color highpass features, deterministic crop/EV coordinates, and optional
camera/ISO noise-sidecar scalars. Source raw is used only to create the
training target.

Current receipts:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/train_receipt.json
```

The stabilized w32/2000-step pass is mildly positive on held-out Z8, with
about 0.50 percent median raw-residual MAE recovery. The matched X2D holdout is
still negative at about -0.21 percent. A quick per-plane highpass linear
baseline did not explain the missing residual either. The current blocker is
therefore not a simple highpass scale/addback; with the later SNR audit, it is
now narrowed to camera-dependent target/objective quality plus X2D/domain
generalization and insufficient raw residual recovery.

The next X2D probes narrowed that further:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w48_1600_abs6_patch256_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_context_w40_1800_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextstoredhf_w40_1800_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_bandloss_w40_1800_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_x2donly_w48_2200_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_camera_balanced_w48_2200_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextpad32_w48_1200_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_earlyselect_20260701/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_framectx_unet_w32_1200_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_framectx_unet_w32_1200_20260630/train_receipt.json
```

The wider/block17 raw-target pass makes the hard X2D holdout barely positive
at about 0.02 percent median raw-residual MAE recovery, but that is still not a
promotable result. Feeding the stored `candidate_raw_hf_cfa4` feature directly
does not solve the holdout and remains negative at about -0.17 percent. A
naive calibrated-noise soft-threshold target is also negative, so simply
subtracting one sigma of sidecar noise removes useful structure and is not the
production noise/signal separation policy. A follow-up larger-patch
high-residual-weighted pass (`w48`, 1600 steps, 256 px patches,
`target_abs_weight=6`) is also rejected: train median raw-residual MAE recovery
falls to about -2.76 percent and the hard X2D holdout falls to about -0.65
percent. A first pooled raw-context feature pass is also rejected: it is
runtime-safe and uses candidate raw plus deterministic context features, but
the hard X2D holdout remains negative at about -0.33 percent median MAE
recovery. An X2D-only train-domain probe also fails: it trains on 216 X2D rows,
holds out 27 rows from `2024_April_X2D_1742`, and still lands at about -0.15
percent median holdout recovery. A combined stored-HF plus pooled-context
feature pass also fails: it trains on 324 rows, holds out the same 27 X2D rows,
and lands at about -0.43 percent median holdout recovery while also regressing
the training split to about -0.70 percent. A camera-balanced sampler pass with
the same candidate-only runtime contract also regresses the hard X2D holdout,
landing at about -0.45 percent median raw-residual MAE recovery and about
-0.50 percent median RMSE recovery. A first 32 px context-padding pass also
stays negative on the hard X2D holdout at about -0.16 percent median MAE
recovery and -0.31 percent median RMSE recovery, despite using only
candidate-side runtime inputs. That rules out "just emphasize
larger residuals and larger local patches", "add simple pooled context planes",
"combine stored-HF with pooled local context", and "route to an X2D-only
version of the same local objective" as the next path. A simple multiscale
residual-band loss objective also fails: it trains on 324 rows, holds out the
same 27 X2D rows, and lands at about -0.54 percent median holdout recovery.
A bounded small U-Net/multiscale architecture probe is the first candidate in
this raw-domain branch to move the hard X2D holdout directionally positive:
1200 steps, width 32, 32 px context padding, candidate-only runtime inputs,
about 0.10 percent median raw-residual MAE recovery, and about 0.02 percent
median RMSE recovery. That is useful evidence for multi-scale structure, but
it remains far below promotion. A diagnostic early-selection variant of the
same U-Net evaluates the first 27 holdout rows during training and saves the
best probe checkpoint. That run selects step 1100 and raises the hard X2D
holdout to about 0.13 percent median raw-residual MAE recovery, but it still
does not beat the best 0.16 percent X2D smoke-row result and remains far below
the 15 percent promotion gate. This rules out "we only saved the wrong final
step" as the primary blocker. Adding runtime-safe absolute crop-position,
camera one-hot, and full-crop candidate raw/HF scalar context to that U-Net
does not improve the result: the X2D holdout lands at about 0.09 percent
median raw-residual MAE recovery, and the matched Z8 holdout lands at about
0.19 percent versus the existing 0.50 percent Z8 raw-CFA residual baseline.
The first true full-crop sample-mode probe also exists:
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_unet_w16_160_20260630/train_receipt.json`.
It trains on whole target crops, uses candidate-only runtime inputs, and holds
out the hard `2024_April_X2D_1742` scene. It reaches about 0.06 percent median
raw-residual MAE recovery on that holdout, about 0.006 percent median RMSE
recovery, and regresses the training split by about -0.20 percent median MAE.
That keeps full-crop sampling as useful evidence, but not a promotion path.
The bounded full-crop stored-HF/context U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_contextstoredhf_unet_w24_360_20260630/train_receipt.json`
combines whole-crop training with candidate-only stored-HF and pooled candidate
context, but reaches only about 0.02 percent median MAE recovery and about
0.001 percent RMSE recovery on the same hard X2D holdout. The next candidate
spectral-loss full-crop U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_spectral_unet_w24_420_20260630/train_receipt.json`
adds a global FFT-magnitude residual loss, but reaches only about 0.03 percent
median MAE recovery and regresses the training split. A larger full-crop
raw-context U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_fullcrop_rawcontext_unet_w32_900_20260630/train_receipt.json`
uses scene-balanced full-crop samples, pooled candidate raw/HF context planes,
global candidate raw scalars, and candidate-only runtime inputs. It also fails
promotion by a wide margin: the hard X2D holdout reaches only about 0.056
percent median raw-residual MAE recovery and about 0.005 percent median RMSE
recovery after 900 steps. A deeper gated pyramid U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_pyramid_rawcontext_w24_700_20260630/train_receipt.json`
adds a third encoder scale plus channel gates while keeping the same
candidate-only full-crop raw-context policy. It is also rejected: the hard X2D
holdout reaches only about 0.031 percent median raw-residual MAE recovery and
about 0.003 percent median RMSE recovery after 700 steps. A bounded
global-context U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_globalctx_unet_w24_500_20260630/train_receipt.json`
adds a downsampled full-crop feature-map branch and scene-balanced full-crop
training while keeping candidate-only runtime inputs. It is also rejected:
the hard X2D holdout reaches only about 0.0166 percent median raw-residual MAE
recovery and about 0.0015 percent median RMSE recovery after 500 steps, below
the earlier small U-Net diagnostic best. A follow-up masked-context
global-context U-Net probe at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_maskedctx_globalctx_w24_420_20260630/train_receipt.json`
randomly hides candidate detail blocks during training while evaluating with
normal candidate-only runtime inputs. It is also rejected: the hard X2D
holdout reaches only about 0.0025 percent median raw-residual MAE recovery and
about -0.0002 percent median RMSE recovery after 420 steps. The next candidate
should use a materially different runtime signal, teacher/detail prior, or
target/objective, not just the
stored-HF feature, simple noise thresholding, local loss-weight tuning,
pooled-context feature concatenation, combined local feature concatenation,
simple band-loss reweighting, camera-domain filtering, camera-balanced
sampling, small context padding, a small U-Net alone, or frame-context scalar
planes alone, bounded full-crop sampling alone, or bounded full-crop
stored-HF/context U-Net training, or bounded full-crop spectral-loss U-Net
training, bounded full-crop raw-context U-Net training, or a deeper gated
pyramid U-Net, global-context U-Net, or training-only random context masking
over the same runtime features.

A later matched global-context U-Net on the current X2D-scene/noise-floor
baseline reaches about 0.149 percent median raw MAE recovery and about -0.0049
percent median RMSE recovery at
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/train_receipt.json`.
That still trails the 0.153 percent small U-Net branch on MAE, confirming that
the blocker is not just the older global-context smoke being too small.

A non-parametric patch-dictionary probe now tests whether the missing residual
is at least recoverable through candidate-only nearest-neighbor retrieval:
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_patch_dictionary_x2dholdout_20260630/patch_dictionary_probe.json`.
It builds 5,832 training residual patches from non-holdout scenes, indexes them
with candidate raw/HF patch statistics plus deterministic crop/EV metadata, and
uses no source/REF content at holdout runtime. This also fails: the hard X2D
holdout median raw-residual MAE recovery is about -0.80 percent and median
RMSE recovery is about -0.72 percent. That rules out a simple retrieval prior
over the current candidate features.

A bounded candidate-signal audit now tests whether low-order runtime-safe
candidate raw/HF/metadata features contain a linearly recoverable version of
the missing residual:
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_signal_x2dholdout_20260630/index.html`.
It samples the same 351-row raw-CFA residual target set, holds out
`2024_April_X2D_1742`, and fits a ridge probe from candidate raw/CFA,
candidate same-color HF, crop/EV/camera metadata, and CFA plane ID. The probe
uses no source raw, REF, or JPEG content at runtime. It also fails: the hard
X2D holdout lands at about -0.29 percent median raw-residual MAE recovery and
about -0.55 percent median RMSE recovery. That rules out a low-order
candidate-signal readout over the current targets as the next primary path.
The same probe now also supports narrower same-scene crop holdouts. Holding out
only the `grid3_01_01` center crop from `2024_April_X2D_1742` while training
on all other rows, including neighboring crops from the same scene, regresses
the center rows to about -3.67 percent median MAE recovery:
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_signal_x2d1742_center_same_scene_20260701/index.html`.
That argues the current low-order candidate-side features are not enough even
with same-scene neighboring context; the blocker is not only the scene-held-out
split.
The next stronger runtime-safe linear baseline is a per-CFA-plane
frequency-domain filter from candidate highpass raw planes to the same raw-CFA
residual target:
`/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_frequency_filter_x2d1742_center_same_scene_20260701/index.html`.
It also fails on the same X2D center-crop split, landing at about -4.29 percent
median MAE recovery. That argues the missing residual is not recoverable by a
simple frequency response from candidate HF, even when neighboring crops from
the same scene are available.
The next path needs a different runtime signal, a materially different
target/objective, or a stronger learned generative/detail prior rather than
nearest-neighbor transfer, a linear readout of current raw-CFA residual
patches, or a per-frequency candidate-HF filter.

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
- `tools/cnn/train_premium_still_sr_hf_residual.py --model-arch raw_cfa_dilated_gated --feature-mode rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright`
  keeps the same no-REF feature contract, but adds dilated raw-CFA and trunk
  blocks to test whether broader local context fixes the weak scene holdouts.

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

The first larger-context raw-CFA pass has also been run with matched training
hyperparameters:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_z8holdout_matched_w48_1000_20260630/train_receipt.json
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_x2dholdout_matched_w48_1000_20260630/train_receipt.json
```

The dilated raw-CFA gate improves the weaker held-out Z8 median MAE recovery
from 1.04 percent to about 1.30 percent, but it does not beat the X2D gated
baseline: 2.86 percent versus 2.92 percent. Its worst rows are also worse,
with negative outliers on both holdouts. This rules out "add simple dilated
context to the current rendered-residual target" as the production path by
itself. The next model must use a stronger raw-domain/noise-cleaned target and
model, then run the full 50 MP / 100 MP still/editor-latitude promotion gate.

## Noise-Clean Target Sweep

The target builder now has an explicit opt-in target-cleaning mode:

```sh
python3 tools/cnn/build_premium_still_sr_hf_residual_targets.py \
  --target-cleaning conservative_noise_floor \
  --noise-sidecar /path/to/gpr.camera_noise_calibration.v1.json
```

This mode does not blur the target. It soft-shrinks only low-texture
high-frequency residuals that are inside a calibrated darkframe noise floor,
and each row records the changed fraction, removed absolute mean, and removed
energy fraction. The default remains `--target-cleaning none`.

The first sweep dashboard is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_clean_sweep_x2d_smoke_20260630/index.html
```

It uses the existing X2D raw-CFA smoke target and the validated ISO 200 X2D
sidecar. The result is important: calibrated sensor noise is much smaller than
the current HF residual. With render-domain gain 1, the median changed fraction
is about 0.17 percent and removed residual energy is effectively zero. With
gain 16, the median changed fraction rises to about 11.93 percent, but median
removed residual energy is still only about 0.24 percent. Gain 32 changes about
34.53 percent of pixels and starts to look too aggressive for a first promoted
target policy.

Conclusion: calibrated noise cleaning should remain in the target contract as a
guardrail, especially for high-ISO X2D/Z8 scenes, but ISO 200 noise removal by
itself will not close the still-SR gap. The next production experiment should
move the supervision closer to raw-domain signal/detail placement rather than
expecting noise removal to make the existing rendered-residual target easy.

## Raw-CFA Residual Audit

The raw-CFA residual audit tests the next target direction directly:

```sh
python3 tools/cnn/audit_premium_still_sr_raw_cfa_residual.py \
  --target-receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_audit_20260630
```

Current dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_audit_20260630/index.html
```

The audit compares rendered HF residual supervision against the editable raw
target: source raw minus candidate raw, high-passed without mixing 2x2 CFA
phases. Across the expanded 351-row / 13-scene X2D+Z8 target set, median
absolute rendered-to-raw residual correlation is 0.691 and median best-phase
correlation is 0.922. Median same-color raw-HF residual magnitude is about
0.346x the rendered HF residual magnitude.

Conclusion: the current rendered-HF target is not the right primary training
objective, but it is meaningfully aligned with true same-color raw residuals.
The next model should train on source-minus-candidate raw CFA residuals
directly, then use rendered HF/editor-latitude dashboards as promotion review.

The trainable raw-CFA residual target has now been built:

```sh
python3 tools/cnn/build_premium_still_sr_raw_cfa_residual_targets.py \
  --target-receipt /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701
```

Current target dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/index.html
```

The output NPZ contains:

- `candidate_raw_cfa4`
- `candidate_raw_hf_cfa4`
- `raw_hf_residual_cfa4`
- `source_raw_hf_cfa4`
- `render_hf_residual_y`

It covers the same 351 rows / 13 scenes. Median same-color raw-HF residual
magnitude is 0.001478, median raw/render HF magnitude ratio is 0.346, and
median rendered-to-raw residual absolute correlation remains 0.691. The
refreshed build also records crop-local CFA phase for every row from source DNG
metadata, so it is now the intended input for the next premium still-SR
training pass.

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
