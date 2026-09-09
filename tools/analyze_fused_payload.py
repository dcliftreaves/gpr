#!/usr/bin/env python3
"""Analyze fused `.gpr` payload composition and storage-target headroom.

This is intentionally format-level tooling: it does not judge image quality.
It answers whether a candidate has enough byte-rate margin for the current
Mission 1 storage target, and which bands/codecs are worth optimizing next.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import struct
import zlib
from pathlib import Path
from typing import Any


FUSED_MAGIC = 0x44535546
FUSED_RAW_LL_MAGIC = 0x314C4C46
FUSED_PRED_LL_MAGIC = 0x324C4C46
HEADER_STRUCT = struct.Struct("<12I")
FLL2_META_STRUCT = struct.Struct("<4I")
SLOTS_SINGLE_LEVEL = ("LL", "LH", "HL", "HH")
DEFAULT_STORAGE_TARGET_NAME = "Lexar Professional SILVER PLUS SDXC/microSDXC UHS-I (128GB-1TB)"
DEFAULT_STORAGE_TARGET_NOTE = (
    "Published 128GB-1TB SILVER PLUS profile is 205 MB/s read and 150 MB/s "
    "write. The 64GB microSD SKU is 205/100 and must override the write target."
)


class PayloadError(RuntimeError):
    pass


class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.acc = 0
        self.bits = 0

    def get_bit(self) -> int:
        if self.bits == 0:
            if self.pos >= len(self.data):
                raise PayloadError("FLL2 bitstream ended early")
            self.acc = self.data[self.pos]
            self.pos += 1
            self.bits = 8
        bit = self.acc & 1
        self.acc >>= 1
        self.bits -= 1
        return bit

    def get_bits(self, nbits: int) -> int:
        out = 0
        for i in range(nbits):
            out |= self.get_bit() << i
        return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="fused .gpr payload")
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--storage-target-name", default=DEFAULT_STORAGE_TARGET_NAME)
    ap.add_argument("--storage-target-read-mbps", type=float, default=205.0)
    ap.add_argument("--storage-target-write-mbps", type=float, default=150.0)
    ap.add_argument("--storage-target-safety-margin", type=float, default=0.90)
    ap.add_argument("--storage-target-note", default=DEFAULT_STORAGE_TARGET_NOTE)
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--output", type=Path)
    return ap.parse_args()


def zigzag_decode(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def zigzag_encode(value: int) -> int:
    return (value << 1) if value >= 0 else ((-value << 1) - 1)


def rice_bits_for_unsigned(value: int, k: int) -> int:
    return (value >> k) + 1 + k


def decode_fll2_residuals(payload: bytes, width: int, height: int, rice_k: int, predictor: int = 0) -> list[int]:
    br = BitReader(payload)
    residuals: list[int] = []
    rows: list[list[int]] = []
    for y in range(height):
        row: list[int] = []
        prev = rows[y - 1] if y > 0 else None
        left = 0
        for x in range(width):
            q = 0
            while br.get_bit():
                q += 1
                if q > 0x1FFFF:
                    raise PayloadError("FLL2 unary run exceeded decoder guard")
            r = br.get_bits(rice_k) if rice_k > 0 else 0
            residual = zigzag_decode((q << rice_k) | r)
            up = prev[x] if prev is not None else left
            pred = ((left + up) >> 1) if predictor == 1 else left
            value = pred + residual
            if value < 0:
                value = 0
            elif value > 65535:
                value = 65535
            left = value
            row.append(value)
            residuals.append(residual)
        rows.append(row)
    return residuals


def fll2_stats(data: bytes) -> dict[str, Any]:
    if len(data) < FLL2_META_STRUCT.size:
        raise PayloadError("short FLL2 band")
    magic, meta, width, height = FLL2_META_STRUCT.unpack_from(data)
    if magic != FUSED_PRED_LL_MAGIC:
        raise PayloadError("not FLL2")
    rice_k = meta & 0xFF
    predictor = (meta >> 8) & 0xFF
    if predictor not in (0, 1):
        raise PayloadError(f"unsupported FLL2 predictor {predictor}")
    payload = data[FLL2_META_STRUCT.size :]
    residuals = decode_fll2_residuals(payload, width, height, rice_k, predictor)
    abs_residuals = [abs(v) for v in residuals]
    zz = [zigzag_encode(v) for v in residuals]
    by_k = []
    for k in range(16):
        bits = sum(rice_bits_for_unsigned(v, k) for v in zz)
        total_bytes = FLL2_META_STRUCT.size + ((bits + 7) // 8)
        by_k.append({"k": k, "estimated_bytes": total_bytes, "delta_vs_current": total_bytes - len(data)})
    best = min(by_k, key=lambda row: row["estimated_bytes"])
    return {
        "codec": "fll2_pred_ll",
        "rice_k": rice_k,
        "predictor": predictor,
        "width": width,
        "height": height,
        "payload_bytes": len(payload),
        "coefficients": len(residuals),
        "abs_residual_mean": statistics.fmean(abs_residuals) if abs_residuals else 0.0,
        "abs_residual_p50": percentile(abs_residuals, 50),
        "abs_residual_p90": percentile(abs_residuals, 90),
        "abs_residual_p99": percentile(abs_residuals, 99),
        "zero_residual_fraction": (sum(1 for v in residuals if v == 0) / len(residuals)) if residuals else 0.0,
        "rice_k_sweep": by_k,
        "best_rice_k": best,
    }


def percentile(values: list[int], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = (len(vals) - 1) * pct / 100.0
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(vals[lo])
    return float(vals[lo] * (hi - idx) + vals[hi] * (idx - lo))


def byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def parse_fused(data: bytes) -> tuple[dict[str, int], list[int], int]:
    if len(data) < HEADER_STRUCT.size:
        raise PayloadError("file is smaller than FUSED_HEADER")
    fields = HEADER_STRUCT.unpack_from(data)
    names = (
        "magic",
        "version",
        "width",
        "height",
        "pixel_format",
        "quality",
        "is_rggb",
        "log_bits",
        "prescale",
        "multi_level",
        "num_bands",
        "decimate",
    )
    header = dict(zip(names, fields))
    if header["magic"] != FUSED_MAGIC:
        raise PayloadError(f"not a fused .gpr payload: magic=0x{header['magic']:08x}")
    num_bands = header["num_bands"]
    table_off = HEADER_STRUCT.size
    table_len = num_bands * 4
    if table_off + table_len > len(data):
        raise PayloadError("band-size table exceeds file")
    band_sizes = list(struct.unpack_from(f"<{num_bands}I", data, table_off))
    payload_off = table_off + table_len
    if payload_off + sum(band_sizes) > len(data):
        raise PayloadError("band payloads exceed file")
    return header, band_sizes, payload_off


def band_label(header: dict[str, int], index: int) -> dict[str, Any]:
    if not header["multi_level"] and header["num_bands"] in (12, 16):
        slots = SLOTS_SINGLE_LEVEL if header["num_bands"] == 16 else SLOTS_SINGLE_LEVEL[1:]
        slots_per_channel = len(slots)
        return {
            "channel": index // slots_per_channel,
            "slot": slots[index % slots_per_channel],
            "level": 1,
        }
    return {"channel": None, "slot": f"band{index}", "level": None}


def analyze(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    data = path.read_bytes()
    header, band_sizes, payload_off = parse_fused(data)
    cursor = payload_off
    bands = []
    totals_by_slot: dict[str, int] = {}
    zlib_total = 0
    fll2_total = 0
    fll2_best_total = 0
    for index, size in enumerate(band_sizes):
        payload = data[cursor : cursor + size]
        cursor += size
        label = band_label(header, index)
        slot = str(label["slot"])
        totals_by_slot[slot] = totals_by_slot.get(slot, 0) + size
        magic = struct.unpack_from("<I", payload)[0] if len(payload) >= 4 else None
        codec = "empty" if size == 0 else "jans"
        extra: dict[str, Any] = {}
        if magic == FUSED_RAW_LL_MAGIC:
            codec = "fll1_raw_ll"
        elif magic == FUSED_PRED_LL_MAGIC:
            codec = "fll2_pred_ll"
            extra = fll2_stats(payload)
            fll2_total += size
            fll2_best_total += int(extra["best_rice_k"]["estimated_bytes"])
        zbytes = len(zlib.compress(payload, level=9)) if payload else 0
        zlib_total += zbytes
        row = {
            "index": index,
            **label,
            "codec": codec,
            "bytes": size,
            "MiB": size / (1024 * 1024),
            "fraction_of_payload": size / sum(band_sizes) if sum(band_sizes) else 0.0,
            "zlib9_bytes": zbytes,
            "zlib9_savings_bytes": size - zbytes,
            "byte_entropy_bits": byte_entropy(payload),
        }
        row.update(extra)
        bands.append(row)

    total_frame_bytes = len(data)
    payload_bytes = sum(band_sizes)
    target_write = args.storage_target_write_mbps
    budget_write = target_write * args.storage_target_safety_margin
    required_write = total_frame_bytes * args.fps / 1_000_000
    budget_frame_bytes = budget_write * 1_000_000 / args.fps
    frame_gap = total_frame_bytes - budget_frame_bytes
    return {
        "input": str(path),
        "file_bytes": total_frame_bytes,
        "payload_bytes": payload_bytes,
        "container_overhead_bytes": total_frame_bytes - payload_bytes,
        "MiB_per_frame": total_frame_bytes / (1024 * 1024),
        "header": header,
        "storage_target": {
            "name": args.storage_target_name,
            "fps": args.fps,
            "target_read_MBps": args.storage_target_read_mbps,
            "target_write_MBps": target_write,
            "profile_note": args.storage_target_note,
            "safety_margin": args.storage_target_safety_margin,
            "budget_write_MBps": budget_write,
            "required_write_MBps": required_write,
            "budget_frame_bytes": budget_frame_bytes,
            "budget_frame_MiB": budget_frame_bytes / (1024 * 1024),
            "gap_bytes": frame_gap,
            "gap_MiB": frame_gap / (1024 * 1024),
            "fits_target": frame_gap <= 0,
        },
        "totals_by_slot": totals_by_slot,
        "zlib9_payload_bytes": zlib_total,
        "zlib9_payload_savings_bytes": payload_bytes - zlib_total,
        "fll2_current_bytes": fll2_total,
        "fll2_best_rice_bytes": fll2_best_total,
        "fll2_best_rice_savings_bytes": fll2_total - fll2_best_total,
        "bands": bands,
    }


def main() -> int:
    args = parse_args()
    result = analyze(args.input, args)
    text = json.dumps(result, indent=2 if args.pretty else None, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
