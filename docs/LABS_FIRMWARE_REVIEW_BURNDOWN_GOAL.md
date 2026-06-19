# Labs Firmware Review Burn-Down Goal

Last updated: 2026-06-15.

This is the concrete burn-down goal for making GPR reviewable by a firmware and
media engineer as a Labs-style camera prototype. It complements
`LABS_READINESS_GOAL.md`, which remains the active session stop-criteria
contract.

## Goal

Make GPR credible as a camera-firmware Labs prototype for `.gvid` half-res raw
capture plus desktop review/export. The repo should let a reviewer determine
what ships, how firmware would integrate it, how the container fails safely,
whether the target path can meet frame-rate and storage requirements, and how to
reproduce the proof without relying on one developer's local machine.

## Stop Criteria

Stop only when one of these is true:

1. The Labs intake package is complete and reviewable.
   - `LABS_INTAKE.md` clearly states what ships and what is out of scope.
   - `LABS_FIRMWARE_API.md` defines the firmware-facing frame input, encoder
     state, memory ownership, timestamps, metadata, output ownership,
     backpressure, dropped-frame behavior, and partial-file recovery contract.
   - `.gvid` C reader/writer validation includes positive and negative tests for
     malformed headers, truncated payloads, dimension mismatches, frame-count
     errors, checksum or receipt mismatches, and recovery from interrupted
     writes.
   - Target-style receipts exist for sustained encode/decode, RSS, storage
     bandwidth, dropped frames, and interrupted-file recovery.
   - Artifact bundle docs make sample media, dashboards, receipts, checksums,
     and model or checkpoint hashes portable outside `/Volumes/OWC_8TB`.
   - Hosted CI covers source-level checks, and target/self-hosted lanes are
     specified for Pi 5 or Mission 1 behavior that hosted CI cannot exercise.
   - The top-level README stays sharp and media-forward, while proof details
     live in linked docs.

2. Labs readiness is objectively blocked with evidence.
   - The blocker is narrowed to missing target hardware access, missing
     sensor/DMA integration, thermal/power/storage infeasibility, an incompatible
     `.gvid` design issue, artifact portability failure, or CI/build
     infrastructure limits.
   - The blocker has committed metrics, receipts, logs, or test output, plus a
     concrete next action.

Do not stop because one optimization lands, hosted CI passes, a dashboard looks
better, or a single receipt is green. The stop condition is a reviewable intake
package or a specific evidenced blocker.

## Current Evidence State

The current Pi 5 stand-in path writes valid `.gvid`, preserves interruption
recovery, and avoids dropped frames in the strict direct-container receipt, but
it does not yet hit the 24 fps target. The active blocker is compute time in the
highpass-preserving half-res path, especially Pass1/channel-unpack work.
Producer-unpack and shared-unpack scratch probes regressed on full-frame Pi 5
timing and have been removed from the production source. A manual col-decimate
prefetch probe also regressed, which keeps the focus on reducing the
unpack/LUT work itself rather than cache hints around the current loop shape.
Manual unrolling of the active 8-entry LUT copy loops was also byte-identical
but slower. A luma-pair shared-unpack scratch candidate improved the best short
direct-container run to 42.48 ms / 23.54 fps only when combined with
stripe64/deferred rANS, but it still missed the 24 fps target and was not
committed.

The next production step is to remove more Pass1/channel-unpack or
tokenization work without row-handoff overhead, or replace that capture-side
algorithm with one that keeps the quality guarantees while meeting target
throughput.

## Burn-Down Workstreams

1. Throughput
   - Keep measuring the real direct `.gvid` target path, not diagnostic-only
     variants.
   - Capture median, p95, sustained fps, dropped frames, RSS, and storage
     bandwidth for every candidate.
   - Treat 24 fps on the Pi 5 or Mission 1 stand-in as the hard gate for the
     capture path.

2. Container safety
   - Harden `.gvid` C read/write paths with malformed-input and interrupted-file
     tests.
   - Keep receipts small and committed; keep large media external and
     checksummed.

3. Firmware integration
   - Keep the API contract explicit about buffers, strides, bit depth, Bayer
     phase, timestamps, metadata, ownership, backpressure, dropped frames, and
     recovery.
   - Separate prototype boundaries from any future sensor/DMA integration.

4. Artifact portability
   - Every dashboard, sample, receipt, and review output referenced by docs
     needs a manifest entry, checksum, and external storage path.
   - Local-only absolute paths are allowed in receipts only when paired with a
     portable manifest path or reproduction instructions.

5. CI and review hygiene
   - Keep hosted CI green on pushed `master`.
   - Keep heavyweight target runs documented as manual or self-hosted lanes until
     they can be automated.
   - Keep historical experiments summarized in docs instead of committing bulky
     artifacts to the main branch.

## Execution Rules

- Use `/Volumes/OWC_8TB/gpr_work` for generated media, target receipts,
  dashboards, scratch builds, and temporary files.
- Set `TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp` for large runs.
- Clean up temporary artifacts after each major run unless they are referenced by
  a receipt or manifest.
- Commit source, tests, docs, compact JSON receipts, manifests, and checksums.
- Do not claim production readiness unless the evidence supports it.
