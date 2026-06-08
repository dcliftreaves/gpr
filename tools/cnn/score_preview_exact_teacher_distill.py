#!/usr/bin/env python3
"""Score exact-teacher distillation outputs against teacher and true REF."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import pass_preview  # noqa: E402


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(str(row["image_id"]), str(row["crop"])): row for row in rows}


def metric_pair(ref: np.ndarray, img: np.ndarray) -> dict[str, Any]:
    metrics = {k: float(v) for k, v in compute_visual_metrics(ref, img).items()}
    metrics["preview_pass"] = pass_preview(metrics)
    return metrics


def summarize(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [row[key] for row in rows]
    return {
        "count": len(values),
        "pass_count": sum(1 for metrics in values if metrics["preview_pass"]),
        "pass_rate": sum(1 for metrics in values if metrics["preview_pass"]) / len(values) if values else 0.0,
        "worst_lpips": max((metrics["lpips"] for metrics in values), default=0.0),
        "median_lpips": float(np.median([metrics["lpips"] for metrics in values])) if values else 0.0,
        "worst_ms_ssim": min((metrics["ms_ssim"] for metrics in values), default=0.0),
        "worst_y_psnr": min((metrics["y_psnr"] for metrics in values), default=0.0),
        "worst_dE2000_mean": max((metrics["dE2000_mean"] for metrics in values), default=0.0),
    }


def copy_asset(src: Path, dst_dir: Path, name: str) -> str:
    dst = dst_dir / name
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return dst.name


def write_html(payload: dict[str, Any], path: Path) -> None:
    css = """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:20px;background:#f7f8f9;color:#222}
table{border-collapse:collapse;width:100%;font-size:12px;background:white}
td,th{border:1px solid #d0d7de;padding:6px;vertical-align:top}
th{background:#eef1f4}
.strip{display:grid;grid-template-columns:repeat(4,128px);gap:6px}
img{width:128px;height:128px;object-fit:contain;background:#111}
.pass{color:#096b2b;font-weight:700}.fail{color:#9b1c1c;font-weight:700}
pre{background:white;border:1px solid #d0d7de;padding:10px}
"""
    lines = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Exact Teacher Distill Score</title>",
        f"<style>{css}</style>",
        "<h1>PREVIEW Exact Teacher Distill Score</h1>",
        "<p>Teacher is exact no-REF crop output. REF is used only for scoring.</p>",
        "<pre>" + json.dumps(payload["summary"], indent=2) + "</pre>",
        "<table><thead><tr><th>row</th><th>views</th><th>source vs REF</th><th>output vs teacher</th><th>output vs REF</th></tr></thead><tbody>",
    ]
    for row in payload["rows"]:
        def metrics_html(metrics: dict[str, Any]) -> str:
            cls = "pass" if metrics["preview_pass"] else "fail"
            return (
                f"<span class='{cls}'>{'PASS' if metrics['preview_pass'] else 'FAIL'}</span><br>"
                f"LPIPS {metrics['lpips']:.4f}<br>MS {metrics['ms_ssim']:.4f}<br>"
                f"Y {metrics['y_psnr']:.2f}<br>dE {metrics['dE2000_mean']:.2f}"
            )

        views = "".join(
            f"<div><img src='{name}'><br>{label}</div>"
            for label, name in [
                ("source", row["assets"]["source"]),
                ("teacher", row["assets"]["teacher"]),
                ("output", row["assets"]["output"]),
                ("REF", row["assets"].get("true_ref", "")),
            ]
            if name
        )
        lines.extend(
            [
                "<tr>",
                f"<td><b>{row['image_id']}</b><br>{row['crop']}</td>",
                f"<td><div class='strip'>{views}</div></td>",
                f"<td>{metrics_html(row['source_vs_ref'])}</td>",
                f"<td>{metrics_html(row['output_vs_teacher'])}</td>",
                f"<td>{metrics_html(row['output_vs_ref']) if row.get('output_vs_ref') else ''}</td>",
                "</tr>",
            ]
        )
    lines.append("</tbody></table>")
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distill-receipt", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dashboard-json", type=Path, required=True)
    parser.add_argument("--dashboard-html", type=Path, required=True)
    args = parser.parse_args()
    distill = json.loads(args.distill_receipt.read_text())
    outputs = json.loads(args.output_receipt.read_text())
    distill_rows = by_key(distill.get("rows") or [])
    output_rows = by_key(outputs.get("rows") or [])
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for key in sorted(set(distill_rows) & set(output_rows)):
        image_id, crop = key
        source = Path(distill_rows[key]["source_png"])
        teacher = Path(distill_rows[key]["teacher_png"])
        true_ref = Path(distill_rows[key]["true_ref_png"]) if distill_rows[key].get("true_ref_png") else None
        output = args.output_receipt.parent / str(output_rows[key]["png"])
        source_rgb = load_rgb(source)
        teacher_rgb = load_rgb(teacher)
        output_rgb = load_rgb(output)
        row: dict[str, Any] = {
            "image_id": image_id,
            "crop": crop,
            "source_vs_teacher": metric_pair(teacher_rgb, source_rgb),
            "output_vs_teacher": metric_pair(teacher_rgb, output_rgb),
            "assets": {
                "source": copy_asset(source, args.output_dir, f"{image_id}_{crop}_source.png"),
                "teacher": copy_asset(teacher, args.output_dir, f"{image_id}_{crop}_teacher.png"),
                "output": copy_asset(output, args.output_dir, f"{image_id}_{crop}_output.png"),
            },
        }
        if true_ref is not None and true_ref.exists():
            true_ref_rgb = load_rgb(true_ref)
            row["source_vs_ref"] = metric_pair(true_ref_rgb, source_rgb)
            row["teacher_vs_ref"] = metric_pair(true_ref_rgb, teacher_rgb)
            row["output_vs_ref"] = metric_pair(true_ref_rgb, output_rgb)
            row["assets"]["true_ref"] = copy_asset(true_ref, args.output_dir, f"{image_id}_{crop}_REF.png")
        rows.append(row)

    payload = {
        "schema": "preview_exact_teacher_distill_score.v1",
        "distill_receipt": str(args.distill_receipt),
        "output_receipt": str(args.output_receipt),
        "summary": {
            "source_vs_teacher": summarize(rows, "source_vs_teacher"),
            "output_vs_teacher": summarize(rows, "output_vs_teacher"),
            "source_vs_ref": summarize(rows, "source_vs_ref") if rows and "source_vs_ref" in rows[0] else None,
            "teacher_vs_ref": summarize(rows, "teacher_vs_ref") if rows and "teacher_vs_ref" in rows[0] else None,
            "output_vs_ref": summarize(rows, "output_vs_ref") if rows and "output_vs_ref" in rows[0] else None,
        },
        "rows": rows,
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2) + "\n")
    write_html(payload, args.dashboard_html)
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(args.dashboard_json)
    print(args.dashboard_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
