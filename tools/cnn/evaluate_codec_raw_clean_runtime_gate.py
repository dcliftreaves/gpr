#!/usr/bin/env python3
"""Evaluate raw-clean acceptance using decoded codec input instead of sidecar labels."""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import numpy as np

from analyze_dng_noise_profile import plane_validation_stats
from build_raw_clean_ref_targets import clean_plane, contract_failure_reasons
from train_codec_raw_clean_sr import upsample_codec


DEFAULT_PAIRS = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_20260604/"
    "ml2_q3_dec2_raw_clean_pairs.npz"
)
DEFAULT_OUT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/"
    "runtime_gate_w64"
)
CHANNELS = ("R", "G1", "G2", "B")


def plane_dict(arr: np.ndarray) -> dict[str, np.ndarray]:
    return {name: arr[idx].astype(np.float32) for idx, name in enumerate(CHANNELS)}


def evaluate_pair(
    codec_planes: np.ndarray,
    sigma_planes: np.ndarray,
    args: argparse.Namespace,
) -> dict[str, Any]:
    codec_up = upsample_codec(codec_planes.astype(np.float32), sigma_planes.shape[1:])
    raw_ch = plane_dict(codec_up)
    sigma_ch = plane_dict(sigma_planes)
    residual_ch: dict[str, np.ndarray] = {}
    plane_rows: dict[str, dict[str, float]] = {}
    residual_energy = 0.0
    sigma_energy = 0.0
    for ch_name in CHANNELS:
        _, residual, _, stats = clean_plane(raw_ch[ch_name], sigma_ch[ch_name], args)
        residual_ch[ch_name] = residual
        plane_rows[ch_name] = stats
        residual_energy += float(np.sum(residual * residual))
        sigma_energy += float(np.sum(sigma_ch[ch_name] * sigma_ch[ch_name]))
    residual_to_sigma_rms = float(np.sqrt(residual_energy / max(sigma_energy, 1e-9)))
    validation = plane_validation_stats(raw_ch, sigma_ch, residual_ch, wavelet=args.wavelet)
    reject_reasons = contract_failure_reasons(
        residual_ch,
        sigma_ch,
        validation,
        residual_to_sigma_rms,
        args,
    )
    return {
        "runtime_accepted": not reject_reasons,
        "runtime_reject_reasons": reject_reasons,
        "runtime_residual_to_sigma_rms": residual_to_sigma_rms,
        "runtime_lag_max_abs": max(
            validation["removed_lag1_corr_x_max_abs"],
            validation["removed_lag1_corr_y_max_abs"],
        ),
        "runtime_edge_removed_energy_ratio": validation["edge_removed_energy_ratio"],
        "runtime_flat_removed_to_sigma_rms": validation["flat_removed_to_sigma_rms"],
        "runtime_mean_mask": float(np.mean([stats["mean_mask"] for stats in plane_rows.values()])),
        "runtime_p90_mask": float(np.mean([stats["p90_mask"] for stats in plane_rows.values()])),
        "runtime_plane_rows": plane_rows,
        "runtime_validation": validation,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    z = np.load(args.pairs, allow_pickle=False)
    rows = []
    for idx in range(len(z["codec_planes"])):
        runtime = evaluate_pair(z["codec_planes"][idx], z["sigma_planes"][idx], args)
        sidecar_accepted = bool(z["accepted"][idx])
        rows.append({
            "image_id": str(z["image_id"][idx]),
            "crop": str(z["crop"][idx]),
            "iso": int(z["iso"][idx]),
            "sidecar_accepted": sidecar_accepted,
            "match": sidecar_accepted == runtime["runtime_accepted"],
            **runtime,
        })

    tp = sum(row["sidecar_accepted"] and row["runtime_accepted"] for row in rows)
    tn = sum((not row["sidecar_accepted"]) and (not row["runtime_accepted"]) for row in rows)
    fp = sum((not row["sidecar_accepted"]) and row["runtime_accepted"] for row in rows)
    fn = sum(row["sidecar_accepted"] and (not row["runtime_accepted"]) for row in rows)
    summary = {
        "pairs": str(args.pairs),
        "params": {
            "wavelet": args.wavelet,
            "levels": args.levels,
            "structure_levels": args.structure_levels,
            "threshold_scale": args.threshold_scale,
            "max_threshold_sigma": args.max_threshold_sigma,
            "min_remove_sigma": args.min_remove_sigma,
            "max_remove_sigma": args.max_remove_sigma,
            "edge_weight": args.edge_weight,
            "cross_weight": args.cross_weight,
            "coherence_weight": args.coherence_weight,
            "structure_cutoff": args.structure_cutoff,
            "structure_power": args.structure_power,
            "mask_blur": args.mask_blur,
            "max_mask_weight": args.max_mask_weight,
            "output_sigma_clip": args.output_sigma_clip,
            "contract_max_residual_sigma": args.contract_max_residual_sigma,
            "contract_max_rms_residual_sigma": args.contract_max_rms_residual_sigma,
            "contract_max_lag_abs": args.contract_max_lag_abs,
            "contract_max_edge_ratio": args.contract_max_edge_ratio,
        },
        "counts": {
            "rows": len(rows),
            "matches": sum(row["match"] for row in rows),
            "mismatches": sum(not row["match"] for row in rows),
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
        },
        "rows": rows,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "codec_raw_clean_runtime_gate.json"
    html_path = args.out_dir / "codec_raw_clean_runtime_gate.html"
    json_path.write_text(json.dumps(summary, indent=2))
    build_html(summary, html_path)
    return summary


def build_html(summary: dict[str, Any], out: Path) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.4f}"
        if isinstance(v, list):
            return ", ".join(escape(str(x)) for x in v)
        return escape(str(v))

    c = summary["counts"]
    html = [
        "<!doctype html><meta charset='utf-8'><title>Codec Raw Clean Runtime Gate</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#18222d}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #d8dee6;padding:7px;font-size:13px;vertical-align:top}"
        "th{background:#eef2f5}.bad{background:#ffe7e7}.good{background:#e9f7ed}</style>",
        "<h1>Codec Raw Clean Runtime Gate</h1>",
        "<p>Acceptance recomputed from decoded/upsampled codec raw plus sigma, then compared with sidecar acceptance.</p>",
        f"<p>matches={c['matches']}/{c['rows']} tn={c['tn']} tp={c['tp']} fp={c['fp']} fn={c['fn']}</p>",
        "<table><thead><tr><th>Image</th><th>Crop</th><th>ISO</th><th>Sidecar</th><th>Runtime</th><th>Match</th>"
        "<th>Reasons</th><th>res/sigma</th><th>lag</th><th>edge ratio</th><th>flat/sigma</th><th>mean mask</th></tr></thead><tbody>",
    ]
    for row in summary["rows"]:
        cls = "good" if row["match"] else "bad"
        html.append(f"<tr class='{cls}'>" + "".join(f"<td>{fmt(v)}</td>" for v in [
            row["image_id"],
            row["crop"],
            row["iso"],
            row["sidecar_accepted"],
            row["runtime_accepted"],
            row["match"],
            row["runtime_reject_reasons"],
            row["runtime_residual_to_sigma_rms"],
            row["runtime_lag_max_abs"],
            row["runtime_edge_removed_energy_ratio"],
            row["runtime_flat_removed_to_sigma_rms"],
            row["runtime_mean_mask"],
        ]) + "</tr>")
    html.append("</tbody></table>")
    out.write_text("\n".join(html))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=2)
    ap.add_argument("--structure-levels", type=int, default=2)
    ap.add_argument("--threshold-scale", type=float, default=0.85)
    ap.add_argument("--max-threshold-sigma", type=float, default=1.25)
    ap.add_argument("--min-remove-sigma", type=float, default=0.05)
    ap.add_argument("--max-remove-sigma", type=float, default=1.40)
    ap.add_argument("--edge-weight", type=float, default=0.45)
    ap.add_argument("--cross-weight", type=float, default=0.45)
    ap.add_argument("--coherence-weight", type=float, default=0.10)
    ap.add_argument("--structure-cutoff", type=float, default=0.95)
    ap.add_argument("--structure-power", type=float, default=0.5)
    ap.add_argument("--mask-blur", type=float, default=0.65)
    ap.add_argument("--max-mask-weight", type=float, default=1.0)
    ap.add_argument("--output-sigma-clip", type=float, default=1.0)
    ap.add_argument("--contract-max-residual-sigma", type=float, default=1.0)
    ap.add_argument("--contract-max-rms-residual-sigma", type=float, default=0.35)
    ap.add_argument("--contract-max-lag-abs", type=float, default=0.20)
    ap.add_argument("--contract-max-edge-ratio", type=float, default=1.0)
    args = ap.parse_args()
    summary = build(args)
    print(args.out_dir / "codec_raw_clean_runtime_gate.json")
    print(args.out_dir / "codec_raw_clean_runtime_gate.html")
    print(json.dumps(summary["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
