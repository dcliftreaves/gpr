#!/usr/bin/env python3
"""Apply a sparse same-color Bayer detail-residual oracle to a codec low raw.

This is a codec-side diagnostic, not a production runtime transform. It uses
the clean low raw to estimate what same-color detail residual an encoder would
need to preserve so the decoder can reconstruct SR-useful low-source detail.
"""

from __future__ import annotations

import argparse
import json
import math
import zlib
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.bayer_detail_residual_oracle_raw.v1"
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


def parse_planes(value: str) -> set[int]:
    names = {item.strip().lower() for item in value.split(",") if item.strip()}
    if not names or "all" in names:
        return set(range(4))
    unknown = sorted(names - set(PLANES))
    if unknown:
        raise ValueError(f"unknown plane names: {', '.join(unknown)}")
    return {PLANES.index(name) for name in names}


def quantize_residual(residual: np.ndarray, quant_step: float) -> np.ndarray:
    if quant_step <= 0.0:
        raise ValueError("--quant-step must be positive")
    return np.rint(residual / quant_step) * quant_step


def compression_estimates(q: np.ndarray) -> dict[str, int]:
    q_i16 = np.clip(np.rint(q), -32768, 32767).astype("<i2", copy=False)
    nonzero = q_i16 != 0
    bitmap = np.packbits(nonzero.reshape(-1).astype(np.uint8))
    values = q_i16[nonzero].astype("<i2", copy=False)
    dense_zlib = zlib.compress(q_i16.tobytes(), level=6)
    bitmap_zlib = zlib.compress(bitmap.tobytes(), level=6)
    values_zlib = zlib.compress(values.tobytes(), level=6)
    return {
        "dense_i16_zlib_bytes": len(dense_zlib),
        "bitmap_zlib_bytes": len(bitmap_zlib),
        "values_i16_zlib_bytes": len(values_zlib),
        "bitmap_values_zlib_bytes": len(bitmap_zlib) + len(values_zlib),
    }


