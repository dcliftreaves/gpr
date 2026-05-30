"""Test guided-filter chroma post-process applied to Variant A's output.

Three strategies, each takes Variant A's Y as the edge guide:
  S1 — VA self-guided      : VA Cb/Cr smoothed using VA Y as guide
  S2 — VA Y + NONE chroma  : cnn=none's Cb/Cr, guided by VA Y
  S3 — VA Y + BIBO chroma  : BIBO_2x's Cb/Cr, guided by VA Y

Reports LPIPS / MS-SSIM / Y-PSNR / ΔE p95 per image per strategy, vs REF.
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
OUT = RUNS / "dashboard" / "variant_a_plus_guided"
OUT.mkdir(parents=True, exist_ok=True)

# Run hashes for the full-res PIPELINE PNGs
VA_RUN   = "1d26a97a3955f271"   # Variant A YCbCr decomp
NONE_RUN = "2362fb8cb863f4c5"   # cnn=none + bicubic
BIBO_RUN = "73aae2672bdb19ab"   # BIBO_2x sl_q3
REF_RUN  = "732da314adc90553"   # REF available here (BIDO run dir)

IMAGES = ["Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693"]
PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "delta_e_p95": 3.0}

Image.MAX_IMAGE_PIXELS = None


def _box(x, r):
    k = 2 * r + 1
    return cv2.boxFilter(x.astype(np.float32), -1, (k, k))


def guided(guide, src, radius=8, eps=1e-3):
    I = guide.astype(np.float32)
    p = src.astype(np.float32)
    mI = _box(I, radius); mp = _box(p, radius)
    cIp = _box(I * p, radius) - mI * mp
    vI  = _box(I * I, radius) - mI * mI
    a = cIp / (vI + eps)
    b = mp - a * mI
    return _box(a, radius) * I + _box(b, radius)


def blend(y_src_rgb, chroma_src_rgb, radius=8, eps=1e-3):
    """Y from y_src_rgb, guided-filter-smoothed chroma from chroma_src_rgb."""
    y_ycc = cv2.cvtColor(y_src_rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32) / 255.0
    c_ycc = cv2.cvtColor(chroma_src_rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32) / 255.0
    out = y_ycc.copy()
    g = y_ycc[..., 0]
    for ch in [1, 2]:
        out[..., ch] = guided(g, c_ycc[..., ch], radius=radius, eps=eps)
    return cv2.cvtColor(np.clip(out * 255.0, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)


def downsample(im, target_w=3840):
    h, w = im.shape[:2]
    if w <= target_w: return im
    s = target_w / w
    return cv2.resize(im, (target_w, int(h * s)), interpolation=cv2.INTER_LANCZOS4)


_lp = None
def lpips_score(a_u8, b_u8):
    global _lp
    if _lp is None:
        _lp = lpips.LPIPS(net='alex').to('cpu').eval()
    a = torch.from_numpy(a_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_lp(a, b).flatten()[0])


def msssim_score(a_u8, b_u8):
    a = torch.from_numpy(a_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(a, b, data_range=1.0))


def y_psnr(a_u8, b_u8):
    ay = cv2.cvtColor(a_u8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    by = cv2.cvtColor(b_u8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    mse = float(np.mean((ay - by) ** 2))
    return 99.0 if mse <= 1e-9 else 10.0 * np.log10(255**2 / mse)


def dE(a_u8, b_u8):
    al = color.rgb2lab(a_u8.astype(np.float32) / 255.0)
    bl = color.rgb2lab(b_u8.astype(np.float32) / 255.0)
    d = color.deltaE_ciede2000(al, bl)
    return float(d.mean()), float(np.percentile(d, 95))


def verdict(m):
    return m["lpips"] <= PREVIEW["lpips"] and m["ms_ssim"] >= PREVIEW["ms_ssim"] \
       and m["y_psnr"] >= PREVIEW["y_psnr"] and m["dE_p95"] <= PREVIEW["delta_e_p95"]


def metrics(render, ref):
    re = downsample(render); rr = downsample(ref)
    dm, dp = dE(re, rr)
    out = {"lpips": lpips_score(re, rr), "ms_ssim": msssim_score(re, rr),
           "y_psnr": y_psnr(re, rr), "dE_mean": dm, "dE_p95": dp}
    out["preview_pass"] = verdict(out)
    return out


def main():
    results = {}
    for img in IMAGES:
        print(f"\n=== {img} ===")
        ref  = np.array(Image.open(RUNS / REF_RUN  / f"{img}_REF.png").convert("RGB"))
        va   = np.array(Image.open(RUNS / VA_RUN   / f"{img}_PIPELINE.png").convert("RGB"))
        none = np.array(Image.open(RUNS / NONE_RUN / f"{img}_PIPELINE.png").convert("RGB"))
        bibo = np.array(Image.open(RUNS / BIBO_RUN / f"{img}_PIPELINE.png").convert("RGB"))
        H = min(ref.shape[0], va.shape[0], none.shape[0], bibo.shape[0])
        W = min(ref.shape[1], va.shape[1], none.shape[1], bibo.shape[1])
        ref  = ref [:H, :W]; va = va[:H, :W]; none = none[:H, :W]; bibo = bibo[:H, :W]

        out = {}
        # Baselines
        out["Variant A (raw)"] = metrics(va, ref)
        out["cnn=none (raw)"]  = metrics(none, ref)
        # Strategies
        s1 = blend(va, va);    Image.fromarray(s1).save(OUT / f"{img}_S1_VA_self.png", optimize=True)
        s2 = blend(va, none);  Image.fromarray(s2).save(OUT / f"{img}_S2_VA_Y_plus_NONE_ab.png", optimize=True)
        s3 = blend(va, bibo);  Image.fromarray(s3).save(OUT / f"{img}_S3_VA_Y_plus_BIBO_ab.png", optimize=True)
        out["S1: VA self-guided (VA Y + VA Cb/Cr filtered)"] = metrics(s1, ref)
        out["S2: VA Y + NONE Cb/Cr (guided)"]                 = metrics(s2, ref)
        out["S3: VA Y + BIBO Cb/Cr (guided)"]                 = metrics(s3, ref)

        for label, m in out.items():
            v = "PASS" if m["preview_pass"] else "FAIL"
            print(f"  {label:48}  LPIPS={m['lpips']:.4f}  MS-SSIM={m['ms_ssim']:.4f}  Y-PSNR={m['y_psnr']:.2f}  ΔE_p95={m['dE_p95']:.2f}  -> {v}")
        results[img] = out

    (OUT / "metrics.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}/metrics.json + per-strategy PNGs")


if __name__ == "__main__":
    main()
