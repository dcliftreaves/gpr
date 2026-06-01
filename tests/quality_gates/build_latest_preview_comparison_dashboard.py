#!/usr/bin/env python3
"""Build a focused latest PREVIEW comparison dashboard.

The dashboard answers one question: across the latest local gate runs, is the
remaining miss chroma, full-image/detail placement, or both?
"""
from __future__ import annotations

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
RUNS = REPO / "tests/quality_gates/runs"
DASH = RUNS / "dashboard"
OUT = DASH / "latest_preview_comparison.html"

IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")

GATE = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}

VARIANTS = [
    {
        "label": "No CNN",
        "run": "2362fb8cb863f4c5",
        "note": "ml2_q3_dec2 + bicubic. Honest embedded preview floor.",
    },
    {
        "label": "Matched BIDO",
        "run": "732da314adc90553",
        "note": "Matched 4x CNN. Sharper intent, but color drifts badly.",
    },
    {
        "label": "Lab Chroma SIPS",
        "run": "5e7d52579ffb2d3e",
        "note": "Latest display-space residual Lab chroma run. dE mean passes; detail metrics still fail.",
    },
    {
        "label": "Lab SIPS + Unsharp s07",
        "run": "1f1ef2ee138c51c3",
        "note": "Best registered luma-unsharp candidate so far. Passes 3/4 images; Z8Z_6693 remains detail-bound.",
    },
    {
        "label": "Full-Gate Linear Detail",
        "run": "387888dda9016edf",
        "note": "Constrained Lab-L high-pass sidecar fit on full-gate REF/PIPELINE pairs. Improves Y-PSNR but regresses LPIPS.",
    },
    {
        "label": "Blend Distill",
        "run": "8d4f8aa3eb81a99d",
        "note": "Older BIDO blend-distill checkpoint. Reject: regresses both detail placement and dE guardrail.",
    },
    {
        "label": "UPRESABLE Ref Path",
        "run": "8864c12ec0b6ce14",
        "note": "Offline BIBO_2x editable-raw path. Not a PREVIEW gate, but useful detail-placement reference.",
    },
]


def load_run(run_hash: str) -> dict:
    path = RUNS / run_hash / "run.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def metric_fails(m: dict) -> list[str]:
    out = []
    if m.get("lpips", 999.0) > GATE["lpips"]:
        out.append("LPIPS")
    if m.get("ms_ssim", 0.0) < GATE["ms_ssim"]:
        out.append("MS-SSIM")
    if m.get("y_psnr", 0.0) < GATE["y_psnr"]:
        out.append("Y-PSNR")
    if m.get("dE2000_mean", 999.0) > GATE["dE2000_mean"]:
        out.append("dE")
    return out


def diagnosis(m: dict) -> str:
    fails = set(metric_fails(m))
    color = "dE" in fails
    detail = bool(fails & {"LPIPS", "MS-SSIM", "Y-PSNR"})
    if color and detail:
        return "color + detail"
    if color:
        return "color"
    if detail:
        return "detail"
    return "passes"


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def psnr_from_mse(mse: float) -> float:
    return 99.0 if mse <= 1e-12 else 10.0 * math.log10(1.0 / mse)


def corr(a: np.ndarray, b: np.ndarray) -> float:
    ax = a.reshape(-1).astype(np.float64)
    bx = b.reshape(-1).astype(np.float64)
    ax -= ax.mean()
    bx -= bx.mean()
    den = math.sqrt(float((ax * ax).sum() * (bx * bx).sum()))
    return 0.0 if den <= 1e-12 else float((ax * bx).sum() / den)


def highpass_luma(luma: np.ndarray, sigma: float = 1.2) -> np.ndarray:
    return luma.astype(np.float32) - gaussian(
        luma.astype(np.float32), sigma=sigma, preserve_range=True
    ).astype(np.float32)


def crop_detail_metrics(ref_path: Path, pipe_path: Path) -> dict[str, float]:
    ref_rgb = load_rgb(ref_path)
    pipe_rgb = load_rgb(pipe_path)
    ref_lab = color.rgb2lab(np.clip(ref_rgb, 0, 1))
    pipe_lab = color.rgb2lab(np.clip(pipe_rgb, 0, 1))
    ref_l = ref_lab[..., 0]
    pipe_l = pipe_lab[..., 0]
    err_l = (pipe_l - ref_l) / 100.0
    ref_hp = highpass_luma(ref_l)
    pipe_hp = highpass_luma(pipe_l)
    ref_hp_rms = float(np.sqrt(np.mean(ref_hp * ref_hp)))
    pipe_hp_rms = float(np.sqrt(np.mean(pipe_hp * pipe_hp)))
    d_ab = pipe_lab[..., 1:3] - ref_lab[..., 1:3]
    return {
        "crop_l_ssim": float(structural_similarity(ref_l, pipe_l, data_range=100.0)),
        "crop_l_psnr": psnr_from_mse(float(np.mean(err_l * err_l))),
        "hp_ratio": float(pipe_hp_rms / max(ref_hp_rms, 1e-12)),
        "hp_corr": corr(ref_hp, pipe_hp),
        "crop_ab_mae": float(np.mean(np.abs(d_ab))),
        "crop_ab_p95": float(np.percentile(np.abs(d_ab), 95)),
    }


def fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return html.escape(value)
    return f"{float(value):.{digits}f}"


def cls_metric(name: str, value: float) -> str:
    if name == "lpips":
        return "pass" if value <= GATE[name] else "fail"
    if name in ("ms_ssim", "y_psnr"):
        return "pass" if value >= GATE[name] else "fail"
    if name == "dE2000_mean":
        return "pass" if value <= GATE[name] else "fail"
    return ""


def main() -> int:
    DASH.mkdir(parents=True, exist_ok=True)
    runs = {v["run"]: load_run(v["run"]) for v in VARIANTS}

    rows = []
    for variant in VARIANTS:
        run = runs[variant["run"]]
        for image_id in IMAGES:
            gate = run["images"][image_id]
            ref = Path(gate["ref_crop"])
            pipe = Path(gate["pipeline_crop"])
            detail = crop_detail_metrics(ref, pipe)
            rows.append({
                "variant": variant,
                "image_id": image_id,
                "gate": gate,
                "ref": ref,
                "pipe": pipe,
                "detail": detail,
                "diagnosis": diagnosis(gate),
            })

    worst_cards = []
    for variant in VARIANTS:
        run = runs[variant["run"]]
        image_metrics = run["images"]
        worst_lpips = max(image_metrics.items(), key=lambda kv: kv[1]["lpips"])
        worst_de = max(image_metrics.items(), key=lambda kv: kv[1]["dE2000_mean"])
        worst_msssim = min(image_metrics.items(), key=lambda kv: kv[1]["ms_ssim"])
        diagnoses = [diagnosis(image_metrics[i]) for i in IMAGES]
        worst_cards.append((variant, run, worst_lpips, worst_de, worst_msssim, diagnoses))

    css = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; margin: 24px; background: #f7f7f4; color: #222; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 18px; margin-top: 28px; }
