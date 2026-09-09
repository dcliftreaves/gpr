#!/usr/bin/env python3
"""Compare 4K Bayer candidates against high-res Bayer rendered to 4K RGB.

This evaluates the 4K->4K cleanup/detail problem in the domain users inspect:
RGB after demosaic. The target is built from the high-resolution Bayer frame by
demosaicing at native high resolution and area-downsampling RGB to the decoded
4K geometry. Baseline and candidate are demosaiced from 4K Bayer directly.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import statistics
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


RAW_PEAK = 16383.0
DEMOSAIC_CODES = {
    "rggb": cv2.COLOR_BayerRGGB2RGB_EA,
    "bggr": cv2.COLOR_BayerBGGR2RGB_EA,
    "grbg": cv2.COLOR_BayerGRBG2RGB_EA,
    "gbrg": cv2.COLOR_BayerGBRG2RGB_EA,
}


def read_raw(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected}")
    return arr.reshape((height, width))


def demosaic_rgb(raw: np.ndarray, code: int) -> np.ndarray:
    return cv2.cvtColor(raw, code).astype(np.float32)


def high_target_to_low_rgb(raw_high: np.ndarray, low_width: int, low_height: int, code: int) -> np.ndarray:
    high_rgb = demosaic_rgb(raw_high, code)
    return cv2.resize(high_rgb, (low_width, low_height), interpolation=cv2.INTER_AREA)


def rgb_to_cfa_raw(rgb: np.ndarray, cfa: str) -> np.ndarray:
    if cfa != "rggb":
        raise ValueError("CFA target metrics currently support rggb only")
    out = np.empty(rgb.shape[:2], dtype=np.float32)
    out[0::2, 0::2] = rgb[0::2, 0::2, 0]
    out[0::2, 1::2] = rgb[0::2, 1::2, 1]
    out[1::2, 0::2] = rgb[1::2, 0::2, 1]
    out[1::2, 1::2] = rgb[1::2, 1::2, 2]
    return out


def gamma01(rgb: np.ndarray) -> np.ndarray:
    return np.power(np.clip(rgb / RAW_PEAK, 0.0, 1.0), 1.0 / 2.2)


def y709(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def metrics(candidate: np.ndarray, target: np.ndarray) -> dict[str, float]:
    diff = candidate.astype(np.float32) - target.astype(np.float32)
    absdiff = np.abs(diff)
    mse = float(np.mean(diff * diff))
    ydiff = y709(candidate) - y709(target)
    ymse = float(np.mean(ydiff * ydiff))
    cand_y = y709(candidate)
    target_y = y709(target)
    dx = np.mean(np.abs(np.diff(cand_y, axis=1) - np.diff(target_y, axis=1)))
    dy = np.mean(np.abs(np.diff(cand_y, axis=0) - np.diff(target_y, axis=0)))
    gamma_diff = gamma01(candidate) - gamma01(target)
    gamma_abs = np.abs(gamma_diff)
    gamma_mse = float(np.mean(gamma_diff * gamma_diff))
    return {
        "rgb_rmse_lsb": math.sqrt(mse),
        "rgb_mae_lsb": float(np.mean(absdiff)),
        "rgb_p95_abs_lsb": float(np.percentile(absdiff, 95)),
        "rgb_p99_abs_lsb": float(np.percentile(absdiff, 99)),
        "y_rmse_lsb": math.sqrt(ymse),
        "y_psnr14_db": 99.0 if ymse <= 1e-12 else 20.0 * math.log10(RAW_PEAK) - 10.0 * math.log10(ymse),
        "y_gradient_mae_lsb": float((dx + dy) * 0.5),
        "gamma_rgb_rmse_0_1": math.sqrt(gamma_mse),
        "gamma_rgb_mae_0_1": float(np.mean(gamma_abs)),
        "gamma_rgb_p95_abs_0_1": float(np.percentile(gamma_abs, 95)),
    }


def raw_metrics(candidate: np.ndarray, target: np.ndarray) -> dict[str, float]:
    diff = candidate.astype(np.float32) - target.astype(np.float32)
    absdiff = np.abs(diff)
    mse = float(np.mean(diff * diff))
    return {
        "raw_rmse_lsb": math.sqrt(mse),
        "raw_mae_lsb": float(np.mean(absdiff)),
        "raw_p95_abs_lsb": float(np.percentile(absdiff, 95)),
        "raw_p99_abs_lsb": float(np.percentile(absdiff, 99)),
        "raw_psnr14_db": 99.0 if mse <= 1e-12 else 20.0 * math.log10(RAW_PEAK) - 10.0 * math.log10(mse),
    }


def improvement(base: dict[str, float], candidate: dict[str, float], key: str) -> float:
    before = float(base[key])
    after = float(candidate[key])
    if before == 0.0:
        return 0.0
    return 100.0 * (before - after) / before


def display_gains(target_rgb: np.ndarray) -> np.ndarray:
    sample = target_rgb.reshape(-1, 3).astype(np.float32)
    lo = np.percentile(sample, 5, axis=0)
    hi = np.percentile(sample, 95, axis=0)
    mask = np.all((sample >= lo) & (sample <= hi), axis=1)
    selected = sample[mask] if np.any(mask) else sample
    med = np.maximum(np.median(selected, axis=0), 1.0)
    gray = float(np.mean(med))
    return np.clip(gray / med, 0.25, 4.0).astype(np.float32)


def tone_crop(rgb: np.ndarray, target_rgb: np.ndarray, gains: np.ndarray | None = None) -> np.ndarray:
    if gains is not None:
        rgb = rgb * gains.reshape(1, 1, 3)
        target_rgb = target_rgb * gains.reshape(1, 1, 3)
    lo, hi = np.percentile(target_rgb, [0.2, 99.8])
    out = np.clip((rgb - lo) / max(1.0, hi - lo), 0.0, 1.0)
    out = np.power(out, 1.0 / 2.2)
    return (out * 255.0 + 0.5).astype(np.uint8)


def error_rgb(candidate: np.ndarray, target: np.ndarray, gain: float) -> np.ndarray:
    err = np.abs(candidate.astype(np.float32) - target.astype(np.float32))
    return (np.clip((err / RAW_PEAK) * gain, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)


def crop_boxes(width: int, height: int, size: int, inset: int) -> dict[str, tuple[int, int, int, int]]:
    size = min(size, width, height)
    inset = min(max(0, inset), max(0, min(width, height) - size))
    return {
        "upper_left": (inset, inset, size, size),
        "center": ((width - size) // 2, (height - size) // 2, size, size),
        "lower_right": (width - size - inset, height - size - inset, size, size),
    }


def parse_dataset(value: str) -> dict[str, Any]:
    parts = value.split(":")
    if len(parts) != 8:
        raise argparse.ArgumentTypeError(
            "--dataset expects NAME:LOW_DIR:CANDIDATE_DIR:HIGH_TARGET_DIR:LOW_W:LOW_H:HIGH_W:HIGH_H"
        )
    name, low_dir, candidate_dir, high_target_dir, low_w, low_h, high_w, high_h = parts
    return {
        "name": name,
        "low_dir": Path(low_dir),
        "candidate_dir": Path(candidate_dir),
        "high_target_dir": Path(high_target_dir),
        "low_width": int(low_w),
        "low_height": int(low_h),
        "high_width": int(high_w),
        "high_height": int(high_h),
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
    code = DEMOSAIC_CODES[args.cfa]
    stems_filter = set(args.stem or [])
    rows: list[dict[str, Any]] = []
    crop_rows: list[dict[str, Any]] = []
    crop_dir = args.output_dir / "crops"

    for dataset in args.dataset:
        stems = sorted(path.stem for path in dataset["candidate_dir"].glob("*.raw"))
        for stem in stems:
            if stems_filter and stem not in stems_filter:
                continue
            low_path = dataset["low_dir"] / f"{stem}.raw"
            candidate_path = dataset["candidate_dir"] / f"{stem}.raw"
            target_path = dataset["high_target_dir"] / f"{stem}.raw"
            if not low_path.exists() or not candidate_path.exists() or not target_path.exists():
                continue
            low_raw = read_raw(low_path, dataset["low_width"], dataset["low_height"])
            candidate_raw = read_raw(candidate_path, dataset["low_width"], dataset["low_height"])
            high_raw = read_raw(target_path, dataset["high_width"], dataset["high_height"])
            target_rgb = high_target_to_low_rgb(high_raw, dataset["low_width"], dataset["low_height"], code)
            target_cfa_raw = rgb_to_cfa_raw(target_rgb, args.cfa)
            baseline_rgb = demosaic_rgb(low_raw, code)
            candidate_rgb = demosaic_rgb(candidate_raw, code)
            gains = None if args.no_display_wb else display_gains(target_rgb)

            baseline = metrics(baseline_rgb, target_rgb)
            candidate = metrics(candidate_rgb, target_rgb)
            baseline_cfa = raw_metrics(low_raw, target_cfa_raw)
            candidate_cfa = raw_metrics(candidate_raw, target_cfa_raw)
            row = {
                "dataset": dataset["name"],
                "stem": stem,
                "low_width": dataset["low_width"],
                "low_height": dataset["low_height"],
                "high_target_width": dataset["high_width"],
                "high_target_height": dataset["high_height"],
                "baseline": baseline,
                "candidate": candidate,
                "baseline_cfa_target": baseline_cfa,
                "candidate_cfa_target": candidate_cfa,
                "improvement_pct": {key: improvement(baseline, candidate, key) for key in baseline},
                "cfa_target_improvement_pct": {
                    key: improvement(baseline_cfa, candidate_cfa, key) for key in baseline_cfa
                },
            }
            rows.append(row)

            for crop_name, (x, y, crop_w, crop_h) in crop_boxes(
                dataset["low_width"], dataset["low_height"], args.crop_size, args.edge_inset
            ).items():
                prefix = f"{stem}_{crop_name}"
                box = (slice(y, y + crop_h), slice(x, x + crop_w))
                paths = {
                    "target_png": crop_dir / f"{prefix}_target_rgb4_from_high.png",
                    "baseline_png": crop_dir / f"{prefix}_baseline_rgb4.png",
                    "candidate_png": crop_dir / f"{prefix}_candidate_rgb4.png",
                    "baseline_error_png": crop_dir / f"{prefix}_baseline_err_x{args.error_gain:g}.png",
                    "candidate_error_png": crop_dir / f"{prefix}_candidate_err_x{args.error_gain:g}.png",
                }
                save_png(paths["target_png"], tone_crop(target_rgb[box], target_rgb[box], gains))
                save_png(paths["baseline_png"], tone_crop(baseline_rgb[box], target_rgb[box], gains))
                save_png(paths["candidate_png"], tone_crop(candidate_rgb[box], target_rgb[box], gains))
                save_png(paths["baseline_error_png"], error_rgb(baseline_rgb[box], target_rgb[box], args.error_gain))
                save_png(paths["candidate_error_png"], error_rgb(candidate_rgb[box], target_rgb[box], args.error_gain))
                crop_rows.append(
                    {
                        "dataset": dataset["name"],
                        "stem": stem,
                        "crop": crop_name,
                        "box": [x, y, crop_w, crop_h],
                        **{key: str(value) for key, value in paths.items()},
                    }
                )

    summary: dict[str, Any] = {
        "count": len(rows),
        "rgb_rmse_improvement_pct": summarize([row["improvement_pct"]["rgb_rmse_lsb"] for row in rows]),
        "rgb_mae_improvement_pct": summarize([row["improvement_pct"]["rgb_mae_lsb"] for row in rows]),
        "gamma_rgb_rmse_improvement_pct": summarize([row["improvement_pct"]["gamma_rgb_rmse_0_1"] for row in rows]),
        "gamma_rgb_mae_improvement_pct": summarize([row["improvement_pct"]["gamma_rgb_mae_0_1"] for row in rows]),
        "y_gradient_improvement_pct": summarize([row["improvement_pct"]["y_gradient_mae_lsb"] for row in rows]),
        "y_psnr_delta_db": summarize([row["candidate"]["y_psnr14_db"] - row["baseline"]["y_psnr14_db"] for row in rows]),
        "cfa_raw_rmse_improvement_pct": summarize(
            [row["cfa_target_improvement_pct"]["raw_rmse_lsb"] for row in rows]
        ),
        "cfa_raw_mae_improvement_pct": summarize(
            [row["cfa_target_improvement_pct"]["raw_mae_lsb"] for row in rows]
        ),
        "cfa_raw_psnr_delta_db": summarize(
            [row["candidate_cfa_target"]["raw_psnr14_db"] - row["baseline_cfa_target"]["raw_psnr14_db"] for row in rows]
        ),
    }
    return {
        "schema": "gpr.4k_rgb_downsampled_high_target_dashboard.v1",
        "source_policy": (
            "target=demosaic high-res Bayer to RGB then area-downsample RGB to 4K; "
            "baseline/candidate=demosaic 4K Bayer directly; cfa_target metrics sample the same RGB target back onto RGGB sites"
        ),
        "display_policy": "crop PNGs use target gray-world white balance for review only; metrics use unbalanced linear RGB",
        "cfa": args.cfa,
        "demosaic": "OpenCV edge-aware Bayer demosaic",
        "datasets": [
            {
                "name": item["name"],
                "low_dir": str(item["low_dir"]),
                "candidate_dir": str(item["candidate_dir"]),
                "high_target_dir": str(item["high_target_dir"]),
                "low_width": item["low_width"],
                "low_height": item["low_height"],
                "high_width": item["high_width"],
                "high_height": item["high_height"],
            }
            for item in args.dataset
        ],
        "summary": summary,
        "rows": rows,
        "crop_rows": crop_rows,
    }


def rel(path: str | Path, base: Path) -> str:
    try:
        return Path(path).resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def write_html(path: Path, payload: dict[str, Any]) -> None:
    rows = sorted(payload["rows"], key=lambda row: row["improvement_pct"]["gamma_rgb_rmse_0_1"])
    crop_rows = {(row["stem"], row["crop"]): row for row in payload["crop_rows"]}
    css = """
    body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#1f2328;background:#fff}
    h1{font-size:24px;margin:0 0 8px} h2{font-size:18px;margin:28px 0 12px}
    pre{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:12px;overflow:auto}
    table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #d8dee4;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}
    .row{border-top:1px solid #d8dee4;padding-top:16px;margin-top:16px}
    .thumbs{display:grid;grid-template-columns:repeat(5,max-content);gap:10px;overflow-x:auto}
    figure{margin:0}figcaption{font-size:12px;color:#57606a;margin-top:4px}
    img{width:512px;height:512px;object-fit:cover;border:1px solid #d0d7de}
    """
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(payload['schema'])}</title><style>{css}</style></head><body>",
        "<h1>4K RGB target from high-res RGB downsample</h1>",
        "<pre>" + html.escape(json.dumps({k: v for k, v in payload.items() if k not in ('rows', 'crop_rows')}, indent=2)) + "</pre>",
        "<h2>Full-frame metrics</h2>",
        "<table><thead><tr><th>frame</th><th>RGB RMSE %</th><th>gamma RMSE %</th><th>RGB MAE %</th><th>Y grad %</th><th>Y PSNR delta</th><th>CFA RMSE %</th><th>CFA PSNR delta</th><th>base RGB RMSE</th><th>candidate RGB RMSE</th></tr></thead><tbody>",
    ]
    for row in rows:
        psnr_delta = row["candidate"]["y_psnr14_db"] - row["baseline"]["y_psnr14_db"]
        cfa_psnr_delta = row["candidate_cfa_target"]["raw_psnr14_db"] - row["baseline_cfa_target"]["raw_psnr14_db"]
        parts.append(
            f"<tr><td>{html.escape(row['dataset'] + '/' + row['stem'])}</td>"
            f"<td>{row['improvement_pct']['rgb_rmse_lsb']:.4f}</td>"
            f"<td>{row['improvement_pct']['gamma_rgb_rmse_0_1']:.4f}</td>"
            f"<td>{row['improvement_pct']['rgb_mae_lsb']:.4f}</td>"
            f"<td>{row['improvement_pct']['y_gradient_mae_lsb']:.4f}</td>"
            f"<td>{psnr_delta:.5f}</td>"
            f"<td>{row['cfa_target_improvement_pct']['raw_rmse_lsb']:.4f}</td>"
            f"<td>{cfa_psnr_delta:.5f}</td>"
            f"<td>{row['baseline']['rgb_rmse_lsb']:.3f}</td>"
            f"<td>{row['candidate']['rgb_rmse_lsb']:.3f}</td></tr>"
        )
    parts.append("</tbody></table><h2>100% crops</h2>")
    for row in rows:
        for crop in ("upper_left", "center", "lower_right"):
            crop_row = crop_rows.get((row["stem"], crop))
            if not crop_row:
                continue
            parts.append(f"<div class=row><h3>{html.escape(row['dataset'] + '/' + row['stem'] + ':' + crop)}</h3><div class=thumbs>")
            for label, key in [
                ("Target: high RGB to 4K", "target_png"),
                ("Baseline 4K demosaic", "baseline_png"),
                ("Candidate 4K demosaic", "candidate_png"),
                ("Baseline error", "baseline_error_png"),
                ("Candidate error", "candidate_error_png"),
            ]:
                parts.append(
                    f"<figure><img src='{html.escape(rel(crop_row[key], path.parent))}'>"
                    f"<figcaption>{html.escape(label)}</figcaption></figure>"
                )
            parts.append("</div></div>")
    parts.append("</body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", action="append", required=True, type=parse_dataset)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--stem", action="append", help="limit to a stem; repeatable")
    ap.add_argument("--cfa", choices=sorted(DEMOSAIC_CODES), default="rggb")
    ap.add_argument("--crop-size", type=int, default=768)
    ap.add_argument("--edge-inset", type=int, default=128)
    ap.add_argument("--error-gain", type=float, default=8.0)
    ap.add_argument("--no-display-wb", action="store_true", help="disable target gray-world WB for PNG review crops")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_dashboard(args)
    (args.output_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_html(args.output_dir / "index.html", payload)
    print(json.dumps({"summary": str(args.output_dir / "summary.json"), "dashboard": str(args.output_dir / "index.html")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
