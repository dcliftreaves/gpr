#!/usr/bin/env python3
"""Aggregate PREVIEW full-frame failure modes across existing receipts."""

from __future__ import annotations

import argparse
import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLDS = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}

METRICS = ("lpips", "ms_ssim", "y_psnr", "dE2000_mean")


def finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def metric_pass(metric: str, value: float | None, thresholds: dict[str, float]) -> bool:
    if value is None:
        return False
    if metric in ("lpips", "dE2000_mean"):
        return value <= thresholds[metric]
    return value >= thresholds[metric]


def metric_margin(metric: str, value: float | None, thresholds: dict[str, float]) -> float:
    """Positive values mean the metric misses the gate."""
    if value is None:
        return float("inf")
    threshold = thresholds[metric]
    if metric in ("lpips", "dE2000_mean"):
        return value - threshold
    return threshold - value


def metric_severity(metric: str, value: float | None, thresholds: dict[str, float]) -> float:
    if value is None:
        return 0.0
    margin = metric_margin(metric, value, thresholds)
    if margin <= 0:
        return 0.0
    threshold = thresholds[metric]
    if threshold == 0:
        return margin
    return margin / abs(threshold)


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('image_id', '')}:{row.get('crop', '')}"


def extract_metrics(row: dict[str, Any]) -> dict[str, float | None]:
    return {metric: finite_float(row.get(metric)) for metric in METRICS}


