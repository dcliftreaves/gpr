# Getting Started

Run commands from the repository root. The library and command-line still
tools use CMake and a C/C++ toolchain. Python 3 is needed for container and
receipt tools. Desktop ProRes review uses macOS, Apple Silicon, Xcode
command-line tools, and the dependencies named in the playback Makefile.

## Build and convert a still

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
export GPR_ARTIFACT_ROOT="${GPR_ARTIFACT_ROOT:-artifacts}"
mkdir -p "$GPR_ARTIFACT_ROOT"
build/source/app/gpr_tools/gpr_tools -i data/sample.dng -o "$GPR_ARTIFACT_ROOT/sample.gpr" -q 3
build/source/app/gpr_tools/gpr_tools -i "$GPR_ARTIFACT_ROOT/sample.gpr" -o "$GPR_ARTIFACT_ROOT/decoded.dng"
```

Supply your own `data/sample.dng`; that filename is an example, not a bundled
fixture. These commands exercise the codec without a CNN. Approved
CNN-assisted still tiers require the matched weights described in
[Reconstruction](RECONSTRUCTION.md).

## Pack raw-video frames

Place compatible per-frame FUSED `.gpr` payloads in
`$GPR_ARTIFACT_ROOT/frames`, in filename order. Match every header option to
the actual encoded frames; packing does not resize or recompress them.

```bash
python3 tools/gvid_pack.py "$GPR_ARTIFACT_ROOT/frames" "$GPR_ARTIFACT_ROOT/clip.gvid" \
  --width 4096 --height 3072 --fps 20 --quality 8 --pixel-format 1
```

For source metadata, additionally pass
`--metadata "$GPR_ARTIFACT_ROOT/clip.gvid.meta.json"` with a valid
`gvid_source_metadata.v1` sidecar. See [GVID Conformance](GVID_CONFORMANCE.md)
for validation, metadata requirements, and recovery semantics.

Pi/camera capture is a separate integration workflow:
[Pi Hardware](PI_HARDWARE.md) and
[Mission 1 Quick Validation](GOPRO_MISSION1_QUICK_VALIDATION.md).
The accepted stand-in floor is 20+ fps for native 4096 x 3072 capture and
full-frame 1024 x 768 preview. Actual sensor/DMA, storage, and display
handoff are not yet proven; no CNN runs on the camera.

## Desktop review without a model

Complete the Release build above first. The playback Makefile links the
libraries under `build/` by default.

```bash
make -C tools/gpr2prores
tools/gpr2prores/gpr2prores \
  --meta-dng data/sample.dng --no-cnn \
  --demosaic core-image --out-resolution uhd \
  "$GPR_ARTIFACT_ROOT/clip.gvid" "$GPR_ARTIFACT_ROOT/review.mov"
```

The metadata DNG must match the clip's camera and color interpretation.
This is a codec-only rendered review, not CNN reconstruction. MOV/GPR1 is
an optional compatibility/export wrapper; `.gvid` is the primary raw-video
container.

For model-backed 4K cleanup or 8K SR, follow
[Reconstruction](RECONSTRUCTION.md). Those approved paths run offline on
desktop hardware. Weight files and large source fixtures are not included in
this checkout, and the build alone does not reproduce their quality receipts.

## Verification

```bash
python3 tools/test/test_gvid_conformance.py
```

See [Testing Methodology](TESTING_METHODOLOGY.md) for the distinction between
container tests, codec regressions, quality signoffs, and hardware evidence.
