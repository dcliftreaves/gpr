# Incremental wavelet and bounded inverse prototype

This experimental worktree keeps a candidate for further capture integration.
It is not yet part of the delivered feature PR #101. No sustained camera rate,
public row API, capture lifecycle integration or package approval is claimed.

The forward scheduler advances each stage only when its upstream LL rows are
available. A private synchronous row callback consumes quantized upper bands
while compact entropy coding retains only its ordinary highpass row buffers.
The test collector reconstructs quarter-scale GS/RG/BG planes during encoding.
Existing complete coefficient callbacks remain supported by their old path.

Dequantization occurs once at coefficient arrival. The collector retains three
upper rows, four reconstructed LL rows, and eight lower HP rows for even lower
band heights. Odd heights use sixteen HP rows: a bottom-edge flush can require
nine live rows. The initial universal eight-row draft fails its guard before
writing and is retained in the external failure receipts. The corrected version
passes a dense height sweep as well as the original format matrix.

Mac/Pi checks include 17 focused Release CTests, 360 complete coefficient-view
comparisons, 840 row-inverse versus unchanged full-inverse cases, and a final
497-case combined codec/stream-inverse comparison on each machine. The last
comparison checks payload bytes against the ordinary encoder and all three
planes against independent entropy decoding. These are prototype checks, not
registered delivery CI targets.

The final ordinary-user Pi diagnostic uses two actual native 12 MP sources,
four fixed modes in the same process/arena, sixteen blocks and sixteen
iterations per block. One declared warmup per block leaves sixty measurements
per mode/source. Retained encode-plus-inverse medians are 43.39984/42.010214 ms;
the final streaming medians are 39.977447/39.7899835 ms. Every final streaming
block median beats every retained control block median. An intermediate
version has mixed/slower results on the first input and remains recorded.
The final encoder arena uses 6,320,640 fewer bytes; additional bounded collector
buffers and final planes are separate allocations, not included in that counter.
There is no color rendering, queue, pacing, writing or final fsync in this test.

Across three diagnostic versions, all 1,536 payloads and 3,456 actually
reconstructed planes compare exactly. The independent audit verifies event
order, warmups, medians, source/driver hashes and final block comparisons.
Measured source snapshots, binaries identified by SHA, protocols, raw numeric
receipts and initial failures are preserved under
`/Volumes/OWC_8TB/gpr_work/artifacts/stock_wavelet_stream_20261031`, with the
matching isolated Pi root under `/mnt/ssd/gpr_work/`.

To exercise the prototype locally:

```sh
cmake -S . -B build-row-prototype -DCMAKE_BUILD_TYPE=Release \
  -DGPR_BUILD_SDK=OFF -DGPR_BUILD_STILL_APPS=OFF \
  -DGPR_BUILD_CODEC_TESTS=ON -DGPR_ENABLE_VIDEO=ON \
  -DGPR_ENABLE_PREVIEW=ON -DGPR_BUILD_VIDEO_TESTS=ON \
  -DGPR_BUILD_PREVIEW_TESTS=ON
cmake --build build-row-prototype --parallel 4
build-row-prototype/preview_inverse_row_contract
env GPR_STREAM_UNPACK=1 GPR_BAND_STREAM=1 GPR_CHANNEL_ASM=1 \
  GPR_DIRECT_BANDS=1 GPR_COMPACT_BANDS=1 \
  build-row-prototype/wavelet_stream_inverse_contract
```

Next: expose a properly validated encoder row entry point, move the collector
out of tests into a reusable preview component with explicit errors/ownership,
integrate capture and calibrated queue submission, gate prototype CMake targets
for stripped builds, then validate cancellation, errors, packages and sustained
native-input recording. Do not treat the unpaced timings as a closed 20 fps
recording-plus-preview gate or replace the supplied production executable yet.
