# Fused Bayer Codec

This optional layer adds the fused encoder/decoder, reusable encoder contexts,
ARM assembly kernels, and coefficient I/O. It depends on the stills
and shared codec commit, but not on the video container or capture API.

The fused payload is distinct from an editable TIFF/GPR file. Use the stills
SDK for conventional GPR/DNG conversion; container and capture support are
separate features built on this layer.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
```

Linux ARM64 builds default to native CPU tuning. Set
`-DFUSED_TUNE_CPU=cortex-a76` for a Pi 5 build or use an empty value for a
generic build. Timing instrumentation and the polynomial log approximation
are opt-in and disabled by default.

For validation procedures, see [Testing Methodology](https://github.com/dcliftreaves/gpr/blob/review/product-validation/docs/TESTING_METHODOLOGY.md)
on the companion `review/product-validation` branch.