def estimate_sidecar_bits(q: np.ndarray, plane_count: int) -> dict[str, Any]:
    nonzero = q != 0.0
    nnz = int(np.count_nonzero(nonzero))
    total = int(q.size)
    if nnz:
        max_symbol = int(np.max(np.abs(q[nonzero])))
        mag_bits = max(1, int(math.ceil(math.log2(max_symbol + 1))))
    else:
        max_symbol = 0
        mag_bits = 0
    index_bits = max(1, int(math.ceil(math.log2(max(1, total)))))
    sparse_bits = nnz * (index_bits + 1 + mag_bits)
    bitmap_bits = total + nnz * (1 + mag_bits)
    return {
        "plane_count": int(plane_count),
        "total_samples": total,
        "nonzero_samples": nnz,
        "nonzero_pct": 100.0 * nnz / float(total) if total else 0.0,
        "max_abs_quantized_residual": max_symbol,
        "magnitude_bits": mag_bits,
        "index_bits": index_bits,
        "sparse_bits_estimate": int(sparse_bits),
        "bitmap_bits_estimate": int(bitmap_bits),
        "sparse_bytes_estimate": int((sparse_bits + 7) // 8),
        "bitmap_bytes_estimate": int((bitmap_bits + 7) // 8),
        **compression_estimates(q),
    }


def apply_detail_residual(
    codec: np.ndarray,
    clean: np.ndarray,
    *,
    significant_detail_threshold: float,
    residual_threshold: float,
    quant_step: float,
    planes: set[int],
    max_value: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    codec_planes = deinterleave(codec)
    clean_planes = deinterleave(clean)
    out = codec_planes.astype(np.float32).copy()
    all_q = []
    rows: dict[str, Any] = {}
    for i, name in enumerate(PLANES):
        codec_detail = codec_planes[i].astype(np.float32) - blur3_reflect(codec_planes[i])
        clean_detail = clean_planes[i].astype(np.float32) - blur3_reflect(clean_planes[i])
        residual = clean_detail - codec_detail
        if i not in planes:
            q = np.zeros_like(residual, dtype=np.float32)
        else:
            mask = np.ones_like(residual, dtype=bool)
            if significant_detail_threshold > 0.0:
                mask &= np.abs(clean_detail) >= significant_detail_threshold
            if residual_threshold > 0.0:
                mask &= np.abs(residual) >= residual_threshold
            q = np.where(mask, quantize_residual(residual, quant_step), 0.0).astype(np.float32)
            out[i] += q
        all_q.append(q)
        plane_bits = estimate_sidecar_bits(q, 1)
        rows[name] = {
            **plane_bits,
            "residual_rmse_before_counts": rmse(codec_planes[i], clean_planes[i]),
            "residual_rmse_after_counts": rmse(out[i], clean_planes[i]),
        }
    stacked_q = np.stack(all_q, axis=0)
    receipt = {
        "sidecar": estimate_sidecar_bits(stacked_q, len(planes)),
        "planes": rows,
    }
    return np.clip(np.rint(reinterleave(out)), 0, max_value).astype(np.uint16), receipt


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    diff = a.astype(np.float32) - b.astype(np.float32)
    return float(np.sqrt(np.mean(diff * diff)))


def sidecar_specs(sidecar: Path, stems: set[str] | None) -> list[dict[str, Any]]:
    payload = read_json(sidecar)
    default_width = int(payload.get("width12", 0) or 0)
    default_height = int(payload.get("height12", 0) or 0)
    specs: list[dict[str, Any]] = []
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


def run_one(
    spec: dict[str, Any],
    out_raw: Path,
    *,
    significant_detail_threshold: float,
    residual_threshold: float,
    quant_step: float,
    planes: set[int],
    max_value: int,
) -> dict[str, Any]:
    codec = read_raw(Path(spec["codec_raw"]), int(spec["width"]), int(spec["height"]))
    clean = read_raw(Path(spec["clean_raw"]), int(spec["width"]), int(spec["height"]))
    out, residual_receipt = apply_detail_residual(
        codec,
        clean,
        significant_detail_threshold=significant_detail_threshold,
        residual_threshold=residual_threshold,
        quant_step=quant_step,
        planes=planes,
        max_value=max_value,
    )
    write_raw(out_raw, out)
    return {
        **spec,
        "output_raw": str(out_raw),
        "codec_clean_rmse": rmse(codec, clean),
        "output_clean_rmse": rmse(out, clean),
        "output_codec_rmse": rmse(out, codec),
        **residual_receipt,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    sidecars = [row["sidecar"] for row in rows]
    return {
        "image_count": len(rows),
        "codec_clean_rmse_mean": float(np.mean([row["codec_clean_rmse"] for row in rows])),
        "output_clean_rmse_mean": float(np.mean([row["output_clean_rmse"] for row in rows])),
        "nonzero_pct_mean": float(np.mean([row["nonzero_pct"] for row in sidecars])),
        "sparse_bytes_estimate_mean": float(np.mean([row["sparse_bytes_estimate"] for row in sidecars])),
        "sparse_bytes_estimate_max": int(max(row["sparse_bytes_estimate"] for row in sidecars)),
        "bitmap_bytes_estimate_mean": float(np.mean([row["bitmap_bytes_estimate"] for row in sidecars])),
        "dense_i16_zlib_bytes_mean": float(np.mean([row["dense_i16_zlib_bytes"] for row in sidecars])),
        "bitmap_values_zlib_bytes_mean": float(np.mean([row["bitmap_values_zlib_bytes"] for row in sidecars])),
        "bitmap_values_zlib_bytes_max": int(max(row["bitmap_values_zlib_bytes"] for row in sidecars)),
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
    ap.add_argument("--planes", default="all", help="comma-separated subset of r,g1,g2,b or all")
    ap.add_argument("--significant-detail-threshold", type=float, default=2.0)
    ap.add_argument("--residual-threshold", type=float, default=0.0)
    ap.add_argument("--quant-step", type=float, default=1.0)
    ap.add_argument("--max-value", type=int, default=65535)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()

    stems = set(args.stem or []) or None
    planes = parse_planes(args.planes)
    if args.pair_sidecar:
        if not args.out_dir:
            raise ValueError("--pair-sidecar requires --out-dir")
        specs = sidecar_specs(args.pair_sidecar, stems)
        rows = [
            run_one(
                spec,
                args.out_dir / f"{spec['image']}.raw",
                significant_detail_threshold=args.significant_detail_threshold,
                residual_threshold=args.residual_threshold,
                quant_step=args.quant_step,
                planes=planes,
                max_value=args.max_value,
            )
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
                significant_detail_threshold=args.significant_detail_threshold,
                residual_threshold=args.residual_threshold,
                quant_step=args.quant_step,
                planes=planes,
                max_value=args.max_value,
            )
        ]

    receipt = {
        "schema": SCHEMA,
        "policy": "diagnostic_oracle_not_for_runtime",
        "pair_sidecar": str(args.pair_sidecar) if args.pair_sidecar else None,
        "planes": [PLANES[i] for i in sorted(planes)],
        "significant_detail_threshold": args.significant_detail_threshold,
        "residual_threshold": args.residual_threshold,
        "quant_step": args.quant_step,
        "max_value": args.max_value,
        "summary": summarize(rows),
        "images": rows,
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"image_count": len(rows), "summary": receipt["summary"], "receipt": str(args.receipt) if args.receipt else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
