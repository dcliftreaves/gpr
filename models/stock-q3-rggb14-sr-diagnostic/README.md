# Optional stock-Q3 RGGB14 2x diagnostic candidate

`selected.pt` provides an explicit, nonzero 2x CNN reconstruction path for
stock-Q3/RGGB14 inputs. Measured improvement over bicubic is small:
**0.00046–0.06133 dB** active PSNR on four historical references,
**0.00729 dB pooled**. These results do not establish useful recovered detail,
rendered/video quality or restored compression tiers.

Architecture: bundled `F_ane`, width 16/depth 3, normalization 16383 and
residual scale **0.0003125** (1/32 of training strength). Bayer width and height
double. Supported calibration uses the checked scale-two transform. Model
counts remain distinct from original payloads and optional lossy re-encoding.

SHA-256: `f7bda0449b94be4ebd3617297b9dee04506b00e38788dba2d0b04eb71fdaa2f4`.
Size: 1,320,232 bytes. This is the exact frozen evaluated checkpoint.
Selection is explicit; no download, automatic model selection, installed
camera/SDK weight dependency or production-quality approval is added.
The checkpoint retains `quality_approval=false`.

Fresh training uses training-source-only full-image masks. Existing patch
regional guards and complete validation-image guards select the checkpoint.
All four historical references pass active/shadow/highlight/detail
nonregression on both Torch MPS and CPU. Those references are not newly unseen.
Inputs are simulated using same-site averaging followed by actual stock Q3;
other presets, Bayer/count domains and physical sensor/noise/video quality do
not inherit these results.

Two supplied 12 MP inputs produce 8192x6144 editable outputs on Pi CPU and Mac
MPS, with exact supported calibration and at most one-count differences
(237/219 differing samples out of 50,331,648 each). Pi inference takes
86.29–99.89 s per frame in this offline check. This is execution agreement,
not lossless GoPro ground truth or sustained inference throughput.

From the repository root with optional Torch/numpy/tifffile dependencies:

```sh
python3 tools/stock_still.py restore input.gpr --sample-bits 14 \
  --sdk build-runtime/source/app/gpr_tools/gpr_tools \
  --checkpoint models/stock-q3-rggb14-sr-diagnostic/selected.pt \
  --device mps --scale 2 --output diagnostic-2x.dng
```

Use `--device cpu` for CPU execution. Native exporters support this architecture,
but this checkpoint's native artifacts have not been qualified. The separate
[1x cleanup candidate](../stock-q3-rggb14-cleanup/README.md) and its checks are
unchanged. This file is a diagnostic asset, not a recommended SR model.

See the [study and receipts](../../docs/stock-sr-source-regions.md) for the
source-wide mask/loss audit, fixed candidate families, frozen selection,
full-reference and cross-host results. Source photos and training arrays remain
external; broader quality and restored-tier approval remain open.
