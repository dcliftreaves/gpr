#!/usr/bin/env python3
"""Build conservative raw clean-signal targets from DNG NoiseProfile metadata.

This is a target-builder, not a perceptual denoiser. It removes only the part
of a raw CFA crop that is both consistent with the camera-predicted noise floor
and weakly supported by same-plane image structure. The exact removed residual
is saved as a sidecar so evaluation can add it back before comparing against
the original REF.
"""
from __future__ import annotations

import argparse
import json
import math
from html import escape
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pywt

from analyze_dng_noise_profile import (
    DEFAULT_TEST_SET,
    bayes_denoise_plane,
    deinterleave,
    interleave,
    noise_sigma_map,
    plane_validation_stats,
    read_bayer,
    read_dng_meta,
    save_u8,
    wavelet_highpass,
)


DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604")
DEFAULT_IMAGES = ["Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693"]


def norm_support(x: np.ndarray, percentile: float) -> np.ndarray:
    x = np.maximum(x.astype(np.float32), 0.0)
    scale = float(np.percentile(x, percentile))
    if scale <= 1e-8:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip(x / scale, 0.0, 1.0).astype(np.float32)


def blur(x: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.0:
        return x.astype(np.float32)
    return cv2.GaussianBlur(x.astype(np.float32), (0, 0), sigma).astype(np.float32)


def selected_hf(plane: np.ndarray, wavelet: str, levels: int, hf_levels: int) -> np.ndarray:
    coeffs = pywt.wavedec2(plane.astype(np.float32), wavelet, mode="periodization", level=levels)
    out: list[Any] = [np.zeros_like(coeffs[0])]
    first_selected = max(1, len(coeffs) - hf_levels)
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_selected:
            out.append(detail)
        else:
            out.append(tuple(np.zeros_like(band) for band in detail))
    rec = pywt.waverec2(out, wavelet, mode="periodization")
    return rec[: plane.shape[0], : plane.shape[1]].astype(np.float32)


def gradient_support(plane: np.ndarray, wavelet: str) -> np.ndarray:
    low = plane - wavelet_highpass(plane, wavelet)
    gx = cv2.Sobel(low.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(low.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    return norm_support(blur(np.sqrt(gx * gx + gy * gy), 1.0), 95.0)


def signed_local_coherence(hf: np.ndarray) -> np.ndarray:
    numerator = np.abs(blur(hf, 1.0))
    denominator = blur(np.abs(hf), 1.0) + 1e-6
    return np.clip(numerator / denominator, 0.0, 1.0).astype(np.float32)


def decorrelate_residual(
    residual: np.ndarray,
    plane: np.ndarray,
    sigma: np.ndarray,
    edge: np.ndarray,
    finest: np.ndarray,
    coarser: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, dict[str, float]]:
    """Remove linear signal-correlated components from whitened residual.

    True stochastic sensor noise may be heteroscedastic, but after dividing by
    the DNG sigma map it should not carry a predictable component from local
    signal level or edge support. This projection is deliberately simple and
    auditable: fit z=residual/sigma against normalized lowpass intensity and
    gradient support, subtract that fit, then convert back to raw counts.
    """
    if not args.decorrelate_residual:
        return residual.astype(np.float32), {
            "decorrelation_beta_offset": 0.0,
            "decorrelation_beta_signal": 0.0,
            "decorrelation_beta_gradient": 0.0,
            "decorrelation_beta_finest": 0.0,
            "decorrelation_beta_coarser": 0.0,
            "decorrelation_removed_rms": 0.0,
        }

    sigma_safe = np.maximum(sigma.astype(np.float32), 1e-6)
    z = residual.astype(np.float32) / sigma_safe
    signal = blur(plane, args.decorrelate_signal_blur)
    signal = (signal - float(np.mean(signal))) / max(float(np.std(signal)), 1e-6)
    grad = (edge.astype(np.float32) - float(np.mean(edge))) / max(float(np.std(edge)), 1e-6)

    predictors = [np.ones_like(z, dtype=np.float32), signal.astype(np.float32)]
    if args.decorrelate_gradient:
        predictors.append(grad.astype(np.float32))
    if args.decorrelate_highpass:
        finest_z = finest.astype(np.float32) / sigma_safe
        finest_z = (finest_z - float(np.mean(finest_z))) / max(float(np.std(finest_z)), 1e-6)
        coarser_z = coarser.astype(np.float32) / sigma_safe
        coarser_z = (coarser_z - float(np.mean(coarser_z))) / max(float(np.std(coarser_z)), 1e-6)
        predictors.extend([finest_z.astype(np.float32), coarser_z.astype(np.float32)])
    x = np.stack([p.ravel() for p in predictors], axis=1).astype(np.float64)
    y = z.ravel().astype(np.float64)
    xtx = x.T @ x
    xtx += np.eye(xtx.shape[0], dtype=np.float64) * args.decorrelate_ridge
    beta = np.linalg.solve(xtx, x.T @ y)
    fitted = (x @ beta).reshape(z.shape).astype(np.float32)
    z_out = z - fitted
    out = z_out * sigma_safe
    idx = 2
    beta_gradient = 0.0
    if args.decorrelate_gradient:
        beta_gradient = float(beta[idx])
        idx += 1
    beta_finest = 0.0
    beta_coarser = 0.0
    if args.decorrelate_highpass:
        beta_finest = float(beta[idx])
        beta_coarser = float(beta[idx + 1])
    return out.astype(np.float32), {
        "decorrelation_beta_offset": float(beta[0]),
        "decorrelation_beta_signal": float(beta[1]) if len(beta) > 1 else 0.0,
        "decorrelation_beta_gradient": beta_gradient,
        "decorrelation_beta_finest": beta_finest,
        "decorrelation_beta_coarser": beta_coarser,
        "decorrelation_removed_rms": float(np.sqrt(np.mean((fitted * sigma_safe) ** 2))),
    }


def residual_lag_max_abs(removed_ch: dict[str, np.ndarray]) -> float:
    values: list[float] = []
    for plane in removed_ch.values():
        centered = plane - float(np.mean(plane))
        for axis in (0, 1):
            if axis == 0:
                a, b = centered[:-1, :], centered[1:, :]
            else:
                a, b = centered[:, :-1], centered[:, 1:]
            denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
            values.append(0.0 if denom <= 1e-9 else float(np.sum(a * b) / denom))
    return float(np.max(np.abs(values))) if values else 0.0


def corr(a: np.ndarray, b: np.ndarray) -> float:
    aa = a.astype(np.float64).ravel()
    bb = b.astype(np.float64).ravel()
    aa -= float(np.mean(aa))
    bb -= float(np.mean(bb))
    denom = math.sqrt(float(np.dot(aa, aa)) * float(np.dot(bb, bb)))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(aa, bb) / denom)


def absres_gradient_corr_max(
    raw_ch: dict[str, np.ndarray],
    residual_ch: dict[str, np.ndarray],
) -> float:
    values: list[float] = []
    for ch_name, plane in raw_ch.items():
        low = cv2.GaussianBlur(plane.astype(np.float32), (0, 0), 1.0)
        gx = cv2.Sobel(low, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(low, cv2.CV_32F, 0, 1, ksize=3)
        grad = np.sqrt(gx * gx + gy * gy).astype(np.float32)
        scale = float(np.percentile(grad, 95.0))
        grad_norm = grad / max(scale, 1e-6)
        values.append(abs(corr(np.abs(residual_ch[ch_name]), grad_norm)))
    return float(max(values)) if values else 0.0


def contract_failure_reasons(
    raw_ch: dict[str, np.ndarray],
    residual_ch: dict[str, np.ndarray],
    sigma_ch: dict[str, np.ndarray],
    validation: dict[str, Any],
    residual_to_sigma_rms: float,
    args: argparse.Namespace,
) -> list[str]:
    max_residual_sigma = 0.0
    for ch_name, residual in residual_ch.items():
        max_residual_sigma = max(
            max_residual_sigma,
            float(np.max(np.abs(residual) / np.maximum(sigma_ch[ch_name], 1e-6))),
        )
    reasons: list[str] = []
    if max_residual_sigma > args.contract_max_residual_sigma + 1e-5:
        reasons.append("max_residual_sigma")
    if residual_to_sigma_rms > args.contract_max_rms_residual_sigma:
        reasons.append("rms_residual_sigma")
    if residual_lag_max_abs(residual_ch) > args.contract_max_lag_abs:
        reasons.append("lag")
    if validation["edge_removed_energy_ratio"] > args.contract_max_edge_ratio:
        reasons.append("edge_ratio")
    if absres_gradient_corr_max(raw_ch, residual_ch) > args.contract_max_abs_gradient_corr:
        reasons.append("gradient_corr")
    return reasons


def clean_plane(
    plane: np.ndarray,
    sigma: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, float]]:
    denoised, _ = bayes_denoise_plane(
        plane,
        sigma,
        wavelet=args.wavelet,
        levels=args.levels,
        threshold_scale=args.threshold_scale,
        max_threshold_sigma=args.max_threshold_sigma,
    )
    candidate_residual = plane - denoised
    sigma_safe = np.maximum(sigma, 1e-6)

    edge = gradient_support(plane, args.wavelet)
    finest = selected_hf(plane, args.wavelet, max(args.structure_levels, 1), 1)
    two_level = selected_hf(plane, args.wavelet, max(args.structure_levels, 2), min(2, args.structure_levels))
    coarser = two_level - finest
    cross = norm_support(blur(np.abs(coarser), 1.2), 95.0)
    coherence = signed_local_coherence(finest)

    whitened_abs = np.abs(candidate_residual) / sigma_safe
    sigma_gate = np.clip(
        (args.max_remove_sigma - whitened_abs)
        / max(args.max_remove_sigma - args.min_remove_sigma, 1e-6),
        0.0,
        1.0,
    )
    support_weight = args.edge_weight + args.cross_weight + args.coherence_weight
    structure_support = (
        args.edge_weight * edge
        + args.cross_weight * cross
        + args.coherence_weight * coherence
    ) / max(support_weight, 1e-6)
    structure_gate = np.power(
        np.clip(
            (args.structure_cutoff - structure_support)
            / max(args.structure_cutoff, 1e-6),
            0.0,
            1.0,
        ),
        args.structure_power,
    )
    mask = blur(sigma_gate * structure_gate, args.mask_blur)
    mask = np.clip(mask, 0.0, args.max_mask_weight).astype(np.float32)

    residual = candidate_residual * mask
    residual, decorrelation_stats = decorrelate_residual(
        residual,
        plane,
        sigma_safe,
        edge,
        finest,
        coarser,
        args,
    )
    if args.post_edge_suppress:
        post_gate = np.power(
            np.clip(
                (args.post_edge_cutoff - edge) / max(args.post_edge_cutoff, 1e-6),
                0.0,
                1.0,
            ),
            args.post_edge_power,
        ).astype(np.float32)
        residual = residual * post_gate
    else:
        post_gate = np.ones_like(residual, dtype=np.float32)
    residual = np.clip(
        residual,
        -args.output_sigma_clip * sigma_safe,
        args.output_sigma_clip * sigma_safe,
    )
    clean = plane - residual
    return clean.astype(np.float32), residual.astype(np.float32), mask, {
        "candidate_residual_rms": float(np.sqrt(np.mean(candidate_residual * candidate_residual))),
        "residual_rms": float(np.sqrt(np.mean(residual * residual))),
        "residual_to_sigma_rms": float(
            np.sqrt(np.mean(residual * residual)) / max(float(np.sqrt(np.mean(sigma * sigma))), 1e-9)
        ),
        "candidate_to_sigma_rms": float(
            np.sqrt(np.mean(candidate_residual * candidate_residual)) / max(float(np.sqrt(np.mean(sigma * sigma))), 1e-9)
        ),
        "mean_mask": float(np.mean(mask)),
        "p90_mask": float(np.percentile(mask, 90)),
        "mean_edge_support": float(np.mean(edge)),
        "mean_cross_support": float(np.mean(cross)),
        "mean_coherence": float(np.mean(coherence)),
        "mean_structure_support": float(np.mean(structure_support)),
        "post_edge_mean_gate": float(np.mean(post_gate)),
        "post_edge_p90_gate": float(np.percentile(post_gate, 90)),
    } | decorrelation_stats


def build_crop(
    image_id: str,
    raw: np.ndarray,
    sigma: np.ndarray,
    meta: Any,
    crop_name: str,
    crop: dict[str, int],
    out_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    x, y, w, h = (int(crop[k]) for k in ("x", "y", "w", "h"))
    x -= x % 2
    y -= y % 2
    w -= w % 2
    h -= h % 2
    raw_crop = raw[y:y + h, x:x + w]
    sigma_crop = sigma[y:y + h, x:x + w]
    raw_ch = deinterleave(raw_crop)
    sigma_ch = deinterleave(sigma_crop)
    force_noop = meta.iso < args.min_noise_iso

    clean_ch: dict[str, np.ndarray] = {}
    residual_ch: dict[str, np.ndarray] = {}
    mask_ch: dict[str, np.ndarray] = {}
    plane_rows: dict[str, dict[str, float]] = {}
    for ch_name, plane in raw_ch.items():
        if force_noop:
            clean = plane.astype(np.float32)
            residual = np.zeros_like(plane, dtype=np.float32)
            mask = np.zeros_like(plane, dtype=np.float32)
            stats = {
                "candidate_residual_rms": 0.0,
                "residual_rms": 0.0,
                "residual_to_sigma_rms": 0.0,
                "candidate_to_sigma_rms": 0.0,
                "mean_mask": 0.0,
                "p90_mask": 0.0,
                "mean_edge_support": 0.0,
                "mean_cross_support": 0.0,
                "mean_coherence": 0.0,
                "mean_structure_support": 0.0,
                "post_edge_mean_gate": 0.0,
                "post_edge_p90_gate": 0.0,
                "decorrelation_beta_offset": 0.0,
                "decorrelation_beta_signal": 0.0,
                "decorrelation_beta_gradient": 0.0,
                "decorrelation_beta_finest": 0.0,
                "decorrelation_beta_coarser": 0.0,
                "decorrelation_removed_rms": 0.0,
            }
        else:
            clean, residual, mask, stats = clean_plane(plane, sigma_ch[ch_name], args)
        clean_ch[ch_name] = clean
        residual_ch[ch_name] = residual
        mask_ch[ch_name] = mask
        plane_rows[ch_name] = stats

    clean_crop = interleave(clean_ch, raw_crop.shape)
    residual_crop = interleave(residual_ch, raw_crop.shape)
    mask_crop = interleave(mask_ch, raw_crop.shape)
    validation = plane_validation_stats(raw_ch, sigma_ch, residual_ch, wavelet=args.wavelet)
    residual_energy = float(np.mean(residual_crop * residual_crop))
    sigma_rms = float(np.sqrt(np.mean(sigma_crop * sigma_crop)))
    residual_to_sigma_rms = float(math.sqrt(residual_energy) / max(sigma_rms, 1e-9))
    reject_reasons = contract_failure_reasons(
        raw_ch,
        residual_ch,
        sigma_ch,
        validation,
        residual_to_sigma_rms,
        args,
    )
    accepted = not reject_reasons
    if force_noop:
        accepted = True
    if args.enforce_contract and reject_reasons and not force_noop:
        clean_ch = {ch: plane.copy() for ch, plane in raw_ch.items()}
        residual_ch = {ch: np.zeros_like(plane, dtype=np.float32) for ch, plane in raw_ch.items()}
        mask_ch = {ch: np.zeros_like(plane, dtype=np.float32) for ch, plane in raw_ch.items()}
        clean_crop = interleave(clean_ch, raw_crop.shape)
        residual_crop = interleave(residual_ch, raw_crop.shape)
        mask_crop = interleave(mask_ch, raw_crop.shape)
        validation = plane_validation_stats(raw_ch, sigma_ch, residual_ch, wavelet=args.wavelet)
        residual_energy = float(np.mean(residual_crop * residual_crop))
        residual_to_sigma_rms = 0.0

    crop_dir = out_dir / image_id
    crop_dir.mkdir(parents=True, exist_ok=True)
    base = f"{image_id}_{crop_name}"
    npz_path = crop_dir / f"{base}_raw_clean_target.npz"
    np.savez_compressed(
        npz_path,
        raw=raw_crop.astype(np.float32),
        clean=clean_crop.astype(np.float32),
        exact_residual=residual_crop.astype(np.float32),
        sigma=sigma_crop.astype(np.float32),
        mask=mask_crop.astype(np.float32),
        crop_xywh=np.asarray([x, y, w, h], dtype=np.int32),
        image_id=np.asarray(image_id),
        crop=np.asarray(crop_name),
        iso=np.asarray([meta.iso], dtype=np.int32),
        min_noise_iso=np.asarray([args.min_noise_iso], dtype=np.int32),
        force_noop=np.asarray([force_noop], dtype=np.bool_),
    )

    hi = float(np.percentile(raw_crop, 99.5))
    save_u8(crop_dir / f"{base}_raw.png", raw_crop, lo=meta.black, hi=hi)
    save_u8(crop_dir / f"{base}_clean.png", clean_crop, lo=meta.black, hi=hi)
    save_u8(crop_dir / f"{base}_exact_residual_x8.png", residual_crop * args.residual_gain + 128.0, lo=0.0, hi=255.0)
    save_u8(crop_dir / f"{base}_sigma.png", sigma_crop, lo=0.0, hi=np.percentile(sigma_crop, 99.5))
    save_u8(crop_dir / f"{base}_mask.png", mask_crop, lo=0.0, hi=1.0)

    candidate_energy = float(np.mean([
        plane_rows[ch]["candidate_residual_rms"] ** 2 for ch in plane_rows
    ]))
    return {
        "image_id": image_id,
        "crop": crop_name,
        "iso": meta.iso,
        "path": str(meta.path),
        "npz": str(npz_path),
        "accepted": accepted,
        "force_noop": force_noop,
        "reject_reasons": reject_reasons,
        "contract_enforced": bool(args.enforce_contract and reject_reasons),
        "sigma_rms_counts": sigma_rms,
        "exact_residual_rms_counts": float(math.sqrt(residual_energy)),
        "exact_residual_to_sigma_rms": residual_to_sigma_rms,
        "candidate_residual_rms_counts": float(math.sqrt(candidate_energy)),
        "kept_candidate_energy_frac": float(residual_energy / max(candidate_energy, 1e-9)),
        "mean_mask": float(np.mean(mask_crop)),
        "p90_mask": float(np.percentile(mask_crop, 90)),
        "lag_max_abs": residual_lag_max_abs(residual_ch),
        "edge_removed_energy_ratio": validation["edge_removed_energy_ratio"],
        "edge_removed_energy_frac": validation["edge_removed_energy_frac"],
        "flat_removed_to_sigma_rms": validation["flat_removed_to_sigma_rms"],
        "plane_rows": plane_rows,
        "validation": validation,
        "artifacts": {
            "raw": str(crop_dir / f"{base}_raw.png"),
            "clean": str(crop_dir / f"{base}_clean.png"),
            "exact_residual_x8": str(crop_dir / f"{base}_exact_residual_x8.png"),
            "sigma": str(crop_dir / f"{base}_sigma.png"),
            "mask": str(crop_dir / f"{base}_mask.png"),
        },
    }


def build_html(rows: list[dict[str, Any]], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.4f}"
        return escape(str(v))

    html = [
        "<!doctype html><meta charset='utf-8'><title>Raw Clean REF Targets</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}"
        ".card{border:1px solid #d8dee6;border-radius:8px;padding:10px;background:white}img{width:100%;height:auto;background:#111}</style>",
        "<h1>Raw Clean REF Targets</h1>",
        "<p>Conservative raw-domain clean targets. Residual images are exact addback sidecars, amplified for display.</p>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>sigma rms</th><th>residual rms</th>"
        "<th>residual/sigma</th><th>flat residual/sigma</th><th>kept candidate energy</th><th>mean mask</th>"
        "<th>lag max abs</th><th>edge energy ratio</th><th>Status</th></tr></thead><tbody>",
    ]
    for row in rows:
        html.append("<tr>" + "".join(
            f"<td>{fmt(v)}</td>" for v in [
                row["image_id"],
                row["crop"],
                row["iso"],
                row["sigma_rms_counts"],
                row["exact_residual_rms_counts"],
                row["exact_residual_to_sigma_rms"],
                row["flat_removed_to_sigma_rms"],
                row["kept_candidate_energy_frac"],
                row["mean_mask"],
                row["lag_max_abs"],
                row["edge_removed_energy_ratio"],
                "forced no-op" if row.get("force_noop") else (
                    "accepted" if row["accepted"] else "rejected: " + ",".join(row["reject_reasons"])
                ),
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
    ap.add_argument("--images", nargs="*", default=DEFAULT_IMAGES)
    ap.add_argument("--crops", nargs="*", default=["A_detail", "B_center", "C_lowerleft"])
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=2)
    ap.add_argument("--structure-levels", type=int, default=2)
    ap.add_argument("--threshold-scale", type=float, default=0.85)
    ap.add_argument("--max-threshold-sigma", type=float, default=1.25)
    ap.add_argument("--min-remove-sigma", type=float, default=0.05)
    ap.add_argument("--max-remove-sigma", type=float, default=1.40)
    ap.add_argument("--edge-weight", type=float, default=0.45)
    ap.add_argument("--cross-weight", type=float, default=0.45)
    ap.add_argument("--coherence-weight", type=float, default=0.10)
    ap.add_argument("--structure-cutoff", type=float, default=0.95)
    ap.add_argument("--structure-power", type=float, default=0.5)
    ap.add_argument("--mask-blur", type=float, default=0.65)
    ap.add_argument("--max-mask-weight", type=float, default=1.0)
    ap.add_argument("--decorrelate-residual", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--decorrelate-gradient", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--decorrelate-highpass", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--decorrelate-signal-blur", type=float, default=2.0)
    ap.add_argument("--decorrelate-ridge", type=float, default=1e-6)
    ap.add_argument("--post-edge-suppress", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--post-edge-cutoff", type=float, default=0.35)
    ap.add_argument("--post-edge-power", type=float, default=1.5)
    ap.add_argument("--output-sigma-clip", type=float, default=1.0)
    ap.add_argument("--min-noise-iso", type=int, default=0,
                    help="Force exact raw-preserving controls below this ISO.")
    ap.add_argument("--enforce-contract", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--contract-max-residual-sigma", type=float, default=1.0)
    ap.add_argument("--contract-max-rms-residual-sigma", type=float, default=0.35)
    ap.add_argument("--contract-max-lag-abs", type=float, default=0.20)
    ap.add_argument("--contract-max-edge-ratio", type=float, default=1.0)
    ap.add_argument("--contract-max-abs-gradient-corr", type=float, default=0.15)
    ap.add_argument("--residual-gain", type=float, default=8.0)
    args = ap.parse_args()

    test_set = json.loads(args.test_set.read_text())
    image_map = {row["id"]: row for row in test_set["images"]}
    crop_map = test_set["crops"]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    image_ids = [row["id"] for row in test_set["images"]] if args.images == ["ALL"] else args.images
    for image_id in image_ids:
        image = image_map[image_id]
        path = Path(image["path"])
        meta = read_dng_meta(image_id, path)
        raw = read_bayer(path)
        sigma = noise_sigma_map(raw, meta)
        for crop_name in args.crops:
            rows.append(build_crop(image_id, raw, sigma, meta, crop_name, crop_map[crop_name], args.out_dir, args))

    summary = {
        "args": vars(args) | {"test_set": str(args.test_set), "out_dir": str(args.out_dir)},
        "rows": rows,
    }
    json_path = args.out_dir / "raw_clean_ref_targets.json"
    html_path = args.out_dir / "raw_clean_ref_targets.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(rows, html_path)
    print(json_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
