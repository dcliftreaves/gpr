# Labs Firmware Intake Goal

## Objective

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
     memory ownership, metadata, container output, backpressure, dropped frames,
     and partial-file recovery.
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
Labs intake evidence, not merely repo cleanliness.

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

The latest strict Pi 5 stand-in target receipt proves `.gvid` validity,
zero dropped frames, and interrupted-tail recovery, but it misses the half-res
24 fps capture target:

- commit: `0dd6660ca478ac9892b014559d3444853663c54b`
- receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json`
- result: 14,400 requested frames, 14,400 written frames, 0 drops
- median frame time: 50.04 ms
- median throughput: 19.98 fps
- p95 frame time: 66.01 ms

Current, historical-document, environment, runtime-knob, and timing probes do
not reproduce the 24.93 fps result. The best current-build knob reaches
22.53 fps median on a 100-frame probe, while the strict 10-minute receipt
remains 19.98 fps median. The timing profile shows multi-level Pass1 dominates,
with channel unpack as the largest measured component. The next engineering
task is to recover the unrecovered downstream worktree or fix/optimize the
current Pass1 unpack path.

## Immediate Next Step

Recover the original downstream `be0328a` worktree if it exists. If it cannot
be recovered, treat the May 26 24.93 fps result as non-reproducible, fix or
retire the producer-unpack heap corruption, and optimize Pass1 unpack enough to
recover the missing 11-18 percent needed to clear the sustained 24 fps target.
