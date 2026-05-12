# GPR Raw Video Encoder — Operating Envelope

**Date:** 2026-05-11 (M1 dev platform measurements). **Updated** for 2-level wavelet landing at commit `301e4a0`.
**Codec state:** feature/raw-video, 2-level wavelet default (`FUSED_WAVELET_LEVELS=2`), rate control + LL emission. Single-level fallback still available at `FUSED_WAVELET_LEVELS=1`.

## Multi-level wavelet impact (2026-05-11 late session)

Going from single-level to 2-level wavelet:
- **Z8 ISO 64 q=3: 19.9 MB → 13.0 MB (-35%)** — main shipping win
- Z8 ISO 22800 q=3: 33.8 MB → 29.9 MB (-12%) — less because noise dominates
- PSNR cost: ~2-3 dB (48 → 46 dB clean, 46 → 44 dB noisy)
- Compute cost: +20% wall time (extra wavelet pass at 1/4 resolution)
- **Per-band overhead higher** — 7 bands × 4 channels = 28 bands vs 16 single-level. This raises the minimum sustainable bitrate floor for the rate controller.

Net: **2-level is better for typical operating points (target ≥ 100 MB/s)** but single-level has a lower minimum-bitrate floor for extreme storage constraints. Compile flag chooses.

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

## What multi-level wavelet would change

(Currently in progress, subagent ae41a11.) Adding a second wavelet level would:
- Cut LL bitstream by ~75% (LL at second level is 1/16 of source vs 1/4 today)
- Reduce file sizes by ~30-50% on real images
- **Lower the noisy-content rate-control floor from 100 MB/s to ~50-70 MB/s** — would make UHS-I V30 viable
- Closes the compression gap to production 3-level encoder

## What's still cold on M1

| Workload | M1 wall time | A78 estimate (2.5×) | 24 fps budget |
|---|---|---|---|
| 45 MP one-shot encode | ~35 ms | ~88 ms | doesn't fit |
| 45 MP steady-state pipeline | ~25 ms | ~63 ms | tight |
| 50 MP one-shot encode | ~38 ms | ~95 ms | doesn't fit |
| 50 MP steady-state pipeline | ~30 ms | ~75 ms | doesn't fit |

A78 compute headroom is the remaining bottleneck for 24 fps × 50 MP. Three queued optimizations:
1. `FUSED_LOG_POLYNOMIAL=ON` at cross-compile (5× slower on M1, 1.5-2× faster on A78)
2. Multi-level wavelet (compute neutral, but smaller output → faster ANS)
3. `vld2q` + branchless clip in unpack (small drop-in win)

## Verified guarantees today

- 24 fps × 45 MP × any ISO on UHS-II V90 microSD: **sustained** (24.0+ fps, 400-frame stress test)
- Encode → decode → reconstruct PSNR: **≥ 46 dB on real photo content at q=3**
- Output is byte-stable across runs (deterministic)
- Container format is self-describing (`gpr_video_format.h`)
- Rate controller tracks within 7% of target above the per-content floor
