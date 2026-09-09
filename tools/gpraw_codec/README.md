# gpraw_codec — FFmpeg decoder for .gpraw (GPR / fused VC-5)

This adds an `AV_CODEC_ID_GPR` decoder to FFmpeg's libavcodec, mapped to
the `GPRr` MOV codec_tag used by the `.gpraw` container. Once installed,
`ffmpeg`, `ffprobe`, `ffplay`, and any libavformat-based tool (Resolve's
ffmpeg-derived ingest, mpv, etc.) can read `.gpraw` natively — no
ProRes intermediate, no transcode.

## What's here

| File                       | Purpose                                            |
|----------------------------|----------------------------------------------------|
| `gpr.c`                    | The decoder source. Installed into libavcodec/.    |
| `ffmpeg_gpr.patch`         | Human-readable diff against vanilla FFmpeg 8.0.    |
| `install_patch.sh`         | Idempotent script that applies the patch.          |
| `configure_and_build.sh`   | Configures + builds a minimal patched FFmpeg.      |
| `test_roundtrip.c`         | End-to-end byte-identity validator.                |
| `test_roundtrip.sh`        | Build + run the validator.                         |

## Build

```bash
# 1. Make sure libvc5_decoder, libvc5_common, libcommon are built:
cd "$GPR_ROOT/build-local"
make -j

# 2. Clone FFmpeg (n8.0):
export GPR_EXTERNAL_ROOT="${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}"
git clone --depth=1 --branch=n8.0 https://github.com/FFmpeg/FFmpeg.git \
  "$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr"

# 3. Apply patches:
"$GPR_ROOT/tools/gpraw_codec/install_patch.sh" \
  "$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr"

# 4. Configure + build:
cd "$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr"
"$GPR_ROOT/tools/gpraw_codec/configure_and_build.sh"
```

This produces `$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr/ffmpeg` and
`$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr/ffplay`.
`ffmpeg -decoders | grep gpr` should list `V....D gpr  GoPro RAW (fused VC-5)`.

## Validate

```bash
tools/gpraw_codec/test_roundtrip.sh
```

Builds a 50-frame 1920x1080 synthetic `.gpraw`, decodes it twice
(once via the new FFmpeg decoder, once directly via `gpr_decode_fused`),
and asserts byte-identical output.

## Use

```bash
# Probe:
"$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr/ffmpeg" -i input.gpraw

# Convert to PNGs (demosaic via swscale's bayer pixel format support):
"$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr/ffmpeg" -i input.gpraw -pix_fmt rgb24 -frames:v 100 frame_%04d.png

# Transcode to ProRes (when prores_ks encoder is enabled):
"$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr/ffmpeg" -i input.gpraw -c:v prores_ks -profile:v 3 out.mov

# Benchmark decode throughput:
"$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr/ffmpeg" -benchmark -i input.gpraw -pix_fmt bayer_rggb16le -f md5 "$TMPDIR/out.md5"
```

## Constraints / known limitations

- **Multi-level encoding required.** `gpr_decode_fused` cannot reconstruct
  single-level streams (no preserved lowpass). Pack `.gpraw` files with
  `FUSED_MULTI_LEVEL=1` set in the encoder environment.
- **CFA pattern**: RGGB and GBRG are supported (via the header `is_rggb`
  flag). GRBG / BGGR would require additional FFmpeg pixel format wiring.
- **ffplay autograph**: bayer16 → display needs a manual `-vf scale,format=rgb24`
  filter chain. `ffplay -vf scale,format=rgb24 input.gpraw` works.
- **Not yet a real FFmpeg upstream patch.** The codec_id is added at the
  end of the enum to preserve the ABI assertion in `libavcodec/version.c`,
  but the decoder is registered as a static-built component. For
  Homebrew distribution we'd want a configure flag (`--enable-gpr`).

## Next steps

- Pull request to FFmpeg upstream (likely needs a public spec for the
  fused format first, or vendor the decoder as a self-contained file
  with no external lib dependency).
- Homebrew formula that builds `ffmpeg-gpr` as a separate keg.
- DaVinci Resolve uses its own bundled ffmpeg; verify Resolve's ffmpeg
  version matches and produce a build for it.
- Apple Codec Extension (Path 2 in the task spec) for QuickTime / FCP.
