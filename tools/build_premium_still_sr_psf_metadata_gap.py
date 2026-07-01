#!/usr/bin/env python3
"""Audit whether premium still-SR has enough PSF metadata for another PSF run."""
from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_psf_metadata_gap.v1"
DEFAULT_TARGETS = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/"
    "premium_still_sr_raw_cfa_residual_targets_dedup_20260701/"
    "raw_cfa_residual_targets_dedup.npz"
)
DEFAULT_PSF_RECEIPT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/"
    "bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/"
    "bayer_resize_psf_receipt.json"
)
DEFAULT_BASELINE_RECEIPT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/"
    "premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/"
    "train_receipt.json"
)
DEFAULT_PSF_PROBE_RECEIPTS = [
    Path(
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_psf_noisefloor_unet_w32_1200_20260701/"
        "train_receipt.json"
    ),
    Path(
        "/Volumes/OWC_8TB/gpr_work/artifacts/"
        "premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fullcrop_rawcontext_psf_unet_w32_900_20260701/"
        "train_receipt.json"
    ),
]
PSF_ROW_KEYS = (
    "psf_kernel_weights",
    "bayer_resize_psf_kernel_weights",
    "same_color_psf_weights",
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--psf-receipt", type=Path, default=DEFAULT_PSF_RECEIPT)
    ap.add_argument("--baseline-receipt", type=Path, default=DEFAULT_BASELINE_RECEIPT)
    ap.add_argument(
        "--psf-probe-receipt",
        type=Path,
        action="append",
        default=None,
        help="PSF-conditioned train receipt; may be repeated.",
    )
    ap.add_argument("--near-box-epsilon", type=float, default=1.0e-3)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def load_target_meta(path: Path) -> list[dict[str, Any]]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised by environments without numpy.
        raise SystemExit("numpy is required to load the raw-CFA target NPZ") from exc
    with np.load(path, allow_pickle=True) as npz:
        if "meta" not in npz.files:
            raise ValueError(f"{path} does not contain a meta array")
        raw_meta = npz["meta"].tolist()
    if isinstance(raw_meta, bytes):
        raw_meta = raw_meta.decode("utf-8")
    if isinstance(raw_meta, str):
        raw_meta = json.loads(raw_meta)
    if not isinstance(raw_meta, list):
        raise ValueError(f"{path} meta is not a JSON list")
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_meta):
        if not isinstance(row, dict):
            raise ValueError(f"{path} meta row {idx} is not a JSON object")
        rows.append(row)
    return rows


def normalized_kernel(value: Any) -> tuple[float, ...] | None:
    if isinstance(value, dict):
        for key in ("normalized_weights", "weights", "kernel", "same_color_weights"):
            if key in value:
                return normalized_kernel(value[key])
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return tuple(round(float(v), 9) for v in value)
    except (TypeError, ValueError):
        return None


def row_psf_kernel(row: dict[str, Any]) -> tuple[float, ...] | None:
    for key in PSF_ROW_KEYS:
        kernel = normalized_kernel(row.get(key))
        if kernel is not None:
            return kernel
    return None


def infer_camera(row: dict[str, Any]) -> str:
    fields = (
        "camera",
        "camera_model",
        "make",
        "model",
        "source_dng",
        "source_raw",
        "candidate_dng",
        "candidate_raw",
        "scene_id",
        "scene",
    )
    text = " ".join(str(row.get(field) or "") for field in fields).lower()
    if "x2d" in text or "hasselblad" in text or "hassel" in text:
        return "x2d"
    if "z8" in text or "z8z_" in text or "nikon" in text:
        return "z8"
    if "mission" in text or "gopro" in text or "gp01" in text:
        return "mission1"
    if "iphone" in text or "/img_" in text or text.endswith("img_"):
        return "iphone"
    return "unknown"


def scene_key(row: dict[str, Any]) -> str:
    for key in ("scene_id", "scene", "source_scene", "source_stem"):
        value = row.get(key)
        if value:
            return str(value)
    for key in ("source_dng", "source_raw", "candidate_dng", "candidate_raw"):
        value = row.get(key)
        if value:
            return Path(str(value)).stem
    return "unknown"


