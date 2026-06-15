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

## Pass1 Col-Decimate Prefetch Candidate

A byte-exact source candidate added the same last-cache-line row prefetch used
by the non-decimated unpack path to the active T13/T14 col-decimate unpack
helpers. A local baseline/candidate `.gpr` dump comparison was byte-identical
on a synthetic decimated fixture.

Pi probe artifacts:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_pass1_prefetch_probe_20260615/pass1_prefetch_probe.json`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_pass1_prefetch_probe_20260615/pass1_prefetch_confirm.json`

| run | variant | median | finding |
|---|---|---:|---|
| A/B | baseline | 46.10 ms / 21.69 fps | below target |
| A/B | prefetch candidate | 45.34 ms / 22.06 fps | faster, below target |
| reversed | prefetch candidate | 46.13 ms / 21.68 fps | faster, below target |
| reversed | baseline | 48.47 ms / 20.63 fps | below target |

This is a safe incremental Pass1 improvement, not a full target fix. It does
not change the production blocker: sustained half-res capture still needs
additional Pass1 work reduction or a different capture-side algorithm to reach
>= 24 fps.

## Pass1 Col-Decimate U16 Scratch Candidate

The active T13/T14 row+col-decimate unpack kernels now keep LUT results in
`uint16_t` scratch and widen directly into NEON lanes, matching the already
used pattern in the 2x2 decimate kernel. This removes avoidable 32-bit
scratch store/load traffic without changing the LUT indices or arithmetic.

Local evidence on Apple Silicon:

- baseline commit: `3d3fea6`
- byte fixtures: generated synthetic RGGB fixtures at 1024 x 768 and
  1056 x 784 under the external scratch tree
- candidate and baseline `.gpr` dumps were byte-identical:
  `0d7cb86a93d4c3a08a16fa645e1c7f31ac41b5bdb6ab40cc7d1f532dc838a93b`
  and
  `82c40fc5cc1722a82a809a26c49a253a93bd80d24b94f793eae55778d3aa37be`
- 50 MP synthetic local timing, 20 frames, no write-all:
  baseline 12.94 ms median, candidate 12.54 ms median

This is byte-exact and directionally positive locally, but it is not yet target
throughput evidence. The next receipt must run the normal Pi 5 stand-in bench
and record whether this small active-kernel reduction moves the sustained
half-res path toward 24 fps.

## GCC Flag And Rehearsal Probe

The prefetch source candidate was also built on the Pi with GCC Release flag
variants. The best short-run build used:

`-O3 -DNDEBUG -frename-registers -funroll-loops -fprefetch-loop-arrays`

Probe artifacts:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_gcc_flags_probe_20260615/gcc_flags_probe.json`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_gcc_flags_probe_20260615/gcc_flag_combos_probe.json`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_gcc_flags_probe_20260615/gcc_fast_confirm.json`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_fast_flags_runtime_probe_20260615/fast_flags_runtime_probe.json`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_fast_rehearsal_cfb63f9_20260615/labs_target_bench.json`
- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_fast_stripe48_rehearsal_c179189_20260615/labs_target_bench.json`

Short probes found promising but unstable results:

| case | median | finding |
|---|---:|---|
| fast flags + `FUSED_STRIPE_ROWS=64 FUSED_DEFER_RANS=1`, 300 frames | 40.26 ms / 24.84 fps | short-run pass |
| fast flags + `FUSED_STRIPE_ROWS=48`, 300 frames | 40.44 ms / 24.73 fps | short-run pass |
| fast flags + default runtime, repeat 300 frames | 43.41 ms / 23.04 fps | below target |

The same fast build and runtime env failed the target-bench rehearsal:

| run | frames | median | verdict |
|---|---:|---:|---|
| fast flags + `FUSED_STRIPE_ROWS=64 FUSED_DEFER_RANS=1` | 1,440 | 45.13 ms / 22.16 fps | valid `.gvid`, no drops, below target |
| fast flags + `FUSED_STRIPE_ROWS=48` | 1,440 | 44.05 ms / 22.70 fps | valid `.gvid`, no drops, below target |

This rules out promoting the GCC flag/runtime combination as production target
evidence. It can remain a future build-tuning lead, but the current evidence
does not support changing the committed Pi build flags or claiming >= 24 fps.

## NEON Compare Probe

