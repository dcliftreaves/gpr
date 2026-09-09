#!/usr/bin/env python3
"""Build a consolidated operations dashboard.

The production dashboard is narrative. This one is tabular and diagnostic:
it rolls quality-gate run.json files into size, timing, FPS, compression,
quality, Bayer-fidelity, and color-error dimensions, then adds the Pi/Mac
benchmarks and chroma signal diagnosis that have been driving recent work.
"""
from __future__ import annotations

import html
import json
import re
import statistics
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "tests/quality_gates/runs"
DASH_DIR = RUNS_DIR / "dashboard"
OUT = DASH_DIR / "ops_matrix.html"
UPRES = Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable")
RAW_FULL_BYTES = 8280 * 5520 * 2
MANIFEST_PATH = REPO / "docs/release_evidence_manifest.json"

PRODUCTION_RUNS = {
    "STILL": "b44fa841c05c9bff",
    "VIDEO_FREEZE": "5c3cce4c472d4197",
    "UPRESABLE": "8864c12ec0b6ce14",
}

CHROMA_RUNS = {
    "Lab sips residual": "5e7d52579ffb2d3e",
    "YCbCr decomp": "03045a1c44ffa38d",
    "Lab absolute ep5": "c9bbe8390032412a",
    "Lab residual ab8": "0c8974e88d94e710",
    "UPRESABLE BIBO2x": "8864c12ec0b6ce14",
    "ml2_dec2 no CNN": "44d95b0985ac01c4",
    "legacy GPR q3": "b44fa841c05c9bff",
    "VIDEO_FREEZE ship": "5c3cce4c472d4197",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def fmt(x, digits=2, suffix=""):
    if x is None:
        return "-"
    if isinstance(x, str):
        return html.escape(x)
    return f"{x:.{digits}f}{suffix}"


def mb(n: float | None) -> float | None:
    return None if n is None else n / 1024 / 1024


def mean(vals):
    vals = [v for v in vals if v is not None]
    return None if not vals else statistics.fmean(vals)


def minv(vals):
    vals = [v for v in vals if v is not None]
    return None if not vals else min(vals)


def maxv(vals):
    vals = [v for v in vals if v is not None]
    return None if not vals else max(vals)


def summarize_run(run_hash: str) -> dict | None:
    p = RUNS_DIR / run_hash / "run.json"
    if not p.exists():
        return None
    data = read_json(p)
    rows = list((data.get("images") or {}).values())
    enc_bytes = [r.get("enc_bytes") for r in rows]
    enc_ms = [r.get("enc_ms") for r in rows]
    cnn_ms = [r.get("cnn_ms") for r in rows]
    total_ms = [r.get("total_ms") for r in rows]
    worst_id = (data.get("worst_first") or [""])[0]
    worst = (data.get("images") or {}).get(worst_id, {})
    mean_bytes = mean(enc_bytes)
    mean_ms = mean(enc_ms)
    mean_cnn_ms = mean(cnn_ms)
    mean_total_ms = mean(total_ms)
    mean_restore_ms = None
    if mean_ms is not None:
        mean_restore_ms = mean_ms + (mean_cnn_ms or 0.0)
    return {
        "run_hash": run_hash,
        "pipeline": data.get("pipeline", ""),
        "ship_class": data.get("ship_class", ""),
        "verdict": data.get("verdict", ""),
        "mean_mb": mb(mean_bytes),
        "min_mb": mb(minv(enc_bytes)),
        "max_mb": mb(maxv(enc_bytes)),
        "bpp": None if mean_bytes is None else (mean_bytes * 8) / (8280 * 5520),
        "raw_ratio": None if mean_bytes is None else RAW_FULL_BYTES / mean_bytes,
        "enc_ms": mean_ms,
        "enc_fps": None if not mean_ms else 1000.0 / mean_ms,
        "cnn_ms": mean_cnn_ms,
        "cnn_fps": None if not mean_cnn_ms else 1000.0 / mean_cnn_ms,
        "restore_ms": mean_restore_ms,
        "restore_fps": None if not mean_restore_ms else 1000.0 / mean_restore_ms,
        "total_ms": mean_total_ms,
        "total_fps": None if not mean_total_ms else 1000.0 / mean_total_ms,
        "worst_id": worst_id,
        "worst_lpips": worst.get("lpips"),
        "min_ms_ssim": minv([r.get("ms_ssim") for r in rows]),
        "min_y_psnr": minv([r.get("y_psnr") for r in rows]),
        "max_de_mean": maxv([r.get("dE2000_mean") for r in rows]),
        "min_bayer_codec": minv([r.get("bayer_psnr_codec") for r in rows]),
        "min_bayer_final": minv([r.get("bayer_psnr_final") for r in rows]),
    }


def all_run_summaries() -> list[dict]:
    out = []
    seen_pipelines = {}
    for run_json in RUNS_DIR.glob("*/run.json"):
        s = summarize_run(run_json.parent.name)
        if not s:
            continue
        # Keep the newest entry per exact pipeline+verdict+metric tuple short
        # enough for a dashboard while preserving distinct experiments.
        key = (s["pipeline"], s["verdict"], round(s.get("worst_lpips") or 0, 6))
        prev = seen_pipelines.get(key)
        if prev is None or s["run_hash"] > prev["run_hash"]:
            seen_pipelines[key] = s
    out.extend(seen_pipelines.values())
    return sorted(out, key=lambda r: (
        r["ship_class"] or "zz",
        r["verdict"] != "PASS",
        -(r.get("worst_lpips") or 0),
    ))


def parse_pi_mac_bench() -> list[dict]:
    log = UPRES / "pi_mac_bench/run.log"
    if not log.exists():
        return []
    rows = []
    pat = re.compile(r"^(A\.|B\.|C\.|D\.)\s+(.+?)\s+([0-9.]+)\s+([0-9.]+)\s+(-|[0-9.]+)$")
    in_table = False
    for line in log.read_text(errors="ignore").splitlines():
        if line.strip().startswith("stage"):
            in_table = True
            continue
        if not in_table:
            continue
        m = pat.search(line.strip())
        if m:
            rows.append({
                "stage": f"{m.group(1)} {m.group(2).strip()}",
                "duration_s": float(m.group(3)),
                "fps": float(m.group(4)),
                "mb_s": None if m.group(5) == "-" else float(m.group(5)),
            })
    return rows


def load_upres_summary() -> dict:
    p = UPRES / "summary.json"
    return read_json(p) if p.exists() else {}


def load_manifest() -> dict:
    return read_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}


