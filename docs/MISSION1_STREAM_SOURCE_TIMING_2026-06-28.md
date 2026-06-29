# Mission 1 Stream Source Timing

Last refreshed: 2026-06-28

This note records the first Pi 5 runs for the deterministic source-to-encoder
handoff harness. These are stand-in runs, not Mission 1 camera evidence.

## Receipts

Compact receipts were copied back to:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/mission1_stream_source_encoder_20260628_pi_compact
/Volumes/OWC_8TB/gpr_work/artifacts/bench_fused_stream_source_20260628_pi_compact
```

Heavy `.gvid` payloads remain on the Pi SSD under:

```text
/mnt/ssd/gpr_work/artifacts/mission1_stream_source_encoder_20260628_pi
/mnt/ssd/gpr_work/artifacts/bench_fused_stream_source_20260628_pi
```

## Results

| mode | source shape | result |
|---|---|---:|
| file-backed shim baseline | one preloaded repeated 4096 x 3072 frame through `labs_encoder_bench_cli` | 22.02 fps median / 22.06 fps mean |
| FIFO stream | deterministic changing frames copied through POSIX FIFO | 14.56 fps wall |
| SSD mmap ring | deterministic changing frames through bounded mapped ring on `/mnt/ssd` | 16.70 fps wall |
| RAM mmap ring | deterministic changing frames through bounded mapped ring in `/dev/shm`, `.gvid` on `/mnt/ssd` | 16.41 fps wall |
| production `bench_fused` mmap ring, synthetic copy producer | changing synthetic frames through FLL2 profile and `GPR_BENCH_MMAP_RING_INPUT=1` | 17.67 fps wall |
| production `bench_fused` mmap ring, actual GP017602 copy producer | actual 4096 x 3072 Mission raw replay copied into the ring each frame | 16.78 fps wall |
| production `bench_fused` mmap ring, actual GP017602 ready-only producer | actual Mission raw preloaded in the ring, producer publishes ready counters to approximate DMA-owned buffers | 19.99 fps wall over 1,440 frames |

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
`.gvid` path, not the Labs shim streaming path. It narrowed the next engineering
gap: the production FLL2 direct encoder path needed a streaming or DMA-ring
source harness, or the Labs shim had to be retuned to use the same production
FLL2 path and measured again. The first part is now implemented in
`bench_fused` behind `GPR_BENCH_STREAM_INPUT=1` and
`GPR_BENCH_MMAP_RING_INPUT=1`, with CI smoke coverage in
`tools/test/test_bench_fused_stream_source.sh`. A Pi 5 production-path stand-in
receipt now exists at
`/Volumes/OWC_8TB/gpr_work/artifacts/bench_fused_stream_source_20260628_pi_compact/receipt_4096x3072_1440f_20fps_mmap_ready_fll2_GP017602_replay.json`.
It records 1,440 valid 4096 x 3072 frames, zero stream drops, 19.990 fps wall,
45.67 ms median encode+write, and 7.88 GB of validated `.gvid` payload.

## Next Step

Do not spend more time optimizing FIFO mechanics. The next useful step is:

1. Compare the ready-only DMA-like source receipt against the existing
   file-backed FLL2 receipts:
   `artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/labs_target_bench.json`.
2. If CPU-copy producer behavior matters for a specific firmware integration,
   optimize or replace the producer copy path; it is currently an artificial
   stand-in cost, not a sensor DMA cost.
3. Keep the camera claim blocked until a real Mission 1 `target.role=camera`
   source/storage/display receipt exists.
