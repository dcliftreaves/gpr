"""Focused dashboard: just the things that need user review/decision.

Generates a smaller HTML with side-by-side worst-image crops for the
items that need an actual call from the user (new ship candidates,
near-misses, etc) — vs the full sweep dashboard which dumps everything.

Output: tests/quality_gates/runs/dashboard/review.html
"""
import json
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
OUT = RUNS / "dashboard" / "review.html"

# Cherry-picked runs that the user should actually look at, with the
# call-to-action for each. Run-hashes are stable per (pipeline, gates_sha).
REVIEWS = [
    # ---- Current gate-pass ships that need claim/audit trail ----
    {
        "title": "STILL — current primary ship, claim needed",
        "pipeline": "codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools",
        "decision": "PASS for STILL at 15.05 MB mean. This is the current primary "
                    "stills ship: much smaller than q8/no-CNN while staying well "
                    "inside the STILL gate. Next action is a visual-inspection "
                    "claim, not another sweep.",
        "vs": "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools",
        "vs_label": "archival q8/no-CNN",
    },
    {
        "title": "VIDEO_FREEZE — current primary ship, claim needed",
        "pipeline": "codec=ml2_q3_l1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools",
        "decision": "PASS for VIDEO_FREEZE at 7.81 MB mean. This remains the "
                    "best size/quality balance among full-res ML2 options. Next "
                    "action is a visual-inspection claim.",
        "vs": "codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools",
        "vs_label": "larger tighter-LPIPS alternate",
    },
    {
        "title": "PREVIEW — only current gate-pass baseline",
        "pipeline": "codec=sl_q3+cnn=none+demosaic=sips_via_gpr_tools",
        "decision": "PASS for PREVIEW, but at 26.60 MB mean it is not the "
                    "embedded-preview answer. Treat this as the visual floor / "
                    "claimable fallback while the ml2_q3_dec2 chroma path is "
                    "still under repair.",
        "vs": "codec=ml2_q3_dec2+cnn=none+demosaic=sips_via_gpr_tools",
        "vs_label": "embedded-size codec/no-CNN fail",
    },
    # ---- New M5 result ----
    {
        "title": "UPRESABLE — M5 gateclean retrain vs current alternate",
        "pipeline": "codec=ml2_q3_dec2+cnn=bibo2x_ane_ml2_q3_dec2_msssim_gateclean+demosaic=sips_via_gpr_tools",
        "decision": "PASS for UPRESABLE and slightly improves Z8Z_6693 rendered "
                    "LPIPS versus the diverse checkpoint (0.325 vs 0.343), but "
                    "the inspected worst diff still has smoother texture than "
                    "REF. Keep as an alternate unless we want to promote a small "
                    "metric win; the next real render-quality work is texture/"
                    "grain restoration, not another retrain on this axis.",
        "vs": "codec=ml2_q3_dec2+cnn=bibo2x_ane_ml2_q3_dec2_diverse+demosaic=sips_via_gpr_tools",
        "vs_label": "current UPRESABLE alternate",
    },
    # ---- Active blocker ----
    {
        "title": "PREVIEW embedded blocker — chroma/decomp path still fails",
        "pipeline": "codec=ml2_q3_dec2+cnn=ycbcr_decomp_y_w16_cb_w8_cr_w8+demosaic=sips_via_gpr_tools",
        "decision": "FAIL for PREVIEW at embedded size. This is why the next "
                    "work item is the Lab chroma-corrector sidecar/trainer: "
                    "the codec size is right, but the current decomp/chroma "
                    "render path misses visual gates.",
        "vs": "codec=ml2_q3_dec2+cnn=none+demosaic=sips_via_gpr_tools",
        "vs_label": "embedded-size no-CNN baseline",
    },
]


def latest_run_for(pipeline_name):
    """Return (run_dir, run.json data) for the most recent run of this pipeline."""
    best = None
    best_mtime = -1
    for d in os.listdir(RUNS):
        rj = RUNS / d / "run.json"
        if not rj.is_file(): continue
        try:
            data = json.loads(rj.read_text())
            if data.get("pipeline") != pipeline_name: continue
            mtime = rj.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best = (RUNS / d, data)
        except Exception: pass
    return best


def format_metrics(data):
    if data is None: return "(no run found)"
    rows = []
    for name, m in sorted(data.get("images", {}).items(),
                          key=lambda kv: -kv[1].get("lpips", 0)):
        lp = m.get("lpips", 0)
        y = m.get("y_psnr", 0)
        ms = m.get("ms_ssim", 0)
        dE = m.get("dE2000_mean", m.get("dE2000", 0))
        bp = m.get("bayer_psnr_final")
        bp_txt = f"{bp:.2f}" if isinstance(bp, (int, float)) else "-"
        rows.append(
            f"<tr><td>{name}</td><td>{lp:.4f}</td><td>{y:.2f}</td>"
            f"<td>{ms:.4f}</td><td>{dE:.2f}</td>"
            f"<td>{bp_txt}</td>"
            f"<td>{m.get('verdict','?')}</td></tr>"
        )
    bytes_list = [m.get("enc_bytes", 0) for m in data.get("images", {}).values()]
    mean_mb = sum(bytes_list) / len(bytes_list) / 1e6 if bytes_list else 0
    return (
        f"<p><b>Run:</b> {data.get('run_hash','?')} "
        f"&nbsp;<b>Verdict:</b> {data.get('verdict','?')} "
        f"({data.get('ship_class','?')}) "
        f"&nbsp;<b>Mean bytes:</b> {mean_mb:.2f} MB</p>"
        f"<table class=metrics><tr><th>image</th><th>LPIPS</th>"
        f"<th>Y-PSNR</th><th>MS-SSIM</th><th>ΔE2000</th>"
        f"<th>Bayer PSNR</th><th>verdict</th></tr>"
        + "".join(rows) + "</table>"
    )


