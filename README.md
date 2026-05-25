# GPR 2.0 — General Purpose Raw, now for video

GPR is a wavelet-based raw image codec built on SMPTE ST 2073 (VC-5) and originally
released by GoPro for compressed Bayer stills inside a DNG-compatible container. **GPR 2.0
extends that codec into a production raw-video pipeline**: a fused single-pass encoder,
a three-thread submit→encode→write pipeline with adaptive bitrate, a simple frame
container, and enough ARM64 NEON to sustain 24 fps × 45 MP onto consumer UHS-II V90
microSD cards. The stills path, CLI, and on-disk GPR format are unchanged and remain
fully compatible with Adobe Camera Raw, Lightroom, and Photoshop.

## What's new in 2.0

- **Fused encoder** — Bayer unpack → 2-level wavelet → quantize → frequency count in
  one streaming pass with no full-frame intermediate arrays. ~22 ms per 45 MP frame
  on an M1 at q=3, including NEON color conversion, NEON vertical/horizontal filters,
  and NEON-vectorized frequency counting.
- **Pipelined video API** — `gpr_video_encoder_create()` in
  `source/lib/vc5_encoder/gpr_video.h`. Caller, encoder, and writer run on
  separate threads with two SPSC ring buffers; submit() applies natural
  backpressure to the caller.
- **Adaptive bitrate** — proportional rate controller modulates per-frame
  quantization toward a target MB/s, smoothing the 3-4× content swing between
  clean ISO 64 and noisy ISO 22800 down to within 7%.
- **Dual-encoder ping-pong** — opt-in `gpr_video_encoder_create_dual(..., 2, ...)`
  runs two fused-encoder contexts in parallel, dispatched by frame tag.
  +40% throughput on M1 in the encoder-bound regime.
- **Container format** — `gpr_video_format.h` defines a self-describing
  32-byte clip header + 16-byte per-frame headers. Decoders can seek and
  reject incompatible versions without parsing bitstream content.
- **Wavelet-domain BayesShrink denoise** — auto-enabled on DNG inputs that
  carry a `NoiseProfile`. 3-38% size win at SSIM 0.9998.
- **Production-ready signaling** — writer callback can return `<0` for fatal
  I/O errors (encoder aborts, drops pending frames, unblocks destroy);
  `gpr_video_encoder_cancel()` provides force-cancel from any thread.
- **ARM64 NEON paths** auto-enabled on ARM64 builds. Optional polynomial-log
  curve (`FUSED_LOG_POLYNOMIAL=ON`) tuned for Cortex-A78 L1d caches.
- **Six test binaries** covering band-level roundtrip, full PSNR, edge sizes,
  pipeline simulation with throttled storage, force-cancel/abort, and full-chain
  integration.

## 30-second quick start

```bash
git clone https://github.com/gopro/gpr
cd gpr
mkdir build && cd build
cmake .. && make
# stills:
./source/app/gpr_tools/gpr_tools -i ../data/samples/input.DNG -o output.GPR
# video round-trip test:
./source/app/test_video_full_roundtrip
```

## Encode a video frame in 10 lines of C

```c
#include "gpr_video.h"

static int write_frame(void *u, const uint8_t *bs, size_t n, uint64_t tag) {
    return fwrite(bs, 1, n, (FILE *)u) == n ? 0 : -1;
}

FILE *out = fopen("clip.gvid", "wb");
GPR_VIDEO_ENCODER *enc = gpr_video_encoder_create(
    /*width=*/8256, /*height=*/5504, /*pixel_format=*/4 /*RGGB16*/,
    /*quality=*/3,  /*ring_depth=*/3, write_frame, out);
gpr_video_encoder_set_target_bitrate(enc, /*MB/s=*/150.0, /*fps=*/24.0);
for (uint64_t tag = 0; tag < n_frames; ++tag)
    gpr_video_encoder_submit(enc, bayer_buf, raw_bytes, tag);
gpr_video_encoder_destroy(enc);   /* flushes + joins */
fclose(out);
```

For the dual-encoder variant, swap in `gpr_video_encoder_create_dual(..., 2, ...)`
on machines with ≥4 cores.

## Architecture

```
Caller thread       Encoder thread          Writer thread
─────────────       ──────────────          ─────────────
    submit() ─→  input ring ─→  encode  ─→  output ring  ─→  writer_fn()
```

Two SPSC ring buffers. The encoder thread owns one fused-encoder context
that internally uses 4 worker threads (channel-parallel Pass 1, band-parallel
Pass 2). One encoder thread is enough because the inner fused encoder already
saturates 4 cores; `encoder_count=2` ping-pong mode adds a second context for
high-core machines.

