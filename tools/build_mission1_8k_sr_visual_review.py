#!/usr/bin/env python3
"""Build a compact visual-review package for the Mission 1 8K SR candidate."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


SCHEMA = "gpr.mission1_8k_sr_visual_review.v1"
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_SR_BASE = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/current_goal_bayer_rgb_target_cleanup_20260625"
    / "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
    / "sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def rel(path: Path, external_root: Path) -> str:
    try:
        return "artifacts/" + path.resolve().relative_to((external_root / "artifacts").resolve()).as_posix()
    except ValueError:
        return str(path)


def font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def summary_checks(name: str, summary: dict[str, Any], expected_count: int) -> list[dict[str, Any]]:
    return [
        {
            "name": f"{name} image count",
            "passed": summary.get("image_count") == expected_count,
            "detail": summary.get("image_count"),
        },
        {
            "name": f"{name} all rows improve RMSE",
            "passed": float(summary["rmse_improvement_pct"]["min"]) > 0.0,
            "detail": f"min={float(summary['rmse_improvement_pct']['min']):.2f}%",
        },
        {
            "name": f"{name} all rows improve MAE",
            "passed": float(summary["mae_improvement_pct"]["min"]) > 0.0,
            "detail": f"min={float(summary['mae_improvement_pct']['min']):.2f}%",
        },
        {
            "name": f"{name} all rows improve gradient MAE",
            "passed": float(summary["gradient_mae_improvement_pct"]["min"]) > 0.0,
            "detail": f"min={float(summary['gradient_mae_improvement_pct']['min']):.2f}%",
        },
        {
            "name": f"{name} model PSNR floor",
            "passed": float(summary["model_psnr14_db"]["min"]) >= 45.0,
            "detail": f"min={float(summary['model_psnr14_db']['min']):.2f} dB",
        },
    ]


def worst_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for key, reason in (
        ("worst_by_rmse_improvement", "worst RMSE improvement"),
        ("worst_by_mae_improvement", "worst MAE improvement"),
        ("worst_by_gradient_improvement", "worst gradient improvement"),
    ):
        row = summary.get(key)
        if isinstance(row, dict) and row.get("image"):
            copied = dict(row)
            copied["selection_reason"] = reason
            selected[str(row["image"])] = copied
    return list(selected.values())


def make_contact_sheet(rows: list[dict[str, Any]], output: Path) -> None:
    title_font = font(22)
    meta_font = font(16)
    panels: list[Image.Image] = []
    for row in rows:
        src = Path(str(row["contact_sheet"]))
        im = Image.open(src).convert("RGB")
        im.thumbnail((1180, 420), Image.Resampling.LANCZOS)
        pad = 14
        header_h = 76
        panel = Image.new("RGB", (im.width + pad * 2, im.height + header_h + pad * 2), (246, 247, 247))
        draw = ImageDraw.Draw(panel)
        draw.text((pad, pad), f"{row['image']} - {row['selection_reason']}", fill=(12, 20, 22), font=title_font)
        draw.text(
            (pad, pad + 32),
            (
                f"RMSE +{float(row['rmse_improvement_pct']):.2f}% | "
                f"MAE +{float(row['mae_improvement_pct']):.2f}% | "
                f"gradient +{float(row['gradient_mae_improvement_pct']):.2f}% | "
                f"PSNR {float(row['model_psnr14_db']):.2f} dB"
            ),
            fill=(52, 72, 76),
            font=meta_font,
        )
        panel.paste(im, (pad, header_h + pad))
        panels.append(panel)
    width = max(panel.width for panel in panels)
    height = sum(panel.height for panel in panels) + 14 * max(0, len(panels) - 1)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for panel in panels:
        sheet.paste(panel, (0, y))
        y += panel.height + 14
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=88)


def write_html(path: Path, report: dict[str, Any]) -> None:
    checks = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(check["name"])),
            "PASS" if check["passed"] else "FAIL",
            html.escape(str(check["detail"])),
        )
        for check in report["checks"]
    )
    rows = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{:.2f}%</td><td>{:.2f}%</td><td>{:.2f}%</td><td>{:.2f}</td></tr>".format(
            html.escape(str(row["image"])),
            html.escape(str(row["selection_reason"])),
            float(row["rmse_improvement_pct"]),
            float(row["mae_improvement_pct"]),
            float(row["gradient_mae_improvement_pct"]),
            float(row["model_psnr14_db"]),
        )
        for row in report["selected_rows"]
    )
    contact = html.escape(Path(report["contact_sheet"]).name)
    text = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mission 1 8K SR Visual Review</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #111; }}
table {{ border-collapse: collapse; margin: 20px 0; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
code {{ background: #eee; padding: 2px 4px; }}
</style>
</head>
<body>
<h1>Mission 1 8K SR Visual Review</h1>
<p>Verdict: <code>{html.escape(report["verdict"])}</code></p>
<p>Production ready: <code>{str(report["production_ready"]).lower()}</code>.
Manual visual review required: <code>{str(report["manual_visual_review_required"]).lower()}</code>.</p>
<h2>Objective Checks</h2>
<table><tr><th>check</th><th>result</th><th>detail</th></tr>{checks}</table>
<h2>Selected Worst Rows</h2>
<table><tr><th>image</th><th>reason</th><th>RMSE improvement</th><th>MAE improvement</th><th>gradient improvement</th><th>PSNR14</th></tr>{rows}</table>
<h2>Contact Sheet</h2>
<img src="{contact}" alt="Mission 1 8K SR visual review contact sheet">
</body>
</html>
"""
    path.write_text(text, encoding="utf-8")


