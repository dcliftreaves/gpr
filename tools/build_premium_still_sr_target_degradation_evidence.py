#!/usr/bin/env python3
"""Build the Premium still-SR target/degradation blocker receipt.

This receipt turns the latest paired smoke failures into a deterministic next
action. It intentionally does not train. Its purpose is to prevent another
long Premium still/SR run from starting from a rejected target/objective family.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_target_degradation_evidence.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_ACCEPTANCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_rawcfa_candidate_hf_noop_smoke_gate_acceptance_20260702"
    / "smoke_gate_acceptance.json"
)
DEFAULT_X2D = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_rawcfa_candidate_hf_noop_x2d_scene_smoke_20260702"
    / "train_receipt.json"
)
DEFAULT_Z8 = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_rawcfa_candidate_hf_noop_z8_scene_smoke_20260702"
    / "train_receipt.json"
)
DEFAULT_FRAMECTX_X2D = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_rawcfa_framectx_noop_x2d_scene_smoke_20260702"
    / "train_receipt.json"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def stat(data: dict[str, Any], metric: str, key: str = "median") -> float | None:
    value = nested(data, ["eval", "holdout", metric, key])
    if isinstance(value, (int, float)):
        return float(value)
    return None


def infer_camera(data: dict[str, Any], fallback: str) -> str:
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    camera = config.get("holdout_camera")
    if camera:
        return str(camera).upper()
    scene = str(config.get("holdout_scene") or "").lower()
    if "x2d" in scene or "austin" in scene:
        return "X2D"
    if "z8" in scene:
        return "Z8"
    return fallback


def summarize_receipt(path: Path, label: str, fallback_camera: str) -> dict[str, Any]:
    data = load_json(path)
    holdout = data.get("eval", {}).get("holdout", {})
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    return {
        "label": label,
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "camera": infer_camera(data, fallback_camera),
        "holdout_scene": config.get("holdout_scene"),
        "feature_mode": config.get("feature_mode"),
        "model_arch": config.get("model_arch"),
        "runtime_safe": policy.get("uses_source_raw_at_runtime") is False,
        "runtime_inputs": policy.get("runtime_inputs"),
        "row_count": holdout.get("row_count"),
        "median_raw_mae_recovery_pct": stat(data, "raw_residual_mae_reduction_pct", "median"),
        "worst_raw_mae_recovery_pct": stat(data, "raw_residual_mae_reduction_pct", "min"),
        "best_raw_mae_recovery_pct": stat(data, "raw_residual_mae_reduction_pct", "max"),
        "median_raw_rmse_recovery_pct": stat(data, "raw_residual_rmse_reduction_pct", "median"),
        "worst_raw_rmse_recovery_pct": stat(data, "raw_residual_rmse_reduction_pct", "min"),
        "candidate_hf_noop_gate_median": stat(data, "candidate_hf_noop_gate", "median"),
        "candidate_hf_noop_gate_min": stat(data, "candidate_hf_noop_gate", "min"),
        "candidate_hf_noop_gate_max": stat(data, "candidate_hf_noop_gate", "max"),
        "candidate_hf_noop_row_count": holdout.get("candidate_hf_noop_row_count"),
        "candidate_hf_noop_threshold": holdout.get("candidate_hf_noop_threshold"),
        "candidate_hf_noop_softness": holdout.get("candidate_hf_noop_softness"),
    }


def pass_smoke(row: dict[str, Any], median_floor: float) -> bool:
    median = row.get("median_raw_mae_recovery_pct")
    worst = row.get("worst_raw_mae_recovery_pct")
    return isinstance(median, (int, float)) and isinstance(worst, (int, float)) and median > median_floor and worst >= 0.0


def build_evidence(
    acceptance_path: Path,
    x2d_path: Path,
    z8_path: Path,
    framectx_x2d_path: Path | None,
    median_floor: float,
) -> dict[str, Any]:
    acceptance = load_json(acceptance_path)
    x2d = summarize_receipt(x2d_path, "candidate_hf_noop_x2d", "X2D")
    z8 = summarize_receipt(z8_path, "candidate_hf_noop_z8", "Z8")
    framectx = summarize_receipt(framectx_x2d_path, "framectx_candidate_hf_noop_x2d", "X2D") if framectx_x2d_path else None

    branch_rows = [x2d, z8] + ([framectx] if framectx else [])
    x2d_pass = pass_smoke(x2d, median_floor)
    z8_pass = pass_smoke(z8, median_floor)
    framectx_median = framectx.get("median_raw_mae_recovery_pct") if framectx else None

    ruled_out = [
        {
            "cause": "candidate_hf_noop_threshold_tuning",
            "decision": "ruled_out",
            "evidence": (
                "Z8 low-HF rows are clipped to exact parity, but median benefit is still 0.0%; "
                "X2D remains negative even when candidate-HF gate is fully open."
            ),
        },
        {
            "cause": "simple_frame_context_conditioning",
            "decision": "ruled_out" if isinstance(framectx_median, (int, float)) and framectx_median <= x2d["median_raw_mae_recovery_pct"] else "not_proven",
            "evidence": (
                f"Frame-context X2D median raw MAE recovery is {framectx_median}% versus "
                f"{x2d['median_raw_mae_recovery_pct']}% for the candidate-HF no-op X2D smoke."
            )
            if framectx
            else "No frame-context diagnostic receipt supplied.",
        },
        {
            "cause": "generic_raw_cfa_residual_long_run",
            "decision": "ruled_out",
            "evidence": (
                "The paired smoke gate fails before promotion: both X2D and Z8 must have positive "
                "median recovery and nonnegative worst-row recovery before a long run is allowed."
            ),
        },
    ]

    blockers: list[str] = []
    if not x2d_pass:
        blockers.append(
            "X2D candidate-HF no-op smoke does not clear positive median and nonnegative worst-row recovery."
        )
    if not z8_pass:
        blockers.append(
            "Z8 candidate-HF no-op smoke is safe but zero-benefit; it does not clear the positive median floor."
        )
    if acceptance.get("smoke_gate_passed") is not True:
        blockers.append("The paired smoke-gate acceptance receipt is failed, so long training is forbidden.")

    long_run_allowed = not blockers
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": "target_degradation_evidence_required_before_next_long_run",
        "production_ready": False,
        "long_run_allowed": long_run_allowed,
        "blocker_classification": (
            "target_degradation_or_route_conditioning_mismatch"
            if not long_run_allowed
            else "paired_smoke_passed_ready_for_long_run"
        ),
        "acceptance": {
            "path": str(acceptance_path),
            "sha256": sha256_file(acceptance_path),
            "schema": acceptance.get("schema"),
            "smoke_gate_passed": bool(acceptance.get("smoke_gate_passed")),
            "production_ready": bool(acceptance.get("production_ready")),
            "long_run_allowed": bool(acceptance.get("long_run_allowed")),
            "verdict": acceptance.get("verdict"),
        },
        "thresholds": {
            "paired_smoke_median_raw_mae_recovery_pct_min_exclusive": median_floor,
            "paired_smoke_worst_raw_mae_recovery_pct_min": 0.0,
            "promotion_median_mae_recovery_pct_min": 15.0,
            "promotion_median_rmse_recovery_pct_min": 15.0,
        },
        "rows": branch_rows,
        "blockers": blockers,
        "ruled_out": ruled_out,
        "next_steps": [
            {
                "order": 1,
                "step": "Build a new target/degradation source receipt.",
                "done_when": (
                    "The receipt shows why the current raw-CFA residual target is mismatched to "
                    "candidate-only runtime inputs, or supplies a replacement objective with measurable "
                    "positive X2D and Z8 source signal."
                ),
            },
            {
                "order": 2,
                "step": "Preflight a materially different route-conditioning candidate.",
                "done_when": (
                    "The candidate changes supervision/source policy beyond candidate-HF threshold tuning "
                    "or simple frame-context planes and still uses no REF/source/JPEG content at render time."
                ),
            },
            {
                "order": 3,
                "step": "Run paired X2D and Z8 smoke gates before any long run.",
                "done_when": (
                    "Both cameras exceed the positive median floor, have nonnegative worst-row recovery, "
                    "and pass tools/check_premium_still_sr_smoke_gate_acceptance.py --require-pass."
                ),
            },
            {
                "order": 4,
                "step": "Only then launch the 50 MP / 100 MP Premium still-SR promotion run.",
                "done_when": (
                    "The production submission has checkpoint hashes, timing/memory, editor/openability, "
                    "exact-sidecar-only noise policy, and the 15% / 15% held-out promotion floor."
                ),
            },
        ],
    }


def fmt_pct(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.6g}%"
    return "n/a"


def render_html(data: dict[str, Any], json_path: Path) -> str:
    row_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['label']))}</td>"
        f"<td>{html.escape(str(row.get('camera')))}</td>"
        f"<td>{html.escape(str(row.get('holdout_scene')))}</td>"
        f"<td>{fmt_pct(row.get('median_raw_mae_recovery_pct'))}</td>"
        f"<td>{fmt_pct(row.get('worst_raw_mae_recovery_pct'))}</td>"
        f"<td>{fmt_pct(row.get('median_raw_rmse_recovery_pct'))}</td>"
        f"<td>{html.escape(str(row.get('candidate_hf_noop_row_count')))}</td>"
        f"<td><code>{html.escape(str(row.get('path')))}</code></td>"
        "</tr>"
        for row in data["rows"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    ruled = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['cause'])}</td>"
        f"<td>{html.escape(item['decision'])}</td>"
        f"<td>{html.escape(item['evidence'])}</td>"
        "</tr>"
        for item in data["ruled_out"]
    )
    next_steps = "\n".join(
        "<tr>"
        f"<td>{item['order']}</td>"
        f"<td>{html.escape(item['step'])}</td>"
        f"<td>{html.escape(item['done_when'])}</td>"
        "</tr>"
        for item in data["next_steps"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Premium Still-SR Target/Degradation Evidence</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 28px; color: #17202a; }}
    h1 {{ margin-bottom: 4px; }}
    .verdict {{ display: inline-block; padding: 6px 10px; border-radius: 6px; background: #fff2cc; border: 1px solid #d6b656; }}
    table {{ width: 100%; border-collapse: collapse; margin: 18px 0 28px; }}
    th, td {{ border: 1px solid #d7dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f6f8; }}
    code {{ font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Premium Still-SR Target/Degradation Evidence</h1>
  <p class="verdict">Verdict: {html.escape(data['verdict'])}</p>
  <p>Production ready: <strong>{data['production_ready']}</strong>. Long run allowed:
  <strong>{data['long_run_allowed']}</strong>. Blocker class:
  <strong>{html.escape(data['blocker_classification'])}</strong>.</p>
  <p>JSON receipt: <code>{html.escape(str(json_path))}</code></p>

  <h2>Blockers</h2>
  <ul>{blockers}</ul>

  <h2>Smoke Evidence</h2>
  <table>
    <tr><th>Receipt</th><th>Camera</th><th>Scene</th><th>Median MAE recovery</th><th>Worst MAE recovery</th><th>Median RMSE recovery</th><th>No-op rows</th><th>Path</th></tr>
    {row_html}
  </table>

  <h2>Ruled Out</h2>
  <table>
    <tr><th>Cause</th><th>Decision</th><th>Evidence</th></tr>
    {ruled}
  </table>

  <h2>Next Required Steps</h2>
  <table>
    <tr><th>Order</th><th>Step</th><th>Done when</th></tr>
    {next_steps}
  </table>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--x2d-receipt", type=Path, default=DEFAULT_X2D)
    parser.add_argument("--z8-receipt", type=Path, default=DEFAULT_Z8)
    parser.add_argument("--framectx-x2d-receipt", type=Path, default=DEFAULT_FRAMECTX_X2D)
    parser.add_argument("--median-floor", type=float, default=0.001)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    framectx = args.framectx_x2d_receipt if args.framectx_x2d_receipt and args.framectx_x2d_receipt.exists() else None
    data = build_evidence(args.acceptance, args.x2d_receipt, args.z8_receipt, framectx, args.median_floor)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "target_degradation_evidence.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
