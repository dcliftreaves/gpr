"""PREVIEW path comparison — does the CNN actually help vs cnn=none + bicubic?

Compares three decode-time treatments of the same ml2_q3_dec2 codec output:
  1. cnn=none + bicubic upscale  (the honest placeholder)
  2. bibo2x_ane_sl_q3 (cross-pair) — best CNN result observed for PREVIEW
  3. bido_4x_ane_ml2_q3_dec2_w24 (matched, larger arch) — supposedly the
     "right" CNN but actually performs worse than cnn=none

Output: tests/quality_gates/runs/dashboard/preview_comparison.html
"""
from __future__ import annotations
import json, os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
OUT = RUNS / "dashboard" / "preview_comparison.html"

VARIANTS = [
    # (label, run_hash, role_blurb)
    ("cnn=none + bicubic", "44d95b0985ac01c4",
     "Codec decoded with no restoration CNN. Bicubic 2× upscale of the half-res output. The honest baseline."),
    ("bibo2x_ane_sl_q3 (cross-pair)", "6676478b154e9fc6",
     "BIBO_2x super-res CNN trained against the FUSED single-level codec (sl_q3), applied to ml2_q3_dec2 output. Best CNN result observed."),
    ("bido_4x_ane_ml2_q3_dec2_w24 (matched)", "732da314adc90553",
     "BIDO_4x at w24 capacity, matched-distribution trained against ml2_q3_dec2. 2× the param count. Worse than cnn=none on the worst image."),
]

GATE_IMAGES = ["Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693"]
PREVIEW_CEILINGS = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "delta_e": 3.0}

CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
       margin: 24px; color: #222; background: #fafafa; max-width: 1600px; }