def external_preview_summary(manifest: dict) -> dict | None:
    for entry in manifest.get("production_paths") or []:
        if entry.get("id") != "preview_offline_review_q8_threeway":
            continue
        metrics = entry.get("metrics") or {}
        return {
            "run_hash": "external-q8-threeway",
            "pipeline": entry.get("pipeline", ""),
            "ship_class": entry.get("ship_class", "PREVIEW"),
            "verdict": "PASS",
            "mean_mb": None,
            "min_mb": None,
            "max_mb": None,
            "bpp": None,
            "raw_ratio": None,
            "enc_ms": None,
            "enc_fps": None,
            "cnn_ms": None,
            "cnn_fps": None,
            "restore_ms": None,
            "restore_fps": None,
            "total_ms": metrics.get("seconds_per_image", 0.0) * 1000.0,
            "total_fps": metrics.get("fps"),
            "worst_id": f"{metrics.get('passing_rows', '-')}/{metrics.get('holdout_rows', '-')} rows",
            "worst_lpips": metrics.get("worst_lpips"),
            "min_ms_ssim": metrics.get("worst_ms_ssim"),
            "min_y_psnr": metrics.get("worst_y_psnr"),
            "max_de_mean": metrics.get("worst_dE2000"),
            "min_bayer_codec": None,
            "min_bayer_final": None,
        }
    return None


