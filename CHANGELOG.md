# Changelog

## Unreleased

- Consolidated current product, build/use, format, hardware, performance,
  reconstruction, and release documentation into a compact guide set.
- Archived superseded experiment reports, work queues, and device-specific
  iteration histories. Preserved audited quality signoffs and format details.
- Documentation examples use repository-relative inputs and user-selected
  artifact/model directories.

No new quality or performance measurements are claimed by this cleanup.
The accepted Pi 5 floor remains 20+ fps for native 4096 x 3072 capture and
full-frame 1024 x 768 preview. Actual camera sensor/DMA, storage, and display
handoff remain unproven. CNN reconstruction runs offline on desktop hardware.

## 2.3.1 - 2026-06-26

Added release-bundle, Labs/plugin handoff, and `.gvid` conformance contracts,
with corresponding validation tooling.

## 2.3.0 - 2026-06-26

Introduced the current raw-video product surface: `.gvid` capture,
native Mission 1 4K Bayer stand-in evidence, full-frame 1024 preview,
offline 4K cleanup and 8K SR, editable raw packaging, ProRes review,
and firmware handoff receipts. Camera production was not established.

## 2.2.0 - 2026-05-30

Added the historical UPRESABLE half-resolution capture-to-editable-raw
workflow and its Bayer-domain gate. Its timing and rendered quality evidence
must not be substituted for the current native-4K capture target.

## 2.0.0 - 2026-05-12

Extended the legacy GPR codec with ANS entropy coding and noise-aware
processing, and added raw-video encoding and desktop integration work.

## 1.0.x

Original GoPro GPR SDK and VC5 raw still support.

## Full history

Detailed release notes and the full research/integration history are preserved
in the [archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/blob/3d675ef/CHANGELOG.md).
See [Product Details](docs/PRODUCT_DETAILS.md) and
[Ship Decision](docs/SHIP_DECISION.md) for current scope.
