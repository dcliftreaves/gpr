#!/usr/bin/env python3
"""Diagnose luma/detail loss in saved quality-gate crop outputs.

This is intentionally crop-based: it compares the REF/PIPELINE detail crops
already emitted by run_gate.py, so it can be run quickly across historical
gate runs without re-encoding or re-rendering full images.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color
from skimage.filters import gaussian
from skimage.metrics import structural_similarity


REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "tests/quality_gates/runs"
DASH_DIR = RUNS_DIR / "dashboard"

DEFAULT_RUNS = {
    "Lab sips residual": "5e7d52579ffb2d3e",
    "ml2_dec2 no CNN": "44d95b0985ac01c4",
    "UPRESABLE BIBO2x": "8864c12ec0b6ce14",
}
DEFAULT_IMAGES = ("Z8Z_5323", "Z8Z_6693")


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def psnr_from_mse(mse: float, peak: float = 1.0) -> float:
    return 99.0 if mse <= 1e-12 else 10.0 * math.log10((peak * peak) / mse)


def corr(a: np.ndarray, b: np.ndarray) -> float:
    ax = a.reshape(-1).astype(np.float64)
    bx = b.reshape(-1).astype(np.float64)
    ax -= ax.mean()
    bx -= bx.mean()
    den = math.sqrt(float((ax * ax).sum() * (bx * bx).sum()))
    return 0.0 if den <= 1e-12 else float((ax * bx).sum() / den)


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
    x = img.astype(np.float64) - float(np.mean(img))
    spec = np.abs(np.fft.fft2(x)) ** 2
    total = float(spec.sum())
    if total <= 1e-12:
        return {"low": 0.0, "mid": 0.0, "high": 0.0}
    bins = radial_frequency_bins(x.shape)
    return {k: float(spec[m].sum() / total) for k, m in bins.items()}


def highpass_luma(luma: np.ndarray, sigma: float = 1.2) -> np.ndarray:
    return luma.astype(np.float32) - gaussian(
        luma.astype(np.float32),
        sigma=sigma,
        preserve_range=True,
    ).astype(np.float32)


def grad_rms(luma: np.ndarray) -> float:
    gy, gx = np.gradient(luma.astype(np.float32))
    return float(np.sqrt(np.mean(gx * gx + gy * gy)))


def metrics_for_pair(ref_rgb: np.ndarray, pipe_rgb: np.ndarray) -> dict[str, float]:
    ref_l = color.rgb2lab(np.clip(ref_rgb, 0, 1))[..., 0]
    pipe_l = color.rgb2lab(np.clip(pipe_rgb, 0, 1))[..., 0]
    err = pipe_l - ref_l
    ref_hp = highpass_luma(ref_l)
    pipe_hp = highpass_luma(pipe_l)
    err_hp = pipe_hp - ref_hp
    ref_hp_rms = float(np.sqrt(np.mean(ref_hp * ref_hp)))
    pipe_hp_rms = float(np.sqrt(np.mean(pipe_hp * pipe_hp)))
    err_hp_rms = float(np.sqrt(np.mean(err_hp * err_hp)))
    ref_grad = grad_rms(ref_l)
    pipe_grad = grad_rms(pipe_l)
    ref_band = band_energy(ref_l)
    pipe_band = band_energy(pipe_l)
    err_band = band_energy(err)

    return {
        "L_mae": float(np.mean(np.abs(err))),
        "L_p95": float(np.percentile(np.abs(err), 95)),
        "L_psnr": psnr_from_mse(float(np.mean((err / 100.0) ** 2))),
        "L_ssim": float(structural_similarity(ref_l, pipe_l, data_range=100.0)),
        "hp_rms_ref": ref_hp_rms,
        "hp_rms_pipe": pipe_hp_rms,
        "hp_rms_ratio": float(pipe_hp_rms / max(ref_hp_rms, 1e-12)),
        "hp_err_rms": err_hp_rms,
        "hp_corr": corr(ref_hp, pipe_hp),
        "grad_ratio": float(pipe_grad / max(ref_grad, 1e-12)),
        "ref_hf_frac": ref_band["high"],
        "pipe_hf_frac": pipe_band["high"],
        "hf_frac_ratio": float(pipe_band["high"] / max(ref_band["high"], 1e-12)),
        "err_low_frac": err_band["low"],
        "err_mid_frac": err_band["mid"],
        "err_high_frac": err_band["high"],
    }


def read_run_meta(run_hash: str) -> dict:
    p = RUNS_DIR / run_hash / "run.json"
    if not p.exists():
        raise FileNotFoundError(f"missing {p}")
    return json.loads(p.read_text())


def crop_pair(run_hash: str, image_id: str, crop: str) -> tuple[Path, Path]:
    run_dir = RUNS_DIR / run_hash
    ref = run_dir / f"{image_id}_REF_{crop}.png"
    pipe = run_dir / f"{image_id}_PIPELINE_{crop}.png"
    if not ref.exists() or not pipe.exists():
        raise FileNotFoundError(f"missing crop pair for {run_hash} {image_id} {crop}")
    return ref, pipe


def collect_rows(runs: dict[str, str], images: tuple[str, ...], crop: str) -> list[dict]:
    rows = []
    for label, run_hash in runs.items():
        meta = read_run_meta(run_hash)
        for image_id in images:
            ref_path, pipe_path = crop_pair(run_hash, image_id, crop)
            gate = (meta.get("images") or {}).get(image_id, {})
            row = {
                "label": label,
                "run_hash": run_hash,
                "pipeline": meta.get("pipeline", ""),
                "verdict": meta.get("verdict", ""),
                "image_id": image_id,
                "gate_lpips": gate.get("lpips"),
                "gate_ms_ssim": gate.get("ms_ssim"),
                "gate_y_psnr": gate.get("y_psnr"),
                "gate_dE2000_mean": gate.get("dE2000_mean"),
            }
            row.update(metrics_for_pair(load_rgb(ref_path), load_rgb(pipe_path)))
            rows.append(row)
    return rows


def fmt(x: object, digits: int = 3) -> str:
    if x is None:
        return "-"
    if isinstance(x, str):
        return x
    return f"{float(x):.{digits}f}"


def print_rows(rows: list[dict]) -> None:
    print(
        "| image | pipeline | verdict | LPIPS | MS-SSIM | Y-PSNR | dE mean | "
        "crop L-SSIM | L-PSNR | hp ratio | hp corr | grad ratio | "
        "HF ratio | err low/mid/high |"
    )
    print(
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    )
    for r in rows:
        print(
            f"| {r['image_id']} | {r['label']} | {r['verdict']} | "
            f"{fmt(r['gate_lpips'], 4)} | {fmt(r['gate_ms_ssim'], 4)} | "
            f"{fmt(r['gate_y_psnr'], 2)} | {fmt(r['gate_dE2000_mean'], 2)} | "
            f"{fmt(r['L_ssim'], 4)} | {fmt(r['L_psnr'], 2)} | "
            f"{fmt(r['hp_rms_ratio'], 3)} | {fmt(r['hp_corr'], 3)} | "
            f"{fmt(r['grad_ratio'], 3)} | {fmt(r['hf_frac_ratio'], 3)} | "
            f"{fmt(r['err_low_frac'], 2)}/{fmt(r['err_mid_frac'], 2)}/{fmt(r['err_high_frac'], 2)} |"
        )


def write_html(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    trs = []
    for r in rows:
        cls = "pass" if r["verdict"] == "PASS" else "fail"
        trs.append(f"""
