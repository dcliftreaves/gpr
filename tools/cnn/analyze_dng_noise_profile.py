#!/usr/bin/env python3
"""Analyze camera-noise separation from DNG NoiseProfile tags.

The goal is to distinguish stochastic sensor noise from recoverable signal.
This script works in raw Bayer space, not rendered RGB:

1. Read DNG metadata: ISO, black/white levels, CFA pattern, NoiseProfile.
2. Convert the DNG NoiseProfile into a per-pixel sigma map in raw counts.
3. Deinterleave Bayer into R/G1/G2/B planes.
4. Run a conservative BayesShrink wavelet denoise per plane.
5. Report removed energy against the camera-predicted noise floor and how
   much removal happened on high-gradient structure.

Outputs are written outside the repo by default so large dashboards do not
land in git.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import pywt
import tifffile


DEFAULT_TEST_SET = Path("tests/quality_gates/test_set.json")
DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/noise_profile_analysis_20260604")


def number_list(value: Any) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        return [float(v) for v in value]
    return [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", str(value), re.I)]


@dataclass
class DngMeta:
    image_id: str
    path: Path
    iso: int
    black: float
    black_levels: list[float]
    white: float
    white_levels: list[float]
    noise_profile: list[float]
    cfa_pattern: list[int]
    cfa_plane_color: list[str]
    make: str
    model: str

    @property
    def white_minus_black(self) -> float:
        return self.white - self.black


def read_dng_meta(image_id: str, path: Path) -> DngMeta:
    tags = [
        "-j",
        "-n",
        "-ISO",
        "-BlackLevel",
        "-WhiteLevel",
        "-NoiseProfile",
        "-CFAPattern",
        "-CFAPlaneColor",
        "-Make",
        "-Model",
    ]
    meta = json.loads(subprocess.check_output(["exiftool", *tags, str(path)], text=True))[0]
    if "NoiseProfile" not in meta:
        raise RuntimeError(f"{path} has no DNG NoiseProfile tag")
    cfa = [int(v) for v in number_list(meta.get("CFAPattern", ""))]
    if len(cfa) >= 6 and cfa[:2] == [2, 2]:
        cfa = cfa[2:6]
    if cfa != [0, 1, 1, 2]:
        raise RuntimeError(
            f"{path} has unsupported CFA pattern {cfa}; this analyzer currently expects RGGB"
        )
    cfa_plane_color = [part.strip() for part in re.split(r"[,\s]+", str(meta.get("CFAPlaneColor", ""))) if part.strip()]
    if cfa_plane_color and cfa_plane_color[:3] not in (["Red", "Green", "Blue"], ["0", "1", "2"]):
        raise RuntimeError(
            f"{path} has unsupported CFAPlaneColor {cfa_plane_color}; expected Red,Green,Blue"
        )
    black_levels = number_list(meta["BlackLevel"])
    white_levels = number_list(meta["WhiteLevel"])
    return DngMeta(
        image_id=image_id,
        path=path,
        iso=int(number_list(meta["ISO"])[0]),
        black=float(np.mean(black_levels)),
        black_levels=black_levels,
        white=float(np.mean(white_levels)),
        white_levels=white_levels,
        noise_profile=number_list(meta["NoiseProfile"]),
        cfa_pattern=cfa,
        cfa_plane_color=cfa_plane_color,
        make=str(meta.get("Make", "")),
        model=str(meta.get("Model", "")),
    )


def read_bayer(path: Path) -> np.ndarray:
    with tifffile.TiffFile(path) as tf:
        candidates: list[Any] = []
        for page in tf.pages:
            if len(page.shape) == 2 and np.issubdtype(page.dtype, np.integer):
                candidates.append(page)
            for subpage in getattr(page, "pages", []):
                if len(subpage.shape) == 2 and np.issubdtype(subpage.dtype, np.integer):
                    candidates.append(subpage)
        if not candidates:
            raise RuntimeError(f"{path} has no 2D integer raw image IFD")
        page = max(candidates, key=lambda p: int(p.shape[0]) * int(p.shape[1]))
        return page.asarray().astype(np.float32)


def noise_sigma_map(raw: np.ndarray, meta: DngMeta) -> np.ndarray:
    """Return per-pixel DNG NoiseProfile sigma in raw counts."""
    if len(meta.noise_profile) < 6:
        raise RuntimeError(f"expected 6 NoiseProfile values, got {meta.noise_profile}")
    black = np.full_like(raw, meta.black, dtype=np.float32)
    if len(meta.black_levels) == 4:
        black[0::2, 0::2] = meta.black_levels[0]
        black[0::2, 1::2] = meta.black_levels[1]
        black[1::2, 0::2] = meta.black_levels[2]
        black[1::2, 1::2] = meta.black_levels[3]
    elif len(meta.black_levels) != 1:
        raise RuntimeError(f"unsupported BlackLevel shape: {meta.black_levels}")
    white = np.full_like(raw, meta.white, dtype=np.float32)
    if len(meta.white_levels) == 4:
        white[0::2, 0::2] = meta.white_levels[0]
        white[0::2, 1::2] = meta.white_levels[1]
        white[1::2, 0::2] = meta.white_levels[2]
        white[1::2, 1::2] = meta.white_levels[3]
    elif len(meta.white_levels) != 1:
        raise RuntimeError(f"unsupported WhiteLevel shape: {meta.white_levels}")
    raw_range = white - black
    norm = np.clip((raw - black) / np.maximum(raw_range, 1.0), 0.0, 1.0)
    out = np.zeros_like(norm, dtype=np.float32)
    # DNG stores three (scale, offset) variance pairs for R, G, B.
    pairs = {
        "R": meta.noise_profile[0:2],
        "G": meta.noise_profile[2:4],
        "B": meta.noise_profile[4:6],
    }

    def fill(view: np.ndarray, pair: list[float]) -> np.ndarray:
        a, b = pair
        return np.sqrt(np.maximum(a * view + b, 0.0))

    out[0::2, 0::2] = fill(norm[0::2, 0::2], pairs["R"]) * raw_range[0::2, 0::2]
    out[0::2, 1::2] = fill(norm[0::2, 1::2], pairs["G"]) * raw_range[0::2, 1::2]
    out[1::2, 0::2] = fill(norm[1::2, 0::2], pairs["G"]) * raw_range[1::2, 0::2]
    out[1::2, 1::2] = fill(norm[1::2, 1::2], pairs["B"]) * raw_range[1::2, 1::2]
    return out


def deinterleave(arr: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "R": arr[0::2, 0::2],
        "G1": arr[0::2, 1::2],
        "G2": arr[1::2, 0::2],
        "B": arr[1::2, 1::2],
    }


def interleave(ch: dict[str, np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    out = np.zeros(shape, dtype=np.float32)
    out[0::2, 0::2] = ch["R"]
    out[0::2, 1::2] = ch["G1"]
    out[1::2, 0::2] = ch["G2"]
    out[1::2, 1::2] = ch["B"]
    return out


def bayes_denoise_plane(
    plane: np.ndarray,
    sigma_plane: np.ndarray,
    *,
    wavelet: str,
    levels: int,
    threshold_scale: float,
    max_threshold_sigma: float,
) -> tuple[np.ndarray, list[dict[str, float]]]:
    coeffs = pywt.wavedec2(plane, wavelet=wavelet, mode="periodization", level=levels)
    sigma = float(np.median(sigma_plane))
    out_coeffs: list[Any] = [coeffs[0]]
    stats: list[dict[str, float]] = []
    for level_index, detail in enumerate(coeffs[1:], start=1):
        denoised_detail = []
        for band_name, band in zip(("LH", "HL", "HH"), detail):
            band_var = float(np.var(band))
            signal_var = max(band_var - sigma * sigma, 1e-6)
            bayes = sigma * sigma / math.sqrt(signal_var)
            threshold = min(bayes * threshold_scale, max_threshold_sigma * sigma)
            threshold = max(threshold, 0.0)
            denoised = pywt.threshold(band, threshold, mode="soft")
            denoised_detail.append(denoised)
            stats.append({
                "level": float(level_index),
                "band": band_name,
                "band_rms": float(np.sqrt(np.mean(band * band))),
                "threshold_counts": float(threshold),
                "sigma_counts": sigma,
                "zeroed_frac": float(np.mean(np.abs(denoised) < 1e-6)),
            })
        out_coeffs.append(tuple(denoised_detail))
    rec = pywt.waverec2(out_coeffs, wavelet=wavelet, mode="periodization")
    return rec[: plane.shape[0], : plane.shape[1]].astype(np.float32), stats


def gradient_mask(raw_crop: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(raw_crop.astype(np.float32))
    mag = np.sqrt(gx * gx + gy * gy)
    cutoff = float(np.percentile(mag, 75.0))
    return mag >= cutoff


def local_activity_mask(raw_crop: np.ndarray, percentile: float) -> np.ndarray:
    gy, gx = np.gradient(raw_crop.astype(np.float32))
    mag = np.sqrt(gx * gx + gy * gy)
    return mag <= float(np.percentile(mag, percentile))


def lag1_corr(arr: np.ndarray, axis: int) -> float:
    centered = arr - float(np.mean(arr))
    if axis == 0:
        a = centered[:-1, :]
        b = centered[1:, :]
    else:
        a = centered[:, :-1]
        b = centered[:, 1:]
    denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
    if denom <= 1e-9:
        return 0.0
    return float(np.sum(a * b) / denom)


def wavelet_highpass(arr: np.ndarray, wavelet: str) -> np.ndarray:
    coeffs = pywt.wavedec2(arr, wavelet, mode="periodization", level=1)
    zero_detail = tuple(np.zeros_like(band) for band in coeffs[1])
    lowpass = pywt.waverec2([coeffs[0], zero_detail], wavelet, mode="periodization")
    return arr - lowpass[: arr.shape[0], : arr.shape[1]]


def rms(arr: np.ndarray) -> float:
    return float(np.sqrt(np.mean(arr * arr)))


def plane_validation_stats(
    raw_ch: dict[str, np.ndarray],
    sigma_ch: dict[str, np.ndarray],
    removed_ch: dict[str, np.ndarray],
    *,
    wavelet: str,
) -> dict[str, Any]:
    flat_hf_energy = 0.0
    flat_hf_sigma_energy = 0.0
    flat_removed_energy = 0.0
    flat_removed_sigma_energy = 0.0
    edge_removed_energy = 0.0
    edge_pixels = 0
    nonedge_removed_energy = 0.0
    nonedge_pixels = 0
    lag_x: list[float] = []
    lag_y: list[float] = []
    per_plane: dict[str, dict[str, float]] = {}

    for ch_name, plane in raw_ch.items():
        sigma = sigma_ch[ch_name]
        removed = removed_ch[ch_name]
        flat = local_activity_mask(plane, 25.0)
        edge = ~local_activity_mask(plane, 75.0)
        hf = wavelet_highpass(plane, wavelet)

        flat_hf = hf[flat]
        flat_sigma = sigma[flat]
        flat_removed = removed[flat]
        plane_lag_x = lag1_corr(removed, axis=1)
        plane_lag_y = lag1_corr(removed, axis=0)
        edge_energy = float(np.sum((removed * removed)[edge]))
        nonedge_energy = float(np.sum((removed * removed)[~edge]))
        edge_count = int(np.sum(edge))
        nonedge_count = int(np.sum(~edge))

        flat_hf_energy += float(np.sum(flat_hf * flat_hf))
        flat_hf_sigma_energy += float(np.sum(flat_sigma * flat_sigma))
        flat_removed_energy += float(np.sum(flat_removed * flat_removed))
        flat_removed_sigma_energy += float(np.sum(flat_sigma * flat_sigma))
        edge_removed_energy += edge_energy
        edge_pixels += edge_count
        nonedge_removed_energy += nonedge_energy
        nonedge_pixels += nonedge_count
        lag_x.append(plane_lag_x)
        lag_y.append(plane_lag_y)
        per_plane[ch_name] = {
            "flat_raw_hf_to_sigma_rms": rms(flat_hf) / max(rms(flat_sigma), 1e-9),
            "flat_removed_to_sigma_rms": rms(flat_removed) / max(rms(flat_sigma), 1e-9),
            "removed_lag1_corr_x": plane_lag_x,
            "removed_lag1_corr_y": plane_lag_y,
            "edge_removed_energy_ratio": (edge_energy / max(edge_count, 1)) / max(nonedge_energy / max(nonedge_count, 1), 1e-9),
        }

    return {
        "flat_raw_hf_to_sigma_rms": math.sqrt(flat_hf_energy / max(flat_hf_sigma_energy, 1e-9)),
        "flat_removed_to_sigma_rms": math.sqrt(flat_removed_energy / max(flat_removed_sigma_energy, 1e-9)),
        "removed_lag1_corr_x_mean": float(np.mean(lag_x)),
        "removed_lag1_corr_y_mean": float(np.mean(lag_y)),
        "removed_lag1_corr_x_max_abs": float(np.max(np.abs(lag_x))),
        "removed_lag1_corr_y_max_abs": float(np.max(np.abs(lag_y))),
        "edge_pixel_frac": edge_pixels / max(edge_pixels + nonedge_pixels, 1),
        "edge_removed_energy_frac": edge_removed_energy / max(edge_removed_energy + nonedge_removed_energy, 1e-9),
        "edge_removed_energy_ratio": (edge_removed_energy / max(edge_pixels, 1)) / max(
            nonedge_removed_energy / max(nonedge_pixels, 1), 1e-9
        ),
        "per_plane": per_plane,
    }


def save_u8(path: Path, arr: np.ndarray, *, lo: float, hi: float) -> None:
    u8 = np.clip((arr - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    Image.fromarray((u8 * 255.0).astype(np.uint8)).save(path)


def analyze_crop(
    image_id: str,
    raw: np.ndarray,
    sigma: np.ndarray,
    meta: DngMeta,
    crop_name: str,
    crop: dict[str, int],
    out_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    x, y, w, h = (int(crop[k]) for k in ("x", "y", "w", "h"))
    # Keep crop aligned to a 2x2 CFA block.
    x -= x % 2
    y -= y % 2
    w -= w % 2
    h -= h % 2
    raw_crop = raw[y:y + h, x:x + w]
    sigma_crop = sigma[y:y + h, x:x + w]

    denoised_ch: dict[str, np.ndarray] = {}
    wavelet_stats: list[dict[str, Any]] = []
    raw_ch = deinterleave(raw_crop)
    sigma_ch = deinterleave(sigma_crop)
    for ch_name, plane in raw_ch.items():
        denoised, ch_stats = bayes_denoise_plane(
            plane,
            sigma_ch[ch_name],
            wavelet=args.wavelet,
            levels=args.levels,
            threshold_scale=args.threshold_scale,
            max_threshold_sigma=args.max_threshold_sigma,
        )
        denoised_ch[ch_name] = denoised
        for row in ch_stats:
            row["channel"] = ch_name
        wavelet_stats.extend(ch_stats)

    denoised_crop = interleave(denoised_ch, raw_crop.shape)
    removed = raw_crop - denoised_crop
    removed_ch = deinterleave(removed)
    plane_stats = plane_validation_stats(raw_ch, sigma_ch, removed_ch, wavelet=args.wavelet)
    removed_energy = float(np.mean(removed * removed))
    raw_hf = interleave({ch: wavelet_highpass(plane, args.wavelet) for ch, plane in raw_ch.items()}, raw_crop.shape)
    sigma_rms = float(np.sqrt(np.mean(sigma_crop * sigma_crop)))
    whitened_removed = removed / np.maximum(sigma_crop, 1e-6)

    crop_dir = out_dir / image_id
    crop_dir.mkdir(parents=True, exist_ok=True)
    base = f"{image_id}_{crop_name}"
    save_u8(crop_dir / f"{base}_raw.png", raw_crop, lo=meta.black, hi=np.percentile(raw_crop, 99.5))
    save_u8(crop_dir / f"{base}_denoised.png", denoised_crop, lo=meta.black, hi=np.percentile(raw_crop, 99.5))
    save_u8(crop_dir / f"{base}_removed_x8.png", removed * args.residual_gain + 128.0, lo=0.0, hi=255.0)
    save_u8(crop_dir / f"{base}_sigma.png", sigma_crop, lo=0.0, hi=np.percentile(sigma_crop, 99.5))

    return {
        "image_id": image_id,
        "crop": crop_name,
        "iso": meta.iso,
        "path": str(meta.path),
        "black": meta.black,
        "white": meta.white,
        "noise_profile": meta.noise_profile,
        "sigma_counts_median": float(np.median(sigma_crop)),
        "sigma_counts_rms": sigma_rms,
        "sigma_counts_p90": float(np.percentile(sigma_crop, 90)),
        "raw_hf_rms_counts": float(np.sqrt(np.mean(raw_hf * raw_hf))),
        "flat_raw_hf_to_sigma_rms": plane_stats["flat_raw_hf_to_sigma_rms"],
        "removed_rms_counts": float(np.sqrt(removed_energy)),
        "removed_to_sigma_rms": float(np.sqrt(removed_energy) / max(sigma_rms, 1e-9)),
        "flat_removed_to_sigma_rms": plane_stats["flat_removed_to_sigma_rms"],
        "whitened_removed_rms": float(np.sqrt(np.mean(whitened_removed * whitened_removed))),
        "removed_lag1_corr_x": plane_stats["removed_lag1_corr_x_mean"],
        "removed_lag1_corr_y": plane_stats["removed_lag1_corr_y_mean"],
        "removed_lag1_corr_x_max_abs": plane_stats["removed_lag1_corr_x_max_abs"],
        "removed_lag1_corr_y_max_abs": plane_stats["removed_lag1_corr_y_max_abs"],
        "removed_energy_frac": float(removed_energy / max(np.mean((raw_crop - np.mean(raw_crop)) ** 2), 1e-9)),
        "edge_pixel_frac": plane_stats["edge_pixel_frac"],
        "edge_removed_energy_frac": plane_stats["edge_removed_energy_frac"],
        "edge_removed_energy_ratio": plane_stats["edge_removed_energy_ratio"],
        "per_plane_validation": plane_stats["per_plane"],
        "wavelet_stats": wavelet_stats,
        "artifacts": {
            "raw": str(crop_dir / f"{base}_raw.png"),
            "denoised": str(crop_dir / f"{base}_denoised.png"),
            "removed_x8": str(crop_dir / f"{base}_removed_x8.png"),
            "sigma": str(crop_dir / f"{base}_sigma.png"),
        },
    }


def build_html(rows: list[dict[str, Any]], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.4f}"
        return escape(str(v))

    html = [
        "<!doctype html><meta charset='utf-8'><title>DNG Noise Profile Analysis</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}"
        ".card{border:1px solid #d8dee6;border-radius:8px;padding:10px;background:white}img{width:100%;height:auto;background:#111}</style>",
        "<h1>DNG Noise Profile Analysis</h1>",
        "<p>Analytic raw-domain noise separation from DNG NoiseProfile. Residual images are amplified.</p>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>sigma median</th><th>sigma rms</th>"
        "<th>raw HF rms</th><th>flat HF/sigma</th><th>removed rms</th><th>removed/sigma</th><th>flat removed/sigma</th>"
        "<th>whitened removed</th><th>lag1 mean x/y</th><th>lag1 max abs x/y</th>"
        "<th>removed energy frac</th><th>edge energy ratio</th></tr></thead><tbody>",
    ]
    for row in rows:
        html.append("<tr>" + "".join(
            f"<td>{fmt(v)}</td>" for v in [
                row["image_id"],
                row["crop"],
                row["iso"],
                row["sigma_counts_median"],
                row["sigma_counts_rms"],
                row["raw_hf_rms_counts"],
                row["flat_raw_hf_to_sigma_rms"],
                row["removed_rms_counts"],
                row["removed_to_sigma_rms"],
                row["flat_removed_to_sigma_rms"],
                row["whitened_removed_rms"],
                f"{row['removed_lag1_corr_x']:.3f}/{row['removed_lag1_corr_y']:.3f}",
                f"{row['removed_lag1_corr_x_max_abs']:.3f}/{row['removed_lag1_corr_y_max_abs']:.3f}",
                row["removed_energy_frac"],
                row["edge_removed_energy_ratio"],
            ]
        ) + "</tr>")
    html.append("</tbody></table><div class='grid'>")
    for row in rows:
        html.append(f"<div class='card'><h3>{escape(row['image_id'])} {escape(row['crop'])}</h3>")
        for label, path in row["artifacts"].items():
            rel = Path(path).relative_to(out.parent)
            html.append(f"<p>{escape(label)}</p><img src='{escape(str(rel))}'>")
        html.append("</div>")
    html.append("</div>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-set", type=Path, default=DEFAULT_TEST_SET)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--images", nargs="*", default=["Z8Z_5323", "Z8Z_6693"])
    ap.add_argument("--crops", nargs="*", default=["A_detail", "B_center", "C_lowerleft"])
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=2)
    ap.add_argument("--threshold-scale", type=float, default=0.85)
    ap.add_argument("--max-threshold-sigma", type=float, default=1.25)
    ap.add_argument("--residual-gain", type=float, default=8.0)
    args = ap.parse_args()

    test_set = json.loads(args.test_set.read_text())
    image_map = {row["id"]: row for row in test_set["images"]}
    crop_map = test_set["crops"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for image_id in args.images:
        image = image_map[image_id]
        path = Path(image["path"])
        meta = read_dng_meta(image_id, path)
        raw = read_bayer(path)
        sigma = noise_sigma_map(raw, meta)
        for crop_name in args.crops:
            rows.append(analyze_crop(image_id, raw, sigma, meta, crop_name, crop_map[crop_name], args.out_dir, args))

    summary = {
        "args": vars(args) | {"test_set": str(args.test_set), "out_dir": str(args.out_dir)},
        "rows": rows,
    }
    json_path = args.out_dir / "noise_profile_analysis.json"
    html_path = args.out_dir / "noise_profile_analysis.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(rows, html_path)
    print(json_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
