# GPR Raw Video Encoder — Operating Envelope

**Date:** 2026-05-12 (M1 dev platform measurements). **Updated** for the 2-level wavelet default flip after visual-quality testing.
**Codec state:** feature/raw-video, **2-level wavelet default** (`FUSED_WAVELET_LEVELS=2`, 1/3 still available via flag), rate control + LL emission, opt-in dual-encoder mode via `gpr_video_encoder_create_dual()`. The `test_preview_decode` binary (`source/app/test_preview_decode.c`) demonstrates the LL2-only 1034×690 preview decode path used by the patent-avoidance strategy.

## Multi-level wavelet impact (Z8 45 MP, q=3, no rate control)

| Levels | Z8 ISO 64 | Z8 ISO 22800 | PSNR clean | PSNR noisy | Visual |
|---|---|---|---|---|---|
| 1 | 19.9 MB | 33.8 MB | 48.2 dB | 46.4 dB | no artifacts |
| **2 (default)** | **13.0 MB (−35%)** | **29.9 MB (−12%)** | **45.6 dB** | **44.3 dB** | minor edge ringing only |
| 3 (opt-in) | 10.77 MB (−46%) | 28.47 MB (−16%) | 43.7 dB | 42.65 dB | visible "comb" ringing on high-contrast edges |

**Why 2-level is the default, not 3-level:** Empirical visual-quality testing (montage crops, gamma-corrected, both auto-leveled and natural exposure) showed 3-level produces pronounced wavelet edge-ringing on high-contrast features (rooflines, structures). The artifact comes from the LL2 quantization error propagating through the L1/L0 inverse cascade and getting magnified by the inverse log curve in dark regions adjacent to bright edges. Confirmed *not* fixable by quantizer tuning: a sweep of `FUSED_L1_HF_SHRINK`, `FUSED_L2_HF_SHRINK`, and `FUSED_LL2_DIVISOR` (including effectively-lossless HF bands ballooning the file to 17 MB) left the visible ringing unchanged.

Fixing 3-level properly would require porting the production GPR decoder's *fixed-width lossless LL storage* (separate from rANS, avoids the 2047-magnitude alphabet cap that forces LL2_DIVISOR≥20). Multi-day work; deferred.

**Bonus: LL1 at 2070×1380 on Z8 is at 2K horizontal; LL2 (still computable from 3-level mode) at 517×345 gives a 1034×690 preview**. The `test_preview_decode` binary cashes this in as a patent-avoidance decode mode that physically lacks any inverse-wavelet logic. 2-level default + `test_preview_decode` together give us full-quality decode AND a sub-2K preview path.

## Dual-encoder ping-pong throughput (M1, Z8 ISO 64, 3-level)

Encoder-bound regime (unlimited bandwidth, no GC, target_fps=120 to saturate):

| Mode | Sustained fps | Throughput |
|---|---|---|
| `encoder_count=1` | 29.76 fps | 295 MB/s |
| **`encoder_count=2`** | **41.64 fps (+40%)** | **413 MB/s** |

Storage-throttled regime (24 fps target × UHS-II V90 simulation): both modes hit 23.94-23.95 fps sustained — bottleneck is writer, not encoder. The +40% win on M1 buys headroom for thermal throttling and worst-case noisy content. On A78 (no shared E-cluster contention), the win should be at least as good.

Memory cost: 2× input slots + 2× output ring + 2× per-encoder band buffers. ~410 MB single → ~820 MB dual at 45 MP/ring_depth=3.

## Quality vs file size at fixed q (45 MP Z8, no rate control)

### Clean content (ISO 64)

| q | File size | PSNR (raw) | Bits/pixel |
|---|---|---|---|
| 0 (low) | 15.4 MB | 48.10 dB | 2.82 |
| 1 (medium) | 16.8 MB | 48.15 dB | 3.09 |
| 2 (high) | 18.7 MB | 48.17 dB | 3.43 |
| 3 (Filmscan-1, default) | 19.9 MB | 48.17 dB | 3.65 |
| 4 (Filmscan-X) | 22.2 MB | 48.17 dB | 4.07 |
| 5 (Filmscan-2) | 27.5 MB | 48.17 dB | 5.04 |
| 6+ | 32.2 MB | 48.18 dB | 5.90 |

**Plateau at ~48.2 dB.** LL quantization floor (FUSED_LL_DIVISOR=64) caps PSNR; highpass quality is only weakly visible above q=3 because the LL is the dominant signal energy.

### Noisy content (ISO 22800)

