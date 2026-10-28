# Calibrated stock RAW to deep ProRes

The optional macOS workflow renders stock GVID v2/v3 or the private GVS2/GVS3
MOV transport to ProRes 422 HQ or 4444. It can apply the same explicit 1x/2x
Bayer reconstruction used by editable export. Compressed stock input is decoded
to Bayer counts, packaged with its actual frame calibration as a DNG, and
processed by `CIRAWFilter`. The renderer uses the RAW output image, never an
embedded thumbnail or the legacy SDK's preview RGB conversion.

This is an offline desktop workflow. It is not a Pi renderer or an on-camera
ProRes encoder. It does not establish model, temporal or final rendered-image
quality approval.

## Build and use

macOS 12 or newer and CMake 3.16 or newer are required. The native tools link
Apple system frameworks; FFmpeg is required only for independent probing and
development decoding. Runtime Python uses the standard library unless a CNN is
explicitly requested.

```sh
cmake -S . -B build-render -DCMAKE_BUILD_TYPE=Release \
  -DGPR_BUILD_SDK=OFF -DGPR_BUILD_STILL_APPS=OFF -DGPR_BUILD_LEGACY_CLI=OFF \
  -DGPR_BUILD_STOCK_VIDEO_EXPERIMENT=ON -DGPR_BUILD_RENDER_TOOLS=ON
cmake --build build-render --target stock_video gpr_render gpr_prores --parallel 4

python3 tools/stock_prores.py recording.gvid --output rendered.mov \
  --decoder build-render/source/app/stock_video/stock_video \
  --renderer build-render/gpr_render --encoder build-render/gpr_prores \
  --ffprobe /path/to/ffprobe --profile hq
```

`--profile 4444` selects ProRes 4444. `--metadata-file calibration.json` supplies
default `gpr.raw_metadata.v1` calibration: per-frame calibration takes precedence,
then clip calibration, then this default. Missing or mismatched calibration is
an error. MOV input additionally requires `--mov-bridge /path/to/gpr_mov`; the
private transport's full-file identity and framing are checked before rendering.

Optional reconstruction adds `--checkpoint /path/to/weights.pt --device mps`
and explicit `--scale 1` or `--scale 2`. The bundled architecture is the default;
`--cnn-root` remains an explicit external override. Scale must match the model.
2x uses the same crop/EXIF/Bayer-site GainMap transforms and unsupported-opcode
rejections as [editable reconstruction](stock-cnn-portable.md). Weights remain
external, and none is selected by default. [Candidate quality](stock-sr-training.md)
and its shadow regression still apply.

## Color and precision contract

- Each DNG contains the decoded or reconstructed Bayer pixels and its typed
  calibration. Source white balance, baseline exposure, crop, EXIF orientation
  and decoder-supported lens processing are retained. Calibration is not cached
  across frames. Geometry changes that alter rendered dimensions require
  separate output clips.
- RAW decoding uses full resolution and disables draft mode, adjustable noise
  reduction, sharpening, detail, contrast, moire reduction, global boost and local
  tone mapping. Exposure adjustment is zero. Remaining RAW decoder behavior,
  including gamut/highlight processing, is Apple's implementation; decoder and
  OS versions and effective white balance are recorded per frame.
- Core Image renders a **16-bit integer RGBA TIFF with an embedded Rec.709 ICC
  profile**. The ProRes writer receives **16-bit big-endian ARGB**, respecting its
  independently allocated row pitch. There is no 8-bit RGB intermediate.
- This is **SDR Rec.709**; the transfer curve still applies when global RAW tone
  boost is disabled. Values outside the integer SDR range can clip. This is not
  log, HDR, ACES or a scene-linear floating-point master.
- Apple ProRes HQ output independently probes as 10-bit 4:2:2; 4444 probes as
  12-bit 4:4:4 with an opaque alpha plane. Deep RGB input does not imply stock
  sensor precision: the historical encoder's 12-bit logarithmic transform and
  any CNN artifacts remain in its decoded data.
- Output dimensions equal the oriented/cropped RAW render. No implicit center
  crop, resizing, guessed white balance or earlier custom "mission" look is
  applied. Broader colorimetric, lens-opcode and grading validation remains open.

