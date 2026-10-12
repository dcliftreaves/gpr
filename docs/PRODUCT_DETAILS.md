# Product Details

## Supported workflows

| Product area | Current scope | Boundary |
|---|---|---|
| Raw stills | Legacy VC5 DNG/GPR conversion; q0 smallest, q3 primary, q8 archival tiers | CNN-assisted tiers require separately supplied matched models |
| Raw video | FUSED frame encoding and `.gvid` packaging; native Mission 1 4096 x 3072 Bayer target | Pi 5 stand-in clears the accepted 20+ fps floor; camera production remains unproven |
| Camera-back preview | Full-frame 1024 x 768 RGB decoded from the same 4K stream | No camera-side CNN; actual rear-display integration remains open |
| Raw-video reconstruction | Approved offline 4K cleanup and 8K SR, editable DNG/GPR packaging and ProRes review | Desktop/post scope; review frame rate is not processing throughput |
| Premium still SR | Separate work on detail, noise, and editing latitude | Research, not a promoted replacement for approved video reconstruction |

The live FUSED/`.gvid` interface supports unpacked RGGB and GBRG at
12/14/16 bits, pixel-format tags `0..5`. The standard stills path separately
supports normal unpacked RGGB/GBRG/GRBG/BGGR. Do not infer live-video four-phase
support from stills support. Raw dimensions describe Bayer samples; rendered
UHD, 4K, or 8K output dimensions depend on the selected export mode.

## Noise and editing

Camera-noise sidecars must describe their source camera, ISO/exposure,
calibration provenance, units, and validation status. A sidecar schema pass
does not prove physical sensor-noise calibration. Mission 1/iPhone
camera-specific noise closure remains separate from ordinary codec support.

Preserve source metadata and Bayer phase through reconstruction and packaging.
A high Bayer PSNR or an editable DNG does not prove unchanged texture,
noise, color, or exposure latitude. Use the matching raw and rendered gates,
plus editor review, before promoting a model or noise policy.

## Evidence and delivery

[Ship Decision](SHIP_DECISION.md) defines the approved boundary;
[Video Status](VIDEO_STATUS.md) records the selected stand-in measurements.
[Reconstruction](RECONSTRUCTION.md) explains model availability.
[Release Artifacts](RELEASE_ARTIFACTS.md) defines what an external reviewer
needs to reproduce and inspect a release.

The [archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09)
at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef)
contains prior scorecards, calibration reports, and experiment history.
