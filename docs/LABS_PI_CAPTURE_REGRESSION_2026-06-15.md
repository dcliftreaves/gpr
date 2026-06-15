# Pi 5 Half-Res Capture Regression - 2026-06-15

## Summary

The latest strict Pi 5 stand-in target receipt at commit
`0dd6660ca478ac9892b014559d3444853663c54b` proves `.gvid` validity, zero
dropped frames, and interrupted-tail recovery, but it does not meet the
half-res 24 fps capture target.

Current strict receipt:

- path:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json`
- frames requested/written: 14,400 / 14,400
- drops: 0
- median frame time: 50.04 ms
- median throughput: 19.98 fps
- p95 frame time: 66.01 ms

Historical comparison:

- path: `docs/pi5_bench_2026-05-26.md`
- branch/commit: `fix/multilevel-cascade-regression` at `be0328a` plus
  downstream changes
- median frame time: 40.11 ms
- median throughput: 24.93 fps
- frame count: 100

## Variant Probe

Short 300-frame probes were run on the same Pi 5 stand-in source tree using
the current clean Labs build. Each variant wrote frame payloads to the Pi SSD
and removed the temporary frame directory after measurement.

Probe artifacts:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_halfres_probe_20260615_0dd6660/pi_halfres_probe.json`
- summary:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_halfres_probe_20260615_0dd6660/pi_halfres_probe_summary.md`

| variant | result | median | note |
|---|---:|---:|---|
| baseline inline default | pass | 47.35 ms / 21.12 fps | below target |
| split tokenization | pass | 47.10 ms / 21.23 fps | best stable probe |
| pinned inline | pass | 47.72 ms / 20.95 fps | below target |
| split + pinned | pass | 47.88 ms / 20.88 fps | below target |
| no streaming | pass | 51.52 ms / 19.41 fps | slower |
| producer unpack | abort | 96.11 ms / 10.40 fps | `free(): invalid next size (normal)` |
| split + producer unpack | abort | 99.22 ms / 10.08 fps | `free(): invalid next size (normal)` |

## Finding

The current clean Labs build does not recover the historical 24.93 fps result
by toggling inline tokenization, producer unpack, streaming mode, or pinning.
The best stable probe remains roughly 18 percent slower than the historical
median.

Producer unpack is not a viable immediate performance knob in this build
because both producer-unpack variants abort after frame output with heap
corruption.

## Next Boundary To Test

The remaining likely causes are:

1. code regression between the historical `be0328a` downstream build and the
   current clean Labs build,
2. benchmark-methodology difference between a 100-frame historical run and the
   strict 10-minute `.gvid` receipt,
3. target-environment difference such as thermal state, filesystem behavior,
   CPU governor, or build flags,
4. encoder-side regression in the producer/unpack path, which currently aborts.

Next step: build or recover the historical `be0328a` benchmark on the Pi and
run the same 300-frame variant probe against both commits under one runner.
That will separate code regression from target/environment and methodology.
