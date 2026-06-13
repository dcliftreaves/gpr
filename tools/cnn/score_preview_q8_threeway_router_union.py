#!/usr/bin/env python3
"""Score a three-way q8/full-frame PREVIEW router union.

Routes each image from q8 source RGB features to one of:
q8 hard-family full-frame specialist, q8 fallback3 full-frame specialist, or
the existing v32 full-frame fallback. REF and metrics are scoring only.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import sha256_file  # noqa: E402
from evaluate_preview_runtime_policy import summarize  # noqa: E402
from score_preview_q8_hard_router_union import build_features, feature_schema, normalize  # noqa: E402


LABEL_FALLBACK = "fallback"
LABEL_FALLBACK3 = "fallback3"
LABEL_HARD = "hard"
LABELS = [LABEL_FALLBACK, LABEL_FALLBACK3, LABEL_HARD]


def receipt_image_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text())
    return {str(row["image_id"]) for row in payload.get("rows") or []}


def labeled_features(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, meta = build_features(args)
    hard_ids = receipt_image_ids(args.q8_hard_receipt)
    fallback3_ids = receipt_image_ids(args.q8_fallback3_receipt)
    overlap = hard_ids & fallback3_ids
    if overlap:
        raise RuntimeError(f"overlapping specialist labels: {sorted(overlap)}")
    for row in rows:
        image_id = str(row["image_id"])
        row["label"] = LABEL_HARD if image_id in hard_ids else LABEL_FALLBACK3 if image_id in fallback3_ids else LABEL_FALLBACK
    meta["hard_image_ids"] = sorted(hard_ids)
    meta["fallback3_image_ids"] = sorted(fallback3_ids)
    meta["feature_schema"] = feature_schema(meta["crop_names"])
    return rows, meta


def guarded_label(distances: dict[str, float], fallback3_max_distance: float) -> str:
    label = min(distances, key=distances.get)
    if label == LABEL_FALLBACK3 and distances[LABEL_FALLBACK3] > fallback3_max_distance:
        return LABEL_FALLBACK
    return label


def build_centers(z_all: np.ndarray, rows: list[dict[str, Any]], train_idx: list[int]) -> dict[str, np.ndarray]:
    centers: dict[str, np.ndarray] = {}
    for label in LABELS:
        idx = [index for index in train_idx if rows[index]["label"] == label]
        if not idx:
            raise RuntimeError(f"no training rows for {label}")
        centers[label] = z_all[idx].mean(axis=0)
    return centers


def route_with_centers(z: np.ndarray, centers: dict[str, np.ndarray], fallback3_max_distance: float) -> tuple[str, dict[str, float], float]:
    distances = {label: float(np.linalg.norm(z - center)) for label, center in centers.items()}
    label = guarded_label(distances, fallback3_max_distance)
    ordered = sorted(distances.items(), key=lambda item: item[1])
    margin = float(ordered[1][1] - ordered[0][1])
    return label, distances, margin


def loo_routes(rows: list[dict[str, Any]], fallback3_max_distance: float) -> list[dict[str, Any]]:
    features = np.stack([row["feature"] for row in rows])
    z_all, _mean, _std = normalize(features)
    routed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        train_idx = [i for i in range(len(rows)) if i != index]
        centers = build_centers(z_all, rows, train_idx)
        label, distances, margin = route_with_centers(z_all[index], centers, fallback3_max_distance)
        routed.append(
            {
                "image_id": row["image_id"],
                "actual_label": row["label"],
                "predicted_label": label,
                "distances": distances,
                "nearest_margin": margin,
            }
        )
    return routed


def frozen_sidecar(rows: list[dict[str, Any]], meta: dict[str, Any], fallback3_max_distance: float) -> dict[str, Any]:
    features = np.stack([row["feature"] for row in rows])
    z_all, mean, std = normalize(features)
    centers = build_centers(z_all, rows, list(range(len(rows))))
    return {
        "schema": "preview_q8_threeway_router_sidecar.v1",
        "feature_schema": meta["feature_schema"],
        "normalization_mean": mean.tolist(),
        "normalization_std": std.tolist(),
        "centers": {label: center.tolist() for label, center in centers.items()},
        "fallback3_max_distance": fallback3_max_distance,
        "training_counts": {label: sum(1 for row in rows if row["label"] == label) for label in LABELS},
        "training_image_ids": {label: [row["image_id"] for row in rows if row["label"] == label] for label in LABELS},
    }


def final_routes(rows: list[dict[str, Any]], sidecar: dict[str, Any]) -> list[dict[str, Any]]:
    mean = np.asarray(sidecar["normalization_mean"], dtype=np.float64)
    std = np.asarray(sidecar["normalization_std"], dtype=np.float64)
    centers = {label: np.asarray(center, dtype=np.float64) for label, center in sidecar["centers"].items()}
    routed = []
    for row in rows:
        z = (row["feature"] - mean) / std
        label, distances, margin = route_with_centers(z, centers, float(sidecar["fallback3_max_distance"]))
        routed.append(
            {
                "image_id": row["image_id"],
                "actual_label": row["label"],
                "predicted_label": label,
                "distances": distances,
                "nearest_margin": margin,
            }
        )
    return routed


def route_summary(routes: list[dict[str, Any]]) -> dict[str, Any]:
    out = {
        "count": len(routes),
        "correct": sum(1 for row in routes if row["actual_label"] == row["predicted_label"]),
    }
    for label in LABELS:
        out[f"{label}_correct"] = sum(1 for row in routes if row["actual_label"] == label and row["predicted_label"] == label)
        out[f"{label}_count"] = sum(1 for row in routes if row["actual_label"] == label)
    return out


def combine_rows(routes: list[dict[str, Any]], hard_rows: list[dict[str, Any]], fallback3_rows: list[dict[str, Any]], fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_by_id = {row["image_id"]: row for row in routes}
    sources = {
        LABEL_HARD: {(row["image_id"], row["crop"]): row for row in hard_rows},
        LABEL_FALLBACK3: {(row["image_id"], row["crop"]): row for row in fallback3_rows},
        LABEL_FALLBACK: {(row["image_id"], row["crop"]): row for row in fallback_rows},
    }
    keys = sorted(set().union(*[set(value) for value in sources.values()]))
    out = []
    for key in keys:
        image_id, crop = key
        route = route_by_id[image_id]
        label = route["predicted_label"]
        source = sources[label].get(key) or sources[LABEL_FALLBACK].get(key) or sources[LABEL_HARD].get(key) or sources[LABEL_FALLBACK3].get(key)
        row = dict(source)
        row["crop"] = crop
        row["route_actual_label"] = route["actual_label"]
        row["route_predicted_label"] = label
        row["route_margin"] = float(route["nearest_margin"])
        row["variant"] = f"{label}_fullframe"
        out.append(row)
    return out


def write_html(payload: dict[str, Any], path: Path) -> None:
    summary = payload["summary"]["routed_preview_union"]
    route = payload["route_summary"][payload["route_mode"]]
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f7f8f9; color:#222; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:10px; margin:14px 0; }
.card { background:#fff; border:1px solid #d4d8de; border-radius:6px; padding:10px; }
table { border-collapse:collapse; background:#fff; width:100%; font-size:12px; margin:14px 0; }
td,th { border:1px solid #ccd2d9; padding:5px 7px; text-align:right; }
th.left,td.left { text-align:left; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
"""
    parts = [
        "<!doctype html><meta charset='utf-8'><title>q8 Three-way Router PREVIEW Union</title>",
        f"<style>{css}</style><h1>q8 Three-way Router PREVIEW Union</h1>",
        "<p>Router inputs are q8 source full-frame/crop RGB features only. REF and metrics are scoring only.</p>",
        "<div class=cards>",
        f"<div class=card><b>Union pass</b><br>{summary['pass_count']}/{summary['count']}</div>",
        f"<div class=card><b>Route</b><br>{route['correct']}/{route['count']}</div>",
        f"<div class=card><b>Hard</b><br>{route['hard_correct']}/{route['hard_count']}</div>",
        f"<div class=card><b>Fallback3</b><br>{route['fallback3_correct']}/{route['fallback3_count']}</div>",
        "</div><table><thead><tr><th class=left>image</th><th class=left>crop</th><th class=left>variant</th><th>pass</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th></tr></thead><tbody>",
    ]
    for row in sorted(payload["rows"], key=lambda item: (item["preview_pass"], item["image_id"], item["crop"])):
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['image_id'])}</td><td class=left>{html.escape(row['crop'])}</td>"
            f"<td class=left>{html.escape(row['variant'])}</td><td class={cls}>{'PASS' if row['preview_pass'] else 'FAIL'}</td>"
            f"<td>{row['lpips']:.4f}</td><td>{row['ms_ssim']:.4f}</td><td>{row['y_psnr']:.2f}</td><td>{row['dE2000_mean']:.2f}</td></tr>"
        )
    parts.append("</tbody></table>")
    path.write_text("".join(parts))


