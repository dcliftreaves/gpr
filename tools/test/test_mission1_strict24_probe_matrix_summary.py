#!/usr/bin/env python3
"""Regression test for Mission 1 strict-24 probe-matrix summary."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/mission1_strict24_probe_matrix_summary.py"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def import_tool():
    spec = importlib.util.spec_from_file_location("mission1_strict24_probe_matrix_summary", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def receipt(total: float, fps: float, wall_fps: float, payload: float, *, instrumented: bool = False) -> dict:
    payload_obj = {"median": payload}
    out = {
        "target": {"actual_wall_fps": wall_fps},
        "timing": {"n": 240, "median_ms": total, "fps_median": fps},
        "writer_handoff": {
            "loop_target_gap_ms": total - (1000.0 / 24.0),
            "wall_target_gap_ms": (1000.0 / wall_fps) - (1000.0 / 24.0),
        },
        "bench_phase_timing": {
            "phase_ms": {
                "encode": {"median_ms": total - 3.5},
                "write": {"median_ms": 3.5},
                "total": {"median_ms": total},
                "payload_kib": payload_obj,
            }
        },
        "storage": {"target": {"fits_target": True, "bytes_per_frame": payload * 1024, "budget_bytes_per_frame": 5625000}},
        "bench": {"build": {"binary_sha256": "b" * 64}},
        "source_provenance": {"sha256": "a" * 64},
        "verdict": {
            "fps_target_met": total <= 1000.0 / 24.0 and wall_fps >= 24.0,
            "storage_target_met": True,
            "gvid_valid": True,
            "no_drops": True,
            "interruption_recovery_proven": True,
        },
    }
    if instrumented:
        out["fused_timing"] = {
            "available": True,
            "timing_line_count": 12,
            "channel_component_by_channel_ms": {
                "0": {"total": {"median_ms": 34.0}, "tokenize": {"median_ms": 21.0}, "unpack": {"median_ms": 7.0}},
                "3": {"total": {"median_ms": 35.0}, "tokenize": {"median_ms": 22.0}, "unpack": {"median_ms": 7.2}},
            },
        }
        out["jans_inline_profile"] = {
            "available": True,
            "profile_line_count": 8,
            "by_label": {
                "ch3_b0": {
                    "overflow_symbols": {"max": 2},
                    "max_symbol_freq": {"max": 91437},
                },
                "ch0_b0": {
                    "overflow_symbols": {"max": 1},
                    "max_symbol_freq": {"max": 88000},
                }
            },
        }
    else:
        out["fused_timing"] = {"available": False, "timing_line_count": 0}
        out["jans_inline_profile"] = {"available": False, "profile_line_count": 0}
    return out


def test_summary(tmp_path: Path) -> None:
    module = import_tool()
    root = tmp_path
    artifact = root / "artifacts"
    write_json(
        artifact / "current_goal_strict24_probe_matrix_20260619/current_source_sustained_repeat_240f/labs_target_bench.json",
        receipt(44.2, 22.6, 22.2, 5388.8),
    )
    write_json(
        artifact / "current_goal_strict24_probe_matrix_20260619/encoder_hotrow_profile_30f/labs_target_bench.json",
        receipt(49.0, 20.4, 20.0, 5388.8, instrumented=True),
    )
    write_json(
        artifact / "current_goal_strict24_probe_matrix_20260619/production_profile_labeled_hotrow_30f/labs_target_bench.json",
        receipt(49.4, 20.2, 18.7, 5345.8, instrumented=True),
    )
    write_json(
        artifact / "current_goal_strict24_probe_matrix_20260619/legacy_policy_ab_240f/labs_target_bench.json",
        receipt(42.8, 23.4, 22.9, 5345.8),
    )
    write_json(
        artifact / "current_goal_strict24_probe_matrix_20260619/production_profile_240f/labs_target_bench.json",
        receipt(43.5, 23.0, 21.4, 5345.8),
    )
    write_json(
        artifact / "current_goal_strict24_probe_matrix_20260619/production_profile_repeat2_240f/labs_target_bench.json",
        receipt(43.4, 23.0, 22.7, 5345.8),
    )
    write_json(
        artifact / "current_goal_provenance_t236_GP017602_240f_20260618/labs_target_bench.json",
        receipt(43.4, 23.0, 22.5, 5388.8),
    )
    summary = module.build_summary(root)
    assert summary["schema"] == "mission1_strict24_probe_matrix_summary.v1"
    assert summary["strict24_closed"] is False
    assert summary["decision"] == "strict24_still_open_current_source_regressed"
    assert summary["current_vs_previous"]["total_median_ms_delta"] > 0.0
    production = summary["production_profile_summary"]
    assert production["count"] == 3
    assert production["strict24_any_closed"] is False
    assert production["best"]["total_median_ms"] == 42.8
    assert production["latest"]["total_median_ms"] == 43.4
    assert production["latest_total_gap_ms"] > 1.0
    assert production["latest_wall_gap_ms"] > 1.0
    assert summary["production_profile_best_vs_current"]["total_median_ms_delta"] < 0.0
    assert summary["production_profile_latest_vs_current"]["total_median_ms_delta"] < 0.0
    assert summary["legacy_policy_repeat"]["fps_target_met"] is False
    assert summary["legacy_policy_vs_current"]["total_median_ms_delta"] < 0.0
    assert summary["legacy_policy_vs_current"]["payload_kib_median_delta"] < 0.0
    hot = summary["hotrow_diagnostics"]
    assert hot["instrumented"] is True
    assert hot["channel_rank_by_tokenize"][0]["channel"] == "3"
    assert hot["jans_label_rank_by_overflow"][0]["label"] == "ch3_b0"
    assert hot["overflow_symbols_max"] == 2.0
    prod_hot = summary["production_profile_labeled_hotrow_diagnostics"]
    assert prod_hot["instrumented"] is True
    assert prod_hot["jans_label_rank_by_overflow"][0]["label"] == "ch3_b0"
    assert "production T233 profile" in summary["next_target"]
    assert "tokenization hot path" in summary["next_target"]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        test_summary(Path(td))
    print("test_mission1_strict24_probe_matrix_summary: PASS")
