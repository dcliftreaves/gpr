#!/usr/bin/env python3
"""Probe candidate-only patch retrieval for premium still-SR raw residuals.

The current CNN family barely moves the hard X2D raw-CFA residual holdout. This
probe asks a different question: can the missing residual be predicted by a
non-parametric dictionary of source-minus-candidate residual patches indexed by
candidate-only raw/HF features? If this works, the next model should look more
like a retrieval/generative prior. If it fails, the blocker is less likely to be
ordinary CNN capacity and more likely missing runtime signal or target
ambiguity.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


SCHEMA = "gpr.premium_still_sr_patch_dictionary_probe.v1"


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
        "mean": float(np.mean(arr)),
        "max": float(np.max(arr)),
    }


def camera_from_row(row: dict[str, Any]) -> str:
    scene = str(row.get("scene_id") or "").lower()
    source = str(row.get("source_dng") or row.get("candidate_raw") or "").lower()
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


def split_rows(rows: list[dict[str, Any]], holdout_scene: str | None, holdout_camera: str | None) -> tuple[list[int], list[int]]:
    if holdout_scene:
        holdout = [idx for idx, row in enumerate(rows) if str(row.get("scene_id") or "") == holdout_scene]
    elif holdout_camera:
        needle = holdout_camera.lower()
        holdout = [idx for idx, row in enumerate(rows) if camera_from_row(row) == needle or needle in str(row.get("source_dng", "")).lower()]
    else:
        raise ValueError("one of --holdout-scene or --holdout-camera is required")
    train = [idx for idx in range(len(rows)) if idx not in holdout]
    if not train or not holdout:
        raise ValueError(f"split produced train={len(train)} holdout={len(holdout)}")
    return train, holdout


def patch_feature(raw_patch: np.ndarray, hf_patch: np.ndarray, *, x0: int, y0: int, width: int, height: int, ev: float) -> np.ndarray:
    raw = raw_patch.astype(np.float32, copy=False)
    hf = hf_patch.astype(np.float32, copy=False)
    raw_mean = np.mean(raw, axis=(0, 1))
    raw_std = np.std(raw, axis=(0, 1))
    hf_mean = np.mean(hf, axis=(0, 1))
    hf_abs = np.mean(np.abs(hf), axis=(0, 1))
    hf_std = np.std(hf, axis=(0, 1))
    coord = np.asarray(
        [
            2.0 * ((x0 + raw_patch.shape[1] * 0.5) / max(width, 1)) - 1.0,
            2.0 * ((y0 + raw_patch.shape[0] * 0.5) / max(height, 1)) - 1.0,
            float(ev) / 2.0,
        ],
        dtype=np.float32,
    )
    return np.concatenate([raw_mean, raw_std, hf_mean, hf_abs, hf_std, coord]).astype(np.float32)


def grid_positions(height: int, width: int, patch: int, stride: int) -> list[tuple[int, int]]:
    patch = min(patch, height, width)
    ys = list(range(0, max(height - patch + 1, 1), max(1, stride)))
    xs = list(range(0, max(width - patch + 1, 1), max(1, stride)))
    if not ys or ys[-1] != height - patch:
        ys.append(height - patch)
    if not xs or xs[-1] != width - patch:
        xs.append(width - patch)
    return [(y, x) for y in ys for x in xs]


def sample_positions(height: int, width: int, patch: int, count: int, rng: random.Random) -> list[tuple[int, int]]:
    patch = min(patch, height, width)
    if count <= 0:
        return []
    return [
        (
            rng.randrange(0, max(height - patch + 1, 1)),
            rng.randrange(0, max(width - patch + 1, 1)),
        )
        for _ in range(count)
    ]


def make_dictionary(
    *,
    raw: np.ndarray,
    hf: np.ndarray,
    target: np.ndarray,
    rows: list[dict[str, Any]],
    train_indices: list[int],
    patch_size: int,
    patches_per_row: int,
    max_patches: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    rng = random.Random(seed)
    h, w = raw.shape[1:3]
    features: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    meta: list[dict[str, Any]] = []
    order = list(train_indices)
    rng.shuffle(order)
    for idx in order:
        positions = sample_positions(h, w, patch_size, patches_per_row, rng)
        ev = float(rows[idx].get("ev", 0.0) or 0.0)
        for y0, x0 in positions:
            raw_patch = raw[idx, y0 : y0 + patch_size, x0 : x0 + patch_size]
            hf_patch = hf[idx, y0 : y0 + patch_size, x0 : x0 + patch_size]
            target_patch = target[idx, y0 : y0 + patch_size, x0 : x0 + patch_size].astype(np.float32)
            if target_patch.shape[:2] != (patch_size, patch_size):
                continue
            features.append(patch_feature(raw_patch, hf_patch, x0=x0, y0=y0, width=w, height=h, ev=ev))
            residuals.append(target_patch)
            meta.append({"row": idx, "scene_id": rows[idx].get("scene_id"), "crop": rows[idx].get("crop"), "xy": [x0, y0]})
            if len(features) >= max_patches:
                return np.stack(features), np.stack(residuals), meta
    if not features:
        raise ValueError("dictionary build produced no patches")
    return np.stack(features), np.stack(residuals), meta


def nearest_residual(
    query: np.ndarray,
    dict_features: np.ndarray,
    dict_residuals: np.ndarray,
    *,
    k: int,
) -> tuple[np.ndarray, float]:
    diff = dict_features - query[None, :]
    dist = np.sum(diff * diff, axis=1)
    k = max(1, min(k, dist.shape[0]))
    nearest = np.argpartition(dist, k - 1)[:k]
    weights = 1.0 / (dist[nearest] + 1.0e-8)
    weights = weights / np.sum(weights)
    pred = np.sum(dict_residuals[nearest] * weights[:, None, None, None], axis=0)
    return pred.astype(np.float32), float(np.min(dist[nearest]))


def evaluate_holdout(
    *,
    raw: np.ndarray,
    hf: np.ndarray,
    target: np.ndarray,
    rows: list[dict[str, Any]],
    holdout_indices: list[int],
    dict_features: np.ndarray,
    dict_residuals: np.ndarray,
    patch_size: int,
    stride: int,
    k: int,
    max_holdout_rows: int | None,
) -> tuple[dict[str, Any], dict[int, np.ndarray]]:
    h, w = raw.shape[1:3]
    out_rows: list[dict[str, Any]] = []
    preds: dict[int, np.ndarray] = {}
    selected = holdout_indices[:max_holdout_rows] if max_holdout_rows else holdout_indices
    for idx in selected:
        pred = np.zeros((h, w, 4), dtype=np.float32)
        weight = np.zeros((h, w, 1), dtype=np.float32)
        distances: list[float] = []
        ev = float(rows[idx].get("ev", 0.0) or 0.0)
        for y0, x0 in grid_positions(h, w, patch_size, stride):
            raw_patch = raw[idx, y0 : y0 + patch_size, x0 : x0 + patch_size]
            hf_patch = hf[idx, y0 : y0 + patch_size, x0 : x0 + patch_size]
            query = patch_feature(raw_patch, hf_patch, x0=x0, y0=y0, width=w, height=h, ev=ev)
            pred_patch, dist = nearest_residual(query, dict_features, dict_residuals, k=k)
            pred[y0 : y0 + patch_size, x0 : x0 + patch_size] += pred_patch
            weight[y0 : y0 + patch_size, x0 : x0 + patch_size] += 1.0
            distances.append(dist)
        pred = pred / np.maximum(weight, 1.0e-6)
        tgt = target[idx].astype(np.float32)
        base_mae = float(np.mean(np.abs(tgt)))
        pred_mae = float(np.mean(np.abs(pred - tgt)))
        base_rmse = float(np.sqrt(np.mean(tgt * tgt)))
        pred_rmse = float(np.sqrt(np.mean((pred - tgt) ** 2)))
        row = dict(rows[idx])
        row.update(
            {
                "index": idx,
                "baseline_raw_residual_mae": base_mae,
                "model_raw_residual_mae": pred_mae,
                "baseline_raw_residual_rmse": base_rmse,
                "model_raw_residual_rmse": pred_rmse,
                "raw_residual_mae_reduction_pct": 100.0 * (base_mae - pred_mae) / max(base_mae, 1.0e-12),
                "raw_residual_rmse_reduction_pct": 100.0 * (base_rmse - pred_rmse) / max(base_rmse, 1.0e-12),
                "nearest_distance": stats(distances),
            }
        )
        out_rows.append(row)
        preds[idx] = pred
    return (
        {
            "row_count": len(out_rows),
            "raw_residual_mae_reduction_pct": stats([float(row["raw_residual_mae_reduction_pct"]) for row in out_rows]),
            "raw_residual_rmse_reduction_pct": stats([float(row["raw_residual_rmse_reduction_pct"]) for row in out_rows]),
            "baseline_raw_residual_mae": stats([float(row["baseline_raw_residual_mae"]) for row in out_rows]),
            "model_raw_residual_mae": stats([float(row["model_raw_residual_mae"]) for row in out_rows]),
            "rows": out_rows,
        },
        preds,
    )


def cfa4_rgb(arr: np.ndarray) -> np.ndarray:
    r = arr[..., 0]
    g = 0.5 * (arr[..., 1] + arr[..., 2])
    b = arr[..., 3]
    return np.stack([r, g, b], axis=-1)


def write_panel(path: Path, raw: np.ndarray, target: np.ndarray, preds: dict[int, np.ndarray], rows: list[dict[str, Any]], eval_rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = eval_rows[:max_rows]
    if not selected:
        return
    crop_h, crop_w = target.shape[1:3]
    preview_w = min(320, crop_w)
    preview_h = min(320, crop_h)
    pad = 10
    label_h = 46
    cols = 4
    sheet = Image.new("RGB", (cols * (preview_w + pad) + pad, len(selected) * (preview_h + label_h + pad) + pad), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    for row_i, row in enumerate(selected):
        idx = int(row["index"])
        pred = preds[idx]
        tgt = target[idx].astype(np.float32)
        err = np.abs(pred - tgt)
        scale = max(float(np.max(np.abs(tgt))), float(np.max(np.abs(pred))), 1.0e-6)
        panels = [
            np.clip(cfa4_rgb(raw[idx].astype(np.float32)), 0.0, 1.0),
            np.clip(cfa4_rgb(tgt) / scale * 0.5 + 0.5, 0.0, 1.0),
            np.clip(cfa4_rgb(pred) / scale * 0.5 + 0.5, 0.0, 1.0),
            np.clip(cfa4_rgb(err) / scale, 0.0, 1.0),
        ]
        labels = ["candidate", "target residual", "dictionary pred", "abs error"]
        y0 = pad + row_i * (preview_h + label_h + pad)
        draw.text(
            (pad, y0),
            f"{rows[idx].get('scene_id')} {rows[idx].get('crop')} EV {float(rows[idx].get('ev', 0.0)):+.0f} MAE {row['raw_residual_mae_reduction_pct']:.2f}%",
            fill=(245, 245, 245),
        )
        for col, panel in enumerate(panels):
            x0 = pad + col * (preview_w + pad)
            draw.text((x0, y0 + 22), labels[col], fill=(190, 190, 190))
            image = Image.fromarray((panel * 255.0 + 0.5).astype(np.uint8), "RGB").resize((preview_w, preview_h), Image.Resampling.BILINEAR)
            sheet.paste(image, (x0, y0 + label_h))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def render_html(receipt: dict[str, Any], output_dir: Path) -> str:
    panel = Path(receipt["artifacts"]["panel_sheet"]).resolve().relative_to(output_dir.resolve()).as_posix()
    rows = sorted(receipt["eval"]["rows"], key=lambda row: row["raw_residual_mae_reduction_pct"])
    table = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('scene_id')))}</td>"
        f"<td>{html.escape(str(row.get('crop')))}</td>"
        f"<td>{float(row.get('ev', 0.0)):+.0f}</td>"
        f"<td>{row['raw_residual_mae_reduction_pct']:.3f}%</td>"
        f"<td>{row['raw_residual_rmse_reduction_pct']:.3f}%</td>"
        f"<td>{row['model_raw_residual_mae']:.6f}</td>"
        "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Patch Dictionary Probe</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#111;color:#eee;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1b1b1b;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left}}
code{{color:#b7d7ff}}img{{max-width:100%;border:1px solid #333}}
</style></head><body>
<h1>Premium Still-SR Patch Dictionary Probe</h1>
<p>This is a candidate-only runtime probe: nearest neighbors use candidate raw/HF patch features; source residuals are dictionary targets only.</p>
<p>Target: <code>{html.escape(receipt['targets'])}</code></p>
<div class="grid">
<section class="card"><h2>Production ready</h2><p>{str(receipt['production_ready']).lower()}</p></section>
<section class="card"><h2>Dictionary patches</h2><p>{receipt['dictionary']['patch_count']}</p></section>
<section class="card"><h2>Holdout rows</h2><p>{receipt['eval']['row_count']}</p></section>
<section class="card"><h2>Median MAE recovery</h2><p>{receipt['eval']['raw_residual_mae_reduction_pct']['median']:.3f}%</p></section>
<section class="card"><h2>Median RMSE recovery</h2><p>{receipt['eval']['raw_residual_rmse_reduction_pct']['median']:.3f}%</p></section>
</div>
<img src="{html.escape(panel)}">
<table><tr><th>scene</th><th>crop</th><th>EV</th><th>MAE recovery</th><th>RMSE recovery</th><th>model MAE</th></tr>{table}</table>
</body></html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    t0 = time.perf_counter()
    with np.load(args.targets, allow_pickle=False) as z:
        raw = z["candidate_raw_cfa4"].astype(np.float32)
        hf = z["candidate_raw_hf_cfa4"].astype(np.float32)
        target = z["raw_hf_residual_cfa4"].astype(np.float32)
        rows = load_meta(z)
    if raw.shape != target.shape or raw.shape != hf.shape:
        raise ValueError(f"raw/hf/target shape mismatch: {raw.shape}, {hf.shape}, {target.shape}")
    train_indices, holdout_indices = split_rows(rows, args.holdout_scene, args.holdout_camera)
    dict_features, dict_residuals, dict_meta = make_dictionary(
        raw=raw,
        hf=hf,
        target=target,
        rows=rows,
        train_indices=train_indices,
        patch_size=args.patch_size,
        patches_per_row=args.patches_per_train_row,
        max_patches=args.max_dictionary_patches,
        seed=args.seed,
    )
    feature_mean = np.mean(dict_features, axis=0, keepdims=True)
    feature_std = np.std(dict_features, axis=0, keepdims=True) + 1.0e-6
    dict_features = (dict_features - feature_mean) / feature_std

    def normalize_eval_features() -> tuple[dict[str, Any], dict[int, np.ndarray]]:
        original_patch_feature = globals()["patch_feature"]

        def normalized_patch_feature(*pa: Any, **kwa: Any) -> np.ndarray:
            return ((original_patch_feature(*pa, **kwa)[None, :] - feature_mean) / feature_std)[0]

        globals()["patch_feature"] = normalized_patch_feature
        try:
            return evaluate_holdout(
                raw=raw,
                hf=hf,
                target=target,
                rows=rows,
                holdout_indices=holdout_indices,
                dict_features=dict_features,
                dict_residuals=dict_residuals,
                patch_size=args.patch_size,
                stride=args.holdout_stride,
                k=args.neighbors,
                max_holdout_rows=args.max_holdout_rows,
            )
        finally:
            globals()["patch_feature"] = original_patch_feature

    eval_payload, preds = normalize_eval_features()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panel = args.output_dir / "panel_sheet.jpg"
    write_panel(panel, raw, target, preds, rows, eval_payload["rows"], args.panel_rows)
    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "targets": str(args.targets),
        "targets_sha256": sha256_file(args.targets),
        "production_ready": False,
        "runtime_policy": {
            "uses_source_raw_at_training_dictionary_build": True,
            "uses_source_raw_at_runtime": False,
            "runtime_inputs": "candidate_raw_cfa4 + candidate_raw_hf_cfa4 + deterministic crop coordinates + EV metadata",
            "status": "diagnostic_probe_not_registered_production_algorithm",
        },
        "config": {
            "holdout_scene": args.holdout_scene,
            "holdout_camera": args.holdout_camera,
            "patch_size": args.patch_size,
            "holdout_stride": args.holdout_stride,
            "patches_per_train_row": args.patches_per_train_row,
            "max_dictionary_patches": args.max_dictionary_patches,
            "neighbors": args.neighbors,
            "seed": args.seed,
        },
        "split": {
            "train_rows": len(train_indices),
            "holdout_rows": len(holdout_indices),
            "evaluated_holdout_rows": eval_payload["row_count"],
        },
        "dictionary": {
            "patch_count": int(dict_features.shape[0]),
            "feature_channels": int(dict_features.shape[1]),
            "sample_rows": dict_meta[: min(12, len(dict_meta))],
        },
        "eval": eval_payload,
        "elapsed_seconds": float(time.perf_counter() - t0),
        "interpretation": (
            "promotion_candidate"
            if eval_payload["raw_residual_mae_reduction_pct"]["median"] >= args.promotion_recovery_threshold
            else "rejected_or_diagnostic"
        ),
        "promotion_recovery_threshold_pct": args.promotion_recovery_threshold,
        "artifacts": {"panel_sheet": str(panel)},
    }
    receipt_path = args.output_dir / "patch_dictionary_probe.json"
    index = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    index.write_text(render_html(receipt, args.output_dir), encoding="utf-8")
    receipt["artifacts"]["receipt"] = str(receipt_path)
    receipt["artifacts"]["dashboard"] = str(index)
    return receipt


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--holdout-scene")
    ap.add_argument("--holdout-camera")
    ap.add_argument("--patch-size", type=int, default=48)
    ap.add_argument("--holdout-stride", type=int, default=96)
    ap.add_argument("--patches-per-train-row", type=int, default=16)
    ap.add_argument("--max-dictionary-patches", type=int, default=6000)
    ap.add_argument("--neighbors", type=int, default=3)
    ap.add_argument("--max-holdout-rows", type=int)
    ap.add_argument("--panel-rows", type=int, default=8)
    ap.add_argument("--promotion-recovery-threshold", type=float, default=15.0)
    ap.add_argument("--seed", type=int, default=1234)
    return ap.parse_args()


def main() -> int:
    receipt = run(parse_args())
    print(
        json.dumps(
            {
                "receipt": receipt["artifacts"]["receipt"],
                "dashboard": receipt["artifacts"]["dashboard"],
                "dictionary_patches": receipt["dictionary"]["patch_count"],
                "holdout_median_raw_mae_reduction_pct": receipt["eval"]["raw_residual_mae_reduction_pct"]["median"],
                "interpretation": receipt["interpretation"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
