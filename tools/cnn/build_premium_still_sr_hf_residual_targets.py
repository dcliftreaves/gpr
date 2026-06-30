#!/usr/bin/env python3
"""Build structured HF residual targets for premium still-SR.

This is a training-target builder, not a runtime render path. It compares a
source DNG render against a candidate SR DNG render, decomposes both into
low/high-frequency bands, and saves the residual needed to move candidate HF
toward source HF. The source DNG is used only to build supervised targets.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_premium_still_sr_latitude_review import (  # noqa: E402
    artifact_ref,
    block_lowpass_rgb,
    crop_metrics,
    crop_starts as named_crop_starts,
    image_from_rgb,
    render_rawpy,
    sha256_file,
    to_float,
)


SCHEMA = "gpr.premium_still_sr_hf_residual_targets.v1"
DEFAULT_EXPOSURES = (-2.0, 0.0, 2.0)


def crop_positions(width: int, height: int, crop: int, grid: int) -> list[tuple[str, int, int]]:
    if grid <= 1:
        return named_crop_starts(width, height, crop)
    if crop > width or crop > height:
        return [("full_fit", 0, 0)]
    xs = np.linspace(0, max(0, width - crop), grid)
    ys = np.linspace(0, max(0, height - crop), grid)
    positions: list[tuple[str, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for gy, yf in enumerate(ys):
        for gx, xf in enumerate(xs):
            x = int(round(float(xf)))
            y = int(round(float(yf)))
            if (x, y) in seen:
                continue
            seen.add((x, y))
            positions.append((f"grid{grid}_{gy:02d}_{gx:02d}", x, y))
    return positions


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


def hf_correlation(ref_hf: np.ndarray, cand_hf: np.ndarray) -> float | None:
    num = float(np.sum(ref_hf * cand_hf))
    den = float(np.sqrt(np.sum(ref_hf * ref_hf) * np.sum(cand_hf * cand_hf)))
    return num / den if den > 1.0e-12 else None


def residual_preview(residual: np.ndarray, scale: float) -> Image.Image:
    arr = np.clip((residual / float(scale)) * 0.5 + 0.5, 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8), "RGB")


def local_cfa4_planes(raw_crop: np.ndarray) -> np.ndarray:
    """Return repeated local 2x2 CFA planes at the crop's full resolution."""
    if raw_crop.ndim != 2:
        raise ValueError(f"raw crop must be 2D, got {raw_crop.shape}")
    height, width = raw_crop.shape
    out = np.empty((height, width, 4), dtype=np.float32)
    for y_phase in (0, 1):
        for x_phase in (0, 1):
            channel = y_phase * 2 + x_phase
            plane = raw_crop[y_phase::2, x_phase::2]
            expanded = np.repeat(np.repeat(plane, 2, axis=0), 2, axis=1)
            if expanded.shape[0] < height:
                expanded = np.pad(expanded, ((0, height - expanded.shape[0]), (0, 0)), mode="edge")
            if expanded.shape[1] < width:
                expanded = np.pad(expanded, ((0, 0), (0, width - expanded.shape[1])), mode="edge")
            out[:, :, channel] = expanded[:height, :width]
    return out


