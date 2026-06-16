# Labs Target Bench

Last refreshed: 2026-06-15

This page defines the target-style evidence required for Labs prototype review.
It separates current Pi 5 stand-in evidence from the still-missing camera
firmware evidence.

## Current Evidence

| item | current evidence | status |
|---|---|---|
| Historical half-res `.gvid` capture budget | `docs/pi5_bench_2026-05-26.md` reports 24.93 fps median on an older Pi branch/run | historical stand-in evidence |
| Current strict 10 minute Pi 5 target run | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` reports 14,400 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, 19.98 fps median | proxy-acceptable Pi stand-in; camera 24 fps pending |
| Current half-res variant probe | `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md` reports current, historical-doc, environment, runtime-knob, compiler-flag, quality, producer, highpass-bound, target-rehearsal, direct-container, and luma-pair probes; the best short direct-container near-miss is luma-pair plus stripe64/deferred rANS at 23.54 fps median | regression evidence |
| Corrected pixel-format direct `.gvid` probe | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_direct_gvid_pf4_120f_e16357f_20260615/labs_target_bench.json` reports commit `e16357f`, 120 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, and 19.85 fps median with pixel format 4 applied to the encoder context | target-performance blocker |
| Mission 1 still source corpus | `/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/GoProMission1` contains 40 Mission 1 `.GPR` files at 8192 x 6144, 16-bit RGGB, plus 4 HERO10 files excluded from Mission 1 receipts. Inventory and decode smoke live at `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_source_inventory_20260615/summary.json`; `GP017517.GPR` decodes to RAW with SHA-256 `8ab2a9772cc813b2036e30c122315ae605111ef2c14be6dab004c5de5ad44f03`, while the current DNG/parameter path throws `dng_exception` and needs compatibility work. | real source corpus; file-backed target input ready |
| Current-head tracked sweep | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_03eaa4d_120f_20260615T112841Z/labs_perf_sweep.json` reports commit `03eaa4d`, 120-frame direct `.gvid` variants, 0 drops, valid `.gvid`, and no passing variant; baseline is best at 21.54 fps median and stripe64/deferred regresses to 18.52 fps median. Timing receipt `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_timing_3c48f2f_30f_20260615T113211Z/labs_target_bench.json` reports Pass1 median 33.5 ms, Pass2 median 11.6 ms, and unpack mean 20.6 ms | current-head target-performance blocker |
| Rejected luma-pair handoff candidate | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_lumapair_dirty_120f_20260615T114724Z/labs_perf_sweep.json` reports a dirty-source opt-in channel0-to-channel3 luma handoff probe; patched baseline is best at 20.44 fps, luma-pair alone regresses to 12.05 fps, and luma-pair plus stripe64/deferred reaches only 18.54 fps | rejected performance candidate |
| Current-head Pi 5 direct `.gvid` rehearsal | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_direct_1440f_1b934a4_20260615/labs_target_bench.json` reports commit `1b934a4`, 1,440 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, and 16.00 fps median; timing-detail receipt `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_timing_detail_30f_1b934a4_20260615/labs_target_bench.json` reports Pass1 median 38.90 ms and unpack mean 22.79 ms | current-head target-performance blocker |
| 2K live/camera-back raw target | `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md` reports `2k_raw_0p5x_l2hh` at 29.85 fps median, 37.1 ms p95 | stand-in evidence |
| Desktop review PREVIEW | `docs/VIDEO_STATUS.md` reports q8 three-way PREVIEW quality pass at 13.65 s/image on Mac/MPS | offline-only evidence |
| Format validation | `test_video_format` and `test_video_full_chain` validate headers, streams, and real encoded `.gvid` files | committed CI evidence |
| Portable source/media bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` | source/media stand-in bundle |
| Portable target-proxy bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` and carries the strict 10-minute Pi proxy receipt | Pi proxy bundle |
| Target receipt harness | `tools/run_labs_target_bench.py` wraps `bench_fused`, packs a strict `.gvid`, validates truncation behavior, parses `FUSED_TIMING_DETAIL` output into `fused_timing`, and writes `labs_target_bench.json` | committed harness |

## Required Target Run

Before claiming firmware readiness, run a sustained target-style capture:

| metric | required receipt |
|---|---|
| duration | 10 minutes or explicit shorter-run blocker |
| fps | median, p95, p99, min |
| encode | median/p95/p99 ms/frame |
| storage | write MB/s and fsync/flush policy |
| memory | RSS or firmware heap high-water mark |
| CPU | utilization per core or firmware equivalent |
| thermal | temperature over time and throttle state |
| drops | count, frame indices, policy taken |
| output validity | C stream validation, metadata validation, decode checksum |
| interruption | normal stop and simulated interrupted-file recovery result |

Run the target-style receipt harness on the Pi 5 stand-in with the actual
`bench_fused` binary and raw input:

```bash
export GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/run_labs_target_bench.py \
  --bench build/bin/bench_fused \
  --raw /path/to/source_bayer.raw \
  --frames 14400 \
  --target-fps 24 \
  --output-dir "$GPR_ARTIFACT_ROOT/labs_target_bench_pi5_10min_YYYYMMDD"
