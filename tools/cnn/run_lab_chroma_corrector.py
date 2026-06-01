"""Run VA-Y plus Lab chroma-corrector inference.

This is the gate/runtime counterpart to train_chroma_corrector.py. It takes
codec-output Bayer, runs the existing VA-Y CNN for luma, builds the same
7-channel input used by the chroma trainer, then assembles RGB via Lab.

Absolute checkpoints predict Lab a/b directly. Residual checkpoints keep the
codec chroma hint as the baseline and apply only a bounded learned correction.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from skimage import color

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from model import build as build_variant  # noqa: E402


AB_NORM = 128.0


def _load_model(ckpt_path, device):
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
    planes = np.stack(
        [b[0::2, 0::2], b[0::2, 1::2], b[1::2, 0::2], b[1::2, 1::2]], 0
    ).astype(np.float32) / raw_norm
    return torch.from_numpy(planes).unsqueeze(0).to(device), planes, (eh, ew)


def _pad16(x):
    h, w = x.shape[-2:]
    ph = (16 - h % 16) % 16
    pw = (16 - w % 16) % 16
    if ph or pw:
        return F.pad(x, (0, pw, 0, ph), mode="reflect")
    return x


def _codec_planes_to_naive_ab_half(planes_chw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    r, g1, g2, b = planes_chw
    rgb = np.stack([r, 0.5 * (g1 + g2), b], axis=-1)
    lab = color.rgb2lab(np.clip(rgb, 0.0, 1.0))
    return lab[..., 1].astype(np.float32), lab[..., 2].astype(np.float32)


def _resolve_ab_prediction(raw_ab_t, a_t, b_t, ck, ab_norm: float):
    target_mode = ck.get("target_mode", "absolute")
    if target_mode == "absolute":
        return raw_ab_t
    if target_mode != "residual":
        raise RuntimeError(f"Unsupported Lab chroma target_mode {target_mode!r}")

    baseline = F.interpolate(torch.cat([a_t, b_t], dim=1), scale_factor=4, mode="bilinear", align_corners=False)
    limit = float(ck.get("residual_limit_ab", 0.0))
    residual = raw_ab_t
    if limit > 0:
        residual = residual.clamp(-limit / ab_norm, limit / ab_norm)
    return (baseline + residual).clamp(-1.0, 1.0)


def run_lab_chroma_corrector(
    bayer_u16,
    y_ckpt,
    chroma_ckpt,
    device=None,
    raw_norm=16383.0,
):
    """Return a full-resolution RGB uint8 image."""
    if device is None:
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    y_model, _ = _load_model(y_ckpt, device)
    chroma_model, ck = _load_model(chroma_ckpt, device)
    ab_norm = float(ck.get("ab_norm", AB_NORM))

    x, planes, _ = _bayer_to_4plane_tensor(bayer_u16, raw_norm, device)
    h, w = x.shape[-2:]
    with torch.no_grad():
        y_full_t = y_model(_pad16(x)).clamp(0, 1)[..., :4 * h, :4 * w]
        y_half_t = F.avg_pool2d(y_full_t, kernel_size=4, stride=4)

        a_half, b_half = _codec_planes_to_naive_ab_half(planes)
        a_t = torch.from_numpy(a_half[None, None] / ab_norm).to(device)
        b_t = torch.from_numpy(b_half[None, None] / ab_norm).to(device)
        inp = torch.cat([x, y_half_t, a_t, b_t], dim=1)
        raw_ab_t = chroma_model(_pad16(inp))[..., :4 * h, :4 * w]
        ab_t = _resolve_ab_prediction(raw_ab_t, a_t, b_t, ck, ab_norm)

    y_full = y_full_t.squeeze(0).squeeze(0).cpu().numpy()
    ab = ab_t.squeeze(0).cpu().numpy() * ab_norm

    # Convert grayscale luma prediction to Lab L. This keeps the luminance
    # transform consistent with skimage's Lab conversion used by the trainer.
    y_rgb = np.repeat(y_full[..., None], 3, axis=2)
    l_chan = color.rgb2lab(np.clip(y_rgb, 0.0, 1.0))[..., 0]
    lab = np.empty((y_full.shape[0], y_full.shape[1], 3), dtype=np.float32)
    lab[..., 0] = l_chan
    lab[..., 1] = ab[0]
    lab[..., 2] = ab[1]
    rgb = color.lab2rgb(lab)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
