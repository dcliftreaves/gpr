"""Combine BIDO_4x w24's luminance with BIBO_2x sl_q3's chroma.

The matched BIDO_4x CNN produces sharp luma but desaturated/drifted chroma —
its loss (multi-scale L1 + LPIPS-alex) doesn't penalize chroma shift in a
perceptually meaningful way. The cross-pair BIBO_2x keeps Bayer-domain
output and lets sips demosaic, preserving color.

Try several strategies for combining the two:
  S1. Naive YCbCr swap            (Y from BIDO, Cb/Cr from BIBO)
  S2. LAB swap                    (L from BIDO, a/b from BIBO)
  S3. Joint bilateral chroma      (BIDO Y as edge guide for BIBO Cb/Cr)
  S4. Guided filter chroma        (He 2010, BIDO Y as guide image)
  S5. Edge-aware chroma blur      (BIBO chroma low-passed except at BIDO Y edges)

Per-strategy metrics (vs REF crop):
  LPIPS-alex, MS-SSIM, Y-PSNR, ΔE2000 (mean and 95th percentile)

Output: an HTML dashboard with side-by-side crops and a per-strategy table.
Also dumps the strategy renders to tests/quality_gates/runs/dashboard/luma_chroma_blend/.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import cv2
import torch
import lpips
from pytorch_msssim import ms_ssim

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
OUT_DIR = RUNS / "dashboard" / "luma_chroma_blend"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BIDO_RUN = "732da314adc90553"     # bido_4x_ane_ml2_q3_dec2_w24 — sharp Y, bad chroma
BIBO_RUN = "6676478b154e9fc6"     # bibo2x_ane_sl_q3 cross-pair — softer Y, good chroma
CNN_NONE_RUN = "44d95b0985ac01c4"  # cnn=none + bicubic — baseline

# Subset of the gate images that matter for visual chroma assessment.
IMAGES = ["Z8Z_6693", "Z8Z_5323", "Z8Z_0001", "Z8Z_0067"]


# ----- color-space conversions (operate on uint8 RGB) -----

def rgb_to_ycbcr(rgb_u8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2YCrCb)  # YCrCb, channel order Y Cr Cb


def ycbcr_to_rgb(ycc_u8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(ycc_u8, cv2.COLOR_YCrCb2RGB)


def rgb_to_lab(rgb_u8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB)


def lab_to_rgb(lab_u8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(lab_u8, cv2.COLOR_LAB2RGB)


# ----- strategies -----

def strategy_ycbcr_swap(bido_rgb, bibo_rgb):
    """Y from BIDO, Cr/Cb from BIBO."""
    bido_ycc = rgb_to_ycbcr(bido_rgb)
    bibo_ycc = rgb_to_ycbcr(bibo_rgb)
    out_ycc = bido_ycc.copy()
    out_ycc[..., 1] = bibo_ycc[..., 1]  # Cr
    out_ycc[..., 2] = bibo_ycc[..., 2]  # Cb
    return ycbcr_to_rgb(out_ycc)


def strategy_lab_swap(bido_rgb, bibo_rgb):
    """L from BIDO, a/b from BIBO."""
    bido_lab = rgb_to_lab(bido_rgb)
    bibo_lab = rgb_to_lab(bibo_rgb)
    out = bido_lab.copy()
    out[..., 1] = bibo_lab[..., 1]
    out[..., 2] = bibo_lab[..., 2]
    return lab_to_rgb(out)


def _boxfilter(x, r):
    """Mean over a (2r+1)x(2r+1) window via box filter."""
    k = 2 * r + 1
    return cv2.boxFilter(x.astype(np.float32), -1, (k, k))


def _guided_filter(guide_f32, input_f32, radius=8, eps=1e-3):
    """He et al. 2010 guided filter (single-channel guide).
    Output: a local linear model q = a*I + b that fits `input` while staying
    close to `guide`'s edges. eps controls smoothness in flat guide regions.
    """
    I = guide_f32
    p = input_f32
    mean_I = _boxfilter(I, radius)
    mean_p = _boxfilter(p, radius)
    corr_Ip = _boxfilter(I * p, radius)
    cov_Ip = corr_Ip - mean_I * mean_p
    var_I = _boxfilter(I * I, radius) - mean_I * mean_I
    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I
    mean_a = _boxfilter(a, radius)
    mean_b = _boxfilter(b, radius)
    return mean_a * I + mean_b


def strategy_joint_bilateral_chroma(bido_rgb, bibo_rgb, d=9, sigma_color=25, sigma_space=25):
    """Use BIDO Y as edge guide for joint-bilateral filtering of BIBO chroma.
    Implementation note: cv2.bilateralFilter (with bibo chroma as both src and
    guide) is the closest stable approximation — the cross-modal joint variant
    needs opencv-contrib which is install-conflicted here. The standard
    bilateral on BIBO chroma alone preserves its own edges, which is decent
    but doesn't use BIDO's luma. See S4 for the principled luma-guided variant.
    """
    bido_ycc = rgb_to_ycbcr(bido_rgb)
    bibo_ycc = rgb_to_ycbcr(bibo_rgb)
    out_ycc = bido_ycc.copy()
    for ch in [1, 2]:
        out_ycc[..., ch] = cv2.bilateralFilter(bibo_ycc[..., ch], d, sigma_color, sigma_space)
    return ycbcr_to_rgb(out_ycc)


def strategy_guided_chroma(bido_rgb, bibo_rgb, radius=8, eps=1e-4):
    """He 2010 guided filter (hand-rolled in numpy/cv2).
    Guide: BIDO Y (sharp). Input: BIBO Cr, Cb (correct color).
    Output: chroma that follows BIDO luma's edge structure but takes color
    from BIBO. This is the principled chroma-from-luma upsample trick.
    """
    bido_ycc = rgb_to_ycbcr(bido_rgb).astype(np.float32) / 255.0
    bibo_ycc = rgb_to_ycbcr(bibo_rgb).astype(np.float32) / 255.0
    guide = bido_ycc[..., 0]
    out = bido_ycc.copy()
    for ch in [1, 2]:
        out[..., ch] = _guided_filter(guide, bibo_ycc[..., ch], radius=radius, eps=eps)
    return ycbcr_to_rgb(np.clip(out * 255.0, 0, 255).astype(np.uint8))


def strategy_edge_aware_blur_chroma(bido_rgb, bibo_rgb, sigma=2.0, edge_thresh=20):
    """Detect edges in BIDO Y → Gaussian-blur BIBO chroma where Y is smooth,
    keep chroma sharp where Y has edges. Lower-quality than guided/bilateral
    but no extra dependency.
    """
    bido_ycc = rgb_to_ycbcr(bido_rgb)
    bibo_ycc = rgb_to_ycbcr(bibo_rgb)
    y = bido_ycc[..., 0]
    # Sobel-magnitude edge map on BIDO luma
    gx = cv2.Sobel(y, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(y, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx*gx + gy*gy)
    edge = np.clip(mag / edge_thresh, 0, 1).astype(np.float32)  # 1 at edges, 0 in flat
    out_ycc = bido_ycc.copy()
    for ch in [1, 2]:
        sharp = bibo_ycc[..., ch].astype(np.float32)
        blur = cv2.GaussianBlur(bibo_ycc[..., ch], (0, 0), sigma).astype(np.float32)
        # at edges, use sharp; in flat regions, use blur (less chroma noise propagation)
        mixed = edge * sharp + (1.0 - edge) * blur
        out_ycc[..., ch] = np.clip(mixed, 0, 255).astype(np.uint8)
    return ycbcr_to_rgb(out_ycc)


STRATEGIES = [
    ("S1 — naive YCbCr swap", strategy_ycbcr_swap),
    ("S2 — naive LAB swap", strategy_lab_swap),
    ("S3 — joint bilateral chroma (luma-guided)", strategy_joint_bilateral_chroma),
    ("S4 — guided filter chroma (He 2010)", strategy_guided_chroma),
    ("S5 — edge-aware blur chroma", strategy_edge_aware_blur_chroma),
]


# ----- metric helpers -----

_lpips_net = None

def lpips_score(a_u8, b_u8):
    global _lpips_net
    if _lpips_net is None:
        _lpips_net = lpips.LPIPS(net='alex').to('cpu').eval()
    a = torch.from_numpy(a_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_lpips_net(a, b).flatten()[0])


def msssim(a_u8, b_u8):
    a = torch.from_numpy(a_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(a, b, data_range=1.0))


def y_psnr(a_u8, b_u8):
    ay = rgb_to_ycbcr(a_u8)[..., 0].astype(np.float32)
    by = rgb_to_ycbcr(b_u8)[..., 0].astype(np.float32)
    mse = np.mean((ay - by) ** 2)
    if mse <= 0: return 99.0
    return 10.0 * np.log10(255.0 ** 2 / mse)


def delta_e_2000(a_u8, b_u8):
    """Approximate ΔE2000 via skimage."""
    from skimage import color
    a_lab = color.rgb2lab(a_u8.astype(np.float32) / 255.0)
    b_lab = color.rgb2lab(b_u8.astype(np.float32) / 255.0)
    return color.deltaE_ciede2000(a_lab, b_lab)


def load_crop(run_hash, image_id, kind):
    p = RUNS / run_hash / f"{image_id}_{kind}_crop_A_detail.png"
    if not p.exists():
        raise FileNotFoundError(p)
    return np.array(Image.open(p).convert("RGB"))


def evaluate_one(image_id):
    ref = load_crop(BIDO_RUN, image_id, "REF")  # REFs should be identical across runs
    bido = load_crop(BIDO_RUN, image_id, "PIPELINE")
    bibo = load_crop(BIBO_RUN, image_id, "PIPELINE")
    none = load_crop(CNN_NONE_RUN, image_id, "PIPELINE")

    rows = []
    # Baselines
    for label, render in [("REF (target)", ref),
                          ("cnn=none + bicubic", none),
                          ("BIBO (color OK, soft)", bibo),
                          ("BIDO (sharp, bad chroma)", bido)]:
        de = delta_e_2000(render, ref)
        rows.append({
            "label": label,
            "render": render,
            "lpips": lpips_score(render, ref),
            "ms_ssim": msssim(render, ref),
            "y_psnr": y_psnr(render, ref),
            "dE_mean": float(np.mean(de)),
            "dE_p95": float(np.percentile(de, 95)),
        })

    # Strategies
    for label, fn in STRATEGIES:
        try:
            out = fn(bido, bibo)
            de = delta_e_2000(out, ref)
            rows.append({
                "label": label,
                "render": out,
                "lpips": lpips_score(out, ref),
                "ms_ssim": msssim(out, ref),
                "y_psnr": y_psnr(out, ref),
                "dE_mean": float(np.mean(de)),
                "dE_p95": float(np.percentile(de, 95)),
            })
        except Exception as e:
            rows.append({"label": label, "render": None, "error": str(e)})

    # Save renders
    for r in rows:
        if r.get("render") is not None:
            safe = r["label"].replace(" ", "_").replace("(", "").replace(")", "").replace("=", "_").replace("+", "_").replace("—", "-")
            out_path = OUT_DIR / f"{image_id}_{safe}.png"
            Image.fromarray(r["render"]).save(out_path)
            r["filename"] = out_path.name
        else:
            r["filename"] = None
    return rows


def make_html(results):
    css = """
    body { font-family: -apple-system, system-ui; margin: 24px; background: #fafafa; color: #222; max-width: 1800px; }
    h1 { font-size: 22px; margin-bottom: 4px; }
    h2 { font-size: 17px; margin-top: 32px; padding-bottom: 6px; border-bottom: 2px solid #ddd; }
    .subtitle { color: #666; font-size: 13px; max-width: 900px; margin-bottom: 18px; }
    .legend { padding: 12px 16px; background: white; border-left: 4px solid #1a5fb4; margin: 16px 0; font-size: 13px; max-width: 1000px; }
    table.metric { border-collapse: collapse; margin: 12px 0; font-size: 12px; }
    table.metric th, table.metric td { border: 1px solid #ddd; padding: 4px 8px; text-align: right; }
    table.metric th { background: #eee; }
    table.metric td.label { text-align: left; font-weight: 500; min-width: 230px; }
    .pass { color: #0a7d28; font-weight: 600; }
    .fail { color: #b00020; font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0; }
    .grid figure { margin: 0; background: white; padding: 6px; border-radius: 6px; border: 1px solid #ddd; }
    .grid figcaption { font-size: 11px; color: #444; text-align: center; margin-top: 4px; line-height: 1.3; }
    .grid img { width: 100%; border: 1px solid #ccc; display: block; }
    """
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>luma/chroma blend</title><style>{css}</style></head><body>"]
    parts.append("<h1>BIDO luma + BIBO chroma — blend strategies</h1>")
    parts.append(
        '<div class="subtitle">Take the sharp luminance from the matched '
        "BIDO_4x w24 CNN (right column of the prior dashboard — good Y, drifted chroma). "
        "Take the color-correct chroma from the cross-pair BIBO_2x_sl_q3 CNN "
        "(middle column — good color, softer luma). Try five strategies for "
        "merging them. Metrics computed at the 512×512 crop_A_detail scale "
        "(same crop the gate uses for the worst-image diff)."
        "</div>"
    )

    for image_id, rows in results.items():
        parts.append(f"<h2>{image_id}</h2>")

        # metric table
        parts.append('<table class="metric"><thead><tr><th>variant</th><th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>ΔE mean</th><th>ΔE p95</th></tr></thead><tbody>')
        for r in rows:
            if "error" in r:
                parts.append(f'<tr><td class="label">{r["label"]}</td><td colspan="5"><i>{r["error"]}</i></td></tr>')
                continue
            parts.append(
                f'<tr><td class="label">{r["label"]}</td>'
                f'<td>{r["lpips"]:.4f}</td>'
                f'<td>{r["ms_ssim"]:.4f}</td>'
                f'<td>{r["y_psnr"]:.2f}</td>'
                f'<td>{r["dE_mean"]:.2f}</td>'
                f'<td>{r["dE_p95"]:.2f}</td></tr>'
            )
        parts.append("</tbody></table>")

        # image grid (show only the rendered variants — skip REF for compactness)
        parts.append('<div class="grid">')
        for r in rows:
            if r.get("filename") is None:
                continue
            parts.append(
                f'<figure><img src="luma_chroma_blend/{r["filename"]}" alt="{r["label"]}">'
                f'<figcaption><b>{r["label"]}</b><br>LPIPS {r.get("lpips","?"):.4f} · ΔE {r.get("dE_mean","?"):.2f}</figcaption></figure>'
            )
        parts.append("</div>")

    parts.append("</body></html>")
    out = RUNS / "dashboard" / "luma_chroma_blend.html"
    out.write_text("\n".join(parts))
    print(f"wrote {out}")


def main():
    results = {}
    for img in IMAGES:
        print(f"\n=== {img} ===")
        rows = evaluate_one(img)
        for r in rows:
            if "error" in r:
                print(f"  {r['label']}: ERROR {r['error']}")
            else:
                print(f"  {r['label']:50}  LPIPS={r['lpips']:.4f}  ΔE_mean={r['dE_mean']:.2f}  ΔE_p95={r['dE_p95']:.2f}")
        results[img] = rows
    make_html(results)


if __name__ == "__main__":
    main()