```

For a receipt that measures the actual sequential `.gvid` write path instead
of staging one `.gpr` file per frame and packing afterward, add
`--direct-gvid`. This mode requires a `bench_fused` binary that supports
`GPR_BENCH_GVID`; the receipt validates the emitted container and records
`fsync_policy: bench_fused sequential .gvid fwrite`.

The receipt must include timing percentiles, dropped-frame accounting, wrapper
and child-process RSS, storage throughput, basic CPU load, thermal samples when
`vcgencmd` is available, relevant encoder env knobs, `bench_fused` binary hash
and CMake/C flags when available, strict `.gvid` validation, and
interrupted-tail recovery. The `--quality` and `--pixel-format` arguments are
passed through to `bench_fused` as `FUSED_QUALITY` and
`GPR_BENCH_PIXEL_FORMAT`, and the receipt records the effective bench
environment, so the encoded payload and receipt/container fields match. CI
runs only the simulated schema smoke:
`bash tools/test/test_labs_target_bench_smoke.sh`.

## Timing-Diagnostic Build

When a target receipt misses 24 fps, rebuild `bench_fused` with the opt-in
timing hooks instead of carrying a scratch source patch:

```bash
cmake -S . -B build-labs-timing \
  -DCMAKE_BUILD_TYPE=Release \
  -DFUSED_TIMING=ON \
  -DFUSED_TIMING_DETAIL=ON
cmake --build build-labs-timing --target bench_fused -j"$(nproc)"
```

`FUSED_TIMING` prints Pass1/Pass2 stage summaries. `FUSED_TIMING_DETAIL`
also prints per-channel unpack, horizontal, vertical/quantize, tokenize, wait,
and other timing. `FUSED_TIMING_DETAIL` implies `FUSED_TIMING` in CMake.
When those lines are present, `tools/run_labs_target_bench.py` records a
structured `fused_timing` object in `labs_target_bench.json` with summarized
`stage_ms`, `channel_component_ms`, `channel_component_by_channel_ms`,
`producer_ms`, and dominant mean-cost keys. This is the reviewer-facing receipt
field for identifying whether the current blocker is unpack, horizontal
filtering, vertical/quantize, tokenization, wait time, Pass2, or producer
overhead.

Diagnostic timing builds are blocker evidence, not production throughput
claims. Keep the production receipt tied to a normal Release build unless the
diagnostic build is explicitly being used to narrow a blocker. The
`tools/run_labs_target_bench.py` receipt stores the `bench_fused` binary hash,
CMake build root, build type, C flags, structured `fused_timing`, and stderr
tail, so timing lines remain attached to the compact JSON evidence.

## Variant Sweep Wrapper

Use `tools/run_labs_perf_sweep.py` for short, reproducible target A/B probes.
It runs multiple `tools/run_labs_target_bench.py` variants into separate
receipt directories and writes a ranked `labs_perf_sweep.json` summary:

```bash
GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts \
python3 tools/run_labs_perf_sweep.py \
  --bench build/bin/bench_fused \
  --raw /path/to/source_bayer.raw \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/labs_perf_sweep_YYYYMMDD \
  --frames 120 \
  --direct-gvid \
  --variant baseline \
  --variant stripe64_defer:FUSED_STRIPE_ROWS=64,FUSED_DEFER_RANS=1
