#!/usr/bin/env python3
"""Build the current offline CNN/product scorecard dashboard.

The dashboard is intentionally a summary layer over existing receipts and
dashboards. It does not retrain or rerender CNN outputs; it makes the approved
4K cleanup, 8K SR, stills latitude, and real-fixture compatibility state easy
to review without depending on Mission 1 camera hardware.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "pipelines/registry.json"

FOURK_CNN = "mission1_native12_4k_cleanup_rgb_cfa_w40_v1"
EIGHTK_CNN = "mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1"

FOURK_SIGNOFF = "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
EIGHTK_PROMOTION = "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"
EIGHTK_CONTINUOUS_REVIEW = "artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/receipt.json"
COMPAT_DIR = "artifacts/real_fixture_compatibility"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def rel_to_abs(root: Path, rel: str | None) -> Path | None:
    if not rel:
        return None
    path = Path(rel)
    return path if path.is_absolute() else root / path


def metric(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def fmt_num(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "n/a"


def latest_compat_receipt(root: Path) -> Path | None:
    path = rel_to_abs(root, COMPAT_DIR)
    if path is None or not path.is_dir():
        return None
    receipts = sorted(path.glob("receipt_*.txt"))
    return receipts[-1] if receipts else None


def parse_compat_receipt(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"path": None, "pass_count": 0, "skip_count": 0, "rows": []}
    rows: list[dict[str, str]] = []
    pass_count = 0
    skip_count = 0
    summary_re = re.compile(r"SUMMARY pass=(?P<pass>[0-9]+) skip=(?P<skip>[0-9]+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(("PASS ", "SKIP ", "RUN ")):
            parts = line.split()
            rows.append({"status": parts[0], "kind": parts[1] if len(parts) > 1 else "", "label": parts[2] if len(parts) > 2 else ""})
        m = summary_re.search(line)
        if m:
            pass_count = int(m.group("pass"))
            skip_count = int(m.group("skip"))
    return {"path": str(path), "pass_count": pass_count, "skip_count": skip_count, "rows": rows}


def summarize_continuous_review(root: Path) -> dict[str, Any]:
    path = rel_to_abs(root, EIGHTK_CONTINUOUS_REVIEW)
    if path is None or not path.is_file():
        return {
            "available": False,
            "receipt": EIGHTK_CONTINUOUS_REVIEW,
            "reason": "missing continuous no-CNN vs CNN 8K review receipt",
        }
    data = load_json(path)
    outputs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}

    def output_summary(name: str) -> dict[str, Any]:
        row = outputs.get(name)
        if not isinstance(row, dict):
            return {"path": None, "bytes": None, "sha256": None, "ffprobe": {}}
        return {
            "path": row.get("path"),
            "bytes": row.get("bytes"),
            "sha256": row.get("sha256"),
            "ffprobe": row.get("ffprobe") if isinstance(row.get("ffprobe"), dict) else {},
        }

    true_no_cnn = output_summary("true_no_cnn")
    with_cnn = output_summary("with_cnn")
    side_by_side = output_summary("side_by_side_review")
    return {
        "available": True,
        "receipt": EIGHTK_CONTINUOUS_REVIEW,
        "schema": data.get("schema"),
        "note": data.get("note"),
        "frames": data.get("frames"),
        "width": data.get("width"),
        "height": data.get("height"),
        "fps": data.get("fps"),
        "baseline_kind": "no-CNN 4096 x 3072 raw Bayer display-upscaled to 8192 x 6144",
        "candidate_kind": "approved 4K cleanup plus 8K SR CNN raw Bayer path",
        "true_no_cnn": true_no_cnn,
        "with_cnn": with_cnn,
        "side_by_side_review": side_by_side,
    }


def summarize(root: Path) -> dict[str, Any]:
    registry = load_json(REGISTRY)
    cnns = registry["cnns"]
    fourk = cnns[FOURK_CNN]
    eightk = cnns[EIGHTK_CNN]

    fourk_summary = load_json(rel_to_abs(root, fourk["mission42_rgb_cfa_summary"]) or Path())
    tone_summary = load_json(rel_to_abs(root, fourk["mission42_tone_audit_summary"]) or Path())
    mission_sr = load_json(rel_to_abs(root, eightk["mission_broad_holdout_receipt"]) or Path())
    z8_sr = load_json(rel_to_abs(root, eightk["z8_regenerated_holdout_receipt"]) or Path())
    fourk_signoff = load_json(rel_to_abs(root, FOURK_SIGNOFF) or Path())
    eightk_promotion = load_json(rel_to_abs(root, EIGHTK_PROMOTION) or Path())
    compat = parse_compat_receipt(latest_compat_receipt(root))
    continuous_review = summarize_continuous_review(root)

    stills = [
        {"tier": "STILL smallest", "pipeline": "gpr_tools_q0 + matched q3 CNN", "mean_mb": 9.80, "worst_lpips": 0.031, "role": "smallest gated still tier"},
        {"tier": "STILL primary", "pipeline": "gpr_tools_q3 + matched q3 CNN", "mean_mb": 15.05, "worst_lpips": 0.016, "role": "general still tier"},
        {"tier": "STILL archival", "pipeline": "gpr_tools_q8 + no CNN", "mean_mb": 27.17, "worst_lpips": 0.004, "role": "highest-fidelity still tier"},
    ]

    return {
        "schema": "gpr.cnn_product_scorecard.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "registry": str(REGISTRY),
            "external_root": str(root),
        },
        "fourk_cleanup": {
            "cnn": FOURK_CNN,
            "status": fourk["status"],
            "scope": "offline_review_only",
            "checkpoint_sha256": fourk["ckpt_sha256"],
            "dashboard": fourk["mission42_rgb_cfa_dashboard"],
            "tone_dashboard": fourk["mission42_tone_audit_dashboard"],
            "signoff_receipt": FOURK_SIGNOFF,
            "visual_signoff_passed": metric(fourk_signoff, "verdict", "production_ready") is True,
            "image_count": metric(fourk_summary, "summary", "count"),
            "rgb_rmse_improvement_median_pct": metric(fourk_summary, "summary", "rgb_rmse_improvement_pct", "median"),
            "cfa_raw_rmse_improvement_median_pct": metric(fourk_summary, "summary", "cfa_raw_rmse_improvement_pct", "median"),
            "y_gradient_improvement_median_pct": metric(fourk_summary, "summary", "y_gradient_improvement_pct", "median"),
            "y_psnr_delta_median_db": metric(fourk_summary, "summary", "y_psnr_delta_db", "median"),
            "tone": {
                "row_count": metric(tone_summary, "summary", "row_count"),
                "selected_count": metric(tone_summary, "summary", "selected_count"),
                "candidate_better_display_mae_count": metric(tone_summary, "summary", "candidate_better_display_mae_count"),
                "candidate_worse_display_mae_count": metric(tone_summary, "summary", "candidate_worse_display_mae_count"),
                "max_abs_candidate_green_delta": metric(tone_summary, "summary", "max_abs_candidate_green_delta"),
                "candidate_green_abs_p95": metric(tone_summary, "summary", "candidate_green_delta_vs_target", "abs_p95"),
            },
            "packaging": fourk.get("gvid_4k_packaging_summary", {}),
            "prores": fourk.get("prores_review_summary", {}),
        },
        "eightk_sr": {
            "cnn": EIGHTK_CNN,
            "status": eightk["status"],
            "scope": "offline_production",
            "checkpoint_sha256": eightk["ckpt_sha256"],
            "mission_dashboard": eightk["dashboard"],
            "z8_dashboard": eightk["z8_dashboard"],
            "promotion_receipt": EIGHTK_PROMOTION,
            "production_ready": metric(eightk_promotion, "verdict", "production_ready") is True,
            "mission42": {
                "image_count": mission_sr.get("image_count"),
                "rmse_median_pct": metric(mission_sr, "rmse_improvement_pct", "median"),
                "rmse_min_pct": metric(mission_sr, "rmse_improvement_pct", "min"),
                "gradient_median_pct": metric(mission_sr, "gradient_mae_improvement_pct", "median"),
                "gradient_min_pct": metric(mission_sr, "gradient_mae_improvement_pct", "min"),
                "model_psnr14_median_db": metric(mission_sr, "model_psnr14_db", "median"),
                "fps_median": metric(mission_sr, "fps_with_write", "median"),
                "worst_rmse_image": metric(mission_sr, "worst_by_rmse_improvement", "image"),
                "worst_gradient_image": metric(mission_sr, "worst_by_gradient_improvement", "image"),
            },
            "z8_all24": {
                "image_count": z8_sr.get("image_count"),
                "rmse_median_pct": metric(z8_sr, "rmse_improvement_pct", "median"),
                "rmse_min_pct": metric(z8_sr, "rmse_improvement_pct", "min"),
                "gradient_median_pct": metric(z8_sr, "gradient_mae_improvement_pct", "median"),
                "gradient_min_pct": metric(z8_sr, "gradient_mae_improvement_pct", "min"),
                "model_psnr14_median_db": metric(z8_sr, "model_psnr14_db", "median"),
                "fps_median": metric(z8_sr, "fps_with_write", "median"),
                "worst_rmse_image": metric(z8_sr, "worst_by_rmse_improvement", "image"),
                "worst_gradient_image": metric(z8_sr, "worst_by_gradient_improvement", "image"),
            },
            "runtime": eightk.get("gvid_decode_sr_multiframe_summary", {}),
            "packaging_quality": eightk.get("packaging_gpr_quality"),
            "continuous_review": continuous_review,
        },
        "stills": stills,
        "compatibility": compat,
        "next_work": [
            "Keep 4K cleanup as approved review/offline enhancer unless a new full-frame visual gate beats it.",
            "Only replace 8K SR if Mission42 and Z8 all24 broad gates beat the current coord/detail alpha0.5 checkpoint.",
            "Fix any dashboard tone/green concern by regenerating review crops with the documented target gray-world display policy, not by changing raw metrics.",
            "Keep Mission 1 live capture and camera-back preview CNN-free.",
        ],
    }


def td(text: Any) -> str:
    return f"<td>{html.escape(str(text))}</td>"


def link(path: str | None, label: str, root: Path | None = None) -> str:
    if not path:
        return ""
    resolved = Path(path)
    if not resolved.is_absolute() and root is not None and str(path).startswith("artifacts/"):
        resolved = root / path
    return f'<a href="file://{html.escape(str(resolved))}">{html.escape(label)}</a>'


def render_html(data: dict[str, Any], out_json: Path) -> str:
    fourk = data["fourk_cleanup"]
    sr = data["eightk_sr"]
    review = sr.get("continuous_review", {})
    compat = data["compatibility"]
    root = Path(data["source"]["external_root"])
    still_rows = "\n".join(
        "<tr>"
        + td(row["tier"])
        + td(row["pipeline"])
        + td(f'{row["mean_mb"]:.2f}')
        + td(f'{row["worst_lpips"]:.3f}')
        + td(row["role"])
        + "</tr>"
        for row in data["stills"]
    )
    compat_rows = "\n".join(
        "<tr>" + td(row["status"]) + td(row["kind"]) + td(row["label"]) + "</tr>"
        for row in compat.get("rows", [])
        if row.get("status") in {"PASS", "SKIP"}
    )
    next_rows = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_work"])
    review_status = "available" if review.get("available") else "missing"
    review_class = "ok" if review.get("available") else "warn"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GPR CNN Product Scorecard</title>
  <style>
    body {{ margin: 0; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #101418; background: #f6f7f8; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: 34px; margin: 0 0 6px; letter-spacing: 0; }}
    h2 {{ font-size: 20px; margin: 30px 0 12px; }}
    .sub {{ color: #56616d; margin: 0 0 22px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .card {{ background: white; border: 1px solid #d9dee3; border-radius: 8px; padding: 16px; }}
    .metric {{ font-size: 28px; font-weight: 700; margin: 4px 0; }}
    .label {{ color: #64707d; font-size: 12px; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d9dee3; }}
    th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid #e8ecef; vertical-align: top; }}
    th {{ background: #eef1f4; font-size: 12px; text-transform: uppercase; color: #47515c; }}
    a {{ color: #0d5ea6; }}
    .ok {{ color: #0c6b3d; font-weight: 700; }}
    .warn {{ color: #8a5200; font-weight: 700; }}
  </style>
</head>
<body>
<main>
  <h1>GPR CNN Product Scorecard</h1>
  <p class="sub">Generated {html.escape(data["created_utc"])}. This dashboard summarizes approved offline CNN state only; it does not claim Mission 1 camera-hardware readiness.</p>

  <div class="grid">
    <section class="card">
      <div class="label">4K cleanup</div>
      <div class="metric">{fmt_num(fourk["rgb_rmse_improvement_median_pct"])}%</div>
      <div>median RGB RMSE improvement across {fourk["image_count"]} Mission frames</div>
      <div class="ok">visual signoff: {fourk["visual_signoff_passed"]}</div>
    </section>
    <section class="card">
      <div class="label">4K tone/green audit</div>
      <div class="metric">{fourk["tone"]["candidate_better_display_mae_count"]}/{fourk["tone"]["row_count"]}</div>
      <div>review crops with lower display MAE than baseline</div>
      <div>green abs p95 {fmt_num(fourk["tone"]["candidate_green_abs_p95"], 4)}</div>
    </section>
    <section class="card">
      <div class="label">8K SR Mission42</div>
      <div class="metric">{fmt_num(sr["mission42"]["rmse_median_pct"])}%</div>
      <div>median RMSE improvement, {sr["mission42"]["image_count"]} full frames</div>
      <div>median throughput {fmt_num(sr["mission42"]["fps_median"])} fps</div>
    </section>
    <section class="card">
      <div class="label">8K SR Z8 all24</div>
      <div class="metric">{fmt_num(sr["z8_all24"]["rmse_median_pct"])}%</div>
      <div>median RMSE improvement, {sr["z8_all24"]["image_count"]} full frames</div>
      <div>median throughput {fmt_num(sr["z8_all24"]["fps_median"])} fps</div>
    </section>
  </div>

  <h2>Current CNN Verdicts</h2>
  <table>
    <tr><th>Path</th><th>Status</th><th>Evidence</th><th>Boundary</th></tr>
    <tr>
      <td>4K cleanup</td>
      <td>{html.escape(fourk["status"])}</td>
      <td>{link(fourk["dashboard"], "RGB/CFA dashboard", root)} / {link(fourk["tone_dashboard"], "tone audit", root)} / {link(fourk["signoff_receipt"], "signoff receipt", root)}</td>
      <td>Offline/review-only enhancer. Not live capture or camera-back preview.</td>
    </tr>
    <tr>
      <td>8K SR</td>
      <td>{html.escape(sr["status"])}</td>
      <td>{link(sr["mission_dashboard"], "Mission42 dashboard", root)} / {link(sr["z8_dashboard"], "Z8 dashboard", root)} / {link(sr["promotion_receipt"], "promotion receipt", root)}</td>
      <td>Offline-production reconstruction. Current median runtime is about 1 fps-class, not live camera playback.</td>
    </tr>
  </table>

  <h2>Continuous 8K No-CNN vs CNN Review</h2>
  <table>
    <tr><th>Status</th><th>Baseline</th><th>Candidate</th><th>Side-by-side</th><th>Receipt</th></tr>
    <tr>
      <td class="{review_class}">{html.escape(review_status)}</td>
      <td>{html.escape(str(review.get("baseline_kind", "n/a")))}<br>{link(metric(review, "true_no_cnn", "path"), "ProRes", root)}</td>
      <td>{html.escape(str(review.get("candidate_kind", "n/a")))}<br>{link(metric(review, "with_cnn", "path"), "ProRes", root)}</td>
      <td>{link(metric(review, "side_by_side_review", "path"), "3840 x 1440 ProRes", root)}</td>
      <td>{link(review.get("receipt"), "receipt", root)}<br>{html.escape(str(review.get("frames", "n/a")))} frames at {html.escape(str(review.get("fps", "n/a")))} fps</td>
    </tr>
  </table>

  <h2>Stills Latitude</h2>
  <table><tr><th>Tier</th><th>Pipeline</th><th>Mean MB</th><th>Worst LPIPS</th><th>Role</th></tr>{still_rows}</table>

  <h2>Compatibility</h2>
  <p>Latest receipt: {link(compat.get("path"), "real fixture compatibility", root)} ({compat.get("pass_count")} pass, {compat.get("skip_count")} skip)</p>
  <table><tr><th>Status</th><th>Check</th><th>Fixture</th></tr>{compat_rows}</table>

  <h2>Next Work</h2>
  <ul>{next_rows}</ul>
  <p>Machine-readable summary: {html.escape(str(out_json))}</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()
    out_dir = args.output_dir or args.external_root / "artifacts/cnn_product_scorecard_20260629"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = summarize(args.external_root)
    out_json = out_dir / "scorecard.json"
    out_html = out_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(json.dumps({"summary": str(out_json), "dashboard": str(out_html)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