`submit()` blocks when the input ring is full — natural backpressure to the
caller. The encoder blocks when the output ring is full — natural backpressure
on slow storage (microSD GC pauses, etc.).

See `source/lib/vc5_encoder/gpr_video.h` for the full API contract and
`docs/operating-envelope.md` for measured numbers.

## Documentation

**Read-this-first artifacts (post-2026-05-25 work):**

- `docs/AUTONOMOUS_RUN_2026-05-25.md` — most recent session summary, links to everything below
- `docs/SHIP_DECISION.md` — three options for shipping the CNN-aware quant work
- `docs/SPEC.md` — formal bitstream format specification (the OEM-contributable artifact)
- `docs/methodology_cnn_aware_quant.md` — AccelIR-style per-subband quant calibration methodology
- `docs/quant_calibration_findings.md` — rate-distortion empirical data
- `docs/perf_findings_20260525.md` — playback pipeline profile + bottleneck analysis
- `docs/ENV_VAR_CLEANUP.md` — env-var inventory + future spec-cleanup plan
- `docs/CAPABILITIES.md` — capability matrix (auto-generated by `tools/test/test_capabilities.py`)

**Background:**

- `docs/operating-envelope.md` — measured fps, file sizes, PSNR, and storage-class fit
- `docs/v2-migration-guide.md` — upgrade notes from the original stills-only GPR
- `docs/raw-video-landscape.md` — codec ecosystem and patent landscape research
- `docs/followups.md` — known follow-ups and parking lot
- `docs/architecture.md` — original VC-5 / GPR codec architecture notes
- `docs/format-spec-v2.md` — bitstream and container specifications (predates `docs/SPEC.md`)
- `CHANGELOG.md` — what changed in 2.0
- `PATENTS.md` — patent posture for prospective deployers

Example test binaries (built from `source/app/test_video_*.c`) double as
example code. They cover band-level decode verification, full PSNR
measurement, pipeline simulation under throttled storage, and abort/force-cancel
flows.

## Build requirements

- **CMake ≥ 3.5.1** (per the existing GPR build)
- **C99 + C++11** toolchain
- **pthreads** (POSIX or Windows)
- **ARM64 NEON** is auto-enabled on ARM64 builds (M1, M2, Cortex-A76+ / A78)
  and is the path that meets the 24 fps × 45 MP envelope. The codec also
  builds on x86_64 with the scalar paths.
- No new external dependencies beyond what GPR 1.x already required.

Tested on:
- macOS 14 / Apple Silicon with Xcode 15
- Linux x86_64 with gcc 9+
- Windows 10/11 with Visual Studio 2019/2022 (see `.github/workflows/`)

## License

GPR 2.0 is dual-licensed under Apache-2.0 or MIT at your option, identical to
the original GPR release.

- `LICENSE-APACHE` — Apache License, Version 2.0
- `LICENSE-MIT` — MIT License

### Patent posture

The Apache-2.0 patent grant covers GoPro's own VC-5 / CineForm / GPR-related
patents. It does **not** grant patent rights from third parties. Notably, the
codec performs Green Average Subtraction (GAS) pre-processing inherited from
upstream CineForm/GPR, which arguably reads on the RED `'384` GAS patent
family (priority 2013, expiry Feb 2034). Operating the codec for in-camera
raw video at 2K+/23+ fps additionally falls within the RED `'967` claim
family (priority 2007, expiry Apr 2028).

These are not legal conclusions; they are landscape sketches a clearance
attorney would want to confirm. See `PATENTS.md` for a concise statement
and `docs/raw-video-landscape.md` for the detailed research.

## File types (recap from GPR 1.x)

- **RAW / CFA RAW** — Bayer sensor data, no metadata.
- **DNG** — Adobe's open raw container; GPR stores its compressed bitstream
  inside a DNG-compatible structure for stills.
- **GPR** — DNG container + VC-5 compressed Bayer (stills).
- **GVID** — the new video container introduced in 2.0
  (`source/lib/vc5_encoder/gpr_video_format.h`). Clip header + per-frame
  headers wrapping a sequence of VC-5 bitstreams.
- **VC5** — raw VC-5 essence with no container or metadata.
- **PPM / JPG** — uncompressed RGB and lossy preview outputs used by
  `gpr_tools`.

## Trademarks

GoPro and CineForm are trademarks of GoPro, Inc. DNG, Photoshop and
Lightroom are trademarks of Adobe Inc.
