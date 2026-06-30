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
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_readiness_20260629
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
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_20260630 \
  --crop-size 768 \
  --output-bps 16 \
  --contact-rows 9 \
  --allow-common-crop
```

Current dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_x2d_latitude_review_20260630/latitude_review.json
```

Result:

| rows | median display MAE | worst display MAE | median Y MAE | median LF Y MAE | worst LF Y MAE | blocker |
|---:|---:|---:|---:|---:|---:|---|
| 9 | 0.04281 | 0.09161 | 0.02909 | 0.00546 | 0.01657 | +2 EV rows, especially bright/shadow stress and fine texture/noise mismatch |

Interpretation: metadata/openability is no longer the X2D blocker. Low-frequency
tone is much closer than full-pixel error, which points toward a combined
highlight/latitude and camera-texture/noise-addback problem rather than a
basic DNG compatibility problem. This is not a production pass.

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
