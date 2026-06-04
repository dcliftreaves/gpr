# Testing methodology — what runs where

After the codification of stills vs video (2026-05-28), there are
**three distinct test layers** with different scopes. Each catches
different bugs. Keep them straight.

## Layer 1 — codec-only regression (`test_capabilities.py`)

**What it measures**: encoder/decoder roundtrip on synthetic content
at specific (bit-depth × resolution × quality) cells. Metrics:
encode/decode ms, compress_ratio, bayer-domain PSNR.

**What it does NOT cover**: the CNN restoration step, the demosaic
rendering, the actual user-facing visual quality.

**Runs in**: CI (every PR, both macOS and Linux runners).

**Catches**: codec speed regressions, file-size regressions, bayer-level
quality regressions.

**Note**: This benchmarks the LEGACY gpr_tools encoder (which ships for
stills). It does NOT cover the FUSED encoder (which ships for video).
That gap is currently open — see "Open methodology gaps" below.

## Layer 2 — perceptual gate (`run_gate.py`)

**What it measures**: full ship pipeline (codec → CNN → demosaic → render)
on 4 fixed real photographs (Z8 50 MP). Metrics: LPIPS, MS-SSIM, Y-PSNR,
ΔE2000, all computed worst-image-first. Per-image thresholds in
`gates.json`; verdict is per-image, never aggregate.

**Truth source**: this is the only thing allowed to issue a PASS or FAIL
ship verdict. Run logs in `tests/quality_gates/runs/<hash>/` are the
durable artifact.

**Runs in**: manually on demand. Not in CI yet (the FUSED encoder needs
MPS for the CNN inference and CI doesn't have it).

**Catches**: visual-quality regressions in the full ship pipeline,
distribution mismatches between codec and matched CNN, gate-threshold
breaches.

## Layer 3 — capture-side benchmarks (Pi 5 timing, etc.)

**What it measures**: real-time encode rate on the Pi 5 capture device,
sustained throughput including disk writes and page-cache exhaustion.

**Current data**: `docs/STILLS_PI5_TIMING.md` (q=0..8 single-thread
timings). `docs/pi5_bench_2026-05-26.md` (sustained 24.93 fps for the
embedded video path).

**Runs in**: manual, on the Pi 5. Should become a CI cell once we have
a Pi 5 runner.

## How layers compose

```
+----------------------------+
| Layer 1: encoder-only      |  bayer in → bayer out → PSNR
|         (test_capabilities)|  CI gates this
+----------------------------+

+----------------------------+
| Layer 2: full ship gate    |  bayer in → codec → CNN → render → LPIPS
|         (run_gate)         |  Manual; THE ship-claim authority
+----------------------------+

+----------------------------+
| Layer 3: real-time bench   |  sustained fps on Pi 5 USB SSD
|         (Pi 5 timing)      |  Manual; capture-rate ceiling
+----------------------------+
```

## Open methodology gaps (intentionally listed)

1. **`test_capabilities.py` doesn't cover the FUSED encoder ship path.**
   It tests gpr_tools (legacy = the STILLS encoder). For VIDEO ship
   coverage we need a sibling test that exercises `test_fused_roundtrip`
   at the ml2_q3+L1×2 cranked operating point.

2. **`test_capabilities.py` doesn't cover the CNN-corrected path.**
   We bench the codec alone; users get codec + CNN + render. A
   `test_stills_full_pipeline.py` that runs the gate-style pipeline
   on synthetic content (small + deterministic + CI-friendly) would
   close this gap.

3. **Perceptual gate isn't in CI.** Because of the MPS dependency.
   A workaround: pre-compute the gate REF images and CNN outputs
   on a Mac, check them in, and have CI verify against the cached
   outputs.

4. **No Pi 5 CI runner.** Pi 5 timing measurements happen by hand,
   so regressions can sneak in. Adding a self-hosted runner on the
   Pi would close this.

5. **`gates.json` thresholds drift.** The change_log captures
   intentional moves, but a CI check that a PR doesn't touch gates.json
   unless explicitly isolated (per CLAUDE.md rule) would prevent
   accidental movement.

## Recommended priority

- (a) Add `test_stills_full_pipeline.py` so CI catches CNN-corrected
  regressions (Layer 1 + 2 unified).
- (b) Add a CI cell that runs a small subset of the perceptual gate
  on Mac CI (where MPS is available) for the shipping pipelines.
- (c) Per-PR check that gates.json changes are isolated (per CLAUDE.md).
- (d) Pi 5 CI runner (longest-term; needs hardware allocation).

Anything else is nice-to-have for now.