def build_rows_from_arrays(
    *,
    ref: np.ndarray,
    cand: np.ndarray,
    candidate_raw_norm: np.ndarray | None = None,
    ev: float,
    crop_size: int,
    crop_grid: int = 1,
    max_crops_per_ev: int | None = None,
    block: int,
    residual_scale: float,
    panels_dir: Path | None = None,
    scene_id: str | None = None,
    source_dng: Path | None = None,
    candidate_dng: Path | None = None,
) -> tuple[list[dict[str, Any]], list[np.ndarray], list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    if ref.shape != cand.shape:
        common_h = min(ref.shape[0], cand.shape[0])
        common_w = min(ref.shape[1], cand.shape[1])
        ref = ref[:common_h, :common_w]
        cand = cand[:common_h, :common_w]
        if candidate_raw_norm is not None:
            candidate_raw_norm = candidate_raw_norm[:common_h, :common_w]
    if candidate_raw_norm is not None and candidate_raw_norm.shape[:2] != cand.shape[:2]:
        raise ValueError(f"candidate raw feature shape {candidate_raw_norm.shape} does not match render shape {cand.shape[:2]}")
    height, width = ref.shape[:2]
    crop = min(crop_size, width, height)
    rows: list[dict[str, Any]] = []
    inputs: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    raw_cfa_features: list[np.ndarray] = []
    if panels_dir is not None:
        panels_dir.mkdir(parents=True, exist_ok=True)
    positions = crop_positions(width, height, crop, crop_grid)
    if max_crops_per_ev is not None:
        positions = positions[: max(0, max_crops_per_ev)]
    for crop_name, x, y in positions:
        ref_crop = ref[y : y + crop, x : x + crop]
        cand_crop = cand[y : y + crop, x : x + crop]
        ref_f = to_float(ref_crop)
        cand_f = to_float(cand_crop)
        ref_hf = ref_f - block_lowpass_rgb(ref_f, block)
        cand_hf = cand_f - block_lowpass_rgb(cand_f, block)
        residual = ref_hf - cand_hf
        metrics = crop_metrics(ref_crop, cand_crop)
        row = {
            "scene_id": scene_id,
            "source_dng": str(source_dng) if source_dng else None,
            "candidate_dng": str(candidate_dng) if candidate_dng else None,
            "crop": crop_name,
            "ev": ev,
            "crop_xy": [x, y],
            "crop_size": crop,
            "crop_grid": crop_grid,
            "block": block,
            "mae": metrics["mae"],
            "y_mae": metrics["y_mae"],
            "lf_y_mae": metrics["lf_y_mae"],
            "hf_y_mae": metrics["hf_y_mae"],
            "hf_y_energy_ratio": metrics["hf_y_energy_ratio"],
            "hf_y_correlation": metrics["hf_y_correlation"],
            "ref_hf_abs_mean": float(np.mean(np.abs(ref_hf))),
            "candidate_hf_abs_mean": float(np.mean(np.abs(cand_hf))),
            "residual_abs_mean": float(np.mean(np.abs(residual))),
            "residual_rmse": float(np.sqrt(np.mean(residual * residual))),
            "residual_p95_abs": float(np.percentile(np.abs(residual), 95.0)),
            "policy": "training_target_uses_source_hf_not_runtime_render_path",
        }
        if candidate_raw_norm is not None:
            raw_crop = candidate_raw_norm[y : y + crop, x : x + crop]
            raw_cfa_features.append(local_cfa4_planes(raw_crop).astype(np.float16))
            row["candidate_raw_cfa_features"] = "local_2x2_cfa_planes_repeated_to_rgb_crop"
            row["candidate_raw_cfa_origin_xy"] = [x, y]
        if panels_dir is not None:
            safe = f"{crop_name}_ev{ev:+.0f}".replace("+", "p").replace("-", "m")
            src_path = panels_dir / f"{safe}_source.jpg"
            cand_path = panels_dir / f"{safe}_candidate.jpg"
            residual_path = panels_dir / f"{safe}_hf_residual.jpg"
            image_from_rgb(ref_crop).save(src_path, quality=92)
            image_from_rgb(cand_crop).save(cand_path, quality=92)
            residual_preview(residual, residual_scale).save(residual_path, quality=92)
            row["panels"] = [
                {"kind": "source", "path": str(src_path)},
                {"kind": "candidate", "path": str(cand_path)},
                {"kind": "hf_residual", "path": str(residual_path)},
            ]
        inputs.append(cand_f.astype(np.float16))
        residuals.append(residual.astype(np.float16))
        targets.append(ref_hf.astype(np.float16))
        rows.append(row)
    return rows, inputs, residuals, targets, raw_cfa_features


def write_contact_sheet(path: Path, rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = rows[:max_rows]
    if not selected or "panels" not in selected[0]:
        return
    first = Image.open(selected[0]["panels"][0]["path"])
    panel_w, panel_h = first.size
    first.close()
    pad = 10
    label_h = 42
    cols = 3
    sheet = Image.new("RGB", (cols * (panel_w + pad) + pad, len(selected) * (panel_h + label_h + pad) + pad), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["source", "candidate", "HF residual target"]
    for row_idx, row in enumerate(selected):
        y0 = pad + row_idx * (panel_h + label_h + pad)
        title = (
            f"{row['crop']} EV {row['ev']:+.0f} "
            f"HF corr {row['hf_y_correlation']:.3f} residual {row['residual_abs_mean']:.4f}"
        )
        draw.text((pad, y0), title, fill=(245, 245, 245))
        for col, panel in enumerate(row["panels"]):
            x0 = pad + col * (panel_w + pad)
            draw.text((x0, y0 + 19), headers[col], fill=(190, 190, 190))
            img = Image.open(panel["path"]).convert("RGB")
            sheet.paste(img, (x0, y0 + label_h))
            img.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def render_html(data: dict[str, Any], output_dir: Path) -> str:
    rows = sorted(data["rows"], key=lambda row: row["residual_abs_mean"], reverse=True)
    contact = Path(data["contact_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    table = []
    for row in rows:
        table.append(
            f"<tr><td>{html.escape(str(row.get('scene_id')))}</td><td>{html.escape(row['crop'])}</td><td>{row['ev']:+.0f}</td>"
            f"<td>{row['mae']:.5f}</td><td>{row['hf_y_mae']:.5f}</td>"
            f"<td>{html.escape(str(row['hf_y_energy_ratio']))}</td>"
            f"<td>{html.escape(str(row['hf_y_correlation']))}</td>"
            f"<td>{row['residual_abs_mean']:.5f}</td><td>{row['residual_p95_abs']:.5f}</td></tr>"
        )
    summary = data["summary"]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR HF Residual Targets</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left}}
code{{color:#b7d7ff}}.contact{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR HF Residual Targets</h1>
<p>Source DNG: <code>{html.escape(data['source_dng'])}</code></p>
<p>Candidate DNG: <code>{html.escape(str(data.get('candidate_dng')))}</code></p>
<p>Candidate raw: <code>{html.escape(str(data.get('candidate_raw')))}</code></p>
<p><b>Policy:</b> source DNG high-frequency content is used only to build supervised training targets. This is not a no-REF runtime render path.</p>
<div class="grid">
<div class="card"><h2>Rows</h2><p>{summary['row_count']}</p></div>
<div class="card"><h2>HF Corr</h2><p>median {summary['hf_y_correlation']['median']:.5f}</p><p>min {summary['hf_y_correlation']['min']:.5f}</p></div>
<div class="card"><h2>Residual Mean</h2><p>median {summary['residual_abs_mean']['median']:.5f}</p><p>max {summary['residual_abs_mean']['max']:.5f}</p></div>
<div class="card"><h2>Residual p95</h2><p>median {summary['residual_p95_abs']['median']:.5f}</p><p>max {summary['residual_p95_abs']['max']:.5f}</p></div>
</div>
<img class="contact" src="{html.escape(contact)}">
<table><tr><th>scene</th><th>crop</th><th>EV</th><th>MAE</th><th>HF Y MAE</th><th>HF energy ratio</th><th>HF corr</th><th>residual mean</th><th>residual p95</th></tr>
{''.join(table)}
</table></body></html>
"""


def write_npz(
    path: Path,
    inputs: list[np.ndarray],
    residuals: list[np.ndarray],
    targets: list[np.ndarray],
    rows: list[dict[str, Any]],
    raw_cfa_features: list[np.ndarray] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, Any] = {
        "inputs": np.stack(inputs, axis=0).astype(np.float16),
        "hf_residuals": np.stack(residuals, axis=0).astype(np.float16),
        "source_hf_targets": np.stack(targets, axis=0).astype(np.float16),
        "meta": np.asarray(json.dumps(rows, sort_keys=True)),
    }
    if raw_cfa_features is not None:
        if len(raw_cfa_features) != len(inputs):
            raise ValueError(f"raw CFA feature count {len(raw_cfa_features)} does not match input count {len(inputs)}")
        arrays["candidate_raw_cfa4"] = np.stack(raw_cfa_features, axis=0).astype(np.float16)
    np.savez_compressed(path, **arrays)


def render_rawpy_with_raw_replacement(
    template_dng: Path,
    replacement_raw: Path,
    *,
    width: int,
    height: int,
    ev: float,
    output_bps: int,
    half_size: bool,
) -> np.ndarray:
    import rawpy

    raw_values = np.fromfile(replacement_raw, dtype="<u2")
    expected = width * height
    if raw_values.size != expected:
        raise ValueError(f"{replacement_raw} has {raw_values.size} pixels, expected {expected}")
    replacement = raw_values.reshape((height, width))
    raw = rawpy.imread(str(template_dng))
    try:
        if raw.raw_image.shape != replacement.shape:
            raise ValueError(f"{template_dng} raw shape {raw.raw_image.shape} does not match replacement {replacement.shape}")
        raw.raw_image[:, :] = replacement
        return raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=output_bps,
            gamma=(2.222, 4.5),
            output_color=rawpy.ColorSpace.sRGB,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            exp_shift=2.0**ev,
            exp_preserve_highlights=0.0,
            user_flip=0,
            half_size=half_size,
        )
    finally:
        raw.close()


def load_normalized_raw_from_dng(path: Path) -> np.ndarray:
    import rawpy

    raw = rawpy.imread(str(path))
    try:
        arr = raw.raw_image.copy().astype(np.float32)
        black = float(np.mean(raw.black_level_per_channel)) if raw.black_level_per_channel is not None else 0.0
        white = float(raw.white_level or 65535.0)
        return np.clip((arr - black) / max(white - black, 1.0), 0.0, 1.0)
    finally:
        raw.close()


def load_normalized_raw_from_file(path: Path, *, width: int, height: int, template_dng: Path) -> np.ndarray:
    values = np.fromfile(path, dtype="<u2")
    expected = width * height
    if values.size != expected:
        raise ValueError(f"{path} has {values.size} pixels, expected {expected}")
    arr = values.reshape((height, width)).astype(np.float32)
    import rawpy

    raw = rawpy.imread(str(template_dng))
    try:
        black = float(np.mean(raw.black_level_per_channel)) if raw.black_level_per_channel is not None else 0.0
        white = float(raw.white_level or 65535.0)
    finally:
        raw.close()
    return np.clip((arr - black) / max(white - black, 1.0), 0.0, 1.0)


def infer_candidate_raw_shape(candidate_raw: Path) -> tuple[int, int]:
    receipt_path = candidate_raw.with_suffix(candidate_raw.suffix + ".json")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"{candidate_raw} requires --candidate-raw-width/--candidate-raw-height "
            f"or a degraded-candidate receipt at {receipt_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{receipt_path} is not valid JSON") from exc
    candidate = receipt.get("candidate") if isinstance(receipt, dict) else None
    if not isinstance(candidate, dict):
        raise ValueError(f"{receipt_path} does not contain a candidate object")
    width = int(candidate.get("width") or 0)
    height = int(candidate.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"{receipt_path} does not contain positive candidate width/height")
    return width, height


def build(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panels_dir = args.output_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    inputs: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    raw_cfa_features: list[np.ndarray] = []
    render_times: list[dict[str, Any]] = []
    candidate_raw_norm: np.ndarray | None = None
    if args.include_raw_cfa_features:
        if args.half_size:
            raise ValueError("--include-raw-cfa-features is incompatible with --half-size")
        if args.candidate_raw:
            candidate_raw_norm = load_normalized_raw_from_file(
                args.candidate_raw,
                width=args.candidate_raw_width,
                height=args.candidate_raw_height,
                template_dng=args.source_dng,
            )
        else:
            candidate_raw_norm = load_normalized_raw_from_dng(args.candidate_dng)
    for ev in [float(v) for v in args.ev]:
        t0 = time.perf_counter()
        ref = render_rawpy(args.source_dng, ev, args.output_bps, args.half_size)
        t1 = time.perf_counter()
        if args.candidate_raw:
            cand = render_rawpy_with_raw_replacement(
                args.source_dng,
                args.candidate_raw,
                width=args.candidate_raw_width,
                height=args.candidate_raw_height,
                ev=ev,
                output_bps=args.output_bps,
                half_size=args.half_size,
            )
        else:
            cand = render_rawpy(args.candidate_dng, ev, args.output_bps, args.half_size)
        t2 = time.perf_counter()
        part_rows, part_inputs, part_residuals, part_targets, part_raw_cfa_features = build_rows_from_arrays(
            ref=ref,
            cand=cand,
            candidate_raw_norm=candidate_raw_norm,
            ev=ev,
            crop_size=args.crop_size,
            crop_grid=args.crop_grid,
            max_crops_per_ev=args.max_crops_per_ev,
            block=args.block,
            residual_scale=args.residual_preview_scale,
            panels_dir=panels_dir,
            scene_id=args.scene_id or args.source_dng.stem,
            source_dng=args.source_dng,
            candidate_dng=args.candidate_dng,
        )
        for row in part_rows:
            row["candidate_raw"] = str(args.candidate_raw) if args.candidate_raw else None
            row["noise_sidecars"] = [str(path) for path in args.noise_sidecar]
        rows.extend(part_rows)
        inputs.extend(part_inputs)
        residuals.extend(part_residuals)
        targets.extend(part_targets)
        raw_cfa_features.extend(part_raw_cfa_features)
        render_times.append({"ev": ev, "source_s": t1 - t0, "candidate_s": t2 - t1})
        del ref
        del cand
    rows_sorted = sorted(rows, key=lambda row: row["residual_abs_mean"], reverse=True)
    contact = args.output_dir / "contact_sheet.jpg"
    write_contact_sheet(contact, rows_sorted, args.contact_rows)
    npz_path = args.output_dir / "hf_residual_targets.npz"
    write_npz(npz_path, inputs, residuals, targets, rows, raw_cfa_features if args.include_raw_cfa_features else None)
    summary = {
        "row_count": len(rows),
        "hf_y_correlation": stats([float(row["hf_y_correlation"]) for row in rows if row["hf_y_correlation"] is not None]),
        "hf_y_energy_ratio": stats([float(row["hf_y_energy_ratio"]) for row in rows if row["hf_y_energy_ratio"] is not None]),
        "residual_abs_mean": stats([float(row["residual_abs_mean"]) for row in rows]),
        "residual_rmse": stats([float(row["residual_rmse"]) for row in rows]),
        "residual_p95_abs": stats([float(row["residual_p95_abs"]) for row in rows]),
        "render_times": render_times,
    }
    data = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "source_dng": str(args.source_dng),
        "candidate_dng": str(args.candidate_dng) if args.candidate_dng else None,
        "candidate_raw": str(args.candidate_raw) if args.candidate_raw else None,
        "source_dng_sha256": sha256_file(args.source_dng),
        "candidate_dng_sha256": sha256_file(args.candidate_dng) if args.candidate_dng else None,
        "candidate_raw_sha256": sha256_file(args.candidate_raw) if args.candidate_raw else None,
        "render": {
            "engine": "rawpy/libraw",
            "use_camera_wb": True,
            "no_auto_bright": True,
            "output_bps": args.output_bps,
            "gamma": [2.222, 4.5],
            "demosaic": "AHD",
            "half_size": args.half_size,
            "ev": [float(v) for v in args.ev],
            "crop_size": args.crop_size,
            "crop_grid": args.crop_grid,
            "max_crops_per_ev": args.max_crops_per_ev,
            "block": args.block,
        },
        "noise_sidecars": [
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in args.noise_sidecar
        ],
        "policy": {
            "uses_source_hf": True,
            "runtime_safe": False,
            "purpose": "supervised_structured_hf_residual_training_target",
        },
        "summary": summary,
        "rows": rows,
        "arrays": {
            "npz": str(npz_path),
            "inputs": "candidate_render_rgb_float16_nhwc",
            "hf_residuals": "source_hf_minus_candidate_hf_float16_nhwc",
            "source_hf_targets": "source_hf_float16_nhwc",
            "candidate_raw_cfa4": (
                "candidate_raw_local_2x2_cfa_planes_float16_nhwc_repeated_to_rgb_crop"
                if args.include_raw_cfa_features
                else None
            ),
        },
        "contact_sheet": str(contact),
        "artifacts": {"npz": artifact_ref(npz_path), "contact_sheet": artifact_ref(contact)},
    }
    receipt = args.output_dir / "hf_residual_targets.json"
    index = args.output_dir / "index.html"
    receipt.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    index.write_text(render_html(data, args.output_dir), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dng", type=Path, required=True)
    candidate = ap.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--candidate-dng", type=Path)
    candidate.add_argument("--candidate-raw", type=Path)
    ap.add_argument("--candidate-raw-width", type=int, default=0)
    ap.add_argument("--candidate-raw-height", type=int, default=0)
    ap.add_argument("--noise-sidecar", type=Path, action="append", default=[])
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--ev", action="append", type=float, default=list(DEFAULT_EXPOSURES))
    ap.add_argument("--crop-size", type=int, default=768)
    ap.add_argument("--crop-grid", type=int, default=1, help="1 keeps named crops; >1 uses a deterministic grid per EV")
    ap.add_argument("--max-crops-per-ev", type=int, help="optional cap after deterministic crop ordering")
    ap.add_argument("--scene-id", help="stable scene/source id written into each row")
    ap.add_argument("--block", type=int, default=16)
    ap.add_argument("--output-bps", type=int, choices=(8, 16), default=16)
    ap.add_argument("--half-size", action="store_true")
    ap.add_argument("--include-raw-cfa-features", action="store_true")
    ap.add_argument("--residual-preview-scale", type=float, default=0.08)
    ap.add_argument("--contact-rows", type=int, default=9)
    args = ap.parse_args()
    if args.candidate_raw and (args.candidate_raw_width <= 0 or args.candidate_raw_height <= 0):
        try:
            args.candidate_raw_width, args.candidate_raw_height = infer_candidate_raw_shape(args.candidate_raw)
        except ValueError as exc:
            ap.error(str(exc))
    data = build(args)
    print(
        json.dumps(
            {
                "receipt": str(args.output_dir / "hf_residual_targets.json"),
                "dashboard": str(args.output_dir / "index.html"),
                "npz": data["arrays"]["npz"],
                "rows": data["summary"]["row_count"],
                "median_hf_correlation": data["summary"]["hf_y_correlation"]["median"],
                "median_residual_abs_mean": data["summary"]["residual_abs_mean"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