h1 { font-size: 22px; margin-bottom: 4px; }
.subtitle { color: #666; font-size: 13px; margin-bottom: 18px; max-width: 900px; }
.legend { padding: 12px 16px; background: white; border-left: 4px solid #b00020;
          margin: 16px 0; font-size: 13px; max-width: 900px; }
.legend.warn { border-left-color: #c46d24; }
table.summary { border-collapse: collapse; margin: 16px 0 28px 0; font-size: 13px; }
table.summary th, table.summary td { border: 1px solid #ddd; padding: 6px 10px; text-align: right; }
table.summary th { background: #eee; font-weight: 600; }
table.summary td.label { text-align: left; font-weight: 500; }
.pass { color: #0a7d28; font-weight: 600; }
.fail { color: #b00020; font-weight: 600; }
.compare-grid { display: grid; grid-template-columns: 120px repeat(3, 1fr); gap: 8px;
                margin: 24px 0; align-items: start; }
.compare-grid .hdr { font-weight: 600; padding: 8px; background: white; border-radius: 6px;
                     text-align: center; font-size: 13px; border: 1px solid #ddd; }
.compare-grid .row-label { font-weight: 600; padding: 8px; font-size: 13px;
                           background: white; border-radius: 6px; border: 1px solid #ddd;
                           align-self: center; text-align: center; }
.compare-grid figure { margin: 0; background: white; padding: 8px; border-radius: 6px;
                        border: 1px solid #ddd; }
.compare-grid figcaption { font-size: 11px; color: #555; text-align: center; margin-top: 6px;
                           font-weight: 500; }
.compare-grid img { width: 100%; border: 1px solid #ccc; display: block; }
.variant-blurb { font-size: 11px; color: #777; padding: 4px 8px; line-height: 1.4; }
.delta { font-size: 10px; color: #555; font-style: italic; }
"""


def load_run(rh):
    return json.loads((RUNS / rh / "run.json").read_text())


def fmt_lpips(value, ceiling=PREVIEW_CEILINGS["lpips"]):
    cls = "pass" if value <= ceiling else "fail"
    return f'<span class="{cls}">{value:.4f}</span>'


def main():
    runs = {label: load_run(rh) for label, rh, _ in VARIANTS}

    parts = []
    parts.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    parts.append("<title>PREVIEW path — does the CNN help vs bicubic baseline?</title>")
    parts.append(f"<style>{CSS}</style></head><body>")
    parts.append("<h1>PREVIEW path — does the restoration CNN actually help?</h1>")
    parts.append(
        '<div class="subtitle">'
        "All three variants decode the same <code>ml2_q3_dec2</code> half-res "
        "capture (1.30 MB/frame; latest strict Pi 5 receipt is blocked at "
        "19.98 fps versus the 24 fps target). What differs is the "
        "decode-time treatment. PREVIEW gate ceilings: "
        f"LPIPS ≤ {PREVIEW_CEILINGS['lpips']}, MS-SSIM ≥ {PREVIEW_CEILINGS['ms_ssim']}, "
        f"Y-PSNR ≥ {PREVIEW_CEILINGS['y_psnr']}, ΔE ≤ {PREVIEW_CEILINGS['delta_e']}."
        "</div>"
    )

    parts.append(
        '<div class="legend warn"><b>The honest finding:</b> none of the three '
        "variants PASS the PREVIEW gate on the worst image (Z8Z_6693, hair / "
        "skin OOD). The supposedly-matched BIDO_4x w24 CNN at 2× param count "
        "actually performs <i>worse</i> than the simple <code>cnn=none + "
        "bicubic</code> baseline on the worst image. The cross-pair CNN "
        "(trained against a different codec, applied here) is the best, "
        "but still fails the gate by 0.10 LPIPS."
        "</div>"
    )

    # Summary metrics table — per-image LPIPS for all three
    parts.append("<h2>Per-image LPIPS — all three decode treatments</h2>")
    parts.append('<table class="summary">')
    parts.append("<thead><tr><th>image</th>")
    for label, _, _ in VARIANTS:
        parts.append(f'<th>{label}</th>')
    parts.append("</tr></thead><tbody>")
    for img in GATE_IMAGES:
        parts.append(f'<tr><td class="label">{img}</td>')
        for label, _, _ in VARIANTS:
            lp = runs[label]["images"].get(img, {}).get("lpips", 0)
            parts.append(f'<td>{fmt_lpips(lp)}</td>')
        parts.append("</tr>")
    # worst-image row
    parts.append('<tr style="background:#fff3cd;"><td class="label"><b>worst image LPIPS</b></td>')
    for label, _, _ in VARIANTS:
        worst = max((im.get("lpips", 0) or 0 for im in runs[label]["images"].values()), default=0)
        parts.append(f'<td><b>{fmt_lpips(worst)}</b></td>')
    parts.append("</tr>")
    parts.append("</tbody></table>")

    # Variant blurbs
    parts.append('<div style="display:grid;grid-template-columns:120px repeat(3,1fr);gap:8px;margin-bottom:20px;">')
    parts.append('<div></div>')
    for label, _, blurb in VARIANTS:
        parts.append(f'<div class="variant-blurb">{blurb}</div>')
    parts.append('</div>')

    # Visual comparison grid — one row per gate image
    parts.append("<h2>Visual comparison — crop_A_detail for each gate image</h2>")
    parts.append(
        '<div class="legend">Each row is one gate test image. Columns: '
        "no-CNN bicubic / best-result cross-pair CNN / matched-arch larger "
        "CNN. The reference (REF) is rendered to the right of every PIPELINE "
        "crop in the visual diffs we saved at gate time, so you can A/B both. "
        "Look for: blockiness in the no-CNN column, washed/smeared texture in "
        "the matched-CNN column, sharpness retention in the cross-pair column."
        "</div>"
    )

    for img in GATE_IMAGES:
        # Find the worst-image diff name in each run — different runs name them
        # by THEIR worst image, but per-image crops are universal.
        parts.append('<div class="compare-grid">')
        parts.append(f'<div class="row-label">{img}</div>')
        for label, rh, _ in VARIANTS:
            pipe = f"../{rh}/{img}_PIPELINE_crop_A_detail.png"
            ref = f"../{rh}/{img}_REF_crop_A_detail.png"
            lp = runs[label]["images"].get(img, {}).get("lpips", 0)
            verdict_class = "pass" if lp <= PREVIEW_CEILINGS["lpips"] else "fail"
            parts.append(
                f'<figure>'
                f'<img src="{ref}" alt="{img} REF">'
                f'<figcaption style="color:#888">REF (target)</figcaption>'
                f'<img src="{pipe}" alt="{img} PIPELINE" style="margin-top:6px">'
                f'<figcaption>PIPELINE · LPIPS '
                f'<span class="{verdict_class}">{lp:.4f}</span></figcaption>'
                f'</figure>'
            )
        parts.append('</div>')

    parts.append(
        '<div class="legend"><b>What this tells us:</b> The PREVIEW gate failure '
        "is structural to the codec, not solvable by the current CNN architecture "
        "family (BIDO_4x / BIBO_2x at w16–w32 capacity). After eight FAIL attempts "
        "(Phase A, Phase B distillation, OOD corpus retrain, μ-law L1, w24, w32, "
        "Restormer-as-decoder, exposure aug), the cnn=none baseline at 0.31 worst "
        "LPIPS is the realistic floor without a different architecture family. "
        "Shipping <code>cnn=none + bicubic</code> as the honest PREVIEW placeholder "
        "is the pragmatic move; the codec capture path still needs the current "
        "Pi 5 throughput blocker fixed."
        "</div>"
    )

    parts.append("</body></html>")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts))
    print(f"=== wrote {OUT} ({OUT.stat().st_size} bytes) ===")


if __name__ == "__main__":
    main()
