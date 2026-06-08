#!/usr/bin/env python3
"""Compare exact-crop PREVIEW inference with arbitrary full-frame tiling.

This audit is for the no-REF PREVIEW production blocker. It compares two
full-frame receipts that use the same source policy and expert route:

- exact manifest-crop tiles, which match the crop-local training contract;
- arbitrary full-frame tiles, which match the runtime render contract.

REF is used only for metrics and dashboard labels.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import pass_preview  # noqa: E402


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["image_id"]), str(row["crop"])


def by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {row_key(row): row for row in rows}


def source_rows(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    data = json.loads(path.read_text())
    return by_key(data.get("rows") or [])


def receipt_image_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(image["image_id"]): image for image in data.get("images") or []}


def copy_named(src: Path, dst_dir: Path, prefix: str) -> str:
    dst = dst_dir / f"{prefix}{src.suffix.lower()}"
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return dst.name


def abs_delta_png(a: np.ndarray, b: np.ndarray, dst: Path, gain: float = 4.0) -> str:
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.float32)
    delta = np.clip(delta * gain, 0, 255).astype(np.uint8)
    Image.fromarray(delta).save(dst)
    return dst.name


def metric_pair(ref: np.ndarray, img: np.ndarray) -> dict[str, Any]:
    metrics = compute_visual_metrics(ref, img)
    metrics["preview_pass"] = pass_preview(metrics)
    return metrics


def pixel_delta_stats(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    diff = a.astype(np.float32) - b.astype(np.float32)
    absdiff = np.abs(diff)
    luma = diff @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return {
        "mean_abs_rgb": float(absdiff.mean()),
        "p95_abs_rgb": float(np.percentile(absdiff, 95)),
        "max_abs_rgb": float(absdiff.max()),
        "mean_luma_delta": float(luma.mean()),
        "p95_abs_luma_delta": float(np.percentile(np.abs(luma), 95)),
    }


def area_intersection(a: list[int], b: list[int]) -> int:
    ax0, ay0, aw, ah = [int(v) for v in a]
    bx0, by0, bx1, by1 = [int(v) for v in b]
    ax1 = ax0 + aw
    ay1 = ay0 + ah
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0
    return (ix1 - ix0) * (iy1 - iy0)


def intersecting_roles(
    image_receipt: dict[str, Any] | None,
    crop_box: list[int] | None,
) -> dict[str, Any]:
    if not image_receipt or not crop_box:
        return {"role_count": 0, "roles": {}, "tiles": []}
    roles: dict[str, int] = {}
    tiles: list[dict[str, Any]] = []
    total_area = 0
    for tile in image_receipt.get("tiles") or []:
        area = area_intersection(tile.get("written_xywh") or tile.get("xywh") or [0, 0, 0, 0], crop_box)
        if area <= 0:
            continue
        role = str(tile.get("checkpoint_role") or "unknown")
        roles[role] = roles.get(role, 0) + area
        total_area += area
        tiles.append(
            {
                "xywh": tile.get("xywh"),
                "written_xywh": tile.get("written_xywh"),
                "role": role,
                "cluster": tile.get("cluster"),
                "override_cluster": tile.get("override_cluster"),
                "conditioning": tile.get("conditioning"),
                "area": area,
            }
        )
    role_fractions = {
        role: float(area) / float(total_area)
        for role, area in sorted(roles.items(), key=lambda item: (-item[1], item[0]))
    } if total_area else {}
    return {
        "role_count": len(role_fractions),
        "roles": role_fractions,
        "tiles": tiles,
    }


def exact_crop_role(image_receipt: dict[str, Any] | None, crop_name: str) -> dict[str, Any]:
    if not image_receipt:
        return {}
    for tile in image_receipt.get("tiles") or []:
        if str(tile.get("tile_label")) == crop_name:
            return {
                "role": tile.get("checkpoint_role"),
                "cluster": tile.get("cluster"),
                "override_cluster": tile.get("override_cluster"),
                "conditioning": tile.get("conditioning"),
            }
    return {}


def fmt_metric(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return str(value)


def write_html(payload: dict[str, Any], path: Path) -> None:
    rows = payload["rows"]
    css = """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#f7f7f4;color:#1f2328}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #d0d7de;padding:6px;vertical-align:top}
