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

Producer unpack was not a viable immediate performance knob in the original
probe because both producer-unpack variants aborted after frame output with
heap corruption. The corruption cause has since been narrowed: the producer
ring emitted full channel-space rows while decimated capture allocated
half-size Pass1 buffers.

## Historical Build Reprobe

The historical benchmark commit recorded in the May 26 bench note was not
available by the original short hash in the sanitized repository. The closest
committed comparison point is `5b95db75f8a3ea21d88b530e79f54c3bb955775f`, which
is the commit that added `docs/pi5_bench_2026-05-26.md` with the 24.93 fps
result. It was built on the same Pi 5 stand-in and probed with the same
300-frame runner.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_halfres_probe_20260615_5b95db7/pi_halfres_probe.json`

| variant | current `0dd6660` | historical-doc commit `5b95db7` | finding |
|---|---:|---:|---|
| baseline inline default | 47.35 ms / 21.12 fps | 48.04 ms / 20.81 fps | both below target |
| split tokenization | 47.10 ms / 21.23 fps | 47.86 ms / 20.90 fps | both below target |
| pinned inline | 47.72 ms / 20.95 fps | 48.45 ms / 20.64 fps | both below target |
| split + pinned | 47.88 ms / 20.88 fps | 49.78 ms / 20.09 fps | both below target |
| no streaming | 51.52 ms / 19.41 fps | 52.79 ms / 18.94 fps | slower on both |
| producer unpack | abort | abort | heap corruption on both |
| split + producer unpack | abort | abort | heap corruption on both |

This reduces the likelihood that the current 19.98 fps strict receipt is caused
by a recent code regression after the historical bench note. The reproducible
blocker is now narrower: under today's Pi target environment and 300-frame
write-all methodology, both current and historical-document commits run at
about 21 fps median, not 24.93 fps.

## Controlled Environment Probe

The exact 100-frame historical command shape was repeated on the current and
historical-document commits while recording target state.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_env_probe_20260615/pi_env_probe.json`

Target state:

- CPU governor: `performance` on all cores
- CPU frequency: 2.4 GHz current/max on all cores
- throttle status: `throttled=0x0`
- storage: `/mnt/ssd` on ext4 with `rw,noatime,stripe=8191`
- temperature range during probe: 58.7 C to 70.3 C

| commit | frames | median | finding |
|---|---:|---:|---|
| current `0dd6660` | 100 | 46.76 ms / 21.39 fps | below target |
| current `0dd6660` | 300 | 46.39 ms / 21.56 fps | below target |
| historical-doc `5b95db7` | 100 | 47.59 ms / 21.02 fps | below target |
| historical-doc `5b95db7` | 300 | 47.32 ms / 21.13 fps | below target |

This rules out the simple explanations that the 24.93 fps result only appears
on the 100-frame command, or that today's failure is caused by CPU governor,
frequency scaling, thermal throttling, or obvious storage mount state.

## Runtime Knob Probe

The remaining current-build runtime knobs were swept on 100-frame write-all
runs.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_runtime_knob_probe_20260615_0dd6660/runtime_knob_probe.json`

| variant | median | finding |
|---|---:|---|
| `FUSED_STRIPE_ROWS=64` | 44.38 ms / 22.53 fps | best tested knob, still below target |
| `FUSED_STRIPE_ROWS=128` | 45.45 ms / 22.00 fps | below target |
| `FUSED_DEFER_RANS=1` | 45.57 ms / 21.94 fps | below target |
| baseline | 45.80 ms / 21.83 fps | below target |
| `FUSED_STRIPE_ROWS=16` | 46.15 ms / 21.67 fps | below target |
| `FUSED_LL2_DIVISOR=32` | 46.71 ms / 21.41 fps | below target |
| `FUSED_INLINE_TOKENIZE=0 FUSED_STRIPE_ROWS=64` | 46.76 ms / 21.38 fps | below target |
| `FUSED_USE_ASM=1` | 47.48 ms / 21.06 fps | slower |
| `FUSED_LL2_DIVISOR=8` | 47.85 ms / 20.90 fps | slower |
| `FUSED_THREADS=1` | 104.83 ms / 9.54 fps | much slower |

No runtime knob restores 24 fps. `FUSED_STRIPE_ROWS=64` is worth keeping as a
candidate optimization, but it is not sufficient for production target capture.

## Runtime Combo Probe

A follow-up 100-frame write-all sweep tested combinations of the best earlier
knobs plus nearby stripe sizes, deferred rANS, LL2 divisor changes, and quality
overrides. This used the same Release Pi build and cleaned frame payloads after
each case.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_runtime_combo_probe_20260615/runtime_combo_probe.json`

