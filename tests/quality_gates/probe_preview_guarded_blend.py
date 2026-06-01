#!/usr/bin/env python3
"""Probe guarded PREVIEW blends on saved quality-gate detail crops.

This is a fast, crop-scale probe for the current productionization blocker:
the display-space Lab residual candidate fixes chroma/dE, but still fails
LPIPS/MS-SSIM on textured regions. The probe keeps that candidate's a/b chroma
and tries several L-channel detail donors before implementing anything in the
full pipeline.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage import color
from skimage.metrics import structural_similarity
import torch
import lpips
from pytorch_msssim import ms_ssim


REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "tests/quality_gates/runs"
DASH_DIR = RUNS_DIR / "dashboard"

DISPLAY_RUN = "5e7d52579ffb2d3e"
NONE_RUN = "44d95b0985ac01c4"
UPRES_RUN = "8864c12ec0b6ce14"
IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")


def load_crop(run_hash: str, image_id: str, kind: str = "PIPELINE") -> np.ndarray:
    p = RUNS_DIR / run_hash / f"{image_id}_{kind}_crop_A_detail.png"
    if not p.exists():
        raise FileNotFoundError(p)
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)


def rgb_to_lab(rgb_u8: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb_u8.astype(np.float32) / 255.0).astype(np.float32)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)


def highpass(x: np.ndarray, sigma: float) -> np.ndarray:
    return x.astype(np.float32) - cv2.GaussianBlur(x.astype(np.float32), (0, 0), sigma)


def lowpass(x: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(x.astype(np.float32), (0, 0), sigma)


def assemble_lab_l(display_rgb: np.ndarray, l_channel: np.ndarray) -> np.ndarray:
    lab = rgb_to_lab(display_rgb)
    lab[..., 0] = np.clip(l_channel, 0, 100)
    return lab_to_rgb(lab)


def local_energy(hp: np.ndarray, radius: int = 5) -> np.ndarray:
    k = 2 * radius + 1
    return cv2.boxFilter((hp * hp).astype(np.float32), -1, (k, k))


def l_from_donor_hf(display_l: np.ndarray, donor_l: np.ndarray, sigma: float, gain: float) -> np.ndarray:
    return lowpass(display_l, sigma) + gain * highpass(donor_l, sigma)


def l_from_guarded_donor_hf(
    display_l: np.ndarray,
    donor_l: np.ndarray,
    sigma: float,
    gain: float,
    energy_ratio: float,
) -> np.ndarray:
    d_hp = highpass(display_l, sigma)
    n_hp = highpass(donor_l, sigma)
    d_e = local_energy(d_hp)
    n_e = local_energy(n_hp)
    mask = np.clip((n_e / np.maximum(d_e * energy_ratio, 1e-6) - 1.0), 0.0, 1.0)
    # Blur the mask to avoid blocky transitions.
    mask = cv2.GaussianBlur(mask, (0, 0), 1.0)
    return lowpass(display_l, sigma) + (1.0 - mask) * d_hp + mask * gain * n_hp


def psnr_from_mse(mse: float, peak: float = 1.0) -> float:
    return 99.0 if mse <= 1e-12 else 10.0 * math.log10((peak * peak) / mse)


_LPIPS_NET = None


def lpips_score(a_u8: np.ndarray, b_u8: np.ndarray) -> float:
    global _LPIPS_NET
    if _LPIPS_NET is None:
        _LPIPS_NET = lpips.LPIPS(net="alex").to("cpu").eval()
    a = torch.from_numpy(a_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_LPIPS_NET(a, b).flatten()[0])


def ms_ssim_score(a_u8: np.ndarray, b_u8: np.ndarray) -> float:
    a = torch.from_numpy(a_u8.astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(a, b, data_range=1.0))


def corr(a: np.ndarray, b: np.ndarray) -> float:
    ax = a.reshape(-1).astype(np.float64)
    bx = b.reshape(-1).astype(np.float64)
    ax -= ax.mean()
    bx -= bx.mean()
    den = math.sqrt(float((ax * ax).sum() * (bx * bx).sum()))
    return 0.0 if den <= 1e-12 else float((ax * bx).sum() / den)


def metrics(render: np.ndarray, ref: np.ndarray) -> dict[str, float]:
    rr = rgb_to_lab(ref)
    pr = rgb_to_lab(render)
    de = color.deltaE_ciede2000(rr, pr)
    l_err = pr[..., 0] - rr[..., 0]
    ref_hp = highpass(rr[..., 0], 1.2)
    pipe_hp = highpass(pr[..., 0], 1.2)
    ref_hp_rms = float(np.sqrt(np.mean(ref_hp * ref_hp)))
    pipe_hp_rms = float(np.sqrt(np.mean(pipe_hp * pipe_hp)))
    return {
        "lpips": lpips_score(render, ref),
        "ms_ssim": ms_ssim_score(render, ref),
        "crop_L_ssim": float(structural_similarity(rr[..., 0], pr[..., 0], data_range=100.0)),
        "L_psnr": psnr_from_mse(float(np.mean((l_err / 100.0) ** 2))),
        "L_mae": float(np.mean(np.abs(l_err))),
        "dE_mean": float(np.mean(de)),
        "dE_p95": float(np.percentile(de, 95)),
        "hp_ratio": float(pipe_hp_rms / max(ref_hp_rms, 1e-12)),
        "hp_corr": corr(ref_hp, pipe_hp),
    }


def candidate_renders(display: np.ndarray, none: np.ndarray, upres: np.ndarray) -> list[tuple[str, np.ndarray]]:
    d_l = rgb_to_lab(display)[..., 0]
    n_l = rgb_to_lab(none)[..., 0]
    u_l = rgb_to_lab(upres)[..., 0]
    out = [
        ("display residual", display),
        ("none L + display ab", assemble_lab_l(display, n_l)),
        ("upres L + display ab", assemble_lab_l(display, u_l)),
    ]
    for alpha in (0.25, 0.50, 0.75):
        out.append((f"L blend display/none alpha={alpha:.2f}", assemble_lab_l(display, alpha * d_l + (1 - alpha) * n_l)))
        out.append((f"L blend display/upres alpha={alpha:.2f}", assemble_lab_l(display, alpha * d_l + (1 - alpha) * u_l)))
    for donor_name, donor_l in (("none", n_l), ("upres", u_l)):
        for sigma in (1.0, 1.6, 2.4):
            for gain in (0.75, 1.0, 1.25):
                out.append((
                    f"{donor_name} HF sigma={sigma:.1f} gain={gain:.2f}",
                    assemble_lab_l(display, l_from_donor_hf(d_l, donor_l, sigma, gain)),
                ))
        for sigma in (1.0, 1.6):
            for gain in (0.75, 1.0):
                out.append((
                    f"guarded {donor_name} HF sigma={sigma:.1f} gain={gain:.2f}",
                    assemble_lab_l(display, l_from_guarded_donor_hf(d_l, donor_l, sigma, gain, energy_ratio=1.10)),
                ))
    return out


def collect_rows(args: argparse.Namespace) -> list[dict]:
    rows = []
    render_dir = DASH_DIR / "preview_guarded_blend"
    render_dir.mkdir(parents=True, exist_ok=True)
    for image_id in args.images:
        ref = load_crop(args.display_run, image_id, "REF")
        display = load_crop(args.display_run, image_id, "PIPELINE")
        none = load_crop(args.none_run, image_id, "PIPELINE")
        upres = load_crop(args.upres_run, image_id, "PIPELINE")
        for label, render in candidate_renders(display, none, upres):
            m = metrics(render, ref)
            safe = (
                label.replace(" ", "_")
                .replace("/", "_")
                .replace("=", "_")
                .replace(".", "p")
            )
            filename = f"{image_id}_{safe}.png"
            if args.write_images:
                Image.fromarray(render).save(render_dir / filename)
            rows.append({
                "image_id": image_id,
                "label": label,
                "filename": f"preview_guarded_blend/{filename}",
                **m,
            })
    return rows


def best_rows(rows: list[dict]) -> list[dict]:
    best = []
    for image_id in sorted({r["image_id"] for r in rows}):
        img_rows = [r for r in rows if r["image_id"] == image_id]
        best.extend(sorted(img_rows, key=lambda r: (r["lpips"], -r["ms_ssim"], r["dE_mean"]))[:8])
    return best


def print_summary(rows: list[dict]) -> None:
    for image_id in sorted({r["image_id"] for r in rows}):
        print(f"\n## {image_id}")
        for r in sorted([x for x in rows if x["image_id"] == image_id], key=lambda x: (x["lpips"], -x["ms_ssim"], x["dE_mean"]))[:10]:
            print(
                f"{r['label']:<42} LPIPS={r['lpips']:.4f} MS-SSIM={r['ms_ssim']:.4f} "
                f"dE={r['dE_mean']:.3f} dE95={r['dE_p95']:.3f} "
                f"Lssim={r['crop_L_ssim']:.4f} Lpsnr={r['L_psnr']:.2f} "
                f"hpRatio={r['hp_ratio']:.3f} hpCorr={r['hp_corr']:.3f}"
            )


def write_html(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    table_rows = []
    for r in rows:
        table_rows.append(f"""
