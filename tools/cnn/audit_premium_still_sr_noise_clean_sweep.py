#!/usr/bin/env python3
"""Sweep conservative noise-floor cleaning for premium still-SR targets."""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from build_premium_still_sr_hf_residual_targets import (  # noqa: E402
    conservative_noise_floor_clean,
    mean_noise_sigma_norm,
    sha256_file,
)


SCHEMA = "gpr.premium_still_sr_noise_clean_sweep.v1"


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


def load_receipt(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def sidecar_paths(receipt: dict[str, Any]) -> list[Path]:
    rows = receipt.get("noise_sidecars", [])
    out: list[Path] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("path"):
                out.append(Path(str(row["path"])))
            elif isinstance(row, str):
                out.append(Path(row))
    return out


def build_sweep(args: argparse.Namespace) -> dict[str, Any]:
    receipt = load_receipt(args.target_receipt)
    arrays = receipt.get("arrays") if isinstance(receipt.get("arrays"), dict) else {}
    npz_path = Path(str(arrays.get("npz") or ""))
    if not npz_path.is_absolute():
        npz_path = args.target_receipt.parent / npz_path
    sidecars = sidecar_paths(receipt)
    if not sidecars:
        raise ValueError(f"{args.target_receipt} has no noise_sidecars")

    with np.load(npz_path, allow_pickle=False) as z:
        residuals = z["hf_residuals"].astype(np.float32)
        source_hf = z["source_hf_targets"].astype(np.float32)
        meta = json.loads(str(z["meta"])) if "meta" in z.files else receipt.get("rows", [])
    candidate_hf = source_hf - residuals

    base_abs = [float(np.mean(np.abs(residuals[i]))) for i in range(residuals.shape[0])]
    gains: list[dict[str, Any]] = []
    for gain in args.render_gain:
        floor, floor_rows = mean_noise_sigma_norm(sidecars, render_gain=float(gain))
        if floor is None:
            raise ValueError("noise sidecars did not contain usable training-target sigma")
        row_stats: list[dict[str, Any]] = []
        for idx in range(residuals.shape[0]):
            cleaned, clean_stats = conservative_noise_floor_clean(
                residuals[idx],
                source_hf[idx],
                candidate_hf[idx],
                noise_floor=floor,
                sigma_mult=args.sigma_mult,
                texture_mult=args.texture_mult,
            )
            row_meta = meta[idx] if isinstance(meta, list) and idx < len(meta) and isinstance(meta[idx], dict) else {}
            row_stats.append(
                {
                    "index": idx,
                    "scene_id": row_meta.get("scene_id"),
                    "crop": row_meta.get("crop"),
                    "ev": row_meta.get("ev"),
                    "base_residual_abs_mean": base_abs[idx],
                    "cleaned_residual_abs_mean": float(np.mean(np.abs(cleaned))),
                    **clean_stats,
                }
            )
        gains.append(
            {
                "render_gain": float(gain),
                "render_noise_floor": float(floor),
                "sidecar_rows": floor_rows,
                "row_count": len(row_stats),
                "changed_fraction": stats([float(row["changed_fraction"]) for row in row_stats]),
                "removed_abs_mean": stats([float(row["removed_abs_mean"]) for row in row_stats]),
                "removed_energy_fraction": stats([float(row["removed_energy_fraction"]) for row in row_stats]),
                "cleaned_residual_abs_mean": stats([float(row["cleaned_residual_abs_mean"]) for row in row_stats]),
                "rows": row_stats,
            }
        )

    return {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "target_receipt": str(args.target_receipt),
        "target_receipt_sha256": sha256_file(args.target_receipt),
        "target_npz": str(npz_path),
        "target_npz_sha256": sha256_file(npz_path),
        "sidecars": [{"path": str(path), "sha256": sha256_file(path)} for path in sidecars],
        "config": {
            "sigma_mult": args.sigma_mult,
            "texture_mult": args.texture_mult,
            "render_gain": [float(v) for v in args.render_gain],
        },
        "base": {
            "row_count": int(residuals.shape[0]),
            "residual_abs_mean": stats(base_abs),
        },
        "gains": gains,
        "interpretation": (
            "This sweeps a training-target cleaning policy only. It does not make a runtime render path; "
            "source-derived HF remains training supervision, while calibrated darkframe sidecars define the noise floor."
        ),
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = []
    for gain in payload["gains"]:
        rows.append(
            "<tr>"
            f"<td>{gain['render_gain']:.2f}</td>"
            f"<td>{gain['render_noise_floor']:.8f}</td>"
            f"<td>{gain['changed_fraction']['median']:.5f}</td>"
            f"<td>{gain['changed_fraction']['max']:.5f}</td>"
            f"<td>{gain['removed_abs_mean']['median']:.8f}</td>"
            f"<td>{gain['removed_energy_fraction']['median']:.8f}</td>"
            f"<td>{gain['cleaned_residual_abs_mean']['median']:.8f}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Noise-Clean Sweep</title>
  <style>
    body {{ margin: 28px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; }}
    th {{ background: #f1f4f6; }}
    code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Premium Still-SR Noise-Clean Sweep</h1>
  <p>{html.escape(payload['interpretation'])}</p>
  <p>Target: <code>{html.escape(payload['target_receipt'])}</code></p>
  <p>Base median residual abs mean: <b>{payload['base']['residual_abs_mean']['median']:.8f}</b></p>
  <table>
    <thead><tr><th>Render gain</th><th>Noise floor</th><th>Changed median</th><th>Changed max</th><th>Removed abs median</th><th>Removed energy median</th><th>Cleaned residual median</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-receipt", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--render-gain", action="append", type=float, help="Render-domain gain to apply to raw normalized sigma; repeat to sweep.")
    ap.add_argument("--sigma-mult", type=float, default=1.0)
    ap.add_argument("--texture-mult", type=float, default=2.0)
    args = ap.parse_args()
    if args.render_gain is None:
        args.render_gain = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]

    payload = build_sweep(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "noise_clean_sweep.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
