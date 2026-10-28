# Stock GVID / MOV interchange

`stock_mov.py` wraps complete stock GVID recordings in MOV and recovers the
**original GVID file byte for byte**, including compressed payloads, calibration,
opaque application metadata, absolute nanosecond timestamps and finalization.
It uses an optional native FFmpeg transport tool and invokes no image encoder,
decoder or CNN. The primary capture format remains GVID.

## Build and use

```sh
cmake -S . -B build-mov -DCMAKE_BUILD_TYPE=Release \
  -DGPR_BUILD_SDK=OFF -DGPR_BUILD_STILL_APPS=OFF -DGPR_BUILD_LEGACY_CLI=OFF \
  -DGPR_BUILD_ENCODER=OFF -DGPR_BUILD_DECODER=OFF \
  -DGPR_BUILD_MOV_TOOLS=ON -DGPR_BUILD_MOV_TESTS=ON
cmake --build build-mov --parallel 4
ctest --test-dir build-mov --output-on-failure

python tools/stock_mov.py wrap recording.gvid --bridge build-mov/gpr_mov \
  --output recording.mov
python tools/stock_mov.py inspect recording.mov --bridge build-mov/gpr_mov
python tools/stock_mov.py unwrap recording.mov --bridge build-mov/gpr_mov \
  --output recovered.gvid
```

The opt-in POSIX target needs CMake >=3.6, pkg-config, FFmpeg development
libraries (`libavformat`, `libavcodec`, `libavutil`) and zlib. Tests also need
Python 3 and `ffprobe`; the wrapper itself uses the Python standard library.
Default capture/preview/SDK builds have no new FFmpeg dependency. MOV transport
can build without either image codec or the DNG/XMP SDK.

`gpr_mov --version` reports the linked libavformat version and its build's
license. These are external shared-library dependencies, not bundled libraries
or part of the camera encoder. MOV-enabled archives use a `-mov` profile suffix
(or standalone `interchange`) and declare the optional tool in build info.
Relocation still requires compatible FFmpeg libraries on the destination host.

## Explicit private profile

The earlier PR's `GPRr`/`GPR1` MOV profiles carry fused payloads. This port uses
distinct **`GVS2` / `GVS3` private video sample tags**:

- One video track; each sync sample contains one exact original `FRM2` or
  `FRM3` record, including its header, metadata bytes and stock payload.
- File-level `mdta` keys declare `gpr.stock.profile=framed_gvid.v1`, the exact
  original header/clip metadata and end marker as hex, original SHA-256, and
  the MOV video-track clock unit in nanoseconds.
- Prefix + ordered samples + ending reconstruct the original recording.
  No metadata sidecar is needed. The adjacent JSON receipt is optional evidence,
  not an input to recovery.
- This is a MOV compatibility wrapper for these tools. It is **not standard
  CFHD**, fused GPRr/GPR1, ProRes or a promise of playback in generic editors.
  Unwrap for the existing RAW extraction/reconstruction tools; calibrated
  rendered ProRes uses the separate [calibrated renderer](stock-prores.md).

The native transport validates GVID framing/CRC/end-marker/whole-file identity,
not opaque compressed-image syntax. The Python wrapper additionally validates
unambiguous finite JSON objects and typed source calibration where supplied.
The format retains the existing GVID v2/v3 CFA/domain/geometry boundary; adding
still formats does not silently extend video formats. V2 has physical EOF but
no verified end marker; V3 requires its checked END3 record.

