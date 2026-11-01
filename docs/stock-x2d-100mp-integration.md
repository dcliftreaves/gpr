# X2D 100 MP capture: offline integration candidate

This branch targets approximately 100 MP stock-compatible GPR/GVID for X2D
100C and X2D II. The implementation has desktop evidence; neither camera has
run it. The existing PR101 and earlier PRs are unchanged.

## Geometry and camera crop

GVID v3 now admits even Bayer dimensions up to 16384 per axis and 128 Mi pixels
in total. The C writer, native reader and Python reader enforce these limits.
V2 retains its 8192 by 6144, multiple-of-eight geometry gate. The record layout
and VC-5 codec have not changed; older strict v3 readers may reject the expanded
geometry. Container acceptance does not imply every preview or CNN adapter
supports the new dimensions.

The tested X2D source is 11664 by 8750 RGGB16. For camera integration, an
eight-pixel-aligned 11664 by 8744 view removes six bottom rows (0.069% of RAW
samples), preserving the top-left origin and CFA phase. It can lease the
original packed sensor buffer through the existing capture API: use the reduced
height, original row width/stride and original buffer lifetime. No pixel copy
is needed for a bottom-only crop. A right crop requires repacking under the
current packed-row lease contract.

`tools/stock_crop.py` provides `aligned(metadata, multiple=8)`. It intersects
ActiveArea, clips DefaultCropSize at the original DefaultCropOrigin, updates
declared dimensions and EXIF pixel dimensions, and records omitted opaque XMP.
The real source has DefaultCropOrigin (4,4) and size (11656,8742); after the
six-row RAW crop its default crop is (11656,8740). Color matrices, black/white
levels and CFA calibration are preserved. Unsupported spatial opcodes, masked
areas, user crop and black-level delta arrays are rejected when cropping;
their coordinates are not silently reused. This helper transforms metadata,
not pixels or the sensor's readout mode.

## Allocation changes and measured memory

Capture no longer eagerly allocates a duplicate RAW image for every slot.
Copied submissions allocate their own RAW storage; leased submissions do not.
Queued payloads grow to actual compressed size while retaining the existing
checked upper bound. Codec output is owned through a scope guard so an
allocation exception cannot leak it. Copy/lease transitions and cancellation
retain the same ownership contract.

An M5 Max experiment replayed one real 102 MP image four times per case at Q3,
with malloc workspace, no preview/CNN and the app's final fsync. Both variants
used identical app, codec and expanded framing objects; only the capture
allocation policy differed. The old unmodified framing gate rejected this
geometry, so the baseline represents its allocation policy with shared new
framing support.

| Slots / input | Previous allocation peak RSS | Candidate peak RSS |
| --- | ---: | ---: |
| One / lease | 966.9 MiB | 491.6 MiB |
| Two / lease | 1454.6 MiB | 504.1 MiB |
| One / copy | 966.9 MiB | 686.3 MiB |
| Two / copy | 1454.6 MiB | 893.5 MiB |

RSS includes the app's resident 194.7 MiB input fixture and codec intermediates.
All 32 payloads were identical across cases, with valid per-frame and END3 CRCs.
These are short desktop replay measurements, not sustained camera frame rates
or proof of fitting camera RAM. More scenes, high-entropy inputs, allocator
accounting, actual sensor-buffer lifetime and target-camera memory remain work.

A follow-up aligned three-frame run with a 1 MiB tracking arena reported
1,022,080 bytes arena peak and 983,572,193 bytes peak live fallback malloc
requests, despite approximately 491 MiB process RSS. Requested capacities and
resident pages differ: large codec buffers are not fully touched. The queue
allocation savings do not establish a camera-safe codec allocation budget.
Reducing those codec reservations is the next memory task.

## Alignment performance measurement

Ten paired, alternating-order M5 Q3 trials compared the original geometry with
the six-row crop; one warmup per geometry was excluded. Encoder profile medians
were 43.687 ms native and 43.721 ms cropped. SDK process medians were 70.432 and
71.123 ms, respectively. No speed improvement was demonstrated. The small crop
provides an aligned integration option; it is not claimed as an encoder
optimization. Sensor readout, DMA or firmware interfaces may have different
requirements and need their own measurements.

## Validation and remaining integration

Five capture-only CTest entries pass: lifecycle/ownership, C API/native reader,
crop calibration, v3 conformance and v2 compatibility. The crop suite contains
four cases covering all CFA phases, actual X2D crop coordinates, identity/right
crop and rejection of untransformed spatial calibration. Lifecycle tests also
lease a larger original buffer while encoding only its cropped row prefix.

Separate desktop three-frame round trips exercise original native geometry and
the aligned crop. Every payload matches standalone Q3 encoding; every decoded
RAW matches standalone decoded counts. Declared calibration survives GVID to
GPR/DNG, timestamps increase, and END3 verifies. Inputs are repetitions of one
real still image, not fresh sensor video. The codec is lossy; matching standalone
decode does not establish lossless sensor equivalence.

The next steps are smaller codec working memory, high-entropy/scene coverage,
camera-specific CPU/RAM/sensor mode identification and an actual RAW-buffer
adapter. First-generation firmware 4.2.0 and second-generation firmware
1.3.16.2/1.3.18.1 require separate evidence. No deployment backend, camera
recording, native 100 MP preview, X2D-trained CNN or achieved camera frame rate
is claimed.

## Receipts and reproduction

Compact, photo-free receipts record [M5 encode timing](stock-x2d-receipts/m5-encoding.json),
[capture memory](stock-x2d-receipts/capture-memory.json),
[paired crop timing](stock-x2d-receipts/aligned-crop.json),
[native round trip](stock-x2d-receipts/native-roundtrip.json),
[aligned round trip](stock-x2d-receipts/aligned-roundtrip.json) and
[implementation source hashes](stock-x2d-receipts/sources.json).
Original photo, RAW pixels, private calibration and machine-local logs are not
included. These are reproducible method descriptions and recorded results;
reproduction needs an independently supplied matching source image.

Run the camera-independent capture checks from the repository root:

```sh
cmake -S . -B build-video-x2d -DCMAKE_BUILD_TYPE=Release \
  -DGPR_BUILD_SDK=OFF -DGPR_BUILD_STILL_APPS=OFF \
  -DGPR_BUILD_LEGACY_CLI=OFF -DGPR_BUILD_DECODER=OFF \
  -DGPR_ENABLE_VIDEO=ON -DGPR_BUILD_CAPTURE_APP=ON -DGPR_BUILD_VIDEO_TESTS=ON
cmake --build build-video-x2d -j 4
ctest --test-dir build-video-x2d --output-on-failure
```

For a file replay, supply tightly packed 11664 by 8744 little-endian uint16
rows and the calibration returned by `stock_crop.aligned`:

```sh
build-video-x2d/gpr_capture_app --input cropped.raw \
  --source-metadata cropped-calibration.json --output clip.gvid \
  --width 11664 --height 8744 --cfa RGGB --sample-bits 16 \
  --quality 3 --frames 3 --fps-num 1 --queue 1 --workspace-mib 0 \
  --submit-timeout-ms 4294967295 --leased
```

This is unpaced fixture replay. The header rate is descriptive; no camera or
one-frame-per-second acquisition is implied. The capture API itself can lease
a larger original sensor buffer for the bottom-cropped view, as tested by the
lifecycle case; the file frontend requires exact input size.

The broader Release configuration with native preview enabled also passed
10/10 CTest entries on M5; this guards existing preview/capture interactions.
The installed package contains the crop helper and this document. No sanitizer
run or Pi/camera validation was performed for this candidate.
