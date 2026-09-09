# Release Artifacts

A source checkout alone is not a reproducible model-backed product release.
Deliver a compact, hash-verifiable review bundle for the exact release commit,
with explicit stand-in, offline-only, research, and camera-handoff-open labels.

## Bundle contents

| Area | Required material |
|---|---|
| Identity | Source commit, matching CI run URL, build/platform information |
| Samples | Real decode-checked 4K Bayer `.gvid` and matching metadata sidecar |
| Review | Compact preview/contact-sheet assets that open without project tools |
| Receipts | Evidence manifest, stream validation, target timing, and applicable handoff/preview receipts |
| Integrity | Manifest and checksums covering bundled artifacts |
| Model-backed reproduction | Exact model/export identity, hashes, availability, license, and preprocessing contract |

Synthetic samples are suitable for labeled conformance bundles, not as
substitutes for real camera quality evidence. Keep large movies, checkpoints,
and datasets outside git, with retrievable artifact references and hashes in
the distributed bundle. An old local receipt does not prove those artifacts
are publicly available.

Expose four product labels: RAW stills, RAW video MVP, premium still/SR
research, and RAW video reconstruction. Premium still/SR and optional PSF
replacement research must remain distinct from approved offline 4K/8K video
reconstruction. Use [Product Details](PRODUCT_DETAILS.md) for scope.

## Build and verify a manifest

Stage the actual files under your chosen `GPR_ARTIFACT_ROOT/review-bundle`.
The example assumes `samples/sample_4k_bayer.gvid`, its sidecar,
`review/preview_1024.webp`, and the listed receipts already exist there.

```bash
python3 tools/build_labs_bundle.py "$GPR_ARTIFACT_ROOT/review-bundle" \
  --repo-commit "$(git rev-parse HEAD)" \
  --ci-run "${GPR_CI_RUN_URL:?Set the CI URL for this source commit}" \
  --target-name "Pi 5 stand-in" --target-role stand-in \
  --no-product-pillars \
  --note "Pi stand-in evidence only; camera sensor, storage, and display handoff remain open" \
  --artifact samples/sample_4k_bayer.gvid:gvid \
  --artifact samples/sample_4k_bayer.gvid.meta.json:json \
  --artifact review/preview_1024.webp:media \
  --artifact receipts/release_evidence.json:json \
  --artifact receipts/labs_target_bench.json:json
python3 tools/verify_labs_bundle.py "$GPR_ARTIFACT_ROOT/review-bundle/manifest.json"
```

The tools use `gpr_labs_bundle.v1`. The compact release evidence file is
included as an artifact; `--no-product-pillars` avoids treating it as the
older product-pillar manifest schema. Keep the four scope labels in the
bundle README and notes. Verify checksums, decode the sample, and
inspect scope labels before distributing the bundle. Source identity must
match the commit that produced or verified its artifacts; do not substitute
a newer commit for an older receipt.

## Camera and model delivery

Include the firmware-facing API, validation instructions, capability
information, and capture requirements in a camera handoff package.
Camera production still requires actual camera-role sensor/DMA, storage,
and full-frame 1024 x 768 display receipts at the accepted 20+ fps floor.
A stand-in bundle can support firmware review without proving that readiness.

[Reconstruction](RECONSTRUCTION.md) defines model-package requirements.
[Ship Decision](SHIP_DECISION.md) defines promotion boundaries.
Prior inventories and release-specific launch histories are in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
