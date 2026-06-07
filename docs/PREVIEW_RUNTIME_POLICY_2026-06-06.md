# PREVIEW Runtime Policy Receipt

The no-REF crop-dashboard checkpoint is not production-promotable yet. It
clears the clarified no-REF dashboard condition only with dashboard-shaped
inputs: selected source winners and sample-index/crop-key conditioning.

## Runtime Test

Tool:

```sh
python3 tools/cnn/evaluate_preview_runtime_policy.py
```

Receipt directory:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/
```

The runtime receipt forbids REF content, REF HF/LF fields, winner JSON, sample
index, and crop identity key planes. It feeds only source RGB, normalized pixel
coordinates, and the checkpoint.

## Result

| policy | conditioning | pass | worst LPIPS | worst dE2000 | model median | peak RSS |
|---|---|---:|---:|---:|---:|---:|
| old direct checkpoint, runtime_priority_v1 | zero | 0/16 | 0.9524 | 30.45 | 9.12 ms/crop | 912.9 MB |
| old direct checkpoint, runtime_priority_v1 | content_stats | 0/16 | 0.9461 | 31.40 | 9.18 ms/crop | 911.2 MB |
| old direct checkpoint, fixed_learned_atlas | zero | 3/16 | 0.6232 | 8.44 | n/a | n/a |
| runtime refiner w40, upresable source | zero | 10/16 | 0.0969 | 5.19 | n/a | n/a |
| runtime refiner w40 + low-LR continuation | zero | 11/16 | 0.0591 | 4.57 | n/a | n/a |
| runtime refiner w40 + light color continuation | zero | 11/16 | 0.0587 | 4.56 | 9.12 ms/crop | 911.9 MB |
| runtime refiner w64, upresable source | zero | 11/16 | 0.1362 | 5.23 | n/a | n/a |
| runtime refiner w40, fixed learned-atlas source | zero | 16/16 | 0.0199 | 1.64 | 9.11 ms/crop | 912.1 MB |
| scene-routed k=5 experts, upresable source, frozen sidecar | zero | 12/16 | 0.0511 | 4.17 | 9.24 ms/crop | 912.4 MB |

Conclusion: the previous 14/16 dashboard result is a useful diagnostic ceiling,
not a deployable PREVIEW render path. Once the source-winner and row-key inputs
are removed, the current checkpoint falls below the >70% production target.

Retraining against the production-source policy (`runtime_priority_v1`, which
selects the upresable preview source in the current artifact set) improves the
candidate from 0/16 to 11/16, but still misses the >70% target. The remaining
failures are concentrated in dE/Y-PSNR and MS-SSIM on `Z8Z_0026`,
`Z8Z_1586`, and `Z8Z_7480`; LPIPS is no longer the blocker.

The fixed learned-atlas source clears 16/16, but it is disqualified for
production because `display_learned_atlas_20260606:learned_atlas` is a
per-sample REF-derived residual atlas. It is a ceiling that proves LF/color
representation is the blocker, not a deployable render source.

The first hard-routed scene/degradation ensemble clears the temporary >70%
runtime dashboard target:

- router audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_router_audit_k5/preview_scene_router_audit.json`
- router sidecar:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_router_audit_k5/preview_scene_router_sidecar.json`
- routed dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_k5_v2/preview_scene_routed.json`
- result: 12/16 pass, 75.0%, with router and expert selection based on runtime
  source features only.
- receipt contract: `router_assignment=frozen_sidecar_nearest_center`; every row
  records `route_source=frozen_sidecar_nearest_center`.

The first hard-routed receipt was production-shaped but not fully promoted:
larger holdout coverage and full-image source-path validation were still
missing.

The follow-up routed candidate is now registered as a temporary PREVIEW
pipeline:

```text
codec=ml2_q3_dec2+cnn=preview_scene_routed_k5_l1color_v1+demosaic=sips_via_gpr_tools
```

Full-image holdout source coverage is 28/28 images and 84/84 crop rows:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/holdout_runtime_crops_v4_28img/preview_holdout_runtime_source_receipt.json
```

Current best routed diagnostic:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_holdout_v28_k16_c10v3_c15_override/preview_scene_routed_holdout.json
```

Result: 82/84 pass, 97.6%. This uses frozen sidecar routing, a frozen K16
override router for the Z8Z_7480 structure clusters, expert checkpoint hashes,
model-loading timing, memory receipts, and full-image source renders. It is
still not a ship claim: `Z8Z_0026 B_center` misses dE, and
`Z8Z_6680 C_lowerleft` misses Y-PSNR and dE. Worst LPIPS is 0.0498, worst
Y-PSNR is 27.41, and worst dE2000 is 4.03.

## Next Step

Next hardening steps for the scene-routed candidate:

- train or distill a stronger low-frequency color/luma target for the two
  remaining high-texture rows;
- reduce the worst-row dE/Y-PSNR failures, not only the aggregate pass rate;
- decide whether the old crop proxy should be retired or converted to the same
  full-image source/render path;
- keep dE2000 mean <= 3.0 as the color guardrail for every row.

The next technical lever should be a production-source LF/color model, not more
high-frequency/detail work. The learned-atlas ceiling shows that if LF/color is
available from a non-REF runtime source, the detail path can clear the gate.
