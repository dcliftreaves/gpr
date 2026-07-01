#!/usr/bin/env python3
"""Build a blocked production audit for a Mission 1 8K SR review candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_8k_sr_review_candidate_audit.v1"
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_REGISTRY = Path("pipelines/registry.json")
DEFAULT_CNN_ID = "mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1"
DEFAULT_PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1"
    "+demosaic=sips_via_gpr_tools"
)
DEFAULT_VISUAL_REVIEW = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_visual_review_20260701/visual_review.json"
)
DEFAULT_VISUAL_SIGNOFF = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_visual_signoff_20260701/visual_signoff.json"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def artifact_path(external_root: Path, ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref:
        return None
    if ref.startswith("artifacts/"):
        return external_root / ref
    path = Path(ref)
    return path if path.is_absolute() else path


def artifact_check(external_root: Path, row: dict[str, Any], path_key: str, sha_key: str) -> dict[str, Any]:
    ref = row.get(path_key)
    expected = row.get(sha_key)
    path = artifact_path(external_root, ref)
    result: dict[str, Any] = {
        "path_key": path_key,
        "sha_key": sha_key,
        "ref": ref,
        "expected_sha256": expected,
        "exists": bool(path and path.exists()),
        "sha256_ok": False,
    }
    if path and path.exists():
        actual = sha256_file(path)
        result.update({
            "path": str(path),
            "actual_sha256": actual,
            "sha256_ok": actual == expected,
            "bytes": path.stat().st_size,
        })
    return result


def stat(summary: dict[str, Any], key: str, field: str) -> float | None:
    value = summary.get(key)
    if not isinstance(value, dict):
        return None
    try:
        return float(value.get(field))
    except (TypeError, ValueError):
        return None


def visual_review_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "objective_checks_pass": False}
    data = read_json(path)
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    passed = bool(checks) and all(isinstance(check, dict) and check.get("passed") is True for check in checks)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "exists": True,
        "schema": data.get("schema"),
        "verdict": data.get("verdict"),
        "objective_checks_pass": passed,
        "check_count": len(checks),
        "manual_visual_review_required": data.get("manual_visual_review_required"),
        "manual_visual_review_complete": data.get("manual_visual_review_complete"),
        "contact_sheet": data.get("contact_sheet"),
        "contact_sheet_sha256": data.get("contact_sheet_sha256"),
    }


def visual_signoff_summary(path: Path | None, visual_review_path: Path) -> dict[str, Any]:
    if path is None:
        return {"exists": False, "manual_visual_review_complete": False}
    if not path.exists():
        return {"path": str(path), "exists": False, "manual_visual_review_complete": False}
    data = read_json(path)
    visual = data.get("visual_review") if isinstance(data.get("visual_review"), dict) else {}
    signoff = data.get("signoff") if isinstance(data.get("signoff"), dict) else {}
    boundary = data.get("production_boundary") if isinstance(data.get("production_boundary"), dict) else {}
    expected_visual_sha = sha256_file(visual_review_path) if visual_review_path.exists() else None
    sha_matches = visual.get("sha256") == expected_visual_sha
    complete = bool(
        data.get("schema") == "gpr.mission1_8k_sr_visual_signoff.v1"
        and signoff.get("manual_visual_review_complete") is True
        and visual.get("objective_checks_pass") is True
        and sha_matches
        and boundary.get("controlled_native_psf_evidence_still_required") is True
    )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "exists": True,
        "schema": data.get("schema"),
        "visual_review_sha256_matches": sha_matches,
        "reviewer_role": signoff.get("reviewer_role"),
        "statement": signoff.get("statement"),
        "scope": signoff.get("scope"),
        "manual_visual_review_complete": complete,
        "controlled_native_psf_evidence_still_required": boundary.get(
            "controlled_native_psf_evidence_still_required"
        ),
    }


def sequence_packaging_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"exists": False, "sequence_packaging_ok": False}
    data = read_json(path)
    prores = data.get("prores_review") if isinstance(data.get("prores_review"), dict) else {}
    gvid = data.get("gvid_packaging") if isinstance(data.get("gvid_packaging"), dict) else {}
    streams = ((prores.get("ffprobe") or {}).get("streams") or [])
    stream = streams[0] if streams else {}
    ok = bool(
        data.get("schema") == "mission1_8k_sr_sequence_packaging.v1"
        and data.get("width") == 8192
        and data.get("height") == 6144
        and int(data.get("frame_count") or 0) >= 42
        and int(gvid.get("frame_count") or 0) >= 42
        and stream.get("codec_name") == "prores"
        and int(stream.get("width") or 0) == 8192
        and int(stream.get("height") or 0) == 6144
    )
    return {
        "exists": True,
        "schema": data.get("schema"),
        "frame_count": data.get("frame_count"),
        "width": data.get("width"),
        "height": data.get("height"),
        "gvid": gvid,
        "prores_review": {
            "path": prores.get("path"),
            "sha256": prores.get("sha256"),
            "bytes": prores.get("bytes"),
            "codec": stream.get("codec_name"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "nb_frames": stream.get("nb_frames"),
            "avg_frame_rate": stream.get("avg_frame_rate"),
        },
        "encode_elapsed_s": (data.get("summary") or {}).get("encode_elapsed_s"),
        "sequence_packaging_ok": ok,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    registry = read_json(args.registry)
    cnns = registry.get("cnns") if isinstance(registry.get("cnns"), dict) else {}
    pipelines = registry.get("pipelines") if isinstance(registry.get("pipelines"), dict) else {}
    cnn = cnns.get(args.cnn_id) if isinstance(cnns.get(args.cnn_id), dict) else {}
    pipeline = pipelines.get(args.pipeline_id) if isinstance(pipelines.get(args.pipeline_id), dict) else {}

    artifact_checks = {
        "mission_holdout": artifact_check(args.external_root, cnn, "mission_broad_holdout_receipt", "mission_broad_holdout_receipt_sha256"),
        "z8_holdout": artifact_check(args.external_root, cnn, "z8_regenerated_holdout_receipt", "z8_regenerated_holdout_receipt_sha256"),
        "frame_packaging": artifact_check(args.external_root, cnn, "gvid_decode_sr_packaging_receipt", "gvid_decode_sr_packaging_receipt_sha256"),
        "fullsequence_render": artifact_check(args.external_root, cnn, "gvid_decode_sr_fullsequence_receipt", "gvid_decode_sr_fullsequence_receipt_sha256"),
        "fullsequence_packaging": artifact_check(args.external_root, cnn, "gvid_decode_sr_fullsequence_packaging_receipt", "gvid_decode_sr_fullsequence_packaging_receipt_sha256"),
        "metadata_transplant": artifact_check(args.external_root, cnn, "mission_metadata_transplant_audit", "mission_metadata_transplant_audit_sha256"),
    }

    mission_path = artifact_path(args.external_root, cnn.get("mission_broad_holdout_receipt"))
    z8_path = artifact_path(args.external_root, cnn.get("z8_regenerated_holdout_receipt"))
    mission = read_json(mission_path) if mission_path and mission_path.exists() else {}
    z8 = read_json(z8_path) if z8_path and z8_path.exists() else {}
    packaging_path = artifact_path(args.external_root, cnn.get("gvid_decode_sr_fullsequence_packaging_receipt"))
    visual = visual_review_summary(args.visual_review)
    visual_signoff = visual_signoff_summary(args.visual_signoff, args.visual_review)
    packaging = sequence_packaging_summary(packaging_path)

    evidence_complete = all(row["sha256_ok"] for row in artifact_checks.values())
    objective_visual_ok = bool(visual.get("objective_checks_pass"))
    sequence_packaging_ok = bool(packaging.get("sequence_packaging_ok"))
    quality_ok = bool(
        mission.get("image_count") == 42
        and z8.get("image_count") == 24
        and (stat(mission, "rmse_improvement_pct", "min") or 0.0) > 0.0
        and (stat(z8, "rmse_improvement_pct", "min") or 0.0) > 0.0
        and (stat(mission, "model_psnr14_db", "min") or 0.0) >= 45.0
        and (stat(z8, "model_psnr14_db", "min") or 0.0) >= 45.0
    )

    blockers: list[str] = []
    if pipeline.get("production_scope") == "offline_review_only":
        blockers.append("registry_scope_offline_review_only")
    if not evidence_complete:
        blockers.append("artifact_hash_or_existence_gap")
    if not objective_visual_ok:
        blockers.append("objective_visual_review_not_passing")
    manual_visual_complete = bool(
        visual.get("manual_visual_review_complete") is True
        or visual_signoff.get("manual_visual_review_complete") is True
    )
    if not manual_visual_complete:
        blockers.append("manual_visual_review_incomplete")
    if not args.controlled_native_psf_proven:
        blockers.append("controlled_native_psf_evidence_missing")
    if not sequence_packaging_ok:
        blockers.append("fullsequence_packaging_not_proven")
    if not quality_ok:
        blockers.append("quality_floor_gap")

    production_ready = bool(args.production_ready and not blockers)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate": {
            "cnn_id": args.cnn_id,
            "pipeline_id": args.pipeline_id,
        },
        "registry": {
            "path": str(args.registry),
            "registry_sha256": sha256_file(args.registry),
            "production_scope": pipeline.get("production_scope"),
            "cnn_status": cnn.get("status"),
        },
        "artifact_checks": artifact_checks,
        "quality": {
            "quality_ok": quality_ok,
            "mission_image_count": mission.get("image_count"),
            "mission_rmse_improvement_min": stat(mission, "rmse_improvement_pct", "min"),
            "mission_psnr14_min_db": stat(mission, "model_psnr14_db", "min"),
            "z8_image_count": z8.get("image_count"),
            "z8_rmse_improvement_min": stat(z8, "rmse_improvement_pct", "min"),
            "z8_psnr14_min_db": stat(z8, "model_psnr14_db", "min"),
        },
        "visual_review": visual,
        "visual_signoff": visual_signoff,
        "fullsequence_packaging": packaging,
        "controlled_native_psf_proven": bool(args.controlled_native_psf_proven),
        "production_ready": production_ready,
        "verdict": {
            "accepted_role": "production" if production_ready else "blocked_review_candidate",
            "blocking_issues": blockers,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--cnn-id", default=DEFAULT_CNN_ID)
    parser.add_argument("--pipeline-id", default=DEFAULT_PIPELINE_ID)
    parser.add_argument("--visual-review", type=Path, default=DEFAULT_VISUAL_REVIEW)
    parser.add_argument("--visual-signoff", type=Path, default=DEFAULT_VISUAL_SIGNOFF)
    parser.add_argument("--controlled-native-psf-proven", action="store_true")
    parser.add_argument("--production-ready", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "production_ready": report["production_ready"],
        "blocking_issues": report["verdict"]["blocking_issues"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
