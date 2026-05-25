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

- **15** EXCEEDED
- **0** MET
- **0** FAILED
- **0** SKIPPED (missing optional deps)
- last run: 2026-05-25 05:29:53
- build dir: `build-local`

## Stills · encode → decode → PSNR roundtrip

| Capability | Encode | Decode | Compressed size | Roundtrip PSNR | Overall |
|---|---|---|---|---|---|
| Stills · rggb12 · 1024² · q=3 (Filmscan-1) | 11.1 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.8 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 5.12%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 43.27 dB<br/>_≥ 42 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb12p (packed) · 1024² · q=3 | 7.7 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.1 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 5.13%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 43.27 dB<br/>_≥ 42 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=3 | 8.7 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 9.1 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 7.18%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.76 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=0 (Low) | 6.8 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 7.0 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 3.06%<br/>_≤ 0.05_<br/>✨ EXCEEDED | 53.08 dB<br/>_≥ 51.5 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=5 (Filmscan-2, quality peak) | 10.6 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 12.5 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 13.49%<br/>_≤ 0.14_<br/>✅ MET | 57.06 dB<br/>_≥ 55 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=8 (Filmscan-5) | 12.0 ms<br/>_≤ 60 ms_<br/>✨ EXCEEDED | 14.2 ms<br/>_≤ 60 ms_<br/>✨ EXCEEDED | 19.64%<br/>_≤ 0.25_<br/>✨ EXCEEDED | 62.05 dB<br/>_≥ 60.5 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb16 · 1024² · q=3 | 7.7 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.3 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 5.36%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.44 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · gbrg16 (alt Bayer) · 1024² · q=3 | 7.8 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.8 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 5.37%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.44 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb12 · 12 MP (4032×3024) · q=3 | 44.5 ms<br/>_≤ 300 ms_<br/>✨ EXCEEDED | 55.4 ms<br/>_≤ 250 ms_<br/>✨ EXCEEDED | 4.72%<br/>_≤ 0.07_<br/>✨ EXCEEDED | 43.31 dB<br/>_≥ 42 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 23 MP HERO10 (5568×4176) · q=3 | 92.7 ms<br/>_≤ 600 ms_<br/>✨ EXCEEDED | 130.7 ms<br/>_≤ 600 ms_<br/>✨ EXCEEDED | 6.75%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.82 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 50 MP Z8 (8280×5520) · q=3 | 187.5 ms<br/>_≤ 1100 ms_<br/>✨ EXCEEDED | 246.7 ms<br/>_≤ 1100 ms_<br/>✨ EXCEEDED | 6.78%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.86 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb16 · 100 MP X2D (11664×8750) · q=3 | 354.2 ms<br/>_≤ 2500 ms_<br/>✨ EXCEEDED | 450.1 ms<br/>_≤ 2500 ms_<br/>✨ EXCEEDED | 4.89%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.52 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |

## CNN-corrected · multi-level + dec=2 FUSED → BIBO_1x → AHD render PSNR

Real-DNG playback chain protected by these cells: multi-level + decimate=2
FUSED encode/decode (half-res topology from PR #10/#11/#13) → BIBO_1x CNN
(`BayInBayOut_1x_AAon_w16_ANE.pt`) on the half-res bayer → bayer-bicubic-2x
back to full size → rawpy AHD render → masked Y-PSNR vs the source-DNG AHD
render at the stated output resolution. macOS-only (torch + MPS); Linux CI
reports SKIPPED for these rows.

| Capability | CNN-corrected PSNR | Overall |
|---|---|---|
| CNN · BIBO_1x · Z8 ISO64 · 50 MP → UHD (multi-level + dec=2) | 29.33 dB<br/>_≥ 27.8 dB_<br/>✨ EXCEEDED | **✨ EXCEEDED** |
| CNN · BIBO_1x · Z8 ISO64 · 50 MP → 4K (multi-level + dec=2) | 29.31 dB<br/>_≥ 27.8 dB_<br/>✨ EXCEEDED | **✨ EXCEEDED** |
| CNN · BIBO_1x · Z8 ISO22800 · 50 MP → UHD (high-ISO, harder) | 30.21 dB<br/>_≥ 28.7 dB_<br/>✨ EXCEEDED | **✨ EXCEEDED** |

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
hotspot. All measurements are wall-clock, single invocation; no warmup or
pinning, because in production users invoke `gpr_tools` once per file.

Run `python3 tools/test/test_capabilities.py` to assert; add `--refresh`
to recompute baselines (don't commit the script changes without revisiting
tolerances).
