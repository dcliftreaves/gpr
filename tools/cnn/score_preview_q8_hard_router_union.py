#!/usr/bin/env python3
"""Score a q8-hard/full-frame routed PREVIEW receipt union.

This diagnostic tests whether a runtime-observable router can select the q8
hard-family full-frame specialist and fall back to the existing full-frame v32
receipt for all other images. Routing uses q8 source full-frame RGB features
only: full image stats plus fixed manifest crop-window stats. REF and gate
metrics are scoring-only inputs.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from build_preview_holdout_runtime_receipt import scaled_box, sha256_file  # noqa: E402
from build_preview_scene_router_audit import feature_vector_rgb  # noqa: E402
from evaluate_preview_runtime_policy import summarize  # noqa: E402


Image.MAX_IMAGE_PIXELS = None


def load_source_receipt(path: Path) -> dict[str, Path]:
    payload = json.loads(path.read_text())
    root = path.parent
    out: dict[str, Path] = {}
    for image in payload.get("images") or []:
        source = root / str(image["stitched_png"])
        if not source.exists():
            raise FileNotFoundError(f"missing q8 source fullframe {source}")
        out[str(image["image_id"])] = source
    return out


def feature_schema(crop_names: list[str]) -> dict[str, Any]:
    return {
        "schema": "preview_q8_hard_router_features.v1",
        "source": "q8_source_fullframe_rgb",
        "regions": ["full_image", *[f"manifest_crop:{name}" for name in crop_names]],
        "per_region_features": [
            "luma_mean",
            "luma_std",
            "luma_p05",
            "luma_p95",
            "contrast_p95_p05",
            "hf_rms",
            "edge_density",
            "sat_mean",
            "sat_p95",
            "sat_frac",
            "dark_frac",
            "bright_frac",
            "r_mean",
            "g_mean",
            "b_mean",
            "rg_bias",
            "bg_bias",
        ],
        "forbidden_router_inputs": ["ref_rgb", "ref_dng", "gate_metrics", "sample_index", "crop_identity_key_planes"],
    }


def feature_for_image(source_rgb: np.ndarray, manifest_image: dict[str, Any], crops: dict[str, dict[str, int]], crop_names: list[str]) -> np.ndarray:
    feats = [feature_vector_rgb(source_rgb, max_side=512).astype(np.float64)]
    for crop_name in crop_names:
        crop = crops[crop_name]
        box = scaled_box(crop, manifest_image["sensor_dims"], (source_rgb.shape[1], source_rgb.shape[0]))
        crop_rgb = np.asarray(Image.fromarray(source_rgb).crop(box).resize((512, 512), Image.Resampling.LANCZOS), dtype=np.uint8)
        feats.append(feature_vector_rgb(crop_rgb, max_side=512).astype(np.float64))
    return np.concatenate(feats)


def build_features(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads(args.manifest.read_text())
    manifest_images = {str(image["id"]): image for image in manifest["images"]}
    crops = {str(key): value for key, value in manifest["crops"].items() if not str(key).startswith("$")}
    crop_names = sorted(crops)
    source_paths = load_source_receipt(args.source_fullframe_receipt)
    hard_payload = json.loads(args.q8_hard_receipt.read_text())
    hard_ids = sorted({str(row["image_id"]) for row in hard_payload.get("rows") or []})
    rows: list[dict[str, Any]] = []
    for image_id in sorted(source_paths):
        source_rgb = np.asarray(Image.open(source_paths[image_id]).convert("RGB"), dtype=np.uint8)
        feature = feature_for_image(source_rgb, manifest_images[image_id], crops, crop_names)
        rows.append(
            {
                "image_id": image_id,
                "feature": feature,
                "is_hard": image_id in hard_ids,
                "source_png": str(source_paths[image_id]),
            }
        )
    return rows, {"crop_names": crop_names, "hard_image_ids": hard_ids, "feature_schema": feature_schema(crop_names)}


def normalize(features: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = features.mean(axis=0)
    std = features.std(axis=0)
    std[std < 1e-6] = 1.0
    return (features - mean) / std, mean, std


def route_one(z: np.ndarray, hard_center: np.ndarray, fallback_center: np.ndarray) -> tuple[bool, float, float, float]:
    hard_distance = float(np.linalg.norm(z - hard_center))
    fallback_distance = float(np.linalg.norm(z - fallback_center))
    return hard_distance < fallback_distance, hard_distance, fallback_distance, fallback_distance - hard_distance


def loo_routes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = np.stack([row["feature"] for row in rows])
    labels = np.asarray([bool(row["is_hard"]) for row in rows], dtype=bool)
    z_all, _mean, _std = normalize(features)
    routed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        train = np.ones(len(rows), dtype=bool)
        train[index] = False
        hard_center = z_all[train & labels].mean(axis=0)
        fallback_center = z_all[train & ~labels].mean(axis=0)
        pred, hard_distance, fallback_distance, margin = route_one(z_all[index], hard_center, fallback_center)
        routed.append(
            {
                "image_id": row["image_id"],
                "actual_hard": bool(row["is_hard"]),
                "predicted_hard": bool(pred),
                "hard_distance": hard_distance,
                "fallback_distance": fallback_distance,
                "margin": margin,
            }
        )
    return routed


def final_sidecar(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    features = np.stack([row["feature"] for row in rows])
    labels = np.asarray([bool(row["is_hard"]) for row in rows], dtype=bool)
    z_all, mean, std = normalize(features)
    return {
        "schema": "preview_q8_hard_router_sidecar.v1",
        "feature_schema": meta["feature_schema"],
        "normalization_mean": mean.tolist(),
        "normalization_std": std.tolist(),
        "hard_center": z_all[labels].mean(axis=0).tolist(),
        "fallback_center": z_all[~labels].mean(axis=0).tolist(),
        "training_counts": {"hard": int(labels.sum()), "fallback": int((~labels).sum())},
        "training_image_ids": {
            "hard": [row["image_id"] for row in rows if row["is_hard"]],
            "fallback": [row["image_id"] for row in rows if not row["is_hard"]],
        },
    }


def final_routes(rows: list[dict[str, Any]], sidecar: dict[str, Any]) -> list[dict[str, Any]]:
    mean = np.asarray(sidecar["normalization_mean"], dtype=np.float64)
    std = np.asarray(sidecar["normalization_std"], dtype=np.float64)
    hard_center = np.asarray(sidecar["hard_center"], dtype=np.float64)
    fallback_center = np.asarray(sidecar["fallback_center"], dtype=np.float64)
    routed: list[dict[str, Any]] = []
    for row in rows:
        z = (row["feature"] - mean) / std
        pred, hard_distance, fallback_distance, margin = route_one(z, hard_center, fallback_center)
        routed.append(
            {
                "image_id": row["image_id"],
                "actual_hard": bool(row["is_hard"]),
                "predicted_hard": bool(pred),
                "hard_distance": hard_distance,
                "fallback_distance": fallback_distance,
                "margin": margin,
            }
        )
    return routed


def combine_rows(routes: list[dict[str, Any]], q8_rows: list[dict[str, Any]], fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_by_id = {row["image_id"]: row for row in routes}
    q8_by_key = {(row["image_id"], row["crop"]): row for row in q8_rows}
    fallback_by_key = {(row["image_id"], row["crop"]): row for row in fallback_rows}
    keys = sorted(set(q8_by_key) | set(fallback_by_key))
    out: list[dict[str, Any]] = []
    for key in keys:
        image_id, crop = key
        route = route_by_id[image_id]
        source = q8_by_key.get(key) if route["predicted_hard"] else fallback_by_key.get(key)
        if source is None:
            source = fallback_by_key.get(key) or q8_by_key.get(key)
        row = dict(source)
        row["crop"] = crop
        row["route_predicted_hard"] = bool(route["predicted_hard"])
        row["route_actual_hard"] = bool(route["actual_hard"])
        row["route_margin"] = float(route["margin"])
        row["variant"] = "q8_hardfit_fullframe" if row["route_predicted_hard"] else "v32_fullframe_fallback"
        out.append(row)
    return out


def route_summary(routes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(routes),
        "correct": sum(1 for row in routes if row["actual_hard"] == row["predicted_hard"]),
        "hard_recall": sum(1 for row in routes if row["actual_hard"] and row["predicted_hard"]),
        "hard_count": sum(1 for row in routes if row["actual_hard"]),
        "fallback_specificity": sum(1 for row in routes if (not row["actual_hard"]) and (not row["predicted_hard"])),
        "fallback_count": sum(1 for row in routes if not row["actual_hard"]),
        "worst_margin": min(float(row["margin"]) for row in routes),
    }


def write_html(payload: dict[str, Any], path: Path) -> None:
    summary = payload["summary"]["routed_preview_union"]
    route = payload["route_summary"]["leave_one_out"]
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
        "<!doctype html><meta charset='utf-8'><title>q8 Hard Router PREVIEW Union</title>",
        f"<style>{css}</style><h1>q8 Hard Router PREVIEW Union</h1>",
        "<p>Router inputs are q8 source full-frame/crop RGB features only. REF and metrics are scoring only.</p>",
        "<div class=cards>",
        f"<div class=card><b>Union pass</b><br>{summary['pass_count']}/{summary['count']}</div>",
        f"<div class=card><b>LOO route</b><br>{route['correct']}/{route['count']}</div>",
        f"<div class=card><b>Hard recall</b><br>{route['hard_recall']}/{route['hard_count']}</div>",
        f"<div class=card><b>Fallback specificity</b><br>{route['fallback_specificity']}/{route['fallback_count']}</div>",
        "</div><table><thead><tr><th class=left>image</th><th class=left>crop</th><th class=left>variant</th><th>pass</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th><th>margin</th></tr></thead><tbody>",
    ]
    for row in sorted(payload["rows"], key=lambda item: (item["preview_pass"], item["image_id"], item["crop"])):
        cls = "pass" if row["preview_pass"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['image_id'])}</td><td class=left>{html.escape(row['crop'])}</td>"
            f"<td class=left>{html.escape(row['variant'])}</td><td class={cls}>{'PASS' if row['preview_pass'] else 'FAIL'}</td>"
            f"<td>{row['lpips']:.4f}</td><td>{row['ms_ssim']:.4f}</td><td>{row['y_psnr']:.2f}</td>"
            f"<td>{row['dE2000_mean']:.2f}</td><td>{row['route_margin']:.3f}</td></tr>"
        )
    parts.append("</tbody></table>")
    path.write_text("".join(parts))


def collect(args: argparse.Namespace) -> dict[str, Any]:
    feature_rows, meta = build_features(args)
    q8_payload = json.loads(args.q8_hard_receipt.read_text())
    fallback_payload = json.loads(args.fallback_receipt.read_text())
    loo = loo_routes(feature_rows)
    sidecar = final_sidecar(feature_rows, meta)
    final = final_routes(feature_rows, sidecar)
    selected_routes = loo if args.route_mode == "leave_one_out" else final
    rows = combine_rows(selected_routes, q8_payload.get("rows") or [], fallback_payload.get("rows") or [])
    return {
        "schema": "preview_q8_hard_router_union.v1",
        "route_mode": args.route_mode,
        "source_fullframe_receipt": str(args.source_fullframe_receipt),
        "q8_hard_receipt": str(args.q8_hard_receipt),
        "fallback_receipt": str(args.fallback_receipt),
        "source_receipt_sha256": sha256_file(args.source_fullframe_receipt),
        "q8_hard_receipt_sha256": sha256_file(args.q8_hard_receipt),
        "fallback_receipt_sha256": sha256_file(args.fallback_receipt),
        "render_contract": {
            "router_inputs": ["q8_source_fullframe_rgb", "fixed_manifest_crop_rgb_windows"],
            "route_outputs": ["q8_hardfit_fullframe", "v32_fullframe_fallback"],
            "forbidden_router_inputs": meta["feature_schema"]["forbidden_router_inputs"],
            "uses_ref_at_route_time": False,
            "uses_ref_at_render_time": False,
        },
        "feature_schema": meta["feature_schema"],
        "sidecar": sidecar,
        "routes": {"leave_one_out": loo, "final_sidecar": final},
        "route_summary": {"leave_one_out": route_summary(loo), "final_sidecar": route_summary(final)},
        "summary": {"routed_preview_union": summarize(rows)},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument(
        "--source-fullframe-receipt",
        type=Path,
        default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_source_fullframes_holdout28_v1/preview_codec_source_fullframes.json"),
    )
    ap.add_argument(
        "--q8-hard-receipt",
        type=Path,
        default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260613/q8_crop_fullframe_hardfit_hard8_t512_v1/preview_q8_crop_fullframe.json"),
    )
    ap.add_argument(
        "--fallback-receipt",
        type=Path,
        default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/fullframe_tiled_v32_holdout28_baseline_t512/preview_scene_routed_fullframe.json"),
    )
    ap.add_argument("--route-mode", choices=["leave_one_out", "final_sidecar"], default="leave_one_out")
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    args = ap.parse_args()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    summary = payload["summary"]["routed_preview_union"]
    route = payload["route_summary"][args.route_mode]
    print(
        f"union {summary['pass_count']}/{summary['count']} "
        f"route={route['correct']}/{route['count']} "
        f"hard={route['hard_recall']}/{route['hard_count']} "
        f"fallback={route['fallback_specificity']}/{route['fallback_count']}"
    )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