.sub { color: #555; max-width: 1100px; line-height: 1.45; }
.cards { display: grid; grid-template-columns: repeat(5, minmax(190px, 1fr)); gap: 10px; margin: 18px 0; }
.card { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 12px; }
.card h3 { margin: 0 0 8px; font-size: 14px; }
.small { font-size: 12px; color: #666; line-height: 1.35; }
.pill { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 12px; border: 1px solid #ccc; background: #f4f4f4; }
.pass { color: #0a6f2a; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
.warn { color: #9a5a00; font-weight: 650; }
table { border-collapse: collapse; width: 100%; font-size: 12px; background: white; }
th, td { border: 1px solid #ddd; padding: 6px 7px; text-align: right; vertical-align: top; }
th { background: #ecece8; position: sticky; top: 0; z-index: 1; }
td.left, th.left { text-align: left; }
.visual { display: grid; grid-template-columns: 110px repeat(5, minmax(160px, 1fr)); gap: 8px; align-items: start; margin: 14px 0 26px; }
.label { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 9px; font-weight: 700; font-size: 13px; }
figure { background: white; border: 1px solid #ddd; border-radius: 6px; margin: 0; padding: 8px; }
figure img { width: 100%; display: block; border: 1px solid #ccc; }
figcaption { font-size: 11px; color: #555; margin-top: 6px; text-align: center; line-height: 1.3; }
.callout { background: #fff; border-left: 4px solid #4b6f9f; padding: 12px 14px; max-width: 1120px; line-height: 1.45; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
"""

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Latest PREVIEW comparison</title>",
        f"<style>{css}</style></head><body>",
        "<h1>Latest PREVIEW Comparison: Chroma vs Detail</h1>",
        "<div class='sub'>Compares the newest relevant local gate runs on all four gate examples. "
        "Gate thresholds: LPIPS <= 0.15, MS-SSIM >= 0.95, Y-PSNR >= 28, dE2000 mean <= 3. "
        "Crop diagnostics are computed from each run's saved <code>crop_A_detail</code> REF/PIPELINE images.</div>",
        "<div class='cards'>",
    ]

    for variant, run, worst_lpips, worst_de, worst_msssim, diagnoses in worst_cards:
        unique_diag = ", ".join(sorted(set(diagnoses)))
        parts.append(f"""
<div class="card">
  <h3>{html.escape(variant['label'])}</h3>
  <div class="small"><code>{variant['run']}</code></div>
  <div class="small">{html.escape(variant['note'])}</div>
  <p class="small">verdict: <span class="{'pass' if run['verdict'] == 'PASS' else 'fail'}">{run['verdict']}</span></p>
  <p class="small">worst LPIPS: <b>{worst_lpips[0]}</b> {worst_lpips[1]['lpips']:.3f}</p>
  <p class="small">worst dE: <b>{worst_de[0]}</b> {worst_de[1]['dE2000_mean']:.2f}</p>
  <p class="small">worst MS-SSIM: <b>{worst_msssim[0]}</b> {worst_msssim[1]['ms_ssim']:.3f}</p>
  <p><span class="pill">{html.escape(unique_diag)}</span></p>
</div>""")
    parts.append("</div>")

    parts.append("""
<div class="callout">
  <b>Read this first:</b> the latest display-space Lab chroma run keeps dE mean under the gate on all four examples,
  so it is not failing as a global chroma-direction problem. It still fails LPIPS/MS-SSIM on the hard texture images.
  The later Y/detail checkpoint did not fix that; it worsened LPIPS and pushes one image back over the dE threshold.
  This does not prove chroma is finished, but it shows the next experiment needs to preserve full-image texture/detail
  while treating dE as a guardrail.
</div>""")

    parts.append("<h2>Per-Image Metrics</h2>")
    parts.append("<table><thead><tr>"
                 "<th class='left'>image</th><th class='left'>variant</th><th class='left'>diagnosis</th>"
                 "<th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>dE mean</th>"
                 "<th>crop L-SSIM</th><th>crop L-PSNR</th><th>HP ratio</th><th>HP corr</th>"
                 "<th>crop |ab| MAE</th><th>crop |ab| p95</th>"
                 "</tr></thead><tbody>")
    for row in rows:
        g = row["gate"]
        d = row["detail"]
        parts.append(f"""
<tr>
  <td class="left">{row['image_id']}</td>
  <td class="left">{html.escape(row['variant']['label'])}</td>
  <td class="left">{html.escape(row['diagnosis'])}</td>
  <td class="{cls_metric('lpips', g['lpips'])}">{fmt(g['lpips'], 4)}</td>
  <td class="{cls_metric('ms_ssim', g['ms_ssim'])}">{fmt(g['ms_ssim'], 4)}</td>
  <td class="{cls_metric('y_psnr', g['y_psnr'])}">{fmt(g['y_psnr'], 2)}</td>
  <td class="{cls_metric('dE2000_mean', g['dE2000_mean'])}">{fmt(g['dE2000_mean'], 2)}</td>
  <td>{fmt(d['crop_l_ssim'], 4)}</td>
  <td>{fmt(d['crop_l_psnr'], 2)}</td>
  <td>{fmt(d['hp_ratio'], 3)}</td>
  <td>{fmt(d['hp_corr'], 3)}</td>
  <td>{fmt(d['crop_ab_mae'], 2)}</td>
  <td>{fmt(d['crop_ab_p95'], 2)}</td>
</tr>""")
    parts.append("</tbody></table>")

    parts.append("<h2>Visual Crops</h2>")
    parts.append("<div class='sub'>Each cell shows REF crop on top and PIPELINE crop below. "
                 "This is intentionally repetitive: it makes it easier to decide whether the visible miss is color, detail, or both.</div>")
    for image_id in IMAGES:
        parts.append("<div class='visual'>")
        parts.append(f"<div class='label'>{image_id}</div>")
        for variant in VARIANTS:
            run = runs[variant["run"]]
            gate = run["images"][image_id]
            ref_rel = Path("..") / variant["run"] / f"{image_id}_REF_crop_A_detail.png"
            pipe_rel = Path("..") / variant["run"] / f"{image_id}_PIPELINE_crop_A_detail.png"
            parts.append(f"""
<figure>
  <img src="{ref_rel.as_posix()}" alt="{image_id} REF">
  <figcaption>REF</figcaption>
  <img src="{pipe_rel.as_posix()}" alt="{image_id} {html.escape(variant['label'])}" style="margin-top:6px">
  <figcaption>{html.escape(variant['label'])}<br>LPIPS {gate['lpips']:.3f} · dE {gate['dE2000_mean']:.2f}</figcaption>
</figure>""")
        parts.append("</div>")

    parts.append("</body></html>")
    OUT.write_text("\n".join(parts))
    print(f"latest comparison dashboard: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
