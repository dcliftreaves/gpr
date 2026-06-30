#!/usr/bin/env python3
"""Analyze premium still-SR HF residual targets by band and brightness.

This diagnostic uses the supervised HF residual target NPZ. It does not train
or render a production image. Its purpose is to decide what the next no-REF
model needs to learn: fine noise, mid texture, coarse structure, or
brightness/exposure-specific residuals.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


SCHEMA = "gpr.premium_still_sr_hf_residual_band_analysis.v1"
LUMA_WEIGHTS = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)


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


def luma(rgb: np.ndarray) -> np.ndarray:
    return np.tensordot(rgb.astype(np.float32), LUMA_WEIGHTS, axes=([-1], [0]))


def block_lowpass(arr: np.ndarray, block: int) -> np.ndarray:
    if block <= 1:
        return arr.copy()
    h, w = arr.shape[:2]
    extra = arr.shape[2:] if arr.ndim > 2 else ()
    pad_h = ((h + block - 1) // block) * block
    pad_w = ((w + block - 1) // block) * block
    pad_spec = [(0, pad_h - h), (0, pad_w - w)] + [(0, 0) for _ in extra]
    padded = np.pad(arr, pad_spec, mode="edge")
    reshaped = padded.reshape(pad_h // block, block, pad_w // block, block, *extra)
    low = reshaped.mean(axis=(1, 3))
    return np.repeat(np.repeat(low, block, axis=0), block, axis=1)[:h, :w]


def band_split(arr: np.ndarray, fine_block: int, mid_block: int, coarse_block: int) -> dict[str, np.ndarray]:
    low_fine = block_lowpass(arr, fine_block)
    low_mid = block_lowpass(arr, mid_block)
    low_coarse = block_lowpass(arr, coarse_block)
    return {
        "fine": arr - low_fine,
        "mid": low_fine - low_mid,
        "coarse": low_mid - low_coarse,
        "very_coarse": low_coarse,
    }


def mean_abs(arr: np.ndarray, mask: np.ndarray | None = None) -> float:
    vals = np.abs(arr) if mask is None else np.abs(arr)[mask]
    return float(np.mean(vals)) if vals.size else 0.0


def rmse(arr: np.ndarray, mask: np.ndarray | None = None) -> float:
    vals = arr if mask is None else arr[mask]
    return float(np.sqrt(np.mean(vals * vals))) if vals.size else 0.0


def corr(a: np.ndarray, b: np.ndarray) -> float | None:
    av = a.reshape(-1).astype(np.float64)
    bv = b.reshape(-1).astype(np.float64)
    av = av - float(np.mean(av))
    bv = bv - float(np.mean(bv))
    den = float(np.sqrt(np.sum(av * av) * np.sum(bv * bv)))
    return float(np.sum(av * bv) / den) if den > 1.0e-12 else None


def percentile_abs(arr: np.ndarray, pct: float, mask: np.ndarray | None = None) -> float:
    vals = np.abs(arr) if mask is None else np.abs(arr)[mask]
    return float(np.percentile(vals, pct)) if vals.size else 0.0


def normalize_panel(arr: np.ndarray, scale: float | None = None) -> np.ndarray:
    if arr.ndim == 2:
        arr = np.repeat(arr[:, :, None], 3, axis=2)
    if scale is None:
        scale = max(float(np.percentile(np.abs(arr), 99.0)), 1.0e-6)
    return np.clip(arr / scale * 0.5 + 0.5, 0.0, 1.0)


def image_from_float(arr: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "RGB")


def row_analysis(
    idx: int,
    row: dict[str, Any],
    candidate: np.ndarray,
    residual: np.ndarray,
    source_hf: np.ndarray,
    *,
    fine_block: int,
    mid_block: int,
    coarse_block: int,
) -> dict[str, Any]:
    target = np.clip(candidate + residual, 0.0, 1.0)
    cand_y = luma(candidate)
    target_y = luma(target)
    residual_y = luma(residual)
    source_hf_y = luma(source_hf)
    candidate_hf_y = source_hf_y - residual_y
    residual_bands = band_split(residual_y, fine_block, mid_block, coarse_block)
    target_bands = band_split(target_y, fine_block, mid_block, coarse_block)
    candidate_bands = band_split(cand_y, fine_block, mid_block, coarse_block)
    total_abs = max(mean_abs(residual_y), 1.0e-12)
    brightness_masks = {
        "shadow": target_y < 0.10,
        "midtone": (target_y >= 0.10) & (target_y < 0.75),
        "bright": (target_y >= 0.75) & (target_y < 0.92),
        "near_clip": target_y >= 0.92,
    }
    band_stats: dict[str, Any] = {}
    for name, band in residual_bands.items():
        band_stats[name] = {
            "abs_mean": mean_abs(band),
            "rmse": rmse(band),
            "p95_abs": percentile_abs(band, 95.0),
            "share_of_residual_abs": mean_abs(band) / total_abs,
            "corr_with_candidate_band": corr(band, candidate_bands[name]),
            "corr_with_target_band": corr(band, target_bands[name]),
        }
    brightness: dict[str, Any] = {}
    for name, mask in brightness_masks.items():
        brightness[name] = {
            "pixel_fraction": float(np.mean(mask)),
            "residual_abs_mean": mean_abs(residual_y, mask),
            "residual_rmse": rmse(residual_y, mask),
            "residual_p95_abs": percentile_abs(residual_y, 95.0, mask),
        }
    grad_x = np.zeros_like(cand_y)
    grad_y = np.zeros_like(cand_y)
    grad_x[:, 1:] = cand_y[:, 1:] - cand_y[:, :-1]
    grad_y[1:, :] = cand_y[1:, :] - cand_y[:-1, :]
    grad_mag = np.sqrt(grad_x * grad_x + grad_y * grad_y)
    return {
        "index": idx,
        "crop": row.get("crop"),
        "ev": float(row.get("ev", 0.0)),
        "crop_xy": row.get("crop_xy"),
        "residual_y_abs_mean": mean_abs(residual_y),
        "residual_y_rmse": rmse(residual_y),
        "residual_y_p95_abs": percentile_abs(residual_y, 95.0),
        "source_hf_y_abs_mean": mean_abs(source_hf_y),
        "candidate_hf_y_abs_mean": mean_abs(candidate_hf_y),
        "hf_y_energy_ratio": mean_abs(candidate_hf_y) / max(mean_abs(source_hf_y), 1.0e-12),
        "residual_corr_with_candidate_luma": corr(residual_y, cand_y),
        "residual_corr_with_target_luma": corr(residual_y, target_y),
        "residual_corr_with_candidate_gradient": corr(np.abs(residual_y), grad_mag),
        "bands": band_stats,
        "brightness": brightness,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    band_names = ["fine", "mid", "coarse", "very_coarse"]
    brightness_names = ["shadow", "midtone", "bright", "near_clip"]
    out: dict[str, Any] = {
        "row_count": len(rows),
        "residual_y_abs_mean": stats([row["residual_y_abs_mean"] for row in rows]),
        "residual_y_p95_abs": stats([row["residual_y_p95_abs"] for row in rows]),
        "hf_y_energy_ratio": stats([row["hf_y_energy_ratio"] for row in rows]),
        "residual_corr_with_candidate_gradient": stats(
            [float(row["residual_corr_with_candidate_gradient"]) for row in rows if row["residual_corr_with_candidate_gradient"] is not None]
        ),
        "bands": {},
        "brightness": {},
    }
    for band in band_names:
        out["bands"][band] = {
            "abs_mean": stats([row["bands"][band]["abs_mean"] for row in rows]),
            "share_of_residual_abs": stats([row["bands"][band]["share_of_residual_abs"] for row in rows]),
            "corr_with_target_band": stats(
                [float(row["bands"][band]["corr_with_target_band"]) for row in rows if row["bands"][band]["corr_with_target_band"] is not None]
            ),
        }
    for name in brightness_names:
        active = [row for row in rows if row["brightness"][name]["pixel_fraction"] > 0.0]
        out["brightness"][name] = {
            "active_rows": len(active),
            "pixel_fraction": stats([row["brightness"][name]["pixel_fraction"] for row in rows]),
            "residual_abs_mean": stats([row["brightness"][name]["residual_abs_mean"] for row in active]),
            "residual_p95_abs": stats([row["brightness"][name]["residual_p95_abs"] for row in active]),
        }
    by_ev: dict[str, Any] = {}
    for ev in sorted({float(row["ev"]) for row in rows}):
        ev_rows = [row for row in rows if abs(float(row["ev"]) - ev) < 1.0e-6]
        by_ev[f"{ev:+.0f}"] = aggregate_without_ev(ev_rows)
    out["by_ev"] = by_ev
    return out


def aggregate_without_ev(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "residual_y_abs_mean": stats([row["residual_y_abs_mean"] for row in rows]),
        "residual_y_p95_abs": stats([row["residual_y_p95_abs"] for row in rows]),
        "band_share": {
            band: stats([row["bands"][band]["share_of_residual_abs"] for row in rows])
            for band in ["fine", "mid", "coarse", "very_coarse"]
        },
        "brightness_abs_mean": {
            name: stats(
                [row["brightness"][name]["residual_abs_mean"] for row in rows if row["brightness"][name]["pixel_fraction"] > 0.0]
            )
            for name in ["shadow", "midtone", "bright", "near_clip"]
        },
    }


def write_contact_sheet(path: Path, data: Any, rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = sorted(rows, key=lambda row: row["residual_y_abs_mean"], reverse=True)[:max_rows]
    if not selected:
        return
    panel = 256
    pad = 10
    label_h = 42
    headers = ["candidate", "target", "residual Y", "fine", "mid", "coarse"]
    sheet = Image.new("RGB", (len(headers) * (panel + pad) + pad, len(selected) * (panel + label_h + pad) + pad), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    inputs = data["inputs"]
    residuals = data["hf_residuals"]
    for row_i, row in enumerate(selected):
        idx = int(row["index"])
        cand = inputs[idx].astype(np.float32)
        residual = residuals[idx].astype(np.float32)
        target = np.clip(cand + residual, 0.0, 1.0)
        residual_y = luma(residual)
        bands = band_split(residual_y, data["fine_block"], data["mid_block"], data["coarse_block"])
        scale = max(float(np.percentile(np.abs(residual_y), 99.0)), 1.0e-6)
        panels = [
            cand,
            target,
            normalize_panel(residual_y, scale),
            normalize_panel(bands["fine"], scale),
            normalize_panel(bands["mid"], scale),
            normalize_panel(bands["coarse"], scale),
        ]
        y0 = pad + row_i * (panel + label_h + pad)
        title = f"{row['crop']} EV {row['ev']:+.0f} residual {row['residual_y_abs_mean']:.4f}"
        draw.text((pad, y0), title, fill=(245, 245, 245))
        for col, img_arr in enumerate(panels):
            x0 = pad + col * (panel + pad)
            draw.text((x0, y0 + 20), headers[col], fill=(190, 190, 190))
            image = image_from_float(img_arr).resize((panel, panel), Image.Resampling.BILINEAR)
            sheet.paste(image, (x0, y0 + label_h))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def render_html(receipt: dict[str, Any], output_dir: Path) -> str:
    contact = Path(receipt["artifacts"]["contact_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    rows = sorted(receipt["rows"], key=lambda row: row["residual_y_abs_mean"], reverse=True)
    band_cards = []
    for name, band in receipt["summary"]["bands"].items():
        band_cards.append(
            f"<div class='card'><h2>{html.escape(name)}</h2>"
            f"<p>share median {band['share_of_residual_abs']['median']:.2f}x</p>"
            f"<p>abs mean {band['abs_mean']['median']:.5f}</p></div>"
        )
    bright_cards = []
    for name, item in receipt["summary"]["brightness"].items():
        bright_cards.append(
            f"<div class='card'><h2>{html.escape(name)}</h2>"
            f"<p>active rows {item['active_rows']}</p>"
            f"<p>residual median {item['residual_abs_mean']['median']:.5f}</p></div>"
        )
    table = []
    for row in rows:
        table.append(
            f"<tr><td>{html.escape(str(row['crop']))}</td><td>{row['ev']:+.0f}</td>"
            f"<td>{row['residual_y_abs_mean']:.5f}</td><td>{row['hf_y_energy_ratio']:.3f}</td>"
            f"<td>{row['bands']['fine']['share_of_residual_abs']:.2f}</td>"
            f"<td>{row['bands']['mid']['share_of_residual_abs']:.2f}</td>"
            f"<td>{row['bands']['coarse']['share_of_residual_abs']:.2f}</td>"
            f"<td>{row['brightness']['near_clip']['residual_abs_mean']:.5f}</td></tr>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR HF Residual Band Analysis</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left}}
code{{color:#b7d7ff}}img{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still SR HF Residual Band Analysis</h1>
<p>Target NPZ: <code>{html.escape(receipt['targets'])}</code></p>
<p><b>Policy:</b> diagnostic only. Source-derived HF residuals are analyzed to decide the next no-REF target; no production render path uses source content.</p>
<div class="grid">
<div class="card"><h2>Rows</h2><p>{receipt['summary']['row_count']}</p></div>
<div class="card"><h2>Residual Y</h2><p>median {receipt['summary']['residual_y_abs_mean']['median']:.5f}</p></div>
<div class="card"><h2>HF energy ratio</h2><p>median {receipt['summary']['hf_y_energy_ratio']['median']:.3f}</p></div>
{''.join(band_cards)}
{''.join(bright_cards)}
</div>
<img src="{html.escape(contact)}">
<table><tr><th>crop</th><th>EV</th><th>Y residual</th><th>HF energy ratio</th><th>fine share</th><th>mid share</th><th>coarse share</th><th>near-clip residual</th></tr>
{''.join(table)}
</table></body></html>
"""


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    with np.load(args.targets, allow_pickle=False) as z:
        inputs = z["inputs"].astype(np.float32)
        residuals = z["hf_residuals"].astype(np.float32)
        source_hf = z["source_hf_targets"].astype(np.float32)
        meta = json.loads(str(z["meta"]))
    if inputs.shape != residuals.shape or inputs.shape != source_hf.shape:
        raise ValueError("target arrays must have matching shapes")
    rows = [
        row_analysis(
            idx,
            meta[idx],
            inputs[idx],
            residuals[idx],
            source_hf[idx],
            fine_block=args.fine_block,
            mid_block=args.mid_block,
            coarse_block=args.coarse_block,
        )
        for idx in range(inputs.shape[0])
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    contact = args.output_dir / "contact_sheet.jpg"
    write_contact_sheet(
        contact,
        {
            "inputs": inputs,
            "hf_residuals": residuals,
            "fine_block": args.fine_block,
            "mid_block": args.mid_block,
            "coarse_block": args.coarse_block,
        },
        rows,
        args.contact_rows,
    )
    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "targets": str(args.targets),
        "targets_sha256": sha256_file(args.targets),
        "config": {
            "fine_block": args.fine_block,
            "mid_block": args.mid_block,
            "coarse_block": args.coarse_block,
        },
        "policy": {
            "uses_source_hf_for_analysis": True,
            "runtime_safe": False,
            "purpose": "diagnose_next_no_ref_texture_target",
        },
        "summary": aggregate(rows),
        "rows": rows,
        "artifacts": {"contact_sheet": str(contact)},
    }
    receipt_path = args.output_dir / "band_analysis.json"
    index = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    index.write_text(render_html(receipt, args.output_dir), encoding="utf-8")
    receipt["artifacts"]["receipt"] = str(receipt_path)
    receipt["artifacts"]["dashboard"] = str(index)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--fine-block", type=int, default=4)
    ap.add_argument("--mid-block", type=int, default=16)
    ap.add_argument("--coarse-block", type=int, default=64)
    ap.add_argument("--contact-rows", type=int, default=9)
    args = ap.parse_args()
    receipt = analyze(args)
    print(
        json.dumps(
            {
                "receipt": receipt["artifacts"]["receipt"],
                "dashboard": receipt["artifacts"]["dashboard"],
                "median_residual_y_abs": receipt["summary"]["residual_y_abs_mean"]["median"],
                "median_fine_share": receipt["summary"]["bands"]["fine"]["share_of_residual_abs"]["median"],
                "median_mid_share": receipt["summary"]["bands"]["mid"]["share_of_residual_abs"]["median"],
                "median_coarse_share": receipt["summary"]["bands"]["coarse"]["share_of_residual_abs"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
