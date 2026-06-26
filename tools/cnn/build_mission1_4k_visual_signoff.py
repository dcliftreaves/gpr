#!/usr/bin/env python3
"""Build a compact visual-signoff package for the Mission 1 4K cleanup CNN."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


DEFAULT_BASE = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_bayer_rgb_target_cleanup_20260625/"
    "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def stat(summary: dict[str, Any], key: str, field: str) -> float:
    return float(summary[key][field])


def safe_name(row: dict[str, Any]) -> str:
    return f"{row.get('stem_crop') or row.get('stem', 'row')}_{row.get('crop', '')}".strip("_")


def load_rgb(path: str | Path, size: tuple[int, int] | None = None) -> Image.Image:
    im = Image.open(path).convert("RGB")
    if size is not None:
        im.thumbnail(size, Image.Resampling.LANCZOS)
    return im


def default_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def make_row_strip(row: dict[str, Any], source_root: Path, width: int = 960) -> Image.Image:
    contact = row.get("contact_jpg")
    if isinstance(contact, str):
        path = source_root / contact
        if path.is_file():
            strip = load_rgb(path)
            strip.thumbnail((width, 360), Image.Resampling.LANCZOS)
            return strip

    panels = []
    for key in ("target_png", "baseline_png", "candidate_png"):
        panels.append(load_rgb(row[key], (width // 3, width // 3)))
    h = max(panel.height for panel in panels)
    strip = Image.new("RGB", (sum(panel.width for panel in panels), h), (18, 18, 18))
    x = 0
    for panel in panels:
        strip.paste(panel, (x, 0))
        x += panel.width
    strip.thumbnail((width, 360), Image.Resampling.LANCZOS)
    return strip


def draw_labelled_row(row: dict[str, Any], source_root: Path, reason: str) -> Image.Image:
    font = default_font(20)
    small = default_font(16)
    strip = make_row_strip(row, source_root)
    pad = 12
    label_h = 74
    out = Image.new("RGB", (strip.width + pad * 2, strip.height + label_h + pad * 2), (242, 244, 244))
    d = ImageDraw.Draw(out)
    stem_crop = row.get("stem_crop") or f"{row.get('stem')} {row.get('crop')}"
    delta = float(row.get("candidate_minus_baseline_mae_delta", 0.0))
    cand_mae = float(row.get("candidate_display_mae", 0.0))
    green = abs(float(row.get("candidate_green_delta_vs_target", 0.0)))
    d.text((pad, pad), str(stem_crop), font=font, fill=(10, 18, 20))
    d.text(
        (pad, pad + 28),
        f"{reason} | candidate MAE {cand_mae:.3f} | MAE delta {delta:+.3f} | green abs {green:.4f}",
        font=small,
        fill=(42, 72, 76),
    )
    out.paste(strip, (pad, label_h + pad))
    return out


def build_contact_sheet(selected: list[dict[str, Any]], source_root: Path, output: Path) -> None:
    rows = [draw_labelled_row(row, source_root, row["_selection_reason"]) for row in selected]
    if not rows:
        rows = [Image.new("RGB", (960, 120), (242, 244, 244))]
    w = max(row.width for row in rows)
    h = sum(row.height for row in rows) + 12 * (len(rows) - 1)
    sheet = Image.new("RGB", (w, h), (255, 255, 255))
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height + 12
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=88)


def select_rows(tone_rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    def add(rows: list[dict[str, Any]], reason: str, limit: int) -> None:
        for row in rows[:limit]:
            key = row.get("stem_crop") or safe_name(row)
            if key not in selected:
                copy = dict(row)
                copy["_selection_reason"] = reason
                selected[key] = copy

    add(
        sorted(tone_rows, key=lambda row: float(row.get("candidate_minus_baseline_mae_delta", 0.0)), reverse=True),
        "candidate worse than baseline",
        8,
    )
    add(
        sorted(tone_rows, key=lambda row: float(row.get("candidate_display_mae", 0.0)), reverse=True),
        "worst candidate display MAE",
        8,
    )
    add(
        sorted(tone_rows, key=lambda row: abs(float(row.get("candidate_green_delta_vs_target", 0.0))), reverse=True),
        "worst candidate green delta",
        8,
    )
    return list(selected.values())[:max_rows]


def build_report(rgb_summary_path: Path, tone_summary_path: Path, output_dir: Path, max_rows: int) -> dict[str, Any]:
    rgb_payload = read_json(rgb_summary_path)
    tone_payload = read_json(tone_summary_path)
    rgb_summary = rgb_payload["summary"]
    tone_summary = tone_payload["summary"]
    tone_rows = tone_payload["rows"]

    selected = select_rows(tone_rows, max_rows)
    contact_path = output_dir / "visual_signoff_contact_sheet.jpg"
    build_contact_sheet(selected, tone_summary_path.parent, contact_path)

    row_count = int(tone_summary["row_count"])
    better_count = int(tone_summary["candidate_better_display_mae_count"])
    worse_count = int(tone_summary["candidate_worse_display_mae_count"])
    max_positive_mae_delta = max(float(row.get("candidate_minus_baseline_mae_delta", 0.0)) for row in tone_rows)
    candidate_green_p95 = float(tone_summary["candidate_green_delta_vs_target"]["abs_p95"])
    baseline_green_p95 = float(tone_summary["baseline_green_delta_vs_target"]["abs_p95"])
    max_abs_candidate_green_delta = float(tone_summary["max_abs_candidate_green_delta"])

    checks = [
        {
            "name": "all Mission42 frames improve RGB RMSE",
            "passed": stat(rgb_summary, "rgb_rmse_improvement_pct", "min") > 0.0,
            "detail": f"min={stat(rgb_summary, 'rgb_rmse_improvement_pct', 'min'):.2f}%",
        },
        {
            "name": "all Mission42 frames improve CFA RMSE",
            "passed": stat(rgb_summary, "cfa_raw_rmse_improvement_pct", "min") > 0.0,
            "detail": f"min={stat(rgb_summary, 'cfa_raw_rmse_improvement_pct', 'min'):.2f}%",
        },
        {
            "name": "all Mission42 frames improve luma gradient MAE",
            "passed": stat(rgb_summary, "y_gradient_improvement_pct", "min") > 0.0,
            "detail": f"min={stat(rgb_summary, 'y_gradient_improvement_pct', 'min'):.2f}%",
        },
        {
            "name": "candidate improves display MAE on at least 95% of crops",
            "passed": better_count / row_count >= 0.95,
            "detail": f"better={better_count}/{row_count} worse={worse_count}",
        },
        {
            "name": "worst candidate MAE regression is visually bounded",
            "passed": max_positive_mae_delta <= 0.06,
            "detail": f"max_positive_delta={max_positive_mae_delta:.4f}",
        },
        {
            "name": "candidate green p95 is no worse than baseline",
            "passed": candidate_green_p95 <= baseline_green_p95,
            "detail": f"candidate={candidate_green_p95:.4f} baseline={baseline_green_p95:.4f}",
        },
        {
            "name": "max candidate green delta stays below review ceiling",
            "passed": max_abs_candidate_green_delta <= 0.03,
            "detail": f"max_abs_candidate_green_delta={max_abs_candidate_green_delta:.4f}",
        },
    ]

    verdict = (
        "objective_visual_metrics_pass_manual_signoff_required"
        if all(check["passed"] for check in checks)
        else "objective_visual_metrics_fail"
    )
    report = {
        "schema": "gpr.mission1_4k_cleanup_visual_signoff.v1",
        "rgb_summary": str(rgb_summary_path),
        "tone_summary": str(tone_summary_path),
        "contact_sheet": str(contact_path),
        "verdict": verdict,
        "production_ready": False,
        "manual_visual_signoff": False,
        "manual_visual_signoff_required": True,
        "checks": checks,
        "selected_rows": [
            {
                "stem_crop": row.get("stem_crop"),
                "selection_reason": row["_selection_reason"],
                "candidate_display_mae": row.get("candidate_display_mae"),
                "candidate_minus_baseline_mae_delta": row.get("candidate_minus_baseline_mae_delta"),
                "candidate_green_delta_vs_target": row.get("candidate_green_delta_vs_target"),
            }
            for row in selected
        ],
    }
    return report


def write_html(path: Path, report: dict[str, Any]) -> None:
    checks = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(check["name"]),
            "PASS" if check["passed"] else "FAIL",
            html.escape(check["detail"]),
        )
        for check in report["checks"]
    )
    rows = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{:.4f}</td><td>{:+.4f}</td></tr>".format(
            html.escape(str(row["stem_crop"])),
            html.escape(str(row["selection_reason"])),
            float(row["candidate_display_mae"]),
            float(row["candidate_minus_baseline_mae_delta"]),
        )
        for row in report["selected_rows"]
    )
    contact = html.escape(Path(report["contact_sheet"]).name)
    production_cmd = html.escape(
        "python3 tools/build_mission1_4k_cleanup_signoff_receipt.py "
        "--output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json "
        '--reviewer-name "PROJECT OWNER" '
        "--reviewer-role project-owner "
        '--reviewed-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
        "--visual-checked "
        "--production-ready && "
        "python3 tools/check_mission1_4k_cleanup_signoff_receipt.py "
        "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
    )
    blocked_cmd = html.escape(
        "python3 tools/build_mission1_4k_cleanup_signoff_receipt.py "
        "--output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff_blocked.json "
        '--reviewer-name "PROJECT OWNER" '
        "--reviewer-role project-owner "
        '--reviewed-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
        '--blocking-issue "describe visual issue" '
        "--blocker-cause manual_visual_signoff_missing && "
        "python3 tools/check_mission1_4k_cleanup_signoff_receipt.py "
        "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff_blocked.json"
    )
    text = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mission 1 4K Cleanup Visual Signoff</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #111; }}
table {{ border-collapse: collapse; margin: 20px 0; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
code {{ background: #eee; padding: 2px 4px; }}
pre {{ white-space: pre-wrap; background: #f4f4f4; padding: 12px; border: 1px solid #ddd; }}
</style>
</head>
<body>
<h1>Mission 1 4K Cleanup Visual Signoff</h1>
<p>Verdict: <code>{html.escape(report["verdict"])}</code></p>
<p>Production ready: <code>{str(report["production_ready"]).lower()}</code>.
Manual visual signoff required: <code>{str(report["manual_visual_signoff_required"]).lower()}</code>.</p>
<h2>Objective Checks</h2>
<table><tr><th>check</th><th>result</th><th>detail</th></tr>{checks}</table>
<h2>Selected Rows</h2>
<table><tr><th>row</th><th>reason</th><th>candidate MAE</th><th>MAE delta</th></tr>{rows}</table>
<h2>Production Signoff Commands</h2>
<p>If the contact sheet and linked dashboards are acceptable, generate the production receipt:</p>
<pre>{production_cmd}</pre>
<p>If review finds a blocking visual issue, keep the blocked receipt explicit:</p>
<pre>{blocked_cmd}</pre>
<h2>Contact Sheet</h2>
<img src="{contact}" alt="Mission 1 4K cleanup visual signoff contact sheet">
</body>
</html>
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--rgb-summary",
        type=Path,
        default=DEFAULT_BASE / "mission42_rgb_cfa_target_gate_wb_review/summary.json",
    )
    ap.add_argument(
        "--tone-summary",
        type=Path,
        default=DEFAULT_BASE / "mission42_4k_cnn_tone_audit_20260625/summary.json",
    )
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--max-rows", type=int, default=20)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(args.rgb_summary, args.tone_summary, args.output_dir, args.max_rows)
    json_path = args.output_dir / "visual_signoff.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_html(html_path, report)
    print(json.dumps({"verdict": report["verdict"], "json": str(json_path), "html": str(html_path)}, indent=2))
    return 0 if report["verdict"].startswith("objective_visual_metrics_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