def pipeline_short(pipeline: str) -> str:
    return pipeline.replace("codec=", "").replace("+cnn=", " | ").replace("+demosaic=", " | ")


def table_quality(rows: list[dict]) -> str:
    trs = []
    for r in rows:
        cls = "pass" if r["verdict"] == "PASS" else "fail"
        trs.append(f"""
<tr>
  <td><code>{html.escape(r['run_hash'])}</code></td>
  <td class="{cls}">{html.escape(r['verdict'])}</td>
  <td>{html.escape(r['ship_class'])}</td>
  <td class="pipe">{html.escape(pipeline_short(r['pipeline']))}</td>
  <td class="num">{fmt(r['mean_mb'])}</td>
  <td class="num">{fmt(r['bpp'], 3)}</td>
  <td class="num">{fmt(r['raw_ratio'], 1)}x</td>
  <td class="num">{fmt(r['enc_ms'], 1)}</td>
  <td class="num">{fmt(r['enc_fps'], 2)}</td>
  <td class="num">{fmt(r['cnn_ms'], 1)}</td>
  <td class="num">{fmt(r['cnn_fps'], 2)}</td>
  <td class="num">{fmt(r['restore_ms'], 1)}</td>
  <td class="num">{fmt(r['restore_fps'], 2)}</td>
  <td class="num">{fmt(r['total_ms'], 1)}</td>
  <td class="num">{fmt(r['total_fps'], 2)}</td>
  <td>{html.escape(r['worst_id'])}</td>
  <td class="num">{fmt(r['worst_lpips'], 4)}</td>
  <td class="num">{fmt(r['min_ms_ssim'], 4)}</td>
  <td class="num">{fmt(r['min_y_psnr'])}</td>
  <td class="num">{fmt(r['max_de_mean'])}</td>
  <td class="num">{fmt(r['min_bayer_codec'])}</td>
  <td class="num">{fmt(r['min_bayer_final'])}</td>
</tr>""")
    return "\n".join(trs)


def table_upres_reg(summary: dict) -> str:
    rows = []
    for image_id, r in (summary.get("regression") or {}).items():
        rows.append(f"""
<tr>
  <td>{html.escape(image_id)}</td>
  <td class="num">{fmt(r.get('halfres_gpr_MB'))}</td>
  <td class="num">{fmt(r.get('fullres_FUSED_gpr_MB'))}</td>
  <td class="num">{fmt(r.get('editable_GPR_MB'))}</td>
  <td class="num">{fmt(r.get('editable_DNG_MB'))}</td>
  <td class="num">{fmt(r.get('bayer_psnr_vs_source_dB'))}</td>
  <td>{'yes' if r.get('dng_opens_in_raw_editor') else 'no'}</td>
</tr>""")
    return "\n".join(rows)


def table_pi_mac(rows: list[dict]) -> str:
    return "\n".join(
        f"<tr><td>{html.escape(r['stage'])}</td><td class='num'>{fmt(r['duration_s'])}</td>"
        f"<td class='num'>{fmt(r['fps'], 2)}</td><td class='num'>{fmt(r['mb_s'], 2)}</td></tr>"
        for r in rows
    )


def chroma_metrics(run_hash: str, image_id: str = "Z8Z_6693") -> dict | None:
    # Import the local diagnostic script without requiring it as a package.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "diagnose_chroma_signal",
        REPO / "tests/quality_gates/diagnose_chroma_signal.py",
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError:
        return None
    run_dir = RUNS_DIR / run_hash
    ref = run_dir / f"{image_id}_REF_crop_A_detail.png"
    pipe = run_dir / f"{image_id}_PIPELINE_crop_A_detail.png"
    if not ref.exists() or not pipe.exists():
        return None
    return mod.metrics_for_pair(mod.load_rgb(ref), mod.load_rgb(pipe))


