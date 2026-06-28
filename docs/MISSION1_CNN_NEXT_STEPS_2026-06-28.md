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
```

All passed locally on 2026-06-28.

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

## Stop/Promotion Rule

Promote a future CNN only when all of these are true:

- checkpoint and training receipt are hash-pinned,
- broad Mission and Z8 full-frame dashboards beat the current registered path,
- worst-row visual review has no severe artifacts,
- editable `.gvid`/GPR/DNG and ProRes receipts exist,
- timing and memory are measured for the intended offline/Mac path,
- registry scope matches the claim: `offline_review_only`,
  `offline_production`, or no production scope.

