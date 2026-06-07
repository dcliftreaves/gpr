#!/usr/bin/env python3
"""Evaluate a hard-routed multi-expert PREVIEW refiner.

Routing is supplied by a scene-router audit generated from runtime source
features. REF is used only for metric labels in the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_scene_router_audit import discover_sources  # noqa: E402
from evaluate_preview_runtime_policy import build_input, load_rgb, summarize, write_html  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import DirectRGBRefiner, pass_preview  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def parse_cluster_checkpoint(values: list[str]) -> dict[int, Path]:
    out: dict[int, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--cluster-checkpoint must be CLUSTER=PATH, got {value!r}")
        left, right = value.split("=", 1)
        out[int(left)] = Path(right)
    return out


def load_model(path: Path) -> DirectRGBRefiner:
    ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
    model = DirectRGBRefiner(width=int(ckpt.get("width", 40))).to(DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def resolve_source(row: dict[str, Any], source_map: dict[tuple[str, str, str], Path]) -> Path:
    path = Path(str(row.get("source_png_resolved") or row.get("source_png") or ""))
    if path.exists():
        return path
    key = (row["image_id"], row["crop"], row["source_label"])
    path = source_map.get(key, path)
    if not path.exists():
        raise FileNotFoundError(f"missing source for {key}: {path}")
    return path


def resolve_ref(row: dict[str, Any], source_map: dict[tuple[str, str, str], Path]) -> Path:
    path = Path(str(row.get("ref_png") or ""))
    if path.exists():
        return path
    # Current receipts use the same root for REF and source rows.
    root_label = str(row["source_label"]).split(":", 1)[0]
    key = (row["image_id"], row["crop"], f"{root_label}:REF")
    path = source_map.get(key, path)
    if not path.exists():
        raise FileNotFoundError(f"missing REF for {key}: {path}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--router-audit", type=Path, required=True)
    ap.add_argument("--source-root", type=Path, action="append", required=True)
    ap.add_argument("--default-checkpoint", type=Path, required=True)
    ap.add_argument("--cluster-checkpoint", action="append", default=[], help="CLUSTER=PATH")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--conditioning", choices=["zero", "content_stats"], default="zero")
    ap.add_argument("--timing-iters", type=int, default=5)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard_html.parent.mkdir(parents=True, exist_ok=True)

    audit = json.loads(args.router_audit.read_text())
    source_map = discover_sources(args.source_root)
    cluster_ckpts = parse_cluster_checkpoint(args.cluster_checkpoint)
    all_ckpts = {"default": args.default_checkpoint, **{f"cluster_{k}": v for k, v in cluster_ckpts.items()}}
    models: dict[str, DirectRGBRefiner] = {}
    for key, path in all_ckpts.items():
        models[key] = load_model(path)

    rows: list[dict[str, Any]] = []
    input_ms: list[float] = []
    model_ms: list[float] = []
    save_ms: list[float] = []
    metric_ms: list[float] = []
    for row in audit.get("rows") or []:
        cluster = int(row["cluster"])
        ckpt_path = cluster_ckpts.get(cluster, args.default_checkpoint)
        model_key = f"cluster_{cluster}" if cluster in cluster_ckpts else "default"
        model = models[model_key]
        source_path = resolve_source(row, source_map)
        ref_path = resolve_ref(row, source_map)
        source = load_rgb(source_path)
        ref = load_rgb(ref_path)
        rgb = None
        sample_input_ms: list[float] = []
        sample_model_ms: list[float] = []
        for _ in range(max(1, args.timing_iters)):
            t0 = time.perf_counter()
            x = build_input(source, args.conditioning)
            t1 = time.perf_counter()
            with torch.no_grad():
                pred = model(x).detach().cpu().numpy()[0]
            t2 = time.perf_counter()
            rgb = np.clip(np.transpose(pred, (1, 2, 0)) * 255, 0, 255).astype(np.uint8)
            sample_input_ms.append((t1 - t0) * 1000.0)
            sample_model_ms.append((t2 - t1) * 1000.0)
        assert rgb is not None
        png = args.output_dir / f"{row['image_id']}_{row['crop']}_scene_routed.png"
        t0 = time.perf_counter()
        Image.fromarray(rgb).save(png)
        save_ms.append((time.perf_counter() - t0) * 1000.0)
        t0 = time.perf_counter()
        metrics = compute_visual_metrics(ref, rgb)
        metric_ms.append((time.perf_counter() - t0) * 1000.0)
        metrics["preview_pass"] = pass_preview(metrics)
        input_ms.extend(sample_input_ms)
        model_ms.extend(sample_model_ms)
        rows.append(
            {
                "image_id": row["image_id"],
                "crop": row["crop"],
                "cluster": cluster,
                "checkpoint_role": model_key,
                "checkpoint": str(ckpt_path),
                "source_label": row["source_label"],
                "source_png": str(source_path),
                "ref_png": str(ref_path),
                "png": png.name,
                **metrics,
            }
        )
        print(
            f"{row['image_id']} {row['crop']} c{cluster} {model_key} "
            f"{'PASS' if metrics['preview_pass'] else 'FAIL'} "
            f"lp={metrics['lpips']:.4f} ms={metrics['ms_ssim']:.4f} "
            f"y={metrics['y_psnr']:.2f} de={metrics['dE2000_mean']:.2f}",
            flush=True,
        )

    payload = {
        "schema": "preview_scene_routed_receipt.v1",
        "router_audit": str(args.router_audit),
        "runtime_contract": {
            "router": "hard cluster route from runtime source features",
            "source_policy": "scene_router_kmeans_runtime_features",
            "conditioning": args.conditioning,
            "forbidden_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes", "gate metrics"],
            "render_inputs": ["source RGB frame/crop", "runtime feature cluster", "selected checkpoint"],
            "device": str(DEVICE),
        },
        "checkpoints": {
            role: {"path": str(path), "sha256": sha256_file(path)}
            for role, path in all_ckpts.items()
        },
        "checkpoint_sha256": "multiple",
        "summary": {"preview_runtime_policy": summarize(rows)},
        "timing": {
            "timing_iters_per_crop": max(1, args.timing_iters),
            "input_ms_per_crop_median": float(statistics.median(input_ms)),
            "input_ms_per_crop_p95": float(np.percentile(input_ms, 95)),
            "model_ms_per_crop_median": float(statistics.median(model_ms)),
            "model_ms_per_crop_p95": float(np.percentile(model_ms, 95)),
            "save_png_ms_per_crop_median": float(statistics.median(save_ms)),
            "metric_ms_per_crop_median": float(statistics.median(metric_ms)),
        },
        "memory": {"max_rss_mb": max_rss_mb(), **mps_memory_mb()},
        "rows": rows,
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2))
    write_html(payload, args.dashboard_html)
    print(json.dumps(payload["summary"]["preview_runtime_policy"], indent=2), flush=True)
    print(args.dashboard_json)
    print(args.dashboard_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
