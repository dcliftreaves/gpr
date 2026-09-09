# Product Details And Evidence

The [main README](../README.md) introduces the workflows. This index connects
each capability to its measurements, limitations, and development history.

![GPR capture and reconstruction overview](img/readme_showcase.webp)

## Current Boundaries

The 50 MP still tiers average 9.80 MB, 15.05 MB, and 27.17 MB on the recorded
quality gate. The smaller tiers use matched restoration models. X2D 100 MP
compatibility does not mean every 100 MP scene meets those same size targets.
See [still quality](SHIP_DECISION.md) and [compatibility](LOCAL_FIXTURE_COMPATIBILITY.md).

The accepted native12 camera evaluation floor is 20+ fps on Pi 5. Real Mission 1
sensor/DMA, storage, and display integration remain open. The native 1024 x 768
preview uses no CNN. Separately, PREVIEW offline/review is a desktop model path,
not a live/camera-back preview path. See [video status](VIDEO_STATUS.md).

Approved 4K cleanup and 8K video SR retain their recorded review status. Premium
still-SR remains research; its replacement gate requires improvement without REF
content at render time. PSF/blur modeling is optional research, not a blocker
for the approved video models. Mission 1 and iPhone noise calibration still
need suitable source evidence before broad noise-addback claims are justified.

The readiness percentages below track engineering evidence, not image quality.
The [lock ledger](PRODUCT_LOCK_LEDGER.md) records approved paths independently
of experiments on their replacements.

![GPR four-pillar production readiness](img/readme_status_matrix.svg)

## Evidence Index

| Topic | Details |
|---|---|
| Stills quality and compression | [Ship decision](SHIP_DECISION.md), [capabilities](CAPABILITIES.md), [Pi stills timing](STILLS_PI5_TIMING.md) |
| Camera noise | [Calibration](CAMERA_NOISE_CALIBRATION.md), [noise work order](RAW_STILLS_NOISE_FIRST_HOUR.md) |
| RAW video and preview | [Video status](VIDEO_STATUS.md), [camera evaluation](GOPRO_MISSION1_QUICK_VALIDATION.md), [Labs intake](LABS_INTAKE.md) |
| CNN and SR | [Video reconstruction](MISSION1_CNN_NEXT_STEPS_2026-06-28.md), [premium still-SR](PREMIUM_STILL_SR.md), [next experiment](PREMIUM_STILL_SR_FIRST_HOUR.md) |
| Readiness and remaining work | [Scorecard](PRODUCT_PILLAR_SCORECARD.md), [closure matrix](GOAL_CLOSURE_MATRIX.md), [production plan](PRODUCTION_100_PERCENT_PLAN.md), [execution queue](PRODUCTION_100_PERCENT_EXECUTION_QUEUE.md) |
| Full-resolution comparisons and models | [Artifacts](PRODUCTION_ARTIFACTS.md), [workspace map](WORKSPACE_AND_ARTIFACT_MAP.md), [release manifest](release_evidence_manifest.json) |
| Format and integration contracts | [Specification](SPEC.md), [GVID conformance](GVID_CONFORMANCE.md), [capture requirements](PRODUCTION_CAPTURE_REQUIREMENTS.md), [release packaging](RELEASE_ARTIFACTS.md) |
| Release requirements | [Product contracts](PRODUCTIZATION_CONTRACTS.md), [CNN scorecard](CNN_PRODUCT_SCORECARD_2026-06-29.md) |
| How the project developed | [Production history](BIG_EFFORTS_STATUS.md), [archived experiments](EXPERIMENT_ARCHIVE_2026-06-04.md), [changelog](../CHANGELOG.md) |

Large datasets, checkpoints, and review movies live outside Git. Their paths
and hashes are recorded in the artifact index and release manifest. A normal
clone can build and run synthetic regression tests without those assets; full
model-quality verification requires them.

## Native Capture At 100 Percent

This crop sheet documents the native12 Bayer capture comparison. It complements
the smaller illustrations on the main page.

![Mission native12 100 percent crop sheet](img/readme_mission1_native12_100pct.png)

## Build And Validation

Follow [getting started](GETTING_STARTED.md) for conversion commands and the
[release readiness guide](RELEASE_READINESS.md) for regression checks. Quality
gates and production roles are defined in
[`pipelines/registry.json`](../pipelines/registry.json).

| Directory | Contents |
|---|---|
| `source/` | Native codec, SDK, command-line applications, and tests |
| `tools/gpr2prores/` | Mac rendering, Metal reconstruction, and ProRes output |
| `tools/cnn/` | Model training, evaluation, and rendering tools |
| `tools/gpraw/` | MOV wrapper tooling |
| `tests/quality_gates/` | Quality gates and committed run summaries |
| `docs/` | Specifications, runbooks, evidence, and research history |
