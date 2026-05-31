#!/usr/bin/env python3
"""Build sidecar inputs for the Lab chroma-corrector trainer.

The source NPZ is the gate-aligned DMSR tile set:

  codec_R/G1/G2/B: (N, H, W) uint16 codec planes
  tgt_rgb:         (N, 4H, 4W, 3) uint8 target render
  src/src_lookup_names

This writes a compact sidecar NPZ with:

  y_half:          (N, H, W) uint8, VA-Y prediction area-pooled from 4H/4W
  a_naive_half:    (N, H, W) float16, Lab a from codec-only bilinear chroma
  b_naive_half:    (N, H, W) float16, Lab b from codec-only bilinear chroma
  tile_sat_score:  (N,) float32, target 95th-percentile Lab chroma

The naive chroma path intentionally uses only codec planes, not tgt_rgb, so
training inputs do not leak target color. It is an approximation of the
gate's demosaic chroma source; the exact gpr_tools/sips path remains the
future higher-fidelity sidecar if this v1 misses the PREVIEW dE gate.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from skimage import color

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from model import build as build_variant  # noqa: E402


RAW_NORM = 16383.0


def _codec_batch(npz, indices: np.ndarray, raw_norm: float) -> torch.Tensor:
    planes = [
        np.asarray(npz[k][indices], dtype=np.float32) / raw_norm
        for k in ("codec_R", "codec_G1", "codec_G2", "codec_B")
    ]
    return torch.from_numpy(np.stack(planes, axis=1))


def _load_y_model(ckpt_path: Path, device: torch.device):
    ck = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    variant = ck.get("variant", "F_ane_no_sr_w16_y")
    model = build_variant(variant)
    model.load_state_dict(ck["backbone_state"])
    model.to(device).eval()
    return model


def _codec_planes_to_naive_lab_half(r, g1, g2, b, raw_norm: float) -> tuple[np.ndarray, np.ndarray]:
    """Cheap codec-only chroma hint at plane resolution.

    The codec planes are already deinterleaved RGGB samples. Average the two
    greens, normalize to display-ish RGB, convert to Lab, and keep a/b. This
    avoids target leakage and gives the corrector a local chroma prior.

    Accepts either a single tile (H, W) or a batch (N, H, W).
    """
    rgb = np.stack([
        r.astype(np.float32),
        0.5 * (g1.astype(np.float32) + g2.astype(np.float32)),
        b.astype(np.float32),
    ], axis=-1)
    rgb = np.clip(rgb / raw_norm, 0.0, 1.0)
    lab = color.rgb2lab(rgb)
    return lab[..., 1].astype(np.float16), lab[..., 2].astype(np.float16)


def _tile_sat_score(tgt_rgb: np.ndarray) -> np.ndarray:
    """Return per-tile 95th percentile Lab chroma for RGB batch."""
    lab = color.rgb2lab(tgt_rgb.astype(np.float32) / 255.0)
    chroma = np.sqrt(lab[..., 1] * lab[..., 1] + lab[..., 2] * lab[..., 2])
    if chroma.ndim == 2:
        return np.asarray([float(np.percentile(chroma, 95))], dtype=np.float32)
    flat = chroma.reshape(chroma.shape[0], -1)
    return np.percentile(flat, 95, axis=1).astype(np.float32)


def _write_zip_stored(out_npz: Path, staging: Path) -> None:
    with zipfile.ZipFile(out_npz, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for fn in sorted(os.listdir(staging)):
            zf.write(staging / fn, arcname=fn)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-npz", required=True)
    ap.add_argument("--y-ckpt", required=True)
    ap.add_argument("--out-npz", required=True)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--raw-norm", type=float, default=RAW_NORM)
    ap.add_argument("--device", default=None, choices=[None, "cpu", "mps", "cuda"])
    args = ap.parse_args()

    in_npz = Path(args.in_npz)
    out_npz = Path(args.out_npz)
    y_ckpt = Path(args.y_ckpt)
    if not in_npz.exists():
        raise FileNotFoundError(in_npz)
    if not y_ckpt.exists():
        raise FileNotFoundError(y_ckpt)

    if args.device is None:
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    print(f"loading {in_npz}", flush=True)
    npz = np.load(in_npz, mmap_mode="r", allow_pickle=True)
    for k in ("codec_R", "codec_G1", "codec_G2", "codec_B", "tgt_rgb", "src", "src_lookup_names"):
        if k not in npz.files:
            raise RuntimeError(f"{in_npz} missing required field {k!r}")

    n, h, w = npz["codec_R"].shape
    print(f"tiles: {n}  codec plane: {h}x{w}  device={device}", flush=True)

    staging = out_npz.with_suffix(out_npz.suffix + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    y_mm = np.lib.format.open_memmap(staging / "y_half.npy", mode="w+", dtype=np.uint8, shape=(n, h, w))
    a_mm = np.lib.format.open_memmap(staging / "a_naive_half.npy", mode="w+", dtype=np.float16, shape=(n, h, w))
    b_mm = np.lib.format.open_memmap(staging / "b_naive_half.npy", mode="w+", dtype=np.float16, shape=(n, h, w))
    sat = np.lib.format.open_memmap(staging / "tile_sat_score.npy", mode="w+", dtype=np.float32, shape=(n,))

    y_model = _load_y_model(y_ckpt, device)
    t0 = time.time()
    for start in range(0, n, args.batch):
        end = min(n, start + args.batch)
        idx = np.arange(start, end)
        x = _codec_batch(npz, idx, args.raw_norm).to(device)
        with torch.no_grad():
            y_full = y_model(x).clamp(0, 1)
            y_half = F.avg_pool2d(y_full, kernel_size=4, stride=4)
        y_mm[start:end] = np.clip(
            y_half.squeeze(1).cpu().numpy() * 255.0 + 0.5, 0, 255
        ).astype(np.uint8)

        a, b = _codec_planes_to_naive_lab_half(
            np.asarray(npz["codec_R"][start:end]),
            np.asarray(npz["codec_G1"][start:end]),
            np.asarray(npz["codec_G2"][start:end]),
            np.asarray(npz["codec_B"][start:end]),
            args.raw_norm,
        )
        a_mm[start:end] = a
        b_mm[start:end] = b
        sat[start:end] = _tile_sat_score(np.asarray(npz["tgt_rgb"][start:end]))

        if start == 0 or end == n or (start // args.batch) % 25 == 0:
            print(f"  {end}/{n} tiles  t={time.time() - t0:.1f}s", flush=True)

    np.save(staging / "src.npy", np.asarray(npz["src"]))
    np.save(staging / "src_lookup_names.npy", np.asarray(npz["src_lookup_names"]), allow_pickle=True)
    (staging / "README.txt").write_text(
        "Sidecar for train_chroma_corrector.py. "
        "a_naive_half/b_naive_half are codec-only Lab hints, not target-derived.\n"
    )
    print(f"writing {out_npz}", flush=True)
    _write_zip_stored(out_npz, staging)
    shutil.rmtree(staging)
    print(f"DONE {out_npz} size={out_npz.stat().st_size / (1024 ** 2):.1f} MiB", flush=True)


if __name__ == "__main__":
    main()