A no-NEON build was tested because the active unpack loops are LUT-heavy and
spill NEON vectors through scalar lookup arrays. Disabling NEON is not viable.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_neon_compare_probe_20260615/neon_compare_probe.json`

| variant | median | finding |
|---|---:|---|
| fast flags, NEON on, `FUSED_STRIPE_ROWS=48` | 48.41 ms / 20.65 fps | below target |
| fast flags, NEON off, `FUSED_STRIPE_ROWS=48` | 58.80 ms / 17.01 fps | much slower |

This rules out a scalar-only build as a recovery path. The remaining work is
still algorithmic Pass1 reduction, not disabling NEON.

## Highpass Lower-Bound Probe

A diagnostic-only build knob skipped highpass transform/tokenization work to
bound the cost of the remaining Pass1/Pass2 highpass path. This is not a valid
production output path: the decoder sees empty highpass bands, so the output
does not preserve the raw detail payload expected from `.gvid`.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_drop_hp_bound_probe_20260615/drop_hp_bound_probe.json`

| variant | median | finding |
|---|---:|---|
| baseline | 48.65 ms / 20.55 fps | below target |
| `GPR_DROP_HIGHPASS=1` | 32.95 ms / 30.35 fps | diagnostic-only pass |
| `GPR_DROP_HIGHPASS=1 FUSED_STRIPE_ROWS=48` | 32.88 ms / 30.41 fps | diagnostic-only pass |

This narrows the throughput blocker to highpass transform/tokenization and
associated Pass1 data movement. The target frame rate is reachable if that
work is reduced, but simply dropping highpass content is not an acceptable
Labs prototype path.

## Quality Env And Quant Probe

`bench_fused` previously hard-coded quality 3. That made earlier
`FUSED_QUALITY=11` short probes invalid as quality experiments, because the
environment variable did not reach `gpr_encode_fused_create`. The benchmark
now reads `FUSED_QUALITY=<0..11>`, rejects invalid values, and
`tools/run_labs_target_bench.py --quality` passes the same quality to the
encoder payload instead of only recording it in the wrapper receipt/header. A
CI smoke test covers this behavior:

- `tools/test/test_bench_fused_quality_env.sh`

Corrected Pi probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_quality_env_quant_probe_20260615/quality_env_quant_probe.json`

| variant | median | finding |
|---|---:|---|
| `FUSED_QUALITY=3` | 46.10 ms / 21.69 fps | below target |
| `FUSED_QUALITY=11` | 45.27 ms / 22.09 fps | below target |
| `FUSED_QUALITY=11 FUSED_STRIPE_ROWS=48` | 46.65 ms / 21.44 fps | below target |
| `FUSED_QUALITY=11 FUSED_STRIPE_ROWS=64 FUSED_DEFER_RANS=1` | 44.73 ms / 22.36 fps | below target |
| `FUSED_QUALITY=11 GPR_QUANT_OVERRIDE=6:24` | 45.40 ms / 22.03 fps | below target |

This rules out quality and highpass quantization knobs as sufficient fixes for
the 24 fps capture target. They move payload size and timing slightly, but the
remaining production gap still requires code-level reduction of the highpass
path rather than another runtime sweep.

Follow-up source audit found a q11 encoder/decoder table drift: the encoder's
q11 level-2 highpass divisors were `{48,48,24}`, while the fused decoder still
used `{24,24,12}`. The q11 decoder table is now fixed, and CI statically
checks all fused quality rows match. The q11 Pi timing probes above remain
encode-side throughput evidence, but any q11 decode-quality interpretation
before this table fix should be treated as superseded.

## Polynomial Log Probe

`FUSED_LOG_POLYNOMIAL=ON` was remeasured on the Pi 5 stand-in because older
follow-up notes listed it as a possible A78/Pi-side unpack win. The current
Labs half-res capture path does not benefit from it.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_poly_log_probe_20260615/poly_log_probe.json`

Build/runtime setup:

- build flags: `-std=c99 -O3 -DNDEBUG -mcpu=native`
- frames: 180
- base env: `GPR_INCLUDE_LL=1 FUSED_MULTI_LEVEL=1 FUSED_WAVELET_LEVELS=2`
  `GPR_COL_DECIMATE=2 GPR_ROW_DECIMATE=2 FUSED_QUALITY=3`

| build | case | median | payload | finding |
|---|---|---:|---:|---|
| LUT/default | baseline write-all | 47.84 ms / 20.90 fps | 231,724,440 bytes | below target |
| polynomial | baseline write-all | 50.25 ms / 19.90 fps | 231,724,440 bytes | slower |
| LUT/default | stripe64 + deferred rANS | 48.29 ms / 20.71 fps | 231,724,440 bytes | below target |
| polynomial | stripe64 + deferred rANS | 48.83 ms / 20.48 fps | 231,724,440 bytes | slower |
| LUT/default | drop highpass lower bound | 32.39 ms / 30.88 fps | 214,846,740 bytes | diagnostic-only pass |
| polynomial | drop highpass lower bound | 72.53 ms / 13.79 fps | 214,846,020 bytes | severe regression |