def collect(args: argparse.Namespace) -> dict[str, Any]:
    feature_rows, meta = labeled_features(args)
    hard_payload = json.loads(args.q8_hard_receipt.read_text())
    fallback3_payload = json.loads(args.q8_fallback3_receipt.read_text())
    fallback_payload = json.loads(args.fallback_receipt.read_text())
    loo = loo_routes(feature_rows, args.fallback3_max_distance)
    sidecar = frozen_sidecar(feature_rows, meta, args.fallback3_max_distance)
    final = final_routes(feature_rows, sidecar)
    routes = loo if args.route_mode == "leave_one_out" else final
    rows = combine_rows(routes, hard_payload.get("rows") or [], fallback3_payload.get("rows") or [], fallback_payload.get("rows") or [])
    return {
        "schema": "preview_q8_threeway_router_union.v1",
        "route_mode": args.route_mode,
        "source_fullframe_receipt": str(args.source_fullframe_receipt),
        "q8_hard_receipt": str(args.q8_hard_receipt),
        "q8_fallback3_receipt": str(args.q8_fallback3_receipt),
        "fallback_receipt": str(args.fallback_receipt),
        "source_receipt_sha256": sha256_file(args.source_fullframe_receipt),
        "q8_hard_receipt_sha256": sha256_file(args.q8_hard_receipt),
        "q8_fallback3_receipt_sha256": sha256_file(args.q8_fallback3_receipt),
        "fallback_receipt_sha256": sha256_file(args.fallback_receipt),
        "render_contract": {
            "router_inputs": ["q8_source_fullframe_rgb", "fixed_manifest_crop_rgb_windows"],
            "route_outputs": ["q8_hard_fullframe", "q8_fallback3_fullframe", "v32_fullframe_fallback"],
            "forbidden_router_inputs": ["ref_rgb", "ref_dng", "gate_metrics", "sample_index", "crop_identity_key_planes"],
            "uses_ref_at_route_time": False,
            "uses_ref_at_render_time": False,
        },
        "sidecar": sidecar,
        "routes": {"leave_one_out": loo, "final_sidecar": final},
        "route_summary": {"leave_one_out": route_summary(loo), "final_sidecar": route_summary(final)},
        "summary": {"routed_preview_union": summarize(rows)},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--source-fullframe-receipt", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_fullframes_holdout28_v1/preview_codec_source_fullframes.json"))
    ap.add_argument("--q8-hard-receipt", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_crop_fullframe_hardfit_hard8_t512_v1/preview_q8_crop_fullframe.json"))
    ap.add_argument("--q8-fallback3-receipt", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_crop_fullframe_fallback3_allfit_t512_v1/preview_q8_crop_fullframe.json"))
    ap.add_argument("--fallback-receipt", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_holdout28_baseline_t512/preview_scene_routed_fullframe.json"))
    ap.add_argument("--fallback3-max-distance", type=float, default=3.0)
    ap.add_argument("--route-mode", choices=["leave_one_out", "final_sidecar"], default="leave_one_out")
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    args = ap.parse_args()
    payload = collect(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    summary = payload["summary"]["routed_preview_union"]
    route = payload["route_summary"][args.route_mode]
    print(f"union {summary['pass_count']}/{summary['count']} route={route['correct']}/{route['count']}")
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
