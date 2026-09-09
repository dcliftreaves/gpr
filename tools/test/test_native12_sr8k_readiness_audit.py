#!/usr/bin/env python3
"""Smoke-test the native12 8K SR production-readiness audit checks."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "tests/quality_gates/audit_production_readiness.py"
PIPELINE_ID = "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_all24_holdout5_v1+demosaic=sips_via_gpr_tools"
CNN_ID = "mission1_native12_8k_sr_all24_holdout5_v1"
FOCUS_PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_focus_hardrows_2500_v1+"
    "demosaic=sips_via_gpr_tools"
)
FOCUS_CNN_ID = "mission1_native12_8k_sr_focus_hardrows_2500_v1"
LIGHT_PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_guardrail_light_w15_800_v1+"
    "demosaic=sips_via_gpr_tools"
)
LIGHT_CNN_ID = "mission1_native12_8k_sr_guardrail_light_w15_800_v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("_fixture_padding", "x" * 1024)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def artifact_ref(path: Path, artifact_root: Path) -> str:
    return "artifacts/" + str(path.relative_to(artifact_root))


def import_audit_module():
    spec = importlib.util.spec_from_file_location("audit_production_readiness_smoke", AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_fixture(artifact_root: Path) -> dict:
    ckpt = artifact_root / "sr8k" / "checkpoint.pt"
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_bytes((b"sr8k-checkpoint-fixture\n" * 6000)[:120_000])

    z8_summary = artifact_root / "sr8k" / "z8_summary.json"
    write_json(z8_summary, {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": 5,
        "rmse_improvement_pct": {"min": 41.5},
        "mae_improvement_pct": {"min": 7.8},
        "gradient_mae_improvement_pct": {"min": 2.6},
        "model_psnr14_db": {"min": 54.1},
    })

    mission_summary = artifact_root / "sr8k" / "mission_summary.json"
    write_json(mission_summary, {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": 1,
        "rmse_improvement_pct": {"min": 48.6},
        "mae_improvement_pct": {"min": 38.1},
        "gradient_mae_improvement_pct": {"min": 18.7},
        "model_psnr14_db": {"min": 47.9},
    })

    mission_broad_summary = artifact_root / "sr8k" / "mission_broad_summary.json"
    write_json(mission_broad_summary, {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": 8,
        "rmse_improvement_pct": {"min": 34.0},
        "mae_improvement_pct": {"min": 21.6},
        "gradient_mae_improvement_pct": {"min": 8.2},
        "model_psnr14_db": {"min": 47.9},
        "fps_with_write": {"median": 2.65},
    })

    refresh = artifact_root / "sr8k" / "gvid_decode_sr.json"
    write_json(refresh, {
        "schema": "mission1_native12_gvid_to_8k_sr_multiframe.v1",
        "frames_rendered": 3,
        "output_bayer": {"width": 8192, "height": 6144},
        "write_sr_raw": True,
        "keep_sr_raw": False,
        "max_rss_mb": 1198.6,
        "summary": {
            "fps_median_decode_plus_sr": 2.73,
            "decode_plus_sr_total_s": {"median": 0.366},
        },
    })

    bench = artifact_root / "sr8k" / "bench.json"
    write_json(bench, {
        "schema": "mission1_sr_8k_bench.v1",
        "output_bayer": {"width": 8192, "height": 6144, "written": True},
        "timing": {"tile_count": 20, "fps_with_write": 2.5},
        "architecture_cost": {"actual_macs_per_frame": 288_098_353_152},
    })

    compare = artifact_root / "sr8k" / "compare.json"
    write_json(compare, {
        "schema": "mission1_sr_fullframe_compare.v1",
        "high_width": 8192,
        "high_height": 6144,
        "improvement_pct": {"rmse": 48.6, "mae": 38.1, "gradient_mae": 18.7},
        "model": {"psnr14_db": 47.9},
    })

    packaging = artifact_root / "sr8k" / "packaging.json"
    write_json(packaging, {
        "schema": "mission1_native12_gvid_to_8k_sr_packaging.v2",
        "sr_raw": {"width": 8192, "height": 6144, "bytes": 100_663_296},
        "editable_dng": {
            "rawpy_open_shape": [6144, 8192],
            "raw_roundtrip_byte_identical": True,
        },
        "editable_gpr": {
            "readback_metrics": {"psnr14_db": 56.2},
            "gpr_to_dng_rawpy_open_shape": [6144, 8192],
        },
        "prores_review": {"ffprobe": {"streams": [{"codec_name": "prores"}]}},
        "prores_fps_review": {
            "ffprobe": {
                "streams": [{
                    "codec_name": "prores",
                    "avg_frame_rate": "24/1",
                    "time_base": "1/24",
                    "duration_ts": 2,
                }]
            }
        },
    })

    prores = artifact_root / "sr8k" / "prores_fps.json"
    write_json(prores, {
        "schema": "gpr.prores_fps_fix_receipt.v1",
        "result": {"pass": True},
        "one_frame_probe": {"time_base": "1/24", "duration_ts": 1},
        "two_frame_probe": {"avg_frame_rate": "24/1", "r_frame_rate": "24/1"},
    })

    metadata = artifact_root / "sr8k" / "metadata.json"
    write_json(metadata, {
        "candidates": [
            {"source": "GP017601.GPR", "missing_required": [], "readable_by_exiftool": True},
            {"source": "GP017602.GPR", "missing_required": [], "readable_by_exiftool": True},
        ],
    })
    training_pairs = artifact_root / "sr8k" / "mission1_z8_pairs.npz"
    training_pairs.write_bytes(b"fixture npz placeholder\n" * 128)
    mission_images = [
        {
            "image_id": f"GP01734{i}",
            "raw50": f"/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/raw50_decode/GP01734{i}.raw",
        }
        for i in range(6, 10)
    ] + [
        {
            "image_id": f"GP01760{i}",
            "raw50": f"/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/raw50_decode/GP01760{i}.raw",
        }
        for i in range(4)
    ]
    z8_images = [
        {
            "image_id": f"Z8Z_{1330 + i}",
            "high_source": f"/Volumes/OWC_8TB/gpr_work/artifacts/fixtures/barn_sky_dngs/Z8Z_{1330 + i}.dng",
        }
        for i in range(24)
    ]
    training_pairs_sidecar = Path(str(training_pairs) + ".json")
    training_pair_meta = {
        "schema": "mission1_sr_pairs_merged.v1",
        "source": "merged Bayer SR tile-pair datasets",
        "source_datasets": [
            {
                "tag": "mission1",
                "path": "/fixtures/mission1_pairs.npz",
                "tile_count": 768,
                "meta": {
                    "schema": "mission1_sr_pairs.v1",
                    "downsample": "gaussian_area",
                    "downsample_policy": "cfa_same_color_gaussian_area_2x",
                    "production_downsample": True,
                    "allow_diagnostic_downsample": False,
                    "cfa_preserving": True,
                    "codec": "current_t233",
                    "codec_profile_id": "mission1_native12_fll2_t233_avg7555_fast_pinp2_20fps_v1",
                    "images": mission_images,
                },
            },
            {
                "tag": "z8",
                "path": "/fixtures/z8_pairs.npz",
                "tile_count": 2304,
                "meta": {
                    "schema": "mission1_sr_pairs.v1",
                    "downsample": "gaussian_area",
                    "downsample_policy": "cfa_same_color_gaussian_area_2x",
                    "production_downsample": True,
                    "allow_diagnostic_downsample": False,
                    "cfa_preserving": True,
                    "codec": "current_t233",
                    "codec_profile_id": "mission1_native12_fll2_t233_avg7555_fast_pinp2_20fps_v1",
                    "images": z8_images,
                },
            },
        ],
        "low_tile": 96,
        "high_tile": 192,
        "images": mission_images + z8_images,
    }
    write_json(training_pairs_sidecar, training_pair_meta)

    diagnostic_pairs = artifact_root / "sr8k" / "diagnostic_pairs.npz"
    diagnostic_pairs.write_bytes(b"diagnostic fixture npz placeholder\n" * 128)
    diagnostic_meta = copy.deepcopy(training_pair_meta)
    diagnostic_meta["source_datasets"][0]["meta"]["downsample"] = "sample"
    diagnostic_meta["source_datasets"][0]["meta"]["production_downsample"] = False
    diagnostic_meta["source_datasets"][0]["meta"]["allow_diagnostic_downsample"] = True
    write_json(Path(str(diagnostic_pairs) + ".json"), diagnostic_meta)

    focus_training = artifact_root / "sr8k_focus" / "training.json"
    write_json(focus_training, {"schema": "mission1_sr_training_receipt.v1", "steps": 2500})
    focus_mission_broad = artifact_root / "sr8k_focus" / "mission_broad.json"
    write_json(focus_mission_broad, {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": 8,
        "rmse_improvement_pct": {"min": 37.7},
        "mae_improvement_pct": {"min": 24.9},
        "gradient_mae_improvement_pct": {"min": 9.9},
        "model_psnr14_db": {"min": 47.9},
        "fps_with_write": {"median": 2.6},
    })
    focus_z8 = artifact_root / "sr8k_focus" / "z8_regen.json"
    write_json(focus_z8, {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": 5,
        "rmse_improvement_pct": {"min": 24.9},
        "mae_improvement_pct": {"min": 6.0},
        "gradient_mae_improvement_pct": {"min": 1.6},
        "model_psnr14_db": {"min": 51.2},
    })
    focus_multiframe = artifact_root / "sr8k_focus" / "multiframe.json"
    write_json(focus_multiframe, {
        "schema": "mission1_native12_gvid_to_8k_sr_multiframe.v1",
        "frames_rendered": 3,
        "output_bayer": {"width": 8192, "height": 6144},
        "write_sr_raw": True,
        "keep_sr_raw": False,
        "max_rss_mb": 1198.5,
        "summary": {
            "fps_median_decode_plus_sr": 2.9,
            "decode_plus_sr_total_s": {"median": 0.345},
        },
    })
    frontier = artifact_root / "mission1_native12_sr_frontier_summary_20260618" / "summary.json"
    write_json(frontier, {
        "schema": "mission1_native12_sr_frontier_summary.v1",
        "decision": "promoted_registered_offline_candidate",
        "profiles": [
            {
                "profile": "t233_registered",
                "registered": True,
                "status": "registered_offline_candidate",
                "gate_pass": True,
                "gradient_improvement_min": 8.2,
                "rmse_improvement_median": 47.6,
                "rmse_improvement_min": 34.0,
                "z8_rmse_improvement_min": 24.9,
            },
            {
                "profile": "t233_focus_hardrows_2500",
                "registered": False,
                "status": "hold_boundary_not_promoted",
                "gate_pass": True,
                "requires_z8_guardrail": True,
                "decision_reason": "regresses regenerated Z8 guardrail metrics: z8_rmse_improvement_min",
            },
            {
                "profile": "t233_guardrail_light_w15_800",
                "registered": True,
                "status": "registered_offline_candidate",
                "gate_pass": True,
                "requires_packaging": True,
                "requires_z8_guardrail": True,
                "z8_rmse_improvement_min": 25.8,
                "packaging_gpr_psnr14_db": 56.3,
                "packaging_raw_to_gpr_mode": "direct_fallback_after_scratch_failure",
                "multiframe_fps_median": 2.8,
            },
            {
                "profile": "t236_ch2lh3",
                "registered": False,
                "status": "rejected_worst_row_regression",
                "gate_pass": False,
            },
            {
                "profile": "t236_ch2lh3_gw08",
                "registered": False,
                "status": "rejected_worst_row_regression",
                "gate_pass": False,
                "rmse_improvement_median": 55.0,
                "rmse_improvement_min": 27.0,
            },
            {
                "profile": "t356_ch2lh3",
                "registered": False,
                "status": "rejected_worst_row_regression",
                "gate_pass": False,
            },
        ],
    })
    guarded_decision = artifact_root / "current_goal_sr_t233_guarded_focus_w8_600_decision_20260618" / "decision.json"
    write_json(guarded_decision, {
        "schema": "mission1_sr_guarded_focus_retrain_decision.v1",
        "decision": "reject_do_not_register",
        "reason": "The guarded focus continuation improves the older registered Mission baseline but does not beat the registered guardrail-light candidate, and it regresses the regenerated Z8 guardrail below the registered/light candidates.",
        "candidate": {
            "checkpoint": "/fixture/mission1_sr_t233_guarded_focus_w8_from_registered_w48_d6_rs03_600.pt",
        },
        "deltas_vs_guardrail_light": {
            "mission_rmse_min": -2.0,
            "mission_rmse_median": -1.7,
            "z8_rmse_min": -1.8,
            "z8_psnr14_min": -0.2,
        },
        "next_experiment": (
            "If continuing SR, try mixed objective/early-stop against explicit Mission+Z8 validation, "
            "not focus-only continuation."
        ),
    })
    mixed_summary = artifact_root / "current_goal_sr_guarded_mixed_probe_20260618" / "guarded_experiment_summary.json"
    write_json(mixed_summary, {
        "schema": "mission1_sr_guarded_experiment.v1",
        "decision": "no_candidate_promoted",
        "candidate_count": 3,
        "candidates": [
            {
                "checkpoint": "/fixture/step000001.pt",
                "decision": "reject_do_not_register",
                "reason": "does not beat guardrail-light on Mission worst-row/median floors",
                "deltas": {
                    "mission_rmse_min": -0.08,
                    "mission_rmse_median": 0.01,
                    "z8_rmse_min": 0.07,
                    "z8_psnr14_min": 0.01,
                },
                "comparison_scope": {
                    "mission": {"missing_baseline_images": ["c"]},
                    "z8": {"missing_baseline_images": ["z3"]},
                },
            },
            {
                "checkpoint": "/fixture/step000200.pt",
                "decision": "reject_do_not_register",
                "reason": "regresses the regenerated Z8 guardrail",
                "deltas": {
                    "mission_rmse_min": 0.16,
                    "mission_rmse_median": -1.57,
                    "z8_rmse_min": -0.24,
                    "z8_psnr14_min": -0.03,
                },
                "comparison_scope": {
                    "mission": {"missing_baseline_images": ["c"]},
                    "z8": {"missing_baseline_images": ["z3"]},
                },
            },
            {
                "checkpoint": "/fixture/best.pt",
                "decision": "reject_do_not_register",
                "reason": "does not beat guardrail-light on Mission worst-row/median floors",
                "deltas": {
                    "mission_rmse_min": -0.08,
                    "mission_rmse_median": 0.01,
                    "z8_rmse_min": 0.07,
                    "z8_psnr14_min": 0.01,
                },
                "comparison_scope": {
                    "mission": {"missing_baseline_images": ["c"]},
                    "z8": {"missing_baseline_images": ["z3"]},
                },
            },
        ],
    })
    full_mixed_summary = (
        artifact_root
        / "current_goal_sr_guarded_mixed_probe_20260618"
        / "guarded_experiment_fullcoverage_summary.json"
    )
    write_json(full_mixed_summary, {
        "schema": "mission1_sr_guarded_experiment.v1",
        "decision": "no_candidate_promoted",
        "coverage": "full_baseline_holdout",
        "mission_image_count": 8,
        "z8_image_count": 5,
        "candidate_count": 3,
        "candidates": [
            {
                "checkpoint": "/fixture/step000001.pt",
                "decision": "reject_do_not_register",
                "reason": "does not beat guardrail-light on Mission worst-row/median floors",
                "deltas": {
                    "mission_rmse_min": -0.08,
                    "mission_rmse_median": -0.10,
                    "z8_rmse_min": 0.07,
                    "z8_psnr14_min": 0.01,
                },
                "comparison_scope": {
                    "mission": {"missing_baseline_images": []},
                    "z8": {"missing_baseline_images": []},
                },
            },
            {
                "checkpoint": "/fixture/step000200.pt",
                "decision": "reject_do_not_register",
                "reason": "regresses the regenerated Z8 guardrail",
                "deltas": {
                    "mission_rmse_min": 0.16,
                    "mission_rmse_median": -0.04,
                    "z8_rmse_min": -0.24,
                    "z8_psnr14_min": -0.03,
                },
                "comparison_scope": {
                    "mission": {"missing_baseline_images": []},
                    "z8": {"missing_baseline_images": []},
                },
            },
            {
                "checkpoint": "/fixture/best.pt",
                "decision": "reject_do_not_register",
                "reason": "does not beat guardrail-light on Mission worst-row/median floors",
                "deltas": {
                    "mission_rmse_min": -0.08,
                    "mission_rmse_median": -0.10,
                    "z8_rmse_min": 0.07,
                    "z8_psnr14_min": 0.01,
                },
                "comparison_scope": {
                    "mission": {"missing_baseline_images": []},
                    "z8": {"missing_baseline_images": []},
                },
            },
        ],
    })
    resblock_summary = (
        artifact_root
        / "current_goal_sr_resblock_zeroinit_w48_800_probe_20260618"
        / "guarded_experiment_summary.json"
    )
    write_json(resblock_summary, {
        "schema": "mission1_sr_guarded_experiment.v1",
        "decision": "no_candidate_promoted",
        "candidate_count": 4,
        "selected": None,
        "candidates": [
            {
                "checkpoint": "/fixture/resblock_step000001.pt",
                "decision": "reject_do_not_register",
                "reason": "below guardrail-light on Mission and regenerated Z8 floors",
                "deltas": {
                    "mission_rmse_min": -36.0,
                    "mission_rmse_median": -45.0,
                    "z8_rmse_min": -24.0,
                    "z8_psnr14_min": -2.4,
                },
            },
            {
                "checkpoint": "/fixture/resblock_step000200.pt",
                "decision": "reject_do_not_register",
                "reason": "below guardrail-light on Mission and regenerated Z8 floors",
                "deltas": {
                    "mission_rmse_min": -35.8,
                    "mission_rmse_median": -44.8,
                    "z8_rmse_min": -23.8,
                    "z8_psnr14_min": -2.3,
                },
            },
            {
                "checkpoint": "/fixture/resblock_step000400.pt",
                "decision": "reject_do_not_register",
                "reason": "below guardrail-light on Mission and regenerated Z8 floors",
                "deltas": {
                    "mission_rmse_min": -35.6,
                    "mission_rmse_median": -44.7,
                    "z8_rmse_min": -23.7,
                    "z8_psnr14_min": -2.2,
                },
            },
            {
                "checkpoint": "/fixture/resblock_step000800.pt",
                "decision": "reject_do_not_register",
                "reason": "below guardrail-light on Mission and regenerated Z8 floors",
                "deltas": {
                    "mission_rmse_min": -35.34,
                    "mission_rmse_median": -44.97,
                    "z8_rmse_min": -23.70,
                    "z8_psnr14_min": -2.10,
                },
            },
        ],
    })
    interp_summary = (
        artifact_root
        / "current_goal_sr_interp_light_focus_probe_20260618"
        / "summary.json"
    )
    write_json(interp_summary, {
        "schema": "mission1_sr_light_focus_interpolation_probe.v1",
        "decision": "no_candidate_promoted",
        "selected": None,
        "candidates": [
            {
                "alpha": 0.25,
                "decision": "reject_do_not_register",
                "reason": "does not beat guardrail-light on Mission median and regenerated Z8 floors",
                "deltas_vs_guardrail_light": {
                    "mission_rmse_min": -0.05,
                    "mission_rmse_median": -0.10,
                    "z8_rmse_min": 0.02,
                    "z8_psnr14_min": 0.01,
                },
            },
            {
                "alpha": 0.5,
                "decision": "reject_do_not_register",
                "reason": "guardrail-light comparison shows a small Mission floor lift but median and Z8 regression",
                "deltas_vs_guardrail_light": {
                    "mission_rmse_min": 0.08,
                    "mission_rmse_median": -0.20,
                    "z8_rmse_min": -0.10,
                    "z8_psnr14_min": -0.02,
                },
            },
            {
                "alpha": 0.75,
                "decision": "reject_do_not_register",
                "reason": "guardrail-light comparison rejects Mission median and Z8 regression",
                "deltas_vs_guardrail_light": {
                    "mission_rmse_min": 0.16,
                    "mission_rmse_median": -0.35,
                    "z8_rmse_min": -0.24,
                    "z8_psnr14_min": -0.03,
                },
            },
        ],
    })

    files = {
        "ckpt": ckpt,
        "holdout": z8_summary,
        "mission": mission_summary,
        "mission_broad": mission_broad_summary,
        "refresh": refresh,
        "bench": bench,
        "compare": compare,
        "packaging": packaging,
        "prores": prores,
        "metadata": metadata,
        "training_pairs": training_pairs,
        "diagnostic_pairs": diagnostic_pairs,
        "focus_training": focus_training,
        "focus_mission_broad": focus_mission_broad,
        "focus_z8": focus_z8,
        "focus_multiframe": focus_multiframe,
        "frontier": frontier,
        "guarded_decision": guarded_decision,
        "resblock_summary": resblock_summary,
        "interp_summary": interp_summary,
    }

    cnn = {
        "ckpt_path": artifact_ref(ckpt, artifact_root),
        "ckpt_sha256": sha256_file(ckpt),
        "training_pairs_path": artifact_ref(training_pairs, artifact_root),
        "training_pairs_sha256": sha256_file(training_pairs),
        "holdout_receipt": artifact_ref(z8_summary, artifact_root),
        "holdout_receipt_sha256": sha256_file(z8_summary),
        "mission_holdout_receipt": artifact_ref(mission_summary, artifact_root),
        "mission_holdout_receipt_sha256": sha256_file(mission_summary),
        "mission_broad_holdout_receipt": artifact_ref(mission_broad_summary, artifact_root),
        "mission_broad_holdout_receipt_sha256": sha256_file(mission_broad_summary),
        "gvid_decode_sr_refresh_receipt": artifact_ref(refresh, artifact_root),
        "gvid_decode_sr_refresh_receipt_sha256": sha256_file(refresh),
        "sr8k_fresh_bench_receipt": artifact_ref(bench, artifact_root),
        "sr8k_fresh_bench_receipt_sha256": sha256_file(bench),
        "sr8k_fresh_compare_receipt": artifact_ref(compare, artifact_root),
        "sr8k_fresh_compare_receipt_sha256": sha256_file(compare),
        "gvid_decode_sr_packaging_receipt": artifact_ref(packaging, artifact_root),
        "gvid_decode_sr_packaging_receipt_sha256": sha256_file(packaging),
        "gvid_decode_sr_prores_fps_receipt": artifact_ref(prores, artifact_root),
        "gvid_decode_sr_prores_fps_receipt_sha256": sha256_file(prores),
        "mission1_metadata_repack_receipt": artifact_ref(metadata, artifact_root),
        "mission1_metadata_repack_receipt_sha256": sha256_file(metadata),
    }
    focus_cnn = {
        "ckpt_path": artifact_ref(ckpt, artifact_root),
        "ckpt_sha256": sha256_file(ckpt),
        "training_receipt": artifact_ref(focus_training, artifact_root),
        "training_receipt_sha256": sha256_file(focus_training),
        "mission_broad_holdout_receipt": artifact_ref(focus_mission_broad, artifact_root),
        "mission_broad_holdout_receipt_sha256": sha256_file(focus_mission_broad),
        "z8_regenerated_holdout_receipt": artifact_ref(focus_z8, artifact_root),
        "z8_regenerated_holdout_receipt_sha256": sha256_file(focus_z8),
        "gvid_decode_sr_multiframe_receipt": artifact_ref(focus_multiframe, artifact_root),
        "gvid_decode_sr_multiframe_receipt_sha256": sha256_file(focus_multiframe),
        "gvid_decode_sr_packaging_receipt": artifact_ref(packaging, artifact_root),
        "gvid_decode_sr_packaging_receipt_sha256": sha256_file(packaging),
    }
    light_cnn = dict(focus_cnn)
    registry = {
        "pipelines": {
            PIPELINE_ID: {
                "$doc": "offline-only candidate; not a live-camera path",
                "codec": "mission1_native12_t233",
                "cnn": CNN_ID,
                "ship_class": "UPRESABLE",
                "use_for": "UPRESABLE_NATIVE12_8K_OFFLINE_CANDIDATE",
                "production_scope": "offline_review_only",
            },
            FOCUS_PIPELINE_ID: {
                "$doc": "registry-review candidate; not the production default",
                "codec": "mission1_native12_t233",
                "cnn": FOCUS_CNN_ID,
                "ship_class": "UPRESABLE",
                "use_for": "UPRESABLE_NATIVE12_8K_OFFLINE_REGISTRY_REVIEW",
                "production_scope": "offline_review_only",
            },
            LIGHT_PIPELINE_ID: {
                "$doc": "registered offline candidate using direct retained-artifact fallback; not a live-camera path",
                "codec": "mission1_native12_t233",
                "cnn": LIGHT_CNN_ID,
                "ship_class": "UPRESABLE",
                "use_for": "UPRESABLE_NATIVE12_8K_OFFLINE_CANDIDATE",
                "production_scope": "offline_review_only",
            },
        },
        "cnns": {CNN_ID: cnn, FOCUS_CNN_ID: focus_cnn, LIGHT_CNN_ID: light_cnn},
    }
    return {"registry": registry, "files": files}


def run_checks(module, registry: dict, artifact_root: Path):
    module.REG = copy.deepcopy(registry)
    module.ARTIFACT_ROOT = artifact_root
    checks = []
    checks.extend(module.check_native12_8k_sr_candidate())
    checks.extend(module.check_native12_sr_registry_boundaries())
    checks.extend(module.check_native12_sr_frontier_summary())
    return checks


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native12_sr8k_audit_", dir=work_parent) as td:
        artifact_root = Path(td) / "artifacts"
        fixture = build_fixture(artifact_root)
        module = import_audit_module()

        checks = run_checks(module, fixture["registry"], artifact_root)
        failures = [check for check in checks if check.status != "PASS"]
        if failures:
            for check in failures:
                print(f"unexpected failure: {check.area} {check.name}: {check.detail}")
            return 1

        bad_registry = copy.deepcopy(fixture["registry"])
        bad_registry["cnns"][CNN_ID]["sr8k_fresh_compare_receipt_sha256"] = "0" * 64
        bad_checks = run_checks(module, bad_registry, artifact_root)
        bad_compare = [
            check for check in bad_checks
            if check.name == "fresh 8K SR compare receipt hash"
        ]
        if len(bad_compare) != 1 or bad_compare[0].status != "FAIL":
            print("expected fresh compare hash mismatch to fail")
            return 1

        bad_pair_hash_registry = copy.deepcopy(fixture["registry"])
        bad_pair_hash_registry["cnns"][CNN_ID]["training_pairs_sha256"] = "0" * 64
        bad_pair_hash_checks = run_checks(module, bad_pair_hash_registry, artifact_root)
        bad_pair_hash = [
            check for check in bad_pair_hash_checks
            if check.name == "8K SR training pair hash"
        ]
        if len(bad_pair_hash) != 1 or bad_pair_hash[0].status != "FAIL":
            print("expected SR training pair hash mismatch to fail")
            return 1

        bad_pairs_registry = copy.deepcopy(fixture["registry"])
        bad_pairs_registry["cnns"][CNN_ID]["training_pairs_path"] = artifact_ref(
            fixture["files"]["diagnostic_pairs"],
            artifact_root,
        )
        bad_pairs_checks = run_checks(module, bad_pairs_registry, artifact_root)
        bad_pairs = [
            check for check in bad_pairs_checks
            if check.name == "8K SR training pair provenance"
        ]
        if len(bad_pairs) != 1 or bad_pairs[0].status != "FAIL":
            print("expected diagnostic SR pair provenance to fail")
            return 1

        bad_boundary_registry = copy.deepcopy(fixture["registry"])
        bad_boundary_registry["pipelines"][
            "codec=mission1_native12_t236_ch2lh3+cnn=unsafe_speedtier_sr+demosaic=sips_via_gpr_tools"
        ] = {
            "$doc": "bad fixture pipeline",
            "codec": "mission1_native12_t236_ch2lh3",
            "cnn": "unsafe_speedtier_sr",
            "ship_class": "UPRESABLE",
            "use_for": "UPRESABLE_NATIVE12_8K_OFFLINE_CANDIDATE",
            "production_scope": "offline_review_only",
        }
        bad_boundary_checks = run_checks(module, bad_boundary_registry, artifact_root)
        bad_boundary = [
            check for check in bad_boundary_checks
            if check.name == "native12 SR registry codec boundary"
        ]
        if len(bad_boundary) != 1 or bad_boundary[0].status != "FAIL":
            print("expected speed-tier SR registry boundary violation to fail")
            return 1

    print("test_native12_sr8k_readiness_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
