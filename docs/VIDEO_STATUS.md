# Video Status

## Current target

Capture native 4096 x 3072 Bayer into `.gvid`, then decode the same stream
to full-frame 1024 x 768 RGB for camera-back preview. The accepted Pi 5
stand-in floor is 20+ fps. Strict 24 fps is a stretch target, not the current
release blocker. No CNN runs on the camera.

Actual Mission 1 production remains unproven: sensor/DMA capture, camera
storage ownership, and rear-display presentation need camera-role receipts.
File-backed Pi runs and simulated source timing cannot establish those facts.

## Selected recorded evidence

These are existing 2026-06-25 receipts, not measurements made during cleanup.

| Receipt | Capture | Preview from the same stream |
|---|---|---|
| 420-frame Pi stand-in | 4096 x 3072, zero drops; 24.32 fps whole-run wall, 25.29 fps median loop | 1024 x 768; 25.85 fps whole-run wall, 36.23 fps median decode-plus-target |
| Selected 1,440-frame aggregate rerun | 4096 x 3072, zero drops, valid `.gvid`; 20.50 fps whole-run wall, 21.52 fps median loop | 24.20 fps whole-run wall, 43.86 fps median decode-plus-target |

The aggregate run records a Lexar SILVER PLUS write-budget pass and consistent
stream identity, dimensions, frame count, pixel format, source provenance,
and drop state across capture/handoff/preview receipts. These claims apply to
that measured setup. Whole-run wall throughput includes work omitted by
per-frame median timings; the two are not interchangeable.

Evidence is indexed by [release_evidence.json](release_evidence.json).
The archived `MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md` and
`VIDEO_STATUS.md` at
[`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef/docs)
preserve the detailed provenance and earlier receipts. The selected receipt
identity is `mission1_camera_closure_run_20260625/current_standin_followup`.
A later attempted camera-role run stopped at the source audit because no
camera sensor was enumerated.

## Reconstruction and format scope

Approved 4K cleanup and 8K SR run offline on desktop hardware and produce
editable Bayer outputs and review media. Z8 and Mission 1 no-CNN/CNN
whole-scene review outputs exist in the evidence record. Their playback
timebase is not a real-time SR performance claim.
See [Reconstruction](RECONSTRUCTION.md).

Live FUSED/`.gvid` pixel formats are unpacked RGGB/GBRG 12/14/16-bit
(`0..5`). Full-frame preview is the current target; older half-resolution
capture and cropped 2K preview receipts are historical only.

## Remaining camera work

Use [Mission 1 Quick Validation](GOPRO_MISSION1_QUICK_VALIDATION.md) to collect
source, storage, display, timing, memory, stream-validation, and recovery
evidence on actual camera hardware. Keep blocked receipts with a concrete
cause. [Labs Firmware API](LABS_FIRMWARE_API.md) defines the ownership and
handoff requirements.

Prior iteration logs remain in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at `3d675ef`.
