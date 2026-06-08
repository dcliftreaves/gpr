#!/usr/bin/env python3
"""Score full-frame PREVIEW source DNG roots against REF crops.

This diagnostic answers a source-formulation question before more training:
does any runtime-safe editable-DNG source root already have enough full-frame
crop fidelity to be a viable PREVIEW teacher/source? REF is used only for
metrics and never as a render-time source.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import scaled_box  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None


def render_dng_to_tiff(dng_path: Path, tiff_path: Path) -> float:
    t0 = time.perf_counter()
    result = subprocess.run(
        ["sips", "-s", "format", "tiff", str(dng_path), "--out", str(tiff_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sips failed for {dng_path}: {result.stderr[-400:]}")
    return (time.perf_counter() - t0) * 1000.0


def parse_source_root(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source-root must be label=/path")
    label, path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("--source-root label cannot be empty")
    return label, Path(path)


def safe_name(value: str) -> str:
    keep = []
    for ch in value:
        keep.append(ch if ch.isalnum() or ch in ("-", "_") else "_")
    return "".join(keep)


def load_crop(render_path: Path, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    with Image.open(render_path) as image:
        rgb = image.convert("RGB")
        box = scaled_box(crop, sensor_dims, rgb.size)
        cropped = rgb.crop(box)
        if cropped.size != (512, 512):
            cropped = cropped.resize((512, 512), Image.Resampling.LANCZOS)
        return np.asarray(cropped.convert("RGB"), dtype=np.uint8)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    pass_count = sum(1 for row in rows if row["preview_pass"])
    return {
        "count": count,
        "pass_count": pass_count,
        "pass_rate": pass_count / max(1, count),
        "worst_lpips": max(float(row["lpips"]) for row in rows),
        "median_lpips": float(np.median([float(row["lpips"]) for row in rows])),
        "worst_ms_ssim": min(float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(float(row["dE2000_mean"]) for row in rows),
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for variant in sorted({row["variant"] for row in rows}):
        vr = [row for row in rows if row["variant"] == variant]
        worst = max(vr, key=lambda row: (float(row["lpips"]), -float(row["ms_ssim"])))
        out.append({
            "variant": variant,
            "worst_image": worst["image_id"],
            "worst_crop": worst["crop"],
            **summarize(vr),
        })
    out.sort(key=lambda row: (row["pass_count"] != row["count"], -row["pass_count"], row["worst_lpips"], -row["worst_ms_ssim"]))
    return out


def collect(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.receipt.read_text())
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images_by_id = {str(image["id"]): image for image in manifest["images"]}
    receipt_images = receipt.get("images") or []
    selected_ids = set(args.image_id)
    if selected_ids:
        receipt_images = [image for image in receipt_images if str(image["image_id"]) in selected_ids]
    if not receipt_images:
        raise RuntimeError("no receipt images selected")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_source_roots_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    render_ms: list[float] = []
    try:
        for image_receipt in receipt_images:
            image_id = str(image_receipt["image_id"])
            image_meta = images_by_id[image_id]
            print(f"[source-roots] {image_id}", flush=True)
            ref_dng = Path(str(image_receipt["ref_dng"]))
            ref_tiff = work / f"{image_id}_REF.tiff"
            render_ms.append(render_dng_to_tiff(ref_dng, ref_tiff))

            candidates: list[tuple[str, Path]] = [("receipt_source", Path(str(image_receipt["source_dng"])))]
            for label, root in args.source_root:
                candidates.append((label, root / f"{image_id}.dng"))

            rendered: list[tuple[str, Path, Path]] = []
            for label, dng_path in candidates:
                if not dng_path.exists():
                    missing.append({"image_id": image_id, "variant": label, "path": str(dng_path)})
                    continue
                tiff_path = work / f"{image_id}_{safe_name(label)}.tiff"
                render_ms.append(render_dng_to_tiff(dng_path, tiff_path))
                rendered.append((label, dng_path, tiff_path))

            for crop_name, crop in crops.items():
                ref_crop = load_crop(ref_tiff, crop, image_meta["sensor_dims"])
                for label, dng_path, tiff_path in rendered:
                    source_crop = load_crop(tiff_path, crop, image_meta["sensor_dims"])
                    metrics = compute_visual_metrics(ref_crop, source_crop)
                    metrics = {k: float(v) for k, v in metrics.items()}
                    metrics["preview_pass"] = pass_preview(metrics)
                    png_name = f"{image_id}_{crop_name}_{safe_name(label)}.png"
                    Image.fromarray(source_crop).save(args.output_dir / png_name)
                    rows.append({
                        "image_id": image_id,
                        "crop": crop_name,
                        "variant": label,
                        "source_dng": str(dng_path),
                        "png": png_name,
                        **metrics,
                    })
            ref_tiff.unlink(missing_ok=True)
            for _label, _dng_path, tiff_path in rendered:
                tiff_path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "schema": "preview_fullframe_source_root_score.v1",
        "receipt": str(args.receipt),
        "manifest": str(args.manifest),
        "source_roots": [{"label": label, "root": str(root)} for label, root in args.source_root],
        "thresholds": PREVIEW,
        "timing": {
            "render_ms_total": float(sum(render_ms)),
            "render_ms_median": float(np.median(render_ms)) if render_ms else 0.0,
        },
        "summary": aggregate(rows),
        "missing": missing,
        "rows": rows,
    }


def write_html(payload: dict[str, Any], out: Path) -> None:
    def fmt(value: float) -> str:
        return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"

    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f7f8f9; color:#222; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(170px,1fr)); gap:10px; margin:14px 0; }
.card,.tile { background:#fff; border:1px solid #d4d8de; border-radius:6px; padding:10px; }
table { border-collapse:collapse; background:#fff; width:100%; font-size:12px; margin:14px 0; }
td,th { border:1px solid #ccd2d9; padding:5px 7px; text-align:right; }
th.left,td.left { text-align:left; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:10px; }
.tile img { width:100%; display:block; border:1px solid #ddd; }
"""
    best = payload["summary"][0] if payload["summary"] else {}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW source root score</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Frame Source Root Score</h1>",
        "<p>All variants are source DNG renders. REF is used only for metrics.</p>",
        "<div class=cards>",
        f"<div class=card><b>Best variant</b><br>{html.escape(str(best.get('variant', 'n/a')))}</div>",
        f"<div class=card><b>Best pass</b><br>{best.get('pass_count', 0)}/{best.get('count', 0)}</div>",
        f"<div class=card><b>Worst LPIPS</b><br>{fmt(float(best.get('worst_lpips', 0.0)))}</div>",
        f"<div class=card><b>Worst dE</b><br>{fmt(float(best.get('worst_dE2000_mean', 0.0)))}</div>",
        "</div>",
        "<h2>Variant Summary</h2><table><thead><tr><th class=left>variant</th><th>pass</th><th>rate</th><th class=left>worst</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['variant'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate'] * 100:.1f}%</td><td class=left>{html.escape(row['worst_image'])} {html.escape(row['worst_crop'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td></tr>"
        )
    parts.append("</tbody></table><h2>Worst Rows</h2><div class=grid>")
    worst_rows = sorted(payload["rows"], key=lambda row: (not row["preview_pass"], row["lpips"], row["dE2000_mean"]), reverse=True)[:48]
    for row in worst_rows:
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<div class=tile><b>{html.escape(row['image_id'])} {html.escape(row['crop'])}</b>"
            f"<br>{html.escape(row['variant'])}<br><span class={cls}>LPIPS {row['lpips']:.4f}, "
            f"MS {row['ms_ssim']:.4f}, Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            f"<img src='{html.escape(row['png'])}'></div>"
        )
    parts.append("</div>")
    out.write_text("".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--source-root", type=parse_source_root, action="append", default=[])
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.output_html)
    for row in payload["summary"]:
        print(
            f"{row['variant']:<24} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
