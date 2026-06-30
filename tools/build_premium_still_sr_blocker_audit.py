#!/usr/bin/env python3
"""Build a root-cause audit for the premium still-SR blocker.

The readiness report says the current premium still-SR path is blocked. This
tool makes that blocker actionable by combining the experiment scoreboard,
merged high-frequency target receipt, residual band analysis, and readiness
receipt into a compact next-experiment decision record.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_blocker_audit.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")

DEFAULT_SCOREBOARD = "artifacts/premium_still_sr_experiment_scoreboard_20260630/scoreboard.json"
DEFAULT_READINESS = "artifacts/premium_still_sr_readiness_20260630/readiness.json"
DEFAULT_MERGED_TARGET = "artifacts/premium_still_sr_expanded_hf_targets_20260630/merged/merge_receipt.json"
DEFAULT_BAND_ANALYSIS = "artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/band_analysis.json"

PROMOTION_RECOVERY_PCT = 15.0
MIN_PRODUCTION_SCENES = 6
MIN_PRODUCTION_TARGET_ROWS = 256


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve(root: Path, path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def nested(data: dict[str, Any] | None, keys: list[str]) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def as_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def bool_from_nested(data: dict[str, Any] | None, keys: list[str]) -> bool | None:
    value = nested(data, keys)
    return bool(value) if isinstance(value, bool) else None


def source_ref(path: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.exists(),
        "loaded": payload is not None,
        "schema": payload.get("schema") if isinstance(payload, dict) else None,
    }


def pct_gap(best: float | None, target: float) -> float | None:
    if best is None:
        return None
    return max(0.0, target - best)


def build_axis(
    axis_id: str,
    title: str,
    status: str,
    severity: str,
    evidence: list[str],
    next_action: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": axis_id,
        "title": title,
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "next_action": next_action,
        "metrics": metrics,
    }


def classify_blockers(
    scoreboard: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
    merged_target: dict[str, Any] | None,
    band_analysis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    best = nested(scoreboard, ["best_candidate"]) if isinstance(scoreboard, dict) else None
    best_mae = as_float(nested(best, ["holdout_residual_mae_reduction_pct_median"]) if isinstance(best, dict) else None)
    best_rmse = as_float(nested(best, ["holdout_residual_rmse_reduction_pct_median"]) if isinstance(best, dict) else None)
    promotable = as_int(nested(scoreboard, ["promotable_candidate_count"])) or 0
    runtime_uses_ref = bool_from_nested(best if isinstance(best, dict) else None, ["uses_source_hf_at_runtime"])
    broader_mae = as_float(nested(readiness, ["evidence_summary", "latest_no_ref_hf_holdout_mae_reduction_pct_median"]))
    broader_rmse = as_float(nested(readiness, ["evidence_summary", "latest_no_ref_hf_holdout_rmse_reduction_pct_median"]))

    row_count = as_int(nested(merged_target, ["summary", "row_count"]))
    scene_count = as_int(nested(merged_target, ["summary", "scene_count"]))
    residual_abs_median = as_float(nested(merged_target, ["summary", "residual_abs_mean", "median"]))
    hf_corr_median = as_float(nested(merged_target, ["summary", "hf_y_correlation", "median"]))

    fine_share = as_float(nested(band_analysis, ["summary", "bands", "fine", "share_of_residual_abs", "median"]))
    mid_share = as_float(nested(band_analysis, ["summary", "bands", "mid", "share_of_residual_abs", "median"]))
    grad_corr = as_float(nested(band_analysis, ["summary", "residual_corr_with_candidate_gradient", "median"]))
    fine_corr = as_float(nested(band_analysis, ["summary", "bands", "fine", "corr_with_target_band", "median"]))
    shadow_residual = as_float(nested(band_analysis, ["summary", "brightness", "shadow", "residual_abs_mean", "median"]))
    highlight_residual = as_float(nested(band_analysis, ["summary", "brightness", "highlight", "residual_abs_mean", "median"]))

    has_gate = bool(nested(readiness, ["evidence_summary", "has_raw_editor_latitude_receipt"]))
    has_noise_sidecars = bool(nested(readiness, ["evidence_summary", "has_validated_x2d_z8_noise_sidecars"]))
    target_coverage_ready = (
        row_count is not None
        and scene_count is not None
        and row_count >= MIN_PRODUCTION_TARGET_ROWS
        and scene_count >= MIN_PRODUCTION_SCENES
    )

    return [
        build_axis(
            "promotion_metric_gap",
            "No candidate clears the no-REF recovery threshold",
            "blocked",
            "high",
            [
                f"promotable rows: {promotable}",
                f"best single-candidate holdout MAE/RMSE recovery: {best_mae}% / {best_rmse}%",
                f"broader scene-held-out no-REF recovery: {broader_mae}% / {broader_rmse}%",
            ],
            "Do not promote another checkpoint until a no-REF holdout row reaches the recovery threshold and then passes full-frame/editor-latitude gates.",
            {
                "promotion_recovery_pct": PROMOTION_RECOVERY_PCT,
                "best_holdout_mae_recovery_pct": best_mae,
                "best_holdout_rmse_recovery_pct": best_rmse,
                "broader_scene_holdout_mae_recovery_pct": broader_mae,
                "broader_scene_holdout_rmse_recovery_pct": broader_rmse,
                "mae_gap_to_threshold_pct": pct_gap(best_mae, PROMOTION_RECOVERY_PCT),
                "rmse_gap_to_threshold_pct": pct_gap(best_rmse, PROMOTION_RECOVERY_PCT),
                "promotable_candidate_count": promotable,
                "best_runtime_uses_ref_content": runtime_uses_ref,
            },
        ),
        build_axis(
            "target_coverage_gap",
            "The supervised HF target set must be broad enough for a 50MP/100MP still product",
            "resolved" if target_coverage_ready else "blocked",
            "low" if target_coverage_ready else "high",
            [
                f"merged target rows: {row_count}",
                f"merged target scenes: {scene_count}",
                f"median target residual magnitude: {residual_abs_median}",
            ],
            (
                "Target coverage is now broad enough for the next training pass; keep it fixed while testing whether the runtime model can learn the fine-band residual."
                if target_coverage_ready
                else "Build a larger target set with more scenes, ISO levels, crops, and both X2D/Z8 classes before using scene-held-out recovery as production evidence."
            ),
            {
                "target_rows": row_count,
                "target_scenes": scene_count,
                "minimum_production_rows": MIN_PRODUCTION_TARGET_ROWS,
                "minimum_production_scenes": MIN_PRODUCTION_SCENES,
                "target_coverage_ready": target_coverage_ready,
                "residual_abs_mean_median": residual_abs_median,
                "hf_y_correlation_median": hf_corr_median,
            },
        ),
        build_axis(
            "runtime_feature_gap",
            "The residual is mostly fine-band texture with weak runtime cue correlation",
            "blocked",
            "high",
            [
                f"fine-band residual share: {fine_share}",
                f"median residual correlation with candidate gradient: {grad_corr}",
                f"fine-band target correlation: {fine_corr}",
            ],
            "Change the runtime input/target design: use larger raw-domain context, CFA-aware coordinates, camera/ISO noise calibration, and explicit texture-placement losses instead of only local rendered features.",
            {
                "fine_band_share_of_residual_abs_median": fine_share,
                "mid_band_share_of_residual_abs_median": mid_share,
                "residual_corr_with_candidate_gradient_median": grad_corr,
                "fine_band_corr_with_target_band_median": fine_corr,
            },
        ),
        build_axis(
            "noise_policy_gap",
            "Noise calibration exists but is not yet a proven remove/addback production policy",
            "open",
            "medium",
            [
                f"validated X2D/Z8 sidecars available: {has_noise_sidecars}",
                f"shadow residual median: {shadow_residual}",
                f"highlight residual median: {highlight_residual}",
            ],
            "Use darkframe sidecars to clean only measured sensor noise from targets, train signal residual separately, then add back either original or simulated noise only after a noise/signal audit passes.",
            {
                "has_validated_x2d_z8_noise_sidecars": has_noise_sidecars,
                "shadow_residual_abs_mean_median": shadow_residual,
                "highlight_residual_abs_mean_median": highlight_residual,
            },
        ),
        build_axis(
            "promotion_gate_gap",
            "There is still no full still/editor-latitude promotion receipt",
            "blocked",
            "high",
            [
                f"raw editor latitude receipt exists: {has_gate}",
                "readiness report keeps production_ready=false",
            ],
            "When a better candidate exists, run the full 50MP/100MP still gate: raw PSNR, rendered LPIPS/dE/MS-SSIM, 100% crops, editor openability, and latitude stress rows.",
            {
                "has_raw_editor_latitude_receipt": has_gate,
                "readiness_production_ready": bool(nested(readiness, ["production_ready"])),
            },
        ),
    ]


def recommended_experiment(axes: list[dict[str, Any]]) -> dict[str, Any]:
    target_axis = next((axis for axis in axes if axis["id"] == "target_coverage_gap"), None)
    target_ready = bool(nested(target_axis, ["metrics", "target_coverage_ready"])) if isinstance(target_axis, dict) else False
    target_instruction = (
        "Keep the expanded target coverage fixed while changing the runtime model; the current target set already clears the row/scene floor."
        if target_ready
        else "Increase target coverage before interpreting holdout recovery as production evidence."
    )
    return {
        "name": "larger_context_raw_domain_noise_conditioned_texture_model",
        "purpose": "Replace the weak rendered-space no-REF HF residual probe with a production-relevant still-SR candidate.",
        "must_change": [
            target_instruction,
            "Predict in raw/CFA-aware space with larger context instead of relying only on local rendered features.",
            "Clean targets with measured camera/ISO noise sidecars and audit that removed content is noise, not signal.",
            "Optimize against fine texture placement and raw/editor-latitude behavior, not only aggregate residual MAE.",
        ],
        "minimum_acceptance": {
            "no_ref_runtime": True,
            "holdout_recovery_mae_pct": PROMOTION_RECOVERY_PCT,
            "holdout_recovery_rmse_pct": PROMOTION_RECOVERY_PCT,
            "minimum_target_rows": MIN_PRODUCTION_TARGET_ROWS,
            "minimum_target_scenes": MIN_PRODUCTION_SCENES,
            "full_still_editor_latitude_gate": True,
        },
        "blocked_axes": [axis["id"] for axis in axes if axis["status"] == "blocked"],
    }


def build_audit(
    external_root: Path,
    scoreboard_path: Path,
    readiness_path: Path,
    merged_target_path: Path,
    band_analysis_path: Path,
) -> dict[str, Any]:
    scoreboard = load_json(scoreboard_path)
    readiness = load_json(readiness_path)
    merged_target = load_json(merged_target_path)
    band_analysis = load_json(band_analysis_path)
    axes = classify_blockers(scoreboard, readiness, merged_target, band_analysis)
    blocked_count = sum(1 for axis in axes if axis["status"] == "blocked")
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "production_ready": False,
        "current_verdict": "blocked_on_runtime_generalized_premium_still_texture_model",
        "summary": {
            "blocker_axis_count": len(axes),
            "blocked_axis_count": blocked_count,
            "promotable_candidate_count": as_int(nested(scoreboard, ["promotable_candidate_count"])) or 0,
            "best_holdout_mae_recovery_pct": as_float(nested(scoreboard, ["best_candidate", "holdout_residual_mae_reduction_pct_median"])),
            "best_holdout_rmse_recovery_pct": as_float(nested(scoreboard, ["best_candidate", "holdout_residual_rmse_reduction_pct_median"])),
            "broader_scene_holdout_mae_recovery_pct": as_float(nested(readiness, ["evidence_summary", "latest_no_ref_hf_holdout_mae_reduction_pct_median"])),
            "target_scene_count": as_int(nested(merged_target, ["summary", "scene_count"])),
            "target_row_count": as_int(nested(merged_target, ["summary", "row_count"])),
            "fine_band_residual_share_median": as_float(nested(band_analysis, ["summary", "bands", "fine", "share_of_residual_abs", "median"])),
            "candidate_gradient_correlation_median": as_float(nested(band_analysis, ["summary", "residual_corr_with_candidate_gradient", "median"])),
        },
        "sources": {
            "scoreboard": source_ref(scoreboard_path, scoreboard),
            "readiness": source_ref(readiness_path, readiness),
            "merged_target": source_ref(merged_target_path, merged_target),
            "band_analysis": source_ref(band_analysis_path, band_analysis),
        },
        "axes": axes,
        "recommended_next_experiment": recommended_experiment(axes),
    }


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return ""
    return str(value)


def render_html(audit: dict[str, Any]) -> str:
    axis_rows = []
    for axis in audit["axes"]:
        evidence = "".join(f"<li>{html.escape(item)}</li>" for item in axis["evidence"])
        metrics = "".join(
            f"<tr><td>{html.escape(key)}</td><td>{html.escape(fmt(value))}</td></tr>"
            for key, value in axis["metrics"].items()
        )
        axis_rows.append(
            f"""<section class="axis {html.escape(axis['severity'])}">
  <div class="axis-head">
    <div><h2>{html.escape(axis['title'])}</h2><p>{html.escape(axis['id'])} / {html.escape(axis['status'])}</p></div>
    <strong>{html.escape(axis['severity'])}</strong>
  </div>
  <h3>Evidence</h3>
  <ul>{evidence}</ul>
  <h3>Metrics</h3>
  <table>{metrics}</table>
  <h3>Next action</h3>
  <p>{html.escape(axis['next_action'])}</p>
