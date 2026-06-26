# Productization Contracts

Last refreshed: 2026-06-26

This page is the compact checklist for the four remaining productization areas:
release artifacts, Labs/plugin handoff, `.gvid` conformance, and CNN/model
governance.

## 1. Release Artifacts

Source tags are not enough. A release is externally useful only when it has a
verified review bundle with:

- `.gvid` sample plus metadata sidecar,
- compact visual review media,
- release evidence manifest and target receipts,
- checksums,
- explicit labels for stand-in, offline-only, or camera-handoff-open evidence.

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

## 3. `.gvid` Conformance

The `.gvid` container contract is separate from codec quality. The product
must reject malformed streams and recover only whole-frame interrupted tails.

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

Source of truth: `pipelines/registry.json`,
`docs/PRODUCTION_ARTIFACTS.md`, and `docs/RELEASE_READINESS.md`.

## CI Guard

Run the productization contract guard before release:

```bash
python3 tools/check_productization_contracts.py
```

The guard verifies that the four productization contracts are documented,
linked, and backed by the expected source/test surfaces.

