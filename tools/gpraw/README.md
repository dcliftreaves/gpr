# GPRaw MOV Wrapper

This tool packs opaque FUSED frame payloads into MOV and unpacks them for
downstream decoding. It is a compatibility/export wrapper; `.gvid` remains
the primary raw-video capture container. See
[GVID Conformance](../../docs/GVID_CONFORMANCE.md) and
[Getting Started](../../docs/GETTING_STARTED.md).

## Build and use

The Makefile requires a C compiler, `pkg-config`, and the FFmpeg
`libavformat` and `libavutil` development libraries.
Run from the repository root:

```bash
make -C tools/gpraw
export GPR_ARTIFACT_ROOT="${GPR_ARTIFACT_ROOT:-artifacts}"
mkdir -p "$GPR_ARTIFACT_ROOT"
tools/gpraw/gpraw_pack --fps 20 --quality 3 --cfa RGGB --bit-depth 14 \
  --black-level "${GPR_BLACK_LEVEL:?Set the source black level}" \
  --white-level "${GPR_WHITE_LEVEL:?Set the source white level}" \
  "$GPR_ARTIFACT_ROOT/frames" "$GPR_ARTIFACT_ROOT/wrapped.mov"
tools/gpraw/gpraw_unpack "$GPR_ARTIFACT_ROOT/wrapped.mov" "$GPR_ARTIFACT_ROOT/unpacked"
ffprobe -show_streams -show_format "$GPR_ARTIFACT_ROOT/wrapped.mov"
```

Supply compatible FUSED `.gpr` frames under `frames/` in filename order.
Match fps, quality, CFA, bit depth, and black/white levels to the actual
source; these options describe metadata and do not recompress or repair
payloads. Dimensions default to the frame header and can be overridden for
the decoded Bayer output size. Inspect the resulting stream and compare
unpacked payloads before relying on a new FFmpeg build.

## Format and API

The MOV sample tag is `GPRr`, with one intra-frame packet per FUSED payload.
It is not the `GPR1` tag used by the separate
`tools/gpr2prores/gpr_mov_tool` compatibility tool. Raw MOV packets are not
ordinary rendered video and require a compatible decoder.

Metadata fields include codec version, quality, CFA, bit depth,
black/white levels, encoder settings, color matrix, and optional source
traceability. Use portable source identifiers when sharing artifacts.
Container metadata does not broaden the FUSED Bayer-format support.

[include/gpraw.h](include/gpraw.h) defines writer/reader signatures and
ownership. Check create, add-frame, close, and read return values. Reader
payload memory is valid only until the next read or close; copy it if it
must outlive that call. Requested fps determines MOV timing, independently
of measured encode or reconstruction speed.

See [SPEC](../../docs/SPEC.md) for payload details and
[Release Artifacts](../../docs/RELEASE_ARTIFACTS.md) for review delivery.
