# Release Artifacts

Last refreshed: 2026-07-01

This document defines what must be attached to a GitHub release before the
release is useful to someone outside the worktree. Source tags and changelog
notes are not enough; a product release needs verifiable inputs, review media,
receipts, and checksums.

## Required Release Bundle

Each production release should have a compact bundle named:

```text
gpr-<version>-review-bundle/
  README.md
  manifest.json
  samples/
    sample_4k_bayer.gvid
    sample_4k_bayer.gvid.meta.json
  review/
    preview_1024.webp
    prores_contact_sheet.jpg
  receipts/
    ci_run.txt
    release_evidence_manifest.json
    mission1_numbered_list_readiness.json
    gvid_validate.txt
    labs_target_bench.json
  hashes/
    sha256sums.txt
```

The bundle may also include platform binaries when they are available, but the
minimum release bundle is source-portable and verifier-friendly. Large movies,
dashboards, checkpoints, and long-run receipts remain outside git and are
referenced by hash from `docs/release_evidence_manifest.json` and
`docs/PRODUCTION_ARTIFACTS.md`.

## Release Bundle Rules

| area | requirement |
|---|---|
| Source identity | `repo_commit` must match the release tag commit. |
| CI identity | `ci_run` must be a GitHub Actions URL for the tagged commit or the merge commit that produced it. |
| Samples | Include at least one readable `.gvid` sample plus matching metadata sidecar. Synthetic samples are allowed only for conformance bundles and must be labeled synthetic in `README.md`. |
| Review media | Include a compact visual review asset that opens without project tooling. |
| Receipts | Include the release evidence manifest, `.gvid` validation output, and at least one target or stand-in timing receipt. |
| Checksums | Every bundle file except the manifest itself must be listed in `hashes/sha256sums.txt`. |
| Scope labels | Stand-in, offline-only, and camera-handoff-open evidence must stay labeled that way in the bundle README and manifest notes. |
| Product-pillar labels | Bundle README and manifest notes must map artifacts to RAW stills, RAW video MVP, premium still/SR, and RAW video reconstruction. Use `docs/release_evidence_manifest.json.product_pillars` as the source of truth. PSF-aware replacement artifacts are research references unless they later replace the approved baseline. |

## Product Pillar Labels

Every release bundle should expose the same four-pillar map used by the README
and product scorecards:

- **RAW stills**: production still tiers, bit-depth support, real 50 MP / 100
  MP-class compatibility evidence, Bayer phase coverage, and validated
  noise-sidecar policy.
- **RAW video MVP**: `.gvid` Bayer recompression, camera-back preview,
  MOV/ProRes review, editable DNG/GPR export, Mission 1 handoff/timing
  receipts, and the production capture requirements that define camera-role
  closure.
- **Premium still/SR**: spend-time-for-quality still/SR targets, model
  receipts, dashboards, and explicit non-promotion blockers.
- **RAW video reconstruction**: approved 4K cleanup and offline 8K SR baselines,
  continuous 8K no-CNN versus CNN review media, editable raw packaging, and
  optional PSF research evidence for a future replacement.

The release manifest's `product_pillars` section owns this mapping.
`tools/build_labs_bundle.py` copies that section into generated bundle
manifests by default, and `tools/verify_labs_bundle.py` rejects malformed
pillar metadata when it is present. Release README prose can be shorter, but it
must keep these labels visible so reviewers can tell what each artifact proves
without reverse-engineering IDs.

Mission 1 handoff bundles built by
`tools/build_gopro_mission1_handoff_bundle.py` must also package
`docs/PRODUCTION_CAPTURE_REQUIREMENTS.md` and
`docs/PRODUCTION_CAPTURE_REQUIREMENTS.json`, and the intake audit treats those
files as required firmware-facing docs.

## Build And Verify

The existing Labs bundle tools are the release-bundle manifest mechanism. Use
the same `gpr_labs_bundle.v1` schema so Labs intake and GitHub release assets
are checked by one verifier:

```bash
python3 tools/build_labs_bundle.py /path/to/gpr-<version>-review-bundle \
  --repo-commit "$(git rev-parse v<version>)" \
  --ci-run "https://github.com/dcliftreaves/gpr/actions/runs/<run-id>" \
  --target-name "Pi 5 stand-in" \
  --target-role stand-in \
  --product-pillars-from docs/release_evidence_manifest.json \
  --note "Mission 1 camera handoff remains open; Pi stand-in receipts prove the current 20+ fps floor" \
  --artifact samples/sample_4k_bayer.gvid:gvid \
  --artifact samples/sample_4k_bayer.gvid.meta.json:json \
  --artifact review/preview_1024.webp:media \
  --artifact receipts/release_evidence_manifest.json:json \
  --artifact receipts/labs_target_bench.json:json

python3 tools/verify_labs_bundle.py /path/to/gpr-<version>-review-bundle/manifest.json
(cd /path/to/gpr-<version>-review-bundle && shasum -a 256 -c hashes/sha256sums.txt)
```

For the Mission 1 firmware handoff specifically, use the narrower builder:

```bash
python3 tools/build_gopro_mission1_handoff_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_handoff_bundle_current \
  --force \
  --ci-run "https://github.com/dcliftreaves/gpr/actions/runs/<run-id>" \
  --fused-decode-cli build-local/bin/fused_decode_cli \
  --require-sample-decode

python3 tools/verify_labs_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_handoff_bundle_current/manifest.json
```

That bundle is meant for firmware reviewers. It includes the GoPro quick
validation command, one decode-checked 4K `.gvid` sample, compact stand-in receipts, a
quick-validation dry-run receipt, visual review assets, and the relevant docs.
It must still be replaced or supplemented by camera-role receipts before
production readiness is claimed.

Attach the verified archive to the release:

```bash
tar -C /path/to -czf /path/to/gpr-<version>-review-bundle.tar.gz gpr-<version>-review-bundle
gh release upload v<version> /path/to/gpr-<version>-review-bundle.tar.gz --repo dcliftreaves/gpr
```

## Current Status

The published `v2.3.1` release is older than current `master`; do not move that
tag. Cut the next public release from the current commit after CI passes, then
attach a verified review bundle built from the same commit.

Current verified CI-backed Mission 1 handoff bundle for commit `041f53e`:

`/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_handoff_bundle_current_master_20260701/manifest.json`

Current verified CI-backed archive for commit `041f53e`:

`/Volumes/OWC_8TB/gpr_work/artifacts/gpr-current-master-mission1-handoff-bundle-20260701.tar.gz`

Current CI receipt:

`https://github.com/dcliftreaves/gpr/actions/runs/28519825322`

Archive SHA-256:

`e56f021ac4de0f4d83cd9235aa846e7d9ecf176afeb4881d374dd5dfd23c1bc7`

Current Mission 1 intake audit:

`/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html`

The CI-backed `041f53e` bundle verifies with `tools/verify_labs_bundle.py` and
contains 21 manifest artifacts, including a decode-checked 4096 x 3072 `.gvid`
sample, compact stand-in closure receipts, the quick-validation dry-run receipt,
visual assets, docs, current product-pillar labels, and checksums. The intake
audit marks the handoff firmware-review ready, but still
`camera_production_ready=false` until camera-role sensor/DMA, storage, and
rear-display receipts replace the stand-in evidence.