</section>"""
        )
    summary_cards = "".join(
        f"<div class='card'><span>{html.escape(key)}</span><strong>{html.escape(fmt(value))}</strong></div>"
        for key, value in audit["summary"].items()
    )
    rec = audit["recommended_next_experiment"]
    must_change = "".join(f"<li>{html.escape(item)}</li>" for item in rec["must_change"])
    acceptance = "".join(
        f"<tr><td>{html.escape(key)}</td><td>{html.escape(fmt(value))}</td></tr>"
        for key, value in rec["minimum_acceptance"].items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Blocker Audit</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #12171c; background: #f5f7f8; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0 0 6px; font-size: 36px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 20px; }}
    h3 {{ margin: 14px 0 6px; font-size: 12px; text-transform: uppercase; color: #5d6873; }}
    p {{ margin: 5px 0; }}
    ul {{ margin: 0; padding-left: 20px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td {{ border-bottom: 1px solid #dce2e7; padding: 6px; vertical-align: top; }}
    .hero {{ margin-bottom: 18px; }}
    .verdict {{ display: inline-block; background: #fff3cd; border: 1px solid #d2a106; border-radius: 7px; padding: 6px 10px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; margin: 18px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 12px; }}
    .card span {{ display: block; color: #5d6873; font-size: 12px; }}
    .card strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    .axis {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; margin: 14px 0; }}
    .axis.high {{ border-left: 5px solid #a33a32; }}
    .axis.medium {{ border-left: 5px solid #b87900; }}
    .axis-head {{ display: flex; justify-content: space-between; gap: 20px; align-items: start; }}
    .rec {{ background: #ffffff; border: 1px solid #c8d5df; border-radius: 8px; padding: 18px; margin-top: 18px; }}
    code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>Premium Still-SR Blocker Audit</h1>
    <p class="verdict">{html.escape(audit['current_verdict'])}</p>
    <p>This dashboard turns the current no-REF still-SR failure into explicit next-experiment requirements.</p>
  </section>
  <section class="cards">{summary_cards}</section>
  {''.join(axis_rows)}
  <section class="rec">
    <h2>Recommended next experiment: <code>{html.escape(rec['name'])}</code></h2>
    <p>{html.escape(rec['purpose'])}</p>
    <h3>Must change</h3>
    <ul>{must_change}</ul>
    <h3>Minimum acceptance</h3>
    <table>{acceptance}</table>
  </section>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--scoreboard", type=Path, default=None)
    ap.add_argument("--readiness", type=Path, default=None)
    ap.add_argument("--merged-target", type=Path, default=None)
    ap.add_argument("--band-analysis", type=Path, default=None)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    scoreboard = args.scoreboard or resolve(args.external_root, DEFAULT_SCOREBOARD)
    readiness = args.readiness or resolve(args.external_root, DEFAULT_READINESS)
    merged_target = args.merged_target or resolve(args.external_root, DEFAULT_MERGED_TARGET)
    band_analysis = args.band_analysis or resolve(args.external_root, DEFAULT_BAND_ANALYSIS)
    audit = build_audit(args.external_root, scoreboard, readiness, merged_target, band_analysis)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.output_dir / "blocker_audit.json"
    out_html = args.output_dir / "index.html"
    out_json.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(audit), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
