# Stills encode timing on Pi 5 (Cortex-A76)

Single-image best-of-3, legacy CineForm VC5 encoder (`gpr_tools -q <q>`).
Source: Z8Z_0067 (Nikon Z8 50 MP, 8280×5520 RGGB14).

| q | encode ms | bytes (MB) | single-frame fps | 24 fps headroom |
|---:|---:|---:|---:|---:|
| 0 | 1639 | 3.22 | 0.61 | NO (-39×) |
| 1 | 1661 | 3.75 | 0.60 | NO |
| 2 | 1706 | 5.88 | 0.59 | NO |
| 3 | 1756 | 7.81 | 0.57 | NO |
| 4 | 1822 | 9.79 | 0.55 | NO |
| 5 | 1929 | 13.35 | 0.52 | NO |
| 6 | 1980 | 16.15 | 0.51 | NO |
| 7 | 1973 | 16.15 | 0.51 | NO |
| 8 | 1972 | 16.18 | 0.51 | NO |

**Notes:**
- Single-thread Pi 5 (4-core Cortex-A76). Multi-threading the encoder
  would help proportionally but not 24× — the wavelet+entropy loop has
  intrinsic serial dependencies.
- Pi 5 is NOT realistic for 24 fps full-res capture with legacy gpr_tools.
  For 24 fps embedded capture use the half-res FUSED path (`ml2_q3_dec2`),
  which is measured at 24.93 fps median.
- These numbers are for the unoptimized legacy gpr_tools. The perf
  subagent is working on memory alignment + NEON + threading.
  Re-measure after that lands.

Recorded 2026-05-28 by Claude during the legacy stills retrain track work.
