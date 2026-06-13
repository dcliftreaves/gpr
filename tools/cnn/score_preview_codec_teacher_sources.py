#!/usr/bin/env python3
"""Score codec-derived no-REF teacher renders on PREVIEW hard rows.

This diagnostic tests whether a higher-quality codec/render path can provide a
runtime-safe teacher for the embedded PREVIEW path. REF is rendered only for
metrics. The candidate variants are generated from the source DNG through
registered codec/CNN/demosaic pipelines, then scored on the fixed PREVIEW
manifest crops.
"""
from __future__ import annotations

import argparse
import html
import json
import math
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
sys.path.insert(0, str(REPO / "tests/quality_gates"))
sys.path.insert(0, str(REPO / "tools/cnn"))
sys.path.insert(0, str(REPO / "tools/test"))

import run_gate  # noqa: E402
from build_preview_holdout_runtime_receipt import scaled_box  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import PREVIEW, pass_preview  # noqa: E402


Image.MAX_IMAGE_PIXELS = None


DEFAULT_PIPELINES = [
    "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools",
    "codec=gpr_tools_q3+cnn=bibo1x_ane_gpr_tools_q3+demosaic=sips_via_gpr_tools",
]


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


def load_registry() -> dict[str, Any]:
    return json.loads((REPO / "pipelines/registry.json").read_text())


