"""q-level decision dashboard — visualize every legacy gpr_tools q level
post-CNN (or codec-alone where CNN-free passes) so the user can decide
whether to promote q=0+CNN as a third STILL tier.

Output: tests/quality_gates/runs/dashboard/q_level_decision.html

For each q in 0..8 it shows:
  - codec mean MB, worst LPIPS / MS-SSIM / Y-PSNR / dE
  - the WORST visual-diff PNG (REF | PIPELINE) for the gate's hardest image
  - the per-image crops in expandable detail

The three highlighted candidates for a possible three-tier ship:
  q=0 (smallest, 9.80 MB)
  q=3 (current STILL primary, 15.05 MB)
  q=8 (current STILL archival, 27.17 MB)
"""
from __future__ import annotations
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
OUT = RUNS / "dashboard" / "q_level_decision.html"

# Manually mapped — run hashes for each q-level pipeline.
# Run hashes were located by grep against pipeline name in run.json.
Q_RUNS = [
    # (q, cnn_label, run_hash, tier_note)
    (0, "matched-q3 CNN", "6c36c53dfec8cd46", "PROPOSED SMALLEST"),
    (1, "matched-q3 CNN", "92c6f588563d8cad", ""),
    (2, "matched-q3 CNN", "a756fd21ed9191be", ""),
    (3, "matched-q3 CNN", "db12063273f2f639", "CURRENT PRIMARY"),
    (4, "no CNN", "a693cbd65e82ab3f", ""),
    (5, "no CNN", "f698157ba2ef4fec", ""),
    (6, "no CNN", "1f2106321adc5654", ""),
    (7, "no CNN", "75ebf63999c92fb2", ""),
    (8, "no CNN", "ff37c83c928cbdb8", "CURRENT ARCHIVAL"),
]

# Gate ceilings (STILL class) — copy of the values shown in SHIP_DECISION.md.
CEILINGS = {"lpips": 0.05, "ms_ssim": 0.99, "y_psnr": 35.0, "delta_e": 1.5}

CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
       margin: 24px; color: #222; background: #fafafa; }
