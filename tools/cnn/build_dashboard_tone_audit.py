#!/usr/bin/env python3
"""Build a tone/green-bias audit from RGB dashboard crop PNGs.

Expected crop naming:
  STEM_CROP_target_rgb4_from_high.png
  STEM_CROP_baseline_rgb4.png
  STEM_CROP_candidate_rgb4.png

The audit works on saved review crops, not raw Bayer. It is intended to catch
review-render regressions such as a candidate looking greener than the target.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


TARGET_SUFFIX = "_target_rgb4_from_high.png"


def median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * percent / 100.0
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] * (hi - k) + ordered[hi] * (k - lo))


def read_pixels(path: Path) -> list[tuple[int, int, int]]:
    return list(Image.open(path).convert("RGB").getdata())


def rgb_stats(pixels: list[tuple[int, int, int]]) -> dict[str, Any]:
    red = [p[0] for p in pixels]
    green = [p[1] for p in pixels]
    blue = [p[2] for p in pixels]
    median_rgb = [median(red), median(green), median(blue)]
    mean_rgb = [mean(red), mean(green), mean(blue)]
    luma = mean([0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels])
    gray = sum(median_rgb) / 3.0 or 1.0
    chroma = [v / gray for v in median_rgb]
    green_excess = median_rgb[1] / (((median_rgb[0] + median_rgb[2]) * 0.5) or 1.0) - 1.0
    return {
        "median_rgb": median_rgb,
        "mean_rgb": mean_rgb,
        "luma": luma,
        "chroma": chroma,
        "green_excess": green_excess,
    }


def rgb_mae(a: list[tuple[int, int, int]], b: list[tuple[int, int, int]]) -> float:
    total = 0.0
    count = 0
    for pa, pb in zip(a, b):
        total += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
        count += 3
    return total / count if count else 0.0


def norm3(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "median": median(values),
        "mean": mean(values),
        "max": max(values),
        "abs_p95": percentile([abs(v) for v in values], 95.0),
    }


def make_contact(row: dict[str, Any], output: Path) -> str:
    panels = []
    for label, key in [
        ("target", "target_png"),
        ("baseline", "baseline_png"),
        ("candidate", "candidate_png"),
    ]:
        image = Image.open(row[key]).convert("RGB").resize((256, 256), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (256, 284), (18, 18, 18))
        canvas.paste(image, (0, 28))
        ImageDraw.Draw(canvas).text((8, 8), label, fill=(240, 240, 240))
        panels.append(canvas)

    contact = Image.new("RGB", (256 * 3, 308), (18, 18, 18))
    note = (
        f"{row['stem_crop']}  green {row['candidate_green_delta_vs_target']:+.4f}  "
        f"chroma {row['candidate_chroma_delta_vs_target']:.4f}  "
        f"MAE {row['candidate_display_mae']:.2f}"
    )
    ImageDraw.Draw(contact).text((8, 4), note, fill=(245, 245, 245))
    for idx, panel in enumerate(panels):
        contact.paste(panel, (idx * 256, 24))

    rel = f"rows/{row['stem_crop']}_tone_contact.jpg"
    path = output / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    contact.save(path, quality=92)
    return rel


def collect_rows(crop_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for target_path in sorted(crop_dir.glob(f"*{TARGET_SUFFIX}")):
        stem_crop = target_path.name[: -len(TARGET_SUFFIX)]
        baseline_path = crop_dir / f"{stem_crop}_baseline_rgb4.png"
        candidate_path = crop_dir / f"{stem_crop}_candidate_rgb4.png"
        if not baseline_path.exists() or not candidate_path.exists():
            continue

        target = read_pixels(target_path)
        baseline = read_pixels(baseline_path)
        candidate = read_pixels(candidate_path)
        target_stats = rgb_stats(target)
        baseline_stats = rgb_stats(baseline)
        candidate_stats = rgb_stats(candidate)

        rows.append(
            {
                "stem_crop": stem_crop,
                "stem": stem_crop.rsplit("_", 1)[0],
                "crop": stem_crop.rsplit("_", 1)[1],
                "target_png": str(target_path),
                "baseline_png": str(baseline_path),
                "candidate_png": str(candidate_path),
                "target_median_rgb": target_stats["median_rgb"],
                "baseline_median_rgb": baseline_stats["median_rgb"],
                "candidate_median_rgb": candidate_stats["median_rgb"],
                "target_green_excess": target_stats["green_excess"],
                "baseline_green_excess": baseline_stats["green_excess"],
                "candidate_green_excess": candidate_stats["green_excess"],
                "baseline_green_delta_vs_target": (
                    baseline_stats["green_excess"] - target_stats["green_excess"]
                ),
                "candidate_green_delta_vs_target": (
                    candidate_stats["green_excess"] - target_stats["green_excess"]
                ),
                "baseline_chroma_delta_vs_target": norm3(
                    [
                        baseline_stats["chroma"][i] - target_stats["chroma"][i]
                        for i in range(3)
                    ]
                ),
                "candidate_chroma_delta_vs_target": norm3(
                    [
                        candidate_stats["chroma"][i] - target_stats["chroma"][i]
                        for i in range(3)
                    ]
                ),
                "baseline_display_mae": rgb_mae(baseline, target),
                "candidate_display_mae": rgb_mae(candidate, target),
                "candidate_minus_baseline_mae_delta": (
                    rgb_mae(candidate, target) - rgb_mae(baseline, target)
                ),
                "baseline_luma_delta_vs_target": baseline_stats["luma"] - target_stats["luma"],
                "candidate_luma_delta_vs_target": candidate_stats["luma"] - target_stats["luma"],
            }
        )
    return rows


def select_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected = []
    seen = set()
    ranking_specs = [
        ("candidate_green_delta_vs_target", True),
        ("candidate_chroma_delta_vs_target", True),
        ("candidate_display_mae", False),
        ("candidate_minus_baseline_mae_delta", False),
    ]
    for key, use_abs in ranking_specs:
        ranked = sorted(rows, key=lambda row: abs(row[key]) if use_abs else row[key], reverse=True)
        for row in ranked[:limit]:
            if row["stem_crop"] not in seen:
                selected.append(row)
                seen.add(row["stem_crop"])
            if len(selected) >= limit:
                return selected
    return selected


def write_html(output: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    html_rows = []
    for row in rows:
        html_rows.append(
            "<tr>"
            f"<td>{html.escape(row['stem_crop'])}</td>"
            f"<td>{row['candidate_green_delta_vs_target']:+.4f}</td>"
            f"<td>{row['candidate_chroma_delta_vs_target']:.4f}</td>"
            f"<td>{row['baseline_display_mae']:.2f}</td>"
            f"<td>{row['candidate_display_mae']:.2f}</td>"
            f"<td>{row['candidate_minus_baseline_mae_delta']:+.2f}</td>"
            f"<td><img src='{html.escape(row['contact_jpg'])}'></td>"
            "</tr>"
        )

    style = (
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;"
        "background:#111;color:#eee;margin:24px}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{border-bottom:1px solid #333;padding:8px;vertical-align:top}"
        "img{max-width:768px;width:100%;height:auto}"
        "pre{white-space:pre-wrap;background:#181818;padding:12px}"
        "</style>"
    )
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Mission 4K CNN Tone Audit</title>{style}</head><body>"
        "<h1>Mission 4K CNN Tone Audit</h1>"
        "<p>This audit uses saved display crops from an RGB/CFA dashboard. "
        "It measures whether the candidate introduces a green-channel display "
        "bias relative to the high-resolution-derived target crop. It is a "
        "review-render audit, not a raw-domain quality gate.</p>"
        f"<h2>Summary</h2><pre>{html.escape(json.dumps(summary, indent=2))}</pre>"
        "<h2>Worst / Representative Rows</h2>"
        "<table><thead><tr><th>crop</th><th>candidate green delta</th>"
        "<th>candidate chroma delta</th><th>baseline MAE</th><th>candidate MAE</th>"
        "<th>MAE delta</th><th>target / baseline / candidate</th></tr></thead><tbody>"
        f"{''.join(html_rows)}</tbody></table></body></html>"
    )
    (output / "index.html").write_text(body)


def build(args: argparse.Namespace) -> dict[str, Any]:
    rows = collect_rows(args.crop_dir)
    if not rows:
        raise SystemExit(f"no matching dashboard crop triplets found in {args.crop_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    selected = select_rows(rows, args.limit)
    for row in selected:
        row["contact_jpg"] = make_contact(row, args.output_dir)

    summary: dict[str, Any] = {
        "schema": "mission1_4k_cnn_tone_audit.v1",
        "source_crop_dir": str(args.crop_dir),
        "row_count": len(rows),
        "selected_count": len(selected),
    }
    for key in [
        "baseline_green_delta_vs_target",
        "candidate_green_delta_vs_target",
        "baseline_chroma_delta_vs_target",
        "candidate_chroma_delta_vs_target",
        "baseline_display_mae",
        "candidate_display_mae",
        "candidate_minus_baseline_mae_delta",
    ]:
        summary[key] = summarize([row[key] for row in rows])
    summary["candidate_better_display_mae_count"] = sum(
        1 for row in rows if row["candidate_display_mae"] < row["baseline_display_mae"]
    )
    summary["candidate_worse_display_mae_count"] = sum(
        1 for row in rows if row["candidate_display_mae"] >= row["baseline_display_mae"]
    )
    summary["max_abs_candidate_green_delta"] = max(
        abs(row["candidate_green_delta_vs_target"]) for row in rows
    )

    (args.output_dir / "summary.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2)
    )
    write_html(args.output_dir, summary, selected)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    summary = build(args)
    print(args.output_dir / "index.html")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