<tr>
  <td>{html.escape(r['image_id'])}</td>
  <td>{html.escape(r['label'])}</td>
  <td><code>{html.escape(r['run_hash'])}</code></td>
  <td class="{cls}">{html.escape(r['verdict'])}</td>
  <td class="num">{fmt(r['gate_lpips'], 4)}</td>
  <td class="num">{fmt(r['gate_ms_ssim'], 4)}</td>
  <td class="num">{fmt(r['gate_y_psnr'], 2)}</td>
  <td class="num">{fmt(r['gate_dE2000_mean'], 2)}</td>
  <td class="num">{fmt(r['L_ssim'], 4)}</td>
  <td class="num">{fmt(r['L_psnr'], 2)}</td>
  <td class="num">{fmt(r['L_mae'], 2)}</td>
  <td class="num">{fmt(r['hp_rms_ratio'], 3)}</td>
  <td class="num">{fmt(r['hp_corr'], 3)}</td>
  <td class="num">{fmt(r['hp_err_rms'], 2)}</td>
  <td class="num">{fmt(r['grad_ratio'], 3)}</td>
  <td class="num">{fmt(r['hf_frac_ratio'], 3)}</td>
  <td class="num">{fmt(r['err_low_frac'], 2)}/{fmt(r['err_mid_frac'], 2)}/{fmt(r['err_high_frac'], 2)}</td>
</tr>""")
    out.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GPR luma/detail diagnostic</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2933; background: #f7f8fa; }}
h1 {{ margin: 0 0 8px; font-size: 28px; }}
p {{ max-width: 1080px; line-height: 1.45; color: #52606d; }}
table {{ border-collapse: collapse; width: 100%; background: white; border: 1px solid #dde3ea; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #edf1f5; padding: 7px 9px; vertical-align: top; }}
th {{ background: #eef2f6; text-align: left; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
code {{ font-size: 12px; background: #edf1f5; padding: 1px 4px; border-radius: 4px; }}
.pass {{ color: #167a3a; font-weight: 650; }}
.fail {{ color: #b42318; font-weight: 650; }}
</style>
</head>
<body>
<h1>GPR luma/detail diagnostic</h1>
<p>
Generated from saved quality-gate detail crops. <code>hp ratio</code> compares
pipeline high-pass luma RMS to REF; values below 1 indicate smoothing.
<code>hp corr</code> measures whether high-frequency detail is in the right
places, and <code>err low/mid/high</code> splits luma-error energy by FFT band.
</p>
<table>
<tr><th>Image</th><th>Pipeline</th><th>Run</th><th>Verdict</th><th class="num">LPIPS</th><th class="num">MS-SSIM</th><th class="num">Y-PSNR</th><th class="num">dE mean</th><th class="num">crop L-SSIM</th><th class="num">L-PSNR</th><th class="num">L MAE</th><th class="num">hp ratio</th><th class="num">hp corr</th><th class="num">hp err</th><th class="num">grad ratio</th><th class="num">HF ratio</th><th class="num">err low/mid/high</th></tr>
{''.join(trs)}
</table>
</body>
</html>
""")
    print(f"wrote {out}")


def parse_run_arg(values: list[str]) -> dict[str, str]:
    if not values:
        return dict(DEFAULT_RUNS)
    out = {}
    for value in values:
        if "=" in value:
            label, run_hash = value.split("=", 1)
        else:
            label, run_hash = value, value
        out[label] = run_hash
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="Run hashes or label=hash pairs")
    ap.add_argument("--crop", default="crop_A_detail")
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument(
        "--html-out",
        type=Path,
        default=DASH_DIR / "luma_detail_diagnostic.html",
    )
    args = ap.parse_args()

    rows = collect_rows(parse_run_arg(args.runs), tuple(args.images), args.crop)
    print_rows(rows)
    if args.html_out:
        write_html(rows, args.html_out)


if __name__ == "__main__":
    main()
