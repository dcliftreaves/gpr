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

## Real-Pair Builder

The pair-derived builder consumes the premium still-SR pair NPZ layout and fits
the same-color 2x Bayer resize kernel that maps high-resolution target planes
to low-resolution input planes:

```sh
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python \
  tools/build_bayer_resize_psf_from_pairs.py \
  --pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629
```

Current receipt:

`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629/bayer_resize_psf_receipt.json`

Current dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_resize_psf_from_pairs_20260629/index.html`

The 2026-06-29 run uses 256 Mission 1, Z8, and X2D real-fixture tiles. The
global fit converges to normalized weights very close to `[0.25, 0.25, 0.25,
0.25]`, selects `same_color_box2` as the best candidate, and reports about
0.30 RMSE on the normalized 14-bit training scale. This confirms the current
pair target is internally consistent with a same-color 2x2 box resize model.

It is still non-production evidence. The current pair generator creates the
low-resolution side by downsampling extracted high-resolution raw, so this does
not yet measure native sensor, camera ISP, DMA, display, or storage blur.

## Production Path

The next real pass should move beyond modeled pairs into native capture and
display evidence:

1. Estimate effective Bayer-domain PSF from true high-res / native-low-res
   Mission 1 and Z8 captures, with sharp edges and texture fields.
2. Train or tune 4K cleanup and 8K SR with CFA-aware targets and
   PSF-conditioned losses.
3. Promote only if Mission42 and Z8 all24 gates improve and the output has
   `.gvid`, editable DNG/GPR, ProRes, timing, memory, and hash receipts.
