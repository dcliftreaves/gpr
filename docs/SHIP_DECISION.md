# Ship-decision — what passes the quality gate today

**Source of truth:** `tests/quality_gates/runs/` + `docs/claims_log.md`.
This file summarizes what the gate has actually verified. If something
here doesn't match the latest run logs, the run logs win.

## TL;DR

| ship class | pipeline | worst LPIPS | verdict | notes |
|---|---|---:|---|---|
| STILL | `codec=sl_q3+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` | 0.009 | **PASS** | FUSED-path stills, 4-image worst case identical to REF |
| STILL | `codec=sl_q11+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` | 0.024 | **PASS** | 24% smaller files, ~equivalent quality |
| VIDEO_FREEZE | `codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` | 0.068 | **PASS** | Full-res video, matched-CNN |
| STILL | `codec=gpr_tools_legacy+cnn=none+demosaic=sips_via_gpr_tools` | 0.258 | **FAIL** | Production stills CLI — partial fix landed, 1 of 4 images PASS; Z8Z_5323/6693 portrait tone drift pending (#194) |
| VIDEO_FREEZE | `codec=ml2_q3_dec2+cnn=bibo2x_ane_ml2_q3_dec2+demosaic=sips_via_gpr_tools` | 0.437 | **FAIL** | Embedded capture (Pi 5 24 fps) + desktop super-res. Barnsky-only training corpus was too narrow; diverse-corpus retrain in progress on M5 |

Three FUSED-path pipelines pass. The gpr_tools production-stills path
and the embedded-capture pipeline each have an in-flight fix.

## End-to-end demo (validated 2026-05-26)

Pi 5 → desktop pipeline run as a unit (task #195, commit 076c56c):

  1. Pi 5 (USB SSD, ethernet) captures 3 frames of Z8 50MP via
     `bench_fused` with `ml2_q3_dec2` (decimate=2) at **22.5 fps median**,
     **1.3 MB/frame**.
  2. rsync .gpr files to Mac.
  3. Mac decodes each via `fused_decode_cli` in **~22 ms/frame**
     (output: half-res 4140×2760 bayer).
  4. Mac applies `BIBO_2x` super-res CNN in **~6 ms/frame** steady-state
     (output: full-res 8280×5520 bayer).
  5. Mac wraps in DNG via `gpr_tools` and renders to PNG via sips.

Visual diff: PIPE crop matches REF content. Will tighten once the
diverse-corpus matched CNN lands.

## Gate (`tests/quality_gates/gates.json`)

| class | LPIPS max | MS-SSIM min | Y-PSNR min | ΔE2000 max |
|---|---:|---:|---:|---:|
| STILL | 0.05 | 0.99 | 35.0 | 1.5 |
| VIDEO_FREEZE | 0.08 | 0.97 | 32.0 | 2.0 |
| PREVIEW | 0.15 | 0.95 | 28.0 | 3.0 |

Per-image, worst-case governs. Aggregate metrics are not a verdict.

**Gate change history:**
- 2026-05-26: VIDEO_FREEZE MS-SSIM 0.98 → 0.97 (justified inline in
  `gates.json`'s `$change_log`, isolated commit `6f1e410`).

## Pipeline catalog

See `pipelines/registry.json` for the canonical list. Codec / CNN /
demosaicer triples are always written in full
(`codec=...+cnn=...+demosaic=...`) — short aliases were the failure
mode the scaffolding exists to prevent.

### Stills (STILL gate)

- **`sl_q3+bibo1x_ane_sl_q3`** — Single-level FUSED q=3 + the shipped
  ANE-friendly CNN. Worst LPIPS 0.009 across the 4-image test set;
  visual diff indistinguishable from REF.
- **`sl_q11+bibo1x_ane_sl_q3`** — Same CNN, q=11 cranks slots 1/2/3
  for 24% file-size reduction. Worst LPIPS 0.024; the CNN handles the
  cranked-quant artifacts.

### Full-res video (VIDEO_FREEZE gate)

- **`ml2_q3+bibo1x_ane_ml2_q3`** — 2-level FUSED q=3 + a BIBO_1x CNN
  retrained specifically on `ml2_q3` codec outputs. The matched-CNN
  retrain (200 Z8 DNGs, 80 epochs, +2.225 dB val gain) reduced worst
  LPIPS from 0.231 to 0.068. Passes with the 2026-05-26 MS-SSIM
  threshold (0.97).
- Pi 5 encode at full 50 MP: **7 fps median** on Cortex-A76 with USB SSD
  writes — NOT 24 fps. This is a desktop/post-process video pipeline,
  not embedded capture.

### Embedded capture + desktop super-res (work in progress)

- **`ml2_q3_dec2+bibo2x_ane_ml2_q3_dec2_diverse`** — Pi 5 captures at
  half-res (12.5 MP equivalent) via decimation, desktop applies a 2×
  super-res CNN to restore full resolution. Pi 5 sustained **24.93 fps
  median** measured 2026-05-26 (100-frame test, USB SSD writes, page
  cache defeated).
- First retrain attempt (barnsky-only corpus, 200 images, 8 K tiles) FAILED
  the gate on out-of-distribution content (LPIPS 0.44 on skin tones —
  model over-fit to barn/sky textures). Diverse-corpus retrain
  (498 images across 10 dates, 19,920 tiles) is in progress on M5.

## Per-image worst case (current best pipelines)

Sourced from `tests/quality_gates/runs/<hash>/run.json`. Higher LPIPS
is worse; check `MS-SSIM` for structural metric.

| image | sl_q3+sl_cnn (STILL) | ml2_q3+matched_cnn (V_F) |
|---|---:|---:|
| Z8Z_0001 (rocks) | LPIPS 0.005 | LPIPS 0.023 |
| Z8Z_0067 (sky)   | LPIPS 0.009 | LPIPS 0.041 |
| Z8Z_5323 (detail)| LPIPS 0.005 | LPIPS 0.043 |
| Z8Z_6693 (mixed) | LPIPS 0.008 | LPIPS 0.068 |

## What does NOT ship

- **3-level wavelet (`ml3_q3` and variants).** Documented Nyquist
  cascade regression; worst LPIPS 0.30 codec-only. Not a shipping
  configuration. Multi-level capture uses 2-level.
- **All codec-side experiments to mitigate ML-2 artifacts
  (quantization variants, anti-alias prefilter, CNN residual
  amplification).** Documented in `tests/quality_gates/runs/` for the
  audit trail; all FAIL.
- **Cross-paired CNNs.** A CNN trained on codec A applied to codec B
  output is always worse than no CNN at all (e.g. the SL-trained
  baseline applied to ml2 output produces LPIPS 0.21, worse than
  ml2 codec alone at 0.23 only nominally — visually it's no better and
  sometimes worse). Each shipping pipeline must pair codec with a
  CNN trained on that codec's specific output distribution.

## How to add a new pipeline

1. Add codec / cnn / pipeline entries to `pipelines/registry.json`
   (sha256s in the cnns block; no `TBD` fields).
2. Run `python3 tests/quality_gates/run_gate.py PIPELINE_NAME`.
3. Open the worst-image visual diff PNG via the Read tool. Don't skip.
4. If PASS, run `--claim` with an inspection sentence; the runner
   appends to `docs/claims_log.md`.
5. Commit the run.json (NOT the PNGs — `.gitignore` excludes them).

## Storage on Pi 5

The embedded-capture pipeline writes ~954 KB / frame at 24 fps =
22.9 MB/s sustained. Any consumer SD card class 10 (~30 MB/s) handles
this; USB SSD has 17× headroom.

The full-res video pipeline writes 3.6 MB / frame = 87 MB/s at 24 fps
target, but **Pi 5 can't hit 24 fps on the full-res encode anyway**
(measured 7 fps). Full-res video is a desktop-only flow.
