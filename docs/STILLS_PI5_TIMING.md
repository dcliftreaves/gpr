# Stills encode timing on Pi 5 (Cortex-A76)

Single-image best-of-3, legacy CineForm VC5 encoder (`gpr_tools -q <q>`).
Source: Z8Z_0067 (Nikon Z8 50 MP, 8280×5520 RGGB14).

## Post-parallel-DNG-read (commits 79403fb + ec1cb2c, 2026-05-28)

Parallelize the Adobe DNG SDK tile decode by enabling `qDNGThreadSafe`
on Linux (was excluded from the vendored default) and implementing a
real multi-threaded `dng_host::PerformAreaTask` that dispatches
`dng_read_tiles_task` across N pthreads. Each tile (256×256 LJ92) is
pulled from a mutex-protected work queue and decoded with per-thread
buffers. Other `dng_area_task` consumers stay serial via an explicit
`MultiThreadSafe()` opt-in.

Multi-DNG best-of-3 wall clock at q=3, all `cmp=OK`, 10/10 deterministic
md5 across runs:

| DNG       | post-metadata-skip | parallel DNG read | saved |
|-----------|-------------------:|------------------:|------:|
| Z8Z_0001  |             1024  |              581  | 43%   |
| Z8Z_0067  |              966  |              544  | 44%   |
| Z8Z_5323  |             1158  |              692  | 40%   |
| Z8Z_6693  |             1188  |              704  | 41%   |

Z8Z_0067 across q levels (single-image best-of-3):

| q | encode ms | bytes (MB) | single-frame fps |
|---:|---:|---:|---:|
| 0 |  581 |  3.22 | 1.72 |
| 3 |  544 |  7.81 | **1.84** |
| 5 |  692 | 13.35 | 1.45 |
| 8 |  704 | 16.18 | 1.42 |

Cumulative vs pre-parallelization baseline (2026-05-28 early): Z8Z_0067
went 1571 → 544 ms = **2.89× speedup**. Mac M3 Max: 819 → 212 ms =
**3.86× speedup** on the same fix.

## Post-metadata-skip (commit 5d7767a, 2026-05-28)

Skipping the redundant DNG metadata pre-parse (`gpr_parse_metadata` was
calling `read_dng`/`ReadStage1Image` to populate fields that
`gpr_convert_dng_to_gpr` later overwrites) eliminates ~600 ms of
single-threaded DNG SDK work per image. Bitstream byte-identical at all
q levels (verified by `cmp` on Mac and Pi).

| q | encode ms | bytes (MB) | single-frame fps | vs prior |
|---:|---:|---:|---:|---:|
| 0 |  904 |  3.22 | 1.11 | 1.67× |
| 3 |  966 |  7.81 | 1.04 | 1.63× |
| 5 | 1062 | 13.35 | 0.94 | 1.57× |
| 8 | 1079 | 16.18 | 0.93 | 1.56× |

Multi-DNG verification (best-of-3 wall clock at q=3, all `cmp=OK`):

| DNG       | baseline | optimized | saved |
|-----------|---------:|----------:|------:|
| Z8Z_0001  |    1658  |     1024  | 38%   |
| Z8Z_0067  |    1571  |      966  | 38%   |
| Z8Z_5323  |    1821  |     1158  | 36%   |
| Z8Z_6693  |    1874  |     1188  | 36%   |

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
  exploits these.
- The metadata-skip pass is a pure plumbing fix in `main_c.c` —
  `gpr_parse_metadata` was running `read_dng` (which decodes the full
  raw image into a `dng_simple_image`) just to populate fields that
  `gpr_convert_dng_to_gpr` re-populates from its own `read_dng` call
  moments later. Skipping the redundant pre-parse saves ~600 ms of
  single-threaded Adobe DNG SDK work for any DNG→GPR conversion with
  `input_skip_rows == 0` (the default).
- On M3 Max the same fix lands 40-44% end-to-end (q=3: 819→464 ms).
- Pi 5 is still NOT realistic for 24 fps full-res capture with legacy
  gpr_tools (best single-frame fps ≈ 1.04 at q=3). The intended 24 fps
  embedded capture path is half-res FUSED (`ml2_q3_dec2`), but the latest
  strict Labs target receipt is blocked at 19.98 fps median; 24.93 fps is a
  historical May 26 result that is not currently reproduced.

Recorded 2026-05-28 by Claude during the legacy stills retrain track work.
