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
| Best RAW stills | 88% | Strong for the current tested Bayer surface, now including a real X2D 100MP visual roundtrip audit, a real Bayer phase inventory, and explicit camera-noise coverage; real GBRG/GRBG/BGGR fixtures and Mission/iPhone darkframe sidecars are still open. |
| GoPro RAW video MVP | 78% | Pi 5 stand-in and handoff package are strong; real Mission 1 sensor/DMA/storage/display receipts are still required. |
| Premium still/SR | 45% | The infrastructure is broad, but the no-REF high-frequency texture model is not production-grade yet. |
| PSF-aware RAW video improvement | 40% | Current 4K cleanup and 8K SR baselines are useful; formal native PSF/blur-aware replacement remains open. |

The current real X2D 100MP still audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html`.
It records a 11,664 x 8,750 DNG to GPR to DNG roundtrip, 100 percent crop
panels, and 49.21 dB full-image raw Bayer PSNR.

The current real Bayer phase inventory lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_inventory_20260630/index.html`.
It confirms that the canonical Mission 1, Z8, X2D, and iPhone CFA fixtures are
normal 2x2 Bayer, but all parsed real fixtures are RGGB. GBRG, GRBG, and BGGR
remain covered by committed synthetic conformance until real camera fixtures are
added.

The current camera-noise coverage audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/index.html`.
It records six validated darkframe sidecars: X2D at ISO 64, 200, 800, 3200,
and 12800, plus Z8 at ISO 500. Mission 1 and iPhone have real fixtures but no
production-ready darkframe sidecars yet, so nonzero noise removal/addback is not
promoted for those cameras.

The current raw-video PSF/SR readiness audit lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_audit_20260630/index.html`.
It records that the current 4K cleanup and 8K SR baselines are approved for
their existing offline roles, but the PSF replacement is not production-ready
without native camera/display PSF evidence and a PSF-conditioned model gate.

The generated JSON keeps `production_ready=false` until all four pillars have
direct evidence. This avoids promoting a proxy benchmark or diagnostic CNN as a
finished product result.
