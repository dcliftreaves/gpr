# Prepared, calibrated native preview

The native preview library now has a separate calibrated display API alongside
the historical byte-compatible SDK RGB API. It uses the decoder's reduced
16-bit linear camera RGB output, removes the legacy horizontal mirror, applies
source black/white calibration and supported stage-two Bayer GainMaps, clips
at the source camera white point, converts to linear sRGB, applies baseline
exposure, encodes sRGB and applies source crop/orientation. It does not build a
full-resolution Bayer image, invoke a CNN or link the DNG SDK into the camera
preview library.

This is a **wavelet preview approximation**, not the full-resolution RAW
renderer. Green difference is not reconstructed: the reduced green signal is
used for both green sites, corrected separately and averaged. Wavelet filtering
and inverse logarithmic conversion do not commute with full RAW demosaicing or
spatial correction. GainMaps are sampled at reduced sensor-grid centers. Color
look tables, custom tone curves and highlight reconstruction are outside this
matrix display path. No rendered or temporal quality approval is implied.

## Prepare and play a recording

The optional host compiler uses the **vendored DNG SDK's color specification**
for AsShotNeutral, dual illuminants, analog/individual/reference calibration,
forward matrices and chromatic adaptation. It parses metadata only. Each unique
typed calibration is wrapped with an existing stock payload as a temporary
GPR; no compression or image decoding occurs in profile preparation.

```sh
cmake -S . -B build-camera -DCMAKE_BUILD_TYPE=Release \
  -DGPR_ENABLE_VIDEO=ON -DGPR_BUILD_CAPTURE_APP=ON \
  -DGPR_BUILD_PREVIEW_TOOLS=ON -DGPR_BUILD_PREVIEW_TESTS=ON
cmake --build build-camera --target gpr_preview_app gpr_preview_profile --parallel 4

python3 tools/stock_preview.py recording.gvid --compiler build-camera/gpr_preview_profile \
  --downsample 8 --output-dir prepared-profiles
build-camera/gpr_preview_app --input recording.gvid --profile-dir prepared-profiles --runs 5
```

`gpr_preview_profile` is built with POSIX still applications and needs the full
DNG/XMP host dependencies. The resulting parameters are portable: capture-only,
preview-only and combined camera libraries still build without that SDK. A
camera caller can supply the equivalent typed calibration directly. No Python,
SDK or JSON parser is required inside `gpr_preview`.

Preparation selects per-frame `raw_metadata`, then clip `raw_metadata`, then an
explicit `--metadata-file` default. It validates the complete recording before
publishing the new profile directory, rechecks source identity, protects existing
paths and records source/compiler/profile/metadata/payload hashes. Publication
uses the still tools' exclusive link/copy fallback and rollback behavior; it is
not group-atomic or an fsync guarantee. The new directory must not already exist.
Files are limited to 100,000 frames and 16 MiB per native profile.

`--profile-dir` reads the prepared `000000.gprp`, `000001.gprp`, etc. Each has a
small `.gprp.bind` companion covering frame index, original uint64 timestamp,
payload size/CRC, exact frame/clip metadata CRCs and the selected profile CRC.
The player rejects stale, swapped, missing or corrupted bindings. These are
integrity/association checks, not cryptographic authentication. The JSON receipt
also contains SHA-256 identities. The player continues validating the complete
recording when `--limit` restricts rendering.

Prepared profiles carry their reduction; `--downsample` is therefore rejected
alongside `--profile-dir`. `--output-dir new_directory` writes oriented sRGB PPMs.
Without `--profile-dir`, the player retains its historical gains, gamma and
mirror convention and still matches the stock RGB fixtures exactly.

## Native API and precision

`gpr_preview_calibration_identity` initializes a synthetic identity transform,
not a camera default. Real callers supply the source parameters:

- Four black values in original sensor Bayer-site order and a scalar WhiteLevel
  in the source 12/14-bit count domain. The preparer aligns black repeats to
  ActiveArea, including odd active origins.
- Camera-to-linear-sRGB matrix, normalized camera-white clipping values and a
  linear baseline-exposure multiplier. The white-point clipping follows the
  DNG SDK baseline RGB transform and avoids treating saturated sensor counts as
  an arbitrary illuminant.
- Absolute active/crop rectangles and EXIF orientation 1..8. Fractional default
  crop coordinates are sampled on the reduced grid; orientation is applied
  after crop and color processing.