def receipt_metric(receipt: dict[str, Any], metric: str) -> float | None:
    cur: Any = receipt.get("eval")
    if isinstance(cur, dict):
        holdout = cur.get("holdout")
        if isinstance(holdout, dict):
            item = holdout.get(metric)
            if isinstance(item, dict) and isinstance(item.get("median"), (int, float)):
                return float(item["median"])
    if metric in ("exact_raw_mae_reduction_pct", "raw_residual_mae_reduction_pct"):
        probe = receipt.get("best_holdout_probe")
        if isinstance(probe, dict) and isinstance(probe.get("raw_mae_reduction_pct_median"), (int, float)):
            return float(probe["raw_mae_reduction_pct_median"])
    return None


def receipt_summary(label: str, path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    probe = receipt.get("best_holdout_probe") if isinstance(receipt.get("best_holdout_probe"), dict) else {}
    return {
        "label": label,
        "path": path.as_posix(),
        "schema": receipt.get("schema"),
        "holdout_row_count": int(probe.get("row_count", 0)) if isinstance(probe.get("row_count"), (int, float)) else None,
        "best_holdout_probe_step": probe.get("step"),
        "median_exact_raw_mae_recovery_pct": receipt_metric(receipt, "exact_raw_mae_reduction_pct"),
        "median_raw_residual_rmse_recovery_pct": receipt_metric(receipt, "raw_residual_rmse_reduction_pct"),
    }


def psf_weights(receipt: dict[str, Any]) -> list[float]:
    model = receipt.get("psf_model")
    if not isinstance(model, dict):
        return []
    weights = model.get("normalized_weights")
    if not isinstance(weights, list):
        return []
    out: list[float] = []
    for value in weights:
        if not isinstance(value, (int, float)):
            return []
        out.append(float(value))
    return out if len(out) == 4 else []


def artifact(label: str, path: Path, schema: str | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "path": path.as_posix(),
        "exists": path.exists(),
        "schema": schema,
    }


def build_gap(
    target_rows: list[dict[str, Any]],
    psf_receipt: dict[str, Any],
    baseline_receipt: dict[str, Any],
    psf_probe_receipts: list[tuple[Path, dict[str, Any]]],
    sources: dict[str, Any],
    near_box_epsilon: float,
) -> dict[str, Any]:
    row_count = len(target_rows)
    scene_count = len({scene_key(row) for row in target_rows})
    camera_counts = Counter(infer_camera(row) for row in target_rows)
    explicit_camera_rows = sum(1 for row in target_rows if row.get("camera") or row.get("camera_model") or row.get("model"))
    row_kernels = [kernel for row in target_rows if (kernel := row_psf_kernel(row)) is not None]
    unique_row_kernels = sorted(set(row_kernels))
    weights = psf_weights(psf_receipt)
    deltas = [abs(value - 0.25) for value in weights]
    max_abs_delta = max(deltas) if deltas else None
    weight_spread = (max(weights) - min(weights)) if weights else None
    near_box = bool(weights) and max_abs_delta is not None and max_abs_delta <= near_box_epsilon

    baseline = receipt_summary("non-PSF baseline", sources["baseline_receipt"], baseline_receipt)
    probes = [
        receipt_summary(f"PSF probe {idx + 1}", path, receipt)
        for idx, (path, receipt) in enumerate(psf_probe_receipts)
    ]
    baseline_mae = baseline["median_exact_raw_mae_recovery_pct"]
    best_probe_mae = max(
        (probe["median_exact_raw_mae_recovery_pct"] for probe in probes if probe["median_exact_raw_mae_recovery_pct"] is not None),
        default=None,
    )
    psf_probe_beats_baseline = (
        baseline_mae is not None and best_probe_mae is not None and best_probe_mae > baseline_mae
    )
    metadata_ready = row_count > 0 and len(row_kernels) == row_count and len(unique_row_kernels) >= 2
    another_psf_run_justified = metadata_ready or psf_probe_beats_baseline

    blockers: list[dict[str, Any]] = []
    if len(row_kernels) < row_count:
        blockers.append(
            {
                "id": "missing_per_row_psf_metadata",
                "status": "required",
                "detail": f"Only {len(row_kernels)} of {row_count} target rows carry row-level PSF weights.",
            }
        )
    if len(unique_row_kernels) < 2:
        blockers.append(
            {
                "id": "no_per_row_psf_variation",
                "status": "required",
                "detail": f"Found {len(unique_row_kernels)} unique row-level PSF kernels; conditioning needs real variation.",
            }
        )
    if near_box:
        blockers.append(
            {
                "id": "global_psf_near_box",
                "status": "diagnostic",
                "detail": f"Global PSF weights are within {near_box_epsilon:g} of a neutral same-color box.",
            }
        )
    if baseline_mae is not None and best_probe_mae is not None and not psf_probe_beats_baseline:
        blockers.append(
            {
                "id": "psf_probe_did_not_beat_baseline",
                "status": "diagnostic",
                "detail": (
                    f"Best PSF probe median exact raw MAE recovery is {best_probe_mae:.6g}%, "
                    f"below baseline {baseline_mae:.6g}%."
                ),
            }
        )
    if explicit_camera_rows < row_count:
        blockers.append(
            {
                "id": "camera_metadata_missing_or_inferred",
                "status": "required_for_broad_conditioning",
                "detail": f"Only {explicit_camera_rows} of {row_count} rows carry explicit camera metadata; audit infers camera from paths.",
            }
        )

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {
            "targets": sources["targets"].as_posix(),
            "psf_receipt": sources["psf_receipt"].as_posix(),
            "baseline_receipt": sources["baseline_receipt"].as_posix(),
            "psf_probe_receipts": [path.as_posix() for path, _ in psf_probe_receipts],
        },
        "summary": {
            "target_row_count": row_count,
            "scene_count": scene_count,
            "rows_with_psf_metadata": len(row_kernels),
            "unique_row_psf_kernel_count": len(unique_row_kernels),
            "rows_with_explicit_camera_metadata": explicit_camera_rows,
            "inferred_camera_counts": dict(sorted(camera_counts.items())),
            "global_psf_weights": weights,
            "global_psf_weight_spread": weight_spread,
            "global_psf_max_abs_delta_from_box": max_abs_delta,
            "global_psf_near_box": near_box,
            "baseline_median_exact_raw_mae_recovery_pct": baseline_mae,
            "best_psf_probe_median_exact_raw_mae_recovery_pct": best_probe_mae,
            "psf_probe_beats_baseline": psf_probe_beats_baseline,
            "psf_metadata_ready_for_model_conditioning": metadata_ready,
            "another_psf_cnn_run_justified": another_psf_run_justified,
        },
        "policy": {
            "require_no_ref_runtime_inputs": True,
            "require_row_level_psf_metadata": True,
            "minimum_unique_row_psf_kernels": 2,
            "near_box_epsilon": near_box_epsilon,
            "do_not_repeat_global_near_box_psf_probe_as_primary_path": True,
        },
        "baseline": baseline,
        "psf_probes": probes,
        "blockers": blockers,
        "next_actions": [
            {
                "priority": 1,
                "action": "Build or attach a per-row PSF sidecar keyed by target row, camera, resize path, crop, and scene.",
                "done_when": "Every deduplicated raw target row has row-level PSF weights and at least two distinct kernels exist.",
            },
            {
                "priority": 2,
                "action": "Derive camera/resolution-specific PSF receipts for X2D, Z8, Mission 1, and iPhone rows that enter still-SR training.",
                "done_when": "Camera metadata is explicit in target rows and PSF variation is not inferred from a single global receipt.",
            },
            {
                "priority": 3,
                "action": "Rebuild the deduplicated raw-CFA target NPZ with the row PSF metadata before another PSF-conditioned CNN run.",
                "done_when": "The target audit flips psf_metadata_ready_for_model_conditioning to true.",
            },
            {
                "priority": 4,
                "action": "If row-level PSF variation is unavailable, prioritize a stronger camera/noise-aware teacher objective instead of repeating near-box PSF planes.",
                "done_when": "A new candidate beats the current 0.153% X2D scene-holdout baseline or narrows the blocker with new evidence.",
            },
        ],
        "artifacts": [
            artifact("deduplicated raw-CFA target NPZ", sources["targets"]),
            artifact("global Bayer-resize PSF receipt", sources["psf_receipt"], psf_receipt.get("schema")),
            artifact("non-PSF X2D scene baseline receipt", sources["baseline_receipt"], baseline_receipt.get("schema")),
            *[
                artifact(f"PSF probe receipt {idx + 1}", path, receipt.get("schema"))
                for idx, (path, receipt) in enumerate(psf_probe_receipts)
            ],
        ],
    }


