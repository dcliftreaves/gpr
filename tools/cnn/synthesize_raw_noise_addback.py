#!/usr/bin/env python3
"""Synthesize ISO-aware raw residual addback from clean-target sidecars."""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from analyze_dng_noise_profile import deinterleave, interleave, local_activity_mask, plane_validation_stats


DEFAULT_TARGETS = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_fullgate_20260604/raw_clean_ref_targets.json")
DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/synthetic_raw_noise_addback_20260604")


def save_u8(path: Path, arr: np.ndarray, lo: float, hi: float) -> None:
    img = np.clip((arr - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    Image.fromarray((img * 255.0).astype(np.uint8)).save(path)


def lag_max_abs(ch: dict[str, np.ndarray]) -> float:
    values = []
    for plane in ch.values():
        centered = plane - float(np.mean(plane))
        for axis in (0, 1):
            if axis == 0:
                a, b = centered[:-1, :], centered[1:, :]
            else:
                a, b = centered[:, :-1], centered[:, 1:]
            denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
            values.append(0.0 if denom <= 1e-9 else float(np.sum(a * b) / denom))
    return float(np.max(np.abs(values))) if values else 0.0


def synthesize(
    z: np.lib.npyio.NpzFile,
    rng: np.random.Generator,
    clip_sigma: float,
    edge_dampen: float,
) -> np.ndarray:
    exact = z["exact_residual"].astype(np.float32)
    sigma = np.maximum(z["sigma"].astype(np.float32), 1e-6)
    mask = np.clip(z["mask"].astype(np.float32), 0.0, 1.0)
    exact_rms = float(np.sqrt(np.mean(exact * exact)))
    if exact_rms <= 1e-9:
        return np.zeros_like(exact, dtype=np.float32)
    noise = rng.normal(0.0, 1.0, size=exact.shape).astype(np.float32)
    synthetic = noise * sigma * mask
    synthetic_ch = deinterleave(synthetic)
    raw_ch = deinterleave(z["raw"].astype(np.float32))
    for ch_name, plane in raw_ch.items():
        edge = ~local_activity_mask(plane, 75.0)
        synthetic_ch[ch_name][edge] *= edge_dampen
    synthetic = interleave(synthetic_ch, exact.shape)
    synth_rms = float(np.sqrt(np.mean(synthetic * synthetic)))
    if synth_rms <= 1e-9:
        return np.zeros_like(exact, dtype=np.float32)
    synthetic *= exact_rms / synth_rms
    synthetic = np.clip(synthetic, -clip_sigma * sigma, clip_sigma * sigma)
    # Re-normalize after clipping when possible.
    synth_rms = float(np.sqrt(np.mean(synthetic * synthetic)))
    if synth_rms > 1e-9:
        synthetic *= min(exact_rms / synth_rms, 1.0)
    return synthetic.astype(np.float32)


def build(args: argparse.Namespace) -> dict[str, Any]:
    data = json.loads(args.targets.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    rows = []
    for row in data["rows"]:
        z = np.load(row["npz"])
        raw = z["raw"].astype(np.float32)
        clean = z["clean"].astype(np.float32)
        exact = z["exact_residual"].astype(np.float32)
        sigma = np.maximum(z["sigma"].astype(np.float32), 1e-6)
        synthetic = synthesize(z, rng, args.clip_sigma, args.edge_dampen)
        exact_ch = deinterleave(exact)
        synthetic_ch = deinterleave(synthetic)
        raw_ch = deinterleave(raw)
        sigma_ch = deinterleave(sigma)
        exact_validation = plane_validation_stats(raw_ch, sigma_ch, exact_ch, wavelet=args.wavelet)
        synthetic_validation = plane_validation_stats(raw_ch, sigma_ch, synthetic_ch, wavelet=args.wavelet)
        exact_rms = float(np.sqrt(np.mean(exact * exact)))
        synthetic_rms = float(np.sqrt(np.mean(synthetic * synthetic)))
        sigma_rms = float(np.sqrt(np.mean(sigma * sigma)))

        image_id = row["image_id"]
        crop = row["crop"]
        base = f"{image_id}_{crop}"
        image_dir = args.out_dir / image_id
        image_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "npz": image_dir / f"{base}_synthetic_addback.npz",
            "clean": image_dir / f"{base}_clean.png",
            "exact_residual_x16": image_dir / f"{base}_exact_residual_x16.png",
            "synthetic_residual_x16": image_dir / f"{base}_synthetic_residual_x16.png",
            "exact_addback": image_dir / f"{base}_exact_addback.png",
            "synthetic_addback": image_dir / f"{base}_synthetic_addback.png",
        }
        np.savez_compressed(
            paths["npz"],
            clean=clean.astype(np.float32),
            exact_residual=exact.astype(np.float32),
            synthetic_residual=synthetic.astype(np.float32),
            exact_addback=(clean + exact).astype(np.float32),
            synthetic_addback=(clean + synthetic).astype(np.float32),
            sigma=sigma.astype(np.float32),
            raw=raw.astype(np.float32),
            image_id=np.asarray(image_id),
            crop=np.asarray(crop),
            iso=np.asarray([row["iso"]], dtype=np.int32),
            accepted=np.asarray([row.get("accepted", True)], dtype=np.bool_),
        )
        hi = float(np.percentile(raw, 99.5))
        lo = float(np.min(raw))
        save_u8(paths["clean"], clean, lo=lo, hi=hi)
        save_u8(paths["exact_residual_x16"], exact * args.residual_gain + 128.0, lo=0.0, hi=255.0)
        save_u8(paths["synthetic_residual_x16"], synthetic * args.residual_gain + 128.0, lo=0.0, hi=255.0)
        save_u8(paths["exact_addback"], clean + exact, lo=lo, hi=hi)
        save_u8(paths["synthetic_addback"], clean + synthetic, lo=lo, hi=hi)
        rows.append({
            "image_id": image_id,
            "crop": crop,
            "iso": row["iso"],
            "accepted": row.get("accepted", True),
            "exact_rms_counts": exact_rms,
            "synthetic_rms_counts": synthetic_rms,
            "sigma_rms_counts": sigma_rms,
            "exact_to_sigma_rms": exact_rms / max(sigma_rms, 1e-9),
            "synthetic_to_sigma_rms": synthetic_rms / max(sigma_rms, 1e-9),
            "exact_lag_max_abs": lag_max_abs(exact_ch),
            "synthetic_lag_max_abs": lag_max_abs(synthetic_ch),
            "exact_edge_ratio": exact_validation["edge_removed_energy_ratio"],
            "synthetic_edge_ratio": synthetic_validation["edge_removed_energy_ratio"],
            "rms_ratio": synthetic_rms / max(exact_rms, 1e-9),
            "artifacts": {k: str(v) for k, v in paths.items()},
        })

    summary = {
        "targets": str(args.targets),
        "params": {
            "seed": args.seed,
            "clip_sigma": args.clip_sigma,
            "edge_dampen": args.edge_dampen,
            "residual_gain": args.residual_gain,
            "wavelet": args.wavelet,
        },
        "rows": rows,
    }
    (args.out_dir / "synthetic_raw_noise_addback.json").write_text(json.dumps(summary, indent=2))
    build_html(summary, args.out_dir / "synthetic_raw_noise_addback.html")
    return summary


def build_html(summary: dict[str, Any], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.4f}"
        return escape(str(v))

    html = [
        "<!doctype html><meta charset='utf-8'><title>Synthetic Raw Noise Addback</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}"
        ".card{border:1px solid #d8dee6;border-radius:8px;padding:10px;background:white}img{width:100%;height:auto;background:#111}</style>",
        "<h1>Synthetic Raw Noise Addback</h1>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Accepted</th><th>exact/sigma</th><th>synthetic/sigma</th><th>rms ratio</th><th>exact lag</th><th>synthetic lag</th><th>exact edge</th><th>synthetic edge</th></tr></thead><tbody>",
    ]
    for row in summary["rows"]:
        html.append("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"], row["crop"], row["iso"], row["accepted"],
            row["exact_to_sigma_rms"], row["synthetic_to_sigma_rms"], row["rms_ratio"],
            row["exact_lag_max_abs"], row["synthetic_lag_max_abs"],
            row["exact_edge_ratio"], row["synthetic_edge_ratio"],
        ]) + "</tr>")
    html.append("</tbody></table><div class='grid'>")
    for row in summary["rows"]:
        html.append(f"<div class='card'><h3>{escape(row['image_id'])} {escape(row['crop'])}</h3>")
        for label, path in row["artifacts"].items():
            rel = Path(path).relative_to(out.parent)
            if Path(path).suffix == ".npz":
                html.append(f"<p>{escape(label)}: <a href='{escape(str(rel))}'>{escape(Path(path).name)}</a></p>")
            else:
                html.append(f"<p>{escape(label)}</p><img src='{escape(str(rel))}'>")
        html.append("</div>")
    html.append("</div>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=20260604)
    ap.add_argument("--clip-sigma", type=float, default=1.0)
    ap.add_argument("--edge-dampen", type=float, default=0.70)
    ap.add_argument("--residual-gain", type=float, default=16.0)
    ap.add_argument("--wavelet", default="sym4")
    args = ap.parse_args()
    summary = build(args)
    print(args.out_dir / "synthetic_raw_noise_addback.json")
    print(args.out_dir / "synthetic_raw_noise_addback.html")
    accepted = [r for r in summary["rows"] if r["accepted"]]
    if accepted:
        print("accepted mean rms ratio", float(np.mean([r["rms_ratio"] for r in accepted])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
