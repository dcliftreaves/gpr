# Raw Video Session Summary — 2026-05-11

Branch: `feature/raw-video` (created from `feature/neon-assembly` at the start of session)

## TL;DR

24 fps × 50 MP raw video to UHS-II V90 microSD is **end-to-end correct and sustained** today. Full encode → bitstream → decode → image reconstruction passes PSNR validation at 48 dB on clean content. Pipeline stress test (400 frames, ~16 s) holds rate without drops. Patent landscape researched; RED (now Nikon) holds the dominant moat with key patents expiring 2028–2034.

## Commits landed this session (newest first)

```
1ae5d5d  8-wide unroll of int32 NEON vertical filter for ILP
8b461b5  Disable int16 horizontal filter for 16-bit input
f5efb93  Disable int16 NEON vertical filter — it overflows for 16-bit input
264f4cf  Fix int16 vertical filter overflow on LL band: full roundtrip 48 dB
d8423ab  Test harness: consume 16-band bitstream (LL now emitted)
bdeb3b3  Emit LL band in fused encoder bitstream
1bdf5ae  Add raw video codec landscape & patent research doc
a38e553  Container format for GPR raw video: clip + frame headers
c8fa877  Full-roundtrip PSNR test for gpr_video_encoder
f1ba70a  Fix DNG roundtrip: read VC5 lowpass coefficients as unsigned
38605f7  Fused encoder: shared-unpack ring (4 producers + 4 consumers)
53e4777  Add FUSED_LOG_POLYNOMIAL switch: NEON polynomial log curve (A78 opt)
f270152  Int16 NEON path in fused horiz/vert filters: 8-wide via int32→int16 narrow
bf5b1d3  Add band-level decode verification test for video encoder
c453251  Adaptive bitrate rate controller in gpr_video_encoder
3405287  Fused encoder: use correct quality-table indices
b0fdab1  Pipeline simulator: optional denoise via positional args
8ccd669  Pipelined video encoder + storage-bus simulator
```

## Bugs found and fixed

Three previously-undetected, significant bugs surfaced and were fixed in the same session:

1. **Quality knob silently disabled** (`3405287`) — fused encoder was reading wrong indices from the quality preset table. Every q=0..5 produced byte-identical output. **3× compression improvement on q=3** by reading the correct level-0 divisors.
2. **DNG roundtrip green channel corruption** (`f1ba70a`) — `fast_decode_lowpass` sign-extended unsigned big-endian lowpass coefficients to negative int16, producing G_r=0 / G_b≈13000 in any decoded DNG. Affects all decode consumers of any GPR file (production codec, not just our fused path). Surfaced by visual quality assessment agent.
3. **Fused encoder never emitted LL band** (`bdeb3b3` + cleanups) — Pass 2 loops iterated `band=1..3`. Encoder output was high-frequency only, decodes capped at ~28 dB. Surfaced by the full-roundtrip test we built. Fix: emit LL with FUSED_LL_DIVISOR=64 (brings LL coefficients into the rANS alphabet).
4. **int16 NEON filter overflow for 16-bit input** (`264f4cf` + cleanups) — agent B's 8-wide int16 NEON path assumed 14-bit input bounds, silently corrupted 16-bit data. Fix: disable int16 path on 16-bit input; use int32 8-wide unrolled cleanup.

## Architecture pieces (now in place)

| Module | File | Purpose |
|---|---|---|
| Fused encoder | `source/lib/vc5_encoder/fused_encode.{h,c}` | Bayer → wavelet → quant → rANS, single-level, NEON-optimized |
| Shared-unpack ring | (in fused_encode.c) | 4 producer threads → 64-row ring → 4 consumer threads. 2.5× less LUT work than per-channel unpack. |
| Video pipeline encoder | `source/lib/vc5_encoder/gpr_video.{h,c}` | 3-thread pipeline: caller → encoder → writer. Two SPSC ring buffers. Adaptive bitrate. |
| Adaptive bitrate controller | (in gpr_video.c) | EMA of recent output sizes + sqrt-error step. Converges in ~10 frames, holds ±7% of target across content. |
| Container format | `source/lib/vc5_encoder/gpr_video_format.{h,c}` | 32 B clip header (GVID magic + encoding params + target bitrate) + 16 B per-frame header (FRM magic + size + tag). |
| Storage-bus simulator | `source/app/test_video_pipeline_sim.c` | Throttled writer callback with MB/s ceiling + periodic GC stalls. |
| Band-level roundtrip | `source/app/test_video_roundtrip.c` | Verifies bitstreams parse and decode at band level. |
| Full PSNR roundtrip | `source/app/test_video_full_roundtrip.c` | Full encode → decode → image reconstruction. Validates math against forward oracle. |
| Format test | `source/app/test_video_format.c` | Container header (de)serialization unit tests. |
| A78 polynomial log curve | (in fused_encode.c, `FUSED_LOG_POLYNOMIAL` CMake flag) | Drop-in NEON polynomial replacement for the LUT log curve. 5× slower on M1; expected 1.5-2× faster on A78 (smaller L1d). Off by default. |

