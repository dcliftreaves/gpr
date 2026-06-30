#!/usr/bin/env python3
"""Build the next-experiment contract for premium still-SR.

This is not a training script. It consumes the current dataset inventory,
experiment scoreboard, raw-CFA residual gap audit, and production capture
requirements, then writes the narrow contract for the next model pass. The
purpose is to keep premium still-SR work pointed at the canonical raw-CFA
targets and away from already-rejected local/context/noise/sampling-only probes.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.premium_still_sr_next_experiment_contract.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def dataset_by_id(inventory: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    for row in inventory.get("datasets", []):
        if isinstance(row, dict) and row.get("id") == dataset_id:
            return row
    return {"id": dataset_id, "exists": False, "ready_for_current_work": False, "missing_expected_artifacts": ["dataset row missing"]}


def requirement_by_id(requirements: dict[str, Any], requirement_id: str) -> dict[str, Any]:
    for row in requirements.get("requirements", []):
        if isinstance(row, dict) and row.get("id") == requirement_id:
            return row
    return {"id": requirement_id, "status": "missing", "required_evidence": [], "acceptance": []}


def num(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def build_contract(
    *,
    inventory: dict[str, Any],
    scoreboard: dict[str, Any],
    residual_gap: dict[str, Any],
    requirements: dict[str, Any],
    external_root: Path,
) -> dict[str, Any]:
    rawcfa_dataset = dataset_by_id(inventory, "premium_still_sr_expanded_rawcfa_targets")
    residual_dataset = dataset_by_id(inventory, "premium_still_sr_raw_cfa_residual_targets")
    requirement = requirement_by_id(requirements, "premium_still_sr_promotion_receipts")
    target = residual_gap.get("target") if isinstance(residual_gap.get("target"), dict) else {}
    thresholds = residual_gap.get("promotion_thresholds") if isinstance(residual_gap.get("promotion_thresholds"), dict) else {}
    camera_summary = [row for row in residual_gap.get("camera_summary", []) if isinstance(row, dict)]
    blockers = [str(row) for row in residual_gap.get("blockers", [])]
    next_experiments = [row for row in residual_gap.get("next_experiments", []) if isinstance(row, dict)]
    promotable_count = int(scoreboard.get("promotable_candidate_count") or 0)

    canonical_targets_ready = bool(rawcfa_dataset.get("ready_for_current_work")) and bool(
        residual_dataset.get("ready_for_current_work")
    )
    gap_production_ready = bool(residual_gap.get("production_ready"))
    scoreboard_production_ready = bool(scoreboard.get("production_ready"))
    requirement_open = requirement.get("status") in {"open", "blocked_on_real_camera_access", "missing"}
    production_ready = canonical_targets_ready and gap_production_ready and scoreboard_production_ready and not requirement_open

    best_by_camera = {
        str(row.get("camera")): {
            "best_holdout_mae_recovery_pct_median": row.get("best_holdout_mae_recovery_pct_median"),
            "best_holdout_rmse_recovery_pct_median": row.get("best_holdout_rmse_recovery_pct_median"),
            "passes_threshold": bool(row.get("passes_threshold")),
            "best_path": row.get("best_path"),
        }
        for row in camera_summary
    }
    mae_threshold = num(thresholds.get("holdout_mae_recovery_pct_median_min"), 15.0)
    rmse_threshold = num(thresholds.get("holdout_rmse_recovery_pct_median_min"), 0.0)

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "production_ready": production_ready,
        "should_start_next_model_pass": canonical_targets_ready and not production_ready,
        "requirement": {
            "id": requirement.get("id"),
            "status": requirement.get("status"),
            "required_evidence": requirement.get("required_evidence", []),
            "acceptance": requirement.get("acceptance", []),
        },
        "canonical_targets": [
            {
                "id": rawcfa_dataset.get("id"),
                "path": rawcfa_dataset.get("path"),
                "ready_for_current_work": bool(rawcfa_dataset.get("ready_for_current_work")),
                "missing_expected_artifacts": rawcfa_dataset.get("missing_expected_artifacts", []),
                "role": rawcfa_dataset.get("role"),
            },
            {
                "id": residual_dataset.get("id"),
                "path": residual_dataset.get("path"),
                "ready_for_current_work": bool(residual_dataset.get("ready_for_current_work")),
                "missing_expected_artifacts": residual_dataset.get("missing_expected_artifacts", []),
                "role": residual_dataset.get("role"),
            },
        ],
        "target_lock": {
            "path": target.get("path"),
            "sha256": target.get("sha256"),
            "row_count": target.get("row_count"),
            "scene_count": target.get("scene_count"),
            "scenes": target.get("scenes", []),
            "render_to_raw_corr_abs_median": target.get("render_to_raw_corr_abs_median"),
            "raw_to_render_hf_abs_ratio_median": target.get("raw_to_render_hf_abs_ratio_median"),
            "runtime_policy": "source raw/HF is training-target only; render-time candidate must use no REF/source content",
        },
        "current_model_state": {
            "scoreboard_receipt_count": scoreboard.get("receipt_count"),
            "scoreboard_promotable_candidate_count": promotable_count,
            "scoreboard_best_candidate": scoreboard.get("best_candidate"),
            "residual_gap_production_ready": gap_production_ready,
            "best_by_camera": best_by_camera,
            "blockers": blockers,
        },
        "next_model_contract": {
            "recommended_first_track": "domain-balanced full-image or routed raw-CFA residual learner",
            "allowed_runtime_inputs": [
                "candidate raw/CFA planes",
                "candidate-derived luma/detail features",
                "camera metadata",
                "ISO/noise sidecar scalar conditioning where validated",
            ],
            "forbidden_runtime_inputs": [
                "REF image content",
                "source raw content",
                "source high-frequency residuals",
                "JPEG-derived target content",
            ],
            "do_not_repeat_as_primary_path": [
                "rendered-context-only target coverage change",
                "stored candidate-HF feature concatenation",
                "naive one-sigma noise-thresholded targets",
                "simple pooled local raw context",
                "combined stored-HF plus pooled-context features",
                "simple multiscale band-loss reweighting",
                "X2D-only domain filtering without a stronger context/objective",
                "camera-balanced sampling without a stronger context/objective",
                "calibrated random-HF or noise addback as a substitute for learned signal detail",
            ],
            "success_gates": [
                f"X2D median raw-residual MAE recovery >= {mae_threshold:.1f}%",
                f"Z8 median raw-residual MAE recovery >= {mae_threshold:.1f}%",
                f"holdout raw-residual RMSE recovery >= {rmse_threshold:.1f}%",
                "no severe negative worst rows in full still/editor-latitude review",
                "50 MP and 100 MP editable raw outputs open and roundtrip",
                "checkpoint, target hashes, config, dashboard, timing, memory, and noise-policy receipts are recorded",
            ],
            "candidate_experiments": next_experiments,
        },
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    targets = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('id')))}</td>"
        f"<td>{'ready' if row.get('ready_for_current_work') else 'missing'}</td>"
        f"<td><code>{html.escape(str(row.get('path')))}</code></td>"
        f"<td>{html.escape(', '.join(map(str, row.get('missing_expected_artifacts') or [])))}</td>"
        "</tr>"
        for row in data["canonical_targets"]
    )
    cameras = "\n".join(
        "<tr>"
        f"<td>{html.escape(camera)}</td>"
        f"<td>{html.escape(str(row.get('best_holdout_mae_recovery_pct_median')))}</td>"
        f"<td>{html.escape(str(row.get('best_holdout_rmse_recovery_pct_median')))}</td>"
        f"<td>{html.escape(str(row.get('passes_threshold')))}</td>"
        f"<td><code>{html.escape(str(row.get('best_path')))}</code></td>"
        "</tr>"
        for camera, row in sorted(data["current_model_state"]["best_by_camera"].items())
    )
    forbidden = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_model_contract"]["forbidden_runtime_inputs"])
    do_not_repeat = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_model_contract"]["do_not_repeat_as_primary_path"])
    gates = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_model_contract"]["success_gates"])
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in data["current_model_state"]["blockers"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Next Experiment Contract</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #121820; background: #f6f8fa; }}
main {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; letter-spacing: 0; }}
h2 {{ margin-top: 26px; }}
.sub {{ color: #5f6b76; max-width: 880px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #5f6b76; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
.warn {{ color: #9a4b00; font-weight: 700; }}
.ok {{ color: #0c6b3d; font-weight: 700; }}
</style></head><body><main>
<h1>Premium Still-SR Next Experiment Contract</h1>
<p class="sub">This locks the next premium still-SR pass to the current raw-CFA target evidence and records what must not be repeated as the primary path.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value {'ok' if data['production_ready'] else 'warn'}">{str(data['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Start next model pass</div><div class="value">{str(data['should_start_next_model_pass']).lower()}</div></section>
  <section class="card"><div class="label">Promotable candidates</div><div class="value">{data['current_model_state']['scoreboard_promotable_candidate_count']}</div></section>
  <section class="card"><div class="label">Target rows</div><div class="value">{data['target_lock'].get('row_count')}</div></section>
</div>
<h2>Canonical Targets</h2>
<table><tr><th>id</th><th>status</th><th>path</th><th>missing</th></tr>{targets}</table>
<h2>Current Camera Blockers</h2>
<table><tr><th>camera</th><th>best MAE recovery</th><th>best RMSE recovery</th><th>passes</th><th>receipt</th></tr>{cameras}</table>
<ul>{blockers}</ul>
<h2>Forbidden Runtime Inputs</h2>
<ul>{forbidden}</ul>
<h2>Do Not Repeat As Primary Path</h2>
<ul>{do_not_repeat}</ul>
<h2>Promotion Gates</h2>
<ul>{gates}</ul>
<p>JSON: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--inventory", type=Path, default=None)
    ap.add_argument("--scoreboard", type=Path, default=None)
    ap.add_argument("--residual-gap", type=Path, default=None)
    ap.add_argument("--requirements", type=Path, default=ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json")
    ap.add_argument("--output-dir", type=Path, required=True)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    inventory_path = args.inventory or args.external_root / "artifacts/cnn_dataset_inventory_20260630/cnn_dataset_inventory.json"
    scoreboard_path = args.scoreboard or args.external_root / "artifacts/premium_still_sr_experiment_scoreboard_20260630/scoreboard.json"
    residual_gap_path = args.residual_gap or args.external_root / "artifacts/premium_still_sr_raw_cfa_residual_gap_20260630/raw_cfa_residual_gap.json"
    data = build_contract(
        inventory=load_json(inventory_path),
        scoreboard=load_json(scoreboard_path),
        residual_gap=load_json(residual_gap_path),
        requirements=load_json(args.requirements),
        external_root=args.external_root,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "premium_still_sr_next_experiment_contract.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
