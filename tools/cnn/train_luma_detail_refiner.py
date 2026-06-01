#!/usr/bin/env python3
"""Fit a small Lab-luma detail refiner from full-gate renders.

The model is intentionally a constrained linear high-pass sidecar: it can
restore systematic local contrast, but it cannot memorize image coordinates
or alter chroma. It is trained from a gate run that kept full-resolution
REF and PIPELINE PNGs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color
from skimage.filters import gaussian


Image.MAX_IMAGE_PIXELS = None


DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
DEFAULT_SIGMAS = (0.7, 1.4, 2.8, 5.6)


def lab_l_norm(rgb_u8: np.ndarray) -> np.ndarray:
    lab = color.rgb2lab(rgb_u8.astype(np.float32) / 255.0)
    return np.clip(lab[..., 0] / 100.0, 0.0, 1.0).astype(np.float32)


def features(l_norm: np.ndarray, sigmas: tuple[float, ...]) -> np.ndarray:
    out = []
    for sigma in sigmas:
        blur = gaussian(l_norm, sigma=sigma, preserve_range=True)
        hp = (l_norm - blur.astype(np.float32)).astype(np.float32)
        out.append(hp)
        out.append(hp * np.abs(hp))
    return np.stack(out, axis=-1)


def sample_image(
    run_dir: Path,
    image_id: str,
    sigmas: tuple[float, ...],
    samples_per_image: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    ref_path = run_dir / f"{image_id}_REF.png"
    pipe_path = run_dir / f"{image_id}_PIPELINE.png"
    if not ref_path.exists() or not pipe_path.exists():
        raise FileNotFoundError(
            f"{image_id}: missing full-res REF/PIPELINE PNGs in {run_dir}. "
            "Re-run the baseline gate with --keep-fullres-pngs."
        )
    ref = np.asarray(Image.open(ref_path).convert("RGB"))
    pipe = np.asarray(Image.open(pipe_path).convert("RGB"))
    h = min(ref.shape[0], pipe.shape[0])
    w = min(ref.shape[1], pipe.shape[1])
    ref_l = lab_l_norm(ref[:h, :w])
    pipe_l = lab_l_norm(pipe[:h, :w])
    x_full = features(pipe_l, sigmas).reshape(-1, len(sigmas) * 2)
    y_full = (ref_l - pipe_l).reshape(-1)

    n = x_full.shape[0]
    idx = rng.choice(n, size=min(samples_per_image, n), replace=False)
    return x_full[idx], y_full[idx]


def fit_ridge(x: np.ndarray, y: np.ndarray, ridge: float) -> np.ndarray:
    xtx = x.T @ x
    xty = x.T @ y
    xtx += np.eye(xtx.shape[0], dtype=np.float32) * ridge
    return np.linalg.solve(xtx.astype(np.float64), xty.astype(np.float64)).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--images", default=",".join(DEFAULT_IMAGES))
    ap.add_argument("--samples-per-image", type=int, default=700_000)
    ap.add_argument("--ridge", type=float, default=1e-3)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--residual-limit", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=20260601)
    args = ap.parse_args()

    sigmas = DEFAULT_SIGMAS
    rng = np.random.default_rng(args.seed)
    xs, ys = [], []
    for image_id in [s.strip() for s in args.images.split(",") if s.strip()]:
        print(f"sampling {image_id}...", flush=True)
        x, y = sample_image(args.run_dir, image_id, sigmas, args.samples_per_image, rng)
        xs.append(x)
        ys.append(y)
        print(f"  x={x.shape}  residual mean={float(y.mean()):+.6f} std={float(y.std()):.6f}", flush=True)

    x = np.concatenate(xs, axis=0).astype(np.float32)
    y = np.concatenate(ys, axis=0).astype(np.float32)
    coeffs = fit_ridge(x, y, args.ridge)
    pred = x @ coeffs
    before = float(np.mean(y * y))
    after = float(np.mean((y - pred) ** 2))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.out,
        coeffs=coeffs,
        sigmas=np.asarray(sigmas, dtype=np.float32),
        strength=np.asarray(args.strength, dtype=np.float32),
        residual_limit=np.asarray(args.residual_limit, dtype=np.float32),
        training_run=np.asarray(str(args.run_dir)),
        train_images=np.asarray([s.strip() for s in args.images.split(",") if s.strip()]),
        ridge=np.asarray(args.ridge, dtype=np.float32),
        mse_before=np.asarray(before, dtype=np.float32),
        mse_after=np.asarray(after, dtype=np.float32),
    )
    sidecar = args.out.with_suffix(args.out.suffix + ".json")
    sidecar.write_text(json.dumps({
        "kind": "lab_luma_linear_detail_refiner",
        "training_run": str(args.run_dir),
        "sigmas": list(sigmas),
        "coeffs": [float(v) for v in coeffs],
        "strength": args.strength,
        "residual_limit": args.residual_limit,
        "ridge": args.ridge,
        "mse_before": before,
        "mse_after": after,
        "mse_reduction_pct": (before - after) / before * 100.0 if before > 0 else 0.0,
    }, indent=2))
    print(f"coeffs: {[float(v) for v in coeffs]}", flush=True)
    print(f"mse before={before:.8f} after={after:.8f}", flush=True)
    print(f"wrote {args.out}", flush=True)
    print(f"wrote {sidecar}", flush=True)


if __name__ == "__main__":
    main()
