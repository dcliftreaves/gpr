#!/usr/bin/env python3
"""Audit PREVIEW source/REF pairing before model evaluation.

The PREVIEW holdout mixes runtime source DNGs with separately resolved REF DNGs.
This tool scores the already-rendered source/REF crop PNGs from a holdout source
receipt so source-policy failures are visible before another model is trained.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


DEFAULT_RECEIPT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/"
    "holdout_runtime_crops_v8_clean_upresable_28img/preview_holdout_runtime_source_receipt.json"
)


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def root_label(path: str) -> str:
    value = str(path)
    markers = [
        "/artifacts/upresable_holdout_clean_20260607/editable_dng/",
        "/artifacts/upresable/editable_dng/",
        "/artifacts/upresable_preview_probe_20260606/editable_dng/",
        "/cnn/diverse_dngs/",
        "/barnsky_full_dngs/",
    ]
    for marker in markers:
        if marker in value:
            return marker.strip("/")
    parent = Path(value).parent
    return str(parent)


def finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def summarize(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not rows:
        return {
            "label": label,
            "count": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "worst_lpips": None,
            "median_lpips": None,
            "worst_ms_ssim": None,
            "worst_y_psnr": None,
            "worst_dE2000_mean": None,
        }
    return {
        "label": label,
        "count": len(rows),
        "pass_count": sum(1 for row in rows if row["preview_pass"]),
        "pass_rate": sum(1 for row in rows if row["preview_pass"]) / len(rows),
        "worst_lpips": max(float(row["lpips"]) for row in rows),
        "median_lpips": float(np.median([float(row["lpips"]) for row in rows])),
        "worst_ms_ssim": min(float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(float(row["dE2000_mean"]) for row in rows),
    }


def group_summary(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, ""))].append(row)
    out = [summarize(group_rows, label) for label, group_rows in groups.items()]
    out.sort(key=lambda row: (row["pass_count"], -float(row["worst_lpips"] or 0.0), row["label"]))
    return out


def collect(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.receipt.read_text())
    rows = []
    for row in receipt.get("rows", []):
        source_png = Path(row["source_png"])
        ref_png = Path(row["ref_png"])
        metrics = {k: float(v) for k, v in compute_visual_metrics(load_rgb(ref_png), load_rgb(source_png)).items()}
        metrics["preview_pass"] = pass_preview(metrics)
        source_dng = str(row.get("source_dng", ""))
        ref_dng = str(row.get("ref_dng", ""))
        rows.append(
            {
                "image_id": str(row["image_id"]),
                "crop": str(row["crop"]),
                "source_png": str(source_png),
                "ref_png": str(ref_png),
                "source_dng": source_dng,
                "ref_dng": ref_dng,
                "source_root": root_label(source_dng),
                "ref_root": root_label(ref_dng),
                "source_label": str(row.get("source_label", "")),
                "strata": row.get("strata", []),
                **metrics,
            }
        )

    by_image = []
    for image_id in sorted({row["image_id"] for row in rows}):
        image_rows = [row for row in rows if row["image_id"] == image_id]
        item = summarize(image_rows, image_id)
        item["source_root"] = image_rows[0]["source_root"]
        item["ref_root"] = image_rows[0]["ref_root"]
        item["source_dng"] = image_rows[0]["source_dng"]
        item["ref_dng"] = image_rows[0]["ref_dng"]
        by_image.append(item)
    by_image.sort(key=lambda row: (row["pass_count"], -float(row["worst_lpips"] or 0.0), row["label"]))

    return {
        "schema": "preview_source_ref_policy_audit.v1",
        "receipt": str(args.receipt),
        "thresholds": PREVIEW,
        "summary": summarize(rows, "all_rows"),
        "by_source_root": group_summary(rows, "source_root"),
        "by_ref_root": group_summary(rows, "ref_root"),
        "by_image": by_image,
        "rows": rows,
    }


def fmt(value: Any) -> str:
    number = finite(value)
    if number is None:
        return ""
    return f"{number:.4f}" if abs(number) < 10 else f"{number:.2f}"


def write_html(payload: dict[str, Any], path: Path) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:22px; color:#1f2933; }
table { border-collapse:collapse; width:100%; font-size:12px; margin:14px 0 28px; }
th,td { border:1px solid #cbd5df; padding:6px 8px; text-align:right; vertical-align:top; }
th.left,td.left { text-align:left; }
.cards { display:grid; grid-template-columns:repeat(5,minmax(150px,1fr)); gap:10px; margin:14px 0; }
.card { border:1px solid #cbd5df; border-radius:6px; padding:10px; background:#fbfcfd; }
.pass { color:#12652f; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
"""
    summary = payload["summary"]
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Source REF Policy Audit</title>",
        f"<style>{css}</style><h1>PREVIEW Source REF Policy Audit</h1>",
        "<p>Scores rendered runtime source crop PNGs directly against their resolved REF crop PNGs before any model is applied.</p>",
        "<div class=cards>",
        f"<div class=card><b>Source baseline pass</b><br>{summary['pass_count']}/{summary['count']}</div>",
        f"<div class=card><b>Worst LPIPS</b><br>{fmt(summary['worst_lpips'])}</div>",
        f"<div class=card><b>Worst MS-SSIM</b><br>{fmt(summary['worst_ms_ssim'])}</div>",
        f"<div class=card><b>Worst Y-PSNR</b><br>{fmt(summary['worst_y_psnr'])}</div>",
        f"<div class=card><b>Worst dE2000</b><br>{fmt(summary['worst_dE2000_mean'])}</div>",
        "</div>",
    ]
    for title, rows in (("By Source Root", payload["by_source_root"]), ("By REF Root", payload["by_ref_root"]), ("By Image", payload["by_image"])):
        parts.append(
            f"<h2>{html.escape(title)}</h2><table><thead><tr><th class=left>label</th><th>pass</th><th>rate</th>"
            "<th>LPIPS</th><th>median LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>"
        )
        for row in rows:
            cls = "pass" if row["pass_count"] == row["count"] and row["count"] else "fail"
            parts.append(
                f"<tr><td class=left>{html.escape(row['label'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
                f"<td>{row['pass_rate']:.1%}</td><td>{fmt(row['worst_lpips'])}</td>"
                f"<td>{fmt(row['median_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
                f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td></tr>"
            )
        parts.append("</tbody></table>")
    path.write_text("".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    args = parser.parse_args()

    payload = collect(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    s = payload["summary"]
    print(
        f"source_baseline={s['pass_count']}/{s['count']} "
        f"LPIPS={s['worst_lpips']:.4f} MS={s['worst_ms_ssim']:.4f} "
        f"Y={s['worst_y_psnr']:.2f} dE={s['worst_dE2000_mean']:.2f}"
    )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
