# Mission 1 CNN Status And Next Steps

Last refreshed: 2026-06-28

This note captures the current CNN state after the Mission 1 4K cleanup and
8K SR approval pass. It is deliberately scoped to offline/post CNN work; the
camera-side 20 fps capture and 1024 preview paths should stay CNN-free unless a
future profile proves otherwise.

## Current Status

| path | current state | boundary |
|---|---|---|
| 4K cleanup | `mission1_native12_4k_cleanup_rgb_cfa_w40_v1` has visual signoff, RGB/CFA dashboard evidence, tone audit, 4K `.gvid` packaging, and 4K ProRes review receipts. | Review/offline cleanup. It is not part of the live capture timing path. |
| 8K SR | `mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1` is promoted as an offline-production 12MP-to-8K SR path with Mission42 and Z8 broad full-frame evidence, editable packaging, metadata/receipt evidence, `.gvid`, and ProRes review receipts. | Offline/upscale path. Runtime is around 1 fps-class for decode+SR+write, so it is not live camera playback. |
| camera preview | 1024 x 768 preview remains the native decode/downsample path. | Do not insert CNN into this path until a target profile proves 20 fps and memory. |
| capture encode | 4K Bayer `.gvid` capture remains codec-only. | Do not add CNN to camera-side encode. |

## 2026-06-29 4K Cleanup Revisit

A sharper 4K cleanup candidate was trained and evaluated:

`/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_4k_cleanup_revisit_20260629/train_w48_d6_rs03_gamma3_grad3_raw1_bayer4_step1200/`

Decision: **reject for production promotion**. It improved median RGB RMSE
slightly against the high-res-derived RGB target, but it regressed the
guardrails that matter for a raw/editable 4K output:

| metric | approved 4K baseline | sharper candidate |
|---|---:|---:|
| median RGB RMSE improvement | 10.361% | 11.369% |
| median gamma RGB RMSE improvement | 10.666% | -1.842% |
| median Y-gradient improvement | 3.228% | -0.120% |
| median CFA raw RMSE improvement | 10.932% | 5.112% |
| median CFA raw MAE improvement | 9.148% | -1.415% |

Tone audit was mixed rather than decisive: 81 of 126 crop rows improved display
MAE and 45 worsened, with candidate green abs p95 at 0.01895. The raw/CFA and
gamma regressions are enough to keep the approved
`mission1_native12_4k_cleanup_rgb_cfa_w40_v1` checkpoint as the production
baseline.

## Checks Run

```bash
python3 tools/check_mission1_4k_cleanup_signoff_receipt.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json

python3 tools/check_mission1_8k_sr_production_promotion.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json

python3 tests/quality_gates/check_registry_consistency.py

python3 tools/test/test_mission1_8k_sr_production_promotion.py
python3 tools/test/test_build_mission1_8k_sr_visual_review.py
python3 tools/test/test_build_mission1_4k_visual_signoff.py
python3 tools/check_mission1_cnn_closure.py --strict-artifacts
```

All passed locally on 2026-06-28. After PR #60 merged, the checks were rerun
on `master` using the external-drive Python venv for NumPy-backed tests:

```bash
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_analyze_mission1_sr_codec_sensitivity.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_analyze_mission1_sr_phase_reconstruction.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_build_mission1_sr_coverage_manifest.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_build_mission1_sr_pairs_from_raw_dirs.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_mine_mission1_sr_hard_tiles.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_mission1_sr_pair_codec_profiles.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_mission1_sr_production_gap_report.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_raw_resolution_targets.py
/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python \
  tools/test/test_train_mission1_sr_expand.py
```

These passed. The plain system Python lacks NumPy, so use the external-drive
venv for CNN/SR tests.

`tools/check_mission1_cnn_closure.py` is the lightweight production-state guard
for the approved CNN claims. Hosted CI runs it without private artifacts; local
release checks should use `--strict-artifacts` so the external 4K signoff and
8K production-promotion receipts are validated too.

## Next Steps

1. Keep 4K cleanup as the approved review/offline 4K enhancer unless a new
   dashboard shows a clear regression or a materially better candidate.
2. Keep 8K SR on the promoted
   `mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1` path. Do not
   replace it with an experimental checkpoint unless it beats the current
   Mission42 and Z8 broad full-frame gates and keeps editable `.gvid`/ProRes
   receipts.
3. If 4K softness becomes worth another pass, train against the high-res
   RGB-area-downsample plus CFA-sampled target again, but select by full-frame
   visual/tone/raw guards rather than tile loss alone.
4. If 8K SR needs another pass, start from the current coord/detail alpha0.5
   path and use full-frame Mission42 plus Z8 all24 gate pressure. Previous
   standalone low-clean tile-loss passes were rejected because they improved
   low-source reconstruction while hurting full-frame SR blockers.
5. Keep CNN artifacts out of live camera paths. Camera-side production work
   should focus on codec timing, streaming source handoff, storage, preview
   decode, and receipts.

## Active Burn-Down

1. Treat the current 4K and 8K checkpoints as the baseline to beat, not as open
   training failures.
2. If reopening 4K cleanup, compare against high-res RGB-area-downsample plus
   CFA-sampled full-frame targets, then require visual/tone/raw guard wins.
3. If reopening 8K SR, start from the coord/detail alpha0.5 checkpoint and run
   Mission42 plus Z8 all24 full-frame gates before any promotion discussion.
4. Keep capture encode and camera-back preview CNN-free unless a target receipt
   proves 20 fps and memory headroom.

## Stop/Promotion Rule

Promote a future CNN only when all of these are true:

- checkpoint and training receipt are hash-pinned,
- broad Mission and Z8 full-frame dashboards beat the current registered path,
- worst-row visual review has no severe artifacts,
- editable `.gvid`/GPR/DNG and ProRes receipts exist,
- timing and memory are measured for the intended offline/Mac path,
- registry scope matches the claim: `offline_review_only`,
  `offline_production`, or no production scope.