def normalize_generic_rows(label: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "variant" in row:
            variant = f"{label}:{row['variant']}"
        else:
            variant = label
        metrics = extract_metrics(row)
        if all(metrics[m] is None for m in METRICS):
            continue
        out.append(
            {
                "source": label,
                "variant": variant,
                "image_id": row.get("image_id"),
                "crop": row.get("crop"),
                "metrics": metrics,
                "preview_pass": bool(row.get("preview_pass", False)),
            }
        )
    return out


def normalize_variant_oracle(label: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("oracle_rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "source": label,
                "variant": f"{label}:{row.get('best_variant', 'best')}",
                "image_id": row.get("image_id"),
                "crop": row.get("crop"),
                "metrics": extract_metrics(row),
                "preview_pass": bool(row.get("preview_pass", False)),
            }
        )
    return out


def normalize_contract_audit(label: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tiled_intersections = row.get("tiled_intersections") or {}
        exact_role = row.get("exact_role") or {}
        contract_meta = {
            "exact_role": exact_role.get("role"),
            "tiled_role_count": tiled_intersections.get("role_count"),
            "tiled_roles": tiled_intersections.get("roles") or {},
        }
        for variant, field in (("exact_manifest_crop", "exact_metrics"), ("arbitrary_tiled", "tiled_metrics")):
            metrics_row = row.get(field)
            if not isinstance(metrics_row, dict):
                continue
            out.append(
                {
                    "source": label,
                    "variant": f"{label}:{variant}",
                    "image_id": row.get("image_id"),
                    "crop": row.get("crop"),
                    "metrics": extract_metrics(metrics_row),
                    "preview_pass": bool(metrics_row.get("preview_pass", False)),
                    "metadata": contract_meta,
                }
            )
    return out


def normalize_alignment_oracle(label: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    metric_map = {
        "lpips": "lpips",
        "ms_ssim": "ms_ssim",
        "y_psnr": "y_psnr",
        "dE2000_mean": "dE2000_mean",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        for prefix, variant in (("base", "base"), ("oracle", "alignment_oracle")):
            metrics = {
                metric: finite_float(row.get(f"{prefix}_{source_key}"))
                for source_key, metric in metric_map.items()
            }
            out.append(
                {
                    "source": label,
                    "variant": f"{label}:{variant}",
                    "image_id": row.get("image_id"),
                    "crop": row.get("crop"),
                    "metrics": metrics,
                    "preview_pass": bool(row.get(f"{prefix}_preview_pass", False)),
                }
            )
    return out


def normalize_exact_teacher_distill_score(label: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in (
            "source_vs_teacher",
            "output_vs_teacher",
            "source_vs_ref",
            "teacher_vs_ref",
            "output_vs_ref",
        ):
            metrics_row = row.get(field)
            if not isinstance(metrics_row, dict):
                continue
            out.append(
                {
                    "source": label,
                    "variant": f"{label}:{field}",
                    "image_id": row.get("image_id"),
                    "crop": row.get("crop"),
                    "metrics": extract_metrics(metrics_row),
                    "preview_pass": bool(metrics_row.get("preview_pass", False)),
                }
            )
    return out


def normalize_receipt(label: str, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text())
    schema = str(payload.get("schema", ""))
    if schema == "preview_fullframe_contract_audit.v1":
        rows = normalize_contract_audit(label, payload)
    elif schema == "preview_fullframe_alignment_oracle.v1":
        rows = normalize_alignment_oracle(label, payload)
    elif schema == "preview_exact_teacher_distill_score.v1":
        rows = normalize_exact_teacher_distill_score(label, payload)
    elif "oracle_rows" in payload:
        rows = normalize_variant_oracle(label, payload)
    else:
        rows = normalize_generic_rows(label, payload)
    return payload, rows


def summarize_rows(
    rows: list[dict[str, Any]], thresholds: dict[str, float]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_row: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[row["variant"]].append(row)
        by_row[row_key(row)].append(row)

    variant_summary = []
    for variant, group in sorted(by_variant.items()):
        count = len(group)
        pass_count = sum(1 for row in group if row["preview_pass"])
        worst: dict[str, float | None] = {}
        for metric in METRICS:
            values = [row["metrics"][metric] for row in group if row["metrics"][metric] is not None]
            if not values:
                worst[metric] = None
            elif metric in ("lpips", "dE2000_mean"):
                worst[metric] = max(values)
            else:
                worst[metric] = min(values)
        variant_summary.append(
            {
                "variant": variant,
                "count": count,
                "pass_count": pass_count,
                "pass_rate": pass_count / count if count else 0.0,
                "worst_metrics": worst,
            }
        )

    row_summary = []
    for key, group in sorted(by_row.items()):
        metric_fail_counts = Counter()
        worst_severity = 0.0
        worst_variant = None
        best_pass_variant = None
        for row in group:
            if row["preview_pass"] and best_pass_variant is None:
                best_pass_variant = row["variant"]
            row_severity = 0.0
            for metric in METRICS:
                value = row["metrics"][metric]
                if not metric_pass(metric, value, thresholds):
                    metric_fail_counts[metric] += 1
                    row_severity += metric_severity(metric, value, thresholds)
            if row_severity > worst_severity:
                worst_severity = row_severity
                worst_variant = row["variant"]
        image_id, crop = key.split(":", 1)
        row_summary.append(
            {
                "row": key,
                "image_id": image_id,
                "crop": crop,
                "variant_count": len(group),
                "pass_variant_count": sum(1 for row in group if row["preview_pass"]),
                "best_pass_variant": best_pass_variant,
                "worst_variant": worst_variant,
                "worst_failure_severity": worst_severity,
                "metric_fail_counts": dict(metric_fail_counts),
            }
        )
    row_summary.sort(key=lambda row: (-row["worst_failure_severity"], row["row"]))

    contract_rows = []
    for key, group in sorted(by_row.items()):
        exact = next((row for row in group if row["variant"].endswith(":exact_manifest_crop")), None)
        tiled = next((row for row in group if row["variant"].endswith(":arbitrary_tiled")), None)
        if exact is None or tiled is None:
            continue
        if exact["preview_pass"] and not tiled["preview_pass"]:
            metadata = tiled.get("metadata") or {}
            tiled_role_count = metadata.get("tiled_role_count")
            try:
                tiled_role_count_int = int(tiled_role_count)
            except (TypeError, ValueError):
                tiled_role_count_int = 0
            failures = {
                metric: metric_margin(metric, tiled["metrics"][metric], thresholds)
                for metric in METRICS
                if not metric_pass(metric, tiled["metrics"][metric], thresholds)
            }
            image_id, crop = key.split(":", 1)
            contract_rows.append(
                {
                    "row": key,
                    "image_id": image_id,
                    "crop": crop,
                    "exact_role": metadata.get("exact_role"),
                    "tiled_role_count": tiled_role_count_int,
                    "mixed_tiled_roles": tiled_role_count_int > 1,
                    "tiled_roles": metadata.get("tiled_roles") or {},
                    "tiled_failures": failures,
                    "exact_metrics": exact["metrics"],
                    "tiled_metrics": tiled["metrics"],
                }
            )
    contract_rows.sort(key=lambda row: (-sum(max(v, 0.0) for v in row["tiled_failures"].values()), row["row"]))

    return variant_summary, row_summary, contract_rows


def write_html(path: Path, payload: dict[str, Any]) -> None:
    def fmt_metric(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            if math.isinf(value):
                return "inf"
            return f"{value:.4f}"
        return html.escape(str(value))

    variant_rows = []
    for row in payload["variant_summary"]:
        worst = row["worst_metrics"]
        variant_rows.append(
            "<tr>"
            f"<td>{html.escape(row['variant'])}</td>"
            f"<td>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate']:.2%}</td>"
            f"<td>{fmt_metric(worst.get('lpips'))}</td>"
            f"<td>{fmt_metric(worst.get('ms_ssim'))}</td>"
            f"<td>{fmt_metric(worst.get('y_psnr'))}</td>"
            f"<td>{fmt_metric(worst.get('dE2000_mean'))}</td>"
            "</tr>"
        )

    hard_rows = []
    for row in payload["row_summary"][:40]:
        hard_rows.append(
            "<tr>"
            f"<td>{html.escape(row['row'])}</td>"
            f"<td>{row['pass_variant_count']}/{row['variant_count']}</td>"
            f"<td>{html.escape(str(row['best_pass_variant'] or ''))}</td>"
            f"<td>{html.escape(str(row['worst_variant'] or ''))}</td>"
            f"<td>{row['worst_failure_severity']:.3f}</td>"
            f"<td>{html.escape(json.dumps(row['metric_fail_counts'], sort_keys=True))}</td>"
            "</tr>"
        )

    contract_rows = []
    for row in payload["exact_pass_tiled_fail_rows"]:
        contract_rows.append(
            "<tr>"
            f"<td>{html.escape(row['row'])}</td>"
            f"<td>{html.escape(str(row.get('exact_role') or ''))}</td>"
            f"<td>{row.get('tiled_role_count', 0)}</td>"
            f"<td>{html.escape(json.dumps(row.get('tiled_roles') or {}, sort_keys=True))}</td>"
            f"<td>{html.escape(json.dumps(row['tiled_failures'], sort_keys=True))}</td>"
            f"<td>{html.escape(json.dumps(row['exact_metrics'], sort_keys=True))}</td>"
            f"<td>{html.escape(json.dumps(row['tiled_metrics'], sort_keys=True))}</td>"
            "</tr>"
        )

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PREVIEW Full-Frame Failure Mode Audit</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2933; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0 28px; font-size: 13px; }}
th, td {{ border: 1px solid #ccd5df; padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf2f7; }}
code, pre {{ background: #f4f7fa; padding: 2px 4px; }}
.summary {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 12px; margin: 16px 0; }}
.tile {{ border: 1px solid #ccd5df; padding: 10px; border-radius: 6px; background: #fbfcfd; }}
</style>
</head>
<body>
<h1>PREVIEW Full-Frame Failure Mode Audit</h1>
<p>This dashboard aggregates existing receipts. It is diagnostic evidence only; it does not register a production path.</p>
<div class="summary">
<div class="tile"><strong>Receipts</strong><br>{len(payload['receipts'])}</div>
<div class="tile"><strong>Normalized Rows</strong><br>{payload['summary']['normalized_row_count']}</div>
<div class="tile"><strong>Unique Row Keys</strong><br>{payload['summary']['unique_row_count']}</div>
<div class="tile"><strong>Exact Pass / Tiled Fail</strong><br>{payload['summary']['exact_pass_tiled_fail_count']}</div>
<div class="tile"><strong>Mixed / Coherent Role Fails</strong><br>{payload['summary']['exact_pass_tiled_fail_mixed_role_count']} / {payload['summary']['exact_pass_tiled_fail_coherent_role_count']}</div>
</div>
<h2>Variant Summary</h2>
<table>
<thead><tr><th>Variant</th><th>Pass</th><th>Rate</th><th>Worst LPIPS</th><th>Worst MS-SSIM</th><th>Worst Y-PSNR</th><th>Worst dE2000</th></tr></thead>
<tbody>
{''.join(variant_rows)}
</tbody>
</table>
<h2>Hardest Rows Across Receipts</h2>
<table>
<thead><tr><th>Row</th><th>Passing Variants</th><th>Best Passing Variant</th><th>Worst Variant</th><th>Severity</th><th>Metric Fail Counts</th></tr></thead>
<tbody>
{''.join(hard_rows)}
</tbody>
</table>
<h2>Exact Manifest-Crop Pass But Arbitrary-Tiled Fail</h2>
<table>
<thead><tr><th>Row</th><th>Exact Role</th><th>Tiled Role Count</th><th>Tiled Roles</th><th>Tiled Fail Margins</th><th>Exact Metrics</th><th>Tiled Metrics</th></tr></thead>
<tbody>
{''.join(contract_rows)}
</tbody>
</table>
</body>
</html>
"""
    path.write_text(doc)


def parse_receipt_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        path = Path(value)
        return path.parent.name, path
    label, raw_path = value.split("=", 1)
    return label, Path(raw_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="append", required=True, help="label=/path/to/receipt.json")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-html", type=Path)
    args = parser.parse_args()

    thresholds = dict(DEFAULT_THRESHOLDS)
    receipts = []
    normalized_rows: list[dict[str, Any]] = []
    for receipt_arg in args.receipt:
        label, path = parse_receipt_arg(receipt_arg)
        payload, rows = normalize_receipt(label, path)
        receipts.append(
            {
                "label": label,
                "path": str(path),
                "schema": payload.get("schema"),
                "normalized_rows": len(rows),
            }
        )
        normalized_rows.extend(rows)

    variant_summary, row_summary, contract_rows = summarize_rows(normalized_rows, thresholds)
    mixed_contract = sum(1 for row in contract_rows if row.get("mixed_tiled_roles"))
    coherent_contract = len(contract_rows) - mixed_contract
    payload = {
        "schema": "preview_fullframe_failure_mode_audit.v1",
        "thresholds": thresholds,
        "receipts": receipts,
        "summary": {
            "normalized_row_count": len(normalized_rows),
            "unique_row_count": len({row_key(row) for row in normalized_rows}),
            "variant_count": len(variant_summary),
            "exact_pass_tiled_fail_count": len(contract_rows),
            "exact_pass_tiled_fail_mixed_role_count": mixed_contract,
            "exact_pass_tiled_fail_coherent_role_count": coherent_contract,
            "top_failure_images": dict(Counter(row["image_id"] for row in row_summary[:40]).most_common()),
        },
        "variant_summary": variant_summary,
        "row_summary": row_summary,
        "exact_pass_tiled_fail_rows": contract_rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    if args.output_html:
        args.output_html.parent.mkdir(parents=True, exist_ok=True)
        write_html(args.output_html, payload)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
