#!/usr/bin/env python3
"""Synthetic MOV payload roundtrip and macOS ProRes smoke test; no models needed."""
import argparse
import array
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run(*args, env=None):
    result = subprocess.run([str(arg) for arg in args], env=env,
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper-only", action="store_true")
    args = parser.parse_args()
    if not args.wrapper_only and sys.platform != "darwin":
        parser.error("full desktop test requires macOS; use --wrapper-only elsewhere")
    build = Path(os.environ.get("BUILD_DIR", ROOT / "build")).resolve()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GPR_", "FUSED_"))}
    with tempfile.TemporaryDirectory(prefix="gpr-desktop-") as directory:
        work = Path(directory)
        raw, clip = work / "frame.raw", work / "clip.gvid"
        samples = array.array("H", (1024 + (x * 11 + y * 7) % 12000
                                    for y in range(512) for x in range(512)))
        if sys.byteorder != "little":
            samples.byteswap()
        raw.write_bytes(samples.tobytes())
        run(build / "source/app/bench_fused/bench_fused", raw, 512, 512, 2,
            env=dict(env, GPR_BENCH_GVID=str(clip), GPR_BENCH_GVID_FPS="24",
                     GPR_BENCH_PIXEL_FORMAT="4", GPR_INCLUDE_LL="1", FUSED_QUALITY="3"))
        data, pos, payloads = clip.read_bytes(), 32, []
        while pos < len(data):
            magic, size, tag = struct.unpack_from("<IIQ", data, pos)
            assert magic == 0x004D5246 and tag == len(payloads)
            payloads.append(data[pos + 16:pos + 16 + size])
            assert len(payloads[-1]) == size
            pos += 16 + size
        assert len(payloads) == 2
        frames = work / "frames"
        frames.mkdir()
        for index, payload in enumerate(payloads):
            (frames / f"frame_{index:04d}.gpr").write_bytes(payload)
        wrapped, unpacked = work / "wrapped.mov", work / "unpacked"
        run(ROOT / "tools/gpraw/gpraw_pack", "--fps", 24, "--quality", 3,
            "--bit-depth", 16, "--black-level", 0, "--white-level", 65535,
            frames, wrapped)
        run(ROOT / "tools/gpraw/gpraw_unpack", wrapped, unpacked)
        assert [p.read_bytes() for p in sorted(unpacked.glob("*.gpr"))] == payloads
        print("PASS: MOV wrapper preserves both freshly encoded payloads")
        if args.wrapper_only:
            return 0
        metadata = work / "metadata.dng"
        run(build / "source/app/gpr_tools/gpr_tools", "-i", raw, "-w", 512,
            "-h", 512, "-x", "rggb16", "-o", metadata)
        output = work / "review.mov"
        run(ROOT / "tools/gpr2prores/gpr2prores", "--meta-dng", metadata,
            "--no-cnn", "--demosaic", "core-image", "--out-resolution", "2k",
            "--fps", 24, clip, output, env=env)
        probe = json.loads(run("ffprobe", "-v", "error", "-count_frames",
                              "-select_streams", "v:0", "-show_streams", "-of", "json", output))
        stream, = probe["streams"]
        assert stream["codec_name"] == "prores", stream
        assert int(stream["nb_read_frames"]) == 2, stream
        assert stream["avg_frame_rate"] == "24/1", stream
        print("PASS: GVID renders two ProRes frames at the requested timebase")
        compat, compat_frames = work / "compat.gpraw", work / "compat_frames"
        meta_dir = work / "metadata"
        meta_dir.mkdir()
        for index in range(2):
            shutil.copyfile(metadata, meta_dir / f"frame_{index:04d}.dng")
        mov_tool = ROOT / "tools/gpr2prores/gpr_mov_tool"
        run(mov_tool, "pack", frames, compat, "--fps", 24, "--meta-dir", meta_dir)
        run(mov_tool, "unpack", compat, compat_frames)
        assert [p.read_bytes() for p in sorted(compat_frames.glob("*.gpr"))] == payloads
        print("PASS: macOS MOV companion preserves both payloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
