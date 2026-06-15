# GPR 2.0 Migration Guide

This document walks an integrator from GPR 1.x (stills-only) to GPR 2.0
(stills + raw video). The headline message: **the stills path did not
change.** If you only use `gpr_convert_dng_to_gpr` / `gpr_convert_gpr_to_dng`
and friends, no source changes are required.

## TL;DR

| You currently use… | What changes in 2.0 |
|---|---|
| `gpr_convert_dng_to_gpr` / `_gpr_to_dng` / `_gpr_to_rgb` / etc. | Nothing. Same signatures, same on-disk format. |
| `gpr_tools` CLI for stills | Nothing required. New flags `-D 1` (noise-aware quant) and `-A 1` (ANS coding) are opt-in and default to off. |
| Direct VC-5 encoder library (`vc5_encoder` lib) | The original API is intact. The fused-encoder API in `source/lib/vc5_encoder/fused_encode.h` is new and complementary. |
| Direct VC-5 decoder library | Unchanged. The fast-decode path picked up a 16-bit sign-extension fix; see "Behavior changes" below. |
| Anything new in raw video | New API in `source/lib/vc5_encoder/gpr_video.h`. See below. |

## Stills API: nothing to do

The functions in `source/lib/gpr_sdk/public/gpr.h`
(`gpr_convert_dng_to_gpr`, `gpr_convert_gpr_to_dng`, `gpr_convert_gpr_to_rgb`,
`gpr_convert_raw_to_dng`, etc.) have unchanged signatures and produce
byte-identical output to the corresponding 1.x release when run with the
default settings. The on-disk GPR file format is unchanged and is still
read correctly by Adobe Camera Raw, Lightroom, and Photoshop.

If you opt into `-D 1` (noise-aware adaptive quantization) or `-A 1`
(ANS entropy coding) on the `gpr_tools` CLI, the output is *still* a
valid DNG-compatible GPR file. The internal compression differs, but
any conforming GPR/DNG reader using the bundled SDK will decode it
correctly. Decoders built from GPR 1.x source predating ANS will not
decode ANS files; readers using the 2.0 SDK or `gpr_tools` will.

## The new video API

The video API lives in
[`source/lib/vc5_encoder/gpr_video.h`](../source/lib/vc5_encoder/gpr_video.h).
It is a thin three-thread wrapper over the fused encoder:

```c
GPR_VIDEO_ENCODER *enc = gpr_video_encoder_create(
    width, height, pixel_format, quality,
    ring_depth, writer_callback, user_data);

/* optional, for rate control */
gpr_video_encoder_set_target_bitrate(enc, target_MBps, fps);

/* optional, mirrors gpr_encode_fused_set_denoise() */
gpr_video_encoder_set_denoise(enc, noise_scale, noise_offset, strength);

for (uint64_t tag = 0; tag < N; ++tag)
    gpr_video_encoder_submit(enc, bayer_buf, raw_bytes, tag);

gpr_video_encoder_destroy(enc);   /* implicit flush + thread join */
```

Key points:

- **`pixel_format`** is one of 6 small integers (RGGB12/14/16, GBRG12/14/16).
  See the header for the table.
- **`writer_callback`** is invoked on the writer thread, not your thread.
  It must be thread-safe with respect to anything else it touches. Return 0
  for success, >0 for a recoverable error on this frame (logged in stats
  and continued), or **<0 for a fatal error** that aborts the encoder and
  unblocks any in-flight `_flush()` / `_destroy()`.
- **`frame_tag`** must be a contiguous sequence 0, 1, 2, … because the
  writer thread emits frames in strict tag order. Gaps deadlock the
  writer. Store your wall-clock timestamps yourself, keyed by tag, if
  you need them.
- **Force-cancel**: `gpr_video_encoder_cancel(enc)` is safe to call from
  any thread (including from inside the writer callback), is idempotent,
  and is the right call on app shutdown or user cancellation when you do
  not want to wait for storage I/O to drain.
- **Dual encoder**: drop in `gpr_video_encoder_create_dual(...,
  encoder_count=2, ...)` on machines with 4 or more cores. Sees ~40%
  encoder-bound throughput win on M1.

The container format that wraps the encoder bitstream is described in
[`source/lib/vc5_encoder/gpr_video_format.h`](../source/lib/vc5_encoder/gpr_video_format.h).
Writers and readers for the 32-byte clip header and 16-byte per-frame
headers ship in `gpr_video_format.c`. If you want raw VC-5 bitstreams
without the container, simply do not call the header helpers — the
encoder hands you the inner bitstream directly via the writer callback.

## Build system

- **CMake ≥ 3.5.1** is still the only build system. No new top-level
  targets are required; `cmake .. && make` builds everything including
  the new video test binaries.
- **No new external dependencies.** GPR 2.0 still uses the bundled DNG
  SDK, XMP core, expat, tiny_jpeg, and md5_lib. No external image
  library, no third-party threading library, nothing pulled from a
  package manager.
- **`vc5_encoder` library** now also exports `gpr_video_*` symbols
  alongside the existing VC-5 entry points. Linking is unchanged.

## Behavior changes worth knowing

These changes alter runtime behavior; none of them break source compatibility.

### NEON is auto-enabled on ARM64 builds

In 1.x, NEON intrinsics were gated behind a CMake `-DNEON=1` switch.
In 2.0 the build auto-detects ARM64 and enables NEON by default. Build
times and code size are slightly larger; runtime is materially faster.
To force the scalar fallback on ARM64 (for debugging or comparison),
pass `-DNEON=0` to CMake.

