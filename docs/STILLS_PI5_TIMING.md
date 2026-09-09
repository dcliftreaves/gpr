# Stills Encode Timing on Pi 5

Recorded 2026-05-28 on Raspberry Pi 5 (Cortex-A76), using the legacy
CineForm VC5 encoder through `gpr_tools`. These are single-image,
best-of-three wall timings after the parallel DNG-read changes
(`79403fb` and `ec1cb2c`), not sustained video measurements.

Source: Nikon Z8 Z8Z_0067, 8280 x 5520 RGGB14 (the historical 50 MP-class
fixture label).

| Quality | Encode ms | Output MB | Reciprocal single-frame fps |
|---:|---:|---:|---:|
| 0 | 581 | 3.22 | 1.72 |
| 3 | 544 | 7.81 | 1.84 |
| 5 | 692 | 13.35 | 1.45 |
| 8 | 704 | 16.18 | 1.42 |

At q3, the four recorded fixtures took 581 ms (Z8Z_0001),
544 ms (Z8Z_0067), 692 ms (Z8Z_5323), and 704 ms (Z8Z_6693).
The receipt reports byte comparisons passing and deterministic repeated
outputs. Sizes vary with content; this single image is not a corpus mean.
No CNN or desktop reconstruction time is included.

The optimized DNG reader decodes tiles in parallel on Linux using per-thread
buffers. Earlier metadata-skip and threading iteration tables are preserved in
the [archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/blob/3d675ef/docs/STILLS_PI5_TIMING.md).

These still timings do not support 20 or 24 fps full-resolution capture.
The current embedded prototype uses native 4096 x 3072 FUSED video;
see [Video Status](VIDEO_STATUS.md) for its separate 20+ fps Pi stand-in
evidence and outstanding camera-hardware proof.

Use [Getting Started](GETTING_STARTED.md) for portable conversion commands
and [Testing Methodology](TESTING_METHODOLOGY.md) when reproducing timings.
