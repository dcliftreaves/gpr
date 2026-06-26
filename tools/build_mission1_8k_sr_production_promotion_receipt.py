#!/usr/bin/env python3
"""Build a Mission 1 8K SR production-promotion receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from check_mission1_8k_sr_production_promotion import PIPELINE_ID, SCHEMA, validate_receipt


DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_REGISTRY = Path("pipelines/registry.json")
SR_BASE_REL = (
    "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/"
    "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/"
    "sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600"
)
DEFAULT_EDITABLE_PACKAGING_REL = (
    "artifacts/mission1_8k_sr_production_promotion_20260625/"
    "current_candidate_editable_packaging_frame0/packaging_receipt.json"
)
DEFAULT_METADATA_TRANSPLANT_REL = (
    "artifacts/mission1_8k_sr_production_promotion_20260625/"
    "current_candidate_metadata_transplant_frame0/metadata_transplant_audit.json"
)
DEFAULT_VISUAL_REVIEW_REL = "artifacts/mission1_8k_sr_visual_review_20260625/visual_review.json"
EDITABLE_PACKAGING_MIN_PSNR14_DB = 50.0
METADATA_ALLOWED_DIFF_TAGS = {"AsShotNeutral", "NoiseProfile"}
METADATA_ALLOWED_MISSING_RECOMMENDED = {"RawDataUniqueID"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def registry_scope(path: Path) -> str:
    data = read_json(path)
    pipeline = data.get("pipelines", {}).get(PIPELINE_ID, {})
    if not isinstance(pipeline, dict):
        return ""
    scope = pipeline.get("production_scope")
    return scope if isinstance(scope, str) else ""


def editable_packaging_proof(path: Path) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "path": str(path),
        "passed": False,
        "checks": [],
    }
    if not path.exists():
        proof["checks"].append({"name": "receipt_exists", "passed": False})
        return proof

    data = read_json(path)
    proof["sha256"] = sha256_file(path)
    schema_ok = data.get("schema") == "mission1_native12_gvid_to_8k_sr_packaging.v2"
    proof["checks"].append({"name": "schema", "passed": schema_ok, "detail": data.get("schema")})

    editable_dng = data.get("editable_dng") if isinstance(data.get("editable_dng"), dict) else {}
    editable_gpr = data.get("editable_gpr") if isinstance(data.get("editable_gpr"), dict) else {}
    readback = editable_gpr.get("readback_metrics") if isinstance(editable_gpr.get("readback_metrics"), dict) else {}
    dng_shape = editable_dng.get("rawpy_open_shape")
    gpr_dng_shape = editable_gpr.get("gpr_to_dng_rawpy_open_shape")
    dng_roundtrip = editable_dng.get("raw_roundtrip_byte_identical")
    psnr14 = readback.get("psnr14_db")

    proof["checks"].extend(
        [
            {
                "name": "editable_dng_rawpy_shape",
                "passed": dng_shape == [6144, 8192],
                "detail": dng_shape,
            },
            {
                "name": "editable_dng_raw_roundtrip_byte_identical",
                "passed": dng_roundtrip is True,
                "detail": dng_roundtrip,
            },
            {
                "name": "editable_gpr_to_dng_rawpy_shape",
                "passed": gpr_dng_shape == [6144, 8192],
                "detail": gpr_dng_shape,
            },
            {
                "name": "editable_gpr_readback_psnr14_db",
                "passed": isinstance(psnr14, (int, float)) and float(psnr14) >= EDITABLE_PACKAGING_MIN_PSNR14_DB,
                "detail": psnr14,
            },
        ]
    )
    proof["passed"] = all(bool(check["passed"]) for check in proof["checks"])
    return proof


def metadata_transplant_proof(path: Path) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "path": str(path),
        "passed": False,
        "checks": [],
    }
    if not path.exists():
        proof["checks"].append({"name": "audit_exists", "passed": False})
        return proof

    data = read_json(path)
    proof["sha256"] = sha256_file(path)
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    proof["checks"].append({"name": "has_candidates", "passed": bool(candidates), "detail": len(candidates)})
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            proof["checks"].append({"name": f"candidate_{index}_object", "passed": False})
            continue
        missing_required = candidate.get("missing_required")
        missing_recommended = candidate.get("missing_recommended")
        diffs = candidate.get("diffs_from_reference")
        diff_tags = {
            item.get("tag")
            for item in diffs
            if isinstance(item, dict) and isinstance(item.get("tag"), str)
        } if isinstance(diffs, list) else set()
        missing_recommended_set = set(missing_recommended) if isinstance(missing_recommended, list) else set()
        proof["checks"].extend(
            [
                {
                    "name": f"candidate_{index}_readable_by_exiftool",
                    "passed": candidate.get("readable_by_exiftool") is True,
                    "detail": candidate.get("source"),
                },
                {
                    "name": f"candidate_{index}_missing_required",
                    "passed": missing_required == [],
                    "detail": missing_required,
                },
                {
                    "name": f"candidate_{index}_missing_recommended_allowed",
                    "passed": missing_recommended_set <= METADATA_ALLOWED_MISSING_RECOMMENDED,
                    "detail": sorted(missing_recommended_set),
                },
                {
                    "name": f"candidate_{index}_reference_diffs_allowed",
                    "passed": diff_tags <= METADATA_ALLOWED_DIFF_TAGS,
                    "detail": sorted(diff_tags),
                },
            ]
        )
    proof["passed"] = all(bool(check["passed"]) for check in proof["checks"])
    return proof


def visual_review_proof(path: Path) -> dict[str, Any]:
    proof: dict[str, Any] = {"path": str(path), "passed": False, "checks": []}
    if not path.exists():
        proof["checks"].append({"name": "visual_review_exists", "passed": False})
        return proof
    data = read_json(path)
    proof["sha256"] = sha256_file(path)
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    all_checks_passed = bool(checks) and all(isinstance(check, dict) and check.get("passed") is True for check in checks)
    proof["checks"].extend(
        [
            {"name": "schema", "passed": data.get("schema") == "gpr.mission1_8k_sr_visual_review.v1", "detail": data.get("schema")},
            {"name": "objective_checks_pass", "passed": all_checks_passed, "detail": len(checks)},
            {
                "name": "manual_visual_review_required",
                "passed": data.get("manual_visual_review_required") is True,
                "detail": data.get("manual_visual_review_required"),
            },
        ]
    )
    proof["passed"] = all(bool(check["passed"]) for check in proof["checks"])
    return proof


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    external_root = args.external_root
    sr_base = external_root / SR_BASE_REL
    runtime = sr_base / "mission42_4kcnn_gvid_to_8k_sr_full42/receipt.json"
    gvid = sr_base / "mission42_4kcnn_8k_sr_gvid_packaging_q3_after_bounds_fix/receipt.json"
    prores = sr_base / "mission42_4kcnn_8k_sr_gvid_to_prores_42f_after_bounds_fix/receipt.json"
    quality_mission = sr_base / "mission42_broad_fullframe/summary.json"
    quality_z8 = sr_base / "z8_all24_fullframe/summary.json"
    scope = registry_scope(args.registry)
    editable_proof = editable_packaging_proof(args.editable_packaging_receipt)
    editable_packaging_proven = bool(args.editable_packaging_proven) or bool(editable_proof["passed"])
    metadata_proof = metadata_transplant_proof(args.metadata_transplant_audit)
    metadata_transplant_proven = bool(args.metadata_transplant_proven) or bool(metadata_proof["passed"])
    visual_proof = visual_review_proof(args.visual_review_package)

    evidence = {
        "runtime_receipt": str(runtime),
        "runtime_receipt_sha256": sha256_file(runtime),
        "gvid_packaging_receipt": str(gvid),
        "gvid_packaging_receipt_sha256": sha256_file(gvid),
        "prores_receipt": str(prores),
        "prores_receipt_sha256": sha256_file(prores),
        "quality_summary": str(quality_mission),
        "quality_summary_sha256": sha256_file(quality_mission),
        "z8_quality_summary": str(quality_z8),
        "z8_quality_summary_sha256": sha256_file(quality_z8),
        "visual_review_complete": bool(args.visual_review_complete),
        "editable_packaging_proven": editable_packaging_proven,
        "metadata_transplant_proven": metadata_transplant_proven,
        "visual_review_proof": visual_proof,
        "editable_packaging_proof": editable_proof,
        "metadata_transplant_proof": metadata_proof,
    }
    if "sha256" in visual_proof:
        evidence["visual_review_package"] = str(args.visual_review_package)
        evidence["visual_review_package_sha256"] = visual_proof["sha256"]
    if "sha256" in editable_proof:
        evidence["editable_packaging_receipt"] = str(args.editable_packaging_receipt)
        evidence["editable_packaging_receipt_sha256"] = editable_proof["sha256"]
    if "sha256" in metadata_proof:
        evidence["metadata_transplant_audit"] = str(args.metadata_transplant_audit)
        evidence["metadata_transplant_audit_sha256"] = metadata_proof["sha256"]

    blocking_issues = []
    if scope not in {"offline_production", "production"}:
        blocking_issues.append("registry_scope_not_promoted")
    if not evidence["visual_review_complete"]:
        blocking_issues.append("visual_review_incomplete")
    elif not visual_proof["passed"]:
        blocking_issues.append("visual_review_package_not_proven")
    if not evidence["editable_packaging_proven"]:
        blocking_issues.append("editable_packaging_not_proven")
    if not evidence["metadata_transplant_proven"]:
        blocking_issues.append("metadata_transplant_not_proven")
    production_ready = bool(args.production_ready) and not blocking_issues

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "candidate": {"pipeline_id": PIPELINE_ID},
        "registry": {
            "path": str(args.registry),
            "production_scope": scope,
            "registry_sha256": sha256_file(args.registry),
        },
        "evidence": evidence,
        "verdict": {
            "production_ready": production_ready,
            "accepted_role": "production" if production_ready else "blocked",
            "blocking_issues": blocking_issues,
        },
    }
    if not production_ready:
        receipt["blocker"] = {"cause": ",".join(blocking_issues) or "production_promotion_not_requested"}
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--editable-packaging-receipt",
        type=Path,
        default=DEFAULT_EXTERNAL_ROOT / DEFAULT_EDITABLE_PACKAGING_REL,
    )
    ap.add_argument(
        "--metadata-transplant-audit",
        type=Path,
        default=DEFAULT_EXTERNAL_ROOT / DEFAULT_METADATA_TRANSPLANT_REL,
    )
    ap.add_argument(
        "--visual-review-package",
        type=Path,
        default=DEFAULT_EXTERNAL_ROOT / DEFAULT_VISUAL_REVIEW_REL,
    )
    ap.add_argument("--visual-review-complete", action="store_true")
    ap.add_argument("--editable-packaging-proven", action="store_true")
    ap.add_argument("--metadata-transplant-proven", action="store_true")
    ap.add_argument("--production-ready", action="store_true")
    args = ap.parse_args()

    receipt = build_receipt(args)
    failures = validate_receipt(receipt)
    if failures:
        for failure in failures:
            print(failure)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
