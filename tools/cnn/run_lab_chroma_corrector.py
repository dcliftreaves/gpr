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
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from skimage import color
from skimage.filters import gaussian

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from model import build as build_variant  # noqa: E402


AB_NORM = 128.0


class LumaDetailCNN(torch.nn.Module):
    def __init__(self, width: int = 8):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Conv2d(1, width, 3, padding=1),
            torch.nn.SiLU(),
            torch.nn.Conv2d(width, width, 3, padding=1),
            torch.nn.SiLU(),
            torch.nn.Conv2d(width, 1, 3, padding=1),
        )

    def forward(self, x):
        return self.net(x)


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


def _display_baseline_to_ab_half(baseline_rgb_u8: np.ndarray, h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    lab = color.rgb2lab(baseline_rgb_u8.astype(np.float32) / 255.0)
    ab = torch.from_numpy(np.transpose(lab[..., 1:3].astype(np.float32), (2, 0, 1))[None])
    ab_half = F.interpolate(ab, size=(h, w), mode="area").squeeze(0).numpy()
    return ab_half[0].astype(np.float32), ab_half[1].astype(np.float32)


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


def _unsharp_luma(y: np.ndarray, amount: float, sigma: float) -> np.ndarray:
    if amount <= 0.0:
        return y
    blur = gaussian(y.astype(np.float32), sigma=sigma, preserve_range=True)
    return np.clip(y + amount * (y - blur.astype(np.float32)), 0.0, 1.0)


def _linear_detail_features(l_norm: np.ndarray, sigmas: np.ndarray) -> np.ndarray:
    feats = []
    lf = l_norm.astype(np.float32)
    for sigma in sigmas:
        blur = gaussian(lf, sigma=float(sigma), preserve_range=True)
        hp = lf - blur.astype(np.float32)
        feats.append(hp)
        feats.append(hp * np.abs(hp))
    return np.stack(feats, axis=0)


def _apply_linear_detail_luma(l_chan: np.ndarray, refiner_path: str | None) -> np.ndarray:
    if not refiner_path:
        return l_chan
    data = np.load(str(refiner_path), allow_pickle=False)
    coeffs = data["coeffs"].astype(np.float32)
    sigmas = data["sigmas"].astype(np.float32)
    strength = float(data["strength"]) if "strength" in data.files else 1.0
    limit = float(data["residual_limit"]) if "residual_limit" in data.files else 0.10
    l_norm = np.clip(l_chan.astype(np.float32) / 100.0, 0.0, 1.0)
    feats = _linear_detail_features(l_norm, sigmas)
    residual = np.tensordot(coeffs, feats, axes=(0, 0)).astype(np.float32)
    residual = np.clip(residual * strength, -limit, limit)
    return np.clip((l_norm + residual) * 100.0, 0.0, 100.0).astype(np.float32)


def _apply_cnn_detail_luma(
    l_chan: np.ndarray,
    ckpt_path: str | None,
    device,
    tile: int = 768,
    overlap: int = 32,
) -> np.ndarray:
    if not ckpt_path:
        return l_chan
    ck = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    width = int(ck.get("width", 8))
    limit = float(ck.get("residual_limit", 0.08))
    model = LumaDetailCNN(width=width)
    model.load_state_dict(ck["state_dict"])
    model.to(device).eval()

    l_norm = np.clip(l_chan.astype(np.float32) / 100.0, 0.0, 1.0)
    h, w = l_norm.shape
    out = np.zeros((h, w), dtype=np.float32)
    weight = np.zeros((h, w), dtype=np.float32)
    step = max(1, tile - 2 * overlap)
    with torch.no_grad():
        for y0 in range(0, h, step):
            for x0 in range(0, w, step):
                y1 = min(h, y0 + tile)
                x1 = min(w, x0 + tile)
                yy0 = max(0, y0 - overlap)
                xx0 = max(0, x0 - overlap)
                yy1 = min(h, y1 + overlap)
                xx1 = min(w, x1 + overlap)
                patch = l_norm[yy0:yy1, xx0:xx1]
                x = torch.from_numpy(patch[None, None]).to(device)
                residual = model(x).clamp(-limit, limit).squeeze().cpu().numpy()
                cy0 = y0 - yy0
                cx0 = x0 - xx0
                cy1 = cy0 + (y1 - y0)
                cx1 = cx0 + (x1 - x0)
                out[y0:y1, x0:x1] += residual[cy0:cy1, cx0:cx1]
                weight[y0:y1, x0:x1] += 1.0
    residual = out / np.maximum(weight, 1.0)
    return np.clip((l_norm + residual) * 100.0, 0.0, 100.0).astype(np.float32)


def run_lab_chroma_corrector(
    bayer_u16,
    y_ckpt,
    chroma_ckpt,
    baseline_rgb_u8=None,
    device=None,
    raw_norm=16383.0,
    luma_unsharp_amount=0.0,
    luma_unsharp_sigma=2.0,
    luma_detail_refiner_path=None,
    luma_detail_cnn_path=None,
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

        if baseline_rgb_u8 is None:
            a_half, b_half = _codec_planes_to_naive_ab_half(planes)
        else:
            a_half, b_half = _display_baseline_to_ab_half(baseline_rgb_u8, h, w)
        a_t = torch.from_numpy(a_half[None, None] / ab_norm).to(device)
        b_t = torch.from_numpy(b_half[None, None] / ab_norm).to(device)
        inp = torch.cat([x, y_half_t, a_t, b_t], dim=1)
        raw_ab_t = chroma_model(_pad16(inp))[..., :4 * h, :4 * w]
        ab_t = _resolve_ab_prediction(raw_ab_t, a_t, b_t, ck, ab_norm)

    y_full = y_full_t.squeeze(0).squeeze(0).cpu().numpy()
    y_full = _unsharp_luma(y_full, float(luma_unsharp_amount), float(luma_unsharp_sigma))
    ab = ab_t.squeeze(0).cpu().numpy() * ab_norm

    # Convert grayscale luma prediction to Lab L. This keeps the luminance
    # transform consistent with skimage's Lab conversion used by the trainer.
    y_rgb = np.repeat(y_full[..., None], 3, axis=2)
    l_chan = color.rgb2lab(np.clip(y_rgb, 0.0, 1.0))[..., 0]
    if luma_detail_refiner_path:
        l_chan = _apply_linear_detail_luma(l_chan, str(Path(luma_detail_refiner_path)))
    if luma_detail_cnn_path:
        l_chan = _apply_cnn_detail_luma(l_chan, str(Path(luma_detail_cnn_path)), device)
    lab = np.empty((y_full.shape[0], y_full.shape[1], 3), dtype=np.float32)
    lab[..., 0] = l_chan
    lab[..., 1] = ab[0]
    lab[..., 2] = ab[1]
    rgb = color.lab2rgb(lab)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
