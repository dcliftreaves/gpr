#!/usr/bin/env python3
"""Smoke-test the external Restormer teacher on one codec-degraded RGB tile."""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F

RAW_NORM = 16383.0


def load_restormer(root: Path, weights: Path, device: torch.device):
    arch_path = root / "basicsr/models/archs/restormer_arch.py"
    spec = importlib.util.spec_from_file_location("external_restormer_arch", arch_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Restormer arch from {arch_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    Restormer = module.Restormer

    model = Restormer(
        inp_channels=3,
        out_channels=3,
        dim=48,
        num_blocks=[4, 6, 6, 8],
        num_refinement_blocks=4,
        heads=[1, 2, 4, 8],
        ffn_expansion_factor=2.66,
        bias=False,
        LayerNorm_type="BiasFree",
        dual_pixel_task=False,
    )
    ckpt = torch.load(str(weights), map_location="cpu", weights_only=False)
    state = ckpt["params"] if isinstance(ckpt, dict) and "params" in ckpt else ckpt
    model.load_state_dict(state, strict=True)
    model.to(device).eval()
    return model


def codec_tile_to_rgb(z: np.lib.npyio.NpzFile, idx: int, out_hw: tuple[int, int]) -> np.ndarray:
    r = z["codec_R"][idx].astype(np.float32) / RAW_NORM
    g1 = z["codec_G1"][idx].astype(np.float32) / RAW_NORM
    g2 = z["codec_G2"][idx].astype(np.float32) / RAW_NORM
    b = z["codec_B"][idx].astype(np.float32) / RAW_NORM
    rgb = np.stack([r, (g1 + g2) * 0.5, b], axis=0)
    with torch.no_grad():
        up = F.interpolate(
            torch.from_numpy(rgb[None]),
            size=out_hw,
            mode="bicubic",
            align_corners=False,
        ).clamp(0, 1)
    return up.numpy()[0]


def save_rgb(path: Path, chw: np.ndarray) -> None:
    arr = np.transpose(np.clip(chw, 0.0, 1.0), (1, 2, 0))
    Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8)).save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail_t192_s96_fullref.npz"))
    ap.add_argument("--restormer-root", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/external/Restormer"))
    ap.add_argument("--weights", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/external/restormer_real_denoising.pth"))
    ap.add_argument("--out-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/restormer_teacher_smoke_20260605"))
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--tile", type=int, default=256, help="center crop size for teacher smoke")
    ap.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    args = ap.parse_args()

    if args.device == "auto":
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    z = np.load(args.npz, allow_pickle=True, mmap_mode="r")
    target = z["tgt_rgb"][args.index]
    out_hw = tuple(int(v) for v in target.shape[:2])
    degraded = codec_tile_to_rgb(z, args.index, out_hw)
    _, h, w = degraded.shape
    tile = min(args.tile, h, w)
    y0 = (h - tile) // 2
    x0 = (w - tile) // 2
    crop = degraded[:, y0:y0 + tile, x0:x0 + tile]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    save_rgb(args.out_dir / "teacher_input.png", crop)
    save_rgb(args.out_dir / "teacher_target.png", np.transpose(target[y0:y0 + tile, x0:x0 + tile], (2, 0, 1)).astype(np.float32) / 255.0)

    model = load_restormer(args.restormer_root, args.weights, device)
    x = torch.from_numpy(crop[None]).to(device)
    t0 = time.perf_counter()
    with torch.no_grad():
        pred = model(x).clamp(0, 1).cpu().numpy()[0]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    save_rgb(args.out_dir / "teacher_output.png", pred)
    print(f"device={device} tile={tile} elapsed_ms={elapsed_ms:.2f}")
    print(args.out_dir / "teacher_input.png")
    print(args.out_dir / "teacher_output.png")
    print(args.out_dir / "teacher_target.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
