#!/usr/bin/env python3
"""Evaluate a Mission 1 Bayer SR checkpoint and build a compact review sheet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_mission1_sr import DEVICE, RAW_SCALE, Mission1SRPairs, make_model_from_config  # noqa: E402


def rmse_counts_np(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - target) ** 2)) * RAW_SCALE)


def mae_counts_np(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - target)) * RAW_SCALE)


def gradient_mae_counts_np(pred: np.ndarray, target: np.ndarray) -> float:
    px = np.abs(np.diff(pred, axis=-1) - np.diff(target, axis=-1)).mean()
    py = np.abs(np.diff(pred, axis=-2) - np.diff(target, axis=-2)).mean()
    return float((px + py) * 0.5 * RAW_SCALE)


def planes_luma(planes: np.ndarray) -> np.ndarray:
    return planes.mean(axis=0)


def scale_u8(img: np.ndarray, lo: float, hi: float) -> Image.Image:
    arr = np.clip((img - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8), mode="L")


def error_u8(pred: np.ndarray, target: np.ndarray, scale_counts: float) -> Image.Image:
    err = np.abs(planes_luma(pred) - planes_luma(target)) * RAW_SCALE
    arr = np.clip(err / scale_counts, 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8), mode="L")


def tile_metrics(idx: int, image_id: str, base: np.ndarray, pred: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    base_rmse = rmse_counts_np(base, target)
    model_rmse = rmse_counts_np(pred, target)
    base_mae = mae_counts_np(base, target)
    model_mae = mae_counts_np(pred, target)
    return {
        "tile_index": int(idx),
        "image_id": image_id,
        "baseline_rmse_counts": base_rmse,
        "model_rmse_counts": model_rmse,
        "baseline_mae_counts": base_mae,
        "model_mae_counts": model_mae,
        "baseline_gradient_mae_counts": gradient_mae_counts_np(base, target),
        "model_gradient_mae_counts": gradient_mae_counts_np(pred, target),
        "rmse_improvement_pct": 100.0 * (base_rmse - model_rmse) / base_rmse if base_rmse else 0.0,
        "mae_improvement_pct": 100.0 * (base_mae - model_mae) / base_mae if base_mae else 0.0,
    }


def weighted(rows: list[dict[str, Any]], key: str) -> float:
    return float(np.mean([float(r[key]) for r in rows])) if rows else 0.0


def render_contact(
    out: Path,
    rows: list[dict[str, Any]],
    tensors: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
    max_rows: int,
) -> None:
    selected = sorted(rows, key=lambda r: r["model_rmse_counts"], reverse=True)[:max_rows]
    if not selected:
        return
    sample_target = tensors[selected[0]["tile_index"]][2]
    h, w = planes_luma(sample_target).shape
    label_h = 28
    pad = 8
    cols = 4
    sheet_w = cols * w + (cols + 1) * pad
    sheet_h = len(selected) * (h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    headers = ["target", "bilinear", "model", "model error"]
    for row_i, metric in enumerate(selected):
        base, pred, target = tensors[metric["tile_index"]]
        lum = planes_luma(target)
        lo, hi = np.percentile(lum, [0.5, 99.5])
        imgs = [
            scale_u8(lum, lo, hi),
            scale_u8(planes_luma(base), lo, hi),
            scale_u8(planes_luma(pred), lo, hi),
            error_u8(pred, target, scale_counts=max(64.0, metric["model_rmse_counts"] * 2.0)),
        ]
        y0 = pad + row_i * (h + label_h + pad)
        title = (
            f"{metric['image_id']} tile {metric['tile_index']} "
            f"RMSE {metric['baseline_rmse_counts']:.1f}->{metric['model_rmse_counts']:.1f} "
            f"({metric['rmse_improvement_pct']:+.1f}%)"
        )
        draw.text((pad, y0), title, fill=(240, 240, 240))
        for col, img in enumerate(imgs):
            x0 = pad + col * (w + pad)
            draw.text((x0, y0 + 14), headers[col], fill=(190, 190, 190))
            sheet.paste(img.convert("RGB"), (x0, y0 + label_h))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--holdout-image", required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--contact-sheet", type=Path, required=True)
    ap.add_argument("--max-contact-rows", type=int, default=12)
    args = ap.parse_args()

    dataset = Mission1SRPairs(args.pairs, args.holdout_image)
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    config = ckpt["config"]
    model = make_model_from_config(config).to(DEVICE)
    model.load_state_dict(ckpt["model"], strict=True)
    model.eval()

    rows: list[dict[str, Any]] = []
    tensors: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    image_ids = [row["image_id"] for row in dataset.meta["tiles"]]
    with torch.no_grad():
        for idx in dataset.eval_idx:
            x = torch.from_numpy(dataset.inputs[[idx]]).to(DEVICE)
            y = torch.from_numpy(dataset.targets[[idx]]).to(DEVICE)
            base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
            pred = model(x)
            base_np = base[0].detach().cpu().numpy()
            pred_np = pred[0].detach().cpu().numpy()
            target_np = y[0].detach().cpu().numpy()
            rows.append(tile_metrics(int(idx), image_ids[int(idx)], base_np, pred_np, target_np))
            tensors[int(idx)] = (base_np, pred_np, target_np)

    payload = {
        "schema": "mission1_sr_eval.v1",
        "pairs": str(args.pairs),
        "checkpoint": str(args.checkpoint),
        "holdout_image": args.holdout_image,
        "device": str(DEVICE),
        "eval_tile_count": len(rows),
        "overall": {
            "baseline_rmse_counts": weighted(rows, "baseline_rmse_counts"),
            "model_rmse_counts": weighted(rows, "model_rmse_counts"),
            "baseline_mae_counts": weighted(rows, "baseline_mae_counts"),
            "model_mae_counts": weighted(rows, "model_mae_counts"),
            "baseline_gradient_mae_counts": weighted(rows, "baseline_gradient_mae_counts"),
            "model_gradient_mae_counts": weighted(rows, "model_gradient_mae_counts"),
            "tiles_model_beats_baseline_rmse": sum(
                1 for r in rows if r["model_rmse_counts"] < r["baseline_rmse_counts"]
            ),
            "tiles_model_beats_baseline_mae": sum(
                1 for r in rows if r["model_mae_counts"] < r["baseline_mae_counts"]
            ),
        },
        "worst_by_model_rmse": sorted(rows, key=lambda r: r["model_rmse_counts"], reverse=True)[:20],
        "worst_regressions": sorted(rows, key=lambda r: r["rmse_improvement_pct"])[:20],
        "rows": rows,
        "contact_sheet": str(args.contact_sheet),
    }
    overall = payload["overall"]
    overall["rmse_improvement_pct"] = (
        100.0
        * (overall["baseline_rmse_counts"] - overall["model_rmse_counts"])
        / overall["baseline_rmse_counts"]
    )
    overall["mae_improvement_pct"] = (
        100.0
        * (overall["baseline_mae_counts"] - overall["model_mae_counts"])
        / overall["baseline_mae_counts"]
    )
    overall["gradient_mae_improvement_pct"] = (
        100.0
        * (overall["baseline_gradient_mae_counts"] - overall["model_gradient_mae_counts"])
        / overall["baseline_gradient_mae_counts"]
    )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    render_contact(args.contact_sheet, rows, tensors, args.max_contact_rows)
    print(json.dumps({"eval": str(args.out_json), "contact_sheet": str(args.contact_sheet), "overall": overall}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