```

Sweep summaries are comparison evidence only. The wrapper records
`production_claim: false`; a sweep winner can promote only after a separate
sustained target receipt proves fps, no drops, valid `.gvid`,
interrupted-tail recovery, timing, memory, and storage behavior.

## Current Gap

The current repo evidence is enough for a Labs prototype conversation, but not
enough for direct firmware readiness. The latest strict Pi 5 stand-in receipt
at commit `0dd6660` proves the container/recovery path on a 14,400-frame run
and is acceptable as conservative 20 fps proxy evidence. It still does not
prove the actual Mission 1 24 fps camera path:

| metric | latest strict Pi 5 receipt |
|---|---|
| receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` |
| frames | 14,400 requested / 14,400 written |
| drops | 0 |
| median fps | 19.98 fps |
| mean fps | 19.23 fps |
| median encode | 50.04 ms/frame |
| p95 encode | 66.01 ms/frame |
| max encode | 239.47 ms/frame |
| `.gvid` | valid, 14,400 frames, 13.73 GB payload |
| recovery | truncated-tail rejected; 14,399 complete frames recovered |
| memory | wrapper 29.0 MB RSS, child 137.5 MB RSS |
| thermal | 60.9 C start, 75.2 C end |

Additional direct-container probes:

| metric | 2026-06-15 current-head direct `.gvid` default probe |
|---|---|
| receipt | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_default_nodrop_120f_ede0e07_20260615/labs_target_bench.json` |
| commit | `ede0e078eae4a5643efd24b1a6a5ebec4844a826` |
| mode | `--direct-gvid`, default LUT path, highpass-preserving no-drop path |
| frames | 120 requested / 120 written |
| median fps | 21.36 fps |
| median encode+write | 46.83 ms/frame |
| p95 encode+write | 49.44 ms/frame |
| `.gvid` | valid |
| dominant timing | Pass1 mean 37.45 ms; unpack mean 22.37 ms across channel workers |

| metric | 2026-06-15 direct `.gvid` polynomial diagnostic |
|---|---|
| receipt | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_poly_nodrop_120f_20260615/labs_target_bench.json` |
| mode | `--direct-gvid`, `FUSED_LOG_POLYNOMIAL=ON`, highpass-preserving no-drop path |
| frames | 120 requested / 120 written |
| median fps | 13.39 fps |
| median encode+write | 74.71 ms/frame |
| p95 encode+write | 86.88 ms/frame |
| `.gvid` | valid, 114,392,072 bytes |

