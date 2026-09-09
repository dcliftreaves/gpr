# Reconstruction and Model Availability

Approved raw-video reconstruction consists of offline 4K cleanup and 8K
super-resolution on desktop hardware. It can produce editable Bayer DNG/GPR
outputs and ProRes review media. It does not run on the camera and does not
establish real-time 8K processing.

## What is available

The checkout contains codec and reconstruction integration code, pipeline
definitions, and evidence references. Trained checkpoints, exported model
blobs, large camera fixtures, and full review movies are external artifacts.
A registry entry or archived receipt is not a downloadable model package;
this documentation does not establish a public weight download.

Without a matching model package, use the codec-only `--no-cnn` review
command in [Getting Started](GETTING_STARTED.md). Do not substitute arbitrary
weights and carry over the approved pipeline's quality claim.

## Model package contract

A reproducible model delivery must include:

- Checkpoint/export hashes, model identity, license, and source provenance.
- Architecture and backend/export version, expected Bayer phase and bit depth,
  normalization, codec profile, scale, and supported dimensions.
- Preprocessing, tiling/overlap, metadata, and color/render settings.
- Matched source/output evidence, quality receipt, timing and peak-memory
  receipt, editable-packaging checks, and review assets.

The historical F and BIBO family names alone do not identify an approved
Mission 1 candidate. Select the exact codec/model pairing from the evidence
and pipeline definitions. A raw gate, rendered gate, and editor-latitude test
measure different outcomes.

## Desktop integration example

For a supplied compatible Metal 1x model package and matching source metadata:

```bash
tools/gpr2prores/gpr2prores \
  --meta-dng data/sample.dng \
  --ckpt "${GPR_MODEL_ROOT:?Set the matching exported model directory}" \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  "$GPR_ARTIFACT_ROOT/clip.gvid" "$GPR_ARTIFACT_ROOT/cleanup-review.mov"
```

This illustrates the CLI integration, not reproduction of a locked receipt.
Use `--cnn-scale 2x --out-resolution 8k` only with a compatible 2x export.
Choose `GPR_ARTIFACT_ROOT` as described in the quickstart. Review media is
rendered output; editable raw requires the matching raw packaging workflow
and metadata validation.

## Approval boundary

The existing approved 4K/8K video baselines remain frozen under
[Ship Decision](SHIP_DECISION.md). The
[compact release evidence index](release_evidence.json) identifies
existing receipts and review artifacts. No new quality or speed measurements
were produced by the documentation cleanup.

Artifact paths in that index are relative to the user-selected
`GPR_EXTERNAL_ROOT`. This locates existing evidence; `GPR_ARTIFACT_ROOT`
in the quickstart chooses where new local outputs are written. Set each
explicitly for the workflow rather than assuming a shared filesystem layout.

[Premium Still SR](PREMIUM_STILL_SR.md) is a separate research track.
Historical model comparisons, private artifact inventories, and training
iterations are in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
