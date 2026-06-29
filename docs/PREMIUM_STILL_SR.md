# Premium Still SR

The premium still-SR pillar is separate from the current video SR work. It is
allowed to spend much more time per image, but it must still preserve editable
raw behavior, tone/color stability, camera noise policy, and worst-row visual
quality.

## Receipt

Premium still-SR evidence is recorded as a `gpr.premium_still_sr_gate.v1` JSON
sidecar and validated by:

```sh
python3 tools/check_product_pillar_receipts.py path/to/premium_still_sr_gate_receipt.json
```

The receipt requires:

- candidate pipeline ID, checkpoint hash, and target role;
- fixture coverage for camera count, 50 MP-class count, 100 MP-class count,
  and CFA phases;
- editable DNG, editable GPR, review TIFF/ProRes, and dashboard artifact
  hashes;
- comparison against the current STILL q0/q3/q8 baseline;
- a noise policy with raw-noise/signal audit status.

## Skeleton Builder

The committed builder creates a CI-safe non-production receipt:

```sh
python3 tools/build_premium_still_sr_gate_receipt.py \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate_skeleton
```

This proves the gate contract and artifact hashing path. It does not promote a
model. `--production-ready` is refused unless `--real-artifacts` is also set,
and the receipt checker still requires real gate pass state, 50 MP fixtures,
100 MP fixtures, and a passing raw-noise/signal audit.

## Current-State Readiness Builder

The current-state builder audits the merged still baselines, 50 MP / 100 MP
capability evidence, reusable SR packaging artifacts, and X2D/Z8 camera-noise
sidecars:

```sh
python3 tools/build_premium_still_sr_readiness.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_readiness_20260629
```

It emits:

- `readiness.json` and `readiness.md`;
- `index.html` for review;
- a non-production `premium_still_sr_gate_receipt.json` that validates against
  the product-pillar checker.

This is the source of truth for the current gap: 50 MP / 100 MP still
roundtrips, current still baselines, reusable editable SR packaging, and
validated X2D/Z8 noise sidecars exist, but a dedicated premium still-SR
checkpoint, still-specific dashboard, and raw-editor latitude receipt do not.

## Production Path

The next real pass should use 50 MP and 100 MP still fixtures, including X2D
and Z8 where available:

1. Train or tune against high-quality still targets, not video crops.
2. Condition on validated camera-noise sidecars for the relevant camera/ISO
   class.
3. Emit editable DNG/GPR plus review TIFF/ProRes/contact sheets.
4. Promote only if the candidate beats the current still tiers on raw-domain
   metrics, rendered visual gates, editor-latitude checks, and worst-image
   review.
