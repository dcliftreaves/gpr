# Documentation

GPR provides compact raw stills, a raw-video container and capture prototype,
and desktop reconstruction tools. Start with [Getting Started](GETTING_STARTED.md)
and [Product Details](PRODUCT_DETAILS.md).

| Topic | Guide |
|---|---|
| Current scope and limitations | [Product Details](PRODUCT_DETAILS.md) |
| Build, still conversion, and video review | [Getting Started](GETTING_STARTED.md) |
| Capture, preview, and recorded Pi evidence | [Video Status](VIDEO_STATUS.md) |
| Approved pipelines and release boundary | [Ship Decision](SHIP_DECISION.md) |
| Audited quality signoffs | [Claims Log](claims_log.md) |
| Architecture and API map | [Architecture](architecture.md) |
| FUSED payload specification | [Bitstream Specification](SPEC.md) |
| Legacy DNG/GPR extensions | [Format Specification v2](format-spec-v2.md) |
| Raw-video wire contract and metadata | [GVID Conformance](GVID_CONFORMANCE.md) |
| Firmware ownership and handoff | [Labs Firmware API](LABS_FIRMWARE_API.md) |
| Camera validation procedure | [Mission 1 Quick Validation](GOPRO_MISSION1_QUICK_VALIDATION.md) |
| Pi setup and storage measurement | [Pi Hardware](PI_HARDWARE.md) |
| Recorded still encode timings | [Stills Pi 5 Timing](STILLS_PI5_TIMING.md) |
| Model availability and offline reconstruction | [Reconstruction](RECONSTRUCTION.md) |
| Separate still-SR research boundary | [Premium Still SR](PREMIUM_STILL_SR.md) |
| Evidence and verification methodology | [Testing Methodology](TESTING_METHODOLOGY.md) |
| Review bundles and release requirements | [Release Artifacts](RELEASE_ARTIFACTS.md) |

## Research archive

Iteration reports, superseded targets, tuning experiments, and integration work
queues are preserved in the
[full research and integration archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
The archive preserves provenance; its historical targets are not current
product promises. Large external datasets, model weights, and review movies
are not made available merely by linking the source archive.

The cleanup introduces no new performance or quality measurements. The
[compact release evidence index](release_evidence.json) and retained
signoffs identify existing evidence.