def render_dng_to_png(dng_path: Path, out_png: Path) -> None:
    r = subprocess.run(
        ["sips", "-s", "format", "png", str(dng_path), "--out", str(out_png)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"sips render failed for {dng_path}: {r.stderr[-300:]}")


def render_ref_png(image: dict[str, Any], work: Path) -> tuple[Path, float]:
    out = work / f"{image['id']}_REF.png"
    t0 = time.perf_counter()
    render_dng_to_png(Path(image["path"]), out)
    return out, (time.perf_counter() - t0) * 1000.0


def legacy_gpr_tools_to_dng(codec: dict[str, Any], src_dng: Path, workdir: Path) -> tuple[Path, int, float]:
    binary = REPO / codec["binary"]
    if not binary.exists():
        raise RuntimeError(f"codec binary not built: {binary}")
    quality = codec.get("quality", 3)
    gpr_path = workdir / "encoded.gpr"
    dec_dng = workdir / "decoded.dng"
    t0 = time.perf_counter()
    r = subprocess.run(
        [str(binary), "-i", str(src_dng), "-q", str(quality), "-o", str(gpr_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"legacy encode failed for {src_dng}: {r.stderr[-300:]}")
    enc_bytes = gpr_path.stat().st_size
    r = subprocess.run(
        [str(binary), "-i", str(gpr_path), "-o", str(dec_dng)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"legacy decode failed for {src_dng}: {r.stderr[-300:]}")
    return dec_dng, int(enc_bytes), (time.perf_counter() - t0) * 1000.0


def render_pipeline_png(
    image: dict[str, Any],
    pipeline_name: str,
    registry: dict[str, Any],
    work: Path,
) -> tuple[Path, dict[str, float | int | str | None]]:
    pipe = registry["pipelines"][pipeline_name]
    codec = registry["codecs"][pipe["codec"]]
    cnn = registry["cnns"][pipe["cnn"]]
    dms = registry["demosaicers"][pipe["demosaic"]]
    image_id = str(image["id"])
    image_work = work / f"{image_id}_{safe_name(pipeline_name)}"
    image_work.mkdir(parents=True, exist_ok=True)

    if codec.get("encoder_kind") == "legacy_gpr_tools" and pipe["cnn"] == "none":
        dec_dng, enc_bytes, enc_ms = legacy_gpr_tools_to_dng(codec, Path(image["path"]), image_work)
        out = work / f"{image_id}_{safe_name(pipeline_name)}.png"
        demosaic_t0 = time.perf_counter()
        render_dng_to_png(dec_dng, out)
        demosaic_ms = (time.perf_counter() - demosaic_t0) * 1000.0
        return out, {
            "codec": pipe["codec"],
            "cnn": pipe["cnn"],
            "demosaic": pipe["demosaic"],
            "enc_bytes": int(enc_bytes),
            "read_ms": 0.0,
            "enc_ms": float(enc_ms),
            "cnn_ms": 0.0,
            "demosaic_ms": float(demosaic_ms),
            "total_render_ms": float(enc_ms + demosaic_ms),
            "decoded_dng_render": "direct_sips",
        }

    if codec.get("encoder_kind") == "legacy_gpr_tools":
        dec_dng, enc_bytes, enc_ms = legacy_gpr_tools_to_dng(codec, Path(image["path"]), image_work)
        t0 = time.perf_counter()
        bayer, w, h = run_gate.read_source_bayer(str(dec_dng))
        read_ms = (time.perf_counter() - t0) * 1000.0
        dec = bayer
    else:
        t0 = time.perf_counter()
        bayer, w, h = run_gate.read_source_bayer(image["path"])
        read_ms = (time.perf_counter() - t0) * 1000.0
        dec, enc_bytes, enc_ms = run_gate.encode_decode(codec, bayer, w, h, image_work, src_dng=image["path"])

    cnn_t0 = time.perf_counter()
    post = run_gate.apply_cnn(dec, cnn, dms=dms, src_dng=Path(image["path"]), workdir=image_work, full_size=(w, h))
    cnn_ms = (time.perf_counter() - cnn_t0) * 1000.0
    cnn_stats: dict[str, Any] = {}
    if isinstance(post, tuple) and post[0] == "bayer_stats":
        post, cnn_stats = post[1], post[2]
    is_rgb_output = isinstance(post, tuple) and post[0] == "rgb"

    demosaic_t0 = time.perf_counter()
    out = work / f"{image_id}_{safe_name(pipeline_name)}.png"
    if is_rgb_output:
        rgb = Image.fromarray(post[1])
        if rgb.size != (w, h):
            rgb = rgb.resize((w, h), Image.Resampling.BICUBIC)
        rgb.save(out)
    else:
        run_gate.demosaic_to_png(post, dms, Path(image["path"]), image_work, out, upscale_to=(w, h))
    demosaic_ms = (time.perf_counter() - demosaic_t0) * 1000.0

    return out, {
        "codec": pipe["codec"],
        "cnn": pipe["cnn"],
        "demosaic": pipe["demosaic"],
        "enc_bytes": int(enc_bytes),
        "read_ms": float(read_ms),
        "enc_ms": float(enc_ms),
        "cnn_ms": float(cnn_ms),
        "demosaic_ms": float(demosaic_ms),
        "total_render_ms": float(read_ms + enc_ms + cnn_ms + demosaic_ms),
        **{k: float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else v for k, v in cnn_stats.items()},
    }


def crop_array(path: Path, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        box = scaled_box(crop, sensor_dims, rgb.size)
        out = rgb.crop(box)
        if out.size != (512, 512):
            out = out.resize((512, 512), Image.Resampling.LANCZOS)
        return np.asarray(out, dtype=np.uint8)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "worst_lpips": 0.0,
            "median_lpips": 0.0,
            "worst_ms_ssim": 0.0,
            "worst_y_psnr": 0.0,
            "worst_dE2000_mean": 0.0,
            "median_render_ms": 0.0,
            "median_enc_bytes": 0.0,
        }
    pass_count = sum(1 for row in rows if row["preview_pass"])
    return {
        "count": len(rows),
        "pass_count": pass_count,
        "pass_rate": pass_count / len(rows),
        "worst_lpips": max(float(row["lpips"]) for row in rows),
        "median_lpips": float(np.median([float(row["lpips"]) for row in rows])),
        "worst_ms_ssim": min(float(row["ms_ssim"]) for row in rows),
        "worst_y_psnr": min(float(row["y_psnr"]) for row in rows),
        "worst_dE2000_mean": max(float(row["dE2000_mean"]) for row in rows),
        "median_render_ms": float(np.median([float(row["timing"]["total_render_ms"]) for row in rows])),
        "median_enc_bytes": float(np.median([float(row["timing"]["enc_bytes"]) for row in rows])),
    }


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for variant in sorted({row["variant"] for row in rows}):
        group = [row for row in rows if row["variant"] == variant]
        worst = max(group, key=lambda row: (float(row["lpips"]), -float(row["ms_ssim"])))
        out.append(
            {
                "variant": variant,
                "worst_image": worst["image_id"],
                "worst_crop": worst["crop"],
                **summarize(group),
            }
        )
    out.sort(key=lambda row: (row["pass_count"] != row["count"], -row["pass_count"], row["worst_lpips"]))
    return out


def selected_images(manifest: dict[str, Any], image_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(image_ids)
    images = [image for image in manifest["images"] if not wanted or str(image["id"]) in wanted]
    if not images:
        raise RuntimeError("no selected images")
    return images


def collect(args: argparse.Namespace) -> dict[str, Any]:
    registry = load_registry()
    manifest = json.loads(args.manifest.read_text())
    crops = {str(k): v for k, v in manifest["crops"].items() if not str(k).startswith("$")}
    images = selected_images(manifest, args.image_id)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preview_codec_teacher_", dir=args.tmp_dir))
    rows: list[dict[str, Any]] = []
    image_receipts: list[dict[str, Any]] = []
    try:
        for image in images:
            image_id = str(image["id"])
            print(f"[codec-teacher] {image_id}", flush=True)
            ref_path, ref_ms = render_ref_png(image, work)
            ref_crops = {
                crop_name: crop_array(ref_path, crop, image["sensor_dims"])
                for crop_name, crop in crops.items()
            }
            image_variants = []
            for pipeline in args.pipeline:
                print(f"[codec-teacher] {image_id} {pipeline}", flush=True)
                pipe_path, timing = render_pipeline_png(image, pipeline, registry, work)
                variant = safe_name(pipeline)
                for crop_name, crop in crops.items():
                    out_crop = crop_array(pipe_path, crop, image["sensor_dims"])
                    metrics = {k: float(v) for k, v in compute_visual_metrics(ref_crops[crop_name], out_crop).items()}
                    metrics["preview_pass"] = pass_preview(metrics)
                    png_name = f"{image_id}_{crop_name}_{variant}.png"
                    Image.fromarray(out_crop).save(args.output_dir / png_name)
                    row = {
                        "image_id": image_id,
                        "crop": crop_name,
                        "variant": pipeline,
                        "png": png_name,
                        "timing": timing,
                        **metrics,
                    }
                    rows.append(row)
                    image_variants.append(row)
                pipe_path.unlink(missing_ok=True)
            ref_path.unlink(missing_ok=True)
            image_receipts.append(
                {
                    "image_id": image_id,
                    "source_dng": image["path"],
                    "ref_render_ms": ref_ms,
                    "rows": len(image_variants),
                }
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {
        "schema": "preview_codec_teacher_source_score.v1",
        "manifest": str(args.manifest),
        "thresholds": PREVIEW,
        "pipelines": list(args.pipeline),
        "render_contract": {
            "candidate_inputs": ["source DNG", "registered codec/CNN/demosaic pipeline"],
            "ref_usage": "metrics only",
            "uses_ref_at_render_time": False,
            "intended_use": "teacher/source formulation diagnostic for embedded no-REF PREVIEW",
        },
        "summary": aggregate(rows),
        "images": image_receipts,
        "rows": rows,
    }


def fmt(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"


def write_html(payload: dict[str, Any], path: Path) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:22px; color:#1f2933; }
table { border-collapse:collapse; width:100%; font-size:12px; margin:14px 0 26px; }
th,td { border:1px solid #cbd5df; padding:6px 8px; text-align:right; vertical-align:top; }
th.left,td.left { text-align:left; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:10px; margin:14px 0; }
.card,.tile { border:1px solid #cbd5df; border-radius:6px; padding:10px; background:#fbfcfd; }
.pass { color:#12652f; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
.tile img { display:block; width:100%; border:1px solid #d8dee6; margin-top:6px; }
"""
    best = payload["summary"][0] if payload["summary"] else {}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Codec Teacher Source Score</title>",
        f"<style>{css}</style><h1>PREVIEW Codec Teacher Source Score</h1>",
        "<p>Candidate renders use only source DNG plus registered codec/CNN/demosaic pipelines. REF is metrics-only.</p>",
        "<div class=cards>",
        f"<div class=card><b>Best variant</b><br>{html.escape(str(best.get('variant', 'n/a')))}</div>",
        f"<div class=card><b>Best pass</b><br>{best.get('pass_count', 0)}/{best.get('count', 0)}</div>",
        f"<div class=card><b>Worst LPIPS</b><br>{fmt(float(best.get('worst_lpips', 0.0)))}</div>",
        f"<div class=card><b>Median bytes</b><br>{best.get('median_enc_bytes', 0) / (1024 * 1024):.2f} MiB</div>",
        "</div>",
        "<h2>Summary</h2><table><thead><tr><th class=left>variant</th><th>pass</th><th>rate</th><th class=left>worst</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th><th>render ms</th><th>bytes</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['variant'])}</td><td class={cls}>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate']:.1%}</td><td class=left>{html.escape(row['worst_image'])} {html.escape(row['worst_crop'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td><td>{fmt(row['worst_dE2000_mean'])}</td>"
            f"<td>{row['median_render_ms']:.1f}</td><td>{row['median_enc_bytes'] / (1024 * 1024):.2f} MiB</td></tr>"
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
    path.write_text("".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    parser.add_argument("--image-id", action="append", default=[])
    parser.add_argument("--pipeline", action="append", default=list(DEFAULT_PIPELINES))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    parser.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = parser.parse_args()
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    for row in payload["summary"]:
        print(
            f"{row['variant']:<92} {row['pass_count']:>3}/{row['count']:<3} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Y={row['worst_y_psnr']:.2f} dE={row['worst_dE2000_mean']:.2f} "
            f"bytes={row['median_enc_bytes'] / (1024 * 1024):.2f}MiB",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
