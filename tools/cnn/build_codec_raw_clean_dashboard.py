#!/usr/bin/env python3
"""Build a dashboard for a codec-raw-clean SR checkpoint."""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import torch

from train_codec_raw_clean_sr import RAW_SCALE, CodecRawCleanSR, PairDataset


def save_u8(path: Path, arr: np.ndarray, lo: float, hi: float) -> None:
    img = np.clip((arr - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    Image.fromarray((img * 255.0).astype(np.uint8)).save(path)


def interleave(ch: np.ndarray) -> np.ndarray:
    _, h, w = ch.shape
    out = np.zeros((h * 2, w * 2), dtype=np.float32)
    out[0::2, 0::2] = ch[0]
    out[0::2, 1::2] = ch[1]
    out[1::2, 0::2] = ch[2]
    out[1::2, 1::2] = ch[3]
    return out


def load_model(path: Path) -> CodecRawCleanSR:
    ckpt = torch.load(path, map_location="cpu")
    model = CodecRawCleanSR(int(ckpt["width"]))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def build(args: argparse.Namespace) -> dict[str, Any]:
    dataset = PairDataset(args.pairs, include_rejected=True)
    model = load_model(args.checkpoint)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with torch.no_grad():
        for idx in range(len(dataset.codec)):
            codec_up = dataset.codec_up[idx]
            sigma = dataset.sigma[idx]
            clean = dataset.clean[idx]
            raw = dataset.raw[idx]
            exact = dataset.exact[idx]
            x = torch.from_numpy(np.concatenate([codec_up, sigma], axis=0)[None])
            pred = model(x).numpy()[0]
            addback = np.clip(pred + exact, 0.0, 1.0)
            clean_err = pred - clean
            addback_err = addback - raw

            image_id = str(dataset.image_id[idx])
            crop = str(dataset.crop[idx])
            base = f"{image_id}_{crop}"
            image_dir = args.out_dir / image_id
            image_dir.mkdir(parents=True, exist_ok=True)
            codec_img = interleave(codec_up) * RAW_SCALE
            clean_img = interleave(clean) * RAW_SCALE
            pred_img = interleave(pred) * RAW_SCALE
            clean_err_img = interleave(clean_err) * RAW_SCALE
            addback_err_img = interleave(addback_err) * RAW_SCALE
            hi = float(np.percentile(clean_img, 99.5))
            lo = float(np.min(clean_img))
            paths = {
                "codec_bilinear": image_dir / f"{base}_codec_bilinear.png",
                "clean_target": image_dir / f"{base}_clean_target.png",
                "model_clean": image_dir / f"{base}_model_clean.png",
                "clean_error_x16": image_dir / f"{base}_clean_error_x16.png",
                "addback_error_x16": image_dir / f"{base}_addback_error_x16.png",
            }
            save_u8(paths["codec_bilinear"], codec_img, lo=lo, hi=hi)
            save_u8(paths["clean_target"], clean_img, lo=lo, hi=hi)
            save_u8(paths["model_clean"], pred_img, lo=lo, hi=hi)
            save_u8(paths["clean_error_x16"], clean_err_img * args.error_gain + 128.0, lo=0.0, hi=255.0)
            save_u8(paths["addback_error_x16"], addback_err_img * args.error_gain + 128.0, lo=0.0, hi=255.0)
            rows.append({
                "image_id": image_id,
                "crop": crop,
                "iso": int(dataset.iso[idx]),
                "accepted": bool(dataset.accepted[idx]),
                "clean_rmse_counts": float(np.sqrt(np.mean(clean_err_img * clean_err_img))),
                "addback_rmse_counts": float(np.sqrt(np.mean(addback_err_img * addback_err_img))),
                "artifacts": {k: str(v) for k, v in paths.items()},
            })

    accepted = [r for r in rows if r["accepted"]]
    summary = {
        "checkpoint": str(args.checkpoint),
        "pairs": str(args.pairs),
        "rows": rows,
        "mean_clean_rmse_counts": float(np.mean([r["clean_rmse_counts"] for r in rows])),
        "accepted_mean_clean_rmse_counts": float(np.mean([r["clean_rmse_counts"] for r in accepted])) if accepted else None,
        "accepted_mean_addback_rmse_counts": float(np.mean([r["addback_rmse_counts"] for r in accepted])) if accepted else None,
    }
    (args.out_dir / "codec_raw_clean_dashboard.json").write_text(json.dumps(summary, indent=2))
    build_html(summary, args.out_dir / "codec_raw_clean_dashboard.html")
    return summary


def build_html(summary: dict[str, Any], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.5f}"
        return escape(str(v))

    html = [
        "<!doctype html><meta charset='utf-8'><title>Codec Raw Clean Dashboard</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}"
        ".card{border:1px solid #d8dee6;border-radius:8px;padding:10px;background:white}img{width:100%;height:auto;background:#111}</style>",
        "<h1>Codec Raw Clean Dashboard</h1>",
        f"<p>Accepted-target RMSE: <b>{fmt(summary['accepted_mean_clean_rmse_counts'])}</b> raw counts.</p>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Accepted</th><th>clean RMSE</th><th>addback RMSE</th></tr></thead><tbody>",
    ]
    for row in summary["rows"]:
        html.append("<tr>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"], row["crop"], row["iso"], row["accepted"],
            row["clean_rmse_counts"], row["addback_rmse_counts"],
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
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--error-gain", type=float, default=16.0)
    args = ap.parse_args()
    summary = build(args)
    print(args.out_dir / "codec_raw_clean_dashboard.json")
    print(args.out_dir / "codec_raw_clean_dashboard.html")
    print(f"accepted clean rmse counts {summary['accepted_mean_clean_rmse_counts']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
