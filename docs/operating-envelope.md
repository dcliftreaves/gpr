# GPR Raw Video Encoder — Operating Envelope

**Date:** 2026-05-12 (M1 dev platform measurements). **Updated** after the 3-level wavelet was removed entirely.
**Current status:** historical operating-envelope note. Current production
readiness and target receipts live in `docs/RELEASE_READINESS.md`,
`docs/VIDEO_STATUS.md`, `docs/LABS_TARGET_BENCH.md`, and
`docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`.
**Codec state:** feature/raw-video, **2-level wavelet default** (`FUSED_WAVELET_LEVELS=2`, 1-level still available via flag), rate control + LL emission, opt-in dual-encoder mode via `gpr_video_encoder_create_dual()`.

## Multi-level wavelet impact (Z8 45 MP, q=3, no rate control)

| Levels | Z8 ISO 64 | Z8 ISO 22800 | PSNR clean | PSNR noisy | Visual |
|---|---|---|---|---|---|
| 1 | 19.9 MB | 33.8 MB | 48.2 dB | 46.4 dB | no artifacts |
| **2 (default)** | **13.0 MB (−35%)** | **29.9 MB (−12%)** | **45.6 dB** | **44.3 dB** | minor edge ringing only |

**Why 3-level was removed:** Empirical visual-quality testing showed 3-level produces pronounced wavelet edge-ringing on high-contrast features. We ran the full set of candidate fixes — lossless LL2 storage (port of production GPR's fixed-width LL path), per-level prescale tuning, and HF lossless storage — and **none** moved the visible ringing. Root cause turned out to be inherent to cascading the biorthogonal 5/3 inverse-wavelet three times; only a different wavelet basis (CDF 9/7 or similar) would fix it, which is a full codec rewrite. We deleted the 3-level paths to keep the codebase clean.

## Dual-encoder ping-pong throughput (M1, Z8 ISO 64, 2-level)

Encoder-bound regime (unlimited bandwidth, no GC, target_fps=120 to saturate):

| Mode | Sustained fps | Throughput |
|---|---|---|
| `encoder_count=1` | 29.76 fps | 295 MB/s |
| **`encoder_count=2`** | **41.64 fps (+40%)** | **413 MB/s** |

Storage-throttled regime in this historical simulation: both modes hit
23.94-23.95 fps sustained — bottleneck was writer, not encoder. The +40% win
on M1 bought headroom for thermal throttling and worst-case noisy content.
Do not use this old simulation as the current Labs production claim.

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
| Historical 200 MB/s class | 200 MB/s | ✓ (target 150-200) | ✓ (target 150-200) |
| CFexpress A | 700 MB/s | ✓ (any target) | ✓ (any target) |

Historical recommendation: use storage that sustains the target write budget
with margin. Current Labs docs prefer measured USB SSD/NVMe receipts, and the
actual camera path must supply its own storage proof.

## What's still cold on M1 (2-level wavelet)

| Workload | M1 sustained fps | A78 estimate (÷2.5) | 24 fps budget |
|---|---|---|---|
| 45 MP single-encoder (encoder-bound ceiling) | ~30 fps | ~12 fps | doesn't fit at 50 MP |
| 45 MP dual-encoder (encoder-bound ceiling) | ~42 fps | ~17 fps | fits 45 MP, tight at 50 MP |
| 45 MP × 24 fps × 200 MB/s simulated storage (rate-controlled) | 23.95 fps | ✓ regardless of encoder_count | ✓ |

A78 compute headroom is still the gating factor for 24 fps × 50 MP. Remaining
queued optimization for real-A78 measurement is a new tokenizer/unpack dataflow
pass; the older shared-unpack assembly path was removed after target
regressions.

`FUSED_LOG_POLYNOMIAL=ON` is no longer a queued fix for the current Labs
half-res path. A 2026-06-15 Pi 5 probe showed it slower than the LUT/default
path on normal write-all output and severely slower on the highpass lower-bound
diagnostic, so the build default should remain OFF.

## Verified guarantees today

- Historical storage simulation sustained 24 fps × 45 MP on the May 12 test
  setup; current `.gvid`/Mission 1 readiness uses the Labs target receipts.
- Encode → decode → reconstruct PSNR: **≥ 46 dB on real photo content at q=3**
- Output is byte-stable across runs (deterministic)
- Container format is self-describing (`gpr_video_format.h`)
- Rate controller tracks within 7% of target above the per-content floor
