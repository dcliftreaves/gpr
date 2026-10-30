# Stock rebuild requirement ledger

Audit date: 2026-10-30. Published source/model inspected: `b224ff1`.
Runtime source remains the restored `f1e08c8` implementation.
Sources: the active goal, frozen runtime PR #95 (`8be29ee`), validation PR #96
(`821420d`), their PR bodies and adoption/validation files cited in the
[eight-group audit](stock-feature-parity-audit.md). Older receipts remain bound
to their recorded revisions; this ledger does not retimestamp their evidence.

## Requirements and evidence

| Requirement | Evidence inspected | Disposition |
|---|---|---|
| Separate branch and reviewable fork PR; preserve old PRs | `feature/stock-raw-media-runtime`; fork [draft #101](https://github.com/dcliftreaves/gpr/pull/101). GitHub reports fork #95/#96 and upstream #71/#72 open, with unchanged frozen head identities | Delivered. No upstream replacement promotion or old-PR closure |
| Build on stock encoder/#99/#100 | Foundation `d3d96ec`; historical payload/pixel comparisons in [core still receipts](stock-core-receipts/stills-mac.json), replay and [encoder evidence](stock-encoder-sub100.md) | Implemented and measured. Compatibility applies to checked codec profiles, not every container/editor |
| Broad stills and explicit compression choice | Four CFA layouts, 12/14/16-bit counts, packed-12 SDK support; `bayer_formats`, `raw_media`, `stock_still`; [presets](stock-still-quality.md) | Implemented. Historical stock log transform remains lossy |
| Original large-image/X2D case | [X2D receipt](stock-still-quality-receipts/mac-x2d-3265.json): 11664x8750 RGGB16, independent source decode, six presets, three repeats | Verified on one real 102 MP source. Broader corpus not established |
| Supported calibration and editable RAW | Typed image/EXIF/GPS/opcode records, decoded DNG/GPR count identities and source hashes; [contract](stock-editable-raw.md), `raw_media`, `stock_still`, real export/native integration receipts | Implemented within documented tag/opcode boundaries. General editor/lens compatibility is not established |
| Bounded recording lifecycle | Public C/C++ API; `capture_lifecycle`, `capture_c_api`; [contract](stock-capture-api.md) | Copies/leases, backpressure, asynchronous writes, cancellation, flush/finish and latched errors implemented. Sensor/DMA/storage adapters unverified |
| Checked RAW-video framing/recovery | `gvid3_conformance`, `gvid2_compatibility`, `video_format_matrix`; [contract](stock-capture-api.md) | Actual PTS, source/frame calibration, CRC/END3 and explicit prefix recovery implemented. Old fused GVID is a different profile |
| Full-frame calibrated 1024x768 preview without camera CNN | Independent fixtures and 192-case plan/plane comparisons; preview/capture tests; [Pi evidence](stock-capture-preview.md) | Implemented. Quarter-scale encoder-derived route optional. Memory sink tested; rear-display integration unverified |
| Relevant end-to-end Pi correctness/performance | Exact real-source replay; 600 recorded/previewed frames; [sustained receipt](stock-core-receipts/mission1-pi5-encoder-preview-600.json), [arena follow-up](stock-core-receipts/mission1-pi5-encoder-arena-600.json) | Correctness verified. Strict timing gate **unmet**: 46.07 ms p95 does not hide four late previews/five late writes; final fsync reduces durable average to 19.34 fps. Follow-up also has late deliveries |
| Exact MOV, large files, PCM/timecode | `stock_mov`; [contract](stock-mov.md), 4.42 GB boundary receipt, [real A/V receipt](stock-av-receipts/real-core.json) | Implemented for declared private stock profiles. Exact recovery does not imply standard CFHD or universal editor support |
| Calibrated deep ProRes/editable outputs | `stock_prores`; [contract](stock-prores.md), real 120-frame outputs and [native integration](stock-native-receipts/real-integration.json) | Implemented on macOS with optional CNN and audio/timecode. Broader rendered look/motion approval open |
| Optional FFmpeg decoder equivalent | Pinned n8.0 adapter; twelve CFA/depth checks, fixtures, malformed configuration and conversion on Mac/Pi/hosted Linux; [contract](stock-ffmpeg-decoder.md) | Implemented as an explicit patched build. Bayer output is not calibrated color rendering |
| Portable offline 1x cleanup and 2x/8K inference | Eight `stock_cnn_test.py` contracts; [runtime](stock-cnn-portable.md), editable media and separate lossy re-encoding identities | Implemented for the declared RGGB14 family, explicit caller weights and optional repository 1x/2x research candidates. Broader codec formats do not widen model support |
| Original native desktop backend capability | Core ML, MPSGraph, custom Metal hybrid; `stock_coreml_test.py`, `stock_metal_test.py`, `stock_native_test.py`; [runtime](stock-native-runtime.md) | Implemented, including standalone host processing without Torch/NumPy runtime. Explicit numeric tolerances; historical monolithic CLI syntax not retained |
| High-level UPRESABLE modes/media chain | `stock_upres_test.py`, `stock_sequence_test.py`; [workflow](stock-upres-workflow.md), real Mac native and [Pi receipt](stock-upres-receipts/pi5-real-captured.json) | Timelapse/regression/both implemented through analysis workflows. Captured-GPR timelapse additionally has a standard-library native path. Native simulation/regression uses the analysis workflow |
| Real Pi reconstruction correctness/cost | Two 4096x3072 captures become 8192x6144 GPR/GVID/MOV; final payloads checked against independent historical encoder, editable pixels/calibration verified | Earlier candidate verified offline: 114.24 s total, 57.12 s/frame. The later [supplied diagnostic](stock-sr-source-regions.md) separately verifies 50 MP editable output/count agreement at 86.29–99.89 s/frame inference. Neither result is real-time CNN or sensor ground truth |
| Compatible checkpoints and stock-input quality validation | Architecture/domain/hash checks; source-grouped training and frozen evaluations in [1x](stock-cleanup-training.md) and [2x](stock-sr-training.md); legacy transfer also evaluated | A separately frozen [half-strength 1x candidate](stock-cleanup-strength.md) passes validation and the declared four-reference numeric guard (+0.639 dB pooled active PSNR), with Pi execution checked. The earlier full-strength 1x and stronger earlier 2x failures remain recorded. The later [source-wide 2x diagnostic](stock-sr-source-regions.md) passes patch/full-image/four-reference CPU/MPS numeric guards, but pooled gain is only +0.00729 dB. Broader visual/temporal/restored-tier promotion remains open |
| Original compact restored-tier claims | Six measured stock presets and explicit model/final decoded metrics | Old size/quality approvals do not transfer. No replacement restored tier or temporal/perceptual model approval |
| Independent packages/public clients | `build_profiles.py`, stripped capture/preview/camera/full packages, relocated C/C++ consumers, installed native receipt | Implemented. Apple/native ML optional and outside camera-library dependencies |
| Applicable validation/reproducible evidence | Old-to-new test map in [audit](stock-feature-parity-audit.md); 24 local Release targets; optional CNN/native/FFmpeg tests; seven hosted jobs and hashed receipts | Implemented; hosted status evaluated per revision. Broader fuzz/sanitizer expansion deferred by user. Old commit-adoption/coverage instrumentation and research diagnostics not recreated |

## Remaining work

1. Keep hosted validation current as the branch advances. All seven checks for
   published source/model `b224ff1` passed in
   [run 41123778153](https://github.com/dcliftreaves/gpr/actions/runs/41123778153),
   including native Core ML/MPSGraph/Metal and relocated packages on Mac.
   Current runtime restoration passes 26 Mac/23 Pi Release targets. These
   results precede this documentation/evidence-only update.
2. The [selected 1x candidate](stock-cleanup-strength.md) now passes the declared
   patch-validation and four-reference numeric nonregression guards, with an
   explicit repository checkpoint and Pi execution evidence. The later
   [2x diagnostic](stock-sr-source-regions.md) also passes narrow numeric guards
   and Pi execution/count checks, with small benefit. Improve useful 2x detail
   quality and broader real-source, rendered visual and temporal evidence before
   promoting restored tiers. [Native artifacts for this checkpoint](stock-sr-native.md)
   now pass scoped execution/count and full-reference RAW-quality checks. Earlier failures remain recorded; the scoped 1x result does
   not approve other domains or video quality.
3. Improve sustained Pi deadlines/durability before claiming a strict sustained
   20 fps floor. Short-run success and p95 do not close this gate.
   The [writeback follow-up](stock-capture-writeback.md) reaches 20.0047 durable
   fps with all 600 frames/previews exact, but 16 write/33 preview deadlines
   remain late. Poorer repeats and an unchanged-binary control also show
   unresolved platform timing variability; this is not a closed gate.
   The subsequent [preview-layout comparison](stock-preview-gain-layout.md)
   reduces retained unity-cap gain storage and measured rendering medians, but
   sustained repeats still overrun. A persistent-worker prototype was discarded.
   A subsequent CFA canonicalization prototype was likewise rejected after
   measurement; [retained independent preview coverage](stock-preview-register-experiment.md)
   now includes all four phases at 12/14/16 bits.
   Optional [compute-stage serialization](stock-preview-compute-stages.md)
   subsequently improves matched durable replay from 16.41–16.76 to
   18.28–18.63 fps, with exact accepted frames/previews. Both serial runs still
   overrun and miss deadlines; this is not closure of the timing gate.
   The following [direct final-plane reconstruction](stock-preview-direct-output.md)
   removes a measured copy and unused bands. Both matched serial runs preserve
   all 600 attempts at 19.9752/19.9988 durable fps and use 11.10 MB scratch,
   but hundreds of deliveries remain late. The gate is still unmet.
   Two [subsequent kernel proposals](stock-preview-rejected-kernels.md) were
   tested and discarded: bounded-token NEON dequantization lacks a consistent
   end-to-end win, and per-row addressing is slower in isolation. Runtime
   source is restored; their experimental test counts do not replace current
   validation or close the timing gate.
4. Keep sensor/DMA, rear-display, actual SD, thermal and physical A/V work
   explicitly unverified. The original PR did not establish those either.

This is broad implementation coverage, not proof of full goal completion while
broader quality and timing gates remain unresolved. Planning percentages
are not passing-test ratios.

## Latest checkpoint and timing evidence

The [published 1x native checks](stock-cleanup-native.md) pass FP32 Core ML and
Metal count budgets, with exact supported calibration. Faster FP16 Core ML
fails its preregistered precision bound. The [2x follow-ups](stock-sr-balanced.md)
fail shadow/highlight guards and supply no new weights. The current-binary
[background workload control](stock-background-control.md) preserves all 600
recordings/previews per run, but pausing competing work still leaves late
deliveries. None of these results closes broader quality or strict Pi timing.

The [region-balanced 2x follow-up](stock-sr-relative.md) also fails final guards.
Its full-frame validation diagnostic fails three of four held-out validation
sources despite patch-level success. This exposes a validation-coverage gap;
full-frame guards should precede subsequent final-reference evaluations.

The [full-image selector](stock-sr-full-selection.md) now implements this
validation stage, with nine optional CNN tests passing on both Mac and Pi.
Forty complete validation-image inferences reject all ten patch-qualified
candidates before further final evaluation. This closes the missing selection
mechanism, not the 2x model-quality gate.

Two [encoder-kernel proposals](stock-encoder-rejected-kernels.md) are tested
and discarded: paired 64-bit unpack loads preserve scalar results but are
slightly slower, and a precombined small-code pair table preserves byte streams
but is slower on its intended synthetic workload. Neither changes production
source or closes the strict Pi timing gate.

A [borrowed preview-plane handoff](stock-preview-plane-leases.md) removes the
queue's three-plane copy and passes ownership/output checks, but both matched
Pi lease runs have slower rendering and higher preview p95 than copying
controls. All 2,400 recordings/previews remain exact; the strict timing gate
still fails. The prototype is discarded, all six files are restored, fresh
26 Mac/23 Pi tests pass and the prior Pi executable is reproduced byte for byte.

The [source-wide 2x follow-up](stock-sr-source-regions.md) supplies an explicit
frozen diagnostic checkpoint after unchanged patch guards, full validation on
all 22 qualified combinations and four-reference CPU/MPS nonregression.
Pooled active gain is only +0.00729 dB; useful restored detail/tier/temporal
approval remains open. Both supplied 12 MP Pi inputs produce 50 MP editable
outputs with exact calibration and at most one-count CPU/MPS differences.
The separate 1x checkpoint and production encoder/capture source are unchanged;
[new 2x native artifacts](stock-sr-native.md) pass 12 execution and 24 full-reference
checks. Useful detail, broader quality and strict Pi timing remain open.

A [bounded shared unpack-row cache](stock-shared-rows.md) is rejected after
byte-exact isolated Pi comparisons: it computes each row once for all four
consumers, yet both eight-row comparisons are slower. Production runtime and
the unresolved strict deadline gate are unchanged.
