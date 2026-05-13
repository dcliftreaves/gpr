# GPR 2.0 Examples

Small, self-contained programs that show downstream users how to use
the GPR 2.0 public API. These are intentionally **not** part of the
main CMake build — they link against the static libraries that the
main build produces so the dependencies are visible at a glance.

## Examples

| File | Language | What it shows |
|------|----------|---------------|
| [`encode_video.c`](encode_video.c) | C | Pipelined raw-Bayer video encoder: `gpr_video_encoder_create` → submit loop → writer callback that emits the container format from `gpr_video_format.h`. Demonstrates the writer-abort path (returning `<0` from the callback shuts the pipeline down cleanly) and prints `gpr_video_stats` at the end. |
| [`decode_dng.cpp`](decode_dng.cpp) | C++ | Stills path: load a `.GPR` file with the gpr_sdk and convert it to a `.DNG`. C++ because the gpr_sdk pulls in the Adobe DNG SDK and a couple of public headers leak C++-only includes; the SDK functions themselves are `extern "C"`. |

## Building

The examples build against the pre-built static libraries in `../build/`,
so make sure the main project is built first:

```bash
cd ..              # repo root
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j
```

Then from the repo root:

```bash
./examples/build_examples.sh
```

That script compiles both examples with `-O2 -Wall -Wextra -Werror`
and drops the binaries in `/tmp/`. Override the output dir by setting
`OUT_DIR=...`.

## Running

### encode_video

Requires a raw Bayer frame on disk. The example assumes 8280x5520
RGGB16 (pixel_format=4), the format produced by Nikon Z8 raw exports.

```bash
/tmp/encode_video /tmp/Z8_ISO64.raw /tmp/clip.gprv
```

Expected output (8-frame test clip):

```
submitted=8  encoded=8  written=8  writer_errors=0
waits  submit=5  encoder=0  writer=8
wrote /tmp/clip.gprv
```

To experiment with the abort path, modify the writer to return `-1`
on, say, frame 3 — you'll see `frames_written < frames_submitted`
and the program exits cleanly without hanging.

### decode_dng

```bash
/tmp/decode_dng ../data/samples/HERO9/GOPR0002.GPR /tmp/decoded.dng
```

The output `.dng` can be inspected with `exiftool`, opened in
Lightroom/RawTherapee/dcraw, etc.

## What's not covered

- **Decoding the video container** (`gpr_video_read_*`): the format
  reader is straightforward to drive from `gpr_video_format.h`; pair
  it with the vc5_decoder for frame-by-frame playback.
- **Dual encoder mode** (`gpr_video_encoder_create_dual`): same API
  shape as the single-encoder path, only the create call changes.
- **Wavelet denoise** (`gpr_video_encoder_set_denoise`): call before
  the first submit; see the docstring in `gpr_video.h`.