| variant | median | finding |
|---|---:|---|
| baseline | 43.97 ms / 22.74 fps | best case in this short sweep, still below target |
| `FUSED_STRIPE_ROWS=64 FUSED_DEFER_RANS=1` | 44.12 ms / 22.67 fps | below target |
| `FUSED_STRIPE_ROWS=64 FUSED_QUALITY=4` | 45.88 ms / 21.80 fps | below target |
| `FUSED_STRIPE_ROWS=64 FUSED_LL2_DIVISOR=16` | 45.98 ms / 21.75 fps | below target |
| `FUSED_STRIPE_ROWS=48` | 46.39 ms / 21.56 fps | below target |
| `FUSED_STRIPE_ROWS=64 FUSED_QUALITY=2` | 46.72 ms / 21.41 fps | below target |
| `FUSED_STRIPE_ROWS=96` | 47.12 ms / 21.22 fps | below target |
| `FUSED_STRIPE_ROWS=80` | 47.92 ms / 20.87 fps | below target |
| `FUSED_STRIPE_ROWS=64 FUSED_LL2_DIVISOR=32` | 48.52 ms / 20.61 fps | smaller payload, slower |
| `FUSED_STRIPE_ROWS=64` | 48.97 ms / 20.42 fps | below target in this run |

This narrows the capture blocker further: simple runtime tuning does not close
the gap. The remaining path is code-level reduction of Pass1 work or a
different capture-side algorithm, not another stripe/divisor/quality sweep.

## Pass 2 Dispatch Probe

The only preserved encoder source delta between the historical-doc commit and
the current Labs source, aside from the producer-decimate safety guard, is the
multi-level Pass 2 worker-pool dispatch. A compile-time probe compared the
current auto policy with forced spawn-per-band and forced worker-pool builds.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_pass2_dispatch_probe_20260615/pass2_dispatch_probe.json`

| variant | median | finding |
|---|---:|---|
| forced worker pool | 46.82 ms / 21.36 fps | best in this probe, below target |
| default auto policy | 47.91 ms / 20.87 fps | below target |
| forced spawn-per-band | 49.71 ms / 20.12 fps | slower |

This rules out Pass 2 dispatch policy as the source of the historical 24.93 fps
receipt. The worker-pool path is directionally helpful, but the remaining gap
is still in the larger Pass1/unpack budget.

## Producer-Unpack Decimate Guard

The current source now disables the shared producer ring when either
`GPR_ROW_DECIMATE=2` or `GPR_COL_DECIMATE=2` is active. That turns the formerly
corrupting `FUSED_PRODUCER_UNPACK=1` + decimated-capture combination into a
safe fallback to the normal per-channel unpack path. A CI smoke test covers
this on a small raw fixture:

- `tools/test/test_producer_unpack_decimate_fallback.sh`

Pi guard receipt:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_producer_guard_20260615/producer_decimate_guard.json`

| case | result |
|---|---:|
| baseline decimated write-all | 300/300 frames, 46.52 ms median, 21.49 fps |
| producer requested + decimated write-all | 300/300 frames, 42.03 ms median, 23.79 fps |

The guard receipt proves the formerly aborting env combination survives
300-frame write-all output. The faster producer-requested row should not be
treated as a production throughput claim because producer mode is intentionally
disabled for decimated capture in this patch and short Pi timing varies run to
run. The real throughput work remains a decimation-aware shared producer or a
different Pass1 unpack optimization.

