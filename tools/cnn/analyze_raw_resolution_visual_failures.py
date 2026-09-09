#!/usr/bin/env python3
"""Analyze raw-resolution visual dashboard failures.

This tool turns a rendered raw-target dashboard into a compact signal report:
failure rows, by-crop pass rates, phase shift, gradient-energy ratio, MAE, and
correlation. It can also rerun lower-right edge-margin probes from the raw
frames to separate literal edge sensitivity from broader texture loss.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/cnn"))
sys.path.insert(0, str(REPO / "tools/test"))

from bench_raw_resolution_targets import decode_gpr_target, default_external_root  # noqa: E402
from build_raw_resolution_visual_dashboard import (  # noqa: E402
    bayer_to_proxy_rgb,
    crop_rgb,
    tone_window,
)
from evaluate_raw_resolution_targets import find_source_dng, read_bayer_from_dng, source_targets  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402


REFERENCE_TARGET = {
    "2k_raw_0p5x": "2k_raw_0p5x",
    "2k_raw_0p5x_fast": "2k_raw_0p5x",
    "2k_raw_0p5x_l2hh": "2k_raw_0p5x",
    "4k_raw_1x": "4k_raw_1x",
}


def load_gray(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def gradient_energy(gray: np.ndarray) -> float:
    gray = gray.astype(np.float32)
    gx = np.diff(gray, axis=1)
    gy = np.diff(gray, axis=0)
    return float(np.mean(np.abs(gx)) + np.mean(np.abs(gy)))


def phase_shift(ref: np.ndarray, cand: np.ndarray) -> dict[str, float]:
    ref32 = ref.astype(np.float32)
    cand32 = cand.astype(np.float32)
    window = cv2.createHanningWindow((ref32.shape[1], ref32.shape[0]), cv2.CV_32F)
    (shift_x, shift_y), response = cv2.phaseCorrelate(ref32, cand32, window)
    return {
        "shift_x_px": float(shift_x),
        "shift_y_px": float(shift_y),
        "response": float(response),
    }


def crop_signal_stats(row: dict[str, Any]) -> dict[str, float]:
    ref_path = Path(row["ref_png"])
    cand_path_raw = row.get("candidate_png")
    if not cand_path_raw:
        raise ValueError(
            "dashboard row is missing candidate_png; regenerate it with "
            "tools/cnn/build_raw_resolution_visual_dashboard.py"
        )
    cand_path = Path(cand_path_raw)
    ref = load_gray(ref_path)
    cand = load_gray(cand_path)
    diff = cand - ref
    ref_ge = gradient_energy(ref)
    cand_ge = gradient_energy(cand)
    corr = float(np.corrcoef(ref.ravel(), cand.ravel())[0, 1])
    stats = {
        "mae": float(np.mean(np.abs(diff))),
        "mean_diff": float(np.mean(diff)),
        "std_diff": float(np.std(diff)),
        "ref_gradient_energy": ref_ge,
        "candidate_gradient_energy": cand_ge,
        "gradient_ratio": float(cand_ge / max(ref_ge, 1e-9)),
        "correlation": corr,
    }
    stats.update(phase_shift(ref, cand))
    return stats


def summarize_numbers(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "min": None, "max": None}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "mean": float(np.mean(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def dashboard_signal_summary(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for row in payload.get("rows") or []:
        stats = crop_signal_stats(row)
        out = {
            "image_id": row.get("image_id"),
            "crop": row.get("crop"),
            "pass": bool(row.get("pass")),
            "metrics": row.get("metrics") or {},
            "signal": stats,
        }
        rows_out.append(out)

    by_crop: dict[str, dict[str, Any]] = {}
    for crop in sorted({str(row["crop"]) for row in rows_out}):
        crop_rows = [row for row in rows_out if row["crop"] == crop]
        by_crop[crop] = {
            "count": len(crop_rows),
            "pass_count": sum(1 for row in crop_rows if row["pass"]),
            "lpips": summarize_numbers([float(row["metrics"]["lpips"]) for row in crop_rows]),
            "gradient_ratio": summarize_numbers([float(row["signal"]["gradient_ratio"]) for row in crop_rows]),
            "mae": summarize_numbers([float(row["signal"]["mae"]) for row in crop_rows]),
            "correlation": summarize_numbers([float(row["signal"]["correlation"]) for row in crop_rows]),
            "shift_x_abs": summarize_numbers([abs(float(row["signal"]["shift_x_px"])) for row in crop_rows]),
            "shift_y_abs": summarize_numbers([abs(float(row["signal"]["shift_y_px"])) for row in crop_rows]),
        }

    failing = [row for row in rows_out if not row["pass"]]
    summary = {
        "count": len(rows_out),
        "pass_count": sum(1 for row in rows_out if row["pass"]),
        "fail_count": len(failing),
        "by_crop": by_crop,
        "top_failures": sorted(
            failing,
            key=lambda row: float(row["metrics"].get("lpips", 0.0)),
            reverse=True,
        )[:20],
    }
    return rows_out, summary


def default_source_roots(external_root: Path, artifact_root: Path) -> list[Path]:
    return [
        external_root / "barnsky_full_dngs",
        artifact_root / "visual_compare_20260525" / "source_dngs",
        external_root / "cnn" / "diverse_dngs",
        external_root / "pi-pre-wipe-2026-05-29",
    ]


def edge_margin_probe(args: argparse.Namespace, payload: dict[str, Any]) -> list[dict[str, Any]]:
    target = str(payload.get("target"))
    ref_key = REFERENCE_TARGET.get(target)
    if not ref_key:
        raise ValueError(f"unsupported target for edge probe: {target}")

    rows = payload.get("rows") or []
    failing_lower_right = [
        row for row in rows if row.get("crop") == "lower_right" and not row.get("pass")
    ]
    if args.edge_probe_limit:
        failing_lower_right = failing_lower_right[: args.edge_probe_limit]

    out_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="raw-target-edge-probe-", dir=args.tmp_dir) as tmp:
        tmp_dir = Path(tmp)
        for row in failing_lower_right:
            image_id = str(row["image_id"])
            frame = Path(row["input_gpr"])
            source = find_source_dng(image_id, args.source_root)
            if source is None:
                out_rows.append({"image_id": image_id, "error": "missing_source_dng"})
                continue

            ref_bayer = source_targets(read_bayer_from_dng(source))[ref_key]
            cand_raw = tmp_dir / f"{image_id}_{target}.raw"
            target_info = decode_gpr_target(
                args.decoder,
                frame,
                args.sensor_width,
                args.sensor_height,
                cand_raw,
                target,
            )
            cand_bayer = np.fromfile(cand_raw, dtype="<u2").reshape(
                int(target_info["height"]),
                int(target_info["width"]),
            )
            cand_raw.unlink(missing_ok=True)

            lo, hi = tone_window(ref_bayer)
            ref_rgb = bayer_to_proxy_rgb(ref_bayer, lo, hi)
            cand_rgb = bayer_to_proxy_rgb(cand_bayer, lo, hi)
            h, w = ref_rgb.shape[:2]
            crop = min(args.crop_size, w, h)
            margin_rows = []
            for margin in args.edge_margins:
                if margin + crop > min(w, h):
                    continue
                box = (w - crop - margin, h - crop - margin, crop, crop)
                metrics = compute_visual_metrics(crop_rgb(ref_rgb, box), crop_rgb(cand_rgb, box))
                margin_rows.append(
                    {
                        "margin_px": int(margin),
                        "box": list(box),
                        "metrics": metrics,
                        "pass": bool(
                            metrics["lpips"] <= 0.15
                            and metrics["ms_ssim"] >= 0.95
                            and metrics["y_psnr"] >= 28.0
                            and metrics["dE2000_mean"] <= 3.0
                        ),
                    }
                )
            out_rows.append(
                {
                    "image_id": image_id,
                    "source_dng": str(source),
                    "input_gpr": str(frame),
                    "target_info": target_info,
                    "margins": margin_rows,
                }
            )
    return out_rows


def main() -> int:
    external_root = default_external_root()
    artifact_root = Path(os.environ.get("GPR_ARTIFACT_ROOT", external_root / "artifacts"))
    tmp_root = Path(os.environ.get("GATE_TMPDIR", external_root / "tmp"))

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dashboard_json", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--edge-probe", action="store_true")
    ap.add_argument("--edge-probe-limit", type=int, default=4)
    ap.add_argument("--edge-margins", type=int, nargs="+", default=[0, 16, 32, 64, 96, 128, 192, 256])
    ap.add_argument("--source-root", type=Path, action="append", default=None)
    ap.add_argument("--tmp-dir", type=Path, default=tmp_root)
    ap.add_argument("--decoder", type=Path, default=REPO / "build-local/bin/fused_decode_cli")
    ap.add_argument("--sensor-width", type=int, default=8280)
    ap.add_argument("--sensor-height", type=int, default=5520)
    ap.add_argument("--crop-size", type=int, default=512)
    args = ap.parse_args()

    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.source_root = args.source_root or default_source_roots(external_root, artifact_root)

    payload = json.loads(args.dashboard_json.read_text())
    rows, summary = dashboard_signal_summary(payload)
    result: dict[str, Any] = {
        "schema": "raw_resolution_visual_failure_analysis.v1",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "dashboard_json": str(args.dashboard_json),
        "target": payload.get("target"),
        "dashboard_summary": payload.get("summary"),
        "summary": summary,
        "rows": rows,
    }
    if args.edge_probe:
        result["edge_margin_probe"] = edge_margin_probe(args, payload)

    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
