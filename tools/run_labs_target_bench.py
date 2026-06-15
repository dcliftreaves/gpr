#!/usr/bin/env python3
"""Run or simulate a Labs target-style `.gvid` capture bench.

On target hardware this wraps `bench_fused` with `GPR_BENCH_WRITE_ALL`, packs
the emitted `.gpr` frames into a strict v1 `.gvid`, and writes a JSON receipt
with timing, storage, memory, drop, validation, and interruption-recovery
fields.

Use `--simulate` only for CI/schema smoke tests. Simulated receipts are not
target evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import shutil
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
GVID_CLIP_MAGIC = 0x44495647
GVID_FRAME_MAGIC = 0x004D5246
GVID_VERSION = 1
CLIP_HEADER_SIZE = 32
FRAME_HEADER_SIZE = 16


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def maxrss_kb() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return value // 1024
    return value


def children_maxrss_kb() -> int:
    value = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    if sys.platform == "darwin":
        return value // 1024
    return value


def loadavg() -> list[float] | None:
    if not hasattr(os, "getloadavg"):
        return None
    try:
        return [float(v) for v in os.getloadavg()]
    except OSError:
        return None


def percentile(sorted_values: list[float], frac: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, round((len(sorted_values) - 1) * frac)))
    return float(sorted_values[idx])


def summarize_ms(values: list[float]) -> dict[str, float | int]:
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
        "p99_ms": percentile(vals, 0.99),
        "max_ms": vals[-1],
        "fps_mean": 1000.0 / mean if mean > 0 else 0.0,
        "fps_median": 1000.0 / median if median > 0 else 0.0,
    }


def read_temp_c() -> float | None:
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None
    marker = "temp="
    if marker not in out:
        return None
    try:
        return float(out.split(marker, 1)[1].split("'C", 1)[0])
    except Exception:
        return None


def run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def bench_times_from_stdout(stdout: str) -> list[float]:
    vals: list[float] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            vals.append(float(line))
        except ValueError:
            continue
    return vals


def write_gvid(frame_paths: list[Path], out: Path, width: int, height: int, fps: float, quality: int, pixel_format: int) -> None:
    fps_x1000 = int(round(fps * 1000.0))
    with out.open("wb") as f:
        f.write(struct.pack(
            "<IBBHHHIIIII",
            GVID_CLIP_MAGIC,
            GVID_VERSION,
            0,
            pixel_format,
            quality,
            0,
            width,
            height,
            fps_x1000,
            0,
            len(frame_paths),
        ))
        for tag, path in enumerate(frame_paths):
            payload = path.read_bytes()
            if not payload:
                raise ValueError(f"empty frame payload: {path}")
            f.write(struct.pack("<IIQ", GVID_FRAME_MAGIC, len(payload), tag))
            f.write(payload)


def validate_gvid(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < CLIP_HEADER_SIZE:
        raise ValueError("too small for clip header")
    clip = struct.unpack("<IBBHHHIIIII", data[:CLIP_HEADER_SIZE])
    magic, version, flags, pixel_format, quality, reserved2 = clip[:6]
    width, height, fps_x1000, target_kbps, frame_count_hint = clip[6:]
    if magic != GVID_CLIP_MAGIC or version != GVID_VERSION:
        raise ValueError("bad .gvid magic/version")
    if flags & ~0x03 or pixel_format > 5 or quality > 8 or reserved2:
        raise ValueError("bad .gvid clip fields")
    if width == 0 or height == 0 or fps_x1000 == 0:
        raise ValueError("bad .gvid dimensions/fps")
    if bool(flags & 0x01) != bool(target_kbps):
        raise ValueError("rate-control flag/target mismatch")
    pos = CLIP_HEADER_SIZE
    frame_count = 0
    last_tag: int | None = None
    payload_bytes = 0
    while pos < len(data):
        if len(data) - pos < FRAME_HEADER_SIZE:
            raise ValueError("truncated frame header")
        frame_magic, payload_size, tag = struct.unpack("<IIQ", data[pos:pos + FRAME_HEADER_SIZE])
        pos += FRAME_HEADER_SIZE
        if frame_magic != GVID_FRAME_MAGIC or payload_size == 0:
            raise ValueError("bad frame header")
        if payload_size > len(data) - pos:
            raise ValueError("truncated payload")
        if last_tag is not None and tag <= last_tag:
            raise ValueError("non-monotonic frame tag")
        last_tag = tag
        frame_count += 1
        payload_bytes += payload_size
        pos += payload_size
    if frame_count_hint and frame_count_hint != frame_count:
        raise ValueError("frame_count_hint mismatch")
    return {
        "valid": True,
        "width": width,
        "height": height,
        "fps_x1000": fps_x1000,
        "frame_count": frame_count,
        "payload_bytes": payload_bytes,
    }


def complete_frame_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < CLIP_HEADER_SIZE:
        return 0
    pos = CLIP_HEADER_SIZE
    count = 0
    last_tag: int | None = None
    while pos < len(data):
        if len(data) - pos < FRAME_HEADER_SIZE:
            return count
        frame_magic, payload_size, tag = struct.unpack("<IIQ", data[pos:pos + FRAME_HEADER_SIZE])
        pos += FRAME_HEADER_SIZE
        if frame_magic != GVID_FRAME_MAGIC or payload_size == 0:
            return count
        if payload_size > len(data) - pos:
            return count
        if last_tag is not None and tag <= last_tag:
            return count
        last_tag = tag
        count += 1
        pos += payload_size
    return count


def synth_frames(frame_dir: Path, frame_count: int) -> list[float]:
    frame_dir.mkdir(parents=True, exist_ok=True)
    times: list[float] = []
    for idx in range(frame_count):
        payload = (f"synthetic-frame-{idx:06d}\n".encode("ascii") * (idx % 7 + 1))
        t0 = time.perf_counter()
        (frame_dir / f"frame_{idx:04d}.gpr").write_bytes(payload)
        times.append((time.perf_counter() - t0) * 1000.0 + 1.0)
    return times


def run_bench(args: argparse.Namespace, frame_dir: Path) -> tuple[list[float], subprocess.CompletedProcess[str] | None]:
    if args.simulate:
        return synth_frames(frame_dir, args.frames), None
    if not args.bench or not args.bench.is_file():
        raise RuntimeError("--bench is required and must point to bench_fused unless --simulate is set")
    if not args.raw or not args.raw.is_file():
        raise RuntimeError("--raw is required and must point to the source Bayer raw unless --simulate is set")
    env = os.environ.copy()
    env.update({
        "GPR_INCLUDE_LL": "1",
        "FUSED_MULTI_LEVEL": "1",
        "FUSED_WAVELET_LEVELS": "2",
        "GPR_COL_DECIMATE": "2",
        "GPR_ROW_DECIMATE": "2",
        "GPR_BENCH_WRITE_ALL": str(frame_dir),
    })
    cmd = [str(args.bench), str(args.raw), str(args.source_width), str(args.source_height), str(args.frames)]
    result = run_cmd(cmd, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"bench failed: {result.stderr[-2000:]}")
    return bench_times_from_stdout(result.stdout), result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bench", type=Path, help="bench_fused binary on target")
    ap.add_argument("--raw", type=Path, help="source Bayer raw input on target")
    ap.add_argument("--output-dir", type=Path, default=Path(os.environ.get("GPR_ARTIFACT_ROOT", "/Volumes/OWC_8TB/gpr_work/artifacts")) / "labs_target_bench")
    ap.add_argument("--frames", type=int, default=14400, help="frames to run; 14400 = 10 minutes at 24 fps")
    ap.add_argument("--target-fps", type=float, default=24.0)
    ap.add_argument("--source-width", type=int, default=8280)
    ap.add_argument("--source-height", type=int, default=5520)
    ap.add_argument("--capture-width", type=int, default=8280)
    ap.add_argument("--capture-height", type=int, default=5520)
    ap.add_argument("--quality", type=int, default=3)
    ap.add_argument("--pixel-format", type=int, default=4)
    ap.add_argument("--simulate", action="store_true", help="write a tiny synthetic receipt for CI/schema tests")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = args.output_dir / "frames"
    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True)

    temp_start = read_temp_c()
    load_start = loadavg()
    wall_start = time.time()
    times_ms, bench_result = run_bench(args, frame_dir)
    wall_s = time.time() - wall_start
    temp_end = read_temp_c()
    load_end = loadavg()

    frame_paths = sorted(frame_dir.glob("frame_*.gpr"))
    expected_tags = {f"frame_{idx:04d}.gpr" for idx in range(args.frames)}
    actual_tags = {path.name for path in frame_paths}
    missing = sorted(expected_tags - actual_tags)
    total_frame_bytes = sum(path.stat().st_size for path in frame_paths)

    gvid = args.output_dir / "capture.gvid"
    write_gvid(frame_paths, gvid, args.capture_width, args.capture_height, args.target_fps, args.quality, args.pixel_format)
    gvid_info = validate_gvid(gvid)

    truncated = args.output_dir / "capture_interrupted_tail.gvid"
    data = gvid.read_bytes()
    truncated.write_bytes(data[:-1] if len(data) > 1 else data)
    interruption = {
        "truncated_path": str(truncated),
        "validator_rejects_truncated": False,
        "complete_frames_recovered": complete_frame_count(truncated),
    }
    try:
        validate_gvid(truncated)
    except Exception as exc:
        interruption["validator_rejects_truncated"] = True
        interruption["reject_reason"] = str(exc)

    timing = summarize_ms(times_ms)
    receipt = {
        "schema": "gpr_labs_target_bench.v1",
        "simulated": bool(args.simulate),
        "repo_commit": git_commit(),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {
            "node": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "target": {
            "name": "Pi 5 / Mission 1 stand-in" if not args.simulate else "synthetic smoke",
            "fps": args.target_fps,
            "duration_target_s": args.frames / args.target_fps if args.target_fps else 0,
            "actual_wall_s": wall_s,
        },
        "capture": {
            "source_width": args.source_width,
            "source_height": args.source_height,
            "capture_width": args.capture_width,
            "capture_height": args.capture_height,
            "quality": args.quality,
            "pixel_format": args.pixel_format,
            "frames_requested": args.frames,
            "frames_written": len(frame_paths),
            "dropped_frames": len(missing),
            "missing_frames": missing[:100],
        },
        "timing": timing,
        "storage": {
            "frame_dir": str(frame_dir),
            "total_frame_bytes": total_frame_bytes,
            "gvid_bytes": gvid.stat().st_size,
            "write_MBps_wall": (total_frame_bytes / (1024 * 1024) / wall_s) if wall_s > 0 else 0.0,
            "fsync_policy": "bench_fused fclose per frame; wrapper packs .gvid after run",
        },
        "memory": {
            "wrapper_maxrss_kb": maxrss_kb(),
            "bench_child_maxrss_kb": children_maxrss_kb(),
        },
        "cpu": {
            "loadavg_start": load_start,
            "loadavg_end": load_end,
            "utilization_policy": "load average receipt; per-core utilization requires target runner instrumentation",
        },
        "thermal": {
            "start_temp_c": temp_start,
            "end_temp_c": temp_end,
        },
        "gvid": {
            "path": str(gvid),
            "sha256": sha256_file(gvid),
            "validation": gvid_info,
        },
        "interruption_recovery": interruption,
        "bench": {
            "cmd": [str(args.bench), str(args.raw), str(args.source_width), str(args.source_height), str(args.frames)] if not args.simulate else None,
            "stdout_tail": bench_result.stdout[-2000:] if bench_result else None,
            "stderr_tail": bench_result.stderr[-2000:] if bench_result else None,
        },
        "verdict": {
            "fps_target_met": float(timing.get("fps_median", 0.0)) >= args.target_fps,
            "no_drops": len(missing) == 0,
            "gvid_valid": bool(gvid_info.get("valid")),
            "interruption_recovery_proven": bool(interruption["validator_rejects_truncated"]),
            "target_evidence": not args.simulate,
        },
    }
    out = args.output_dir / "labs_target_bench.json"
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(out), "verdict": receipt["verdict"], "timing": timing}, indent=2))
    ok = receipt["verdict"]["gvid_valid"] and receipt["verdict"]["no_drops"]
    if not args.simulate:
        ok = ok and receipt["verdict"]["fps_target_met"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
