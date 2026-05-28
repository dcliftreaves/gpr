# Stills encode timing on Pi 5 (Cortex-A76)

Single-image best-of-3, legacy CineForm VC5 encoder (`gpr_tools -q <q>`).
Source: Z8Z_0067 (Nikon Z8 50 MP, 8280×5520 RGGB14).

## Post-parallelization (commit ffc5e47, 2026-05-28)

| q | encode ms | bytes (MB) | single-frame fps | vs baseline |
|---:|---:|---:|---:|---:|
| 0 | 1506 | 3.22 | 0.66 | 1.09× |
| 1 | 1521 | 3.75 | 0.66 | 1.09× |
| 2 | 1547 | 5.88 | 0.65 | 1.10× |
| 3 | 1578 | 7.81 | 0.63 | 1.11× |
| 4 | 1610 | 9.79 | 0.62 | 1.13× |
| 5 | 1665 | 13.35 | 0.60 | 1.16× |
| 6 | 1684 | 16.15 | 0.59 | 1.18× |
| 7 | 1688 | 16.15 | 0.59 | 1.17× |
| 8 | 1682 | 16.18 | 0.59 | 1.17× |

## Pre-parallelization baseline (early 2026-05-28)

| q | encode ms | bytes (MB) | single-frame fps |
|---:|---:|---:|---:|
| 0 | 1639 | 3.22 | 0.61 |
| 1 | 1661 | 3.75 | 0.60 |
| 2 | 1706 | 5.88 | 0.59 |
| 3 | 1756 | 7.81 | 0.57 |
| 4 | 1822 | 9.79 | 0.55 |
| 5 | 1929 | 13.35 | 0.52 |
| 6 | 1980 | 16.15 | 0.51 |
| 7 | 1973 | 16.15 | 0.51 |
| 8 | 1972 | 16.18 | 0.51 |

**Notes:**
- Pi 5 has 4 cores (Cortex-A76). Per-channel threading (4 channels)
  exploits these. 9-18% speedup observed end-to-end (DNG container
  parse/write is single-threaded and dilutes the encoder gain).
- On M3 Max (12+ cores), encoder-only is 43% faster (Z8Z_6693
  298ms → 169ms); end-to-end 6-13% faster.
- Pi 5 is NOT realistic for 24 fps full-res capture with legacy gpr_tools.
  For 24 fps embedded capture use the half-res FUSED path (`ml2_q3_dec2`),
  which is measured at 24.93 fps median.

Recorded 2026-05-28 by Claude during the legacy stills retrain track work.
