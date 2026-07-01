#!/usr/bin/env python3
"""Build a row-level PSF sidecar contract for premium still-SR targets.

The premium still-SR raw-CFA trainer can condition on PSF/kernel scalar planes,
but a global near-box kernel is not enough evidence for promotion. This tool
attaches PSF receipts to target rows by stable row key so camera-specific PSF
measurements can be consumed without rebuilding the target NPZ.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


CONTRACT_SCHEMA = "gpr.premium_still_sr_psf_sidecar_contract.v1"
SIDECAR_SCHEMA = "gpr.premium_still_sr_psf_sidecar.v1"
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


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument(
        "--camera-psf",
        action="append",
        default=[],
        metavar="CAMERA=RECEIPT.json",
        help="Camera-specific PSF receipt. May be repeated, for example x2d=receipt.json.",
    )
    ap.add_argument(
        "--default-psf",
        type=Path,
        default=DEFAULT_PSF_RECEIPT,
        help="Fallback PSF receipt for rows without a camera-specific receipt.",
    )
    ap.add_argument("--near-box-epsilon", type=float, default=1.0e-3)
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def load_target_meta(path: Path) -> list[dict[str, Any]]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
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


def normalize_weights(values: Any) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"expected four PSF weights, got {values!r}")
    weights = [float(v) for v in values]
    total = sum(weights)
    if abs(total) <= 1.0e-12:
        raise ValueError("PSF weights must not sum to zero")
    return [float(v / total) for v in weights]


def receipt_weights(payload: dict[str, Any], path: Path) -> list[float]:
    model = payload.get("psf_model")
    if not isinstance(model, dict):
        raise ValueError(f"{path} has no psf_model object")
    weights = model.get("normalized_weights") or model.get("weights")
    return normalize_weights(weights)


def parse_camera_psf(values: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--camera-psf must be CAMERA=PATH, got {value!r}")
        camera, raw_path = value.split("=", 1)
        camera = camera.strip().lower()
        if not camera:
            raise ValueError(f"--camera-psf has an empty camera name: {value!r}")
        out[camera] = Path(raw_path).expanduser()
    return out


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


def target_row_key(row: dict[str, Any], idx: int) -> str:
    payload = {
        "index": int(idx),
        "scene_id": row.get("scene_id") or row.get("scene") or "",
        "crop": row.get("crop") or "",
        "crop_xy": row.get("crop_xy") or row.get("candidate_raw_cfa_origin_xy") or [],
        "candidate_raw": row.get("candidate_raw") or row.get("candidate_dng") or "",
        "source_raw": row.get("source_raw") or row.get("source_dng") or "",
        "ev": row.get("ev"),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def is_near_box(weights: list[float], epsilon: float) -> bool:
    return max(abs(float(v) - 0.25) for v in weights) <= float(epsilon)


def source_record(label: str, path: Path, weights: list[float]) -> dict[str, Any]:
    return {
        "label": label,
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "psf_kernel_weights": weights,
    }


def build_sidecar_and_contract(
    *,
    targets: Path,
    target_rows: list[dict[str, Any]],
    camera_receipts: dict[str, Path],
    default_psf: Path | None,
    near_box_epsilon: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_sources: dict[str, dict[str, Any]] = {}
    camera_weights: dict[str, list[float]] = {}
    for camera, path in sorted(camera_receipts.items()):
        payload = load_json(path)
        weights = receipt_weights(payload, path)
        camera_weights[camera] = weights
        receipt_sources[f"camera:{camera}"] = source_record(f"camera:{camera}", path, weights)

    default_weights: list[float] | None = None
    if default_psf is not None and default_psf.exists():
        payload = load_json(default_psf)
        default_weights = receipt_weights(payload, default_psf)
        receipt_sources["default"] = source_record("default", default_psf, default_weights)

    rows: list[dict[str, Any]] = []
    camera_counts: Counter[str] = Counter()
    assignment_counts: Counter[str] = Counter()
    near_box_count = 0
    for idx, row in enumerate(target_rows):
        camera = infer_camera(row)
        camera_counts[camera] += 1
        weights = camera_weights.get(camera)
        assignment_policy = "camera_specific"
        source_key = f"camera:{camera}"
        if weights is None:
            weights = default_weights
            assignment_policy = "default_global" if default_weights is not None else "missing"
            source_key = "default" if default_weights is not None else ""
        if weights is None:
            rows.append(
                {
                    "target_row_index": idx,
                    "row_key": target_row_key(row, idx),
                    "scene": scene_key(row),
                    "crop": row.get("crop"),
                    "camera": camera,
                    "assignment_policy": assignment_policy,
                    "psf_kernel_weights": None,
                }
            )
            assignment_counts[assignment_policy] += 1
            continue
        source = receipt_sources[source_key]
        if is_near_box(weights, near_box_epsilon):
            near_box_count += 1
        rows.append(
            {
                "target_row_index": idx,
                "row_key": target_row_key(row, idx),
                "scene": scene_key(row),
                "crop": row.get("crop"),
                "camera": camera,
                "assignment_policy": assignment_policy,
                "psf_kernel_weights": weights,
                "psf_receipt_path": source["path"],
                "psf_receipt_sha256": source["sha256"],
                "near_box": is_near_box(weights, near_box_epsilon),
            }
        )
        assignment_counts[assignment_policy] += 1

    unique_kernels = sorted(
        {
            tuple(round(float(v), 9) for v in row["psf_kernel_weights"])
            for row in rows
            if isinstance(row.get("psf_kernel_weights"), list)
        }
    )
    summary = {
        "target_row_count": len(target_rows),
        "scene_count": len({scene_key(row) for row in target_rows}),
        "camera_counts": dict(sorted(camera_counts.items())),
        "rows_with_camera_specific_psf": int(assignment_counts["camera_specific"]),
        "rows_using_default_psf": int(assignment_counts["default_global"]),
        "rows_missing_psf": int(assignment_counts["missing"]),
        "unique_kernel_count": len(unique_kernels),
        "near_box_rows": near_box_count,
        "training_ready_for_psf_conditioning": (
            len(target_rows) > 0
            and assignment_counts["camera_specific"] == len(target_rows)
            and assignment_counts["default_global"] == 0
            and assignment_counts["missing"] == 0
            and len(unique_kernels) >= 2
            and near_box_count < len(target_rows)
        ),
    }
    blockers: list[dict[str, Any]] = []
    if summary["rows_missing_psf"]:
        blockers.append({"id": "missing_psf_rows", "detail": f"{summary['rows_missing_psf']} target rows have no PSF assignment."})
    if summary["rows_using_default_psf"]:
        blockers.append({"id": "default_global_psf_rows", "detail": f"{summary['rows_using_default_psf']} target rows still use the global fallback."})
    if summary["unique_kernel_count"] < 2:
        blockers.append({"id": "no_psf_variation", "detail": f"Only {summary['unique_kernel_count']} unique PSF kernels are assigned."})
    if near_box_count == len(target_rows) and target_rows:
        blockers.append({"id": "all_psf_kernels_near_box", "detail": "All assigned kernels are near a 2x box filter."})

    created = int(time.time())
    sidecar = {
        "schema": SIDECAR_SCHEMA,
        "created_unix": created,
        "targets": targets.as_posix(),
        "targets_sha256": sha256_file(targets),
        "row_key_algorithm": "sha256(index, scene_id, crop, crop_xy, candidate_raw, source_raw, ev)",
        "rows": rows,
    }
    contract = {
        "schema": CONTRACT_SCHEMA,
        "created_unix": created,
        "targets": targets.as_posix(),
        "targets_sha256": sidecar["targets_sha256"],
        "sidecar_schema": SIDECAR_SCHEMA,
        "row_key_algorithm": sidecar["row_key_algorithm"],
        "sources": receipt_sources,
        "summary": summary,
        "blockers": blockers,
        "usage": {
            "trainer_flag": "--psf-sidecar",
            "trainer_policy": "row metadata wins; sidecar beats global PSF fallback",
        },
    }
    return sidecar, contract


def render_html(contract: dict[str, Any], sidecar_path: Path) -> str:
    summary = contract["summary"]
    blockers = contract["blockers"]
    rows = [
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in summary.items()
    ]
    blocker_rows = [
        f"<tr><td>{html.escape(str(row['id']))}</td><td>{html.escape(str(row['detail']))}</td></tr>"
        for row in blockers
    ]
    source_rows = [
        f"<tr><td>{html.escape(str(label))}</td><td><code>{html.escape(str(src['path']))}</code></td><td><code>{html.escape(str(src['sha256']))}</code></td><td>{html.escape(str(src['psf_kernel_weights']))}</td></tr>"
        for label, src in sorted(contract["sources"].items())
    ]
    ready = "ready" if summary["training_ready_for_psf_conditioning"] else "not ready"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR PSF Sidecar Contract</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#101216;color:#f0f3f6;margin:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #2d3540;background:#171b21;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}td,th{{border-bottom:1px solid #2d3540;padding:8px;text-align:left;vertical-align:top}}
code{{color:#b9d7ff}}
.bad{{color:#ffb7b7}}.good{{color:#9effbd}}
</style></head><body>
<h1>Premium Still SR PSF Sidecar Contract</h1>
<p>This artifact maps raw-CFA target rows to PSF kernels by stable row key. It is a production guardrail: training should not treat a global near-box fallback as camera-specific PSF evidence.</p>
<div class="grid">
<div class="card"><h2>Readiness</h2><p class="{'good' if summary['training_ready_for_psf_conditioning'] else 'bad'}">{ready}</p></div>
<div class="card"><h2>Rows</h2><p>{summary['target_row_count']}</p></div>
<div class="card"><h2>Camera-Specific</h2><p>{summary['rows_with_camera_specific_psf']}</p></div>
<div class="card"><h2>Default Fallback</h2><p>{summary['rows_using_default_psf']}</p></div>
</div>
<p>Trainer sidecar: <code>{html.escape(sidecar_path.as_posix())}</code></p>
<h2>Summary</h2><table><tr><th>metric</th><th>value</th></tr>{''.join(rows)}</table>
<h2>Blockers</h2><table><tr><th>id</th><th>detail</th></tr>{''.join(blocker_rows) or '<tr><td colspan="2">none</td></tr>'}</table>
<h2>Sources</h2><table><tr><th>source</th><th>path</th><th>sha256</th><th>weights</th></tr>{''.join(source_rows)}</table>
</body></html>
"""


def main() -> int:
    args = parse_args()
    target_rows = load_target_meta(args.targets)
    sidecar, contract = build_sidecar_and_contract(
        targets=args.targets,
        target_rows=target_rows,
        camera_receipts=parse_camera_psf(args.camera_psf),
        default_psf=args.default_psf,
        near_box_epsilon=args.near_box_epsilon,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = args.output_dir / "premium_still_sr_psf_sidecar.json"
    contract_path = args.output_dir / "premium_still_sr_psf_sidecar_contract.json"
    index_path = args.output_dir / "index.html"
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    contract["artifacts"] = {
        "sidecar": sidecar_path.as_posix(),
        "sidecar_sha256": sha256_file(sidecar_path),
        "contract": contract_path.as_posix(),
        "dashboard": index_path.as_posix(),
    }
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index_path.write_text(render_html(contract, sidecar_path), encoding="utf-8")
    print(json.dumps({"contract": contract_path.as_posix(), "sidecar": sidecar_path.as_posix(), "dashboard": index_path.as_posix(), "summary": contract["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
