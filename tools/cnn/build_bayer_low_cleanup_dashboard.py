#!/usr/bin/env python3
"""Build a full-frame dashboard for 1x Bayer cleanup candidates."""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


RAW_PEAK = 16383.0


def read_u16(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected}")
    return arr.reshape((height, width))


def raw_metrics(candidate: np.ndarray, target: np.ndarray) -> dict[str, float | int]:
    if candidate.shape != target.shape:
        raise ValueError(f"shape mismatch: {candidate.shape} vs {target.shape}")
    diff = candidate.astype(np.int32) - target.astype(np.int32)
    absdiff = np.abs(diff)
    mse = float(np.mean(diff.astype(np.float64) ** 2))
    psnr = 999.0 if mse <= 1e-12 else 20.0 * math.log10(RAW_PEAK) - 10.0 * math.log10(mse)
    return {
        "rmse_lsb": math.sqrt(mse),
        "mae_lsb": float(np.mean(absdiff)),
        "p95_abs_lsb": float(np.percentile(absdiff, 95)),
        "p99_abs_lsb": float(np.percentile(absdiff, 99)),
        "max_abs_lsb": int(absdiff.max(initial=0)),
        "psnr_db": psnr,
    }


def metric_delta(base: dict[str, float | int], candidate: dict[str, float | int], key: str) -> float:
    before = float(base[key])
    after = float(candidate[key])
    if before == 0.0:
        return 0.0
    return 100.0 * (before - after) / before


def bayer_planes(bayer: np.ndarray) -> list[np.ndarray]:
    return [
        bayer[0::2, 0::2].astype(np.float32),
        bayer[0::2, 1::2].astype(np.float32),
        bayer[1::2, 0::2].astype(np.float32),
        bayer[1::2, 1::2].astype(np.float32),
    ]


def bayer_wb_gains(bayer: np.ndarray) -> list[float]:
    planes = bayer_planes(bayer)
    medians = [float(np.median(plane)) for plane in planes]
    green = max(1.0, 0.5 * (medians[1] + medians[2]))
    return [
        green / max(1.0, medians[0]),
        1.0,
        1.0,
        green / max(1.0, medians[3]),
    ]


def bayer_to_linear_rgb(bayer: np.ndarray, gains: list[float]) -> np.ndarray:
    height, width = bayer.shape
    planes = [plane * gains[idx] for idx, plane in enumerate(bayer_planes(bayer))]
    resized: list[np.ndarray] = []
    for plane in planes:
        img = Image.fromarray(plane, mode="F").resize((width, height), Image.Resampling.BILINEAR)
        resized.append(np.asarray(img, dtype=np.float32))
    green = 0.5 * (resized[1] + resized[2])
    return np.stack([resized[0], green, resized[3]], axis=-1)


def bayer_to_proxy_rgb(bayer: np.ndarray, lo: float, hi: float, gains: list[float]) -> np.ndarray:
    rgb = bayer_to_linear_rgb(bayer, gains)
    rgb = np.clip((rgb - lo) / max(1.0, hi - lo), 0.0, 1.0)
    rgb = np.power(rgb, 1.0 / 2.2)
    return (rgb * 255.0 + 0.5).astype(np.uint8)


def fixed_crops(width: int, height: int, crop: int, inset: int) -> dict[str, tuple[int, int, int, int]]:
    crop = min(crop, width, height)
    inset = max(0, min(inset, max(0, min(width, height) - crop)))
    return {
        "upper_left": (inset, inset, crop, crop),
        "center": ((width - crop) // 2, (height - crop) // 2, crop, crop),
        "lower_right": (width - crop - inset, height - crop - inset, crop, crop),
    }


def save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)


def diff_rgb(a: np.ndarray, b: np.ndarray, gain: float) -> np.ndarray:
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.float32)
    return np.clip(diff * gain, 0, 255).astype(np.uint8)


def parse_dataset(value: str) -> dict[str, Any]:
    parts = value.split(":")
    if len(parts) != 6:
        raise argparse.ArgumentTypeError(
            "--dataset expects NAME:LOW_DIR:CLEAN_DIR:CANDIDATE_DIR:WIDTH:HEIGHT"
        )
    name, low_dir, clean_dir, candidate_dir, width, height = parts
    return {
        "name": name,
        "low_dir": Path(low_dir),
        "clean_dir": Path(clean_dir),
        "candidate_dir": Path(candidate_dir),
        "width": int(width),
        "height": int(height),
    }


