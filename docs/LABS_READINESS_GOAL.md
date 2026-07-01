# Labs Firmware Intake Goal

Last updated: 2026-06-15.

This file is the durable goal contract for the current session. If the
in-session tracker is lost, recreated, or summarized, restart from this file
instead of inferring new stop criteria from chat history.

## Active Session Goal

Make GPR reviewable as a camera-firmware Labs prototype: `.gvid` half-res raw
capture plus desktop review/export, with clear evidence for safety,
performance, artifact portability, and firmware integration boundaries.

This is not a claim that GPR is ready for direct camera firmware merge. The
target is a credible Labs intake package that lets a firmware/media engineer
decide whether to prototype `.gvid` raw capture and review tooling on target
hardware.

## Stop Criteria

Stop only when one of these is true:

1. The Labs intake package is complete and reviewable:
   - `docs/LABS_INTAKE.md` defines what ships and what is out of scope.
   - Firmware integration contract exists for frame input, encoder state,
     memory ownership, metadata, container output, backpressure, dropped
     frames, and partial-file recovery.
   - `.gvid` C reader/writer validation is hardened and covered by negative
     tests.
   - Target-style performance receipts exist for sustained capture/decode,
     memory, storage bandwidth, and dropped-frame behavior.
   - Artifact bundle docs make samples, dashboards, receipts, review media, and
     model/checkpoint hashes portable outside the local 8TB drive.
   - CI and release checks cover the Labs path, with self-hosted/target lanes
     specified where hosted CI cannot run them.
   - README remains a sharp media overview; detailed proof lives in linked docs.

2. Labs readiness is objectively blocked, with evidence:
   - target hardware access unavailable,
   - sensor/DMA integration missing,
   - thermal/power/storage target cannot be met,
   - `.gvid` format hardening exposes an incompatible design issue,
   - artifact portability cannot be satisfied,
   - or CI/build infrastructure cannot exercise the required path.

Do not stop at partial docs or a passing hosted CI run. The goal is reviewable
Labs intake evidence, not merely repo cleanliness. Use
`/Volumes/OWC_8TB/gpr_work` for large artifacts and temp. Start with `.gvid` C
hardening and the Labs intake package.

## Session Binding

As of 2026-06-15, this file is synced from the active Codex session goal for
the current burn-down. The in-session goal tracker is active with the same
objective and stop criteria. Work should continue against this file as the
durable source of truth for what "done" means until the Labs intake package is
complete, or until a specific evidenced blocker is documented.

Proper session goal:

> Make GPR reviewable as a camera-firmware Labs prototype: `.gvid` half-res raw
> capture plus desktop review/export, with clear evidence for safety,
> performance, artifact portability, and firmware integration boundaries.

The session should not stop because an intermediate optimization lands, hosted
CI passes, a dashboard improves, or one receipt looks better. It should stop
only when the package is reviewable by a firmware/media engineer, or when the
blocker is specific enough that the next required action depends on missing
hardware, missing integration access, or a documented design decision.

Goal tracker status for this session: active. A second goal should not be
created while this one is active; work should continue under this goal until it
is complete or objectively blocked.

## Reviewer Frame

Evaluate this repo as a firmware-media prototype intake, not as a research
dump. A reviewer should be able to answer these questions from committed docs,
source, tests, and compact receipts:

- What exactly would ship in the Labs prototype, and what is out of scope?
- Can the container be parsed, rejected, recovered, and decoded safely in C?
- Can the capture path sustain the target frame rate without frame drops,
  unbounded memory growth, storage stalls, or thermal collapse?
- Is the firmware-facing API explicit about frame buffers, stride, bit depth,
  timestamps, output ownership, backpressure, dropped frames, metadata, and
  partial-file recovery?
- Can a fresh machine verify the artifact bundle without depending on one
  developer's local drive?
- Which checks are covered by hosted CI, which require target/self-hosted CI,
  and which are currently manual receipts?
- Are historical experiments separated from the small, reviewable production
  path?

## Execution Rules

- Use `/Volumes/OWC_8TB/gpr_work` for large artifacts, temporary files, target
  receipts, dashboards, and media generated while pursuing this goal.
- Keep bulky generated media out of the repository; commit compact receipts,
  manifests, checksums, docs, tests, and source changes.
- Clean temporary artifacts after each major run unless they are referenced by a
  manifest or receipt.
- Do not register or claim production readiness unless the evidence supports it.
- Do not stop at intermediate pass-rate improvements, partial docs, or hosted CI
  alone.
