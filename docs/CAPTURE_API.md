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

For validation procedures, see [Testing Methodology](https://github.com/dcliftreaves/gpr/blob/review/product-validation/docs/TESTING_METHODOLOGY.md)
on the companion `review/product-validation` branch.
