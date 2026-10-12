# Fused Bayer Codec

This optional layer adds the fused encoder/decoder, reusable encoder contexts,
ARM assembly kernels, and coefficient diagnostics. It depends on the stills
and shared codec commit, but not on the video container or capture API.

The fused payload is distinct from an editable TIFF/GPR file. Use the stills
SDK for conventional GPR/DNG conversion; container and capture support are
separate features built on this layer.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
ctest --test-dir build --output-on-failure
```

Native tests exercise edge dimensions, split and inline tokenization, and
serial/pool byte equivalence when high-frequency bands are omitted. Additional
round-trip tools accept caller-supplied Bayer fixtures:

```sh
GPR_INCLUDE_LL=1 FUSED_INLINE_TOKENIZE=0 \
  build/bin/test_fused_roundtrip input.raw 4096 3072
```

Linux ARM64 builds default to native CPU tuning. Set
`-DFUSED_TUNE_CPU=cortex-a76` for a Pi 5 build or use an empty value for a
generic build. Timing instrumentation and the polynomial log approximation
are opt-in and disabled by default. Performance comparisons must use the same
profile, compiler flags, source frames, and storage path.

`tools/test/compare_codec_checkpoints.py` compares both encoded payloads and
decoded Bayer bytes from two builds. Supply `--baseline`, `--candidate`, one
or more `--raw` inputs, and `--width`/`--height`. An optional `--environment`
JSON object selects an explicit codec profile; no ambient codec overrides are
inherited. `--receipt` records hashes and results, while scratch payloads are
removed. Byte equivalence is a regression check, not a performance measurement.