- Keep active work on the 8TB drive. Use `/Volumes/OWC_8TB/gpr_work` for
  generated media, Pi receipts, dashboards, scratch builds, and temporary files.
- Keep the repository small: source, tests, scripts, compact JSON receipts,
  manifests, checksums, and docs are commit candidates; bulky media and
  generated artifacts are external bundle contents.

## Current Priority

The immediate blocker has moved from Pi-only throughput to camera-hardware
handoff evidence. The latest strict Pi 5 receipt proves valid `.gvid` output,
zero dropped frames, and interrupted tail recovery at 19.98 fps median, which
is acceptable as a conservative 20 fps proxy for advancing Labs integration.
Actual Mission 1 firmware readiness still requires a camera-role receipt from
the real sensor/DMA or camera ring-buffer source, storage writer, and rear
display at the accepted 20+ fps floor. Strict 24 fps is stretch performance
research unless the product target is raised again.
The corrected pixel-format direct `.gvid` receipt at commit `e16357f` is a
short 19.85 fps probe and keeps Pass1/channel-unpack as the known compute
hotspot if the camera path is still slow.

Current evidence says Pass1 unpack dominates the runtime. Producer unpack with
decimated capture is now guarded to avoid unsafe buffer writes, but that guard
does not recover enough frame rate by itself. Later lazy scratch allocation,
manual prefetch, LUT unroll, and luma-pair shared-unpack probes did not clear
the target. The best short direct-container near-miss is 23.54 fps median with
luma-pair plus stripe64/deferred rANS, still below the 24 fps target. A later
channel0-to-channel3 luma handoff implementation was byte-identical locally but
regressed to 12.05 fps on the Pi, so cross-channel row handoff is rejected.
Next optimization attempts must preserve row/channel parallelism, prove
byte-level output equivalence, or document intentional differences.

## Milestones

### 1. Define Labs Scope

Deliverable: `docs/LABS_INTAKE.md`

Lock the proposed Labs feature:

- In scope: half-res raw capture to `.gvid`.
- In scope: desktop unpack/review/ProRes path.
- In scope: bounded 2K live/camera-back preview evidence.
- Out of scope for this intake: full 4K/8K live preview.
- Out of scope for this intake: direct production firmware merge.
- Out of scope for this intake: arbitrary per-tile model routing in firmware.

Acceptance:

- One-page what-ships / what-does-not-ship table.
- Clear go/no-go recommendation for Labs prototype exploration.
- Links to current receipts, dashboards, release manifest, and CI.

### 2. Define Firmware Integration Contract

Deliverable: `docs/LABS_FIRMWARE_API.md` and/or a small C header.

Specify the firmware-facing contract:

- input frame buffer layout,
- Bayer format and bit depth,
- dimensions and stride,
- encoder state lifetime,
- memory ownership,
- output callback or writer interface,
- metadata fields,
- frame index and timestamp handling,
- backpressure behavior,
- dropped-frame policy,
- partial-file recovery policy.

Acceptance:

- API is documented without depending on Python.
- A fake-frame C harness can feed frames and produce deterministic `.gvid`.
- Memory budget is stated.

### 3. Harden `.gvid` For Firmware

Deliverables:

- stricter C validation in `.gvid` reader/writer,
- malformed-file tests,
- fuzz or deterministic negative-test target.
- whole-stream C validation for payload bounds, frame-count hints, and
  monotonic frame tags.

Validation should enforce:

- magic/version,
- reserved fields,
- supported flags,
- sane dimensions,
- sane fps,
- valid pixel format,
- valid quality level,
- frame-count consistency,
- payload offset/size bounds,
- monotonic frame indices/tags,
- truncated file behavior,
- duplicate or out-of-order frame behavior.

Acceptance:

- C tests cover valid and malformed `.gvid`.
- Python tooling is no longer the only safety boundary.
- Hosted CI runs the cheap validation tests.

### 4. Produce Target Hardware Evidence

Deliverable: `docs/LABS_TARGET_BENCH.md`

Measure a target-style run. If actual camera hardware is unavailable, use Pi 5
as the explicit stand-in and mark the gap.

Capture:

- sustained 10+ minute run,
- fps median/p95/p99,
- encode ms/frame,
- write MB/s,
- max RSS or heap,
- CPU utilization,
- temperature over time,
- dropped frames,
- output file validity,
- post-run decode/checksum.

Acceptance:

