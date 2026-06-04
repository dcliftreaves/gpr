#!/usr/bin/env python3
"""Build a dashboard for a raw clean-target CNN checkpoint."""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import torch

from train_raw_clean_ref_cnn import RAW_SCALE, RawCleanCNN, deinterleave, interleave


def save_u8(path: Path, arr: np.ndarray, lo: float, hi: float) -> None:
    img = np.clip((arr - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    Image.fromarray((img * 255.0).astype(np.uint8)).save(path)


def load_model(path: Path) -> RawCleanCNN:
    ckpt = torch.load(path, map_location="cpu")
    model = RawCleanCNN(int(ckpt["width"]))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def run_model(model: RawCleanCNN, raw: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    raw_ch = deinterleave(raw) / RAW_SCALE
    sigma_ch = deinterleave(sigma) / RAW_SCALE
    x = torch.from_numpy(np.concatenate([raw_ch, sigma_ch], axis=0)[None])
    with torch.no_grad():
        pred = model(x).cpu().numpy()[0]
    return interleave(pred) * RAW_SCALE


def build(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model(args.checkpoint)
    data = json.loads(args.targets.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in data["rows"]:
        z = np.load(row["npz"])
        raw = z["raw"].astype(np.float32)
        clean = z["clean"].astype(np.float32)
        exact = z["exact_residual"].astype(np.float32)
        sigma = z["sigma"].astype(np.float32)
        pred_clean = run_model(model, raw, sigma)
        pred_addback = pred_clean + exact
        clean_err = pred_clean - clean
        addback_err = pred_addback - raw
        base = f"{row['image_id']}_{row['crop']}"
        image_dir = args.out_dir / row["image_id"]
        image_dir.mkdir(parents=True, exist_ok=True)
        hi = float(np.percentile(raw, 99.5))
        paths = {
            "raw": image_dir / f"{base}_raw.png",
            "clean_target": image_dir / f"{base}_clean_target.png",
            "model_clean": image_dir / f"{base}_model_clean.png",
            "clean_error_x16": image_dir / f"{base}_clean_error_x16.png",
            "addback_error_x16": image_dir / f"{base}_addback_error_x16.png",
        }
        save_u8(paths["raw"], raw, lo=float(np.min(raw)), hi=hi)
        save_u8(paths["clean_target"], clean, lo=float(np.min(raw)), hi=hi)
        save_u8(paths["model_clean"], pred_clean, lo=float(np.min(raw)), hi=hi)
        save_u8(paths["clean_error_x16"], clean_err * args.error_gain + 128.0, lo=0.0, hi=255.0)
        save_u8(paths["addback_error_x16"], addback_err * args.error_gain + 128.0, lo=0.0, hi=255.0)
        rows.append({
            "image_id": row["image_id"],
            "crop": row["crop"],
            "iso": row["iso"],
            "accepted": row.get("accepted", True),
            "clean_l1": float(np.mean(np.abs(pred_clean - clean)) / RAW_SCALE),
            "addback_l1": float(np.mean(np.abs(pred_addback - raw)) / RAW_SCALE),
            "clean_rmse_counts": float(np.sqrt(np.mean(clean_err * clean_err))),
            "addback_rmse_counts": float(np.sqrt(np.mean(addback_err * addback_err))),
            "artifacts": {k: str(v) for k, v in paths.items()},
        })

    accepted = [row for row in rows if row["accepted"]]
    rejected = [row for row in rows if not row["accepted"]]

    def mean_or_none(items: list[dict[str, Any]], key: str) -> float | None:
        if not items:
            return None
        return float(np.mean([r[key] for r in items]))

    summary = {
        "checkpoint": str(args.checkpoint),
        "targets": str(args.targets),
        "rows": rows,
        "mean_clean_rmse_counts": float(np.mean([r["clean_rmse_counts"] for r in rows])),
        "mean_addback_rmse_counts": float(np.mean([r["addback_rmse_counts"] for r in rows])),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_mean_clean_rmse_counts": mean_or_none(accepted, "clean_rmse_counts"),
        "accepted_mean_addback_rmse_counts": mean_or_none(accepted, "addback_rmse_counts"),
        "rejected_mean_clean_rmse_counts": mean_or_none(rejected, "clean_rmse_counts"),
        "rejected_mean_addback_rmse_counts": mean_or_none(rejected, "addback_rmse_counts"),
    }
    (args.out_dir / "raw_clean_model_dashboard.json").write_text(json.dumps(summary, indent=2))
    build_html(summary, args.out_dir / "raw_clean_model_dashboard.html")
    return summary


def build_html(summary: dict[str, Any], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.5f}"
        return escape(str(v))

    html = [
        "<!doctype html><meta charset='utf-8'><title>Raw Clean Model Dashboard</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}"
        ".card{border:1px solid #d8dee6;border-radius:8px;padding:10px;background:white}img{width:100%;height:auto;background:#111}</style>",
        "<h1>Raw Clean Model Dashboard</h1>",
        f"<p>Checkpoint: <code>{escape(summary['checkpoint'])}</code></p>",
        f"<p>Accepted target RMSE: <b>{fmt(summary['accepted_mean_clean_rmse_counts'])}</b> raw counts; "
        f"all-target RMSE: <b>{fmt(summary['mean_clean_rmse_counts'])}</b> raw counts.</p>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Accepted target</th>"
        "<th>clean RMSE counts</th><th>exact-addback RMSE counts</th></tr></thead><tbody>",
    ]
    for row in summary["rows"]:
        html.append("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"],
            row["crop"],
            row["iso"],
            row["accepted"],
            row["clean_rmse_counts"],
            row["addback_rmse_counts"],
        ]) + "</tr>")
    html.append("</tbody></table><div class='grid'>")
    for row in summary["rows"]:
        html.append(f"<div class='card'><h3>{escape(row['image_id'])} {escape(row['crop'])}</h3>")
        for label, path in row["artifacts"].items():
            rel = Path(path).relative_to(out.parent)
            html.append(f"<p>{escape(label)}</p><img src='{escape(str(rel))}'>")
        html.append("</div>")
    html.append("</div>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--error-gain", type=float, default=16.0)
    args = ap.parse_args()
    summary = build(args)
    print(args.out_dir / "raw_clean_model_dashboard.json")
    print(args.out_dir / "raw_clean_model_dashboard.html")
    print(f"mean clean rmse counts {summary['mean_clean_rmse_counts']:.3f}")
    print(f"mean addback rmse counts {summary['mean_addback_rmse_counts']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
