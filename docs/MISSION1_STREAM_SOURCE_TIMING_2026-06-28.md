# Mission 1 Stream Source Timing

Last refreshed: 2026-06-28

This note records the first Pi 5 runs for the deterministic source-to-encoder
handoff harness. These are stand-in runs, not Mission 1 camera evidence.

## Receipts

Compact receipts were copied back to:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/mission1_stream_source_encoder_20260628_pi_compact
```

Heavy `.gvid` payloads remain on the Pi SSD under:

```text
/mnt/ssd/gpr_work/artifacts/mission1_stream_source_encoder_20260628_pi
```

## Results

| mode | source shape | result |
|---|---|---:|
| file-backed shim baseline | one preloaded repeated 4096 x 3072 frame through `labs_encoder_bench_cli` | 22.02 fps median / 22.06 fps mean |
| FIFO stream | deterministic changing frames copied through POSIX FIFO | 14.56 fps wall |
| SSD mmap ring | deterministic changing frames through bounded mapped ring on `/mnt/ssd` | 16.70 fps wall |
| RAM mmap ring | deterministic changing frames through bounded mapped ring in `/dev/shm`, `.gvid` on `/mnt/ssd` | 16.41 fps wall |

All stream modes wrote valid 4096 x 3072 `.gvid` files with 120/120 frames and
zero drops. All receipts remain `production_evidence=false`.

## Interpretation

The FIFO miss was not purely a pipe-copy issue. Moving the source to a bounded
mapped ring removed source wait but did not restore 20 fps. The repeated-frame
file-backed shim baseline still clears 20 fps, which means the current
firmware-facing Labs shim can look fast on a hot repeated frame but falls below
20 fps with changing stream input.

This should not invalidate the existing production codec evidence, because the
current 20+ fps Mission 1 capture claim is based on the FLL2/bench-fused direct
`.gvid` path, not the Labs shim streaming path. It does narrow the next
engineering gap: the production FLL2 direct encoder path needs a streaming or
DMA-ring source harness, or the Labs shim must be retuned to use the same
production FLL2 path and measured again.

## Next Step

Do not spend more time optimizing FIFO mechanics. The next useful step is:

1. Add streaming/mmap-ring source support to the production FLL2 direct `.gvid`
   encode path, or route the Labs shim through the same FLL2 profile.
2. Re-run 120/240/1440-frame Pi timing with changing 4096 x 3072 frames.
3. Compare against the existing file-backed FLL2 receipts:
   `artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/labs_target_bench.json`.
4. Keep the camera claim blocked until a real Mission 1 `target.role=camera`
   source/storage/display receipt exists.