h1 { font-size: 22px; margin-bottom: 4px; }
.subtitle { color: #666; font-size: 13px; margin-bottom: 24px; }
table.summary { border-collapse: collapse; margin: 16px 0 32px 0; font-size: 13px; }
table.summary th, table.summary td { border: 1px solid #ddd; padding: 6px 10px; text-align: right; }
table.summary th { background: #eee; font-weight: 600; }
table.summary td.label { text-align: left; font-weight: 500; }
table.summary tr.tier td { background: #fff8d6; font-weight: 600; }
table.summary tr.smallest td { background: #d6f0ff; font-weight: 700; }
table.summary tr.primary td { background: #d8e8ff; font-weight: 700; }
table.summary tr.archival td { background: #ffe2c7; font-weight: 700; }
.pass { color: #0a7d28; font-weight: 600; }
.fail { color: #b00020; font-weight: 600; }
.q-block { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 16px;
           margin-bottom: 28px; }
.q-block h2 { margin: 0 0 8px 0; font-size: 17px; }
.q-block .tier-pill { display: inline-block; background: #ffe066; color: #5a4500;
                      padding: 2px 8px; border-radius: 8px; font-size: 11px;
                      vertical-align: middle; margin-left: 8px; }
.q-block.smallest { background: #f4faff; border-color: #6cb0e5; }
.q-block.smallest .tier-pill { background: #2576c4; color: white; }
.q-block.primary { background: #f0f5ff; border-color: #5a8fdc; }
.q-block.primary .tier-pill { background: #1a5fb4; color: white; }
.q-block.archival { background: #fff6ed; border-color: #d99454; }
.q-block.archival .tier-pill { background: #c46d24; color: white; }
.metrics { display: inline-block; margin-right: 24px; font-size: 13px; color: #555; }
.metrics b { color: #222; font-size: 14px; }
.diff-image { display: block; max-width: 100%; margin: 12px 0; border: 1px solid #ccc; }
details { margin-top: 8px; }
details summary { cursor: pointer; font-size: 12px; color: #555; }
.per-image { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
.per-image figure { margin: 0; }
.per-image figcaption { font-size: 11px; color: #666; text-align: center; margin-top: 2px; }
.per-image img { width: 100%; border: 1px solid #ccc; }
.legend { padding: 12px 16px; background: white; border-left: 4px solid #1a5fb4;
          margin-bottom: 20px; font-size: 13px; }
.three-up { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 20px 0; }
.three-up figure { margin: 0; background: white; padding: 8px; border-radius: 8px;
                   border: 1px solid #ddd; }
.three-up figcaption { font-size: 12px; text-align: center; margin-top: 6px; }
.three-up img { width: 100%; border: 1px solid #ccc; }
.three-up .smallest figure { border-color: #2576c4; }
.context-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0 28px 0; }
.context-row figure { margin: 0; background: white; padding: 8px; border-radius: 8px;
                      border: 1px solid #ddd; }
.context-row figcaption { font-size: 12px; text-align: center; margin-top: 6px; }
.context-row img { width: 100%; border: 1px solid #ccc; }
"""

GATE_IMAGES = ["Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693"]


def load_run(rh):
    p = RUNS / rh / "run.json"
    return json.loads(p.read_text()) if p.exists() else None


def metric_row(q, cnn_label, rh, tier):
    d = load_run(rh)
    if d is None:
        return None
    imgs = d.get("images", {})
    worst_lpips = max((im.get("lpips", 0) or 0 for im in imgs.values()), default=0)
    worst_ms = min((im.get("ms_ssim", 0) or 0 for im in imgs.values()), default=0)
    worst_y = min((im.get("y_psnr", 0) or 0 for im in imgs.values()), default=0)
    worst_de = max((im.get("delta_e", 0) or 0 for im in imgs.values()), default=0)
    bytes_list = [im.get("enc_bytes", 0) for im in imgs.values()]
    mean_mb = (sum(bytes_list) / len(bytes_list) / 1e6) if bytes_list else 0.0
    verdict = d.get("verdict", "?")
    return {
        "q": q,
        "cnn": cnn_label,
        "rh": rh,
        "tier": tier,
        "mean_mb": mean_mb,
        "lpips": worst_lpips,
        "ms_ssim": worst_ms,
        "y_psnr": worst_y,
        "delta_e": worst_de,
        "verdict": verdict,
    }


def fmt_metric(value, threshold, lower_is_better):
    """Format value with PASS/FAIL coloring relative to a ceiling."""
    if lower_is_better:
        ok = value <= threshold
    else:
        ok = value >= threshold
    cls = "pass" if ok else "fail"
    return f'<span class="{cls}">{value:.4f}</span>'


def make_html(rows):
    parts = []
    parts.append("<!DOCTYPE html><html><head>")
    parts.append('<meta charset="utf-8">')
    parts.append("<title>q-level decision dashboard — STILL ship</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("</head><body>")
    parts.append("<h1>Stills q-level decision dashboard</h1>")
    parts.append(
        '<div class="subtitle">'
        "All values are end-to-end gate metrics (codec roundtrip → CNN → sips render vs REF). "
        "Per-image worst-case shown. STILL gate ceilings: "
        f"LPIPS ≤ {CEILINGS['lpips']}, MS-SSIM ≥ {CEILINGS['ms_ssim']}, "
        f"Y-PSNR ≥ {CEILINGS['y_psnr']}, ΔE2000 ≤ {CEILINGS['delta_e']}."
        "</div>"
    )

    parts.append(
        '<div class="legend"><b>The question:</b> Is q=0 + matched-q3 CNN '
        "(9.80 MB mean) worth promoting as a third STILL tier? "
        "Currently the ship is two-tier: primary q=3 (15.05 MB) and archival q=8 (27.17 MB). "
        "q=0 PASSes STILL on metrics; the call is whether the visible quality holds up to inspection."
        "</div>"
    )

    # --- Test-set context: full-frame thumbnails so reader knows the content ---
    parts.append("<h2>What the gate test set actually is</h2>")
    parts.append('<div class="context-row">')
    for img, role in [
        ("Z8Z_0001", "rocks / shadows — <b>canonical fine-detail diagnostic</b>"),
        ("Z8Z_0067", "sky / skin — easy smooth-gradient"),
        ("Z8Z_5323", "studio shot — sharp edges + saturated"),
        ("Z8Z_6693", "hair / portrait — OOD worst LPIPS"),
    ]:
        parts.append(
            f'<figure><img src="context/{img}_full.png" alt="{img}">'
            f"<figcaption><b>{img}</b><br>{role}</figcaption></figure>"
        )
    parts.append("</div>")

    # --- 3-way visual comparison for the decision ---
    # Lead with Z8Z_0001 (the canonical fine-detail/blockiness diagnostic) NOT
    # Z8Z_6693 hair (which is the LPIPS worst but where compression artifacts
    # are hidden by texture randomness). The user wants to see whether codec
    # artifacts are visible at q=0 — that means looking at sharp edges and
    # fine texture, which is exactly what Z8Z_0001 is for.
    parts.append("<h2>q=0 vs q=3 vs q=8 — Z8Z_0001 (the fine-detail diagnostic)</h2>")
    parts.append(
        '<div class="legend" style="border-left-color:#0a7d28;">'
        "<b>Look for:</b> blockiness / cross-hatch on the sharp pebble edges, "
        "smearing on the dark shadows, color noise in the flat brown areas. "
        "If you can't see a difference between q=0 and q=8 here, the codec at "
        "q=0 + matched-q3 CNN is producing visually indistinguishable output "
        "on the hardest content the test set has."
        "</div>"
    )
    parts.append('<div class="three-up">')
    for r in rows:
        if r["tier"] not in {"PROPOSED SMALLEST", "CURRENT PRIMARY", "CURRENT ARCHIVAL"}:
            continue
        tier_class = r["tier"].lower().split()[-1]
        verdict_class = "pass" if r["verdict"] == "PASS" else "fail"
        pipe_rel = f"../{r['rh']}/Z8Z_0001_PIPELINE_crop_A_detail.png"
        parts.append(
            f'<figure class="{tier_class}"><img src="{pipe_rel}" alt="q={r["q"]}">'
            f"<figcaption>"
            f"<b>q={r['q']}</b> · {r['mean_mb']:.2f} MB · "
            f'worst LPIPS <span class="{verdict_class}">{r["lpips"]:.4f}</span><br>'
            f"<i>{r['tier']}</i>"
            f"</figcaption></figure>"
        )
    # Plus the REF for direct comparison
    parts.append(
        '<figure style="grid-column: 1 / -1;">'
        f'<img src="../{rows[0]["rh"]}/Z8Z_0001_REF_crop_A_detail.png" alt="REF">'
        "<figcaption><b>REF</b> — the sips render of the source DNG, "
        "the target the pipeline is trying to match</figcaption></figure>"
    )
    parts.append("</div>")

    # --- Second visual comparison: hair worst (Z8Z_6693) ---
    parts.append("<h2>q=0 vs q=3 vs q=8 — Z8Z_6693 (LPIPS worst — hair texture)</h2>")
    parts.append(
        '<div class="legend">For completeness — this is the image with the '
        "highest LPIPS in every q-row. Differences here are sub-visible at "
        "all three q levels because hair grain is statistically dominated by "
        "the camera's noise rather than the codec's quantization.</div>"
    )
    parts.append('<div class="three-up">')
    for r in rows:
        if r["tier"] not in {"PROPOSED SMALLEST", "CURRENT PRIMARY", "CURRENT ARCHIVAL"}:
            continue
        tier_class = r["tier"].lower().split()[-1]
        verdict_class = "pass" if r["verdict"] == "PASS" else "fail"
        diff_rel = f"../{r['rh']}/WORST_Z8Z_6693_visual_diff.png"
        parts.append(
            f'<figure class="{tier_class}"><img src="{diff_rel}" alt="q={r["q"]}">'
            f"<figcaption><b>q={r['q']}</b> · LPIPS "
            f'<span class="{verdict_class}">{r["lpips"]:.4f}</span></figcaption>'
            f"</figure>"
        )
    parts.append("</div>")

    # --- Summary table ---
    parts.append("<h2>Summary table — all q levels</h2>")
    parts.append('<table class="summary">')
    parts.append(
        "<thead><tr>"
        "<th>q</th><th>CNN</th><th>mean MB</th>"
        "<th>worst LPIPS<br><small>≤ 0.05</small></th>"
        "<th>worst MS-SSIM<br><small>≥ 0.99</small></th>"
        "<th>worst Y-PSNR<br><small>≥ 35</small></th>"
        "<th>worst ΔE<br><small>≤ 1.5</small></th>"
        "<th>verdict</th><th>tier</th>"
        "</tr></thead><tbody>"
    )
    for r in rows:
        cls = ""
        if r["tier"] == "PROPOSED SMALLEST": cls = "smallest"
        elif r["tier"] == "CURRENT PRIMARY": cls = "primary"
        elif r["tier"] == "CURRENT ARCHIVAL": cls = "archival"
        verdict_class = "pass" if r["verdict"] == "PASS" else "fail"
        parts.append(
            f'<tr class="{cls}">'
            f'<td class="label">q={r["q"]}</td>'
            f'<td class="label">{r["cnn"]}</td>'
            f'<td>{r["mean_mb"]:.2f}</td>'
            f'<td>{fmt_metric(r["lpips"], CEILINGS["lpips"], True)}</td>'
            f'<td>{fmt_metric(r["ms_ssim"], CEILINGS["ms_ssim"], False)}</td>'
            f'<td>{fmt_metric(r["y_psnr"], CEILINGS["y_psnr"], False)}</td>'
            f'<td>{fmt_metric(r["delta_e"], CEILINGS["delta_e"], True)}</td>'
            f'<td class="{verdict_class}">{r["verdict"]}</td>'
            f'<td class="label">{r["tier"]}</td>'
            f"</tr>"
        )
    parts.append("</tbody></table>")

    # --- Per-q detailed blocks ---
    parts.append("<h2>Per-q visual diff and per-image crops</h2>")
    for r in rows:
        cls = ""
        if r["tier"] == "PROPOSED SMALLEST": cls = "smallest"
        elif r["tier"] == "CURRENT PRIMARY": cls = "primary"
        elif r["tier"] == "CURRENT ARCHIVAL": cls = "archival"
        pill = f'<span class="tier-pill">{r["tier"]}</span>' if r["tier"] else ""
        verdict_class = "pass" if r["verdict"] == "PASS" else "fail"
        parts.append(f'<div class="q-block {cls}">')
        parts.append(f'<h2>q={r["q"]} · {r["cnn"]} {pill}</h2>')
        parts.append(
            f'<div class="metrics">mean MB: <b>{r["mean_mb"]:.2f}</b></div>'
            f'<div class="metrics">worst LPIPS: <b class="{verdict_class}">{r["lpips"]:.4f}</b></div>'
            f'<div class="metrics">worst MS-SSIM: <b>{r["ms_ssim"]:.4f}</b></div>'
            f'<div class="metrics">worst Y-PSNR: <b>{r["y_psnr"]:.2f} dB</b></div>'
            f'<div class="metrics">worst ΔE: <b>{r["delta_e"]:.3f}</b></div>'
            f'<div class="metrics">verdict: <b class="{verdict_class}">{r["verdict"]}</b></div>'
            f'<div class="metrics" style="float:right;font-size:11px;color:#888;">'
            f"run hash: <code>{r['rh']}</code></div>"
        )
        # Worst-image visual diff (Z8Z_6693 in every case)
        diff_rel = f"../{r['rh']}/WORST_Z8Z_6693_visual_diff.png"
        parts.append(
            f'<img class="diff-image" src="{diff_rel}" alt="WORST Z8Z_6693 visual diff">'
        )
        # Per-image crop grid
        parts.append("<details><summary>Per-image crops (REF | PIPELINE)</summary>")
        parts.append('<div class="per-image">')
        for img in GATE_IMAGES:
            ref = f"../{r['rh']}/{img}_REF_crop_A_detail.png"
            pipe = f"../{r['rh']}/{img}_PIPELINE_crop_A_detail.png"
            parts.append(
                f'<figure><img src="{ref}" alt="{img} REF"><figcaption>{img} REF</figcaption></figure>'
                f'<figure><img src="{pipe}" alt="{img} PIPE"><figcaption>{img} PIPE</figcaption></figure>'
            )
        parts.append("</div></details>")
        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def main():
    rows = []
    for q, cnn, rh, tier in Q_RUNS:
        r = metric_row(q, cnn, rh, tier)
        if r is None:
            print(f"  MISSING run {rh} for q={q}")
            continue
        rows.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(make_html(rows))
    print(f"=== wrote {OUT} ({OUT.stat().st_size} bytes, {len(rows)} q-rows) ===")
    print(f"open with: open '{OUT}'")


if __name__ == "__main__":
    main()