Apple documents EXIF orientation values in
[CIRAWFilter.orientation](https://developer.apple.com/documentation/coreimage/cirawfilter/orientation).
The installed Apple `AVAssetWriterInput.h` deep-input contract recommends
`kCVPixelFormatType_64ARGB` and forbids output scaling/color matching for that
path. This implementation pre-renders exact dimensions, tags the pixel buffers
with Rec.709, and appends explicit-duration image sample buffers. Independent
FFprobe checks confirm the resulting color tags and component formats.

## Timeline, resources and publication

Original frame timestamps remain in the receipt as unsigned absolute nanoseconds.
MOV starts at zero relative to the first frame. Its timescale defaults to
1,000,000,000 ticks/s; powers-of-ten coarsening handle the MOV 32-bit sample-duration
limit for large gaps. Rounding error is reported, and timestamps that collapse
onto one tick are rejected. Every frame has an explicit duration: the next
timestamp difference, or a rounded nominal frame period for the final frame.
The movie and track timescales agree, avoiding a default 600-tick movie edit.

The complete input, checksums and calibration are validated before loading a
model. A second pass checks frame identity, and input file hashes are checked
again before encoding. The current decoder/CNN adapter requires **RGGB14**.
There is no recovery mode for incomplete recordings. First export a deliberately
recovered clip if that is required.

The wrapper stages all rendered TIFFs in a private directory beside the output;
scratch disk use grows with the recording. RAW/DNG scratch files are reused one
frame at a time. Limits are 100,000 frames, 128 million rendered pixels per frame,
32,768 pixels per dimension and 2 GiB per native input image. Apple's decoder can
reject smaller or otherwise unsupported DNGs; no preview fallback is allowed.
Native frame buffers remain bounded by frame geometry, but this is not a
bounded-storage streaming transcoder. Rendering very large frames requires
corresponding host memory. Native writer readiness/finalization waits are bounded.

The wrapper verifies every output packet's PTS/DTS, duration and sync flag, track
duration, dimensions, component format, codec/profile and Rec.709 tags through
FFprobe before publication. This is not a full entropy decode of every output
frame; development tests also independently decode the generated ProRes.
Output and JSON receipt are published exclusively using the common still-tool
rollback/copy-fallback behavior. Existing files and dangling symlinks are
protected. This is not group-atomic publication or a durability/fsync claim.

## Validation and measured examples

`GPR_BUILD_RENDER_TESTS=ON` adds `stock_prores` to CTest and requires the stock
video experiment, NumPy, tifffile, FFmpeg and FFprobe. Eight tests check all eight
orientations against independent array transforms, white balance/color-matrix
changes, compensated black/white shifts, crop geometry, an oriented 318-pixel-wide deep-buffer path, stage-two Bayer GainMaps,
HQ/4444 independent decoding, irregular nanosecond timing, a six-second gap with
an adaptive clock, changing per-frame calibration, uint64 absolute timestamps,
truncated input, malformed native timestamps and exclusive publication. Tests
use synthetic 512x384 Bayer data; real 12 MP runs provide additional evidence.

Initial M5 Max functional runs (single runs, not repeat-based benchmarks):

| Workflow | Output | Time before publication |
|---|---|---:|
| Supplied-camera 12-frame stock replay, no CNN | 4096x3072 HQ, 68.25 MB | 6.29 s |
| One real camera frame via private MOV, existing explicit 1x model | 4096x3072 HQ, 5.68 MB | 1.78 s |
| One real camera frame, fresh explicit 2x candidate | 8192x6144 4444, 34.34 MB | 6.49 s |

The last run spends 0.472 s inside the recorded tiled MPS reconstruction call;
the 1x call records 0.447 s. End-to-end times also include validation, model
loading where requested, Bayer decoding, calibrated DNG packaging, deep TIFF
rendering, native ProRes writing, hashes and FFprobe verification. They exclude
final publication/fsync and are not live frame-rate measurements. The 12-frame
input is the same USB-SSD still replay used in [MOV testing](stock-mov.md), with
its actual bursty timestamps, not a continuous live sensor capture. No CNN or
ProRes rendering was measured on Pi.

[Functional run receipts and source/binary hashes](stock-prores-receipts/runs.json),
[Release/sanitizer checks](stock-prores-receipts/validation.json) and
[relocated packages](stock-prores-receipts/packages.json) record this milestone. Image data and model weights remain
outside Git. Audio, SMPTE timecode, custom grading looks, streaming scratch
reduction, broader format adapters and temporal/rendered quality approval remain
unfinished.
