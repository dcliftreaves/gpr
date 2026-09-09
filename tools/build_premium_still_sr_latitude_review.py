#!/usr/bin/env python3
"""Build a raw-editor-style latitude review for premium still-SR DNGs.

This differs from the Bayer/OpenCV proxy dashboard: it renders the source DNG
and candidate DNG through rawpy/LibRaw with the camera white balance, color
metadata, exposure shift, and demosaic path. It is still an automated receipt,
not a substitute for manual review in Lightroom/ACR.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


SCHEMA = "gpr.premium_still_sr_latitude_review.v1"
DEFAULT_EXPOSURES = (-2.0, 0.0, 2.0)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def stable_seed(*parts: object) -> int:
    text = "\n".join(str(part) for part in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "little", signed=False)


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


def crop_starts(width: int, height: int, crop: int) -> list[tuple[str, int, int]]:
    margin = max(0, crop // 4)
    return [
        ("upper_left", min(margin, max(0, width - crop)), min(margin, max(0, height - crop))),
        ("center", max(0, (width - crop) // 2), max(0, (height - crop) // 2)),
        ("lower_detail", max(0, width - crop - margin), max(0, height - crop - margin)),
    ]


def render_rawpy(path: Path, ev: float, output_bps: int, half_size: bool) -> np.ndarray:
    import rawpy

    raw = rawpy.imread(str(path))
    try:
        rgb = raw.postprocess(
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
        return rgb
    finally:
        raw.close()


def to_float(rgb: np.ndarray) -> np.ndarray:
    denom = 65535.0 if rgb.dtype == np.uint16 else 255.0
    return rgb.astype(np.float32) / denom


def from_float_like(rgb: np.ndarray, template: np.ndarray) -> np.ndarray:
    if template.dtype == np.uint16:
        return (np.clip(rgb, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    return (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def block_lowpass_rgb(rgb: np.ndarray, block: int) -> np.ndarray:
    if block <= 1:
        return rgb.copy()
    h, w, c = rgb.shape
    pad_h = ((h + block - 1) // block) * block
    pad_w = ((w + block - 1) // block) * block
    padded = np.pad(rgb, ((0, pad_h - h), (0, pad_w - w), (0, 0)), mode="edge")
    low = padded.reshape(pad_h // block, block, pad_w // block, block, c).mean(axis=(1, 3))
    return np.repeat(np.repeat(low, block, axis=0), block, axis=1)[:h, :w]


def block_lowpass_gray(gray: np.ndarray, block: int) -> np.ndarray:
    if block <= 1:
        return gray.copy()
    h, w = gray.shape
    pad_h = ((h + block - 1) // block) * block
    pad_w = ((w + block - 1) // block) * block
    padded = np.pad(gray, ((0, pad_h - h), (0, pad_w - w)), mode="edge")
    low = padded.reshape(pad_h // block, block, pad_w // block, block).mean(axis=(1, 3))
    return np.repeat(np.repeat(low, block, axis=0), block, axis=1)[:h, :w]


def oracle_hf_addback(ref: np.ndarray, cand: np.ndarray, block: int) -> np.ndarray:
    """Replace candidate HF with source HF while preserving candidate LF.

    This is a diagnostic upper bound that uses source content. It is not a
    production render path and must not be promoted as no-REF behavior.
    """
    ref_f = to_float(ref)
    cand_f = to_float(cand)
    ref_lf = block_lowpass_rgb(ref_f, block)
    cand_lf = block_lowpass_rgb(cand_f, block)
    ref_hf = ref_f - ref_lf
    return from_float_like(cand_lf + ref_hf, cand)


def load_noise_sidecar(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def noise_sidecar_sigma_norm(sidecar: dict[str, Any] | None) -> float | None:
    if not sidecar:
        return None
    camera = sidecar.get("camera", {})
    black = float(camera.get("black_level", 0.0))
    white = float(camera.get("white_level", 0.0))
    span = white - black
    if span <= 0.0:
        return None
    sigmas = []
    per_plane = sidecar.get("per_plane", {})
    if not per_plane and sidecar.get("calibrations"):
        per_plane = sidecar["calibrations"][0].get("per_plane", {})
    for plane in per_plane.values():
        if "sigma_black" in plane:
            sigmas.append(float(plane["sigma_black"]))
    if not sigmas:
        return None
    return float(np.median(np.asarray(sigmas, dtype=np.float64)) / span)


def synthetic_hf_addback(cand: np.ndarray, scale: float, seed: int, block: int, color: bool) -> np.ndarray:
    """Add deterministic generated high-frequency texture without source pixels."""
    cand_f = to_float(cand)
    rng = np.random.default_rng(seed)
    if color:
        noise = rng.normal(0.0, 1.0, cand_f.shape).astype(np.float32)
        noise -= block_lowpass_rgb(noise, block)
        denom = float(np.std(noise))
        if denom > 1.0e-9:
            noise /= denom
    else:
        noise_y = rng.normal(0.0, 1.0, cand_f.shape[:2]).astype(np.float32)
        noise_y -= block_lowpass_gray(noise_y, block)
        denom = float(np.std(noise_y))
        if denom > 1.0e-9:
            noise_y /= denom
        noise = np.repeat(noise_y[:, :, None], 3, axis=2)
    return from_float_like(cand_f + noise * float(scale), cand)


def crop_metrics(ref: np.ndarray, cand: np.ndarray) -> dict[str, Any]:
    ref_f = to_float(ref)
    cand_f = to_float(cand)
    diff = cand_f - ref_f
    abs_diff = np.abs(diff)
    rmse = float(np.sqrt(np.mean(diff * diff)))
    mae = float(np.mean(abs_diff))
    psnr = 99.0 if rmse == 0.0 else 20.0 * math.log10(1.0 / rmse)
    ref_y = 0.2126 * ref_f[:, :, 0] + 0.7152 * ref_f[:, :, 1] + 0.0722 * ref_f[:, :, 2]
    cand_y = 0.2126 * cand_f[:, :, 0] + 0.7152 * cand_f[:, :, 1] + 0.0722 * cand_f[:, :, 2]
    y_diff = np.abs(cand_y - ref_y)
    block = 16
    bh = (ref_y.shape[0] // block) * block
    bw = (ref_y.shape[1] // block) * block
    if bh > 0 and bw > 0:
        ref_lf = ref_y[:bh, :bw].reshape(bh // block, block, bw // block, block).mean(axis=(1, 3))
        cand_lf = cand_y[:bh, :bw].reshape(bh // block, block, bw // block, block).mean(axis=(1, 3))
        lf_delta = cand_lf - ref_lf
        lf_y_mae: float | None = float(np.mean(np.abs(lf_delta)))
        lf_y_bias: float | None = float(np.mean(lf_delta))
        ref_lf_up = np.repeat(np.repeat(ref_lf, block, axis=0), block, axis=1)
        cand_lf_up = np.repeat(np.repeat(cand_lf, block, axis=0), block, axis=1)
        ref_hf = ref_y[:bh, :bw] - ref_lf_up
        cand_hf = cand_y[:bh, :bw] - cand_lf_up
        hf_delta = cand_hf - ref_hf
        hf_y_mae: float | None = float(np.mean(np.abs(hf_delta)))
        hf_y_rmse: float | None = float(np.sqrt(np.mean(hf_delta * hf_delta)))
        ref_hf_energy = float(np.mean(np.abs(ref_hf)))
        cand_hf_energy = float(np.mean(np.abs(cand_hf)))
        hf_energy_ratio: float | None = cand_hf_energy / ref_hf_energy if ref_hf_energy > 1.0e-9 else None
        hf_energy_delta: float | None = cand_hf_energy - ref_hf_energy
        corr_num = float(np.sum(ref_hf * cand_hf))
        corr_den = float(np.sqrt(np.sum(ref_hf * ref_hf) * np.sum(cand_hf * cand_hf)))
        hf_corr: float | None = corr_num / corr_den if corr_den > 1.0e-12 else None
    else:
        lf_y_mae = None
        lf_y_bias = None
        hf_y_mae = None
        hf_y_rmse = None
        ref_hf_energy = None
        cand_hf_energy = None
        hf_energy_ratio = None
        hf_energy_delta = None
        hf_corr = None
    highlight = ref_y >= 0.85
    shadow = ref_y <= 0.10
    midtone = (ref_y > 0.10) & (ref_y < 0.85)
    clip_delta = float(np.mean(np.any(cand_f >= 0.999, axis=2)) - np.mean(np.any(ref_f >= 0.999, axis=2)))
    return {
        "mae": mae,
        "rmse": rmse,
        "psnr_db": psnr,
        "y_mae": float(np.mean(y_diff)),
        "lf_y_mae": lf_y_mae,
        "lf_y_bias": lf_y_bias,
        "hf_y_mae": hf_y_mae,
        "hf_y_rmse": hf_y_rmse,
        "ref_hf_y_energy": ref_hf_energy,
        "candidate_hf_y_energy": cand_hf_energy,
        "hf_y_energy_ratio": hf_energy_ratio,
        "hf_y_energy_delta": hf_energy_delta,
        "hf_y_correlation": hf_corr,
        "highlight_y_mae": float(np.mean(y_diff[highlight])) if np.any(highlight) else None,
        "shadow_y_mae": float(np.mean(y_diff[shadow])) if np.any(shadow) else None,
        "midtone_y_mae": float(np.mean(y_diff[midtone])) if np.any(midtone) else None,
        "channel_mean_delta": [float(v) for v in np.mean(diff, axis=(0, 1))],
        "ref_clip_fraction": float(np.mean(np.any(ref_f >= 0.999, axis=2))),
        "candidate_clip_fraction": float(np.mean(np.any(cand_f >= 0.999, axis=2))),
        "clip_fraction_delta": clip_delta,
    }


def image_from_rgb(rgb: np.ndarray) -> Image.Image:
    if rgb.dtype == np.uint16:
        arr = (np.clip(rgb.astype(np.float32) / 257.0, 0.0, 255.0) + 0.5).astype(np.uint8)
    else:
        arr = rgb.astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def error_image(ref: np.ndarray, cand: np.ndarray, scale: float) -> Image.Image:
    err = np.mean(np.abs(to_float(cand) - to_float(ref)), axis=2)
    arr = (np.clip(err / scale, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(arr, "L").convert("RGB")


def write_contact_sheet(path: Path, rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = rows[:max_rows]
    if not selected:
        return
    first = Image.open(selected[0]["panels"][0]["path"])
    panel_w, panel_h = first.size
    first.close()
    pad = 10
    label_h = 42
    has_oracle = any(any(panel["kind"] == "oracle" for panel in row["panels"]) for row in selected)
    has_synthetic = any(any(panel["kind"] == "synthetic_hf" for panel in row["panels"]) for row in selected)
    cols = 3 + (2 if has_synthetic else 0) + (2 if has_oracle else 0)
    sheet_w = cols * (panel_w + pad) + pad
    sheet_h = len(selected) * (panel_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["source DNG", "candidate DNG", "error"]
    if has_synthetic:
        headers += ["synthetic HF", "synthetic error"]
    if has_oracle:
        headers += ["source-HF oracle", "oracle error"]
    for row_idx, row in enumerate(selected):
        y0 = pad + row_idx * (panel_h + label_h + pad)
        title = (
            f"{row['crop']} EV {row['ev']:+.0f} "
            f"MAE {row['mae']:.4f} Y {row['y_mae']:.4f} "
            f"LF {row.get('lf_y_mae'):.4f} HF {row.get('hf_y_mae'):.4f} PSNR {row['psnr_db']:.2f}"
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
    rows = sorted(data["rows"], key=lambda row: row["mae"], reverse=True)
    table_rows = []
    has_oracle = any("oracle_mae" in row for row in rows)
    has_synthetic = any("synthetic_hf_mae" in row for row in rows)
    for row in rows:
        err_panel = next(panel for panel in row["panels"] if panel["kind"] == "error")
        rel = Path(err_panel["path"]).resolve().relative_to(output_dir.resolve()).as_posix()
        if has_synthetic:
            synthetic_cols = (
                f"<td>{html.escape(str(row.get('synthetic_hf_best_scale')))}</td>"
                f"<td>{html.escape(str(row.get('synthetic_hf_mae')))}</td>"
                f"<td>{html.escape(str(row.get('synthetic_hf_y_mae')))}</td>"
                f"<td>{html.escape(str(row.get('synthetic_hf_y_energy_ratio')))}</td>"
                f"<td>{html.escape(str(row.get('synthetic_hf_mae_improvement')))}</td>"
                f"<td>{html.escape(str(row.get('synthetic_hf_oracle_mae_gap')))}</td>"
            )
        else:
            synthetic_cols = ""
        if has_oracle:
            oracle_cols = (
                f"<td>{html.escape(str(row.get('oracle_mae')))}</td>"
                f"<td>{html.escape(str(row.get('oracle_y_mae')))}</td>"
                f"<td>{html.escape(str(row.get('oracle_hf_y_mae')))}</td>"
                f"<td>{html.escape(str(row.get('oracle_mae_improvement')))}</td>"
            )
        else:
            oracle_cols = ""
        table_rows.append(
            f"<tr><td>{html.escape(row['crop'])}</td><td>{row['ev']:+.0f}</td>"
            f"<td>{row['mae']:.5f}</td><td>{row['y_mae']:.5f}</td>"
            f"<td>{html.escape(str(row.get('lf_y_mae')))}</td>"
            f"<td>{html.escape(str(row.get('hf_y_mae')))}</td>"
            f"<td>{html.escape(str(row.get('hf_y_energy_ratio')))}</td>"
            f"<td>{html.escape(str(row.get('hf_y_correlation')))}</td>"
            f"{synthetic_cols}"
            f"{oracle_cols}"
            f"<td>{row['psnr_db']:.2f}</td>"
            f"<td>{html.escape(str(row['highlight_y_mae']))}</td>"
            f"<td>{html.escape(str(row['shadow_y_mae']))}</td>"
            f"<td><img src='{html.escape(rel)}'></td></tr>"
        )
    summary = data["summary"]
    contact = Path(data["contact_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    if has_synthetic:
        synthetic_cards = (
            f"<div class=\"card\"><h2>Synthetic HF MAE</h2><p>median {summary['synthetic_hf_mae']['median']:.5f}</p>"
            f"<p>worst {summary['synthetic_hf_mae']['max']:.5f}</p></div>"
            f"<div class=\"card\"><h2>Synthetic HF Gain</h2><p>median {summary['synthetic_hf_mae_improvement']['median']:.5f}</p>"
            f"<p>best {summary['synthetic_hf_mae_improvement']['max']:.5f}</p></div>"
        )
        synthetic_header = (
            "<th>synthetic scale</th><th>synthetic MAE</th><th>synthetic Y MAE</th>"
            "<th>synthetic HF energy ratio</th><th>synthetic MAE gain</th><th>synthetic gap to oracle</th>"
        )
        synthetic_config = data["render"].get("synthetic_hf_addback_config", {})
        synthetic_note = (
            "<p><b>Synthetic HF note:</b> this path adds deterministic generated high-frequency texture "
            "from candidate/runtime metadata only; it does not use source pixels. Scale selection in this "
            "dashboard is an offline diagnostic sweep, not yet a fixed production policy. "
            f"Scales: <code>{html.escape(str(synthetic_config.get('scale_values')))}</code></p>"
        )
    else:
        synthetic_cards = ""
        synthetic_header = ""
        synthetic_note = ""
    if has_oracle:
        oracle_cards = (
            f"<div class=\"card\"><h2>Oracle MAE</h2><p>median {summary['oracle_mae']['median']:.5f}</p>"
            f"<p>worst {summary['oracle_mae']['max']:.5f}</p></div>"
            f"<div class=\"card\"><h2>Oracle Gain</h2><p>median {summary['oracle_mae_improvement']['median']:.5f}</p>"
            f"<p>best {summary['oracle_mae_improvement']['max']:.5f}</p></div>"
        )
        oracle_header = "<th>oracle MAE</th><th>oracle Y MAE</th><th>oracle HF Y MAE</th><th>oracle MAE gain</th>"
        oracle_note = (
            "<p><b>Oracle note:</b> source-HF addback uses source DNG high-frequency content. "
            "It is a diagnostic upper bound, not a production/no-REF render path.</p>"
        )
    else:
        oracle_cards = ""
        oracle_header = ""
        oracle_note = ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR Latitude Review</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left;vertical-align:top}}
img{{max-width:220px;height:auto}}code{{color:#b7d7ff}}.contact{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR Latitude Review</h1>
<p>Source DNG: <code>{html.escape(data['source_dng'])}</code></p>
<p>Candidate DNG: <code>{html.escape(data['candidate_dng'])}</code></p>
{synthetic_note}
{oracle_note}
<div class="grid">
<div class="card"><h2>Rows</h2><p>{summary['row_count']}</p></div>
<div class="card"><h2>MAE</h2><p>median {summary['mae']['median']:.5f}</p><p>worst {summary['mae']['max']:.5f}</p></div>
<div class="card"><h2>Y MAE</h2><p>median {summary['y_mae']['median']:.5f}</p><p>worst {summary['y_mae']['max']:.5f}</p></div>
<div class="card"><h2>LF Y MAE</h2><p>median {summary['lf_y_mae']['median']:.5f}</p><p>worst {summary['lf_y_mae']['max']:.5f}</p></div>
<div class="card"><h2>HF Y MAE</h2><p>median {summary['hf_y_mae']['median']:.5f}</p><p>worst {summary['hf_y_mae']['max']:.5f}</p></div>
<div class="card"><h2>HF Corr</h2><p>median {summary['hf_y_correlation']['median']:.5f}</p><p>min {summary['hf_y_correlation']['min']:.5f}</p></div>
<div class="card"><h2>PSNR</h2><p>median {summary['psnr_db']['median']:.2f} dB</p><p>worst {summary['psnr_db']['min']:.2f} dB</p></div>
{synthetic_cards}
{oracle_cards}
</div>
<img class="contact" src="{html.escape(contact)}">
<table><tr><th>crop</th><th>EV</th><th>MAE</th><th>Y MAE</th><th>LF Y MAE</th><th>HF Y MAE</th><th>HF energy ratio</th><th>HF corr</th>{synthetic_header}{oracle_header}<th>PSNR</th><th>highlight Y MAE</th><th>shadow Y MAE</th><th>error</th></tr>
{''.join(table_rows)}
</table></body></html>
"""


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panels_dir = args.output_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    exposures = [float(v) for v in args.ev]
    source_sha = sha256_file(args.source_dng)
    candidate_sha = sha256_file(args.candidate_dng)
    noise_sidecar = load_noise_sidecar(args.synthetic_hf_sidecar)
    noise_sigma_norm = noise_sidecar_sigma_norm(noise_sidecar)
    synthetic_hf_scales: list[float] = []
    if args.synthetic_hf_addback:
        if args.synthetic_hf_scale:
            synthetic_hf_scales = [float(v) for v in args.synthetic_hf_scale]
        elif noise_sigma_norm is not None:
            multipliers = args.synthetic_hf_multiplier or [1.0, 2.0, 4.0, 8.0, 12.0, 16.0]
            synthetic_hf_scales = [float(noise_sigma_norm * multiplier) for multiplier in multipliers]
        else:
            synthetic_hf_scales = [0.0025, 0.005, 0.01, 0.02, 0.04, 0.08]
    rows: list[dict[str, Any]] = []
    render_times: list[dict[str, Any]] = []
    for ev in exposures:
        t0 = time.perf_counter()
        ref = render_rawpy(args.source_dng, ev, args.output_bps, args.half_size)
        t1 = time.perf_counter()
        cand = render_rawpy(args.candidate_dng, ev, args.output_bps, args.half_size)
        t2 = time.perf_counter()
        source_shape_before_common_crop = list(ref.shape)
        candidate_shape_before_common_crop = list(cand.shape)
        if ref.shape != cand.shape:
            common_h = min(ref.shape[0], cand.shape[0])
            common_w = min(ref.shape[1], cand.shape[1])
            if not args.allow_common_crop:
                raise ValueError(
                    f"render shape mismatch: source {ref.shape}, candidate {cand.shape}; "
                    f"rerun with --allow-common-crop to compare {common_w}x{common_h}"
                )
            ref = ref[:common_h, :common_w]
            cand = cand[:common_h, :common_w]
        height, width = ref.shape[:2]
        crop = min(args.crop_size, width, height)
        render_times.append(
            {
                "ev": ev,
                "source_s": t1 - t0,
                "candidate_s": t2 - t1,
                "shape": [height, width, 3],
                "source_shape_before_common_crop": source_shape_before_common_crop,
                "candidate_shape_before_common_crop": candidate_shape_before_common_crop,
            }
        )
        for crop_name, x, y in crop_starts(width, height, crop):
            ref_crop = ref[y : y + crop, x : x + crop]
            cand_crop = cand[y : y + crop, x : x + crop]
            metrics = crop_metrics(ref_crop, cand_crop)
            safe = f"{crop_name}_ev{ev:+.0f}".replace("+", "p").replace("-", "m")
            ref_path = panels_dir / f"{safe}_source.jpg"
            cand_path = panels_dir / f"{safe}_candidate.jpg"
            err_path = panels_dir / f"{safe}_error.jpg"
            image_from_rgb(ref_crop).save(ref_path, quality=92)
            image_from_rgb(cand_crop).save(cand_path, quality=92)
            error_image(ref_crop, cand_crop, args.error_scale).save(err_path, quality=92)
            panels = [
                {"kind": "source", "path": str(ref_path)},
                {"kind": "candidate", "path": str(cand_path)},
                {"kind": "error", "path": str(err_path)},
            ]
            if args.synthetic_hf_addback:
                synthetic_trials = []
                for scale in synthetic_hf_scales:
                    seed = stable_seed(args.synthetic_hf_seed, candidate_sha, crop_name, ev, x, y, crop)
                    synthetic_crop = synthetic_hf_addback(
                        cand_crop,
                        scale=scale,
                        seed=seed,
                        block=args.synthetic_hf_block,
                        color=args.synthetic_hf_color,
                    )
                    synthetic_metrics = crop_metrics(ref_crop, synthetic_crop)
                    synthetic_trials.append((synthetic_metrics["mae"], scale, synthetic_metrics, synthetic_crop))
                synthetic_trials.sort(key=lambda trial: trial[0])
                _, best_scale, best_synthetic_metrics, best_synthetic_crop = synthetic_trials[0]
                synthetic_path = panels_dir / f"{safe}_synthetic_hf.jpg"
                synthetic_err_path = panels_dir / f"{safe}_synthetic_hf_error.jpg"
                image_from_rgb(best_synthetic_crop).save(synthetic_path, quality=92)
                error_image(ref_crop, best_synthetic_crop, args.error_scale).save(synthetic_err_path, quality=92)
                panels += [
                    {"kind": "synthetic_hf", "path": str(synthetic_path)},
                    {"kind": "synthetic_hf_error", "path": str(synthetic_err_path)},
                ]
                metrics.update(
                    {
                        "synthetic_hf_best_scale": best_scale,
                        "synthetic_hf_mae": best_synthetic_metrics["mae"],
                        "synthetic_hf_y_mae": best_synthetic_metrics["y_mae"],
                        "synthetic_hf_lf_y_mae": best_synthetic_metrics["lf_y_mae"],
                        "synthetic_hf_hf_y_mae": best_synthetic_metrics["hf_y_mae"],
                        "synthetic_hf_y_energy_ratio": best_synthetic_metrics["hf_y_energy_ratio"],
                        "synthetic_hf_mae_improvement": metrics["mae"] - best_synthetic_metrics["mae"],
                        "synthetic_hf_y_mae_improvement": metrics["y_mae"] - best_synthetic_metrics["y_mae"],
                        "synthetic_hf_trials": [
                            {
                                "scale": scale,
                                "mae": trial_metrics["mae"],
                                "y_mae": trial_metrics["y_mae"],
                                "hf_y_mae": trial_metrics["hf_y_mae"],
                                "hf_y_energy_ratio": trial_metrics["hf_y_energy_ratio"],
                                "hf_y_correlation": trial_metrics["hf_y_correlation"],
                            }
                            for _, scale, trial_metrics, _ in synthetic_trials
                        ],
                        "synthetic_hf_note": "generated_high_frequency_texture_no_source_pixels_used",
                    }
                )
            if args.oracle_hf_addback:
                oracle_crop = oracle_hf_addback(ref_crop, cand_crop, args.oracle_hf_block)
                oracle_metrics = crop_metrics(ref_crop, oracle_crop)
                oracle_path = panels_dir / f"{safe}_oracle_source_hf.jpg"
                oracle_err_path = panels_dir / f"{safe}_oracle_error.jpg"
                image_from_rgb(oracle_crop).save(oracle_path, quality=92)
                error_image(ref_crop, oracle_crop, args.error_scale).save(oracle_err_path, quality=92)
                panels += [
                    {"kind": "oracle", "path": str(oracle_path)},
                    {"kind": "oracle_error", "path": str(oracle_err_path)},
                ]
                metrics.update(
                    {
                        "oracle_mae": oracle_metrics["mae"],
                        "oracle_y_mae": oracle_metrics["y_mae"],
                        "oracle_lf_y_mae": oracle_metrics["lf_y_mae"],
                        "oracle_hf_y_mae": oracle_metrics["hf_y_mae"],
                        "oracle_hf_y_energy_ratio": oracle_metrics["hf_y_energy_ratio"],
                        "oracle_mae_improvement": metrics["mae"] - oracle_metrics["mae"],
                        "oracle_y_mae_improvement": metrics["y_mae"] - oracle_metrics["y_mae"],
                        "oracle_note": "source_high_frequency_content_used_for_diagnostic_only",
                    }
                )
                if "synthetic_hf_mae" in metrics:
                    metrics["synthetic_hf_oracle_mae_gap"] = metrics["synthetic_hf_mae"] - oracle_metrics["mae"]
                    metrics["synthetic_hf_oracle_y_mae_gap"] = metrics["synthetic_hf_y_mae"] - oracle_metrics["y_mae"]
            rows.append(
                {
                    "crop": crop_name,
                    "ev": ev,
                    "crop_xy": [x, y],
                    "crop_size": crop,
                    **metrics,
                    "panels": panels,
                }
            )
        del ref
        del cand
    rows_sorted = sorted(rows, key=lambda row: row["mae"], reverse=True)
    contact = args.output_dir / "contact_sheet.jpg"
    write_contact_sheet(contact, rows_sorted, args.contact_rows)
    summary = {
        "row_count": len(rows),
        "mae": stats([float(row["mae"]) for row in rows]),
        "y_mae": stats([float(row["y_mae"]) for row in rows]),
        "lf_y_mae": stats([float(row["lf_y_mae"]) for row in rows if row["lf_y_mae"] is not None]),
        "lf_y_bias": stats([float(row["lf_y_bias"]) for row in rows if row["lf_y_bias"] is not None]),
        "hf_y_mae": stats([float(row["hf_y_mae"]) for row in rows if row["hf_y_mae"] is not None]),
        "hf_y_rmse": stats([float(row["hf_y_rmse"]) for row in rows if row["hf_y_rmse"] is not None]),
        "hf_y_energy_ratio": stats([float(row["hf_y_energy_ratio"]) for row in rows if row["hf_y_energy_ratio"] is not None]),
        "hf_y_energy_delta": stats([float(row["hf_y_energy_delta"]) for row in rows if row["hf_y_energy_delta"] is not None]),
        "hf_y_correlation": stats([float(row["hf_y_correlation"]) for row in rows if row["hf_y_correlation"] is not None]),
        "psnr_db": stats([float(row["psnr_db"]) for row in rows]),
        "highlight_y_mae": stats([float(row["highlight_y_mae"]) for row in rows if row["highlight_y_mae"] is not None]),
        "shadow_y_mae": stats([float(row["shadow_y_mae"]) for row in rows if row["shadow_y_mae"] is not None]),
        "render_times": render_times,
    }
    if args.oracle_hf_addback:
        summary.update(
            {
                "oracle_mae": stats([float(row["oracle_mae"]) for row in rows if "oracle_mae" in row]),
                "oracle_y_mae": stats([float(row["oracle_y_mae"]) for row in rows if "oracle_y_mae" in row]),
                "oracle_hf_y_mae": stats([float(row["oracle_hf_y_mae"]) for row in rows if row.get("oracle_hf_y_mae") is not None]),
                "oracle_mae_improvement": stats([float(row["oracle_mae_improvement"]) for row in rows if "oracle_mae_improvement" in row]),
                "oracle_y_mae_improvement": stats([float(row["oracle_y_mae_improvement"]) for row in rows if "oracle_y_mae_improvement" in row]),
            }
        )
    if args.synthetic_hf_addback:
        summary.update(
            {
                "synthetic_hf_mae": stats([float(row["synthetic_hf_mae"]) for row in rows if "synthetic_hf_mae" in row]),
                "synthetic_hf_y_mae": stats([float(row["synthetic_hf_y_mae"]) for row in rows if "synthetic_hf_y_mae" in row]),
                "synthetic_hf_hf_y_mae": stats([float(row["synthetic_hf_hf_y_mae"]) for row in rows if row.get("synthetic_hf_hf_y_mae") is not None]),
                "synthetic_hf_y_energy_ratio": stats(
                    [float(row["synthetic_hf_y_energy_ratio"]) for row in rows if row.get("synthetic_hf_y_energy_ratio") is not None]
                ),
                "synthetic_hf_mae_improvement": stats(
                    [float(row["synthetic_hf_mae_improvement"]) for row in rows if "synthetic_hf_mae_improvement" in row]
                ),
                "synthetic_hf_y_mae_improvement": stats(
                    [float(row["synthetic_hf_y_mae_improvement"]) for row in rows if "synthetic_hf_y_mae_improvement" in row]
                ),
                "synthetic_hf_oracle_mae_gap": stats(
                    [float(row["synthetic_hf_oracle_mae_gap"]) for row in rows if "synthetic_hf_oracle_mae_gap" in row]
                ),
            }
        )
    artifacts: dict[str, Any] = {"contact_sheet": artifact_ref(contact)}
    if args.synthetic_hf_sidecar:
        artifacts["synthetic_hf_sidecar"] = artifact_ref(args.synthetic_hf_sidecar)
    data = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "source_dng": str(args.source_dng),
        "candidate_dng": str(args.candidate_dng),
        "source_dng_sha256": source_sha,
        "candidate_dng_sha256": candidate_sha,
        "render": {
            "engine": "rawpy/libraw",
            "use_camera_wb": True,
            "no_auto_bright": True,
            "output_bps": args.output_bps,
            "gamma": [2.222, 4.5],
            "demosaic": "AHD",
            "user_flip": 0,
            "half_size": args.half_size,
            "allow_common_crop": args.allow_common_crop,
            "oracle_hf_addback": args.oracle_hf_addback,
            "oracle_hf_block": args.oracle_hf_block if args.oracle_hf_addback else None,
            "synthetic_hf_addback": args.synthetic_hf_addback,
            "synthetic_hf_addback_config": {
                "sidecar": str(args.synthetic_hf_sidecar) if args.synthetic_hf_sidecar else None,
                "sidecar_schema": noise_sidecar.get("schema") if noise_sidecar else None,
                "sidecar_camera": noise_sidecar.get("camera", {}) if noise_sidecar else None,
                "noise_sigma_norm": noise_sigma_norm,
                "scale_values": synthetic_hf_scales,
                "block": args.synthetic_hf_block,
                "color": args.synthetic_hf_color,
                "seed": args.synthetic_hf_seed,
                "selection": "best_mae_against_source_for_offline_diagnostic_only",
            }
            if args.synthetic_hf_addback
            else None,
        },
        "summary": summary,
        "rows": rows,
        "contact_sheet": str(contact),
        "artifacts": artifacts,
    }
    out_json = args.output_dir / "latitude_review.json"
    out_html = args.output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, args.output_dir), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dng", type=Path, required=True)
    ap.add_argument("--candidate-dng", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--ev", action="append", type=float, default=list(DEFAULT_EXPOSURES))
    ap.add_argument("--crop-size", type=int, default=768)
    ap.add_argument("--output-bps", type=int, choices=(8, 16), default=16)
    ap.add_argument("--half-size", action="store_true")
    ap.add_argument("--allow-common-crop", action="store_true")
    ap.add_argument("--oracle-hf-addback", action="store_true")
    ap.add_argument("--oracle-hf-block", type=int, default=16)
    ap.add_argument("--synthetic-hf-addback", action="store_true")
    ap.add_argument("--synthetic-hf-sidecar", type=Path)
    ap.add_argument("--synthetic-hf-scale", action="append", type=float)
    ap.add_argument("--synthetic-hf-multiplier", action="append", type=float)
    ap.add_argument("--synthetic-hf-block", type=int, default=16)
    ap.add_argument("--synthetic-hf-color", action="store_true")
    ap.add_argument("--synthetic-hf-seed", type=int, default=20260630)
    ap.add_argument("--error-scale", type=float, default=0.06)
    ap.add_argument("--contact-rows", type=int, default=9)
    args = ap.parse_args()
    data = build_review(args)
    print(
        json.dumps(
            {
                "receipt": str(args.output_dir / "latitude_review.json"),
                "dashboard": str(args.output_dir / "index.html"),
                "rows": data["summary"]["row_count"],
                "median_mae": data["summary"]["mae"]["median"],
                "worst_mae": data["summary"]["mae"]["max"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
