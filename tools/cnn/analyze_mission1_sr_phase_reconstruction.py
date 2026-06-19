#!/usr/bin/env python3
"""Analyze same-color Bayer detail phase preservation before Mission 1 SR.

The SR hard rows can fail even when low-res codec RMSE is small. This diagnostic
looks at whether the codec-decoded 12MP Bayer preserves the sign and placement
of clean-low same-color detail. It consumes SR pair sidecars so it can use the
exact low_source_raw and low_clean_raw frames used by training/evaluation.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.mission1_sr_phase_reconstruction.v1"
PLANES = ("r", "g1", "g2", "b")
DEFAULT_FLOORS = {
    "rmse_improvement_pct": 30.0,
    "mae_improvement_pct": 20.0,
    "gradient_mae_improvement_pct": 8.0,
    "model_psnr14_db": 45.0,
}


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def read_raw(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} samples, expected {expected}")
    return arr.reshape((height, width))


def planes(raw: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "r": raw[0::2, 0::2],
        "g1": raw[0::2, 1::2],
        "g2": raw[1::2, 0::2],
        "b": raw[1::2, 1::2],
    }


def binomial_lowpass(arr: np.ndarray) -> np.ndarray:
    f = arr.astype(np.float32, copy=False)
    p = np.pad(f, ((1, 1), (1, 1)), mode="reflect")
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
    ) * (1.0 / 16.0)


def detail(arr: np.ndarray) -> np.ndarray:
    return arr.astype(np.float32, copy=False) - binomial_lowpass(arr)


def rmse(diff: np.ndarray) -> float:
    d = diff.astype(np.float32, copy=False)
    return float(np.sqrt(np.mean(d * d)))


def mae(diff: np.ndarray) -> float:
    return float(np.mean(np.abs(diff.astype(np.float32, copy=False))))


def percentile_abs(diff: np.ndarray, pct: float) -> float:
    return float(np.percentile(np.abs(diff.astype(np.float32, copy=False)), pct))


def normalized_dot(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    if not np.any(mask):
        return 0.0
    av = a[mask].astype(np.float64, copy=False)
    bv = b[mask].astype(np.float64, copy=False)
    denom = math.sqrt(float(np.dot(av, av)) * float(np.dot(bv, bv)))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(av, bv) / denom)


def gradient_mae(a: np.ndarray, b: np.ndarray) -> float:
    af = a.astype(np.float32, copy=False)
    bf = b.astype(np.float32, copy=False)
    dx = np.mean(np.abs((af[:, 1:] - af[:, :-1]) - (bf[:, 1:] - bf[:, :-1])))
    dy = np.mean(np.abs((af[1:, :] - af[:-1, :]) - (bf[1:, :] - bf[:-1, :])))
    return float((dx + dy) * 0.5)


def sr_rows(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = read_json(path)
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("images") or []:
        if isinstance(row, dict) and row.get("image") is not None:
            rows[str(row["image"])] = row
    return rows


def gate_deficits(row: dict[str, Any] | None, floors: dict[str, float]) -> dict[str, float]:
    if row is None:
        return {}
    out: dict[str, float] = {}
    for key, floor in floors.items():
        out[key] = max(0.0, floor - float(row.get(key, 0.0)))
    return out


def collect_image_specs(sidecar: dict[str, Any], stems: set[str] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    default_width = int(sidecar.get("width12", 0) or 0)
    default_height = int(sidecar.get("height12", 0) or 0)
    for image in sidecar.get("images") or []:
        if not isinstance(image, dict):
            continue
        image_id = str(image.get("image_id") or "")
        if not image_id or (stems and image_id not in stems):
            continue
        low_source = image.get("low_source_raw")
        low_clean = image.get("low_clean_raw")
        if not low_source or not low_clean:
            continue
        width = int(image.get("low_width") or default_width)
        height = int(image.get("low_height") or default_height)
        if (width <= 0 or height <= 0) and image_id.startswith("GP"):
            width, height = 4096, 3072
        if (width <= 0 or height <= 0) and image_id.startswith("Z8"):
            width, height = 4140, 2760
        if width <= 0 or height <= 0:
            raise ValueError(f"{image_id} lacks low_width/low_height")
        rows.append(
            {
                "image": image_id,
                "low_source_raw": str(low_source),
                "low_clean_raw": str(low_clean),
                "width": width,
                "height": height,
            }
        )
    if stems:
        missing = sorted(stems - {row["image"] for row in rows})
        if missing:
            raise ValueError(f"missing stems in sidecar: {', '.join(missing)}")
    return rows


def analyze_plane(codec: np.ndarray, clean: np.ndarray, threshold: float) -> dict[str, float]:
    codec_d = detail(codec)
    clean_d = detail(clean)
    residual = codec_d - clean_d
    mask = np.abs(clean_d) >= threshold
    sign_mismatch = np.logical_and(mask, np.sign(codec_d) != np.sign(clean_d))
    clean_energy = float(np.sum(np.abs(clean_d[mask]))) if np.any(mask) else 0.0
    mismatch_energy = float(np.sum(np.abs(clean_d[sign_mismatch]))) if np.any(sign_mismatch) else 0.0
    clean_std = float(np.std(clean_d[mask])) if np.any(mask) else 0.0
    codec_std = float(np.std(codec_d[mask])) if np.any(mask) else 0.0
    corr = normalized_dot(codec_d, clean_d, mask)
    sign_pct = 100.0 * float(np.mean(sign_mismatch[mask])) if np.any(mask) else 0.0
    flip_energy_pct = 100.0 * mismatch_energy / clean_energy if clean_energy > 0.0 else 0.0
    return {
        "low_rmse_counts": rmse(codec.astype(np.float32) - clean.astype(np.float32)),
        "low_mae_counts": mae(codec.astype(np.float32) - clean.astype(np.float32)),
        "low_p99_abs_counts": percentile_abs(codec.astype(np.float32) - clean.astype(np.float32), 99),
        "gradient_mae_counts": gradient_mae(codec, clean),
        "detail_rmse_counts": rmse(residual),
        "detail_mae_counts": mae(residual),
        "detail_p99_abs_counts": percentile_abs(residual, 99),
        "detail_corr": corr,
        "detail_sign_mismatch_pct": sign_pct,
        "detail_flip_energy_pct": flip_energy_pct,
        "detail_energy_ratio": codec_std / clean_std if clean_std > 0.0 else 0.0,
        "significant_detail_pct": 100.0 * float(np.mean(mask)),
        "phase_error_score": (1.0 - corr) * 100.0 + sign_pct + 0.25 * flip_energy_pct,
    }


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "max": 0.0, "mean": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def analyze_image(spec: dict[str, Any], sr_row: dict[str, Any] | None, floors: dict[str, float], threshold: float) -> dict[str, Any]:
    codec = read_raw(Path(spec["low_source_raw"]), int(spec["width"]), int(spec["height"]))
    clean = read_raw(Path(spec["low_clean_raw"]), int(spec["width"]), int(spec["height"]))
    codec_planes = planes(codec)
    clean_planes = planes(clean)
    plane_rows = {
        name: analyze_plane(codec_planes[name], clean_planes[name], threshold)
        for name in PLANES
    }
    worst_phase_plane = max(plane_rows, key=lambda name: plane_rows[name]["phase_error_score"])
    worst_detail_plane = max(plane_rows, key=lambda name: plane_rows[name]["detail_rmse_counts"])
    deficits = gate_deficits(sr_row, floors)
    pressure = float(sum(deficits.values()))
    return {
        **spec,
        "sr_metrics": {
            key: float(sr_row[key])
            for key in DEFAULT_FLOORS
            if sr_row is not None and key in sr_row
        },
        "gate_deficits": deficits,
        "gate_pressure": pressure,
        "gate_pass": bool(sr_row is not None and pressure == 0.0),
        "planes": plane_rows,
        "worst_phase_plane": worst_phase_plane,
        "worst_detail_plane": worst_detail_plane,
        "phase_error_score": float(plane_rows[worst_phase_plane]["phase_error_score"]),
        "detail_rmse_counts": float(max(row["detail_rmse_counts"] for row in plane_rows.values())),
        "detail_corr_min": float(min(row["detail_corr"] for row in plane_rows.values())),
        "sign_mismatch_max_pct": float(max(row["detail_sign_mismatch_pct"] for row in plane_rows.values())),
    }


def correlation(rows: list[dict[str, Any]], x_key: str, y_key: str) -> float:
    if len(rows) < 2:
        return 0.0
    x = np.asarray([float(row[x_key]) for row in rows], dtype=np.float64)
    y = np.asarray([float(row[y_key]) for row in rows], dtype=np.float64)
    if float(np.std(x)) == 0.0 or float(np.std(y)) == 0.0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def build_summary(
    *,
    pair_sidecar: Path,
    sr_summary: Path | None,
    rows: list[dict[str, Any]],
    floors: dict[str, float],
    threshold: float,
    out_dir: Path,
) -> dict[str, Any]:
    failing = [row for row in rows if not row["gate_pass"]]
    passing = [row for row in rows if row["gate_pass"]]
    def group_stats(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "image_count": len(group),
            "phase_error_score": summarize([row["phase_error_score"] for row in group]),
            "detail_rmse_counts": summarize([row["detail_rmse_counts"] for row in group]),
            "detail_corr_min": summarize([row["detail_corr_min"] for row in group]),
            "sign_mismatch_max_pct": summarize([row["sign_mismatch_max_pct"] for row in group]),
        }
    decision = "codec_phase_likely_blocker"
    reason = "failing rows have stronger phase/detail reconstruction errors than passing rows"
    if passing and failing:
        fail_phase = np.median([row["phase_error_score"] for row in failing])
        pass_phase = np.median([row["phase_error_score"] for row in passing])
        fail_detail = np.median([row["detail_rmse_counts"] for row in failing])
        pass_detail = np.median([row["detail_rmse_counts"] for row in passing])
        phase_worse = fail_phase > pass_phase * 1.05
        detail_worse = fail_detail > pass_detail * 1.05
        if phase_worse and detail_worse:
            decision = "codec_phase_likely_blocker"
            reason = "failing rows have stronger low-frame phase and detail reconstruction errors than passing rows"
        elif phase_worse:
            decision = "codec_phase_mixed_signal"
            reason = "failing rows have worse low-frame phase scores, but not worse detail residual amplitude"
        elif detail_worse:
            decision = "codec_detail_mixed_signal"
            reason = "failing rows have worse low-frame detail residual amplitude, but not worse phase scores"
        else:
            decision = "sr_objective_or_capacity_likely_blocker"
            reason = "failing rows do not have worse low-frame phase/detail reconstruction than passing rows"
    elif not passing:
        decision = "no_passing_rows_for_contrast"
        reason = "all analyzed rows fail the supplied SR gate, so use per-row/plane rankings instead of pass-fail contrast"
    return {
        "schema": SCHEMA,
        "pair_sidecar": str(pair_sidecar),
        "sr_summary": str(sr_summary) if sr_summary else None,
        "dashboard": str(out_dir / "index.html"),
        "floors": floors,
        "significant_detail_threshold_counts": threshold,
        "image_count": len(rows),
        "decision": decision,
        "reason": reason,
        "correlations": {
            "gate_pressure_vs_phase_error": correlation(rows, "gate_pressure", "phase_error_score"),
            "gate_pressure_vs_detail_rmse": correlation(rows, "gate_pressure", "detail_rmse_counts"),
            "gate_pressure_vs_sign_mismatch": correlation(rows, "gate_pressure", "sign_mismatch_max_pct"),
        },
        "groups": {
            "passing": group_stats(passing),
            "failing": group_stats(failing),
        },
        "worst_by_phase_error": sorted(rows, key=lambda row: row["phase_error_score"], reverse=True)[:5],
        "worst_by_gate_pressure": sorted(rows, key=lambda row: row["gate_pressure"], reverse=True)[:5],
        "images": rows,
    }


def write_dashboard(out_dir: Path, summary: dict[str, Any]) -> None:
    rows = sorted(summary["images"], key=lambda row: (row["gate_pass"], -row["gate_pressure"], -row["phase_error_score"]))
    head = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Mission 1 SR Phase Reconstruction</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#17201b;background:#f7f8f6}
table{border-collapse:collapse;font-size:13px;width:100%;background:white}
th,td{border:1px solid #d4d8d2;padding:6px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}.fail{background:#fff0ea}.pass{background:#edf8ef}
.wrap{overflow-x:auto}.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:16px 0}
.metric{background:white;border:1px solid #d4d8d2;padding:10px}.metric span{display:block;color:#607066;font-size:12px}.metric strong{font-size:20px}
</style></head><body>
"""
    metrics = f"""
<h1>Mission 1 SR Phase Reconstruction</h1>
<p>{html.escape(summary['reason'])}</p>
<section class="summary">
<div class="metric"><span>Decision</span><strong>{html.escape(summary['decision'])}</strong></div>
<div class="metric"><span>Images</span><strong>{summary['image_count']}</strong></div>
<div class="metric"><span>Gate/phase corr</span><strong>{summary['correlations']['gate_pressure_vs_phase_error']:.3f}</strong></div>
<div class="metric"><span>Gate/detail corr</span><strong>{summary['correlations']['gate_pressure_vs_detail_rmse']:.3f}</strong></div>
</section>
"""
    columns = [
        "image",
        "gate",
        "pressure",
        "phase score",
        "worst phase plane",
        "detail rmse",
        "min corr",
        "max sign mismatch",
        "SR rmse%",
        "SR mae%",
        "SR grad%",
        "PSNR14",
    ]
    body = ["<div class='wrap'><table><thead><tr>"]
    body.append("".join(f"<th>{html.escape(col)}</th>" for col in columns))
    body.append("</tr></thead><tbody>")
    for row in rows:
        sr = row.get("sr_metrics") or {}
        values = [
            row["image"],
            "pass" if row["gate_pass"] else "fail",
            f"{row['gate_pressure']:.3f}",
            f"{row['phase_error_score']:.3f}",
            row["worst_phase_plane"],
            f"{row['detail_rmse_counts']:.3f}",
            f"{row['detail_corr_min']:.3f}",
            f"{row['sign_mismatch_max_pct']:.2f}%",
            f"{sr.get('rmse_improvement_pct', 0.0):.3f}",
            f"{sr.get('mae_improvement_pct', 0.0):.3f}",
            f"{sr.get('gradient_mae_improvement_pct', 0.0):.3f}",
            f"{sr.get('model_psnr14_db', 0.0):.3f}",
        ]
        cls = "pass" if row["gate_pass"] else "fail"
        body.append("<tr class='%s'>%s</tr>" % (cls, "".join(f"<td>{html.escape(str(v))}</td>" for v in values)))
    body.append("</tbody></table></div></body></html>")
    (out_dir / "index.html").write_text(head + metrics + "\n".join(body), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair-sidecar", type=Path, required=True)
    ap.add_argument("--sr-summary", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--stem", action="append")
    ap.add_argument("--significant-detail-threshold", type=float, default=2.0)
    ap.add_argument("--rmse-floor", type=float, default=DEFAULT_FLOORS["rmse_improvement_pct"])
    ap.add_argument("--mae-floor", type=float, default=DEFAULT_FLOORS["mae_improvement_pct"])
    ap.add_argument("--gradient-floor", type=float, default=DEFAULT_FLOORS["gradient_mae_improvement_pct"])
    ap.add_argument("--psnr14-floor", type=float, default=DEFAULT_FLOORS["model_psnr14_db"])
    args = ap.parse_args()

    floors = {
        "rmse_improvement_pct": args.rmse_floor,
        "mae_improvement_pct": args.mae_floor,
        "gradient_mae_improvement_pct": args.gradient_floor,
        "model_psnr14_db": args.psnr14_floor,
    }
    stems = set(args.stem or []) or None
    sidecar = read_json(args.pair_sidecar)
    rows_by_sr = sr_rows(args.sr_summary)
    image_specs = collect_image_specs(sidecar, stems)
    rows = [
        analyze_image(spec, rows_by_sr.get(spec["image"]), floors, args.significant_detail_threshold)
        for spec in image_specs
    ]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(
        pair_sidecar=args.pair_sidecar,
        sr_summary=args.sr_summary,
        rows=rows,
        floors=floors,
        threshold=args.significant_detail_threshold,
        out_dir=args.out_dir,
    )
    (args.out_dir / "mission1_sr_phase_reconstruction.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_dashboard(args.out_dir, summary)
    print(json.dumps({"summary": str(args.out_dir / "mission1_sr_phase_reconstruction.json"), "decision": summary["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