def build(args: argparse.Namespace) -> dict[str, Any]:
    mission_summary_path = getattr(args, "mission_summary", None) or args.sr_base / "mission42_broad_fullframe/summary.json"
    z8_summary_path = getattr(args, "z8_summary", None) or args.sr_base / "z8_all24_fullframe/summary.json"
    mission_dashboard_path = getattr(args, "mission_dashboard", None) or mission_summary_path.with_name("index.html")
    z8_dashboard_path = getattr(args, "z8_dashboard", None) or z8_summary_path.with_name("index.html")
    mission = read_json(mission_summary_path)
    z8 = read_json(z8_summary_path)
    selected = worst_rows(mission) + worst_rows(z8)
    contact = args.output_dir / "visual_review_contact_sheet.jpg"
    make_contact_sheet(selected, contact)
    checks = summary_checks("Mission42", mission, 42) + summary_checks("Z8 all24", z8, 24)
    report = {
        "schema": SCHEMA,
        "mission_summary": rel(mission_summary_path, args.external_root),
        "mission_summary_sha256": sha256_file(mission_summary_path),
        "z8_summary": rel(z8_summary_path, args.external_root),
        "z8_summary_sha256": sha256_file(z8_summary_path),
        "mission_dashboard": rel(mission_dashboard_path, args.external_root),
        "z8_dashboard": rel(z8_dashboard_path, args.external_root),
        "contact_sheet": rel(contact, args.external_root),
        "contact_sheet_sha256": sha256_file(contact),
        "verdict": "objective_visual_metrics_pass_manual_review_required" if all(c["passed"] for c in checks) else "objective_visual_metrics_fail",
        "production_ready": False,
        "manual_visual_review_complete": False,
        "manual_visual_review_required": True,
        "checks": checks,
        "selected_rows": selected,
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--sr-base", type=Path, default=DEFAULT_SR_BASE)
    ap.add_argument("--mission-summary", type=Path)
    ap.add_argument("--z8-summary", type=Path)
    ap.add_argument("--mission-dashboard", type=Path)
    ap.add_argument("--z8-dashboard", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build(args)
    out = args.output_dir / "visual_review.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_html(args.output_dir / "index.html", report)
    print(json.dumps({"output": str(out), "verdict": report["verdict"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
