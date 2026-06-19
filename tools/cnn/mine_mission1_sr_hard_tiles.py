#!/usr/bin/env python3
"""Mine hard full-frame tiles for Mission 1 12MP-to-8K SR training.

The full-frame dashboard failures are mostly detail/gradient misses. This tool
turns those failures into a deterministic tile manifest that
build_mission1_sr_pairs.py can consume with --tile-manifest.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "mission1_sr_hard_tile_manifest.v1"


def read_u16_raw(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected}")
    return arr.reshape((height, width))


def deinterleave(bayer: np.ndarray) -> np.ndarray:
    return np.stack(
        [
            bayer[0::2, 0::2],
            bayer[0::2, 1::2],
            bayer[1::2, 0::2],
            bayer[1::2, 1::2],
        ],
        axis=0,
    )


def highpass_score(target: np.ndarray, model: np.ndarray) -> tuple[float, dict[str, float]]:
    target_f = target.astype(np.float32)
    model_f = model.astype(np.float32)
    tx = target_f[:, :, 1:] - target_f[:, :, :-1]
    ty = target_f[:, 1:, :] - target_f[:, :-1, :]
    mx = model_f[:, :, 1:] - model_f[:, :, :-1]
    my = model_f[:, 1:, :] - model_f[:, :-1, :]
    grad_error = float((np.mean(np.abs(mx - tx)) + np.mean(np.abs(my - ty))) * 0.5)
    target_grad = float((np.mean(np.abs(tx)) + np.mean(np.abs(ty))) * 0.5)
    mae = float(np.mean(np.abs(model_f - target_f)))
    # Favor visible signal/detail misses. Flat regions can have error but do not
    # teach the missing high-frequency placement that is failing the dashboard.
    score = grad_error * np.log1p(target_grad) + 0.05 * mae
    return score, {
        "gradient_error_counts": grad_error,
        "target_gradient_counts": target_grad,
        "mae_counts": mae,
    }


def binomial_lowpass(arr: np.ndarray) -> np.ndarray:
    f = arr.astype(np.float32, copy=False)
    p = np.pad(f, ((0, 0), (1, 1), (1, 1)), mode="edge")
    return (
        p[:, :-2, :-2]
        + 2.0 * p[:, :-2, 1:-1]
        + p[:, :-2, 2:]
        + 2.0 * p[:, 1:-1, :-2]
        + 4.0 * p[:, 1:-1, 1:-1]
        + 2.0 * p[:, 1:-1, 2:]
        + p[:, 2:, :-2]
        + 2.0 * p[:, 2:, 1:-1]
        + p[:, 2:, 2:]
    ) / 16.0


def codec_tile_score(
    clean_low: np.ndarray | None,
    codec_low: np.ndarray | None,
    *,
    low_x: int,
    low_y: int,
    low_tile: int,
    focus_plane: int | None,
) -> tuple[float, dict[str, float]]:
    if clean_low is None or codec_low is None:
        return 0.0, {}
    clean = clean_low[:, low_y : low_y + low_tile, low_x : low_x + low_tile]
    codec = codec_low[:, low_y : low_y + low_tile, low_x : low_x + low_tile]
    diff = codec.astype(np.float32) - clean.astype(np.float32)
    hf = (codec.astype(np.float32) - binomial_lowpass(codec)) - (clean.astype(np.float32) - binomial_lowpass(clean))
    plane_slice = slice(None) if focus_plane is None else slice(focus_plane, focus_plane + 1)
    selected_diff = diff[plane_slice]
    selected_hf = hf[plane_slice]
    rmse = float(np.sqrt(np.mean(selected_diff * selected_diff)))
    hf_rmse = float(np.sqrt(np.mean(selected_hf * selected_hf)))
    return rmse + hf_rmse, {
        "codec_rmse_counts": rmse,
        "codec_hf_rmse_counts": hf_rmse,
        "codec_focus_plane": float(focus_plane if focus_plane is not None else -1),
    }


def sensitivity_by_image(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else []
    return {str(row["image"]): row for row in rows if isinstance(row, dict) and row.get("image") is not None}


def plane_index(name: str | None) -> int | None:
    return {"r": 0, "g1": 1, "g2": 2, "b": 3}.get(str(name or ""))


def candidate_tiles(
    compare_json: Path,
    low_tile: int,
    stride: int,
    top_k: int,
    min_spacing: int,
    codec_low_dir: Path | None,
    clean_low_dir: Path | None,
    sensitivity: dict[str, dict[str, Any]],
    gate_pressure_weight: float,
    codec_score_weight: float,
) -> list[dict[str, Any]]:
    compare = json.loads(compare_json.read_text())
    image_id = Path(compare["target_raw"]).stem
    high_w = int(compare["high_width"])
    high_h = int(compare["high_height"])
    raw_low_w = int(compare["low_width"])
    raw_low_h = int(compare["low_height"])
    low_w = raw_low_w // 2
    low_h = raw_low_h // 2
    high_tile = low_tile * 2
    target = deinterleave(read_u16_raw(Path(compare["target_raw"]), high_w, high_h))
    model = deinterleave(read_u16_raw(Path(compare["sr_raw"]), high_w, high_h))
    clean_low = None
    codec_low = None
    if codec_low_dir is not None and clean_low_dir is not None:
        codec_low = deinterleave(read_u16_raw(codec_low_dir / f"{image_id}.raw", raw_low_w, raw_low_h))
        clean_low = deinterleave(read_u16_raw(clean_low_dir / f"{image_id}.raw", raw_low_w, raw_low_h))
    image_sensitivity = sensitivity.get(image_id, {})
    gate_pressure = float(image_sensitivity.get("gate_pressure", 0.0) or 0.0)
    focus_plane = plane_index(image_sensitivity.get("worst_hf_plane"))
    scored: list[dict[str, Any]] = []
    for low_y in range(0, low_h - low_tile + 1, stride):
        high_y = low_y * 2
        for low_x in range(0, low_w - low_tile + 1, stride):
            high_x = low_x * 2
            detail_score, components = highpass_score(
                target[:, high_y : high_y + high_tile, high_x : high_x + high_tile],
                model[:, high_y : high_y + high_tile, high_x : high_x + high_tile],
            )
            codec_score, codec_components = codec_tile_score(
                clean_low,
                codec_low,
                low_x=low_x,
                low_y=low_y,
                low_tile=low_tile,
                focus_plane=focus_plane,
            )
            score = (detail_score + codec_score_weight * codec_score) * (1.0 + gate_pressure_weight * gate_pressure)
            scored.append(
                {
                    "image_id": image_id,
                    "low_x": low_x,
                    "low_y": low_y,
                    "low_tile": low_tile,
                    "score": score,
                    "score_mode": "gate_pressure_weighted_detail_error_plus_codec_residual",
                    "score_components": {
                        **components,
                        **codec_components,
                        "detail_score": detail_score,
                        "codec_score": codec_score,
                        "gate_pressure": gate_pressure,
                        "gate_pressure_weight": gate_pressure_weight,
                        "codec_score_weight": codec_score_weight,
                    },
                    "source_compare": str(compare_json),
                }
            )
    scored.sort(key=lambda row: float(row["score"]), reverse=True)
    selected: list[dict[str, Any]] = []
    spacing2 = min_spacing * min_spacing
    for row in scored:
        if all(
            (int(row["low_x"]) - int(prev["low_x"])) ** 2 + (int(row["low_y"]) - int(prev["low_y"])) ** 2
            >= spacing2
            for prev in selected
        ):
            row = dict(row)
            row["rank"] = len(selected) + 1
            selected.append(row)
        if len(selected) >= top_k:
            break
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare-json", type=Path, action="append", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--low-tile", type=int, default=128)
    ap.add_argument("--stride", type=int, default=64)
    ap.add_argument("--top-k-per-image", type=int, default=128)
    ap.add_argument("--min-spacing", type=int, default=96)
    ap.add_argument("--codec-low-dir", type=Path)
    ap.add_argument("--clean-low-dir", type=Path)
    ap.add_argument("--codec-sensitivity", type=Path)
    ap.add_argument("--gate-pressure-weight", type=float, default=0.0)
    ap.add_argument("--codec-score-weight", type=float, default=0.0)
    args = ap.parse_args()

    sensitivity = sensitivity_by_image(args.codec_sensitivity)
    if (args.codec_low_dir is None) != (args.clean_low_dir is None):
        raise SystemExit("--codec-low-dir and --clean-low-dir must be provided together")

    tiles: list[dict[str, Any]] = []
    for compare_json in args.compare_json:
        tiles.extend(
            candidate_tiles(
                compare_json,
                args.low_tile,
                args.stride,
                args.top_k_per_image,
                args.min_spacing,
                args.codec_low_dir,
                args.clean_low_dir,
                sensitivity,
                args.gate_pressure_weight,
                args.codec_score_weight,
            )
        )
    payload = {
        "schema": SCHEMA,
        "source": "full-frame SR compare model-vs-target detail failures",
        "low_tile": args.low_tile,
        "stride": args.stride,
        "top_k_per_image": args.top_k_per_image,
        "min_spacing": args.min_spacing,
        "codec_low_dir": str(args.codec_low_dir) if args.codec_low_dir else None,
        "clean_low_dir": str(args.clean_low_dir) if args.clean_low_dir else None,
        "codec_sensitivity": str(args.codec_sensitivity) if args.codec_sensitivity else None,
        "gate_pressure_weight": args.gate_pressure_weight,
        "codec_score_weight": args.codec_score_weight,
        "compare_jsons": [str(p) for p in args.compare_json],
        "tile_count": len(tiles),
        "tiles": tiles,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"out": str(args.out), "tile_count": len(tiles)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