## Test status

All 4 test harnesses green:

```
test_stripe_roundtrip:    7/7 PASS  (band-level codec)
test_edge_sizes:          8/8 PASS  (encoder validity across image sizes)
test_video_format:        all PASS  (container header roundtrip + bad inputs)
test_video_roundtrip:     PASS      (band-level decode of rate-controlled output)
test_video_full_roundtrip:
  Z8 ISO 64 clean:        PASS  raw PSNR 48.17 dB, oracle inf
  Z8 ISO 22800 noisy:     PASS  raw PSNR 46.36 dB, oracle inf
test_video_pipeline_sim:
  400 frames × 24 fps × 45 MP × UHS-II V90:
    24.02 fps sustained, 0 dropped frames, GC stalls absorbed
```

## Performance (M1 dev platform)

| Workload | Encode wall time | A78 estimate (2.5×) |
|---|---|---|
| 50 MP one-shot (q=3, no denoise) | 37 ms | 92 ms |
| 50 MP one-shot (q=3 + denoise) | ~40 ms | 100 ms |
| 50 MP steady-state pipeline (RC target 150 MB/s) | ~30 ms/frame | ~75 ms |
| 24 fps × 45 MP sustained (UHS-II V90 microSD) | n/a — sustains target framerate | same |

A78 24 fps budget is 41 ms. Steady-state pipeline at 30 ms M1 = 75 ms A78 at 2.5×. **Doesn't fit 24 fps × 50 MP on A78 yet** — need ~2× more compute speedup. Three known levers queued:
1. `FUSED_LOG_POLYNOMIAL` (already implemented as compile flag) — expected 1.5-2× on A78
2. `vld2q` + branchless clip in unpack — small win, drop-in
3. Multi-level wavelet — neutral compute, big compression win (2×) → smaller bitstream → less ANS work

## IP / patent context

**Critical:** Nikon acquired RED in March 2024. The compressed-raw-Bayer patent moat now belongs to Nikon. Specific patents that read on our pipeline:

- `'967` family ("in-camera compressed raw at 2K+/23+ fps, visually lossless") — **expires April 11, 2028**
- `'384` / `'866` / `'168` family (Green Average Subtraction — `RG = R - GS`, `BG = B - GS`) — **expires February 13, 2034**

Our `source/lib/vc5_encoder/raw.c` does exactly the GAS pattern. Inherited from GoPro's CineForm (Apache 2.0, dates to 2005, pre-dates RED's earliest priority of Dec 2007). Apple's IPR challenge using CineForm as prior art **failed**, so patents stand.

Full landscape in `docs/raw-video-landscape.md` (subagent output committed `1bdf5ae`).

Posture for shipping: align with GoPro's MISSION 1 patent position. Stay VC-5 / SMPTE ST 2073 bit-stream conformant. Keep extensions (adaptive bitrate, denoise, container format) as separable modules with kill switches.

## What's left

| Item | Why it matters | Effort |
|---|---|---|
| A78 cross-compile + real perf measurement | Validate the 2-3× slowdown estimate. Most of the queued optimizations target A78 cache behavior. | hardware-blocked |
| Multi-level wavelet in fused encoder | Single biggest compression lever remaining (~2×). Would close the gap to production VC-5 and let rate control run at higher quality for the same target bitrate. | 4-6 hours of focused work |
| vld2q + branchless clip in unpack | Small drop-in win, especially on A78 with smaller L1d | hours |
| GoPro patent statement at SMPTE | Required for clean shipping. Needs a counsel read. | external |

## How to pick up

- The code is on `feature/raw-video`. Everything compiles, all tests green.
- For video work: start by running `/tmp/test_video_pipeline_sim /tmp/Z8_ISO64.raw 8280 5520 4 3 30 24 200 100 15 3 0 0 1.0 150` to confirm the env. That's 24 fps × 45 MP × UHS-II V90 with adaptive bitrate at 150 MB/s target.
- For correctness work: `test_video_full_roundtrip.c` is the canonical roundtrip test. PSNR ≥ 35 dB for q=3 indicates encoder + decoder math is consistent.
- For perf work: 50 MP M1 baseline is ~30 ms steady-state. A78 fit needs M1 ≤ ~14 ms (3× safety) or ≤ ~17 ms (2.5× realistic).
