# Optional stock-Q3 RGGB14 1x cleanup candidate

`selected.pt` is an explicitly selected research checkpoint for offline cleanup
after historical stock-Q3 VC-5 decoding. It uses the bundled `F_ane_no_sr`
architecture, width 16/depth 3, normalization 16383 and residual scale 0.005.
It preserves Bayer dimensions and supported source calibration. It changes
decoded counts and does not make stock compression lossless.

SHA-256: `9de03f8203f4cb1bb264087cd922b04c1b0e1169684a064d0aeb3a2a6c97f48a`.
Size: 1,312,812 bytes. No model is downloaded or selected automatically.
This file is separate from the installed camera/SDK packages.

The candidate passes the declared validation and four-reference numeric RAW
nonregression guards. On the four historical Nikon references, active-area
PSNR improves 0.328–0.854 dB; shadow, highlight and detail MSE improve on every
reference. The pooled active-area gain is 0.639 dB. The full-strength candidate
failed validation; half strength was selected using validation pixels only,
then the checkpoint was frozen before final evaluation.

This is not broader-camera, sensor-noise, rendered visual, temporal, 2x SR or
production-quality approval. The checkpoint retains `quality_approval=false`.
Its trained/evaluated domain is RGGB14 and stock Q3; other codec formats and
presets do not inherit these results. Pi replay checks use still-derived
inputs, not new lossless sensor references.
Measured backend agreement covers Torch CPU and MPS. Other backends require
explicit export and their own numeric check for this checkpoint.

From the repository root, with optional Torch/numpy/tifffile dependencies:

```sh
python3 tools/stock_still.py restore input.gpr --sample-bits 14 \
  --sdk build-runtime/source/app/gpr_tools/gpr_tools \
  --checkpoint models/stock-q3-rggb14-cleanup/selected.pt \
  --device mps --output restored.dng
```

Use `--device cpu` for CPU inference. Inputs must belong to the declared domain.
See the [study and receipts](../../docs/stock-cleanup-strength.md) for provenance,
source separation, selection criteria, measurements and remaining limits.
