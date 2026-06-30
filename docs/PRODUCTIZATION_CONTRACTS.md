# Productization Contracts

Last refreshed: 2026-06-30

This page is the compact checklist for turning the four product pillars into a
production-ready suite:

1. best RAW stills for 50 MP and 100 MP cameras,
2. GoPro / Mission 1 RAW video MVP,
3. premium spend-time-for-quality still/SR,
4. PSF-aware RAW video cleanup and reconstruction.

Release artifacts, Labs/plugin handoff, `.gvid` conformance, and CNN/model
governance are the cross-cutting contracts that keep those pillars shippable.
The top-level status lives in `docs/PRODUCT_PILLAR_SCORECARD.md`, while
`docs/PRODUCT_LOCK_LEDGER.md` separates locked paths from still-open
production-readiness gates. `docs/PRODUCTION_CAPTURE_REQUIREMENTS.md` and
`docs/PRODUCTION_CAPTURE_REQUIREMENTS.json` are the committed contract for the
real fixtures, darkframes, camera receipts, controlled PSF pairs, and
model-promotion receipts still needed to close those gates.

## Current Product Boundary

| pillar | locked today | still open |
|---|---|---|
| RAW stills | 50 MP production still tiers, 12/14/16-bit support, real X2D 100 MP-class roundtrip evidence, normal Bayer parser/conformance coverage. | Real GRBG/BGGR camera fixtures and Mission 1/iPhone darkframe sidecars before nonzero noise addback can be enabled for those cameras. |
| RAW video MVP | 4096 x 3072 Bayer `.gvid` encode and 1024 x 768 preview above the accepted 20 fps Pi 5 stand-in floor, plus conformance and handoff tooling. | Real Mission 1 camera-role sensor/DMA, SD writer, and rear-display receipts. |
| Premium still/SR | Target builders, raw-CFA residual datasets, model probes, dashboards, and explicit blocker evidence. | Candidate-only 50 MP / 100 MP still-SR model that clears broad Z8/X2D holdouts, editor-latitude review, and worst-row visual gates. |
| PSF-aware video/SR | Approved 4K cleanup and offline 8K SR baselines, including continuous 8K no-CNN versus CNN ProRes review media. | Controlled Mission 1 high/low Bayer pairs, stable native PSF kernel, and a PSF-conditioned 4K/8K model that beats the current baselines. |

The detailed closure list is pinned in
`docs/PRODUCTION_CAPTURE_REQUIREMENTS.json`: `real_grbg_fixture`,
`real_bggr_fixture`, `mission1_darkframe_stack`,
`iphone_cfa_darkframe_stack`, `mission1_camera_role_receipts`,
`controlled_mission1_psf_pairs`, and
`premium_still_sr_promotion_receipts`.

The normal-Bayer support claim is deliberately split by path: the still/GPR
path covers synthetic RGGB/GBRG/GRBG/BGGR conformance today, while the live
FUSED/.gvid path remains scoped to its 0..5 RGGB/GBRG 12/14/16-bit contract
until the fused header and preview decoder grow a real four-phase contract.

## 1. Release Artifacts

Source tags are not enough. A release is externally useful only when it has a
verified review bundle with:

- `.gvid` sample plus metadata sidecar,
- compact visual review media,
- release evidence manifest and target receipts,
- checksums,
- explicit labels for stand-in, offline-only, or camera-handoff-open evidence.
- product-pillar labels for RAW stills, RAW video MVP, premium still/SR, and
  PSF-aware video/SR so reviewers can tell what each artifact proves.

Source of truth: `docs/RELEASE_ARTIFACTS.md`.

## 2. Labs / Plugin Handoff

The firmware-facing integration must stay small and stable:

- `source/lib/vc5_encoder/gpr_labs_encoder.h` is the ABI surface,
- `docs/LABS_FIRMWARE_API.md` defines lifetime, memory ownership, metadata,
  storage handoff, camera handoff receipts, preview UI receipts, install,
  rollback, and capability discovery,
- firmware readiness is accepted only from `target.role=camera` receipts with
  sensor/DMA, storage, and display handoff executed.

Pi stand-in evidence may advance integration review, but it cannot be relabeled
as camera production evidence.

The live camera path must stay CNN-free unless a future target receipt proves
otherwise. Current 4K cleanup and 8K SR CNN paths are desktop/post workflows.

## 3. `.gvid` Conformance

The `.gvid` container contract is separate from codec quality. The product
must reject malformed streams and recover only whole-frame interrupted tails.
For the raw-video MVP, `.gvid` must contain recompressed Bayer payloads, not
packed original camera files.

Source of truth: `docs/GVID_CONFORMANCE.md`.

Required checks:

```bash
python3 tools/test/test_gvid_conformance.py
bash tools/test/test_gvid_pack.sh
bash tools/test/test_gvid_metadata.sh
bash tools/test/test_gpr2prores_gvid_input.sh
```

## 4. CNN / Model Governance

Production CNNs must be reproducible and scoped:

- every registered CNN has architecture, trained-against codec, raw
  normalization, checkpoint paths, and SHA-256 hashes,
- routed models have frozen router sidecars, router hashes, expert mappings,
  and deterministic loading policy,
- offline-only models are explicitly marked offline in the pipeline registry,
- Mission 1 4K/8K CNNs carry training-pair or training-receipt hashes plus
  promotion/signoff receipts,
- render paths must not consume forbidden REF content at runtime.
- camera-noise conditioning/noise addback is enabled only for cameras with
  validated sidecars; Mission 1 and iPhone remain metadata-conditioning-only
  until their darkframe stacks validate.

Source of truth: `pipelines/registry.json`,
`docs/PRODUCTION_ARTIFACTS.md`, and `docs/RELEASE_READINESS.md`.

## CI Guard

Run the productization contract guard before release:

```bash
python3 tools/check_productization_contracts.py
python3 tools/test/check_production_capture_requirements.py
```

The guard verifies that the four product pillars and the cross-cutting
productization contracts are documented, linked, and backed by the expected
source/test surfaces. The capture-requirements guard verifies the committed
real-sample and hardware-receipt closure contract.