- `.gvid` capture sustains target fps for the full run or the blocker is named.
- No unbounded memory growth.
- Files remain readable after normal stop and simulated interruption.
- Receipts are compact and committed or indexed; bulky media stays external.

### 5. Package Portable Labs Artifacts

Deliverable: `docs/LABS_ARTIFACT_BUNDLE.md`

Define a review bundle independent of a personal external drive:

- sample `.gvid`,
- source metadata,
- ProRes review MOV,
- dashboards,
- strict artifact manifest,
- model/checkpoint hashes where needed,
- scripts to verify the bundle.

Acceptance:

- A fresh machine can verify the bundle.
- Checksums are listed.
- Missing artifacts fail with clear instructions.

### 6. Add Labs CI Coverage

Deliverables:

- hosted CI coverage for `.gvid` C validation and manifest checks,
- documented self-hosted target lane for media/runtime behavior.

Self-hosted or target CI should cover:

- real `.gvid` sample decode,
- `gpr2prores` review path,
- sustained playback/render smoke,
- artifact bundle verification,
- target hardware capture bench when available.

Acceptance:

- Hosted CI proves source-level safety.
- Target/self-hosted CI proves media/runtime behavior.
- Skips are explicit and do not masquerade as passes.

### 7. Reconcile Intake Docs

Deliverable: docs cleanup PR.

Clean up stale or conflicting numbers:

- reconcile historical `3.5 MB/frame / 84 MB/s` Pi notes with the current
  `1.30 MB/frame / 31 MB/s` half-res path,
- mark old measurements as historical where they remain useful,
- keep README as a media overview,
- keep `docs/RELEASE_READINESS.md` as production proof,
- make `docs/LABS_INTAKE.md` the Labs entry point.

Acceptance:

- A reviewer can read one Labs doc and understand current state.
- No stale performance number appears without context.

### 8. Write Labs Readiness Review

Deliverable: `docs/LABS_READINESS_REVIEW.md`

Summarize the readiness decision in one place:

- what is ready now,
- what is not ready,
- current performance blocker,
- artifact bundle status,
- CI status,
- target hardware gaps,
- next required evidence.

Acceptance:

- The review links to the intake doc, target bench, artifact bundle, firmware
  API, CI plan, and Pi regression note.
- Any no-go item is backed by a receipt, failed run, or explicit missing
  hardware integration step.

## Burn-Down Order

1. Keep CI green on `master` and preserve the small Labs path.
2. Finish the active Pi half-res throughput investigation:
   - capture timing receipts for each candidate,
   - reject slow or unsafe variants,
   - commit only source changes that are correct, tested, and justified.
3. Treat the strict 19.98 fps Pi receipt as proxy-acceptable, then prove
   sustained half-res capture at >= 24 fps on actual Mission 1 hardware or
   document the precise bottleneck that blocks it.
4. Refresh `docs/LABS_TARGET_BENCH.md`,
   `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md`, and
   `docs/LABS_READINESS_REVIEW.md` with the final receipt paths and hashes.
5. Package the portable Labs artifact bundle and verify it from its manifest.
6. Confirm `.gvid` C validation, negative tests, release evidence checks,
   artifact hygiene checks, and sensitive-content checks pass locally and in CI.
7. Re-check the README as a media overview and keep detailed proof in linked
   docs.

Final review should answer:

- What is ready for a Labs prototype?
- What is not ready for firmware merge?
- What hardware evidence exists?
- What safety/failure-mode evidence exists?
- What artifacts are required?
- What risks remain?

Expected recommendation shape:

- Go: Labs prototype exploration for `.gvid` half-res raw capture plus desktop
  review tooling.
- No-go: direct firmware merge until actual camera hardware integration and
  thermal/storage validation are complete.

## Current Objective

Burn down the remaining GoPro Labs intake concerns until the repository is
reviewable as a firmware-adjacent prototype package. The reviewer should be
able to answer four questions from committed source, docs, CI, and compact
receipts:

1. What would be integrated into firmware, and what remains desktop-only?
2. Does `.gvid` fail safely under malformed, truncated, interrupted, or
   out-of-order stream conditions?
3. Does the target-style capture path sustain the required frame rate, storage
   bandwidth, memory use, and recovery behavior?
4. Can a reviewer reproduce the proof bundle without relying on local machine
   state or personal external-drive paths?

## Current Blocker

The active production blocker is now the actual Mission 1 capture handoff and
camera-role receipt at the accepted 20+ fps floor. The current native
12MP/4K Pi stand-in closure has the release-facing receipt; the older
highpass-preserving half-res Pi stand-in remains diagnostic context with a
strict proxy-acceptable receipt plus several probes:

