#!/usr/bin/env python3
"""Evaluate a runtime dispatch policy for raw-signal SR candidates.

The model can over-correct low-ISO, low-texture crops where bilinear upsampled
codec raw is already very close to the source Bayer signal. This tool sweeps a
small policy family:

    use model if ISO >= threshold OR decoded high-frequency RMS >= threshold

and reports the best policy against dashboard metrics.
"""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np

from train_codec_raw_clean_sr import RAW_SCALE, upsample_codec


def high_frequency_rms(codec_planes: np.ndarray, target_shape: tuple[int, int]) -> float:
    up = upsample_codec(codec_planes.astype(np.float32) / RAW_SCALE, target_shape) * RAW_SCALE
    pad = np.pad(up, ((0, 0), (1, 1), (1, 1)), mode="edge")
    mean4 = (
        pad[:, 1:-1, :-2]
        + pad[:, 1:-1, 2:]
        + pad[:, :-2, 1:-1]
        + pad[:, 2:, 1:-1]
    ) * 0.25
    return float(np.sqrt(np.mean((up - mean4) ** 2)))


def load_rows(dashboard: Path, pairs: Path) -> list[dict[str, Any]]:
    dash = json.loads(dashboard.read_text())
    z = np.load(pairs, allow_pickle=False)
    rows = []
    for idx, row in enumerate(dash["rows"]):
        rows.append({
            **row,
            "hf_rms_counts": high_frequency_rms(
                z["codec_planes"][idx],
                tuple(z["target_raw_planes"][idx].shape[1:]),
            ),
        })
    return rows


def policy_value(row: dict[str, Any], *, iso_threshold: int, hf_threshold: float) -> tuple[float, bool]:
    use_model = int(row["iso"]) >= iso_threshold or float(row["hf_rms_counts"]) >= hf_threshold
    rmse = float(row["target_rmse_counts"] if use_model else row["baseline_rmse_counts"])
    return rmse, use_model


def summarize(rows: list[dict[str, Any]], iso_threshold: int, hf_threshold: float) -> dict[str, Any]:
    values = []
    selected = []
    regressions = []
    for row in rows:
        rmse, use_model = policy_value(row, iso_threshold=iso_threshold, hf_threshold=hf_threshold)
        selected.append(use_model)
        values.append(rmse)
        if rmse > float(row["baseline_rmse_counts"]):
            regressions.append(row)
    return {
        "iso_threshold": iso_threshold,
        "hf_threshold": hf_threshold,
        "mean_rmse_counts": float(np.mean(values)),
        "max_rmse_counts": float(np.max(values)),
        "model_rows": int(sum(selected)),
        "bypass_rows": int(len(selected) - sum(selected)),
        "regression_rows": len(regressions),
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    rows = load_rows(args.dashboard, args.pairs)
    hf_values = np.asarray([row["hf_rms_counts"] for row in rows], dtype=np.float32)
    hf_thresholds = [0.0]
    hf_thresholds.extend(float(np.percentile(hf_values, pct)) for pct in range(0, 101, 5))
    hf_thresholds.append(float(np.max(hf_values) + 1.0))

    candidates = []
    for iso_threshold in args.iso_thresholds:
        for hf_threshold in hf_thresholds:
            candidates.append(summarize(rows, iso_threshold, hf_threshold))
    candidates.sort(key=lambda row: (row["mean_rmse_counts"], row["max_rmse_counts"], row["regression_rows"]))
    best = candidates[0]

    policy_rows = []
    for row in rows:
        rmse, use_model = policy_value(
            row,
            iso_threshold=int(best["iso_threshold"]),
            hf_threshold=float(best["hf_threshold"]),
        )
        policy_rows.append({
            **row,
            "policy_rmse_counts": rmse,
            "policy_selected": "model" if use_model else "bypass",
            "policy_delta_vs_baseline": rmse - float(row["baseline_rmse_counts"]),
        })

    summary = {
        "dashboard": str(args.dashboard),
        "pairs": str(args.pairs),
        "best_policy": best,
        "model_only": {
            "mean_rmse_counts": float(np.mean([row["target_rmse_counts"] for row in rows])),
            "max_rmse_counts": float(np.max([row["target_rmse_counts"] for row in rows])),
            "regression_rows": int(sum(row["target_rmse_counts"] > row["baseline_rmse_counts"] for row in rows)),
        },
        "bypass_only": {
            "mean_rmse_counts": float(np.mean([row["baseline_rmse_counts"] for row in rows])),
            "max_rmse_counts": float(np.max([row["baseline_rmse_counts"] for row in rows])),
        },
        "rows": policy_rows,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "raw_signal_dispatch_policy.json"
    html_path = args.out_dir / "raw_signal_dispatch_policy.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(summary, html_path)
    return summary


def build_html(summary: dict[str, Any], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.3f}"
        return escape(str(v))

    best = summary["best_policy"]
    html = [
        "<!doctype html><meta charset='utf-8'><title>Raw Signal Dispatch Policy</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.model{background:#eef8ef}.bypass{background:#f4f6f8}.bad{background:#ffe7e7}</style>",
        "<h1>Raw Signal Dispatch Policy</h1>",
        f"<p>Best policy: use model if ISO >= <b>{fmt(best['iso_threshold'])}</b> "
        f"or decoded HF RMS >= <b>{fmt(best['hf_threshold'])}</b> raw counts.</p>",
        "<table><thead><tr><th>Mode</th><th>Mean RMSE</th><th>Max RMSE</th><th>Regressions</th><th>Model rows</th><th>Bypass rows</th></tr></thead><tbody>",
        "<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            "policy",
            best["mean_rmse_counts"],
            best["max_rmse_counts"],
            best["regression_rows"],
            best["model_rows"],
            best["bypass_rows"],
        ]) + "</tr>",
        "<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            "model_only",
            summary["model_only"]["mean_rmse_counts"],
            summary["model_only"]["max_rmse_counts"],
            summary["model_only"]["regression_rows"],
            len(summary["rows"]),
            0,
        ]) + "</tr>",
        "<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            "bypass_only",
            summary["bypass_only"]["mean_rmse_counts"],
            summary["bypass_only"]["max_rmse_counts"],
            "",
            0,
            len(summary["rows"]),
        ]) + "</tr>",
        "</tbody></table>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>HF RMS</th><th>Selected</th><th>Policy RMSE</th><th>Model RMSE</th><th>Baseline RMSE</th><th>Delta vs baseline</th></tr></thead><tbody>",
    ]
    for row in sorted(summary["rows"], key=lambda r: r["policy_rmse_counts"], reverse=True):
        cls = row["policy_selected"]
        if row["policy_delta_vs_baseline"] > 0:
            cls = "bad"
        html.append(f"<tr class='{cls}'>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"],
            row["crop"],
            row["iso"],
            row["hf_rms_counts"],
            row["policy_selected"],
            row["policy_rmse_counts"],
            row["target_rmse_counts"],
            row["baseline_rmse_counts"],
            row["policy_delta_vs_baseline"],
        ]) + "</tr>")
    html.append("</tbody></table>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dashboard", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--iso-thresholds", type=int, nargs="*", default=[0, 100, 200, 500, 1000, 5000, 10000, 20000, 30000])
    args = ap.parse_args()
    summary = build(args)
    print(args.out_dir / "raw_signal_dispatch_policy.json")
    print(args.out_dir / "raw_signal_dispatch_policy.html")
    print(json.dumps(summary["best_policy"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
