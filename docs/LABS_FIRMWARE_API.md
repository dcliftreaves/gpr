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
| Storage handle and durability policy | Caller-owned; record flush/fsync behavior in the receipt |
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

## Required camera evidence

The active target is native 4096 x 3072 capture plus full-frame 1024 x 768
preview from the same stream at the accepted 20+ fps floor. The Pi 5 evidence
is stand-in only. Final camera readiness requires:

- `target.role=camera` with actual sensor/DMA or camera-ring input.
- Executed sensor/DMA, camera storage, and rear-display/compositor handoffs.
- Source and output identity, dimensions, format, frame count, and hashes
  consistent across capture and preview.
- Sustained timing, frame-time percentiles, memory high-water mark,
  temperature, CPU utilization, and writer throughput.
- Zero drops, valid decoded output, interrupted-tail recovery, and visual
  display inspection.

The capture schema is `gpr_labs_camera_handoff_receipt.v1`; preview uses
`gpr_labs_preview_ui_receipt.v1`. Preview additionally records full-frame
downsample policy, color/tone processing, display surface, presentation path,
and buffer ownership. Schema validity alone does not prove hardware execution.

```bash
python3 tools/check_labs_camera_handoff_receipt.py "$GPR_ARTIFACT_ROOT/camera/camera_handoff_receipt.json"
python3 tools/check_labs_preview_ui_receipt.py "$GPR_ARTIFACT_ROOT/camera/preview_ui_receipt.json"
python3 tools/check_mission1_camera_closure_run.py "$GPR_ARTIFACT_ROOT/camera/mission1_camera_closure_run.json"
```

Set `GPR_ARTIFACT_ROOT` to your chosen output directory. Use
[Mission 1 Quick Validation](GOPRO_MISSION1_QUICK_VALIDATION.md) to collect
the receipts. Blocked receipts must name the source, ownership, storage,
display, timing, memory, thermal, or validation failure.

## Delivery lifecycle

Record the source commit and GPR version with the ABI and capability receipt.
Stage updates in a versioned directory, run preflight and short capture
validation, then switch the active component atomically. Retain the previous
working component for rollback; rollback must preserve captured media.
Log activation, validation, failure, and rollback events.

[Release Artifacts](RELEASE_ARTIFACTS.md) defines the review bundle.
Prior handoff plans and device-specific runbooks are in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09)
at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
