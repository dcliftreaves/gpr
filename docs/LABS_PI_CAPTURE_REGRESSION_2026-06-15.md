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

## Next Boundary To Test

The remaining likely causes are:

1. missing downstream changes from the original unsanitized `be0328a` build,
2. code-level throughput regression before the historical bench-note commit
   that was not preserved as a committed source delta,
3. encoder-side corruption in the producer/unpack path, which currently aborts
   on both comparison commits.

Next step: recover the original downstream `be0328a` worktree if it still
exists, or treat the May 26 number as non-reproducible and profile the current
encoder hot path directly. The production target remains >= 24 fps sustained;
today's best evidenced current-build knob is 22.53 fps median on a 100-frame
probe and 19.98 fps median on the strict 10-minute receipt.
