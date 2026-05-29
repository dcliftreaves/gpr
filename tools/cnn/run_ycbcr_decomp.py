"""Run the YCbCr per-channel decomposition pipeline (Variant A):

  Bayer (4ch half-res) ─┬─ Y_CNN   → Y  (4x spatial)
                        ├─ Cb_CNN  → Cb (4x spatial)
                        └─ Cr_CNN  → Cr (4x spatial)
  inverse BT.709 → RGB (4x spatial)

Module exposes `run_ycbcr_decomp(bayer_uint16, y_ckpt, cb_ckpt, cr_ckpt,
device=..., raw_norm=16383.0)` returning a (H4, W4, 3) uint8 RGB image.

CLI:
  python3 tools/cnn/run_ycbcr_decomp.py \
      --bayer-raw <path> --w <W> --h <H> \
      --y-ckpt models/F_ane_no_sr_w16_y.pt \
      --cb-ckpt models/F_ane_no_sr_w8_chroma_cb.pt \
      --cr-ckpt models/F_ane_no_sr_w8_chroma_cr.pt \
      --out out.png
"""
from __future__ import annotations
import argparse
import sys
import os

import numpy as np
import torch
import torch.nn.functional as F

# BT.709 inverse (YCbCr → RGB). Inverse of the matrix in train_ycbcr_channel.py.
# Pre-computed once so inference is fast.
_BT709_M = np.array([
    [0.2126,  0.7152,  0.0722],
    [-0.1146, -0.3854, 0.5000],
    [0.5000, -0.4542, -0.0458],
], dtype=np.float32)
_BT709_OFFSET = np.array([0.0, 0.5, 0.5], dtype=np.float32)
_BT709_M_INV = np.linalg.inv(_BT709_M).astype(np.float32)


def ycbcr_to_rgb_chw(ycc_chw: np.ndarray) -> np.ndarray:
    """Input (3, H, W) YCbCr in [0, 1] → (3, H, W) RGB in [0, 1]."""
    flat = ycc_chw.reshape(3, -1).T  # (HW, 3)
    rgb = (flat - _BT709_OFFSET) @ _BT709_M_INV.T
    return rgb.T.reshape(3, ycc_chw.shape[1], ycc_chw.shape[2])


def _load_model(ckpt_path, device):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from model import build as build_variant
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    variant = ck.get("variant")
    if variant is None:
        raise RuntimeError(f"Checkpoint {ckpt_path} has no 'variant' field")
    m = build_variant(variant)
    m.load_state_dict(ck["backbone_state"])
    m.to(device).eval()
    return m, ck


def _bayer_to_4plane_tensor(bayer_u16: np.ndarray, raw_norm: float, device):
    h, w = bayer_u16.shape
    eh, ew = h - (h & 1), w - (w & 1)
    b = bayer_u16[:eh, :ew]
    pl = np.stack(
        [b[0::2, 0::2], b[0::2, 1::2], b[1::2, 0::2], b[1::2, 1::2]], 0
    )
    x = torch.from_numpy(pl.astype(np.float32) / raw_norm).unsqueeze(0).to(device)
    return x, (eh, ew)


def _run_one_channel(model, x):
    """Forward + clamp + crop padded edges. Returns (1, 1, 4*Hp, 4*Wp) tensor."""
    H, W = x.shape[-2:]
    ph = (16 - H % 16) % 16
    pw = (16 - W % 16) % 16
    if ph or pw:
        x_p = F.pad(x, (0, pw, 0, ph), mode="reflect")
    else:
        x_p = x
    with torch.no_grad():
        y = model(x_p).clamp(0, 1)
    # Crop padding (4x scale).
    return y[..., :4 * H, :4 * W]


def run_ycbcr_decomp(bayer_u16, y_ckpt, cb_ckpt, cr_ckpt,
                     device=None, raw_norm=16383.0):
    """Run the three CNNs + BT.709 recombine. Returns (4*H_e, 4*W_e, 3) uint8."""
    if device is None:
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    y_m, _ = _load_model(y_ckpt, device)
    cb_m, _ = _load_model(cb_ckpt, device)
    cr_m, _ = _load_model(cr_ckpt, device)
    x, (eh, ew) = _bayer_to_4plane_tensor(bayer_u16, raw_norm, device)
    y_out = _run_one_channel(y_m, x)
    cb_out = _run_one_channel(cb_m, x)
    cr_out = _run_one_channel(cr_m, x)
    # (1, 1, 4H, 4W) each → (3, 4H, 4W)
    ycc = torch.cat([y_out, cb_out, cr_out], dim=1).squeeze(0).cpu().numpy()
    rgb = ycbcr_to_rgb_chw(ycc)
    rgb = np.transpose(rgb, (1, 2, 0))  # (H', W', 3)
    rgb_u8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    return rgb_u8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bayer-raw", required=True,
                    help="Raw uint16 bayer file (W*H*2 bytes, RGGB).")
    ap.add_argument("--w", type=int, required=True)
    ap.add_argument("--h", type=int, required=True)
    ap.add_argument("--y-ckpt", required=True)
    ap.add_argument("--cb-ckpt", required=True)
    ap.add_argument("--cr-ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-norm", type=float, default=16383.0)
    args = ap.parse_args()
    bayer = np.fromfile(args.bayer_raw, dtype=np.uint16).reshape(args.h, args.w)
    rgb = run_ycbcr_decomp(bayer, args.y_ckpt, args.cb_ckpt, args.cr_ckpt,
                           raw_norm=args.raw_norm)
    from PIL import Image
    Image.fromarray(rgb).save(args.out)
    print(f"Wrote {args.out}  shape={rgb.shape}")


if __name__ == "__main__":
    main()
