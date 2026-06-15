# Labs Intake: `.gvid` Raw-Video Prototype

Last refreshed: 2026-06-14

## Recommendation

GPR is ready for **Labs prototype exploration** as a half-res raw-video capture
path that writes `.gvid` streams and uses desktop tools for unpack, review, and
ProRes export.

GPR is **not** ready for direct camera-firmware merge. The missing work is not
the desktop media path; it is target firmware integration evidence: sensor/DMA
handoff, sustained target capture under thermal and storage load, exact memory
ownership, and target CI.

## What Ships In The Prototype

| area | status | evidence |
|---|---|---|
| Raw-video container | `.gvid` sequence of per-frame FUSED `.gpr` payloads | `source/lib/vc5_encoder/gpr_video_format.h`, `tools/gvid_pack.py` |
| Half-res 24 fps capture target | Pi 5 stand-in path has measured headroom | `docs/VIDEO_STATUS.md`, `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md` |
| Desktop review/export | `.gvid` can feed `gpr2prores` and ProRes review outputs | `docs/GETTING_STARTED.md`, `tools/gpr2prores/USAGE.md` |
| Metadata dispatch | source metadata sidecar and runtime dispatch validation | `docs/GVID_METADATA_DISPATCH_2026-06-04.md` |
| Production evidence tracking | release manifest and CI checks | `docs/RELEASE_READINESS.md`, `docs/release_evidence_manifest.json` |

## What Does Not Ship In The Prototype

| area | reason |
|---|---|
| Direct firmware merge | No camera-firmware sensor/DMA integration contract has been executed on target hardware. |
| Full-res 4K/8K live preview | Current quality paths are desktop/offline; live camera-back output is bounded to the 2K edge-safe policy. |
| Arbitrary CNN routing in firmware | The current CNN/routing work is desktop-side review output, not a firmware dependency. |
| Unbounded capture guarantees | Sustained thermal, power, storage, and partial-file recovery evidence still needs target-style bench receipts. |

## Current Readiness

| question | answer |
|---|---|
| Can the repo demonstrate the media shape? | Yes: `.gvid` pack/unpack, metadata dispatch, and ProRes review tooling exist. |
| Can it hit the half-res capture-rate target on the stand-in path? | Current docs report Pi 5 half-res capture at 24.93 fps median and 31 MB/s sustained budget. |
| Is the format safe enough for firmware review? | Source-level path is hardened: v1 C parsing rejects malformed headers and streams; target recovery still needs receipts. |
| Are artifacts portable outside the 8TB work drive? | Bundle contract exists; real sample media, checksums, and receipts still need packaging. |
| Is CI sufficient for Labs intake? | Hosted CI covers source-level checks; target/self-hosted lanes are specified for media and hardware behavior. |

## Reviewer Entry Points

- Product/media overview: `../README.md`
- Release proof trail: `docs/RELEASE_READINESS.md`
- Capture-to-review walkthrough: `docs/GETTING_STARTED.md`
- Video status and target ladder: `docs/VIDEO_STATUS.md`
- Raw target timing: `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`
- Labs goal and stop criteria: `docs/LABS_READINESS_GOAL.md`
- Firmware integration contract: `docs/LABS_FIRMWARE_API.md`
- Artifact bundle contract: `docs/LABS_ARTIFACT_BUNDLE.md`
- Target bench requirements: `docs/LABS_TARGET_BENCH.md`
- CI lane plan: `docs/LABS_CI_PLAN.md`
- Current readiness review: `docs/LABS_READINESS_REVIEW.md`

## Next Required Evidence

1. Finish strict `.gvid` C validation and malformed-file tests.
2. Add a target-style bench receipt for sustained capture, memory, storage,
   dropped frames, and file recovery.
3. Package a portable artifact bundle with checksums and verification steps.
4. Add or document CI lanes for hosted source checks and target/self-hosted
   media checks.
