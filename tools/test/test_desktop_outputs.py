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
    with tempfile.TemporaryDirectory(prefix="gpr desktop ") as directory:
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
        run(ROOT / "tools/gvid_mov/gvid_mov_pack", "--fps", 24, "--quality", 3,
            "--bit-depth", 16, "--black-level", 0, "--white-level", 65535,
            frames, wrapped)
        run(ROOT / "tools/gvid_mov/gvid_mov_unpack", wrapped, unpacked)
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
        compat, compat_frames = work / "compat.mov", work / "compat_frames"
        meta_dir = work / "metadata"
        meta_dir.mkdir()
        for index in range(2):
            shutil.copyfile(metadata, meta_dir / f"frame_{index:04d}.dng")
        mov_tool = ROOT / "tools/gpr2prores/gpr_mov_tool"
        run(mov_tool, "pack", frames, compat, "--fps", 24, "--meta-dir", meta_dir)
        run(mov_tool, "unpack", compat, compat_frames)
        assert [p.read_bytes() for p in sorted(compat_frames.glob("*.gpr"))] == payloads
        print("PASS: macOS MOV companion preserves both payloads")
        summary = run(mov_tool, "info", compat)
        assert "yes (per-frame)" in summary, summary
        for source, reader, destination in (
                (compat, ROOT / "tools/gvid_mov/gvid_mov_unpack", work / "portable cross"),
                (wrapped, mov_tool, work / "desktop cross")):
            command = [reader, source, destination]
            if reader == mov_tool:
                command.insert(1, "unpack")
            run(*command)
            assert [p.read_bytes() for p in sorted(destination.glob("*.gpr"))] == payloads
        print("PASS: both MOV sample tags roundtrip through the other frontend")
        legacy = work / "header sniff.legacy"
        shutil.copyfile(wrapped, legacy)
        for source in (wrapped, compat, legacy):
            rendered = work / f"rendered {source.name}.mov"
            run(ROOT / "tools/gpr2prores/gpr2prores", "--meta-dng", metadata,
                "--no-cnn", "--demosaic", "core-image", "--out-resolution", "2k",
                "--fps", 24, source, rendered, env=env)
            info = json.loads(run("ffprobe", "-v", "error", "-count_frames",
                                  "-select_streams", "v:0", "-show_streams", "-of", "json", rendered))
            video, = info["streams"]
            assert video["codec_name"] == "prores" and int(video["nb_read_frames"]) == 2, video
            assert video["avg_frame_rate"] == "24/1", video
            assert (video["width"], video["height"]) == (stream["width"], stream["height"]), video
        for reader in (ROOT / "tools/gvid_mov/gvid_mov_unpack", mov_tool):
            command = [str(reader), str(output), str(work / "not raw")]
            if reader == mov_tool:
                command.insert(1, "unpack")
            rejected = subprocess.run(command, capture_output=True, text=True, timeout=30)
            assert rejected.returncode != 0, "non-RAW ProRes must not be accepted as RAW packets"
        print("PASS: MOV rendering, paths with spaces, header sniffing and non-RAW rejection")
        broken = work / "truncated exif.mov"
        shutil.copyfile(compat, broken)
        Path(str(broken) + ".exif").write_bytes(b"GEX0" + struct.pack("<I", 100))
        rejected = subprocess.run([str(mov_tool), "unpack", str(broken),
                                   str(work / "broken sidecar")],
                                  capture_output=True, text=True, timeout=30)
        assert rejected.returncode != 0, "truncated EXIF record must fail even when not requested"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
