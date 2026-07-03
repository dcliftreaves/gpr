#!/usr/bin/env python3
"""Audit whether candidate high-frequency CFA predicts still-SR residuals.

This is a pre-training diagnostic for Premium still/SR. It evaluates simple
candidate-only transforms of candidate_raw_hf_cfa4 against raw_hf_residual_cfa4.
If scalar candidate-HF transforms cannot improve the target rows, the next
production candidate should change target/supervision construction rather than
spending more training time on stored-HF feature variants or scalar output
tuning.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_candidate_hf_feature_audit.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_TARGETS = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate17_replacement_targets_20260702/gate17_replacement_targets.npz"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "artifacts/premium_still_sr_candidate_hf_feature_audit_20260703"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def row_class(row: dict[str, Any]) -> str:
    explicit = str(row.get("class") or row.get("camera_class") or "").lower()
    if "100" in explicit:
        return "100mp"
    if "50" in explicit:
        return "50mp"
    camera_key = str(row.get("camera_key") or row.get("domain") or row.get("camera") or "").lower()
    if "x2d" in camera_key or "100" in camera_key:
        return "100mp"
    if "z8" in camera_key or "mission" in camera_key or "gopro" in camera_key or "50" in camera_key:
        return "50mp"
    return "unknown"


def parse_alphas(text: str) -> list[float]:
    alphas = sorted({float(part) for part in text.replace(",", " ").split()})
    if not alphas:
        raise ValueError("at least one alpha is required")
    return alphas


def load_rows(npz: Any) -> list[dict[str, Any]]:
    meta = npz["meta"].item()
    rows = json.loads(meta) if isinstance(meta, str) else meta
    if not isinstance(rows, list):
        raise ValueError("target NPZ meta must contain a row list")
    return [dict(row) for row in rows]


def summarize(rows: list[dict[str, Any]], alpha: float) -> dict[str, Any]:
    selected = [row for row in rows if abs(float(row["alpha"]) - alpha) < 1.0e-12]
    by_class: dict[str, Any] = {}
    for cls in sorted({str(row["class"]) for row in selected}):
        cls_rows = [row for row in selected if str(row["class"]) == cls]
        by_class[cls] = {
            "row_count": len(cls_rows),
            "mae_reduction_pct": stats([float(row["mae_reduction_pct"]) for row in cls_rows]),
            "rmse_reduction_pct": stats([float(row["rmse_reduction_pct"]) for row in cls_rows]),
        }
    return {
        "alpha": alpha,
        "row_count": len(selected),
        "mae_reduction_pct": stats([float(row["mae_reduction_pct"]) for row in selected]),
        "rmse_reduction_pct": stats([float(row["rmse_reduction_pct"]) for row in selected]),
        "by_class": by_class,
    }


def score(summary: dict[str, Any]) -> float:
    base = float(summary["mae_reduction_pct"]["median"] or -1.0e9)
    for cls in ("50mp", "100mp"):
        cls_summary = summary.get("by_class", {}).get(cls)
        if not cls_summary:
            return -1.0e9
        base += float(cls_summary["mae_reduction_pct"]["median"] or -1.0e9)
        base += float(cls_summary["rmse_reduction_pct"]["median"] or -1.0e9)
        if cls_summary["mae_reduction_pct"]["min"] is not None:
            base += float(cls_summary["mae_reduction_pct"]["min"])
    return base


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    alphas = parse_alphas(args.alphas)
    npz = np.load(args.targets, allow_pickle=True)
    rows = load_rows(npz)
    target = npz["raw_hf_residual_cfa4"]
    candidate_hf = npz["candidate_raw_hf_cfa4"]
    if len(rows) != int(target.shape[0]) or target.shape != candidate_hf.shape:
        raise ValueError("target rows and candidate/target arrays do not match")

    eval_rows: list[dict[str, Any]] = []
    indices = list(range(len(rows)))
    if args.max_rows > 0:
        indices = indices[: args.max_rows]
    for idx in indices:
        row = rows[idx]
        cls = row_class(row)
        target_row = target[idx].astype(np.float32, copy=False)
        hf_row = candidate_hf[idx].astype(np.float32, copy=False)
        base_mae = float(np.mean(np.abs(target_row)))
        base_rmse = float(np.sqrt(np.mean(target_row * target_row)))
        for alpha in alphas:
            err = float(alpha) * hf_row - target_row
            pred_mae = float(np.mean(np.abs(err)))
            pred_rmse = float(np.sqrt(np.mean(err * err)))
            eval_rows.append(
                {
                    "alpha": float(alpha),
                    "index": idx,
                    "class": cls,
                    "scene_id": row.get("scene_id"),
                    "crop": row.get("crop"),
                    "baseline_mae": base_mae,
                    "model_mae": pred_mae,
                    "baseline_rmse": base_rmse,
                    "model_rmse": pred_rmse,
                    "mae_reduction_pct": 100.0 * (base_mae - pred_mae) / max(base_mae, 1.0e-12),
                    "rmse_reduction_pct": 100.0 * (base_rmse - pred_rmse) / max(base_rmse, 1.0e-12),
                }
            )
    summaries = [summarize(eval_rows, alpha) for alpha in alphas]
    best = max(summaries, key=score)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_ready": False,
        "inputs": {
            "targets": str(args.targets),
            "targets_sha256": sha256_file(args.targets),
        },
        "runtime_policy": {
            "candidate_only_feature_probe": True,
            "forbidden_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "JPG", "gate_metrics"],
        },
        "coverage": {
            "target_row_count": len(indices),
            "classes": {cls: sum(1 for idx in indices if row_class(rows[idx]) == cls) for cls in sorted({row_class(rows[idx]) for idx in indices})},
        },
        "alpha_summaries": summaries,
        "best_alpha_summary": best,
        "timing": {
            "eval_seconds": time.perf_counter() - started,
            "target_rows_per_second": len(indices) / max(time.perf_counter() - started, 1.0e-12),
        },
        "next_decision": (
            "candidate_hf_feature_has_scalar_signal"
            if float(best["mae_reduction_pct"]["median"] or 0.0) >= 1.0
            else "candidate_hf_feature_not_predictive_change_supervision"
        ),
    }


def render_html(receipt: dict[str, Any]) -> str:
    rows = []
    for summary in receipt["alpha_summaries"]:
        rows.append(
            "<tr>"
            f"<td>{float(summary['alpha']):.3f}</td>"
            f"<td>{float(summary['mae_reduction_pct']['median'] or 0.0):.3f}%</td>"
            f"<td>{float(summary['rmse_reduction_pct']['median'] or 0.0):.3f}%</td>"
            f"<td>{float(summary['mae_reduction_pct']['min'] or 0.0):.3f}%</td>"
            "</tr>"
        )
    best = receipt["best_alpha_summary"]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Candidate-HF Feature Audit</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;line-height:1.45;color:#18202a}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d9dee7;padding:8px;text-align:left}}th{{background:#f4f6f9}}
code{{background:#f4f6f9;padding:2px 4px;border-radius:4px}}
</style>
<h1>Premium Still-SR Candidate-HF Feature Audit</h1>
<p>Best alpha: <code>{float(best["alpha"]):.3f}</code>, median MAE recovery <code>{float(best["mae_reduction_pct"]["median"] or 0.0):.3f}%</code>.</p>
<p>Decision: <code>{html.escape(receipt["next_decision"])}</code></p>
<table><tr><th>alpha</th><th>median MAE recovery</th><th>median RMSE recovery</th><th>worst MAE recovery</th></tr>{''.join(rows)}</table>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--alphas", default="-2 -1 -0.75 -0.5 -0.25 -0.1 -0.05 -0.025 0 0.025 0.05 0.1 0.25 0.5 0.75 1 2")
    ap.add_argument("--max-rows", type=int, default=0)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = run_audit(args)
    receipt_path = args.output_dir / "candidate_hf_feature_audit.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "dashboard": str(html_path),
                "best_alpha": receipt["best_alpha_summary"]["alpha"],
                "next_decision": receipt["next_decision"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
