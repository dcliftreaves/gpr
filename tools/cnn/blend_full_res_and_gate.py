"""Full-res LAB-swap blend evaluation against PREVIEW gate thresholds.

Takes the saved full-res PIPELINE PNGs from the BIDO_4x w24 and BIBO_2x sl_q3
gate runs, performs the LAB-swap (BIDO L + BIBO a,b), and computes the same
metrics the gate runner uses. Verdicts use PREVIEW thresholds.

This is the path-1 verification — does the crop-scale finding hold at the
full-image scale the gate actually evaluates?
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

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
OUT = RUNS / "dashboard" / "blend_full_res_gate.html"
BLEND_PNG_DIR = RUNS / "dashboard" / "blend_full_res_pngs"
BLEND_PNG_DIR.mkdir(parents=True, exist_ok=True)

BIDO_RUN = "732da314adc90553"
BIBO_RUN = "73aae2672bdb19ab"
IMAGES = ["Z8Z_6693", "Z8Z_5323", "Z8Z_0001", "Z8Z_0067"]

# PREVIEW gate thresholds — from tests/quality_gates/gates.json.
PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "delta_e_p95": 3.0}

# Image.MAX_IMAGE_PIXELS guard — these are 8K renders
Image.MAX_IMAGE_PIXELS = None


def lab_swap(bido_rgb_u8: np.ndarray, bibo_rgb_u8: np.ndarray) -> np.ndarray:
    """L from BIDO, a/b from BIBO. Operates in 8-bit LAB."""
    a = cv2.cvtColor(bido_rgb_u8, cv2.COLOR_RGB2LAB)
    b = cv2.cvtColor(bibo_rgb_u8, cv2.COLOR_RGB2LAB)
    out = a.copy()
    out[..., 1] = b[..., 1]
    out[..., 2] = b[..., 2]
    return cv2.cvtColor(out, cv2.COLOR_LAB2RGB)


def y_psnr(a_u8, b_u8):
    ay = cv2.cvtColor(a_u8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    by = cv2.cvtColor(b_u8, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    mse = float(np.mean((ay - by) ** 2))
    if mse <= 1e-9:
        return 99.0
    return 10.0 * np.log10(255.0 * 255.0 / mse)


def msssim_full(a_u8, b_u8):
    """MS-SSIM at the gate's metric resolution (test_set 3840px wide).
    Downsample to 3840 wide first if larger.
    """
    h, w = a_u8.shape[:2]
    target_w = 3840
    if w > target_w:
        scale = target_w / w
        target_h = int(h * scale)
        a_u8 = cv2.resize(a_u8, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
        b_u8 = cv2.resize(b_u8, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    a = torch.from_numpy(a_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 255).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(a, b, data_range=1.0))


_lpips_net = None


def lpips_full(a_u8, b_u8):
    """LPIPS-alex on downsampled-to-3840 (gate metric eval resolution)."""
    global _lpips_net
    if _lpips_net is None:
        _lpips_net = lpips.LPIPS(net='alex').to('cpu').eval()
    h, w = a_u8.shape[:2]
    if w > 3840:
        scale = 3840 / w
        new_h = int(h * scale)
        a_u8 = cv2.resize(a_u8, (3840, new_h), interpolation=cv2.INTER_LANCZOS4)
        b_u8 = cv2.resize(b_u8, (3840, new_h), interpolation=cv2.INTER_LANCZOS4)
    a = torch.from_numpy(a_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    b = torch.from_numpy(b_u8.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_lpips_net(a, b).flatten()[0])


def delta_e_2000(a_u8, b_u8):
    """ΔE2000 — return mean and p95."""
    al = color.rgb2lab(a_u8.astype(np.float32) / 255.0)
    bl = color.rgb2lab(b_u8.astype(np.float32) / 255.0)
    d = color.deltaE_ciede2000(al, bl)
    return float(d.mean()), float(np.percentile(d, 95))


def verdict_preview(metrics: dict) -> bool:
    return (metrics["lpips"] <= PREVIEW["lpips"]
            and metrics["ms_ssim"] >= PREVIEW["ms_ssim"]
            and metrics["y_psnr"] >= PREVIEW["y_psnr"]
            and metrics["dE_p95"] <= PREVIEW["delta_e_p95"])


def compute(image_id):
    ref = np.array(Image.open(RUNS / BIDO_RUN / f"{image_id}_REF.png").convert("RGB"))
    bido = np.array(Image.open(RUNS / BIDO_RUN / f"{image_id}_PIPELINE.png").convert("RGB"))
    bibo = np.array(Image.open(RUNS / BIBO_RUN / f"{image_id}_PIPELINE.png").convert("RGB"))
    print(f"  {image_id}: ref={ref.shape} bido={bido.shape} bibo={bibo.shape}")

    # Ensure all three share size — they should, since they came from same source DNG
    H = min(ref.shape[0], bido.shape[0], bibo.shape[0])
    W = min(ref.shape[1], bido.shape[1], bibo.shape[1])
    ref = ref[:H, :W]; bido = bido[:H, :W]; bibo = bibo[:H, :W]

    blend = lab_swap(bido, bibo)
    Image.fromarray(blend).save(BLEND_PNG_DIR / f"{image_id}_BLEND.png", optimize=True)

    out = {}
    for label, render in [("bido_w24", bido), ("bibo2x_sl_q3", bibo), ("blend (BIDO L + BIBO ab)", blend)]:
        de_mean, de_p95 = delta_e_2000(render, ref)
        m = {
            "lpips": lpips_full(render, ref),
            "ms_ssim": msssim_full(render, ref),
            "y_psnr": y_psnr(render, ref),
            "dE_mean": de_mean,
            "dE_p95": de_p95,
        }
        m["preview_pass"] = verdict_preview(m)
        out[label] = m
    return out


def render_html(results):
    css = """
    body { font-family: -apple-system, system-ui; margin: 24px; background: #fafafa; max-width: 1400px; }
    h1 { font-size: 22px; margin-bottom: 4px; }
    h2 { font-size: 16px; margin-top: 28px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
    .subtitle { color: #666; font-size: 13px; max-width: 900px; margin-bottom: 14px; }
    .legend { padding: 12px 16px; background: white; border-left: 4px solid #1a5fb4;
              margin: 12px 0; font-size: 13px; max-width: 1000px; }
    table { border-collapse: collapse; margin: 12px 0; font-size: 13px; }
    th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: right; }
    th { background: #eee; }
    td.label { text-align: left; font-weight: 500; min-width: 220px; }
    .pass { color: #0a7d28; font-weight: 700; }
    .fail { color: #b00020; font-weight: 700; }
    .verdict-pass { background: #d4edda; }
    .verdict-fail { background: #f8d7da; }
    """
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{css}</style></head><body>"]
    parts.append("<h1>Full-res LAB-swap blend vs PREVIEW gate</h1>")
    parts.append('<div class="subtitle">'
                 "Take BIDO_4x w24's full-res PIPELINE render (sharp luma, bad chroma) "
                 "and BIBO_2x sl_q3's full-res PIPELINE render (good chroma, soft luma). "
                 "Convert both to LAB, take L from BIDO, a and b from BIBO, convert back. "
                 "Evaluate at the gate's 3840-wide metric resolution. PREVIEW "
                 f"ceilings: LPIPS ≤ {PREVIEW['lpips']}, MS-SSIM ≥ {PREVIEW['ms_ssim']}, "
                 f"Y-PSNR ≥ {PREVIEW['y_psnr']}, ΔE p95 ≤ {PREVIEW['delta_e_p95']}."
                 '</div>')

    for img in IMAGES:
        if img not in results:
            continue
        parts.append(f"<h2>{img}</h2>")
        parts.append("<table><thead><tr><th>variant</th><th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>ΔE mean</th><th>ΔE p95</th><th>PREVIEW</th></tr></thead><tbody>")
        for label, m in results[img].items():
            cls = "verdict-pass" if m["preview_pass"] else "verdict-fail"
            lp_cls = "pass" if m["lpips"] <= PREVIEW["lpips"] else "fail"
            ms_cls = "pass" if m["ms_ssim"] >= PREVIEW["ms_ssim"] else "fail"
            y_cls = "pass" if m["y_psnr"] >= PREVIEW["y_psnr"] else "fail"
            de_cls = "pass" if m["dE_p95"] <= PREVIEW["delta_e_p95"] else "fail"
            v = "PASS" if m["preview_pass"] else "FAIL"
            v_cls = "pass" if m["preview_pass"] else "fail"
            parts.append(
                f'<tr class="{cls}"><td class="label">{label}</td>'
                f'<td><span class="{lp_cls}">{m["lpips"]:.4f}</span></td>'
                f'<td><span class="{ms_cls}">{m["ms_ssim"]:.4f}</span></td>'
                f'<td><span class="{y_cls}">{m["y_psnr"]:.2f}</span></td>'
                f'<td>{m["dE_mean"]:.2f}</td>'
                f'<td><span class="{de_cls}">{m["dE_p95"]:.2f}</span></td>'
                f'<td><span class="{v_cls}">{v}</span></td></tr>'
            )
        parts.append("</tbody></table>")

    # Summary row across images
    parts.append("<h2>Worst-image summary across all four test images</h2>")
    parts.append("<table><thead><tr><th>variant</th><th>worst LPIPS</th><th>worst MS-SSIM</th><th>worst Y-PSNR</th><th>worst ΔE p95</th><th>all-images PASS</th></tr></thead><tbody>")
    for label in ["bido_w24", "bibo2x_sl_q3", "blend (BIDO L + BIBO ab)"]:
        worst_lp = max((results[img][label]["lpips"] for img in IMAGES if img in results), default=0)
        worst_ms = min((results[img][label]["ms_ssim"] for img in IMAGES if img in results), default=1)
        worst_y = min((results[img][label]["y_psnr"] for img in IMAGES if img in results), default=99)
        worst_de = max((results[img][label]["dE_p95"] for img in IMAGES if img in results), default=0)
        all_pass = all(results[img][label]["preview_pass"] for img in IMAGES if img in results)
        v = "PASS" if all_pass else "FAIL"
        v_cls = "pass" if all_pass else "fail"
        parts.append(
            f'<tr><td class="label">{label}</td>'
            f'<td><span class="{"pass" if worst_lp<=PREVIEW["lpips"] else "fail"}">{worst_lp:.4f}</span></td>'
            f'<td><span class="{"pass" if worst_ms>=PREVIEW["ms_ssim"] else "fail"}">{worst_ms:.4f}</span></td>'
            f'<td><span class="{"pass" if worst_y>=PREVIEW["y_psnr"] else "fail"}">{worst_y:.2f}</span></td>'
            f'<td><span class="{"pass" if worst_de<=PREVIEW["delta_e_p95"] else "fail"}">{worst_de:.2f}</span></td>'
            f'<td><span class="{v_cls}">{v}</span></td></tr>'
        )
    parts.append("</tbody></table>")

    parts.append("</body></html>")
    OUT.write_text("\n".join(parts))
    print(f"\nwrote {OUT}")


def main():
    print("=== Full-res LAB-swap blend gate evaluation ===")
    results = {}
    for img in IMAGES:
        try:
            results[img] = compute(img)
            for label, m in results[img].items():
                v = "PASS" if m["preview_pass"] else "FAIL"
                print(f"    {label:32}  LPIPS={m['lpips']:.4f}  MS-SSIM={m['ms_ssim']:.4f}  "
                      f"Y-PSNR={m['y_psnr']:.2f}  ΔE_p95={m['dE_p95']:.2f}  -> {v}")
        except Exception as e:
            print(f"  {img}: ERROR {type(e).__name__}: {e}")
    render_html(results)
    print("\nopen tests/quality_gates/runs/dashboard/blend_full_res_gate.html")


if __name__ == "__main__":
    main()
