#!/usr/bin/env python3
"""Smoke-test the Mission 1 8K SR production gap report."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/mission1_sr_production_gap_report.py"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_blob(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def import_tool():
    spec = importlib.util.spec_from_file_location("mission1_sr_production_gap_report_smoke", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def broad_summary(image_prefix: str, image_count: int) -> dict[str, object]:
    images = [
        {
            "image": f"{image_prefix}{idx:04d}",
            "rmse_improvement_pct": 50.0,
            "mae_improvement_pct": 22.0,
            "gradient_mae_improvement_pct": 8.0,
            "model_psnr14_db": 52.0,
            "fps_with_write": 1.2,
        }
        for idx in range(image_count)
    ]
    return {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": image_count,
        "images": images,
        "fps_with_write": {"median": 1.2},
        "rmse_improvement_pct": {"min": 36.0, "median": 50.0},
        "mae_improvement_pct": {"min": 21.0},
        "gradient_mae_improvement_pct": {"min": 5.8},
        "model_psnr14_db": {"min": 47.1},
        "worst_by_rmse_improvement": {"image": f"{image_prefix}0001"},
        "worst_by_gradient_improvement": {"image": f"{image_prefix}0002"},
        "dashboard": "index.html",
    }


def test_gap_report() -> None:
    tool = import_tool()
    with tempfile.TemporaryDirectory(prefix="sr_gap_report_") as td:
        root = Path(td)
        artifacts = root / "artifacts"
        registry = root / "registry.json"

        ckpt = artifacts / "ckpt.pt"
        pairs = artifacts / "pairs.npz"
        training = artifacts / "train.json"
        write_blob(ckpt, b"checkpoint")
        write_blob(pairs, b"pairs")
        write_json(training, {"schema": "train"})

        decision_rel = "artifacts/decision.json"
        mission_rel = "artifacts/mission.json"
        z8_rel = "artifacts/z8.json"
        multi_rel = "artifacts/multiframe.json"
        pack_rel = "artifacts/packaging.json"
        interp_rel = "current_goal_sr_q4t2_sidecar_aware_interp_probe_20260619/interpolation_decision_summary.json"
        strict_rel = "current_goal_mission1_strict24_gap_report_20260619/summary.json"

        write_json(
            artifacts / "decision.json",
            {
                "schema": "mission1_sr_guarded_focus_retrain_decision.v1",
                "decision": "promote_for_registry_review",
                "reason": "candidate beats broad floors",
                "deltas_vs_q4t2_preclean_step0200": {
                    "mission_rmse_min": 1.0,
                    "z8_rmse_min": 1.0,
                },
                "comparison_scope": {
                    "mission": {
                        "coverage_ok": True,
                        "per_image_rmse_delta": {"GP017346": -0.75, "GP017349": 1.0},
                        "per_image_psnr14_delta": {"GP017346": -0.1, "GP017349": 0.2},
                    },
                    "z8": {
                        "coverage_ok": True,
                        "per_image_rmse_delta": {"Z8Z_1346": 1.0},
                        "per_image_psnr14_delta": {"Z8Z_1346": 0.2},
                    },
                },
            },
        )
        write_json(artifacts / "mission.json", broad_summary("GP", 42))
        write_json(artifacts / "z8.json", broad_summary("Z8Z_", 24))
        write_json(
            artifacts / "multiframe.json",
            {
                "schema": "mission1_native12_gvid_to_8k_sr_multiframe.v1",
                "gvid": "capture.gvid",
                "gvid_sha256": "gvidsha",
                "frames_rendered": 3,
                "output_bayer": {"width": 8192, "height": 6144},
                "max_rss_mb": 1200.0,
                "summary": {
                    "fps_median_decode_plus_sr": 1.16,
                    "decode_plus_sr_total_s": {"median": 0.86},
                    "sr_total_with_write_s": {"median": 0.85},
                },
                "frames": [{"payload_size": 8765001}],
            },
        )
        write_json(
            artifacts / "packaging.json",
            {
                "schema": "mission1_native12_gvid_to_8k_sr_packaging.v2",
                "sr_raw": {"width": 8192, "height": 6144},
                "editable_dng": {
                    "raw_roundtrip_byte_identical": True,
                    "rawpy_open_shape": [6144, 8192],
                },
                "editable_gpr": {
                    "quality": 3,
                    "readback_metrics": {"psnr14_db": 52.95},
                    "gpr_to_dng_rawpy_open_shape": [6144, 8192],
                },
                "prores_review": {"ffprobe": {"streams": [{"codec_name": "prores"}]}},
                "prores_fps_review": {
                    "ffprobe": {
                        "streams": [
                            {
                                "avg_frame_rate": "24/1",
                                "time_base": "1/24",
                                "duration_ts": 2,
                            }
                        ]
                    }
                },
            },
        )
        write_json(
            artifacts / interp_rel,
            {
                "schema": "mission1_sr_q4t2_interpolation_decision.v1",
                "decision": "reject_interpolations_keep_step400_as_review_candidate",
                "decision_reason": "tradeoff only",
            },
        )
        write_json(
            artifacts / strict_rel,
            {
                "schema": "mission1_strict24_gap_report.v1",
                "decision": "strict24_open_wall_throughput_gap",
                "required_loop_reduction_ms": 0.8,
                "required_wall_reduction_ms": 2.4,
            },
        )

        files = {
            "ckpt": ckpt,
            "pairs": pairs,
            "training": training,
            "decision": artifacts / "decision.json",
            "mission": artifacts / "mission.json",
            "z8": artifacts / "z8.json",
            "multi": artifacts / "multiframe.json",
            "pack": artifacts / "packaging.json",
        }
        shas = {name: tool.sha256_file(path) for name, path in files.items()}
        write_json(
            registry,
            {
                "cnns": {
                    tool.CNN_ID: {
                        "$doc": "review only",
                        "status": "review_only_full_production_audit_open",
                        "runtime_entrypoint": "tools/cnn/render_gvid_sr_receipt.py",
                        "ckpt_path": "artifacts/ckpt.pt",
                        "ckpt_sha256": shas["ckpt"],
                        "training_pairs_path": "artifacts/pairs.npz",
                        "training_pairs_sha256": shas["pairs"],
                        "training_receipt": "artifacts/train.json",
                        "training_receipt_sha256": shas["training"],
                        "promotion_review_decision": decision_rel,
                        "promotion_review_decision_sha256": shas["decision"],
                        "mission_broad_holdout_receipt": mission_rel,
                        "mission_broad_holdout_receipt_sha256": shas["mission"],
                        "z8_regenerated_holdout_receipt": z8_rel,
                        "z8_regenerated_holdout_receipt_sha256": shas["z8"],
                        "gvid_decode_sr_multiframe_receipt": multi_rel,
                        "gvid_decode_sr_multiframe_receipt_sha256": shas["multi"],
                        "gvid_decode_sr_packaging_receipt": pack_rel,
                        "gvid_decode_sr_packaging_receipt_sha256": shas["pack"],
                        "gvid_decode_sr_packaging_summary": {
                            "mission_metadata_transplant": "not refreshed for sidecar-aware candidate"
                        },
                    }
                },
                "pipelines": {
                    tool.PIPELINE_ID: {
                        "use_for": "UPRESABLE_NATIVE12_8K_OFFLINE_REGISTRY_REVIEW",
                        "production_scope": "offline_review_only",
                        "$doc": "not a live-camera path",
                    }
                },
            },
        )

        report = tool.build_report(root, registry)
        blockers = {row["name"] for row in report["blockers"]}
        assert report["schema"] == tool.SCHEMA
        assert report["production_ready"] is False
        assert report["production_status"] == "offline_registry_review_not_production"
        assert report["quality"]["quality_evidence_ok_for_registry_review"] is True
        assert report["packaging"]["packaging_ok"] is True
        assert report["runtime"]["live_timing_ok"] is False
        assert report["quality"]["mission_paired_rmse_regressions"] == {"GP017346": -0.75}
        assert "offline_scope" in blockers
        assert "live_timing" in blockers
        assert "mission_paired_regression" in blockers
        assert "mission_metadata_refresh" in blockers
        assert "native12_capture_strict24" in blockers
        assert "checkpoint_interpolation_rejected" in blockers
        assert report["candidate_artifacts"]["checkpoint"]["sha256_ok"] is True


if __name__ == "__main__":
    test_gap_report()
    print("test_mission1_sr_production_gap_report: PASS")