This rules out `FUSED_LOG_POLYNOMIAL=ON` for the current Labs half-res path.
The default should remain OFF. The next speed attempt should target active
Pass1 unpack/highpass work directly, not the log polynomial path.

## U16 Log-Scratch Candidate

A current-code candidate changed the active luma/chroma col-decimate helpers
to keep LUT results as `uint16_t` scratch and widen in NEON instead of storing
intermediate log values in `int32_t` arrays. The candidate was byte-exact, but
slower on the Pi 5 stand-in, so it was not committed.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_u16log_probe_20260615/u16log_probe.json`

| build | frames | median | first-frame hash | finding |
|---|---:|---:|---|---|
| baseline `3f7f2c3` | 300 | 45.60 ms / 21.93 fps | `c3cc5bc080a4df6f66e1215362d7c0c48abe0f342f1a4324559248d032dc6229` | below target |
| u16 log-scratch candidate | 300 | 49.24 ms / 20.31 fps | `c3cc5bc080a4df6f66e1215362d7c0c48abe0f342f1a4324559248d032dc6229` | byte-exact but slower |

This rules out a narrower-log-scratch rewrite of the active mode-1
col-decimate helpers as the next speed path. The remaining useful direction is
still deeper Pass1 work reduction: avoid work, reduce horizontal/highpass
traffic, or change the capture-side algorithm.

## Prescale-2 Fixed-Shift Candidate

A current-code candidate specialized the hot `horizontal_filter` NEON loop for
`prescale == 2`, replacing variable-vector right shifts with fixed immediate
right shifts. The candidate was byte-exact locally and on the Pi 5 stand-in,
but slower on the target write-all probe, so it was not committed.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_p2shift_probe_20260615/p2shift_probe.json`

| build | frames | median | first-frame hash | finding |
|---|---:|---:|---|---|
| baseline `0dbcd75` | 300 | 48.93 ms / 20.44 fps | `c3cc5bc080a4df6f66e1215362d7c0c48abe0f342f1a4324559248d032dc6229` | below target |
| prescale-2 fixed-shift candidate | 300 | 51.05 ms / 19.59 fps | `c3cc5bc080a4df6f66e1215362d7c0c48abe0f342f1a4324559248d032dc6229` | byte-exact but slower |

This rules out fixed-shift specialization of the existing horizontal-filter
math as the next speed path. The useful boundary is now clearer: simple
instruction reshaping around the same Pass1/highpass work has not recovered
the target. The next experiment should remove or share actual work in the
active Pass1/highpass path, or change the capture-side algorithm.

## Producer-Unpack Decimate Guard

The current source disables the shared producer ring when either
`GPR_ROW_DECIMATE=2` or `GPR_COL_DECIMATE=2` is active. That turns the formerly
corrupting `FUSED_PRODUCER_UNPACK=1` + decimated-capture combination into a
safe fallback to the normal per-channel unpack path. A CI smoke test now covers
byte identity for that fallback on a small raw fixture:

- `tools/test/test_producer_unpack_decimate_fallback.sh`

Pi guard receipt:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_producer_guard_20260615/producer_decimate_guard.json`

| case | result |
|---|---:|
| baseline decimated write-all | 300/300 frames, 46.52 ms median, 21.49 fps |
| producer requested + decimated write-all | 300/300 frames, 42.03 ms median, 23.79 fps |

The older guard receipt proves the formerly aborting env combination survived
300-frame write-all output after the fallback was added. It should not be
treated as a production throughput claim. A fresh decimation-aware producer
scratch candidate was tested separately and rejected by full-frame Pi timing
below. The real throughput work now needs a different Pass1 unpack optimization.

## Decimated Producer Experiment

A scratch decimation-aware producer was tested and not committed. It reused the
existing per-channel decimation kernels inside the producer threads, emitted
correctly sized rows, and avoided heap corruption, but it was too slow to keep
as production code. This was not the committed byte-identity candidate; it is
kept here as a ruled-out shape.

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
work in that probe. A fresh corrected scratch version was then tested with the
direct `.gvid` harness and rejected by timing.

Probe artifact:

- JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_pi_producer_combined_probe_20260615/producer_combined_dec2_probe.json`

| case | result |
|---|---:|
| baseline decimated write-all | 300/300 frames, 47.50 ms median, 21.05 fps |
| producer requested fallback | 300/300 frames, 46.67 ms median, 21.43 fps |
| combined decimated producer scratch path | 300/300 frames, 53.20 ms median, 18.80 fps |