def summarize(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "mean": statistics.mean(ordered),
        "max": ordered[-1],
    }


def build_dashboard(args: argparse.Namespace) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    crop_rows: list[dict[str, Any]] = []
    crop_dir = args.output_dir / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    stems_filter = set(args.stem or [])

    for dataset in args.dataset:
        low_dir = dataset["low_dir"]
        clean_dir = dataset["clean_dir"]
        candidate_dir = dataset["candidate_dir"]
        width = int(dataset["width"])
        height = int(dataset["height"])
        for clean_path in sorted(clean_dir.glob("*.raw")):
            stem = clean_path.stem
            if stems_filter and stem not in stems_filter:
                continue
            low_path = low_dir / clean_path.name
            candidate_path = candidate_dir / clean_path.name
            if not low_path.exists() or not candidate_path.exists():
                continue
            clean = read_u16(clean_path, width, height)
            low = read_u16(low_path, width, height)
            candidate = read_u16(candidate_path, width, height)
            baseline = raw_metrics(low, clean)
            model = raw_metrics(candidate, clean)
            row = {
                "dataset": dataset["name"],
                "stem": stem,
                "width": width,
                "height": height,
                "baseline": baseline,
                "candidate": model,
                "rmse_improvement_pct": metric_delta(baseline, model, "rmse_lsb"),
                "mae_improvement_pct": metric_delta(baseline, model, "mae_lsb"),
                "psnr_delta_db": float(model["psnr_db"]) - float(baseline["psnr_db"]),
            }
            rows.append(row)

            if args.no_crops:
                continue
            gains = [1.0, 1.0, 1.0, 1.0] if args.no_auto_wb else bayer_wb_gains(clean)
            clean_linear_rgb = bayer_to_linear_rgb(clean, gains)
            lo, hi = np.percentile(clean_linear_rgb, [args.tone_low_percentile, args.tone_high_percentile])
            clean_rgb = bayer_to_proxy_rgb(clean, float(lo), float(hi), gains)
            low_rgb = bayer_to_proxy_rgb(low, float(lo), float(hi), gains)
            candidate_rgb = bayer_to_proxy_rgb(candidate, float(lo), float(hi), gains)
            for crop_name, (x, y, crop_w, crop_h) in fixed_crops(width, height, args.crop_size, args.edge_inset).items():
                prefix = f"{stem}_{crop_name}"
                clean_png = crop_dir / f"{prefix}_clean.png"
                low_png = crop_dir / f"{prefix}_baseline.png"
                candidate_png = crop_dir / f"{prefix}_candidate.png"
                baseline_diff_png = crop_dir / f"{prefix}_baseline_diff_x{args.diff_gain:g}.png"
                candidate_diff_png = crop_dir / f"{prefix}_candidate_diff_x{args.diff_gain:g}.png"
                clean_crop = clean_rgb[y : y + crop_h, x : x + crop_w]
                low_crop = low_rgb[y : y + crop_h, x : x + crop_w]
                candidate_crop = candidate_rgb[y : y + crop_h, x : x + crop_w]
                save_png(clean_png, clean_crop)
                save_png(low_png, low_crop)
                save_png(candidate_png, candidate_crop)
                save_png(baseline_diff_png, diff_rgb(low_crop, clean_crop, args.diff_gain))
                save_png(candidate_diff_png, diff_rgb(candidate_crop, clean_crop, args.diff_gain))
                crop_rows.append(
                    {
                        "dataset": dataset["name"],
                        "stem": stem,
                        "crop": crop_name,
                        "box": [x, y, crop_w, crop_h],
                        "clean_png": str(clean_png),
                        "baseline_png": str(low_png),
                        "candidate_png": str(candidate_png),
                        "baseline_diff_png": str(baseline_diff_png),
                        "candidate_diff_png": str(candidate_diff_png),
                        "auto_wb_gains": gains,
                    }
                )

    summary = {
        "count": len(rows),
        "rmse_improvement_pct": summarize([float(row["rmse_improvement_pct"]) for row in rows]),
        "mae_improvement_pct": summarize([float(row["mae_improvement_pct"]) for row in rows]),
        "psnr_delta_db": summarize([float(row["psnr_delta_db"]) for row in rows]),
    }
    return {
        "schema": "gpr.bayer_low_cleanup_dashboard.v1",
        "datasets": [
            {
                "name": item["name"],
                "low_dir": str(item["low_dir"]),
                "clean_dir": str(item["clean_dir"]),
                "candidate_dir": str(item["candidate_dir"]),
                "width": item["width"],
                "height": item["height"],
            }
            for item in args.dataset
        ],
        "summary": summary,
        "review_render": {
            "auto_wb": not args.no_auto_wb,
            "wb_source": "clean target CFA medians",
            "tone_source": "white-balanced clean target proxy RGB percentiles",
            "tone_low_percentile": args.tone_low_percentile,
            "tone_high_percentile": args.tone_high_percentile,
        },
        "rows": rows,
        "crop_rows": crop_rows,
    }