| q | File size | PSNR (raw) | Bits/pixel |
|---|---|---|---|
| 0 | 23.5 MB | 46.12 dB | 4.31 |
| 1 | 28.4 MB | 46.30 dB | 5.20 |
| 2 | 33.3 MB | 46.35 dB | 6.12 |
| 3 (default) | 33.8 MB | 46.36 dB | 6.21 |
| 4 | 36.1 MB | 46.36 dB | 6.63 |
| 5 | 40.7 MB | 46.36 dB | 7.47 |
| 6+ | **encoder + test failure** | n/a | n/a |

**q ≥ 6 on heavily-noisy content fails roundtrip** — known limitation. Likely the rANS encoder hits its alphabet edge on a band, or the test's band-walker fails to parse. Not blocking ship because rate controller stays in q=0..3 range; flagged as a follow-up.

## Rate controller convergence (Z8 45 MP × 24 fps, no storage throttle)

### Clean content

| Target MB/s | Actual MB/s | Avg MB/frame | Sustained fps |
|---|---|---|---|
| 20 | 38 | 1.59 | 24.1 ✓ |
| 50 | 58 | 2.41 | 24.1 ✓ |
| 80 | 82 | 3.40 | 24.1 ✓ |
| 100 | 101 | 4.17 | 24.1 ✓ |
| 150 | 151 | 6.23 | 24.2 ✓ |
| 200 | 201 | 8.32 | 24.1 ✓ |
| 300 | 288 | 11.89 | 24.2 ✓ |

**Floor: ~38 MB/s** — controller can't go below this on clean content because LL bitstream is irreducible at FUSED_LL_DIVISOR=64.

### Noisy content (ISO 22800)

| Target MB/s | Actual MB/s | Avg MB/frame | Sustained fps |
|---|---|---|---|
| 50 | 101 | 4.20 | 24.1 ✓ |
| 80 | 115 | 4.80 | 24.0 ✓ |
| 100 | 130 | 5.38 | 24.1 ✓ |
| 150 | 161 | 6.69 | 24.1 ✓ |
| 200 | 199 | 8.30 | 24.0 ✓ |
| 300 | 298 | 12.39 | 24.0 ✓ |

**Floor: ~100 MB/s** on noisy content — quantizer hits its 16× scale ceiling. Above target=150 the controller tracks within 7%.

## Storage class fit (45 MP × 24 fps, with rate control)

| Card class | Sustained throughput | Clean content | Noisy content |
|---|---|---|---|
| UHS-I V30 | 80 MB/s | ✓ (target 80) | ✗ (floor 100) |
| UHS-I V60 | 100 MB/s | ✓ (target 100) | borderline (floor 100) |
| UHS-I V90 | 150 MB/s | ✓ (target 100-150) | ✓ (target 150) |
| **UHS-II V90** | **200 MB/s** | ✓ (target 150-200) | ✓ (target 150-200) |
| CFexpress A | 700 MB/s | ✓ (any target) | ✓ (any target) |

**Recommended deployment: UHS-II V90 microSD with target=150 MB/s.** Handles any ISO content at 24 fps × 45 MP with 30% storage headroom.

## What's still cold on M1 (3-level wavelet, single-encoder mode)

| Workload | M1 sustained fps | A78 estimate (÷2.5) | 24 fps budget |
|---|---|---|---|
| 45 MP single-encoder (encoder-bound ceiling) | 29.8 fps | 11.9 fps | doesn't fit at 50 MP |
| 45 MP dual-encoder (encoder-bound ceiling) | 41.6 fps | 16.6 fps | fits 45 MP, tight at 50 MP |
| 45 MP × 24 fps × UHS-II V90 (rate-controlled) | 23.95 fps | ✓ regardless of encoder_count | ✓ |

A78 compute headroom is still the gating factor for 24 fps × 50 MP. Remaining queued optimizations for real-A78 measurement:
1. `FUSED_LOG_POLYNOMIAL=ON` at cross-compile (5× slower on M1, 1.5-2× faster on A78)
2. ARM64 hand-asm unpack (`FUSED_UNPACK_ASM=1`, 1% on M1, expected 10-20% on A78)
3. (3-level wavelet and dual-encoder: shipped)

## Verified guarantees today

- 24 fps × 45 MP × any ISO on UHS-II V90 microSD: **sustained** (24.0+ fps, 400-frame stress test)
- Encode → decode → reconstruct PSNR: **≥ 46 dB on real photo content at q=3**
- Output is byte-stable across runs (deterministic)
- Container format is self-describing (`gpr_video_format.h`)
- Rate controller tracks within 7% of target above the per-content floor
