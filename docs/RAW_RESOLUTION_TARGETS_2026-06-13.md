# Raw Resolution Targets - 2026-06-13

This note freezes the first production-shaped raw target ladder for the
`ml2_q3_dec2` capture stream. The point is to choose the fastest raw path that
preserves Bayer semantics and bit depth for each output size.

## Target Contract

| target | dimensions | source | method | CNN |
|---|---:|---|---|---|
| `2k_raw_0p5x` | 2070 x 1380 | `ml2_q3_dec2` payload | direct half-res decode; optional fast mode drops L2 highpass | none |
| `4k_raw_1x` | 4140 x 2760 | decoded `ml2_q3_dec2` half-res Bayer | direct decoded Bayer output | none |
| `8k_raw_2x` | 8280 x 5520 | decoded `ml2_q3_dec2` half-res Bayer | BIBO_2x Bayer super-resolution | `bibo2x_ane_ml2_q3_dec2_diverse` |

The 2K path is not an RGB resize. The runtime path decodes directly to the
lower-resolution Bayer target. The older CFA-plane area downsample remains a
reference/fallback path for streams that cannot emit the 2K target directly.
Outputs remain little-endian `uint16` Bayer data with 14-bit sensor values
preserved in the payload type.

## Receipts

Timing and quality scripts:

- `tools/cnn/bench_raw_resolution_targets.py`
- `tools/cnn/evaluate_raw_resolution_targets.py`

Receipts were written under `/Volumes/OWC_8TB/gpr_work/artifacts/raw_resolution_targets_20260613/`
and `/Volumes/OWC_8TB/gpr_work/artifacts/raw_resolution_targets_20260614/`.

| receipt | frames | targets |
|---|---:|---|
| `bench_2k4k_native_100f/raw_resolution_targets_bench.json` | 100 | 2K, 4K native runtime path |
| `bench_2k4k_100f/raw_resolution_targets_bench.json` | 100 | 2K, 4K |
| `quality_2k4k_100f/raw_resolution_targets_quality.json` | 100 | 2K, 4K |
| `smoke_2k4k8k_3f/raw_resolution_targets_bench.json` | 3 | 2K, 4K, 8K |
| `quality_2k4k8k_3f/raw_resolution_targets_quality.json` | 3 | 2K, 4K, 8K |
| `pi5_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K, 4K Pi 5 decode-side timing |
| `pi5_fast_l2drop_v2_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K fast Pi 5 decode-side timing |
| `quality_2k_runtime_fast_l2drop_100f/raw_resolution_targets_quality.json` | 100 | 2K fast runtime quality |
| `visual_fast_2k_28f/raw_resolution_targets_visual_dashboard.html` | 28 images / 84 crops | 2K fast proxy visual dashboard |
| `visual_2k_preserve_l2_28f/raw_resolution_targets_visual_dashboard.html` | 28 images / 84 crops | 2K preserve-L2 comparison dashboard |
| `visual_2k_l2mask4_28f/raw_resolution_targets_visual_dashboard.json` | 28 images / 84 crops | 2K selective L2 HH visual diagnostic |
| `visual_4k_28f/raw_resolution_targets_visual_dashboard.html` | 28 images / 84 crops | 4K rendered proxy visual dashboard |
| `pi5_l2mask4_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K selective L2 HH Pi 5 timing |
| `pi5_l2drop_stream_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K fast L2-drop Pi 5 timing with L2 streaming |
| `pi5_l2drop_stream_v2_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K fast L2-drop Pi 5 timing with L2 streaming and explicit receipt schema |
| `pi5_l2mask4_stream_v2_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K selective L2 HH Pi 5 timing with L2 streaming |
| `pi5_l2mask4_stream_v3_120f/raw_resolution_targets_pi5_120f.json` | 120 | 2K selective L2 HH Pi 5 timing with L2 streaming and explicit receipt schema |
| `hh_scale_sweep_2k_l2mask4_28f.json` | 28 images / 84 crops | HH amplitude sweep diagnostic |

## Current Results

### 4K raw 1x

- Dimensions: 4140 x 2760.
- Method: direct decode from `ml2_q3_dec2`.
- 100-frame native timing: 22.9 ms median, 43.7 fps median.
- Pi 5 120-frame decode-side timing: 159.6 ms median, 6.3 fps median.
- 100-frame raw quality against source-derived half-scale Bayer: 50.25 dB mean
  PSNR, 49.78 dB median PSNR, 10.41 LSB mean MAE.
- 28-image / 84-crop rendered proxy dashboard: 55/84 crops pass PREVIEW proxy
  thresholds, worst LPIPS 0.3327, worst MS-SSIM 0.8772, worst Y-PSNR 30.82,
  worst dE2000 2.11. Failures are 27 LPIPS-only rows plus two LPIPS+MS-SSIM
  rows, concentrated in lower-right texture/detail crops.
- Current decision: production candidate for Mac/offline raw output with a
  documented rendered-proxy blocker. It is not a 24 fps Pi decode-side path
  until `gpr_decode_fused` is accelerated or the live path avoids decode, and
  it should not be promoted to a rendered/perceptual production path until the
  LPIPS texture misses are closed or explicitly scoped out.

