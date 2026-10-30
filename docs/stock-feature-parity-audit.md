# Original feature and validation accounting

Audit sources: fork PR #95 runtime `8be29eee57b4637865b572f18ab9e3f4edaa2236`,
PR #96 validation `821420d7acac8a316d16293b93d4b3204631a38f`, their PR bodies,
`docs/ADOPTION.md` and `tests/Validation.cmake` at those revisions. The original
eight adoption groups define the rows below. This is an accounting of current
implementation and evidence, not a claim that all original features are done.

| Original group | Current stock implementation/evidence | Remaining or different |
|---|---|---|
| Stills | Four CFA phases, 12/14/16-bit words, packed-12 SDK paths, six presets, typed calibration and editable DNG/GPR; `stock_still`, `bayer_formats`, `raw_media`; [format contract](stock-still-formats.md) and [quality evidence](stock-still-quality.md). One real 11664x8750 X2D source passes all six presets with three repeats and independently verified source decoding | Old compact three-tier size/quality approvals do not transfer. New restored tiers lack approved models. The single 100 MP source does not establish a broad camera corpus. |
| Fused codec | Replaced by the requested historical stock-compatible VC-5 architecture. Exact still/replay payload checks and encoder/decoder boundary tests cover the replacement. [Stock encoder](stock-encoder-sub100.md) | Fused subband/ANS edge tests cannot prove stock VC-5 behavior and are not applicable. Old Q8/profile semantics are deliberately not advertised. |
| Capture/GVID | Bounded copy/lease ownership, asynchronous writer, flush/finish/cancel, actual PTS, source metadata, CRC/END3 and explicit prefix recovery; `capture_lifecycle`, `capture_c_api`, `gvid3_conformance`, `gvid2_compatibility`; [contract](stock-capture-api.md) | Old fused GVID is not silently interpreted as stock GVID. Physical sensor/storage scheduling and durable SD remain unverified. |
| Native preview | Independent stock RGB fixtures, calibrated source plans, all reductions/orientations, bounded latest-pending queue and sink-error isolation. Optional encoder-derived quarter-scale path eliminates entropy decoding; [Pi receipts](stock-capture-preview.md) | Physical display, broader lens/look/temporal approval and strict sustained zero-late timing remain open. Encoder path is opt-in and quarter-scale only. |
| Desktop outputs | Exact GVID/MOV recovery, >4 GiB offsets, PCM/timecode, editable Bayer export and calibrated macOS deep ProRes with optional reconstruction. Core ML/MPSGraph/hybrid engines now also run through a standalone native raw executable, with standard-library still/GVID/timelapse/ProRes control paths; [native runtime](stock-native-runtime.md), [Metal](stock-metal.md), [Core ML](stock-coreml.md), [MOV](stock-mov.md), [ProRes](stock-prores.md) | Historical monolithic command syntax is not retained; containers are coordinated by the standard-library layer. Native simulated-capture/regression analysis remains on the analysis workflows. Backend/host arithmetic is not universally bit-identical to Torch. Selected export interoperability and look/motion approval remain open. |
| Optional FFmpeg decoder | New `gpr_stock` adapter for pinned FFmpeg n8.0 directly decodes GVS2/GVS3 to Bayer, using checked clip configuration in `glbl`. Twelve CFA/depth combinations, frozen fixtures, corruption rejection and PNG/ProRes exercise the replacement; [build/contract](stock-ffmpeg-decoder.md) | Requires a patched FFmpeg build; old MOVs without decoder configuration must be unwrapped/rewrapped. Native/hosted platform results are revision-bound; this is not bundled-application support or calibrated color rendering. |
| Reconstruction | Explicit portable 1x/2x architectures, checkpoint contracts, editable sequence/still output, optional GPR re-encoding and fresh source-grouped training/evaluation. Stock UPRESABLE provides timelapse/regression/both orchestration, direct captured-GPR inputs, exact GPR sequence packing and optional calibrated ProRes. Two real 12 MP Pi inputs produce independently verified 8192x6144 outputs. Core ML/MPSGraph/hybrid execution and a standalone native host cover the supported media paths; [workflow/measurements](stock-upres-workflow.md), [native runtime](stock-native-runtime.md), [portable runtime](stock-cnn-portable.md), [cleanup experiment](stock-cleanup-training.md), [SR experiment](stock-sr-training.md) | Functional inference does not approve a checkpoint. Current candidates regress in held-out regions; no new model promotion. Broader real-source and temporal/motion quality remain open. Native simulation/regression analysis uses the existing analysis workflows; historical command syntax and universal cross-backend bit identity are not claimed. |
| Integration/validation | Separate fork draft #101, four stripped/relocated packages, external C/C++ clients, optional reconstruction contracts, Mac/Pi Release suites and seven hosted platform jobs | Current feature checkpoints use the new architecture rather than replaying old eight-commit adoption identities. Latest CI must pass for each head. Broader fuzz/sanitizer expansion is explicitly deferred at the user's request. |

