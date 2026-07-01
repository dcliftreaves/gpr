# Product Lock Ledger

Last refreshed: 2026-07-01

This ledger separates locked product evidence from open production-readiness
work. It exists to keep percentage changes from being misread as algorithm
regressions.

The rule is simple: a locked path regresses only when its own committed gate,
receipt, hash, or CI guard fails. A lower or unchanged pillar percentage can
still be correct when new hardware, fixture, noise, or promotion evidence is
required.

## Locked Paths

| path | locked role | evidence that owns the lock | what would count as regression |
|---|---|---|---|
| STILL smallest | 50 MP compact editable raw still tier, `gpr_tools_q0` plus matched q3 BIBO_1x CNN. | `docs/SHIP_DECISION.md`, `docs/release_evidence_manifest.json`, still-image quality matrix, release manifest guard. | STILL visual gate failure, changed committed run hash without replacement evidence, broken DNG/GPR roundtrip, or release-manifest guard failure. |
| STILL primary | 50 MP general-purpose editable raw still tier, `gpr_tools_q3` plus matched q3 BIBO_1x CNN. | `docs/SHIP_DECISION.md`, `docs/CAPABILITIES.md`, still-image quality matrix, release manifest guard. | STILL visual gate failure, capability regression, broken still roundtrip, or manifest/hash drift. |
| STILL archival | Tight editable raw still tier, `gpr_tools_q8`, no CNN required. | `docs/SHIP_DECISION.md`, `docs/CAPABILITIES.md`, still-image quality matrix. | STILL visual gate failure, capability regression, or archival tier hash/receipt drift. |
| Broad real-camera Bayer phase coverage | Stills path has real RGGB/GBRG/GRBG/BGGR fixture evidence plus synthetic conformance for every normal unpacked 2x2 Bayer phase. | `docs/PRODUCTION_CAPTURE_REQUIREMENTS.md`, broad GoPro/Mission scan, broad old-photo scan, still fixture gap plan. | A phase inventory/fixture receipt no longer parses a real fixture, or still matrix/capability coverage for a normal phase fails. |
| VIDEO_FREEZE | Full-resolution desktop/post raw-video path. | `docs/VIDEO_STATUS.md`, `docs/FULL_PIPELINE_MATRIX.md`, release manifest guard. | Committed VIDEO_FREEZE gate failure, registry mismatch, or broken `.gvid`/review receipt. |
| UPRESABLE editable raw | Half-resolution capture to editable full-resolution raw. | `docs/UPRESABLE_PIPELINE.md`, `docs/release_evidence_manifest.json`, release manifest guard. | Bayer PSNR gate failure, editable raw packaging failure, or manifest/hash drift. |
| Mission 1 4K cleanup | Offline/review enhancement for current Mission 1 4K raw path. | `docs/CNN_PRODUCT_SCORECARD_2026-06-29.md`, `tools/check_mission1_cnn_closure.py`, 4K cleanup signoff receipt. | A replacement fails the Mission42 RGB/CFA target guard, tone/green audit, packaging receipt, or CNN closure guard. |
| Mission 1 8K SR | Offline/post 12MP-to-8K reconstruction path. | `docs/CNN_PRODUCT_SCORECARD_2026-06-29.md`, 8K SR promotion receipt, Mission42 and Z8 all24 full-frame gates, `.gvid`, DNG/GPR, and ProRes receipts. | Mission42 or Z8 broad gate failure, packaging/openability failure, registry/hash drift, or CNN closure guard failure. |
| Mission 1 Pi stand-in raw-video encode | 4096 x 3072 Bayer to `.gvid` above the accepted 20 fps Pi 5 stand-in floor. | `docs/VIDEO_STATUS.md`, `docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md`, Labs target-bench receipts. | The stand-in receipt no longer validates as true Bayer recompression, drops frames, misses the accepted 20 fps floor, or fails `.gvid` recovery/validation. |
| Mission 1 Pi stand-in preview | 4096 x 3072 `.gvid` to full-frame 1024 x 768 preview above 20 fps on Pi 5. | `docs/VIDEO_STATUS.md`, `docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md`, preview receipt. | Preview no longer decodes from the same `.gvid`, becomes crop-only, misses 20 fps, or fails the preview receipt validator. |

## Open Production Gates

| gate | why it is still open | evidence needed to close |
|---|---|---|
| Real Mission 1 camera-role raw-video closure | Current raw-video encode and preview receipts are Pi stand-ins, not actual Mission 1 sensor/DMA, SD writer, and rear-display receipts. | Real camera-role closure run with sensor/DMA or camera ring-buffer source, storage handoff, rear-display/UI handoff, zero drops, valid `.gvid`, and timing receipts. |
| Mission 1 and iPhone nonzero noise addback | X2D and Z8 have validated darkframe sidecars; Mission 1 and iPhone do not. | Same-camera, same-ISO darkframe stacks with source hashes, v1 camera-noise sidecars, runtime policy update, and raw-noise/signal audit pass. |
| Premium still-SR promotion | Current raw-CFA residual targets and trainers are diagnostic; Z8 is mildly positive, X2D/domain-general recovery is too weak. | Candidate-only runtime model that clears dedicated 50 MP and 100 MP still-SR gates, editor-latitude review, worst-row dashboard, editable DNG/GPR packaging, and no REF/source content at render time. |

## Optional Research

| research item | why it is not a production gate | evidence needed before it can replace a locked path |
|---|---|---|
| PSF-aware raw-video replacement | 4K cleanup and 8K SR are already approved baselines, and current native high/low pairs produce an unstable kernel. | Controlled Mission 1 high/low Bayer pairs with source hashes, decoded Bayer hashes, fixed settings, negative controls, stable native PSF kernel, and a PSF-conditioned 4K/8K candidate that beats the current baselines. |

## Reviewer Read

The repo is a working raw-stills and raw-video prototype with several locked
product paths. It is not a complete production claim for every pillar. The
remaining work is specific: real Mission 1 camera-role receipts,
Mission/iPhone noise sidecars, and promotable premium still-SR. The approved
4K/8K reconstruction path is closed for the current offline/post release.
Controlled PSF evidence is still useful for a better future video/SR model, but
it is optional research rather than a shipping blocker.
