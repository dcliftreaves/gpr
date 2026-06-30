#!/usr/bin/env python3
"""Build same-color raw CFA residual targets for premium still-SR.

This converts the expanded rendered-HF supervision set into a raw-domain
training target. For each crop it loads the source DNG raw and degraded
candidate raw, computes source-minus-candidate residuals, high-passes the
residual without mixing CFA phases, and saves full-resolution repeated 2x2 CFA
planes. Rendered HF remains a review signal; the trainable target is editable
raw signal.
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

from audit_premium_still_sr_raw_cfa_residual import (  # noqa: E402
    candidate_raw_norm,
    corr,
    luma,
    same_color_highpass,
    source_raw_norm,
    target_npzs,
)
from build_premium_still_sr_hf_residual_targets import local_cfa4_planes, sha256_file  # noqa: E402


SCHEMA = "gpr.premium_still_sr_raw_cfa_residual_targets.v1"


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


def load_meta(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    if "meta" not in z.files:
        return []
    meta = json.loads(str(z["meta"]))
    if not isinstance(meta, list):
        return []
    return [row if isinstance(row, dict) else {} for row in meta]


def crop_common(raw_a: np.ndarray, raw_b: np.ndarray, x: int, y: int, crop: int) -> tuple[np.ndarray, np.ndarray]:
    a = raw_a[y : y + crop, x : x + crop]
    b = raw_b[y : y + crop, x : x + crop]
    common_h = min(a.shape[0], b.shape[0])
    common_w = min(a.shape[1], b.shape[1])
    return a[:common_h, :common_w], b[:common_h, :common_w]


def build_from_npz(path: Path, *, max_rows: int | None = None) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray], list[np.ndarray], list[np.ndarray], list[dict[str, Any]]]:
    candidate_cfa: list[np.ndarray] = []
    candidate_hf_cfa: list[np.ndarray] = []
    raw_hf_residual_cfa: list[np.ndarray] = []
    source_hf_cfa: list[np.ndarray] = []
    render_hf_y: list[np.ndarray] = []
    out_rows: list[dict[str, Any]] = []

    with np.load(path, allow_pickle=False) as z:
        rendered_residuals = z["hf_residuals"].astype(np.float32)
        meta = load_meta(z)
        if max_rows is not None:
            rendered_residuals = rendered_residuals[:max_rows]
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
                crop = int(row.get("crop_size") or rendered_residuals[idx].shape[0])
                block = int(row.get("block") or 16)
                src_crop, cand_crop = crop_common(source_raw, candidate_raw, x, y, crop)
                common_h = min(src_crop.shape[0], rendered_residuals[idx].shape[0])
                common_w = min(src_crop.shape[1], rendered_residuals[idx].shape[1])
                src_crop = src_crop[:common_h, :common_w]
                cand_crop = cand_crop[:common_h, :common_w]
                render_y = luma(rendered_residuals[idx, :common_h, :common_w])

                raw_residual = src_crop - cand_crop
                raw_hf = same_color_highpass(raw_residual, block)
                cand_hf = same_color_highpass(cand_crop, block)
                src_hf = same_color_highpass(src_crop, block)

                candidate_cfa.append(local_cfa4_planes(cand_crop).astype(np.float16))
                candidate_hf_cfa.append(local_cfa4_planes(cand_hf).astype(np.float16))
                raw_hf_residual_cfa.append(local_cfa4_planes(raw_hf).astype(np.float16))
                source_hf_cfa.append(local_cfa4_planes(src_hf).astype(np.float16))
                render_hf_y.append(render_y.astype(np.float16))

                out = dict(row)
                out.update(
                    {
                        "source_dng": source_path,
                        "candidate_raw": candidate_path,
                        "target_npz": str(path),
                        "target_index": int(idx),
                        "raw_target_kind": "source_minus_candidate_same_color_highpass_residual",
                        "raw_residual_abs_mean": float(np.mean(np.abs(raw_residual))),
                        "raw_same_color_hf_residual_abs_mean": float(np.mean(np.abs(raw_hf))),
                        "source_raw_same_color_hf_abs_mean": float(np.mean(np.abs(src_hf))),
                        "candidate_raw_same_color_hf_abs_mean": float(np.mean(np.abs(cand_hf))),
                        "render_hf_residual_y_abs_mean": float(np.mean(np.abs(render_y))),
                        "raw_to_render_hf_abs_ratio": float(np.mean(np.abs(raw_hf)) / max(float(np.mean(np.abs(render_y))), 1.0e-12)),
                        "render_y_to_raw_same_color_hf_corr": corr(render_y, raw_hf),
                    }
                )
                out_rows.append(out)
            del source_raw
            del candidate_raw
    return candidate_cfa, candidate_hf_cfa, raw_hf_residual_cfa, source_hf_cfa, render_hf_y, out_rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scenes = sorted({str(row.get("scene_id")) for row in rows})
    return {
        "row_count": len(rows),
        "scene_count": len(scenes),
        "scenes": scenes,
        "raw_residual_abs_mean": stats([float(row["raw_residual_abs_mean"]) for row in rows]),
        "raw_same_color_hf_residual_abs_mean": stats([float(row["raw_same_color_hf_residual_abs_mean"]) for row in rows]),
        "render_hf_residual_y_abs_mean": stats([float(row["render_hf_residual_y_abs_mean"]) for row in rows]),
        "raw_to_render_hf_abs_ratio": stats([float(row["raw_to_render_hf_abs_ratio"]) for row in rows]),
        "render_y_to_raw_same_color_hf_corr_abs": stats(
            [
                abs(float(row["render_y_to_raw_same_color_hf_corr"]))
                for row in rows
                if row["render_y_to_raw_same_color_hf_corr"] is not None
            ]
        ),
    }


def render_html(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    rows = sorted(payload["rows"], key=lambda row: float(row["raw_same_color_hf_residual_abs_mean"]), reverse=True)[:48]
    body_rows = []
    for row in rows:
        corr_value = row.get("render_y_to_raw_same_color_hf_corr")
        corr_text = "n/a" if corr_value is None else f"{float(corr_value):.4f}"
        body_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('scene_id')))}</td>"
            f"<td>{html.escape(str(row.get('crop')))}</td>"
            f"<td>{float(row.get('ev') or 0.0):+.0f}</td>"
            f"<td>{row['raw_same_color_hf_residual_abs_mean']:.6f}</td>"
            f"<td>{row['render_hf_residual_y_abs_mean']:.6f}</td>"
            f"<td>{row['raw_to_render_hf_abs_ratio']:.3f}</td>"
            f"<td>{corr_text}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Raw CFA Residual Targets</title>
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
  <h1>Premium Still-SR Raw CFA Residual Targets</h1>
  <p>Trainable target: source raw minus candidate raw, high-passed separately per CFA phase. Rendered HF is retained only as a review/alignment signal.</p>
  <p>Source receipt: <code>{html.escape(payload['source_target_receipt'])}</code></p>
  <div class="grid">
    <div class="card"><h2>Rows</h2><p>{summary['row_count']} rows / {summary['scene_count']} scenes</p></div>
    <div class="card"><h2>Raw HF Residual</h2><p>median {summary['raw_same_color_hf_residual_abs_mean']['median']:.6f}</p></div>
    <div class="card"><h2>Raw / Render</h2><p>median {summary['raw_to_render_hf_abs_ratio']['median']:.3f}</p></div>
    <div class="card"><h2>Abs Corr</h2><p>median {summary['render_y_to_raw_same_color_hf_corr_abs']['median']:.4f}</p></div>
  </div>
  <h2>Largest Raw Residual Rows</h2>
  <table><thead><tr><th>Scene</th><th>Crop</th><th>EV</th><th>Raw HF residual</th><th>Rendered residual</th><th>Raw/render</th><th>Corr</th></tr></thead><tbody>{''.join(body_rows)}</tbody></table>
</body>
</html>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.target_receipt.read_text(encoding="utf-8"))
    npzs = target_npzs(receipt, args.target_receipt)
    all_candidate_cfa: list[np.ndarray] = []
    all_candidate_hf_cfa: list[np.ndarray] = []
    all_raw_hf_residual_cfa: list[np.ndarray] = []
    all_source_hf_cfa: list[np.ndarray] = []
    all_render_hf_y: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    for npz in npzs:
        candidate_cfa, candidate_hf_cfa, raw_hf_residual_cfa, source_hf_cfa, render_hf_y, part_rows = build_from_npz(
            npz,
            max_rows=args.max_rows_per_npz,
        )
        all_candidate_cfa.extend(candidate_cfa)
        all_candidate_hf_cfa.extend(candidate_hf_cfa)
        all_raw_hf_residual_cfa.extend(raw_hf_residual_cfa)
        all_source_hf_cfa.extend(source_hf_cfa)
        all_render_hf_y.extend(render_hf_y)
        rows.extend(part_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = args.output_dir / "raw_cfa_residual_targets.npz"
    np.savez_compressed(
        npz_path,
        candidate_raw_cfa4=np.stack(all_candidate_cfa, axis=0).astype(np.float16),
        candidate_raw_hf_cfa4=np.stack(all_candidate_hf_cfa, axis=0).astype(np.float16),
        raw_hf_residual_cfa4=np.stack(all_raw_hf_residual_cfa, axis=0).astype(np.float16),
        source_raw_hf_cfa4=np.stack(all_source_hf_cfa, axis=0).astype(np.float16),
        render_hf_residual_y=np.stack(all_render_hf_y, axis=0).astype(np.float16),
        meta=np.asarray(json.dumps(rows, sort_keys=True)),
    )

    payload = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "source_target_receipt": str(args.target_receipt),
        "source_target_receipt_sha256": sha256_file(args.target_receipt),
        "source_target_npzs": [{"path": str(path), "sha256": sha256_file(path)} for path in npzs],
        "output_npz": str(npz_path),
        "output_npz_sha256": sha256_file(npz_path),
        "arrays": {
            "candidate_raw_cfa4": "candidate_raw_local_2x2_cfa_planes_float16_nhwc_repeated_to_crop",
            "candidate_raw_hf_cfa4": "candidate_raw_same_color_highpass_local_2x2_cfa_planes_float16_nhwc",
            "raw_hf_residual_cfa4": "source_minus_candidate_same_color_highpass_residual_float16_nhwc",
            "source_raw_hf_cfa4": "source_raw_same_color_highpass_local_2x2_cfa_planes_float16_nhwc",
            "render_hf_residual_y": "rendered_hf_residual_luma_float16_nhw",
        },
        "policy": {
            "purpose": "trainable_raw_domain_premium_still_sr_target",
            "uses_source_raw": True,
            "runtime_safe": False,
            "rendered_hf_is_review_signal_only": True,
        },
        "summary": summarize(rows),
        "rows": rows,
    }
    json_path = args.output_dir / "raw_cfa_residual_targets.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    payload["receipt"] = str(json_path)
    payload["dashboard"] = str(html_path)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-receipt", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--max-rows-per-npz", type=int)
    args = ap.parse_args()
    payload = build(args)
    print(
        json.dumps(
            {
                "receipt": payload["receipt"],
                "dashboard": payload["dashboard"],
                "npz": payload["output_npz"],
                "rows": payload["summary"]["row_count"],
                "median_raw_hf_residual": payload["summary"]["raw_same_color_hf_residual_abs_mean"]["median"],
                "median_abs_corr": payload["summary"]["render_y_to_raw_same_color_hf_corr_abs"]["median"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
