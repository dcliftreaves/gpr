#!/usr/bin/env python3
"""Compare fused encoder coefficient bands against decoder rANS output.

This is a diagnostic receipt, not a quality gate. It answers one narrow
question: does the fused wrapper/rANS path return the same quantized bands the
encoder handed to Pass 2?
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np


COEFF_RE = re.compile(r"ch(?P<ch>\d+)_s(?P<slot>\d+)_w(?P<w>\d+)_h(?P<h>\d+)\.s32$")


def parse_coeff_name(path: Path) -> tuple[int, int, int, int]:
    match = COEFF_RE.match(path.name)
    if not match:
        raise ValueError(f"unexpected coeff filename: {path}")
    return (
        int(match.group("ch")),
        int(match.group("slot")),
        int(match.group("w")),
        int(match.group("h")),
    )


def load_s32(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype=np.int32)
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path}: got {arr.size} int32 values, expected {expected}")
    return arr


def compare_dirs(encode_dir: Path, decode_dir: Path) -> dict:
    encode_files = {parse_coeff_name(p): p for p in encode_dir.glob("*.s32")}
    decode_files = {parse_coeff_name(p): p for p in decode_dir.glob("*.s32")}
    keys = sorted(set(encode_files) | set(decode_files))

    rows = []
    exact_count = 0
    compared_count = 0
    worst_max_abs = 0
    worst_nonzero_diff = 0
    missing = []

    for key in keys:
        epath = encode_files.get(key)
        dpath = decode_files.get(key)
        ch, slot, width, height = key
        if epath is None or dpath is None:
            missing.append(
                {
                    "channel": ch,
                    "slot": slot,
                    "width": width,
                    "height": height,
                    "encode_present": epath is not None,
                    "decode_present": dpath is not None,
                }
            )
            continue
        enc = load_s32(epath, width, height)
        dec = load_s32(dpath, width, height)
        diff = dec.astype(np.int64) - enc.astype(np.int64)
        nonzero = int(np.count_nonzero(diff))
        max_abs = int(np.max(np.abs(diff))) if diff.size else 0
        exact = nonzero == 0
        compared_count += 1
        exact_count += int(exact)
        worst_max_abs = max(worst_max_abs, max_abs)
        worst_nonzero_diff = max(worst_nonzero_diff, nonzero)
        rows.append(
            {
                "channel": ch,
                "slot": slot,
                "width": width,
                "height": height,
                "n": int(diff.size),
                "exact": exact,
                "nonzero_diff": nonzero,
                "max_abs_diff": max_abs,
                "mean_abs_diff": float(np.mean(np.abs(diff))) if diff.size else 0.0,
            }
        )

    return {
        "compared_bands": compared_count,
        "exact_bands": exact_count,
        "all_exact": compared_count > 0 and exact_count == compared_count and not missing,
        "worst_max_abs_diff": worst_max_abs,
        "worst_nonzero_diff": worst_nonzero_diff,
        "missing": missing,
        "bands": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True, type=Path, help="path to coeff_io_tool")
    ap.add_argument("--raw", required=True, type=Path)
    ap.add_argument("--width", required=True, type=int)
    ap.add_argument("--height", required=True, type=int)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--pixel-format", type=int, default=1)
    ap.add_argument("--quality", type=int, default=3)
    ap.add_argument("--wavelet-levels", type=int, default=3)
    ap.add_argument("--keep-raw-output", action="store_true")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    encode_dir = args.output_dir / "encode_quant_coeffs"
    decode_dir = args.output_dir / "decode_quant_coeffs"
    for path in (encode_dir, decode_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    decoded_raw = args.output_dir / "decoded.raw"
    env = os.environ.copy()
    env.update(
        {
            "GPR_INCLUDE_LL": "1",
            "FUSED_MULTI_LEVEL": "1",
            "FUSED_WAVELET_LEVELS": str(args.wavelet_levels),
            "FUSED_QUALITY": str(args.quality),
            "GPR_BENCH_PIXEL_FORMAT": str(args.pixel_format),
            "GPR_DUMP_ENCODE_COEFFS": str(encode_dir),
            "GPR_DUMP_DECODE_QUANT_COEFFS": str(decode_dir),
            "TMPDIR": os.environ.get("TMPDIR", "/Volumes/OWC_8TB/gpr_work/tmp"),
        }
    )

    cmd = [
        str(args.tool),
        str(args.raw),
        str(args.width),
        str(args.height),
        str(decoded_raw),
    ]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True, check=False)
    result = {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "config": {
            "pixel_format": args.pixel_format,
            "quality": args.quality,
            "wavelet_levels": args.wavelet_levels,
            "width": args.width,
            "height": args.height,
        },
    }
    if proc.returncode == 0:
        result["comparison"] = compare_dirs(encode_dir, decode_dir)
    else:
        result["comparison"] = None

    if decoded_raw.exists() and not args.keep_raw_output:
        decoded_raw.unlink()

    receipt = args.output_dir / "coeff_roundtrip_receipt.json"
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["comparison"], indent=2) if result["comparison"] else proc.stderr)
    print(f"receipt: {receipt}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