def write_html(path: Path, payload: dict[str, Any]) -> None:
    rows = sorted(payload["rows"], key=lambda row: row["rmse_improvement_pct"])
    crop_rows = {(row["stem"], row["crop"]): row for row in payload["crop_rows"]}
    css = """
    body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#1f2328;background:#fff}
    h1{font-size:24px;margin:0 0 8px} h2{font-size:18px;margin:28px 0 12px}
    pre{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:12px;overflow:auto}
    table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #d8dee4;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}
    .row{border-top:1px solid #d8dee4;padding-top:16px;margin-top:16px}
    .thumbs{display:grid;grid-template-columns:repeat(5,max-content);gap:10px;overflow-x:auto}
    figure{margin:0}figcaption{font-size:12px;color:#57606a;margin-top:4px}
    img{width:512px;height:512px;max-width:none;border:1px solid #d0d7de}
    """
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(payload['schema'])}</title><style>{css}</style></head><body>",
        "<h1>1x Bayer cleanup dashboard</h1>",
        "<p>Review crops use target-derived CFA white balance for display only. Raw metrics are computed on unchanged Bayer values.</p>",
        "<pre>" + html.escape(json.dumps(payload["summary"], indent=2)) + "</pre>",
        "<h2>Full-frame raw metrics</h2>",
        "<table><thead><tr><th>frame</th><th>RMSE %</th><th>MAE %</th><th>PSNR delta</th><th>base RMSE</th><th>candidate RMSE</th></tr></thead><tbody>",
    ]
    for row in rows:
        parts.append(
            f"<tr><td>{html.escape(row['dataset'])}/{html.escape(row['stem'])}</td>"
            f"<td>{row['rmse_improvement_pct']:.3f}</td>"
            f"<td>{row['mae_improvement_pct']:.3f}</td>"
            f"<td>{row['psnr_delta_db']:.4f}</td>"
            f"<td>{row['baseline']['rmse_lsb']:.3f}</td>"
            f"<td>{row['candidate']['rmse_lsb']:.3f}</td></tr>"
        )
    parts.append("</tbody></table><h2>100% crops</h2>")
    for row in rows:
        for crop in ("upper_left", "center", "lower_right"):
            crop_row = crop_rows.get((row["stem"], crop))
            if not crop_row:
                continue
            parts.append(
                f"<div class=row><h3>{html.escape(row['dataset'])}/{html.escape(row['stem'])}:{crop} "
                f"RMSE {row['rmse_improvement_pct']:.3f}% MAE {row['mae_improvement_pct']:.3f}%</h3>"
                "<div class=thumbs>"
            )
            for label, key in (
                ("clean target", "clean_png"),
                ("baseline low", "baseline_png"),
                ("cleanup", "candidate_png"),
                ("baseline diff", "baseline_diff_png"),
                ("cleanup diff", "candidate_diff_png"),
            ):
                rel = Path(crop_row[key]).relative_to(path.parent)
                parts.append(f"<figure><img src='{html.escape(str(rel))}'><figcaption>{label}</figcaption></figure>")
            parts.append("</div></div>")
    parts.append("</body></html>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", type=parse_dataset, required=True)
    parser.add_argument("--stem", action="append", help="Optional stem filter; repeatable.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crop-size", type=int, default=512)
    parser.add_argument("--edge-inset", type=int, default=128)
    parser.add_argument("--diff-gain", type=float, default=8.0)
    parser.add_argument("--tone-low-percentile", type=float, default=0.1)
    parser.add_argument("--tone-high-percentile", type=float, default=99.8)
    parser.add_argument("--no-auto-wb", action="store_true", help="Disable target-derived display white balance for review crops.")
    parser.add_argument("--no-crops", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_dashboard(args)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_html(args.output_dir / "index.html", payload)
    print(json.dumps({"summary": str(summary_path), "dashboard": str(args.output_dir / "index.html")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
