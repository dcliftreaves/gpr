"""Test the user's hypothesis: Y_CNN alone + guided-filter chroma is enough.

The Variant A experiment showed Cb/Cr CNNs added nothing — replacing them
with cnn=none chroma + guided filter strictly improved metrics. This script
formalizes that finding by isolating which pieces are load-bearing:

  A. Y_CNN + cnn=none Cb/Cr (LAB swap, NO guided filter) — isolate guided contribution
  B. Y_CNN + cnn=none Cb/Cr + guided (r=8, the current S2 setting)
  C. Y_CNN + cnn=none Cb/Cr + guided (r=16, more chroma smoothing)
  D. Y_CNN + cnn=none Cb/Cr + guided (r=32, aggressive smoothing)
  E. Y_CNN + AVG(NONE, BIBO) Cb/Cr + guided — chroma ensemble

Compare to baselines:
  - BIDO_w24 alone (the prior matched CNN)
  - cnn=none alone (the bicubic baseline)
  - guided-filter post (BIDO Y + cnn=none Cb/Cr + guided r=8) — prior SOTA
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
OUT = RUNS / "dashboard" / "y_only_plus_guided"
OUT.mkdir(parents=True, exist_ok=True)

VA_RUN   = "1d26a97a3955f271"
BIDO_RUN = "732da314adc90553"
NONE_RUN = "2362fb8cb863f4c5"
BIBO_RUN = "73aae2672bdb19ab"

IMAGES = ["Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693"]
PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "delta_e_p95": 3.0}

Image.MAX_IMAGE_PIXELS = None


def _box(x, r):
    k = 2 * r + 1
    return cv2.boxFilter(x.astype(np.float32), -1, (k, k))


def guided(guide, src, radius=8, eps=1e-3):
    I = guide.astype(np.float32); p = src.astype(np.float32)
    mI = _box(I, radius); mp = _box(p, radius)
    cIp = _box(I * p, radius) - mI * mp
    vI  = _box(I * I, radius) - mI * mI
    a = cIp / (vI + eps); b = mp - a * mI
    return _box(a, radius) * I + _box(b, radius)


def assemble(y_rgb, chroma_rgb, use_guided=True, radius=8, eps=1e-3):
    """Y from y_rgb, chroma from chroma_rgb (optionally guided-filtered)."""
    y_ycc = cv2.cvtColor(y_rgb,      cv2.COLOR_RGB2YCrCb).astype(np.float32) / 255.0
    c_ycc = cv2.cvtColor(chroma_rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32) / 255.0
    out = y_ycc.copy()
    g = y_ycc[..., 0]
    for ch in [1, 2]:
        if use_guided:
            out[..., ch] = guided(g, c_ycc[..., ch], radius=radius, eps=eps)
        else:
            out[..., ch] = c_ycc[..., ch]
    return cv2.cvtColor(np.clip(out * 255.0, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)


def downsample(im, target_w=3840):
    h, w = im.shape[:2]
    if w <= target_w: return im
    s = target_w / w
    return cv2.resize(im, (target_w, int(h * s)), interpolation=cv2.INTER_LANCZOS4)


_lp = None
def lpips_score(a, b):
    global _lp
    if _lp is None:
        _lp = lpips.LPIPS(net='alex').to('cpu').eval()
    a_t = torch.from_numpy(a.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    b_t = torch.from_numpy(b.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_lp(a_t, b_t).flatten()[0])


def msssim_score(a, b):
    a_t = torch.from_numpy(a.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    b_t = torch.from_numpy(b.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(a_t, b_t, data_range=1.0))


def y_psnr_(a, b):
    ay = cv2.cvtColor(a, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    by = cv2.cvtColor(b, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    mse = float(np.mean((ay - by) ** 2))
    return 99.0 if mse <= 1e-9 else 10.0 * np.log10(255**2 / mse)


def dE(a, b):
    al = color.rgb2lab(a.astype(np.float32) / 255.0)
    bl = color.rgb2lab(b.astype(np.float32) / 255.0)
    d = color.deltaE_ciede2000(al, bl)
    return float(d.mean()), float(np.percentile(d, 95))


def verdict(m):
    return m["lpips"] <= PREVIEW["lpips"] and m["ms_ssim"] >= PREVIEW["ms_ssim"] \
       and m["y_psnr"] >= PREVIEW["y_psnr"] and m["dE_p95"] <= PREVIEW["delta_e_p95"]


def metrics(render, ref):
    re = downsample(render); rr = downsample(ref)
    dm, dp = dE(re, rr)
    out = {"lpips": lpips_score(re, rr), "ms_ssim": msssim_score(re, rr),
           "y_psnr": y_psnr_(re, rr), "dE_mean": dm, "dE_p95": dp}
    out["preview_pass"] = verdict(out)
    return out


def main():
    results = {}
    for img in IMAGES:
        print(f"\n=== {img} ===")
        ref  = np.array(Image.open(RUNS / BIDO_RUN / f"{img}_REF.png").convert("RGB"))
        va   = np.array(Image.open(RUNS / VA_RUN   / f"{img}_PIPELINE.png").convert("RGB"))
        bido = np.array(Image.open(RUNS / BIDO_RUN / f"{img}_PIPELINE.png").convert("RGB"))
        none = np.array(Image.open(RUNS / NONE_RUN / f"{img}_PIPELINE.png").convert("RGB"))
        bibo = np.array(Image.open(RUNS / BIBO_RUN / f"{img}_PIPELINE.png").convert("RGB"))
        H = min(ref.shape[0], va.shape[0], bido.shape[0], none.shape[0], bibo.shape[0])
        W = min(ref.shape[1], va.shape[1], bido.shape[1], none.shape[1], bibo.shape[1])
        ref  = ref [:H, :W]; va = va[:H, :W]; bido = bido[:H, :W]; none = none[:H, :W]; bibo = bibo[:H, :W]

        out = {}
        # Baselines
        out["BIDO_w24 alone"]   = metrics(bido, ref)
        out["cnn=none alone"]   = metrics(none, ref)
        out["Variant A raw"]    = metrics(va, ref)

        # Prior SOTA: BIDO Y + cnn=none Cb/Cr + guided r=8
        prior_sota = assemble(bido, none, use_guided=True, radius=8)
        Image.fromarray(prior_sota).save(OUT / f"{img}_PRIOR_SOTA.png", optimize=True)
        out["Prior SOTA (BIDO Y + NONE ab guided r=8)"] = metrics(prior_sota, ref)

        # User hypothesis variants — all use VA Y as the luma source
        sa = assemble(va, none, use_guided=False)
        Image.fromarray(sa).save(OUT / f"{img}_A_VA_Y_NONE_ab_LABswap.png", optimize=True)
        out["A: VA Y + NONE Cb/Cr (LAB swap, no guided)"] = metrics(sa, ref)

        sb = assemble(va, none, use_guided=True, radius=8)
        Image.fromarray(sb).save(OUT / f"{img}_B_VA_Y_NONE_ab_guided_r8.png", optimize=True)
        out["B: VA Y + NONE Cb/Cr + guided r=8"] = metrics(sb, ref)

        sc = assemble(va, none, use_guided=True, radius=16)
        Image.fromarray(sc).save(OUT / f"{img}_C_VA_Y_NONE_ab_guided_r16.png", optimize=True)
        out["C: VA Y + NONE Cb/Cr + guided r=16"] = metrics(sc, ref)

        sd = assemble(va, none, use_guided=True, radius=32)
        Image.fromarray(sd).save(OUT / f"{img}_D_VA_Y_NONE_ab_guided_r32.png", optimize=True)
        out["D: VA Y + NONE Cb/Cr + guided r=32"] = metrics(sd, ref)

        # E: chroma ensemble (avg of NONE and BIBO)
        chroma_avg = ((none.astype(np.uint16) + bibo.astype(np.uint16)) // 2).astype(np.uint8)
        se = assemble(va, chroma_avg, use_guided=True, radius=8)
        Image.fromarray(se).save(OUT / f"{img}_E_VA_Y_avgChroma_guided.png", optimize=True)
        out["E: VA Y + avg(NONE,BIBO) Cb/Cr + guided"] = metrics(se, ref)

        for label, m in out.items():
            v = "PASS" if m["preview_pass"] else "FAIL"
            print(f"  {label:50}  LPIPS={m['lpips']:.4f}  MS-SSIM={m['ms_ssim']:.4f}  Y-PSNR={m['y_psnr']:.2f}  ΔE_p95={m['dE_p95']:.2f}  -> {v}")
        results[img] = out

    (OUT / "metrics.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}/metrics.json + per-strategy PNGs")


if __name__ == "__main__":
    main()
