# Labs Target Bench

Last refreshed: 2026-06-14

This page defines the target-style evidence required for Labs prototype review.
It separates current Pi 5 stand-in evidence from the still-missing camera
firmware evidence.

## Current Evidence

| item | current evidence | status |
|---|---|---|
| Half-res `.gvid` capture budget | `docs/VIDEO_STATUS.md` reports 24.93 fps median and 31 MB/s at 1.30 MB/frame | stand-in evidence |
| 2K live/camera-back raw target | `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md` reports `2k_raw_0p5x_l2hh` at 29.85 fps median, 37.1 ms p95 | stand-in evidence |
| Desktop review PREVIEW | `docs/VIDEO_STATUS.md` reports q8 three-way PREVIEW quality pass at 13.65 s/image on Mac/MPS | offline-only evidence |
| Format validation | `test_video_format` and `test_video_full_chain` validate headers, streams, and real encoded `.gvid` files | committed CI evidence |
| Portable review bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` | stand-in bundle |

## Required Target Run

Before claiming firmware readiness, run a sustained target-style capture:

| metric | required receipt |
|---|---|
| duration | 10 minutes or explicit shorter-run blocker |
| fps | median, p95, p99, min |
| encode | median/p95/p99 ms/frame |
| storage | write MB/s and fsync/flush policy |
| memory | RSS or firmware heap high-water mark |
| CPU | utilization per core or firmware equivalent |
| thermal | temperature over time and throttle state |
| drops | count, frame indices, policy taken |
| output validity | C stream validation, metadata validation, decode checksum |
| interruption | normal stop and simulated interrupted-file recovery result |

## Current Gap

The current repo evidence is enough for a Labs prototype conversation, but not
enough for direct firmware readiness. Missing receipts:

- actual camera sensor/DMA handoff,
- sustained thermal/power behavior,
- storage behavior on the intended media path,
- partial-file recovery on target,
- target memory high-water mark.

Until those exist, Pi 5 numbers must be labeled as stand-in evidence.

The current Labs bundle includes the 120-frame Pi 5 stand-in receipt
`receipts/pi5_2k_l2hh_120f_standin.json`; it does not replace the required
10 minute target-style run.
