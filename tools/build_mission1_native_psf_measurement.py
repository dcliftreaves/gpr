#!/usr/bin/env python3
"""Measure native Mission 1 high/low PSF evidence from selected raw pairs.

This executes the measurement plan, but keeps the result separate from
production promotion. Near-time high/low stills can prove the tooling and can
reject weak calibration pairs; they are not automatically a production native
PSF model.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_native_psf_measurement.v1"
HIGH_SHAPE = (6144, 8192)
LOW_SHAPE = (3072, 4096)
RAW_SCALE = 16383.0


def import_numpy():
    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError:
        print("build_mission1_native_psf_measurement: missing numpy", file=sys.stderr)
        return None
    return np


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256_file(path), "exists": path.exists()}


def write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact_ref(path)


def read_raw(np: Any, path: Path, shape: tuple[int, int]) -> Any:
    expected = shape[0] * shape[1] * 2
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != expected:
        raise ValueError(f"{path} has {path.stat().st_size} bytes, expected {expected}")
    return np.memmap(path, dtype=np.uint16, mode="r", shape=shape)


def block_mean2(np: Any, a: Any) -> Any:
    h = (a.shape[0] // 2) * 2
    w = (a.shape[1] // 2) * 2
    return a[:h, :w].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3)).astype(np.float32)


def block_mean(np: Any, a: Any, scale: int) -> Any:
    h = (a.shape[0] // scale) * scale
    w = (a.shape[1] // scale) * scale
    return a[:h, :w].reshape(h // scale, scale, w // scale, scale).mean(axis=(1, 3)).astype(np.float32)


def gradient_proxy(np: Any, a: Any, scale: int) -> Any:
    s = block_mean(np, a, scale)
    gx = np.zeros_like(s, dtype=np.float32)
    gy = np.zeros_like(s, dtype=np.float32)
    gx[:, 1:-1] = s[:, 2:] - s[:, :-2]
    gy[1:-1, :] = s[2:, :] - s[:-2, :]
    g = np.sqrt(gx * gx + gy * gy)
    return ((g - g.mean()) / (g.std() + 1.0e-6)).astype(np.float32)


def phase_shift(np: Any, source: Any, target: Any) -> tuple[int, int, float]:
    fa = np.fft.rfft2(source)
    fb = np.fft.rfft2(target)
    cross = fb * np.conj(fa)
    cross /= np.maximum(np.abs(cross), 1.0e-9)
    corr = np.fft.irfft2(cross, s=source.shape)
    y, x = np.unravel_index(int(np.argmax(corr)), corr.shape)
    if x > source.shape[1] // 2:
        x -= source.shape[1]
    if y > source.shape[0] // 2:
        y -= source.shape[0]
    response = float(corr.max() / (np.sqrt(np.mean(corr * corr)) + 1.0e-9))
    return int(x), int(y), response


def crop_params(sx: int, sy: int, low_shape: tuple[int, int]) -> dict[str, int]:
    y0 = max(0, sy)
    yh0 = max(0, -sy)
    x0 = max(0, sx)
    xh0 = max(0, -sx)
    h = min(low_shape[0] - y0, low_shape[0] - yh0)
    w = min(low_shape[1] - x0, low_shape[1] - xh0)
    y0 = (y0 // 2) * 2
    x0 = (x0 // 2) * 2
    yh0 = (yh0 // 2) * 2
    xh0 = (xh0 // 2) * 2
    h = (h // 2) * 2
    w = (w // 2) * 2
    return {"low_y": y0, "low_x": x0, "high_low_y": yh0, "high_low_x": xh0, "height": h, "width": w}


def aligned_corr(np: Any, low: Any, high_low: Any, crop: dict[str, int], sample_step: int) -> float:
    y0, x0, yh0, xh0 = crop["low_y"], crop["low_x"], crop["high_low_y"], crop["high_low_x"]
    h, w = crop["height"], crop["width"]
    lo = np.asarray(low[y0 : y0 + h : sample_step, x0 : x0 + w : sample_step], dtype=np.float32)
    hi = np.asarray(high_low[yh0 : yh0 + h : sample_step, xh0 : xh0 + w : sample_step], dtype=np.float32)
    lo = (lo - lo.mean()) / (lo.std() + 1.0e-6)
    hi = (hi - hi.mean()) / (hi.std() + 1.0e-6)
    return float(np.mean(lo * hi))


def robust_line(np: Any, x: Any, y: Any) -> dict[str, float]:
    xx = x.reshape(-1).astype(np.float64)
    yy = y.reshape(-1).astype(np.float64)
    if xx.size > 200000:
        idx = np.linspace(0, xx.size - 1, 200000).astype(np.int64)
        xx = xx[idx]
        yy = yy[idx]
    a = np.stack([xx, np.ones_like(xx)], axis=1)
    gain, offset = np.linalg.lstsq(a, yy, rcond=None)[0]
    pred = gain * xx + offset
    diff = pred - yy
    return {
        "gain": float(gain),
        "offset": float(offset),
        "rmse_14bit": float(np.sqrt(np.mean(diff * diff))),
        "mae_14bit": float(np.mean(np.abs(diff))),
    }


def tile_counts(np: Any, low: Any, crop: dict[str, int], tile: int, stride: int) -> dict[str, Any]:
    y0, x0 = crop["low_y"], crop["low_x"]
    h, w = crop["height"], crop["width"]
    edge = 0
    texture = 0
    total = 0
    edge_scores = []
    texture_scores = []
    for y in range(y0, y0 + h - tile + 1, stride):
        for x in range(x0, x0 + w - tile + 1, stride):
            t = np.asarray(low[y : y + tile, x : x + tile], dtype=np.float32)
            gx = np.abs(t[:, 1:] - t[:, :-1])
            gy = np.abs(t[1:, :] - t[:-1, :])
            grad = np.concatenate([gx.reshape(-1), gy.reshape(-1)])
            p99 = float(np.percentile(grad, 99))
            std = float(np.std(t))
            edge_scores.append(p99)
            texture_scores.append(std)
            if p99 >= max(64.0, std * 0.35):
                edge += 1
            if std >= 48.0 and float(np.percentile(grad, 95)) >= 8.0:
                texture += 1
            total += 1
    return {
        "tile_size_raw_px": tile,
        "stride_raw_px": stride,
        "total_tiles": total,
        "sharp_edge_tile_count": edge,
        "texture_field_tile_count": texture,
        "edge_p99_median": float(np.median(np.asarray(edge_scores))) if edge_scores else 0.0,
        "texture_std_median": float(np.median(np.asarray(texture_scores))) if texture_scores else 0.0,
    }


def bayer_plane_fit(np: Any, low: Any, high: Any, crop: dict[str, int], max_samples: int) -> dict[str, Any]:
    y0, x0, yh0, xh0 = crop["low_y"], crop["low_x"], crop["high_low_y"], crop["high_low_x"]
    h, w = crop["height"], crop["width"]
    rows = []
    ys = []
    plane_rows = []
    for py in (0, 1):
        for px in (0, 1):
            high_py = (y0 + py) % 2
            high_px = (x0 + px) % 2
            low_plane = np.asarray(low[y0 + py : y0 + h : 2, x0 + px : x0 + w : 2], dtype=np.float32)
            high_plane = np.asarray(
                high[2 * yh0 + high_py : 2 * (yh0 + h) : 2, 2 * xh0 + high_px : 2 * (xh0 + w) : 2],
                dtype=np.float32,
            )
            cells = np.stack(
                [
                    high_plane[0::2, 0::2],
                    high_plane[0::2, 1::2],
                    high_plane[1::2, 0::2],
                    high_plane[1::2, 1::2],
                ],
                axis=-1,
            )
            mh = min(low_plane.shape[0], cells.shape[0])
            mw = min(low_plane.shape[1], cells.shape[1])
            low_plane = low_plane[:mh, :mw]
            cells = cells[:mh, :mw]
            stride = max(1, int(math.sqrt((mh * mw * 4) / max(max_samples, 1))))
            a = cells[::stride, ::stride].reshape(-1, 4)
            y = low_plane[::stride, ::stride].reshape(-1)
            mask = (y > 16.0) & (y < RAW_SCALE)
            a = a[mask]
            y = y[mask]
            rows.append(a)
            ys.append(y)
            plane_rows.append({"plane": f"{py}{px}", "sample_count": int(y.shape[0]), "stride": int(stride)})

    a_all = np.concatenate(rows, axis=0).astype(np.float64)
    y_all = np.concatenate(ys, axis=0).astype(np.float64)
    if a_all.shape[0] > max_samples:
        idx = np.linspace(0, a_all.shape[0] - 1, max_samples).astype(np.int64)
        a_all = a_all[idx]
        y_all = y_all[idx]
    x_all = np.concatenate([a_all, np.ones((a_all.shape[0], 1), dtype=np.float64)], axis=1)
    coef, residuals, rank, singular_values = np.linalg.lstsq(x_all, y_all, rcond=None)
    weights = coef[:4]
    intercept = float(coef[4])
    pred = x_all @ coef
    diff = pred - y_all
    weight_sum = float(np.sum(weights))
    norm = weights / weight_sum if abs(weight_sum) > 1.0e-9 else weights
    box = np.full(4, 0.25, dtype=np.float64)
    has_negative = bool(np.any(norm < -0.05))
    active = np.abs(norm) >= 0.01
    cols = np.asarray([0, 1, 0, 1])
    rows_idx = np.asarray([0, 0, 1, 1])
    return {
        "sample_count": int(a_all.shape[0]),
        "plane_sample_rows": plane_rows,
        "weights": [float(x) for x in weights],
        "normalized_weights": [float(x) for x in norm],
        "weight_sum_gain": weight_sum,
        "intercept": intercept,
        "rank": int(rank),
        "singular_values": [float(x) for x in singular_values],
        "rmse_14bit": float(np.sqrt(np.mean(diff * diff))),
        "mae_14bit": float(np.mean(np.abs(diff))),
        "normalized_rmse": float(np.sqrt(np.mean(diff * diff)) / RAW_SCALE),
        "box_weight_rmse": float(np.sqrt(np.mean((norm - box) ** 2))),
        "has_negative_weight": has_negative,
        "kernel_width_px": float((cols[active].max() - cols[active].min() + 1) if np.any(active) else 0.0),
        "kernel_height_px": float((rows_idx[active].max() - rows_idx[active].min() + 1) if np.any(active) else 0.0),
    }


def measure_pair(np: Any, pair: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    high_path = Path(pair["high_raw_path"])
    low_path = Path(pair["low_raw_path"])
    high = read_raw(np, high_path, tuple(args.high_shape))
    low = read_raw(np, low_path, tuple(args.low_shape))
    high_low = block_mean2(np, high)
    source = gradient_proxy(np, high_low, args.alignment_scale)
    target = gradient_proxy(np, low, args.alignment_scale)
    sx_small, sy_small, phase_response = phase_shift(np, source, target)
    sx = int(sx_small * args.alignment_scale)
    sy = int(sy_small * args.alignment_scale)
    crop = crop_params(sx, sy, tuple(args.low_shape))
    corr = aligned_corr(np, low, high_low, crop, args.correlation_sample_step)
    tile_summary = tile_counts(np, low, crop, args.tile_size, args.tile_stride)
    tone = robust_line(
        np,
        np.asarray(high_low[crop["high_low_y"] : crop["high_low_y"] + crop["height"] : 16, crop["high_low_x"] : crop["high_low_x"] + crop["width"] : 16], dtype=np.float32),
        np.asarray(low[crop["low_y"] : crop["low_y"] + crop["height"] : 16, crop["low_x"] : crop["low_x"] + crop["width"] : 16], dtype=np.float32),
    )
    fit = bayer_plane_fit(np, low, high, crop, args.max_samples_per_pair)
    accepted = (
        corr >= args.min_alignment_corr
        and tile_summary["sharp_edge_tile_count"] > 0
        and tile_summary["texture_field_tile_count"] > 0
    )
    return {
        "low_stem": pair.get("low_stem"),
        "high_stem": pair.get("high_stem"),
        "time_delta_s": pair.get("time_delta_s"),
        "low_raw": artifact_ref(low_path),
        "high_raw": artifact_ref(high_path),
        "alignment": {
            "shift_low_raw_px_x": sx,
            "shift_low_raw_px_y": sy,
            "phase_response": phase_response,
            "correlation": corr,
            "crop": crop,
            "accepted_for_kernel": accepted,
        },
        "tone_match_high_box_to_low": tone,
        "tile_summary": tile_summary,
        "psf_fit": fit,
        "rejection_reasons": [] if accepted else ["alignment/scene correlation below threshold or insufficient tile support"],
    }


def combine_fits(np: Any, pair_rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in pair_rows if row["alignment"]["accepted_for_kernel"]]
    if not accepted:
        return {
            "available": False,
            "accepted_pair_count": 0,
            "normalized_weights_mean": [],
            "normalized_weights_std": [],
            "kernel_stable": False,
        }
    weights = np.asarray([row["psf_fit"]["normalized_weights"] for row in accepted], dtype=np.float64)
    rmses = np.asarray([row["psf_fit"]["rmse_14bit"] for row in accepted], dtype=np.float64)
    neg_count = sum(1 for row in accepted if row["psf_fit"]["has_negative_weight"])
    std = weights.std(axis=0)
    mean = weights.mean(axis=0)
    kernel_stable = bool(accepted and len(accepted) >= 3 and float(np.max(std)) <= 0.10 and neg_count == 0)
    return {
        "available": True,
        "accepted_pair_count": len(accepted),
        "normalized_weights_mean": [float(x) for x in mean],
        "normalized_weights_std": [float(x) for x in std],
        "rmse_14bit_median": float(np.median(rmses)),
        "negative_weight_pair_count": int(neg_count),
        "kernel_stable": kernel_stable,
        "stability_rule": "requires >=3 accepted pairs, max normalized-weight std <= 0.10, and no pair with normalized weight < -0.05",
    }


def build_measurement(args: argparse.Namespace) -> dict[str, Any]:
    np = import_numpy()
    if np is None:
        raise SystemExit(2)
    plan = json.loads(args.measurement_plan.read_text(encoding="utf-8"))
    pairs = plan.get("selected_pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("measurement plan has no selected_pairs")
    start = time.perf_counter()
    pair_rows = [measure_pair(np, pair, args) for pair in pairs if isinstance(pair, dict)]
    combined = combine_fits(np, pair_rows)
    accepted_count = int(combined["accepted_pair_count"])
    edge_count = sum(int(row["tile_summary"]["sharp_edge_tile_count"]) for row in pair_rows if row["alignment"]["accepted_for_kernel"])
    texture_count = sum(int(row["tile_summary"]["texture_field_tile_count"]) for row in pair_rows if row["alignment"]["accepted_for_kernel"])
    acceptance = dict(plan.get("acceptance") or {})
    min_pairs = int(acceptance.get("minimum_accepted_after_scene_vetting") or 3)
    min_edges = int(acceptance.get("minimum_sharp_edge_tiles") or 96)
    min_textures = int(acceptance.get("minimum_texture_field_tiles") or 96)
    measured_native_psf_ready = bool(
        accepted_count >= min_pairs
        and edge_count >= min_edges
        and texture_count >= min_textures
        and combined.get("kernel_stable")
    )
    blockers = []
    if accepted_count < min_pairs:
        blockers.append(f"Only {accepted_count} selected pairs passed scene/alignment vetting; {min_pairs} are required.")
    if edge_count < min_edges:
        blockers.append(f"Accepted pairs provide {edge_count} sharp-edge tiles; {min_edges} are required.")
    if texture_count < min_textures:
        blockers.append(f"Accepted pairs provide {texture_count} texture-field tiles; {min_textures} are required.")
    if not combined.get("kernel_stable"):
        blockers.append("The measured per-pair kernels are not stable enough to promote as a native PSF model.")
    blockers.append("No PSF-conditioned 4K cleanup or 8K SR gate has been run with this measured kernel yet.")

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "measurement_plan": artifact_ref(args.measurement_plan),
        "implementation": {
            "method": "numpy_phase_correlation_alignment_plus_bayer_plane_lstsq_v1",
            "high_shape": list(args.high_shape),
            "low_shape": list(args.low_shape),
            "alignment_scale": args.alignment_scale,
            "min_alignment_corr": args.min_alignment_corr,
            "max_samples_per_pair": args.max_samples_per_pair,
        },
        "production_ready": False,
        "measurement_executed": True,
        "native_psf_measured": measured_native_psf_ready,
        "native_psf_ready_for_model_conditioning": measured_native_psf_ready,
        "summary": {
            "selected_pair_count": len(pair_rows),
            "accepted_pair_count": accepted_count,
            "rejected_pair_count": len(pair_rows) - accepted_count,
            "accepted_sharp_edge_tile_count": edge_count,
            "accepted_texture_field_tile_count": texture_count,
            "meets_plan_pair_requirement": accepted_count >= min_pairs,
            "meets_plan_tile_requirement": edge_count >= min_edges and texture_count >= min_textures,
            "kernel_stable": bool(combined.get("kernel_stable")),
            "measured_native_psf_ready": measured_native_psf_ready,
            "elapsed_ms": (time.perf_counter() - start) * 1000.0,
        },
        "combined_kernel": combined,
        "pair_measurements": pair_rows,
        "blockers": blockers,
        "next_actions": [
            "Capture or locate at least three controlled same-scene Mission 1 high/low pairs if near-time pairs remain rejected.",
            "Re-run this measurement until the accepted pair count, tile support, and kernel stability gates pass.",
            "Train the next 4K cleanup / 8K SR candidate with the measured kernel only after native_psf_ready_for_model_conditioning is true.",
        ],
    }


def render_html(data: dict[str, Any], out_json: Path) -> str:
    cards = [
        ("Executed", str(data["measurement_executed"]).lower()),
        ("Native PSF ready", str(data["native_psf_measured"]).lower()),
        ("Accepted pairs", data["summary"]["accepted_pair_count"]),
        ("Rejected pairs", data["summary"]["rejected_pair_count"]),
        ("Sharp-edge tiles", data["summary"]["accepted_sharp_edge_tile_count"]),
        ("Texture tiles", data["summary"]["accepted_texture_field_tile_count"]),
    ]
    card_html = "\n".join(
        f'<section class="card"><div class="k">{html.escape(str(k))}</div><div class="v">{html.escape(str(v))}</div></section>'
        for k, v in cards
    )
    pair_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['low_stem']))}</td>"
        f"<td>{html.escape(str(row['high_stem']))}</td>"
        f"<td>{html.escape(str(row['time_delta_s']))}</td>"
        f"<td>{row['alignment']['shift_low_raw_px_x']}</td>"
        f"<td>{row['alignment']['shift_low_raw_px_y']}</td>"
        f"<td>{row['alignment']['correlation']:.4f}</td>"
        f"<td class=\"{'pass' if row['alignment']['accepted_for_kernel'] else 'fail'}\">{str(row['alignment']['accepted_for_kernel']).lower()}</td>"
        f"<td>{row['psf_fit']['rmse_14bit']:.3f}</td>"
        f"<td>{html.escape(json.dumps([round(x, 4) for x in row['psf_fit']['normalized_weights']]))}</td>"
        "</tr>"
        for row in data["pair_measurements"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    combined = data["combined_kernel"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mission 1 Native PSF Measurement</title>
  <style>
    body {{ margin: 0; background: #f4f6f7; color: #101820; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    p {{ color: #53606d; max-width: 900px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
    .k {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .v {{ font-size: 26px; font-weight: 760; margin-top: 4px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin-top: 10px; }}
    th, td {{ padding: 9px; border-bottom: 1px solid #e6ebef; text-align: left; vertical-align: top; }}
    th {{ color: #53606d; font-size: 12px; text-transform: uppercase; }}
    .panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; margin-top: 10px; }}
    .pass {{ color: #16794c; font-weight: 760; }}
    .fail {{ color: #a33a32; font-weight: 760; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body><main>
  <h1>Mission 1 Native PSF Measurement</h1>
  <p>This executes the high/low pair measurement protocol. The current run is a production diagnostic: it may measure useful alignment and kernel data, but it only promotes a native PSF when scene vetting, tile support, and kernel stability all pass.</p>
  <div class="grid">{card_html}</div>
  <section class="panel">
    <strong>Combined kernel:</strong>
    mean weights {html.escape(json.dumps([round(x, 5) for x in combined.get('normalized_weights_mean', [])]))};
    std {html.escape(json.dumps([round(x, 5) for x in combined.get('normalized_weights_std', [])]))};
    stable {str(combined.get('kernel_stable')).lower()}.
  </section>
  <h2>Pair Measurements</h2>
  <table><thead><tr><th>low</th><th>high</th><th>delta s</th><th>shift x</th><th>shift y</th><th>corr</th><th>accepted</th><th>fit RMSE</th><th>weights</th></tr></thead><tbody>{pair_rows}</tbody></table>
  <h2>Blockers</h2><section class="panel"><ul>{blockers}</ul></section>
  <h2>Next Actions</h2><section class="panel"><ul>{actions}</ul></section>
  <p class="meta">Generated {html.escape(data['created_utc'])}. JSON: {html.escape(str(out_json))}.</p>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measurement-plan", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--high-shape", type=int, nargs=2, default=list(HIGH_SHAPE), metavar=("HEIGHT", "WIDTH"))
    ap.add_argument("--low-shape", type=int, nargs=2, default=list(LOW_SHAPE), metavar=("HEIGHT", "WIDTH"))
    ap.add_argument("--alignment-scale", type=int, default=8)
    ap.add_argument("--correlation-sample-step", type=int, default=16)
    ap.add_argument("--min-alignment-corr", type=float, default=0.75)
    ap.add_argument("--tile-size", type=int, default=128)
    ap.add_argument("--tile-stride", type=int, default=128)
    ap.add_argument("--max-samples-per-pair", type=int, default=240000)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = build_measurement(args)
    out_json = args.output_dir / "native_psf_measurement.json"
    out_html = args.output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(out_html)
    print(json.dumps(data["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
