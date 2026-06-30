#!/usr/bin/env python3
"""Build a tile-level visual review dashboard for premium still-SR candidates."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CNN_DIR = ROOT / "tools" / "cnn"
SCHEMA = "gpr.premium_still_sr_visual_review.v1"
RAW_SCALE = 16383.0

DEFAULT_RECEIPT = "artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt.json"


def import_deps():
    try:
        import numpy as np  # type: ignore
        import torch  # type: ignore
        import torch.nn.functional as F  # type: ignore
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ModuleNotFoundError as exc:
        print(f"build_premium_still_sr_visual_review: missing optional dependency: {exc.name}", file=sys.stderr)
        return None
    sys.path.insert(0, str(CNN_DIR))
    from train_mission1_sr import (  # type: ignore
        DEVICE,
        Mission1SRPairs,
        append_coord_channels,
        architecture_uses_coords,
        make_model_from_config,
    )

    return {
        "np": np,
        "torch": torch,
        "F": F,
        "Image": Image,
        "ImageDraw": ImageDraw,
        "ImageFont": ImageFont,
        "DEVICE": DEVICE,
        "Mission1SRPairs": Mission1SRPairs,
        "append_coord_channels": append_coord_channels,
        "architecture_uses_coords": architecture_uses_coords,
        "make_model_from_config": make_model_from_config,
    }


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "sha256": sha256_file(path) if path.is_file() else None,
        "bytes": path.stat().st_size if path.is_file() else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def rmse(np: Any, a: Any, b: Any) -> float:
    diff = a.astype(np.float32) - b.astype(np.float32)
    return float(np.sqrt(np.mean(diff * diff)) * RAW_SCALE)


def mae(np: Any, a: Any, b: Any) -> float:
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))) * RAW_SCALE)


def bayer_planes_to_rgb8(np: Any, planes: Any, lo: float, hi: float) -> Any:
    rgb = np.stack([planes[0], (planes[1] + planes[2]) * 0.5, planes[3]], axis=-1)
    scaled = (rgb - lo) / max(1e-6, hi - lo)
    return np.clip(scaled * 255.0 + 0.5, 0, 255).astype(np.uint8)


def error_to_rgb8(np: Any, pred: Any, target: Any, scale: float) -> Any:
    err = np.mean(np.abs(pred.astype(np.float32) - target.astype(np.float32)), axis=0)
    return np.clip(err * scale * 255.0 + 0.5, 0, 255).astype(np.uint8)


def titled_panel(Image: Any, ImageDraw: Any, image: Any, title: str) -> Any:
    pil = Image.fromarray(image)
    out = Image.new("RGB", (pil.width, pil.height + 24), "white")
    out.paste(pil.convert("RGB"), (0, 24))
    draw = ImageDraw.Draw(out)
    draw.text((4, 5), title, fill=(20, 20, 20))
    return out


def make_contact_sheet(deps: dict[str, Any], panels: list[tuple[str, Any]], out_path: Path) -> None:
    Image = deps["Image"]
    ImageDraw = deps["ImageDraw"]
    titled = [titled_panel(Image, ImageDraw, image, title) for title, image in panels]
    width = sum(item.width for item in titled)
    height = max(item.height for item in titled)
    sheet = Image.new("RGB", (width, height), "white")
    x = 0
    for panel in titled:
        sheet.paste(panel, (x, 0))
        x += panel.width
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def load_model(deps: dict[str, Any], checkpoint: Path) -> tuple[Any, dict[str, Any]]:
    torch = deps["torch"]
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    config = ckpt.get("config")
    if not isinstance(config, dict):
        raise ValueError(f"{checkpoint} lacks checkpoint config")
    model = deps["make_model_from_config"](config)
    model.load_state_dict(ckpt["model"], strict=True)
    model.to(deps["DEVICE"])
    model.eval()
    return model, config


def select_rows(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: (row["model_rmse_counts"] - row["baseline_rmse_counts"], row["model_rmse_counts"]), reverse=True)
    selected = ranked[:max_rows]
    return sorted(selected, key=lambda row: row["rank"])


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    deps = import_deps()
    if deps is None:
        raise SystemExit(2)
    np = deps["np"]
    torch = deps["torch"]
    F = deps["F"]

    root = args.external_root
    receipt_path = resolve_path(root, args.receipt)
    receipt = load_json(receipt_path)
    pairs = resolve_path(root, str(receipt["pairs"]))
    checkpoint = resolve_path(root, str(receipt["checkpoint"]))
    holdout = args.holdout_image or receipt.get("holdout_image")

    dataset = deps["Mission1SRPairs"](pairs, holdout_image=holdout)
    model, config = load_model(deps, checkpoint)
    with_coords = deps["architecture_uses_coords"](str(config.get("architecture", "")))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    eval_indexes = list(map(int, dataset.eval_idx[: args.max_tiles]))
    with torch.no_grad():
        for rank, idx in enumerate(eval_indexes):
            x_np = dataset.inputs[idx : idx + 1]
            y_np = dataset.targets[idx : idx + 1]
            x = torch.from_numpy(x_np).to(deps["DEVICE"])
            y = torch.from_numpy(y_np).to(deps["DEVICE"])
            coords = dataset.coord_channels_for_indices([idx]) if with_coords else None
            base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
            pred = model(deps["append_coord_channels"](x, coords))
            row = {
                "rank": rank,
                "tile_index": idx,
                "image_id": str(dataset.image_ids[idx]),
                "baseline_rmse_counts": rmse(np, base.detach().cpu().numpy()[0], y_np[0]),
                "model_rmse_counts": rmse(np, pred.detach().cpu().numpy()[0], y_np[0]),
                "baseline_mae_counts": mae(np, base.detach().cpu().numpy()[0], y_np[0]),
                "model_mae_counts": mae(np, pred.detach().cpu().numpy()[0], y_np[0]),
                "low_x": int(dataset.tiles[idx].get("low_x", 0)),
                "low_y": int(dataset.tiles[idx].get("low_y", 0)),
            }
            rows.append(row)

    selected = select_rows(rows, args.review_rows)
    for out_rank, row in enumerate(selected):
        idx = int(row["tile_index"])
        x = torch.from_numpy(dataset.inputs[idx : idx + 1]).to(deps["DEVICE"])
        coords = dataset.coord_channels_for_indices([idx]) if with_coords else None
        with torch.no_grad():
            base = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
            pred = model(deps["append_coord_channels"](x, coords))
        target = dataset.targets[idx]
        base_np = base.detach().cpu().numpy()[0]
        pred_np = pred.detach().cpu().numpy()[0]
        lo = float(np.percentile(target, args.display_low_pct))
        hi = float(np.percentile(target, args.display_high_pct))
        err_scale = args.error_scale
        image_name = f"tile_{out_rank:02d}_{row['image_id']}_{idx}.png"
        make_contact_sheet(
            deps,
            [
                ("baseline", bayer_planes_to_rgb8(np, base_np, lo, hi)),
                ("model", bayer_planes_to_rgb8(np, pred_np, lo, hi)),
                ("target", bayer_planes_to_rgb8(np, target, lo, hi)),
                ("model abs error", error_to_rgb8(np, pred_np, target, err_scale)),
            ],
            args.output_dir / image_name,
        )
        row["contact_sheet"] = image_name

    def weighted(key: str) -> float:
        return float(sum(row[key] for row in rows) / max(1, len(rows)))

    summary = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": root.as_posix(),
        "receipt": artifact_ref(receipt_path),
        "pairs": artifact_ref(pairs),
        "checkpoint": artifact_ref(checkpoint),
        "checkpoint_config": config,
        "holdout_image": holdout,
        "evaluated_tiles": len(rows),
        "review_rows": selected,
        "aggregate": {
            "baseline_rmse_counts": weighted("baseline_rmse_counts"),
            "model_rmse_counts": weighted("model_rmse_counts"),
            "baseline_mae_counts": weighted("baseline_mae_counts"),
            "model_mae_counts": weighted("model_mae_counts"),
            "rmse_improvement_pct": 100.0
            * (weighted("baseline_rmse_counts") - weighted("model_rmse_counts"))
            / max(weighted("baseline_rmse_counts"), 1e-9),
            "mae_improvement_pct": 100.0
            * (weighted("baseline_mae_counts") - weighted("model_mae_counts"))
            / max(weighted("baseline_mae_counts"), 1e-9),
        },
        "production_ready": False,
        "limitations": [
            "tile-level Bayer-plane RGB preview, not a raw-editor render",
            "current candidate remains exploratory and is not a production-grade still-SR checkpoint",
            "raw-editor latitude and full-frame still visual receipts are still missing",
        ],
    }
    (args.output_dir / "visual_review.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(summary), encoding="utf-8")
    return summary


def render_html(summary: dict[str, Any]) -> str:
    rows = []
    for row in summary["review_rows"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(row['image_id'])}</td>"
            f"<td>{row['tile_index']}</td>"
            f"<td>{row['low_x']}, {row['low_y']}</td>"
            f"<td>{row['baseline_rmse_counts']:.3f}</td>"
            f"<td>{row['model_rmse_counts']:.3f}</td>"
            f"<td>{row['model_rmse_counts'] - row['baseline_rmse_counts']:.3f}</td>"
            f"<td><img src=\"{html.escape(row['contact_sheet'])}\" width=\"768\"></td>"
            "</tr>"
        )
    limitations = "\n".join(f"<li>{html.escape(item)}</li>" for item in summary["limitations"])
    agg = summary["aggregate"]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Visual Review</title>
<style>
body {{ font: 14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #171717; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f5f5f5; }}
.warn {{ display: inline-block; padding: 6px 10px; background: #fff3cd; border: 1px solid #d7a500; border-radius: 6px; }}
img {{ image-rendering: auto; max-width: 100%; }}
</style>
<h1>Premium Still-SR Visual Review</h1>
<p><span class="warn">production_ready={summary["production_ready"]}</span></p>
<p>Checkpoint: <code>{html.escape(Path(summary["checkpoint"]["path"]).name)}</code></p>
<p>Holdout: <code>{html.escape(str(summary["holdout_image"]))}</code>; evaluated tiles: {summary["evaluated_tiles"]}</p>
<ul>
<li>Baseline RMSE: {agg["baseline_rmse_counts"]:.3f}</li>
<li>Model RMSE: {agg["model_rmse_counts"]:.3f}</li>
<li>RMSE improvement: {agg["rmse_improvement_pct"]:.4f}%</li>
</ul>
<h2>Worst Reviewed Tiles</h2>
<table>
<thead><tr><th>image</th><th>tile</th><th>low xy</th><th>baseline RMSE</th><th>model RMSE</th><th>model-baseline</th><th>contact sheet</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<h2>Limitations</h2>
<ul>{limitations}</ul>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--receipt", type=Path, default=Path(DEFAULT_RECEIPT))
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--holdout-image")
    ap.add_argument("--max-tiles", type=int, default=128)
    ap.add_argument("--review-rows", type=int, default=12)
    ap.add_argument("--display-low-pct", type=float, default=0.5)
    ap.add_argument("--display-high-pct", type=float, default=99.5)
    ap.add_argument("--error-scale", type=float, default=24.0)
    args = ap.parse_args()

    if args.max_tiles <= 0 or args.review_rows <= 0:
        print("build_premium_still_sr_visual_review: --max-tiles and --review-rows must be positive", file=sys.stderr)
        return 2
    summary = build_review(args)
    print(args.output_dir / "visual_review.json")
    print(json.dumps(summary["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