Fresh direct `.gvid` A/B receipts from the corrected scratch version:

| case | receipt | median | p95 | dominant timing |
|---|---|---:|---:|---|
| baseline, direct `.gvid` | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_baseline_dec2_120f_decprod_candidate_20260615/labs_target_bench.json` | 44.93 ms / 22.26 fps | 53.22 ms | Pass1 mean 37.15 ms; unpack mean 22.16 ms |
| decimated producer scratch, direct `.gvid` | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_producer_dec2_120f_decprod_candidate_20260615/labs_target_bench.json` | 63.41 ms / 15.77 fps | 65.99 ms | Pass1 mean 53.15 ms; channel wait mean 25.20 ms |

This rejects the producer-ring architecture for the active half-res capture
path. The synchronization/wait cost is larger than the raw-to-log sharing win.
The remaining useful direction is to reduce Pass1 unpack inside the active
worker path itself, where shared raw-to-log work can avoid cross-thread handoff
costs.

## Pass1 Lazy Scratch Allocation Probe

A low-risk in-worker allocation probe was tested and rejected. The candidate
only allocated the full-width `unpack_full` scratch buffer when the legacy luma
fallback could use it, instead of allocating it for every `col_decimate == 2`
Pass1 channel. The default highpass-preserving half-res path does not read that
buffer, so this was a safety probe for per-frame scratch allocation overhead,
not an algorithm change.

Correctness and local timing checks:

- A 1024 x 768 decimated fixture produced byte-identical output versus the
  baseline. Both `.gpr` files hashed to
  `fef6948bcbe6015db4d0c879f3361ef6f42aa718e0b7d80ae6bb09e783053a21`.
- A local full Z8 raw sanity run was neutral to slightly slower: baseline
  8.19 ms median / 122.14 fps, candidate 8.23 ms median / 121.58 fps.

Fresh Pi direct `.gvid` A/B receipts:

| case | receipt | median | p95 | result |
|---|---|---:|---:|---|
| baseline, direct `.gvid` | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_baseline_lazyalloc_ab_120f_20260615/labs_target_bench.json` | 45.50 ms / 21.98 fps | 48.53 ms | below target |
| lazy scratch allocation, direct `.gvid` | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_lazyalloc_candidate_120f_20260615/labs_target_bench.json` | 47.34 ms / 21.13 fps | 51.31 ms | slower |

This rules out allocation-only cleanup as the missing throughput source. The
active blocker remains highpass-preserving Pass1 row math, unpack, tokenization,
or data movement, not unused full-width scratch allocation.

## Col-Decimate Prefetch Probe

A second low-risk in-worker probe added forward prefetch hints inside the active
highpass-preserving chroma and luma col-decimate unpack loops. This changed no
arithmetic and was byte-identical on the local 1024 x 768 decimated fixture:
both outputs hashed to
`fef6948bcbe6015db4d0c879f3361ef6f42aa718e0b7d80ae6bb09e783053a21`.

Fresh Pi direct `.gvid` A/B receipts:

| case | receipt | median | p95 | result |
|---|---|---:|---:|---|
| baseline, direct `.gvid` | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_baseline_prefetch_ab_120f_20260615/labs_target_bench.json` | 44.62 ms / 22.41 fps | 49.68 ms | below target |
| col-decimate forward prefetch, direct `.gvid` | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_prefetch_candidate_120f_20260615/labs_target_bench.json` | 51.17 ms / 19.54 fps | 61.40 ms | slower |

This rejects simple forward prefetch hints in the active unpack kernels. The Pi
regression suggests the hot loop is limited by LUT/arithmetic and scheduling
behavior more than by raw row cache misses that manual prefetch can hide.

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

Short direct `.gvid` timing-detail receipt:

- JSON:
  `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_timing_detail_30f_0f72df0_20260615/labs_target_bench.json`

| case | median | Pass1 median | Pass2 median | dominant channel component |
|---|---:|---:|---:|---|
| direct `.gvid`, timing-detail build | 42.16 ms / 23.72 fps | 32.80 ms | 8.50 ms | unpack mean 20.58 ms |

Component means from the direct-container timing receipt:

| component | mean |
|---|---:|
| unpack | 20.58 ms |
| vertical + quantize | 5.79 ms |
| tokenize | 3.51 ms |
| horizontal | 3.04 ms |
| other | 0.31 ms |

