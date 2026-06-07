#!/usr/bin/env python3
"""Evaluate tiled full-frame PREVIEW scene routing.

This diagnostic renders full source/REF images, runs the scene-routed PREVIEW
policy on overlapped source tiles, stitches the full output, and scores the
manifest crops from that stitched output. REF is used only for scoring.
"""
from __future__ import annotations

import argparse
import json
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import resolve_ref, resolve_source, scaled_box  # noqa: E402
from evaluate_preview_runtime_policy import build_input, load_rgb, summarize, write_html  # noqa: E402
from evaluate_preview_scene_routed import (  # noqa: E402
    parse_cluster_checkpoint,
    parse_cluster_conditioning,
    parse_override_checkpoint,
    parse_override_conditioning,
    route_from_sidecar,
    sha256_file,
)
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import DirectRGBRefiner, build_rgb_refiner, pass_preview  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def max_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(rss) / (1024.0 * 1024.0)
    return float(rss) / 1024.0


def mps_memory_mb() -> dict[str, float]:
    if not hasattr(torch, "mps") or not torch.backends.mps.is_available():
        return {}
    out: dict[str, float] = {}
    for name in ("current_allocated_memory", "driver_allocated_memory"):
        fn = getattr(torch.mps, name, None)
        if callable(fn):
            out[name.replace("_memory", "_mb")] = float(fn()) / (1024.0 * 1024.0)
    return out


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


