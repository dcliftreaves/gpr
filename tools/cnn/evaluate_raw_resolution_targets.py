#!/usr/bin/env python3
"""Evaluate raw 0.5x/1x/2x target quality against source Bayer.

The source DNG is reduced to each target resolution with the same CFA-plane
area downsampler used by ``bench_raw_resolution_targets.py``. Metrics are raw
Bayer-domain and preserve bit depth; RGB/perceptual gates can be layered on top
after the raw targets clear this contract.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import tifffile


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/cnn"))

from bench_raw_resolution_targets import (  # noqa: E402
    decode_gpr,
    decode_gpr_target,
    default_external_root,
    downsample_bayer_0p5x,
    frame_paths,
    load_bibo2x,
    run_bibo2x,
    summarize,
)


RAW_PEAK = 16383.0
TARGET_2K_CHOICES = ("2k_raw_0p5x", "2k_raw_0p5x_fast", "2k_raw_0p5x_l2hh")
REFERENCE_TARGET = {
    "2k_raw_0p5x": "2k_raw_0p5x",
    "2k_raw_0p5x_fast": "2k_raw_0p5x",
    "2k_raw_0p5x_l2hh": "2k_raw_0p5x",
}


def find_source_dng(image_id: str, roots: list[Path]) -> Path | None:
    for root in roots:
        candidate = root / f"{image_id}.dng"
        if candidate.exists():
            return candidate
    return None


def read_bayer_from_dng(path: Path) -> np.ndarray:
    errors: list[str] = []
    with tifffile.TiffFile(path) as tf:
        # Prefer the largest 2D page/subpage. This handles both ordinary DNGs
        # and DNGs with previews/thumbnails.
        candidates: list[np.ndarray] = []
        for page in tf.pages:
            pages = list(page.pages) if getattr(page, "pages", None) else [page]
            for subpage in pages:
                try:
                    shape = subpage.shape
                except Exception:
                    continue
                if len(shape) == 2 and shape[0] > 1000 and shape[1] > 1000:
                    try:
                        candidates.append(subpage.asarray())
                    except Exception as exc:
                        errors.append(f"{type(exc).__name__}: {exc}")
        if not candidates:
            try:
                import rawpy

                with rawpy.imread(str(path)) as raw:
                    return np.asarray(raw.raw_image.copy(), dtype=np.uint16)
            except Exception as exc:
                errors.append(f"rawpy {type(exc).__name__}: {exc}")
                detail = "; ".join(errors[-3:])
                raise RuntimeError(f"no Bayer-like 2D page found in {path}; {detail}") from exc
        arr = max(candidates, key=lambda item: item.shape[0] * item.shape[1])
    return np.asarray(arr, dtype=np.uint16)


def psnr(a: np.ndarray, b: np.ndarray, peak: float = RAW_PEAK) -> float:
    diff = a.astype(np.float32) - b.astype(np.float32)
    mse = float(np.mean(diff * diff))
    if mse <= 1e-12:
        return 999.0
    return 20.0 * math.log10(peak) - 10.0 * math.log10(mse)


def raw_metrics(candidate: np.ndarray, target: np.ndarray) -> dict[str, float | int]:
    if candidate.shape != target.shape:
        raise RuntimeError(f"shape mismatch candidate={candidate.shape} target={target.shape}")
    diff = candidate.astype(np.int32) - target.astype(np.int32)
    absdiff = np.abs(diff)
    return {
        "width": int(candidate.shape[1]),
        "height": int(candidate.shape[0]),
        "psnr_db": psnr(candidate, target),
        "mae_lsb": float(np.mean(absdiff)),
        "p95_abs_lsb": float(np.percentile(absdiff, 95)),
        "p99_abs_lsb": float(np.percentile(absdiff, 99)),
        "max_abs_lsb": int(absdiff.max(initial=0)),
    }


def source_targets(source_bayer: np.ndarray) -> dict[str, np.ndarray]:
    target_4k = downsample_bayer_0p5x(source_bayer)
    target_2k = downsample_bayer_0p5x(target_4k)
    return {
        "8k_raw_2x": source_bayer,
        "4k_raw_1x": target_4k,
        "2k_raw_0p5x": target_2k,
    }


def summarize_metric(rows: list[dict[str, Any]], target_name: str, key: str) -> dict[str, float | int]:
    values = [float(row["targets"][target_name][key]) for row in rows if target_name in row["targets"]]
    if not values:
        return {"n": 0}
    vals = sorted(values)
    return {
        "n": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "min": vals[0],
        "max": vals[-1],
    }


def main() -> int:
    external_root = default_external_root()
    artifact_root = Path(os.environ.get("GPR_ARTIFACT_ROOT", external_root / "artifacts"))
    tmp_root = Path(os.environ.get("GATE_TMPDIR", external_root / "tmp"))
    source_roots_default = [
        external_root / "barnsky_full_dngs",
        artifact_root / "visual_compare_20260525" / "source_dngs",
        external_root / "cnn" / "diverse_dngs",
        external_root / "pi-pre-wipe-2026-05-29",
    ]

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame-dir", type=Path, default=artifact_root / "upresable" / "halfres")
    ap.add_argument("--source-root", type=Path, action="append", default=None)
    ap.add_argument("--output-dir", type=Path, default=artifact_root / "raw_resolution_targets_20260613" / "quality")
    ap.add_argument("--tmp-dir", type=Path, default=tmp_root)
    ap.add_argument("--decoder", type=Path, default=REPO / "build-local/bin/fused_decode_cli")
    ap.add_argument("--bibo2x-ckpt", type=Path, default=external_root / "models" / "BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt")
    ap.add_argument("--sensor-width", type=int, default=8280)
    ap.add_argument("--sensor-height", type=int, default=5520)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--include-8k", action="store_true")
    ap.add_argument("--residual-scale", type=float, default=0.01)
    ap.add_argument(
        "--runtime-2k-target",
        action="store_true",
        help="evaluate the decoder's named 2K target output instead of Python CFA-downsampling 4K",
    )
    ap.add_argument(
        "--target-2k",
        choices=TARGET_2K_CHOICES,
        default="2k_raw_0p5x",
        help="2K fused_decode_cli target used when --runtime-2k-target is set",
    )
    args = ap.parse_args()

    source_roots = args.source_root or source_roots_default
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="raw-target-quality-", dir=args.tmp_dir))

    selected_frames = frame_paths(args.frame_dir, args.limit, args.image_id)
    bibo_model = None
    bibo_device = None
    if args.include_8k:
        bibo_model, bibo_device = load_bibo2x(args.bibo2x_ckpt)

    rows: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    t0 = time.perf_counter()
    try:
        for frame in selected_frames:
            image_id = frame.stem
            source = find_source_dng(image_id, source_roots)
            if source is None:
                missing.append({"image_id": image_id, "reason": "missing_source_dng"})
                continue
            source_bayer = read_bayer_from_dng(source)
            targets = source_targets(source_bayer)

            tmp_raw = work / f"{image_id}_4k.raw"
            half_bayer, decode_info = decode_gpr(
                args.decoder,
                frame,
                args.sensor_width,
                args.sensor_height,
                tmp_raw,
            )
            if args.runtime_2k_target:
                tmp_2k = work / f"{image_id}_2k.raw"
                target_2k_info = decode_gpr_target(
                    args.decoder,
                    frame,
                    args.sensor_width,
                    args.sensor_height,
                    tmp_2k,
                    args.target_2k,
                )
                candidate_2k = np.fromfile(tmp_2k, dtype="<u2").reshape(
                    int(target_2k_info["height"]),
                    int(target_2k_info["width"]),
                )
                tmp_2k.unlink(missing_ok=True)
                method_2k = f"decoder runtime {args.target_2k} target"
            else:
                candidate_2k = downsample_bayer_0p5x(half_bayer)
                method_2k = "CFA plane area downsample 2x"
            row: dict[str, Any] = {
                "image_id": image_id,
                "input_gpr": str(frame),
                "source_dng": str(source),
                "source_dims": [int(source_bayer.shape[1]), int(source_bayer.shape[0])],
                "decode_ms": decode_info["decode_ms"],
                "targets": {
                    "4k_raw_1x": raw_metrics(half_bayer, targets["4k_raw_1x"]),
                    args.target_2k: raw_metrics(candidate_2k, targets[REFERENCE_TARGET[args.target_2k]]),
                },
            }
            row["targets"]["4k_raw_1x"]["cnn"] = "none"
            row["targets"][args.target_2k]["cnn"] = "none"
            row["targets"][args.target_2k]["method"] = method_2k

            if args.include_8k and bibo_model is not None and bibo_device is not None:
                full_bayer, model_ms = run_bibo2x(bibo_model, bibo_device, half_bayer, args.residual_scale)
                metrics = raw_metrics(full_bayer, targets["8k_raw_2x"])
                metrics["cnn"] = "bibo2x_ane_ml2_q3_dec2_diverse"
                metrics["model_ms"] = model_ms
                row["targets"]["8k_raw_2x"] = metrics

            rows.append(row)
            tmp_raw.unlink(missing_ok=True)
            msg = (
                f"{image_id}: 4k PSNR={row['targets']['4k_raw_1x']['psnr_db']:.2f}dB, "
                f"2k PSNR={row['targets'][args.target_2k]['psnr_db']:.2f}dB"
            )
            if "8k_raw_2x" in row["targets"]:
                msg += f", 8k PSNR={row['targets']['8k_raw_2x']['psnr_db']:.2f}dB"
            print(msg, flush=True)
    finally:
        for child in work.glob("*"):
            child.unlink(missing_ok=True)
        work.rmdir()

    target_names = sorted({name for row in rows for name in row["targets"]})
    summary: dict[str, Any] = {}
    for target_name in target_names:
        summary[target_name] = {
            "count": sum(1 for row in rows if target_name in row["targets"]),
            "psnr_db": summarize_metric(rows, target_name, "psnr_db"),
            "mae_lsb": summarize_metric(rows, target_name, "mae_lsb"),
            "p99_abs_lsb": summarize_metric(rows, target_name, "p99_abs_lsb"),
            "dims": sorted({(row["targets"][target_name]["width"], row["targets"][target_name]["height"]) for row in rows if target_name in row["targets"]}),
            "cnn": sorted({str(row["targets"][target_name].get("cnn", "unknown")) for row in rows if target_name in row["targets"]}),
        }
    if rows:
        summary["decode_only"] = summarize([float(row["decode_ms"]) for row in rows])

    payload = {
        "schema": "raw_resolution_targets_quality.v1",
        "frame_dir": str(args.frame_dir),
        "source_roots": [str(path) for path in source_roots],
        "frame_count": len(rows),
        "missing": missing,
        "include_8k": bool(args.include_8k),
        "runtime_2k_target": bool(args.runtime_2k_target),
        "target_2k": args.target_2k,
        "drop_l2_hp": os.environ.get("GPR_DECODE_HALFRES_DROP_L2_HP") == "1",
        "l2_hp_mask": os.environ.get("GPR_DECODE_HALFRES_L2_MASK"),
        "halfres_stream": os.environ.get("GPR_DECODE_HALFRES_STREAM", "1") != "0",
        "elapsed_s": time.perf_counter() - t0,
        "summary": summary,
        "rows": rows,
    }
    out = args.output_dir / "raw_resolution_targets_quality.json"
    out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"receipt": str(out), "summary": summary, "missing": missing}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
