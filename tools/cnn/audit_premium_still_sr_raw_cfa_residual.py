#!/usr/bin/env python3
"""Audit premium still-SR targets against same-color raw CFA residuals.

This is a training-target diagnostic. It checks whether the rendered HF
residual target is coherent with the physically editable raw target:
source raw minus candidate raw, measured on matching same-color Bayer samples.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from build_premium_still_sr_hf_residual_targets import sha256_file  # noqa: E402


SCHEMA = "gpr.premium_still_sr_raw_cfa_residual_audit.v1"


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "max": float(arr.max()),
    }


def corr(a: np.ndarray, b: np.ndarray) -> float | None:
    aa = a.astype(np.float64, copy=False).reshape(-1)
    bb = b.astype(np.float64, copy=False).reshape(-1)
    aa = aa - float(np.mean(aa))
    bb = bb - float(np.mean(bb))
    den = float(np.sqrt(np.sum(aa * aa) * np.sum(bb * bb)))
    if den <= 1.0e-18:
        return None
    return float(np.sum(aa * bb) / den)


def block_lowpass_2d(x: np.ndarray, kernel: int) -> np.ndarray:
    kernel = max(3, int(kernel))
    if kernel % 2 == 0:
        kernel += 1
    pad = kernel // 2
    padded = np.pad(x.astype(np.float32, copy=False), ((pad, pad), (pad, pad)), mode="edge")
    integ = np.pad(np.cumsum(np.cumsum(padded, axis=0), axis=1), ((1, 0), (1, 0)), mode="constant")
    h, w = x.shape
    total = integ[kernel : kernel + h, kernel : kernel + w]
    total -= integ[:h, kernel : kernel + w]
    total -= integ[kernel : kernel + h, :w]
    total += integ[:h, :w]
    return (total / float(kernel * kernel)).astype(np.float32)


def same_color_highpass(raw: np.ndarray, block: int) -> np.ndarray:
    """High-pass a Bayer mosaic without mixing 2x2 CFA phases."""
    out = np.empty_like(raw, dtype=np.float32)
    same_color_kernel = max(3, int(round(block / 2.0)))
    for y_phase in (0, 1):
        for x_phase in (0, 1):
            plane = raw[y_phase::2, x_phase::2].astype(np.float32, copy=False)
            out[y_phase::2, x_phase::2] = plane - block_lowpass_2d(plane, same_color_kernel)
    return out


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[:, :, 0] * 0.2126 + rgb[:, :, 1] * 0.7152 + rgb[:, :, 2] * 0.0722


def source_raw_norm(path: Path) -> tuple[np.ndarray, float, float]:
    import rawpy

    raw = rawpy.imread(str(path))
    try:
        arr = raw.raw_image.copy().astype(np.float32)
        black = float(np.mean(raw.black_level_per_channel)) if raw.black_level_per_channel is not None else 0.0
        white = float(raw.white_level or 65535.0)
    finally:
        raw.close()
    return np.clip((arr - black) / max(white - black, 1.0), 0.0, 1.0), black, white


def candidate_raw_norm(path: Path, *, shape: tuple[int, int], black: float, white: float) -> np.ndarray:
    values = np.fromfile(path, dtype="<u2")
    expected = int(shape[0] * shape[1])
    if values.size != expected:
        raise ValueError(f"{path} has {values.size} pixels, expected {expected}")
    arr = values.reshape(shape).astype(np.float32)
    return np.clip((arr - black) / max(white - black, 1.0), 0.0, 1.0)


def target_npzs(receipt: dict[str, Any], receipt_path: Path) -> list[Path]:
    if receipt.get("schema") == "gpr.premium_still_sr_hf_residual_targets_merged.v1":
        return [Path(str(row["path"])) for row in receipt.get("sources", []) if isinstance(row, dict) and row.get("path")]
    arrays = receipt.get("arrays") if isinstance(receipt.get("arrays"), dict) else {}
    npz = arrays.get("npz") or receipt.get("output_npz")
    if not npz:
        raise ValueError(f"{receipt_path} does not identify a target NPZ")
    path = Path(str(npz))
    return [path if path.is_absolute() else receipt_path.parent / path]


def load_meta(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    if "meta" not in z.files:
        return []
    meta = json.loads(str(z["meta"]))
    if not isinstance(meta, list):
        return []
    return [row if isinstance(row, dict) else {} for row in meta]


def audit_npz(path: Path, *, max_rows: int | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with np.load(path, allow_pickle=False) as z:
        residuals = z["hf_residuals"].astype(np.float32)
        meta = load_meta(z)
        if max_rows is not None:
            residuals = residuals[:max_rows]
            meta = meta[:max_rows]

        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(meta):
            source = row.get("source_dng")
            candidate = row.get("candidate_raw")
            if source and candidate:
                groups[(str(source), str(candidate))].append(idx)

        for (source_path, candidate_path), indices in groups.items():
            source_raw, black, white = source_raw_norm(Path(source_path))
            candidate_raw = candidate_raw_norm(Path(candidate_path), shape=source_raw.shape, black=black, white=white)
            for idx in indices:
                row = meta[idx]
                x, y = [int(v) for v in row.get("crop_xy", [0, 0])]
                crop = int(row.get("crop_size") or residuals.shape[1])
                block = int(row.get("block") or 16)
                src_crop = source_raw[y : y + crop, x : x + crop]
                cand_crop = candidate_raw[y : y + crop, x : x + crop]
                common_h = min(src_crop.shape[0], cand_crop.shape[0], residuals[idx].shape[0])
                common_w = min(src_crop.shape[1], cand_crop.shape[1], residuals[idx].shape[1])
                src_crop = src_crop[:common_h, :common_w]
                cand_crop = cand_crop[:common_h, :common_w]
                render_y = luma(residuals[idx, :common_h, :common_w])

                raw_residual = src_crop - cand_crop
                raw_hf = same_color_highpass(raw_residual, block)
                cand_hf = same_color_highpass(cand_crop, block)
                source_hf = same_color_highpass(src_crop, block)

                phase_corrs: list[float] = []
                for y_phase in (0, 1):
                    for x_phase in (0, 1):
                        c = corr(render_y[y_phase::2, x_phase::2], raw_hf[y_phase::2, x_phase::2])
                        if c is not None:
                            phase_corrs.append(c)

                raw_hf_abs = float(np.mean(np.abs(raw_hf)))
                raw_residual_abs = float(np.mean(np.abs(raw_residual)))
                render_abs = float(np.mean(np.abs(render_y)))
                source_hf_abs = float(np.mean(np.abs(source_hf)))
                cand_hf_abs = float(np.mean(np.abs(cand_hf)))
                out.append(
                    {
                        "target_npz": str(path),
                        "target_index": int(idx),
                        "scene_id": row.get("scene_id"),
                        "crop": row.get("crop"),
                        "ev": row.get("ev"),
                        "source_dng": source_path,
                        "candidate_raw": candidate_path,
                        "crop_xy": [x, y],
                        "crop_size": crop,
                        "block": block,
                        "render_hf_residual_y_abs_mean": render_abs,
                        "raw_residual_abs_mean": raw_residual_abs,
                        "raw_same_color_hf_residual_abs_mean": raw_hf_abs,
                        "source_raw_same_color_hf_abs_mean": source_hf_abs,
                        "candidate_raw_same_color_hf_abs_mean": cand_hf_abs,
                        "raw_to_render_hf_abs_ratio": float(raw_hf_abs / max(render_abs, 1.0e-12)),
                        "raw_hf_to_source_hf_abs_ratio": float(raw_hf_abs / max(source_hf_abs, 1.0e-12)),
                        "render_y_to_raw_same_color_hf_corr": corr(render_y, raw_hf),
                        "render_y_to_raw_same_color_hf_phase_corr_max_abs": (
                            float(max(abs(v) for v in phase_corrs)) if phase_corrs else None
                        ),
                        "render_y_to_candidate_raw_hf_corr": corr(render_y, cand_hf),
                    }
                )
            del source_raw
            del candidate_raw
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_scene[str(row.get("scene_id"))].append(row)
    scene_rows = []
    for scene, scene_data in sorted(by_scene.items()):
        scene_rows.append(
            {
                "scene_id": scene,
                "row_count": len(scene_data),
                "raw_same_color_hf_residual_abs_mean": stats(
                    [float(row["raw_same_color_hf_residual_abs_mean"]) for row in scene_data]
                ),
                "render_y_to_raw_same_color_hf_corr": stats(
                    [
                        abs(float(row["render_y_to_raw_same_color_hf_corr"]))
                        for row in scene_data
                        if row["render_y_to_raw_same_color_hf_corr"] is not None
                    ]
                ),
                "raw_hf_to_source_hf_abs_ratio": stats([float(row["raw_hf_to_source_hf_abs_ratio"]) for row in scene_data]),
            }
        )
    return {
        "row_count": len(rows),
        "scene_count": len(by_scene),
        "render_hf_residual_y_abs_mean": stats([float(row["render_hf_residual_y_abs_mean"]) for row in rows]),
        "raw_residual_abs_mean": stats([float(row["raw_residual_abs_mean"]) for row in rows]),
        "raw_same_color_hf_residual_abs_mean": stats([float(row["raw_same_color_hf_residual_abs_mean"]) for row in rows]),
        "raw_to_render_hf_abs_ratio": stats([float(row["raw_to_render_hf_abs_ratio"]) for row in rows]),
        "raw_hf_to_source_hf_abs_ratio": stats([float(row["raw_hf_to_source_hf_abs_ratio"]) for row in rows]),
        "render_y_to_raw_same_color_hf_corr_abs": stats(
            [
                abs(float(row["render_y_to_raw_same_color_hf_corr"]))
                for row in rows
                if row["render_y_to_raw_same_color_hf_corr"] is not None
            ]
        ),
        "render_y_to_raw_same_color_hf_phase_corr_max_abs": stats(
            [
                float(row["render_y_to_raw_same_color_hf_phase_corr_max_abs"])
                for row in rows
                if row["render_y_to_raw_same_color_hf_phase_corr_max_abs"] is not None
            ]
        ),
        "scenes": scene_rows,
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.target_receipt.read_text(encoding="utf-8"))
    npzs = target_npzs(receipt, args.target_receipt)
    rows: list[dict[str, Any]] = []
    for npz in npzs:
        rows.extend(audit_npz(npz, max_rows=args.max_rows_per_npz))
    return {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "target_receipt": str(args.target_receipt),
        "target_receipt_sha256": sha256_file(args.target_receipt),
        "target_npzs": [{"path": str(path), "sha256": sha256_file(path)} for path in npzs],
        "config": {"max_rows_per_npz": args.max_rows_per_npz},
        "policy": {
            "purpose": "diagnose whether rendered HF supervision agrees with editable raw same-color residuals",
            "uses_source_raw": True,
            "runtime_safe": False,
        },
        "summary": summarize(rows),
        "rows": rows,
    }


def render_html(payload: dict[str, Any]) -> str:
    def fmt(value: Any, places: int = 4) -> str:
        if value is None:
            return "n/a"
        return f"{float(value):.{places}f}"

    summary = payload["summary"]
    scene_rows = []
    for row in summary["scenes"]:
        scene_rows.append(
            "<tr>"
            f"<td>{html.escape(row['scene_id'])}</td>"
            f"<td>{row['row_count']}</td>"
            f"<td>{row['raw_same_color_hf_residual_abs_mean']['median']:.6f}</td>"
            f"<td>{row['render_y_to_raw_same_color_hf_corr']['median']:.4f}</td>"
            f"<td>{row['raw_hf_to_source_hf_abs_ratio']['median']:.4f}</td>"
            "</tr>"
        )
    worst = sorted(
        payload["rows"],
        key=lambda r: abs(float(r["render_y_to_raw_same_color_hf_corr"] or 0.0)),
    )[:24]
    worst_rows = []
    for row in worst:
        corr_value = row["render_y_to_raw_same_color_hf_corr"]
        worst_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('scene_id')))}</td>"
            f"<td>{html.escape(str(row.get('crop')))}</td>"
            f"<td>{float(row.get('ev') or 0.0):+.0f}</td>"
            f"<td>{row['render_hf_residual_y_abs_mean']:.6f}</td>"
            f"<td>{row['raw_same_color_hf_residual_abs_mean']:.6f}</td>"
            f"<td>{fmt(corr_value)}</td>"
            f"<td>{fmt(row['render_y_to_raw_same_color_hf_phase_corr_max_abs'])}</td>"
            f"<td>{row['raw_hf_to_source_hf_abs_ratio']:.4f}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Raw CFA Residual Audit</title>
  <style>
    body {{ margin: 28px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ border: 1px solid #d8dde3; border-radius: 8px; padding: 14px; background: #f8fafb; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; }}
    th {{ background: #eef2f5; }}
    code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Premium Still-SR Raw CFA Residual Audit</h1>
  <p>This compares rendered HF residual supervision with the editable raw target: source raw minus candidate raw, high-passed without mixing CFA phases.</p>
  <p>Target receipt: <code>{html.escape(payload['target_receipt'])}</code></p>
  <div class="grid">
    <div class="card"><h2>Rows</h2><p>{summary['row_count']} rows / {summary['scene_count']} scenes</p></div>
    <div class="card"><h2>Raw HF Residual</h2><p>median {summary['raw_same_color_hf_residual_abs_mean']['median']:.6f}</p></div>
    <div class="card"><h2>Raw / Render Ratio</h2><p>median {summary['raw_to_render_hf_abs_ratio']['median']:.3f}</p></div>
    <div class="card"><h2>Abs Corr</h2><p>median {summary['render_y_to_raw_same_color_hf_corr_abs']['median']:.4f}</p></div>
    <div class="card"><h2>Phase Abs Corr</h2><p>median {summary['render_y_to_raw_same_color_hf_phase_corr_max_abs']['median']:.4f}</p></div>
  </div>
  <h2>Scene Summary</h2>
  <table><thead><tr><th>Scene</th><th>Rows</th><th>Raw HF residual median</th><th>Abs corr median</th><th>Raw HF / source HF median</th></tr></thead><tbody>{''.join(scene_rows)}</tbody></table>
  <h2>Weakest Alignment Rows</h2>
  <table><thead><tr><th>Scene</th><th>Crop</th><th>EV</th><th>Rendered residual</th><th>Raw HF residual</th><th>Corr</th><th>Best phase corr</th><th>Raw/source HF</th></tr></thead><tbody>{''.join(worst_rows)}</tbody></table>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-receipt", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--max-rows-per-npz", type=int)
    args = ap.parse_args()
    payload = build_audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_cfa_residual_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(json_path),
                "dashboard": str(html_path),
                "rows": payload["summary"]["row_count"],
                "median_abs_corr": payload["summary"]["render_y_to_raw_same_color_hf_corr_abs"]["median"],
                "median_raw_to_render_ratio": payload["summary"]["raw_to_render_hf_abs_ratio"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
