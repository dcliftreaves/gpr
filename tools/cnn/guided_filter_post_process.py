"""Apply guided filter to BIDO_4x_w24's chroma using cnn=none's chroma at full-res,
guided by BIDO's luma. Pure inference; no training. Tests whether the chroma fix
can be a decode-time post-process.

Source PIPELINE PNGs (8K × 5.5K):
  - BIDO   = tests/quality_gates/runs/732da314adc90553/{img}_PIPELINE.png
  - NONE   = tests/quality_gates/runs/2362fb8cb863f4c5/{img}_PIPELINE.png

Output: blended PNGs + gate metrics for each image.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from PIL import Image
import cv2
import torch
import lpips
from pytorch_msssim import ms_ssim
from skimage import color

REPO = Path("/Users/dcliftreaves/Documents/Github/gpr")
RUNS = REPO / "tests/quality_gates/runs"
OUT_DIR = RUNS / "dashboard" / "guided_filter_post"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BIDO_RUN = "732da314adc90553"     # BIDO_4x_w24 — sharp Y, bad chroma
NONE_RUN = "2362fb8cb863f4c5"     # cnn=none + bicubic — color-correct, blurry
IMAGES = ["Z8Z_6693", "Z8Z_5323", "Z8Z_0001", "Z8Z_0067"]
PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "delta_e_p95": 3.0}

Image.MAX_IMAGE_PIXELS = None


def _boxfilter(x, r):
    k = 2 * r + 1
    return cv2.boxFilter(x.astype(np.float32), -1, (k, k))


def guided_filter(guide, src, radius=8, eps=1e-3):
    """He et al. 2010 guided filter."""
    I = guide.astype(np.float32)
    p = src.astype(np.float32)
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


def blend_guided(bido_rgb, none_rgb, radius=8, eps=1e-3):
    """BIDO Y + guided-filtered NONE chroma."""
    bido_ycc = cv2.cvtColor(bido_rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32) / 255.0
    none_ycc = cv2.cvtColor(none_rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32) / 255.0
    out = bido_ycc.copy()
    guide = bido_ycc[..., 0]
    for ch in [1, 2]:
        out[..., ch] = guided_filter(guide, none_ycc[..., ch], radius=radius, eps=eps)
    return cv2.cvtColor(np.clip(out * 255.0, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)


def downsample_for_metrics(im_u8, target_w=3840):
    h, w = im_u8.shape[:2]
    if w <= target_w:
        return im_u8
    scale = target_w / w
    return cv2.resize(im_u8, (target_w, int(h * scale)), interpolation=cv2.INTER_LANCZOS4)


_lpips_net = None


def lpips_alex(a_u8, b_u8):
    global _lpips_net
    if _lpips_net is None:
        _lpips_net = lpips.LPIPS(net='alex').to('cpu').eval()
    a = torch.from_numpy(a_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_lpips_net(a, b).flatten()[0])


def msssim_t(a_u8, b_u8):
    a = torch.from_numpy(a_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(a, b, data_range=1.0))


def y_psnr(a_u8, b_u8):
    ay = cv2.cvtColor(a_u8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    by = cv2.cvtColor(b_u8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    mse = float(np.mean((ay - by) ** 2))
    return 99.0 if mse <= 1e-9 else 10.0 * np.log10(255.0**2 / mse)


def delta_e(a_u8, b_u8):
    al = color.rgb2lab(a_u8.astype(np.float32) / 255.0)
    bl = color.rgb2lab(b_u8.astype(np.float32) / 255.0)
    d = color.deltaE_ciede2000(al, bl)
    return float(d.mean()), float(np.percentile(d, 95))


def evaluate(img_id):
    bido = np.array(Image.open(RUNS / BIDO_RUN / f"{img_id}_PIPELINE.png").convert("RGB"))
    none = np.array(Image.open(RUNS / NONE_RUN / f"{img_id}_PIPELINE.png").convert("RGB"))
    ref = np.array(Image.open(RUNS / BIDO_RUN / f"{img_id}_REF.png").convert("RGB"))
    H = min(bido.shape[0], none.shape[0], ref.shape[0])
    W = min(bido.shape[1], none.shape[1], ref.shape[1])
    bido = bido[:H, :W]; none = none[:H, :W]; ref = ref[:H, :W]

    blend = blend_guided(bido, none)
    Image.fromarray(blend).save(OUT_DIR / f"{img_id}_BLEND.png", optimize=True)

    out = {}
    for label, render in [("BIDO_w24 (bad chroma)", bido),
                          ("cnn=none (blurry)", none),
                          ("guided-filter post (BIDO Y + NONE ab)", blend)]:
        ref_eval = downsample_for_metrics(ref)
        ren_eval = downsample_for_metrics(render)
        de_mean, de_p95 = delta_e(ren_eval, ref_eval)
        m = {
            "lpips": lpips_alex(ren_eval, ref_eval),
            "ms_ssim": msssim_t(ren_eval, ref_eval),
            "y_psnr": y_psnr(ren_eval, ref_eval),
            "dE_mean": de_mean,
            "dE_p95": de_p95,
        }
        m["preview_pass"] = (m["lpips"] <= PREVIEW["lpips"]
                             and m["ms_ssim"] >= PREVIEW["ms_ssim"]
                             and m["y_psnr"] >= PREVIEW["y_psnr"]
                             and m["dE_p95"] <= PREVIEW["delta_e_p95"])
        out[label] = m
    return out


def main():
    print("=== Guided-filter post-process: BIDO Y + cnn=none chroma at full-res ===")
    results = {}
    for img in IMAGES:
        print(f"\n{img}:")
        results[img] = evaluate(img)
        for label, m in results[img].items():
            v = "PASS" if m["preview_pass"] else "FAIL"
            print(f"  {label:42}  LPIPS={m['lpips']:.4f}  MS-SSIM={m['ms_ssim']:.4f}  "
                  f"Y-PSNR={m['y_psnr']:.2f}  ΔE_p95={m['dE_p95']:.2f}  -> {v}")
    # Save metrics
    with open(OUT_DIR / "metrics.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {OUT_DIR}/metrics.json + 4 blended PNGs")


if __name__ == "__main__":
    main()
