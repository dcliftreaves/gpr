#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/mission1_strict24_gap_report.py"


def test_gap_report_cli() -> None:
    default_tmp = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    tmp_parent = os.environ.get("GPR_TMPDIR")
    if tmp_parent is None and default_tmp.exists():
        tmp_parent = str(default_tmp)
    if tmp_parent is None:
        tmp_parent = os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(dir=tmp_parent) as td:
        root = Path(td)
        summary = {
            "schema": "mission1_write_contention_summary.v1",
            "latest_t236_boundary": {
                "blocker_class": "visual_neutral_write_handoff_margin",
                "visual_quality_impact": "none_detected_quality_storage_boundary",
                "source_receipts": {"real_write": "/x/real.json"},
                "real_write_best_case": {
                    "total_median_ms": 42.5,
                    "encode_median_ms": 38.7,
                    "write_median_ms": 3.7,
                    "fps_median": 23.5,
                    "payload_kib_median": 5400.0,
                    "storage_target_met": True,
                    "gvid_valid": True,
                },
            },
            "recent_t236_followup_probes": {
                "prealloc": {
                    "classification": "rejected_visual_neutral_storage_preallocation",
                    "quality_impact": "none_detected_no_codec_parameter_change",
                    "rejected": True,
                    "decision": "rejected_no_timing_win",
                    "source_receipt": "/x/prealloc.json",
                    "total_delta_ms": 0.5,
                    "write_delta_ms": -0.35,
                },
                "explicit_gap_t236_240f": {
                    "classification": "visual_neutral_explicit_loop_wall_gap_receipt",
                    "quality_impact": "none_detected_no_codec_parameter_change",
                    "source_receipt": "/x/gap.json",
                    "actual_wall_fps": 22.5,
                    "metrics": {
                        "total_median_ms": 43.5,
                        "encode_median_ms": 40.0,
                        "write_median_ms": 3.4,
                        "fps_median": 23.0,
                        "payload_kib_median": 5400.0,
                        "storage_target_met": True,
                        "gvid_valid": True,
                    },
                }
            },
        }
        summary_path = root / "write_summary.json"
        out_path = root / "gap.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--write-summary",
                str(summary_path),
                "--output",
                str(out_path),
            ],
            check=True,
            cwd=ROOT,
        )
        report = json.loads(out_path.read_text(encoding="utf-8"))
        assert report["schema"] == "mission1_strict24_gap_report.v1"
        assert report["decision"] == "strict24_open_wall_throughput_gap"
        assert report["best_loop_candidate"]["name"] == "t236_quality_storage_boundary_real_write"
        assert report["best_wall_candidate"]["name"] == "explicit_gap_t236_240f"
        assert report["required_loop_reduction_ms"] > 0.8
        assert report["required_wall_reduction_ms"] > report["required_loop_reduction_ms"]
        plan = report["optimization_plan"]
        assert plan["status"] == "visual_quality_and_storage_are_not_the_current_blocker"
        assert plan["dominant_gap"] == "wall"
        assert "prealloc" in plan["do_not_repeat"]
        rejected = {row["name"]: row for row in plan["already_rejected"]}
        assert rejected["prealloc"]["classification"] == "rejected_visual_neutral_storage_preallocation"
        assert any(row["name"] == "explicit_gap_t236_240f" for row in plan["near_miss_candidates"])
        probes = {row["probe_id"]: row for row in plan["next_probe_matrix"]}
        assert list(probes) == [
            "current_source_sustained_repeat_240f",
            "encoder_hotrow_profile_30f",
            "camera_like_handoff_floor_240f",
            "indexed_writev_plus_clean_source_ab_240f",
            "target_hardware_or_20fps_decision_receipt",
        ]
        assert probes["current_source_sustained_repeat_240f"]["env"]["FUSED_QUALITY"] == "8"
        assert probes["current_source_sustained_repeat_240f"]["env"]["GPR_INLINE_DENOISE_HARD"] == "1"
        assert probes["current_source_sustained_repeat_240f"]["env"]["GPR_INLINE_DENOISE_T_CH2_LH"] == "3"
        assert probes["encoder_hotrow_profile_30f"]["env"]["JANS_INLINE_PROFILE"] == "1"
        assert probes["camera_like_handoff_floor_240f"]["acceptance"]["wall_save_ms_needed"] > 0.0
        assert probes["indexed_writev_plus_clean_source_ab_240f"]["acceptance"]["both_orders_win"] is True
        assert probes["target_hardware_or_20fps_decision_receipt"]["frames"] == 14400
        assert any("whole-run wall throughput" in item for item in plan["acceptance_criteria"])


if __name__ == "__main__":
    test_gap_report_cli()
    print("test_mission1_strict24_gap_report: PASS")
