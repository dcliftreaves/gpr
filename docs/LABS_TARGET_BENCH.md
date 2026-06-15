# Labs Target Bench

Last refreshed: 2026-06-15

This page defines the target-style evidence required for Labs prototype review.
It separates current Pi 5 stand-in evidence from the still-missing camera
firmware evidence.

## Current Evidence

| item | current evidence | status |
|---|---|---|
| Historical half-res `.gvid` capture budget | `docs/pi5_bench_2026-05-26.md` reports 24.93 fps median on an older Pi branch/run | historical stand-in evidence |
| Current strict 10 minute Pi 5 target run | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` reports 14,400 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, 19.98 fps median | target-performance blocker |
| Current half-res variant probe | `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md` reports current, historical-doc, environment, runtime-knob, compiler-flag, quality, producer, highpass-bound, and target-rehearsal probes; best 1-minute rehearsal is 22.70 fps median and best corrected quality-env short probe is 22.36 fps median | regression evidence |
| 2K live/camera-back raw target | `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md` reports `2k_raw_0p5x_l2hh` at 29.85 fps median, 37.1 ms p95 | stand-in evidence |
| Desktop review PREVIEW | `docs/VIDEO_STATUS.md` reports q8 three-way PREVIEW quality pass at 13.65 s/image on Mac/MPS | offline-only evidence |
| Format validation | `test_video_format` and `test_video_full_chain` validate headers, streams, and real encoded `.gvid` files | committed CI evidence |
| Portable review bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` | stand-in bundle |
| Target receipt harness | `tools/run_labs_target_bench.py` wraps `bench_fused`, packs a strict `.gvid`, validates truncation behavior, and writes `labs_target_bench.json` | committed harness |

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

The receipt must include timing percentiles, dropped-frame accounting, wrapper
and child-process RSS, storage throughput, basic CPU load, thermal samples when
`vcgencmd` is available, relevant encoder env knobs, `bench_fused` binary hash
and CMake/C flags when available, strict `.gvid` validation, and
interrupted-tail recovery. The `--quality` argument is passed through to
`bench_fused` as `FUSED_QUALITY`, so the encoded payload and receipt/header
quality now match. CI runs only the simulated schema smoke:
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

Diagnostic timing builds are blocker evidence, not production throughput
claims. Keep the production receipt tied to a normal Release build unless the
diagnostic build is explicitly being used to narrow a blocker. The
`tools/run_labs_target_bench.py` receipt stores the `bench_fused` binary hash,
CMake build root, build type, C flags, and stderr tail, so timing lines remain
attached to the compact JSON evidence.

## Current Gap

The current repo evidence is enough for a Labs prototype conversation, but not
enough for direct firmware readiness. The latest strict Pi 5 stand-in receipt
at commit `0dd6660` proves the container/recovery path on a 14,400-frame run,
but it misses the 24 fps target:

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

Remaining missing receipts:

- actual camera sensor/DMA handoff,
- sustained thermal/power behavior,
- storage behavior on the intended camera media path,
- a current commit/path that restores the half-res encoder to >= 24 fps.

Until those exist, Pi 5 numbers must be labeled as stand-in evidence.

The current Labs bundle includes the 120-frame Pi 5 stand-in receipt
`receipts/pi5_2k_l2hh_120f_standin.json`; it does not replace the required
10 minute target-style run.
