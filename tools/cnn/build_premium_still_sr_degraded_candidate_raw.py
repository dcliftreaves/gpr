#!/usr/bin/env python3
"""Build a deterministic degraded candidate raw for premium still-SR targets.

The output simulates a conservative 2x loss path: same-color 2x2 Bayer values
are averaged per CFA position, then expanded back to the original raw shape.
It is a target-construction baseline, not a production SR candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_degraded_candidate_raw.v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_raw_from_dng(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    import rawpy

    raw = rawpy.imread(str(path))
    try:
        arr = raw.raw_image.copy().astype("<u2", copy=False)
        meta = {
            "width": int(arr.shape[1]),
            "height": int(arr.shape[0]),
            "black_level_per_channel": [int(v) for v in raw.black_level_per_channel],
            "white_level": int(raw.white_level),
            "raw_pattern": raw.raw_pattern.tolist(),
        }
        return arr, meta
    finally:
        raw.close()


def same_color_box2_roundtrip(raw: np.ndarray) -> np.ndarray:
    height, width = raw.shape
    even_h = height - (height % 2)
    even_w = width - (width % 2)
    core = raw[:even_h, :even_w].astype(np.float32)
    out = np.empty_like(raw)
    for y_phase in (0, 1):
        for x_phase in (0, 1):
            plane = core[y_phase::2, x_phase::2]
            ph, pw = plane.shape
            avg_h = ph - (ph % 2)
            avg_w = pw - (pw % 2)
            avg_core = plane[:avg_h, :avg_w].reshape(avg_h // 2, 2, avg_w // 2, 2).mean(axis=(1, 3))
            expanded = np.repeat(np.repeat(avg_core, 2, axis=0), 2, axis=1)
            restored = np.empty((ph, pw), dtype=np.float32)
            restored[:avg_h, :avg_w] = expanded
            if avg_w < pw:
                restored[:avg_h, avg_w:] = restored[:avg_h, avg_w - 1 : avg_w]
            if avg_h < ph:
                restored[avg_h:, :] = restored[avg_h - 1 : avg_h, :]
            out[y_phase:even_h:2, x_phase:even_w:2] = np.clip(restored, 0, 65535).astype("<u2")
    if even_h < height:
        out[even_h:, :even_w] = out[even_h - 1 : even_h, :even_w]
    if even_w < width:
        out[:, even_w:] = out[:, even_w - 1 : even_w]
    return out


def build(args: argparse.Namespace) -> dict[str, Any]:
    args.output_raw.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    source, source_meta = source_raw_from_dng(args.source_dng)
    candidate = same_color_box2_roundtrip(source)
    candidate.astype("<u2", copy=False).tofile(args.output_raw)
    elapsed = time.perf_counter() - t0
    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "source_dng": str(args.source_dng),
        "source_dng_sha256": sha256_file(args.source_dng),
        "output_raw": str(args.output_raw),
        "output_raw_sha256": sha256_file(args.output_raw),
        "source": source_meta,
        "candidate": {
            "width": source_meta["width"],
            "height": source_meta["height"],
            "bytes": args.output_raw.stat().st_size,
            "degradation": "same_color_box2_downsample_then_nearest_expand",
        },
        "timing_seconds": elapsed,
        "policy": {
            "purpose": "training_target_candidate_baseline",
            "production_sr_candidate": False,
        },
    }
    receipt_path = args.output_raw.with_suffix(args.output_raw.suffix + ".json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    receipt["receipt"] = str(receipt_path)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dng", type=Path, required=True)
    ap.add_argument("--output-raw", type=Path, required=True)
    args = ap.parse_args()
    receipt = build(args)
    print(
        json.dumps(
            {
                "receipt": receipt["receipt"],
                "output_raw": receipt["output_raw"],
                "width": receipt["candidate"]["width"],
                "height": receipt["candidate"]["height"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