The old PR explicitly left firmware deployment, sensor/display integration,
durable SD, external model weights and premium still-SR approval unproven.
Those boundaries remain explicit; preserving an old limitation does not make
it completed hardware or model-quality validation.

Mac and Pi functional validation of the new FFmpeg decoder passes, with its
hosted platform gate passing at `eaeaefa`. New command orchestration also passes
on the two real captured-GPR Pi sources. Native backend execution is implemented;
it is no longer an unimplemented parity item. Reuse of an old model or GPU
backend still requires a stock-input quality check. No old
visual/quality approval, size-tier claim, or historical timing receipt is
relabeled as new evidence.

## Applicable validation from #96

The frozen `tests/Validation.cmake` registers the tests in the first column.
Replacement tests check corresponding stock contracts; old fused-codec tests
cannot establish correctness of a different codec architecture.

| Original validation | Current evidence | Replacement scope |
|---|---|---|
| `test_labs_encoder_api`, `test_video_encoder_abort`, `test_video_full_chain`, portable pipeline simulation | `capture_lifecycle`, `capture_c_api`, `capture_preview`, `stock_sequence`; real Mac/Pi replay | Copy/lease ownership, bounded queues, cancellation waking blocked callers, flush/finish/writer errors and recording-to-preview/export. Replay uses supplied frames, not a sensor. |
| `gvid_format` | `gvid3_conformance`, `gvid2_compatibility`, `video_format_matrix`, `stock_mov` | Stock profile/version checks, CRC/END3, metadata, truncation and explicit prefix recovery. Old fused GVID is not silently accepted. |
| `fused_band_roundtrip`, `fused_pool_drop_hp`, `fused_edges_split`, `fused_edges_inline`, `entropy_inline_tail_flush` | `bayer_formats`, `bayer_formats_fast`, `encoder_bounds`, `encoder_bounds_fast`, `decoder_bounds`, encoder-preview probes and historical payload/pixel comparisons | Applicable boundary/equivalence checks rebuilt for stock VC-5. Fused pool, split/inline joint-ANS and tail-flush details are replaced, not ported. |
| `still_metadata` | `sdk_c_api`, `raw_media`, `stock_still`, independent real-source still receipts | Typed supported metadata, editable counts, twelve CFA/depth combinations, six presets, SDK ownership and real Nikon/X2D sources. Unsupported metadata stays explicit. |
| `native_preview` | `preview_contract`, `preview_scalar_contract`, `preview_queue`, `preview_cli`, `stock_preview_profiles`, `capture_preview` | Independent RGB fixtures, calibration/orientation/reductions, serial/vector equivalence, queue ownership and failure isolation. No physical display claim. |
| `sr_runtime`, registry/model contracts and external quality gates | `stock_cnn_test.py`, `stock_upres_test.py`, `stock_coreml_test.py`, `stock_metal_test.py`, `stock_native_test.py`; fresh 1x/2x training/evaluation | Checkpoint/artifact binding, scales/tiling/count domains, native engines, editable output and end-to-end workflows. Learned models fail quality promotion; passing runtime tests cannot override that result. |
| Desktop/FFmpeg integration | `stock_mov_test.py`, `stock_prores_test.py`, `stock_ffmpeg_test.py`; real A/V, >4 GiB and native media receipts | Exact payload/timing recovery, declared PCM/timecode, calibrated deep ProRes and optional pinned FFmpeg Bayer decoder. Editor interoperability remains broader than these checks. |
| Adoption/build/CI/evidence tooling | `build_profiles.py`, relocated external C/C++ clients, seven hosted jobs and revision-bound receipts | Current independent packages replace old eight-commit adoption identities. Old feature-coverage instrumentation/research diagnostics are not reproduced. Broader fuzz/sanitizer expansion is deferred at the user's request. |

## Delivery versus approval

All eight original production groups have a stock implementation or an explicit
architectural replacement above. This establishes feature coverage, not
completion of the entire goal or approval of every output. The
[requirement ledger](stock-rebuild-requirements.md) distinguishes implementation,
measured failures, unsupported combinations and external validation. The strict
sustained Pi timing gate and learned-model quality gate remain unmet.
Percentages are planning estimates, not fractions of passing tests.

The [writeback follow-up](stock-capture-writeback.md) adds an optional Linux
storage policy. Its final 600-frame replay reaches 20.0047 durable fps and
retains all pixels/payloads, but misses 16 write/33 preview deadlines. Slower
repeats, including an unchanged-binary control, expose additional unresolved
platform timing variability. No sustained-floor approval follows.
