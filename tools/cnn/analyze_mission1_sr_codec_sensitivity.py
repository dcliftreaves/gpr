#!/usr/bin/env python3
"""Analyze low-res codec error against Mission 1 SR full-frame gate failures."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.mission1_sr_codec_sensitivity.v1"
DEFAULT_FLOORS = {
    "rmse_improvement_pct": 30.0,
    "mae_improvement_pct": 20.0,
    "gradient_mae_improvement_pct": 8.0,
    "model_psnr14_db": 45.0,
}


def read_raw_u16(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype=np.uint16)
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} samples; expected {expected} for {width}x{height}")
    return arr.reshape((height, width))


def metric_stats(diff: np.ndarray) -> dict[str, float]:
    d = diff.astype(np.float32, copy=False)
    abs_d = np.abs(d)
    return {
        "rmse_counts": float(np.sqrt(np.mean(d * d))),
        "mae_counts": float(np.mean(abs_d)),
        "p95_abs_counts": float(np.percentile(abs_d, 95)),
        "p99_abs_counts": float(np.percentile(abs_d, 99)),
        "max_abs_counts": float(np.max(abs_d)),
        "bias_counts": float(np.mean(d)),
    }


def gradient_mae(a: np.ndarray, b: np.ndarray) -> float:
    af = a.astype(np.float32, copy=False)
    bf = b.astype(np.float32, copy=False)
    if af.shape[0] < 2 or af.shape[1] < 2:
        return 0.0
    ax = af[:, 1:] - af[:, :-1]
    bx = bf[:, 1:] - bf[:, :-1]
    ay = af[1:, :] - af[:-1, :]
    by = bf[1:, :] - bf[:-1, :]
    return float((np.mean(np.abs(ax - bx)) + np.mean(np.abs(ay - by))) * 0.5)


def binomial_lowpass(arr: np.ndarray) -> np.ndarray:
    f = arr.astype(np.float32, copy=False)
    p = np.pad(f, ((1, 1), (1, 1)), mode="edge")
    return (
        p[:-2, :-2]
        + 2.0 * p[:-2, 1:-1]
        + p[:-2, 2:]
        + 2.0 * p[1:-1, :-2]
        + 4.0 * p[1:-1, 1:-1]
        + 2.0 * p[1:-1, 2:]
        + p[2:, :-2]
        + 2.0 * p[2:, 1:-1]
        + p[2:, 2:]
    ) / 16.0


def cfa_planes(arr: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "r": arr[0::2, 0::2],
        "g1": arr[0::2, 1::2],
        "g2": arr[1::2, 0::2],
        "b": arr[1::2, 1::2],
    }


def residual_band(arr: np.ndarray) -> np.ndarray:
    return arr.astype(np.float32, copy=False) - binomial_lowpass(arr)


def read_sr_rows(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("images") or []:
        if isinstance(row, dict) and isinstance(row.get("image"), str):
            rows[row["image"]] = row
    return rows


def gate_deficits(row: dict[str, Any], floors: dict[str, float]) -> dict[str, float]:
    deficits: dict[str, float] = {}
    for key, floor in floors.items():
        value = row.get(key)
        if value is None:
            deficits[key] = math.inf
            continue
        if key == "model_psnr14_db":
            deficits[key] = max(0.0, floor - float(value))
        else:
            deficits[key] = max(0.0, floor - float(value))
    return deficits


def analyze_one(
    *,
    stem: str,
    codec: np.ndarray,
    clean: np.ndarray,
    sr_row: dict[str, Any] | None,
    floors: dict[str, float],
) -> dict[str, Any]:
    diff = codec.astype(np.float32) - clean.astype(np.float32)
    planes: dict[str, Any] = {}
    for name, codec_plane in cfa_planes(codec).items():
        clean_plane = cfa_planes(clean)[name]
        plane_diff = codec_plane.astype(np.float32) - clean_plane.astype(np.float32)
        codec_hf = residual_band(codec_plane)
        clean_hf = residual_band(clean_plane)
        planes[name] = {
            **metric_stats(plane_diff),
            "gradient_mae_counts": gradient_mae(codec_plane, clean_plane),
            "hf_rmse_counts": metric_stats(codec_hf - clean_hf)["rmse_counts"],
            "hf_mae_counts": metric_stats(codec_hf - clean_hf)["mae_counts"],
        }

    sr_metrics = {}
    deficits = {}
    if sr_row:
        sr_metrics = {
            "rmse_improvement_pct": float(sr_row.get("rmse_improvement_pct", 0.0)),
            "mae_improvement_pct": float(sr_row.get("mae_improvement_pct", 0.0)),
            "gradient_mae_improvement_pct": float(sr_row.get("gradient_mae_improvement_pct", 0.0)),
            "model_psnr14_db": float(sr_row.get("model_psnr14_db", 0.0)),
        }
        deficits = gate_deficits(sr_row, floors)

    worst_plane = max(planes.items(), key=lambda item: item[1]["hf_rmse_counts"])[0] if planes else None
    pressure = sum(v for v in deficits.values() if math.isfinite(v))
    return {
        "image": stem,
        "overall": {
            **metric_stats(diff),
            "gradient_mae_counts": gradient_mae(codec, clean),
            "hf_rmse_counts": metric_stats(residual_band(codec) - residual_band(clean))["rmse_counts"],
            "hf_mae_counts": metric_stats(residual_band(codec) - residual_band(clean))["mae_counts"],
        },
        "cfa_planes": planes,
        "worst_hf_plane": worst_plane,
        "sr_metrics": sr_metrics,
        "gate_deficits": deficits,
        "gate_pressure": float(pressure),
        "gate_pass": bool(sr_row is not None and pressure == 0.0),
    }


def html_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "image",
        "gate",
        "pressure",
        "low rmse",
        "low p99",
        "low grad",
        "low hf rmse",
        "worst plane",
        "SR rmse%",
        "SR mae%",
        "SR grad%",
        "PSNR14",
    ]
    lines = [
        "<!doctype html><meta charset='utf-8'><title>Mission 1 SR Codec Sensitivity</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px}"
        "table{border-collapse:collapse;font-size:13px}th,td{border:1px solid #ccc;padding:6px 8px;text-align:right}"
        "th:first-child,td:first-child{text-align:left}.fail{background:#ffe8e0}.pass{background:#e9f8eb}</style>",
        "<h1>Mission 1 SR Codec Sensitivity</h1>",
        "<table><thead><tr>",
        "".join(f"<th>{html.escape(h)}</th>" for h in headers),
        "</tr></thead><tbody>",
    ]
    for row in rows:
        overall = row["overall"]
        sr = row.get("sr_metrics") or {}
        cls = "pass" if row.get("gate_pass") else "fail"
        values = [
            row["image"],
            "pass" if row.get("gate_pass") else "fail",
            f"{row.get('gate_pressure', 0.0):.3f}",
            f"{overall['rmse_counts']:.3f}",
            f"{overall['p99_abs_counts']:.3f}",
            f"{overall['gradient_mae_counts']:.3f}",
            f"{overall['hf_rmse_counts']:.3f}",
            row.get("worst_hf_plane") or "",
            f"{sr.get('rmse_improvement_pct', 0.0):.3f}",
            f"{sr.get('mae_improvement_pct', 0.0):.3f}",
            f"{sr.get('gradient_mae_improvement_pct', 0.0):.3f}",
            f"{sr.get('model_psnr14_db', 0.0):.3f}",
        ]
        lines.append("<tr class='%s'>%s</tr>" % (cls, "".join(f"<td>{html.escape(str(v))}</td>" for v in values)))
    lines.extend(["</tbody></table>"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codec-low-dir", type=Path, required=True)
    parser.add_argument("--clean-low-dir", type=Path, required=True)
    parser.add_argument("--sr-summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=4096)
    parser.add_argument("--height", type=int, default=3072)
    parser.add_argument("--stem", action="append")
    parser.add_argument("--rmse-floor", type=float, default=DEFAULT_FLOORS["rmse_improvement_pct"])
    parser.add_argument("--mae-floor", type=float, default=DEFAULT_FLOORS["mae_improvement_pct"])
    parser.add_argument("--gradient-floor", type=float, default=DEFAULT_FLOORS["gradient_mae_improvement_pct"])
    parser.add_argument("--psnr14-floor", type=float, default=DEFAULT_FLOORS["model_psnr14_db"])
    args = parser.parse_args()

    floors = {
        "rmse_improvement_pct": args.rmse_floor,
        "mae_improvement_pct": args.mae_floor,
        "gradient_mae_improvement_pct": args.gradient_floor,
        "model_psnr14_db": args.psnr14_floor,
    }
    sr_rows = read_sr_rows(args.sr_summary)
    stems = args.stem or sorted({p.stem for p in args.codec_low_dir.glob("*.raw")} & {p.stem for p in args.clean_low_dir.glob("*.raw")})
    if not stems:
        raise SystemExit("no common raw stems found")

    rows = []
    for stem in stems:
        codec_path = args.codec_low_dir / f"{stem}.raw"
        clean_path = args.clean_low_dir / f"{stem}.raw"
        if not codec_path.exists() or not clean_path.exists():
            raise FileNotFoundError(f"missing raw pair for {stem}")
        rows.append(
            analyze_one(
                stem=stem,
                codec=read_raw_u16(codec_path, args.width, args.height),
                clean=read_raw_u16(clean_path, args.width, args.height),
                sr_row=sr_rows.get(stem),
                floors=floors,
            )
        )

    rows.sort(key=lambda row: (not row["gate_pass"], -row["gate_pressure"], -row["overall"]["hf_rmse_counts"], row["image"]))
    summary = {
        "schema": SCHEMA,
        "codec_low_dir": str(args.codec_low_dir),
        "clean_low_dir": str(args.clean_low_dir),
        "sr_summary": str(args.sr_summary),
        "dashboard": str(args.out_dir / "index.html"),
        "dimensions": {"width": args.width, "height": args.height},
        "floors": floors,
        "rows": rows,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.out_dir / "mission1_sr_codec_sensitivity.json"
    html_path = args.out_dir / "index.html"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(html_table(rows), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "dashboard": str(html_path), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
