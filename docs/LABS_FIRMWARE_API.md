# Labs Firmware Integration Contract

Last refreshed: 2026-06-15

This document defines the firmware-facing contract required before `.gvid`
capture can move from repository prototype to Labs target integration.

## Scope

The firmware prototype captures Bayer frames, encodes each frame with the
existing FUSED `.gpr` path, and writes a `.gvid` stream. Desktop tools perform
unpack, review rendering, and ProRes export.

The firmware contract deliberately excludes desktop CNN restoration, ProRes
encoding, and arbitrary scene routing.

## Input Frame Contract

| field | requirement |
|---|---|
| buffer | one Bayer frame, caller-owned until `submit` returns or the async retain contract is explicitly enabled |
| format | Bayer raw, packed or unpacked layout must be declared in metadata |
| bit depth | declared per stream; decoder must not infer from payload size |
| width/height | nonzero, fixed for a stream |
| stride | bytes per row, declared for each plane or packed stream |
| timestamp | monotonic capture timestamp in microseconds or nanoseconds |
| frame index | monotonic `uint64_t`; used as `.gvid` frame tag |

## Encoder Lifetime

```c
typedef struct gpr_labs_encoder gpr_labs_encoder;

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t stride_bytes;
    uint16_t bit_depth;
    uint16_t pixel_format;
    uint16_t quality;
    uint32_t fps_x1000;
    uint32_t target_kbps;
    uint32_t max_inflight_frames;
} gpr_labs_encoder_config;

typedef struct {
    const uint8_t *data;
    size_t size_bytes;
    uint64_t frame_index;
    uint64_t timestamp_ns;
} gpr_labs_frame;

typedef int (*gpr_labs_write_cb)(void *user, const uint8_t *data, size_t size);

gpr_labs_encoder *gpr_labs_encoder_create(const gpr_labs_encoder_config *cfg,
                                          gpr_labs_write_cb write_cb,
                                          void *write_user);
int gpr_labs_encoder_submit(gpr_labs_encoder *enc, const gpr_labs_frame *frame);
int gpr_labs_encoder_flush(gpr_labs_encoder *enc);
void gpr_labs_encoder_destroy(gpr_labs_encoder *enc);
```

This is an integration contract, not yet a committed public C API. The existing
shipping source remains `source/lib/vc5_encoder/gpr_video.h` and
`source/lib/vc5_encoder/gpr_video_format.h`.

## Memory Ownership

| object | owner | lifetime |
|---|---|---|
| input frame | camera pipeline | valid through `submit` for synchronous mode |
| encoder state | Labs encoder | `create` to `destroy` |
| output bytes | encoder until callback returns | callback must copy or write before returning |
| `.gvid` stream handle | caller or callback implementation | responsible for flush/fsync policy |

For a firmware target, the default contract should be synchronous submit with
bounded scratch memory. Async submit is allowed only if `max_inflight_frames`
is nonzero and the retain/release contract is tested.

## Metadata Contract

The `.gvid` stream is the byte container. Stream metadata travels beside it as
a sidecar or target receipt until a firmware-owned metadata path is defined.
Required metadata for Labs review:

| field | requirement |
|---|---|
| pixel format | declared explicitly; decoder must not infer it from payload size |
| bit depth | declared per stream |
| frame tags | match `.gvid` frame tags exactly and remain monotonic |
| timestamps | monotonic capture timestamps with declared time unit |
| source dimensions | source and capture dimensions recorded when decimation is used |
| dropped frames | index and timestamp recorded when a frame is rejected or dropped |
| target role | `stand-in` or `camera`, so Pi proxy evidence cannot be mistaken for firmware-ready camera evidence |

Existing metadata tooling is documented in
`docs/GVID_METADATA_DISPATCH_2026-06-04.md`; target runs additionally normalize
the same evidence into `gpr_labs_camera_handoff_receipt.v1`.

## Output Stream Contract

The stream starts with one 32-byte `.gvid` clip header, followed by one 16-byte
frame header and payload per encoded frame. Strict v1 rules:

- magic and version must match,
- flags may only use defined v1 bits,
- reserved fields must be zero,
- width, height, and fps must be nonzero,
- fps and target bitrate inputs must be finite and fit their v1 scaled
  `uint32_t` fields before serialization,
- pixel format must be in `0..5` and quality must be in `0..11`,
- rate-control flag and target bitrate must agree,
- frame payloads must be nonzero and bounded by the containing file.

## Backpressure And Drops

| condition | required behavior |
|---|---|
| encoder queue full | return a retry/backpressure code before accepting ownership |
| writer callback failure | stop accepting frames, flush recoverable bytes, return hard error |
| storage below sustained bandwidth | drop policy must be explicit: reject new frame or end clip; never silently skip without metadata |
| dropped frame | record dropped frame index/timestamp in sidecar or stream metadata plan |
| timestamp discontinuity | return validation warning or hard error based on configured policy |

## Partial-File Recovery

A valid interrupted `.gvid` file is any stream with a valid clip header and
whole frame records up to EOF. Readers should:

- accept EOF after a complete frame payload,
- reject EOF inside a frame header or payload,
- report the number of complete frames recovered,
- compare recovered count against `frame_count_hint` when nonzero.

## Target Bench Requirements

Before claiming firmware readiness, the prototype needs a receipt that records:

- sustained fps median/p95/p99,
- encode ms/frame,
- writer MB/s,
- max RSS or heap high-water mark,
- CPU utilization,
- temperature,
- dropped-frame count,
- output checksum and post-run decode validation.

The Pi 5 may stand in for early Labs evaluation, but the receipt must label it
as a stand-in and not as final camera-firmware evidence.

## Camera Handoff Receipt

Firmware or target runs should write a compact JSON receipt with schema
`gpr_labs_camera_handoff_receipt.v1` and validate it with:

```bash
python3 tools/check_labs_camera_handoff_receipt.py \
  /path/to/camera_handoff_receipt.json
```

Pi stand-in `labs_target_bench.json` receipts can be converted into the same
schema. The manual self-hosted target workflow does this automatically after
`tools/run_labs_target_bench.py`:

```bash
python3 tools/labs_target_to_camera_handoff_receipt.py \
  /path/to/labs_target_bench.json \
  --output /path/to/camera_handoff_receipt.json \
  --target-name "Pi 5 stand-in" \
  --target-role stand-in
```

Required sections:

| section | purpose |
|---|---|
| `target` | hardware name and `role`: `stand-in` or `camera` |
| `integration` | frame source, memory ownership, write path, and whether sensor/DMA and storage handoffs executed |
| `input_frame` | width, height, stride, bit depth, pixel format, target fps |
| `capture` | requested/written/dropped frame counts |
| `timing` | fps median and frame-time percentiles |
| `storage` | write throughput and flush policy |
| `memory` | heap high-water mark or RSS |
| `output` | `.gvid` checksum and validation result |
| `interruption_recovery` | truncated-tail rejection and recovered-frame proof |
| `verdict` | firmware-ready, target-evidence, fps-target, and no-drop booleans |

`integration.storage_handoff` is required for camera receipts. It records
whether the real camera storage path ran, the storage medium, and who owns the
write buffer. Stand-in receipts may set `executed=false`; firmware-ready
camera receipts must set it to `true`.

`verdict.firmware_ready=true` is accepted only for `target.role=camera` with
sensor/DMA handoff executed, storage handoff executed, target fps met, no
drops, valid `.gvid`, and interruption recovery proven. A blocked camera
receipt must include
`blocker.cause` so the failure is narrowed to hardware handoff, storage,
thermal, memory, codec timing, or another concrete cause.
