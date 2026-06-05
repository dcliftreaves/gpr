#!/usr/bin/env python3
"""Compare codec raw-clean candidates and a sidecar-label dispatch policy."""
from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gvid_metadata import validate_metadata  # noqa: E402


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


def load_metadata_acceptance(path: Path) -> dict[tuple[str, str], bool]:
    meta = json.loads(path.read_text())
    validate_metadata(meta)
    accepted_by_key: dict[tuple[str, str], bool] = {}
    for frame in meta["frames"]:
        source_id = str(frame["source_id"])
        for tile in frame["raw_clean_tiles"]:
            key = (source_id, str(tile["crop"]))
            if key in accepted_by_key:
                raise ValueError(f"duplicate metadata tile {key} in {path}")
            accepted_by_key[key] = bool(tile["accepted"])
    return accepted_by_key


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return float(np.mean([float(row[key]) for row in rows]))


def metric(row: dict[str, Any]) -> float:
    return float(row.get("target_rmse_counts", row["clean_rmse_counts"]))


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in rows if row["accepted"]]
    rejected = [row for row in rows if not row["accepted"]]
    return {
        "count": len(rows),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "mean_clean_rmse_counts": float(np.mean([metric(row) for row in rows])) if rows else None,
        "accepted_mean_clean_rmse_counts": float(np.mean([metric(row) for row in accepted])) if accepted else None,
        "rejected_mean_clean_rmse_counts": float(np.mean([metric(row) for row in rejected])) if rejected else None,
        "max_clean_rmse_counts": max((metric(row) for row in rows), default=None),
        "worst_row": max(rows, key=metric) if rows else None,
    }


def rel(path: str, out_file: Path) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(out_file.parent))
    except ValueError:
        return path


def artifact_path(artifacts: dict[str, str], *labels: str) -> str | None:
    for label in labels:
        if label in artifacts:
            return artifacts[label]
    return None


def build(args: argparse.Namespace) -> dict[str, Any]:
    accepted_rows = load_rows(args.accepted_only)
    all_rows = load_rows(args.all_targets)
    if set(accepted_rows) != set(all_rows):
        missing_a = sorted(set(all_rows) - set(accepted_rows))
        missing_b = sorted(set(accepted_rows) - set(all_rows))
        raise ValueError(f"dashboard key mismatch accepted_missing={missing_a} all_missing={missing_b}")
    metadata_acceptance = load_metadata_acceptance(args.metadata) if args.metadata else None
    if metadata_acceptance is not None and set(metadata_acceptance) != set(accepted_rows):
        missing_meta = sorted(set(accepted_rows) - set(metadata_acceptance))
        extra_meta = sorted(set(metadata_acceptance) - set(accepted_rows))
        raise ValueError(f"metadata key mismatch metadata_missing={missing_meta} metadata_extra={extra_meta}")

    rows = []
    label_mismatches = []
    for key in sorted(accepted_rows):
        a = accepted_rows[key]
        b = all_rows[key]
        if bool(a["accepted"]) != bool(b["accepted"]):
            raise ValueError(f"accepted flag mismatch for {key}")
        dashboard_accepted = bool(a["accepted"])
        accepted = metadata_acceptance[key] if metadata_acceptance is not None else dashboard_accepted
        if metadata_acceptance is not None and accepted != dashboard_accepted:
            label_mismatches.append({
                "image_id": a["image_id"],
                "crop": a["crop"],
                "dashboard_accepted": dashboard_accepted,
                "metadata_accepted": accepted,
            })
        selected = a if accepted else b
        selected_name = "accepted_only" if accepted else "all_targets"
        rows.append({
            "image_id": a["image_id"],
            "crop": a["crop"],
            "iso": a["iso"],
            "accepted": accepted,
            "dashboard_accepted": dashboard_accepted,
            "selected": selected_name,
            "accepted_only_clean_rmse_counts": metric(a),
            "all_targets_clean_rmse_counts": metric(b),
            "dispatch_clean_rmse_counts": metric(selected),
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
        "metadata": str(args.metadata) if args.metadata else None,
        "label_source": "gvid_source_metadata" if args.metadata else "dashboard_oracle",
        "policy": (
            "gvid_source_metadata_acceptance: accepted tiles use accepted-only model; rejected tiles use all-target model"
            if args.metadata else
            "oracle_dashboard_acceptance: accepted crops use accepted-only model; rejected crops use all-target model"
        ),
        "label_mismatches": label_mismatches,
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
        f"<p class='warn'>Policy: {escape(summary['policy'])}</p>",
    ]
    if summary["metadata"]:
        html.append(f"<p>Metadata: {escape(summary['metadata'])}</p>")
    if summary["label_mismatches"]:
        html.append(
            f"<p class='warn'>Dashboard label mismatches: {len(summary['label_mismatches'])}. "
            "Dispatch selection used metadata labels.</p>"
        )
    html.append("<table><thead><tr><th>Candidate</th><th>All mean</th><th>Accepted mean</th><th>Rejected mean</th><th>Worst RMSE</th><th>Worst row</th></tr></thead><tbody>")
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
    html.append("<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Accepted</th><th>Dashboard accepted</th><th>Selected</th><th>Accepted-only RMSE</th><th>All-target RMSE</th><th>Dispatch RMSE</th></tr></thead><tbody>")
    for row in summary["rows"]:
        html.append("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"],
            row["crop"],
            row["iso"],
            row["accepted"],
            row["dashboard_accepted"],
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
            for label, aliases in (
                ("model", ("model", "model_clean")),
                ("error_x16", ("target_error_x16", "clean_error_x16")),
            ):
                path = artifact_path(artifacts, *aliases)
                if path is not None:
                    html.append(f"<p>{escape(label)}</p><img src='{escape(rel(path, out))}'>")
        html.append("</div>")
    html.append("</div>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accepted-only", type=Path, default=DEFAULT_ACCEPTED)
    ap.add_argument("--all-targets", type=Path, default=DEFAULT_ALL)
    ap.add_argument("--metadata", type=Path, help="gvid_source_metadata.v1 sidecar; selects dispatch policy by source_id/crop")
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
