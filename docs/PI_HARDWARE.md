# Pi 5 Hardware

Raspberry Pi 5 with 64-bit Raspberry Pi OS is the conservative capture
stand-in. Provide cooling, adequate power, and storage measured under the
actual workload. The recorded setup used an 8 GB Pi 5. Hardware capacity alone
does not establish camera readiness.

## Setup

Build with the portable CMake commands in [Getting Started](GETTING_STARTED.md).
Choose an artifact directory on the storage device being evaluated through
`GPR_ARTIFACT_ROOT`; do not assume a particular mounted volume or device name.

The current workload is native 4096 x 3072 Bayer FUSED capture and full-frame
1024 x 768 preview from the same `.gvid`. Use the matching codec profile,
pixel format, source provenance, and frame count when comparing runs.
[Video Status](VIDEO_STATUS.md) summarizes the existing 20+ fps receipts.

## Storage and timing

Measure sustained writes beyond page-cache buffering, including the chosen
flush policy, frame-size distribution, noisy-content behavior, and thermal
state. Derive required bytes/second from actual encoded bytes and target fps.
A card's advertised speed or class is not a sustained capture receipt.
The selected Pi evidence includes a Lexar SILVER PLUS write-budget pass;
that result is specific to the recorded setup.

Record whole-run wall throughput separately from per-frame median timing.
Include p95/p99 frame times, drops, memory, temperature, output hashes,
decode validation, and interrupted-tail behavior. RAM-only output and short
cached runs are diagnostics, not storage closure.

For genuine camera tests, use
[Mission 1 Quick Validation](GOPRO_MISSION1_QUICK_VALIDATION.md).
A file replay or simulated DMA source on a Pi remains stand-in evidence even
if it meets the timing target.

Full-resolution legacy still encode timings are a different workload; see
[Stills Pi 5 Timing](STILLS_PI5_TIMING.md). Prior storage estimates and
half-resolution runs are preserved in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