The profile says the blocker is not primarily `.gvid` wrapping or storage I/O
at this sample size. Multi-level Pass1 dominates the encode, and the largest
measured Pass1 component is channel unpack. The already-existing
`FUSED_PRODUCER_UNPACK=1` path was the obvious architectural candidate, but its
old full-size ring was not valid for decimated capture. A corrected
decimation-aware scratch producer removed that correctness blocker but regressed
full-frame Pi timing. A real speed fix now requires another Pass1 unpack
optimization.

The fused encoder mode knobs used by the half-res path are now captured at
context creation and guarded by `tools/test/test_fused_context_env_capture.sh`,
so post-create environment drift cannot silently change the emitted decimation
header while worker threads are running.

## Reproducible Timing Build

The timing path is now a supported diagnostic build instead of a scratch source
edit. Configure the Pi/self-hosted worktree with:

```bash
cmake -S . -B build-labs-timing \
  -DCMAKE_BUILD_TYPE=Release \
  -DFUSED_TIMING=ON \
  -DFUSED_TIMING_DETAIL=ON
cmake --build build-labs-timing --target bench_fused -j"$(nproc)"
```

`FUSED_TIMING` prints the per-frame Pass1/Pass2 summaries already used in the
timing profile. `FUSED_TIMING_DETAIL` also prints per-channel wait, horizontal,
vertical/quantize, tokenize, and other timing, and it implies `FUSED_TIMING` in
CMake. `tools/run_labs_target_bench.py` now parses those lines into the
`fused_timing` receipt object, including `stage_ms`, `channel_component_ms`,
per-channel summaries, producer timing, and dominant mean-cost keys. Use this
build to narrow the blocker in a `labs_target_bench.json` receipt; use a normal
Release build for final production throughput evidence.

## Next Boundary To Test

The remaining likely causes are:

1. missing downstream changes from the original unsanitized `be0328a` build,
2. code-level throughput regression before the historical bench-note commit
   that was not preserved as a committed source delta,
3. missing in-worker Pass1 unpack optimization for the current hot path.

Next step: treat the May 26 number as non-reproducible unless the original
downstream `be0328a` worktree is recovered, and focus the current-code fix on
real Pass1/highpass work reduction. Polynomial log, u16 log scratch, and
prescale-2 fixed-shift candidates are all ruled out by Pi timing. The
producer-unpack corruption is now covered by a decimated byte-identity
regression, and the corrected decimation-aware producer scratch path is rejected
by full-frame Pi timing. Lazy allocation of an unused full-width scratch buffer
is also byte-identical but slower on the Pi, and manual forward prefetch in the
active col-decimate unpack loops regresses sharply. The next speed experiment
must share raw-to-log work inside the active Pass1 worker path, remove highpass
work without invalidating output, reduce highpass tokenization/data movement, or
replace the capture-side algorithm.
The production target remains >= 24 fps sustained; today's best evidenced
current-build knob is 22.53 fps median on a 100-frame probe and 19.98 fps
median on the strict 10-minute receipt.

## Direct `.gvid` Receipt Mode

`bench_fused` now supports `GPR_BENCH_GVID=<path>` for target probes that write
one strict `.gvid` stream directly as frames are encoded. The target receipt
harness exposes this as `tools/run_labs_target_bench.py --direct-gvid`, so a
run can measure sequential container writes instead of writing one `.gpr` file
per frame and packing afterward.

Current-head Pi 5 stand-in default probe:

- receipt:
  `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_default_nodrop_120f_ede0e07_20260615/labs_target_bench.json`
- commit: `ede0e078eae4a5643efd24b1a6a5ebec4844a826`
- mode: highpass-preserving no-drop path, default LUT path, `--direct-gvid`
- frames: 120 / 120
- `.gvid`: valid
- median: 46.83 ms / 21.36 fps
- p95: 49.44 ms
- timing detail: Pass1 mean 37.45 ms, Pass2 mean 8.09 ms, channel-unpack
  mean 22.37 ms across channel workers

This rules out the earlier 13 fps direct-container result as a polynomial-log
diagnostic rather than the default target path. It still does not clear the
production target.

Polynomial diagnostic Pi 5 stand-in probe:

- receipt:
  `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_poly_nodrop_120f_20260615/labs_target_bench.json`
- mode: highpass-preserving no-drop path, `FUSED_LOG_POLYNOMIAL=ON`,
  `--direct-gvid`
- frames: 120 / 120
- `.gvid`: valid, 114,392,072 bytes
- median: 74.71 ms / 13.39 fps
- p95: 86.88 ms

These receipts prove the direct container measurement path but do not clear
the production target. The remaining blocker is still compute throughput for
the highpass-preserving half-res path, with Pass1 channel unpack still the
largest measured component.