th{background:#e9ecef;position:sticky;top:0}
.pass{color:#116329;font-weight:600}.fail{color:#a40e26;font-weight:600}
.strip{display:grid;grid-template-columns:repeat(5,128px);gap:6px;align-items:start}
img{width:128px;height:128px;image-rendering:auto;object-fit:contain;background:#111}
.label{font-size:11px;color:#57606a}
.roles{max-width:280px;white-space:normal}
"""
    lines = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Full-Frame Contract Audit</title>",
        f"<style>{css}</style>",
        "<h1>PREVIEW Full-Frame Contract Audit</h1>",
        "<p>REF is used only for metrics. Exact-crop output is the crop-local contract; tiled output is the runtime full-frame contract.</p>",
        "<h2>Summary</h2>",
        "<pre>" + json.dumps(payload["summary"], indent=2) + "</pre>",
        "<table><thead><tr>",
        "<th>row</th><th>views at 100%</th><th>exact</th><th>tiled</th><th>exact-vs-tiled</th><th>runtime roles crossing crop</th>",
        "</tr></thead><tbody>",
    ]
    for row in rows:
        exact_pass = "pass" if row["exact_metrics"]["preview_pass"] else "fail"
        tiled_pass = "pass" if row["tiled_metrics"]["preview_pass"] else "fail"
        ev_metrics = row["exact_vs_tiled_metrics"]
        roles = "<br>".join(
            f"{role}: {frac:.2f}" for role, frac in row["tiled_intersections"]["roles"].items()
        )
        views = "".join(
            f"<div><img src='{name}'><div class='label'>{label}</div></div>"
            for label, name in [
                ("source", row["assets"]["source"]),
                ("REF", row["assets"]["ref"]),
                ("exact", row["assets"]["exact"]),
                ("tiled", row["assets"]["tiled"]),
                ("abs delta x4", row["assets"]["delta"]),
            ]
        )
        lines.extend(
            [
                "<tr>",
                f"<td><b>{row['image_id']}</b><br>{row['crop']}<br>"
                f"exact role: {row.get('exact_role', {}).get('role', '')}</td>",
                f"<td><div class='strip'>{views}</div></td>",
                f"<td class='{exact_pass}'>{'PASS' if row['exact_metrics']['preview_pass'] else 'FAIL'}<br>"
                f"LPIPS {fmt_metric(row['exact_metrics']['lpips'])}<br>"
                f"MS {fmt_metric(row['exact_metrics']['ms_ssim'])}<br>"
                f"Y {fmt_metric(row['exact_metrics']['y_psnr'], 2)}<br>"
                f"dE {fmt_metric(row['exact_metrics']['dE2000_mean'], 2)}</td>",
                f"<td class='{tiled_pass}'>{'PASS' if row['tiled_metrics']['preview_pass'] else 'FAIL'}<br>"
                f"LPIPS {fmt_metric(row['tiled_metrics']['lpips'])}<br>"
                f"MS {fmt_metric(row['tiled_metrics']['ms_ssim'])}<br>"
                f"Y {fmt_metric(row['tiled_metrics']['y_psnr'], 2)}<br>"
                f"dE {fmt_metric(row['tiled_metrics']['dE2000_mean'], 2)}</td>",
                f"<td>LPIPS {fmt_metric(ev_metrics['lpips'])}<br>"
                f"MS {fmt_metric(ev_metrics['ms_ssim'])}<br>"
                f"Y {fmt_metric(ev_metrics['y_psnr'], 2)}<br>"
                f"dE {fmt_metric(ev_metrics['dE2000_mean'], 2)}<br>"
                f"mean abs RGB {fmt_metric(row['pixel_delta']['mean_abs_rgb'], 2)}</td>",
                f"<td class='roles'>{roles}</td>",
                "</tr>",
            ]
        )
    lines.append("</tbody></table>")
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exact-receipt", type=Path, required=True)
    ap.add_argument("--tiled-receipt", type=Path, required=True)
    ap.add_argument("--source-receipt", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument(
        "--only-regressions",
        action="store_true",
        help="Only include rows where exact-crop passes and tiled runtime fails.",
    )
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard_html.parent.mkdir(parents=True, exist_ok=True)

    exact = json.loads(args.exact_receipt.read_text())
    tiled = json.loads(args.tiled_receipt.read_text())
    sources = source_rows(args.source_receipt)
    exact_rows = by_key(exact.get("rows") or [])
    tiled_rows = by_key(tiled.get("rows") or [])
    exact_images = receipt_image_map(exact)
    tiled_images = receipt_image_map(tiled)

    rows: list[dict[str, Any]] = []
    for key in sorted(set(exact_rows) & set(tiled_rows)):
        image_id, crop = key
        source_row = sources.get(key)
        if not source_row:
            raise FileNotFoundError(f"missing source receipt row for {image_id} {crop}")
        exact_row = exact_rows[key]
        tiled_row = tiled_rows[key]
        exact_path = args.exact_receipt.parent / str(exact_row["png"])
        tiled_path = args.tiled_receipt.parent / str(tiled_row["png"])
        source_path = Path(source_row["source_png"])
        ref_path = Path(source_row["ref_png"])
        ref_rgb = load_rgb(ref_path)
        source_rgb = load_rgb(source_path)
        exact_rgb = load_rgb(exact_path)
        tiled_rgb = load_rgb(tiled_path)
        exact_metrics = metric_pair(ref_rgb, exact_rgb)
        tiled_metrics = metric_pair(ref_rgb, tiled_rgb)
        if args.only_regressions and (not exact_metrics["preview_pass"] or tiled_metrics["preview_pass"]):
            continue
        exact_vs_tiled = compute_visual_metrics(exact_rgb, tiled_rgb)
        delta_name = abs_delta_png(
            exact_rgb,
            tiled_rgb,
            args.output_dir / f"{image_id}_{crop}_exact_vs_tiled_delta_x4.png",
        )
        prefix = f"{image_id}_{crop}_"
        crop_box = (source_row.get("source_render") or {}).get("crop_box_render")
        tiled_intersections = intersecting_roles(tiled_images.get(image_id), crop_box)
        exact_role = exact_crop_role(exact_images.get(image_id), crop)
        rows.append(
            {
                "image_id": image_id,
                "crop": crop,
                "source_crop_box_render": crop_box,
                "exact_role": exact_role,
                "tiled_intersections": tiled_intersections,
                "exact_metrics": exact_metrics,
                "tiled_metrics": tiled_metrics,
                "exact_vs_tiled_metrics": exact_vs_tiled,
                "pixel_delta": pixel_delta_stats(exact_rgb, tiled_rgb),
                "assets": {
                    "source": copy_named(source_path, args.output_dir, prefix + "source"),
                    "ref": copy_named(ref_path, args.output_dir, prefix + "ref"),
                    "exact": copy_named(exact_path, args.output_dir, prefix + "exact"),
                    "tiled": copy_named(tiled_path, args.output_dir, prefix + "tiled"),
                    "delta": delta_name,
                },
            }
        )

    regressions = [row for row in rows if row["exact_metrics"]["preview_pass"] and not row["tiled_metrics"]["preview_pass"]]
    both_fail = [row for row in rows if not row["exact_metrics"]["preview_pass"] and not row["tiled_metrics"]["preview_pass"]]
    role_mixed = [row for row in rows if row["tiled_intersections"]["role_count"] > 1]
    summary = {
        "row_count": len(rows),
        "exact_pass_count": sum(1 for row in rows if row["exact_metrics"]["preview_pass"]),
        "tiled_pass_count": sum(1 for row in rows if row["tiled_metrics"]["preview_pass"]),
        "exact_pass_tiled_fail_count": len(regressions),
        "both_fail_count": len(both_fail),
        "mixed_runtime_role_count": len(role_mixed),
        "worst_tiled_lpips": max((row["tiled_metrics"]["lpips"] for row in rows), default=0.0),
        "worst_tiled_dE2000_mean": max((row["tiled_metrics"]["dE2000_mean"] for row in rows), default=0.0),
        "worst_exact_vs_tiled_lpips": max((row["exact_vs_tiled_metrics"]["lpips"] for row in rows), default=0.0),
        "median_exact_vs_tiled_mean_abs_rgb": float(np.median([row["pixel_delta"]["mean_abs_rgb"] for row in rows])) if rows else 0.0,
    }
    payload = {
        "schema": "preview_fullframe_contract_audit.v1",
        "exact_receipt": str(args.exact_receipt),
        "tiled_receipt": str(args.tiled_receipt),
        "source_receipt": str(args.source_receipt),
        "runtime_contract": {
            "forbidden_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes", "gate metrics"],
            "compared_paths": ["exact manifest-crop tiled inference", "arbitrary full-frame tiled inference"],
        },
        "summary": summary,
        "rows": rows,
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.dashboard_html)
    print(json.dumps(summary, indent=2), flush=True)
    print(args.dashboard_json)
    print(args.dashboard_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
