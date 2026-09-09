#!/usr/bin/env python3
"""Build CFA-preserving diagnostic low-frame phase oracles for Mission 1 SR.

This is not a production transform: modes that use ``clean`` data are oracles.
They answer whether preserving same-color low-frame phase/detail before SR
would be sufficient to move full-frame SR blockers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.bayer_phase_oracle_raw.v1"
PLANES = ("r", "g1", "g2", "b")


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def read_raw(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} samples, expected {expected}")
    return arr.reshape((height, width))


def write_raw(path: Path, raw: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.astype("<u2", copy=False).tofile(path)


def deinterleave(raw: np.ndarray) -> np.ndarray:
    return np.stack(
        [
            raw[0::2, 0::2],
            raw[0::2, 1::2],
            raw[1::2, 0::2],
            raw[1::2, 1::2],
        ],
        axis=0,
    )


def reinterleave(planes: np.ndarray) -> np.ndarray:
    _, h, w = planes.shape
    out = np.empty((h * 2, w * 2), dtype=np.uint16)
    out[0::2, 0::2] = planes[0]
    out[0::2, 1::2] = planes[1]
    out[1::2, 0::2] = planes[2]
    out[1::2, 1::2] = planes[3]
    return out


def blur3_reflect(plane: np.ndarray) -> np.ndarray:
    padded = np.pad(plane.astype(np.float32), 1, mode="reflect")
    return (
        padded[:-2, :-2]
        + 2.0 * padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + 2.0 * padded[1:-1, :-2]
        + 4.0 * padded[1:-1, 1:-1]
        + 2.0 * padded[1:-1, 2:]
        + padded[2:, :-2]
        + 2.0 * padded[2:, 1:-1]
        + padded[2:, 2:]
    ) * (1.0 / 16.0)


def phase_oracle(
    codec: np.ndarray,
    clean: np.ndarray,
    mode: str,
    threshold: float,
    max_value: int,
) -> np.ndarray:
    codec_planes = deinterleave(codec)
    clean_planes = deinterleave(clean)
    out = np.empty_like(codec_planes, dtype=np.float32)
    for i in range(4):
        codec_low = blur3_reflect(codec_planes[i])
        codec_detail = codec_planes[i].astype(np.float32) - codec_low
        clean_low = blur3_reflect(clean_planes[i])
        clean_detail = clean_planes[i].astype(np.float32) - clean_low
        significant = np.abs(clean_detail) >= threshold if threshold > 0.0 else np.ones_like(clean_detail, dtype=bool)

        if mode == "codec":
            detail = codec_detail
        elif mode == "clean":
            out[i] = clean_planes[i].astype(np.float32)
            continue
        elif mode == "codec_lf_clean_detail":
            detail = np.where(significant, clean_detail, codec_detail)
        elif mode == "codec_lf_clean_phase_codec_mag":
            detail = np.where(significant, np.abs(codec_detail) * np.sign(clean_detail), codec_detail)
        elif mode == "codec_lf_clean_phase_clean_mag":
            detail = np.where(significant, np.abs(clean_detail) * np.sign(clean_detail), codec_detail)
        else:
            raise ValueError(f"unknown phase oracle mode: {mode}")
        out[i] = codec_low + detail
    return np.clip(np.rint(reinterleave(out)), 0, max_value).astype(np.uint16)


def metrics(codec: np.ndarray, clean: np.ndarray, out: np.ndarray) -> dict[str, Any]:
    def rmse(a: np.ndarray, b: np.ndarray) -> float:
        diff = a.astype(np.float32) - b.astype(np.float32)
        return float(np.sqrt(np.mean(diff * diff)))

    rows = {}
    codec_p = deinterleave(codec)
    clean_p = deinterleave(clean)
    out_p = deinterleave(out)
    for i, name in enumerate(PLANES):
        rows[name] = {
            "codec_clean_rmse": rmse(codec_p[i], clean_p[i]),
            "output_clean_rmse": rmse(out_p[i], clean_p[i]),
            "output_codec_rmse": rmse(out_p[i], codec_p[i]),
        }
    return {
        "codec_clean_rmse": rmse(codec, clean),
        "output_clean_rmse": rmse(out, clean),
        "output_codec_rmse": rmse(out, codec),
        "planes": rows,
    }


def sidecar_specs(sidecar: Path, stems: set[str] | None) -> list[dict[str, Any]]:
    payload = read_json(sidecar)
    default_width = int(payload.get("width12", 0) or 0)
    default_height = int(payload.get("height12", 0) or 0)
    specs = []
    for image in payload.get("images") or []:
        if not isinstance(image, dict):
            continue
        image_id = str(image.get("image_id") or "")
        if not image_id or (stems and image_id not in stems):
            continue
        codec = image.get("low_source_raw")
        clean = image.get("low_clean_raw")
        if not codec or not clean:
            continue
        width = int(image.get("low_width") or default_width)
        height = int(image.get("low_height") or default_height)
        if (width <= 0 or height <= 0) and image_id.startswith("GP"):
            width, height = 4096, 3072
        if (width <= 0 or height <= 0) and image_id.startswith("Z8"):
            width, height = 4140, 2760
        if width <= 0 or height <= 0:
            raise ValueError(f"{image_id} lacks low dimensions")
        specs.append(
            {
                "image": image_id,
                "codec_raw": str(codec),
                "clean_raw": str(clean),
                "width": width,
                "height": height,
            }
        )
    if stems:
        missing = sorted(stems - {str(row["image"]) for row in specs})
        if missing:
            raise ValueError(f"missing stems in sidecar: {', '.join(missing)}")
    return specs


def run_one(spec: dict[str, Any], out_raw: Path, mode: str, threshold: float, max_value: int) -> dict[str, Any]:
    codec = read_raw(Path(spec["codec_raw"]), int(spec["width"]), int(spec["height"]))
    clean = read_raw(Path(spec["clean_raw"]), int(spec["width"]), int(spec["height"]))
    out = phase_oracle(codec, clean, mode, threshold, max_value)
    write_raw(out_raw, out)
    return {
        **spec,
        "output_raw": str(out_raw),
        "metrics": metrics(codec, clean, out),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codec-raw", type=Path)
    ap.add_argument("--clean-raw", type=Path)
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--pair-sidecar", type=Path)
    ap.add_argument("--stem", action="append")
    ap.add_argument("--out-raw", type=Path)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument(
        "--mode",
        choices=(
            "codec",
            "clean",
            "codec_lf_clean_detail",
            "codec_lf_clean_phase_codec_mag",
            "codec_lf_clean_phase_clean_mag",
        ),
        required=True,
    )
    ap.add_argument("--significant-detail-threshold", type=float, default=2.0)
    ap.add_argument("--max-value", type=int, default=65535)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()

    stems = set(args.stem or []) or None
    if args.pair_sidecar:
        if not args.out_dir:
            raise ValueError("--pair-sidecar requires --out-dir")
        specs = sidecar_specs(args.pair_sidecar, stems)
        rows = [
            run_one(spec, args.out_dir / f"{spec['image']}.raw", args.mode, args.significant_detail_threshold, args.max_value)
            for spec in specs
        ]
    else:
        if not args.codec_raw or not args.clean_raw or not args.out_raw or not args.width or not args.height:
            raise ValueError("single-frame mode requires --codec-raw, --clean-raw, --out-raw, --width, and --height")
        rows = [
            run_one(
                {
                    "image": args.codec_raw.stem,
                    "codec_raw": str(args.codec_raw),
                    "clean_raw": str(args.clean_raw),
                    "width": args.width,
                    "height": args.height,
                },
                args.out_raw,
                args.mode,
                args.significant_detail_threshold,
                args.max_value,
            )
        ]

    receipt = {
        "schema": SCHEMA,
        "mode": args.mode,
        "significant_detail_threshold": args.significant_detail_threshold,
        "max_value": args.max_value,
        "pair_sidecar": str(args.pair_sidecar) if args.pair_sidecar else None,
        "image_count": len(rows),
        "images": rows,
        "policy": "diagnostic_oracle_not_for_runtime" if args.mode != "codec" else "identity",
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"image_count": len(rows), "mode": args.mode, "receipt": str(args.receipt) if args.receipt else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
