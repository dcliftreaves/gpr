#!/usr/bin/env python3
"""Discover and calibrate raw darkframes.

This is the camera-calibration counterpart to the DNG NoiseProfile analysis.
It deliberately works from raw values, black levels, CFA sites, and ISO/exposure
metadata. The outputs are small JSON/HTML/PNG receipts written outside the repo
by default.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import rawpy


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root()))
ARTIFACT_ROOT = Path(os.environ.get("GPR_ARTIFACT_ROOT", EXTERNAL_ROOT / "artifacts"))
DEFAULT_OUT = ARTIFACT_ROOT / "darkframe_calibration_20260605"


def number_list(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        return [float(v) for v in value]
    return [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", str(value), re.I)]


def as_float(value: Any, default: float = 0.0) -> float:
    values = number_list(value)
    return values[0] if values else default


def read_exif(path: Path) -> dict[str, Any]:
    tags = [
        "-j",
        "-n",
        "-ISO",
        "-BlackLevel",
        "-WhiteLevel",
        "-NoiseProfile",
        "-CFAPattern",
        "-CFAPlaneColor",
        "-Make",
        "-Model",
        "-ExposureTime",
        "-DateTimeOriginal",
        "-FileName",
        "-FileSize",
    ]
    try:
        return json.loads(subprocess.check_output(["exiftool", *tags, str(path)], text=True))[0]
    except Exception as exc:
        return {"SourceFile": str(path), "FileName": path.name, "exif_error": str(exc)}


@dataclass
class RawMeta:
    path: Path
    make: str
    model: str
    iso: int
    exposure_time: float
    black_by_site: dict[str, float]
    white: float
    raw_shape: tuple[int, int]
    pattern: list[list[int]]
    color_desc: str
    exif: dict[str, Any]


def site_name(y: int, x: int, color_index: int, color_desc: str) -> str:
    color = color_desc[color_index] if 0 <= color_index < len(color_desc) else str(color_index)
    return f"{color}{y}{x}"


def read_raw_meta(path: Path, raw: rawpy.RawPy, exif: dict[str, Any]) -> RawMeta:
    pattern_arr = np.asarray(raw.raw_pattern)
    if pattern_arr.shape[0] < 2 or pattern_arr.shape[1] < 2:
        pattern_arr = np.array([[0, 1], [1, 2]], dtype=np.int32)
    pattern = pattern_arr[:2, :2].astype(int)
    color_desc = raw.color_desc.decode("ascii", "replace")
    raw_black = [float(v) for v in raw.black_level_per_channel]
    exif_black = number_list(exif.get("BlackLevel"))
    black_by_site: dict[str, float] = {}
    for y in range(2):
        for x in range(2):
            color_index = int(pattern[y, x])
            name = site_name(y, x, color_index, color_desc)
            if 0 <= color_index < len(raw_black):
                black = raw_black[color_index]
            elif len(exif_black) == 4:
                black = exif_black[y * 2 + x]
            elif exif_black:
                black = float(np.mean(exif_black))
            else:
                black = 0.0
            black_by_site[name] = black

    exif_white = number_list(exif.get("WhiteLevel"))
    white = float(raw.white_level or (np.mean(exif_white) if exif_white else 65535.0))
    return RawMeta(
        path=path,
        make=str(exif.get("Make", "")),
        model=str(exif.get("Model", "")),
        iso=int(as_float(exif.get("ISO"), 0.0)),
        exposure_time=as_float(exif.get("ExposureTime"), 0.0),
        black_by_site=black_by_site,
        white=white,
        raw_shape=tuple(int(v) for v in raw.raw_image_visible.shape),
        pattern=pattern.tolist(),
        color_desc=color_desc,
        exif=exif,
    )


def iter_raw_files(paths: list[Path], extensions: set[str]) -> list[Path]:
    out: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in extensions:
            out.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in extensions:
                    out.append(child)
    return sorted(out)


def site_samples(raw_image: np.ndarray, meta: RawMeta, stride: int) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    pattern = np.asarray(meta.pattern)
    for y in range(2):
        for x in range(2):
            name = site_name(y, x, int(pattern[y, x]), meta.color_desc)
            plane = raw_image[y::2, x::2]
            out[name] = plane[::stride, ::stride].astype(np.float32) - meta.black_by_site[name]
    return out


def robust_sigma(values: np.ndarray) -> float:
    med = float(np.median(values))
    return 1.4826 * float(np.median(np.abs(values - med)))


def discovery_row(path: Path, stride: int, args: argparse.Namespace) -> dict[str, Any]:
    exif = read_exif(path)
    raw = rawpy.imread(str(path))
    try:
        meta = read_raw_meta(path, raw, exif)
        samples_by_site = site_samples(raw.raw_image_visible, meta, stride)
    finally:
        raw.close()

    all_values = np.concatenate([v.ravel() for v in samples_by_site.values()])
    above_black = np.maximum(all_values, 0.0)
    per_site = {}
    for name, values in samples_by_site.items():
        clipped = np.maximum(values, 0.0)
        per_site[name] = {
            "mean_signal_counts": float(np.mean(values)),
            "median_signal_counts": float(np.median(values)),
            "mad_sigma_counts": robust_sigma(values),
            "std_counts": float(np.std(values)),
            "p95_above_black_counts": float(np.percentile(clipped, 95.0)),
            "p99_above_black_counts": float(np.percentile(clipped, 99.0)),
        }

    p95 = float(np.percentile(above_black, 95.0))
    p99 = float(np.percentile(above_black, 99.0))
    p999 = float(np.percentile(above_black, 99.9))
    candidate = p95 <= args.dark_p95_counts and p99 <= args.dark_p99_counts
    return {
        "path": str(path),
        "file_name": path.name,
        "make": meta.make,
        "model": meta.model,
        "iso": meta.iso,
        "exposure_time": meta.exposure_time,
        "raw_shape": list(meta.raw_shape),
        "pattern": meta.pattern,
        "color_desc": meta.color_desc,
        "black_by_site": meta.black_by_site,
        "white": meta.white,
        "has_noise_profile": "NoiseProfile" in exif,
        "dark_candidate": bool(candidate),
        "p50_above_black_counts": float(np.percentile(above_black, 50.0)),
        "p95_above_black_counts": p95,
        "p99_above_black_counts": p99,
        "p999_above_black_counts": p999,
        "mean_signal_counts": float(np.mean(all_values)),
        "std_signal_counts": float(np.std(all_values)),
        "mad_sigma_counts": robust_sigma(all_values),
        "per_site": per_site,
    }


class GridAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.mean: np.ndarray | None = None
        self.m2: np.ndarray | None = None

    def add(self, values: np.ndarray) -> None:
        x = values.astype(np.float64)
        if self.mean is None:
            self.mean = np.zeros_like(x, dtype=np.float64)
            self.m2 = np.zeros_like(x, dtype=np.float64)
        if x.shape != self.mean.shape:
            raise ValueError(f"sample grid shape changed from {self.mean.shape} to {x.shape}")
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (x - self.mean)

    def temporal_std(self) -> np.ndarray:
        if self.m2 is None or self.count < 2:
            assert self.mean is not None
            return np.zeros_like(self.mean)
        return np.sqrt(self.m2 / (self.count - 1))


def hot_fraction(values: np.ndarray, sigma_floor: float, hot_sigma: float, hot_counts: float) -> float:
    sigma = max(robust_sigma(values), sigma_floor, 1e-6)
    threshold = max(hot_counts, hot_sigma * sigma)
    return float(np.mean(np.maximum(values, 0.0) > threshold))


def assemble_sites(sites: dict[str, np.ndarray], meta: RawMeta) -> np.ndarray:
    heights = [v.shape[0] for v in sites.values()]
    widths = [v.shape[1] for v in sites.values()]
    h = min(heights)
    w = min(widths)
    out = np.zeros((h * 2, w * 2), dtype=np.float32)
    pattern = np.asarray(meta.pattern)
    for y in range(2):
        for x in range(2):
            name = site_name(y, x, int(pattern[y, x]), meta.color_desc)
            out[y::2, x::2] = sites[name][:h, :w]
    return out


def save_signed_png(path: Path, arr: np.ndarray) -> None:
    span = float(np.percentile(np.abs(arr), 99.0))
    span = max(span, 1.0)
    img = np.clip((arr / span) * 0.5 + 0.5, 0.0, 1.0)
    Image.fromarray((img * 255.0).astype(np.uint8)).save(path)


def calibrate_group(rows: list[dict[str, Any]], out_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    selected = rows[: args.max_calibration_frames if args.max_calibration_frames > 0 else None]
    grid_acc: dict[str, GridAccumulator] = {}
    frame_stats: list[dict[str, Any]] = []
    first_meta: RawMeta | None = None
    grid_error = ""

    for row in selected:
        path = Path(row["path"])
        exif = read_exif(path)
        raw = rawpy.imread(str(path))
        try:
            meta = read_raw_meta(path, raw, exif)
            if first_meta is None:
                first_meta = meta
            samples = site_samples(raw.raw_image_visible, meta, args.calibration_stride)
        finally:
            raw.close()

        site_rows = {}
        for name, values in samples.items():
            vals = values.ravel()
            site_rows[name] = {
                "mean_counts": float(np.mean(vals)),
                "median_counts": float(np.median(vals)),
                "std_counts": float(np.std(vals)),
                "mad_sigma_counts": robust_sigma(vals),
                "p01_counts": float(np.percentile(vals, 1.0)),
                "p99_counts": float(np.percentile(vals, 99.0)),
                "hot_fraction": hot_fraction(vals, args.hot_sigma_floor, args.hot_sigma, args.hot_counts),
            }
            if not grid_error:
                try:
                    grid_acc.setdefault(name, GridAccumulator()).add(values)
                except ValueError as exc:
                    grid_error = str(exc)
                    grid_acc = {}
        frame_stats.append({"path": str(path), "sites": site_rows})

    if first_meta is None:
        raise RuntimeError("empty darkframe group")

    per_site: dict[str, Any] = {}
    mean_sites: dict[str, np.ndarray] = {}
    temporal_sites: dict[str, np.ndarray] = {}
    for name, acc in grid_acc.items():
        assert acc.mean is not None
        temporal = acc.temporal_std()
        mean_sites[name] = acc.mean.astype(np.float32)
        temporal_sites[name] = temporal.astype(np.float32)
        per_site[name] = {
            "frames": acc.count,
            "mean_residual_counts": float(np.mean(acc.mean)),
            "spatial_fpn_rms_counts": float(np.std(acc.mean)),
            "row_fpn_rms_counts": float(np.std(np.mean(acc.mean, axis=1))),
            "col_fpn_rms_counts": float(np.std(np.mean(acc.mean, axis=0))),
            "temporal_noise_rms_counts": float(np.mean(temporal)),
            "temporal_noise_p95_counts": float(np.percentile(temporal, 95.0)),
        }

    key = group_key(rows[0])
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", key).strip("_")
    artifacts: dict[str, str] = {}
    if mean_sites and temporal_sites:
        mean_mosaic = assemble_sites(mean_sites, first_meta)
        temporal_mosaic = assemble_sites(temporal_sites, first_meta)
        mean_path = out_dir / f"{safe_key}_mean_residual.png"
        temporal_path = out_dir / f"{safe_key}_temporal_noise.png"
        save_signed_png(mean_path, mean_mosaic)
        save_signed_png(temporal_path, temporal_mosaic)
        artifacts["mean_residual"] = str(mean_path)
        artifacts["temporal_noise"] = str(temporal_path)

    return {
        "key": key,
        "frame_count": len(selected),
        "available_candidate_count": len(rows),
        "make": rows[0]["make"],
        "model": rows[0]["model"],
        "iso": rows[0]["iso"],
        "exposure_time": rows[0]["exposure_time"],
        "raw_shape": rows[0]["raw_shape"],
        "calibration_stride": args.calibration_stride,
        "grid_error": grid_error,
        "per_site": per_site,
        "frame_stats": frame_stats,
        "artifacts": artifacts,
    }


def group_key(row: dict[str, Any]) -> str:
    return f"{row['make']} {row['model']} ISO{row['iso']} exp{float(row['exposure_time']):.6g}"


def build_html(summary: dict[str, Any], path: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.3f}"
        return escape(str(v))

    rows = summary["discovery_rows"]
    groups = summary["calibration_groups"]
    html = [
        "<!doctype html><meta charset='utf-8'><title>Darkframe Calibration</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#17212b}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d7dde5;padding:7px;font-size:12px;vertical-align:top}"
        "th{background:#eef2f5}.pass{color:#0b6b35;font-weight:700}.fail{color:#9d1c20;font-weight:700}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}.card{border:1px solid #d7dde5;border-radius:8px;padding:10px}"
        "img{width:100%;height:auto;background:#111}</style>",
        "<h1>Darkframe Calibration</h1>",
        "<p>Candidate detection uses raw signal above black level; calibration metrics are sampled per CFA site.</p>",
        f"<p>files_scanned={summary['files_scanned']} candidates={summary['candidate_count']} groups={len(groups)}</p>",
        "<h2>Calibration Groups</h2>",
        "<table><thead><tr><th>Group</th><th>Frames</th><th>Site</th><th>Mean</th><th>Spatial FPN</th>"
        "<th>Row FPN</th><th>Col FPN</th><th>Temporal RMS</th><th>Temporal p95</th></tr></thead><tbody>",
    ]
    for group in groups:
        if group["per_site"]:
            for site, stats in group["per_site"].items():
                html.append("<tr>" + "".join([
                    f"<td>{escape(group['key'])}</td>",
                    f"<td>{group['frame_count']}</td>",
                    f"<td>{escape(site)}</td>",
                    f"<td>{fmt(stats['mean_residual_counts'])}</td>",
                    f"<td>{fmt(stats['spatial_fpn_rms_counts'])}</td>",
                    f"<td>{fmt(stats['row_fpn_rms_counts'])}</td>",
                    f"<td>{fmt(stats['col_fpn_rms_counts'])}</td>",
                    f"<td>{fmt(stats['temporal_noise_rms_counts'])}</td>",
                    f"<td>{fmt(stats['temporal_noise_p95_counts'])}</td>",
                ]) + "</tr>")
        else:
            html.append(f"<tr><td>{escape(group['key'])}</td><td>{group['frame_count']}</td><td colspan='7'>{escape(group['grid_error'])}</td></tr>")
    html.append("</tbody></table><div class='grid'>")
    for group in groups:
        if not group["artifacts"]:
            continue
        html.append(f"<div class='card'><h3>{escape(group['key'])}</h3>")
        for label, artifact in group["artifacts"].items():
            rel = Path(artifact).relative_to(path.parent)
            html.append(f"<p>{escape(label)}</p><img src='{escape(str(rel))}'>")
        html.append("</div>")
    html.extend([
        "</div><h2>Darkframe Candidates</h2>",
        "<table><thead><tr><th>Status</th><th>File</th><th>Camera</th><th>ISO</th><th>Exposure</th>"
        "<th>p50</th><th>p95</th><th>p99</th><th>p99.9</th><th>Std</th><th>MAD sigma</th></tr></thead><tbody>",
    ])
    for row in rows[: summary["args"]["html_rows"]]:
        status = "candidate" if row["dark_candidate"] else "reject"
        klass = "pass" if row["dark_candidate"] else "fail"
        html.append("<tr>" + "".join([
            f"<td class='{klass}'>{status}</td>",
            f"<td>{escape(row['path'])}</td>",
            f"<td>{escape((row['make'] + ' ' + row['model']).strip())}</td>",
            f"<td>{row['iso']}</td>",
            f"<td>{fmt(row['exposure_time'])}</td>",
            f"<td>{fmt(row['p50_above_black_counts'])}</td>",
            f"<td>{fmt(row['p95_above_black_counts'])}</td>",
            f"<td>{fmt(row['p99_above_black_counts'])}</td>",
            f"<td>{fmt(row['p999_above_black_counts'])}</td>",
            f"<td>{fmt(row['std_signal_counts'])}</td>",
            f"<td>{fmt(row['mad_sigma_counts'])}</td>",
        ]) + "</tr>")
    html.append("</tbody></table>")
    path.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--extensions", nargs="*", default=[".dng", ".nef", ".fff"])
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--discovery-stride", type=int, default=64)
    ap.add_argument("--calibration-stride", type=int, default=32)
    ap.add_argument("--dark-p95-counts", type=float, default=512.0)
    ap.add_argument("--dark-p99-counts", type=float, default=1024.0)
    ap.add_argument("--max-calibration-frames", type=int, default=32)
    ap.add_argument("--hot-sigma-floor", type=float, default=1.0)
    ap.add_argument("--hot-sigma", type=float, default=8.0)
    ap.add_argument("--hot-counts", type=float, default=1024.0)
    ap.add_argument("--html-rows", type=int, default=200)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    extensions = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in args.extensions}
    files = iter_raw_files(args.inputs, extensions)
    if args.max_files > 0:
        files = files[: args.max_files]

    discovery_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for idx, path in enumerate(files, start=1):
        try:
            discovery_rows.append(discovery_row(path, args.discovery_stride, args))
        except Exception as exc:
            failures.append({"path": str(path), "error": str(exc)})
        if idx % 50 == 0:
            print(f"scanned {idx}/{len(files)}", flush=True)

    discovery_rows.sort(key=lambda row: (
        not row["dark_candidate"],
        row["p95_above_black_counts"],
        row["p99_above_black_counts"],
        row["path"],
    ))

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in discovery_rows:
        if row["dark_candidate"]:
            grouped[group_key(row)].append(row)

    calibration_groups = [
        calibrate_group(rows, args.out_dir, args)
        for _, rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    summary = {
        "kind": "darkframe_calibration",
        "args": vars(args) | {
            "inputs": [str(path) for path in args.inputs],
            "out_dir": str(args.out_dir),
        },
        "files_scanned": len(files),
        "candidate_count": sum(1 for row in discovery_rows if row["dark_candidate"]),
        "failure_count": len(failures),
        "failures": failures,
        "discovery_rows": discovery_rows,
        "calibration_groups": calibration_groups,
    }
    json_path = args.out_dir / "darkframe_calibration.json"
    html_path = args.out_dir / "darkframe_calibration.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(summary, html_path)
    print(json_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
