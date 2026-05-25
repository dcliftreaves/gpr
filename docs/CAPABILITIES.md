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

- **12** EXCEEDED
- **0** MET
- **0** FAILED
- last run: 2026-05-25 04:53:43
- build dir: `build-local`

## Stills · encode → decode → PSNR roundtrip

| Capability | Encode | Decode | Compressed size | Roundtrip PSNR | Overall |
|---|---|---|---|---|---|
| Stills · rggb12 · 1024² · q=3 (Filmscan-1) | 8.2 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 9.8 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 5.12%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 43.27 dB<br/>_≥ 42 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb12p (packed) · 1024² · q=3 | 8.1 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 8.7 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 5.12%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 43.27 dB<br/>_≥ 42 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=3 | 8.4 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 9.1 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 7.16%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.76 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=0 (Low) | 7.1 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 7.0 ms<br/>_≤ 40 ms_<br/>✨ EXCEEDED | 3.07%<br/>_≤ 0.05_<br/>✨ EXCEEDED | 53.08 dB<br/>_≥ 51.5 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=5 (Filmscan-2, quality peak) | 11.3 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 13.9 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 13.48%<br/>_≤ 0.14_<br/>✅ MET | 57.06 dB<br/>_≥ 55 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 1024² · q=8 (Filmscan-5) | 12.5 ms<br/>_≤ 60 ms_<br/>✨ EXCEEDED | 14.5 ms<br/>_≤ 60 ms_<br/>✨ EXCEEDED | 19.65%<br/>_≤ 0.25_<br/>✨ EXCEEDED | 62.06 dB<br/>_≥ 60.5 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb16 · 1024² · q=3 | 8.5 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 9.6 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 5.37%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.44 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · gbrg16 (alt Bayer) · 1024² · q=3 | 9.7 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 10.5 ms<br/>_≤ 50 ms_<br/>✨ EXCEEDED | 5.37%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.43 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb12 · 12 MP (4032×3024) · q=3 | 47.8 ms<br/>_≤ 300 ms_<br/>✨ EXCEEDED | 54.3 ms<br/>_≤ 250 ms_<br/>✨ EXCEEDED | 4.72%<br/>_≤ 0.07_<br/>✨ EXCEEDED | 43.31 dB<br/>_≥ 42 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 23 MP HERO10 (5568×4176) · q=3 | 92.1 ms<br/>_≤ 600 ms_<br/>✨ EXCEEDED | 129.5 ms<br/>_≤ 600 ms_<br/>✨ EXCEEDED | 6.75%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.82 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb14 · 50 MP Z8 (8280×5520) · q=3 | 192.4 ms<br/>_≤ 1100 ms_<br/>✨ EXCEEDED | 258.0 ms<br/>_≤ 1100 ms_<br/>✨ EXCEEDED | 6.78%<br/>_≤ 0.1_<br/>✨ EXCEEDED | 53.86 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |
| Stills · rggb16 · 100 MP X2D (11664×8750) · q=3 | 361.8 ms<br/>_≤ 2500 ms_<br/>✨ EXCEEDED | 453.1 ms<br/>_≤ 2500 ms_<br/>✨ EXCEEDED | 4.89%<br/>_≤ 0.08_<br/>✨ EXCEEDED | 53.52 dB<br/>_≥ 52 dB_<br/>✅ MET | **✨ EXCEEDED** |

## Metric definitions

- **Encode ms** — wall-clock time for `gpr_tools dng→gpr` at the stated quality.
- **Decode ms** — wall-clock time for `gpr_tools gpr→dng`.
- **Compressed size** — output GPR bytes ÷ raw bayer bytes (W·H·2). Lower = more compression.
- **Roundtrip PSNR** — bayer-domain PSNR (decoded vs original synth raw), peak set per bit depth.

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
