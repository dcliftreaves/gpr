#!/usr/bin/env python3
"""Benchmark raw-resolution targets from the ml2_q3_dec2 capture stream.

Targets:
  2k_raw_0p5x  decode half-res Bayer, CFA-preserving area downsample 0.5x
  4k_raw_1x    decode half-res Bayer as-is
  8k_raw_2x    optional BIBO_2x Bayer super-res to full sensor dimensions

The 2K path intentionally downsamples each Bayer color plane independently
before reassembling RGGB. That preserves editable raw semantics; it is not an
RGB resize.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[2]
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DECODE_RE = re.compile(r"DECODE: (\d+)x(\d+) in ([0-9.]+) ms .* in (\d+) bytes")
TARGET_RE = re.compile(r"TARGET: ([^ ]+) (\d+)x(\d+) in ([0-9.]+) ms")


def default_external_root() -> Path:
    if os.environ.get("GPR_EXTERNAL_ROOT"):
        return Path(os.environ["GPR_EXTERNAL_ROOT"])
    if DEFAULT_EXTERNAL_ROOT.exists():
        return DEFAULT_EXTERNAL_ROOT
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


def percentile(sorted_values: list[float], frac: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * frac))))
    return float(sorted_values[idx])


def summarize(values: list[float]) -> dict[str, float | int]:
    vals = sorted(float(v) for v in values)
    if not vals:
        return {"n": 0}
    mean = statistics.mean(vals)
    median = statistics.median(vals)
    return {
        "n": len(vals),
        "mean_ms": mean,
        "median_ms": median,
        "min_ms": vals[0],
        "p25_ms": percentile(vals, 0.25),
        "p75_ms": percentile(vals, 0.75),
        "p95_ms": percentile(vals, 0.95),
        "max_ms": vals[-1],
        "fps_mean": 1000.0 / mean if mean > 0 else 0.0,
        "fps_median": 1000.0 / median if median > 0 else 0.0,
    }


def deinterleave(bayer: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return (
        bayer[0::2, 0::2],
        bayer[0::2, 1::2],
        bayer[1::2, 0::2],
        bayer[1::2, 1::2],
    )


def area_down2_plane(plane: np.ndarray) -> np.ndarray:
    h = (plane.shape[0] // 2) * 2
    w = (plane.shape[1] // 2) * 2
    p = plane[:h, :w].astype(np.uint32)
    out = (
        p[0::2, 0::2]
        + p[0::2, 1::2]
        + p[1::2, 0::2]
        + p[1::2, 1::2]
        + 2
    ) >> 2
    return out.astype(np.uint16)


def downsample_bayer_0p5x(bayer: np.ndarray) -> np.ndarray:
    planes = [area_down2_plane(p) for p in deinterleave(bayer)]
    out_h = planes[0].shape[0] * 2
    out_w = planes[0].shape[1] * 2
    out = np.zeros((out_h, out_w), dtype=np.uint16)
    out[0::2, 0::2] = planes[0]
    out[0::2, 1::2] = planes[1]
    out[1::2, 0::2] = planes[2]
    out[1::2, 1::2] = planes[3]
    return out


def decode_gpr(
    decoder: Path,
    frame: Path,
    sensor_w: int,
    sensor_h: int,
    out_raw: Path,
) -> tuple[np.ndarray, dict[str, Any]]:
    t0 = time.perf_counter()
    result = subprocess.run(
        [str(decoder), str(frame), str(sensor_w), str(sensor_h), str(out_raw)],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0
    if result.returncode != 0:
        raise RuntimeError(f"decode failed for {frame}:\n{result.stderr[-2000:]}")
    match = DECODE_RE.search(result.stderr)
    if not match:
        raise RuntimeError(f"could not parse decode timing for {frame}:\n{result.stderr}")
    width, height, decode_ms, in_bytes = match.groups()
    width_i = int(width)
    height_i = int(height)
    bayer = np.fromfile(out_raw, dtype="<u2").reshape(height_i, width_i)
    return bayer, {
        "width": width_i,
        "height": height_i,
        "decode_ms": float(decode_ms),
        "decode_wall_ms": wall_ms,
        "input_bytes": int(in_bytes),
        "raw_bytes": int(out_raw.stat().st_size),
    }


def decode_gpr_target(
    decoder: Path,
    frame: Path,
    sensor_w: int,
    sensor_h: int,
    out_raw: Path,
    target: str,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    result = subprocess.run(
        [str(decoder), str(frame), str(sensor_w), str(sensor_h), str(out_raw), target],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0
    if result.returncode != 0:
        raise RuntimeError(f"decode target failed for {frame} target={target}:\n{result.stderr[-2000:]}")
    decode_match = DECODE_RE.search(result.stderr)
    target_match = TARGET_RE.search(result.stderr)
    if not decode_match or not target_match:
        raise RuntimeError(f"could not parse target timing for {frame}:\n{result.stderr}")
    _dec_width, _dec_height, decode_ms, in_bytes = decode_match.groups()
    target_name, width, height, target_ms = target_match.groups()
    if target_name != target:
        raise RuntimeError(f"target mismatch: requested {target}, decoder reported {target_name}")
    return {
        "width": int(width),
        "height": int(height),
        "decode_ms": float(decode_ms),
        "downsample_ms": float(target_ms),
        "decode_plus_downsample_ms": float(decode_ms) + float(target_ms),
        "wall_ms": wall_ms,
        "input_bytes": int(in_bytes),
        "raw_bytes": int(out_raw.stat().st_size),
    }


def load_bibo2x(ckpt_path: Path):
    import torch

    sys.path.insert(0, str(REPO / "tools/cnn"))
    from model import build

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    variant = ckpt.get("variant", "F_ane")
    model = build(variant).to(device)
    state = ckpt.get("backbone_state") or ckpt.get("model") or ckpt
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, device


def run_bibo2x(model, device, half_bayer: np.ndarray, res_scale: float) -> tuple[np.ndarray, float]:
    sys.path.insert(0, str(REPO / "tools/cnn"))
    import torch
    from upresable_pipeline import run_bibo2x_mps

    t0 = time.perf_counter()
    full = run_bibo2x_mps(model, half_bayer, device, res_scale=res_scale)
    if device.type == "mps":
        torch.mps.synchronize()
    return full, (time.perf_counter() - t0) * 1000.0


def frame_paths(frame_dir: Path, limit: int, image_id: list[str]) -> list[Path]:
    frames = sorted(frame_dir.glob("*.gpr"))
    if image_id:
        wanted = set(image_id)
        frames = [p for p in frames if p.stem in wanted]
    if limit:
        frames = frames[:limit]
    if not frames:
        raise RuntimeError(f"no .gpr frames selected from {frame_dir}")
    return frames


def main() -> int:
    external_root = default_external_root()
    artifact_root = Path(os.environ.get("GPR_ARTIFACT_ROOT", external_root / "artifacts"))
    tmp_root = Path(os.environ.get("GATE_TMPDIR", external_root / "tmp"))

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame-dir", type=Path, default=artifact_root / "upresable" / "halfres")
    ap.add_argument("--output-dir", type=Path, default=artifact_root / "raw_resolution_targets_20260613")
    ap.add_argument("--tmp-dir", type=Path, default=tmp_root)
    ap.add_argument("--decoder", type=Path, default=REPO / "build-local/bin/fused_decode_cli")
    ap.add_argument("--bibo2x-ckpt", type=Path, default=external_root / "models" / "BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt")
    ap.add_argument("--sensor-width", type=int, default=8280)
    ap.add_argument("--sensor-height", type=int, default=5520)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--include-8k", action="store_true", help="also run BIBO_2x full-res reconstruction")
    ap.add_argument("--keep-raw", action="store_true", help="persist target raw outputs under output-dir/raw")
    ap.add_argument("--residual-scale", type=float, default=0.01)
    ap.add_argument(
        "--downsample-mode",
        choices=("native", "python"),
        default="native",
        help="2K/0.5x implementation to benchmark; native uses fused_decode_cli target output",
    )
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="raw-target-bench-", dir=args.tmp_dir))
    raw_out_dir = args.output_dir / "raw"
    if args.keep_raw:
        raw_out_dir.mkdir(parents=True, exist_ok=True)

    frames = frame_paths(args.frame_dir, args.limit, args.image_id)
    bibo_model = None
    bibo_device = None
    if args.include_8k:
        bibo_model, bibo_device = load_bibo2x(args.bibo2x_ckpt)

    rows: list[dict[str, Any]] = []
    try:
        # Warm the decoder on the first selected frame.
        warm_raw = work / "warm.raw"
        decode_gpr(args.decoder, frames[0], args.sensor_width, args.sensor_height, warm_raw)
        warm_raw.unlink(missing_ok=True)

        for frame in frames:
            tmp_raw = work / f"{frame.stem}_4k.raw"
            half_bayer, decode_info = decode_gpr(
                args.decoder,
                frame,
                args.sensor_width,
                args.sensor_height,
                tmp_raw,
            )

            bayer_2k: np.ndarray | None = None
            tmp_2k = work / f"{frame.stem}_2k.raw"
            if args.downsample_mode == "native":
                target_2k_info = decode_gpr_target(
                    args.decoder,
                    frame,
                    args.sensor_width,
                    args.sensor_height,
                    tmp_2k,
                    "2k_raw_0p5x",
                )
            else:
                t0 = time.perf_counter()
                bayer_2k = downsample_bayer_0p5x(half_bayer)
                down2_ms = (time.perf_counter() - t0) * 1000.0
                bayer_2k.astype("<u2").tofile(tmp_2k)
                target_2k_info = {
                    "width": int(bayer_2k.shape[1]),
                    "height": int(bayer_2k.shape[0]),
                    "decode_ms": decode_info["decode_ms"],
                    "downsample_ms": down2_ms,
                    "decode_plus_downsample_ms": decode_info["decode_ms"] + down2_ms,
                    "wall_ms": decode_info["decode_wall_ms"] + down2_ms,
                    "raw_bytes": int(bayer_2k.nbytes),
                    "input_bytes": decode_info["input_bytes"],
                }
            method_2k = (
                "decoder runtime 2k_raw_0p5x target"
                if args.downsample_mode == "native"
                else "CFA plane area downsample 2x"
            )

            row: dict[str, Any] = {
                "image_id": frame.stem,
                "input_gpr": str(frame),
                "input_bytes": decode_info["input_bytes"],
                "targets": {
                    "4k_raw_1x": {
                        "width": decode_info["width"],
                        "height": decode_info["height"],
                        "decode_ms": decode_info["decode_ms"],
                        "wall_ms": decode_info["decode_wall_ms"],
                        "raw_bytes": decode_info["raw_bytes"],
                        "cnn": "none",
                    },
                    "2k_raw_0p5x": {
                        "width": target_2k_info["width"],
                        "height": target_2k_info["height"],
                        "decode_ms": target_2k_info["decode_ms"],
                        "downsample_ms": target_2k_info["downsample_ms"],
                        "decode_plus_downsample_ms": target_2k_info["decode_plus_downsample_ms"],
                        "wall_ms": target_2k_info["wall_ms"],
                        "raw_bytes": target_2k_info["raw_bytes"],
                        "cnn": "none",
                        "method": method_2k,
                        "implementation": args.downsample_mode,
                        "drop_l2_hp": os.environ.get("GPR_DECODE_HALFRES_DROP_L2_HP") == "1",
                    },
                },
            }

            if args.keep_raw:
                keep_4k = raw_out_dir / f"{frame.stem}_4k_1x.raw"
                keep_2k = raw_out_dir / f"{frame.stem}_2k_0p5x.raw"
                tmp_raw.replace(keep_4k)
                tmp_2k.replace(keep_2k)
                row["targets"]["4k_raw_1x"]["path"] = str(keep_4k)
                row["targets"]["2k_raw_0p5x"]["path"] = str(keep_2k)
            else:
                tmp_raw.unlink(missing_ok=True)
                tmp_2k.unlink(missing_ok=True)

            if args.include_8k and bibo_model is not None and bibo_device is not None:
                full_bayer, model_ms = run_bibo2x(bibo_model, bibo_device, half_bayer, args.residual_scale)
                row["targets"]["8k_raw_2x"] = {
                    "width": int(full_bayer.shape[1]),
                    "height": int(full_bayer.shape[0]),
                    "decode_ms": decode_info["decode_ms"],
                    "model_ms": model_ms,
                    "decode_plus_model_ms": decode_info["decode_ms"] + model_ms,
                    "raw_bytes": int(full_bayer.nbytes),
                    "cnn": "bibo2x_ane_ml2_q3_dec2_diverse",
                    "checkpoint": str(args.bibo2x_ckpt),
                }
                if args.keep_raw:
                    keep_8k = raw_out_dir / f"{frame.stem}_8k_2x.raw"
                    full_bayer.astype("<u2").tofile(keep_8k)
                    row["targets"]["8k_raw_2x"]["path"] = str(keep_8k)

            rows.append(row)
            print(
                f"{frame.stem}: 4k decode={decode_info['decode_ms']:.2f}ms, "
                f"2k down={target_2k_info['downsample_ms']:.2f}ms"
                + (
                    f", 8k model={row['targets']['8k_raw_2x']['model_ms']:.2f}ms"
                    if "8k_raw_2x" in row["targets"]
                    else ""
                ),
                flush=True,
            )
    finally:
        if not args.keep_raw:
            for child in work.glob("*"):
                child.unlink(missing_ok=True)
            work.rmdir()

    target_names = sorted({name for row in rows for name in row["targets"]})
    summary: dict[str, Any] = {}
    for name in target_names:
        entries = [row["targets"][name] for row in rows if name in row["targets"]]
        ms_key = (
            "decode_plus_model_ms"
            if any("decode_plus_model_ms" in e for e in entries)
            else "decode_plus_downsample_ms"
            if any("decode_plus_downsample_ms" in e for e in entries)
            else "decode_ms"
        )
        summary[name] = {
            "count": len(entries),
            "dims": sorted({(int(e["width"]), int(e["height"])) for e in entries}),
            "timing_key": ms_key,
            "timing": summarize([float(e[ms_key]) for e in entries]),
            "decode_only": summarize([float(e["decode_ms"]) for e in entries if "decode_ms" in e]),
            "raw_bytes_mean": statistics.mean(float(e["raw_bytes"]) for e in entries),
            "input_bytes_mean": statistics.mean(float(row["input_bytes"]) for row in rows),
            "cnn": sorted({str(e.get("cnn", "unknown")) for e in entries}),
        }

    payload = {
        "schema": "raw_resolution_targets_bench.v1",
        "frame_dir": str(args.frame_dir),
        "frame_count": len(rows),
        "include_8k": bool(args.include_8k),
        "drop_l2_hp": os.environ.get("GPR_DECODE_HALFRES_DROP_L2_HP") == "1",
        "targets": {
            "2k_raw_0p5x": "4140x2760 decoded Bayer -> 2070x1380 CFA-preserving plane area downsample",
            "4k_raw_1x": "4140x2760 decoded Bayer direct from ml2_q3_dec2",
            "8k_raw_2x": "8280x5520 Bayer via BIBO_2x super-res from ml2_q3_dec2",
        },
        "summary": summary,
        "rows": rows,
    }
    receipt = args.output_dir / "raw_resolution_targets_bench.json"
    receipt.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"receipt": str(receipt), "summary": summary}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
