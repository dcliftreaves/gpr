# Capabilities — measured, criteria-stated, regression-tested

Each row is one capability we claim. The four metric columns show the
**measured value** alongside the **explicit criterion** the test asserts,
and the verdict — MET, EXCEEDED, or FAILED.

- **MET**     — measured value passes the stated criterion.
- **EXCEEDED** — measured value comfortably beats the criterion
  (≥ 10 % better on time/size metrics, ≥ 2 dB better on PSNR).
- **FAILED**  — measured value breaks the criterion.

Regenerated on every run of `tools/test/test_capabilities.py`. Adding a
capability = adding one row to that script with its criteria.

## Summary

- **16** EXCEEDED
- **0** MET
- **0** FAILED
- **0** SKIPPED (missing optional deps)
- last run: 2026-06-03 08:32:44
- build dir: `build-local`

## Stills · encode → decode → PSNR roundtrip

| Capability | Encode | Decode | Compressed size | Roundtrip PSNR | Overall |
|---|---|---|---|---|---|
| Stills · rggb12 · 1024² · q=3 (Filmscan-1) | 6.0 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 6.8 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 5.14%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 43.26 dB<br/>_≥ 42 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb12p (packed) · 1024² · q=3 | 6.5 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 7.3 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 5.12%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 43.28 dB<br/>_≥ 42 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=3 | 6.8 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.2 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 7.18%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.76 dB<br/>_≥ 52 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=0 (Low) | 6.0 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 6.3 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 3.06%<br/>_≤ 0.05_<br/>✨ EXCEEDED | 53.07 dB<br/>_≥ 51.5 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=5 (Filmscan-2, quality peak) | 7.9 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 10.8 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 13.48%<br/>_≤ 0.14_<br/>✅ MET | 57.07 dB<br/>_≥ 55 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=8 (Filmscan-5) | 8.7 ms<br/>_≤ 60 ms_<br/>✨ EXCEEDED | 12.2 ms<br/>_≤ 60 ms_<br/>✨ EXCEEDED | 19.02%<br/>_≤ 0.25_<br/>✨ EXCEEDED | 61.18 dB<br/>_≥ 60.5 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=11 (CNN-aware) | 6.9 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 7.6 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 4.99%<br/>_≤ 0.06_<br/>✅ MET | 53.52 dB<br/>_≥ 51.5 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb16 · 1024² · q=3 | 7.2 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.1 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 5.37%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.44 dB<br/>_≥ 52 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · gbrg16 (alt Bayer) · 1024² · q=3 | 7.2 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.3 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 5.38%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.43 dB<br/>_≥ 52 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb12 · 12 MP (4032×3024) · q=3 | 33.0 ms<br/>_≤ 300 ms_<br/>✨ EXCEEDED | 51.7 ms<br/>_≤ 250 ms_<br/>✨ EXCEEDED | 4.72%<br/>_≤ 0.07_<br/>✨ EXCEEDED | 43.31 dB<br/>_≥ 42 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 23 MP HERO10 (5568×4176) · q=3 | 72.9 ms<br/>_≤ 600 ms_<br/>✨ EXCEEDED | 123.3 ms<br/>_≤ 600 ms_<br/>✨ EXCEEDED | 6.75%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.82 dB<br/>_≥ 52 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb14 · 50 MP Z8 (8280×5520) · q=3 | 133.7 ms<br/>_≤ 1100 ms_<br/>✨ EXCEEDED | 240.6 ms<br/>_≤ 1100 ms_<br/>✨ EXCEEDED | 6.78%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.85 dB<br/>_≥ 52 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |
| Stills · rggb16 · 100 MP X2D (11664×8750) · q=3 | 265.1 ms<br/>_≤ 2500 ms_<br/>✨ EXCEEDED | 447.3 ms<br/>_≤ 2500 ms_<br/>✨ EXCEEDED | 4.89%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.52 dB<br/>_≥ 52 dB_<br/>✅ MET | — | — | — | — | **✨ EXCEEDED** |

## CNN-corrected · multi-level + dec=2 FUSED → BIBO_1x → AHD render PSNR

Real-DNG playback chain protected by these cells: multi-level + decimate=2
FUSED encode/decode (half-res topology from PR #10/#11/#13) → BIBO_1x CNN
(`BayInBayOut_1x_AAon_w16_ANE.pt`) on the half-res bayer → bayer-bicubic-2x
back to full size → rawpy AHD render → masked Y-PSNR vs the source-DNG AHD
render at the stated output resolution. macOS-only (torch + MPS); Linux CI
reports SKIPPED for these rows.

| Capability | CNN-corrected PSNR | Overall |
|---|---|---|
| CNN · BIBO_1x · Z8 ISO64 · 50 MP → UHD (single-level + CNN) | 53.95 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| CNN · BIBO_1x · Z8 ISO64 · 50 MP → 4K (single-level + CNN) | 53.86 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| CNN · BIBO_1x · Z8 ISO22800 · 50 MP → UHD (single-level + CNN) | 47.24 dB<br/>_≥ 42.5 dB_<br/>✨ EXCEEDED | **✨ EXCEEDED** |

## Metric definitions

- **Encode ms** — wall-clock time for `gpr_tools dng→gpr` at the stated quality.
- **Decode ms** — wall-clock time for `gpr_tools gpr→dng`.
- **Compressed size** — output GPR bytes ÷ raw bayer bytes (W·H·2). Lower = more compression.
- **Roundtrip PSNR** — bayer-domain PSNR (decoded vs original synth raw), peak set per bit depth.
- **CNN-corrected PSNR** — render-domain masked Y-PSNR (channel-brightness matched) for the
  full multi-level + dec=2 FUSED → BIBO_1x → AHD-render chain vs the source-DNG AHD render
  at the stated output resolution. Dark/bright masked (Y∈(10,250) on 8-bit scale).

## Test methodology

Each cell uses a deterministic synthetic Bayer fixture (radial gradient +
per-channel DC offsets + noise) sized to match the stated resolution.
The fixture is designed so 3-level wavelet LL coefficients exceed 32767,
exercising the sign-extension path that has historically been a regression
hotspot. Timing measurements are wall-clock subprocess invocations. For
CI-sized still cells the harness records the best of a small number of
invocations to suppress hosted-runner cold-start noise; larger cells run
once because codec work dominates launch overhead.

Run `python3 tools/test/test_capabilities.py` to assert; add `--refresh`
to recompute baselines (don't commit the script changes without revisiting
tolerances).
