# Labs Intake: `.gvid` Raw-Video Prototype

Last refreshed: 2026-07-01

## Recommendation

GPR is ready for **Labs prototype exploration** as a native 4096 x 3072 Bayer
raw-video capture path that writes `.gvid` streams, decodes the same stream for
camera-back preview, and uses desktop tools for cleanup, 8K SR, review, and
ProRes export.

GPR is **not** ready for direct camera-firmware merge. The missing work is not
the desktop media path; it is target firmware integration evidence: sensor/DMA
handoff, sustained target capture under thermal and storage load, exact memory
ownership, and target CI.

## What Ships In The Prototype

| area | status | evidence |
|---|---|---|
| Raw-video container | `.gvid` sequence of per-frame FUSED `.gpr` payloads | `source/lib/vc5_encoder/gpr_video_format.h`, `tools/gvid_pack.py` |
| Native 12MP / 4K Bayer capture target | Selected 1,440-frame Pi stand-in closure validates 4096 x 3072 Bayer recompression into `.gvid`, 0 drops, recovery, valid container, and 20.50 fps wall / 21.52 fps median. This clears the accepted 20+ fps floor for Labs handoff; actual Mission 1 firmware readiness still needs a camera-role receipt from sensor/DMA or camera ring buffer, SD writer, and rear display. Strict 24 fps is stretch performance research unless the product target is raised again. | `docs/LABS_TARGET_BENCH.md`, `docs/VIDEO_STATUS.md` |
| Live/camera-back preview | The same 4096 x 3072 `.gvid` decodes to 1024 x 768 full-frame RGB preview at 24.20 fps wall / 43.86 fps median decode-plus-target on the Pi stand-in. | `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`, `docs/LABS_TARGET_BENCH.md` |
| Desktop review/export | `.gvid` can feed `gpr2prores` and ProRes review outputs | `docs/GETTING_STARTED.md`, `tools/gpr2prores/USAGE.md` |
| Metadata dispatch | source metadata sidecar and runtime dispatch validation | `docs/GVID_METADATA_DISPATCH_2026-06-04.md` |
| Production evidence tracking | release manifest and CI checks | `docs/RELEASE_READINESS.md`, `docs/release_evidence_manifest.json` |

## What Does Not Ship In The Prototype

| area | reason |
|---|---|
| Direct firmware merge | No camera-firmware sensor/DMA integration contract has been executed on target hardware. |
| Full-res 4K/8K live preview | Current quality paths are desktop/offline; live camera-back output is the 1024 x 768 full-frame preview from the 4K `.gvid` stream. |
| Arbitrary CNN routing in firmware | The current CNN/routing work is desktop-side review output, not a firmware dependency. |
| Unbounded capture guarantees | Pi stand-in receipts validate container/recovery behavior above the accepted 20+ fps floor, but actual Mission 1 camera-role capture is not proven. Strict 24 fps is optional performance research unless reinstated as the product target. |

## Current Readiness

| question | answer |
|---|---|
| Can the repo demonstrate the media shape? | Yes: `.gvid` pack/unpack, metadata dispatch, and ProRes review tooling exist. |
| Can it hit the native 12MP / 4K Bayer capture-rate target on the stand-in path? | Yes for the accepted 20+ fps floor: the selected 1,440-frame Pi stand-in closure records 20.50 fps wall / 21.52 fps median with zero drops, valid `.gvid`, recovery, and Lexar write-budget pass. It does not prove actual Mission 1 camera-role capture until the real sensor/DMA or camera ring-buffer source, SD writer, and rear display run. |
| Can it hit the live display target? | Yes for the stand-in decode/display side: the same 4K `.gvid` decodes to full-frame 1024 x 768 RGB preview above 20 fps. |
| Is the format safe enough for firmware review? | Source-level path is hardened: v1 C parsing rejects malformed headers and streams, and v1 writing rejects non-finite/overflowing FPS and bitrate fields; target recovery still needs receipts. |
| Are artifacts portable outside the 8TB work drive? | Source/media and Pi target-proxy bundles verify; final camera bundle still needs actual camera-firmware receipts. |
| Is CI sufficient for Labs intake? | Hosted CI covers source-level checks; target/self-hosted lanes are specified for media and hardware behavior. |

## Reviewer Entry Points

- Product/media overview: `../README.md`
- First-hour GoPro/Labs camera-role checklist: `docs/GOPRO_LABS_FIRST_HOUR.md`
- Release proof trail: `docs/RELEASE_READINESS.md`
- Capture-to-review walkthrough: `docs/GETTING_STARTED.md`
- Video status and target ladder: `docs/VIDEO_STATUS.md`
- Raw target timing: `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`
- Labs goal and stop criteria: `docs/LABS_READINESS_GOAL.md`
- Pi 5 capture regression note: `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md`
- Firmware integration contract: `docs/LABS_FIRMWARE_API.md`
- Artifact bundle contract: `docs/LABS_ARTIFACT_BUNDLE.md`
- Mission 1 evidence runbook: `docs/LABS_MISSION1_RUNBOOK.md`
- Target bench requirements: `docs/LABS_TARGET_BENCH.md`
- CI lane plan: `docs/LABS_CI_PLAN.md`
- Current readiness review: `docs/LABS_READINESS_REVIEW.md`

## Next Required Evidence

1. Package or refresh a portable target artifact bundle with checksums and
   verification steps, using the native 12MP / 4K Bayer Pi closure receipts as
   conservative 20+ fps stand-in evidence while labeling actual Mission 1
   camera-role capture as unproven.
2. Execute or stub the firmware sensor/DMA handoff receipt: frame ownership,
   metadata, storage path, recovery behavior, and accepted 20+ fps camera
   target.
3. Add or document CI lanes for hosted source checks and target/self-hosted
   media checks.