def render_html(gap: dict[str, Any]) -> str:
    summary = gap["summary"]
    cards = [
        ("Another PSF CNN run justified", summary["another_psf_cnn_run_justified"]),
        ("Rows", summary["target_row_count"]),
        ("Scenes", summary["scene_count"]),
        ("Rows with PSF metadata", summary["rows_with_psf_metadata"]),
        ("Unique row kernels", summary["unique_row_psf_kernel_count"]),
        ("Global PSF near box", summary["global_psf_near_box"]),
        ("Baseline MAE recovery", summary["baseline_median_exact_raw_mae_recovery_pct"]),
        ("Best PSF probe MAE recovery", summary["best_psf_probe_median_exact_raw_mae_recovery_pct"]),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    blocker_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('id') or ''))}</td>"
        f"<td>{html.escape(str(row.get('status') or ''))}</td>"
        f"<td>{html.escape(str(row.get('detail') or ''))}</td>"
        "</tr>"
        for row in gap["blockers"]
    )
    probe_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('label') or ''))}</td>"
        f"<td>{html.escape(str(row.get('median_exact_raw_mae_recovery_pct')))}</td>"
        f"<td>{html.escape(str(row.get('median_raw_residual_rmse_recovery_pct')))}</td>"
        f"<td>{html.escape(str(row.get('best_holdout_probe_step')))}</td>"
        f"<td>{html.escape(str(row.get('path') or ''))}</td>"
        "</tr>"
        for row in [gap["baseline"], *gap["psf_probes"]]
    )
    action_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('priority') or ''))}</td>"
        f"<td>{html.escape(str(row.get('action') or ''))}</td>"
        f"<td>{html.escape(str(row.get('done_when') or ''))}</td>"
        "</tr>"
        for row in gap["next_actions"]
    )
    artifact_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('label') or ''))}</td>"
        f"<td>{html.escape(str(row.get('exists')))}</td>"
        f"<td>{html.escape(str(row.get('schema') or 'n/a'))}</td>"
        f"<td>{html.escape(str(row.get('path') or ''))}</td>"
        "</tr>"
        for row in gap["artifacts"]
    )
    camera_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(camera))}</td>"
        f"<td>{html.escape(str(count))}</td>"
        "</tr>"
        for camera, count in summary["inferred_camera_counts"].items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR PSF Metadata Gap</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; max-width: 920px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