def table_chroma() -> str:
    rows = []
    for label, run_hash in CHROMA_RUNS.items():
        m = chroma_metrics(run_hash)
        s = summarize_run(run_hash)
        if not m or not s:
            continue
        rows.append(f"""
<tr>
  <td>{html.escape(label)}</td>
  <td><code>{run_hash}</code></td>
  <td>{html.escape(s['verdict'])}</td>
  <td class="num">{fmt(s['worst_lpips'], 4)}</td>
  <td class="num">{fmt(m['dE_p95'])}</td>
  <td class="num">{fmt(m['L_mae'])}</td>
  <td class="num">{fmt(m['ab_mae'])}</td>
  <td class="num">{fmt(m['ab_p95'])}</td>
  <td class="num">{fmt(m['hue_abs_deg_p95'], 1)}</td>
  <td class="num">{fmt(m['ab_bias_a'])}, {fmt(m['ab_bias_b'])}</td>
  <td class="num">{fmt(m['ab_corr_a'], 3)}, {fmt(m['ab_corr_b'], 3)}</td>
  <td class="num">{fmt(m['chroma_hf_ratio'], 2)}</td>
</tr>""")
    if not rows:
        return (
            "<tr><td colspan='12'>Chroma crop diagnostics are unavailable in "
            "this Python environment or the referenced crop assets are absent. "
            "Install the quality-gate Python dependencies and regenerate the "
            "gate dashboards to populate this table.</td></tr>"
        )
    return "\n".join(rows)


