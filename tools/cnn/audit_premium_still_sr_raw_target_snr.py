#!/usr/bin/env python3
"""Audit raw-CFA residual target SNR against camera noise sidecars.

This is a target/objective diagnostic for premium still-SR. It does not train a
model. It answers whether the source-minus-candidate raw residual target is
above calibrated sensor-noise scale, near the noise floor, or missing calibrated
noise evidence. That distinction decides whether the next still-SR pass should
learn signal, build a denoised target first, or collect better darkframes.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_raw_target_snr_audit.v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "max": float(arr.max()),
    }


def camera_from_row(row: dict[str, Any]) -> str:
    scene = str(row.get("scene_id") or "").lower()
    source = str(row.get("source_dng") or row.get("candidate_raw") or row.get("candidate_dng") or "").lower()
    if "x2d" in scene or "x2d" in source or "austin" in scene:
        return "x2d"
    if "z8" in scene or "z8" in source:
        return "z8"
    if "mission" in scene or "gopro" in source or "gp0" in scene:
        return "mission1"
    return "unknown"


def load_meta(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list):
        raise ValueError("target meta must be a JSON list")
    return [row if isinstance(row, dict) else {} for row in rows]


def sidecar_path(row: dict[str, Any]) -> str:
    sidecars = row.get("noise_sidecars", [])
    if isinstance(sidecars, list) and sidecars:
        return str(sidecars[0])
    if isinstance(sidecars, str):
        return sidecars
    return ""


def noise_from_sidecar(path: str) -> dict[str, Any]:
    if not path:
        return {
            "available": False,
            "path": "",
            "iso": 0.0,
            "white_level": 65535.0,
            "black_level": 0.0,
            "sigma4_norm": [0.0, 0.0, 0.0, 0.0],
            "p95_4_norm": [0.0, 0.0, 0.0, 0.0],
            "fpn4_norm": [0.0, 0.0, 0.0, 0.0],
        }
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "available": False,
            "path": path,
            "iso": 0.0,
            "white_level": 65535.0,
            "black_level": 0.0,
            "sigma4_norm": [0.0, 0.0, 0.0, 0.0],
            "p95_4_norm": [0.0, 0.0, 0.0, 0.0],
            "fpn4_norm": [0.0, 0.0, 0.0, 0.0],
        }
    camera = payload.get("camera", {}) if isinstance(payload, dict) else {}
    white = float(camera.get("white_level", 65535.0) or 65535.0)
    black = float(camera.get("black_level", 0.0) or 0.0)
    scale = max(white - black, 1.0)
    calibrations = payload.get("calibrations", []) if isinstance(payload, dict) else []
    cal = calibrations[0] if calibrations and isinstance(calibrations[0], dict) else {}
    per_plane = cal.get("per_plane", {}) if isinstance(cal, dict) else {}
    fallback = [v for v in per_plane.values() if isinstance(v, dict)]

    def values_for(key: str) -> list[float]:
        vals: list[float] = []
        for plane in ("r", "g1", "g2", "b"):
            payload_plane = per_plane.get(plane, {}) if isinstance(per_plane, dict) else {}
            if isinstance(payload_plane, dict) and key in payload_plane:
                vals.append(float(payload_plane.get(key, 0.0) or 0.0) / scale)
        if len(vals) == 4:
            return vals
        fallback_vals = [float(v.get(key, 0.0) or 0.0) / scale for v in fallback]
        mean = float(sum(fallback_vals) / len(fallback_vals)) if fallback_vals else 0.0
        return [mean, mean, mean, mean]

    return {
        "available": bool(fallback),
        "path": path,
        "iso": float(cal.get("iso", 0.0) or 0.0),
        "white_level": white,
        "black_level": black,
        "sigma4_norm": values_for("sigma_black"),
        "p95_4_norm": values_for("temporal_noise_p95_counts"),
        "fpn4_norm": values_for("spatial_fpn_rms_counts"),
    }


def classify_row(target_rmse: float, target_p95: float, sigma_mean: float, p95_mean: float) -> str:
    if sigma_mean <= 0.0 and p95_mean <= 0.0:
        return "missing_noise_sidecar"
    rmse_ratio = target_rmse / max(sigma_mean, 1.0e-12) if sigma_mean > 0.0 else float("inf")
    p95_ratio = target_p95 / max(p95_mean, 1.0e-12) if p95_mean > 0.0 else rmse_ratio
    if rmse_ratio >= 3.0 and p95_ratio >= 2.0:
        return "signal_dominated"
    if rmse_ratio <= 1.5 and p95_ratio <= 1.5:
        return "noise_floor"
    return "mixed_signal_noise"


def row_metrics(
    idx: int,
    row: dict[str, Any],
    target: np.ndarray,
    candidate_hf: np.ndarray | None,
    source_hf: np.ndarray | None,
    sidecar_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    t = target[idx].astype(np.float32, copy=False)
    abs_t = np.abs(t)
    sidecar = sidecar_path(row)
    if sidecar not in sidecar_cache:
        sidecar_cache[sidecar] = noise_from_sidecar(sidecar)
    noise = sidecar_cache[sidecar]
    sigma4 = np.asarray(noise["sigma4_norm"], dtype=np.float64)
    p95_4 = np.asarray(noise["p95_4_norm"], dtype=np.float64)
    sigma_mean = float(np.mean(sigma4))
    p95_mean = float(np.mean(p95_4))
    target_rmse = float(np.sqrt(np.mean(t * t)))
    target_mae = float(np.mean(abs_t))
    target_p95 = float(np.percentile(abs_t, 95.0))
    target_p99 = float(np.percentile(abs_t, 99.0))
    candidate_hf_mae = float(np.mean(np.abs(candidate_hf[idx].astype(np.float32)))) if candidate_hf is not None else 0.0
    source_hf_mae = float(np.mean(np.abs(source_hf[idx].astype(np.float32)))) if source_hf is not None else 0.0
    row_class = classify_row(target_rmse, target_p95, sigma_mean, p95_mean)
    return {
        "row_index": idx,
        "scene_id": row.get("scene_id"),
        "crop": row.get("crop"),
        "camera": camera_from_row(row),
        "iso": float(noise.get("iso", 0.0) or 0.0),
        "noise_sidecar": sidecar,
        "noise_available": bool(noise.get("available")),
        "target_abs_mean": target_mae,
        "target_rmse": target_rmse,
        "target_p95_abs": target_p95,
        "target_p99_abs": target_p99,
        "noise_sigma_mean_norm": sigma_mean,
        "noise_p95_mean_norm": p95_mean,
        "target_rmse_to_noise_sigma": target_rmse / max(sigma_mean, 1.0e-12) if sigma_mean > 0.0 else 0.0,
        "target_p95_to_noise_p95": target_p95 / max(p95_mean, 1.0e-12) if p95_mean > 0.0 else 0.0,
        "target_abs_to_candidate_hf_abs": target_mae / max(candidate_hf_mae, 1.0e-12),
        "target_abs_to_source_hf_abs": target_mae / max(source_hf_mae, 1.0e-12),
        "classification": row_class,
    }


def grouped(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key))].append(row)
    out: list[dict[str, Any]] = []
    for value, group in sorted(buckets.items()):
        out.append(
            {
                key: value,
                "row_count": len(group),
                "target_rmse_to_noise_sigma": stats([float(row["target_rmse_to_noise_sigma"]) for row in group]),
                "target_p95_to_noise_p95": stats([float(row["target_p95_to_noise_p95"]) for row in group]),
                "target_abs_mean": stats([float(row["target_abs_mean"]) for row in group]),
                "classifications": dict(Counter(str(row["classification"]) for row in group)),
            }
        )
    return out


def render_html(receipt: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{int(row['row_index'])}</td>"
        f"<td>{html.escape(str(row.get('camera')))}</td>"
        f"<td>{html.escape(str(row.get('scene_id')))}</td>"
        f"<td>{html.escape(str(row.get('crop')))}</td>"
        f"<td>{html.escape(str(row.get('iso')))}</td>"
        f"<td>{row['target_rmse_to_noise_sigma']:.2f}x</td>"
        f"<td>{row['target_p95_to_noise_p95']:.2f}x</td>"
        f"<td>{row['target_abs_to_candidate_hf_abs']:.4f}</td>"
        f"<td>{html.escape(str(row.get('classification')))}</td>"
        "</tr>"
        for row in receipt["rows"][:160]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Raw Target SNR Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #131820; background: #f7f8fa; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dde3e9; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3e9; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Raw Target SNR Audit</h1>
<p class="sub">Compares source-minus-candidate raw-CFA residual targets with calibrated camera noise sidecars. It does not train a model and does not use source raw at runtime; it is a target/objective diagnostic.</p>
<div class="grid">
  <section class="card"><div class="label">Rows</div><div class="value">{receipt['summary']['row_count']}</div></section>
  <section class="card"><div class="label">Rows with noise sidecars</div><div class="value">{receipt['summary']['rows_with_noise_sidecars']}</div></section>
  <section class="card"><div class="label">Median target RMSE / noise sigma</div><div class="value">{receipt['summary']['target_rmse_to_noise_sigma']['median']:.2f}x</div></section>
  <section class="card"><div class="label">Median target p95 / noise p95</div><div class="value">{receipt['summary']['target_p95_to_noise_p95']['median']:.2f}x</div></section>
</div>
<h2>Interpretation</h2>
<p>{html.escape(receipt['interpretation'])}</p>
<h2>Rows</h2>
<table><tr><th>row</th><th>camera</th><th>scene</th><th>crop</th><th>ISO</th><th>RMSE/sigma</th><th>p95/noise p95</th><th>target/candidate HF</th><th>class</th></tr>{rows}</table>
<p>JSON receipt: <code>{html.escape(receipt['artifacts']['receipt'])}</code></p>
</main></body></html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    z = np.load(args.targets, allow_pickle=False)
    rows_meta = load_meta(z)
    target = z["raw_hf_residual_cfa4"].astype(np.float32)
    candidate_hf = z["candidate_raw_hf_cfa4"].astype(np.float32) if "candidate_raw_hf_cfa4" in z.files else None
    source_hf = z["source_raw_hf_cfa4"].astype(np.float32) if "source_raw_hf_cfa4" in z.files else None
    sidecar_cache: dict[str, dict[str, Any]] = {}
    rows = [
        row_metrics(idx, row, target, candidate_hf, source_hf, sidecar_cache)
        for idx, row in enumerate(rows_meta)
    ]
    rows_with_noise = sum(1 for row in rows if row["noise_available"])
    class_counts = dict(Counter(str(row["classification"]) for row in rows))
    summary = {
        "row_count": len(rows),
        "rows_with_noise_sidecars": rows_with_noise,
        "target_abs_mean": stats([float(row["target_abs_mean"]) for row in rows]),
        "target_rmse": stats([float(row["target_rmse"]) for row in rows]),
        "target_p95_abs": stats([float(row["target_p95_abs"]) for row in rows]),
        "target_rmse_to_noise_sigma": stats([float(row["target_rmse_to_noise_sigma"]) for row in rows if row["noise_available"]]),
        "target_p95_to_noise_p95": stats([float(row["target_p95_to_noise_p95"]) for row in rows if row["noise_available"]]),
        "target_abs_to_candidate_hf_abs": stats([float(row["target_abs_to_candidate_hf_abs"]) for row in rows]),
        "classification_counts": class_counts,
    }
    signal_rows = int(class_counts.get("signal_dominated", 0))
    noise_rows = int(class_counts.get("noise_floor", 0))
    if rows_with_noise == 0:
        interpretation = "No calibrated noise sidecars were available, so target SNR cannot be used to choose the next objective."
    elif signal_rows >= max(1, int(0.75 * rows_with_noise)):
        interpretation = (
            "Most calibrated rows are above the camera-noise floor. The next premium still-SR pass should treat the raw-CFA residual as signal-dominated "
            "and focus on stronger teacher/objective construction, not broad noise removal."
        )
    elif noise_rows >= max(1, int(0.5 * rows_with_noise)):
        interpretation = (
            "A large share of calibrated rows is near the camera-noise floor. Build a denoised/uncertainty-weighted target before training a larger teacher."
        )
    else:
        interpretation = (
            "The target is mixed signal/noise by calibrated SNR. The next teacher should use noise-aware loss weighting or row filtering rather than a single unweighted residual objective."
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output_dir / "raw_target_snr_audit.json"
    dashboard_path = args.output_dir / "index.html"
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "targets": str(args.targets),
        "targets_sha256": sha256_file(args.targets),
        "policy": {
            "uses_source_raw_at_training_target": True,
            "uses_source_raw_at_runtime": False,
            "uses_ref_or_jpeg_content_at_runtime": False,
            "diagnostic_only": True,
            "classification_rule": "signal_dominated if target_rmse/noise_sigma >= 3 and target_p95/noise_p95 >= 2; noise_floor if both <= 1.5",
        },
        "summary": summary,
        "by_camera": grouped(rows, "camera"),
        "by_scene": grouped(rows, "scene_id"),
        "rows": rows,
        "interpretation": interpretation,
        "artifacts": {
            "receipt": str(receipt_path),
            "dashboard": str(dashboard_path),
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    dashboard_path.write_text(render_html(receipt), encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    receipt = run(args)
    print(receipt["artifacts"]["dashboard"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
