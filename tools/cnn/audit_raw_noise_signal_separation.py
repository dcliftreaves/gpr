#!/usr/bin/env python3
"""Audit raw clean-target sidecars for noise-vs-signal separation.

This is a pre-training guardrail. A residual is considered usable as "removed
noise" only when it is small relative to the DNG sigma model, reconstructs
exactly through clean+residual addback, and has weak evidence of image-signal
structure in same-plane spatial, edge, clean-correlation, and spectral tests.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from html import escape
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from analyze_dng_noise_profile import deinterleave, plane_validation_stats, save_u8


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root()))
ARTIFACT_ROOT = Path(os.environ.get("GPR_ARTIFACT_ROOT", EXTERNAL_ROOT / "artifacts"))
DEFAULT_TARGETS = ARTIFACT_ROOT / "raw_clean_ref_targets_fullgate_20260604" / "raw_clean_ref_targets.json"
DEFAULT_OUT = ARTIFACT_ROOT / "raw_noise_signal_audit_20260605"


def corr(a: np.ndarray, b: np.ndarray) -> float:
    aa = a.astype(np.float64).ravel()
    bb = b.astype(np.float64).ravel()
    aa -= float(np.mean(aa))
    bb -= float(np.mean(bb))
    denom = math.sqrt(float(np.dot(aa, aa)) * float(np.dot(bb, bb)))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(aa, bb) / denom)


def robust_gradient(plane: np.ndarray) -> np.ndarray:
    low = cv2.GaussianBlur(plane.astype(np.float32), (0, 0), 1.0)
    gx = cv2.Sobel(low, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(low, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy).astype(np.float32)


def spectral_metrics(z: np.ndarray) -> dict[str, float]:
    centered = z.astype(np.float32) - float(np.mean(z))
    if centered.size == 0 or float(np.std(centered)) <= 1e-9:
        return {
            "spectral_flatness": 1.0,
            "psd_peak_to_median": 1.0,
            "lowfreq_energy_frac": 0.0,
        }
    win_y = np.hanning(centered.shape[0]).astype(np.float32)
    win_x = np.hanning(centered.shape[1]).astype(np.float32)
    windowed = centered * win_y[:, None] * win_x[None, :]
    psd = np.abs(np.fft.rfft2(windowed)) ** 2
    psd = psd.astype(np.float64)
    psd = psd[1:, 1:] if psd.shape[0] > 1 and psd.shape[1] > 1 else psd
    eps = 1e-18
    median = float(np.median(psd))
    flatness = float(np.exp(np.mean(np.log(psd + eps))) / max(float(np.mean(psd)), eps))
    peak_to_median = float(np.max(psd) / max(median, eps))

    yy, xx = np.mgrid[:psd.shape[0], :psd.shape[1]]
    rr = np.sqrt((yy / max(psd.shape[0] - 1, 1)) ** 2 + (xx / max(psd.shape[1] - 1, 1)) ** 2)
    low = psd[rr <= 0.10]
    low_frac = float(np.sum(low) / max(float(np.sum(psd)), eps)) if low.size else 0.0
    return {
        "spectral_flatness": flatness,
        "psd_peak_to_median": peak_to_median,
        "lowfreq_energy_frac": low_frac,
    }


def plane_noise_evidence(
    raw: np.ndarray,
    clean: np.ndarray,
    residual: np.ndarray,
    sigma: np.ndarray,
) -> dict[str, float]:
    sigma_safe = np.maximum(sigma.astype(np.float32), 1e-6)
    z = residual.astype(np.float32) / sigma_safe
    grad = robust_gradient(raw)
    grad_scale = float(np.percentile(grad, 95.0))
    grad_norm = grad / max(grad_scale, 1e-6)
    active = np.abs(residual) > max(float(np.percentile(np.abs(residual), 75.0)), 1e-6)
    active_frac = float(np.mean(active))

    out = {
        "z_mean": float(np.mean(z)),
        "z_std": float(np.std(z)),
        "z_p99_abs": float(np.percentile(np.abs(z), 99.0)),
        "clean_corr": corr(z, clean),
        "absres_gradient_corr": corr(np.abs(z), grad_norm),
        "active_frac": active_frac,
    }
    out.update(spectral_metrics(z))
    return out


def audit_row(row: dict[str, Any], args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    z = np.load(row["npz"])
    raw = z["raw"].astype(np.float32)
    clean = z["clean"].astype(np.float32)
    residual = z["exact_residual"].astype(np.float32)
    sigma = np.maximum(z["sigma"].astype(np.float32), 1e-6)
    mask = z["mask"].astype(np.float32)

    raw_ch = deinterleave(raw)
    clean_ch = deinterleave(clean)
    residual_ch = deinterleave(residual)
    sigma_ch = deinterleave(sigma)
    validation = plane_validation_stats(raw_ch, sigma_ch, residual_ch, wavelet=args.wavelet)

    addback_err = float(np.max(np.abs((clean + residual) - raw)))
    residual_rms = float(np.sqrt(np.mean(residual * residual)))
    sigma_rms = float(np.sqrt(np.mean(sigma * sigma)))
    residual_to_sigma = residual_rms / max(sigma_rms, 1e-9)
    max_residual_sigma = float(np.max(np.abs(residual) / sigma))
    lag_max_abs = max(
        float(validation["removed_lag1_corr_x_max_abs"]),
        float(validation["removed_lag1_corr_y_max_abs"]),
    )
    edge_ratio = float(validation["edge_removed_energy_ratio"])
    plane_rows = {
        name: plane_noise_evidence(raw_ch[name], clean_ch[name], residual_ch[name], sigma_ch[name])
        for name in raw_ch
    }
    max_abs_clean_corr = max(abs(v["clean_corr"]) for v in plane_rows.values())
    max_abs_grad_corr = max(abs(v["absres_gradient_corr"]) for v in plane_rows.values())
    min_flatness = min(v["spectral_flatness"] for v in plane_rows.values())
    max_peak_to_median = max(v["psd_peak_to_median"] for v in plane_rows.values())
    max_lowfreq_frac = max(v["lowfreq_energy_frac"] for v in plane_rows.values())

    no_op = (
        (residual_rms <= args.noop_residual_rms_counts and float(np.max(mask)) <= args.noop_max_mask)
        or residual_to_sigma <= args.noop_residual_to_sigma_rms
    )
    checks = {
        "addback": addback_err <= args.max_addback_error,
        "max_residual_sigma": max_residual_sigma <= args.max_residual_sigma + 1e-5,
        "rms_residual_sigma": residual_to_sigma <= args.max_rms_residual_sigma,
        "lag": lag_max_abs <= args.max_lag_abs,
        "edge_ratio": edge_ratio <= args.max_edge_ratio,
        "clean_corr": max_abs_clean_corr <= args.max_abs_clean_corr,
        "gradient_corr": max_abs_grad_corr <= args.max_abs_gradient_corr,
        "spectral_flatness": min_flatness >= args.min_spectral_flatness,
        "psd_peak": max_peak_to_median <= args.max_psd_peak_to_median,
        "lowfreq": max_lowfreq_frac <= args.max_lowfreq_energy_frac,
    }
    if no_op:
        checks = checks | {
            "rms_residual_sigma": True,
            "lag": True,
            "edge_ratio": True,
            "clean_corr": True,
            "gradient_corr": True,
            "spectral_flatness": True,
            "psd_peak": True,
            "lowfreq": True,
        }

    image_dir = out_dir / str(row["image_id"])
    image_dir.mkdir(parents=True, exist_ok=True)
    base = f"{row['image_id']}_{row['crop']}"
    hi = float(np.percentile(raw, 99.5))
    artifacts = {
        "raw": image_dir / f"{base}_raw.png",
        "clean": image_dir / f"{base}_clean.png",
        "residual_x8": image_dir / f"{base}_residual_x8.png",
        "mask": image_dir / f"{base}_mask.png",
    }
    lo = float(np.percentile(raw, 0.5))
    save_u8(artifacts["raw"], raw, lo=lo, hi=hi)
    save_u8(artifacts["clean"], clean, lo=lo, hi=hi)
    save_u8(artifacts["residual_x8"], residual * args.residual_gain + 128.0, lo=0.0, hi=255.0)
    save_u8(artifacts["mask"], mask, lo=0.0, hi=1.0)

    return {
        "image_id": row["image_id"],
        "crop": row["crop"],
        "iso": row["iso"],
        "accepted": bool(row.get("accepted", True)),
        "no_op": no_op,
        "pass": all(checks.values()),
        "failed_checks": [key for key, ok in checks.items() if not ok],
        "checks": checks,
        "metrics": {
            "addback_err_counts": addback_err,
            "residual_rms_counts": residual_rms,
            "sigma_rms_counts": sigma_rms,
            "residual_to_sigma_rms": residual_to_sigma,
            "max_residual_sigma": max_residual_sigma,
            "lag_max_abs": lag_max_abs,
            "edge_removed_energy_ratio": edge_ratio,
            "max_abs_clean_corr": max_abs_clean_corr,
            "max_abs_gradient_corr": max_abs_grad_corr,
            "min_spectral_flatness": min_flatness,
            "max_psd_peak_to_median": max_peak_to_median,
            "max_lowfreq_energy_frac": max_lowfreq_frac,
        },
        "plane_rows": plane_rows,
        "artifacts": {key: str(path) for key, path in artifacts.items()},
    }


def build_html(summary: dict[str, Any], out_path: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.4f}"
        return escape(str(v))

    rows = summary["rows"]
    html = [
        "<!doctype html><meta charset='utf-8'><title>Raw Noise/Signal Audit</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#17212b}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d7dde5;padding:7px;font-size:12px;vertical-align:top}"
        "th{background:#eef2f5}.pass{color:#0b6b35;font-weight:600}.fail{color:#9d1c20;font-weight:600}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.card{border:1px solid #d7dde5;border-radius:8px;padding:10px}"
        "img{width:100%;height:auto;background:#111}</style>",
        "<h1>Raw Noise/Signal Audit</h1>",
        "<p>Residuals are accepted only when they are sub-sigma, low-structure, low-correlation, and exactly add back to REF.</p>",
        f"<p>pass={summary['pass_count']} fail={summary['fail_count']} no_op={summary['no_op_count']}</p>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Status</th><th>Residual/Sigma</th>"
        "<th>Lag</th><th>Edge Ratio</th><th>|Clean Corr|</th><th>|Gradient Corr|</th>"
        "<th>Flatness</th><th>PSD Peak</th><th>Low Freq</th><th>Failed</th></tr></thead><tbody>",
    ]
    for row in rows:
        m = row["metrics"]
        status = "PASS" if row["pass"] else "FAIL"
        html.append("<tr>" + "".join([
            f"<td>{escape(str(row['image_id']))}</td>",
            f"<td>{escape(str(row['crop']))}</td>",
            f"<td>{escape(str(row['iso']))}</td>",
            f"<td class='{status.lower()}'>{status}{' no-op' if row['no_op'] else ''}</td>",
            f"<td>{fmt(m['residual_to_sigma_rms'])}</td>",
            f"<td>{fmt(m['lag_max_abs'])}</td>",
            f"<td>{fmt(m['edge_removed_energy_ratio'])}</td>",
            f"<td>{fmt(m['max_abs_clean_corr'])}</td>",
            f"<td>{fmt(m['max_abs_gradient_corr'])}</td>",
            f"<td>{fmt(m['min_spectral_flatness'])}</td>",
            f"<td>{fmt(m['max_psd_peak_to_median'])}</td>",
            f"<td>{fmt(m['max_lowfreq_energy_frac'])}</td>",
            f"<td>{escape(','.join(row['failed_checks']))}</td>",
        ]) + "</tr>")
    html.append("</tbody></table><div class='grid'>")
    for row in rows:
        html.append(f"<div class='card'><h3>{escape(row['image_id'])} {escape(row['crop'])}</h3>")
        for label, path_str in row["artifacts"].items():
            rel = Path(path_str).relative_to(out_path.parent)
            html.append(f"<p>{escape(label)}</p><img src='{escape(str(rel))}'>")
        html.append("</div>")
    html.append("</div>")
    out_path.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--max-addback-error", type=float, default=0.001)
    ap.add_argument("--max-residual-sigma", type=float, default=1.0)
    ap.add_argument("--max-rms-residual-sigma", type=float, default=0.35)
    ap.add_argument("--max-lag-abs", type=float, default=0.20)
    ap.add_argument("--max-edge-ratio", type=float, default=1.0)
    ap.add_argument("--max-abs-clean-corr", type=float, default=0.08)
    ap.add_argument("--max-abs-gradient-corr", type=float, default=0.15)
    ap.add_argument("--min-spectral-flatness", type=float, default=0.05)
    ap.add_argument("--max-psd-peak-to-median", type=float, default=1500.0)
    ap.add_argument("--max-lowfreq-energy-frac", type=float, default=0.20)
    ap.add_argument("--noop-residual-to-sigma-rms", type=float, default=0.02)
    ap.add_argument("--noop-residual-rms-counts", type=float, default=1e-6)
    ap.add_argument("--noop-max-mask", type=float, default=1e-6)
    ap.add_argument("--residual-gain", type=float, default=8.0)
    args = ap.parse_args()

    data = json.loads(args.targets.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = [audit_row(row, args, args.out_dir) for row in data["rows"]]
    failed = [row for row in rows if not row["pass"]]
    summary = {
        "kind": "raw_noise_signal_audit",
        "targets": str(args.targets),
        "thresholds": {
            "max_addback_error": args.max_addback_error,
            "max_residual_sigma": args.max_residual_sigma,
            "max_rms_residual_sigma": args.max_rms_residual_sigma,
            "max_lag_abs": args.max_lag_abs,
            "max_edge_ratio": args.max_edge_ratio,
            "max_abs_clean_corr": args.max_abs_clean_corr,
            "max_abs_gradient_corr": args.max_abs_gradient_corr,
            "min_spectral_flatness": args.min_spectral_flatness,
            "max_psd_peak_to_median": args.max_psd_peak_to_median,
            "max_lowfreq_energy_frac": args.max_lowfreq_energy_frac,
        },
        "pass_count": len(rows) - len(failed),
        "fail_count": len(failed),
        "no_op_count": len([row for row in rows if row["no_op"]]),
        "rows": rows,
    }
    json_path = args.out_dir / "raw_noise_signal_audit.json"
    html_path = args.out_dir / "raw_noise_signal_audit.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(summary, html_path)
    for row in rows:
        status = "PASS" if row["pass"] else "FAIL"
        m = row["metrics"]
        print(
            f"{status} {row['image_id']} {row['crop']} ISO={row['iso']} "
            f"res/sigma={m['residual_to_sigma_rms']:.3f} "
            f"lag={m['lag_max_abs']:.3f} edge={m['edge_removed_energy_ratio']:.3f} "
            f"corr={m['max_abs_clean_corr']:.3f}/{m['max_abs_gradient_corr']:.3f} "
            f"flat={m['min_spectral_flatness']:.3f} peak={m['max_psd_peak_to_median']:.1f}"
            + (f" failed={','.join(row['failed_checks'])}" if row["failed_checks"] else "")
        )
    print(json_path)
    print(html_path)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
