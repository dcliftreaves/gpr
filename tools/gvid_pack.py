#!/usr/bin/env python3
"""Pack a lexicographic .gpr frame sequence into the neutral .gvid container."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


GVID_MAGIC = 0x44495647
FRAME_MAGIC = 0x004D5246
GVID_VERSION = 1
FLAG_RATE_CONTROL = 0x01
FLAG_DENOISE = 0x02


def positive_float(text: str) -> float:
    value = float(text)
    if value <= 0.0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def pack_gvid(
    frame_dir: Path,
    output: Path,
    *,
    width: int,
    height: int,
    fps: float,
    pixel_format: int,
    quality: int,
    target_mbps: float,
    denoise: bool,
) -> int:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if not (0 <= pixel_format <= 5):
        raise ValueError("pixel-format must be in 0..5")
    if not (0 <= quality <= 8):
        raise ValueError("quality must be in 0..8")
    if fps <= 0.0:
        raise ValueError("fps must be positive")

    frames = sorted(frame_dir.glob("*.gpr"))
    if not frames:
        raise FileNotFoundError(f"no .gpr frames found in {frame_dir}")

    output.parent.mkdir(parents=True, exist_ok=True)
    flags = 0
    if target_mbps > 0.0:
        flags |= FLAG_RATE_CONTROL
    if denoise:
        flags |= FLAG_DENOISE
    fps_x1000 = int(fps * 1000.0 + 0.5)
    target_kbps = int(target_mbps * 8.0 * 1024.0 + 0.5) if target_mbps > 0.0 else 0

    with output.open("wb") as out:
        out.write(struct.pack(
            "<IBBHHHIIIII",
            GVID_MAGIC,
            GVID_VERSION,
            flags,
            pixel_format,
            quality,
            0,
            width,
            height,
            fps_x1000,
            target_kbps,
            len(frames),
        ))
        for idx, frame in enumerate(frames):
            payload = frame.read_bytes()
            if len(payload) > 0xFFFFFFFF:
                raise ValueError(f"frame too large for .gvid header: {frame}")
            out.write(struct.pack("<IIQ", FRAME_MAGIC, len(payload), idx))
            out.write(payload)
    return len(frames)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Pack a directory of .gpr frame payloads into a .gvid video container."
    )
    ap.add_argument("frame_dir", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--fps", type=positive_float, default=24.0)
    ap.add_argument("--pixel-format", type=int, default=4, help="fused pixel_format enum; default RGGB16")
    ap.add_argument("--quality", type=int, default=3)
    ap.add_argument("--target-mbps", type=float, default=0.0)
    ap.add_argument("--denoise", action="store_true")
    args = ap.parse_args(argv)

    try:
        count = pack_gvid(
            args.frame_dir,
            args.output,
            width=args.width,
            height=args.height,
            fps=args.fps,
            pixel_format=args.pixel_format,
            quality=args.quality,
            target_mbps=args.target_mbps,
            denoise=args.denoise,
        )
    except Exception as exc:
        print(f"gvid_pack: {exc}", file=sys.stderr)
        return 1

    print(f"gvid_pack: wrote {args.output} ({count} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