## Decimated Producer Experiment

A scratch decimation-aware producer was tested and not committed. It reused the
existing per-channel decimation kernels inside the producer threads, emitted
correctly sized rows, and avoided heap corruption, but it was too slow to keep
as production code.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_producer_dec2_probe_20260615/producer_dec2_probe.json`

| case | result |
|---|---:|
| baseline decimated write-all | 300/300 frames, 47.47 ms median, 21.06 fps |
| producer requested fallback | 300/300 frames, 42.12 ms median, 23.74 fps |
| explicit decimated producer scratch path | 300/300 frames, 59.50 ms median, 16.81 fps |

The scratch producer was correct enough to run but architecturally wrong for
speed: it moved the same four per-channel decimation kernels into producer
threads instead of sharing log/LUT work across channels. That added producer /
consumer overhead without removing the real cost. Do not revive that shape
unless it also shares the raw-to-log work across channels.

## Combined Decimated Producer Experiment

A second scratch producer was tested to share raw-to-log work across all four
channels before emitting decimated GS/RG/BG/GD rows. The candidate produced the
same payload byte count as the baseline and avoided the prior heap corruption,
but the extra producer/consumer synchronization still outweighed the shared
work. It was not committed.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_producer_combined_probe_20260615/producer_combined_dec2_probe.json`

| case | result |
|---|---:|
| baseline decimated write-all | 300/300 frames, 47.50 ms median, 21.05 fps |
| producer requested fallback | 300/300 frames, 46.67 ms median, 21.43 fps |
| combined decimated producer scratch path | 300/300 frames, 53.20 ms median, 18.80 fps |

This rules out the current producer-ring architecture as the next speed path
for half-res capture. The remaining useful direction is to reduce Pass1 unpack
inside the active worker path itself, where shared raw-to-log work can avoid
cross-thread handoff costs.

## Timing Profile

A timing-enabled build of the current clean Labs commit was run on the Pi to
separate encode stages. The instrumentation build is not a production timing
receipt, but it identifies where the missing throughput has to come from.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_timing_probe_20260615_0dd6660/timing_probe.json`

| case | median | Pass1 mean | Pass2 mean | dominant channel cost |
|---|---:|---:|---:|---|
| baseline, no write | 46.40 ms | 38.14 ms | 7.99 ms | unpack 22.77 ms |
| baseline, write-all | 46.68 ms | 38.41 ms | 7.74 ms | unpack 22.68 ms |
| stripe64, no write | 47.11 ms | 39.67 ms | 7.73 ms | unpack 23.62 ms |
| stripe64, write-all | 44.49 ms | 35.74 ms | 7.80 ms | unpack 21.56 ms |

The profile says the blocker is not primarily `.gvid` wrapping or storage I/O
at this sample size. Multi-level Pass1 dominates the encode, and the largest
measured Pass1 component is channel unpack. The already-existing
`FUSED_PRODUCER_UNPACK=1` path was the obvious architectural candidate, but its
full-size ring is not valid for decimated capture. The guarded fallback removes
the corruption; a real speed fix requires a decimation-aware producer or
another Pass1 unpack optimization.

## Next Boundary To Test

The remaining likely causes are:

1. missing downstream changes from the original unsanitized `be0328a` build,
2. code-level throughput regression before the historical bench-note commit
   that was not preserved as a committed source delta,
3. missing in-worker Pass1 unpack optimization for the current hot path.

Next step: recover the original downstream `be0328a` worktree if it still
exists. If it cannot be recovered, treat the May 26 number as non-reproducible
and focus the current-code fix on Pass1 unpack throughput. The producer-unpack
corruption is now guarded for decimated capture, and the naive decimated
producer and combined producer scratch paths are both ruled out by timing. The
next speed experiment must share raw-to-log work in the active Pass1 worker
path or otherwise reduce unpack cost directly without producer-ring overhead.
The production target remains >= 24 fps sustained; today's best evidenced
current-build knob is 22.53 fps median on a 100-frame probe and 19.98 fps
median on the strict 10-minute receipt.
