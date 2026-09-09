#!/usr/bin/env python3
"""Score an oracle union between two PREVIEW row-level receipts.

This is a planning diagnostic for runtime source-policy work. It does not claim
a deployable selector because the oracle chooses per row from already-scored
metrics. Its job is to show whether training a source-derived selector between
two no-REF candidate paths has enough ceiling to be worth doing.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any


PREVIEW_THRESHOLDS = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}
METRICS = ("lpips", "ms_ssim", "y_psnr", "dE2000_mean")


def finite_float(value: Any) -> float:
    out = float(value)
    if not math.isfinite(out):
        return out
    return out


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["image_id"]), str(row["crop"])


def metric_pass(metric: str, value: float) -> bool:
    threshold = PREVIEW_THRESHOLDS[metric]
    if metric in {"lpips", "dE2000_mean"}:
        return value <= threshold
    return value >= threshold


def normalized_miss_score(row: dict[str, Any]) -> float:
    lpips = finite_float(row["lpips"]) / PREVIEW_THRESHOLDS["lpips"]
    ms = PREVIEW_THRESHOLDS["ms_ssim"] / max(finite_float(row["ms_ssim"]), 1e-6)
    y = PREVIEW_THRESHOLDS["y_psnr"] / max(finite_float(row["y_psnr"]), 1e-6)
    de = finite_float(row["dE2000_mean"]) / PREVIEW_THRESHOLDS["dE2000_mean"]
    return max(lpips, ms, y, de)


def summarize(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    if not rows:
        return {
            "variant": variant,
            "count": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "worst_lpips": 0.0,
            "worst_ms_ssim": 0.0,
            "worst_y_psnr": 0.0,
            "worst_dE2000_mean": 0.0,
        }
    pass_count = sum(1 for row in rows if row["preview_pass"])
    return {
        "variant": variant,
        "count": len(rows),
        "pass_count": pass_count,
        "pass_rate": pass_count / len(rows),
        "worst_lpips": max(finite_float(row["lpips"]) for row in rows),
        "worst_ms_ssim": min(finite_float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(finite_float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(finite_float(row["dE2000_mean"]) for row in rows),
    }


def load_rows(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text())
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError(f"{path} has no row list")
    return {row_key(row): row for row in rows}


def collect(args: argparse.Namespace) -> dict[str, Any]:
    a_rows = load_rows(args.candidate_a)
    b_rows = load_rows(args.candidate_b)
    if set(a_rows) != set(b_rows):
        missing_a = sorted(set(b_rows) - set(a_rows))
        missing_b = sorted(set(a_rows) - set(b_rows))
        raise RuntimeError(f"row-key mismatch: missing_a={missing_a[:5]} missing_b={missing_b[:5]}")

    rows = []
    selected_rows = []
    for key in sorted(a_rows):
        a = a_rows[key]
        b = b_rows[key]
        a_pass = bool(a.get("preview_pass"))
        b_pass = bool(b.get("preview_pass"))
        if a_pass and not b_pass:
            selected_name, selected = args.label_a, a
        elif b_pass and not a_pass:
            selected_name, selected = args.label_b, b
        elif a_pass and b_pass:
            selected_name, selected = (args.label_a, a) if normalized_miss_score(a) <= normalized_miss_score(b) else (args.label_b, b)
        else:
            selected_name, selected = (args.label_a, a) if normalized_miss_score(a) <= normalized_miss_score(b) else (args.label_b, b)
        selected_row = {
            "image_id": key[0],
            "crop": key[1],
            "variant": "oracle_union",
            "selected": selected_name,
            "candidate_a_pass": a_pass,
            "candidate_b_pass": b_pass,
            "preview_pass": a_pass or b_pass,
            **{metric: finite_float(selected[metric]) for metric in METRICS},
        }
        selected_rows.append(selected_row)
        rows.append(
            {
                "image_id": key[0],
                "crop": key[1],
                "candidate_a": {metric: finite_float(a[metric]) for metric in METRICS} | {"preview_pass": a_pass},
                "candidate_b": {metric: finite_float(b[metric]) for metric in METRICS} | {"preview_pass": b_pass},
                "oracle_union": selected_row,
            }
        )

    both_fail = [row for row in rows if not row["candidate_a"]["preview_pass"] and not row["candidate_b"]["preview_pass"]]
    a_only = [row for row in rows if row["candidate_a"]["preview_pass"] and not row["candidate_b"]["preview_pass"]]
    b_only = [row for row in rows if row["candidate_b"]["preview_pass"] and not row["candidate_a"]["preview_pass"]]
    return {
        "schema": "preview_policy_union_score.v1",
        "thresholds": PREVIEW_THRESHOLDS,
        "candidate_a": {"label": args.label_a, "path": str(args.candidate_a)},
        "candidate_b": {"label": args.label_b, "path": str(args.candidate_b)},
        "render_contract": {
            "candidate_inputs": ["existing no-REF row-level receipts"],
            "uses_ref_at_render_time": False,
            "oracle_uses_metrics_for_selection": True,
            "intended_use": "upper bound for a trainable runtime source-policy selector",
        },
        "summary": [
            summarize(list(a_rows.values()), args.label_a),
            summarize(list(b_rows.values()), args.label_b),
            summarize(selected_rows, "oracle_union"),
        ],
        "selector_ceiling": {
            "union_pass_count": sum(1 for row in selected_rows if row["preview_pass"]),
            "count": len(selected_rows),
            "candidate_a_only_pass": len(a_only),
            "candidate_b_only_pass": len(b_only),
            "both_fail": len(both_fail),
        },
        "rows": rows,
    }


def fmt(value: float) -> str:
    return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"


def write_html(payload: dict[str, Any], path: Path) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:22px; color:#1f2933; }
table { border-collapse:collapse; width:100%; font-size:12px; margin:14px 0 26px; }
th,td { border:1px solid #cbd5df; padding:6px 8px; text-align:right; vertical-align:top; }
th.left,td.left { text-align:left; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:10px; margin:14px 0; }
.card { border:1px solid #cbd5df; border-radius:6px; padding:10px; background:#fbfcfd; }
.pass { color:#12652f; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
"""
    ceiling = payload["selector_ceiling"]
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Policy Union Score</title>",
        f"<style>{css}</style><h1>PREVIEW Policy Union Score</h1>",
        "<p>Oracle upper bound for selecting between two no-REF PREVIEW candidate receipts. Selection uses scored metrics and is not deployable.</p>",
        "<div class=cards>",
        f"<div class=card><b>Union pass</b><br>{ceiling['union_pass_count']}/{ceiling['count']}</div>",
        f"<div class=card><b>A-only pass</b><br>{ceiling['candidate_a_only_pass']}</div>",
        f"<div class=card><b>B-only pass</b><br>{ceiling['candidate_b_only_pass']}</div>",
        f"<div class=card><b>Both fail</b><br>{ceiling['both_fail']}</div>",
        "</div><h2>Summary</h2><table><thead><tr><th class=left>variant</th><th>pass</th><th>rate</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['variant'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate']:.1%}</td><td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td></tr>"
        )
    parts.append("</tbody></table><h2>Both-Fail Rows</h2><table><thead><tr><th class=left>image</th><th class=left>crop</th><th>A LPIPS</th><th>A MS</th><th>A Y</th><th>A dE</th><th>B LPIPS</th><th>B MS</th><th>B Y</th><th>B dE</th></tr></thead><tbody>")
    for row in payload["rows"]:
        a = row["candidate_a"]
        b = row["candidate_b"]
        if a["preview_pass"] or b["preview_pass"]:
            continue
        parts.append(
            f"<tr><td class=left>{html.escape(row['image_id'])}</td><td class=left>{html.escape(row['crop'])}</td>"
            f"<td>{fmt(a['lpips'])}</td><td>{fmt(a['ms_ssim'])}</td><td>{fmt(a['y_psnr'])}</td><td>{fmt(a['dE2000_mean'])}</td>"
            f"<td>{fmt(b['lpips'])}</td><td>{fmt(b['ms_ssim'])}</td><td>{fmt(b['y_psnr'])}</td><td>{fmt(b['dE2000_mean'])}</td></tr>"
        )
    parts.append("</tbody></table>")
    path.write_text("".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-a", type=Path, required=True)
    parser.add_argument("--candidate-b", type=Path, required=True)
    parser.add_argument("--label-a", default="candidate_a")
    parser.add_argument("--label-b", default="candidate_b")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    args = parser.parse_args()
    payload = collect(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    for row in payload["summary"]:
        print(f"{row['variant']:<28} {row['pass_count']:>3}/{row['count']:<3} LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}")
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