- latest strict sustained receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json`
- latest committed direct-container receipt support: commit
  `be969d1aa40116992694439d6abbb99c0fd59e3b`
- latest direct `.gvid` probe receipt:
  `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_default_nodrop_120f_ede0e07_20260615/labs_target_bench.json`
- current-head direct `.gvid` rehearsal receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_direct_1440f_1b934a4_20260615/labs_target_bench.json`
- current-head timing-detail receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_timing_detail_30f_1b934a4_20260615/labs_target_bench.json`

Strict sustained result:

- commit: `0dd6660ca478ac9892b014559d3444853663c54b`
- result: 14,400 requested frames, 14,400 written frames, 0 drops
- median frame time: 50.04 ms
- median throughput: 19.98 fps
- p95 frame time: 66.01 ms

Earlier direct `.gvid` default short-probe result:

- commit: `ede0e078eae4a5643efd24b1a6a5ebec4844a826`
- mode: `--direct-gvid`, default LUT path, highpass-preserving no-drop path
- result: 120 requested frames, 120 written frames, valid `.gvid`
- median frame time: 46.83 ms
- median throughput: 21.36 fps
- p95 frame time: 49.44 ms
- timing detail: Pass1 mean 37.45 ms; channel-unpack mean 22.37 ms across
  channel workers

Current-head direct `.gvid` rehearsal result:

- commit: `1b934a41e0e9dee8f2189e67442e310ed6aa866a`
- mode: `--direct-gvid`, default LUT path, highpass-preserving no-drop path
- result: 1,440 requested frames, 1,440 written frames, valid `.gvid`,
  interrupted-tail recovery proven
- median frame time: 62.48 ms
- median throughput: 16.00 fps
- p95 frame time: 73.21 ms
- target state: performance governor, 2.4 GHz, `throttled=0x0`, SSD ext4
  `rw,noatime,stripe=8191`
- timing detail: Pass1 median 38.90 ms; Pass2 median 9.20 ms; channel-unpack
  mean 22.79 ms

Direct `.gvid` polynomial diagnostic result:

- commit: `be969d1aa40116992694439d6abbb99c0fd59e3b`
- mode: `--direct-gvid`, `FUSED_LOG_POLYNOMIAL=ON`, highpass-preserving
  no-drop path
- result: 120 requested frames, 120 written frames, valid `.gvid`
- median frame time: 74.71 ms
- median throughput: 13.39 fps
- p95 frame time: 86.88 ms

The direct-container receipts improve measurement fidelity but do not solve
camera-hardware readiness. The current-head default path is far better than the
polynomial diagnostic but still below 24 fps. Current, historical-document,
environment,
runtime-knob, and timing probes do not reproduce the 24.93 fps result. The
best current-build knob reaches roughly 22-23 fps on short probes, while the
strict 10-minute receipt remains 19.98 fps median and the current-head
1,440-frame direct-container rehearsal is 16.00 fps median. Timing detail shows
multi-level Pass1 dominates, with channel unpack as the largest measured
component. The invalid producer+decimate combination was removed rather than
kept as a supported mode, and a fresh decimation-aware producer scratch probe
was rejected by Pi 5 full-frame timing. A 2026-06-15 search found
no separate
recoverable `be0328a` downstream source tree on the consolidated 8TB work
area; the archived branch only contains the stale polynomial-comment delta for
the codec. Polynomial-log, u16 log-scratch, prescale-2 fixed-shift, and
identity-quant shortcut probes were byte-safe or documented but did not recover
24 fps. A productionizable channel0-to-channel3 luma handoff candidate also
regressed badly on Pi because the row handoff lost channel parallelism. Further
Pi hot-path work should resume only if the camera receipt shows compute remains
the blocker; otherwise the next engineering task is the firmware handoff,
portable bundle, and target/self-hosted CI evidence.

## Immediate Next Step

Package the current proxy-acceptable Pi evidence into the portable Labs bundle
and run or document the actual camera-hardware handoff receipt. Treat the May
26 24.93 fps result as non-reproducible until a real source tree or target
receipt proves otherwise. If Mission 1 capture misses 24 fps, use the existing
timing-detail receipt shape to decide whether the fix is in-worker
Pass1/highpass reduction, row-sharded shared work that avoids channel waiting,
a different capture-side algorithm, or the firmware storage/sensor path.
