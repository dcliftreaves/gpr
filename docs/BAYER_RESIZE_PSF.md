# Bayer Resize PSF

The raw-video improvement pillar is about understanding the blur introduced
when Bayer data is resized or reconstructed. The current 4K cleanup and 8K SR
paths are approved empirical baselines, but they are not yet formal
PSF-calibrated models.

## Receipt

PSF evidence is recorded as a `gpr.bayer_resize_psf_receipt.v1` JSON sidecar
and validated by:

```sh
python3 tools/check_product_pillar_receipts.py path/to/bayer_resize_psf_receipt.json
```

Production promotion requires real Mission and Z8 full-frame evidence, not just
a synthetic or crop-local measurement. The receipt must include sharp-edge
evidence, texture-field evidence, gate results, raw/editable outputs, ProRes
review media, and timing/memory artifacts.

## Synthetic Builder

The committed builder creates a small non-production receipt that exercises the
contract without private data:

```sh
python3 tools/build_bayer_resize_psf_receipt.py \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/psf_synthetic_smoke \
  --resize-factor 2 --cfa-phase RGGB --cfa-phase GBRG
```

It generates synthetic sharp-edge and texture fixtures, applies a box
downsample/nearest-upsample path, estimates edge-spread width, writes artifact
hashes, and marks `production_ready=false`. This is useful for CI and tool
stability. It is not enough to replace the current SR baseline.

## Production Path

The next real pass should replace the synthetic fixtures with high-res /
low-res Bayer pairs from Mission 1 and Z8:

1. Estimate effective Bayer-domain PSF from sharp edges and texture fields.
2. Train or tune 4K cleanup and 8K SR with CFA-aware targets and
   PSF-conditioned losses.
3. Promote only if Mission42 and Z8 all24 gates improve and the output has
   `.gvid`, editable DNG/GPR, ProRes, timing, memory, and hash receipts.
