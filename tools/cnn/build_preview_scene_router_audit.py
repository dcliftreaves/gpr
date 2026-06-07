#!/usr/bin/env python3
"""Build a runtime-feature audit for PREVIEW scene/expert routing.

This is the first step before training multiple scene/degradation experts. It
clusters current runtime PREVIEW rows using only source-image features, then
reports how the clusters align with pass/fail and failure metrics. The REF/gate
metrics are labels for analysis only; they are never used as router inputs.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


DEFAULT_RECEIPT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606/"
    "runtime_refiner_priority_zero_cont_colorlight_timing/preview_runtime_policy.json"
)
DEFAULT_SOURCE_ROOTS = [
    Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/crops"),
    Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_learned_atlas_20260606"),
    Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_rgb_refiner_20260606"),
]
FEATURE_NAMES = [
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
]


@dataclass(frozen=True)
class RowImage:
    row: dict[str, Any]
    source_path: Path


def parse_crop_png(path: Path) -> tuple[str, str, str] | None:
    parts = path.stem.split("_")
    if len(parts) < 4:
        return None
    image_id = "_".join(parts[:2])
    if parts[2] == "center":
        return image_id, "center", "_".join(parts[3:])
    if parts[2] == "upper" and len(parts) > 4 and parts[3] == "left":
        return image_id, "upper_left", "_".join(parts[4:])
    return None


def discover_sources(source_roots: list[Path]) -> dict[tuple[str, str, str], Path]:
    out: dict[tuple[str, str, str], Path] = {}
    for root in source_roots:
        for path in root.glob("Z8Z_*_*.png"):
            parsed = parse_crop_png(path)
            if parsed is None:
                continue
            image_id, crop, variant = parsed
            out[(image_id, crop, f"{root.name}:{variant}")] = path
    return out


def resolve_rows(receipt: dict[str, Any], source_roots: list[Path]) -> list[RowImage]:
    source_map = discover_sources(source_roots)
    out: list[RowImage] = []
    for row in receipt.get("rows") or []:
        source_path = Path(str(row.get("source_png", "")))
        if not source_path.exists():
            key = (row["image_id"], row["crop"], row["source_label"])
            source_path = source_map.get(key, source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"source image missing for {row.get('image_id')} {row.get('crop')}: {source_path}")
        out.append(RowImage(row=row, source_path=source_path))
    if not out:
        raise RuntimeError("receipt has no rows")
    return out


def load_rgb01(path: Path, max_side: int = 512) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    w, h = image.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BICUBIC)
    return np.asarray(image, dtype=np.float32) / 255.0


def rgb_to_hsv_saturation(rgb: np.ndarray) -> np.ndarray:
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def feature_vector(path: Path) -> np.ndarray:
    rgb = load_rgb01(path)
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat = rgb_to_hsv_saturation(rgb)
    blur = np.asarray(
        Image.fromarray(np.clip(luma * 255.0, 0, 255).astype(np.uint8))
        .resize((max(1, luma.shape[1] // 8), max(1, luma.shape[0] // 8)), Image.Resampling.BICUBIC)
        .resize((luma.shape[1], luma.shape[0]), Image.Resampling.BICUBIC),
        dtype=np.float32,
    ) / 255.0
    hf = luma - blur
    gx = np.diff(luma, axis=1, append=luma[:, -1:])
    gy = np.diff(luma, axis=0, append=luma[-1:, :])
    grad = np.sqrt(gx * gx + gy * gy)
    p05 = float(np.percentile(luma, 5))
    p95 = float(np.percentile(luma, 95))
    return np.array(
        [
            float(luma.mean()),
            float(luma.std()),
            p05,
            p95,
            p95 - p05,
            float(np.sqrt(np.mean(hf * hf))),
            float(np.mean(grad > 0.035)),
            float(sat.mean()),
            float(np.percentile(sat, 95)),
            float(np.mean(sat > 0.45)),
            float(np.mean(luma < 0.12)),
            float(np.mean(luma > 0.88)),
            float(r.mean()),
            float(g.mean()),
            float(b.mean()),
            float(r.mean() - g.mean()),
            float(b.mean() - g.mean()),
        ],
        dtype=np.float64,
    )


def kmeans(x: np.ndarray, k: int, iters: int = 80) -> tuple[np.ndarray, np.ndarray]:
    if k <= 0 or k > len(x):
        raise ValueError(f"k must be between 1 and n rows, got {k}")
    order = np.argsort(x[:, 0] + 0.37 * x[:, 1] - 0.19 * x[:, 2])
    centers = x[order[np.linspace(0, len(order) - 1, k).astype(int)]].copy()
    labels = np.zeros(len(x), dtype=np.int64)
    for _ in range(iters):
        dist = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dist.argmin(axis=1)
        if np.array_equal(labels, new_labels):
            break
        labels = new_labels
        for idx in range(k):
            group = x[labels == idx]
            if len(group):
                centers[idx] = group.mean(axis=0)
    return labels, centers


def zscore(features: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = features.mean(axis=0)
    std = features.std(axis=0)
    std[std < 1e-6] = 1.0
    return (features - mean) / std, mean, std


def cluster_name(center: dict[str, float]) -> str:
    if center["dark_frac"] > 0.18:
        return "dark_noise_risk"
    if center["sat_frac"] > 0.18 or center["sat_p95"] > 0.72:
        return "saturated_color_risk"
    if center["edge_density"] > 0.22 or center["hf_rms"] > 0.065:
        return "fine_texture_edge"
    if center["contrast_p95_p05"] < 0.28 and center["sat_mean"] < 0.22:
        return "smooth_gradient"
    return "general_lf_color"


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return html.escape(str(value))


def sidecar_payload(
    *,
    source_receipt: Path,
    clusters: list[dict[str, Any]],
    mean: np.ndarray,
    std: np.ndarray,
    centers_z: np.ndarray,
    centers: np.ndarray,
) -> dict[str, Any]:
    return {
        "schema": "preview_scene_router_sidecar.v1",
        "source_receipt": str(source_receipt),
        "router": {
            "type": "zscore_nearest_center",
            "feature_names": FEATURE_NAMES,
            "feature_mean": {name: float(mean[idx]) for idx, name in enumerate(FEATURE_NAMES)},
            "feature_std": {name: float(std[idx]) for idx, name in enumerate(FEATURE_NAMES)},
            "centers_z": [
                {name: float(centers_z[row, idx]) for idx, name in enumerate(FEATURE_NAMES)}
                for row in range(centers_z.shape[0])
            ],
            "centers": [
                {name: float(centers[row, idx]) for idx, name in enumerate(FEATURE_NAMES)}
                for row in range(centers.shape[0])
            ],
        },
        "cluster_roles": {
            str(cluster["cluster"]): cluster["suggested_expert"]
            for cluster in clusters
        },
        "router_inputs": {
            "allowed": ["source RGB crop/frame", "runtime metadata"],
            "forbidden": ["REF content", "REF-derived fields", "gate metrics", "image id", "crop id", "winner JSON"],
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    receipt = json.loads(args.receipt.read_text())
    rows = resolve_rows(receipt, args.source_root)
    features = np.stack([feature_vector(row.source_path) for row in rows])
    x, mean, std = zscore(features)
    labels, centers_z = kmeans(x, args.clusters)
    centers = centers_z * std + mean
    out_rows: list[dict[str, Any]] = []
    for idx, row_image in enumerate(rows):
        fv = {name: float(features[idx, j]) for j, name in enumerate(FEATURE_NAMES)}
        out_rows.append(
            {
                **row_image.row,
                "source_png_resolved": str(row_image.source_path),
                "cluster": int(labels[idx]),
                "features": fv,
            }
        )
    clusters = []
    for cluster_idx in range(args.clusters):
        group = [r for r in out_rows if r["cluster"] == cluster_idx]
        center = {name: float(centers[cluster_idx, j]) for j, name in enumerate(FEATURE_NAMES)}
        failures = [r for r in group if not r.get("preview_pass")]
        clusters.append(
            {
                "cluster": cluster_idx,
                "suggested_expert": cluster_name(center),
                "count": len(group),
                "fail_count": len(failures),
                "pass_count": len(group) - len(failures),
                "failure_rate": len(failures) / max(1, len(group)),
                "worst_lpips": max((float(r.get("lpips", 0.0)) for r in group), default=0.0),
                "worst_ms_ssim": min((float(r.get("ms_ssim", 1.0)) for r in group), default=1.0),
                "worst_y_psnr": min((float(r.get("y_psnr", 99.0)) for r in group), default=99.0),
                "worst_dE2000_mean": max((float(r.get("dE2000_mean", 0.0)) for r in group), default=0.0),
                "center": center,
                "members": [f"{r['image_id']}:{r['crop']}" for r in group],
                "failures": [f"{r['image_id']}:{r['crop']}" for r in failures],
            }
        )
    sidecar = sidecar_payload(
        source_receipt=args.receipt,
        clusters=clusters,
        mean=mean,
        std=std,
        centers_z=centers_z,
        centers=centers,
    )
    return {
        "schema": "preview_scene_router_audit.v1",
        "receipt": str(args.receipt),
        "router_inputs": {
            "allowed": ["source RGB crop/frame", "runtime metadata"],
            "forbidden": ["REF content", "REF-derived fields", "gate metrics", "image id", "crop id", "winner JSON"],
        },
        "router_sidecar": sidecar,
        "clusters": clusters,
        "rows": out_rows,
    }


def write_html(payload: dict[str, Any], html_path: Path) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:18px; background:#f6f6f2; color:#222; }
table { border-collapse:collapse; background:white; font-size:12px; margin:14px 0; }
td,th { border:1px solid #ccc; padding:5px 7px; text-align:right; vertical-align:top; }
td.left,th.left { text-align:left; }
.pass { color:#096b2b; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.small { color:#555; font-size:12px; max-width:1050px; line-height:1.45; }
"""
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Scene Router Audit</title>",
        f"<style>{css}</style><h1>PREVIEW Scene Router Audit</h1>",
        "<p class=small>Clusters use only source-image features. Gate metrics label the result after the fact and are not router inputs.</p>",
        "<h2>Clusters</h2><table><tr><th>cluster</th><th class=left>expert</th><th>count</th><th>fail</th>"
        "<th>worst LPIPS</th><th>worst MS</th><th>worst Y</th><th>worst dE</th><th class=left>members</th></tr>",
    ]
    for c in payload["clusters"]:
        parts.append(
            "<tr>"
            f"<td>{c['cluster']}</td><td class=left>{html.escape(c['suggested_expert'])}</td>"
            f"<td>{c['count']}</td><td>{c['fail_count']}</td>"
            f"<td>{c['worst_lpips']:.4f}</td><td>{c['worst_ms_ssim']:.4f}</td>"
            f"<td>{c['worst_y_psnr']:.2f}</td><td>{c['worst_dE2000_mean']:.2f}</td>"
            f"<td class=left>{html.escape(', '.join(c['members']))}</td></tr>"
        )
    parts.append("</table><h2>Rows</h2><table><tr><th class=left>image</th><th class=left>crop</th><th>cluster</th><th>pass</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th><th>hf</th><th>edge</th><th>sat</th><th>dark</th></tr>")
    for r in payload["rows"]:
        klass = "pass" if r.get("preview_pass") else "fail"
        f = r["features"]
        parts.append(
            "<tr>"
            f"<td class=left>{html.escape(r['image_id'])}</td><td class=left>{html.escape(r['crop'])}</td>"
            f"<td>{r['cluster']}</td><td class={klass}>{fmt(r.get('preview_pass'))}</td>"
            f"<td>{float(r['lpips']):.4f}</td><td>{float(r['ms_ssim']):.4f}</td>"
            f"<td>{float(r['y_psnr']):.2f}</td><td>{float(r['dE2000_mean']):.2f}</td>"
            f"<td>{f['hf_rms']:.4f}</td><td>{f['edge_density']:.3f}</td>"
            f"<td>{f['sat_mean']:.3f}</td><td>{f['dark_frac']:.3f}</td></tr>"
        )
    parts.append("</table>")
    html_path.write_text("\n".join(parts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    ap.add_argument("--source-root", type=Path, action="append", default=DEFAULT_SOURCE_ROOTS)
    ap.add_argument("--clusters", type=int, default=5)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-html", type=Path, required=True)
    ap.add_argument("--out-sidecar", type=Path)
    args = ap.parse_args()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_html.parent.mkdir(parents=True, exist_ok=True)
    payload = build(args)
    args.out_json.write_text(json.dumps(payload, indent=2))
    if args.out_sidecar:
        args.out_sidecar.parent.mkdir(parents=True, exist_ok=True)
        args.out_sidecar.write_text(json.dumps(payload["router_sidecar"], indent=2))
    write_html(payload, args.out_html)
    print(json.dumps({"clusters": payload["clusters"]}, indent=2))
    print(args.out_json)
    if args.out_sidecar:
        print(args.out_sidecar)
    print(args.out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
