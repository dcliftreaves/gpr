#!/usr/bin/env python3
"""Build Gate17 balanced replacement targets for Premium still-SR.

Gate15/Gate16 proved that a narrow X2D-positive target set plus Z8 exact no-op
does not generalize. Gate17 starts from the same Gate14 clean-source target
surface, but it materializes a balanced candidate-only training/evaluation
package with both 50 MP and 100 MP rows. This tool does not train a model and
does not claim production readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime env
    raise SystemExit("build_premium_still_sr_gate17_replacement_targets.py requires numpy") from exc


SCHEMA = "gpr.premium_still_sr_gate17_replacement_targets.v1"
PREFLIGHT_SCHEMA = "gpr.premium_still_sr_candidate_preflight.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_GATE14_TARGET_NPZ = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate14_floor_student_targets_20260702"
    / "gate14_floor_student_targets.npz"
)
DEFAULT_GATE16_AUDIT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_target_row_audit_20260702"
    / "gate16_target_row_audit.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "artifacts/premium_still_sr_gate17_replacement_targets_20260702"
DEFAULT_PYTHON = "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python"
DEFAULT_CANDIDATE_ID = "premium_still_sr_gate17_balanced_50mp_100mp_v1"
TARGET_KEYS = (
    "candidate_raw_cfa4",
    "candidate_raw_hf_cfa4",
    "raw_hf_residual_cfa4",
    "source_raw_hf_cfa4",
    "render_hf_residual_y",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def load_targets(path: Path) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    with np.load(path, allow_pickle=False) as z:
        missing = sorted(set(TARGET_KEYS + ("meta",)) - set(z.files))
        if missing:
            raise ValueError(f"{path} is missing required arrays: {', '.join(missing)}")
        arrays = {key: z[key] for key in TARGET_KEYS}
        rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} meta must be a JSON list of row objects")
    count = len(rows)
    for key, arr in arrays.items():
        if arr.shape[0] != count:
            raise ValueError(f"{key} row count {arr.shape[0]} does not match meta row count {count}")
    return arrays, rows


def row_class(row: dict[str, Any]) -> str:
    explicit = str(row.get("class") or "").lower()
    if "100" in explicit:
        return "100mp"
    if "50" in explicit:
        return "50mp"
    text = " ".join(str(row.get(key) or "") for key in ("domain", "camera_key", "camera", "image_id", "source_dng")).lower()
    if "x2d" in text or "100" in text:
        return "100mp"
    if "z8" in text or "mission" in text or "gopro" in text or "50" in text:
        return "50mp"
    return "unknown"


def number(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def selection_score(row: dict[str, Any]) -> float:
    residual = number(row, "raw_same_color_hf_residual_abs_mean")
    candidate_hf = number(row, "candidate_raw_same_color_hf_abs_mean")
    source_hf = number(row, "source_raw_same_color_hf_abs_mean")
    return residual + 0.25 * candidate_hf + 0.1 * source_hf


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def evenly_spaced_by_score(indices: list[int], rows: list[dict[str, Any]], count: int) -> list[int]:
    ordered = sorted(indices, key=lambda idx: (selection_score(rows[idx]), idx))
    if count <= 0 or count >= len(ordered):
        return ordered
    if count == 1:
        return [ordered[len(ordered) // 2]]
    selected: list[int] = []
    seen: set[int] = set()
    for pos in np.linspace(0, len(ordered) - 1, count):
        idx = ordered[int(round(float(pos)))]
        if idx not in seen:
            selected.append(idx)
            seen.add(idx)
    if len(selected) < count:
        for idx in ordered:
            if idx not in seen:
                selected.append(idx)
                seen.add(idx)
                if len(selected) == count:
                    break
    return sorted(selected)


def build_manifest(
    *,
    candidate_id: str,
    python_bin: str,
    output_dir: Path,
    target_npz: Path,
    target_sha256: str,
    receipt_path: Path,
    gate16_audit: Path,
) -> dict[str, Any]:
    train_out = output_dir.parent / "premium_still_sr_gate17_balanced_smoke_train_20260702"
    train_command = (
        f"env TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp {python_bin} "
        "tools/cnn/train_premium_still_sr_raw_cfa_residual.py "
        f"--targets {target_npz} --output-dir {train_out} "
        "--model-arch unet --feature-mode raw_context_coord_ev_noise_cfa "
        "--target-representation residual --target-policy raw "
        "--sample-balance row --sample-mode random_patch "
        "--context-padding 24 --eval-overlap 64 --seam-check-width 16 "
        "--steps 900 --batch-size 4 --patch-size 128 "
        "--width 48 --depth 6 --residual-scale 0.06 --lr 0.0002 "
        "--grad-weight 0.08 --target-abs-weight 0.35 "
        "--band-weight 0.04 --band-blocks 9 17 33 "
        "--target-energy-loss-weight-policy high_energy_emphasis "
        "--target-energy-loss-weight-strength 0.35 "
        "--candidate-hf-noop-threshold 0.0 "
        "--eval-holdout-rows 96 --eval-train-rows 96 "
        "--eval-during-training-rows 24 --save-best-holdout-checkpoint "
        "--seed 260717"
    )
    audit_command = (
        f"env TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp {python_bin} "
        "tools/build_premium_still_sr_gate16_target_row_audit.py "
        f"--candidate-id {candidate_id} "
        f"--train-receipt {train_out / 'train_receipt.json'} "
        f"--targets {target_npz} "
        f"--output-dir {output_dir.parent / 'premium_still_sr_gate17_balanced_target_row_audit_20260702'}"
    )
    return {
        "schema": PREFLIGHT_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "gate17_balanced_50mp_100mp_replacement_targets",
        "production_ready": False,
        "promotion_claimed": False,
        "launchable_for_production_attempt": False,
        "requires_material_edits_before_launch": False,
        "material_change_summary": (
            "Replaces the rejected Gate16 X2D-only target-row package with balanced "
            "50 MP and 100 MP candidate-only target rows before any promotion attempt."
        ),
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "candidate_tile_statistics",
            "candidate_tile_coordinates",
            "validated_noise_sidecar_optional",
        ],
        "forbidden_runtime_inputs_absent": True,
        "uses_ref_or_source_content_at_render_time": False,
        "source_evidence_receipts": [str(receipt_path), str(gate16_audit)],
        "target_dataset": str(target_npz),
        "target_dataset_sha256": target_sha256,
        "model_arch": "balanced candidate-only raw-CFA residual student",
        "architecture_family": "candidate-only raw-CFA restoration student",
        "architecture_deltas": [
            "balanced 50 MP and 100 MP target rows",
            "no exact-noop camera class during target-row smoke",
            "candidate-only runtime features",
            "broad target-row audit required before full promotion",
        ],
        "degradation_policy": (
            "Train on Gate14 clean-source low-Bayer to high-Bayer residual targets, "
            "balanced by camera class and selected across the target-energy range."
        ),
        "validation_plan": [
            "target-row audit must contain both 50mp and 100mp rows",
            "median MAE/RMSE recovery must clear 15% for both classes before promotion",
            "worst-row MAE must be nonnegative for both classes",
            "full-frame promotion gate remains required after target-row pass",
        ],
        "smoke_gate_commands": [train_command, audit_command],
        "smoke_gate_acceptance": {
            "minimum_median_mae_reduction_pct_50mp": 15.0,
            "minimum_median_rmse_reduction_pct_50mp": 15.0,
            "minimum_median_mae_reduction_pct_100mp": 15.0,
            "minimum_median_rmse_reduction_pct_100mp": 15.0,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_target_row_audit_fails": True,
        },
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
    }


def render_html(receipt: dict[str, Any]) -> str:
    class_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(cls)}</td>"
        f"<td>{summary['available_rows']}</td>"
        f"<td>{summary['selected_rows']}</td>"
        f"<td>{summary['selection_score']['median']:.6f}</td>"
        f"<td>{summary['residual_hf_abs_mean']['median']:.6f}</td>"
        "</tr>"
        for cls, summary in receipt["class_summary"].items()
    )
    missing = "\n".join(f"<li>{html.escape(item)}</li>" for item in receipt["missing_evidence_before_production"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate17 Premium Still-SR Replacement Targets</title>
<style>
body {{ margin: 30px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f6f8fa; }}
main {{ max-width: 1120px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style>
<main>
<h1>Gate17 Premium Still-SR Replacement Targets</h1>
<p>This package replaces the rejected Gate16 X2D-only target-row candidate with a balanced 50 MP / 100 MP target set. It is a training/audit input, not a production claim.</p>
<div class="grid">
<section class="card"><div class="label">Candidate</div><div class="value">{html.escape(receipt['candidate_id'])}</div></section>
<section class="card"><div class="label">Target rows</div><div class="value">{receipt['coverage']['selected_row_count']}</div></section>
<section class="card"><div class="label">50 MP rows</div><div class="value">{receipt['coverage']['selected_class_counts'].get('50mp', 0)}</div></section>
<section class="card"><div class="label">100 MP rows</div><div class="value">{receipt['coverage']['selected_class_counts'].get('100mp', 0)}</div></section>
<section class="card"><div class="label">Smoke ready</div><div class="value">{receipt['paired_smoke_ready']}</div></section>
</div>
<h2>Class Coverage</h2>
<table><tr><th>class</th><th>available</th><th>selected</th><th>median score</th><th>median residual HF</th></tr>{class_rows}</table>
<h2>Missing Evidence Before Production</h2>
<ul>{missing}</ul>
<h2>Artifacts</h2>
<pre>{html.escape(json.dumps(receipt['artifacts'], indent=2, sort_keys=True))}</pre>
</main>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    arrays, rows = load_targets(args.gate14_target_npz)
    gate16 = load_json(args.gate16_audit) if args.gate16_audit.exists() else {}
    class_to_indices: dict[str, list[int]] = {"50mp": [], "100mp": []}
    for idx, row in enumerate(rows):
        cls = row_class(row)
        if cls in class_to_indices:
            class_to_indices[cls].append(idx)
    available_counts = {cls: len(indices) for cls, indices in class_to_indices.items()}
    if min(available_counts.values()) <= 0:
        raise ValueError(f"replacement targets require both 50mp and 100mp rows, got {available_counts}")
    rows_per_class = int(args.rows_per_class)
    if rows_per_class <= 0:
        rows_per_class = min(available_counts.values())
    if rows_per_class < int(args.minimum_rows_per_class):
        raise ValueError(f"rows_per_class {rows_per_class} is below minimum {args.minimum_rows_per_class}")
    if any(count < rows_per_class for count in available_counts.values()):
        raise ValueError(f"not enough rows for balanced selection {rows_per_class}: {available_counts}")

    selected_by_class = {
        cls: evenly_spaced_by_score(indices, rows, rows_per_class)
        for cls, indices in class_to_indices.items()
    }
    selected_indices = sorted(idx for indices in selected_by_class.values() for idx in indices)
    index_to_class = {idx: cls for cls, indices in selected_by_class.items() for idx in indices}
    selected_rows: list[dict[str, Any]] = []
    for out_idx, source_idx in enumerate(selected_indices):
        row = dict(rows[source_idx])
        cls = index_to_class[source_idx]
        row.update(
            {
                "gate17_candidate_id": args.candidate_id,
                "gate17_source_index": int(source_idx),
                "gate17_output_index": int(out_idx),
                "gate17_policy": "balanced_50mp_100mp_signal_stratified_replacement",
                "gate17_target_class": cls,
                "gate17_target_row_scope": "target_row_tile",
                "gate17_candidate_only_runtime": True,
                "gate17_exact_noop": False,
                "gate17_selection_score": selection_score(row),
                "gate16_rejection_audit_sha256": sha256_file(args.gate16_audit) if args.gate16_audit.exists() else None,
            }
        )
        selected_rows.append(row)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    idx_arr = np.asarray(selected_indices, dtype=np.int64)
    out_npz = args.output_dir / "gate17_replacement_targets.npz"
    np.savez_compressed(
        out_npz,
        **{key: arrays[key][idx_arr] for key in TARGET_KEYS},
        meta=np.asarray(json.dumps(selected_rows, sort_keys=True)),
    )
    target_sha = sha256_file(out_npz)
    receipt_path = args.output_dir / "gate17_replacement_targets.json"
    manifest_path = args.output_dir / "candidate_preflight.json"
    manifest = build_manifest(
        candidate_id=args.candidate_id,
        python_bin=args.python_bin,
        output_dir=args.output_dir,
        target_npz=out_npz,
        target_sha256=target_sha,
        receipt_path=receipt_path,
        gate16_audit=args.gate16_audit,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    class_summary: dict[str, Any] = {}
    for cls, indices in selected_by_class.items():
        selected_class_rows = [rows[idx] for idx in indices]
        available_class_rows = [rows[idx] for idx in class_to_indices[cls]]
        class_summary[cls] = {
            "available_rows": len(available_class_rows),
            "selected_rows": len(selected_class_rows),
            "selection_score": stats([selection_score(row) for row in selected_class_rows]),
            "available_selection_score": stats([selection_score(row) for row in available_class_rows]),
            "residual_hf_abs_mean": stats([number(row, "raw_same_color_hf_residual_abs_mean") for row in selected_class_rows]),
            "candidate_hf_abs_mean": stats([number(row, "candidate_raw_same_color_hf_abs_mean") for row in selected_class_rows]),
        }
    selected_counts = dict(sorted(Counter(row["gate17_target_class"] for row in selected_rows).items()))
    smoke_ready = (
        selected_counts.get("50mp", 0) >= args.minimum_rows_per_class
        and selected_counts.get("100mp", 0) >= args.minimum_rows_per_class
    )
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": args.candidate_id,
        "production_ready": False,
        "promotion_claimed": False,
        "paired_smoke_ready": smoke_ready,
        "long_run_allowed": False,
        "row_scope": "target_row_tile",
        "replacement_for": str(gate16.get("candidate_id") or "premium_still_sr_gate16_tail_safe_x2d_positive_z8_noop_v1"),
        "replacement_reason": (
            "Gate16 target-row audit rejected the X2D-only target package; Gate17 restores balanced "
            "50 MP and 100 MP target-row coverage before another model promotion attempt."
        ),
        "coverage": {
            "source_row_count": len(rows),
            "source_class_counts": available_counts,
            "selected_row_count": len(selected_rows),
            "selected_class_counts": selected_counts,
            "rows_per_class": rows_per_class,
            "minimum_rows_per_class": int(args.minimum_rows_per_class),
        },
        "class_summary": class_summary,
        "runtime_policy": {
            "allowed_runtime_inputs": manifest["runtime_inputs"],
            "forbidden_runtime_inputs_absent": True,
            "uses_ref_or_source_content_at_render_time": False,
            "training_supervision_uses_source_tile": True,
        },
        "inputs": {
            "gate14_target_npz": {
                "path": str(args.gate14_target_npz),
                "sha256": sha256_file(args.gate14_target_npz),
            },
            "gate16_rejection_audit": {
                "path": str(args.gate16_audit),
                "sha256": sha256_file(args.gate16_audit) if args.gate16_audit.exists() else None,
            },
        },
        "artifacts": {
            "targets": str(out_npz),
            "targets_sha256": target_sha,
            "candidate_preflight": str(manifest_path),
            "candidate_preflight_sha256": sha256_file(manifest_path),
            "dashboard": str(args.output_dir / "index.html"),
        },
        "next_unambiguous_action": (
            "Run the candidate_preflight smoke training command, then run the target-row audit command. "
            "Do not proceed to full promotion unless both 50mp and 100mp rows clear the 15%/15% floors and nonnegative worst-row MAE."
        ),
        "missing_evidence_before_production": [
            "Gate17 trained checkpoint and hash",
            "Gate17 target-row audit pass on both 50mp and 100mp rows",
            "full-frame 50 MP / 100 MP promotion rows",
            "render seconds per 50 MP and 100 MP frame",
            "peak RSS",
            "editor/openability and exact-sidecar-only noise policy wiring",
            "production submission validation",
        ],
        "sample_rows": selected_rows[:8],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(receipt), encoding="utf-8")
    return receipt


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate14-target-npz", type=Path, default=DEFAULT_GATE14_TARGET_NPZ)
    ap.add_argument("--gate16-audit", type=Path, default=DEFAULT_GATE16_AUDIT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID)
    ap.add_argument("--python-bin", default=DEFAULT_PYTHON)
    ap.add_argument("--rows-per-class", type=int, default=0, help="Default 0 selects the largest balanced class count.")
    ap.add_argument("--minimum-rows-per-class", type=int, default=256)
    return ap.parse_args()


def main() -> int:
    receipt = build(parse_args())
    print(
        json.dumps(
            {
                "receipt": str(Path(receipt["artifacts"]["dashboard"]).with_name("gate17_replacement_targets.json")),
                "dashboard": receipt["artifacts"]["dashboard"],
                "targets": receipt["artifacts"]["targets"],
                "paired_smoke_ready": receipt["paired_smoke_ready"],
                "selected_class_counts": receipt["coverage"]["selected_class_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
