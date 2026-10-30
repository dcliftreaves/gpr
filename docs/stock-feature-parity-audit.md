# Original feature and validation accounting

Audit sources: fork PR #95 runtime `8be29eee57b4637865b572f18ab9e3f4edaa2236`,
PR #96 validation `821420d7acac8a316d16293b93d4b3204631a38f`, their PR bodies,
`docs/ADOPTION.md` and `tests/Validation.cmake` at those revisions. The original
eight adoption groups define the rows below. This is an accounting of current
implementation and evidence, not a claim that all original features are done.

| Original group | Current stock implementation/evidence | Remaining or different |
|---|---|---|
| Stills | Four CFA phases, 12/14/16-bit words, packed-12 SDK paths, six presets, typed calibration and editable DNG/GPR; `stock_still`, `bayer_formats`, `raw_media`; [format contract](stock-still-formats.md) and [quality evidence](stock-still-quality.md) | Old compact three-tier size/quality approvals do not transfer. New restored tiers lack approved models. Broader 100 MP real-source corpus remains open. |
| Fused codec | Replaced by the requested historical stock-compatible VC-5 architecture. Exact still/replay payload checks and encoder/decoder boundary tests cover the replacement. [Stock encoder](stock-encoder-sub100.md) | Fused subband/ANS edge tests cannot prove stock VC-5 behavior and are not applicable. Old Q8/profile semantics are deliberately not advertised. |
| Capture/GVID | Bounded copy/lease ownership, asynchronous writer, flush/finish/cancel, actual PTS, source metadata, CRC/END3 and explicit prefix recovery; `capture_lifecycle`, `capture_c_api`, `gvid3_conformance`, `gvid2_compatibility`; [contract](stock-capture-api.md) | Old fused GVID is not silently interpreted as stock GVID. Physical sensor/storage scheduling and durable SD remain unverified. |
| Native preview | Independent stock RGB fixtures, calibrated source plans, all reductions/orientations, bounded latest-pending queue and sink-error isolation. Optional encoder-derived quarter-scale path eliminates entropy decoding; [Pi receipts](stock-capture-preview.md) | Physical display, broader lens/look/temporal approval and strict sustained zero-late timing remain open. Encoder path is opt-in and quarter-scale only. |
| Desktop outputs | Exact GVID/MOV recovery, >4 GiB offsets, PCM/timecode, editable Bayer export and calibrated macOS deep ProRes with optional reconstruction; [MOV](stock-mov.md), [ProRes](stock-prores.md) | Original native CoreML/Metal inference backend options are not recreated by portable Torch inference. Native acceleration/selected export compatibility remains open. The macOS RAW renderer is a distinct processing path. |
| Optional FFmpeg decoder | New `gpr_stock` adapter for pinned FFmpeg n8.0 directly decodes GVS2/GVS3 to Bayer, using checked clip configuration in `glbl`. Twelve CFA/depth combinations, frozen fixtures, corruption rejection and PNG/ProRes exercise the replacement; [build/contract](stock-ffmpeg-decoder.md) | Requires a patched FFmpeg build; old MOVs without decoder configuration must be unwrapped/rewrapped. Native/hosted platform results are revision-bound; this is not bundled-application support or calibrated color rendering. |
| Reconstruction | Explicit portable 1x/2x architectures, checkpoint contracts, editable sequence/still output, optional GPR re-encoding and fresh source-grouped training/evaluation; [portable runtime](stock-cnn-portable.md), [cleanup experiment](stock-cleanup-training.md), [SR experiment](stock-sr-training.md) | Functional inference does not approve a checkpoint. Current candidates regress in held-out regions; no new model promotion. The original UPRESABLE timelapse/both-mode command orchestration is not mapped command-for-command; existing stock tools compose constituent workflows. Temporal/motion quality and original native backend parity remain open. |
| Integration/validation | Separate fork draft #101, four stripped/relocated packages, external C/C++ clients, optional reconstruction contracts, Mac/Pi Release suites and six hosted platform jobs | Current feature checkpoints use the new architecture rather than replaying old eight-commit adoption identities. Latest CI must pass for each head. Broader fuzz/sanitizer expansion is explicitly deferred at the user's request. |

The old PR explicitly left firmware deployment, sensor/display integration,
durable SD, external model weights and premium still-SR approval unproven.
Those boundaries remain explicit; preserving an old limitation does not make
it completed hardware or model-quality validation.

Mac and Pi functional validation of the new FFmpeg decoder now passes. Next
parity work must finish its hosted platform gate and
decide/implement the applicable native inference and command-orchestration interfaces. Reuse of
an old model or GPU backend also requires a stock-input quality check. No old
visual/quality approval, size-tier claim, or historical timing receipt is
relabeled as new evidence.