- Up to 32 single-plane GainMaps with pitch one/two, Bayer-site masks and
  bilinear grids up to 256x256. Per-site products and saturation limits preserve
  the ordering of overlapping gain/attenuation operations. Green-site black,
  gain and saturation corrections precede green averaging.

`gpr_preview_plan_create` copies/prepares the required sampling and gain data.
Caller calibration buffers may expire afterward. The immutable plan can be
rendered concurrently with separate output buffers; `plan_info` gives oriented
dimensions, and `plan_destroy` releases it. The serialized equivalent uses
`gpr_preview_plan_from_profile`. RGB24 output respects arbitrary caller pitch
and capacity; row padding and canaries are tested. Unaligned compressed inputs
are copied to aligned scratch. New plans require sensor dimensions at least 48.

Plans precompute spatial gains once. With maps, storage is eight float factors
per reduced, unrotated sample plus row/column indices; without maps there is no
gain table. At 1024x768 this is about 25.2 MB per mapped plan. The player keeps a
bounded four-plan LRU cache, shared across playback passes. Real camera callers
control plan lifetime and scheduling.

On AArch64 with NEON enabled, a four-pixel kernel deinterleaves linear word
triplets, fixes byte/lane order and processes independent pixels in vector
registers through black normalization, gains, clipping and the 3x3 transform.
Non-contiguous crop samples and tails use the scalar path. `GPR_PREVIEW_SCALAR=1`
forces scalar processing for comparison. Both paths use a shared 65,536-entry
sRGB lookup; independent floating-point references allow one RGB8 count of
rounding difference. Legacy RGB8 behavior is unchanged.

The preparer rejects unsupported linearization tables, row/column black deltas,
non-unit DefaultScale, non-full DefaultUserCrop and nonempty stage-one/three
opcodes. Supported source GainMaps are retained; profile hue/saturation/look and
tone-curve tags are explicitly reported as omitted looks. Full lens/rendering
workflows remain available through [editable RAW](stock-editable-raw.md) and the
separate [macOS RAW/ProRes renderer](stock-prores.md).

## Evidence and Pi measurements

Six new linear 16-bit big-endian fixtures come from a fresh build of the
historical stock revision `6b22975dcf4e65ab9445852cd7b2220ae3faa3af`.
The original six RGB8 fixtures also match that fresh build. The calibrated C++
contract exercises **192 combinations** of two geometries, three reductions,
eight orientations, two CFA layouts and two count domains, with crop, fractional
and distinct Bayer-site blacks, gains, sequential saturation, source-white
clipping, unaligned payloads and padded RGB rows. It also checks immutable-plan
concurrency, caller map lifetime, malformed profiles, every profile truncation
and byte corruption, capacity failure and nonfinite parameters.

Five stdlib integration tests cover the DNG color compiler, neutral-white and
dual-illuminant response, per-frame WB/orientation changes, profile cache reuse,
odd ActiveArea origins, typed GainMaps, unsupported metadata, profile/frame
binding, strict finalization, protected outputs and non-regular inputs.

Pi 5 results use the same **12-frame 4096x3072 stock-Q3 still-derived replay** as
[MOV validation](stock-mov.md). Each mode renders five passes / 60 frames, with
two prepared camera calibrations. Warm USB-SSD playback includes source reading,
CRC/end checks, frame binding checks, profile reads/preparation, RGB checksums
and per-frame JSON logging; no PPM writes are timed.

| Calibrated output | Decode + display color median | Full wall throughput |
|---|---:|---:|
| 1024x768, NEON | 67.38 ms | 13.59 previews/s |
| 1024x768, forced scalar, same binary | 91.10 ms | 10.35 previews/s |
| 512x384, NEON | 16.16 ms | 50.78 previews/s |
| 256x192, NEON | 3.16 ms | 176.57 previews/s |

The NEON kernel reduces the 1024x768 decode/color median by about 26% (1.35x).
Two 12 MP source profiles and preview pixels also matched across Mac/Pi in the
checked runs. These are standalone playback measurements, **not simultaneous
capture, sensor delivery, display presentation or live camera frame rates**.
Combined capture/preview scheduling and actual display integration remain work
in the active rebuild. No CNN runs in this path.

Source/binary identities, full per-frame logs, platform comparisons, sanitizer
checks and relocated-package evidence accompany the milestone receipts.
