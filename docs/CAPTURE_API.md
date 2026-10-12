# Raw Video Capture

The firmware-facing C entry point is `gpr_labs_encoder.h`. Supply unpacked
uint16 Bayer rows, their stride, pixel format, quality, and clip rate. The
encoder emits GVID headers and freshly compressed frames through a writer
callback. It does not wrap previously compressed camera GPR files.

## Integration Contract

- Serialize calls to submit. Frame indices begin at zero and are contiguous.
- Submit copies the input before returning; the camera may then reuse its
  buffer. Padded rows are repacked. This is not a zero-copy DMA API.
- Bounded queues apply backpressure. Do not call blocking submit from a sensor
  interrupt handler; use a camera worker with an explicit overrun policy.
- The writer runs on a background thread. Return zero only after accepting
  every byte; a failure aborts pending work. Do not destroy the encoder from
  its writer callback.
- Flush reports writer errors or incomplete delivery. It drains the encoder,
  not the filesystem: the application owns storage synchronization.
- Keep timestamps, exposure, gain, and dropped-frame records separately.
  GVID v1 does not serialize the submitted timestamp.

This layer requires the shared codec, fused codec, and GVID format commits.
It does not require preview, a desktop renderer, or CNN models. It is an
integration API, not a downloadable Mission 1 firmware plugin; sensor access,
threading, storage, and camera shutdown must be connected and tested by the
firmware owner.

## Tests

Build with CMake and run `ctest --test-dir build --output-on-failure`.
Native tests cover padded rows, ordered submission, writer failure,
cancellation, and container framing. The full-chain test checks framing and
band decoding, not whole-image perceptual quality.

`tools/test/test_labs_encoder_bench_cli.sh` exercises the public shim and a
separate-process simulated source. `tools/mission1_stream_source_encoder.py`
accepts a deterministic delay schedule; simulation is not a sensor receipt.
Use the same real Bayer fixture, quality profile, CPU settings, and storage
device when comparing builds. Report encode time, write/drain time, final
filesystem flush, output bytes, dropped frames, and memory separately.
