# gpraw — GPRaw video container (MOV-wrapped GPR frames)

GPRaw packages a stream of fused-format GPR frames into a single MOV file
with a custom codec tag and rich metadata. Same convention as BRAW, ProRes
RAW, and REDCODE: ISO BMFF (MOV) container, opaque codec payload, frames
remain independent, per-track and per-frame metadata.

## Wire format

| Field           | Value                                                            |
|-----------------|------------------------------------------------------------------|
| Extension       | `.mov`                                                           |
| Container       | ISO BMFF / MOV (libavformat MOV muxer)                           |
| Video codec_tag | `GPRr` (0x47 0x50 0x52 0x72; little-endian 0x72525047 on the wire) |
| `AVCodecID`     | `AV_CODEC_ID_NONE` (tag-only)                                    |
| Frame payload   | Opaque fused-format GPR bytes (FUSED_HEADER + bands)             |
| Keyframes       | Every frame (intra-only)                                         |

Track metadata (file-level mdta atom, surfaces via `ffprobe -show_format`):

* `gpr.codec_version` — e.g. `vc5/2.0+gpr`
* `gpr.quality` — 0..5
* `gpr.cfa_pattern` — `RGGB`, `GBRG`, ...
* `gpr.bit_depth` — 14 or 16
* `gpr.black_level`, `gpr.white_level`
* `gpr.encoder_settings` — JSON blob
* `gpr.source_dng_path`
* `gpr.color_matrix` — 9 comma-separated floats

Per-frame metadata is attached as AVPacket side data of type
`AV_PKT_DATA_STRINGS_METADATA`.

## Build

```
make -C tools/gpraw
```

Depends on Homebrew FFmpeg (`brew install ffmpeg`; tested with 8.0.1).

## Usage

Pack a directory of `.gpr` files into one MOV:

```
gpraw_pack --fps 24 --quality 3 --cfa RGGB --bit-depth 14 \
  --black-level 1008 --white-level 15892 \
  --encoder-settings '{"GPR_INCLUDE_LL":1,"GPR_DECIMATE_AA":1}' \
  INPUT_DIR/ output.mov
```

Unpack:

```
gpraw_unpack output.mov OUTPUT_DIR/
```

Frames in `OUTPUT_DIR/frame_NNNN.gpr` are byte-identical to the inputs.

Inspect:

```
ffprobe -show_streams -show_format output.mov
```

## Library API

See `include/gpraw.h`. Pure C, no dependencies beyond libavformat and
libavutil.

```c
GPRaw_Writer *w = gpraw_writer_create(path, w, h, fps_num, fps_den, &meta);
gpraw_writer_add_frame(w, gpr_bytes, n, ts_ns, NULL);
gpraw_writer_close(w);

GPRaw_Reader *r = gpraw_reader_open(path);
gpraw_reader_get_metadata(r, &meta);
while (gpraw_reader_next_frame(r, &bytes, &n, &ts_ns) == 0) {
    /* decode bytes ... */
}
gpraw_reader_close(r);
```
