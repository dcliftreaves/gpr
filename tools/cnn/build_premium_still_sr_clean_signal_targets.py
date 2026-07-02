#!/usr/bin/env python3
"""Build clean-signal raw-CFA residual targets for premium still-SR.

The legacy premium still-SR raw target is source-minus-candidate high-frequency
raw CFA. Recent audits showed that objective mixes structure with camera noise
strongly enough that larger CNNs chase the wrong target. This builder produces a
trainer-compatible target set where per-plane residuals are confidence-gated by
calibrated camera noise sidecars. Source raw is used only to build the training
target; render-time code must use candidate/raw metadata plus a validated noise
model, never the source residual itself.
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


SCHEMA = "gpr.premium_still_sr_clean_signal_targets.v1"


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
        "mean": float(arr.mean()),
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
    empty = {
        "available": False,
        "path": path,
        "iso": 0.0,
        "white_level": 65535.0,
        "black_level": 0.0,
        "sigma4_norm": [0.0, 0.0, 0.0, 0.0],
        "p95_4_norm": [0.0, 0.0, 0.0, 0.0],
        "fpn4_norm": [0.0, 0.0, 0.0, 0.0],
    }
    if not path:
        return empty
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
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


def clean_signal(
    target: np.ndarray,
    threshold4: np.ndarray,
    ramp_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    threshold = threshold4.reshape((1, 1, 4)).astype(np.float32)
    abs_target = np.abs(target)
    denom = np.maximum(threshold * max(float(ramp_width), 1.0e-6), 1.0e-12)
    confidence = np.clip((abs_target - threshold) / denom, 0.0, 1.0).astype(np.float32)
    return (target * confidence).astype(np.float32), confidence


def row_metrics(
    idx: int,
    row: dict[str, Any],
    raw_target: np.ndarray,
    clean_target: np.ndarray,
    confidence: np.ndarray,
    threshold4: np.ndarray,
    noise: dict[str, Any],
) -> dict[str, Any]:
    raw_abs = np.abs(raw_target)
    clean_abs = np.abs(clean_target)
    raw_energy = float(np.mean(raw_target * raw_target))
    clean_energy = float(np.mean(clean_target * clean_target))
    clean_abs_mean = float(np.mean(clean_abs))
    raw_abs_mean = float(np.mean(raw_abs))
    retained_energy = clean_energy / max(raw_energy, 1.0e-18)
    retained_abs = clean_abs_mean / max(raw_abs_mean, 1.0e-18)
    active_fraction = float(np.mean(confidence > 0.0))
    full_conf_fraction = float(np.mean(confidence >= 0.999))
    sigma4 = np.asarray(noise["sigma4_norm"], dtype=np.float64)
    p95_4 = np.asarray(noise["p95_4_norm"], dtype=np.float64)
    raw_rmse = float(np.sqrt(raw_energy))
    raw_p95 = float(np.percentile(raw_abs, 95.0))
    sigma_mean = float(np.mean(sigma4))
    p95_mean = float(np.mean(p95_4))
    if not noise.get("available"):
        classification = "missing_noise_sidecar"
    elif retained_energy <= 0.05 and active_fraction <= 0.05:
        classification = "suppressed_noise_floor"
    elif retained_energy >= 0.50 or active_fraction >= 0.20:
        classification = "retained_signal"
    else:
        classification = "mixed_signal_noise"
    return {
        "row_index": idx,
        "scene_id": row.get("scene_id"),
        "crop": row.get("crop"),
        "camera": camera_from_row(row),
        "iso": float(noise.get("iso", 0.0) or 0.0),
        "noise_sidecar": noise.get("path", ""),
        "noise_available": bool(noise.get("available")),
        "threshold4_norm": [float(v) for v in threshold4.tolist()],
        "raw_target_abs_mean": raw_abs_mean,
        "clean_target_abs_mean": clean_abs_mean,
        "raw_target_rmse": raw_rmse,
        "clean_target_rmse": float(np.sqrt(clean_energy)),
        "raw_target_p95_abs": raw_p95,
        "active_pixel_fraction": active_fraction,
        "full_confidence_pixel_fraction": full_conf_fraction,
        "target_abs_retained_fraction": retained_abs,
        "target_energy_retained_fraction": retained_energy,
        "target_rmse_to_noise_sigma": raw_rmse / max(sigma_mean, 1.0e-12) if sigma_mean > 0.0 else 0.0,
        "target_p95_to_noise_p95": raw_p95 / max(p95_mean, 1.0e-12) if p95_mean > 0.0 else 0.0,
        "classification": classification,
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
                "target_energy_retained_fraction": stats(
                    [float(row["target_energy_retained_fraction"]) for row in group]
                ),
                "active_pixel_fraction": stats([float(row["active_pixel_fraction"]) for row in group]),
                "clean_target_abs_mean": stats([float(row["clean_target_abs_mean"]) for row in group]),
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
        f"<td>{row['target_energy_retained_fraction']:.3f}</td>"
        f"<td>{100.0 * row['active_pixel_fraction']:.2f}%</td>"
        f"<td>{row['clean_target_abs_mean']:.7f}</td>"
        f"<td>{html.escape(str(row.get('classification')))}</td>"
        "</tr>"
        for row in receipt["rows"][:180]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Clean-Signal Targets</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #131820; background: #f7f8fa; }}
main {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 920px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dde3e9; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3e9; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Clean-Signal Targets</h1>
<p class="sub">Builds a trainer-compatible raw-CFA target after calibrated per-plane noise confidence gating. This is the next objective before another expensive still-SR CNN pass; exact source residual/noise is forbidden at render time.</p>
<div class="grid">
  <section class="card"><div class="label">Rows</div><div class="value">{receipt['summary']['row_count']}</div></section>
  <section class="card"><div class="label">Noise sidecars</div><div class="value">{receipt['summary']['rows_with_noise_sidecars']}</div></section>
  <section class="card"><div class="label">Median energy retained</div><div class="value">{receipt['summary']['target_energy_retained_fraction']['median']:.3f}</div></section>
  <section class="card"><div class="label">Median active pixels</div><div class="value">{100.0 * receipt['summary']['active_pixel_fraction']['median']:.2f}%</div></section>
</div>
<h2>Interpretation</h2>
<p>{html.escape(receipt['interpretation'])}</p>
<h2>Rows</h2>
<table><tr><th>row</th><th>camera</th><th>scene</th><th>crop</th><th>ISO</th><th>energy retained</th><th>active</th><th>clean abs mean</th><th>class</th></tr>{rows}</table>
<p>Clean target NPZ: <code>{html.escape(receipt['artifacts']['clean_targets_npz'])}</code></p>
<p>JSON receipt: <code>{html.escape(receipt['artifacts']['receipt'])}</code></p>
</main></body></html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    z = np.load(args.targets, allow_pickle=False)
    rows_meta = load_meta(z)
    raw_target = z["raw_hf_residual_cfa4"].astype(np.float32)
    candidate_hf = z["candidate_raw_hf_cfa4"].astype(np.float32)
    if len(rows_meta) != raw_target.shape[0]:
        raise ValueError(f"meta row count {len(rows_meta)} does not match target rows {raw_target.shape[0]}")

    clean_target = np.zeros_like(raw_target, dtype=np.float32)
    confidence_out = np.zeros_like(raw_target, dtype=np.float16) if args.write_confidence else None
    sidecar_cache: dict[str, dict[str, Any]] = {}
    output_meta: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []

    for idx, row in enumerate(rows_meta):
        sidecar = sidecar_path(row)
        if sidecar not in sidecar_cache:
            sidecar_cache[sidecar] = noise_from_sidecar(sidecar)
        noise = sidecar_cache[sidecar]
        sigma4 = np.asarray(noise["sigma4_norm"], dtype=np.float32)
        p95_4 = np.asarray(noise["p95_4_norm"], dtype=np.float32)
        fpn4 = np.asarray(noise["fpn4_norm"], dtype=np.float32)
        if noise.get("available"):
            threshold4 = np.maximum.reduce(
                [
                    sigma4 * float(args.sigma_scale),
                    p95_4 * float(args.p95_scale),
                    fpn4 * float(args.fpn_scale),
                    np.full((4,), float(args.min_threshold), dtype=np.float32),
                ]
            ).astype(np.float32)
        else:
            threshold4 = np.full((4,), float(args.missing_sidecar_threshold), dtype=np.float32)

        row_clean, confidence = clean_signal(raw_target[idx], threshold4, args.ramp_width)
        clean_target[idx] = row_clean
        if confidence_out is not None:
            confidence_out[idx] = confidence.astype(np.float16)

        row_out = dict(row)
        row_out["clean_signal_target"] = {
            "schema": SCHEMA,
            "source_target_kind": row.get("raw_target_kind", "source_minus_candidate_raw_hf_residual"),
            "target_kind": "calibrated_noise_confidence_gated_raw_hf_residual",
            "noise_sidecar": str(noise.get("path", "")),
            "noise_available": bool(noise.get("available")),
            "threshold4_norm": [float(v) for v in threshold4.tolist()],
            "sigma_scale": float(args.sigma_scale),
            "p95_scale": float(args.p95_scale),
            "fpn_scale": float(args.fpn_scale),
            "ramp_width": float(args.ramp_width),
            "uses_source_raw_at_training_target": True,
            "uses_source_raw_at_runtime": False,
            "exact_source_noise_addback_allowed_at_runtime": False,
        }
        output_meta.append(row_out)
        metric_rows.append(row_metrics(idx, row, raw_target[idx], row_clean, confidence, threshold4, noise))

    rows_with_noise = sum(1 for row in metric_rows if row["noise_available"])
    class_counts = dict(Counter(str(row["classification"]) for row in metric_rows))
    summary = {
        "row_count": len(metric_rows),
        "rows_with_noise_sidecars": rows_with_noise,
        "raw_target_abs_mean": stats([float(row["raw_target_abs_mean"]) for row in metric_rows]),
        "clean_target_abs_mean": stats([float(row["clean_target_abs_mean"]) for row in metric_rows]),
        "target_energy_retained_fraction": stats(
            [float(row["target_energy_retained_fraction"]) for row in metric_rows]
        ),
        "target_abs_retained_fraction": stats([float(row["target_abs_retained_fraction"]) for row in metric_rows]),
        "active_pixel_fraction": stats([float(row["active_pixel_fraction"]) for row in metric_rows]),
        "target_rmse_to_noise_sigma": stats(
            [float(row["target_rmse_to_noise_sigma"]) for row in metric_rows if row["noise_available"]]
        ),
        "target_p95_to_noise_p95": stats(
            [float(row["target_p95_to_noise_p95"]) for row in metric_rows if row["noise_available"]]
        ),
        "classification_counts": class_counts,
    }
    if rows_with_noise < len(metric_rows):
        interpretation = (
            "Some rows are missing calibrated noise sidecars, so this target is not ready for promotion until those rows are either calibrated or excluded."
        )
    elif summary["target_energy_retained_fraction"]["median"] <= 0.01:
        interpretation = (
            "The calibrated clean-signal gate suppresses nearly all residual energy. Do not train a larger CNN on this source-minus-candidate target; build a different teacher or target."
        )
    elif summary["active_pixel_fraction"]["median"] <= 0.05:
        interpretation = (
            "The clean target keeps sparse residual structure. A focused still-SR pass can train against this target, but promotion must prove holdout learnability and visual latitude."
        )
    else:
        interpretation = (
            "The clean target retains enough above-noise structure to justify a bounded CNN pass, with calibrated synthetic/noise-sidecar addback handled separately at render time."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = args.output_dir / "clean_signal_targets.npz"
    receipt_path = args.output_dir / "clean_signal_targets.json"
    dashboard_path = args.output_dir / "index.html"
    arrays: dict[str, Any] = {
        "candidate_raw_cfa4": z["candidate_raw_cfa4"],
        "candidate_raw_hf_cfa4": z["candidate_raw_hf_cfa4"],
        "raw_hf_residual_cfa4": clean_target.astype(np.float16),
        "source_raw_hf_cfa4": (candidate_hf + clean_target).astype(np.float16),
        "meta": np.asarray(json.dumps(output_meta, sort_keys=True)),
    }
    for key in ("render_hf_residual_y", "source_raw_cfa4", "raw_residual_cfa4"):
        if key in z.files:
            arrays[key] = z[key]
    if confidence_out is not None:
        arrays["clean_signal_confidence_cfa4"] = confidence_out
    np.savez_compressed(npz_path, **arrays)

    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_targets": str(args.targets),
        "source_targets_sha256": sha256_file(args.targets),
        "clean_targets_sha256": sha256_file(npz_path),
        "parameters": {
            "sigma_scale": float(args.sigma_scale),
            "p95_scale": float(args.p95_scale),
            "fpn_scale": float(args.fpn_scale),
            "ramp_width": float(args.ramp_width),
            "min_threshold": float(args.min_threshold),
            "missing_sidecar_threshold": float(args.missing_sidecar_threshold),
            "write_confidence": bool(args.write_confidence),
        },
        "policy": {
            "uses_source_raw_at_training_target": True,
            "uses_source_raw_at_runtime": False,
            "uses_ref_or_jpeg_content_at_runtime": False,
            "exact_source_noise_addback_allowed_at_runtime": False,
            "runtime_addback_policy": "validated camera noise sidecar or future synthetic noise model only",
            "trainer_compatibility": "raw_hf_residual_cfa4 is replaced with calibrated clean-signal residual; source_raw_hf_cfa4 is candidate_raw_hf_cfa4 plus that clean target",
        },
        "summary": summary,
        "by_camera": grouped(metric_rows, "camera"),
        "by_scene": grouped(metric_rows, "scene_id"),
        "rows": metric_rows,
        "interpretation": interpretation,
        "artifacts": {
            "clean_targets_npz": str(npz_path),
            "receipt": str(receipt_path),
            "dashboard": str(dashboard_path),
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dashboard_path.write_text(render_html(receipt), encoding="utf-8")
    print(dashboard_path)
    return receipt


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--sigma-scale", type=float, default=2.0)
    ap.add_argument("--p95-scale", type=float, default=0.5)
    ap.add_argument("--fpn-scale", type=float, default=1.0)
    ap.add_argument("--ramp-width", type=float, default=1.0)
    ap.add_argument("--min-threshold", type=float, default=0.0)
    ap.add_argument("--missing-sidecar-threshold", type=float, default=1.0)
    ap.add_argument("--write-confidence", action="store_true")
    return ap.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
