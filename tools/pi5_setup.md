# Pi 5 Setup

Use a Raspberry Pi 5 with 64-bit Raspberry Pi OS, adequate power and cooling,
and storage measured under the intended capture workload. Configure network
access and your own login through the OS installation process.

The current target is native 4096 x 3072 Bayer capture with full-frame
1024 x 768 preview from the same `.gvid` at the accepted 20+ fps stand-in
floor. Actual camera sensor/DMA, storage, and display integration remain
unproven. No CNN runs on the camera.

## Build on the Pi

Install the build tools, then clone the fork into a directory you choose:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git pkg-config python3 python3-numpy
git clone https://github.com/dcliftreaves/gpr.git gpr
cd gpr
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
export GPR_ARTIFACT_ROOT="${GPR_ARTIFACT_ROOT:-artifacts}"
mkdir -p "$GPR_ARTIFACT_ROOT"
```

For an existing checkout, start at the CMake commands. Set
`GPR_ARTIFACT_ROOT` to a directory on the storage device being tested.

## Capture validation

Follow [Pi Hardware](../docs/PI_HARDWARE.md) for sustained-write and timing
requirements and [Mission 1 Quick Validation](../docs/GOPRO_MISSION1_QUICK_VALIDATION.md)
for camera-source probing and receipt validation.
[Video Status](../docs/VIDEO_STATUS.md) summarizes the recorded stand-in
evidence. Short kernel benchmarks and advertised card speeds do not establish
sustained capture performance.

The older `pi5_setup.sh` helper contains a synthetic full-resolution
benchmark and a historical storage-budget verdict. Its result is not current
Mission 1 readiness evidence; use the explicit build and validation steps
above for this workflow.

Prior setup and timing iterations are preserved in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