def build_html() -> str:
    all_rows = all_run_summaries()
    prod = [summarize_run(h) for h in PRODUCTION_RUNS.values()]
    prod = [p for p in prod if p]
    manifest = load_manifest()
    preview = external_preview_summary(manifest)
    if preview:
        prod.append(preview)
    summary = load_upres_summary()
    stats = summary.get("timelapse_stats") or {}
    pi_mac = parse_pi_mac_bench()

    cards = {
        "Pi capture": "blocked 19.98 fps",
        "Pi SSH loop": "6.08 fps",
        "Pi to Mac sustained": "1.79 fps",
        "USB transfer": "501 MB/s",
        "BIBO2x median": f"{fmt(stats.get('bibo2x_ms_median'), 0)} ms",
        "Full ProRes path": f"{fmt(stats.get('total_ms_median'), 0)} ms/frame",
        "UPRESABLE halfres median": f"{fmt(stats.get('halfres_gpr_mb_median'), 2)} MB",
        "UPRESABLE ProRes": f"{fmt(stats.get('prores_size_mb'), 1)} MB",
    }

    card_html = "\n".join(
        f"<div class='card'><div class='k'>{html.escape(k)}</div><div class='v'>{html.escape(v)}</div></div>"
        for k, v in cards.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GPR operations matrix</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2933; background: #f7f8fa; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }}
h2 {{ margin-top: 34px; font-size: 20px; border-bottom: 1px solid #d8dee6; padding-bottom: 8px; }}
p {{ max-width: 1100px; line-height: 1.45; color: #52606d; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dde3ea; border-radius: 8px; padding: 14px; }}
.card .k {{ color: #697586; font-size: 12px; text-transform: uppercase; }}
.card .v {{ font-size: 24px; font-weight: 650; margin-top: 4px; }}
table {{ border-collapse: collapse; width: 100%; background: white; border: 1px solid #dde3ea; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #edf1f5; padding: 7px 9px; vertical-align: top; }}
th {{ position: sticky; top: 0; background: #eef2f6; text-align: left; z-index: 1; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td.pipe {{ max-width: 520px; }}
code {{ font-size: 12px; background: #edf1f5; padding: 1px 4px; border-radius: 4px; }}
.pass {{ color: #167a3a; font-weight: 650; }}
.fail {{ color: #b42318; font-weight: 650; }}
.scroll {{ max-height: 760px; overflow: auto; border: 1px solid #dde3ea; }}
.note {{ font-size: 13px; color: #697586; }}
</style>
</head>
<body>
<h1>GPR operations matrix</h1>
<p>
Generated from <code>tests/quality_gates/runs/*/run.json</code>,
<code>docs/release_evidence_manifest.json</code>,
<code>/Volumes/OWC_8TB/gpr_work/artifacts/upresable/summary.json</code>, and
<code>/Volumes/OWC_8TB/gpr_work/artifacts/upresable/pi_mac_bench/run.log</code>.
The table keeps quality, encoded size, compression ratio, encode timing, and
gate-stage timing in one place. <code>restore ms</code> is codec plus CNN time;
<code>gate total ms</code> includes gate-only rendering, crop, and metric work.
External-receipt rows such as the q8 three-way PREVIEW path have no committed
run hash and therefore show receipt-level timing/quality instead of codec MB.
</p>

<div class="cards">{card_html}</div>

<h2>Production run rollup</h2>
<table>
<tr><th>Run</th><th>Verdict</th><th>Class</th><th>Pipeline</th><th class="num">mean MB</th><th class="num">bpp</th><th class="num">raw ratio</th><th class="num">enc ms</th><th class="num">enc fps</th><th class="num">cnn ms</th><th class="num">cnn fps</th><th class="num">restore ms</th><th class="num">restore fps</th><th class="num">gate total ms</th><th class="num">gate total fps</th><th>worst</th><th class="num">LPIPS</th><th class="num">MS-SSIM min</th><th class="num">Y-PSNR min</th><th class="num">dE max</th><th class="num">Bayer codec min</th><th class="num">Bayer final min</th></tr>
{table_quality(prod)}
</table>

<h2>Pi-to-Mac pipeline benchmark</h2>
<table>
<tr><th>Stage</th><th class="num">duration s</th><th class="num">fps</th><th class="num">MB/s</th></tr>
{table_pi_mac(pi_mac)}
</table>

<h2>UPRESABLE artifact accounting</h2>
<table>
<tr><th>Image</th><th class="num">halfres GPR MB</th><th class="num">fullres FUSED GPR MB</th><th class="num">editable GPR MB</th><th class="num">editable DNG MB</th><th class="num">Bayer PSNR dB</th><th>raw editor</th></tr>
{table_upres_reg(summary)}
</table>

<h2>Chroma signal diagnosis, Z8Z_6693 crop A</h2>
<p class="note">
<code>chrHF</code> is the high-frequency chroma-energy ratio vs REF. Values near 1 preserve chroma texture;
very low values indicate chroma smoothing/desaturation. Low ab correlation or large ab bias indicates
the color problem is not just luma/detail loss.
</p>
<table>
<tr><th>Pipeline</th><th>Run</th><th>Verdict</th><th class="num">worst LPIPS</th><th class="num">dE95</th><th class="num">L MAE</th><th class="num">ab MAE</th><th class="num">ab95</th><th class="num">hue95 deg</th><th class="num">ab bias a,b</th><th class="num">ab corr a,b</th><th class="num">chrHF</th></tr>
{table_chroma()}
</table>

<h2>All gate runs</h2>
<div class="scroll">
<table>
<tr><th>Run</th><th>Verdict</th><th>Class</th><th>Pipeline</th><th class="num">mean MB</th><th class="num">bpp</th><th class="num">raw ratio</th><th class="num">enc ms</th><th class="num">enc fps</th><th class="num">cnn ms</th><th class="num">cnn fps</th><th class="num">restore ms</th><th class="num">restore fps</th><th class="num">gate total ms</th><th class="num">gate total fps</th><th>worst</th><th class="num">LPIPS</th><th class="num">MS-SSIM min</th><th class="num">Y-PSNR min</th><th class="num">dE max</th><th class="num">Bayer codec min</th><th class="num">Bayer final min</th></tr>
{table_quality(all_rows)}
</table>
</div>
</body>
</html>
"""


def main() -> None:
    DASH_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_html())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
