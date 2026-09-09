#!/usr/bin/env python3
"""Smoke-test Mission 1 native12 frontier classification."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/mission1_native12_frontier_summary.py"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def import_tool():
    spec = importlib.util.spec_from_file_location("mission1_native12_frontier_summary_smoke", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def receipt(path: Path, *, fps: float, target_met: bool, frames: int = 120) -> None:
    write_json(path, {
        "schema": "gpr_labs_target_bench.v1",
        "timing": {
            "n": frames,
            "median_ms": 1000.0 / fps,
            "p95_ms": (1000.0 / fps) + 2.0,
            "fps_median": fps,
            "actual_wall_fps": fps - 0.25,
        },
        "verdict": {
            "fps_target_met": target_met,
            "fps_median_target_met": target_met,
            "fps_wall_target_met": target_met,
            "no_drops": True,
            "gvid_valid": True,
            "interruption_recovery_proven": True,
            "storage_target_met": True,
            "target_evidence": True,
        },
        "storage": {
            "total_frame_bytes": 123456789,
            "gvid_bytes": 123457000,
            "write_MBps_wall": 110.0,
        },
    })


def jans_receipt(path: Path, *, stripe_rows: int, max_symbol_freq: int, overflow_symbols: int) -> None:
    write_json(path, {
        "schema": "gpr_labs_target_bench.v1",
        "jans_inline_profile": {
            "available": True,
            "by_label": {
                "unlabeled": {
                    "max_symbol_freq": {"max": max_symbol_freq},
                    "overflow_symbols": {"max": overflow_symbols},
                    "stripe_rows": {"max": stripe_rows},
                },
            },
        },
    })


def build_fixture(external_root: Path) -> None:
    artifact_root = external_root / "artifacts"
    write_json(artifact_root / "mission1_native12_threshold_quality_matrix_20260618/summary.json", {
        "schema": "mission1_native12_threshold_quality_matrix.v1",
        "quality_floor_psnr14": 75.0,
        "storage_budget_MBps_at_24fps": 135.0,
        "summary": [
            {
                "config": "t236_ch2lh3",
                "min_psnr14": 75.0644,
                "mean_psnr14": 81.215,
                "mean_MiB": 5.2159,
                "max_required_MBps_at_24fps": 134.7714,
                "quality_floor_pass": True,
                "storage_24fps_pass": True,
                "rows": [{"image": "GP017603", "psnr": 75.0644}],
            },
            {
                "config": "t356_ch2lh3",
                "min_psnr14": 61.4308,
                "mean_psnr14": 67.3676,
                "mean_MiB": 4.6596,
                "max_required_MBps_at_24fps": 120.2922,
                "quality_floor_pass": False,
                "storage_24fps_pass": True,
                "rows": [{"image": "GP017603", "psnr": 61.4308}],
            },
            {
                "config": "t468_ch2lh4",
                "min_psnr14": 58.7738,
                "mean_psnr14": 64.6405,
                "mean_MiB": 4.1634,
                "max_required_MBps_at_24fps": 106.5718,
                "quality_floor_pass": False,
                "storage_24fps_pass": True,
                "rows": [{"image": "GP017603", "psnr": 58.7738}],
            },
        ],
    })
    receipt(
        artifact_root / "mission1_hardened_fps_gate_lh3_k6656_GP017602_120f_24fps_20260618/labs_target_bench.json",
        fps=22.99,
        target_met=False,
    )
    write_json(artifact_root / "mission1_t238_quality_local_20260618/summary.json", {
        "profile": "T238",
        "rows": [
            {"image": "GP017601", "bytes": 5469415, "psnr14": 84.51, "pass_75db": True},
            {"image": "GP017602", "bytes": 5569005, "psnr14": 85.18, "pass_75db": True},
            {"image": "GP017603", "bytes": 5197873, "psnr14": 75.38, "pass_75db": True},
        ],
        "all_pass_75db": True,
    })
    receipt(
        artifact_root / "mission1_ch2lh3_t238_GP017602_120f_24fps_20260618/labs_target_bench.json",
        fps=22.87,
        target_met=False,
    )
    write_json(artifact_root / "mission1_native12_t244_quality_dashboard_20260618/summary.json", {
        "schema": "mission1_native12_quality_dashboard.v1",
        "profile_id": "mission1_native12_t244_lh2_hl4_hh4_k7555_probe",
        "all_pass": False,
        "rows": [
            {"stem": "GP017601", "encoded_bytes": 4883365, "metrics": {"psnr14": 69.874}},
            {"stem": "GP017602", "encoded_bytes": 5000612, "metrics": {"psnr14": 71.2149}},
            {"stem": "GP017603", "encoded_bytes": 4745497, "metrics": {"psnr14": 61.5243}},
        ],
    })
    receipt(
        artifact_root / "mission1_t244_GP017602_120f_24fps_20260618/labs_target_bench.json",
        fps=24.83,
        target_met=True,
    )
    receipt(
        artifact_root / "mission1_native12_t356_ch2lh3_GP017602_120f_24fps_20260618/labs_target_bench.json",
        fps=24.11,
        target_met=True,
    )
    receipt(
        artifact_root / "mission1_native12_t468_ch2lh4_GP017602_120f_24fps_20260618/labs_target_bench.json",
        fps=28.86,
        target_met=True,
    )
    for stem, fps in (("GP017601", 24.51), ("GP017602", 25.32), ("GP017603", 23.97)):
        receipt(
            artifact_root / f"mission1_native12_q0_l1_labs_1440f_20260616_{stem}/labs_target_bench.json",
            fps=fps,
            target_met=fps >= 24.0,
            frames=1440,
        )
    jans_receipt(
        artifact_root / "mission1_jans_freq_audit_20260618/GP017601/labs_target_bench.json",
        stripe_rows=384,
        max_symbol_freq=83935,
        overflow_symbols=2,
    )
    jans_receipt(
        artifact_root / "mission1_jans_freq_audit_20260618/GP017602/labs_target_bench.json",
        stripe_rows=384,
        max_symbol_freq=91437,
        overflow_symbols=2,
    )
    jans_receipt(
        artifact_root / "mission1_jans_freq_audit_20260618/GP017603/labs_target_bench.json",
        stripe_rows=384,
        max_symbol_freq=71066,
        overflow_symbols=1,
    )
    write_json(artifact_root / "mission1_jans_freq_audit_20260618/stripe_sweep/summary.json", {
        "256": {"max_symbol_freq": 63759, "overflow_symbols_max": 0, "per_image": {}},
    })
    write_json(artifact_root / "mission1_jans_freq_audit_20260618/stripe_refine/summary.json", {
        "272": {"max_symbol_freq": 67100, "overflow_symbols_max": 1, "per_image": {}},
    })
    write_json(artifact_root / "mission1_jans_freq_audit_20260618/stripe_fine/summary.json", {
        "260": {"max_symbol_freq": 64645, "overflow_symbols_max": 0, "per_image": {}},
        "264": {"max_symbol_freq": 65524, "overflow_symbols_max": 0, "per_image": {}},
        "268": {"max_symbol_freq": 66319, "overflow_symbols_max": 1, "per_image": {}},
    })
    write_json(artifact_root / "mission1_stripe264_quality_20260618/summary.json", {
        "schema": "mission1_native12_current_profile_quality.v1",
        "profile_id": "mission1_native12_fll2_t233_avg7555_fast_pinp2_20fps_v1",
        "profile_env": {"FUSED_STRIPE_ROWS": "264"},
        "all_pass": True,
        "passes_20fps_storage_budget_all": True,
        "rows": [
            {"image": "GP017601", "PSNR14_dB": 84.51, "required_MBps_at_24fps": 126.99},
            {"image": "GP017602", "PSNR14_dB": 85.13, "required_MBps_at_24fps": 131.06},
            {"image": "GP017603", "PSNR14_dB": 75.35, "required_MBps_at_24fps": 123.84},
        ],
    })
    write_json(artifact_root / "mission1_stripe264_timing_20260618/summary.json", {
        "GP017601": {"fps_median": 21.18, "wall_fps": 20.06, "fps_target_met": False, "storage_target_met": True},
        "GP017602": {"fps_median": 20.44, "wall_fps": 18.86, "fps_target_met": False, "storage_target_met": True},
        "GP017603": {"fps_median": 22.24, "wall_fps": 20.73, "fps_target_met": False, "storage_target_met": True},
    })
    write_json(artifact_root / "current_goal_jans_freq_saturate_probe_20260618/summary.json", {
        "schema": "mission1_jans_freq_saturate_probe.v1",
        "candidate": "inline_jans_saturating_uint16_frequency_increment",
        "decision": "rejected_for_current_strict24_path",
        "source_change_reverted": True,
        "quality_impact": "none_detected_decoded_bayer_byte_identical",
        "local_ab": {
            "decoded_delta_saturating_vs_wrap": {
                "byte_identical": True,
                "max_abs": 0,
            },
            "delta": {
                "bytes": -97347,
                "total_median_ms": 0.233,
            },
        },
        "pi_metrics": {
            "fps_target_met": False,
            "gvid_valid": True,
            "storage_target_met": True,
            "total_median_ms": 43.32,
            "fps_median": 23.08,
            "payload_kib_median": 5388.797,
        },
    })


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_frontier_", dir=work_parent) as td:
        external_root = Path(td)
        build_fixture(external_root)
        tool = import_tool()
        summary = tool.build_summary(external_root)

    by_config = {row["config"]: row for row in summary["frontier"]}
    assert by_config["t236_ch2lh3"]["production_status"] == "fps_fail"
    assert by_config["t236_ch2lh3"]["quality"]["quality_floor_pass"] is True
    assert by_config["t236_ch2lh3"]["quality"]["storage_24fps_pass"] is True
    assert by_config["t236_ch2lh3"]["cnn_recovery_policy"]["cnn_recovery_allowed"] is True
    assert by_config["t236_ch2lh3"]["cnn_recovery_policy"]["decoded_bayer_status"] == "valid_quality_storage_boundary"
    assert by_config["t238_ch2lh3"]["production_status"] == "fps_fail"
    assert by_config["t238_ch2lh3"]["quality"]["quality_floor_pass"] is True
    assert by_config["t238_ch2lh3"]["quality"]["storage_24fps_pass"] is True
    assert by_config["t238_ch2lh3"]["performance"]["fps_target_met"] is False
    assert by_config["t238_ch2lh3"]["cnn_recovery_policy"]["cnn_recovery_allowed"] is True
    assert by_config["t244_lh2_hl4_hh4"]["production_status"] == "quality_fail"
    assert by_config["t244_lh2_hl4_hh4"]["quality"]["quality_floor_pass"] is False
    assert by_config["t244_lh2_hl4_hh4"]["quality"]["storage_24fps_pass"] is True
    assert by_config["t244_lh2_hl4_hh4"]["quality"]["min_psnr14"] == 61.5243
    assert by_config["t244_lh2_hl4_hh4"]["performance"]["fps_target_met"] is True
    assert by_config["t244_lh2_hl4_hh4"]["cnn_recovery_policy"]["cnn_recovery_allowed"] is False
    assert by_config["t244_lh2_hl4_hh4"]["cnn_recovery_policy"]["decoded_bayer_status"] == "codec_quality_failure"
    assert "do_not_hide_with_cnn" in by_config["t244_lh2_hl4_hh4"]["cnn_recovery_policy"]["policy"]
    assert by_config["t356_ch2lh3"]["production_status"] == "quality_fail"
    assert by_config["t356_ch2lh3"]["performance"]["fps_target_met"] is True
    assert by_config["t356_ch2lh3"]["cnn_recovery_policy"]["cnn_recovery_allowed"] is False
    assert by_config["t468_ch2lh4"]["production_status"] == "quality_fail"
    assert by_config["t468_ch2lh4"]["performance"]["fps_median"] == 28.86
    assert by_config["t468_ch2lh4"]["cnn_recovery_policy"]["cnn_recovery_allowed"] is False
    assert len(summary["legacy_fast_q0_l1"]) == 3
    assert {
        row["production_status"] for row in summary["legacy_fast_q0_l1"]
    } == {"invalid_legacy_no_quality_boundary_or_current_provenance"}
    entropy = summary["entropy_safety"]
    assert summary["schema"] == "mission1_native12_frontier_summary.v2"
    assert entropy["schema"] == "mission1_native12_entropy_safety.v1"
    assert entropy["production_status"] == "raw_count_over_uint16_diagnostic"
    assert entropy["practical_blocker"] is False
    assert entropy["current_profile"]["stripe_rows"] == 384
    assert entropy["current_profile"]["entropy_counter_safe"] is False
    assert entropy["current_profile"]["max_symbol_freq"] == 91437
    assert entropy["current_profile"]["overflow_symbols_max"] == 2
    assert entropy["stripe_sweep"]["largest_no_overflow"]["rows"] == 264
    assert entropy["stripe_sweep"]["first_overflow_above_safe"]["rows"] == 268
    assert entropy["safe_stripe"]["quality_profile_env_matches"] is True
    assert entropy["safe_stripe"]["quality"]["all_pass"] is True
    assert entropy["safe_stripe"]["quality"]["min_psnr14"] == 75.35
    assert entropy["safe_stripe"]["timing"]["all_storage_target_met"] is True
    assert entropy["safe_stripe"]["timing"]["all_fps_target_met"] is False
    assert entropy["safe_stripe"]["timing"]["min_fps_median"] == 20.44
    freq_sat = entropy["frequency_saturation_candidate"]
    assert freq_sat["schema"] == "mission1_jans_freq_saturate_probe.v1"
    assert freq_sat["decision"] == "rejected_for_current_strict24_path"
    assert freq_sat["source_change_reverted"] is True
    assert freq_sat["quality_impact"] == "none_detected_decoded_bayer_byte_identical"
    assert freq_sat["local_ab"]["decoded_delta_saturating_vs_wrap"]["byte_identical"] is True
    assert freq_sat["local_ab"]["delta"]["bytes"] < 0
    assert freq_sat["pi_metrics"]["fps_target_met"] is False
    assert freq_sat["pi_metrics"]["gvid_valid"] is True
    assert freq_sat["pi_metrics"]["storage_target_met"] is True
    assert "not a visual-quality blocker" in entropy["decision"]

    print("test_mission1_native12_frontier_summary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
