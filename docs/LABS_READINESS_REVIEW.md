# Labs Readiness Review

Last refreshed: 2026-06-15

## Decision

Go for Labs prototype exploration of half-res `.gvid` raw capture plus desktop
review/export.

No-go for direct firmware merge until target hardware integration exists and
the current half-res capture path restores >= 24 fps on the target-style run.

## Ready Now

| area | evidence |
|---|---|
| Media shape | `.gvid` clip/frame format, Python packer, metadata sidecars |
| Desktop review path | `gpr2prores` accepts `.gvid` and validates runtime dispatch |
| Source-level safety | hosted CI validates headers, streams, release evidence, registry consistency |
| Format hardening | C reader rejects malformed v1 headers and whole-stream corruption |
| Portable stand-in bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` |
| Target receipt harness | `tools/run_labs_target_bench.py` produces `labs_target_bench.json` with timing, storage, memory, drop, `.gvid`, and interruption fields |
| Strict Pi 5 target receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` proves 14,400 frames, 0 drops, valid `.gvid`, and interrupted-tail recovery |
| Pi 5 regression probe | `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md` records current, historical-doc, environment, runtime-knob, compiler-flag, quality, highpass-bound, timing, producer-guard, polynomial-log, u16 log-scratch, and prescale-2 fixed-shift probes; corrected q11/quant sweeps top out at 22.36 fps median, while diagnostic highpass dropping reaches 30.35 fps but is not valid output |
| Current overview | README is media-focused; detailed proof lives in docs |

## Not Ready Yet

| area | missing evidence |
|---|---|
| Firmware capture integration | sensor/DMA handoff and memory ownership have not been executed on target |
| Sustained target run | latest strict Pi 5 receipt misses 24 fps: 19.98 fps median, 50.04 ms median, 66.01 ms p95 |
| Final target artifact bundle | stand-in bundle exists; final bundle still needs passing target receipt and camera-firmware evidence |
| Firmware capture integration | target receipt uses Pi stand-in file input, not sensor/DMA handoff |

## Current Risk

The main risk is no longer whether `.gvid` can represent, validate, and recover
the media. The latest strict Pi 5 receipt proves that path. The blocker is that
the current half-res encoder path misses the 24 fps target on the stand-in run.

## Next Work

1. Continue current-code Pass1/highpass optimization or choose a different
   capture-side algorithm. A 2026-06-15 search did not find a separate
   recoverable `be0328a` source tree in the consolidated 8TB work area, the
   archived branch does not contain a missing codec speed delta, and the
   polynomial-log, u16 log-scratch, and prescale-2 fixed-shift probes were
   slower than the LUT/default path. The invalid producer+decimate path is now
   guarded, naive / combined producer variants plus compiler/runtime tuning did
   not sustain the target, and the highpass lower-bound probe identifies
   highpass transform/tokenization as the next speed target.
2. Replace or supplement the stand-in bundle with a passing target-capture
   receipt.
3. Add target/self-hosted CI jobs or documented manual receipts for media
   behavior hosted CI cannot exercise.
4. Re-run the readiness review with target bundle hashes and bench receipts attached.
