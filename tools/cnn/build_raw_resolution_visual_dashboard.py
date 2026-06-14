#!/usr/bin/env python3
"""Build a rendered visual dashboard for 2K/4K raw resolution targets.

This is a proxy visual gate for raw outputs. It intentionally renders source
and candidate Bayer with the same simple Bayer-to-RGB path, so differences come
from the raw target, not from DNG color science or camera profiles.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/cnn"))
sys.path.insert(0, str(REPO / "tools/test"))

from bench_raw_resolution_targets import decode_gpr_target, default_external_root, frame_paths  # noqa: E402
from evaluate_raw_resolution_targets import find_source_dng, read_bayer_from_dng, source_targets  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402


PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "dE2000_mean": 3.0}
TARGET_CHOICES = ("2k_raw_0p5x", "2k_raw_0p5x_fast", "2k_raw_0p5x_l2hh", "4k_raw_1x")
DEFAULT_TARGET = "2k_raw_0p5x"
REFERENCE_TARGET = {
    "2k_raw_0p5x": "2k_raw_0p5x",
    "2k_raw_0p5x_fast": "2k_raw_0p5x",
    "2k_raw_0p5x_l2hh": "2k_raw_0p5x",
    "4k_raw_1x": "4k_raw_1x",
}


def bayer_to_proxy_rgb(bayer: np.ndarray, lo: float, hi: float) -> np.ndarray:
    h, w = bayer.shape
    planes = [
        bayer[0::2, 0::2].astype(np.float32),
        bayer[0::2, 1::2].astype(np.float32),
        bayer[1::2, 0::2].astype(np.float32),
        bayer[1::2, 1::2].astype(np.float32),
    ]
    resized: list[np.ndarray] = []
    for plane in planes:
        img = Image.fromarray(plane, mode="F").resize((w, h), Image.Resampling.BILINEAR)
        resized.append(np.asarray(img, dtype=np.float32))
    green = 0.5 * (resized[1] + resized[2])
    rgb = np.stack([resized[0], green, resized[3]], axis=-1)
    rgb = np.clip((rgb - lo) / max(1.0, hi - lo), 0.0, 1.0)
    rgb = np.power(rgb, 1.0 / 2.2)
    return (rgb * 255.0 + 0.5).astype(np.uint8)


def tone_window(ref_bayer: np.ndarray) -> tuple[float, float]:
    sample = ref_bayer.astype(np.float32)
    lo = float(np.percentile(sample, 0.1))
    hi = float(np.percentile(sample, 99.8))
    if hi <= lo + 1.0:
        hi = lo + 1.0
    return lo, hi


def fixed_crops(width: int, height: int, crop: int) -> dict[str, tuple[int, int, int, int]]:
    crop = min(crop, width, height)
    return {
        "upper_left": (0, 0, crop, crop),
        "center": ((width - crop) // 2, (height - crop) // 2, crop, crop),
        "lower_right": (width - crop, height - crop, crop, crop),
    }


def crop_rgb(rgb: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    return rgb[y : y + h, x : x + w]


def save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)


def diff_rgb(ref: np.ndarray, cand: np.ndarray) -> np.ndarray:
    diff = np.abs(ref.astype(np.int16) - cand.astype(np.int16)).astype(np.float32)
    boosted = np.clip(diff * 4.0, 0, 255).astype(np.uint8)
    return boosted


def metric_pass(metrics: dict[str, float]) -> bool:
    lp = metrics.get("lpips", float("nan"))
    ms = metrics.get("ms_ssim", float("nan"))
    y = metrics.get("y_psnr", float("nan"))
    de = metrics.get("dE2000_mean", float("nan"))
    return bool(lp <= PREVIEW["lpips"] and ms >= PREVIEW["ms_ssim"] and y >= PREVIEW["y_psnr"] and de <= PREVIEW["dE2000_mean"])


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0}

    def vals(key: str) -> list[float]:
        return [float(row["metrics"].get(key, float("nan"))) for row in rows]

    out: dict[str, Any] = {
        "count": len(rows),
        "pass_count": sum(1 for row in rows if row["pass"]),
        "pass_rate": sum(1 for row in rows if row["pass"]) / len(rows),
        "worst_lpips": max(vals("lpips")),
        "worst_ms_ssim": min(vals("ms_ssim")),
        "worst_y_psnr": min(vals("y_psnr")),
        "worst_dE2000_mean": max(vals("dE2000_mean")),
    }
    out["preview_thresholds"] = PREVIEW
    return out


def write_dashboard(out_path: Path, payload: dict[str, Any]) -> None:
    rows = sorted(payload["rows"], key=lambda row: (not row["pass"], row["metrics"]["lpips"], -row["metrics"]["ms_ssim"]), reverse=True)
    summary = payload["summary"]
    css = """
    body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#1f2328;background:#fff}
    h1{font-size:24px;margin:0 0 8px} h2{font-size:18px;margin:28px 0 12px}
    .grid{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:8px;margin:14px 0 22px}
    .card{border:1px solid #d0d7de;border-radius:6px;padding:10px;background:#f6f8fa}
    .v{font-size:20px;font-weight:700}.sub{font-size:12px;color:#57606a}
    table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #d8dee4;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}
    .pass{color:#1a7f37}.fail{color:#cf222e}.thumbs{display:flex;gap:12px;align-items:flex-start;overflow-x:auto}
    figure{margin:0}figcaption{font-size:12px;color:#57606a;margin:3px 0 8px}img{image-rendering:auto;max-width:none;border:1px solid #d0d7de}
    .row{border-top:1px solid #d8dee4;padding-top:16px;margin-top:16px}
    """
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(payload['schema'])}</title><style>{css}</style></head><body>",
        f"<h1>{html.escape(payload['target'])} Raw Runtime Visual Dashboard</h1>",
        f"<div class=sub>Generated {html.escape(payload['generated_at'])}. Target {html.escape(payload['target'])}. "
        f"Drop L2 HP: {payload['drop_l2_hp']}. L2 mask: {html.escape(str(payload.get('l2_hp_mask')))}. "
        f"Halfres stream: {payload.get('halfres_stream')}</div>",
        "<div class=grid>",
        f"<div class=card><div class=v>{summary['pass_count']}/{summary['count']}</div><div class=sub>crop rows passing proxy thresholds</div></div>",
        f"<div class=card><div class=v>{summary['worst_lpips']:.4f}</div><div class=sub>worst LPIPS</div></div>",
        f"<div class=card><div class=v>{summary['worst_ms_ssim']:.4f}</div><div class=sub>worst MS-SSIM</div></div>",
        f"<div class=card><div class=v>{summary['worst_y_psnr']:.2f}</div><div class=sub>worst Y-PSNR</div></div>",
        f"<div class=card><div class=v>{summary['worst_dE2000_mean']:.2f}</div><div class=sub>worst dE2000</div></div>",
        "</div>",
        "<h2>Rows</h2><table><thead><tr><th>row</th><th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>dE2000</th><th>verdict</th></tr></thead><tbody>",
    ]
    for row in rows:
        m = row["metrics"]
        cls = "pass" if row["pass"] else "fail"
        parts.append(
            f"<tr><td>{html.escape(row['image_id'])}:{html.escape(row['crop'])}</td>"
            f"<td>{m['lpips']:.4f}</td><td>{m['ms_ssim']:.4f}</td><td>{m['y_psnr']:.2f}</td>"
            f"<td>{m['dE2000_mean']:.2f}</td><td class={cls}>{'PASS' if row['pass'] else 'FAIL'}</td></tr>"
        )
    parts.append("</tbody></table><h2>100% Crops</h2>")
    for row in rows[: min(72, len(rows))]:
        m = row["metrics"]
        cls = "pass" if row["pass"] else "fail"
        parts.append(
            f"<div class=row><b>{html.escape(row['image_id'])}:{html.escape(row['crop'])}</b> "
            f"<span class={cls}>LPIPS {m['lpips']:.4f}, MS {m['ms_ssim']:.4f}, Y {m['y_psnr']:.2f}, dE {m['dE2000_mean']:.2f}</span>"
            "<div class=thumbs>"
        )
        for label, key in (("REF proxy", "ref_png"), (payload["target"], "candidate_png"), ("diff x4", "diff_png")):
            rel = Path(row[key]).relative_to(out_path.parent)
            parts.append(f"<figure><img src='{html.escape(str(rel))}'><figcaption>{label}</figcaption></figure>")
        parts.append("</div></div>")
    parts.append("</body></html>")
    out_path.write_text("\n".join(parts) + "\n")


def main() -> int:
    external_root = default_external_root()
    artifact_root = Path(os.environ.get("GPR_ARTIFACT_ROOT", external_root / "artifacts"))
    tmp_root = Path(os.environ.get("GATE_TMPDIR", external_root / "tmp"))
    source_roots_default = [
        external_root / "barnsky_full_dngs",
        artifact_root / "visual_compare_20260525" / "source_dngs",
        external_root / "cnn" / "diverse_dngs",
        external_root / "pi-pre-wipe-2026-05-29",
    ]

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame-dir", type=Path, default=artifact_root / "upresable" / "halfres")
    ap.add_argument("--source-root", type=Path, action="append", default=None)
    ap.add_argument("--output-dir", type=Path, default=artifact_root / "raw_resolution_targets_20260613" / "visual_fast_2k")
    ap.add_argument("--tmp-dir", type=Path, default=tmp_root)
    ap.add_argument("--decoder", type=Path, default=REPO / "build-local/bin/fused_decode_cli")
    ap.add_argument("--sensor-width", type=int, default=8280)
    ap.add_argument("--sensor-height", type=int, default=5520)
    ap.add_argument("--limit", type=int, default=28)
    ap.add_argument("--image-id", action="append", default=[])
    ap.add_argument("--crop-size", type=int, default=512)
    ap.add_argument("--target", choices=TARGET_CHOICES, default=DEFAULT_TARGET)
    args = ap.parse_args()

    source_roots = args.source_root or source_roots_default
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    crop_dir = args.output_dir / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="raw-target-visual-", dir=args.tmp_dir))

    frames = frame_paths(args.frame_dir, args.limit, args.image_id)
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    t0 = time.perf_counter()
    try:
        for frame in frames:
            image_id = frame.stem
            source = find_source_dng(image_id, source_roots)
            if source is None:
                missing.append({"image_id": image_id, "reason": "missing_source_dng"})
                continue
            ref_bayer = source_targets(read_bayer_from_dng(source))[REFERENCE_TARGET[args.target]]
            cand_raw = work / f"{image_id}_{args.target}.raw"
            target_info = decode_gpr_target(args.decoder, frame, args.sensor_width, args.sensor_height, cand_raw, args.target)
            cand_bayer = np.fromfile(cand_raw, dtype="<u2").reshape(int(target_info["height"]), int(target_info["width"]))
            cand_raw.unlink(missing_ok=True)
            if cand_bayer.shape != ref_bayer.shape:
                raise RuntimeError(f"{image_id} shape mismatch: {cand_bayer.shape} vs {ref_bayer.shape}")
            lo, hi = tone_window(ref_bayer)
            ref_rgb = bayer_to_proxy_rgb(ref_bayer, lo, hi)
            cand_rgb = bayer_to_proxy_rgb(cand_bayer, lo, hi)
            crops = fixed_crops(ref_rgb.shape[1], ref_rgb.shape[0], args.crop_size)
            for crop_name, box in crops.items():
                ref_crop = crop_rgb(ref_rgb, box)
                cand_crop = crop_rgb(cand_rgb, box)
                metrics = compute_visual_metrics(ref_crop, cand_crop)
                passed = metric_pass(metrics)
                stem = f"{image_id}_{crop_name}"
                ref_png = crop_dir / f"{stem}_ref.png"
                cand_png = crop_dir / f"{stem}_candidate.png"
                diff_png = crop_dir / f"{stem}_diff_x4.png"
                save_png(ref_png, ref_crop)
                save_png(cand_png, cand_crop)
                save_png(diff_png, diff_rgb(ref_crop, cand_crop))
                rows.append(
                    {
                        "image_id": image_id,
                        "crop": crop_name,
                        "box": list(box),
                        "source_dng": str(source),
                        "input_gpr": str(frame),
                        "target_info": target_info,
                        "tone_window": [lo, hi],
                        "metrics": metrics,
                        "pass": passed,
                        "ref_png": str(ref_png),
                        "candidate_png": str(cand_png),
                        "diff_png": str(diff_png),
                    }
                )
            print(f"{image_id}: rendered {len(crops)} crops", flush=True)
    finally:
        for child in work.glob("*"):
            child.unlink(missing_ok=True)
        work.rmdir()

    payload = {
        "schema": "raw_resolution_targets_visual_dashboard.v1",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "target": args.target,
        "drop_l2_hp": os.environ.get("GPR_DECODE_HALFRES_DROP_L2_HP") == "1",
        "l2_hp_mask": os.environ.get("GPR_DECODE_HALFRES_L2_MASK"),
        "halfres_stream": os.environ.get("GPR_DECODE_HALFRES_STREAM", "1") != "0",
        "frame_dir": str(args.frame_dir),
        "source_roots": [str(path) for path in source_roots],
        "frame_count": len({row["image_id"] for row in rows}),
        "row_count": len(rows),
        "missing": missing,
        "elapsed_s": time.perf_counter() - t0,
        "summary": summarize(rows),
        "rows": rows,
    }
    json_path = args.output_dir / "raw_resolution_targets_visual_dashboard.json"
    html_path = args.output_dir / "raw_resolution_targets_visual_dashboard.html"
    json_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_dashboard(html_path, payload)
    print(json.dumps({"json": str(json_path), "html": str(html_path), "summary": payload["summary"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