def find_worst_diff(run_dir):
    for f in run_dir.glob("WORST_*_visual_diff.png"):
        return f
    return None


def find_image_crops(run_dir, image_id):
    """Return (ref_crop, pipeline_crop) for the given image, or (None, None)."""
    ref = run_dir / f"{image_id}_REF_crop_A_detail.png"
    pipe = run_dir / f"{image_id}_PIPELINE_crop_A_detail.png"
    return (ref if ref.exists() else None, pipe if pipe.exists() else None)


def relpath(p):
    return os.path.relpath(p, OUT.parent)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sections = []
    for r in REVIEWS:
        pn = r["pipeline"]
        candidate = latest_run_for(pn)
        baseline = latest_run_for(r["vs"]) if r.get("vs") else None
        worst_cand = find_worst_diff(candidate[0]) if candidate else None
        worst_base = find_worst_diff(baseline[0]) if baseline else None

        worst_html = ""
        if worst_cand:
            worst_html += (
                f"<div class=col><div class=caption>candidate worst-image diff "
                f"(REF | PIPELINE)</div>"
                f"<img src='{relpath(worst_cand)}' /></div>"
            )
        if worst_base:
            worst_html += (
                f"<div class=col><div class=caption>{r['vs_label']} worst-image diff</div>"
                f"<img src='{relpath(worst_base)}' /></div>"
            )

        # Z8Z_0001 — same image across all candidates, useful for direct comparison
        z0001_html = ""
        if candidate:
            ref_c, pipe_c = find_image_crops(candidate[0], "Z8Z_0001")
            if ref_c and pipe_c:
                lp = candidate[1]['images'].get('Z8Z_0001', {}).get('lpips', 0)
                z0001_html += (
                    f"<div class=col><div class=caption>Z8Z_0001 REF (this run's REF render)</div>"
                    f"<img src='{relpath(ref_c)}' /></div>"
                    f"<div class=col><div class=caption>Z8Z_0001 PIPELINE — candidate (LPIPS {lp:.4f})</div>"
                    f"<img src='{relpath(pipe_c)}' /></div>"
                )
        if baseline:
            _, pipe_b = find_image_crops(baseline[0], "Z8Z_0001")
            if pipe_b:
                lp = baseline[1]['images'].get('Z8Z_0001', {}).get('lpips', 0)
                z0001_html += (
                    f"<div class=col><div class=caption>Z8Z_0001 PIPELINE — {r['vs_label']} (LPIPS {lp:.4f})</div>"
                    f"<img src='{relpath(pipe_b)}' /></div>"
                )

        sections.append(f"""
        <section>
          <h2>{r['title']}</h2>
          <p class=cta><b>Decision:</b> {r['decision']}</p>
          <h3>Candidate: <code>{pn}</code></h3>
          {format_metrics(candidate[1] if candidate else None)}
          <h3>Baseline for comparison: <code>{r['vs']}</code></h3>
          {format_metrics(baseline[1] if baseline else None)}
          <h3>Worst-image side-by-side</h3>
          <div class=row>{worst_html}</div>
          <h3>Z8Z_0001 — same image, consistent across all candidates</h3>
          <div class=row>{z0001_html}</div>
        </section>
        """)

    html = f"""<!doctype html>
<html><head><meta charset=utf-8><title>Review dashboard — {time.strftime('%Y-%m-%d')}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1400px; margin: 2em auto; padding: 0 1em; color: #222; }}
section {{ border-top: 3px solid #444; padding: 1.5em 0; }}
h2 {{ margin-top: 0; color: #036; }}
.cta {{ background: #ffd; padding: 0.8em 1em; border-left: 4px solid #c80; }}
table.metrics {{ border-collapse: collapse; margin: 0.5em 0; font-family: monospace; font-size: 0.9em; }}
table.metrics th, table.metrics td {{ border: 1px solid #ccc; padding: 3px 8px; text-align: right; }}
table.metrics th {{ background: #eee; }}
table.metrics td:first-child {{ text-align: left; }}
.row {{ display: flex; gap: 1em; margin-top: 1em; flex-wrap: wrap; }}
.col {{ flex: 1; min-width: 400px; }}
.col img {{ width: 100%; border: 1px solid #999; }}
.caption {{ font-size: 0.85em; color: #555; margin-bottom: 4px; }}
code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; }}
</style></head><body>
<h1>Things to review — autonomous session {time.strftime('%Y-%m-%d')}</h1>
<p>Each section has a candidate pipeline, a baseline for comparison, the per-image metrics, and the worst-image side-by-side diff (REF | PIPELINE). The yellow callout is the decision waiting on you.</p>
{''.join(sections)}
</body></html>"""
    OUT.write_text(html)
    print(f"review dashboard: {OUT}")


if __name__ == "__main__":
    main()
