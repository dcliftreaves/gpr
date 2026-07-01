#!/usr/bin/env python3
"""Smoke-test the Mission 1 8K SR review-candidate audit builder."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_8k_sr_review_candidate_audit.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("build_mission1_8k_sr_review_candidate_audit_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    tool = import_tool()
    with tempfile.TemporaryDirectory(prefix="mission1_8k_review_audit_") as td:
        root = Path(td)
        artifacts = root / "artifacts"
        registry = root / "registry.json"
        visual = artifacts / "visual/visual_review.json"

        mission = artifacts / "mission/summary.json"
        z8 = artifacts / "z8/summary.json"
        frame_pack = artifacts / "frame_pack/receipt.json"
        full_render = artifacts / "full_render/receipt.json"
        full_pack = artifacts / "full_pack/receipt.json"
        metadata = artifacts / "metadata/audit.json"

        write_json(mission, {
            "image_count": 42,
            "rmse_improvement_pct": {"min": 36.0},
            "model_psnr14_db": {"min": 47.0},
        })
        write_json(z8, {
            "image_count": 24,
            "rmse_improvement_pct": {"min": 44.0},
            "model_psnr14_db": {"min": 54.0},
        })
        write_json(frame_pack, {"schema": "frame-pack"})
        write_json(full_render, {"schema": "full-render"})
        write_json(metadata, {"schema": "metadata"})
        write_json(full_pack, {
            "schema": "mission1_8k_sr_sequence_packaging.v1",
            "width": 8192,
            "height": 6144,
            "frame_count": 42,
            "gvid_packaging": {"frame_count": 42, "sha256": "a" * 64},
            "prores_review": {
                "path": "artifacts/full_pack/review.mov",
                "sha256": "b" * 64,
                "bytes": 123,
                "ffprobe": {
                    "streams": [
                        {
                            "codec_name": "prores",
                            "width": 8192,
                            "height": 6144,
                            "nb_frames": "42",
                            "avg_frame_rate": "20/1",
                        }
                    ]
                },
            },
            "summary": {"encode_elapsed_s": {"median": 0.18}},
        })
        write_json(visual, {
            "schema": "gpr.mission1_8k_sr_visual_review.v1",
            "verdict": "objective_visual_metrics_pass_manual_review_required",
            "manual_visual_review_required": True,
            "manual_visual_review_complete": False,
            "contact_sheet": "artifacts/visual/contact.jpg",
            "contact_sheet_sha256": "c" * 64,
            "checks": [{"name": "check", "passed": True}],
        })

        def ref(path: Path) -> str:
            return "artifacts/" + path.relative_to(artifacts).as_posix()

        cnn = {
            "status": "review_only",
            "mission_broad_holdout_receipt": ref(mission),
            "mission_broad_holdout_receipt_sha256": tool.sha256_file(mission),
            "z8_regenerated_holdout_receipt": ref(z8),
            "z8_regenerated_holdout_receipt_sha256": tool.sha256_file(z8),
            "gvid_decode_sr_packaging_receipt": ref(frame_pack),
            "gvid_decode_sr_packaging_receipt_sha256": tool.sha256_file(frame_pack),
            "gvid_decode_sr_fullsequence_receipt": ref(full_render),
            "gvid_decode_sr_fullsequence_receipt_sha256": tool.sha256_file(full_render),
            "gvid_decode_sr_fullsequence_packaging_receipt": ref(full_pack),
            "gvid_decode_sr_fullsequence_packaging_receipt_sha256": tool.sha256_file(full_pack),
            "mission_metadata_transplant_audit": ref(metadata),
            "mission_metadata_transplant_audit_sha256": tool.sha256_file(metadata),
        }
        write_json(registry, {
            "cnns": {tool.DEFAULT_CNN_ID: cnn},
            "pipelines": {
                tool.DEFAULT_PIPELINE_ID: {
                    "production_scope": "offline_review_only",
                    "use_for": "UPRESABLE_NATIVE12_8K_OFFLINE_REGISTRY_REVIEW",
                }
            },
        })

        report = tool.build(argparse.Namespace(
            external_root=root,
            registry=registry,
            cnn_id=tool.DEFAULT_CNN_ID,
            pipeline_id=tool.DEFAULT_PIPELINE_ID,
            visual_review=visual,
            visual_signoff=None,
            controlled_native_psf_proven=False,
            production_ready=False,
        ))
        blockers = set(report["verdict"]["blocking_issues"])
        assert report["schema"] == tool.SCHEMA
        assert report["production_ready"] is False
        assert report["quality"]["quality_ok"] is True
        assert report["visual_review"]["objective_checks_pass"] is True
        assert report["fullsequence_packaging"]["sequence_packaging_ok"] is True
        assert "registry_scope_offline_review_only" in blockers
        assert "manual_visual_review_incomplete" in blockers
        assert "controlled_native_psf_evidence_missing" in blockers
        assert "artifact_hash_or_existence_gap" not in blockers

        signoff = artifacts / "visual_signoff/visual_signoff.json"
        write_json(signoff, {
            "schema": "gpr.mission1_8k_sr_visual_signoff.v1",
            "visual_review": {
                "path": str(visual),
                "sha256": tool.sha256_file(visual),
                "objective_checks_pass": True,
            },
            "signoff": {
                "manual_visual_review_complete": True,
                "reviewer_role": "project_owner",
                "statement": "approved",
                "scope": "test",
            },
            "production_boundary": {
                "controlled_native_psf_evidence_still_required": True,
            },
        })
        signed_report = tool.build(argparse.Namespace(
            external_root=root,
            registry=registry,
            cnn_id=tool.DEFAULT_CNN_ID,
            pipeline_id=tool.DEFAULT_PIPELINE_ID,
            visual_review=visual,
            visual_signoff=signoff,
            controlled_native_psf_proven=False,
            production_ready=False,
        ))
        signed_blockers = set(signed_report["verdict"]["blocking_issues"])
        assert signed_report["visual_signoff"]["manual_visual_review_complete"] is True
        assert "manual_visual_review_incomplete" not in signed_blockers
        assert "registry_scope_offline_review_only" in signed_blockers
        assert "controlled_native_psf_evidence_missing" in signed_blockers

    print("test_build_mission1_8k_sr_review_candidate_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
