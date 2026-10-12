# Labs Firmware Integration

The integration boundary is
`source/lib/vc5_encoder/gpr_labs_encoder.h`, a C shim over the video
encoder and `.gvid` writer. Use the header for exact structures, signatures,
and return codes. The firmware path does not run a CNN or encode ProRes.

## Input and ownership

Configure fixed dimensions, stride, bit depth, pixel format, quality, timebase,
target bitrate, and maximum in-flight frames before submitting input.
The current shim accepts unpacked 16-bit Bayer rows, including padded stride.
Live formats are RGGB/GBRG 12/14/16-bit (`0..5`); packed input and the
other Bayer phases require conversion or an explicit future contract.

| Object | Ownership |
|---|---|
| Input frame | Caller-owned; valid through synchronous `submit` |
| Encoder state | Created and destroyed through the shim |
| Callback output bytes | Encoder-owned until callback returns; copy or write before returning |
| Storage handle and durability policy | Caller-owned, including flush/fsync behavior |
| Display buffers | Camera integration must declare allocation, handoff, and release |

Frame indices are contiguous from zero. `timestamp_ns` supports receipt and
sidecar correlation; `.gvid` v1 does not serialize per-frame timestamps.
A nonzero write-callback result is fatal. Do not assume asynchronous
retain/release semantics without validating the actual implementation and
buffer lifetime.

Reject unsupported capabilities before accepting a frame. Record backpressure
and drops explicitly; do not silently change the format, dimensions, or target
fps. Stop on writer failure and preserve the complete-frame prefix for
recovery analysis. [GVID Conformance](GVID_CONFORMANCE.md) defines validity.

## Camera integration boundary

The active target is native 4096 x 3072 capture plus full-frame 1024 x 768
preview from the same stream at the accepted 20+ fps floor. Pi 5 encoding
with buffered writes is a stand-in, not proof of durable SD-card recording
or camera readiness. Firmware must provide actual sensor/DMA or camera-ring
input, storage synchronization, and rear-display/compositor integration,
including display buffers, presentation, and frame pacing.

For validation procedures, see [Testing Methodology](https://github.com/dcliftreaves/gpr/blob/review/product-validation/docs/TESTING_METHODOLOGY.md)
on the companion `review/product-validation` branch.

## Delivery lifecycle

Record the source commit and GPR version with the ABI and capabilities.
Stage updates in a versioned directory, then switch the active component
atomically after validation. Retain the previous
working component for rollback; rollback must preserve captured media.
