# PREVIEW Scene Router Research

Question: should PREVIEW run a scene/degradation classifier before the CNN and
select one of several specialist CNNs?

## Short Answer

Yes, but implement it as a runtime degradation/content router with shared
guardrails, not as a brittle human scene-label switch. The literature supports
specialized experts for heterogeneous image restoration, but the router must use
render-available inputs only and must be trained/evaluated with the same gate as
the experts.

## Relevant Prior Work

- Mixture-of-experts super-resolution is an active direction. Recent Real-ISR
  work routes degraded images to sparse experts using degradation-aware routing,
  shared experts, and load-balancing/zero-expert mechanisms so easy samples do
  not pay for all experts.
  - https://ojs.aaai.org/index.php/AAAI/article/view/42469
- Multi-category super-resolution papers explicitly call out the two classic
  options: separate CNNs per category with a classifier, or one shared CNN. A
  multi-task category head can improve SR by letting category information shape
  the restoration features.
  - https://www.jstage.jst.go.jp/article/transinf/E104.D/1/E104.D_2020EDP7054/_article
- Blind / multi-degradation SR work shows that one model trained for a single
  assumed degradation can fail badly when the real degradation differs. For this
  project that maps to codec source, ISO/noise, texture density, and demosaic
  color failure mode, not just semantic labels like "sky" or "hair".
  - https://arxiv.org/abs/1712.06116
- Neural compression work supports content-adaptive behavior, but decoder-side
  cost and transmitted state matter. A PREVIEW router should therefore be
  deterministic from the decoded source and cheap enough to run before CNN
  inference.
  - https://openaccess.thecvf.com/content_CVPRW_2019/papers/CLIC%202019/Campos_Content_Adaptive_Optimization_for_Neural_Image_Compression_CVPRW_2019_paper.pdf
  - https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136780545.pdf

## Project Guidance

Use 5-10 experts only after the data supports that many clusters. Start with
3-5 runtime-derived clusters:

- low-frequency/color risk: large Lab mean/std drift, low Y-PSNR risk;
- fine texture/high HF: hair, foliage, rock, saturated texture;
- smooth gradients/sky: banding and chroma sensitivity;
- dark/high-ISO/noise: noise/signal separation risk;
- edge/line content: ringing and MS-SSIM risk.

Router inputs must be available at render time:

- decoded/upresable RGB or Bayer-derived display proxy;
- ISO/noise metadata if available in the container sidecar;
- cheap feature statistics: luma/chroma histograms, HF energy, edge density,
  saturation, dark fraction, local contrast, source codec mode.

Do not route using:

- REF pixels or REF-derived LF/HF/noise fields;
- gate metrics against REF;
- image IDs, crop IDs, sample indices, or dashboard winner JSON.

## Production Stop Criteria

The router path is promotable only if:

- router + selected expert runs from runtime inputs only;
- every expert has a checkpoint hash and training config;
- routing decisions are logged per crop/frame in the dashboard;
- the routed ensemble clears >70% on the PREVIEW runtime dashboard;
- dE2000 mean stays <= 3.0 for every row;
- timing includes router + model, and memory includes the largest loaded expert
  set or the explicit model-loading policy.

## First Implementation Step

Build a router audit that clusters current PREVIEW failures using runtime
features and reports which rows each expert would own. Then train specialist
experts per cluster and compare:

1. single runtime refiner baseline;
2. hard-routed specialists;
3. top-2 blended specialists if hard routing causes boundary artifacts.

Hard routing is simplest for a camera pipeline, but top-2 blending should stay
on the table if adjacent clusters disagree visually near boundaries.

## First Audit Result

Tool:

```sh
python3 tools/cnn/build_preview_scene_router_audit.py
```

Receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_router_audit_k5/preview_scene_router_audit.json
```

The first k=5 audit used only source RGB features from the upresable preview
crop set. It did not use REF pixels, gate metrics, image ID, crop ID, or winner
JSON as router inputs. Gate metrics were used only to label clusters after the
fact.

| cluster | suggested expert | count | failures | failed rows |
|---:|---|---:|---:|---|
| 0 | dark_noise_risk | 3 | 0 | none |
| 1 | general_lf_color | 4 | 3 | `Z8Z_0026:center`, `Z8Z_0026:upper_left`, `Z8Z_7480:center` |
| 2 | dark_noise_risk | 5 | 0 | none |
| 3 | saturated_color_risk | 2 | 1 | `Z8Z_1586:center` |
| 4 | general_lf_color | 2 | 1 | `Z8Z_7480:upper_left` |

Interpretation: the runtime features already separate several always-passing
regions from the current misses. The immediate specialist target should be
LF/color experts for clusters 1 and 4, plus a saturated-color expert for
cluster 3. Clusters 0 and 2 should probably route to the shared/default expert
until they show failures on a larger corpus.

## First Routed Ensemble

Receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_k5_v1/preview_scene_routed.json
```

Experts:

- default: `runtime_refiner_priority_zero_cont_colorlight`;
- cluster 1: `scene_expert_cluster1_lf_color`;
- cluster 3: `scene_expert_cluster3_saturated`;
- cluster 4: `scene_expert_cluster4_lf_color`.

Result:

| candidate | pass | worst LPIPS | worst MS-SSIM | worst Y-PSNR | worst dE2000 | model median | peak RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| single runtime refiner | 11/16 | 0.0587 | 0.8706 | 27.49 | 4.56 | 9.12 ms/crop | 911.9 MB |
| scene-routed k=5 v1 | 12/16 | 0.0511 | 0.9115 | 28.61 | 4.17 | 9.21 ms/crop | 913.3 MB |

The routed ensemble clears the temporary >70% runtime dashboard target. The
remaining four failures are:

- `Z8Z_0026:center`: dE still high;
- `Z8Z_1586:center`: dE still high;
- `Z8Z_7480:center`: MS-SSIM still low;
- `Z8Z_7480:upper_left`: MS-SSIM still low.

This validates the multi-expert direction enough to continue, but it is not a
ship pipeline until the router sidecar, larger holdout, full-image path, and
model-loading policy are hardened.
