# High-Bit-Depth RAW Stills

This feature extends the existing GPR still-image workflow with unpacked
14/16-bit Bayer input, the four standard 2x2 Bayer phases, and camera metadata
round trips. It does not require the video container, capture API, preview,
Python CNN packages, or desktop video renderer.

The codec is lossy. A 16-bit input/output representation does not imply
lossless preservation of every sensor bit. Retain source originals where
lossless archival is required.

## Build and Convert

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
build/source/app/gpr_tools/gpr_tools -i input.dng -o output.gpr
build/source/app/gpr_tools/gpr_tools -i output.gpr -o decoded.dng
```

Use conventional single-plane CFA DNG inputs. Non-Bayer layouts and
already-demosaiced linear RGB DNGs are not interchangeable with Bayer RAW.
Camera-specific support must be checked with representative inputs; a filename
extension alone is not sufficient.

Native builds enable NEON by default on ARM64. `-DNEON=OFF` disables the
option-controlled paths; some architecture-specific entropy kernels remain
selected by compiler macros. It is not a fully scalar comparison switch.
Neither configuration requires camera firmware integration.

For validation procedures, see [Testing Methodology](https://github.com/dcliftreaves/gpr/blob/review/product-validation/docs/TESTING_METHODOLOGY.md)
on the companion `review/product-validation` branch.
