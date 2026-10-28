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
counts; this does not extend the encoder's accepted formats.

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
approval, broader metadata support and video frontend mappings remain pending.

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
the transport. It is not standard CFHD or rendered ProRes; audio/timecode
extensions remain pending.

[Calibrated ProRes rendering](stock-prores.md) now processes each actual typed
DNG through the macOS RAW decoder into a 16-bit Rec.709 intermediate and deep
ProRes HQ/4444, with explicit frame durations and independent packet/color checks.
Both caller-selected 1x and 2x CNN paths run through this renderer. Real camera
functional checks include 8192x6144 12-bit 4444 output; broader rendered/temporal
quality approval and audio/timecode integration remain pending.

This is not feature-suite parity. Restored still tiers, MOV audio/timecode extensions, broader rendering validation, full reconstruction/model quality
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