### 2K raw 0.5x

- Dimensions: 2070 x 1380.
- Method: direct half-res decode from `ml2_q3_dec2`.
- Native implementation: optional `2k_raw_0p5x` target in
  `build-local/bin/fused_decode_cli`.
- 100-frame native timing: 25.2 ms median, 39.7 fps median.
- Pi 5 120-frame decode-side timing: 168.8 ms median, 5.9 fps median.
- Pi 5 downsample-only timing: 8.9 ms median, 112.4 fps median.
- Pi 5 direct half-res decoder timing after skipping unused L1 highpass:
  48.75 ms median, 20.5 fps median.
- Pi 5 fast direct half-res mode with `GPR_DECODE_HALFRES_DROP_L2_HP=1`:
  31.4 ms median, 31.85 fps median before L2 streaming; 29.3 ms median,
  34.13 fps median after L2 streaming.
- 100-frame raw quality against source-derived quarter-scale Bayer: 52.41 dB
  mean PSNR, 51.89 dB median PSNR, 7.44 LSB mean MAE.
- 100-frame fast runtime quality with `GPR_DECODE_HALFRES_DROP_L2_HP=1`:
  55.14 dB mean PSNR, 54.71 dB median PSNR, 6.84 LSB mean MAE.
- 28-image / 84-crop proxy visual dashboard with
  `GPR_DECODE_HALFRES_DROP_L2_HP=1`: 56/84 crops pass PREVIEW proxy
  thresholds, worst LPIPS 0.1628, worst MS-SSIM 0.9768, worst Y-PSNR
  37.31, worst dE2000 1.46.
- Preserve-L2 comparison on the same proxy dashboard: 55/84 crops pass, worst
  LPIPS 0.1850, worst MS-SSIM 0.9684, worst Y-PSNR 35.56, worst dE2000 1.54.
- Selective L2 highpass diagnostics with `GPR_DECODE_HALFRES_L2_MASK` show that
  restoring only mask 4 (the L2 HH band) is the only quality-positive middle
  ground: 80/84 crops pass, worst LPIPS 0.1549, worst MS-SSIM 0.9771, worst
  Y-PSNR 37.60, worst dE2000 1.46. Other masks are worse: mask 1 = 56/84,
  mask 2 = 55/84, mask 3 = 55/84, mask 5 = 56/84, mask 6 = 56/84, and full
  mask 7 = 55/84.
- Pi 5 timing for `GPR_DECODE_HALFRES_L2_MASK=4` before L2 streaming: 47.5 ms
  median, 21.05 fps median, p95 51.1 ms. After routing the L2 stop point
  through the row-strip streaming inverse+color path: 38.7 ms median,
  25.84 fps median, p95 41.8 ms.
- Current decision: selective L2 HH is now the 2K live-quality candidate. It
  clears the Pi 5 24 fps decode-side target and fixes most LPIPS-only texture
  misses while preserving structure, luma PSNR, and color. It is not a full
  PREVIEW proxy pass yet because four crop rows remain just above LPIPS 0.15
  (worst 0.1549). The low-detail L2-drop mode remains the fastest live mode.

### 8K raw 2x

- Dimensions: 8280 x 5520.
- Method: BIBO_2x from decoded half-res Bayer.
- 3-frame timing: 376.4 ms median for decode plus model in the earlier timing
  smoke, roughly 2.7 fps median on this local path.
- 3-frame raw quality: 48.79 dB mean PSNR, 50.80 dB median PSNR.
- Current decision: offline/review candidate only. It is not a live 24 fps path
  without a much faster model or a different 2x reconstruction strategy.

## Source-Lineage Caution

`Z8Z_0001` is an outlier in the 100-frame quality receipt. It resolves from the
fallback `artifacts/visual_compare_20260525/source_dngs` root rather than the
main `barnsky_full_dngs` corpus. Its 4K PSNR is 36.72 dB while the neighboring
main-corpus frames sit near 49-53 dB. Treat that row as a source-lineage warning
until the exact source DNG/GPR pairing is verified.

## Next Production Work

1. Decide whether the fast 2K mode should be a named registry/output policy or
   remain an env-gated live-preview path.
2. If 2K live preview must pass LPIPS <= 0.15 on every proxy crop, the next
   work is not generic sharpening, synthetic noise, or simple HH amplitude
   scaling: the 2026-06-14 probes reached only 65/84 for RGB unsharp, 57/84
   for deterministic fine-grain synthesis, and 80/84 for the best HH scale
   sweep. The useful signal is actual L2 HH and it now fits the Pi 5 frame
   budget; the remaining blocker is four near-threshold LPIPS rows.
3. Close or scope the 4K rendered-proxy blocker. The current no-CNN 4K path has
   raw PSNR evidence but passes only 55/84 rendered proxy rows, dominated by
   LPIPS texture misses.
4. Keep 8K as an offline/review target until a faster 2x raw reconstruction
   exists and clears both quality and timing gates.
