#!/usr/bin/env python3
"""Smoke-test Mission 1 write-contention classification."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/mission1_write_contention_summary.py"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def import_tool():
    spec = importlib.util.spec_from_file_location("mission1_write_contention_summary_smoke", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_fixture(external_root: Path) -> None:
    artifact_root = external_root / "artifacts"
    write_json(artifact_root / "mission1_writer_contention_isolation_20260617/summary.json", [
        {
            "name": "pingpong_devnull",
            "encode_median": 40.934,
            "write_median": 0.003,
            "total_median": 40.938,
            "payload_kib_median": 5440.82,
        },
        {
            "name": "pingpong_ssd",
            "encode_median": 46.353,
            "write_median": 0.004,
            "total_median": 46.406,
            "payload_kib_median": 5440.82,
        },
    ])
    write_json(
        artifact_root / "current_goal_t236_build_variant_probe_GP017602_120f_20260618/summary.json",
        {
            "cases": {
                "ofast_p2order": {
                    "phases": {
                        "encode": {"median_ms": 38.870},
                        "payload_kib": {"median_ms": 5483.862},
                        "total": {"median_ms": 38.870},
                        "write": {"median_ms": 0.0},
                    }
                }
            }
        },
    )
    write_json(
        artifact_root / "current_goal_t236_write_build_probe_GP017602_240f_20260618/summary.json",
        {
            "cases": {
                "codegen_ofast": {
                    "phases": {
                        "encode": {"median_ms": 38.664},
                        "payload_kib": {"median_ms": 5483.862},
                        "total": {"median_ms": 42.503},
                        "write": {"median_ms": 3.764},
                    }
                }
            }
        },
    )
    write_json(
        artifact_root / "current_goal_t236_clean_pi_probe_GP017602_60f_20260618/summary.json",
        {
            "schema": "mission1_t236_clean_pi_probe.v1",
            "cases": {
                "ofast_no_write": {
                    "metrics": {
                        "total_median_ms": 38.676,
                        "fps_median": 25.856,
                        "strict_24_pass": True,
                    }
                },
                "ofast_real_write": {
                    "metrics": {
                        "total_median_ms": 42.641,
                        "encode_median_ms": 39.554,
                        "write_median_ms": 3.190,
                        "fps_median": 23.452,
                        "strict_24_pass": False,
                    }
                },
                "ofast_pingpong": {
                    "metrics": {
                        "total_median_ms": 47.486,
                        "fps_median": 21.059,
                        "strict_24_pass": False,
                    }
                },
            },
            "decision": {
                "classification": "visual_neutral_target_handoff_near_miss",
                "quality_impact": "none_detected_no_codec_parameter_change",
                "ofast_real_write_gap_ms": 0.974,
                "pingpong_rejected": True,
                "pingpong_regression_ms": 4.845,
                "recommended_next": "Do not pursue scatter-pingpong writer.",
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_prealloc_probe_GP017602_60f_20260618/summary.json",
        {
            "schema": "mission1_t236_prealloc_probe.v1",
            "cases": {
                "baseline": {"metrics": {"total_median_ms": 42.783, "write_median_ms": 3.259, "strict_24_pass": False}},
                "prealloc": {"metrics": {"total_median_ms": 43.282, "write_median_ms": 2.906, "strict_24_pass": False}},
            },
            "decision": {
                "classification": "rejected_visual_neutral_storage_preallocation",
                "quality_impact": "none_detected_no_codec_parameter_change",
                "total_regression_ms": 0.499,
                "write_delta_ms": -0.353,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_sdwrite_probe_GP017602_60f_20260618/summary.json",
        {
            "schema": "mission1_t236_sdwrite_probe.v1",
            "metrics": {
                "total_median_ms": 42.656,
                "encode_median_ms": 39.547,
                "write_median_ms": 3.191,
                "fps_median": 23.443,
                "strict_24_pass": False,
            },
            "decision": {
                "classification": "visual_neutral_sd_write_near_miss",
                "quality_impact": "none_detected_no_codec_parameter_change",
                "storage_interpretation": "Pi root microSD write is similar to SSD-write near-miss.",
                "strict_24_gap_ms": 0.989,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_lto_probe_GP017602_60f_20260618/summary.json",
        {
            "schema": "mission1_t236_lto_probe.v1",
            "cases": {
                "lto_no_write": {"metrics": {"total_median_ms": 38.976, "strict_24_pass": True}},
                "lto_real_write": {"metrics": {"total_median_ms": 42.860, "write_median_ms": 3.054, "strict_24_pass": False}},
            },
            "decision": {
                "classification": "rejected_visual_neutral_lto_build_variant",
                "quality_impact": "none_detected_no_codec_parameter_change",
                "lto_real_write_gap_ms": 1.193,
            },
        },
    )
    write_json(
        artifact_root / "current_sync_t236_exact_encode_pgo_ofast_20260618/summary.json",
        {
            "schema": "gpr_pi_t236_exact_pgo_layout_probe.v1",
            "profile": "T236 q8 native12 exact knobs; train on encode-only GP017602; compare Ofast baseline vs PGO-use",
            "compiler": "gcc",
            "frames_train": 240,
            "frames_eval": 120,
            "profile_gcda_count": 7,
            "baseline_encode_only": {
                "fps_median": 22.68,
                "encode": {"median_ms": 44.091},
                "write": {"median_ms": 0.0},
                "total": {"median_ms": 44.091},
                "payload_kib": {"median_ms": 5483.862},
            },
            "pgo_encode_only": {
                "fps_median": 22.60,
                "encode": {"median_ms": 44.257},
                "write": {"median_ms": 0.0},
                "total": {"median_ms": 44.257},
                "payload_kib": {"median_ms": 5483.862},
            },
            "baseline_real_write": {
                "fps_median": 21.53,
                "encode": {"median_ms": 42.766},
                "write": {"median_ms": 3.578},
                "total": {"median_ms": 46.442},
                "payload_kib": {"median_ms": 5483.862},
            },
            "pgo_real_write": {
                "fps_median": 21.49,
                "encode": {"median_ms": 42.924},
                "write": {"median_ms": 3.394},
                "total": {"median_ms": 46.543},
                "payload_kib": {"median_ms": 5483.862},
            },
            "byte_identical_gvid": True,
            "encode_only_delta_ms": 0.166,
            "real_write_total_delta_ms": 0.101,
        },
    )
    write_json(
        artifact_root / "current_goal_t236_layoutalign_probe_GP017602_120f_20260618/summary.json",
        {
            "schema": "mission1_t236_layout_alignment_probe.v1",
            "profile": "current native12 FLL2 T233 strict-24 120f GP017602; GCC layout/alignment flags versus current build",
            "flags": "-Ofast -DNDEBUG -freorder-blocks -freorder-blocks-and-partition -falign-functions=32 -falign-loops=32 -falign-labels=16",
            "baseline": {
                "total_median_ms": 43.397,
                "encode_median_ms": 40.113,
                "write_median_ms": 3.253,
                "fps_median": 23.044,
                "payload_kib_median": 5440.82,
                "verdict": {"gvid_valid": True, "storage_target_met": True},
                "strict_24_pass": False,
            },
            "layoutalign": {
                "total_median_ms": 44.054,
                "encode_median_ms": 40.122,
                "write_median_ms": 3.910,
                "fps_median": 22.709,
                "payload_kib_median": 5440.82,
                "verdict": {"gvid_valid": True, "storage_target_met": True},
                "strict_24_pass": False,
            },
            "total_delta_ms": 0.657,
            "encode_delta_ms": 0.009,
            "write_delta_ms": 0.657,
            "fps_delta": -0.335,
            "quality_impact": "none_detected_codec_parameters_unchanged",
            "decision": "reject_no_strict24_or_no_sustained_win",
        },
    )
    write_json(
        artifact_root / "current_sync_t236_ionice_probe_20260618/summary.json",
        {
            "schema": "mission1_t236_ionice_probe.v1",
            "profile": "T236 q8 native12 direct scatter .gvid; process ionice variants",
            "frames": 120,
            "decision": "reject_no_timing_win",
            "cases": {
                "baseline": {
                    "fps_median": 22.81,
                    "encode": {"median_ms": 40.056},
                    "write": {"median_ms": 3.589},
                    "total": {"median_ms": 43.84},
                    "payload_kib": {"median_ms": 5483.862},
                    "gvid_sha256": "same",
                },
                "ionice_idle": {
                    "fps_median": 20.55,
                    "encode": {"median_ms": 44.265},
                    "write": {"median_ms": 3.835},
                    "total": {"median_ms": 48.661},
                    "payload_kib": {"median_ms": 5483.862},
                    "gvid_sha256": "same",
                    "delta_total_vs_baseline_ms": 4.821,
                    "byte_identical_to_baseline": True,
                },
                "ionice_best_effort_low": {
                    "fps_median": 22.13,
                    "encode": {"median_ms": 41.433},
                    "write": {"median_ms": 3.688},
                    "total": {"median_ms": 45.179},
                    "payload_kib": {"median_ms": 5483.862},
                    "gvid_sha256": "same",
                    "delta_total_vs_baseline_ms": 1.339,
                    "byte_identical_to_baseline": True,
                },
            },
        },
    )
    for name, total, encode, write, fps, sync_enabled in (
        ("baseline", 43.148, 39.845, 3.265, 23.180, False),
        ("sync_range", 44.230, 40.951, 3.236, 22.609, True),
    ):
        write_json(
            artifact_root
            / f"current_goal_t236_syncrange_probe_GP017602_120f_20260618/{name}/labs_target_bench.json",
            {
                "schema": "gpr_labs_target_bench.v1",
                "timing": {"fps_median": fps},
                "bench_phase_timing": {
                    "phase_ms": {
                        "encode": {"median_ms": encode},
                        "write": {"median_ms": write},
                        "total": {"median_ms": total},
                        "payload_kib": {"median": 5382.972},
                    }
                },
                "verdict": {
                    "fps_target_met": False,
                    "gvid_valid": True,
                    "storage_target_met": True,
                },
                "bench": {
                    "env_overrides": {"GPR_BENCH_GVID_SYNC_RANGE": "1"} if sync_enabled else {},
                },
            },
        )
    write_json(
        artifact_root / "current_goal_t236_neonzero_GP017602_120f_20260618/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "timing": {"fps_median": 21.549},
            "bench_phase_timing": {
                "phase_ms": {
                    "encode": {"median_ms": 42.727},
                    "write": {"median_ms": 3.640},
                    "total": {"median_ms": 46.407},
                    "payload_kib": {"median": 5382.972},
                }
            },
            "verdict": {
                "fps_target_met": False,
                "gvid_valid": True,
                "storage_target_met": True,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_pwritev_probe_GP017602_120f_20260618/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "timing": {"fps_median": 22.828},
            "bench_phase_timing": {
                "phase_ms": {
                    "encode": {"median_ms": 40.158},
                    "write": {"median_ms": 3.607},
                    "total": {"median_ms": 43.809},
                    "payload_kib": {"median": 5382.972},
                }
            },
            "verdict": {
                "fps_target_met": False,
                "gvid_valid": True,
                "storage_target_met": True,
            },
            "bench": {
                "env_overrides": {
                    "GPR_BENCH_GVID_SCATTER": "1",
                    "GPR_BENCH_GVID_PWRITEV": "1",
                },
            },
        },
    )
    for rel, decision, baseline_total, candidate_total, delta in (
        (
            "current_goal_t236_coalesce_probe_GP017602_240f_20260618/summary.json",
            "promote_for_target_probe",
            43.249,
            42.376,
            -0.873,
        ),
        (
            "current_goal_t236_coalesce_native_probe_GP017602_240f_20260618/summary.json",
            "reject_no_timing_win",
            42.403,
            42.598,
            0.195,
        ),
    ):
        write_json(
            artifact_root / rel,
            {
                "schema": "mission1_t236_coalesced_header_probe.v1",
                "visual_quality_impact": "none_byte_layout_only",
                "decision": decision,
                "delta_coalesce_minus_baseline_ms": delta,
                "cases": {
                    "baseline": {
                        "fps_median": 1000.0 / baseline_total,
                        "strict24_total_pass": False,
                        "phases": {
                            "encode": {"median_ms": 38.971},
                            "write": {"median_ms": 3.484},
                            "total": {"median_ms": baseline_total},
                            "payload_kib": {"median_ms": 5483.862},
                        },
                    },
                    "coalesce": {
                        "fps_median": 1000.0 / candidate_total,
                        "strict24_total_pass": False,
                        "phases": {
                            "encode": {"median_ms": 38.987},
                            "write": {"median_ms": 3.602},
                            "total": {"median_ms": candidate_total},
                            "payload_kib": {"median_ms": 5483.862},
                        },
                    },
                },
            },
        )
    write_json(
        artifact_root / "current_goal_t236_dontneed_probe_GP017602_240f_20260618/summary.json",
        {
            "schema": "mission1_t236_dontneed_probe.v1",
            "candidate": "posix_fadvise_dontneed_after_direct_gvid_frame_write",
            "profile": "t236_ch2lh3",
            "source_image": "GP017602",
            "frames": 240,
            "decision": "rejected_no_timing_win",
            "classification": "rejected_visual_neutral_posix_fadvise_dontneed",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "source_change_reverted": True,
            "baseline": {
                "total_median_ms": 44.264,
                "encode_median_ms": 40.554,
                "write_median_ms": 3.638,
                "fps_median": 22.593764121102577,
                "wall_fps": 22.330284304502523,
                "payload_kib_median": 5388.797,
                "fps_target_met": False,
                "storage_target_met": True,
                "gvid_valid": True,
                "no_drops": True,
                "interruption_recovery_proven": True,
            },
            "candidate_metrics": {
                "total_median_ms": 44.966,
                "encode_median_ms": 40.641,
                "write_median_ms": 4.29,
                "fps_median": 22.241992882562275,
                "wall_fps": 22.02749854739465,
                "payload_kib_median": 5388.797,
                "fps_target_met": False,
                "storage_target_met": True,
                "gvid_valid": True,
                "no_drops": True,
                "interruption_recovery_proven": True,
            },
            "delta_candidate_minus_baseline_ms": {
                "total": 0.702,
                "encode": 0.087,
                "write": 0.652,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_timing_detail_30f_20260618/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "timing": {"fps_median": 22.69, "median_ms": 44.065},
            "fused_timing": {
                "dominant_stage_by_mean_ms": "pass1",
                "stage_ms": {"total": {"median_ms": 39.9}},
            },
            "bench_phase_timing": {
                "dominant_phase_by_mean_ms": "encode",
                "phase_ms": {
                    "encode": {"median_ms": 39.946},
                    "write": {"median_ms": 3.737},
                    "total": {"median_ms": 44.087},
                    "payload_kib": {"median": 5483.862},
                },
            },
            "verdict": {
                "fps_target_met": False,
                "gvid_valid": True,
                "storage_target_met": True,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_pin_probe_20260618/summary.json",
        {
            "schema": "mission1_t236_pin_probe_summary.v1",
            "classification": "rejected_visual_neutral_scheduler_pinning",
            "bytestream_policy": "codec parameters unchanged; no quality impact expected",
            "decision": "rejected_target_total_regression",
            "baseline": {
                "total_median_ms": 42.560,
                "encode_median_ms": 39.238,
                "write_median_ms": 3.547,
                "fps_median": 23.496,
                "strict_24_pass": False,
            },
            "pinned": {
                "total_median_ms": 43.745,
                "encode_median_ms": 40.088,
                "write_median_ms": 3.527,
                "fps_median": 22.860,
                "strict_24_pass": False,
            },
            "total_delta_ms": 1.185,
            "encode_delta_ms": 0.850,
            "write_delta_ms": -0.020,
        },
    )
    write_json(
        artifact_root / "current_goal_t236_scatter_async_probe_20260618/summary.json",
        {
            "schema": "mission1_t236_scatter_async_copy_probe.v1",
            "classification": "rejected_visual_neutral_scatter_async_copy_writer",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "decision": "rejected_target_total_and_wall_regression",
            "baseline": {
                "total_median_ms": 43.640,
                "encode_median_ms": 40.053,
                "write_median_ms": 3.601,
                "fps_median": 22.915,
                "wall_fps": 22.396,
                "strict_24_pass": False,
            },
            "async_copy": {
                "total_median_ms": 47.120,
                "encode_median_ms": 45.542,
                "write_median_ms": 1.373,
                "fps_median": 21.222,
                "wall_fps": 20.736,
                "strict_24_pass": False,
            },
            "total_delta_ms": 3.480,
            "encode_delta_ms": 5.489,
            "write_delta_ms": -2.228,
            "wall_fps_delta": -1.659,
        },
    )
    write_json(
        artifact_root / "current_goal_writer_core_probe_GP017602_60f_20260619_t236s264_recorded/summary.json",
        {
            "schema": "gpr.writer_core_probe.v1",
            "decision": "reject_writer_core_pinning_not_strict24_closure",
            "reason": (
                "Scatter baseline remained faster than ping-pong writer variants; pinning the writer "
                "did not close strict 24 fps and worsened ping-pong in this 60-frame Pi probe."
            ),
            "rows": [
                {
                    "name": "pingpong_core0",
                    "total_median_ms": 49.356,
                    "encode_median_ms": 49.352,
                    "write_median_ms": 0.004,
                    "fps_median": 20.362,
                    "wall_fps": 19.543,
                    "fps_target_met": False,
                    "pingpong_drain_ms": 3.514,
                },
                {
                    "name": "pingpong_core3",
                    "total_median_ms": 47.954,
                    "encode_median_ms": 47.950,
                    "write_median_ms": 0.004,
                    "fps_median": 20.927,
                    "wall_fps": 19.841,
                    "fps_target_met": False,
                    "pingpong_drain_ms": 3.527,
                },
                {
                    "name": "pingpong_nopin",
                    "total_median_ms": 48.022,
                    "encode_median_ms": 48.018,
                    "write_median_ms": 0.004,
                    "fps_median": 20.982,
                    "wall_fps": 19.876,
                    "fps_target_met": False,
                    "pingpong_drain_ms": 3.124,
                },
                {
                    "name": "scatter_baseline",
                    "total_median_ms": 44.487,
                    "encode_median_ms": 41.257,
                    "write_median_ms": 3.072,
                    "fps_median": 22.482,
                    "wall_fps": 21.382,
                    "fps_target_met": False,
                },
            ],
        },
    )
    write_json(
        artifact_root / "current_goal_t236_llrice_sweep_GP017602_30f_20260618/summary.json",
        {
            "schema": "mission1_t236_llrice_sweep.v1",
            "profile": "current no-pin T236 q8 native12; exact LL Rice KS sweep; visual-neutral by construction",
            "frames": 30,
            "decision": "no_short_strict24_pass",
            "rows": [
                {
                    "case": "k6556",
                    "ks": "6,5,5,6",
                    "total_median_ms": 43.299,
                    "encode_median_ms": 40.145,
                    "write_median_ms": 3.138,
                    "payload_kib_median": 5435.399,
                    "fps_median": 23.105,
                    "strict_24_pass": False,
                    "storage_target_met": True,
                    "gvid_valid": True,
                    "delta_total_vs_k6656_ms": -0.568,
                    "delta_payload_vs_k6656_kib": -48.463,
                },
                {
                    "case": "k6656",
                    "ks": "6,6,5,6",
                    "total_median_ms": 43.867,
                    "encode_median_ms": 39.758,
                    "write_median_ms": 3.884,
                    "payload_kib_median": 5483.862,
                    "fps_median": 22.886,
                    "strict_24_pass": False,
                    "storage_target_met": True,
                    "gvid_valid": True,
                    "delta_total_vs_k6656_ms": 0.0,
                    "delta_payload_vs_k6656_kib": 0.0,
                },
            ],
        },
    )
    write_json(
        artifact_root / "current_goal_t236_llrice_k6556_ab_GP017602_120f_20260618/summary.json",
        {
            "schema": "mission1_t236_llrice_k6556_ab.v1",
            "profile": "current no-pin T236 q8 native12; exact LL Rice k6556 sustained A/B",
            "frames": 120,
            "decision": "reject_k6556_no_sustained_win",
            "baseline": {
                "case": "baseline",
                "ks": "6,6,5,6",
                "total_median_ms": 43.015,
                "encode_median_ms": 39.529,
                "write_median_ms": 3.351,
                "payload_kib_median": 5483.862,
                "fps_median": 23.259,
                "strict_24_pass": False,
                "storage_target_met": True,
                "gvid_valid": True,
            },
            "candidate": {
                "case": "candidate",
                "ks": "6,5,5,6",
                "total_median_ms": 46.993,
                "encode_median_ms": 43.403,
                "write_median_ms": 3.488,
                "payload_kib_median": 5435.399,
                "fps_median": 21.283,
                "strict_24_pass": False,
                "storage_target_met": True,
                "gvid_valid": True,
            },
            "deltas": {
                "total_ms": 3.978,
                "encode_ms": 3.874,
                "write_ms": 0.137,
                "payload_kib": -48.463,
                "fps": -1.975,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_writev_index_probe_GP017602_240f_ba_20260618/summary.json",
        {
            "schema": "gpr.writev_index_probe.v1",
            "frames": 240,
            "order": "candidate_then_baseline",
            "classification": "visual_neutral_near_miss_not_strict24",
            "quality_impact": "none_detected_payload_and_codec_settings_unchanged",
            "baseline": {
                "total_median_ms": 46.270,
                "encode_median_ms": 42.318,
                "write_median_ms": 3.850,
                "payload_kib_median": 5483.862,
                "fps_median": 21.612,
                "strict_24_pass": False,
                "gvid_valid": True,
            },
            "candidate": {
                "total_median_ms": 45.895,
                "encode_median_ms": 42.251,
                "write_median_ms": 3.593,
                "payload_kib_median": 5483.862,
                "fps_median": 21.789,
                "strict_24_pass": False,
                "gvid_valid": True,
            },
            "delta_total_ms": -0.375,
            "delta_encode_ms": -0.067,
            "delta_write_ms": -0.257,
        },
    )
    write_json(
        artifact_root / "current_goal_t236_coalesce_index_probe_GP017602_240f_ab_20260618/summary.json",
        {
            "schema": "gpr.coalesce_index_probe.v1",
            "frames": 240,
            "primary_order": "baseline_then_candidate",
            "secondary_order": "candidate_then_baseline",
            "classification": "visual_neutral_near_miss_not_strict24",
            "quality_impact": "none_detected_payload_and_codec_settings_unchanged",
            "payload_unchanged": True,
            "all_gvid_valid": True,
            "primary": {
                "baseline": {
                    "total_median_ms": 44.753,
                    "encode_median_ms": 41.105,
                    "write_median_ms": 3.574,
                    "payload_kib_median": 5483.862,
                    "fps_median": 22.349,
                    "strict_24_pass": False,
                    "gvid_valid": True,
                },
                "candidate": {
                    "total_median_ms": 44.273,
                    "encode_median_ms": 40.663,
                    "write_median_ms": 3.571,
                    "payload_kib_median": 5483.862,
                    "fps_median": 22.594,
                    "strict_24_pass": False,
                    "gvid_valid": True,
                },
                "total_delta_ms": -0.480,
                "encode_delta_ms": -0.442,
                "write_delta_ms": -0.003,
                "fps_median_delta": 0.245,
            },
            "secondary": {
                "total_delta_ms": -0.921,
                "fps_median_delta": 0.471,
            },
        },
    )
    write_json(
        artifact_root / "current_goal_t236_coalesce_scout_20260619/summary.json",
        {
            "schema": "gpr.t236_coalesce_scout.v1",
            "frames": 60,
            "rows": [
                {
                    "case": "baseline",
                    "total_median_ms": 43.206,
                    "encode_median_ms": 39.565,
                    "write_median_ms": 3.797,
                    "payload_kib_median": 5483.862,
                    "fps_median": 23.145,
                    "fps_target_met": False,
                    "storage_target_met": True,
                    "gvid_valid": True,
                },
                {
                    "case": "writev",
                    "total_median_ms": 43.950,
                    "encode_median_ms": 39.924,
                    "write_median_ms": 3.964,
                    "payload_kib_median": 5483.862,
                    "fps_median": 22.753,
                    "fps_target_met": False,
                    "storage_target_met": True,
                    "gvid_valid": True,
                    "delta_total_vs_baseline_ms": 0.744,
                },
                {
                    "case": "coalesce",
                    "total_median_ms": 44.289,
                    "encode_median_ms": 40.669,
                    "write_median_ms": 3.623,
                    "payload_kib_median": 5483.862,
                    "fps_median": 22.581,
                    "fps_target_met": False,
                    "storage_target_met": True,
                    "gvid_valid": True,
                    "delta_total_vs_baseline_ms": 1.083,
                },
                {
                    "case": "coalesce_writev",
                    "total_median_ms": 44.509,
                    "encode_median_ms": 40.715,
                    "write_median_ms": 3.641,
                    "payload_kib_median": 5483.862,
                    "fps_median": 22.497,
                    "fps_target_met": False,
                    "storage_target_met": True,
                    "gvid_valid": True,
                    "delta_total_vs_baseline_ms": 1.303,
                },
            ],
        },
    )
    write_json(
        artifact_root / "current_goal_t236_partition_abab_probe_20260619/summary.json",
        {
            "schema": "mission1_t236_partition_abab_probe.v1",
            "binary": "/mnt/ssd/gpr_work/build-codegen-ofast-20260618/source/app/bench_fused/bench_fused",
            "raw": "/mnt/ssd/gpr_work/fixtures/mission1/GP017602.raw",
            "frames_per_case": 120,
            "profile": {
                "width": 4096,
                "height": 3072,
                "quality": 8,
                "pixel_format": 1,
                "wavelet_levels": 1,
                "scatter_direct_gvid": True,
                "env": "native12_t236_quality_boundary",
            },
            "case_order": [
                "a_encode_only",
                "b_direct_gvid",
                "c_encode_only",
                "d_direct_gvid",
            ],
            "cases": {
                "a_encode_only": {
                    "mode": "encode_only",
                    "phases": {
                        "encode": {"median": 42.193},
                        "write": {"median": 0.0},
                        "total": {"median": 42.194},
                        "payload_kib": {"median": 5483.862},
                    },
                    "wall": {"wall_fps": 22.2},
                    "capture_size_bytes": 0,
                },
                "b_direct_gvid": {
                    "mode": "direct_gvid",
                    "phases": {
                        "encode": {"median": 39.54},
                        "write": {"median": 3.58},
                        "total": {"median": 43.11},
                        "payload_kib": {"median": 5483.862},
                    },
                    "wall": {"wall_fps": 22.8},
                    "capture_size_bytes": 673858880,
                },
                "c_encode_only": {
                    "mode": "encode_only",
                    "phases": {
                        "encode": {"median": 42.555},
                        "write": {"median": 0.0},
                        "total": {"median": 42.556},
                        "payload_kib": {"median": 5483.862},
                    },
                    "wall": {"wall_fps": 21.7},
                    "capture_size_bytes": 0,
                },
                "d_direct_gvid": {
                    "mode": "direct_gvid",
                    "phases": {
                        "encode": {"median": 39.565},
                        "write": {"median": 3.516},
                        "total": {"median": 43.195},
                        "payload_kib": {"median": 5483.862},
                    },
                    "wall": {"wall_fps": 22.6},
                    "capture_size_bytes": 673858880,
                },
            },
            "analysis": {
                "encode_only_total_median_of_medians_ms": 42.375,
                "encode_only_encode_median_of_medians_ms": 42.374,
                "direct_gvid_total_median_of_medians_ms": 43.1525,
                "direct_gvid_encode_median_of_medians_ms": 39.5525,
                "direct_gvid_write_median_of_medians_ms": 3.548,
                "direct_minus_encode_total_ms": 0.7775,
                "strict24_frame_ms": 41.6666666667,
                "direct_loop_gap_ms": 1.4858333333,
                "interpretation": "diagnostic_partition_only_not_release_receipt",
            },
        },
    )
    write_json(
        artifact_root / "current_goal_writer_handoff_t236_GP017602_60f_20260618/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "timing": {"n": 60, "fps_median": 23.38087444470423, "median_ms": 42.77},
            "target": {"actual_wall_fps": 22.366398583812945},
            "verdict": {
                "fps_target_met": False,
                "fps_median_target_met": False,
                "fps_wall_target_met": False,
                "gvid_valid": True,
                "storage_target_met": True,
            },
            "bench_phase_timing": {
                "phase_ms": {
                    "encode": {"median_ms": 39.48},
                    "write": {"median_ms": 3.391},
                    "total": {"median_ms": 42.774},
                    "payload_kib": {"median": 5483.862},
                },
            },
            "writer_handoff": {
                "wall_includes_writer_drain": True,
                "deferred_writer_phase_names": [],
                "deferred_writer_drain_ms": 0.0,
                "deferred_writer_work_present": False,
                "loop_fps_median": 23.378687988030112,
                "wall_fps": 22.366398583812945,
                "target_fps": 24.0,
                "fps_target_met": False,
            },
            "storage": {"target": {"fits_target": True}},
        },
    )
    write_json(
        artifact_root / "current_goal_gap_receipt_t236_GP017602_240f_20260618/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "timing": {"n": 240, "fps_median": 22.946305644791188, "median_ms": 43.58},
            "target": {"actual_wall_fps": 22.673859686469935},
            "verdict": {
                "fps_target_met": False,
                "fps_median_target_met": False,
                "fps_wall_target_met": False,
                "gvid_valid": True,
                "storage_target_met": True,
            },
            "bench_phase_timing": {
                "phase_ms": {
                    "encode": {"median_ms": 40.195},
                    "write": {"median_ms": 3.393},
                    "total": {"median_ms": 43.579},
                    "payload_kib": {"median": 5483.862},
                },
            },
            "writer_handoff": {
                "wall_includes_writer_drain": True,
                "deferred_writer_phase_names": [],
                "deferred_writer_drain_ms": 0.0,
                "deferred_writer_work_present": False,
                "loop_fps_median": 22.946832189816195,
                "loop_median_ms": 43.579,
                "wall_fps": 22.673859686469935,
                "wall_ms_per_frame": 44.10365124543508,
                "target_fps": 24.0,
                "target_frame_ms": 41.666666666666664,
                "loop_target_gap_ms": 1.9123333333333363,
                "wall_target_gap_ms": 2.436984578768417,
                "bottleneck_target_gap_ms": 2.436984578768417,
                "fps_target_met": False,
            },
            "storage": {"target": {"fits_target": True}},
        },
    )
    write_json(
        artifact_root / "current_goal_provenance_t236_GP017602_240f_20260618/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "timing": {"n": 240, "fps_median": 22.996435552489366, "median_ms": 43.485},
            "target": {"actual_wall_fps": 22.45577516031339},
            "verdict": {
                "fps_target_met": False,
                "fps_median_target_met": False,
                "fps_wall_target_met": False,
                "gvid_valid": True,
                "storage_target_met": True,
            },
            "bench_phase_timing": {
                "phase_ms": {
                    "encode": {"median_ms": 39.82},
                    "write": {"median_ms": 3.533},
                    "total": {"median_ms": 43.492},
                    "payload_kib": {"median": 5440.82},
                },
            },
            "storage": {"target": {"fits_target": True}},
            "source_provenance": {
                "available": True,
                "sha256": "eac88f91c8717d40f0bf5197422f9e03fd6c50c15af1b209565c16403f08ce6d",
                "file_count": 565,
            },
            "bench": {
                "build": {
                    "binary_sha256": "e034bcc62f1733cff3878234622a8378f1707e4d0e38b32b732e21d2f7321994",
                    "encoder_c_flags": "-std=c99 -Ofast -DNDEBUG -mcpu=native",
                    "bench_c_flags": "-std=c99 -Ofast -DNDEBUG -mcpu=native",
                }
            },
        },
    )
    write_json(artifact_root / "mission1_single_pingpong_isolation_20260617/summary.json", [
        {
            "name": "contiguous_dbuf",
            "encode_median": 42.005,
            "write_median": 0.0,
            "total_median": 42.006,
            "payload_kib_median": 5440.82,
        },
        {
            "name": "scatter_dbuf",
            "encode_median": 40.62,
            "write_median": 0.0,
            "total_median": 40.62,
            "payload_kib_median": 5440.82,
        },
        {
            "name": "scatter_no_dbuf",
            "encode_median": 40.612,
            "write_median": 0.0,
            "total_median": 40.612,
            "payload_kib_median": 5440.82,
        },
    ])


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_write_contention_", dir=work_parent) as td:
        external_root = Path(td)
        build_fixture(external_root)
        tool = import_tool()
        summary = tool.build_summary(external_root)

    assert summary["blocker_class"] == "block_write_cache_contention"
    assert summary["best_no_block_case"]["name"] == "scatter_no_dbuf"
    assert summary["best_no_block_case"]["strict_24_pass"] is True
    assert summary["real_block_write_case"]["name"] == "pingpong_ssd"
    assert summary["real_block_write_case"]["strict_24_pass"] is False
    assert summary["block_write_penalty_ms"] > 5.0
    latest = summary["latest_t236_boundary"]
    assert latest["blocker_class"] == "visual_neutral_write_handoff_margin"
    assert latest["visual_quality_impact"] == "none_detected_quality_storage_boundary"
    assert latest["encode_only_best_case"]["strict_24_pass"] is True
    assert latest["real_write_best_case"]["strict_24_pass"] is False
    assert 0.8 < latest["strict_24_total_gap_ms"] < 0.9
    clean = summary["fresh_t236_clean_pi_probe"]
    assert clean["classification"] == "visual_neutral_target_handoff_near_miss"
    assert clean["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert clean["ofast_no_write"]["strict_24_pass"] is True
    assert clean["ofast_real_write"]["strict_24_pass"] is False
    assert 0.9 < clean["ofast_real_write_gap_ms"] < 1.1
    assert clean["pingpong"]["rejected"] is True
    assert clean["pingpong"]["regression_ms"] > 4.0
    followups = summary["recent_t236_followup_probes"]
    sustained = followups["current_source_t236_sustained_240f"]
    assert sustained["classification"] == "visual_neutral_sustained_current_source_strict24_miss"
    assert sustained["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert sustained["frames"] == 240
    assert sustained["metrics"]["strict_24_pass"] is False
    assert sustained["metrics"]["gvid_valid"] is True
    assert sustained["metrics"]["storage_target_met"] is True
    assert sustained["storage_fits_target"] is True
    assert 1.8 < sustained["strict_24_gap_ms"] < 1.9
    assert sustained["actual_wall_fps"] < sustained["metrics"]["fps_median"]
    assert sustained["binary_sha256"] == "e034bcc62f1733cff3878234622a8378f1707e4d0e38b32b732e21d2f7321994"
    assert sustained["source_provenance_sha256"] == "eac88f91c8717d40f0bf5197422f9e03fd6c50c15af1b209565c16403f08ce6d"
    assert sustained["source_provenance_file_count"] == 565
    assert followups["writer_handoff_t236"]["classification"] == "visual_neutral_writer_handoff_not_deferred_drain"
    assert followups["writer_handoff_t236"]["fps_target_met"] is False
    assert followups["writer_handoff_t236"]["storage_fits_target"] is True
    assert followups["writer_handoff_t236"]["deferred_writer_work_present"] is False
    assert followups["writer_handoff_t236"]["writer_handoff"]["deferred_writer_drain_ms"] == 0.0
    assert followups["writer_handoff_t236"]["encode_median_ms"] > followups["writer_handoff_t236"]["write_median_ms"] * 10
    assert 1.0 < followups["writer_handoff_t236"]["strict_24_gap_ms"] < 1.2
    assert followups["explicit_gap_t236_240f"]["classification"] == "visual_neutral_explicit_loop_wall_gap_receipt"
    assert followups["explicit_gap_t236_240f"]["fps_target_met"] is False
    assert followups["explicit_gap_t236_240f"]["storage_fits_target"] is True
    assert followups["explicit_gap_t236_240f"]["loop_target_gap_ms"] > 1.9
    assert followups["explicit_gap_t236_240f"]["wall_target_gap_ms"] > 2.4
    assert followups["explicit_gap_t236_240f"]["bottleneck_target_gap_ms"] == followups["explicit_gap_t236_240f"]["wall_target_gap_ms"]
    assert followups["prealloc"]["rejected"] is True
    assert followups["prealloc"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["prealloc"]["candidate"]["total_median_ms"] > followups["prealloc"]["baseline"]["total_median_ms"]
    assert followups["prealloc"]["write_delta_ms"] < 0.0
    assert followups["sdwrite"]["classification"] == "visual_neutral_sd_write_near_miss"
    assert followups["sdwrite"]["metrics"]["strict_24_pass"] is False
    assert 0.9 < followups["sdwrite"]["strict_24_gap_ms"] < 1.1
    assert followups["lto"]["rejected"] is True
    assert followups["lto"]["no_write"]["strict_24_pass"] is True
    assert followups["lto"]["real_write"]["strict_24_pass"] is False
    assert 1.0 < followups["lto"]["real_write_gap_ms"] < 1.3
    assert followups["exact_encode_pgo"]["rejected"] is True
    assert followups["exact_encode_pgo"]["classification"] == "rejected_visual_neutral_gcc_pgo_code_layout"
    assert followups["exact_encode_pgo"]["quality_impact"] == "none_byte_identical_gvid"
    assert followups["exact_encode_pgo"]["compiler"] == "gcc"
    assert followups["exact_encode_pgo"]["profile_gcda_count"] == 7
    assert followups["exact_encode_pgo"]["byte_identical_gvid"] is True
    assert followups["exact_encode_pgo"]["baseline_encode_only"]["strict_24_pass"] is False
    assert followups["exact_encode_pgo"]["pgo_encode_only"]["strict_24_pass"] is False
    assert followups["exact_encode_pgo"]["pgo_real_write"]["strict_24_pass"] is False
    assert followups["exact_encode_pgo"]["encode_only_delta_ms"] > 0.0
    assert followups["exact_encode_pgo"]["real_write_total_delta_ms"] > 0.0
    assert followups["layout_alignment"]["rejected"] is True
    assert followups["layout_alignment"]["classification"] == "rejected_visual_neutral_gcc_layout_alignment_flags"
    assert followups["layout_alignment"]["quality_impact"] == "none_detected_codec_parameters_unchanged"
    assert followups["layout_alignment"]["candidate"]["verdict"]["gvid_valid"] is True
    assert followups["layout_alignment"]["candidate"]["payload_kib_median"] == followups["layout_alignment"]["baseline"]["payload_kib_median"]
    assert followups["layout_alignment"]["candidate"]["strict_24_pass"] is False
    assert followups["layout_alignment"]["total_delta_ms"] > 0.0
    assert followups["layout_alignment"]["write_delta_ms"] > 0.0
    assert followups["layout_alignment"]["fps_delta"] < 0.0
    assert followups["ionice"]["rejected"] is True
    assert followups["ionice"]["classification"] == "rejected_visual_neutral_process_io_priority"
    assert followups["ionice"]["quality_impact"] == "none_byte_identical_gvid"
    assert followups["ionice"]["byte_identical_gvid"] is True
    assert followups["ionice"]["ionice_idle"]["strict_24_pass"] is False
    assert followups["ionice"]["ionice_best_effort_low"]["strict_24_pass"] is False
    assert followups["ionice"]["ionice_idle_total_delta_ms"] > 4.0
    assert followups["ionice"]["ionice_best_effort_low_total_delta_ms"] > 1.0
    assert followups["sync_range"]["rejected"] is True
    assert followups["sync_range"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["sync_range"]["candidate"]["gvid_valid"] is True
    assert followups["sync_range"]["candidate"]["storage_target_met"] is True
    assert followups["sync_range"]["candidate"]["total_median_ms"] > followups["sync_range"]["baseline"]["total_median_ms"]
    assert followups["sync_range"]["total_delta_ms"] > 1.0
    assert followups["neon_zero_scan"]["rejected"] is True
    assert followups["neon_zero_scan"]["classification"] == "rejected_visual_neutral_neon_zero_scan"
    assert followups["neon_zero_scan"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["neon_zero_scan"]["candidate"]["gvid_valid"] is True
    assert followups["neon_zero_scan"]["candidate"]["storage_target_met"] is True
    assert followups["neon_zero_scan"]["candidate"]["payload_kib_median"] == followups["neon_zero_scan"]["baseline"]["payload_kib_median"]
    assert followups["neon_zero_scan"]["encode_delta_ms"] > 2.0
    assert followups["neon_zero_scan"]["total_delta_ms"] > 3.0
    assert followups["pwritev"]["rejected"] is True
    assert followups["pwritev"]["classification"] == "rejected_visual_neutral_explicit_offset_pwritev"
    assert followups["pwritev"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["pwritev"]["candidate"]["gvid_valid"] is True
    assert followups["pwritev"]["candidate"]["storage_target_met"] is True
    assert followups["pwritev"]["candidate"]["strict_24_pass"] is False
    assert followups["pwritev"]["candidate"]["payload_kib_median"] == followups["pwritev"]["baseline"]["payload_kib_median"]
    assert 0.6 < followups["pwritev"]["total_delta_ms"] < 0.8
    assert 0.3 < followups["pwritev"]["write_delta_ms"] < 0.4
    assert followups["coalesced_header"]["rejected"] is True
    assert followups["coalesced_header"]["classification"] == "rejected_visual_neutral_coalesced_header"
    assert followups["coalesced_header"]["quality_impact"] == "none_byte_layout_only"
    assert followups["coalesced_header"]["initial_decision"] == "promote_for_target_probe"
    assert followups["coalesced_header"]["native_repeat_decision"] == "reject_no_timing_win"
    assert followups["coalesced_header"]["initial"]["candidate"]["strict_24_pass"] is False
    assert followups["coalesced_header"]["initial"]["total_delta_ms"] < 0.0
    assert followups["coalesced_header"]["native_repeat"]["candidate"]["strict_24_pass"] is False
    assert followups["coalesced_header"]["native_repeat"]["total_delta_ms"] > 0.0
    assert (
        followups["coalesced_header"]["native_repeat"]["candidate"]["payload_kib_median"]
        == followups["coalesced_header"]["native_repeat"]["baseline"]["payload_kib_median"]
    )
    assert followups["dontneed"]["rejected"] is True
    assert followups["dontneed"]["classification"] == "rejected_visual_neutral_posix_fadvise_dontneed"
    assert followups["dontneed"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["dontneed"]["source_change_reverted"] is True
    assert followups["dontneed"]["candidate"]["gvid_valid"] is True
    assert followups["dontneed"]["candidate"]["storage_target_met"] is True
    assert followups["dontneed"]["candidate"]["fps_target_met"] is False
    assert (
        followups["dontneed"]["candidate"]["payload_kib_median"]
        == followups["dontneed"]["baseline"]["payload_kib_median"]
    )
    assert followups["dontneed"]["total_delta_ms"] > 0.0
    assert followups["dontneed"]["write_delta_ms"] > 0.0
    assert followups["timing_detail_current_t236"]["classification"] == "stage_split_current_t236"
    assert followups["timing_detail_current_t236"]["fused_total_strict_24_pass"] is True
    assert followups["timing_detail_current_t236"]["metrics"]["strict_24_pass"] is False
    assert followups["timing_detail_current_t236"]["wall_minus_fused_total_ms"] > 4.0
    assert followups["pinning"]["classification"] == "rejected_visual_neutral_scheduler_pinning"
    assert followups["pinning"]["rejected"] is True
    assert followups["pinning"]["pinned"]["strict_24_pass"] is False
    assert followups["pinning"]["total_delta_ms"] > 1.0
    assert followups["scatter_async_copy"]["classification"] == "rejected_visual_neutral_scatter_async_copy_writer"
    assert followups["scatter_async_copy"]["rejected"] is True
    assert followups["scatter_async_copy"]["async_copy"]["strict_24_pass"] is False
    assert followups["scatter_async_copy"]["total_delta_ms"] > 3.0
    assert followups["scatter_async_copy"]["encode_delta_ms"] > 5.0
    assert followups["scatter_async_copy"]["write_delta_ms"] < -2.0
    assert followups["scatter_async_copy"]["wall_fps_delta"] < -1.0
    assert followups["writer_core_pinning"]["classification"] == "rejected_visual_neutral_writer_core_pinning"
    assert followups["writer_core_pinning"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["writer_core_pinning"]["rejected"] is True
    assert followups["writer_core_pinning"]["scatter_remained_best"] is True
    assert followups["writer_core_pinning"]["all_variants_miss_strict24"] is True
    assert followups["writer_core_pinning"]["best"]["name"] == "scatter_baseline"
    assert followups["writer_core_pinning"]["best"]["total_median_ms"] < 45.0
    assert followups["writer_core_pinning"]["pingpong_variants"]["pingpong_core0"]["total_median_ms"] > 49.0
    assert followups["writer_core_pinning"]["pingpong_variants"]["pingpong_core3"]["fps_target_met"] is False
    assert followups["llrice_k6556"]["classification"] == "rejected_visual_neutral_exact_ll_rice_ks"
    assert followups["llrice_k6556"]["quality_impact"] == "none_exact_ll_entropy_parameter_only"
    assert followups["llrice_k6556"]["short_sweep_decision"] == "no_short_strict24_pass"
    assert followups["llrice_k6556"]["short_best"]["ks"] == "6,5,5,6"
    assert followups["llrice_k6556"]["short_best"]["delta_total_vs_k6656_ms"] < 0.0
    assert followups["llrice_k6556"]["rejected"] is True
    assert followups["llrice_k6556"]["candidate"]["ks"] == "6,5,5,6"
    assert followups["llrice_k6556"]["candidate"]["strict_24_pass"] is False
    assert followups["llrice_k6556"]["candidate"]["gvid_valid"] is True
    assert followups["llrice_k6556"]["payload_delta_kib"] < 0.0
    assert followups["llrice_k6556"]["total_delta_ms"] > 3.0
    assert followups["llrice_k6556"]["encode_delta_ms"] > 3.0
    assert followups["llrice_k6556"]["fps_delta"] < -1.0
    assert followups["writev_index"]["classification"] == "visual_neutral_near_miss_not_strict24"
    assert followups["writev_index"]["quality_impact"] == "none_detected_payload_and_codec_settings_unchanged"
    assert followups["writev_index"]["near_miss"] is True
    assert followups["writev_index"]["frames"] == 240
    assert followups["writev_index"]["candidate"]["strict_24_pass"] is False
    assert followups["writev_index"]["candidate"]["gvid_valid"] is True
    assert (
        followups["writev_index"]["candidate"]["payload_kib_median"]
        == followups["writev_index"]["baseline"]["payload_kib_median"]
    )
    assert followups["writev_index"]["total_delta_ms"] < 0.0
    assert followups["writev_index"]["write_delta_ms"] < 0.0
    assert followups["coalesce_index"]["classification"] == "visual_neutral_near_miss_not_strict24"
    assert followups["coalesce_index"]["quality_impact"] == "none_detected_payload_and_codec_settings_unchanged"
    assert followups["coalesce_index"]["near_miss"] is True
    assert followups["coalesce_index"]["frames"] == 240
    assert followups["coalesce_index"]["candidate"]["strict_24_pass"] is False
    assert followups["coalesce_index"]["candidate"]["gvid_valid"] is True
    assert followups["coalesce_index"]["payload_unchanged"] is True
    assert followups["coalesce_index"]["all_gvid_valid"] is True
    assert (
        followups["coalesce_index"]["candidate"]["payload_kib_median"]
        == followups["coalesce_index"]["baseline"]["payload_kib_median"]
    )
    assert followups["coalesce_index"]["total_delta_ms"] < 0.0
    assert followups["coalesce_index"]["secondary_total_delta_ms"] < 0.0
    assert followups["coalesce_scout"]["classification"] == "rejected_visual_neutral_coalesce_writev_scout"
    assert followups["coalesce_scout"]["quality_impact"] == "none_detected_payload_and_codec_settings_unchanged"
    assert followups["coalesce_scout"]["rejected"] is True
    assert followups["coalesce_scout"]["all_variants_valid"] is True
    assert followups["coalesce_scout"]["all_variants_miss_strict24"] is True
    assert followups["coalesce_scout"]["all_variants_regress_total"] is True
    assert followups["coalesce_scout"]["best_variant"]["case"] == "writev"
    assert followups["coalesce_scout"]["variants"]["coalesce"]["delta_total_vs_baseline_ms"] > 1.0
    assert followups["partition_abab"]["classification"] == "diagnostic_visual_neutral_encode_write_partition"
    assert followups["partition_abab"]["quality_impact"] == "none_detected_no_codec_parameter_change"
    assert followups["partition_abab"]["diagnostic_only"] is True
    assert followups["partition_abab"]["production_receipt"] is False
    assert followups["partition_abab"]["strict_24_pass"] is False
    assert followups["partition_abab"]["direct_loop_gap_ms"] > 1.0
    assert followups["partition_abab"]["direct_minus_encode_total_ms"] > 0.0
    assert followups["partition_abab"]["direct_gvid_cases"]["b_direct_gvid"]["write_median_ms"] > 3.0
    assert "threshold tuning" in summary["production_direction"]

    print("test_mission1_write_contention_summary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