FFmpeg writes and reads the MOV sample tables; the tool does not implement a
second MOV muxer. The design retains the earlier PR's libavformat approach,
using [MOV metadata/timescale options](https://ffmpeg.org/ffmpeg-formats.html)
and a version-specific custom-AVIO callback signature. Primary format handling
is tested against libavformat 59 on Pi and 62 on macOS.

## Timing, limits and failures

MOV packet PTS/DTS are derived from actual source timestamps relative to the
first frame, with no nominal-CFR rewrite. Track clocks start at nanosecond
precision. If a long frame gap would overflow MOV's 32-bit sample-duration
field, the tool chooses the smallest power-of-ten clock unit that fits.
Original absolute timestamps still remain exact inside each record. Receipts
report the selected track tick and whether presentation timestamps were
quantized. A timing pattern that cannot represent both very large gaps and
very fine spacing is rejected, rather than shifting source records to fit.
The final sample uses the rounded nominal frame period, with a one-tick minimum.

The native operational limits are one million frames, the reader's 128 MiB
payload limit, 64 KiB clip/frame metadata, and a 256 MiB per-allocation FFmpeg
limit. Only one video track is accepted. Audio/WAV, SMPTE timecode tracks,
arbitrary edited/remuxed MOV layouts and interrupted-MOV recovery are not
implemented in this milestone; the previous feature inventory is not treated
as complete by this transport alone.

Strict outer-atom extent checks reject truncation even when libavformat could
salvage an incomplete final metadata atom. Import checks the declared profile,
dimensions, track clock, packet PTS/DTS, durations and sync flags against the
original records, verifies source SHA-256, then validates the recovered GVID
again. Additional data references/network I/O are disabled. This is integrity
checking, not authenticated provenance.

Inputs must be regular local files; devices and FIFOs fail before reads. Native
output files are created exclusively and removed on failure. The Python
wrapper stages privately, verifies a complete inverse round trip before wrapping
publication, validates recovered JSON/calibration before unwrapping publication,
and publishes output/receipt exclusively with owned-partial rollback. Existing
files and dangling symlinks are refused. Publication has the still workflow's
filesystem-copy fallback; it does not add fsync or group-atomic durability.

## Validation and Pi 5 measurements

Eight stdlib contract/integration tests cover actual stock payload fixtures,
both GVID versions, changing typed calibration, Unicode and maximum 64 KiB
metadata, original timestamps near UINT64_MAX, adaptive clocks, impossible
clock patterns, missing END3, trailing/corrupt data, malformed JSON, damaged
MOV samples/digests/tags/timing/size tables, truncated containers, protected
outputs and receipt-free recovery. Independent `ffprobe` checks every sample's
hash, PTS and sync flag, plus dimensions and private codec tag.

All eight cases pass locally in Release and ASan/UBSan. With MOV enabled, all
eleven local native/media CTest targets pass. Pi Release passes the transport
suite using system FFmpeg 5/libavformat 59. The eight-case Pi ASan/UBSan/leak
suite also passes in 128.71 s at `5824f81`; subsequent Release/report changes
are source-verified separately at `e2065cb`. CI adds standalone Linux Release/sanitizer transport builds with SDK and
both image-codec source directories physically absent.

A new 12-frame Pi replay alternates the supplied GP011728/GPAB1094-derived
4096x3072 RAWs with their per-frame calibration. Three warm-cache attempts:

| Offline workflow | Median wall time |
|---|---:|
| Verified GVID to MOV wrapper | **1.074 s** |
| Verified MOV to original GVID | **0.602 s** |

Wrapping includes source JSON/calibration checks, hashes, native muxing and a
complete inverse readback/hash check. Unwrapping includes native demuxing,
GVID checksums, JSON/calibration validation and hashes. Timings end before final
publication/fsync. Capture and subsequent independent SDK/RAW verification are
outside these times. No CNN or image conversion runs in the timed transport.
These are still-derived replays on USB SSD, not live sensor/card or real-time
capture measurements.

All source GVID bytes are exact after every attempt. Independent `ffprobe`
verifies all twelve packet hashes and timestamps. Every recovered frame exports
editable DNG/GPR with its exact typed calibration; SDK decoding of all twelve
GPRs matches the two independent historical RAW references. Source/binary/library
identity, per-frame hashes and revision-bound test/measurement receipts accompany
the PR. Cross-version exchange is checked in both directions between Pi/FFmpeg
5 and Mac/FFmpeg 8, without copying a metadata sidecar.

Reproduce the measured wrapper path on an existing complete recording:

```sh
python tools/benchmark_stock_mov.py --input recording.gvid \
  --bridge build-mov/gpr_mov --ffprobe /path/to/ffprobe --repeats 3 \
  --output-dir /new/mov-benchmark
```

The benchmark independently verifies all packet hashes/timestamps and stream
properties after timing. Measurement tools/runtime files match Git `e2065cb`;
415 source/test/tool/build/fixture files on Pi were checked against that revision.
The initial sanitizer/SDK-pixel validation snapshot matches `5824f81` (414 files).
The independent capture/SDK/decoder binaries retain their verified `31274ea`
identity. All four MOV-enabled relocated package profiles pass C/C++ clients,
installed wrapping/recovery, guide presence and external-dependency declarations.

Receipts: [current Pi benchmark](stock-mov-receipts/pi5-current.json),
[initial tests and SDK pixel/calibration checks](stock-mov-receipts/pi5-initial-validation.json),
[cross-version exchange](stock-mov-receipts/cross-version.json),
[relocated packages](stock-mov-receipts/packages-mac.json),
[final Pi Release input guards](stock-mov-receipts/pi5-final-guards.json).
The source recordings remain outside the repository.

Broader rendering validation, audio/timecode integration and integrated capture/display
performance remain part of the active high-level rebuild.