def load_model(path: Path) -> DirectRGBRefiner:
    ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
    model = build_rgb_refiner(
        str(ckpt.get("architecture", "direct")),
        width=int(ckpt.get("width", 40)),
        residual_scale=float(ckpt.get("residual_scale", 0.5)),
    ).to(DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def tile_origins(length: int, tile: int, stride: int) -> list[int]:
    if length <= tile:
        return [0]
    out = list(range(0, max(1, length - tile + 1), stride))
    last = length - tile
    if out[-1] != last:
        out.append(last)
    return out


def tile_weight(height: int, width: int) -> np.ndarray:
    wy = np.hanning(height).astype(np.float32)
    wx = np.hanning(width).astype(np.float32)
    if height <= 2:
        wy = np.ones(height, dtype=np.float32)
    if width <= 2:
        wx = np.ones(width, dtype=np.float32)
    weight = np.maximum(wy[:, None] * wx[None, :], 1e-3)
    return weight[..., None]


def build_tile_input(
    source_rgb: np.ndarray,
    conditioning: str,
    coordinate_mode: str,
    xywh: tuple[int, int, int, int],
    full_size: tuple[int, int],
    global_stats: dict[str, float] | None = None,
) -> torch.Tensor:
    if coordinate_mode == "local":
        return build_input(source_rgb, conditioning)
    if coordinate_mode != "global_tile":
        raise ValueError(f"unsupported coordinate mode {coordinate_mode!r}")
    height, width = source_rgb.shape[:2]
    x0, y0, _w, _h = xywh
    full_w, full_h = full_size
    yy, xx = np.meshgrid(
        (np.arange(height, dtype=np.float32) + float(y0)) / max(1.0, float(full_h - 1)),
        (np.arange(width, dtype=np.float32) + float(x0)) / max(1.0, float(full_w - 1)),
        indexing="ij",
    )
    source = np.transpose(source_rgb.astype(np.float32) / 255.0, (2, 0, 1))
    key_planes = np.zeros((4, height, width), dtype=np.float32)
    if conditioning == "zero":
        pass
    elif conditioning == "content_stats":
        gray = source.mean(axis=0)
        key_planes[0].fill(float(gray.mean()))
        key_planes[1].fill(float(gray.std()))
        key_planes[2].fill(float(np.percentile(gray, 95) - np.percentile(gray, 5)))
    elif conditioning == "color_stats":
        gray = source.mean(axis=0)
        key_planes[0].fill(float(source[0].mean()))
        key_planes[1].fill(float(source[1].mean()))
        key_planes[2].fill(float(source[2].mean()))
        key_planes[3].fill(float(gray.std()))
    elif conditioning == "global_color_stats":
        if global_stats is None:
            gray = source.mean(axis=0)
            global_stats = {
                "r_mean": float(source[0].mean()),
                "g_mean": float(source[1].mean()),
                "b_mean": float(source[2].mean()),
                "gray_std": float(gray.std()),
            }
        key_planes[0].fill(float(global_stats["r_mean"]))
        key_planes[1].fill(float(global_stats["g_mean"]))
        key_planes[2].fill(float(global_stats["b_mean"]))
        key_planes[3].fill(float(global_stats["gray_std"]))
    else:
        raise ValueError(f"unsupported conditioning {conditioning!r}")
    arr = np.concatenate([source, np.stack([xx, yy], axis=0), key_planes], axis=0)
    return torch.from_numpy(arr[None].copy()).to(DEVICE).contiguous()


def select_model(
    *,
    source_path: Path,
    base_sidecar: dict[str, Any],
    override_sidecars: list[tuple[Path, dict[str, Any]]],
    default_checkpoint: Path,
    cluster_ckpts: dict[int, Path],
    override_ckpts: dict[tuple[int | None, int], Path],
    cluster_conditioning: dict[int, str],
    override_conditioning: dict[tuple[int | None, int], str],
    default_conditioning: str,
) -> tuple[int, int | None, str, Path, str, dict[str, Any]]:
    cluster, route = route_from_sidecar(source_path, base_sidecar)
    ckpt_path = cluster_ckpts.get(cluster, default_checkpoint)
    model_key = f"cluster_{cluster}" if cluster in cluster_ckpts else "default"
    conditioning = cluster_conditioning.get(cluster, default_conditioning)
    override_cluster = None
    if override_sidecars:
        trace = []
        for override_index, (_path, override_sidecar) in enumerate(override_sidecars):
            routed_cluster, override_route = route_from_sidecar(source_path, override_sidecar)
            trace.append(
                {
                    "index": override_index,
                    "cluster": routed_cluster,
                    "route_source": override_route["route_source"],
                    "route_distance": override_route["route_distance"],
                }
            )
            override_key = (override_index, routed_cluster)
            legacy_key = (None, routed_cluster)
            matched_key = override_key if override_key in override_ckpts else legacy_key
            if matched_key in override_ckpts:
                override_cluster = routed_cluster
                ckpt_path = override_ckpts[matched_key]
                model_key = (
                    f"override_{override_index}_cluster_{override_cluster}"
                    if override_key in override_ckpts
                    else f"override_cluster_{override_cluster}"
                )
                conditioning = override_conditioning.get(
                    matched_key,
                    override_conditioning.get(legacy_key, conditioning),
                )
                route["override_route_source"] = override_route["route_source"]
                route["override_route_distance"] = override_route["route_distance"]
                route["override_router_index"] = override_index
                break
        route["override_trace"] = trace
    return cluster, override_cluster, model_key, ckpt_path, conditioning, route


def crop_metric_image(image: np.ndarray, crop: dict[str, int], sensor_dims: list[int]) -> np.ndarray:
    box = scaled_box(crop, sensor_dims, (image.shape[1], image.shape[0]))
    pil = Image.fromarray(image).crop(box)
    if pil.size != (512, 512):
        pil = pil.resize((512, 512), Image.Resampling.LANCZOS)
    return np.asarray(pil.convert("RGB"), dtype=np.uint8)


def render_full_image(args: argparse.Namespace, image: dict[str, Any], work: Path, models: dict[str, DirectRGBRefiner], routing: dict[str, Any]) -> dict[str, Any]:
    image_id = str(image["id"])
    manifest = json.loads(args.manifest.read_text())
    ref_dng = resolve_ref(image, args.ref_root)
    source_dng = resolve_source(image_id, args.source_root)
    if source_dng is None:
        raise FileNotFoundError(f"missing source DNG for {image_id}")
    ref_tiff = work / f"{image_id}_REF.tiff"
    source_tiff = work / f"{image_id}_source.tiff"
    ref_render_ms = render_dng_to_tiff(ref_dng, ref_tiff)
    source_render_ms = render_dng_to_tiff(source_dng, source_tiff)
    source_rgb = load_rgb(source_tiff)
    ref_rgb = load_rgb(ref_tiff)
    height, width = source_rgb.shape[:2]
    source_global_stats = {
        "r_mean": float((source_rgb[:, :, 0].astype(np.float32) / 255.0).mean()),
        "g_mean": float((source_rgb[:, :, 1].astype(np.float32) / 255.0).mean()),
        "b_mean": float((source_rgb[:, :, 2].astype(np.float32) / 255.0).mean()),
        "gray_std": float((source_rgb.astype(np.float32).mean(axis=2) / 255.0).std()),
    }
    tile = int(args.tile_size)
    stride = max(1, tile - int(args.overlap))
    out_acc = np.zeros((height, width, 3), dtype=np.float32)
    weight_acc = np.zeros((height, width, 1), dtype=np.float32)
    tile_rows: list[dict[str, Any]] = []
    model_ms: list[float] = []
    input_ms: list[float] = []
    route_ms: list[float] = []
    save_tile_ms: list[float] = []
    if args.tile_mode == "manifest_crops":
        tile_specs = []
        for crop_name, crop in manifest["crops"].items():
            if crop_name.startswith("$"):
                continue
            x0, y0, x1, y1 = scaled_box(crop, image["sensor_dims"], (width, height))
            tile_specs.append((x0, y0, x1, y1, crop_name))
    else:
        tile_specs = [
            (x0, y0, min(width, x0 + tile), min(height, y0 + tile), "grid")
            for y0 in tile_origins(height, tile, stride)
            for x0 in tile_origins(width, tile, stride)
        ]
    for x0, y0, x1, y1, tile_label in tile_specs:
            tile_rgb = source_rgb[y0:y1, x0:x1]
            tile_path = work / f"{image_id}_tile_{x0}_{y0}.png"
            t0 = time.perf_counter()
            Image.fromarray(tile_rgb).save(tile_path)
            save_tile_ms.append((time.perf_counter() - t0) * 1000.0)
            t0 = time.perf_counter()
            if args.force_model_key:
                cluster = -1
                override_cluster = None
                model_key = args.force_model_key
                conditioning = args.force_conditioning
                route = {
                    "route_source": "forced_diagnostic_model_key",
                    "route_distance": 0.0,
                }
            else:
                cluster, override_cluster, model_key, _ckpt, conditioning, route = select_model(
                    source_path=tile_path,
                    **routing,
                )
            route_ms.append((time.perf_counter() - t0) * 1000.0)
            t0 = time.perf_counter()
            x = build_tile_input(
                tile_rgb,
                conditioning,
                args.coordinate_mode,
                (x0, y0, x1 - x0, y1 - y0),
                (width, height),
                source_global_stats,
            )
            t1 = time.perf_counter()
            with torch.no_grad():
                pred = models[model_key](x).detach().cpu().numpy()[0]
            t2 = time.perf_counter()
            pred_rgb = np.clip(np.transpose(pred, (1, 2, 0)) * 255.0, 0, 255).astype(np.uint8)
            w = tile_weight(pred_rgb.shape[0], pred_rgb.shape[1])
            y1 = y0 + pred_rgb.shape[0]
            x1 = x0 + pred_rgb.shape[1]
            out_acc[y0:y1, x0:x1] += pred_rgb.astype(np.float32) * w
            weight_acc[y0:y1, x0:x1] += w
            input_ms.append((t1 - t0) * 1000.0)
            model_ms.append((t2 - t1) * 1000.0)
            tile_rows.append(
                {
                    "xywh": [x0, y0, pred_rgb.shape[1], pred_rgb.shape[0]],
                    "tile_label": tile_label,
                    "cluster": cluster,
                    "override_cluster": override_cluster,
                    "checkpoint_role": model_key,
                    "conditioning": conditioning,
                    **route,
                }
            )
    stitched = np.clip(out_acc / np.maximum(weight_acc, 1e-6), 0, 255).astype(np.uint8)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stitched_path = args.output_dir / f"{image_id}_scene_routed_fullframe.png"
    Image.fromarray(stitched).save(stitched_path)
    crop_rows: list[dict[str, Any]] = []
    for crop_name, crop in manifest["crops"].items():
        if crop_name.startswith("$"):
            continue
        ref_crop = crop_metric_image(ref_rgb, crop, image["sensor_dims"])
        out_crop = crop_metric_image(stitched, crop, image["sensor_dims"])
        crop_png = args.output_dir / f"{image_id}_{crop_name}_scene_routed_fullframe.png"
        Image.fromarray(out_crop).save(crop_png)
        metrics = compute_visual_metrics(ref_crop, out_crop)
        metrics = {k: float(v) for k, v in metrics.items()}
        metrics["preview_pass"] = pass_preview(metrics)
        crop_rows.append(
            {
                "image_id": image_id,
                "crop": crop_name,
                "png": crop_png.name,
                **metrics,
            }
        )
    return {
        "image_id": image_id,
        "source_dng": str(source_dng),
        "ref_dng": str(ref_dng),
        "source_render_size": [width, height],
        "ref_render_size": [ref_rgb.shape[1], ref_rgb.shape[0]],
        "stitched_png": stitched_path.name,
        "tile_count": len(tile_rows),
        "tile_size": tile,
        "overlap": int(args.overlap),
        "timing": {
            "source_render_ms": source_render_ms,
            "ref_render_ms": ref_render_ms,
            "route_ms_median": float(statistics.median(route_ms)) if route_ms else 0.0,
            "save_tile_ms_median": float(statistics.median(save_tile_ms)) if save_tile_ms else 0.0,
            "input_ms_median": float(statistics.median(input_ms)) if input_ms else 0.0,
            "model_ms_median": float(statistics.median(model_ms)) if model_ms else 0.0,
            "model_ms_total": float(sum(model_ms)),
        },
        "tile_roles": {
            role: sum(1 for row in tile_rows if row["checkpoint_role"] == role)
            for role in sorted({row["checkpoint_role"] for row in tile_rows})
        },
        "tiles": tile_rows,
        "rows": crop_rows,
    }


def write_dashboard(payload: dict[str, Any], html_path: Path) -> None:
    summary = payload["summary"]["preview_runtime_policy"]
    rows = payload["rows"]
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f7f8f9; color:#222; }
.cards { display:grid; grid-template-columns:repeat(5,minmax(160px,1fr)); gap:10px; margin:14px 0; }
.card,.tile { background:white; border:1px solid #d4d8de; border-radius:6px; padding:10px; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(220px,1fr)); gap:10px; }
.tile img { width:100%; display:block; border:1px solid #ddd; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
td,th { border:1px solid #ccc; padding:5px 7px; text-align:right; }
table { border-collapse:collapse; background:white; font-size:12px; }
th.left,td.left { text-align:left; }
"""
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW full-frame tiled receipt</title>",
        f"<style>{css}</style><h1>PREVIEW Full-Frame Tiled Receipt</h1>",
        "<p>Diagnostic no-REF tiled full-frame render. REF is scoring-only.</p><div class=cards>",
    ]
    cards = [
        ("Pass", f"{summary['pass_count']}/{summary['count']}"),
        ("Pass rate", f"{summary['pass_rate'] * 100:.1f}%"),
        ("Worst LPIPS", f"{summary['worst_lpips']:.4f}"),
        ("Worst Y-PSNR", f"{summary['worst_y_psnr']:.2f}"),
        ("Worst dE2000", f"{summary['worst_dE2000_mean']:.2f}"),
    ]
    for label, value in cards:
        parts.append(f"<div class=card><b>{label}</b><br>{value}</div>")
    parts.append("</div><table><thead><tr><th class=left>image</th><th class=left>crop</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th><th>pass</th></tr></thead><tbody>")
    for row in rows:
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<tr><td class=left>{row['image_id']}</td><td class=left>{row['crop']}</td>"
            f"<td>{row['lpips']:.4f}</td><td>{row['ms_ssim']:.4f}</td>"
            f"<td>{row['y_psnr']:.2f}</td><td>{row['dE2000_mean']:.2f}</td>"
            f"<td class={cls}>{'PASS' if row['preview_pass'] else 'FAIL'}</td></tr>"
        )
    parts.append("</tbody></table><div class=grid>")
    for row in rows:
        parts.append(
            f"<div class=tile><b>{row['image_id']} {row['crop']}</b>"
            f"<br>LPIPS {row['lpips']:.4f} Y {row['y_psnr']:.2f} dE {row['dE2000_mean']:.2f}"
            f"<img src='{row['png']}'></div>"
        )
    parts.append("</div>")
    html_path.write_text("".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--ref-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"),
        Path("/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs"),
    ])
    ap.add_argument("--source-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_holdout_clean_20260607/editable_dng"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/editable_dng"),
    ])
    ap.add_argument("--router-sidecar", type=Path, required=True)
    ap.add_argument("--override-router-sidecar", type=Path, action="append", default=[])
    ap.add_argument("--default-checkpoint", type=Path, required=True)
    ap.add_argument("--cluster-checkpoint", action="append", default=[])
    ap.add_argument("--override-cluster-checkpoint", action="append", default=[])
    ap.add_argument("--cluster-conditioning", action="append", default=[])
    ap.add_argument("--override-cluster-conditioning", action="append", default=[])
    ap.add_argument("--conditioning", choices=["zero", "content_stats", "color_stats", "global_color_stats"], default="zero")
    ap.add_argument("--coordinate-mode", choices=["local", "global_tile"], default="local")
    ap.add_argument("--tile-size", type=int, default=768)
    ap.add_argument("--overlap", type=int, default=128)
    ap.add_argument("--tile-mode", choices=["full_grid", "manifest_crops"], default="full_grid")
    ap.add_argument("--force-model-key", help="Diagnostic: bypass routing and run one loaded model key on every tile.")
    ap.add_argument("--force-conditioning", choices=["zero", "content_stats", "color_stats", "global_color_stats"], default="zero")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard_html.parent.mkdir(parents=True, exist_ok=True)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)

    cluster_ckpts = parse_cluster_checkpoint(args.cluster_checkpoint)
    override_ckpts = parse_override_checkpoint(args.override_cluster_checkpoint)
    all_ckpts = {
        "default": args.default_checkpoint,
        **{f"cluster_{k}": v for k, v in cluster_ckpts.items()},
        **{
            f"override_{idx}_cluster_{cluster}" if idx is not None else f"override_cluster_{cluster}": v
            for (idx, cluster), v in override_ckpts.items()
        },
    }
    models = {key: load_model(path) for key, path in all_ckpts.items()}
    if args.force_model_key and args.force_model_key not in models:
        raise ValueError(f"--force-model-key must be one of {sorted(models)}, got {args.force_model_key!r}")
    checkpoint_receipts = {
        key: {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for key, path in all_ckpts.items()
    }
    routing = {
        "base_sidecar": json.loads(args.router_sidecar.read_text()),
        "override_sidecars": [(path, json.loads(path.read_text())) for path in args.override_router_sidecar],
        "default_checkpoint": args.default_checkpoint,
        "cluster_ckpts": cluster_ckpts,
        "override_ckpts": override_ckpts,
        "cluster_conditioning": parse_cluster_conditioning(args.cluster_conditioning),
        "override_conditioning": parse_override_conditioning(args.override_cluster_conditioning),
        "default_conditioning": args.conditioning,
    }
    manifest = json.loads(args.manifest.read_text())
    images = [
        image for image in manifest["images"]
        if not args.image_id or str(image["id"]) in set(args.image_id)
    ]
    if not images:
        raise RuntimeError("no manifest images selected")
    work = Path(tempfile.mkdtemp(prefix="preview_fullframe_", dir=args.tmp_dir))
    image_receipts = []
    rows = []
    try:
        for image in images:
            receipt = render_full_image(args, image, work, models, routing)
            image_receipts.append(receipt)
            rows.extend(receipt["rows"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    payload = {
        "schema": "preview_scene_routed_fullframe_receipt.v1",
        "runtime_contract": {
            "source_policy": "scene_router_kmeans_runtime_features_tiled_fullframe",
            "forbidden_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes", "gate metrics"],
            "render_inputs": ["source RGB full frame", "runtime tile feature cluster", "selected checkpoint"],
            "router_sidecar": str(args.router_sidecar),
            "override_router_sidecar": [str(path) for path in args.override_router_sidecar],
            "tile_size": args.tile_size,
            "overlap": args.overlap,
            "coordinate_mode": args.coordinate_mode,
            "device": str(DEVICE),
        },
        "router_sidecar_sha256": sha256_file(args.router_sidecar),
        "override_router_sidecar_sha256": [sha256_file(path) for path in args.override_router_sidecar],
        "checkpoints": checkpoint_receipts,
        "summary": {"preview_runtime_policy": summarize(rows)},
        "memory": {"max_rss_mb": max_rss_mb(), **mps_memory_mb()},
        "images": image_receipts,
        "rows": rows,
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2))
    write_dashboard(payload, args.dashboard_html)
    print(json.dumps(payload["summary"]["preview_runtime_policy"], indent=2), flush=True)
    print(args.dashboard_json)
    print(args.dashboard_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
