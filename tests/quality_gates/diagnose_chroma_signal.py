#!/usr/bin/env python3
"""Diagnose color/chroma error in saved quality-gate crop outputs.

This is intentionally crop-based: it compares the REF/PIPELINE detail crops
already emitted by run_gate.py, so it can be run quickly across historical
gate runs without re-encoding or re-rendering full images.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color


REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "tests/quality_gates/runs"


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def psnr_from_mse(mse: float, peak: float = 1.0) -> float:
    return 99.0 if mse <= 1e-12 else 10.0 * math.log10((peak * peak) / mse)


def radial_frequency_bins(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    h, w = shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    r = np.sqrt(fx * fx + fy * fy)
    return {
        "low": r < 0.06,
        "mid": (r >= 0.06) & (r < 0.18),
        "high": r >= 0.18,
    }


def band_energy(img: np.ndarray) -> dict[str, float]:
    """Return fractional FFT energy for low/mid/high radial bands."""
    x = img.astype(np.float64) - float(np.mean(img))
    spec = np.abs(np.fft.fft2(x)) ** 2
    total = float(spec.sum())
    if total <= 1e-12:
        return {"low": 0.0, "mid": 0.0, "high": 0.0}
    bins = radial_frequency_bins(x.shape)
    return {k: float(spec[m].sum() / total) for k, m in bins.items()}


def corr(a: np.ndarray, b: np.ndarray) -> float:
    ax = a.reshape(-1).astype(np.float64)
    bx = b.reshape(-1).astype(np.float64)
    ax -= ax.mean()
    bx -= bx.mean()
    den = math.sqrt(float((ax * ax).sum() * (bx * bx).sum()))
    return 0.0 if den <= 1e-12 else float((ax * bx).sum() / den)


def metrics_for_pair(ref_rgb: np.ndarray, pipe_rgb: np.ndarray) -> dict[str, float]:
    ref_lab = color.rgb2lab(np.clip(ref_rgb, 0, 1))
    pipe_lab = color.rgb2lab(np.clip(pipe_rgb, 0, 1))
    d_lab = pipe_lab - ref_lab
    d_e = color.deltaE_ciede2000(ref_lab, pipe_lab)

    l_ref = ref_lab[..., 0]
    ab_ref = ref_lab[..., 1:3]
    l_err = d_lab[..., 0]
    ab_err = d_lab[..., 1:3]
    chroma_ref = np.sqrt(np.sum(ab_ref * ab_ref, axis=-1))
    chroma_err = np.sqrt(np.sum(ab_err * ab_err, axis=-1))

    # Hue angle error, only where reference chroma is meaningful.
    mask = chroma_ref > np.percentile(chroma_ref, 50)
    ref_h = np.arctan2(ref_lab[..., 2], ref_lab[..., 1])
    pipe_h = np.arctan2(pipe_lab[..., 2], pipe_lab[..., 1])
    hue_delta = np.angle(np.exp(1j * (pipe_h - ref_h)))

    l_energy = band_energy(l_err)
    ab_energy = band_energy(chroma_err)
    ref_ab_hf = band_energy(chroma_ref)["high"]
    pipe_chroma = np.sqrt(np.sum(pipe_lab[..., 1:3] ** 2, axis=-1))
    pipe_ab_hf = band_energy(pipe_chroma)["high"]

    return {
        "dE_mean": float(np.mean(d_e)),
        "dE_p95": float(np.percentile(d_e, 95)),
        "L_mae": float(np.mean(np.abs(l_err))),
        "ab_mae": float(np.mean(np.abs(ab_err))),
        "ab_p95": float(np.percentile(chroma_err, 95)),
        "L_psnr": psnr_from_mse(float(np.mean((l_err / 100.0) ** 2))),
        "ab_psnr": psnr_from_mse(float(np.mean((ab_err / 128.0) ** 2))),
        "ab_bias_a": float(np.mean(ab_err[..., 0])),
        "ab_bias_b": float(np.mean(ab_err[..., 1])),
        "ab_corr_a": corr(ref_lab[..., 1], pipe_lab[..., 1]),
        "ab_corr_b": corr(ref_lab[..., 2], pipe_lab[..., 2]),
        "hue_abs_deg_p95": float(np.percentile(np.abs(hue_delta[mask]) * 180.0 / math.pi, 95)),
        "Lerr_low_frac": l_energy["low"],
        "Lerr_high_frac": l_energy["high"],
        "aberr_low_frac": ab_energy["low"],
        "aberr_high_frac": ab_energy["high"],
        "chroma_hf_ratio": float(pipe_ab_hf / max(ref_ab_hf, 1e-12)),
    }


def find_crop_pairs(run_dir: Path, crop: str) -> list[tuple[str, Path, Path]]:
    pairs = []
    for ref in sorted(run_dir.glob(f"*_REF_{crop}.png")):
        image_id = ref.name.split("_REF_")[0]
        pipe = run_dir / f"{image_id}_PIPELINE_{crop}.png"
        if pipe.exists():
            pairs.append((image_id, ref, pipe))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="Run hashes under tests/quality_gates/runs")
    ap.add_argument("--crop", default="crop_A_detail")
    args = ap.parse_args()

    for run_hash in args.runs:
        run_dir = RUNS_DIR / run_hash
        meta_path = run_dir / "run.json"
        if not meta_path.exists():
            raise SystemExit(f"missing run.json for {run_hash}")
        meta = json.loads(meta_path.read_text())
        print(f"\n## {run_hash}  {meta.get('verdict')}  {meta.get('pipeline')}")
        for image_id, ref_path, pipe_path in find_crop_pairs(run_dir, args.crop):
            m = metrics_for_pair(load_rgb(ref_path), load_rgb(pipe_path))
            print(
                f"{image_id:8s} dE95={m['dE_p95']:6.2f} "
                f"Lmae={m['L_mae']:5.2f} abmae={m['ab_mae']:5.2f} "
                f"ab95={m['ab_p95']:6.2f} hue95={m['hue_abs_deg_p95']:6.1f} "
                f"abBias=({m['ab_bias_a']:+5.2f},{m['ab_bias_b']:+5.2f}) "
                f"abCorr=({m['ab_corr_a']:+.3f},{m['ab_corr_b']:+.3f}) "
                f"abErrLow/High={m['aberr_low_frac']:.2f}/{m['aberr_high_frac']:.2f} "
                f"chrHF={m['chroma_hf_ratio']:.2f}"
            )


if __name__ == "__main__":
    main()