<tr>
  <td>{html.escape(r['image_id'])}</td>
  <td>{html.escape(r['label'])}</td>
  <td class="num">{r['lpips']:.4f}</td>
  <td class="num">{r['ms_ssim']:.4f}</td>
  <td class="num">{r['dE_mean']:.3f}</td>
  <td class="num">{r['dE_p95']:.3f}</td>
  <td class="num">{r['crop_L_ssim']:.4f}</td>
  <td class="num">{r['L_psnr']:.2f}</td>
  <td class="num">{r['L_mae']:.2f}</td>
  <td class="num">{r['hp_ratio']:.3f}</td>
  <td class="num">{r['hp_corr']:.3f}</td>
</tr>""")
    figures = []
    for r in best_rows(rows):
        figures.append(f"""
<figure>
  <img src="{html.escape(r['filename'])}" alt="{html.escape(r['label'])}">
  <figcaption><b>{html.escape(r['image_id'])}</b><br>{html.escape(r['label'])}<br>LPIPS {r['lpips']:.3f} · dE {r['dE_mean']:.2f}</figcaption>
</figure>""")
    out.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PREVIEW guarded blend probe</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2933; background: #f7f8fa; }}
h1 {{ margin: 0 0 8px; font-size: 28px; }}
p {{ max-width: 1120px; line-height: 1.45; color: #52606d; }}
table {{ border-collapse: collapse; width: 100%; background: white; border: 1px solid #dde3ea; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #edf1f5; padding: 7px 9px; vertical-align: top; }}
th {{ background: #eef2f6; text-align: left; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }}
figure {{ margin: 0; background: white; border: 1px solid #dde3ea; padding: 8px; }}
figure img {{ width: 100%; display: block; border: 1px solid #d8dee6; }}
figcaption {{ font-size: 12px; color: #52606d; line-height: 1.35; margin-top: 6px; }}
</style>
</head>
<body>
<h1>PREVIEW guarded blend probe</h1>
<p>
Crop-scale probe using display-space residual chroma as the a/b source and
testing alternate L-channel donors. This dashboard is a preflight before a
full-pipeline implementation.
</p>
<div class="grid">{''.join(figures)}</div>
<table>
<tr><th>Image</th><th>Candidate</th><th class="num">LPIPS</th><th class="num">MS-SSIM</th><th class="num">dE mean</th><th class="num">dE95</th><th class="num">crop L-SSIM</th><th class="num">L-PSNR</th><th class="num">L MAE</th><th class="num">hp ratio</th><th class="num">hp corr</th></tr>
{''.join(table_rows)}
</table>
</body>
</html>
""")
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--display-run", default=DISPLAY_RUN)
    ap.add_argument("--none-run", default=NONE_RUN)
    ap.add_argument("--upres-run", default=UPRES_RUN)
    ap.add_argument("--images", nargs="+", default=list(IMAGES))
    ap.add_argument("--write-images", action="store_true")
    ap.add_argument("--html-out", type=Path, default=DASH_DIR / "preview_guarded_blend_probe.html")
    args = ap.parse_args()

    rows = collect_rows(args)
    print_summary(rows)
    write_html(rows, args.html_out)
    metrics_path = args.html_out.with_suffix(".json")
    metrics_path.write_text(json.dumps(rows, indent=2))
    print(f"wrote {metrics_path}")


if __name__ == "__main__":
    main()