### Default wavelet levels: 2

The new fused encoder applies a **2-level wavelet by default**
(`FUSED_WAVELET_LEVELS=2`). Files are ~35% smaller than 1-level on
clean content for a ~3 dB raw-PSNR cost. **For maximum-fidelity stills,
set `FUSED_WAVELET_LEVELS=1`** at compile time. 1-level produces 19.9 MB
files at 48.2 dB raw PSNR on Z8 ISO 64 q=3, vs 13.0 MB at 45.6 dB at
the 2-level default.

Only 1 and 2 levels are supported. A 3-level cascade was prototyped
and removed because the biorthogonal 5/3 inverse produces visible
ringing when cascaded three times; see
[`docs/operating-envelope.md`](operating-envelope.md) for the rationale
and data.

Note: this knob controls the *new fused encoder*. The legacy 3-level
production GPR encoder used for stills still operates as it did in 1.x.

### Wavelet-domain BayesShrink denoise auto-enables on DNGs

DNG inputs that carry a `NoiseProfile` metadata block now trigger
wavelet-domain BayesShrink denoise on the encode path. Output files
are 3-38% smaller with SSIM 0.9998 against the input. To force-disable,
either strip the `NoiseProfile` tag, or call
`gpr_encode_fused_set_denoise(ctx, 0, 0, 0)` on the fused encoder
context before submitting frames.

### `fast_decode.c` 16-bit sign-extension fix

A latent bug in `fast_decode_lowpass` cast big-endian 16-bit unsigned
lowpass coefficients through `int16_t` before storing into the int32
`PIXEL` band, sign-extending values ≥ 32768 to large negatives. The
serial decoder was always correct. The fast decoder fix is byte-stable
for 1.x bitstreams (whose lowpass coefficients are small enough to not
trigger sign extension) and corrects 2.0-style multi-level lowpass.
**No source change is needed.** If you have stored 2.0 GPR files
decoded by an old fast-decoder, they will reconstruct correctly with
the fixed decoder.

### Default stripe / threading heuristics

The fused encoder picks stripe rows adaptively: 128 above 1200 band
rows, 64 below. Per-band rANS encode runs across 12 threads; per-channel
Pass 1 across 4 threads. To force single-threaded operation for
benchmarking or correctness comparison, set `FUSED_THREADS=1` in the
environment. To force the original split-pass mode (no inline tokenize)
set `FUSED_INLINE_TOKENIZE=0`.

### Knobs introduced in 2.0

| Compile flag / env var | What it does | Default |
|---|---|---|
| `FUSED_WAVELET_LEVELS` | 1 = max-fidelity stills, 2 = video default | 2 |
| `FUSED_LL_DIVISOR` | LL band quantization divisor | 64 |
| `FUSED_LOG_POLYNOMIAL` | Polynomial log curve in unpack; measured slower than LUT/default on the current Pi 5 half-res Labs path | OFF |
| `FUSED_UNPACK_ASM` (env) | Use ARM64 hand-asm unpack | 0 |
| `FUSED_THREADS` (env) | 1 = serial Pass 1 + Pass 2 (debug) | parallel |
| `FUSED_INLINE_TOKENIZE` (env) | 0 = split-pass, 1 = inline-tokenize | inline |
| `DUMP_BAYER` (env, test only) | Write decoded Bayer to disk for inspection | 0 |

See `docs/followups.md` for the parking lot of knobs that are not yet
shipped on by default.

## Performance

See [`docs/operating-envelope.md`](operating-envelope.md) for historical
encoder time, fps, file sizes, PSNR, rate-controller convergence, and
storage-class fit. Current production readiness lives in
`docs/RELEASE_READINESS.md`, `docs/VIDEO_STATUS.md`, and
`docs/LABS_TARGET_BENCH.md`. Historical headline numbers on an M1, Z8 45 MP,
q=3, 2-level:

- ~22 ms per frame in the fused encoder (single context).
- 29.8 fps sustained encoder-bound throughput on a single context, 41.6
  fps on dual encoder (+40%).
- Historical storage simulation sustained 24 fps × 45 MP across both clean and
  noisy content with the rate controller at target=150 MB/s. Current `.gvid`
  and Mission 1 readiness must use the Labs target receipts.
- A78 estimate ~17 fps with dual-encoder mode. The 50 MP × 24 fps × A78
  envelope is not yet closed; see follow-ups.

## API surface stability

For the rest of the 2.x release line, we will treat the following as
stable APIs:

- All existing 1.x `gpr_convert_*` functions in `source/lib/gpr_sdk/public/`.
- The new `gpr_video_*` functions in `source/lib/vc5_encoder/gpr_video.h`.
- The new fused-encoder context functions in
  `source/lib/vc5_encoder/fused_encode.h`.
- The container header functions in
  `source/lib/vc5_encoder/gpr_video_format.h`.

Internal helpers in `source/lib/vc5_common/`, `source/lib/vc5_encoder/`,
and `source/lib/vc5_decoder/` outside the public headers are not part of
the stable API and may change between minor releases.

## Where to ask for help

- Open an issue on GitHub for behavior questions or bug reports.
- See `SECURITY.md` for vulnerability disclosure.
  posture before commercial deployment.
- See `docs/operating-envelope.md` for performance and quality data.
- See `docs/followups.md` for the parking lot of known limitations.
