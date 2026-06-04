# CNN post-processor for GPR

The GPR codec is co-designed with a CNN that corrects quantization
artifacts on the decoded Bayer plane. This directory contains the
architecture, training script, and recipe for retraining against new
codec configurations.

## Architecture

`model.py` — `BIBO_1x` (Bayer-In/Bayer-Out, 1× resolution) and `BIBO_2x`
(super-resolution variant). 4-channel-in / 4-channel-out residual UNet,
width 16, ANE-friendly (BatchNorm + SiLU). ~330K parameters total.

## Shipped checkpoints

`models/BayInBayOut_1x_AAon_w16_ANE.pt` — baseline 1× checkpoint,
trained on Z8 50 MP corpus through the **single-level FUSED q=3** codec
path. Gives +4 to +17 dB bayer-PSNR gain on natural images.

```python
import torch, sys
sys.path.append("tools/cnn")
from model import build
ckpt = torch.load("models/BayInBayOut_1x_AAon_w16_ANE.pt",
                  map_location="cpu", weights_only=False)
m = build(ckpt.get("variant", "F_ane"))
m.load_state_dict(ckpt["backbone_state"])
m.eval()
```

## Pairing with the codec

The CNN is calibrated against a SPECIFIC codec configuration. The
shipped checkpoint was trained on:

- FUSED encoder, single-level mode (`FUSED_MULTI_LEVEL=0`)
- q=3 default quantization
- Full-res output (no `GPR_COL/ROW_DECIMATE`)

It also gives positive gain on cranked-quant outputs (q=11 single-level)
because the cranked content is still in-distribution. If you ship a
materially different codec configuration (e.g. multi-level once it's
fixed, or a new quality preset), you'll want to retrain — see
`train.py` and `requirements.txt`.

## Retraining

Requires: PyTorch 2.0+ with MPS (Mac) or CUDA. See `requirements.txt`.

```bash
# Build training-pair dataset (encodes source DNGs through the codec)
# then train:
python3 tools/cnn/train.py \
    --variant F_ane_no_sr \
    --tiles /path/to/tile_pairs.npz \
    --epochs 80 --batch 32 --lr 1e-3
```

The training data layout expects NPZ pairs of (source_bayer, codec_bayer)
tiles at 128×128. The original dataset-building scripts live in
`dering_proto_v2/build_dataset_*.py` (will be migrated separately).

## Status

- Architecture and training script: **in the repo as of 2026-05-25 evening**.
- Default checkpoint: **in the repo** (1.3 MB, acceptable).
- Cranked-quant checkpoints (`BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt`,
  `BayInBayOut_1x_AAon_w16_ANE_L1L2x4.pt`): **NOT migrated** because they
  were trained against the broken multi-level codec path. Re-train once
  task #172 is fixed.

## Related docs

- `docs/methodology_cnn_aware_quant.md` — AccelIR-style co-design rationale
- `docs/REGRESSION_2026-05-25.md` — multi-level regression context (relevant
  for understanding which retrained CNNs are valid)
