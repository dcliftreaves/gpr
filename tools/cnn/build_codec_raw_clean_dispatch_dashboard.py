#!/usr/bin/env python3
"""Compare codec raw-clean candidates and a sidecar-label dispatch policy."""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_ACCEPTED = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/"
    "dashboard_w64_accepted/codec_raw_clean_dashboard.json"
)
DEFAULT_ALL = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/"
    "dashboard_w64_all_targets/codec_raw_clean_dashboard.json"
)
DEFAULT_OUT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/"
    "dispatch_comparison_w64"
)


def load_rows(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    data = json.loads(path.read_text())
    rows = {}
    for row in data["rows"]:
        key = (row["image_id"], row["crop"])
        if key in rows:
            raise ValueError(f"duplicate dashboard row {key} in {path}")
        rows[key] = row
    return rows


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return float(np.mean([float(row[key]) for row in rows]))


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in rows if row["accepted"]]
    rejected = [row for row in rows if not row["accepted"]]
    return {
        "count": len(rows),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "mean_clean_rmse_counts": mean(rows, "clean_rmse_counts"),
        "accepted_mean_clean_rmse_counts": mean(accepted, "clean_rmse_counts"),
        "rejected_mean_clean_rmse_counts": mean(rejected, "clean_rmse_counts"),
        "max_clean_rmse_counts": max((float(row["clean_rmse_counts"]) for row in rows), default=None),
        "worst_row": max(rows, key=lambda row: float(row["clean_rmse_counts"])) if rows else None,
    }


def rel(path: str, out_file: Path) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(out_file.parent))
    except ValueError:
        return path


def build(args: argparse.Namespace) -> dict[str, Any]:
    accepted_rows = load_rows(args.accepted_only)
    all_rows = load_rows(args.all_targets)
    if set(accepted_rows) != set(all_rows):
        missing_a = sorted(set(all_rows) - set(accepted_rows))
        missing_b = sorted(set(accepted_rows) - set(all_rows))
        raise ValueError(f"dashboard key mismatch accepted_missing={missing_a} all_missing={missing_b}")

    rows = []
    for key in sorted(accepted_rows):
        a = accepted_rows[key]
        b = all_rows[key]
        if bool(a["accepted"]) != bool(b["accepted"]):
            raise ValueError(f"accepted flag mismatch for {key}")
        selected = a if a["accepted"] else b
        selected_name = "accepted_only" if a["accepted"] else "all_targets"
        rows.append({
            "image_id": a["image_id"],
            "crop": a["crop"],
            "iso": a["iso"],
            "accepted": bool(a["accepted"]),
            "selected": selected_name,
            "accepted_only_clean_rmse_counts": a["clean_rmse_counts"],
            "all_targets_clean_rmse_counts": b["clean_rmse_counts"],
            "dispatch_clean_rmse_counts": selected["clean_rmse_counts"],
            "accepted_only_artifacts": a["artifacts"],
            "all_targets_artifacts": b["artifacts"],
        })

    accepted_eval = [
        {
            **row,
            "clean_rmse_counts": row["accepted_only_clean_rmse_counts"],
        }
        for row in rows
    ]
    all_eval = [
        {
            **row,
            "clean_rmse_counts": row["all_targets_clean_rmse_counts"],
        }
        for row in rows
    ]
    dispatch_eval = [
        {
            **row,
            "clean_rmse_counts": row["dispatch_clean_rmse_counts"],
        }
        for row in rows
    ]
    summary = {
        "accepted_only_dashboard": str(args.accepted_only),
        "all_targets_dashboard": str(args.all_targets),
        "policy": "oracle_sidecar_acceptance: accepted crops use accepted-only model; rejected crops use all-target model",
        "accepted_only": stats(accepted_eval),
        "all_targets": stats(all_eval),
        "dispatch": stats(dispatch_eval),
        "rows": rows,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "codec_raw_clean_dispatch_dashboard.json"
    html_path = args.out_dir / "codec_raw_clean_dispatch_dashboard.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(summary, html_path)
    return summary


def build_html(summary: dict[str, Any], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.3f}"
        return escape(str(v))

    html = [
        "<!doctype html><meta charset='utf-8'><title>Codec Raw Clean Dispatch Comparison</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}"
        ".card{border:1px solid #d8dee6;border-radius:8px;padding:10px;background:white}img{width:100%;height:auto;background:#111}"
        ".warn{background:#fff8dc;border:1px solid #dfc46d;padding:10px}</style>",
        "<h1>Codec Raw Clean Dispatch Comparison</h1>",
        "<p class='warn'>This is an oracle dispatch based on sidecar acceptance labels, not a runtime classifier.</p>",
        "<table><thead><tr><th>Candidate</th><th>All mean</th><th>Accepted mean</th><th>Rejected mean</th><th>Worst RMSE</th><th>Worst row</th></tr></thead><tbody>",
    ]
    for name in ("accepted_only", "all_targets", "dispatch"):
        s = summary[name]
        worst = s["worst_row"]
        worst_label = "" if worst is None else f"{worst['image_id']} {worst['crop']}"
        html.append("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            name,
            s["mean_clean_rmse_counts"],
            s["accepted_mean_clean_rmse_counts"],
            s["rejected_mean_clean_rmse_counts"],
            s["max_clean_rmse_counts"],
            worst_label,
        ]) + "</tr>")
    html.append("</tbody></table>")
    html.append("<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Accepted</th><th>Selected</th><th>Accepted-only RMSE</th><th>All-target RMSE</th><th>Dispatch RMSE</th></tr></thead><tbody>")
    for row in summary["rows"]:
        html.append("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"],
            row["crop"],
            row["iso"],
            row["accepted"],
            row["selected"],
            row["accepted_only_clean_rmse_counts"],
            row["all_targets_clean_rmse_counts"],
            row["dispatch_clean_rmse_counts"],
        ]) + "</tr>")
    html.append("</tbody></table><div class='grid'>")
    for row in summary["rows"]:
        html.append(f"<div class='card'><h3>{escape(row['image_id'])} {escape(row['crop'])}</h3>")
        html.append(
            f"<p>selected={escape(row['selected'])}; "
            f"accepted_only={float(row['accepted_only_clean_rmse_counts']):.2f}; "
            f"all_targets={float(row['all_targets_clean_rmse_counts']):.2f}; "
            f"dispatch={float(row['dispatch_clean_rmse_counts']):.2f}</p>"
        )
        for name, artifacts in (
            ("accepted_only", row["accepted_only_artifacts"]),
            ("all_targets", row["all_targets_artifacts"]),
        ):
            html.append(f"<h4>{escape(name)}</h4>")
            for label in ("model_clean", "clean_error_x16"):
                path = artifacts[label]
                html.append(f"<p>{escape(label)}</p><img src='{escape(rel(path, out))}'>")
        html.append("</div>")
    html.append("</div>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accepted-only", type=Path, default=DEFAULT_ACCEPTED)
    ap.add_argument("--all-targets", type=Path, default=DEFAULT_ALL)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    summary = build(args)
    print(args.out_dir / "codec_raw_clean_dispatch_dashboard.json")
    print(args.out_dir / "codec_raw_clean_dispatch_dashboard.html")
    print("dispatch mean clean rmse", summary["dispatch"]["mean_clean_rmse_counts"])
    print("dispatch accepted mean clean rmse", summary["dispatch"]["accepted_mean_clean_rmse_counts"])
    print("dispatch rejected mean clean rmse", summary["dispatch"]["rejected_mean_clean_rmse_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
