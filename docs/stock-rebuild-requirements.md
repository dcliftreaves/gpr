# Stock rebuild requirement ledger

Audit date: 2026-10-30. Implementation inspected: `6860b55`.
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
| Portable offline 1x cleanup and 2x/8K inference | Eight `stock_cnn_test.py` contracts; [runtime](stock-cnn-portable.md), editable media and separate lossy re-encoding identities | Implemented for declared RGGB14 model family and optional external weights. Broader codec formats do not widen model support |
| Original native desktop backend capability | Core ML, MPSGraph, custom Metal hybrid; `stock_coreml_test.py`, `stock_metal_test.py`, `stock_native_test.py`; [runtime](stock-native-runtime.md) | Implemented, including standalone host processing without Torch/NumPy runtime. Explicit numeric tolerances; historical monolithic CLI syntax not retained |
| High-level UPRESABLE modes/media chain | `stock_upres_test.py`, `stock_sequence_test.py`; [workflow](stock-upres-workflow.md), real Mac native and [Pi receipt](stock-upres-receipts/pi5-real-captured.json) | Timelapse/regression/both implemented through analysis workflows. Captured-GPR timelapse additionally has a standard-library native path. Native simulation/regression uses the analysis workflow |
| Real Pi reconstruction correctness/cost | Two 4096x3072 captures become 8192x6144 GPR/GVID/MOV; final payloads checked against independent historical encoder, editable pixels/calibration verified | Verified offline: 114.24 s total, 57.12 s/frame. Not real-time CNN or sensor ground truth |
| Compatible checkpoints and stock-input quality validation | Architecture/domain/hash checks; source-grouped training and frozen evaluations in [1x](stock-cleanup-training.md) and [2x](stock-sr-training.md); legacy transfer also evaluated | Evaluation implemented. Learned-quality promotion **unmet**: all 30 trained 1x checkpoints fail the region guard; 2x pooled +0.067 dB hides shadow regression. Identity fallback supplies no learned improvement |
| Original compact restored-tier claims | Six measured stock presets and explicit model/final decoded metrics | Old size/quality approvals do not transfer. No replacement restored tier or temporal/perceptual model approval |
| Independent packages/public clients | `build_profiles.py`, stripped capture/preview/camera/full packages, relocated C/C++ consumers, installed native receipt | Implemented. Apple/native ML optional and outside camera-library dependencies |
| Applicable validation/reproducible evidence | Old-to-new test map in [audit](stock-feature-parity-audit.md); 24 local Release targets; optional CNN/native/FFmpeg tests; seven hosted jobs and hashed receipts | Implemented; hosted status evaluated per revision. Broader fuzz/sanitizer expansion deferred by user. Old commit-adoption/coverage instrumentation and research diagnostics not recreated |

## Remaining work

1. Keep hosted validation current as the branch advances. All seven checks for
   implementation `6860b5519a15584691cc489e6eb0ab87efe26b44` passed in
   [run 41063867230](https://github.com/dcliftreaves/gpr/actions/runs/41063867230),
   including native Core ML/MPSGraph/Metal and relocated packages on Mac.
   The fresh local 24-target Release run also passed (16.94 seconds). These
   results precede this documentation-only audit update.
2. Extend model and real-source quality evidence before recommending a learned
   restoration tier; temporal evidence is absent. Preserve failed gates rather
   than substituting aggregate PSNR or backend agreement for quality approval.
3. Improve sustained Pi deadlines/durability before claiming a strict sustained
   20 fps floor. Short-run success and p95 do not close this gate.
   The [writeback follow-up](stock-capture-writeback.md) reaches 20.0047 durable
   fps with all 600 frames/previews exact, but 16 write/33 preview deadlines
   remain late. Poorer repeats and an unchanged-binary control also show
   unresolved platform timing variability; this is not a closed gate.
   The subsequent [preview-layout comparison](stock-preview-gain-layout.md)
   reduces retained unity-cap gain storage and measured rendering medians, but
   sustained repeats still overrun. A persistent-worker prototype was discarded.
4. Keep sensor/DMA, rear-display, actual SD, thermal and physical A/V work
   explicitly unverified. The original PR did not establish those either.

This is broad implementation coverage, not proof of full goal completion while
quality/timing gates remain unresolved. Planning percentages
are not passing-test ratios.