| metric | 2026-06-15 luma-pair shared-unpack near miss |
|---|---|
| receipts | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_lumapair_probe_20260615/baseline_120f.json`, `/Volumes/OWC_8TB/gpr_work/artifacts/labs_lumapair_probe_20260615/lumapair_stripe64_defer_120f.json` |
| mode | scratch luma-pair shared unpack, `FUSED_STRIPE_ROWS=64`, `FUSED_DEFER_RANS=1`, direct `.gvid` |
| frames | 120 requested / 120 written |
| baseline median | 45.49 ms / 21.99 fps |
| luma-pair median | 42.48 ms / 23.54 fps |
| luma-pair p95 | 44.23 ms/frame |
| `.gvid` | valid |
| status | best short near miss; below 24 fps target; scratch source not committed |

Current-head direct `.gvid` rehearsal:

| metric | 2026-06-15 current-head direct `.gvid` rehearsal |
|---|---|
| receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_direct_1440f_1b934a4_20260615/labs_target_bench.json` |
| commit | `1b934a41e0e9dee8f2189e67442e310ed6aa866a` |
| frames | 1,440 requested / 1,440 written |
| drops | 0 |
| median fps | 16.00 fps |
| median encode+write | 62.48 ms/frame |
| p95 encode+write | 73.21 ms/frame |
| `.gvid` | valid, 1.43 GB container, interrupted-tail recovery proven |
| target state | performance governor, 2.4 GHz, `throttled=0x0`, SSD ext4 `rw,noatime,stripe=8191` |
| timing receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_timing_detail_30f_1b934a4_20260615/labs_target_bench.json` |
| timing finding | Pass1 median 38.90 ms, Pass2 median 9.20 ms, unpack mean 22.79 ms |

Corrected pixel-format direct `.gvid` probe:

| metric | 2026-06-15 corrected pixel-format direct `.gvid` probe |
|---|---|
| receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_direct_gvid_pf4_120f_e16357f_20260615/labs_target_bench.json` |
| commit | `e16357f7984315ec86ae5173fded94d057b1030f` |
| mode | `--direct-gvid`, pixel format 4 applied to `bench_fused` encoder context |
| frames | 120 requested / 120 written |
| drops | 0 |
| median fps | 19.85 fps |
| median encode+write | 50.38 ms/frame |
| p95 encode+write | 57.23 ms/frame |
| `.gvid` | valid, interrupted-tail recovery proven |
| timing receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_direct_gvid_pf4_timing_30f_e16357f_20260615/labs_target_bench.json` |
| timing finding | Pass1 median 34.60 ms, Pass2 median 11.60 ms, unpack mean 21.82 ms |

Commit `e16357f` fixed the bench harness so `GPR_BENCH_PIXEL_FORMAT` reaches
the encoder context, not just the `.gvid` header. Pre-fix receipts remain
useful as container and blocker evidence, but they should not be treated as
exact RGGB16 timing evidence when the requested pixel format was 4.

Current-head tracked sweep:

| metric | 2026-06-15 current-head tracked sweep |
|---|---|
| sweep | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_03eaa4d_120f_20260615T112841Z/labs_perf_sweep.json` |
| commit | `03eaa4d1da923d1217dccbc7d98411c606e9a06b` |
| mode | `--direct-gvid`, pixel format 4, q3, 2-level decimate=2 |
| variants | baseline; `FUSED_STRIPE_ROWS=64 FUSED_DEFER_RANS=1` |
| frames | 120 per variant, 0 drops, valid `.gvid`, interrupted-tail recovery proven |
| best variant | baseline |
| best median fps | 21.54 fps |
| best median encode+write | 46.43 ms/frame |
| best p95 encode+write | 52.94 ms/frame |
| stripe64/deferred median | 18.52 fps / 53.99 ms/frame |
| timing receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_timing_3c48f2f_30f_20260615T113211Z/labs_target_bench.json` |
| timing finding | Pass1 median 33.5 ms, Pass2 median 11.6 ms, unpack mean 20.6 ms; luma unpack channels 0 and 3 are 22.04 ms and 21.86 ms mean |
| status | below 24 fps target; stripe64/deferred no longer reproduces the older scratch near miss on current head |

Rejected luma-pair handoff candidate:

| metric | 2026-06-15 dirty-source luma-pair handoff sweep |
|---|---|
| sweep | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_lumapair_dirty_120f_20260615T114724Z/labs_perf_sweep.json` |
| mode | dirty-source opt-in `FUSED_LUMA_PAIR=1`, direct `.gvid`, pixel format 4, q3, 2-level decimate=2 |
| frames | 120 per variant, 0 drops, valid `.gvid`, interrupted-tail recovery proven |
| patched baseline | 20.44 fps / 48.92 ms median |
| luma-pair handoff | 12.05 fps / 83.00 ms median |
| luma-pair handoff + stripe64/deferred | 18.54 fps / 53.94 ms median |
| status | rejected; the channel0 producer/channel3 consumer handoff loses channel parallelism and adds synchronization/copy overhead |

The direct default receipts improve measurement fidelity and rule out the
earlier 13 fps result as a polynomial-log diagnostic, not the default target
path. The current-head 1,440-frame rehearsal is slower than short probes and
confirms that short-run medians cannot be promoted as sustained target
evidence. The luma-pair shared-unpack scratch probe is the strongest short-run
lead so far, but it still does not remove the camera-performance question: the
highpass-preserving half-res path is proxy-acceptable on the strict Pi 5
stand-in receipt, while actual Mission 1 24 fps capture remains unproven.
The fresh luma-pair handoff integration attempt shows that sharing luma work
through a cross-channel row handoff is not the right production shape; any
future shared-luma work must preserve parallel row execution or remove work
inside existing channel workers without forcing channel 3 to wait on channel 0.

Remaining missing receipts:

- actual camera sensor/DMA handoff,
- sustained thermal/power behavior,
- storage behavior on the intended camera media path,
- an actual Mission 1 camera-hardware receipt that proves the half-res encoder
  at >= 24 fps, or identifies the hardware bottleneck.

Until those exist, Pi 5 numbers must be labeled as stand-in evidence.

The current Labs bundle includes the 120-frame Pi 5 stand-in receipt
`receipts/pi5_2k_l2hh_120f_standin.json`; it does not replace the required
10 minute target-style run.
