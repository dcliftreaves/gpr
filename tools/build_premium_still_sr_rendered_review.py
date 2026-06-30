#!/usr/bin/env python3
"""Build rendered/editor-latitude review for premium still-SR full-frame runs.

This is a proxy review, not a raw-editor promotion receipt. It reuses the
existing full-frame SR receipts, reruns the checkpoint in memory, renders
fixed Bayer crops to RGB at -2/0/+2 EV, and scores baseline/model display
MAE against the target render. Generated SR raws are not written.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent / "cnn"))
from bench_mission1_sr_8k import load_model, run_tiles  # noqa: E402
from compare_mission1_sr_fullframe import bilinear_planes, deinterleave, read_raw  # noqa: E402
from train_mission1_sr import RAW_SCALE  # noqa: E402


SCHEMA = "gpr.premium_still_sr_rendered_review.v1"
EXPOSURES = (-2.0, 0.0, 2.0)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "max": 0.0, "mean": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
    }


def crop_starts(plane_w: int, plane_h: int, crop: int) -> list[tuple[str, int, int]]:
    margin = max(0, crop // 4)
    return [
        ("upper_left", min(margin, max(0, plane_w - crop)), min(margin, max(0, plane_h - crop))),
        ("center", max(0, (plane_w - crop) // 2), max(0, (plane_h - crop) // 2)),
        ("lower_detail", max(0, plane_w - crop - margin), max(0, plane_h - crop - margin)),
    ]


def reinterleave_crop(planes: np.ndarray, x: int, y: int, crop: int) -> np.ndarray:
    patch = planes[:, y : y + crop, x : x + crop]
    out = np.empty((crop * 2, crop * 2), dtype=np.uint16)
    out[0::2, 0::2] = np.clip(patch[0], 0, 65535).astype(np.uint16)
    out[0::2, 1::2] = np.clip(patch[1], 0, 65535).astype(np.uint16)
    out[1::2, 0::2] = np.clip(patch[2], 0, 65535).astype(np.uint16)
    out[1::2, 1::2] = np.clip(patch[3], 0, 65535).astype(np.uint16)
    return out


def render_rgb(planes: np.ndarray, x: int, y: int, crop: int, ev: float) -> np.ndarray:
    bayer = reinterleave_crop(planes, x, y, crop).astype(np.float32)
    exposed = np.clip(bayer * (2.0**ev), 0.0, RAW_SCALE)
    # OpenCV's RG code matches the repo's deinterleave convention: R at [0,0].
    rgb16 = cv2.cvtColor(exposed.astype(np.uint16), cv2.COLOR_BayerRG2RGB_EA).astype(np.float32)
    rgb = np.clip(rgb16 / RAW_SCALE, 0.0, 1.0)
    return np.power(rgb, 1.0 / 2.2)


def rgb_to_image(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "RGB")


def error_image(model: np.ndarray, target: np.ndarray, scale: float = 0.12) -> Image.Image:
    err = np.mean(np.abs(model - target), axis=2)
    arr = np.clip(err / scale, 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8), "L").convert("RGB")


def mae_rgb(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))


def write_contact_sheet(path: Path, rows: list[dict[str, Any]], max_rows: int) -> None:
    selected = rows[:max_rows]
    if not selected:
        return
    first = Image.open(selected[0]["panels"][0]["path"])
    panel_w, panel_h = first.size
    first.close()
    pad = 10
    label_h = 38
    cols = 4
    sheet_w = cols * (panel_w + pad) + pad
    sheet_h = len(selected) * (panel_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    headers = ["target", "bilinear", "model", "model error"]
    for row_idx, row in enumerate(selected):
        y0 = pad + row_idx * (panel_h + label_h + pad)
        title = (
            f"{row['route']} {row['image']} {row['crop']} EV {row['ev']:+.0f} "
            f"MAE {row['baseline_display_mae']:.4f}->{row['model_display_mae']:.4f}"
        )
        draw.text((pad, y0), title, fill=(245, 245, 245))
        for col, panel in enumerate(row["panels"]):
            x0 = pad + col * (panel_w + pad)
            draw.text((x0, y0 + 17), headers[col], fill=(190, 190, 190))
            img = Image.open(panel["path"]).convert("RGB")
            sheet.paste(img, (x0, y0 + label_h))
            img.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def review_image(
    *,
    route: str,
    checkpoint: Path,
    compare_path: Path,
    output_dir: Path,
    crop_size: int,
    tile: int,
    overlap: int,
    device_name: str,
) -> list[dict[str, Any]]:
    import torch

    compare = load_json(compare_path)
    low_w = int(compare["low_width"])
    low_h = int(compare["low_height"])
    high_w = int(compare["high_width"])
    high_h = int(compare["high_height"])
    low_raw = Path(str(compare["low_raw"]))
    target_raw = Path(str(compare["target_raw"]))
    image_id = compare_path.parent.name

    if device_name == "auto":
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    else:
        device = torch.device(device_name)
    low = deinterleave(read_raw(low_raw, low_w, low_h))
    target = deinterleave(read_raw(target_raw, high_w, high_h)).astype(np.float32)
    baseline = bilinear_planes(low, high_w, high_h)
    model, config = load_model(checkpoint, device)
    coord = bool(config.get("coordinate_channels"))
    sr, _timing = run_tiles(
        model,
        low,
        device,
        tile=tile,
        overlap=overlap,
        write_output=True,
        high_width=high_w,
        high_height=high_h,
        coordinate_channels=coord,
    )
    if sr is None:
        raise RuntimeError("run_tiles returned no SR output")
    sr_f = sr.astype(np.float32)
    plane_h, plane_w = target.shape[1], target.shape[2]
    crop = min(crop_size, plane_w, plane_h)
    rows: list[dict[str, Any]] = []
    panels_dir = output_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    for crop_name, x, y in crop_starts(plane_w, plane_h, crop):
        for ev in EXPOSURES:
            target_rgb = render_rgb(target, x, y, crop, ev)
            base_rgb = render_rgb(baseline, x, y, crop, ev)
            model_rgb = render_rgb(sr_f, x, y, crop, ev)
            base_mae = mae_rgb(base_rgb, target_rgb)
            model_mae = mae_rgb(model_rgb, target_rgb)
            safe = f"{route}_{image_id}_{crop_name}_ev{ev:+.0f}".replace("+", "p").replace("-", "m")
            panel_paths = {
                "target": panels_dir / f"{safe}_target.jpg",
                "baseline": panels_dir / f"{safe}_baseline.jpg",
                "model": panels_dir / f"{safe}_model.jpg",
                "error": panels_dir / f"{safe}_error.jpg",
            }
            rgb_to_image(target_rgb).save(panel_paths["target"], quality=92)
            rgb_to_image(base_rgb).save(panel_paths["baseline"], quality=92)
            rgb_to_image(model_rgb).save(panel_paths["model"], quality=92)
            error_image(model_rgb, target_rgb).save(panel_paths["error"], quality=92)
            rows.append(
                {
                    "route": route,
                    "image": image_id,
                    "crop": crop_name,
                    "ev": ev,
                    "baseline_display_mae": base_mae,
                    "model_display_mae": model_mae,
                    "model_minus_baseline_mae": model_mae - base_mae,
                    "model_better": model_mae < base_mae,
                    "crop_plane_xy": [x, y],
                    "crop_plane_size": crop,
                    "panels": [{"kind": key, "path": str(path)} for key, path in panel_paths.items()],
                }
            )
    return rows


def render_html(data: dict[str, Any], output_dir: Path) -> str:
    rows = sorted(data["rows"], key=lambda row: row["model_minus_baseline_mae"], reverse=True)
    cards = []
    for row in rows:
        err_panel = next(panel for panel in row["panels"] if panel["kind"] == "error")
        rel = Path(err_panel["path"]).resolve().relative_to(output_dir.resolve()).as_posix()
        cls = "bad" if not row["model_better"] else "good"
        cards.append(
            f"<tr class='{cls}'><td>{html.escape(row['route'])}</td><td>{html.escape(row['image'])}</td>"
            f"<td>{html.escape(row['crop'])}</td><td>{row['ev']:+.0f}</td>"
            f"<td>{row['baseline_display_mae']:.5f}</td><td>{row['model_display_mae']:.5f}</td>"
            f"<td>{row['model_minus_baseline_mae']:+.5f}</td><td><a href='{html.escape(rel)}'><img src='{html.escape(rel)}'></a></td></tr>"
        )
    contact = Path(data["contact_sheet"]).name
    s = data["summary"]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Rendered Review</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
table {{ border-collapse: collapse; width: 100%; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f4f6f8; }}
img {{ width: 220px; height: auto; display: block; }}
.good {{ background: #f4fbf5; }}
.bad {{ background: #fff7f2; }}
.warn {{ display: inline-block; padding: 6px 10px; background: #fff3cd; border: 1px solid #d7a500; border-radius: 6px; }}
</style>
<h1>Premium Still-SR Rendered / Latitude Review</h1>
<p class="warn">Proxy review: simple demosaic and EV stress, not a raw-editor promotion receipt.</p>
<p>Rows: {s['row_count']}; model better: {s['model_better_count']}; model worse: {s['model_worse_count']};
median display MAE delta: {s['model_minus_baseline_mae']['median']:+.5f}; worst delta: {s['model_minus_baseline_mae']['max']:+.5f}.</p>
<h2>Contact Sheet</h2>
<p><a href="{html.escape(contact)}"><img src="{html.escape(contact)}" style="width:100%;max-width:1400px"></a></p>
<h2>Rows</h2>
<table><thead><tr><th>route</th><th>image</th><th>crop</th><th>EV</th><th>baseline MAE</th><th>model MAE</th><th>delta</th><th>model error</th></tr></thead>
<tbody>{''.join(cards)}</tbody></table>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", action="append", type=Path, required=True, help="full-frame SR summary.json; repeatable")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--crop-size", type=int, default=384, help="crop size in deinterleaved Bayer-plane pixels")
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    ap.add_argument("--contact-rows", type=int, default=18)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    inputs = []
    for summary_path in args.summary:
        summary = load_json(summary_path)
        checkpoint = Path(str(summary["checkpoint"]))
        route = summary_path.parent.parent.name.replace("premium_still_sr_fullframe_", "").replace("_specialist_20260630", "")
        inputs.append({"summary": str(summary_path), "checkpoint": str(checkpoint), "route": route})
        for image in summary.get("images", []):
            compare_path = Path(str(image["compare_json"]))
            all_rows.extend(
                review_image(
                    route=route,
                    checkpoint=checkpoint,
                    compare_path=compare_path,
                    output_dir=args.output_dir,
                    crop_size=args.crop_size,
                    tile=args.tile,
                    overlap=args.overlap,
                    device_name=args.device,
                )
            )
    deltas = [float(row["model_minus_baseline_mae"]) for row in all_rows]
    summary = {
        "row_count": len(all_rows),
        "model_better_count": sum(1 for row in all_rows if row["model_better"]),
        "model_worse_count": sum(1 for row in all_rows if not row["model_better"]),
        "model_minus_baseline_mae": stats(deltas),
        "baseline_display_mae": stats([float(row["baseline_display_mae"]) for row in all_rows]),
        "model_display_mae": stats([float(row["model_display_mae"]) for row in all_rows]),
        "worst_rows": sorted(all_rows, key=lambda row: float(row["model_minus_baseline_mae"]), reverse=True)[:10],
    }
    contact = args.output_dir / "rendered_latitude_contact_sheet.jpg"
    write_contact_sheet(contact, sorted(all_rows, key=lambda row: float(row["model_minus_baseline_mae"]), reverse=True), args.contact_rows)
    payload = {
        "schema": SCHEMA,
        "inputs": inputs,
        "review_kind": "simple_demosaic_ev_stress_proxy",
        "exposures_ev": list(EXPOSURES),
        "crop_size_plane_pixels": args.crop_size,
        "summary": summary,
        "rows": all_rows,
        "contact_sheet": str(contact),
        "production_ready": False,
        "limitations": [
            "simple OpenCV demosaic, not Adobe/LibRaw camera rendering",
            "EV stress is a proxy for editor latitude, not a raw-editor receipt",
            "review checks crops, not every full-frame pixel visually",
        ],
    }
    (args.output_dir / "rendered_review.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(payload, args.output_dir), encoding="utf-8")
    print(args.output_dir / "rendered_review.json")
    compact_summary = {k: v for k, v in summary.items() if k != "worst_rows"}
    print(json.dumps(compact_summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
