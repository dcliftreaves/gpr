#!/usr/bin/env python3
"""Materialize Gate15 target-construction policy into paired-smoke inputs.

Gate15 target-construction preflight proves that a proposal has enough X2D
candidate-only positive rows and safe Z8 exact-noop rows. This tool turns that
proposal into the next executable artifact: an X2D-positive raw-CFA target NPZ
for the trainer plus a candidate-preflight-style manifest whose Z8 leg is an
explicit exact-noop receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime env
    raise SystemExit("build_premium_still_sr_gate15_smoke_targets.py requires numpy") from exc


SCHEMA = "gpr.premium_still_sr_gate15_smoke_targets.v1"
MANIFEST_SCHEMA = "gpr.premium_still_sr_candidate_preflight.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_GATE14_TARGET_NPZ = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate14_floor_student_targets_20260702"
    / "gate14_floor_student_targets.npz"
)
DEFAULT_PROPOSAL = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate15_target_construction_proposal_20260702"
    / "target_construction_proposal.json"
)
DEFAULT_PREFLIGHT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate15_target_construction_preflight_with_proposal_20260702"
    / "target_construction_preflight.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "artifacts/premium_still_sr_gate15_smoke_targets_20260702"
DEFAULT_PYTHON = "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python"


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


def policy_key(row: dict[str, Any]) -> str:
    return str(row.get("gate14_output_index") if row.get("gate14_output_index") is not None else row.get("tile_index"))


def load_targets(path: Path) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    with np.load(path, allow_pickle=False) as z:
        required = {
            "candidate_raw_cfa4",
            "candidate_raw_hf_cfa4",
            "raw_hf_residual_cfa4",
            "source_raw_hf_cfa4",
            "render_hf_residual_y",
            "meta",
        }
        missing = sorted(required - set(z.files))
        if missing:
            raise ValueError(f"{path} is missing required arrays: {', '.join(missing)}")
        arrays = {key: z[key] for key in required if key != "meta"}
        rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} meta must be a JSON list of row objects")
    count = len(rows)
    for key, arr in arrays.items():
        if arr.shape[0] != count:
            raise ValueError(f"{key} row count {arr.shape[0]} does not match meta row count {count}")
    return arrays, rows


def build_manifest(
    *,
    candidate_id: str,
    python_bin: str,
    target_npz: Path,
    x2d_out: Path,
    z8_out: Path,
    z8_row_count: int,
    target_sha256: str,
    proposal: Path,
    preflight: Path,
) -> dict[str, Any]:
    common_args = (
        "--model-arch unet "
        "--feature-mode raw_context_coord_ev_noise_cfa "
        "--target-representation residual --target-policy raw "
        "--sample-balance scene --sample-mode full_crop "
        "--context-padding 24 --eval-overlap 64 --seam-check-width 16 "
        "--steps 420 --batch-size 2 --patch-size 192 "
        "--width 40 --depth 5 --residual-scale 0.04 --lr 0.0001 "
        "--grad-weight 0.08 --target-abs-weight 0.25 "
        "--band-weight 0.04 --band-blocks 9 17 33 "
        "--target-energy-loss-weight-policy high_energy_emphasis "
        "--target-energy-loss-weight-strength 0.35 "
        "--target-scale-policy candidate_hf_abs_mean "
        "--target-scale-strength 0.5 "
        "--candidate-hf-noop-threshold 0.001 "
        "--candidate-hf-noop-softness 0.001 "
        "--eval-holdout-rows 32 --eval-train-rows 32 "
        "--eval-during-training-rows 12 --save-best-holdout-checkpoint "
        "--seed 260715"
    )
    x2d_command = (
        f"{python_bin} tools/cnn/train_premium_still_sr_raw_cfa_residual.py "
        f"--targets {target_npz} --output-dir {x2d_out} "
        "--holdout-scene x2d_2025_austin_07 "
        f"{common_args}"
    )
    z8_command = (
        f"{python_bin} tools/build_premium_still_sr_exact_noop_receipt.py "
        f"--output-dir {z8_out} --holdout z8 --mode exact-noop --row-count {int(z8_row_count)} "
        "--reason \"Gate15 proposal keeps Z8 exact no-op until positive source evidence exists\""
    )
    return {
        "schema": MANIFEST_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_kind": "gate15_x2d_positive_z8_exact_noop_smoke",
        "teacher_gate_before_student": True,
        "production_ready": False,
        "promotion_claimed": False,
        "launchable_for_production_attempt": True,
        "requires_material_edits_before_launch": False,
        "material_change_summary": (
            "Materializes Gate15 target construction: train only X2D rows with "
            "candidate-derived positive signal, and keep Z8 as an exact no-op "
            "route until positive source evidence exists."
        ),
        "runtime_inputs": [
            "candidate_raw",
            "camera_metadata",
            "candidate_tile_statistics",
            "candidate_tile_coordinates",
            "candidate_scene_normalized_tile_statistics",
            "validated_noise_sidecar_optional",
        ],
        "forbidden_runtime_inputs_absent": True,
        "uses_ref_or_source_content_at_render_time": False,
        "source_evidence_receipts": [str(proposal), str(preflight)],
        "target_dataset": str(target_npz),
        "target_dataset_sha256": target_sha256,
        "model_arch": "full-image raw-CFA restoration student with exact-noop route guard",
        "architecture_family": "candidate-only full-image raw-CFA restoration student",
        "architecture_deltas": [
            "full-image raw-CFA restoration student",
            "overlapped-tile high-resolution inference",
            "target/objective revision from Gate15 candidate-positive row evidence",
            "candidate-only exact no-op behavior for routes without positive source evidence",
        ],
        "degradation_policy": (
            "Gate15 target/objective revision: train on X2D candidate-positive "
            "same-color CFA residual targets, preserve Z8 exact no-op until "
            "positive source evidence exists, and validate against same-color "
            "Bayer interpolation before any long run."
        ),
        "degradation_deltas": [
            "sensor and CFA phase aware raw-CFA target construction",
            "ISO/noise sidecars remain exact-sidecar-only metadata until strict provenance exists",
            "bit-depth and compression/decode simulation remains part of the full promotion gate",
            "candidate-derived target scale and no-op route policy replace unsafe threshold rescue",
        ],
        "validation_plan": [
            "held-out X2D full-image gate using Gate15 positive raw-CFA targets",
            "held-out Z8 exact no-op smoke gate until positive source evidence exists",
            "50 MP full-frame gate row accounting",
            "100 MP full-frame gate row accounting",
            "overlapped-tile evaluation with seam diagnostics",
            "both X2D and Z8 smoke holdouts beat interpolation before long run",
            "worst-row 100 percent crop review",
        ],
        "holdouts": [
            "X2D scene-held-out full-frame raw-CFA images",
            "Z8 exact no-op route receipt",
        ],
        "baseline_comparisons": [
            "same-color Bayer interpolation baseline",
            "current still-SR scoreboard and 12k window-attention rejection",
            "Gate14 objective-gate audit showing threshold tuning cannot rescue failed objectives",
            "Gate15 target-construction preflight pass",
        ],
        "planned_receipts": [
            "checkpoint hash",
            "training config hash",
            "target dataset hash",
            "dashboard",
            "timing memory receipt",
            "editor latitude review",
            "editable DNG/GPR raw receipt",
            "noise policy receipt",
            "smoke gate acceptance receipt",
        ],
        "promotion_receipts": [
            "50 MP full-frame gate",
            "100 MP full-frame gate",
            "worst-row visual review",
            "seconds per frame and peak RSS memory",
        ],
        "smoke_gate_commands": [x2d_command, z8_command],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 1.0,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "route_acceptance": {
                "z8": {
                    "requires_exact_noop": True,
                    "minimum_median_mae_reduction_pct": 0.0,
                    "minimum_worst_row_mae_reduction_pct": 0.0,
                }
            },
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
        "notes": (
            "This is a paired smoke manifest only. A long run remains blocked "
            "until the smoke acceptance checker passes."
        ),
        "noise_policy": {
            "exact_sidecars_only": True,
            "forbids_source_residual_noise": True,
            "missing_sidecars": "metadata_only",
        },
    }


def render_html(receipt: dict[str, Any]) -> str:
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate15 Smoke Targets</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #17202a; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: #d5f5e3; }}
table {{ border-collapse: collapse; min-width: 720px; margin-top: 16px; }}
th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px 10px; text-align: left; }}
code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
</style>
<h1>Gate15 Smoke Targets</h1>
<p class="status"><b>READY</b> {html.escape(str(receipt["candidate_id"]))}</p>
<table>
<tr><th>X2D positive target rows</th><td>{receipt["coverage"]["x2d_positive_target_rows"]}</td></tr>
<tr><th>Z8 exact no-op rows</th><td>{receipt["coverage"]["z8_exact_noop_rows"]}</td></tr>
<tr><th>Target NPZ</th><td><code>{html.escape(receipt["artifacts"]["x2d_positive_targets"])}</code></td></tr>
<tr><th>Launch manifest</th><td><code>{html.escape(receipt["artifacts"]["candidate_preflight"])}</code></td></tr>
</table>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate14-target-npz", type=Path, default=DEFAULT_GATE14_TARGET_NPZ)
    ap.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    ap.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--python-bin", default=DEFAULT_PYTHON)
    ap.add_argument("--minimum-x2d-positive-rows", type=int, default=289)
    args = ap.parse_args()

    proposal = load_json(args.proposal)
    preflight = load_json(args.preflight)
    if preflight.get("paired_smoke_allowed") is not True:
        raise ValueError("Gate15 smoke targets require a preflight with paired_smoke_allowed=true")
    candidate_id = str(proposal.get("candidate_id") or "premium_still_sr_gate15_x2d_positive_z8_noop_v1")
    policies = proposal.get("pretraining_signal_rows")
    if not isinstance(policies, list):
        raise ValueError("proposal is missing pretraining_signal_rows")
    policy_by_key = {policy_key(row): row for row in policies if isinstance(row, dict)}

    arrays, rows = load_targets(args.gate14_target_npz)
    positive_indices: list[int] = []
    z8_noop_rows = 0
    missing_policy_rows = 0
    for idx, row in enumerate(rows):
        policy = policy_by_key.get(policy_key(row))
        if not isinstance(policy, dict):
            missing_policy_rows += 1
            continue
        domain = str(row.get("domain") or policy.get("domain") or "").lower()
        if domain == "x2d" and policy.get("candidate_only_positive_floor") is True:
            positive_indices.append(idx)
        if domain == "z8" and policy.get("exact_noop") is True:
            z8_noop_rows += 1
    if len(positive_indices) < args.minimum_x2d_positive_rows:
        raise ValueError(
            f"only {len(positive_indices)} X2D positive rows; need at least {args.minimum_x2d_positive_rows}"
        )
    if z8_noop_rows <= 0:
        raise ValueError("proposal produced no Z8 exact-noop rows")

    idx_arr = np.asarray(positive_indices, dtype=np.int64)
    out_npz = args.output_dir / "gate15_x2d_positive_targets.npz"
    out_manifest = args.output_dir / "candidate_preflight.json"
    x2d_out = args.output_dir.parent / "premium_still_sr_gate15_x2d_positive_smoke_20260702"
    z8_out = args.output_dir.parent / "premium_still_sr_gate15_z8_exact_noop_smoke_20260702"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    out_rows: list[dict[str, Any]] = []
    for out_idx, source_idx in enumerate(positive_indices):
        row = dict(rows[source_idx])
        row.update(
            {
                "gate15_candidate_id": candidate_id,
                "gate15_source_index": int(source_idx),
                "gate15_output_index": int(out_idx),
                "gate15_policy": "x2d_candidate_only_positive_supervision",
                "gate15_candidate_only_positive_floor": True,
                "gate15_exact_noop": False,
                "gate15_proposal_sha256": sha256_file(args.proposal),
                "gate15_preflight_sha256": sha256_file(args.preflight),
            }
        )
        out_rows.append(row)

    np.savez_compressed(
        out_npz,
        candidate_raw_cfa4=arrays["candidate_raw_cfa4"][idx_arr],
        candidate_raw_hf_cfa4=arrays["candidate_raw_hf_cfa4"][idx_arr],
        raw_hf_residual_cfa4=arrays["raw_hf_residual_cfa4"][idx_arr],
        source_raw_hf_cfa4=arrays["source_raw_hf_cfa4"][idx_arr],
        render_hf_residual_y=arrays["render_hf_residual_y"][idx_arr],
        meta=np.asarray(json.dumps(out_rows, sort_keys=True)),
    )
    target_sha = sha256_file(out_npz)
    manifest = build_manifest(
        candidate_id=candidate_id,
        python_bin=args.python_bin,
        target_npz=out_npz,
        x2d_out=x2d_out,
        z8_out=z8_out,
        z8_row_count=z8_noop_rows,
        target_sha256=target_sha,
        proposal=args.proposal,
        preflight=args.preflight,
    )
    out_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": candidate_id,
        "production_ready": False,
        "promotion_claimed": False,
        "paired_smoke_ready": True,
        "long_run_allowed": False,
        "coverage": {
            "gate14_row_count": len(rows),
            "proposal_policy_row_count": len(policy_by_key),
            "missing_policy_rows": missing_policy_rows,
            "x2d_positive_target_rows": len(positive_indices),
            "minimum_x2d_positive_rows": args.minimum_x2d_positive_rows,
            "z8_exact_noop_rows": z8_noop_rows,
        },
        "inputs": {
            "gate14_target_npz": str(args.gate14_target_npz),
            "gate14_target_npz_sha256": sha256_file(args.gate14_target_npz),
            "proposal": str(args.proposal),
            "proposal_sha256": sha256_file(args.proposal),
            "preflight": str(args.preflight),
            "preflight_sha256": sha256_file(args.preflight),
        },
        "artifacts": {
            "x2d_positive_targets": str(out_npz),
            "x2d_positive_targets_sha256": target_sha,
            "candidate_preflight": str(out_manifest),
            "candidate_preflight_sha256": sha256_file(out_manifest),
            "dashboard": str(args.output_dir / "index.html"),
        },
        "next_step": "run smoke_gate_commands from candidate_preflight.json, then run smoke acceptance",
    }
    receipt_path = args.output_dir / "gate15_smoke_targets.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "candidate_id": candidate_id,
                "x2d_positive_rows": len(positive_indices),
                "z8_exact_noop_rows": z8_noop_rows,
                "paired_smoke_ready": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