</style></head><body><main>
<h1>Premium Still-SR PSF Metadata Gap</h1>
<p class="sub">Schema {html.escape(gap["schema"])}. This audit decides whether the next expensive still-SR CNN should repeat PSF conditioning, or whether the current evidence says the PSF input is too global/neutral to be useful.</p>
<div class="grid">{card_html}</div>
<h2>Inferred Camera Coverage</h2>
<table><thead><tr><th>Camera</th><th>Rows</th></tr></thead><tbody>{camera_rows}</tbody></table>
<h2>Baseline And PSF Probes</h2>
<table><thead><tr><th>Receipt</th><th>Median exact raw MAE recovery pct</th><th>Median raw RMSE recovery pct</th><th>Best step</th><th>Path</th></tr></thead><tbody>{probe_rows}</tbody></table>
<h2>Blockers</h2>
<table><thead><tr><th>ID</th><th>Status</th><th>Detail</th></tr></thead><tbody>{blocker_rows}</tbody></table>
<h2>Next Actions</h2>
<table><thead><tr><th>Priority</th><th>Action</th><th>Done when</th></tr></thead><tbody>{action_rows}</tbody></table>
<h2>Artifacts</h2>
<table><thead><tr><th>Artifact</th><th>Exists</th><th>Schema</th><th>Path</th></tr></thead><tbody>{artifact_rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    psf_probe_paths = args.psf_probe_receipt or DEFAULT_PSF_PROBE_RECEIPTS
    sources = {
        "targets": args.targets,
        "psf_receipt": args.psf_receipt,
        "baseline_receipt": args.baseline_receipt,
    }
    gap = build_gap(
        load_target_meta(args.targets),
        load_json(args.psf_receipt),
        load_json(args.baseline_receipt),
        [(path, load_json(path)) for path in psf_probe_paths],
        sources,
        args.near_box_epsilon,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "premium_still_sr_psf_metadata_gap.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(gap, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(gap), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
