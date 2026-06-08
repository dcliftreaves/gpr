#!/usr/bin/env python3
"""Compare full-frame PREVIEW receipts and report a best-variant oracle.

The oracle is analysis-only: it uses gate metrics to choose the best existing
variant per row, so it is not a runtime policy. Its purpose is to answer
whether a runtime scene/router selector over already-existing variants could
clear the current failures.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def parse_receipt(values: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--receipt must be LABEL=PATH, got {value!r}")
        label, path = value.split("=", 1)
        if not label:
            raise ValueError("--receipt label cannot be empty")
        out[label] = Path(path)
    if len(out) < 2:
        raise ValueError("need at least two --receipt entries")
    return out


def score_key(row: dict[str, Any]) -> tuple[bool, float, float, float, float]:
    return (
        not bool(row.get("preview_pass", False)),
        float(row.get("lpips", 999.0)),
        -float(row.get("ms_ssim", 0.0)),
        -float(row.get("y_psnr", 0.0)),
        float(row.get("dE2000_mean", 999.0)),
    )


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["image_id"]), str(row["crop"])


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "pass_count": 0, "pass_rate": 0.0}
    return {
        "count": len(rows),
        "pass_count": sum(1 for row in rows if row.get("preview_pass")),
        "pass_rate": sum(1 for row in rows if row.get("preview_pass")) / len(rows),
        "worst_lpips": max(float(row.get("lpips", 0.0)) for row in rows),
        "median_lpips": sorted(float(row.get("lpips", 0.0)) for row in rows)[len(rows) // 2],
        "worst_ms_ssim": min(float(row.get("ms_ssim", 1.0)) for row in rows),
        "worst_y_psnr": min(float(row.get("y_psnr", 999.0)) for row in rows),
        "worst_dE2000_mean": max(float(row.get("dE2000_mean", 0.0)) for row in rows),
    }


def write_html(path: Path, payload: dict[str, Any]) -> None:
    rows = payload["oracle_rows"]
    parts = [
        "<html><head><meta charset='utf-8'><style>",
        "body{font-family:system-ui,Arial;margin:24px;background:#f7f7f7;color:#222}",
        "table{border-collapse:collapse;width:100%;background:white}th,td{padding:6px 8px;border-bottom:1px solid #ddd;text-align:right}",
        "th.left,td.left{text-align:left}.pass{color:#067a25;font-weight:700}.fail{color:#a40000;font-weight:700}",
        ".card{display:inline-block;background:white;border:1px solid #ddd;padding:10px 12px;margin:0 8px 12px 0}",
        "</style></head><body><h1>PREVIEW Full-Frame Variant Oracle</h1>",
    ]
    oracle = payload["oracle_summary"]
    parts.append(
        f"<div class=card><b>Oracle pass</b><br>{oracle['pass_count']}/{oracle['count']} "
        f"({oracle['pass_rate'] * 100:.1f}%)</div>"
    )
    parts.append(f"<div class=card><b>Unsolved rows</b><br>{payload['unsolved_count']}</div>")
    for label, summary in payload["variant_summaries"].items():
        parts.append(
            f"<div class=card><b>{html.escape(label)}</b><br>{summary['pass_count']}/{summary['count']} "
            f"({summary['pass_rate'] * 100:.1f}%)</div>"
        )
    parts.append(
        "<table><thead><tr><th class=left>image</th><th class=left>crop</th>"
        "<th class=left>best</th><th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>dE</th><th>pass</th></tr></thead><tbody>"
    )
    for row in rows:
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['image_id'])}</td>"
            f"<td class=left>{html.escape(row['crop'])}</td>"
            f"<td class=left>{html.escape(row['best_variant'])}</td>"
            f"<td>{float(row['lpips']):.4f}</td><td>{float(row['ms_ssim']):.4f}</td>"
            f"<td>{float(row['y_psnr']):.2f}</td><td>{float(row['dE2000_mean']):.2f}</td>"
            f"<td class={cls}>{'PASS' if row['preview_pass'] else 'FAIL'}</td></tr>"
        )
    parts.append("</tbody></table></body></html>")
    path.write_text("".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", action="append", default=[], help="LABEL=preview_scene_routed_fullframe.json")
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    args = ap.parse_args()

    receipts = parse_receipt(args.receipt)
    rows_by_key: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    variant_summaries: dict[str, dict[str, Any]] = {}
    for label, path in receipts.items():
        payload = json.loads(path.read_text())
        rows = payload.get("rows") or []
        variant_summaries[label] = summarize_rows(rows)
        for row in rows:
            rows_by_key.setdefault(row_key(row), {})[label] = row

    complete_keys = [key for key, rows in rows_by_key.items() if len(rows) == len(receipts)]
    oracle_rows: list[dict[str, Any]] = []
    for key in sorted(complete_keys):
        candidates = rows_by_key[key]
        best_label, best_row = min(candidates.items(), key=lambda item: score_key(item[1]))
        oracle_rows.append(
            {
                "image_id": key[0],
                "crop": key[1],
                "best_variant": best_label,
                "preview_pass": bool(best_row.get("preview_pass", False)),
                "lpips": float(best_row.get("lpips", 999.0)),
                "ms_ssim": float(best_row.get("ms_ssim", 0.0)),
                "y_psnr": float(best_row.get("y_psnr", 0.0)),
                "dE2000_mean": float(best_row.get("dE2000_mean", 999.0)),
            }
        )

    oracle_summary = summarize_rows(oracle_rows)
    payload = {
        "schema": "preview_fullframe_variant_oracle.v1",
        "note": "Analysis-only oracle. It uses gate metrics to choose variants and is not a runtime policy.",
        "receipts": {label: str(path) for label, path in receipts.items()},
        "variant_summaries": variant_summaries,
        "complete_row_count": len(complete_keys),
        "oracle_summary": oracle_summary,
        "unsolved_count": sum(1 for row in oracle_rows if not row["preview_pass"]),
        "oracle_rows": oracle_rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n")
    write_html(args.output_html, payload)
    print(json.dumps({"oracle_summary": oracle_summary, "unsolved_count": payload["unsolved_count"]}, indent=2))
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
