# RAW codec and GVID release workflow

This maintained fork combines the optimized stock-compatible VC-5 codec, bounded non-CNN GVID v3 capture, native preview, high-resolution Bayer support and calibrated DNG/GPR export. The software foundation is independently usable; physical camera acquisition remains an integration task.

## Build and verify

CMake 3.20+ supports the checked-in presets. The core requires a C/C++ toolchain, threads, zlib and Python 3 for its tests. No neural runtime or model weights are required.

```sh
cmake --preset raw-video
cmake --build --preset raw-video
ctest --preset raw-video
```

For the DNG/XMP SDK, independent TIFF checks and the ordered-stills workflow:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tests/requirements-release.txt
cmake --preset raw-video-sdk -DPYTHON_EXECUTABLE="$(command -v python)"
cmake --build --preset raw-video-sdk
ctest --preset raw-video-sdk
```

The preset frontends require POSIX. The portable codec can also be built on Windows; release CI configures that separately. Release CI covers Linux x86-64, Linux ARM64, macOS and portable Windows codec builds. CI execution status belongs to the run for the exact revision; the workflow file alone is not evidence that a run passed.

## Make a movie from camera stills

Prepare a sequence of Bayer DNGs (or GPRs) with matching dimensions, sample domain and CFA. Camera-native formats such as 3FR need a camera-aware converter first. Pass inputs in playback order; filenames should be zero-padded before using a shell glob.

```sh
python tools/raw_sequence.py pictures/*.DNG \
  --sdk build/raw-video-sdk/source/app/gpr_tools/gpr_tools \
  --sample-bits 16 --quality 3 --fps-num 24 \
  --output movie-test
python tools/stock_video.py inspect movie-test/sequence.gvid
python tools/stock_video.py extract movie-test/sequence.gvid \
  --decoder build/raw-video-sdk/source/app/stock_video/stock_video \
  --editable both --out-dir movie-test/editable
```

The workflow accepts 50 or more stills, emits individually usable GPRs plus a checked GVID movie and receipts, and verifies every record. It synthesizes playback timestamps. It does not establish that the camera captured those stills at the playback rate, or that offline encoding met a real-time deadline. Re-encoding an already compressed GPR adds another lossy generation.

A self-contained regression exercises calibrated capture/decode/export across all 12 Bayer/bit-depth combinations:

```sh
python tests/raw_video_workflow.py \
  --capture build/raw-video/gpr_capture_app \
  --decoder build/raw-video/source/app/stock_video/stock_video
```

## Quality and compatibility

Q3 is **Film Scan 1**; Q4 is **Film Scan X**, with gentler fine-band quantization and usually larger files. They are quality settings, not bit depths or fixed bitrates. The low-level encoder and capture frontend default to Q4. The historical SDK conversion calls retain their Q3 default (Q1 when their legacy `fast_encoding` switch is selected); choose `--quality` explicitly in new workflows.

The existing bit-exact streaming, compact-band, direct-band and ARM assembly paths are enabled by default where supported. They do not change the stock quantization tables or introduce a new bitstream. Build with `GPR_ENCODER_FAST_DEFAULT=OFF`, or set the individual `GPR_STREAM_UNPACK`, `GPR_BAND_STREAM`, `GPR_COMPACT_BANDS`, `GPR_DIRECT_BANDS` and `GPR_CHANNEL_ASM` switches to `0` before starting threads, for reference comparisons. CPU pinning remains explicit. The library does not mutate process environment state.

The GVID v3 framing limits are even dimensions up to 16384 per side and 128 Mi pixels total. These are validation ceilings, not memory or speed promises. Capture requires dimensions at least 48. Aligned 11664×8744 X2D crops are supported alongside the existing Bayer formats. Legacy GVID v2 retains its original 8192×6144 and multiple-of-eight limits. Use `gpr_capture_app` for v3 recording; the `stock_video` executable's encoder is a legacy v2 experiment, while its decoder also serves v3 exports.

## Storage qualification

Use the filesystem and operating conditions intended for deployment. A fast encoder does not qualify a storage device.

```sh
python tools/qualify_raw_video.py \
  --capture build/raw-video/gpr_capture_app \
  --input frame.raw --metadata frame.json \
  --quality 3 --seconds 180 --fps 24 --queue 16 \
  --output /path/on/storage/new-qualification-directory
```

`frame.json` is typed calibration from `tools/raw_media.py metadata`, with `--sample-bits` matching the RAW word domain. Supply repeated `--input`/`--metadata` pairs to cycle through distinct fixtures. The replay frontend currently preloads up to 16 fixtures; the offline sequence workflow has no 16-frame limit.

On Linux, the qualifier defaults to asynchronous page-aligned writeback every 8 MiB, plus final file and directory `fsync`; elsewhere writeback defaults to disabled. This schedules writeout and is not an intermediate durability guarantee. `gpr_capture_app --fsync-each` is available when per-frame durability is required, with a different performance envelope. The capture library leaves filesystem durability to the application callback.

Qualification requires every requested frame, no queue overruns, valid records/calibration and a flush-inclusive average within 1% of the requested rate. It separately reports deadline misses; a qualified average does not mean every frame was written within one frame interval. The actual source duration, final flush, peak RSS, thermal/throttling observations and binary hash are retained. Failed runs retain their clips. Successful runs delete their large clip after validation unless `--keep-clip` is selected.

See [the dated release evidence](stock-release-20261121.md) for Pi 5 results and failed configurations. Longer deployment tests, changing scenes, high-noise inputs, different drives, power loss and physical sensor delivery remain the integrator's responsibility.

## Errors, recovery and ownership

Capture has a bounded in-flight count, explicit backpressure, copied or leased RAW input and exact lease-release rules. Writer callbacks must accept all supplied bytes or fail. Short writes and `EINTR` are handled by the replay frontend. Writer failures, cancellation, completion failures, repeated finish, input reuse and concurrent instances have regression coverage. See [the capture API](stock-capture-api.md) before integrating a sensor buffer or storage callback.

Strict GVID parsing requires checksums, contiguous frame indices, increasing timestamps and a valid completion marker. An incomplete recording is not silently accepted. To recover only its verified complete prefix:

```sh
python tools/stock_video.py extract interrupted.gvid --recover \
  --decoder build/raw-video/source/app/stock_video/stock_video \
  --editable both --out-dir recovered-frames
```

The receipt explicitly marks the recording incomplete and records the recovery error. A fast index checks headers and declared checksums without checking payload bytes; its receipt says `headers_only`. Indexing skips the whole-file SHA-256 pass by default; choose `index --hash-clip` when that additional read is wanted. Random-access extraction checks its selected payloads and says `selected_frames`. Use full `inspect` to check every payload. Original recordings are never repaired in place. Capture and export frontends require new output destinations, preventing accidental overwrite. CRCs detect corruption; they are not authentication or a substitute for durable storage and backups.

## Rendering and SDK migration

The SDK's GPR-to-RGB render now uses camera color matrices, illuminant interpolation, Bradford adaptation, source shading, black subtraction, baseline-aware exposure and the ACR3 display curve. Its horizontal orientation matches the ported upstream rendering pipeline. The historical low-level RGB decoder retains its pixel behavior; `vc5_decoder_process_calibrated` is a separate entry point. JPEG exports are 8-bit and carry EXIF orientation; choose quality 1..3 with `-j N`. Full SDK builds generate embedded thumbnails through the same calibrated decoder and use growable JPEG storage. Encoder-only SDK builds retain the legacy encoder thumbnail path; the non-CNN capture libraries do not depend on the still SDK. PPM pixels remain in sensor orientation because PPM has no orientation metadata.

This is a defined display rendering, not a universal reproduction of every camera's JPEG style. Geometric lens warps are preserved as DNG metadata, not applied by that reduced raster-render path. Sensor counts and editable RAW exports do not receive the display tone curve. Matching camera looks across firmware and scene types needs paired RAW/JPEG fixtures and a measured rendering recipe.

Full supported WarpRectilinear coefficients, centers and flags, baseline tags, source illuminants and gain maps survive the SDK's supported conversions. Default exports preserve source gain-map samples. `gpr_tools --apple-compatible-dng` explicitly equalizes the two green maps in an uncompressed DNG for Apple display compatibility; that changes the exported calibration and is not an exact metadata-preservation mode. Compressed GPR maps and caller-owned metadata are untouched.

The fork package is **0.2.0**. Public SDK structs have gained calibration/policy fields and a longer image description; rebuild all static SDK clients and regenerate language bindings together. Do not mix objects compiled against older headers. Existing codec parameter structs, Bayer enum values, VC-5 payloads and GVID v3 framing remain compatible. The historical SDK version macros are independent of the fork package version.

## Release review

[Upstream review and attribution](stock-upstream-review.md) records selected fixes, overlapping implementations and changes intentionally excluded. [Project direction](../VISION.md) explains the optical, noise, grain and optional-AI goals. Experimental reconstruction claims in older design/evidence documents are historical, not release guarantees.
