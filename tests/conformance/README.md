# Conformance tests — fused-encoder bitstream stability

This corpus pins the fused GPR 2.0 encoder's output **byte-for-byte**. Any
unintentional change to wavelet, quantizer, tokenizer, or rANS state is caught
the moment a check runs: each encoded bitstream is md5-hashed and compared
against a golden file checked into the repo.

The fused encoder is deterministic — for a fixed input, `pixel_format`,
`quality`, and compile-time `FUSED_WAVELET_LEVELS`, it produces the same
bytes every run. We exercise that with a small synthetic corpus so the
goldens stay tiny and the test is fast.

## Layout

```
tests/conformance/
  inputs/                     # 4 synthetic RGGB14 raw frames (~1 MB)
    gradient_256.raw            256x256 deterministic diagonal ramp
    noise_256.raw               256x256 LCG pseudo-random (seed 0xDEADBEEF)
    edge_512x384.raw            512x384 vertical edge at column 256
    flat_512x512.raw            512x512 constant 8192 (DC preservation)
  golden/                     # 24 md5 hex files (~800 B)
    <input>_q<q>_L<l>.md5       one md5 per (input, quality, levels) combo
  common.h                    # shared helpers (corpus, generators, md5 hex)
  generate.c                  # populates inputs/ and golden/
  check.c                     # verifies encoder vs golden
  build.sh                    # builds 4 binaries (generate/check x L1/L2)
```

The (quality, levels) matrix is **{0, 3, 5} x {1, 2}** for each of the four
inputs — 24 golden files per run.

## Workflow

### Run the conformance check (regression detection)

```
./tests/conformance/build.sh
/tmp/conformance_check_L1   # exits 0 on match, 1 on diff
/tmp/conformance_check_L2
```

Hook this into CI / the pre-PR check: any encoder change that wasn't intended
to alter the bitstream surfaces here.

### Regenerate goldens (intentional encoder change)

```
./tests/conformance/build.sh
/tmp/conformance_generate_L1
/tmp/conformance_generate_L2
git diff tests/conformance/golden/
```

Review every changed md5 before committing — each one is a bitstream change
that downstream decoders need to be aware of.

## Implementation notes

- **Wavelet levels are compile-time.** `FUSED_WAVELET_LEVELS` is a macro
  inside `fused_encode.c`, not a runtime flag. We compile two variants of
  each binary (`_L1` and `_L2`) by re-including `fused_encode.c` directly
  in the link with `-DFUSED_WAVELET_LEVELS={1,2}`. The fresh `.o` overrides
  the matching symbols in the prebuilt `libvc5_encoder.a`; all other
  encoder symbols still resolve from the archive.
- **Threads pinned.** Both binaries set `FUSED_THREADS=1` so the serial
  encode path is exercised. The parallel path is also deterministic in
  practice today, but pinning serial removes any future threading surprise.
- **Pixel format is RGGB14** (`pixel_format=1`) for all four inputs. The
  pattern generators emit 14-bit values directly.
- **Build prereq:** the top-level CMake build must be populated at `build/`
  before running `build.sh`.
