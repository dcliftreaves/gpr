#!/usr/bin/env python3
"""Build the raw-video PSF/SR production-readiness audit.

This audit separates two things that are easy to conflate:

* the approved 4K cleanup and 8K SR baselines, which have useful production
  receipts for offline review/reconstruction, and
* the unfinished PSF-aware replacement work, which still needs native
  camera/display PSF evidence and a PSF-conditioned model gate.
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
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
SCHEMA = "gpr.raw_video_psf_audit.v1"


DEFAULT_PSF_RECEIPT = (
    "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/"
    "bayer_resize_psf_receipt.json"
)
DEFAULT_4K_SIGNOFF = "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
DEFAULT_8K_PROMOTION = "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"
DEFAULT_SR_SCOREBOARD = "artifacts/raw_video_sr_candidate_scoreboard_20260630/scoreboard.json"
DEFAULT_NATIVE_PAIR_INVENTORY = "artifacts/mission1_native_psf_pair_inventory_20260630/inventory.json"
DEFAULT_NATIVE_PSF_MEASUREMENT_PLAN = "artifacts/mission1_native_psf_measurement_plan_20260630/measurement_plan.json"
DEFAULT_NATIVE_PSF_MEASUREMENT = "artifacts/mission1_native_psf_measurement_20260630/native_psf_measurement.json"
DEFAULT_Z8_CONTINUOUS_REVIEW = "artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/receipt.json"
DEFAULT_MISSION_CONTINUOUS_REVIEW = (
    "artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/receipt.json"
)


def resolve_artifact(external_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return external_root / candidate


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def bool_at(data: dict[str, Any] | None, keys: list[str], default: bool = False) -> bool:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return bool(cur)


def num_at(data: dict[str, Any] | None, keys: list[str]) -> float | None:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def list_at(data: dict[str, Any] | None, keys: list[str]) -> list[Any]:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return []
        cur = cur[key]
    return list(cur) if isinstance(cur, list) else []


def artifact_entry(label: str, path: Path, data: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "schema": data.get("schema") if isinstance(data, dict) else None,
    }


def output_path_exists(output: dict[str, Any], require_exists: bool) -> bool:
    path = output.get("path")
    if not isinstance(path, str) or not path:
        return False
    return Path(path).exists() if require_exists else True


def review_output_meta(review: dict[str, Any], key: str, top_level: dict[str, Any]) -> dict[str, Any]:
    output = review.get("outputs", {}).get(key, {})
    if not isinstance(output, dict):
        output = {}
    ffprobe = output.get("ffprobe")
    if not isinstance(ffprobe, dict):
        ffprobe = {}
    return {
        "path": output.get("path"),
        "bytes": output.get("bytes"),
        "sha256": output.get("sha256"),
        "width": int(ffprobe.get("width") or top_level.get("width") or 0),
        "height": int(ffprobe.get("height") or top_level.get("height") or 0),
        "fps": str(ffprobe.get("avg_frame_rate") or ffprobe.get("r_frame_rate") or top_level.get("fps") or ""),
        "frames": int(ffprobe.get("nb_frames") or top_level.get("frames") or 0),
    }


def summarize_continuous_review(
    label: str,
    path: Path,
    review: dict[str, Any] | None,
    *,
    minimum_frames: int,
    require_exists: bool,
) -> dict[str, Any]:
    if not isinstance(review, dict):
        return {
            "label": label,
            "path": str(path),
            "exists": path.exists(),
            "ready": False,
            "reason": "missing receipt",
        }

    top_level = {
        "width": review.get("width") or review.get("scene", {}).get("width"),
        "height": review.get("height") or review.get("scene", {}).get("height"),
        "fps": review.get("fps") or review.get("scene", {}).get("fps"),
        "frames": len(review.get("frames", [])) if isinstance(review.get("frames"), list) else review.get("scene", {}).get("frame_count"),
    }
    baseline = review_output_meta(review, "true_no_cnn", top_level)
    candidate = review_output_meta(review, "with_cnn", top_level)
    baseline_exists = output_path_exists(review.get("outputs", {}).get("true_no_cnn", {}), require_exists)
    candidate_exists = output_path_exists(review.get("outputs", {}).get("with_cnn", {}), require_exists)
    same_shape = (
        baseline["width"] > 0
        and baseline["height"] > 0
        and baseline["width"] == candidate["width"]
        and baseline["height"] == candidate["height"]
    )
    same_rate = bool(baseline["fps"]) and baseline["fps"] == candidate["fps"]
    same_frames = baseline["frames"] >= minimum_frames and baseline["frames"] == candidate["frames"]
    note = f"{review.get('note', '')} {review.get('purpose', '')}".lower()
    explicitly_not_dashboard = "not a dashboard" in note or "not a dashboard" in str(review.get("purpose", "")).lower()
    sequential_scene = (
        isinstance(review.get("frames"), list)
        and len(review["frames"]) >= minimum_frames
    ) or (
        isinstance(review.get("scene", {}).get("source_frame_stems"), list)
        and len(review["scene"]["source_frame_stems"]) >= minimum_frames
    )
    ready = all(
        [
            baseline_exists,
            candidate_exists,
            same_shape,
            same_rate,
            same_frames,
            explicitly_not_dashboard,
            sequential_scene,
        ]
    )
    reasons = []
    if not baseline_exists:
        reasons.append("missing no-CNN standalone movie")
    if not candidate_exists:
        reasons.append("missing CNN standalone movie")
    if not same_shape:
        reasons.append("movie dimensions differ or are missing")
    if not same_rate:
        reasons.append("movie frame rates differ or are missing")
    if not same_frames:
        reasons.append(f"need matching frame counts >= {minimum_frames}")
    if not explicitly_not_dashboard:
        reasons.append("receipt does not explicitly reject dashboard/side-by-side review")
    if not sequential_scene:
        reasons.append("receipt does not describe a sequential scene frame list")
    return {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "schema": review.get("schema"),
        "ready": ready,
        "reason": "; ".join(reasons) if reasons else "ok",
        "minimum_frames": minimum_frames,
        "true_no_cnn": baseline,
        "with_cnn": candidate,
    }


def synthetic_inputs() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    psf = {
        "schema": "gpr.bayer_resize_psf_receipt.v1",
        "production_ready": False,
        "dataset": {
            "pair_count": 16,
            "sharp_edge_count": 8,
            "texture_field_count": 8,
            "cfa_phases": ["RGGB"],
        },
        "psf_model": {
            "model_id": "synthetic_same_color_box2",
            "best_candidate_kernel": "same_color_box2",
            "normalized_weights": [0.25, 0.25, 0.25, 0.25],
            "rmse_14bit": 0.3,
        },
        "detail_budget": {
            "fine_share_of_residual_abs": 0.999,
            "mid_share_of_residual_abs": 0.003,
            "coarse_share_of_residual_abs": 0.002,
            "residual_to_target_cell_detail_ratio": 1.0,
        },
        "gate_results": {
            "mission42_passed": False,
            "z8_all24_passed": False,
        },
    }
    cleanup = {
        "schema": "gpr.mission1_4k_cleanup_production_signoff.v1",
        "verdict": {"production_ready": True, "accepted_role": "production"},
    }
    sr = {
        "schema": "gpr.mission1_8k_sr_production_promotion.v1",
        "verdict": {"production_ready": True, "accepted_role": "production"},
    }
    native_pairs = {
        "schema": "gpr.mission1_native_psf_pair_inventory.v1",
        "summary": {
            "candidate_pair_count": 3,
            "decoded_candidate_pair_count": 3,
            "native_psf_ready": False,
            "production_ready": False,
        },
    }
    native_plan = {
        "schema": "gpr.mission1_native_psf_measurement_plan.v1",
        "production_ready": False,
        "native_psf_measured": False,
        "measurement_plan_ready": True,
        "summary": {
            "selected_pair_count": 3,
            "pair_derived_best_kernel": "same_color_box2",
        },
    }
    native_measurement = {
        "schema": "gpr.mission1_native_psf_measurement.v1",
        "production_ready": False,
        "measurement_executed": True,
        "native_psf_ready_for_model_conditioning": False,
        "summary": {
            "selected_pair_count": 3,
            "accepted_pair_count": 2,
            "rejected_pair_count": 1,
            "accepted_sharp_edge_tile_count": 120,
            "accepted_texture_field_tile_count": 140,
            "kernel_stable": False,
            "measured_native_psf_ready": False,
        },
    }
    z8_review = {
        "schema": "gpr.z8_continuous_8k_no_cnn_vs_cnn_scene_video.v1",
        "note": "Two standalone continuous 8K-ish Z8 scene videos, not a dashboard or side-by-side.",
        "frames": [f"Z8Z_{1330 + i}" for i in range(24)],
        "fps": 20,
        "width": 8280,
        "height": 5520,
        "outputs": {
            "true_no_cnn": {"path": "/synthetic/z8_no_cnn.mov", "bytes": 1, "sha256": "synthetic"},
            "with_cnn": {"path": "/synthetic/z8_with_cnn.mov", "bytes": 1, "sha256": "synthetic"},
        },
    }
    mission_review = {
        "schema": "gpr.mission1_8k_scene_no_cnn_vs_cnn_review.v1",
        "purpose": "Standalone continuous-scene 8K ProRes A/B. This is not a dashboard, crop sheet, contact sheet, or side-by-side review video.",
        "scene": {
            "source_frame_stems": [f"GP017{497 + i}" for i in range(12)],
            "frame_count": 12,
            "fps": 20,
            "width": 8192,
            "height": 6144,
        },
        "outputs": {
            "true_no_cnn": {"path": "/synthetic/mission_no_cnn.mov", "bytes": 1, "sha256": "synthetic"},
            "with_cnn": {"path": "/synthetic/mission_with_cnn.mov", "bytes": 1, "sha256": "synthetic"},
        },
    }
    return psf, cleanup, sr, native_pairs, native_plan, native_measurement, z8_review, mission_review


def build_audit(
    external_root: Path,
    psf_receipt_path: Path,
    cleanup_signoff_path: Path,
    sr_promotion_path: Path,
    sr_scoreboard_path: Path,
    native_pair_inventory_path: Path,
    native_psf_measurement_plan_path: Path,
    native_psf_measurement_path: Path,
    z8_continuous_review_path: Path,
    mission_continuous_review_path: Path,
    synthetic: bool = False,
) -> dict[str, Any]:
    if synthetic:
        (
            psf_receipt,
            cleanup_signoff,
            sr_promotion,
            native_pair_inventory,
            native_psf_measurement_plan,
            native_psf_measurement,
            z8_continuous_review,
            mission_continuous_review,
        ) = synthetic_inputs()
        sr_scoreboard = {
            "schema": "gpr.raw_video_sr_candidate_scoreboard.v1",
            "decision_count": 3,
            "promotable_row_count": 0,
            "production_ready": False,
        }
    else:
        psf_receipt = load_json(psf_receipt_path)
        cleanup_signoff = load_json(cleanup_signoff_path)
        sr_promotion = load_json(sr_promotion_path)
        sr_scoreboard = load_json(sr_scoreboard_path)
        native_pair_inventory = load_json(native_pair_inventory_path)
        native_psf_measurement_plan = load_json(native_psf_measurement_plan_path)
        native_psf_measurement = load_json(native_psf_measurement_path)
        z8_continuous_review = load_json(z8_continuous_review_path)
        mission_continuous_review = load_json(mission_continuous_review_path)

    cleanup_ready = bool_at(cleanup_signoff, ["verdict", "production_ready"])
    sr_ready = bool_at(sr_promotion, ["verdict", "production_ready"])
    psf_receipt_ready = bool_at(psf_receipt, ["production_ready"])
    mission42_psf_gate = bool_at(psf_receipt, ["gate_results", "mission42_passed"])
    z8_psf_gate = bool_at(psf_receipt, ["gate_results", "z8_all24_passed"])

    native_psf_ready = bool_at(native_psf_measurement, ["native_psf_ready_for_model_conditioning"])
    psf_conditioned_model_ready = False
    psf_replacement_ready = (
        native_psf_ready
        and psf_conditioned_model_ready
        and psf_receipt_ready
        and mission42_psf_gate
        and z8_psf_gate
    )

    pair_count = int(num_at(psf_receipt, ["dataset", "pair_count"]) or 0)
    sharp_edge_count = int(num_at(psf_receipt, ["dataset", "sharp_edge_count"]) or 0)
    texture_field_count = int(num_at(psf_receipt, ["dataset", "texture_field_count"]) or 0)
    fine_share = num_at(psf_receipt, ["detail_budget", "fine_share_of_residual_abs"])
    mid_share = num_at(psf_receipt, ["detail_budget", "mid_share_of_residual_abs"])
    coarse_share = num_at(psf_receipt, ["detail_budget", "coarse_share_of_residual_abs"])
    detail_ratio = num_at(psf_receipt, ["detail_budget", "residual_to_target_cell_detail_ratio"])
    sr_decision_count = int(num_at(sr_scoreboard, ["decision_count"]) or 0)
    sr_promotable_rows = int(num_at(sr_scoreboard, ["promotable_row_count"]) or 0)
    native_candidate_pairs = int(num_at(native_pair_inventory, ["summary", "candidate_pair_count"]) or 0)
    decoded_native_candidate_pairs = int(num_at(native_pair_inventory, ["summary", "decoded_candidate_pair_count"]) or 0)
    native_pair_inventory_ready = native_candidate_pairs > 0 and decoded_native_candidate_pairs > 0
    native_measurement_plan_ready = bool_at(native_psf_measurement_plan, ["measurement_plan_ready"])
    native_measurement_selected_pairs = int(num_at(native_psf_measurement_plan, ["summary", "selected_pair_count"]) or 0)
    native_measurement_executed = bool_at(native_psf_measurement, ["measurement_executed"])
    native_measurement_accepted_pairs = int(num_at(native_psf_measurement, ["summary", "accepted_pair_count"]) or 0)
    native_measurement_rejected_pairs = int(num_at(native_psf_measurement, ["summary", "rejected_pair_count"]) or 0)
    native_measurement_kernel_stable = bool_at(native_psf_measurement, ["summary", "kernel_stable"])
    z8_review = summarize_continuous_review(
        "Z8 continuous 8K no-CNN vs CNN review",
        z8_continuous_review_path,
        z8_continuous_review,
        minimum_frames=24,
        require_exists=not synthetic,
    )
    mission_review = summarize_continuous_review(
        "Mission 1 continuous 8K no-CNN vs CNN review",
        mission_continuous_review_path,
        mission_continuous_review,
        minimum_frames=12,
        require_exists=not synthetic,
    )
    continuous_reviews_ready = z8_review["ready"] and mission_review["ready"]

    checks = [
        {
            "id": "approved_4k_cleanup_baseline",
            "passed": cleanup_ready,
            "production_meaning": "Current Mission 1 4K cleanup baseline is available for offline/review use.",
        },
        {
            "id": "approved_8k_sr_baseline",
            "passed": sr_ready,
            "production_meaning": "Current candidate-aware 8K SR baseline has packaging and review receipts.",
        },
        {
            "id": "standalone_continuous_8k_review_media",
            "passed": continuous_reviews_ready,
            "production_meaning": "Review evidence must be two separate normal full-frame movies, no-CNN and with-CNN, not a dashboard, crop montage, or side-by-side-only video.",
        },
        {
            "id": "pair_derived_psf_detail_budget",
            "passed": pair_count >= 1000 and fine_share is not None,
            "production_meaning": "Modeled high-to-low real-fixture pair analysis is broad enough to guide the next PSF experiment.",
        },
        {
            "id": "native_capture_display_psf",
            "passed": native_psf_ready,
            "production_meaning": "Requires real native high-res/low-res or display/capture PSF measurements; not satisfied by modeled pairs.",
        },
        {
            "id": "native_high_low_pair_inventory",
            "passed": native_pair_inventory_ready,
            "production_meaning": "Near-time native Mission 1 high/low captures are indexed as candidate inputs, but still need alignment and PSF measurement.",
        },
        {
            "id": "native_psf_measurement_plan",
            "passed": native_measurement_plan_ready,
            "production_meaning": "The native pair inventory has been converted into a concrete alignment, edge/texture mining, and measured-kernel protocol.",
        },
        {
            "id": "native_psf_measurement_executed",
            "passed": native_measurement_executed,
            "production_meaning": "The native high/low pairs have been aligned, vetted, mined, and fit; current result can still reject the available pairs.",
        },
        {
            "id": "psf_conditioned_model_gate",
            "passed": psf_conditioned_model_ready,
            "production_meaning": "Requires a PSF-conditioned model beating the approved 4K/8K baselines on raw and rendered gates.",
        },
        {
            "id": "sr_detail_decision_scoreboard",
            "passed": sr_decision_count > 0 and sr_promotable_rows == 0,
            "production_meaning": "Historical SR/detail decisions are indexed; none currently satisfy the current-scale promotion row.",
        },
    ]

    blockers = [
        "No production-ready native camera/sensor/DMA/display PSF receipt is present.",
        f"Standalone continuous 8K review media ready is {str(continuous_reviews_ready).lower()}; Mission 1 reason: {mission_review['reason']}; Z8 reason: {z8_review['reason']}.",
        f"The native high/low inventory has {native_candidate_pairs} candidate pairs and {decoded_native_candidate_pairs} decoded raw candidates.",
        f"The native PSF measurement plan selects {native_measurement_selected_pairs} pairs for alignment, tile mining, and measured-kernel fitting.",
        f"The native PSF measurement accepted {native_measurement_accepted_pairs} pairs and rejected {native_measurement_rejected_pairs}; kernel stable is {str(native_measurement_kernel_stable).lower()}, so it is not ready for model conditioning.",
        "No PSF-conditioned replacement model has beaten both current Mission42 and Z8 baselines.",
        f"The SR/detail candidate scoreboard indexes {sr_decision_count} decision receipts and finds {sr_promotable_rows} current-scale promotion rows.",
        "The existing pair-derived receipt is non-production by design; it proves the modeled target, not the native camera path.",
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "synthetic" if synthetic else "real",
        "external_root": str(external_root),
        "readiness_percent": 44 if native_measurement_executed else (43 if native_measurement_plan_ready else (42 if native_pair_inventory_ready else 40)),
        "production_ready": False,
        "approved_baselines_ready": cleanup_ready and sr_ready,
        "psf_replacement_ready": psf_replacement_ready,
        "summary": {
            "cleanup_4k_ready": cleanup_ready,
            "sr_8k_ready": sr_ready,
            "standalone_continuous_8k_review_media_ready": continuous_reviews_ready,
            "psf_receipt_ready": psf_receipt_ready,
            "mission42_psf_gate_passed": mission42_psf_gate,
            "z8_all24_psf_gate_passed": z8_psf_gate,
            "native_psf_ready": native_psf_ready,
            "native_high_low_candidate_pair_count": native_candidate_pairs,
            "native_high_low_decoded_candidate_pair_count": decoded_native_candidate_pairs,
            "native_psf_measurement_plan_ready": native_measurement_plan_ready,
            "native_psf_measurement_selected_pair_count": native_measurement_selected_pairs,
            "native_psf_measurement_executed": native_measurement_executed,
            "native_psf_measurement_accepted_pair_count": native_measurement_accepted_pairs,
            "native_psf_measurement_rejected_pair_count": native_measurement_rejected_pairs,
            "native_psf_measurement_kernel_stable": native_measurement_kernel_stable,
            "psf_conditioned_model_ready": psf_conditioned_model_ready,
            "sr_detail_decision_count": sr_decision_count,
            "sr_detail_promotable_row_count": sr_promotable_rows,
        },
        "pair_derived_psf": {
            "pair_count": pair_count,
            "sharp_edge_count": sharp_edge_count,
            "texture_field_count": texture_field_count,
            "cfa_phases": list_at(psf_receipt, ["dataset", "cfa_phases"]),
            "best_kernel": (psf_receipt or {}).get("psf_model", {}).get("best_candidate_kernel"),
            "normalized_weights": list_at(psf_receipt, ["psf_model", "normalized_weights"]),
            "rmse_14bit": num_at(psf_receipt, ["psf_model", "rmse_14bit"]),
            "fine_share_of_residual_abs": fine_share,
            "mid_share_of_residual_abs": mid_share,
            "coarse_share_of_residual_abs": coarse_share,
            "residual_to_target_cell_detail_ratio": detail_ratio,
        },
        "continuous_8k_review_media": {
            "z8": z8_review,
            "mission1": mission_review,
        },
        "checks": checks,
        "blockers": blockers,
        "next_actions": [
            "Capture or synthesize a native camera-source PSF fixture: high-res reference, native 4K/12MP Bayer source, sharp edges, and texture fields.",
            "Capture or locate controlled same-scene Mission 1 high/low pairs because the current near-time pair measurement does not meet the accepted-pair/kernel-stability gate.",
            "Re-run the native PSF measurement on controlled pairs until scene vetting, tile support, and kernel stability pass.",
            "Train a PSF-conditioned 4K cleanup or 8K SR candidate against CFA-aware high-res targets and explicit fine-detail losses.",
            "Gate the candidate against current Mission42 and Z8 baselines in raw domain and rendered review, including worst-row visual inspection.",
            "Promote only with .gvid, editable DNG/GPR, ProRes, timing, memory, checkpoint, config, and hash receipts.",
        ],
        "artifacts": [
            artifact_entry("pair-derived PSF/detail receipt", psf_receipt_path, psf_receipt),
            artifact_entry("Mission 1 4K cleanup signoff", cleanup_signoff_path, cleanup_signoff),
            artifact_entry("Mission 1 8K SR promotion", sr_promotion_path, sr_promotion),
            artifact_entry("raw-video SR/detail candidate scoreboard", sr_scoreboard_path, sr_scoreboard),
            artifact_entry("Z8 standalone continuous 8K review receipt", z8_continuous_review_path, z8_continuous_review),
            artifact_entry("Mission 1 standalone continuous 8K review receipt", mission_continuous_review_path, mission_continuous_review),
            artifact_entry("Mission 1 native high/low pair inventory", native_pair_inventory_path, native_pair_inventory),
            artifact_entry("Mission 1 native PSF measurement plan", native_psf_measurement_plan_path, native_psf_measurement_plan),
            artifact_entry("Mission 1 native PSF measurement", native_psf_measurement_path, native_psf_measurement),
        ],
    }


def pct(value: float | None) -> str:
    if value is None:
        return "missing"
    return f"{value:.5g}"


def render_html(data: dict[str, Any], out_json: Path) -> str:
    checks = "\n".join(
        f"""<tr><td>{html.escape(check["id"])}</td><td class="{'pass' if check['passed'] else 'fail'}">{str(check['passed']).lower()}</td><td>{html.escape(check['production_meaning'])}</td></tr>"""
        for check in data["checks"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    next_actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    artifacts = "\n".join(
        f"""<tr><td>{html.escape(a["label"])}</td><td class="{'pass' if a['exists'] else 'fail'}">{str(a['exists']).lower()}</td><td>{html.escape(str(a.get("schema") or "missing"))}</td><td><a href="file://{html.escape(a["path"])}">{html.escape(a["path"])}</a></td></tr>"""
        for a in data["artifacts"]
    )
    psf = data["pair_derived_psf"]
    reviews = data["continuous_8k_review_media"]
    weights = ", ".join(f"{float(w):.8f}" for w in psf.get("normalized_weights") or [])
    phases = ", ".join(str(p) for p in psf.get("cfa_phases") or [])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GPR Raw Video PSF Audit</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f3f6f8; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 22px; }}
    p {{ color: #52606d; max-width: 850px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d8e0e6; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e4e9ed; text-align: left; vertical-align: top; }}
    th {{ color: #52606d; font-size: 12px; text-transform: uppercase; }}
    a {{ color: #075c9f; }}
    .hero {{ padding-bottom: 22px; }}
    .score {{ display: flex; align-items: end; gap: 18px; margin-top: 16px; }}
    .num {{ font-size: 58px; font-weight: 780; }}
    .label {{ color: #52606d; padding-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 18px 0; }}
    .card {{ background: white; border: 1px solid #d8e0e6; border-radius: 8px; padding: 15px; }}
    .k {{ color: #52606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .v {{ font-size: 26px; font-weight: 740; margin-top: 6px; overflow-wrap: anywhere; }}
    .section {{ margin-top: 18px; background: white; border: 1px solid #d8e0e6; border-radius: 8px; padding: 18px; }}
    .section table {{ border: 0; }}
    .pass {{ color: #16794c; font-weight: 760; }}
    .fail {{ color: #a33a32; font-weight: 760; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>Raw Video PSF / SR Audit</h1>
    <p>Approved 4K cleanup and 8K SR baselines are separated from unfinished native PSF-aware replacement work. This prevents the current useful SR path from being mistaken for a completed PSF model.</p>
    <div class="score"><div class="num">{data["readiness_percent"]}%</div><div class="label">PSF-aware video-improvement readiness; production ready: {str(data["production_ready"]).lower()}</div></div>
  </section>
  <div class="grid">
    <div class="card"><div class="k">4K cleanup baseline</div><div class="v">{str(data["summary"]["cleanup_4k_ready"]).lower()}</div></div>
    <div class="card"><div class="k">8K SR baseline</div><div class="v">{str(data["summary"]["sr_8k_ready"]).lower()}</div></div>
    <div class="card"><div class="k">Standalone 8K A/B</div><div class="v">{str(data["summary"]["standalone_continuous_8k_review_media_ready"]).lower()}</div></div>
    <div class="card"><div class="k">PSF replacement</div><div class="v">{str(data["psf_replacement_ready"]).lower()}</div></div>
    <div class="card"><div class="k">Native candidates</div><div class="v">{data["summary"]["native_high_low_candidate_pair_count"]}</div></div>
    <div class="card"><div class="k">Measurement plan</div><div class="v">{str(data["summary"]["native_psf_measurement_plan_ready"]).lower()}</div></div>
    <div class="card"><div class="k">Measurement run</div><div class="v">{str(data["summary"]["native_psf_measurement_executed"]).lower()}</div></div>
    <div class="card"><div class="k">Pair fixtures</div><div class="v">{psf["pair_count"]}</div></div>
    <div class="card"><div class="k">Best modeled kernel</div><div class="v">{html.escape(str(psf.get("best_kernel") or "missing"))}</div></div>
    <div class="card"><div class="k">Fine residual share</div><div class="v">{html.escape(pct(psf.get("fine_share_of_residual_abs")))}</div></div>
  </div>
  <section class="section">
    <h2>Standalone Continuous 8K Review Media</h2>
    <table>
      <tr><th>set</th><th>ready</th><th>frames</th><th>shape</th><th>reason</th><th>receipt</th></tr>
      <tr><td>Z8</td><td class="{'pass' if reviews['z8']['ready'] else 'fail'}">{str(reviews['z8']['ready']).lower()}</td><td>{reviews['z8']['true_no_cnn']['frames']}</td><td>{reviews['z8']['true_no_cnn']['width']} x {reviews['z8']['true_no_cnn']['height']}</td><td>{html.escape(reviews['z8']['reason'])}</td><td>{html.escape(reviews['z8']['path'])}</td></tr>
      <tr><td>Mission 1</td><td class="{'pass' if reviews['mission1']['ready'] else 'fail'}">{str(reviews['mission1']['ready']).lower()}</td><td>{reviews['mission1']['true_no_cnn']['frames']}</td><td>{reviews['mission1']['true_no_cnn']['width']} x {reviews['mission1']['true_no_cnn']['height']}</td><td>{html.escape(reviews['mission1']['reason'])}</td><td>{html.escape(reviews['mission1']['path'])}</td></tr>
    </table>
  </section>
  <section class="section">
    <h2>Pair-Derived PSF Detail Budget</h2>
    <table>
      <tr><th>metric</th><th>value</th></tr>
      <tr><td>CFA phases</td><td>{html.escape(phases or "missing")}</td></tr>
      <tr><td>sharp-edge fixtures</td><td>{psf["sharp_edge_count"]}</td></tr>
      <tr><td>texture-field fixtures</td><td>{psf["texture_field_count"]}</td></tr>
      <tr><td>normalized weights</td><td>{html.escape(weights or "missing")}</td></tr>
      <tr><td>RMSE, 14-bit scale</td><td>{html.escape(pct(psf.get("rmse_14bit")))}</td></tr>
      <tr><td>mid residual share</td><td>{html.escape(pct(psf.get("mid_share_of_residual_abs")))}</td></tr>
      <tr><td>coarse residual share</td><td>{html.escape(pct(psf.get("coarse_share_of_residual_abs")))}</td></tr>
      <tr><td>residual / target same-cell detail</td><td>{html.escape(pct(psf.get("residual_to_target_cell_detail_ratio")))}</td></tr>
    </table>
  </section>
  <section class="section">
    <h2>Production Checks</h2>
    <table><tr><th>check</th><th>passed</th><th>meaning</th></tr>{checks}</table>
  </section>
  <section class="section">
    <h2>Blockers</h2>
    <ul>{blockers}</ul>
  </section>
  <section class="section">
    <h2>Next Actions</h2>
    <ul>{next_actions}</ul>
  </section>
  <section class="section">
    <h2>Artifacts</h2>
    <table><tr><th>artifact</th><th>exists</th><th>schema</th><th>path</th></tr>{artifacts}</table>
  </section>
  <p class="meta">Generated {html.escape(data["created_utc"])}. JSON: {html.escape(str(out_json))}. Mode: {html.escape(data["mode"])}.</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--output-dir", type=Path, default=None)
    ap.add_argument("--psf-receipt", default=DEFAULT_PSF_RECEIPT)
    ap.add_argument("--cleanup-signoff", default=DEFAULT_4K_SIGNOFF)
    ap.add_argument("--sr-promotion", default=DEFAULT_8K_PROMOTION)
    ap.add_argument("--sr-scoreboard", default=DEFAULT_SR_SCOREBOARD)
    ap.add_argument("--native-pair-inventory", default=DEFAULT_NATIVE_PAIR_INVENTORY)
    ap.add_argument("--native-psf-measurement-plan", default=DEFAULT_NATIVE_PSF_MEASUREMENT_PLAN)
    ap.add_argument("--native-psf-measurement", default=DEFAULT_NATIVE_PSF_MEASUREMENT)
    ap.add_argument("--z8-continuous-review", default=DEFAULT_Z8_CONTINUOUS_REVIEW)
    ap.add_argument("--mission-continuous-review", default=DEFAULT_MISSION_CONTINUOUS_REVIEW)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d", time.gmtime())
        output_dir = args.external_root / "artifacts" / f"raw_video_psf_audit_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    psf_receipt_path = resolve_artifact(args.external_root, args.psf_receipt)
    cleanup_signoff_path = resolve_artifact(args.external_root, args.cleanup_signoff)
    sr_promotion_path = resolve_artifact(args.external_root, args.sr_promotion)
    sr_scoreboard_path = resolve_artifact(args.external_root, args.sr_scoreboard)
    native_pair_inventory_path = resolve_artifact(args.external_root, args.native_pair_inventory)
    native_psf_measurement_plan_path = resolve_artifact(args.external_root, args.native_psf_measurement_plan)
    native_psf_measurement_path = resolve_artifact(args.external_root, args.native_psf_measurement)
    z8_continuous_review_path = resolve_artifact(args.external_root, args.z8_continuous_review)
    mission_continuous_review_path = resolve_artifact(args.external_root, args.mission_continuous_review)
    data = build_audit(
        args.external_root,
        psf_receipt_path,
        cleanup_signoff_path,
        sr_promotion_path,
        sr_scoreboard_path,
        native_pair_inventory_path,
        native_psf_measurement_plan_path,
        native_psf_measurement_path,
        z8_continuous_review_path,
        mission_continuous_review_path,
        synthetic=args.synthetic,
    )

    out_json = output_dir / "raw_video_psf_audit.json"
    out_html = output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
