# fuzz_decoder

Fuzz harness for the GPR raw-video decode path. Production decoders read
attacker-controlled bytes; this scaffolding finds the bugs that
hand-written tests miss.

## What's fuzzed

The harness in `main.c` (`LLVMFuzzerTestOneInput`) exercises:

1. **`gpr_video_read_clip_header`** and **`gpr_video_read_frame_header`**
   — the container parser, the first thing a decoder sees on the wire.
2. **`jans_decode_band_x4`** — the 4-way interleaved rANS band decoder
   used by the fused encoder/decoder pipeline. Fired against each
   parsed frame's payload, plus once on the raw input (so band bugs are
   reachable without a parseable container).

Constraints the harness enforces on adversarial input:

- Output band buffers are bounded by `MAX_BAND_WIDTH x MAX_BAND_HEIGHT`
  (currently 2048 x 2048).
- The frame loop is capped at 64 iterations and bails when a declared
  `payload_size` overruns the remaining buffer.
- Inputs over 16 MB are skipped to keep the fuzzer fast.

## Building

This subdir is **opt-in** — it isn't wired into the root
`add_subdirectory` chain. Two ways to build:

### `build.sh` (recommended, direct clang)

Prerequisite: an in-tree build of the libs so that
`build/source/lib/*/lib*.a` exist:

```
cmake -S . -B build && cmake --build build -j
```

Then:

```
./source/app/fuzz_decoder/build.sh             # build both variants
./source/app/fuzz_decoder/build.sh fuzzer      # libFuzzer only
./source/app/fuzz_decoder/build.sh standalone  # standalone only
```

Outputs:
- `/tmp/fuzz_decoder` — libFuzzer + ASan build (needs Clang with
  `-fsanitize=fuzzer`; on macOS this means a recent
  Homebrew or Xcode Clang).
- `/tmp/fuzz_decoder_standalone` — plain build, runs anywhere.

### CMake

```
cmake -S source/app/fuzz_decoder -B build-fuzz_decoder
cmake --build build-fuzz_decoder
```

Builds the standalone variant only. Same prerequisite (the libs must
already be compiled under `build/`).

## Running

### libFuzzer

```
/tmp/fuzz_decoder source/app/fuzz_decoder/corpus/ -max_total_time=300
```

Crashes are written to `crashes/` (created by libFuzzer in the cwd).
Reproduce a crash by passing the crash file as the only argv:

```
/tmp/fuzz_decoder crashes/crash-abc123
```

### Standalone (no libFuzzer dependency)

Run against a list of files; installs a SIGSEGV/SIGABRT/SIGBUS/SIGFPE
handler and reports which input crashed:

```
/tmp/fuzz_decoder_standalone source/app/fuzz_decoder/corpus/*.gvid
```

Exit status: 0 if all inputs survive, non-zero if any crashed.

## Corpus

Seeds in `corpus/`:

- `happy.gvid` — known-good output from `test_video_full_chain`.
- `truncated_64.gvid` — first 64 bytes only (exercises short-input paths
  in the container parser).
- `flipped_magic.gvid` — first 2048 bytes with byte 0 XOR'd (exercises
  the magic-mismatch path).

Generate fresh seeds by running:

```
./build/source/app/test_video_full_chain && \
  cp /tmp/test_video_full_chain_happy.gvid source/app/fuzz_decoder/corpus/
```

Add interesting crash-repro inputs from libFuzzer back into `corpus/`
once their underlying bug is fixed, to prevent regressions.
