# Product Pillar Scorecard

The product pillar scorecard is the top-level audit view for the four large
efforts currently driving the repo:

1. best RAW stills for 50 MP / 100 MP cameras,
2. GoPro / Mission 1 RAW video MVP,
3. premium spend-time-for-quality still/SR,
4. PSF-aware RAW video cleanup and reconstruction.

It is intentionally stricter than the README. The README can sell the project
clearly; this scorecard says what is proven, what is only proxy-proven, and
what still blocks a production claim.

Build it with:

```bash
GPR_TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp \
python3 tools/build_product_pillar_scorecard.py \
  --external-root /Volumes/OWC_8TB/gpr_work \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_20260630
```

Current generated dashboard:

`/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_20260630/index.html`

Current interpretation:

| pillar | current score | production reading |
|---|---:|---|
| Best RAW stills | 85% | Strong for the current tested Bayer surface; more real alternate-phase fixtures and calibrated Mission/iPhone noise are still open. |
| GoPro RAW video MVP | 78% | Pi 5 stand-in and handoff package are strong; real Mission 1 sensor/DMA/storage/display receipts are still required. |
| Premium still/SR | 45% | The infrastructure is broad, but the no-REF high-frequency texture model is not production-grade yet. |
| PSF-aware RAW video improvement | 40% | Current 4K cleanup and 8K SR baselines are useful; formal native PSF/blur-aware replacement remains open. |

The generated JSON keeps `production_ready=false` until all four pillars have
direct evidence. This avoids promoting a proxy benchmark or diagnostic CNN as a
finished product result.
