# Rebuild the RAW-media feature suite on the stock encoder

## Objective and source revisions

Recreate the high-level workflows of fork PR #95 / upstream PR #71 using
the stock-compatible encoder and RAW-video experiment as the foundation.
Work in a separate fork branch and replacement draft PR. Keep the existing
feature and validation PRs open; do not retarget, merge or close them.

- Previous runtime: `8be29eee57b4637865b572f18ab9e3f4edaa2236`
  (`review/product-runtime`, fork #95, upstream #71).
- Previous validation: `821420d7acac8a316d16293b93d4b3204631a38f`
  (`review/product-validation`, fork #96, upstream #72).
- New foundation: `d3d96ec49970a7edc8736d07ed39b3964ca4dc10`
  (`experiment/stock-raw-video-12mp`, fork #100), including fork #99.
- Rebuild branch: `feature/stock-raw-media-runtime`.

The old suite's approved results describe its old codec/model pairings.
Historical evidence remains historical. Porting an interface or model loader
does not establish parity, quality, performance, or camera deployment.

## Current delivery priority (2026-10-29)

Finish a usable end-to-end path before expanding support at every stage.
RAW stills retain broad Bayer/count-format support. RAW video delivery focuses
on the Mission 1 workflow: 4096x3072 recording, calibrated preview, editable
RAW extraction and desktop ProRes, with explicit optional offline 1x/2x
reconstruction. The existing working stock RGGB14 path is the immediate
integration target; additional video/render/reconstruction format combinations
are stretch work, not prerequisites for this delivery.

The earlier Mission 1 handoff specifies a 20 fps floor for 4096x3072 capture
and 1024x768 preview. Retain that floor separately from the more demanding
30 fps replay experiments. A host replay and memory preview sink cannot close
the actual sensor/DMA, rear-display, SD durability or camera thermal gates.
Prioritize ordinary Release integration, real-sample workflows and reviewable
local packages. Broader sanitizer/fuzz auditing is deferred from the immediate
critical path. Work stays local; remote source uploads, pushes and publication
require separate explicit user approval.

## Core workflow

Build the full desktop workflow on macOS with FFmpeg development libraries,
Python, NumPy and tifffile available. Capture/preview library profiles remain
independent of the desktop SDK and Apple renderer.

```sh
cmake -S . -B build-runtime -DCMAKE_BUILD_TYPE=Release \
  -DGPR_ENABLE_VIDEO=ON -DGPR_BUILD_CAPTURE_APP=ON \
  -DGPR_BUILD_PREVIEW_TOOLS=ON -DGPR_BUILD_PREVIEW_TESTS=ON \
  -DGPR_BUILD_STOCK_VIDEO_EXPERIMENT=ON -DGPR_BUILD_MEDIA_TESTS=ON \
  -DGPR_BUILD_CODEC_TESTS=ON -DGPR_BUILD_VIDEO_TESTS=ON \
  -DGPR_BUILD_MOV_TOOLS=ON -DGPR_BUILD_MOV_TESTS=ON \
  -DGPR_BUILD_RENDER_TOOLS=ON -DGPR_BUILD_RENDER_TESTS=ON \
  -DGPR_BUILD_PACKAGE=ON
cmake --build build-runtime --parallel 4
ctest --test-dir build-runtime --output-on-failure

# Calibrated still: declare the source's sample domain, not its storage word size.
python3 tools/stock_still.py encode source.dng --source-type dng --sample-bits 14 \
  --quality 3 --sdk build-runtime/source/app/gpr_tools/gpr_tools \
  --output still.gpr --editable still.dng

# Mission 1-style replay: tightly packed 4096x3072 RGGB14 words and actual calibration.
build-runtime/gpr_capture_app --input frame.raw --source-metadata calibration.json \
  --output recording.gvid --quality 3 --fps-num 20 --fps-den 1 \
  --frames 120 --paced --leased
python3 tools/stock_preview.py recording.gvid --output-dir preview-profiles \
  --compiler build-runtime/gpr_preview_profile --downsample 4
build-runtime/gpr_preview_app --input recording.gvid --profile-dir preview-profiles

# Recover editable RAW and wrap the original compressed recording without image conversion.
python3 tools/stock_video.py extract recording.gvid --out-dir editable \
  --decoder build-runtime/source/app/stock_video/stock_video --editable both
python3 tools/stock_mov.py wrap recording.gvid --bridge build-runtime/gpr_mov \
  --output stock.mov
python3 tools/stock_prores.py stock.mov --mov-bridge build-runtime/gpr_mov \
  --output rendered.mov --decoder build-runtime/source/app/stock_video/stock_video \
  --renderer build-runtime/gpr_render --encoder build-runtime/gpr_prores \
  --ffprobe /path/to/ffprobe --profile hq
```

All output names/directories must be new. These commands write local files;
"publication" in the tool receipts means exclusive local filesystem creation.
The preview command above is playback. To exercise recording and calibrated
preview simultaneously, use the repeatable matched replay:

```sh
python3 tools/benchmark_mission1.py \
  --capture build-runtime/gpr_capture_app --compiler build-runtime/gpr_preview_profile \
  --player build-runtime/gpr_preview_app --reference /path/to/independent/vc5_encoder_app \
  --input frame.raw --metadata calibration.json --frames 600 --fps 20 \
  --quality 3 --downsample 4 --out-dir new-mission1-review --require-floor
```

The reference app must honor `GPR_BENCH_QUALITY`; the historical codec may be
instrumented at the sample-app boundary without changing its encoder. Repeat
`--input` and `--metadata` in matching source order for alternating inputs.
The runner checks every accepted payload against independent stock bytes,
source calibration and attempt association, END3/accounting, and every
delivered preview against separately prepared offline playback. It reports
recording deadlines, preview deadlines and drops independently. Missing the
requested timing floor is not mistaken for a functional pass; `--require-floor`
returns status 2 for that case. Other formats are outside this focused runner.

### Local core review, 2026-10-29

The M5 Max replay uses two supplied camera-still-derived RAWs, warm cache and
a memory CRC preview sink. Both recording-only and combined runs accept/write
120/120 frames at a requested 20 fps, with zero overruns or late writes. All
240 payloads match the independent stock encoder. The combined run delivers
all 120 full-frame 1024x768 previews, with no replacements/discards and every
delivery within 50 ms of its replay timestamp. Durable recording throughput
is 20.12 fps; capture-to-preview p95 is 31.93 ms. This six-second host replay
does not establish sustained Pi or actual camera performance, nor a preview
speed benefit from the differing single-run encode medians.

Two lossless source stills (45.7 MP Nikon RGGB14 and 102.1 MP X2D RGGB16) pass
36 fresh encode/decode pairs across six presets/three repeats. Independent
lossless source decoding, every historical payload/pixel hash and every
distortion metric agree exactly. Q3 SDK-process/preparation medians are
32.61/96.33 ms and 67.19/148.99 ms respectively, before final publication/fsync.
These are scene-specific host workflow timings, not codec-only or camera latency.

All four relocated local package profiles pass. The full installed package's
capture, preview/compiler and SDK binaries have exactly the hashes used by
these measurements. The configured local Release suite passes 21/21; seven
optional CPU/Torch workflow contracts pass without trained weights. Exact
receipts: [Mission 1 replay](stock-core-receipts/mission1-mac.json),
[stills](stock-core-receipts/stills-mac.json),
[packages](stock-core-receipts/packages-mac.json),
[Release checks](stock-core-receipts/release-tests.txt),
[optional CNN contracts](stock-core-receipts/cnn-contracts.txt) and
[source/reference identity](stock-core-receipts/validation.json).

Using that relocated full package, the actual 120-frame recording passes an
exact GVID/MOV/GVID round trip. Two exported editable DNG/GPR frames retain
their exact source calibration and agree pixel-for-pixel with the historical
independent decoder and the SDK. The complete private MOV then renders to
4096x3072 ProRes HQ: all 120 frames pass timing/color/profile checks and a full
independent FFmpeg decode. The single functional export takes 61.22 s before
publication and produces 682,542,583 bytes; this is offline processing, not
real-time ProRes. [Export receipt](stock-core-receipts/exports-mac.json).

The subsequent [streaming ProRes follow-up](stock-prores.md#bounded-image-scratch-2026-10-29)
removes the accumulated TIFF pool. The same 120-frame clip now peaks at
100.67 MB of TIFF storage / 154.71 MB of image scratch, with exact prior
ProRes packets, decoded pixels and timestamps. Ten Release rendering tests
pass. This closes the frame-image scratch growth gap without broadening the
focused RGGB14 video format scope.

The local review bundle is at
`/Users/dcliftreaves/Documents/slop/gpr_check/releases/stock-core-20261029`.
Its recording alternates two stills; no scene motion or temporal quality is
established. The bundle is a review candidate for the core host workflow.
Camera integration, Pi combined-preview performance, model quality approval
and broader per-stage format parity remain separate work. Optional desktop
PCM/timecode transport and ProRes inheritance are now implemented under the
[explicit auxiliary-track contract](stock-mov.md#optional-pcm-and-timecode).

## Current task and evidence matrix

The delivery priority above narrows the immediate video integration path; it
does not turn unresolved quality or hardware requirements into completed work.
Historical platform receipts remain bound to their recorded revisions.

| Task | Current progress and authoritative evidence | Still open |
|---|---|---|
| Optimized stock encoder | Streaming/parallel/NEON foundation implemented; [Pi latency evidence](stock-encoder-sub100.md), [fresh exact still payload/pixel comparisons](stock-core-receipts/stills-mac.json), [240 exact replay payloads](stock-core-receipts/mission1-mac.json) | Universal latency guarantees; actual camera execution |
| Broad RAW still formats | Four CFA phases, 12/14/16-bit words and legacy packed-12 supported; [format/conformance scope](stock-still-formats.md) | Broader real-camera fixtures and metadata cases; stock log precision remains lossy |
| Still presets/workflow | Six explicit presets, validated source calibration and editable DNG/GPR; [36 fresh pairs on two lossless sources](stock-core-receipts/stills-mac.json) | Restored-tier/model quality selection; no inherited old-tier approval |
| Calibration/editable RAW | Typed supported calibration, EXIF/GPS/opcodes and per-frame precedence implemented; [contracts](stock-editable-raw.md), [independent core export pixels/calibration](stock-core-receipts/exports-mac.json) | Unsupported metadata/lens operations and broader reader interoperability |
| Bounded capture API | Ownership, leases, backpressure, cancellation, flush and writer failures implemented; [capture contract](stock-capture-api.md) | Physical sensor/DMA/storage adapter integration |
| Checked recording/recovery | Actual timestamps, CRC metadata/payloads, END3 and explicit prefix recovery implemented; [recording contract](stock-capture-api.md) | Live sensor/card interruption and durability evidence |
| Native calibrated preview | Immutable plans, source color/GainMaps/orientation and bounded queue implemented; [preview contract](stock-calibrated-preview.md), [combined path](stock-capture-preview.md) | Rear-display backend and broader lens/look/temporal approval |
| Mission 1 20-fps host path | 120/120 recorded and previewed at 1024x768 with no late deliveries/overruns; [matched host receipt](stock-core-receipts/mission1-mac.json) | Refreshed combined Pi floor and actual camera proof; source is still replay, sink is memory |
| Offline 1x reconstruction | Portable inference and editable/sequence export work; [24 legacy comparisons](stock-cnn-quality.md), [fresh source-grouped Q3 experiment and seven contracts](stock-cleanup-training.md); all 30 trained checkpoints rejected by validation region guard | Model quality approval; identity fallback is not a quality improvement; legacy Q5 scene regression remains |
| Offline 2x/8K reconstruction | Explicit architecture/geometry/calibration paths and fresh training/evaluation implemented; [functional evidence](stock-cnn-portable.md), [frozen candidate](stock-sr-training.md) | Candidate selection/perceptual/temporal approval; current shadow regression |
| Exact MOV interchange | Complete original stock GVID survives wrap/unwrap; [transport evidence](stock-mov.md), [core full-recording identity](stock-core-receipts/exports-mac.json) | Latest auxiliary-profile platform/version exchange |
| PCM/timecode interchange | Optional declared PCM16/24/float32 mono/stereo, independent timecode clocks, exact WAV samples and ProRes inheritance implemented; [120-frame A/V receipt](stock-av-receipts/real-core.json), [24 Release cases](stock-av-receipts/release-tests.txt) | Actual camera audio/synchronization and broader editor compatibility |
| Calibrated ProRes | Deep HQ/4444, original timing and optional reconstruction implemented; [core decode](stock-core-receipts/exports-mac.json), [one-TIFF scratch](stock-prores-receipts/streaming.json), [A/V pixel/packet identity](stock-av-receipts/real-core.json) | Broader rendered-color/lens/temporal approval and custom grading looks |
| SDK ABI and selected boundaries | Published C symbols, owned-copy rollback and encoder/decoder boundary fixes implemented; [C API](stock-sdk-api.md), [encoder](stock-encoder-bounds.md), [decoder](stock-decoder-bounds.md) | Broader malformed-input/failure/concurrency audit, deferred from immediate delivery |
| Independent packages | Four MOV-enabled profiles pass relocated C/C++/SDK and installed PCM/timecode wrap/recovery; [current packages](stock-av-receipts/packages.json), [installed gates](stock-av-receipts/validation.json) | Latest hosted platform/release validation; source uploads require approval |
| Actual camera production | Integration requirements documented; host/Pi evidence stays explicitly labeled | Sensor/DMA, display presentation, durable SD, thermal and physical A/V synchronization receipts |

## Feature accounting at the start

| Previous high-level capability | New foundation | Rebuild work |
|---|---|---|
| Editable RAW stills and camera metadata | Stock GPR/DNG SDK and encoder | Reconcile metadata preservation, still quality selection and restoration workflows |
| High-bit-depth and four-phase Bayer workflows | Stock formats and an optimized RGGB14 path | Audit and port 14/16-bit and CFA support with explicit format/metadata tests; keep historical format paths byte-compatible |
| Compact still tiers | Stock presets 0–5; historical tiers used other profiles/models | Re-establish size/fidelity tiers; do not relabel old Q8 or old quality results as new measurements |
| Independently decodable RAW video | Native replay writer with stock VC-5 payloads | Turn the replay into a usable library-backed recording workflow |
| Bounded capture lifecycle | Synchronous serial replay and reusable allocator | Recreate create/submit/flush/destroy, ownership, cancellation, writer-error propagation and bounded backpressure |
| GVID framing and metadata | Experimental v2/VC5 profile, nominal PTS, strict inspector | Preserve actual capture timestamps, camera/CFA/black/white/color metadata and interrupted-recording behavior with explicit versioning |
| Native full-frame camera preview | Stock decoder available; preview not integrated into recorder | Decode the same recorded stream to a bounded full-frame RGB preview and measure its cost |
| Offline 1x Bayer cleanup | Explicit model adapter, tested on two frames | Reconcile model identity/codec pairing and quality; existing tested weights worsen replay-reference PSNR |
| Offline 2x/8K Bayer SR | Old fused-profile model does not automatically transfer | Rebuild inference and editable packaging, validate an appropriate model against stock input; separate functional support from quality approval |
| MOV without re-encoding | Not yet ported | Preserve stock compressed payloads through wrap/unwrap with explicit codec/profile identification |
| RAW-derived ProRes and editable DNG/GPR | Stock SDK available; old renderer expects fused GVID | Rebuild stock-payload dispatch and metadata-preserving export; retain optional reconstruction |
| Build profiles, distribution and documentation | Opt-in host experiment | Recreate independent build options and cross-platform delivery around actual supported features |
| Quality, conformance, CI and hardware receipts | Stock-byte tests, sanitizer tests, 3,360-frame Pi replay evidence | Adapt relevant old tests and add integration/ownership/failure/metadata/preview/export/model-contract checks |

## Work order and completion evidence

1. **Capture and storage architecture.** Extract reusable framing and recording
   interfaces. Add bounded ownership and asynchronous storage with explicit
   backpressure/error policy. Test cancellation, failed writers, flush and
   complete-frame preservation. Measure real absolute deadlines rather than
   process CPU time or average buffered FPS alone.
2. **Metadata, stills and preview.** Recreate camera metadata and supported
   Bayer workflows, implement preview from the same stock stream, verify
   dimensions/color and correct buffer lifetimes. Audit high-bit-depth paths
   before making parity claims. Keep the fast RGGB14 path and compatible
   fallbacks separately testable.
3. **Interchange and reconstruction.** Port MOV/RAW/ProRes workflows to the
   explicit stock payload kind. Restore 1x and 2x model contracts and editable
   outputs without assuming the old fused-profile checkpoints are approved
   for the new input. Evaluate held-out detail/color/noise and temporal
   behavior as well as numeric RAW distortion.
4. **Integrated verification and replacement PR.** Run meaningful native and
   SDK checks, relevant platform builds, new Pi capture/preview/end-to-end
   measurements, and applicable quality tests. Publish one separate reviewable
   fork draft with an implementation/evidence matrix and explicit remaining
   hardware/model limitations. Keep the old PRs open.

## Baseline constraints to preserve in reporting

### First implementation milestone (in progress)

The [stock capture API](stock-capture-api.md) now implements bounded
copy-before-return and explicit input leases, asynchronous writing,
flush/finish/cancel/error handling, actual timestamps, opaque clip/frame
metadata, checksum-protected v3 framing and explicit interrupted-prefix
recovery. Native C/C++ and independent Python tests exercise these contracts.
The codec entry point also serializes global codebook state across captures
and still SDK calls, and skips an unrequested thumbnail allocation.

The [native preview](stock-preview.md) now renders full-frame reductions from
the same stock recording, with independent stock RGB fixtures and Pi playback
measurements. The [bounded asynchronous capture preview](stock-capture-preview.md)
now connects recording to a calibrated RGB callback with copied payloads,
retained source plans, latest-pending replacement and isolated sink failure.
Matched 900-attempt Pi runs show 256x192 preview is much cheaper than 512x384;
capture overruns and late completions remain.
The [prepared calibrated preview](stock-calibrated-preview.md) additionally uses
source matrix/white-point/black/white/GainMap data and crop/orientation, with an
SDK-independent immutable plan and four-pixel NEON processing. It is a reduced
wavelet approximation; full look/lens/temporal approval, physical display
integration and reliable capture/display scheduling remain pending.

The [metadata and editable RAW workflow](stock-editable-raw.md) now carries
per-source calibration through recording and exports decoded DNGs or GPRs
without re-encoding their stock payloads. Independent TIFF reads and SDK
decodes verify calibration, EXIF/GPS, compressed bytes and Bayer values.
Standalone uncompressed DNG packaging supports four CFA phases and 12/14/16-bit
counts. The video frontend now maps these domains to the stock encoder.

The [independent build profiles](stock-build-profiles.md) now separate the
capture, preview and desktop SDK dependencies, export installed CMake targets
and generate relocatable static-library ZIPs. Package checks remove the SDK
and unused codec sources from minimal builds, delete producer paths and run
outside C/C++ clients against the extracted archive. Full packages also check
the installed Python/native editable-export workflow.

The [low-level Bayer format port](stock-bayer-formats.md) now accepts all four
Bayer phases with word-packed 12/14/16-bit counts while retaining the stock
12-bit logarithmic transform. It does not import the earlier codec's higher
internal precision. The [still SDK port](stock-still-formats.md) adds its public
format mapping, spatial black-level handling, source matrices/illuminants and
supported GainMaps. The [still preset workflow](stock-still-quality.md) adds
explicit Q0–Q5 selection and exact typed-calibration packaging around the SDK,
with lossless-DNG and Pi replay measurements. Restored still-tier/model quality
approval and broader metadata support remain pending. Video capture, extraction,
editable RAW packaging and calibrated preview now cover all 12 Bayer/count
combinations; the optional CNN adapter remains RGGB14-only.
The [decoder boundary audit](stock-decoder-bounds.md) now checks public arguments
and every allocator-failure point reached by an independent stock RAW/RGB
fixture. Arbitrary malformed entropy streams and wider SDK error handling
remain separate work.

The [public SDK C API audit](stock-sdk-api.md) repairs two missing published
symbols, adds an allocator-aware parameter copy with rollback, makes owned
parameter cleanup repeatable and classifies VC-5 metadata without image decode.
Real C callers, allocation-failure tests and installed clients exercise the
contracts; broader geometry/buffer and still concurrency auditing remain open.

The [encoder boundary audit](stock-encoder-bounds.md) additionally rejects tiny
or overflowing geometry and short row capacity before codec allocation, and
normalizes unaligned/odd-stride historical Bayer layouts through scratch
allocated with the caller's callbacks. Valid aligned callers retain their existing fast path and
stock-byte evidence. Full compressed-decoder and SDK failure/concurrency audits
remain separate requirements.

The [optional still reconstruction workflow](stock-cnn-quality.md) now produces
calibrated editable DNG using the existing stock-Q3 1x model. Twenty-four
lossless-reference comparisons show modest aggregate improvements, including
a Q5 scene regression. This is functional/model-evaluation evidence, not
restored-tier or 2x quality approval; training-split membership is unknown.

[Portable reconstruction](stock-cnn-portable.md) now bundles the legacy BIBO
architecture and supports explicit 1x/2x still and recorded-sequence inference,
including scaled crop/EXIF and phase-correct GainMap metadata. Four legacy 2x
checkpoints all regress against bicubic in sixteen simulated-stock comparisons;
no 2x model is approved. A [fresh stock-matched candidate](stock-sr-training.md)
now has source-grouped training and frozen final evaluation. Its modest overall
gains and shadow regression leave the full quality gate unfinished.

[Stock MOV interchange](stock-mov.md) now preserves complete stock GVID files
through private GVS2/GVS3 MOV sample profiles, including original payloads,
metadata and timestamps. Independent packet checks, Pi SDK pixels/calibration,
Mac/Pi FFmpeg-version exchange, sanitizer checks and relocated packages validate
the transport. It is not standard CFHD or rendered ProRes. Optional declared
PCM audio and nominal-rate timecode now preserve video bytes/timestamps, with
sample-exact WAV extraction and independent timecode clocks.

[Calibrated ProRes rendering](stock-prores.md) now processes each actual typed
DNG through the macOS RAW decoder into a 16-bit Rec.709 intermediate and deep
ProRes HQ/4444, with explicit frame durations and independent packet/color checks.
Acknowledged frame delivery now reuses one deep TIFF instead of retaining
the entire rendered sequence; the original batch manifest interface remains.
Both caller-selected 1x and 2x CNN paths run through this renderer. Real camera
functional checks include 8192x6144 12-bit 4444 output; broader rendered/temporal
quality approval remain pending. Declared stock-MOV audio/timecode now carry
through ProRes export; caller-supplied synchronized WAV/labels are also accepted.

This is not feature-suite parity. Restored still tiers, broader rendering validation, full reconstruction/model quality
selection, broader preview color/lens validation, integrated capture/display performance
and remaining platform/release integration remain
pending. Earlier
feature/validation PRs remain open and unchanged.

The #100 experiment used preloaded RAWs decoded from two supplied GPR stills,
not a live sensor sequence. On Pi 5 the 900-frame Q3/Q4 runs averaged about
30 fps before final flush, but missed 231/900 and 294/900 completion deadlines;
final flush reduced total throughput to 28.47/28.22 fps. Q3 per-frame fsync
measured 23.44 fps. Storage was USB SSD, not microSD. Four channel workers
used the four CPU cores; preview and CNN were outside capture.

Existing stock-Q3 BIBO1x inference works, but reduced PSNR relative to those
two replay references. Those references are already compressed-camera output,
not sensor truth. Do not enable restoration by default or inherit the old
fused-codec model's visual approval without new evidence.

Actual sensor delivery, firmware integration, on-camera display presentation,
durable microSD recording and camera-specific thermal behavior remain
hardware integration work. Host evidence must identify those boundaries.
