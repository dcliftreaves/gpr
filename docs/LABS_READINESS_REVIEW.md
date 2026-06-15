# Labs Readiness Review

Last refreshed: 2026-06-15

## Decision

Go for Labs prototype exploration of half-res `.gvid` raw capture plus desktop
review/export.

No-go for direct firmware merge until target hardware integration exists and
actual Mission 1 capture proves the 24 fps camera target. The current strict
Pi 5 stand-in receipt is acceptable as a conservative 20 fps proxy for moving
the Labs prototype into firmware-handoff review.

## Ready Now

| area | evidence |
|---|---|
| Media shape | `.gvid` clip/frame format, Python packer, metadata sidecars |
| Desktop review path | `gpr2prores` accepts `.gvid` and validates runtime dispatch |
| Source-level safety | hosted CI validates headers, streams, release evidence, registry consistency |
| Format hardening | C reader rejects malformed v1 headers, truncated headers/payloads, zero-frame streams, duplicate or out-of-order frame tags, and whole-stream corruption; C writer rejects non-finite, negative, overflowing, or rate-control-rounds-to-zero FPS/bitrate fields |
| Portable source/media bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` |
| Portable target-proxy bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` and includes the strict 10-minute Pi proxy receipt plus normalized camera-handoff receipt |
| Target receipt harness | `tools/run_labs_target_bench.py` produces `labs_target_bench.json` with timing, structured `fused_timing`, storage, memory, drop, `.gvid`, and interruption fields |
| Strict Pi 5 target receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` proves 14,400 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, and a 19.98 fps median that is acceptable as a conservative 20 fps Pi proxy |
| Pi 5 regression probe | `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md` records current, historical-doc, environment, runtime-knob, compiler-flag, quality, highpass-bound, timing, producer-guard, polynomial-log, u16 log-scratch, prescale-2 fixed-shift, lazy scratch allocation, prefetch, LUT-unroll, luma-pair shared-unpack, rejected luma-pair handoff, current-head direct `.gvid` rehearsal, and corrected pixel-format probes; best short direct-container near-miss is 23.54 fps median with luma-pair plus stripe64/deferred rANS, while the productionizable channel0-to-channel3 handoff version regressed to 12.05 fps, the corrected pixel-format direct `.gvid` receipt is 19.85 fps median, and diagnostic highpass dropping reaches 30.35 fps but is not valid output |
| Reproducible target timing build | CMake exposes `-DFUSED_TIMING=ON -DFUSED_TIMING_DETAIL=ON`; the target receipt harness parses diagnostics into `fused_timing`, and a local smoke verifies per-channel unpack/horizontal/vertical/tokenize detail plus Pass1/Pass2 summaries without editing source |
| Current overview | README is media-focused; detailed proof lives in docs |

## Not Ready Yet

| area | missing evidence |
|---|---|
| Firmware capture integration | sensor/DMA handoff and memory ownership have not been executed on target; current receipts use Pi stand-in file input |
| Sustained target run | latest strict Pi 5 receipt is proxy-acceptable at 19.98 fps median, 50.04 ms median, 66.01 ms p95; actual Mission 1 24 fps capture remains unproven. Current-head direct `.gvid` rehearsal misses the proxy at 16.00 fps median over 1,440 frames; corrected pixel-format direct `.gvid` receipt is a short probe at 19.85 fps median over 120 frames |
| Final camera artifact bundle | Pi target-proxy bundle exists; final bundle still needs actual camera-firmware evidence |

## Current Risk

The main risk is no longer whether `.gvid` can represent, validate, and recover
the media. The latest strict Pi 5 receipt proves that path and is close enough
to the 20 fps proxy threshold to continue camera integration. The remaining
performance blocker moves to actual Mission 1 evidence: prove 24 fps with the
real sensor/storage path, or record the specific hardware bottleneck.

## Next Work

1. Package the proxy-acceptable Pi receipt into the portable target bundle,
   then run or stub the actual firmware handoff receipt. If the camera path
   fails 24 fps, use the existing `FUSED_TIMING_DETAIL` receipt shape to name
   the specific bottleneck. Use `docs/LABS_MISSION1_RUNBOOK.md` for the exact
   workflow inputs, artifacts, and pass/block rules.
2. Continue current-code Pass1/highpass optimization only if the hardware
   receipt shows Pi-side compute remains the limiting factor. A 2026-06-15
   search did not find a separate
   recoverable `be0328a` source tree in the consolidated 8TB work area, the
   archived branch does not contain a missing codec speed delta, and the
   polynomial-log, u16 log-scratch, and prescale-2 fixed-shift probes were
   slower than the LUT/default path. The invalid producer+decimate path is
   covered by a committed fallback identity fixture, a fresh decimation-aware
   producer scratch probe regressed on full-frame Pi timing, and a lazy scratch
   allocation probe was byte-identical but also slower on Pi. A col-decimate
   prefetch probe and an 8-entry LUT-unroll probe were also byte-identical but
   regressed target timing. A luma-pair shared-unpack scratch candidate improved
   the best short direct-container median to 23.54 fps only with
   stripe64/deferred rANS, but still missed the 24 fps target and was not
   committed. A later channel0-to-channel3 luma handoff implementation was
   byte-identical locally but regressed to 12.05 fps on Pi, so cross-channel
   row handoff is rejected. The corrected pixel-format direct `.gvid` receipt
   also misses at 19.85 fps median, with timing detail again pointing to Pass1
   channel unpack.
3. Replace or supplement the stand-in bundle with a passing target-capture
   receipt.
4. Add target/self-hosted CI jobs or documented manual receipts for media
   behavior hosted CI cannot exercise.
5. Re-run the readiness review with target bundle hashes and bench receipts attached.
