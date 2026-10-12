# GPR FFmpeg Codec

Adds a fused VC-5 decoder to a local FFmpeg build, with `GPRr` and `GPR1` MOV
tags. Output is 16-bit RGGB or GBRG Bayer. Applications must use this patched
FFmpeg build to recognize the codec.

## Build

Requires GPR static libraries built in Release mode, FFmpeg n8.0 sources,
a C compiler, make, Python 3, and pkg-config. SDL2 is optional for ffplay.
On macOS, install Xcode command-line tools; satisfy any architecture-specific
assembler requirements reported by FFmpeg configure.

From the GPR repository root:

```sh
export GPR_ROOT="$PWD"
export GPR_BUILD="$GPR_ROOT/build"
export FF_ROOT="$GPR_ROOT/external/ffmpeg_gpr"
cmake -S "$GPR_ROOT" -B "$GPR_BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$GPR_BUILD" --parallel
git clone --depth=1 --branch=n8.0 https://github.com/FFmpeg/FFmpeg.git "$FF_ROOT"
"$GPR_ROOT/tools/gpraw_codec/install_patch.sh" "$FF_ROOT"
cd "$FF_ROOT"
"$GPR_ROOT/tools/gpraw_codec/configure_and_build.sh"
./ffmpeg -hide_banner -decoders
```

`GPR_BUILD` accepts any compatible CMake build directory; headers come from
`GPR_ROOT/source`. Prefer absolute paths when switching directories.
`PREFIX` defaults to the FFmpeg working directory's `install-gpr`; the script
builds in place and does not install. Set `PKG_CONFIG_PATH` for dependency
prefixes. ffplay is built when SDL2 is detected.

`install_patch.sh` uses its first argument, then `FF_ROOT`, then
`$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr`. If unset, `GPR_EXTERNAL_ROOT` defaults
to `gpr_work` under `RUNNER_TEMP`, `TMPDIR`, or the system temporary directory.
Set paths explicitly for persistent builds.

## Validate and Use

After the static FFmpeg build, run on macOS:

```sh
"$GPR_ROOT/tools/gpraw_codec/test_roundtrip.sh"
"$FF_ROOT/ffmpeg" -i input.gpraw -pix_fmt rgb24 -frames:v 100 frame_%04d.png
"$FF_ROOT/ffmpeg" -i input.gpraw -c:v prores_ks -profile:v 3 out.mov
# When SDL2 was available at build time:
"$FF_ROOT/ffplay" -vf scale,format=rgb24 input.gpraw
```

The validator encodes 50 synthetic 1920x1080 frames and compares FFmpeg decoding
against direct `gpr_decode_fused` output byte for byte. It uses `GPR_ROOT`,
`GPR_BUILD`, and `FF_ROOT`. Its optional first argument sets the output
container; otherwise it writes under `GPR_TMPDIR` (default
`$GPR_EXTERNAL_ROOT/tmp`).

Multi-level encoding is required: set `FUSED_MULTI_LEVEL=1` when encoding
(the validator does this automatically). GRBG/BGGR pixel formats are not
wired. This is a local integration, not an upstream codec or a plugin for
applications with bundled FFmpeg.

`gpr.c` is installed by `install_patch.sh`; `ffmpeg_gpr.patch` documents the
registration changes. The original integration is preserved on
`archive/research-and-integration-2026-09-09` at `3d675ef`.
