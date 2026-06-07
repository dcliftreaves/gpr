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
| scene-routed k=5 experts, upresable source | zero | 12/16 | 0.0511 | 4.17 | 9.21 ms/crop | 913.3 MB |

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
- routed dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/scene_routed_k5_v1/preview_scene_routed.json`
- result: 12/16 pass, 75.0%, with router and expert selection based on runtime
  source features only.

This is production-shaped but not fully promoted: it still needs larger holdout
coverage, full-image/source-path validation, and a model-loading policy before
it becomes a ship pipeline.

## Next Step

Next hardening steps for the scene-routed candidate:

- freeze the router feature schema and cluster centers as a sidecar;
- rerun on the larger holdout set and report per-cluster pass/fail;
- train specialists from more rows per cluster, not only the current 16-crop
  dashboard;
- validate full-image source/render behavior;
- define model-loading policy: preload all experts, or lazy-load per scene;
- keep dE2000 mean <= 3.0 as the color guardrail for every row.

The next technical lever should be a production-source LF/color model, not more
high-frequency/detail work. The learned-atlas ceiling shows that if LF/color is
available from a non-REF runtime source, the detail path can clear the gate.
