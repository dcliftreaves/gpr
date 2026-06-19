#!/usr/bin/env python3
"""Build a Mission 1 native12 8K SR production gap report.

The report is intentionally conservative. It records the best current q4/t2
sidecar-aware 8K SR candidate as an offline registry-review candidate, then
keeps the production blockers explicit: live/camera timing, paired hard-row
regression, metadata refresh, and the still-open native12 strict-24 capture
receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "mission1_sr_production_gap_report.v1"
ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_sidecar_aware_s400_v1+"
    "demosaic=sips_via_gpr_tools"
)
CNN_ID = "mission1_native12_8k_sr_q4t2_sidecar_aware_s400_v1"
STRICT24_REL = "current_goal_mission1_strict24_gap_report_20260619/summary.json"


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def artifact_path(artifact_root: Path, ref: str | None) -> Path | None:
    if not ref:
        return None
    text = str(ref)
    if text.startswith("artifacts/"):
        return artifact_root / text[len("artifacts/"):]
    path = Path(text)
    return path if path.is_absolute() else ROOT / path


def registry_artifact_receipt(
    artifact_root: Path,
    row: dict[str, Any],
    path_key: str,
    sha_key: str,
) -> dict[str, Any]:
    ref = row.get(path_key)
    expected = row.get(sha_key)
    path = artifact_path(artifact_root, str(ref) if ref else None)
    receipt: dict[str, Any] = {
        "ref": ref,
        "path": str(path) if path else None,
        "expected_sha256": expected,
        "exists": bool(path and path.exists()),
    }
    if path and path.exists():
        actual = sha256_file(path)
        receipt.update({
            "actual_sha256": actual,
            "sha256_ok": bool(expected and actual == expected),
            "bytes": path.stat().st_size,
        })
    else:
        receipt["sha256_ok"] = False
    return receipt


def stat(summary: dict[str, Any], key: str, field: str) -> float | None:
    value = summary.get(key)
    if not isinstance(value, dict):
        return None
    return safe_float(value.get(field))


def holdout_summary(path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "image_count": summary.get("image_count"),
        "dashboard": summary.get("dashboard"),
        "fps_with_write_median": stat(summary, "fps_with_write", "median"),
        "rmse_improvement_min": stat(summary, "rmse_improvement_pct", "min"),
        "rmse_improvement_median": stat(summary, "rmse_improvement_pct", "median"),
        "mae_improvement_min": stat(summary, "mae_improvement_pct", "min"),
        "gradient_improvement_min": stat(summary, "gradient_mae_improvement_pct", "min"),
        "psnr14_min_db": stat(summary, "model_psnr14_db", "min"),
        "worst_rmse_image": (summary.get("worst_by_rmse_improvement") or {}).get("image"),
        "worst_gradient_image": (
            (summary.get("worst_by_gradient_improvement") or {}).get("image")
            or (summary.get("worst_by_gradient_mae_improvement") or {}).get("image")
        ),
    }


def negative_deltas(values: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in values.items():
        number = safe_float(value)
        if number is not None and number < 0.0:
            out[str(key)] = number
    return dict(sorted(out.items(), key=lambda item: item[1]))


def packaging_summary(packaging: dict[str, Any]) -> dict[str, Any]:
    sr_raw = packaging.get("sr_raw") if isinstance(packaging.get("sr_raw"), dict) else {}
    dng = packaging.get("editable_dng") if isinstance(packaging.get("editable_dng"), dict) else {}
    gpr = packaging.get("editable_gpr") if isinstance(packaging.get("editable_gpr"), dict) else {}
    gpr_metrics = gpr.get("readback_metrics") if isinstance(gpr.get("readback_metrics"), dict) else {}
    prores = packaging.get("prores_review") if isinstance(packaging.get("prores_review"), dict) else {}
    prores_fps = packaging.get("prores_fps_review") if isinstance(packaging.get("prores_fps_review"), dict) else {}
    prores_streams = ((prores.get("ffprobe") or {}).get("streams") or [])
    prores_fps_streams = ((prores_fps.get("ffprobe") or {}).get("streams") or [])
    prores_stream = prores_streams[0] if prores_streams else {}
    prores_fps_stream = prores_fps_streams[0] if prores_fps_streams else {}
    return {
        "schema": packaging.get("schema"),
        "sr_raw_width": sr_raw.get("width"),
        "sr_raw_height": sr_raw.get("height"),
        "editable_dng_roundtrip_byte_identical": dng.get("raw_roundtrip_byte_identical"),
        "editable_dng_shape": dng.get("rawpy_open_shape"),
        "editable_gpr_quality": gpr.get("quality"),
        "editable_gpr_psnr14_db": safe_float(gpr_metrics.get("psnr14_db")),
        "gpr_to_dng_shape": gpr.get("gpr_to_dng_rawpy_open_shape"),
        "prores_codec": prores_stream.get("codec_name"),
        "prores_two_frame_avg_frame_rate": prores_fps_stream.get("avg_frame_rate"),
        "prores_two_frame_time_base": prores_fps_stream.get("time_base"),
        "prores_two_frame_duration_ts": prores_fps_stream.get("duration_ts"),
    }


def build_report(external_root: Path, registry_path: Path) -> dict[str, Any]:
    artifact_root = external_root / "artifacts"
    registry = read_json(registry_path)
    pipelines = registry.get("pipelines") if isinstance(registry.get("pipelines"), dict) else {}
    cnns = registry.get("cnns") if isinstance(registry.get("cnns"), dict) else {}
    pipeline = pipelines.get(PIPELINE_ID) if isinstance(pipelines.get(PIPELINE_ID), dict) else {}
    cnn = cnns.get(CNN_ID) if isinstance(cnns.get(CNN_ID), dict) else {}

    decision_path = artifact_path(artifact_root, cnn.get("promotion_review_decision"))
    mission_path = artifact_path(artifact_root, cnn.get("mission_broad_holdout_receipt"))
    z8_path = artifact_path(artifact_root, cnn.get("z8_regenerated_holdout_receipt"))
    multiframe_path = artifact_path(artifact_root, cnn.get("gvid_decode_sr_multiframe_receipt"))
    packaging_path = artifact_path(artifact_root, cnn.get("gvid_decode_sr_packaging_receipt"))
    interp_path = artifact_root / "current_goal_sr_q4t2_sidecar_aware_interp_probe_20260619" / "interpolation_decision_summary.json"
    strict24_path = artifact_root / STRICT24_REL

    decision = read_json(decision_path) if decision_path and decision_path.exists() else {}
    mission = read_json(mission_path) if mission_path and mission_path.exists() else {}
    z8 = read_json(z8_path) if z8_path and z8_path.exists() else {}
    multiframe = read_json(multiframe_path) if multiframe_path and multiframe_path.exists() else {}
    packaging = read_json(packaging_path) if packaging_path and packaging_path.exists() else {}
    interp = read_json(interp_path) if interp_path.exists() else {}
    strict24 = read_json(strict24_path) if strict24_path.exists() else {}

    comparison = decision.get("comparison_scope") if isinstance(decision.get("comparison_scope"), dict) else {}
    mission_comparison = comparison.get("mission") if isinstance(comparison.get("mission"), dict) else {}
    z8_comparison = comparison.get("z8") if isinstance(comparison.get("z8"), dict) else {}
    mission_rmse_regressions = negative_deltas(mission_comparison.get("per_image_rmse_delta") or {})
    mission_psnr_regressions = negative_deltas(mission_comparison.get("per_image_psnr14_delta") or {})
    z8_rmse_regressions = negative_deltas(z8_comparison.get("per_image_rmse_delta") or {})
    z8_psnr_regressions = negative_deltas(z8_comparison.get("per_image_psnr14_delta") or {})

    multiframe_summary = multiframe.get("summary") if isinstance(multiframe.get("summary"), dict) else {}
    decode_sr = multiframe_summary.get("decode_plus_sr_total_s") if isinstance(multiframe_summary.get("decode_plus_sr_total_s"), dict) else {}
    fps = safe_float(multiframe_summary.get("fps_median_decode_plus_sr"))
    packaging_row = packaging_summary(packaging)
    metadata_note = (
        ((cnn.get("gvid_decode_sr_packaging_summary") or {}).get("mission_metadata_transplant"))
        if isinstance(cnn.get("gvid_decode_sr_packaging_summary"), dict)
        else None
    )

    quality_evidence_ok = bool(
        decision.get("decision") == "promote_for_registry_review"
        and mission_comparison.get("coverage_ok") is True
        and z8_comparison.get("coverage_ok") is True
        and not z8_rmse_regressions
        and not z8_psnr_regressions
    )
    packaging_ok = bool(
        packaging_row.get("schema") == "mission1_native12_gvid_to_8k_sr_packaging.v2"
        and packaging_row.get("sr_raw_width") == 8192
        and packaging_row.get("sr_raw_height") == 6144
        and packaging_row.get("editable_dng_roundtrip_byte_identical") is True
        and tuple(packaging_row.get("editable_dng_shape") or []) == (6144, 8192)
        and tuple(packaging_row.get("gpr_to_dng_shape") or []) == (6144, 8192)
        and safe_float(packaging_row.get("editable_gpr_psnr14_db")) is not None
        and float(packaging_row["editable_gpr_psnr14_db"]) >= 50.0
        and packaging_row.get("prores_codec") == "prores"
        and packaging_row.get("prores_two_frame_avg_frame_rate") == "24/1"
    )
    live_timing_ok = bool(fps is not None and fps >= 20.0)
    strict24_capture_ok = strict24.get("decision") == "strict24_candidate_present"
    production_ready = bool(
        quality_evidence_ok
        and packaging_ok
        and live_timing_ok
        and strict24_capture_ok
        and not mission_rmse_regressions
        and not mission_psnr_regressions
        and pipeline.get("production_scope") != "offline_review_only"
    )

    blockers: list[dict[str, Any]] = []
    if pipeline.get("production_scope") == "offline_review_only":
        blockers.append({
            "name": "offline_scope",
            "evidence": "registry production_scope is offline_review_only",
        })
    if fps is None or fps < 20.0:
        blockers.append({
            "name": "live_timing",
            "evidence": f"decode+SR+write fps={fps}; live/camera target is at least 20 fps proxy and 24 fps final",
        })
    if mission_rmse_regressions or mission_psnr_regressions:
        blockers.append({
            "name": "mission_paired_regression",
            "evidence": {
                "rmse": mission_rmse_regressions,
                "psnr14": mission_psnr_regressions,
            },
        })
    if metadata_note and "not refreshed" in str(metadata_note):
        blockers.append({
            "name": "mission_metadata_refresh",
            "evidence": metadata_note,
        })
    if not strict24_capture_ok:
        blockers.append({
            "name": "native12_capture_strict24",
            "evidence": strict24.get("decision"),
        })
    if interp.get("decision") == "reject_interpolations_keep_step400_as_review_candidate":
        blockers.append({
            "name": "checkpoint_interpolation_rejected",
            "evidence": interp.get("decision_reason"),
        })

    return {
        "schema": SCHEMA,
        "artifact_root": str(artifact_root),
        "pipeline_id": PIPELINE_ID,
        "cnn_id": CNN_ID,
        "production_ready": production_ready,
        "production_status": (
            "production_ready"
            if production_ready
            else "offline_registry_review_not_production"
        ),
        "registry": {
            "pipeline_scope": pipeline.get("production_scope"),
            "pipeline_use_for": pipeline.get("use_for"),
            "pipeline_doc": pipeline.get("$doc"),
            "cnn_status": cnn.get("status"),
            "runtime_entrypoint": cnn.get("runtime_entrypoint"),
        },
        "candidate_artifacts": {
            "checkpoint": registry_artifact_receipt(artifact_root, cnn, "ckpt_path", "ckpt_sha256"),
            "training_pairs": registry_artifact_receipt(
                artifact_root, cnn, "training_pairs_path", "training_pairs_sha256"
            ),
            "training_receipt": registry_artifact_receipt(
                artifact_root, cnn, "training_receipt", "training_receipt_sha256"
            ),
            "promotion_decision": registry_artifact_receipt(
                artifact_root, cnn, "promotion_review_decision", "promotion_review_decision_sha256"
            ),
            "multiframe_receipt": registry_artifact_receipt(
                artifact_root, cnn, "gvid_decode_sr_multiframe_receipt", "gvid_decode_sr_multiframe_receipt_sha256"
            ),
            "packaging_receipt": registry_artifact_receipt(
                artifact_root, cnn, "gvid_decode_sr_packaging_receipt", "gvid_decode_sr_packaging_receipt_sha256"
            ),
        },
        "quality": {
            "decision": decision.get("decision"),
            "decision_reason": decision.get("reason"),
            "quality_evidence_ok_for_registry_review": quality_evidence_ok,
            "mission": holdout_summary(mission_path, mission) if mission_path and mission else {},
            "z8": holdout_summary(z8_path, z8) if z8_path and z8 else {},
            "deltas_vs_q4t2_preclean_step0200": decision.get("deltas_vs_q4t2_preclean_step0200"),
            "mission_paired_rmse_regressions": mission_rmse_regressions,
            "mission_paired_psnr14_regressions": mission_psnr_regressions,
            "z8_paired_rmse_regressions": z8_rmse_regressions,
            "z8_paired_psnr14_regressions": z8_psnr_regressions,
            "interpolation_decision": interp.get("decision"),
        },
        "runtime": {
            "frames_rendered": multiframe.get("frames_rendered"),
            "input_gvid": multiframe.get("gvid"),
            "input_gvid_sha256": multiframe.get("gvid_sha256"),
            "payload_size": (((multiframe.get("frames") or [{}])[0]).get("payload_size") if multiframe.get("frames") else None),
            "decode_plus_sr_fps_median": fps,
            "decode_plus_sr_median_s": safe_float(decode_sr.get("median")),
            "sr_total_with_write_median_s": safe_float((multiframe_summary.get("sr_total_with_write_s") or {}).get("median")),
            "max_rss_mb": safe_float(multiframe.get("max_rss_mb")),
            "live_timing_ok": live_timing_ok,
            "output_bayer": multiframe.get("output_bayer"),
        },
        "packaging": {
            **packaging_row,
            "packaging_ok": packaging_ok,
            "mission_metadata_transplant": metadata_note,
        },
        "native12_capture_dependency": {
            "strict24_report": str(strict24_path),
            "decision": strict24.get("decision"),
            "required_loop_reduction_ms": strict24.get("required_loop_reduction_ms"),
            "required_wall_reduction_ms": strict24.get("required_wall_reduction_ms"),
            "strict24_capture_ok": strict24_capture_ok,
        },
        "blockers": blockers,
        "next_steps": [
            "Keep this q4/t2 checkpoint as offline review evidence, not a live/camera path.",
            "Fix or route around the GP017346 paired regression before promoting beyond registry review.",
            "Refresh Mission metadata transplant receipts if this checkpoint becomes an output-suite default.",
            "Do not revisit linear checkpoint interpolation unless the objective changes; current interpolation probe rejected it.",
            "Treat native12 strict-24 capture as a separate release blocker until target hardware or policy closes it.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-root",
        type=Path,
        default=Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root())),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "pipelines" / "registry.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    output = args.output
    if output is None:
        output = (
            args.external_root
            / "artifacts"
            / "current_goal_sr_production_gap_report_20260619"
            / "summary.json"
        )
    report = build_report(args.external_root, args.registry)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "production_status": report["production_status"],
        "blockers": [row["name"] for row in report["blockers"]],
        "decode_plus_sr_fps_median": report["runtime"]["decode_plus_sr_fps_median"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
